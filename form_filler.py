"""
form_filler.py  --  Unified Google Form Filler
Contains both backends:
  - HTTP     : fast httpx-based submissions, more CAPTCHAs
  - Chromium : Selenium Chrome, slower, fewer CAPTCHAs (normal / headless / turbo)

Terminal usage:  python form_filler.py
UI usage:        python ui.py  (imports this file)

Setup:
    pip install playwright httpx selenium webdriver-manager screeninfo
    playwright install chromium
    Optional (Linux/macOS): pip install uvloop

--- CHANGE LOG -----------------------------------------------------------
[merged] Combined form_filler_http.py + v6flood.py into one file.
  - HTTP backend:     all logic under "HTTP BACKEND" section
  - Chromium backend: all logic under "CHROMIUM BACKEND" section
  - Shared main():    prompts for backend choice first, then routes to the
                      appropriate terminal flow (http_main / chromium_main)
  - ui.py imports this file and uses both backends directly

[v6flood fixes carried over]
  - prevent_sleep / allow_sleep guarded with _IS_WINDOWS check
  - ctypes.wintypes import guarded so file loads on Linux/macOS without error

[http fixes carried over -- see original form_filler_http.py changelog]
  All 18 bug fixes from the HTTP backend are preserved unchanged.
--------------------------------------------------------------------------
"""

# ===========================================================================
# SHARED IMPORTS
# ===========================================================================
import re
import sys
import os
import json
import time
import random
import string
import asyncio
import logging
import platform
import threading
import subprocess
import signal
import atexit
import ctypes
import struct
import httpx
from enum import IntEnum
from urllib.parse import urlencode
# [FIX] Guard playwright import -- missing install disables CAPTCHA helper instead of crashing the module
try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

# ===========================================================================
# PLATFORM SETUP
# ===========================================================================
OS         = platform.system()
_IS_WINDOWS = OS == "Windows"

if OS == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
elif OS in ("Linux", "Darwin"):
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

# Guard Windows-only ctypes
if _IS_WINDOWS:
    import ctypes.wintypes


# ===========================================================================
# ANSWER TRACKING CALLBACK
# [NEW] Called once per successful _resolve_planned() call (i.e. once per
# submission attempt that passes validation).  ui.py registers a function here
# to count which options were selected for each question so the Analytics tab
# can draw live pie / bar charts without touching the submission hot-path.
# Signature: callback(resolved: list[dict]) -> None
# 'resolved' is the list of fully-resolved answer dicts (same structure as
# the return value of _resolve_planned).
# ===========================================================================
_answer_tracked_callback = None

def set_answer_tracked_callback(fn):
    """Register (or clear with None) the per-submission answer tracking hook."""
    global _answer_tracked_callback
    _answer_tracked_callback = fn


# ===========================================================================
# SLEEP PREVENTION  (HTTP backend -- cross-platform)
# ===========================================================================
_caffeinate_proc = None

def prevent_sleep_http(keep_system=True, keep_screen=False):
    global _caffeinate_proc
    if not keep_system and not keep_screen:
        return
    if OS == "Windows":
        flags = 0x80000000
        if keep_system: flags |= 0x00000001
        if keep_screen: flags |= 0x00000002
        try: ctypes.windll.kernel32.SetThreadExecutionState(flags)
        except Exception: pass
    elif OS == "Darwin":
        args = ["caffeinate"]
        if keep_system: args.append("-i")
        if keep_screen: args.append("-d")
        try: _caffeinate_proc = subprocess.Popen(args)
        except FileNotFoundError: pass
    elif OS == "Linux":
        try:
            what = []
            if keep_system: what.append("sleep")
            if keep_screen: what.append("idle")
            _caffeinate_proc = subprocess.Popen(
                ["systemd-inhibit", f"--what={':'.join(what)}", "--who=form_filler",
                 "--why=Submitting forms", "--mode=block", "sleep", "infinity"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError: pass

def allow_sleep_http():
    global _caffeinate_proc
    if OS == "Windows":
        try: ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        except Exception: pass
    elif _caffeinate_proc:
        try: _caffeinate_proc.terminate(); _caffeinate_proc = None
        except Exception: pass

atexit.register(allow_sleep_http)


# ===========================================================================
# SLEEP PREVENTION  (Chromium backend -- Windows only)
# ===========================================================================
def prevent_sleep_chromium():
    """Windows-only sleep prevention for Chromium backend."""
    if not _IS_WINDOWS:
        return
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(
            0x80000000 | 0x00000001)  # CONTINUOUS | SYSTEM_REQUIRED
    except Exception:
        pass

def allow_sleep_chromium():
    if not _IS_WINDOWS:
        return
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    except Exception:
        pass


# ===========================================================================
# WINDOWS JOB OBJECT  (Chromium -- kills child procs when terminal closes)
# ===========================================================================
def _create_job_object():
    try:
        job = ctypes.windll.kernel32.CreateJobObjectW(None, None)
        info = ctypes.c_buffer(16)
        ctypes.windll.kernel32.QueryInformationJobObject(job, 9, info, 16, None)
        flags = struct.unpack_from('I', info, 4)[0] | 0x2000
        struct.pack_into('I', info, 4, flags)
        ctypes.windll.kernel32.SetInformationJobObject(job, 9, info, 16)
        ctypes.windll.kernel32.AssignProcessToJobObject(
            job, ctypes.windll.kernel32.GetCurrentProcess())
    except Exception:
        pass  # Non-Windows or permission issue, skip silently

if _IS_WINDOWS:
    _create_job_object()


# ===========================================================================
# LOGGING
# ===========================================================================
from logging.handlers import RotatingFileHandler as _RFH

# HTTP backend logger
log = logging.getLogger("form_filler")
log.setLevel(logging.DEBUG)
log.propagate = False
_fh_http = _RFH("form_filler.log", maxBytes=2*1024*1024, backupCount=3, encoding="utf-8")
_fh_http.setLevel(logging.DEBUG)
_fh_http.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_ch_http = logging.StreamHandler()
_ch_http.setLevel(logging.WARNING)
_ch_http.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
log.addHandler(_fh_http)
log.addHandler(_ch_http)

# Chromium backend logger
_chrom_logger = logging.getLogger("form_bot")
_chrom_logger.setLevel(logging.DEBUG)
_chrom_file_handler = logging.FileHandler("form_bot_log.txt", encoding="utf-8")
_chrom_file_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
_chrom_console_handler = logging.StreamHandler()
_chrom_console_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
_chrom_logger.addHandler(_chrom_file_handler)
_chrom_logger.addHandler(_chrom_console_handler)

def chrom_log(message):
    _chrom_logger.info(message)

def chrom_log_session_start():
    date_str = time.strftime("%Y-%m-%d %H:%M:%S")
    sep = "=" * 60
    with open("form_bot_log.txt", "a", encoding="utf-8") as f:
        f.write(f"\n{sep}\n  SESSION STARTED: {date_str}\n{sep}\n")


# ===========================================================================
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                         HTTP BACKEND                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# ===========================================================================

class HeavyTrafficError(Exception):
    """Raised when Google returns a heavy-traffic / unavailable interstitial."""
    pass

class ScanAbortedError(Exception):
    """[FIX issue-3] Raised by scan_form with a descriptive reason instead of sys.exit(1).
    The UI catches this and shows the real reason in the error dialog."""
    pass

# -- Enums ------------------------------------------------------------------
class QType(IntEnum):
    SHORT_TEXT    = 0
    LONG_TEXT     = 1
    RADIO         = 2
    DROPDOWN      = 3
    CHECKBOX      = 4
    LINEAR        = 5
    STAR          = 6
    GRID          = 7
    CHECKBOX_GRID = 8
    DATE          = 9
    TIME          = 10
    # [FIX issue-1] FILE_UPLOAD (13) removed -- file uploads require Google sign-in
    # and cannot be submitted via either backend.  All FILE_UPLOAD questions are
    # silently skipped during scanning and answer collection.

class VType(IntEnum):
    NUMBER   = 1
    TEXT_LEN = 2
    REGEX    = 3
    EMAIL    = 4
    URL      = 5

# -- User agents ------------------------------------------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

_UA_CH_HINTS = [
    '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    '"Chromium";v="123", "Google Chrome";v="123", "Not-A.Brand";v="8"',
    '"Chromium";v="122", "Google Chrome";v="122", "Not-A.Brand";v="24"',
    '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    '"Chromium";v="123", "Google Chrome";v="123", "Not-A.Brand";v="8"',
    None, None, None,
    '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    '"Chromium";v="124", "Microsoft Edge";v="124", "Not-A.Brand";v="99"',
    '"Chromium";v="123", "Microsoft Edge";v="123", "Not-A.Brand";v="8"',
]

_UA_PLATFORMS = [
    '"Windows"', '"Windows"', '"Windows"',
    '"macOS"', '"macOS"', '"macOS"',
    '"Windows"', '"Windows"',
    '"Linux"',
    '"Windows"', '"Windows"',
]

_ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.8",
    "en-CA,en;q=0.9,fr-CA;q=0.8",
    "en-US,en;q=0.9,fr;q=0.7",
]

def _pick_ua_bundle():
    idx = random.randrange(len(USER_AGENTS))
    return (USER_AGENTS[idx], _UA_CH_HINTS[idx], _UA_PLATFORMS[idx],
            random.choice(_ACCEPT_LANGUAGES))

# -- Random generators ------------------------------------------------------

# [SYNC] Token expansion system -- kept in sync with ui.py.
# Tokens: <*RND_N*>    <*CRND_N*>    <*LRND_N*>
#         <*ANRND_N*>  <*CANRND_N*>  <*LANRND_N*>
#         <*FRND_N*>   <*CFRND_N*>   <*LFRND_N*>
#         <*URND_N*>   <*CURND_N*>   <*LURND_N*>   (username: a-z A-Z 0-9, at most one interior _)
#         <*URLRND_N*> <*CURLRND_N*> <*LURLRND_N*> (URL-safe: a-z A-Z 0-9 _ -)
#         <*NRND_N*>   (digits only)
#         <*WRND_N*>   (lowercase letters only)
#         <*SRND_N*>   (symbols/punctuation only)
#         <*QSTN_N*>   (value of answer N in the current submission)
#         <*filename.txt*>  (random line from a .txt file)
# Range syntax works on all sized tokens: <*RND_4-8*>, <*NRND_2-5*>, etc.

_SIZE_PART = r'(\d+)(?:-(\d+))?'   # lo, optional hi -- same as ui.py

_TOKEN_PATTERN = re.compile(
    r'<\*'
    r'(?:'
    r'([CLcl]?)(RND)_'    + _SIZE_PART +    # groups 1-4 : prefix, RND,    lo, hi
    r'|([CLcl]?)(ANRND)_' + _SIZE_PART +    # groups 5-8 : prefix, ANRND,  lo, hi
    r'|([CLcl]?)(FRND)_'  + _SIZE_PART +    # groups 9-12: prefix, FRND,   lo, hi
    r'|([CLcl]?)(URND)_'  + _SIZE_PART +    # groups 13-16: prefix, URND,  lo, hi
    r'|([CLcl]?)(URLRND)_'+ _SIZE_PART +    # groups 17-20: prefix, URLRND,lo, hi
    r'|(NRND)_'           + _SIZE_PART +    # groups 21-23: NRND, lo, hi
    r'|(WRND)_'           + _SIZE_PART +    # groups 24-26: WRND, lo, hi
    r'|(SRND)_'           + _SIZE_PART +    # groups 27-29: SRND, lo, hi
    r'|(QSTN)_(\d+)'                        # groups 30-31: QSTN, question index
    r'|([^*]+\.[^*]+)'                      # group 32   : filename.ext
    r')'
    r'\*>'
)

_ALPHA_LOWER  = string.ascii_lowercase
_ALPHA_UPPER  = string.ascii_uppercase
_AN_LOWER     = string.ascii_lowercase + string.digits
_AN_UPPER     = string.ascii_uppercase + string.digits
_AN_BOTH      = string.ascii_letters   + string.digits
_FULL_ASCII   = string.ascii_letters   + string.digits + string.punctuation
_URL_CHARS    = string.ascii_letters   + string.digits + "_-"  # URLRND
_URL_CHARS_UP = string.ascii_uppercase + string.digits + "_-"  # CURLRND
_URL_CHARS_LO = string.ascii_lowercase + string.digits + "_-"  # LURLRND
_DIGITS_ONLY  = string.digits                                   # NRND
_SYMBOLS_ONLY = string.punctuation                             # SRND

# [SYNC] URND: at most one underscore, interior only (not first/last), n>=3 required
_USERNAME_BASE = string.ascii_letters + string.digits
_USERNAME_UP   = string.ascii_uppercase + string.digits
_USERNAME_LO   = string.ascii_lowercase + string.digits

def _gen_username(n: int, prefix: str) -> str:
    """Username token: a-z A-Z 0-9, at most one _ at a random interior position.
    n<3: no underscore possible (no valid interior slot)."""
    base = _USERNAME_UP if prefix == "C" else (_USERNAME_LO if prefix == "L" else _USERNAME_BASE)
    chars = random.choices(base, k=n)
    if n >= 3 and random.random() < 0.5:
        chars[random.randint(1, n - 2)] = "_"
    return ''.join(chars)

_list_cache: dict = {}

def _load_list_file(filename: str) -> list:
    """Load filename from the script folder, splitting on blank lines. Cached.
    Non-.txt files return ['invalid file type']."""
    global _list_cache
    key = filename.lower()
    if key in _list_cache:
        return _list_cache[key]
    if not filename.lower().endswith(".txt"):
        _list_cache[key] = ["invalid file type"]
        return _list_cache[key]
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, filename)
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        entries = [e.strip() for e in re.split(r'\n\s*\n', raw) if e.strip()]
        if not entries:
            entries = [f"[{filename}: empty]"]
    except FileNotFoundError:
        entries = [f"[{filename}: file not found]"]
    except Exception as e:
        entries = [f"[{filename}: error: {e}]"]
    _list_cache[key] = entries
    return entries

def _resolve_size(lo_str: str, hi_str: str | None) -> int:
    """Convert _SIZE_PART match groups to a concrete length (range or fixed)."""
    lo = max(1, min(256, int(lo_str)))
    if not hi_str:
        return lo
    hi = max(1, min(256, int(hi_str)))
    if hi < lo: lo, hi = hi, lo
    return random.randint(lo, hi)

def _expand_templates(text: str, _seen_files: frozenset = frozenset(),
                      qstn_map: dict | None = None) -> str:
    """Expand all template tokens.
    _seen_files: tracks file call stack to prevent infinite recursion.
    qstn_map:    {1: 'david', 2: 'gratsky', ...} resolved before this call;
                 <*QSTN_N*> substitutes the value of answer N."""
    def _replace(m):
        if m.group(2):    # RND family
            prefix = (m.group(1) or "").upper()
            n = _resolve_size(m.group(3), m.group(4))
            pool = _ALPHA_UPPER if prefix == "C" else _ALPHA_LOWER
            return ''.join(random.choices(pool, k=n))
        elif m.group(6):  # ANRND family
            prefix = (m.group(5) or "").upper()
            n = _resolve_size(m.group(7), m.group(8))
            pool = _AN_UPPER if prefix == "C" else (_AN_LOWER if prefix == "L" else _AN_BOTH)
            return ''.join(random.choices(pool, k=n))
        elif m.group(10): # FRND family
            prefix = (m.group(9) or "").upper()
            n = _resolve_size(m.group(11), m.group(12))
            raw = ''.join(random.choices(_FULL_ASCII, k=n))
            if prefix == "C":   return raw.upper()
            elif prefix == "L": return raw.lower()
            return raw
        elif m.group(14): # URND family
            prefix = (m.group(13) or "").upper()
            n = _resolve_size(m.group(15), m.group(16))
            return _gen_username(n, prefix)
        elif m.group(18): # URLRND family
            prefix = (m.group(17) or "").upper()
            n = _resolve_size(m.group(19), m.group(20))
            pool = _URL_CHARS_UP if prefix == "C" else (_URL_CHARS_LO if prefix == "L" else _URL_CHARS)
            return ''.join(random.choices(pool, k=n))
        elif m.group(21): # NRND
            n = _resolve_size(m.group(22), m.group(23))
            return ''.join(random.choices(_DIGITS_ONLY, k=n))
        elif m.group(24): # WRND (lowercase letters only)
            n = _resolve_size(m.group(25), m.group(26))
            return ''.join(random.choices(_ALPHA_LOWER, k=n))
        elif m.group(27): # SRND (symbols only)
            n = _resolve_size(m.group(28), m.group(29))
            return ''.join(random.choices(_SYMBOLS_ONLY, k=n))
        elif m.group(30): # QSTN_N -- value of question N in this submission
            idx = int(m.group(31))
            if qstn_map and idx in qstn_map:
                return str(qstn_map[idx])
            return m.group(0)   # token left as-is if map not available
        elif m.group(32): # filename.ext
            fname = m.group(32).strip()
            fname_key = fname.lower()
            if fname_key in _seen_files:
                return m.group(0)   # circular reference -- leave as plain text
            entries = _load_list_file(fname)
            if not entries:
                return ""
            return _expand_templates(random.choice(entries), _seen_files | {fname_key}, qstn_map)
        return m.group(0)
    return _TOKEN_PATTERN.sub(_replace, text)

_expand_rnd = _expand_templates

def _print_token_help():
    """[NEW] Print the token reference to the terminal (called with --help or 'help' at menu)."""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║              Form Filler  —  Template Token Reference            ║
╚══════════════════════════════════════════════════════════════════╝

Use tokens in any text field answer.  Each submission replaces them
with a fresh random value independently.  N = character count (1-64).

── Letters only (RND) ────────────────────────────────────────────
  <*RND_N*>      lowercase a-z               e.g. <*RND_4*>   → xqmz
  <*LRND_N*>     lowercase a-z  (= RND)      e.g. <*LRND_4*>  → bkjp
  <*CRND_N*>     UPPERCASE A-Z               e.g. <*CRND_4*>  → XQMZ

── Alphanumeric (ANRND — letters + digits) ───────────────────────
  <*ANRND_N*>    mixed-case  a-z A-Z 0-9     e.g. <*ANRND_5*>  → aB3xQ
  <*LANRND_N*>   lowercase   a-z 0-9         e.g. <*LANRND_5*> → ab3xq
  <*CANRND_N*>   UPPERCASE   A-Z 0-9         e.g. <*CANRND_5*> → AB3XQ

── Full printable ASCII (FRND — letters + digits + symbols) ──────
  <*FRND_N*>     mixed-case  a-z A-Z 0-9 + !@#…  e.g. <*FRND_5*>  → aB3!k
  <*LFRND_N*>    lowercase forced               e.g. <*LFRND_5*> → ab3!k
  <*CFRND_N*>    UPPERCASE forced               e.g. <*CFRND_5*> → AB3!K

── URL-safe (URLRND — letters + digits + _ -) ────────────────────
  <*URLRND_N*>   mixed-case  a-z A-Z 0-9 _ -   e.g. <*URLRND_8*>  → aB3_x-Qr
  <*LURLRND_N*>  lowercase forced               e.g. <*LURLRND_8*> → ab3_x-qr
  <*CURLRND_N*>  UPPERCASE forced               e.g. <*CURLRND_8*> → AB3_X-QR
  Tip: Google Drive link → https://drive.google.com/file/d/1<*URLRND_34*>/view?usp=sharing

── List file ─────────────────────────────────────────────────────
  <*filename.txt*>   Pick a random entry from filename.txt
                     (file must be in the same folder as form_filler.py)
                     Entries are separated by blank lines.
                     Non-.txt extension → outputs: invalid file type

── Question reference (QSTN) ─────────────────────────────────────
  <*QSTN_N*>         Insert the resolved value of question N (1-based).
                     Expands after all other tokens, so it captures the
                     final value of earlier questions including their
                     random tokens.
                     e.g. Q1 = <*RND_4*> → "xqmz"
                          Q3 = <*QSTN_1*>@gmail.com → "xqmz@gmail.com"

── Examples ──────────────────────────────────────────────────────
  "test<*RND_4*>123"              → testxqmz123
  "<*CRND_3*>_<*LANRND_4*>"      → ABX_b3kq
  "<*colors.txt*> is my fav"     → PURPLE is my fav
  "user<*CANRND_6*>@example.com" → userAB3XQ9@example.com
""")

def random_text(min_len=4, max_len=10):
    length = random.randint(min_len, max_len)
    split  = random.randint(2, max(2, length - 2))
    p1 = ''.join(random.choices(string.ascii_lowercase, k=split))
    p2 = ''.join(random.choices(string.ascii_lowercase, k=length - split))
    return f"{p1} {p2}"

def random_email():
    user   = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 9)))
    domain = ''.join(random.choices(string.ascii_lowercase, k=random.randint(3, 6)))
    tld    = random.choice(["com", "net", "org", "io", "co"])
    return f"{user}@{domain}.{tld}"

def random_url():
    slug = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 10)))
    tld  = random.choice(["com", "net", "org", "io"])
    path = ''.join(random.choices(string.ascii_lowercase, k=4))
    return f"https://www.{slug}.{tld}/{path}"

def random_number(min_val=1, max_val=100):
    return str(random.randint(int(min_val), int(max_val)))

def _random_date(year_range=(1990, 2005)):
    return (str(random.randint(1, 12)),
            str(random.randint(1, 28)),
            str(random.randint(year_range[0], year_range[1])))

def _random_time(hour_range=(0, 23)):
    return f"{random.randint(hour_range[0], hour_range[1]):02d}:{random.randint(0,59):02d}"

def _safe_vargs(vargs):
    if isinstance(vargs, list):          return vargs
    if isinstance(vargs, (int, float)):  return [vargs]
    return []

def _number_range(vargs):
    if not vargs: return (1, 100)
    sub = int(vargs[0])
    t1  = int(vargs[1]) if len(vargs) > 1 and vargs[1] is not None else None
    t2  = int(vargs[2]) if len(vargs) > 2 and vargs[2] is not None else None
    if sub == 1: lo = (t1+1) if t1 is not None else 1;  return (lo, lo+99)
    if sub == 2: lo = t1 if t1 is not None else 1;       return (lo, lo+99)
    if sub == 3: hi = (t1-1) if t1 is not None else 100; return (max(1,hi-99), hi)
    if sub == 4: hi = t1 if t1 is not None else 100;     return (max(1,hi-99), hi)
    if sub == 5: v  = t1 if t1 is not None else 42;      return (v, v)
    if sub == 6:
        away = (t1 + 50) if t1 is not None else 1
        if t1 is not None and away == t1: away += 1
        return (away, away + 49)
    if sub == 7: lo = t1 if t1 is not None else 1; hi = t2 if t2 is not None else lo+99; return (lo, hi)
    if sub == 8: lo = max(1,(t1-99)) if t1 is not None else 1; hi=(t1-1) if t1 is not None else 100; return (lo, max(lo, hi))
    return (1, 100)

def random_value_for(q):
    vtype = q.get("validation", {}).get("type")
    vargs = _safe_vargs(q.get("validation", {}).get("args", []))
    if vtype == VType.TEXT_LEN and vargs and vargs[0] == 102: return random_email()
    if vtype == VType.TEXT_LEN and vargs and vargs[0] == 103: return random_url()
    if vtype == VType.EMAIL:   return random_email()
    if vtype == VType.URL:     return random_url()
    if vtype == VType.NUMBER:  mn, mx = _number_range(vargs); return random_number(mn, mx)
    if vtype == VType.TEXT_LEN:
        threshold = int(vargs[1]) if len(vargs) > 1 and vargs[1] is not None else 8
        sub = int(vargs[0]) if vargs else 0
        if sub in (1, 2):   mn, mx = threshold, threshold + 6
        elif sub in (3, 4): mn, mx = max(4, threshold - 6), threshold
        elif sub == 5:      mn, mx = threshold, threshold
        else:               mn, mx = 4, 10
        return random_text(max(1, mn), max(mn + 1, mx))
    return random_text()

# -- Input helpers ----------------------------------------------------------
def get_single_choice(prompt, max_n):
    while True:
        raw = input(prompt).strip().lower()
        if raw == 'r': return 'r'
        try:
            n = int(raw)
            if 1 <= n <= max_n: return n - 1
            print(f"    Enter 1--{max_n}")
        except ValueError:
            print("    Enter a number")

def get_multi_choice(prompt, max_n):
    while True:
        raw = input(prompt).strip().lower()
        if raw == 'r': return 'r'
        try:
            picks = [int(x.strip()) - 1 for x in raw.split(",")]
            if all(0 <= p < max_n for p in picks): return picks
            print(f"    Enter numbers 1--{max_n}")
        except ValueError:
            print("    Enter numbers separated by commas e.g. 1,3")

def prompt_mode():
    print("\n  What mode would you like?")
    print("    n / normal   -- pick answers manually, submit once")
    print("    l / lazy     -- only fill required questions, submit once")
    print("    r / random   -- fully random answers, re-randomized every submission")
    print("    s / specific -- pick answers once, repeat them N times")
    while True:
        raw = input("\n  Mode: ").strip().lower()
        if raw in ("n", "normal"):   return "normal"
        if raw in ("l", "lazy"):     return "lazy"
        if raw in ("r", "random"):   return "random"
        if raw in ("s", "specific"): return "specific"
        print("  Type n, l, r, or s")

def prompt_times():
    while True:
        raw = input("  How many times to submit in total? (or 'inf'): ").strip().lower()
        if raw == "inf": return float("inf")
        try:
            n = int(raw)
            if n >= 1: return n
            print("  Enter >= 1 or 'inf'")
        except ValueError:
            print("  Enter a number or 'inf'")

def prompt_workers():
    while True:
        raw = input("  Concurrent workers (default 1): ").strip()
        if not raw: return 1
        try:
            n = int(raw)
            if n < 1: print("  Enter >= 1"); continue
            if n > 100:
                print(f"  Note: {n} workers is very high -- OS socket limits may apply.")
            return n
        except ValueError:
            print("  Enter a number")

def prompt_delay():
    print("\n  Delay between submissions:")
    print("    0 / none  -- full speed, no delay (fastest)")
    print("    n         -- fixed delay in seconds (e.g. 0.5)")
    print("    lo-hi     -- random delay range in seconds (e.g. 0.3-1.2)")
    while True:
        raw = input("  Delay (default 0): ").strip().lower()
        if not raw or raw in ("0", "none"): return (0.0, 0.0)
        if "-" in raw:
            try:
                lo, hi = raw.split("-", 1)
                lo, hi = float(lo.strip()), float(hi.strip())
                if lo >= 0 and hi >= lo: return (lo, hi)
                print("  Enter lo <= hi, both >= 0")
            except ValueError:
                print("  Format: lo-hi e.g. 0.3-1.2")
        else:
            try:
                v = float(raw)
                if v >= 0: return (v, v)
                print("  Enter >= 0")
            except ValueError:
                print("  Enter a number, or lo-hi range")

def prompt_date_range():
    print("    Enter year range for random dates (e.g. 1990-2005, or press Enter for default):")
    while True:
        raw = input("    Year range (default 1990-2005): ").strip()
        if not raw: return (1990, 2005)
        if "-" in raw:
            try:
                lo, hi = raw.split("-", 1)
                lo, hi = int(lo.strip()), int(hi.strip())
                if 1900 <= lo <= hi <= 2100: return (lo, hi)
                print("    Enter a valid range e.g. 1990-2005")
            except ValueError:
                print("    Format: YYYY-YYYY e.g. 1980-2000")
        else:
            print("    Format: YYYY-YYYY e.g. 1980-2000")

def prompt_time_range():
    print("    Enter hour range for random times (0-23, e.g. 9-17 for business hours):")
    while True:
        raw = input("    Hour range (default 0-23): ").strip()
        if not raw: return (0, 23)
        if "-" in raw:
            try:
                lo, hi = raw.split("-", 1)
                lo, hi = int(lo.strip()), int(hi.strip())
                if 0 <= lo <= hi <= 23: return (lo, hi)
                print("    Enter 0-23 range e.g. 9-17")
            except ValueError:
                print("    Format: HH-HH e.g. 9-17")
        else:
            print("    Format: HH-HH e.g. 9-17")

def prompt_weights(options, question_title):
    yn = input("    Add weighted answers? (y/n, default n): ").strip().lower()
    if yn != "y": return None
    manual = input("    Pick the weights yourself? (y/n, default n): ").strip().lower()
    if manual == "y":
        weights = []
        # [FIX issue-5] Allow 0 weight to exclude an option entirely.
        print("    Enter a weight for each option (0 = never chosen, higher = more likely):")
        for i, opt in enumerate(options):
            while True:
                try:
                    w = float(input(f"      {i+1}. {opt}: ").strip())
                    if w >= 0: weights.append(w); break
                    print("      Enter a number >= 0 (use 0 to exclude this option)")
                except ValueError:
                    print("      Enter a number e.g. 0, 1, 2.5, 10")
        return weights
    else:
        weights = [random.uniform(1, 10) for _ in options]
        total   = sum(weights)
        pct     = [f"{o}: {w/total*100:.0f}%" for o, w in zip(options, weights)]
        print(f"    Auto weights: {', '.join(pct)}")
        return weights

# -- Config -----------------------------------------------------------------
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "form_filler_config.json")

def _planned_to_config(planned):
    out = []
    for a in planned:
        d = {k: v for k, v in a.items()
             if k in ("entry", "title", "type", "value", "choice",
                      "all_opts", "options", "has_other", "other_text",
                      "other_texts", "is_required", "validation",
                      "weights", "date_range", "time_range", "grid_rows",
                      "grid_choices")}  # [FIX] added grid_choices -- was missing, broke config save/load for grids
        out.append(d)
    return out

def save_config(url, mode, times, workers, delay, planned):
    cfg = {
        "url":     url,
        "mode":    mode,
        "times":   times if times != float("inf") else "inf",
        "workers": workers,
        "delay":   list(delay),
        "planned": _planned_to_config(planned),
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        print(f"  Config saved to {CONFIG_FILE}")
    except Exception as e:
        print(f"  Could not save config: {e}")

def load_config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("times") == "inf": cfg["times"] = float("inf")
        cfg["delay"] = tuple(cfg.get("delay", [0.0, 0.0]))
        for a in cfg.get("planned", []):
            a["type"] = int(a["type"])
        return cfg
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None

# -- Form parsing -----------------------------------------------------------
def parse_question(block):
    try:
        title    = block[1] or ""
        fields   = block[4]
        if not fields: return None
        field    = fields[0]
        field_id = field[0]
        qtype    = block[3]
        opts_raw = field[1] if len(field) > 1 else []
        required = bool(field[2]) if len(field) > 2 else False
        entry    = f"entry.{field_id}"

        options, has_other = [], False
        for opt in (opts_raw or []):
            label = opt[0] if opt else ""
            if label == "__other_option__" or (len(opt) > 4 and opt[4] == 1):
                has_other = True
            elif label:
                options.append(label)

        validation = {}
        try:
            vb = field[4] if len(field) > 4 else None
            if vb and vb[0]:
                vtype     = vb[0][0]
                sub       = vb[0][1] if len(vb[0]) > 1 else None
                threshold = vb[0][2][0] if len(vb[0]) > 2 and vb[0][2] else None
                if sub is not None and threshold is not None:
                    vargs = [sub, threshold]
                elif sub is not None:
                    vargs = [sub]
                else:
                    vargs = []
                validation = {"type": vtype, "args": vargs}
        except (IndexError, TypeError):
            pass

        t = title.lower()
        if not validation:
            if qtype in (0, 1):
                if "email" in t:
                    validation = {"type": VType.EMAIL, "args": []}
                elif any(k in t for k in ("url", "website", "link")):
                    validation = {"type": VType.URL, "args": []}
        elif validation.get("type") == VType.TEXT_LEN:
            sub = (validation.get("args") or [None])[0]
            if sub == 102: validation = {"type": VType.EMAIL, "args": []}
            elif sub == 103: validation = {"type": VType.URL,   "args": []}

        grid_rows = []
        if qtype in (7, 8):
            for row_field in fields:
                row_label    = row_field[3][0] if len(row_field) > 3 and row_field[3] else ""
                row_entry_id = row_field[0]
                row_required = bool(row_field[2]) if len(row_field) > 2 else False
                grid_rows.append({"label": row_label, "entry": f"entry.{row_entry_id}",
                                  "required": row_required})
            if grid_rows:
                required = any(r["required"] for r in grid_rows)

        return {"title": title, "entry": entry, "field_id": field_id,
                "type": qtype, "options": options, "has_other": has_other,
                "is_required": required, "validation": validation,
                "grid_rows": grid_rows}
    except (IndexError, TypeError):
        return None

def extract_fb_data(html):
    marker = "FB_PUBLIC_LOAD_DATA_"
    idx = html.find(marker)
    if idx == -1: return None
    start = html.find('[', idx)
    if start == -1: return None
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(html[start:], start):
        if esc:                    esc = False;  continue
        if ch == '\\' and in_str:  esc = True;  continue
        if ch == '"' and not esc:  in_str = not in_str; continue
        if in_str: continue
        if ch == '[':   depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                try:    return json.loads(html[start:i+1])
                except: return None
    return None

def scan_form(url):
    """
    Scan a Google Form using Playwright.
    Returns (form_action, pages, cookies, is_multipage, seed_fbzx).
    """
    print("  Opening browser to scan form...")
    cookies, page_source = {}, ""

    with sync_playwright() as p:
        browser = None
        for name, launcher in [("Chromium", p.chromium), ("Firefox", p.firefox), ("WebKit", p.webkit)]:
            try: browser = launcher.launch(headless=False); break
            except: continue
        if not browser:
            print("  No browser found. Run: playwright install chromium"); sys.exit(1)
        print(f"  Using {name}")
        ctx  = browser.new_context(user_agent=random.choice(USER_AGENTS),
                                   viewport={"width": 1280, "height": 900}, locale="en-US")
        page = ctx.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1500)

        if page.query_selector(".g-recaptcha, [data-sitekey], iframe[src*='recaptcha']"):
            print("\n  [!]  CAPTCHA detected -- solve it in the browser window.")
            input("  Press ENTER once solved...")
            page.wait_for_timeout(1000)

        page_source = page.content()
        for c in ctx.cookies():
            cookies[c["name"]] = c["value"]

        m = re.search(r'/forms/d/e/([^/]+)/', url)
        if m:
            try: page.evaluate(f"fetch('https://docs.google.com/forms/d/e/{m.group(1)}/formResponse',{{method:'HEAD'}}).catch(()=>{{}})")
            except: pass
        browser.close()

    # [FIX issue-3] Raise ScanAbortedError with a clear reason instead of sys.exit(1).
    # The UI catches this and shows the message directly in the error dialog.
    if _check_access_denied(page_source):
        raise ScanAbortedError(
            "Access denied -- you do not have permission to view this form.\n\n"
            "Make sure you're signed into the right Google account, "
            "or ask the form owner to grant you access.")

    # [FIX issue-3] Same for closed forms.
    if _check_form_shutdown(page_source):
        raise ScanAbortedError(
            "Form closed -- this form is no longer accepting responses.")

    data = extract_fb_data(page_source)
    if not data:
        raise ScanAbortedError("Could not find form data -- the page may have loaded incorrectly. Try again.")
    try:
        blocks = data[1][1]
    except (IndexError, TypeError):
        raise ScanAbortedError("Unexpected form data structure -- the form may be a newer format not yet supported.")

    m = re.search(r'/forms/d/e/([^/]+)/', url)
    form_action = (f"https://docs.google.com/forms/d/e/{m.group(1)}/formResponse"
                   if m else url.replace("viewform", "formResponse"))

    seed_fbzx = None
    try:
        c = str(data[3]).strip()
        if re.fullmatch(r"-?\d+", c): seed_fbzx = c
    except: pass
    if not seed_fbzx:
        for pat in [r'"fbzx"\s*:\s*"(-?\d+)"', r'fbzx[^\"]*\"(-?\d+)\"',
                    r'\\\"fbzx\\\":\\\"(-?\d+)\\\"', r"'fbzx'\s*:\s*'(-?\d+)'"]:
            mm = re.search(pat, page_source)
            if mm: seed_fbzx = mm.group(1); break
    print(f"  fbzx: {seed_fbzx or '(not found -- will use random)'}")

    email_collection_q = None
    if 'type="email"' in page_source or "type='email'" in page_source:
        email_collection_q = {
            "title": "Email", "entry": "emailAddress", "field_id": "emailAddress",
            "type": QType.SHORT_TEXT, "options": [], "has_other": False,
            "is_required": True, "validation": {"type": VType.EMAIL, "args": []},
            "grid_rows": [], "page_index": 0,
        }
        print("  [i] Form-level email collection detected -- added Email as first question.")

    pages: list[list[dict]] = [[]]
    if email_collection_q:
        pages[0].append(email_collection_q)

    for block in blocks:
        if not isinstance(block, list) or len(block) < 4:
            continue
        if block[3] == 8:
            pages.append([])
            continue
        q = parse_question(block)
        if q:
            q["page_index"] = len(pages) - 1
            pages[-1].append(q)

    pages = [p for p in pages if p]
    is_multipage = len(pages) > 1
    all_questions = [q for page in pages for q in page]

    # [FIX issue-1] File uploads are silently dropped -- they require Google sign-in
    # and cannot be automated.  qtype==13 is not in QType anymore so parse_question
    # already filtered them; this block is just a safety notice if any slipped through.
    file_uploads = [q for q in all_questions if q["type"] == 13]
    if file_uploads:
        titles = ", ".join(q.get("title") or q.get("entry","?") for q in file_uploads)
        print(f"  [i] File upload question(s) skipped (not supported): {titles}")
        all_questions = [q for q in all_questions if q["type"] != 13]
        pages = [[q for q in page if q["type"] != 13] for page in pages]
        pages = [p for p in pages if p]

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "form_schema.json"), "w") as f:
        json.dump({"pages": pages, "questions": all_questions}, f, indent=2)
    print(f"  Saved {len(all_questions)} question(s) across {len(pages)} page(s) to form_schema.json")
    return form_action, pages, cookies, is_multipage, seed_fbzx

# -- Answer prompting -------------------------------------------------------
def prompt_answers(questions, mode):
    planned = []
    print(f"\n  Found {len(questions)} question(s).\n")

    for i, q in enumerate(questions):
        title   = q["title"] or f"Question {i+1}"
        req_tag = " *" if q["is_required"] else ""
        qtype   = q["type"]
        opts    = q["options"]
        vtype   = q.get("validation", {}).get("type")

        if mode == "lazy" and not q["is_required"]:
            print(f"  [SKIP] {title}"); continue

        if qtype in (QType.SHORT_TEXT, QType.LONG_TEXT):
            kind = ("EMAIL" if vtype == VType.EMAIL else "URL" if vtype == VType.URL
                    else "NUMBER" if vtype == VType.NUMBER
                    else "LONG TEXT" if qtype == QType.LONG_TEXT else "TEXT")
            print(f"  [{kind}]{req_tag} {title}")
            if mode == "random":
                val = "r"; print("    (random each submission)")
            else:
                raw = input("  Type answer (or 'r' for random): ").strip()
                val = "r" if raw.lower() == "r" else raw
            planned.append({**q, "value": val})
            print()

        elif qtype in (QType.RADIO, QType.DROPDOWN, QType.LINEAR):
            kind = {QType.DROPDOWN: "DROPDOWN", QType.LINEAR: "SCALE"}.get(qtype, "MULTIPLE CHOICE")
            print(f"  [{kind}]{req_tag} {title}")
            all_opts = opts + (["Other"] if q["has_other"] else [])
            for j, o in enumerate(all_opts): print(f"    {j+1}. {o}")
            weights = None
            if mode == "random":
                choice = "r"; print("    (random each submission)")
                weights = prompt_weights(all_opts, title)
            else:
                choice = get_single_choice("  Pick number (or 'r' for random): ", len(all_opts))
                if choice == "r": weights = prompt_weights(all_opts, title)
            other_text = ""
            if choice != "r" and q["has_other"] and choice == len(opts):
                other_text = input("    Type your 'Other' answer: ").strip()
            planned.append({**q, "choice": choice, "all_opts": all_opts,
                            "other_text": other_text, "weights": weights})
            print()

        elif qtype == QType.STAR:
            stars = opts if opts else ["1", "2", "3", "4", "5"]
            print(f"  [STAR RATING]{req_tag} {title}  (1-{len(stars)} stars)")
            weights = None
            if mode == "random":
                choice = "r"; print("    (random each submission)")
                weights = prompt_weights(stars, title)
            else:
                choice = get_single_choice("  Pick star rating (or 'r' for random): ", len(stars))
                if choice == "r": weights = prompt_weights(stars, title)
            planned.append({**q, "choice": choice, "all_opts": stars,
                            "weights": weights, "has_other": False})
            print()

        elif qtype == QType.CHECKBOX:
            print(f"  [CHECKBOX]{req_tag} {title}")
            all_opts = opts + (["Other"] if q["has_other"] else [])
            for j, o in enumerate(all_opts): print(f"    {j+1}. {o}")
            weights = None
            if mode == "random":
                choice = "r"; print("    (random each submission)")
                weights = prompt_weights(all_opts, title)
            else:
                print("    (separate multiple with commas e.g. 1,3)")
                choice = get_multi_choice("  Pick number(s) (or 'r' for random): ", len(all_opts))
                if choice == "r": weights = prompt_weights(all_opts, title)
            other_texts = {}
            if choice != "r" and q["has_other"]:
                for idx in (choice if isinstance(choice, list) else [choice]):
                    if idx == len(opts):
                        other_texts[idx] = input("    Type your 'Other' answer: ").strip()
            planned.append({**q, "choice": choice, "all_opts": all_opts,
                            "other_texts": other_texts, "weights": weights})
            print()

        elif qtype in (QType.GRID, QType.CHECKBOX_GRID):
            kind = "CHECKBOX GRID" if qtype == QType.CHECKBOX_GRID else "GRID"
            print(f"  [{kind}]{req_tag} {title}")
            print(f"    Columns: {', '.join(opts)}")
            grid_rows    = q.get("grid_rows", [])
            grid_choices = {}
            weights      = None
            if mode == "random":
                print("    (random each submission)")
                weights = prompt_weights(opts, title)
                for row in grid_rows:
                    grid_choices[row["entry"]] = "r"
            else:
                for row in grid_rows:
                    row_label = row["label"] or row["entry"]
                    print(f"    Row: {row_label}")
                    for j, o in enumerate(opts): print(f"      {j+1}. {o}")
                    if qtype == QType.CHECKBOX_GRID:
                        c = get_multi_choice(f"    Pick column(s) for '{row_label}' (or 'r'): ", len(opts))
                    else:
                        c = get_single_choice(f"    Pick column for '{row_label}' (or 'r'): ", len(opts))
                    grid_choices[row["entry"]] = c
                    if c == "r" and weights is None:
                        weights = prompt_weights(opts, title)
            planned.append({**q, "grid_choices": grid_choices, "weights": weights})
            print()

        elif qtype == QType.DATE:
            print(f"  [DATE]{req_tag} {title}")
            if mode == "random":
                print("    (random each submission)")
                date_range = prompt_date_range()
            else:
                raw = input("  Enter date (MM/DD/YYYY) or 'r' for random: ").strip()
                if raw.lower() == "r":
                    date_range = prompt_date_range()
                    planned.append({**q, "value": "r", "date_range": date_range})
                    print(); continue
                else:
                    planned.append({**q, "value": raw, "date_range": None})
                    print(); continue
            planned.append({**q, "value": "r", "date_range": date_range})
            print()

        elif qtype == QType.TIME:
            print(f"  [TIME]{req_tag} {title}")
            if mode == "random":
                print("    (random each submission)")
                time_range = prompt_time_range()
            else:
                raw = input("  Enter time (HH:MM) or 'r' for random: ").strip()
                if raw.lower() == "r":
                    time_range = prompt_time_range()
                    planned.append({**q, "value": "r", "time_range": time_range})
                    print(); continue
                else:
                    planned.append({**q, "value": raw, "time_range": None})
                    print(); continue
            planned.append({**q, "value": "r", "time_range": time_range})
            print()

        # [FIX issue-1] qtype==13 (file upload) is filtered out before this point;
        # no branch needed. Fall through to the else/debug log if somehow reached.
        else:
            log.debug(f"Skipping unsupported qtype {qtype}: {title}")

    return planned

# -- Payload builder --------------------------------------------------------
def _weighted_choice(options, weights):
    # [FIX issue-5] Allow weight=0 to completely exclude an option.
    # Build a filtered list of (index, weight) where weight > 0.
    # If ALL weights are 0 (shouldn't happen, but guard anyway), fall back to uniform random.
    if not weights or len(weights) != len(options):
        return random.randrange(len(options))
    eligible = [(i, w) for i, w in enumerate(weights) if w > 0]
    if not eligible:
        return random.randrange(len(options))   # all-zero fallback: uniform random
    total = sum(w for _, w in eligible)
    r     = random.uniform(0, total)
    cumulative = 0
    for i, w in eligible:
        cumulative += w
        if r <= cumulative: return i
    return eligible[-1][0]

def _val_text(value: str, q: dict, overflow_policy: str) -> tuple:
    """[REWRITE] Validate a resolved text/number answer against ALL Google Forms constraint types.

    VType coverage:
      NUMBER   (1) -- sub 1=> 2=>= 3=< 4=<= 5== 6!= 7=between 8=not-between
      TEXT_LEN (2) -- sub 1=> 2=>= 3=< 4=<= 5== 6!= 7=between 8=not-between  (chars)
      REGEX    (3) -- sub 1=contains 2=not-contains 3=matches 4=not-matches
      EMAIL    (4) -- basic @ + domain check
      URL      (5) -- must start with http:// or https://

    Returns (final_value, action):
      "ok"              -- value is valid, use as-is
      "truncate"        -- TEXT_LEN: value was cut to fit the max, still usable
      "skip_answer"     -- invalid and policy is skip_answer (caller falls back to random if required)
      "skip_submission" -- invalid and policy is skip_submission (discard whole attempt)

    For NUMBER, REGEX, EMAIL, URL: truncation makes no sense so 'truncate' policy
    also falls back to skip_answer (let the idiot-proof layer use random_value_for).
    """
    vtype = q.get("validation", {}).get("type")
    vargs = q.get("validation", {}).get("args", [])
    if isinstance(vargs, (int, float)): vargs = [vargs]
    if not isinstance(vargs, list):     vargs = []

    def _bad(fixable_by_truncation=False, truncated_val=None):
        """Return appropriate action tuple based on policy."""
        if fixable_by_truncation and overflow_policy == "truncate" and truncated_val is not None:
            return (truncated_val, "truncate")
        if overflow_policy == "skip_submission":
            return (value, "skip_submission")
        return ("", "skip_answer")

    # -------------------------------------------------------------------------
    # NUMBER (VType 1)
    # -------------------------------------------------------------------------
    if vtype == VType.NUMBER:
        try:
            num = float(value)
        except (ValueError, TypeError):
            return _bad()   # not a number at all

        if not vargs:
            return (value, "ok")   # no specific constraint beyond "must be a number"

        try:
            sub = int(vargs[0])
            t1  = float(vargs[1]) if len(vargs) > 1 and vargs[1] is not None else None
            t2  = float(vargs[2]) if len(vargs) > 2 and vargs[2] is not None else None
        except (ValueError, TypeError, IndexError):
            return (value, "ok")

        # sub 1 = >t1   sub 2 = >=t1   sub 3 = <t1   sub 4 = <=t1
        # sub 5 = ==t1  sub 6 = !=t1   sub 7 = between[t1,t2]  sub 8 = not between[t1,t2]
        invalid = False
        if   sub == 1 and t1 is not None: invalid = not (num >  t1)
        elif sub == 2 and t1 is not None: invalid = not (num >= t1)
        elif sub == 3 and t1 is not None: invalid = not (num <  t1)
        elif sub == 4 and t1 is not None: invalid = not (num <= t1)
        elif sub == 5 and t1 is not None: invalid = not (num == t1)
        elif sub == 6 and t1 is not None: invalid = not (num != t1)
        elif sub == 7 and t1 is not None and t2 is not None:
            invalid = not (t1 <= num <= t2)
        elif sub == 8 and t1 is not None and t2 is not None:
            invalid = (t1 <= num <= t2)   # "not between" -- valid means OUTSIDE [t1,t2]

        if invalid:
            return _bad()   # numbers can't be truncated
        return (value, "ok")

    # -------------------------------------------------------------------------
    # TEXT_LEN (VType 2)
    # -------------------------------------------------------------------------
    if vtype == VType.TEXT_LEN and vargs:
        try:
            sub = int(vargs[0])
            t1  = int(vargs[1]) if len(vargs) > 1 and vargs[1] is not None else None
            t2  = int(vargs[2]) if len(vargs) > 2 and vargs[2] is not None else None
        except (ValueError, TypeError):
            return (value, "ok")

        length = len(value)

        # sub 1 = len>t1   sub 2 = len>=t1   sub 3 = len<t1   sub 4 = len<=t1
        # sub 5 = len==t1  sub 6 = len!=t1   sub 7 = t1<=len<=t2  sub 8 = not between
        if   sub == 1 and t1 is not None:
            if length <= t1:  return _bad()   # too short, can't fix
        elif sub == 2 and t1 is not None:
            if length <  t1:  return _bad()
        elif sub == 3 and t1 is not None:
            if length >= t1:
                # too long -- truncate to t1-1
                return _bad(fixable_by_truncation=True, truncated_val=value[:max(1, t1-1)])
        elif sub == 4 and t1 is not None:
            if length >  t1:
                return _bad(fixable_by_truncation=True, truncated_val=value[:t1])
        elif sub == 5 and t1 is not None:
            if length > t1:
                return _bad(fixable_by_truncation=True, truncated_val=value[:t1])
            elif length < t1:
                return _bad()   # too short, can't pad
        elif sub == 6 and t1 is not None:
            # must NOT equal exactly t1 chars -- if it does, truncate by 1 (or skip)
            if length == t1:
                return _bad(fixable_by_truncation=True, truncated_val=value[:max(1, t1-1)])
        elif sub == 7 and t1 is not None and t2 is not None:
            if length > t2:
                return _bad(fixable_by_truncation=True, truncated_val=value[:t2])
            elif length < t1:
                return _bad()
        elif sub == 8 and t1 is not None and t2 is not None:
            # must NOT be between t1 and t2 -- if it is, truncate to t1-1 (shorter)
            if t1 <= length <= t2:
                return _bad(fixable_by_truncation=True,
                            truncated_val=value[:max(1, t1-1)] if t1 > 1 else value[:0])

        return (value, "ok")

    # -------------------------------------------------------------------------
    # REGEX (VType 3)
    # sub 1 = contains pattern   sub 2 = does NOT contain pattern
    # sub 3 = matches pattern    sub 4 = does NOT match pattern
    # -------------------------------------------------------------------------
    if vtype == VType.REGEX and vargs:
        try:
            sub     = int(vargs[0]) if vargs else 1
            pattern = str(vargs[1]) if len(vargs) > 1 and vargs[1] is not None else None
        except (ValueError, TypeError, IndexError):
            return (value, "ok")

        if not pattern:
            return (value, "ok")

        try:
            compiled = re.compile(pattern)
        except re.error:
            # Bad regex in form metadata -- just pass through
            return (value, "ok")

        match   = compiled.search(value)    # for contains / not-contains
        full    = compiled.fullmatch(value) # for matches / not-matches

        invalid = False
        if   sub == 1: invalid = not bool(match)    # must contain
        elif sub == 2: invalid = bool(match)         # must NOT contain
        elif sub == 3: invalid = not bool(full)      # must fully match
        elif sub == 4: invalid = bool(full)          # must NOT fully match

        if invalid:
            return _bad()   # regex failures can't be truncated
        return (value, "ok")

    # -------------------------------------------------------------------------
    # EMAIL (VType 4)
    # -------------------------------------------------------------------------
    if vtype == VType.EMAIL:
        # Basic check: contains @ with something on both sides and a dot in the domain
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', value):
            return _bad()
        return (value, "ok")

    # -------------------------------------------------------------------------
    # URL (VType 5)
    # -------------------------------------------------------------------------
    if vtype == VType.URL:
        if not re.match(r'^https?://', value, re.IGNORECASE):
            return _bad()
        return (value, "ok")

    # No validation constraint -- always ok
    return (value, "ok")


def _val_choice(choice, all_opts: list, invalid_policy: str) -> tuple:
    """[NEW] Validate a resolved choice index (or list) against available options.

    Returns (final_choice, action):
      action = "ok"              -- choice is valid
      action = "skip_answer"     -- choice invalid, skip/omit this field
      action = "skip_submission" -- choice invalid, discard whole submission

    'r' (random sentinel) is always "ok" -- it was already resolved by this point,
    but guard just in case.
    """
    if choice == "r":
        return (choice, "ok")

    n_opts = len(all_opts)

    if isinstance(choice, list):
        valid = [i for i in choice if isinstance(i, int) and 0 <= i < n_opts]
        if not valid and choice:
            if invalid_policy == "skip_submission": return (choice, "skip_submission")
            return ([], "skip_answer")
        return (valid, "ok")

    if choice is None:
        return (None, "skip_answer")

    if not isinstance(choice, int) or choice < 0 or choice >= n_opts:
        if invalid_policy == "skip_submission": return (choice, "skip_submission")
        return (None, "skip_answer")

    return (choice, "ok")


def _resolve_planned(planned, val_overflow="truncate", val_invalid_choice="skip_choice"):
    """Resolve all planned answers to their final concrete values.

    [NEW] Validation parameters (passed in from UI theme settings):
      val_overflow:        "truncate" | "skip_answer" | "skip_submission"
      val_invalid_choice:  "skip_choice" | "skip_submission"

    Returns a list of resolved answer dicts, or None if a skip_submission
    validation event fired (caller should discard this submission entirely).

    Idiot-proof guarantee: if skip_answer would leave a REQUIRED field blank,
    we fall back to a random valid value instead of submitting an empty required
    field (which would be rejected by Google Forms anyway).
    """
    resolved = []
    for a in planned:
        a2      = dict(a)
        qtype   = a2["type"]
        weights = a2.get("weights")

        if qtype in (QType.SHORT_TEXT, QType.LONG_TEXT):
            if a2.get("value") == "r":
                a2["value"] = random_value_for(a2)
            elif isinstance(a2.get("value"), str) and a2["value"].startswith("__RND__:"):
                # [NEW] Template from UI: expand <*RND_N*> tokens each submission.
                # QSTN tokens are NOT expanded here -- they need the full resolved list
                # first. They are expanded in the second pass below.
                template = a2["value"][len("__RND__:"):]
                a2["value"] = _expand_rnd(template)   # pass 1: expand everything except QSTN

            # [NEW] Validate the resolved text/number answer against form constraints.
            # _val_text does: number range check, text length check, applies overflow policy.
            val, action = _val_text(a2["value"], a2, val_overflow)
            if action == "skip_submission":
                log.warning(f"[validation] skip_submission on '{a2.get('title','?')}' "
                            f"value={a2['value']!r} -- aborting this submission")
                return None
            elif action in ("skip_answer", "truncate"):
                if not val and a2.get("is_required"):
                    # [IDIOT-PROOF] Required field must have a value -- use random instead
                    # of submitting blank, which would fail validation on Google's end anyway.
                    log.debug(f"[validation] skip_answer on required field '{a2.get('title','?')}' "
                              f"-- falling back to random to avoid broken submission")
                    val = random_value_for(a2)
                a2["value"] = val

        elif qtype in (QType.RADIO, QType.DROPDOWN, QType.LINEAR, QType.STAR):
            if a2.get("choice") == "r":
                all_opts = a2.get("all_opts", a2.get("options", []))
                if all_opts:
                    a2["choice"] = _weighted_choice(all_opts, weights)

            # [NEW] Validate the resolved choice index against the available options.
            all_opts = a2.get("all_opts", a2.get("options", []))
            choice, action = _val_choice(a2.get("choice"), all_opts, val_invalid_choice)
            if action == "skip_submission":
                log.warning(f"[validation] skip_submission on choice '{a2.get('title','?')}' "
                            f"choice={a2.get('choice')!r} -- aborting this submission")
                return None
            elif action == "skip_answer":
                if a2.get("is_required") and all_opts:
                    # [IDIOT-PROOF] Required field -- pick a random valid option
                    log.debug(f"[validation] skip_choice on required field '{a2.get('title','?')}' "
                              f"-- picking random option instead")
                    a2["choice"] = random.randrange(len(all_opts))
                else:
                    a2["choice"] = None   # _build_fields skips None choices safely
            else:
                a2["choice"] = choice

        elif qtype == QType.CHECKBOX:
            if a2.get("choice") == "r":
                all_opts = a2.get("all_opts", a2.get("options", []))
                if all_opts:
                    if weights:
                        # [FIX issue-5] Weight=0 means never selected; only pick from w>0 options.
                        # Use w/max_positive_w as independent selection probability per option.
                        positive_weights = [w for w in weights if w > 0]
                        if not positive_weights:
                            a2["choice"] = random.sample(range(len(all_opts)), k=random.randint(1, len(all_opts)))
                        else:
                            max_w  = max(positive_weights)
                            chosen = [i for i, w in enumerate(weights) if w > 0 and random.random() < w / max_w]
                            if not chosen: chosen = [_weighted_choice(all_opts, weights)]
                            a2["choice"] = chosen
                    else:
                        a2["choice"] = random.sample(range(len(all_opts)),
                                                     k=random.randint(1, len(all_opts)))

            # [NEW] Validate checkbox indices -- filter out any out-of-range indices.
            all_opts = a2.get("all_opts", a2.get("options", []))
            choice, action = _val_choice(a2.get("choice"), all_opts, val_invalid_choice)
            if action == "skip_submission":
                log.warning(f"[validation] skip_submission on checkbox '{a2.get('title','?')}' "
                            f"-- aborting this submission")
                return None
            elif action == "skip_answer":
                if a2.get("is_required") and all_opts:
                    # [IDIOT-PROOF] Required checkbox -- pick at least one random option
                    a2["choice"] = [random.randrange(len(all_opts))]
                else:
                    a2["choice"] = []
            else:
                a2["choice"] = choice if isinstance(choice, list) else ([] if choice is None else [choice])

        elif qtype in (QType.GRID, QType.CHECKBOX_GRID):
            new_gc = {}
            for row_entry, row_choice in a2.get("grid_choices", {}).items():
                opts = a2.get("options", [])
                if row_choice == "r":
                    if qtype == QType.CHECKBOX_GRID:
                        if weights:
                            # [FIX issue-5] Same w=0 exclusion fix as CHECKBOX branch above
                            positive_weights = [w for w in weights if w > 0]
                            if not positive_weights:
                                new_gc[row_entry] = random.sample(range(len(opts)), k=random.randint(1, max(1, len(opts))))
                            else:
                                max_w  = max(positive_weights)
                                chosen = [i for i, w in enumerate(weights) if w > 0 and random.random() < w / max_w]
                                if not chosen: chosen = [_weighted_choice(opts, weights)]
                                new_gc[row_entry] = chosen
                        else:
                            new_gc[row_entry] = random.sample(
                                range(len(opts)), k=random.randint(1, max(1, len(opts))))
                    else:
                        new_gc[row_entry] = _weighted_choice(opts, weights)
                else:
                    new_gc[row_entry] = row_choice
            a2["grid_choices"] = new_gc

        elif qtype == QType.DATE:
            if a2.get("value") == "r":
                a2["value"] = _random_date(a2.get("date_range") or (1990, 2005))

        elif qtype == QType.TIME:
            if a2.get("value") == "r":
                a2["value"] = _random_time(a2.get("time_range") or (0, 23))

        resolved.append(a2)

    # [NEW] Second pass: expand <*QSTN_N*> tokens now that all answers are resolved.
    # Build a 1-based map of question index -> final value (text questions only;
    # choice questions expose their selected option text for convenience).
    qstn_map = {}
    for i, a in enumerate(resolved, start=1):
        qtype = a["type"]
        if qtype in (QType.SHORT_TEXT, QType.LONG_TEXT):
            qstn_map[i] = a.get("value", "")
        elif qtype in (QType.RADIO, QType.DROPDOWN, QType.LINEAR, QType.STAR):
            choice = a.get("choice")
            opts   = a.get("all_opts", a.get("options", []))
            if choice is not None and opts and 0 <= choice < len(opts):
                qstn_map[i] = opts[choice]
        # other types (checkbox, grid, date, time) are skipped -- no single text value

    # Now re-expand any answer that still contains <*QSTN_N*> tokens
    for a in resolved:
        if a["type"] in (QType.SHORT_TEXT, QType.LONG_TEXT):
            val = a.get("value", "")
            if "<*QSTN_" in val:
                a["value"] = _expand_templates(val, qstn_map=qstn_map)

    # [NEW] Fire the answer tracking callback (non-blocking, best-effort).
    # ui.py registers this to count per-question answer distributions for the
    # Analytics tab.  Any exception here must not break the submission.
    if _answer_tracked_callback is not None:
        try:
            _answer_tracked_callback(resolved)
        except Exception:
            pass

    return resolved

def _build_fields(resolved):
    fields  = []
    partial = []

    for a in resolved:
        qtype    = a["type"]
        entry    = a["entry"]
        try:
            entry_id = int(entry.replace("entry.", ""))
        except ValueError:
            entry_id = 0
        opts     = a.get("options", [])
        all_opts = a.get("all_opts", opts)

        if qtype in (QType.SHORT_TEXT, QType.LONG_TEXT):
            val = a.get("value", "")
            fields.append((entry, val))
            partial.append(json.dumps([None, entry_id, [val], 0], separators=(",", ":")))
            continue

        elif qtype in (QType.RADIO, QType.DROPDOWN, QType.LINEAR, QType.STAR):
            if not all_opts: continue
            choice = a.get("choice", 0)
            # [NEW] None means the field was skipped by validation (skip_answer policy)
            if choice is None: continue
            if not isinstance(choice, int): choice = 0
            if a.get("has_other") and choice == len(opts):
                fields.append((entry, "__other_option__"))
                other = a.get("other_text") or random_text()
                fields.append((entry + ".other_option_response", other))
                partial.append(json.dumps([None, entry_id, ["__other_option__"], 0], separators=(",", ":")))
            else:
                val = all_opts[min(choice, len(all_opts) - 1)]
                fields.append((entry, val))
                partial.append(json.dumps([None, entry_id, [val], 0], separators=(",", ":")))

        elif qtype == QType.CHECKBOX:
            if not all_opts: continue
            indices = a.get("choice", [])
            if not isinstance(indices, list): indices = [indices]
            chosen = []
            for idx in indices:
                if a["has_other"] and idx == len(opts):
                    fields.append((entry, "__other_option__"))
                    other = a.get("other_texts", {}).get(idx) or random_text()
                    fields.append((entry + ".other_option_response", other))
                    chosen.append("__other_option__")
                else:
                    v = all_opts[idx]
                    fields.append((entry, v))
                    chosen.append(v)
            fields.append((entry + "_sentinel", ""))
            partial.append(json.dumps([None, entry_id, chosen, 0], separators=(",", ":")))

        elif qtype == QType.DATE:
            val = a.get("value") or _random_date()
            if isinstance(val, tuple):
                month, day, year = val
            else:
                parts = str(val).replace("-", "/").split("/")
                month, day, year = (parts + ["1", "1", "2000"])[:3]
            fields.append((entry + "_month", str(month)))
            fields.append((entry + "_day",   str(day)))
            fields.append((entry + "_year",  str(year)))

        elif qtype == QType.TIME:
            t    = a.get("value", _random_time())
            h, mn = t.split(":")
            fields.append((entry + "_hour",   h))
            fields.append((entry + "_minute", mn))

        elif qtype in (QType.GRID, QType.CHECKBOX_GRID):
            opts = a.get("options", [])
            for row in a.get("grid_rows", []):
                row_entry    = row["entry"]
                row_entry_id = int(row_entry.replace("entry.", ""))
                row_choice   = a.get("grid_choices", {}).get(row_entry, 0)
                if qtype == QType.CHECKBOX_GRID:
                    indices = row_choice if isinstance(row_choice, list) else [row_choice]
                    chosen  = [opts[i] for i in indices if i < len(opts)]
                    for v in chosen:
                        fields.append((row_entry, v))
                    fields.append((row_entry + "_sentinel", ""))
                    partial.append(json.dumps([None, row_entry_id, chosen, 0], separators=(",", ":")))
                else:
                    idx = row_choice if isinstance(row_choice, int) else 0
                    val = opts[min(idx, len(opts)-1)] if opts else ""
                    fields.append((row_entry, val))
                    partial.append(json.dumps([None, row_entry_id, [val], 0], separators=(",", ":")))

    return fields, partial

def _make_answer_for_unplanned(q):
    a2 = dict(q)
    a2["all_opts"]    = q["options"] + (["Other"] if q["has_other"] else [])
    a2["other_text"]  = ""
    a2["other_texts"] = {}
    a2["weights"]     = None
    qtype = q["type"]
    if qtype in (QType.SHORT_TEXT, QType.LONG_TEXT):
        a2["value"] = random_value_for(q)
    elif qtype in (QType.RADIO, QType.DROPDOWN, QType.LINEAR, QType.STAR):
        a2["choice"] = random.randrange(len(a2["all_opts"])) if a2["all_opts"] else 0
    elif qtype == QType.CHECKBOX:
        a2["choice"] = (random.sample(range(len(a2["all_opts"])),
                         k=random.randint(1, len(a2["all_opts"])))
                        if a2["all_opts"] else [])
    elif qtype in (QType.GRID, QType.CHECKBOX_GRID):
        opts = q.get("options", [])
        grid_choices = {}
        for row in q.get("grid_rows", []):
            if qtype == QType.CHECKBOX_GRID:
                grid_choices[row["entry"]] = random.sample(
                    range(len(opts)), k=random.randint(1, max(1, len(opts))))
            else:
                grid_choices[row["entry"]] = random.randrange(len(opts)) if opts else 0
        a2["grid_choices"] = grid_choices
    elif qtype == QType.DATE:
        a2["value"] = _random_date()
    elif qtype == QType.TIME:
        a2["value"] = _random_time()
    return a2

def _resolve_page(page_questions, planned_by_entry,
                  val_overflow="truncate", val_invalid_choice="skip_choice"):
    """Resolve answers for one page and run validation.
    Returns None if validation triggers skip_submission, otherwise a list of resolved answers.
    """
    planned = []
    for q in page_questions:
        a = planned_by_entry.get(q["entry"])
        planned.append(a if a is not None else _make_answer_for_unplanned(q))
    # [NEW] Pass validation settings into _resolve_planned; propagate None (skip_submission)
    return _resolve_planned(planned, val_overflow=val_overflow,
                            val_invalid_choice=val_invalid_choice)

# -- Headers ----------------------------------------------------------------
def make_headers(referer, cookies):
    ua, ch_ua, platform_hint, lang = _pick_ua_bundle()
    h = {
        "User-Agent":                ua,
        "Referer":                   referer,
        "Origin":                    "https://docs.google.com",
        "Content-Type":              "application/x-www-form-urlencoded",
        "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language":           lang,
        "Accept-Encoding":           "gzip, deflate, br",
        "Sec-Fetch-Site":            "same-origin",
        "Sec-Fetch-Mode":            "navigate",
        "Sec-Fetch-User":            "?1",
        "Sec-Fetch-Dest":            "document",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control":             "max-age=0",
        "Cookie":                    "; ".join(f"{k}={v}" for k, v in cookies.items()),
    }
    if ch_ua:
        h["sec-ch-ua"]          = ch_ua
        h["sec-ch-ua-mobile"]   = "?0"
        h["sec-ch-ua-platform"] = platform_hint
    return h

# -- Response checks --------------------------------------------------------
_CONFIRM_MARKERS = [
    "freebirdformsresponse",
    "your response has been recorded",
    "your response has been submitted",
    "thanks for your response",
    "response recorded",
    "submitted successfully",
    "response has been submitted",
]

def is_success(r):
    if r.status_code != 200: return False
    body = r.text.lower()
    if any(m in body for m in _CONFIRM_MARKERS): return True
    url = str(r.url).lower()
    if "formresponse" in url and "fb_public_load_data_" not in body: return True
    return False

def is_next_page(r):
    return r.status_code == 200 and "fb_public_load_data_" in r.text.lower()

def is_heavy_traffic(r):
    if r.status_code == 503: return True
    if r.status_code != 200: return False
    b = r.text.lower()
    return "this file might be unavailable" in b or "heavy traffic" in b

def is_captcha(r):
    if is_heavy_traffic(r): return False
    if r.status_code == 429: return True
    if r.status_code != 200: return False
    b = r.text.lower()
    return "recaptcha" in b or "g-recaptcha" in b or "data-sitekey" in b

def _dump_debug(label, payload_str, r, path="debug_last_response.html"):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"<!-- {label} -->\n")
            f.write(f"<!-- STATUS: {r.status_code}  URL: {r.url} -->\n")
            f.write(f"<!-- PAYLOAD:\n{payload_str}\n-->\n\n")
            f.write(r.text)
    except Exception as e:
        log.debug(f"Could not write debug file: {e}")

# -- Stats ------------------------------------------------------------------
def fmt_time(s):
    s = int(s); h, r = divmod(s, 3600); m, sc = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sc:02d}" if h else f"{m:02d}:{sc:02d}"

def print_stats(workers, submitted, success, total, start, retries=0):
    elapsed = time.time() - start
    rate    = (submitted / elapsed * 60) if elapsed > 0 else 0.0
    inf     = total == float("inf")
    pct     = "--" if inf else f"{submitted/total*100:.0f}%"
    tot_s   = "inf" if inf else str(int(total))
    eta     = "--:--" if inf or rate == 0 else fmt_time((total - submitted) / (rate / 60))
    # [NEW] Show retry count in stats bar so you can tell when Google is pushing back
    retry_s = f" | {retries}↺" if retries > 0 else ""
    bar = (f"  [{workers} worker{'s' if workers>1 else ''}]"
           f" | {fmt_time(elapsed)} elapsed"
           f" | {rate:.1f}/min"
           f" | {success}/{tot_s} ({pct})"
           + (f" | ETA {eta}" if not inf else "")
           + retry_s)
    print(f"\r{bar:<120}", end="", flush=True)

# -- CAPTCHA handler --------------------------------------------------------
def _solve_captcha_in_browser(url):
    new_cookies = {}
    # [FIX] Guard against playwright not being installed
    if not _PLAYWRIGHT_AVAILABLE:
        log.warning("playwright not installed -- CAPTCHA browser helper unavailable")
        return new_cookies
    try:
        with sync_playwright() as p:
            browser = None
            for _, launcher in [("Chromium", p.chromium), ("Firefox", p.firefox), ("WebKit", p.webkit)]:
                try: browser = launcher.launch(headless=False); break
                except: continue
            if not browser: return {}
            ctx  = browser.new_context(user_agent=random.choice(USER_AGENTS),
                                       viewport={"width": 1280, "height": 900}, locale="en-US")
            page = ctx.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1000)
            input("  [Browser open] Solve CAPTCHA then press ENTER: ")
            page.wait_for_timeout(500)
            for c in ctx.cookies(): new_cookies[c["name"]] = c["value"]
            browser.close()
    except Exception as e:
        log.warning(f"CAPTCHA browser error: {e}")
    return new_cookies

# -- Core HTTP submission ---------------------------------------------------
async def submit_once(client, form_action, pages, planned_by_entry, referer,
                      cookies, is_multipage, fbzx, captcha_event=None,
                      shutdown_event=None, val_overflow="truncate",
                      val_invalid_choice="skip_choice"):
    # [FIX] Added shutdown_event param so submit_once can signal all workers to stop
    # when a form-closed/access-denied response is detected, not just return False.
    # [NEW] val_overflow / val_invalid_choice come from UI theme settings and control
    # what happens when answers fail validation (see _val_text / _val_choice).
    if random.random() < 0.3:
        try:
            get_headers = make_headers(referer, cookies)
            get_headers["Sec-Fetch-Mode"] = "navigate"
            get_headers["Sec-Fetch-Dest"] = "document"
            get_headers.pop("Content-Type", None)
            await client.get(referer, headers=get_headers, follow_redirects=True)
            await asyncio.sleep(random.uniform(0.5, 2.5))
        except Exception:
            pass

    if not is_multipage:
        resolved = _resolve_page(pages[0], planned_by_entry,
                                 val_overflow=val_overflow,
                                 val_invalid_choice=val_invalid_choice)
        # [NEW] None means a skip_submission validation event fired -- silently discard
        if resolved is None:
            log.debug("[validation] skip_submission fired -- discarding this attempt")
            return False
        # [FIX] _resolve_page returns (fields, partial) tuple -- unpack it.
        # 'fields' and 'partial' were used as bare names below causing NameError on every submit.
        fields, partial = resolved
        partial_resp = f'[[{",".join(partial)}],null,"{fbzx}"]'
        payload = fields + [
            ("fvv",                 "1"),
            ("partialResponse",     partial_resp),
            ("pageHistory",         "0"),
            ("fbzx",                fbzx),
            ("submissionTimestamp", str(int(time.time() * 1000) + random.randint(-2000, 500))),
        ]
        encoded = urlencode(payload)
        log.debug(f"[single-page] POST {form_action}\nPAYLOAD: {encoded}")
        try:
            r = await client.post(form_action, content=encoded,
                                  headers=make_headers(referer, cookies),
                                  follow_redirects=True)
        except Exception as e:
            log.warning(f"Submit error: {e}"); return False

        if is_heavy_traffic(r): raise HeavyTrafficError("heavy traffic on single-page")
        if is_captcha(r) and captcha_event is not None:
            captcha_event.set(); return False
        # [NEW] Form shutdown/access-denied detection -- signal all workers to stop
        if _check_form_shutdown(r.text):
            log.warning("Form shutdown/access-denied detected (single-page)!")
            if shutdown_event is not None:
                shutdown_event.set()
            _trigger_shutdown_callback()
            return False
        ok = is_success(r)
        if not ok:
            log.warning(f"Single-page failed -- status {r.status_code}")
            _dump_debug("single-page failure", encoded, r)
        return ok

    # Multi-page
    session_cookies = dict(cookies)
    current_url     = referer
    page_history    = [0]
    all_page_fields = []

    def _headers_with_cookies(referer_url, current_cookies):
        return {
            "User-Agent":      random.choice(USER_AGENTS),
            "Referer":         referer_url,
            "Origin":          "https://docs.google.com",
            "Content-Type":    "application/x-www-form-urlencoded",
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie":          "; ".join(f"{k}={v}" for k, v in current_cookies.items()),
        }

    for page_num, page_questions in enumerate(pages):
        resolved = _resolve_page(page_questions, planned_by_entry,
                                 val_overflow=val_overflow,
                                 val_invalid_choice=val_invalid_choice)
        # [NEW] None = skip_submission validation event -- abort the whole attempt
        if resolved is None:
            log.debug(f"[validation] skip_submission fired on page {page_num} -- discarding attempt")
            return False
        fields, partial = _build_fields(resolved)
        all_page_fields.append((fields, partial))

        is_final    = (page_num == len(pages) - 1)
        history_str = ",".join(str(p) for p in page_history)

        if is_final:
            all_partial  = [p for _, pg_partial in all_page_fields for p in pg_partial]
            partial_resp = f'[[{",".join(all_partial)}],null,"{fbzx}"]'
            payload = fields + [
                ("fvv",                 "1"),
                ("partialResponse",     partial_resp),
                ("pageHistory",         history_str),
                ("fbzx",                fbzx),
                ("submissionTimestamp", str(int(time.time() * 1000) + random.randint(-2000, 500))),
            ]
        else:
            page_partial_resp = f'[[{",".join(partial)}],null,"{fbzx}"]'
            payload = fields + [
                ("dlut",                str(int(time.time() * 1000))),
                ("hud",                 "true"),
                ("fvv",                 "1"),
                ("partialResponse",     page_partial_resp),
                ("pageHistory",         history_str),
                ("fbzx",                fbzx),
                ("submissionTimestamp", "-1"),
                ("continue",            "1"),
            ]

        encoded = urlencode(payload)
        try:
            r = await client.post(form_action, content=encoded,
                                  headers=_headers_with_cookies(current_url, session_cookies),
                                  follow_redirects=True)
        except Exception as e:
            log.warning(f"Page {page_num} submit error: {e}"); return False

        for cookie_name, cookie_val in r.cookies.items():
            session_cookies[cookie_name] = cookie_val

        if is_heavy_traffic(r): raise HeavyTrafficError(f"heavy traffic on page {page_num}")
        if is_captcha(r) and captcha_event is not None:
            captcha_event.set(); return False
        # [NEW] Form shutdown/access-denied detection on any page -- signal all workers
        if _check_form_shutdown(r.text):
            log.warning(f"Form shutdown/access-denied detected (page {page_num})!")
            if shutdown_event is not None:
                shutdown_event.set()
            _trigger_shutdown_callback()
            return False

        if is_final:
            ok = is_success(r)
            if not ok:
                log.warning(f"Final page failed -- status {r.status_code}")
                _dump_debug(f"final-page failure (page {page_num})", encoded, r)
            return ok
        else:
            if r.status_code != 200:
                log.warning(f"Page {page_num} unexpected status {r.status_code}")
                _dump_debug(f"intermediate-page failure (page {page_num})", encoded, r)
                return False
            if is_captcha(r):
                if captcha_event: captcha_event.set()
                return False
            page_history.append(page_num + 1)
            current_url = str(r.url) or current_url

    log.warning("submit_once: exhausted pages without final success")
    return False

# -- HTTP submission engine -------------------------------------------------
async def _run_all(form_action, pages, planned, referer, cookies, times, workers,
                   start_time, mode, is_multipage, seed_fbzx, delay=(0.0, 0.0),
                   val_overflow="truncate", val_invalid_choice="skip_choice"):
    submitted  = 0
    success    = 0
    peak_rate  = 0.0
    retries    = 0   # [NEW] total heavy-traffic/error retries across all workers
    stop_event     = asyncio.Event()
    cap_event      = asyncio.Event()
    # [FIX] shutdown_event is set by submit_once when a form-closed/access-denied
    # response is detected; all workers then exit gracefully.
    shutdown_event = asyncio.Event()
    cap_lock       = asyncio.Lock()
    stats_lock     = asyncio.Lock()
    inf        = times == float("inf")
    target     = None if inf else int(times)
    last_print_time = 0.0

    limits = httpx.Limits(max_connections=workers + 4,
                          max_keepalive_connections=workers + 4,
                          keepalive_expiry=30)

    def make_planned_by_entry():
        # [NEW] Pass validation settings so _resolve_planned can apply them
        resolved = _resolve_planned(planned,
                                    val_overflow=val_overflow,
                                    val_invalid_choice=val_invalid_choice)
        if resolved is None:
            return None   # skip_submission fired at planning stage
        return {a["entry"]: a for a in resolved}

    probe_fbzx        = seed_fbzx or str(random.randint(-9007199254740992, 9007199254740992))
    probe_done        = asyncio.Event()
    probe_failed_flag = False

    # [FIX] Removed debug prints that leaked internal state to console on every run

    async def handle_captcha():
        nonlocal cookies
        async with cap_lock:
            if not cap_event.is_set(): return
            print("\n\n  [!]  CAPTCHA detected -- opening browser...")
            loop = asyncio.get_running_loop()
            nc   = await loop.run_in_executor(None, _solve_captcha_in_browser, referer)
            if nc: cookies = nc
            cap_event.clear()
            print("  Resuming...\n")

    async def worker(idx):
        nonlocal submitted, success, probe_failed_flag, peak_rate, retries

        stagger = random.uniform(0, min(idx * 0.4, 2.0))
        if stagger > 0:
            await asyncio.sleep(stagger)

        if idx > 0:
            await probe_done.wait()
            if probe_failed_flag: return

        first_iter = (idx == 0)

        while not stop_event.is_set():
            # [FIX] Exit immediately if form shutdown/access-denied was detected
            if shutdown_event.is_set():
                print("\n  [!] Form shutdown/access-denied detected -- stopping all workers.")
                stop_event.set()
                return

            if cap_event.is_set():
                await handle_captcha()
                await asyncio.sleep(random.uniform(1.0, 3.0))
                continue

            if delay[1] > 0:
                await asyncio.sleep(random.uniform(delay[0], delay[1]))

            sub_fbzx = probe_fbzx if first_iter else str(
                random.randint(-9007199254740992, 9007199254740992))
            pbe = make_planned_by_entry()
            # [NEW] None = skip_submission fired during planning -- skip this attempt
            if pbe is None:
                log.debug("[validation] skip_submission in make_planned_by_entry -- skipping attempt")
                continue

            ok = False
            for attempt in range(3):
                try:
                    ok = await submit_once(client, form_action, pages, pbe,
                                           referer, cookies, is_multipage,
                                           sub_fbzx, cap_event, shutdown_event,
                                           val_overflow=val_overflow,
                                           val_invalid_choice=val_invalid_choice)
                    break
                except HeavyTrafficError as e:
                    backoff = 2 ** (attempt + 1)
                    log.warning(f"Worker {idx} heavy traffic (attempt {attempt+1}), "
                                f"backing off {backoff}s: {e}")
                    async with stats_lock:
                        retries += 1   # [NEW] count heavy-traffic retries
                    if attempt < 2:
                        await asyncio.sleep(backoff + random.uniform(0, backoff))
                    else:
                        log.error(f"Worker {idx} gave up after 3 heavy-traffic retries")
                except Exception as e:
                    log.warning(f"Worker {idx} attempt {attempt+1}: {e}")
                    async with stats_lock:
                        retries += 1   # [NEW] count generic error retries
                    if attempt < 2: await asyncio.sleep(1.5 * (attempt + 1))

            if first_iter:
                first_iter = False
                if ok:
                    print("  [1] [ok]")
                else:
                    print("  [x] First submission failed.")
                    print("  -> Full payload + response saved to: debug_last_response.html")
                    print("  -> Detailed step-by-step logs in:   form_filler.log  (DEBUG level)")
                    loop = asyncio.get_running_loop()
                    ans  = await loop.run_in_executor(
                        None, lambda: input("  Continue anyway? (y/n): ").strip().lower())
                    if ans != "y":
                        probe_failed_flag = True
                        probe_done.set()
                        stop_event.set()
                        return
                probe_done.set()

            if cap_event.is_set(): continue

            async with stats_lock:
                nonlocal last_print_time
                submitted += 1
                if ok:
                    success += 1
                else:
                    log.error(f"Failed submission #{submitted}")
                elapsed = time.time() - start_time
                rate    = (submitted / elapsed * 60) if elapsed > 0 else 0.0
                if rate > peak_rate: peak_rate = rate
                now = time.time()
                if now - last_print_time >= 0.1:
                    print_stats(workers, submitted, success, times, start_time, retries)
                    last_print_time = now
                if not inf and submitted >= target:
                    stop_event.set()

    _timeout   = httpx.Timeout(connect=10.0, read=25.0, write=25.0, pool=10.0)
    try:
        _transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    except Exception:
        _transport = None

    async with httpx.AsyncClient(limits=limits, timeout=_timeout,
                                 transport=_transport) as client:
        try:
            await asyncio.gather(*[worker(i) for i in range(workers)])
        except (KeyboardInterrupt, asyncio.CancelledError):
            stop_event.set()

    return submitted, success, peak_rate, retries

def submit_all(form_action, pages, planned, referer, cookies, times, workers,
               mode="random", is_multipage=False, seed_fbzx=None, delay=(0.0, 0.0),
               val_overflow="truncate", val_invalid_choice="skip_choice"):
    start = time.time()
    try:
        total, ok, peak_rate, retries = asyncio.run(_run_all(
            form_action, pages, planned, referer, cookies, times, workers,
            start, mode, is_multipage, seed_fbzx, delay,
            val_overflow=val_overflow, val_invalid_choice=val_invalid_choice))
    except KeyboardInterrupt:
        print("\n  Stopped."); return 0, 0, 0.0, 0
    except Exception as e:
        log.error(f"submit_all error: {e}"); return 0, 0, 0.0, 0
    print(); return total, ok, peak_rate, retries

# -- Summary ----------------------------------------------------------------
def summarise(planned):
    print(f"\n{'='*60}\n  YOUR ANSWERS:")
    for a in planned:
        qtype   = a["type"]
        title   = (a["title"] or a["entry"])[:50]
        weights = a.get("weights")

        if qtype in (QType.SHORT_TEXT, QType.LONG_TEXT, QType.DATE, QType.TIME):
            display = "(random)" if a.get("value") == "r" else a.get("value", "?")
            if a.get("date_range") and a.get("value") == "r":
                display = f"(random {a['date_range'][0]}-{a['date_range'][1]})"
            if a.get("time_range") and a.get("value") == "r":
                display = f"(random {a['time_range'][0]:02d}:xx-{a['time_range'][1]:02d}:xx)"
        elif qtype in (QType.RADIO, QType.DROPDOWN, QType.LINEAR, QType.STAR):
            c  = a.get("choice", "r")
            ao = a.get("all_opts", a.get("options", []))
            display = "(random)" if c == "r" or not ao else ao[min(c, len(ao)-1)]
            if weights:
                total = sum(weights)
                pct   = [f"{o}: {w/total*100:.0f}%" for o, w in zip(ao, weights)]
                display += f"  [weights: {', '.join(pct)}]"
        elif qtype == QType.CHECKBOX:
            c  = a.get("choice", "r")
            ao = a.get("all_opts", a.get("options", []))
            display = "(random)" if c == "r" or not ao else \
                      ", ".join(ao[i] for i in (c if isinstance(c, list) else [c]) if i < len(ao))
            if weights:
                total = sum(weights)
                pct   = [f"{o}: {w/total*100:.0f}%" for o, w in zip(ao, weights)]
                display += f"  [weights: {', '.join(pct)}]"
        elif qtype in (QType.GRID, QType.CHECKBOX_GRID):
            rows  = a.get("grid_rows", [])
            gc    = a.get("grid_choices", {})
            opts  = a.get("options", [])
            parts = []
            for row in rows:
                rc = gc.get(row["entry"], "r")
                if rc == "r":
                    parts.append(f"{row['label']}: (random)")
                elif isinstance(rc, list):
                    parts.append(f"{row['label']}: {', '.join(opts[i] for i in rc if i < len(opts))}")
                else:
                    parts.append(f"{row['label']}: {opts[rc] if rc < len(opts) else '?'}")
            display = " | ".join(parts) or "(grid)"
        else:
            display = "(random)"
        print(f"  {title}: {display}")
    print('='*60)

def final_summary(total, ok, start_time, workers, peak_rate=None, retries=0):
    elapsed  = time.time() - start_time
    failed   = total - ok
    avg_rate = (total / elapsed * 60) if elapsed > 0 else 0
    h, rem   = divmod(int(elapsed), 3600)
    m, s     = divmod(rem, 60)
    dur_str  = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    print(f"\n{'='*60}")
    print(f"  RUN COMPLETE")
    print(f"{'='*60}")
    print(f"  Total submitted : {total}")
    print(f"  Successful      : {ok}")
    print(f"  Failed          : {failed}")
    if total > 0: print(f"  Success rate    : {ok/total*100:.1f}%")
    print(f"  Total time      : {dur_str}")
    print(f"  Avg rate        : {avg_rate:.1f} /min")
    if peak_rate: print(f"  Peak rate       : {peak_rate:.1f} /min")
    if retries:   print(f"  Retries         : {retries}")   # [NEW] show retry count
    print(f"  Workers used    : {workers}")
    print(f"{'='*60}")
    # [NEW] Append session result to a JSONL results log so runs are never lost
    export_session_result(total, ok, failed, elapsed, avg_rate, peak_rate, retries, workers)


def export_session_result(total, ok, failed, elapsed, avg_rate, peak_rate, retries, workers,
                           url="", mode="", extra=None):
    """[NEW] Append one JSON line to form_filler_results.jsonl after every run.
    Each line is a self-contained record -- easy to grep, import into pandas, etc.
    extra: optional dict of additional fields (e.g. backend, form title).
    """
    record = {
        "timestamp":  time.strftime("%Y-%m-%dT%H:%M:%S"),
        "url":        url,
        "mode":       mode,
        "total":      total,
        "success":    ok,
        "failed":     failed,
        "elapsed_s":  round(elapsed, 2),
        "avg_per_min": round(avg_rate, 2),
        "peak_per_min": round(peak_rate, 2) if peak_rate else 0,
        "retries":    retries,
        "workers":    workers,
    }
    if extra:
        record.update(extra)
    results_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "form_filler_results.jsonl")
    try:
        with open(results_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        log.debug(f"Could not write results log: {e}")


# ===========================================================================
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                      CHROMIUM BACKEND                                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# ===========================================================================

# -- Selenium imports (optional -- only needed if Chromium backend is used) --
try:
    from selenium import webdriver as _webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service as ChromeService
        _WEBDRIVER_MANAGER = True
    except ImportError:
        _WEBDRIVER_MANAGER = False
    try:
        from screeninfo import get_monitors as _get_monitors
        _SCREENINFO = True
    except ImportError:
        _SCREENINFO = False
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# -- Chromium global state (polled by ui.py for live stats) -----------------
chrom_total_submitted = 0
chrom_start_time      = None
_chrom_stats_lock     = threading.Lock()
_chrom_drivers        = []
_chrom_drivers_lock   = threading.Lock()

def chrom_register_driver(driver):
    with _chrom_drivers_lock:
        _chrom_drivers.append(driver)

def kill_all_drivers():
    """Close all open Chrome windows. Called on stop or exit."""
    with _chrom_drivers_lock:
        for d in _chrom_drivers:
            try: d.quit()
            except: pass
        _chrom_drivers.clear()

def _chrom_increment():
    global chrom_total_submitted
    with _chrom_stats_lock:
        chrom_total_submitted += 1

def chrom_print_stats(num_instances, iterations, infinite):
    with _chrom_stats_lock:
        submitted = chrom_total_submitted
    elapsed    = time.time() - chrom_start_time if chrom_start_time else 0
    mins, secs = divmod(int(elapsed), 60)
    hrs, mins  = divmod(mins, 60)
    time_str   = f"{hrs:02d}:{mins:02d}:{secs:02d}"
    rate       = (submitted / elapsed * 60) if elapsed > 0 else 0.0
    if infinite:
        count_str = f"{submitted}/inf submitted"
    else:
        target    = iterations
        pct       = (submitted / target * 100) if target > 0 else 0
        eta_sec   = ((target - submitted) / (submitted / elapsed)) if submitted > 0 else 0
        em, es    = divmod(int(eta_sec), 60)
        eh, em    = divmod(em, 60)
        eta_str   = f"{eh:02d}:{em:02d}:{es:02d}"
        count_str = f"{submitted}/{target} submitted ({pct:.0f}% | ETA {eta_str})"
    print(f"[{num_instances} instances] | runtime {time_str} | {rate:.1f} forms/min | {count_str}")

def make_driver(options):
    """Create a Chrome WebDriver. Uses webdriver-manager if available."""
    if not SELENIUM_AVAILABLE:
        raise RuntimeError("selenium is not installed. Run: pip install selenium webdriver-manager")
    if _WEBDRIVER_MANAGER:
        return _webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()), options=options)
    return _webdriver.Chrome(options=options)

# -- Monitor tiling ---------------------------------------------------------
def get_monitor_layout(num_instances):
    monitors = []
    if _SCREENINFO:
        try: monitors = _get_monitors()
        except Exception: pass
    if not monitors:
        print("  (Could not detect monitors, assuming 1920x1080)")
        monitors = [type('M', (), {'x': 0, 'y': 0, 'width': 1920, 'height': 1080, 'is_primary': True})()]
    primary    = next((m for m in monitors if getattr(m, 'is_primary', False)), monitors[0])
    use_spread = False
    if len(monitors) > 1:
        print(f"\n{len(monitors)} monitors detected.")
        raw = input("Tile on primary monitor or spread across all? (primary/spread): ").strip().lower()
        use_spread = raw in ("spread", "s")
    return _tile_spread(monitors, primary, num_instances) if use_spread \
           else _tile_on_monitor(primary, num_instances)

def _tile_on_monitor(monitor, num_instances):
    cols = int(-(-num_instances ** 0.5 // 1))
    rows = -(-num_instances // cols)
    w    = monitor.width  // cols
    h    = monitor.height // rows
    positions = []
    for i in range(num_instances):
        col = i % cols
        row = i // cols
        positions.append((monitor.x + col * w, monitor.y + row * h, w, h))
    return positions

def _tile_spread(monitors, primary, num_instances):
    base     = num_instances // len(monitors)
    overflow = num_instances % len(monitors)
    positions = []
    for m in monitors:
        count     = base + (1 if overflow > 0 else 0)
        overflow -= 1
        positions.extend(_tile_on_monitor(m, count))
    while len(positions) < num_instances:
        positions.extend(_tile_on_monitor(primary, num_instances - len(positions)))
    return positions[:num_instances]

# -- Chromium helpers (random generators used inside browser interactions) --
def _chrom_random_text(length=10):
    # [FIX] Generate length-1 chars then insert space so total length == length (was length+1)
    chars = random.choices(string.ascii_letters + string.digits, k=length - 1)
    mid   = random.randint(1, max(1, length - 2))
    chars.insert(mid, ' ')
    return ''.join(chars)

def _chrom_random_email():
    user   = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(5, 10)))
    domain = ''.join(random.choices(string.ascii_lowercase, k=random.randint(4, 8)))
    tld    = random.choice(["com", "net", "org", "io", "co"])
    return f"{user}@{domain}.{tld}"

# -- Question scanner (Selenium) -------------------------------------------
def chrom_scan_questions(driver, wait, mode):
    """
    Scan a loaded Google Form page using Selenium.
    Returns a list of action dicts for execute_submission().
    """
    questions       = driver.find_elements(By.XPATH, '//div[@role="listitem"]')
    planned_actions = []
    print(f"\nFound {len(questions)} question(s). Scanning...\n")

    for q_idx, q in enumerate(questions):
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", q)
        time.sleep(0.3)

        try:
            title_el = q.find_elements(By.XPATH, './/div[contains(@role,"heading")] | .//span[contains(@class,"M7eMe")]')
            title = title_el[0].text.replace('*', '').split('\n')[0].strip() if title_el else f"Question {q_idx+1}"
        except:
            title = f"Question {q_idx+1}"

        is_required = (bool(q.find_elements(By.XPATH, './/*[@aria-required="true"]')) or
                       bool(q.find_elements(By.XPATH, './/*[contains(@class,"vnumgf")]')))

        if mode == "lazy" and not is_required:
            print(f"  [SKIP] {title} (not required)")
            continue

        req_tag = " *" if is_required else ""

        # DROPDOWN
        dropdowns = q.find_elements(By.XPATH, './/div[@role="listbox"]')
        if dropdowns:
            print(f"[DROPDOWN]{req_tag} {title}")
            # [FIX] Dropdown options are in a hidden overlay that only appears AFTER
            # the listbox is clicked open.  Previously we tried to read them before
            # clicking, which always returned an empty list and caused the question
            # to be skipped.  Now we click to open, wait for options, scrape, then
            # press Escape to close before moving on.
            try:
                trigger = dropdowns[0]
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", trigger)
                time.sleep(0.3)
                try:
                    trigger.click()
                except Exception:
                    ActionChains(driver).move_to_element(trigger).click().perform()
                time.sleep(0.7)  # wait for overlay to render
                opt_els   = driver.find_elements(By.XPATH, '//div[@role="option"]')
                opt_texts = [o.get_attribute("data-value").strip() for o in opt_els
                             if o.get_attribute("data-value") and
                                o.get_attribute("data-value").strip() not in ("", "0")
                                and o.is_displayed()]
                # Close the dropdown without selecting anything
                try:
                    from selenium.webdriver.common.keys import Keys
                    trigger.send_keys(Keys.ESCAPE)
                except Exception:
                    driver.execute_script("arguments[0].click();", trigger)
                time.sleep(0.3)
            except Exception:
                opt_texts = []

            if not opt_texts:
                print("  (Could not detect options, skipping)")
                continue
            for i, txt in enumerate(opt_texts): print(f"  {i+1}: {txt}")
            choice = 'r' if mode == "random" else get_single_choice(
                "  Select number (or 'r' for random): ", len(opt_texts))
            planned_actions.append({"type": "dropdown", "q_idx": q_idx, "title": title,
                                    "options": opt_texts, "choice": choice})
            print(); continue

        # RADIO / CHECKBOX
        radios     = q.find_elements(By.XPATH, './/div[@role="radio"]')
        checkboxes = q.find_elements(By.XPATH, './/div[@role="checkbox"]')
        btns = checkboxes if checkboxes else radios
        if btns:
            is_multi = bool(checkboxes)
            kind     = "CHECKBOX (multi-select)" if is_multi else "MULTIPLE CHOICE"
            print(f"[{kind}]{req_tag} {title}")
            labels = [
                "Other" if b.get_attribute("data-value") == "__other_option__"
                else b.get_attribute("aria-label") or b.text or f"Option {i+1}"
                for i, b in enumerate(btns)
            ]
            for i, lbl in enumerate(labels): print(f"  {i+1}: {lbl}")
            if mode == "random":
                choice = 'r'
            elif is_multi:
                print("  Tip: separate multiple selections with commas e.g. 1,3")
                choice = get_multi_choice("  Select number(s) (or 'r' for random): ", len(btns))
            else:
                choice = get_single_choice("  Select number (or 'r' for random): ", len(btns))

            other_texts = {}
            if choice != 'r' and mode != "random":
                indices = choice if isinstance(choice, list) else [choice]
                for idx in indices:
                    if idx < len(btns) and btns[idx].get_attribute("data-value") == "__other_option__":
                        other_texts[idx] = input("  -> Type text for 'Other': ").strip()

            planned_actions.append({
                "type": "click", "q_idx": q_idx, "title": title,
                "labels": labels, "is_multi": is_multi,
                "choice": choice, "other_texts": other_texts,
                "other_indices": {i for i, b in enumerate(btns)
                                  if b.get_attribute("data-value") == "__other_option__"},
            })
            print(); continue

        # EMAIL
        email_inputs = q.find_elements(By.XPATH, './/input[@type="email"]')
        if email_inputs:
            print(f"[EMAIL]{req_tag} {title}")
            if mode == "random":
                val = 'email_r'; print("  (random email)")
            else:
                raw = input("  Type email (or 'r' for random): ").strip()
                val = 'email_r' if raw.lower() == 'r' else raw
            planned_actions.append({"type": "email", "q_idx": q_idx, "title": title, "value": val})
            print(); continue

        # [NEW] DATE -- Google Forms renders date fields as three separate number inputs
        # (month, day, year).  We detect them by looking for input[type="number"] with
        # aria-labels that contain "month", "day", or "year".
        date_inputs = q.find_elements(By.XPATH, './/input[@type="number"]')
        if date_inputs:
            aria_labels = [inp.get_attribute("aria-label") or "" for inp in date_inputs]
            is_date = any("month" in al.lower() or "day" in al.lower() or "year" in al.lower()
                          for al in aria_labels)
            is_time = any("hour" in al.lower() or "minute" in al.lower()
                          for al in aria_labels)

            if is_date:
                print(f"[DATE]{req_tag} {title}")
                if mode == "random":
                    val = 'r'; print("  (random date, default range 1990-2005)")
                    date_range = (1990, 2005)
                else:
                    raw = input("  Enter date MM/DD/YYYY or 'r' for random: ").strip()
                    if raw.lower() == 'r':
                        val = 'r'
                        date_range = (1990, 2005)
                    else:
                        val = raw
                        date_range = None
                planned_actions.append({"type": "date", "q_idx": q_idx, "title": title,
                                        "value": val, "date_range": date_range})
                print(); continue

            if is_time:
                print(f"[TIME]{req_tag} {title}")
                if mode == "random":
                    val = 'r'; print("  (random time)")
                    time_range = (0, 23)
                else:
                    raw = input("  Enter time HH:MM or 'r' for random: ").strip()
                    if raw.lower() == 'r':
                        val = 'r'
                        time_range = (0, 23)
                    else:
                        val = raw
                        time_range = None
                planned_actions.append({"type": "time_input", "q_idx": q_idx, "title": title,
                                        "value": val, "time_range": time_range})
                print(); continue

        # TEXT
        text_inputs = q.find_elements(By.XPATH, './/input[@type="text"] | .//textarea')
        if text_inputs:
            print(f"[TEXT]{req_tag} {title}")
            if mode == "random":
                val = 'r'; print("  (random)")
            else:
                raw = input("  Type answer (or 'r' for random): ").strip()
                val = 'r' if raw.lower() == 'r' else raw
            planned_actions.append({"type": "text", "q_idx": q_idx, "title": title, "value": val})
            print()

    return planned_actions

# -- Execute one submission (Selenium) -------------------------------------
def chrom_execute_submission(driver, wait, planned_actions):
    # [FIX] Do NOT cache the questions list here -- Google Forms re-renders the DOM
    # after scroll events and dynamic validation, causing stale element exceptions
    # that silently abort after the first question.  Re-fetch for each action instead.

    for action in planned_actions:
        q_idx = action["q_idx"]

        # [FIX] Re-fetch question elements fresh for every action so we never hold
        # a stale reference.  This is the primary cause of "only first question filled".
        current_questions = driver.find_elements(By.XPATH, '//div[@role="listitem"]')
        if q_idx >= len(current_questions):
            chrom_log(f"  [WARN] q_idx {q_idx} out of range (have {len(current_questions)}), skipping")
            continue

        q_box = current_questions[q_idx]
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", q_box)
        time.sleep(0.3)  # [FIX] was 0.2 -- bumped slightly so scroll animation settles before interaction

        if action["type"] == "email":
            val   = _chrom_random_email() if action["value"] == 'email_r' else action["value"]
            field = q_box.find_element(By.XPATH, './/input[@type="email"]')
            field.clear(); field.send_keys(val)

        elif action["type"] == "text":
            val   = _chrom_random_text() if action["value"] == 'r' else action["value"]
            field = q_box.find_element(By.XPATH, './/input[@type="text"] | .//textarea')
            field.clear(); field.send_keys(val)

        elif action["type"] == "click":
            btns    = q_box.find_elements(By.XPATH, './/div[@role="radio"] | .//div[@role="checkbox"]')
            choice  = action["choice"]
            indices = [random.randint(0, len(btns) - 1)] if choice == 'r' else \
                      (choice if isinstance(choice, list) else [choice])
            for idx in indices:
                if idx >= len(btns): continue
                driver.execute_script("arguments[0].click();", btns[idx])
                time.sleep(0.3)  # [FIX] was 0.2 -- give Google's validation JS time to run
                                 # before we move to the next field; too-fast clicks caused
                                 # subsequent elements to not register.
                if idx in action.get("other_indices", set()):
                    other_text = action.get("other_texts", {}).get(idx) or _chrom_random_text()
                    try:
                        time.sleep(0.3)
                        txt_field = q_box.find_element(By.XPATH, './/input[@type="text"]')
                        txt_field.clear(); txt_field.send_keys(other_text)
                    except: pass

        elif action["type"] == "dropdown":
            opts       = action["options"]
            chosen_val = random.choice(opts) if action["choice"] == 'r' else opts[action["choice"]]
            trigger    = q_box.find_element(By.XPATH, './/div[@role="listbox"]')
            try: trigger.click()
            except: ActionChains(driver).move_to_element(trigger).click().perform()
            time.sleep(0.6)
            for _ in range(10):
                time.sleep(0.2)
                all_opts = driver.find_elements(By.XPATH, '//div[@role="option"]')
                visible  = [o for o in all_opts
                            if o.get_attribute("data-value") == chosen_val and o.is_displayed()]
                if visible:
                    try: visible[0].click()
                    except: driver.execute_script("arguments[0].click();", visible[0])
                    break
            time.sleep(0.3)

        # [NEW] DATE -- fill the three number inputs (month, day, year) individually.
        # Google Forms uses input[type="number"] with aria-label for each part.
        elif action["type"] == "date":
            val = action.get("value", "r")
            if val == "r":
                date_range = action.get("date_range") or (1990, 2005)
                month, day, year = _random_date(date_range)
            else:
                parts = str(val).replace("-", "/").split("/")
                month, day, year = (parts + ["1", "1", "2000"])[:3]
            date_inputs = q_box.find_elements(By.XPATH, './/input[@type="number"]')
            for inp in date_inputs:
                al = (inp.get_attribute("aria-label") or "").lower()
                try:
                    inp.click(); inp.clear()
                    if "month" in al:   inp.send_keys(str(month))
                    elif "day" in al:   inp.send_keys(str(day))
                    elif "year" in al:  inp.send_keys(str(year))
                    time.sleep(0.1)
                except Exception: pass

        # [NEW] TIME -- fill hour and minute number inputs.
        elif action["type"] == "time_input":
            val = action.get("value", "r")
            if val == "r":
                time_range = action.get("time_range") or (0, 23)
                t_str = _random_time(time_range)
            else:
                t_str = val
            try:
                h_str, m_str = t_str.split(":")
            except ValueError:
                h_str, m_str = "12", "00"
            time_inputs = q_box.find_elements(By.XPATH, './/input[@type="number"]')
            for inp in time_inputs:
                al = (inp.get_attribute("aria-label") or "").lower()
                try:
                    inp.click(); inp.clear()
                    if "hour" in al:   inp.send_keys(h_str)
                    elif "minute" in al: inp.send_keys(m_str)
                    time.sleep(0.1)
                except Exception: pass

# [NEW] Form shutdown detection -- callback called when a closed/accepting-no-more-responses
# page is detected.  ui.py sets this to trigger its overlay/popup/confetti system.
_form_shutdown_callback = None

def set_form_shutdown_callback(fn):
    """Register a function to call when form shutdown is detected.
    fn() will be called from a worker thread -- must be thread-safe."""
    global _form_shutdown_callback
    _form_shutdown_callback = fn

# Strings that appear on Google Forms "closed / not accepting responses" pages.
# These show up at the /closedform endpoint when a form owner has closed the form.
_FORM_CLOSED_MARKERS = [
    "no longer accepting responses",
    "this form is no longer accepting responses",
    "closed to new responses",
    "this form has been closed",
    "form is closed",
    "not accepting responses",
]

# Strings that appear on Google's "Access Denied / You need access" page.
# This is served by Drive sharing when the viewer lacks permission to see the form.
_FORM_ACCESS_DENIED_MARKERS = [
    "you need access",
    "request access",
    "you don't have access",
    "you do not have access",
    # The page title used by the Drive access-denied handler
    "<title>access denied</title>",
]

def _check_form_shutdown(response_text):
    """Return True if the response body indicates the form is closed OR access is denied.
    Covers both the /closedform page and the Drive 'You need access' page."""
    low = response_text.lower()
    return any(m in low for m in _FORM_CLOSED_MARKERS) or \
           any(m in low for m in _FORM_ACCESS_DENIED_MARKERS)

def _check_access_denied(response_text):
    """Return True specifically if the response is the Drive access-denied page.
    Used during scan_form to give a clearer error message to the user."""
    low = response_text.lower()
    return any(m in low for m in _FORM_ACCESS_DENIED_MARKERS)

def _trigger_shutdown_callback():
    """Call the registered shutdown callback safely."""
    if _form_shutdown_callback:
        try:
            _form_shutdown_callback()
        except Exception as e:
            log.error(f"Shutdown callback error: {e}")


# -- Chromium instance worker ----------------------------------------------
def chrom_run_instance(instance_id, url, planned_actions, iterations, infinite,
                       num_instances, window_rect, headless=False, perf_mode="normal"):
    """Run one Chrome instance submitting the form in a loop."""
    chrome_options = ChromeOptions()
    chrome_options.add_experimental_option("detach", True)
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    )

    if headless:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1280,800")

    if perf_mode == "turbo":
        for arg in ("--disable-extensions", "--disable-background-networking",
                    "--disable-sync", "--disable-renderer-backgrounding",
                    "--disable-notifications", "--disable-dev-shm-usage",
                    "--disable-logging", "--silent",
                    "--blink-settings=imagesEnabled=false"):
            chrome_options.add_argument(arg)
        chrome_options.add_experimental_option("prefs", {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.notifications": 2,
        })

    driver = make_driver(chrome_options)
    chrom_register_driver(driver)
    driver.get(url)

    if not headless:
        x, y, w, h = window_rect
        driver.set_window_rect(x, y, w, h)

    wait = WebDriverWait(driver, 10)
    try:
        wait.until(EC.presence_of_element_located((By.XPATH, '//div[@role="listitem"]')))
    except: pass

    # [FIX] Detect closed/access-denied on the initial page load before doing anything.
    # Previously, the loop would just silently fail or throw weird errors.
    try:
        initial_src = driver.page_source.lower()
        if _check_access_denied(initial_src):
            chrom_log(f"Instance {instance_id} | ACCESS DENIED -- cannot view this form.")
            print(f"\n  [!] Instance {instance_id}: ACCESS DENIED. Check your Google account.")
            driver.quit()
            return
        if _check_form_shutdown(initial_src):
            chrom_log(f"Instance {instance_id} | FORM CLOSED -- not accepting responses.")
            print(f"\n  [!] Instance {instance_id}: Form is closed / not accepting responses.")
            _trigger_shutdown_callback()
            driver.quit()
            return
    except Exception: pass

    try:
        i = 0
        while True:
            if not infinite and i >= iterations:
                break

            # [FIX issue-2] Small sleep to let the form DOM fully render before filling,
            # especially important on the 2nd+ iteration after "Submit another" reloads.
            time.sleep(0.5)

            chrom_execute_submission(driver, wait, planned_actions)

            # [FIX issue-2] Broaden submit button detection -- Google Forms uses
            # <span> text inside a <div role="button">.  The old XPATH only matched
            # the <span> which sometimes isn't directly clickable; clicking the
            # parent button div is more reliable.  Also replaced bare `except: break`
            # (which silently exited the loop on ANY failure) with a logged continue
            # so temporary failures don't kill the whole run.
            submit_clicked = False
            for submit_xpath in [
                '//div[@role="button"][.//span[text()="Submit"]]',
                '//div[@role="button"][.//span[text()="Send"]]',
                '//span[text()="Submit"]/ancestor::div[@role="button"]',
                '//span[text()="Submit"]',
                '//span[text()="Send"]',
            ]:
                try:
                    btn = driver.find_element(By.XPATH, submit_xpath)
                    driver.execute_script("arguments[0].click();", btn)
                    submit_clicked = True
                    break
                except Exception:
                    continue

            if not submit_clicked:
                chrom_log(f"Instance {instance_id} | Could not find Submit button on iteration {i+1} -- retrying next loop")
                # Don't break -- maybe a page transition is in progress; retry next iter
                time.sleep(1.5)
                continue

            # [NEW] Detect form shutdown after submit (page source check)
            try:
                time.sleep(0.8)
                page_src = driver.page_source.lower()
                if _check_form_shutdown(page_src):
                    chrom_log(f"Instance {instance_id} | FORM SHUTDOWN DETECTED")
                    _trigger_shutdown_callback()
                    break
            except Exception: pass

            _chrom_increment()
            chrom_print_stats(num_instances, iterations, infinite)
            _chrom_file_handler.stream.write(
                f"[{time.strftime('%H:%M:%S')}] Instance {instance_id} | Submission {i+1} | OK\n")
            _chrom_file_handler.stream.flush()
            i += 1

            if infinite or i < iterations:
                try:
                    again_link = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, '//a[contains(text(), "Submit another")]')))
                    driver.execute_script("arguments[0].click();", again_link)
                except:
                    driver.get(url)
                try:
                    wait.until(EC.presence_of_element_located(
                        (By.XPATH, '//div[@role="listitem"]')))
                except: pass

    except Exception as e:
        chrom_log(f"Instance {instance_id} | ERROR: {e}")


# ===========================================================================
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                     TERMINAL  MAIN                                      ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# ===========================================================================

def _pick_backend():
    """Ask user which backend to use. Returns 'http' or 'chromium'."""
    print("\n  Backend:")
    print("    1 / http      -- HTTP (fast, more CAPTCHAs)")
    print("    2 / chromium  -- Chromium (slower, fewer CAPTCHAs)")
    print("    help / tokens -- show template token reference")
    while True:
        raw = input("\n  Backend: ").strip().lower()
        if raw in ("1", "h", "http"):             return "http"
        if raw in ("2", "c", "chromium"):         return "chromium"
        if raw in ("help", "tokens", "?", "h?"):  _print_token_help(); continue
        print("  Type 1 or 2  (or 'help' for token reference)")

def http_main():
    """Terminal flow for the HTTP backend."""
    print("\n== HTTP Backend ==\n")

    ks = input("  Prevent system sleep? (y/n): ").strip().lower() == "y"
    kd = input("  Prevent screen sleep? (y/n): ").strip().lower() == "y"
    prevent_sleep_http(ks, kd)

    url = input("\nEnter Google Form URL: ").strip()
    if not url: print("No URL."); sys.exit(1)

    mode  = prompt_mode()
    times = 1  # [FIX] was 1.0 (float); use int for consistency with prompt_times() return value
    if mode in ("random", "specific"):
        times = prompt_times()
    elif input("  Submit more than once? (y/n, default n): ").strip().lower() == "y":
        times = prompt_times()

    workers = 1
    delay   = (0.0, 0.0)
    if times != 1:
        workers = prompt_workers()
        delay   = prompt_delay()

    times_s = "inf" if times == float("inf") else str(int(times))
    print(f"\n  Mode: {mode}  |  Workers: {workers}  |  Submissions: {times_s}")

    form_action, pages, cookies, is_multipage, seed_fbzx = scan_form(url)
    all_questions = [q for page in pages for q in page]
    if not all_questions: print("  No questions found."); sys.exit(1)
    if is_multipage: print(f"  Multi-page form detected ({len(pages)} pages).")

    scan_mode = "normal" if mode == "specific" else mode
    planned   = prompt_answers(all_questions, scan_mode)
    if not planned: print("  Nothing to submit."); sys.exit(0)

    summarise(planned)

    if input(f"\n  Submit {times_s} time(s)? (y/n): ").strip().lower() != "y":
        print("  Cancelled."); sys.exit(0)

    start = time.time()
    try:
        total, ok, peak, retries = submit_all(form_action, pages, planned, url, cookies,
                                              times, workers, mode, is_multipage, seed_fbzx, delay)
    except KeyboardInterrupt:
        print("\n  Stopped."); sys.exit(0)

    final_summary(total, ok, start, workers, peak, retries)
    log.info(f"Session complete: {ok}/{total}")

def chromium_main(preset_perf=None):
    """Terminal flow for the Chromium backend.
    preset_perf: if set by launcher, skip the interactive perf-mode prompt.
    """
    global chrom_total_submitted, chrom_start_time

    if not SELENIUM_AVAILABLE:
        print("\n  [!] selenium is not installed.")
        print("      Run: pip install selenium webdriver-manager")
        sys.exit(1)

    prevent_sleep_chromium()
    chrom_log_session_start()
    print("\n== Chromium Backend ==\n")

    url      = input("Paste the Google Form link: ").strip()
    raw_mode = input("Mode (specific / random / lazy): ").strip().lower()
    mode_map = {"s": "specific", "r": "random", "l": "lazy"}
    mode     = mode_map.get(raw_mode, raw_mode)
    while mode not in ("specific", "random", "lazy"):
        raw_mode = input("  Invalid. Enter specific/random/lazy (or s/r/l): ").strip().lower()
        mode     = mode_map.get(raw_mode, raw_mode)

    print("\nOpening browser to scan form...")
    chrome_options = ChromeOptions()
    chrome_options.add_experimental_option("detach", True)
    scan_driver = make_driver(chrome_options)
    scan_driver.get(url)
    wait = WebDriverWait(scan_driver, 10)
    time.sleep(2)

    try:
        wait.until(EC.presence_of_element_located((By.XPATH, '//div[@role="listitem"]')))
    except:
        print("[ERROR] Could not load form.")
        scan_driver.quit()
        return

    planned_actions = chrom_scan_questions(scan_driver, wait, mode)
    scan_driver.quit()

    if not planned_actions:
        print("\nNo actions planned. Exiting.")
        return

    print("-" * 50)

    raw_iter = input("\nHow many times to submit in total? (or 'inf'): ").strip().lower()
    while not (raw_iter == 'inf' or (raw_iter.isdigit() and int(raw_iter) >= 1)):
        raw_iter = input("  Invalid. Enter a number or 'inf': ").strip().lower()
    infinite     = raw_iter == 'inf'
    total_target = None if infinite else int(raw_iter)

    raw_inst = input("How many instances (browser windows)? ").strip()
    while not (raw_inst.isdigit() and int(raw_inst) >= 1):
        raw_inst = input("  Invalid. Enter a number >= 1: ").strip()
    num_instances = int(raw_inst)

    if infinite:
        per_instance     = None
        per_instance_rem = None
    else:
        base             = total_target // num_instances
        remainder        = total_target % num_instances
        per_instance     = base
        per_instance_rem = base + remainder

    # If called from launcher.py with a preset perf mode, skip the prompt
    if preset_perf and preset_perf in ("normal", "headless", "turbo"):
        perf_mode = preset_perf
        print(f"  Performance mode: {perf_mode}  (set by launcher)")
    else:
        raw_perf = input("Performance mode (normal / headless / turbo): ").strip().lower()
        while raw_perf not in ("normal", "headless", "turbo", "n", "h", "t"):
            raw_perf = input("  Invalid. Enter normal/headless/turbo (or n/h/t): ").strip().lower()
        perf_map  = {"n": "normal", "h": "headless", "t": "turbo"}
        perf_mode = perf_map.get(raw_perf, raw_perf)
    headless  = perf_mode in ("headless", "turbo")

    window_rects = get_monitor_layout(num_instances) if not headless \
                   else [(0, 0, 0, 0)] * num_instances

    # Graceful shutdown hooks
    atexit.register(kill_all_drivers)
    def _shutdown(*a):
        print("\nShutting down and closing all Chrome windows...")
        kill_all_drivers()
        sys.exit(0)
    signal.signal(signal.SIGINT, _shutdown)
    try:
        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGBREAK, _shutdown)  # Windows Ctrl+Break
    except (AttributeError, OSError):
        pass
    print("  (Press Ctrl+C at any time to stop and close all browsers)")

    print(f"\nStarting {num_instances} instance(s)...\n")
    chrom_total_submitted = 0
    chrom_start_time      = time.time()

    threads = []
    for i in range(num_instances):
        iters = None if infinite else (per_instance_rem if i == 0 else per_instance)
        t = threading.Thread(
            target=chrom_run_instance,
            args=(i + 1, url, planned_actions, iters, infinite,
                  num_instances, window_rects[i], headless, perf_mode),
            daemon=True)
        threads.append(t)
        t.start()
        time.sleep(0.5)

    for t in threads:
        t.join()

    elapsed    = time.time() - chrom_start_time
    mins, secs = divmod(int(elapsed), 60)
    hrs, mins  = divmod(mins, 60)
    print(f"\nAll done! {chrom_total_submitted} forms submitted in {hrs:02d}:{mins:02d}:{secs:02d}")
    allow_sleep_chromium()
    input("Press Enter to exit...")


def main():
    import argparse
    # Optional CLI args so launcher.py can skip the interactive backend prompt.
    # When run directly without args the old interactive prompts still appear.
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--backend", choices=["http", "chromium"], default=None)
    ap.add_argument("--perf",    choices=["normal", "headless", "turbo"], default=None)
    # [NEW] --help or --tokens prints the token reference and exits
    ap.add_argument("--help",   action="store_true", dest="show_help")
    ap.add_argument("--tokens", action="store_true", dest="show_help")
    args, _ = ap.parse_known_args()

    if args.show_help:
        _print_token_help()
        return

    print("=" * 50)
    print("       GOOGLE FORM FILLER")
    print("=" * 50)
    # [NEW] Allow typing 'help' or 'tokens' at the backend prompt to see token docs
    print("  (type 'help' at any prompt to see token reference)")

    # If launcher passed --backend, skip the interactive prompt
    if args.backend:
        backend = args.backend
    else:
        backend = _pick_backend()

    if backend == "help":
        _print_token_help()
        backend = _pick_backend()

    if backend == "http":
        http_main()
    else:
        chromium_main(preset_perf=args.perf)


if __name__ == "__main__":
    main()