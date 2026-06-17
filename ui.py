"""
ui.py -- Form Filler GUI  (CustomTkinter rewrite)
Run directly: python ui.py
Via launcher:  python launcher.py

Tabs:  Setup | Questions | Run | Debug | Customise
[CTK] Migrated from tkinter/ttk to CustomTkinter for rounded, modern widgets.
      tk.StringVar/IntVar/BooleanVar/DoubleVar are still used (CTk accepts them).
      Plain tk is only kept where CTk has no equivalent (ScrolledText-like box,
      Spinbox for weight inputs).
"""

import tkinter as tk
from tkinter import messagebox, colorchooser, font as tkfont, filedialog
import customtkinter as ctk
import threading
import time
import sys
import os
import json
import random
import string   # [NEW] for RND template expansion
import datetime
import re      # [NEW] for URL validation
import csv     # [NEW] for CSV session export

# ---------------------------------------------------------------------------
# Ensure form_filler.py is importable from the same folder
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import form_filler as ff
except ImportError:
    _r = ctk.CTk(); _r.withdraw()
    messagebox.showerror("Import error",
                         "form_filler.py not found.\n"
                         "Make sure ui.py and form_filler.py are in the same folder.")
    sys.exit(1)


# ===========================================================================
# THEME SYSTEM
# All colours live in T (the active theme dict).
# CustomTkinter uses set_appearance_mode / CTkTheme; we drive colours manually
# via configure() calls after every theme change, same as before.
# ===========================================================================

THEME_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_theme.json")

# [FIX issue-6] Saved links file -- persists named URL presets across sessions.
SAVED_LINKS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_links.json")

def _load_saved_links():
    """Return dict of {name: url} from saved_links.json, or {} if not found."""
    try:
        with open(SAVED_LINKS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_saved_links(links: dict):
    """Persist the {name: url} dict to saved_links.json."""
    try:
        with open(SAVED_LINKS_FILE, "w", encoding="utf-8") as f:
            json.dump(links, f, indent=2)
    except Exception as e:
        print(f"Could not save links: {e}")

PRESETS = {
    # ------------------------------------------------------------------
    # [CTK] Dark Purple -- modernised default, softer than original
    # ------------------------------------------------------------------
    "Dark Purple (default)": {
        "bg":       "#16161e", "bg2":     "#1f1f2e", "bg3":    "#2a2a3c",
        "accent":   "#8b7cf8", "accent2": "#b3a9fa",
        "fg":       "#dcdcf0", "fg2":     "#8888aa",
        "success":  "#57e389", "fail":    "#f4786a",
        "font_family": "Segoe UI", "font_size": 13,
        "mono_family": "Consolas", "mono_size": 11,
        "title_text": "Form Filler", "title_font_size": 15,
        "pad_x": 16, "pad_y": 8, "corner_radius": 10,
        "opacity": 1.0, "titlebar_height": 48,
    },
    "Midnight Blue": {
        "bg":       "#0d1117", "bg2":     "#161b22", "bg3":    "#21262d",
        "accent":   "#58a6ff", "accent2": "#79c0ff",
        "fg":       "#c9d1d9", "fg2":     "#8b949e",
        "success":  "#3fb950", "fail":    "#f85149",
        "font_family": "Segoe UI", "font_size": 13,
        "mono_family": "Consolas", "mono_size": 11,
        "title_text": "Form Filler", "title_font_size": 15,
        "pad_x": 16, "pad_y": 8, "corner_radius": 10,
        "opacity": 1.0, "titlebar_height": 48,
    },
    "Forest Green": {
        "bg":       "#1a2e1a", "bg2":     "#223322", "bg3":    "#2a3d2a",
        "accent":   "#4caf50", "accent2": "#81c784",
        "fg":       "#e8f5e9", "fg2":     "#a5d6a7",
        "success":  "#66bb6a", "fail":    "#ef5350",
        "font_family": "Segoe UI", "font_size": 13,
        "mono_family": "Consolas", "mono_size": 11,
        "title_text": "Form Filler", "title_font_size": 15,
        "pad_x": 16, "pad_y": 8, "corner_radius": 10,
        "opacity": 1.0, "titlebar_height": 48,
    },
    "Crimson Dark": {
        "bg":       "#1c0a0a", "bg2":     "#2a1010", "bg3":    "#3d1515",
        "accent":   "#e53935", "accent2": "#ef9a9a",
        "fg":       "#fce4ec", "fg2":     "#ef9a9a",
        "success":  "#66bb6a", "fail":    "#ff8a80",
        "font_family": "Segoe UI", "font_size": 13,
        "mono_family": "Consolas", "mono_size": 11,
        "title_text": "Form Filler", "title_font_size": 15,
        "pad_x": 16, "pad_y": 8, "corner_radius": 10,
        "opacity": 1.0, "titlebar_height": 48,
    },
    "Light / Clean": {
        "bg":       "#f5f5f5", "bg2":     "#e8e8e8", "bg3":    "#d8d8d8",
        "accent":   "#1976d2", "accent2": "#42a5f5",
        "fg":       "#212121", "fg2":     "#757575",
        "success":  "#388e3c", "fail":    "#d32f2f",
        "font_family": "Segoe UI", "font_size": 13,
        "mono_family": "Consolas", "mono_size": 11,
        "title_text": "Form Filler", "title_font_size": 15,
        "pad_x": 16, "pad_y": 8, "corner_radius": 8,
        "opacity": 1.0, "titlebar_height": 48,
    },
    "Hacker Terminal": {
        "bg":       "#000000", "bg2":     "#0a0a0a", "bg3":    "#111111",
        "accent":   "#00ff41", "accent2": "#39ff14",
        "fg":       "#00ff41", "fg2":     "#008f11",
        "success":  "#00ff41", "fail":    "#ff0000",
        "font_family": "Courier New", "font_size": 12,
        "mono_family": "Courier New", "mono_size": 11,
        "title_text": "FORM_FILLER.EXE", "title_font_size": 13,
        "pad_x": 14, "pad_y": 7, "corner_radius": 4,
        "opacity": 0.95, "titlebar_height": 44,
    },
    "Sunset Orange": {
        "bg":       "#1a0a00", "bg2":     "#2d1500", "bg3":    "#3d1f00",
        "accent":   "#ff6d00", "accent2": "#ffab40",
        "fg":       "#fff3e0", "fg2":     "#ffcc80",
        "success":  "#69f0ae", "fail":    "#ff1744",
        "font_family": "Segoe UI", "font_size": 13,
        "mono_family": "Consolas", "mono_size": 11,
        "title_text": "Form Filler", "title_font_size": 15,
        "pad_x": 16, "pad_y": 8, "corner_radius": 10,
        "opacity": 1.0, "titlebar_height": 48,
    },
    "Cyberpunk": {
        "bg":       "#0d0221", "bg2":     "#1a0533", "bg3":    "#240a47",
        "accent":   "#ff00ff", "accent2": "#00ffff",
        "fg":       "#ffffff", "fg2":     "#cc99ff",
        "success":  "#00ffcc", "fail":    "#ff0055",
        "font_family": "Segoe UI", "font_size": 13,
        "mono_family": "Consolas", "mono_size": 11,
        "title_text": "FORM FILLER ///", "title_font_size": 14,
        "pad_x": 16, "pad_y": 8, "corner_radius": 6,
        "opacity": 0.97, "titlebar_height": 50,
    },
    # ------------------------------------------------------------------
    # [NEW] 4chan -- authentic Yotsuba B light theme
    # Colours pulled directly from 4chan's CSS and screenshot:
    #   body bg: #FFFFEE (cream), reply bg: #f0e0d6 (beige),
    #   border: #D9BFB7 (tan), text: #800000 (maroon),
    #   names/quotes: #117743 / #789922 (greens), subject: #cc1105
    # corner_radius: 0 (4chan has zero rounding anywhere)
    # ------------------------------------------------------------------
    "4chan": {
        "bg":       "#FFFFEE", "bg2":     "#f0e0d6", "bg3":    "#D9BFB7",
        "accent":   "#117743", "accent2": "#789922",
        "fg":       "#800000", "fg2":     "#707070",
        "success":  "#117743", "fail":    "#cc1105",
        "font_family": "Arial", "font_size": 10,
        "mono_family": "Courier New", "mono_size": 9,
        "title_text": "Form Filler  [ /ff/ ]", "title_font_size": 11,
        "pad_x": 8, "pad_y": 4, "corner_radius": 0,
        "opacity": 1.0, "titlebar_height": 38,
    },
    # ------------------------------------------------------------------
    # [NEW] Nerf -- bright orange + yellow toy-gun brand palette
    # ------------------------------------------------------------------
    "Nerf": {
        "bg":       "#1a1a1a", "bg2":     "#2b2b2b", "bg3":    "#3a3a3a",
        "accent":   "#f97316", "accent2": "#facc15",
        "fg":       "#ffffff", "fg2":     "#cccccc",
        "success":  "#facc15", "fail":    "#ef4444",
        "font_family": "Arial Black", "font_size": 12,
        "mono_family": "Consolas", "mono_size": 11,
        "title_text": "FORM FILLER  N-STRIKE", "title_font_size": 14,
        "pad_x": 16, "pad_y": 9, "corner_radius": 14,
        "opacity": 1.0, "titlebar_height": 52,
    },
}

def _default_theme(): return dict(PRESETS["Dark Purple (default)"])

# [NEW] Default shutdown alert settings -- stored alongside theme so they persist.
SHUTDOWN_DEFAULTS = {
    "sd_rainbow_text":      True,    # rainbow text in log
    "sd_confetti":          True,    # confetti animation in log area
    "sd_popup":             True,    # OS-level messagebox popup
    "sd_overlay":           True,    # translucent overlay on main window
    "sd_overlay_alpha":     0.55,    # overlay transparency (0.1 - 0.95)
    "sd_overlay_color":     "#ff3333",
    "sd_overlay_text":      "THE FORM HAS SHUT DOWN!",
    "sd_overlay_font_size": 36,
    "sd_overlay_bold":      True,
    "sd_sound":             False,   # system bell (cross-platform)
    "sd_flash_taskbar":     True,    # flash window in taskbar (Windows)
    "sd_confetti_count":    80,
    "sd_confetti_speed":    3,       # 1=slow … 5=fast
    "sd_rainbow_cycles":    3,       # how many full rainbow cycles in the log line
    # [NEW] Overlay keep-on-top mode: True=loop every 100ms, False=lift once only
    "sd_overlay_keep_on_top": True,
    # [NEW] Sleep prevention -- keep system awake while the app is running
    "prevent_system_sleep": False,   # prevent system from sleeping
    "prevent_screen_sleep": False,   # prevent screen/display from sleeping
    # [NEW] Answer validation settings
    # val_on_length_overflow: what to do when a text answer (or token expansion) is too long
    #   "truncate"         -- cut the text to the max allowed length
    #   "skip_answer"      -- leave the field blank (or use random if required)
    #   "skip_submission"  -- discard the entire submission attempt
    # val_on_invalid_choice: what to do when a chosen option doesn't exist in the form
    #   "skip_choice"      -- omit that field (leave unselected)
    #   "skip_submission"  -- discard the entire submission attempt
    "val_on_length_overflow": "truncate",
    "val_on_invalid_choice":  "skip_choice",
}

# [NEW] Validate that a URL looks like a Google Forms link before scanning
# [NEW] Sleep prevention -- cross-platform.
# Windows: SetThreadExecutionState  |  macOS: caffeinate subprocess  |  Linux: systemd-inhibit
_sleep_proc    = None   # subprocess handle (macOS / Linux)
_sleep_enabled = False  # current state

def _apply_sleep_prevention():
    """Read T['prevent_system_sleep'] / T['prevent_screen_sleep'] and enable/disable
    the platform-appropriate sleep prevention mechanism."""
    global _sleep_proc, _sleep_enabled
    want_system = bool(T.get("prevent_system_sleep", False))
    want_screen = bool(T.get("prevent_screen_sleep", False))
    want_any    = want_system or want_screen

    if want_any == _sleep_enabled:
        return  # no change needed

    if sys.platform == "win32":
        try:
            import ctypes
            ES_CONTINUOUS       = 0x80000000
            ES_SYSTEM_REQUIRED  = 0x00000001
            ES_DISPLAY_REQUIRED = 0x00000002
            flags = ES_CONTINUOUS
            if want_system: flags |= ES_SYSTEM_REQUIRED
            if want_screen: flags |= ES_DISPLAY_REQUIRED
            if want_any:
                ctypes.windll.kernel32.SetThreadExecutionState(flags)
            else:
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception:
            pass

    elif sys.platform == "darwin":
        import subprocess
        if _sleep_proc:
            try: _sleep_proc.terminate()
            except Exception: pass
            _sleep_proc = None
        if want_any:
            args = ["caffeinate"]
            if want_system: args.append("-i")   # prevent idle sleep
            if want_screen: args.append("-d")   # prevent display sleep
            try:
                _sleep_proc = subprocess.Popen(args,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    else:  # Linux
        import subprocess
        if _sleep_proc:
            try: _sleep_proc.terminate()
            except Exception: pass
            _sleep_proc = None
        if want_any:
            what = []
            if want_system: what += ["sleep", "idle"]
            if want_screen: what += ["screen-blank"]
            try:
                _sleep_proc = subprocess.Popen(
                    ["systemd-inhibit", "--what=" + ":".join(what),
                     "--who=FormFiller", "--why=Run in progress",
                     "--mode=block", "sleep", "infinity"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                try:
                    _sleep_proc = subprocess.Popen(
                        ["xdg-screensaver", "reset"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass

    _sleep_enabled = want_any


def _validate_form_url(url: str) -> str:
    """Return an error string if url is not a Google Forms URL, else empty string."""
    url = url.strip()
    if not url:
        return "Please enter a URL."
    if not url.startswith(("http://", "https://")):
        return "URL must start with https://"
    if not re.search(r'docs\.google\.com/forms', url, re.IGNORECASE):
        return ("That doesn't look like a Google Forms URL.\n"
                "Expected: https://docs.google.com/forms/d/e/…/viewform")
    return ""

# [NEW] Template token expansion system.
# Supported tokens:
#   <*RND_N*>        -- N random lowercase letters              e.g. <*RND_4*>    -> "xqmz"
#   <*RND_4-6*>      -- random LENGTH between 4 and 6 (range)  e.g. <*RND_4-6*>  -> "xqmzk"
#   <*CRND_N*>       -- N random UPPERCASE letters              e.g. <*CRND_4*>   -> "XQMZ"
#   <*LRND_N*>       -- alias for RND (explicit lowercase)      e.g. <*LRND_4*>   -> "xqmz"
#   <*ANRND_N*>      -- N random mixed-case alphanumeric        e.g. <*ANRND_3*>  -> "aB7"
#   <*CANRND_N*>     -- N random UPPERCASE alphanumeric         e.g. <*CANRND_3*> -> "AB7"
#   <*LANRND_N*>     -- N random lowercase alphanumeric         e.g. <*LANRND_3*> -> "ab7"
#   <*FRND_N*>       -- N random printable ASCII (all)          e.g. <*FRND_5*>   -> "aB3!k"
#   <*CFRND_N*>      -- N random printable ASCII, letters forced UPPERCASE
#   <*LFRND_N*>      -- N random printable ASCII, letters forced lowercase
#   <*URND_N*>       -- N username chars: a-z A-Z 0-9 _         e.g. <*URND_8*>   -> "cool_K3y"
#   <*CURND_N*>      -- same but letters forced UPPERCASE        e.g. <*CURND_6*>  -> "AB_3XQ"
#   <*LURND_N*>      -- same but letters forced lowercase        e.g. <*LURND_6*>  -> "ab_3xq"
#   <*NRND_N*>       -- N random digits 0-9 (numeric string)    e.g. <*NRND_4*>   -> "3847"
#   <*WRND_N*>       -- N random "word" chars: a-z only, no digits/symbols
#                       identical to RND but semantically distinct; useful for names
#   <*SRND_N*>       -- N random symbols/punctuation only       e.g. <*SRND_3*>   -> "!@#"
#   Range syntax works on ALL token types: <*URND_4-8*>, <*NRND_2-5*>, etc.
#   <*filename.txt*> -- random entry from filename.txt in script folder
#                       entries separated by blank lines; non-.txt -> "invalid file type"
# Multiple tokens replaced independently per submission.

# [NEW] Range syntax: N or N-M where N and M are integers.
_SIZE_PART = r'(\d+)(?:-(\d+))?'   # group A=lo, group B=hi (optional)

_TOKEN_PATTERN = re.compile(
    r'<\*'
    r'(?:'
    r'([CLcl]?)(RND)_'    + _SIZE_PART +    # groups 1-4 : prefix, RND, lo, hi
    r'|([CLcl]?)(ANRND)_' + _SIZE_PART +    # groups 5-8 : prefix, ANRND, lo, hi
    r'|([CLcl]?)(FRND)_'  + _SIZE_PART +    # groups 9-12: prefix, FRND, lo, hi
    r'|([CLcl]?)(URND)_'   + _SIZE_PART +    # groups 13-16: prefix, URND,   lo, hi
    r'|([CLcl]?)(URLRND)_' + _SIZE_PART +    # groups 17-20: prefix, URLRND, lo, hi  [NEW]
    r'|(NRND)_'            + _SIZE_PART +    # groups 21-23: NRND, lo, hi
    r'|(WRND)_'            + _SIZE_PART +    # groups 24-26: WRND, lo, hi
    r'|(SRND)_'            + _SIZE_PART +    # groups 27-29: SRND, lo, hi
    r'|(QSTN)_(\d+)'                        +# groups 30-31: QSTN, question index  [NEW]
    r'|([^*]+\.[^*]+)'                        # group 32   : bare filename.ext
    r')'
    r'\*>'
)

_ALPHA_LOWER  = string.ascii_lowercase
_ALPHA_UPPER  = string.ascii_uppercase
_ALPHA_BOTH   = string.ascii_letters
_AN_LOWER     = string.ascii_lowercase + string.digits
_AN_UPPER     = string.ascii_uppercase + string.digits
_AN_BOTH      = string.ascii_letters   + string.digits
_FULL_ASCII   = string.ascii_letters   + string.digits + string.punctuation
# [FIX] URND pools -- underscore removed from random.choices pool entirely;
# underscore placement is now handled explicitly by _gen_username() below.
_USERNAME_BASE = string.ascii_letters + string.digits   # no _ here -- added deliberately by _gen_username
_USERNAME_UP   = string.ascii_uppercase + string.digits
_USERNAME_LO   = string.ascii_lowercase + string.digits

def _gen_username(n: int, prefix: str) -> str:
    """Generate a username-style string of exactly n chars:
    - chars are a-z A-Z 0-9 (casing controlled by prefix C/L/none)
    - at most ONE underscore, placed at a random interior position
      that is NOT first, NOT last, and NOT adjacent to another _ (moot
      since there's only one, but the position must be index 1..n-2)
    - n=1 or n=2: no underscore possible (no valid interior slot for n=1;
      for n=2 there's no index that is both non-first and non-last)
    """
    base = _USERNAME_UP if prefix == "C" else (_USERNAME_LO if prefix == "L" else _USERNAME_BASE)
    chars = random.choices(base, k=n)
    # Only insert underscore if there's a valid interior position (needs n >= 3)
    # and we randomly decide to (50% chance keeps output varied)
    if n >= 3 and random.random() < 0.5:
        pos = random.randint(1, n - 2)   # guaranteed not first or last
        chars[pos] = "_"
    return ''.join(chars)
_URL_CHARS    = string.ascii_letters   + string.digits + "_-"  # URLRND: a-z A-Z 0-9 _ -  [NEW]
_URL_CHARS_UP = string.ascii_uppercase + string.digits + "_-"  # CURLRND  [NEW]
_URL_CHARS_LO = string.ascii_lowercase + string.digits + "_-"  # LURLRND  [NEW]
_DIGITS_ONLY  = string.digits                                   # NRND: 0-9
_SYMBOLS_ONLY = string.punctuation                             # SRND: !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~

# Cache loaded list files so we only read each file once per session.
_list_cache: dict = {}

def _load_list_file(filename: str) -> list:
    """Load a .txt file from the script folder, splitting entries on blank lines.
    Returns a list of non-empty stripped strings. Result is cached after first load."""
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

def _expand_templates(text: str, _seen_files: frozenset = frozenset(),
                      qstn_map: dict | None = None) -> str:
    """Replace all recognised tokens in text with their random expansions.
    _seen_files tracks which .txt files are currently in the call stack so that
    a file referencing itself (directly or indirectly) just prints the token as
    plain text the second time instead of looping forever.
    qstn_map: {1: 'david', 2: 'gratsky', ...} -- resolved answer values by
              1-based question index; <*QSTN_N*> substitutes answer N's value.
    """
    def _resolve_size(lo_str, hi_str):
        """Return a random int in [lo, hi]. If hi_str is None, return lo exactly."""
        lo = max(1, min(256, int(lo_str)))
        if hi_str is None:
            return lo
        hi = max(1, min(256, int(hi_str)))
        if hi < lo: lo, hi = hi, lo   # swap if user wrote them backwards e.g. <*RND_6-4*>
        return random.randint(lo, hi)

    def _replace(m):
        # Groups (from updated _TOKEN_PATTERN):
        # 1=prefix 2=RND    3=lo 4=hi   |
        # 5=prefix 6=ANRND  7=lo 8=hi   |
        # 9=prefix 10=FRND  11=lo 12=hi  |
        # 13=prefix 14=URND 15=lo 16=hi  |
        # 17=prefix 18=URLRND 19=lo 20=hi |
        # 21=NRND 22=lo 23=hi            |
        # 24=WRND 25=lo 26=hi            |
        # 27=SRND 28=lo 29=hi            |
        # 30=QSTN 31=index               | [NEW]
        # 32=filename
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
        elif m.group(14): # URND family -- username: a-z A-Z 0-9, at most one _ in interior position
            prefix = (m.group(13) or "").upper()
            n = _resolve_size(m.group(15), m.group(16))
            return _gen_username(n, prefix)
        elif m.group(18): # URLRND family (URL-safe: a-z A-Z 0-9 _ -)
            prefix = (m.group(17) or "").upper()
            n = _resolve_size(m.group(19), m.group(20))
            pool = _URL_CHARS_UP if prefix == "C" else (_URL_CHARS_LO if prefix == "L" else _URL_CHARS)
            return ''.join(random.choices(pool, k=n))
        elif m.group(21): # NRND (digits only)
            n = _resolve_size(m.group(22), m.group(23))
            return ''.join(random.choices(_DIGITS_ONLY, k=n))
        elif m.group(24): # WRND (word / letters only, lowercase -- same as RND but explicit intent)
            n = _resolve_size(m.group(25), m.group(26))
            return ''.join(random.choices(_ALPHA_LOWER, k=n))
        elif m.group(27): # SRND (symbols / punctuation only)
            n = _resolve_size(m.group(28), m.group(29))
            return ''.join(random.choices(_SYMBOLS_ONLY, k=n))
        elif m.group(30): # [NEW] QSTN_N -- resolved value of question N in this submission
            idx = int(m.group(31))
            if qstn_map and idx in qstn_map:
                return str(qstn_map[idx])
            return m.group(0)   # leave token as-is if map not available (e.g. preview mode)
        elif m.group(32): # filename.ext
            fname = m.group(32).strip()
            fname_key = fname.lower()
            if fname_key in _seen_files:
                return m.group(0)
            entries = _load_list_file(fname)
            if not entries:
                return ""
            # [FIX] Pass qstn_map through recursive file expansion so QSTN works inside .txt files
            return _expand_templates(random.choice(entries), _seen_files | {fname_key}, qstn_map)
        return m.group(0)
    return _TOKEN_PATTERN.sub(_replace, text)

_expand_rnd = _expand_templates

def _has_rnd(text: str) -> bool:
    """Return True if text contains at least one template token."""
    return bool(_TOKEN_PATTERN.search(text))


# ===========================================================================
# ANSWER VALIDATION
# Checks a resolved answer against the question's known constraints and
# applies the configured overflow/invalid-choice policy.
#
# Returns a tuple: (final_value, action)
#   action = "ok"               -- use final_value as-is
#   action = "skip_answer"      -- blank/omit this field
#   action = "skip_submission"  -- abort the whole submission
# ===========================================================================

def _validate_text_answer(value: str, q: dict) -> tuple:
    """Validate a resolved text answer against the question's validation constraints.
    Returns (final_value, action) where action is 'ok', 'skip_answer', or 'skip_submission'.
    """
    overflow_policy = T.get("val_on_length_overflow", "truncate")
    vtype = q.get("validation", {}).get("type")
    vargs = q.get("validation", {}).get("args", [])
    if isinstance(vargs, (int, float)): vargs = [vargs]

    # --- Number validation ---
    if vtype == ff.VType.NUMBER:
        # Try to parse the value as a number
        try:
            num = float(value)
        except (ValueError, TypeError):
            # Not a valid number at all -- skip answer
            return ("", "skip_answer")

        # Determine the valid range from vargs using form_filler's _number_range logic
        try:
            lo, hi = ff._number_range(vargs)
        except Exception:
            lo, hi = None, None

        if lo is not None and num < lo:
            # Below minimum -- truncating doesn't make sense for numbers, so skip
            if overflow_policy == "skip_submission":
                return (value, "skip_submission")
            return ("", "skip_answer")
        if hi is not None and num > hi:
            if overflow_policy == "skip_submission":
                return (value, "skip_submission")
            return ("", "skip_answer")
        return (value, "ok")

    # --- Text length validation ---
    if vtype == ff.VType.TEXT_LEN and vargs:
        try:
            sub = int(vargs[0]) if vargs else 0
            threshold = int(vargs[1]) if len(vargs) > 1 and vargs[1] is not None else None
        except (ValueError, TypeError):
            sub, threshold = 0, None

        length = len(value)

        # sub codes from form_filler: 1=>, 2=>=, 3=<, 4=<=, 5==, 6!=, 7=between, 8=not between
        if threshold is not None:
            too_short = (sub == 1 and length <= threshold) or \
                        (sub == 2 and length < threshold)  or \
                        (sub == 5 and length != threshold)
            too_long  = (sub == 3 and length >= threshold) or \
                        (sub == 4 and length > threshold)  or \
                        (sub == 5 and length != threshold)

            if too_long or (sub == 4 and length > threshold) or (sub == 3 and length >= threshold):
                # Text is too long
                if overflow_policy == "truncate":
                    max_len = threshold - (1 if sub == 3 else 0)
                    return (value[:max(1, max_len)], "ok")
                elif overflow_policy == "skip_submission":
                    return (value, "skip_submission")
                else:
                    return ("", "skip_answer")

            if too_short:
                # Too short -- can't fix by truncating, skip
                if overflow_policy == "skip_submission":
                    return (value, "skip_submission")
                return ("", "skip_answer")

        # Between / not-between (sub 7/8)
        if sub == 7 and len(vargs) >= 3:
            try:
                lo2 = int(vargs[1]) if vargs[1] is not None else 0
                hi2 = int(vargs[2]) if vargs[2] is not None else 9999
            except (ValueError, TypeError):
                lo2, hi2 = 0, 9999
            if length > hi2:
                if overflow_policy == "truncate":
                    return (value[:hi2], "ok")
                elif overflow_policy == "skip_submission":
                    return (value, "skip_submission")
                else:
                    return ("", "skip_answer")
            if length < lo2:
                if overflow_policy == "skip_submission":
                    return (value, "skip_submission")
                return ("", "skip_answer")

    return (value, "ok")


def _validate_choice_answer(choice, all_opts: list, q: dict) -> tuple:
    """Validate a resolved choice index or list of indices against available options.
    Returns (final_choice, action).
    choice can be an int index, a list of int indices, or 'r' (random -- always ok).
    """
    if choice == "r":
        return (choice, "ok")

    invalid_policy = T.get("val_on_invalid_choice", "skip_choice")
    n_opts = len(all_opts)

    if isinstance(choice, list):
        # Checkbox: filter out out-of-range indices
        valid = [i for i in choice if isinstance(i, int) and 0 <= i < n_opts]
        if not valid and choice:
            # All chosen options were invalid
            if invalid_policy == "skip_submission":
                return (choice, "skip_submission")
            return ([], "skip_answer")
        return (valid, "ok")
    else:
        # Single choice
        if not isinstance(choice, int) or choice < 0 or choice >= n_opts:
            if invalid_policy == "skip_submission":
                return (choice, "skip_submission")
            return (None, "skip_answer")
        return (choice, "ok")


def _load_saved_theme():
    base = _default_theme()
    base.update(SHUTDOWN_DEFAULTS)   # apply all defaults first
    try:
        with open(THEME_FILE, encoding="utf-8") as f:
            data = json.load(f)
        # Only update keys that exist in data -- missing keys stay as defaults above.
        # This means new keys added to SHUTDOWN_DEFAULTS always get their default value
        # on first run even if the theme file predates them.
        for k, v in data.items():
            base[k] = v
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass   # no file or corrupt -- use defaults
    return base

T = _load_saved_theme()

def _save_theme():
    try:
        with open(THEME_FILE, "w", encoding="utf-8") as f:
            json.dump(T, f, indent=2)
    except Exception as e:
        print(f"Could not save theme: {e}")

# Convenience colour accessors
def BG():      return T["bg"]
def BG2():     return T["bg2"]
def BG3():     return T["bg3"]
def ACCENT():  return T["accent"]
def ACCENT2(): return T["accent2"]
def FG():      return T["fg"]
def FG2():     return T["fg2"]
def SUCCESS(): return T["success"]
def FAIL():    return T["fail"]
def FONT():    return (T["font_family"], T["font_size"])
def FONT_BOLD(): return (T["font_family"], T["font_size"], "bold")
def FONT_BIG():  return (T["font_family"], T["title_font_size"], "bold")
def FONT_MONO(): return (T["mono_family"], T["mono_size"])
def CR():      return T.get("corner_radius", 10)   # [CTK] corner radius


# ===========================================================================
# WIDGET REGISTRY  (unchanged purpose -- live recolour on theme change)
# ===========================================================================
_widget_registry = []

def _reg(widget, role):
    _widget_registry.append((widget, role))
    return widget


def _apply_theme(root, nb, title_label):
    """Recolour every registered widget + CTk globals."""
    global _widget_registry
    # --- CTk global colours ------------------------------------------------
    # [CTK] CustomTkinter uses a global colour system; we override it by
    # setting appearance to "dark" (prevents auto-override) then manually
    # configure each widget.  We don't call set_default_color_theme() here
    # because that only applies at startup.
    ctk.set_appearance_mode("dark")

    # --- purge dead references ---
    live = []
    for w, r in _widget_registry:
        try:
            if w.winfo_exists(): live.append((w, r))
        except Exception: pass
    _widget_registry[:] = live

    role_cfg = {
        # CTk widgets
        "frame":        {"fg_color": BG()},
        "frame2":       {"fg_color": BG2()},
        "frame3":       {"fg_color": BG3()},
        "label":        {"text_color": FG(),   "fg_color": "transparent"},
        "label2":       {"text_color": FG2(),  "fg_color": "transparent"},
        "label_accent": {"text_color": ACCENT2(), "fg_color": "transparent"},
        "label_bold":   {"text_color": FG(),   "fg_color": "transparent"},
        "btn":          {"fg_color": ACCENT(), "hover_color": ACCENT2(),
                         "text_color": _btn_text_color(), "corner_radius": CR()},
        "btn_danger":   {"fg_color": FAIL(),   "hover_color": FAIL(),
                         "text_color": _btn_text_color(), "corner_radius": CR()},
        "btn_success":  {"fg_color": SUCCESS(),"hover_color": SUCCESS(),
                         "text_color": _btn_text_color(), "corner_radius": CR()},
        "entry":        {"fg_color": BG3(), "text_color": FG(),
                         "border_color": BG3(), "corner_radius": CR()},
        "textbox":      {"fg_color": BG2(), "text_color": FG2(),
                         "border_color": BG3(), "corner_radius": CR()},
        "switch":       {"fg_color": BG3(), "progress_color": ACCENT(),
                         "button_color": ACCENT2()},
        "radio":        {"fg_color": ACCENT(), "text_color": FG(),
                         "bg_color": BG()},
        "check":        {"fg_color": ACCENT(), "text_color": FG2(),
                         "bg_color": BG(), "checkmark_color": "#ffffff",
                         "border_color": BG3()},
        "check_opt":    {"fg_color": ACCENT(), "text_color": FG(),
                         "bg_color": BG(), "checkmark_color": "#ffffff",
                         "border_color": BG3()},
        "seg":          {"fg_color": BG3(), "selected_color": ACCENT(),
                         "selected_hover_color": ACCENT2(),
                         "unselected_color": BG3(),
                         "text_color": FG(), "corner_radius": CR()},
        "progress":     {"fg_color": BG3(), "progress_color": ACCENT(),
                         "corner_radius": 6},
        "sep":          {"fg_color": BG3()},
        # Plain tk widgets still in use
        "tk_label":     {"bg": BG(),  "fg": FG()},
        "tk_label2":    {"bg": BG(),  "fg": FG2()},
        "tk_label_acc": {"bg": BG(),  "fg": ACCENT2()},
        "tk_logbox":    {"bg": BG2(), "fg": FG2(),
                         "insertbackground": FG(), "font": FONT_MONO()},
        "tk_spin":      {"bg": BG3(), "fg": FG(), "buttonbackground": BG2(),
                         "insertbackground": FG()},
        "tk_sep":       {"bg": BG3()},
        "tk_frame":     {"bg": BG()},
    }

    for w, role in _widget_registry:
        cfg = role_cfg.get(role, {})
        if not cfg: continue
        try: w.configure(**cfg)
        except Exception: pass

    # Root + notebook background
    try: root.configure(fg_color=BG())
    except Exception: pass
    try: nb.configure(fg_color=BG(), segmented_button_fg_color=BG2(),
                      segmented_button_selected_color=BG3(),
                      segmented_button_selected_hover_color=BG3(),
                      segmented_button_unselected_color=BG2(),
                      text_color=FG2())
    except Exception: pass

    # Title label
    try:
        title_label.configure(text=" " + T["title_text"],
                               text_color=ACCENT2(),
                               font=ctk.CTkFont(T["font_family"],
                                                T["title_font_size"],
                                                weight="bold"))
    except Exception: pass

    # Opacity
    try: root.attributes("-alpha", max(0.1, min(1.0, T["opacity"])))
    except Exception: pass


# ===========================================================================
# WIDGET FACTORIES
# [CTK] All factories now return CTk widgets.  Plain tk kept only for
#       ScrolledText equivalent (CTkTextbox) and Spinbox (no CTk equivalent).
# ===========================================================================

def _is_light_theme():
    """Return True if bg is a light colour (brightness > 128).
    Used to flip button text to dark so it stays readable."""
    try:
        c = T["bg"].lstrip("#")
        r, g, b = int(c[0:2],16), int(c[2:4],16), int(c[4:6],16)
        return (r*0.299 + g*0.587 + b*0.114) > 128
    except Exception: return False

def _btn_text_color():
    # [THEME] On light themes (4chan) buttons need dark text, not white
    return T["fg"] if _is_light_theme() else "#ffffff"

# [FIX] _font() body was inside _btn_text_color() after its return (dead code),
# so _font was never defined. Every widget factory call to _font() crashed.
def _font(bold=False, mono=False, size=None):
    fam  = T["mono_family"] if mono else T["font_family"]
    sz   = size or (T["mono_size"] if mono else T["font_size"])
    wt   = "bold" if bold else "normal"
    return ctk.CTkFont(fam, sz, weight=wt)

def _label(parent, text, role="label", **kw):
    color = ACCENT2() if role == "label_accent" else (FG2() if "2" in role else FG())
    bold  = "bold" in role
    w = ctk.CTkLabel(parent, text=text, text_color=color, fg_color="transparent",
                     font=_font(bold=bold), **kw)
    _reg(w, role); return w

def _entry(parent, width=280, **kw):
    w = ctk.CTkEntry(parent, width=width, fg_color=BG3(), text_color=FG(),
                     border_color=BG3(), corner_radius=CR(),
                     font=_font(), **kw)
    _reg(w, "entry"); return w

def _button(parent, text, command, role="btn", width=0, **kw):
    color  = ACCENT()  if role == "btn"         else \
             FAIL()    if role == "btn_danger"   else \
             SUCCESS() if role == "btn_success"  else ACCENT()
    hover  = ACCENT2() if role == "btn"         else color
    # [THEME] Text colour adapts: dark on light themes, white on dark themes
    w = ctk.CTkButton(parent, text=text, command=command,
                      fg_color=color, hover_color=hover,
                      text_color=_btn_text_color(), corner_radius=CR(),
                      font=_font(bold=True),
                      width=width or 0, **kw)
    _reg(w, role); return w

def _frame(parent, role="frame", **kw):
    color = BG() if role == "frame" else BG2() if role == "frame2" else BG3()
    w = ctk.CTkFrame(parent, fg_color=color, corner_radius=0, **kw)
    _reg(w, role); return w

def _textbox(parent, height=180, mono=False, **kw):
    """CTkTextbox replaces ScrolledText.  Has built-in scrollbar."""
    w = ctk.CTkTextbox(parent, height=height, fg_color=BG2(), text_color=FG2(),
                       border_color=BG3(), corner_radius=CR(),
                       font=_font(mono=True), **kw)
    _reg(w, "textbox"); return w

def _scrollframe(parent):
    """CTkScrollableFrame -- replaces the manual canvas+scrollbar setup.
    [CTK] Mousewheel is handled natively; no bind_all hack needed."""
    w = ctk.CTkScrollableFrame(parent, fg_color=BG(), corner_radius=0)
    _reg(w, "frame"); return w

def _separator(parent):
    w = ctk.CTkFrame(parent, height=1, fg_color=BG3(), corner_radius=0)
    _reg(w, "sep"); return w

def _check(parent, text, variable, role="check", command=None, **kw):
    w = ctk.CTkCheckBox(parent, text=text, variable=variable,
                        fg_color=ACCENT(), text_color=FG2() if role=="check" else FG(),
                        checkmark_color="#ffffff", border_color=BG3(),
                        bg_color=BG(), hover_color=ACCENT2(),
                        font=_font(), command=command, **kw)
    _reg(w, role); return w

def _radio(parent, text, variable, value, **kw):
    w = ctk.CTkRadioButton(parent, text=text, variable=variable, value=value,
                           fg_color=ACCENT(), text_color=FG(), bg_color=BG(),
                           hover_color=ACCENT2(), font=_font(), **kw)
    _reg(w, "radio"); return w

# Spinbox has no CTk equivalent -- keep plain tk
def _spinbox(parent, from_, to, textvariable, width=5):
    w = tk.Spinbox(parent, from_=from_, to=to, textvariable=textvariable,
                   width=width, font=FONT(), bg=BG3(), fg=FG(),
                   buttonbackground=BG2(), insertbackground=FG(),
                   relief="flat", bd=0)
    _reg(w, "tk_spin"); return w


# ===========================================================================
# PER-QUESTION WIDGET
# [CTK] Rebuilt with CTk widgets; logic (resolve()) is unchanged.
# ===========================================================================

class QuestionWidget:
    def __init__(self, parent, q, row_idx):
        self.q     = q
        self.type  = q["type"]
        self.entry = q["entry"]
        self._vars = {}
        # CTkScrollableFrame children use pack/grid normally
        self._frame = ctk.CTkFrame(parent, fg_color=BG2(), corner_radius=8)
        self._frame.pack(fill="x", padx=12, pady=5)
        _reg(self._frame, "frame2")
        self._build()

    def _build(self):
        q     = self.q
        title = q["title"] or q["entry"]
        req   = "  *" if q["is_required"] else ""
        qtype = self.type
        opts  = q.get("options", [])
        QT    = ff.QType

        tl = ctk.CTkLabel(self._frame, text=f"{title}{req}",
                          text_color=ACCENT2(), fg_color="transparent",
                          font=_font(bold=True), anchor="w")
        tl.pack(fill="x", padx=12, pady=(10, 4))
        _reg(tl, "label_accent")

        if qtype in (QT.SHORT_TEXT, QT.LONG_TEXT):
            self._vars["random"] = tk.BooleanVar(value=True)
            _check(self._frame, "Random each submission",
                   self._vars["random"], command=self._toggle_text
                   ).pack(anchor="w", padx=12, pady=2)
            self._text_entry = _entry(self._frame, width=500,
                                       placeholder_text="Tokens: <*RND_4*> <*RND_4-8*> <*URND_8*> <*NRND_6*> <*ANRND_4*> <*FRND_4*> <*colors.txt*>  — see Help tab")
            self._text_entry.pack(fill="x", padx=12, pady=(2,8))
            self._text_entry.configure(state="disabled")

        elif qtype in (QT.RADIO, QT.DROPDOWN, QT.LINEAR, QT.STAR):
            all_opts         = opts + (["Other"] if q.get("has_other") else [])
            all_opts_display = ["(random)"] + all_opts
            self._vars["choice"] = tk.StringVar(value="(random)")
            for opt in all_opts_display:
                _radio(self._frame, opt, self._vars["choice"], opt
                       ).pack(anchor="w", padx=20, pady=1)

            # Weight sub-frame
            self._weight_frame = ctk.CTkFrame(self._frame, fg_color=BG3(), corner_radius=6)
            _reg(self._weight_frame, "frame3")
            self._weight_frame.pack(anchor="w", padx=12, pady=(4,4))
            ctk.CTkLabel(self._weight_frame, text="  Weights (for random):",
                         text_color=FG2(), fg_color="transparent",
                         font=_font()).grid(row=0, column=0, columnspan=99, sticky="w", padx=4)
            # [FIX] Removed orphaned invisible label (created via walrus but never packed/gridded)
            self._vars["weights"] = {}
            for col_i, opt in enumerate(all_opts):
                ctk.CTkLabel(self._weight_frame, text=f"  {opt[:18]}",
                             text_color=FG2(), fg_color="transparent",
                             font=ctk.CTkFont(T["font_family"], T["font_size"]-1)
                             ).grid(row=1, column=col_i, padx=4, sticky="w")
                wv = tk.IntVar(value=1)
                self._vars["weights"][opt] = wv
                _spinbox(self._weight_frame, 0, 100, wv, width=4
                         ).grid(row=2, column=col_i, padx=4)

            def _toggle_weights(*_, wf=self._weight_frame, cv=self._vars["choice"]):
                if cv.get() == "(random)": wf.pack(anchor="w", padx=12, pady=(4,4))
                else:                      wf.pack_forget()
            self._vars["choice"].trace_add("write", _toggle_weights)

        elif qtype == QT.CHECKBOX:
            all_opts = opts + (["Other"] if q.get("has_other") else [])
            self._vars["checks"]    = {}
            self._vars["random_cb"] = tk.BooleanVar(value=True)
            _check(self._frame, "Random each submission",
                   self._vars["random_cb"], command=self._toggle_cb_weights
                   ).pack(anchor="w", padx=12, pady=2)
            for opt in all_opts:
                v = tk.BooleanVar(value=False)
                self._vars["checks"][opt] = v
                _check(self._frame, opt, v, role="check_opt"
                       ).pack(anchor="w", padx=24, pady=1)

            self._cb_weight_frame = ctk.CTkFrame(self._frame, fg_color=BG3(), corner_radius=6)
            _reg(self._cb_weight_frame, "frame3")
            self._cb_weight_frame.pack(anchor="w", padx=12, pady=(4,4))
            ctk.CTkLabel(self._cb_weight_frame, text="  Weights (for random):",
                         text_color=FG2(), fg_color="transparent",
                         font=_font()).grid(row=0, column=0, columnspan=99, sticky="w", padx=4)
            self._vars["cb_weights"] = {}
            for col_i, opt in enumerate(all_opts):
                ctk.CTkLabel(self._cb_weight_frame, text=f"  {opt[:18]}",
                             text_color=FG2(), fg_color="transparent",
                             font=ctk.CTkFont(T["font_family"], T["font_size"]-1)
                             ).grid(row=1, column=col_i, padx=4, sticky="w")
                wv = tk.IntVar(value=1)
                self._vars["cb_weights"][opt] = wv
                _spinbox(self._cb_weight_frame, 0, 100, wv, width=4
                         ).grid(row=2, column=col_i, padx=4)

        elif qtype == QT.DATE:
            self._vars["random"] = tk.BooleanVar(value=True)
            _check(self._frame, "Random each submission",
                   self._vars["random"], command=self._toggle_date
                   ).pack(anchor="w", padx=12, pady=2)
            row = ctk.CTkFrame(self._frame, fg_color="transparent"); row.pack(anchor="w", padx=12)
            _reg(row, "frame")
            for ltext, attr, w in [("MM:", "_mm", 60), ("DD:", "_dd", 60), ("YYYY:", "_yy", 80)]:
                ctk.CTkLabel(row, text=ltext, text_color=FG2(), fg_color="transparent",
                             font=_font()).pack(side="left")
                e = _entry(row, width=w); e.pack(side="left", padx=2)
                setattr(self, attr, e)
            for w in (self._mm, self._dd, self._yy): w.configure(state="disabled")

        elif qtype == QT.TIME:
            self._vars["random"] = tk.BooleanVar(value=True)
            _check(self._frame, "Random each submission",
                   self._vars["random"], command=self._toggle_time
                   ).pack(anchor="w", padx=12, pady=2)
            row = ctk.CTkFrame(self._frame, fg_color="transparent"); row.pack(anchor="w", padx=12)
            _reg(row, "frame")
            for ltext, attr in [("HH:", "_hh"), ("MM:", "_mmin")]:
                ctk.CTkLabel(row, text=ltext, text_color=FG2(), fg_color="transparent",
                             font=_font()).pack(side="left")
                e = _entry(row, width=60); e.pack(side="left", padx=2)
                setattr(self, attr, e)
            for w in (self._hh, self._mmin): w.configure(state="disabled")

        # [FIX issue-1] FILE_UPLOAD (qtype 13) removed -- filtered out before reaching here.
        # No branch needed; fall through to the GRID branch below.

        elif qtype in (QT.GRID, QT.CHECKBOX_GRID):
            self._vars["grid"] = {}
            for grow in q.get("grid_rows", []):
                rl = grow["label"] or grow["entry"]
                ctk.CTkLabel(self._frame, text=f"  Row: {rl}", text_color=FG2(),
                             fg_color="transparent", font=_font()).pack(anchor="w", padx=12)
                if qtype == QT.CHECKBOX_GRID:
                    row_checks = {}
                    for opt in opts:
                        v = tk.BooleanVar(value=False)
                        row_checks[opt] = v
                        _check(self._frame, f"    {opt}", v, role="check_opt"
                               ).pack(anchor="w", padx=28, pady=1)
                    self._vars["grid"][grow["entry"]] = ("checkbox", row_checks)
                else:
                    rv = tk.StringVar(value="(random)")
                    for opt in ["(random)"] + opts:
                        _radio(self._frame, f"    {opt}", rv, opt
                               ).pack(anchor="w", padx=28, pady=1)
                    self._vars["grid"][grow["entry"]] = ("radio", rv)

        _separator(self._frame).pack(fill="x", padx=12, pady=(8, 6))

    # --- toggle helpers (unchanged logic) ---
    def _toggle_text(self):
        # [NEW] If random is checked, disable the text entry (fully random).
        # If random is unchecked, enable it so the user can type a fixed value
        # OR a template like test<*RND_4*>123 for partial randomisation.
        self._text_entry.configure(state="disabled" if self._vars["random"].get() else "normal")

    def _toggle_cb_weights(self):
        if not hasattr(self, "_cb_weight_frame"): return
        if self._vars["random_cb"].get(): self._cb_weight_frame.pack(anchor="w", padx=12, pady=(4,4))
        else:                             self._cb_weight_frame.pack_forget()

    def _toggle_date(self):
        s = "disabled" if self._vars["random"].get() else "normal"
        for w in (self._mm, self._dd, self._yy): w.configure(state=s)

    def _toggle_time(self):
        s = "disabled" if self._vars["random"].get() else "normal"
        for w in (self._hh, self._mmin): w.configure(state=s)

    def resolve(self):
        """Collect form answer -- logic completely unchanged from original."""
        q     = self.q
        qtype = self.type
        opts  = q.get("options", [])
        QT    = ff.QType
        base  = dict(q)

        if qtype in (QT.SHORT_TEXT, QT.LONG_TEXT):
            raw_val = self._text_entry.get().strip()
            if self._vars["random"].get():
                # Fully random -- form_filler will generate a random string
                base["value"] = "r"
            elif _has_rnd(raw_val):
                # [NEW] Template mode: contains <*RND_N*> tokens.
                # Store the raw template; _expand_rnd() will be called per-submission
                # in form_filler so each submission gets a different expansion.
                # We prefix with "__RND__:" so form_filler knows to expand it.
                base["value"] = "__RND__:" + raw_val
            else:
                # Fixed text or empty (fall back to random)
                base["value"] = raw_val or "r"

        elif qtype in (QT.RADIO, QT.DROPDOWN, QT.LINEAR, QT.STAR):
            all_opts = opts + (["Other"] if q.get("has_other") else [])
            chosen   = self._vars["choice"].get()
            if chosen == "(random)":
                base["choice"]   = "r"
                base["all_opts"] = all_opts
                raw_w = [self._vars["weights"][o].get() for o in all_opts
                         if o in self._vars.get("weights", {})]
                base["weights"] = raw_w if raw_w and any(w != raw_w[0] for w in raw_w) else None
            else:
                idx = all_opts.index(chosen) if chosen in all_opts else 0
                base["choice"]   = idx
                base["all_opts"] = all_opts
                base["weights"]  = None
            base["other_text"] = ""

        elif qtype == QT.CHECKBOX:
            all_opts = opts + (["Other"] if q.get("has_other") else [])
            if self._vars["random_cb"].get():
                base["choice"] = "r"
                raw_w = [self._vars["cb_weights"][o].get() for o in all_opts
                         if o in self._vars.get("cb_weights", {})]
                base["weights"] = raw_w if raw_w and any(w != raw_w[0] for w in raw_w) else None
            else:
                chosen = [i for i, opt in enumerate(all_opts)
                          if self._vars["checks"].get(opt, tk.BooleanVar()).get()]
                base["choice"]  = chosen if chosen else "r"
                base["weights"] = None
            base["all_opts"]    = all_opts
            base["other_texts"] = {}

        elif qtype == QT.DATE:
            if self._vars["random"].get():
                base["value"] = "r"; base["date_range"] = (1990, 2005)
            else:
                mm = self._mm.get().strip(); dd = self._dd.get().strip(); yy = self._yy.get().strip()
                base["value"] = f"{mm}/{dd}/{yy}" if mm and dd and yy else "r"
                base["date_range"] = None

        elif qtype == QT.TIME:
            if self._vars["random"].get():
                base["value"] = "r"; base["time_range"] = (0, 23)
            else:
                hh = self._hh.get().strip(); mmin = self._mmin.get().strip()
                base["value"] = f"{hh}:{mmin}" if hh and mmin else "r"
                base["time_range"] = None

        elif qtype in (QT.GRID, QT.CHECKBOX_GRID):
            grid_choices = {}
            for row_entry, (kind, var) in self._vars.get("grid", {}).items():
                if kind == "radio":
                    chosen = var.get()
                    grid_choices[row_entry] = "r" if chosen == "(random)" \
                        else (opts.index(chosen) if chosen in opts else 0)
                else:
                    chosen = [i for i, opt in enumerate(opts)
                              if var.get(opt, tk.BooleanVar()).get()]
                    grid_choices[row_entry] = chosen if chosen else "r"
            base["grid_choices"] = grid_choices
            base["weights"]      = None

        # [FIX issue-1] FILE_UPLOAD (type 13) is filtered out before questions are shown,
        # so this branch is never reached. Kept as a safety return None.
        elif qtype == 13:
            return None

        return base


# ===========================================================================
# HTTP planned -> Chromium action converter  (unchanged)
# ===========================================================================
def _http_planned_to_chrom_actions(planned):
    QT = ff.QType; actions = []
    # [FIX] page_index on HTTP-scanned questions is the PAGE number (0,1,2...),
    # NOT the DOM position inside div[role="listitem"]. Using it as q_idx caused
    # every action to get q_idx=0 and target only the first question.
    # Google Forms DOM layout: listitem[0] = form title block (not a question),
    # listitem[1] = Q1, listitem[2] = Q2, etc.
    # Correct DOM index = 1 (title offset) + sequential question position.
    DOM_OFFSET = 1  # listitem[0] is the form title/description, not a question
    for idx, a in enumerate(planned):
        qtype = int(a.get("type", -1))
        title = a.get("title") or a.get("entry", f"Q{idx+1}")
        q_idx = DOM_OFFSET + idx
        if qtype in (QT.SHORT_TEXT, QT.LONG_TEXT):
            val = a.get("value", "r"); vtype = a.get("validation", {}).get("type")
            if vtype == ff.VType.EMAIL:
                actions.append({"type": "email", "q_idx": q_idx, "title": title,
                                 "value": "email_r" if val == "r" else val})
            else:
                actions.append({"type": "text", "q_idx": q_idx, "title": title, "value": val})
        elif qtype in (QT.RADIO, QT.DROPDOWN, QT.LINEAR, QT.STAR):
            all_opts = a.get("all_opts", a.get("options", []))
            atype    = "dropdown" if qtype == QT.DROPDOWN else "click"
            actions.append({"type": atype, "q_idx": q_idx, "title": title,
                             "options": all_opts, "labels": all_opts,
                             "choice": a.get("choice","r"), "is_multi": False,
                             "other_texts": {},
                             "other_indices": {len(a.get("options",[]))} if a.get("has_other") else set()})
        elif qtype == QT.CHECKBOX:
            all_opts = a.get("all_opts", a.get("options", []))
            actions.append({"type": "click", "q_idx": q_idx, "title": title,
                             "options": all_opts, "labels": all_opts,
                             "choice": a.get("choice","r"), "is_multi": True,
                             "other_texts": a.get("other_texts", {}),
                             "other_indices": {len(a.get("options",[]))} if a.get("has_other") else set()})
        elif qtype in (QT.GRID, QT.CHECKBOX_GRID):
            opts = a.get("options", []); gc = a.get("grid_choices", {})
            is_cb = (qtype == QT.CHECKBOX_GRID)
            for row in a.get("grid_rows", []):
                actions.append({"type": "click", "q_idx": a.get("page_index", idx),
                                 "title": f"{title} / {row['label']}",
                                 "options": opts, "labels": opts,
                                 "choice": gc.get(row["entry"], "r"), "is_multi": is_cb,
                                 "other_texts": {}, "other_indices": set()})
    return actions


# ===========================================================================
# MAIN APPLICATION
# [CTK] Root is now CTk(); notebook is CTkTabview.
# ===========================================================================

class FormFillerApp:

    def __init__(self, root):
        self.root = root
        root.title("Form Filler")
        root.configure(fg_color=BG())
        root.geometry("900x740")
        root.minsize(720, 540)
        try: root.attributes("-alpha", max(0.1, min(1.0, T["opacity"])))
        except Exception: pass

        # App state
        self.form_action  = None
        self.pages        = None
        self.cookies      = {}
        self.is_multipage = False
        self.seed_fbzx    = None
        self.q_widgets    = []
        self._stop_flag   = threading.Event()
        self._run_thread  = None
        # [NEW] session history: list of result dicts for the History tab
        self._session_history = []
        # [NEW] shutdown overlay widget (created lazily)
        self._shutdown_overlay = None
        # [NEW] Analytics: per-question answer count dicts; keyed by question title.
        # Structure: { q_title: {"__type__": qtype, "__opts__": [...], opt_label: count, ...} }
        # __tracking_enabled__: bool controlled by UI toggle (defaults True)
        self._analytics_data    = {}
        self._analytics_lock    = threading.Lock()
        self._analytics_enabled = True    # tracking on/off toggle

        self._backend_var   = tk.StringVar(value="http")
        self._perf_var      = tk.StringVar(value="normal")
        self._instances_var = tk.IntVar(value=1)

        self._build_ui()

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self):
        # --- Header bar ---
        hdr = ctk.CTkFrame(self.root, fg_color=BG2(), corner_radius=0,
                           height=T["titlebar_height"])
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        _reg(hdr, "frame2")

        self._title_label = ctk.CTkLabel(
            hdr, text=" " + T["title_text"],
            text_color=ACCENT2(), fg_color="transparent",
            font=ctk.CTkFont(T["font_family"], T["title_font_size"], weight="bold"))
        self._title_label.pack(side="left", padx=16, pady=10)
        _reg(self._title_label, "label_accent")

        badge = ctk.CTkLabel(hdr, text="v2", text_color=FG2(), fg_color="transparent",
                             font=ctk.CTkFont(T["font_family"], 9))
        badge.pack(side="right", padx=14)
        _reg(badge, "label2")

        # [4CHAN] When the 4chan theme is active, show an "Anonymous" tag
        # in the header bar to match the board aesthetic.
        self._anon_badge = ctk.CTkLabel(
            hdr, text="  Anonymous  ", fg_color=BG3(),
            text_color=FG(), corner_radius=0,
            font=ctk.CTkFont(T["font_family"], 9, weight="bold"))
        _reg(self._anon_badge, "frame3")
        if T.get("title_text", "").startswith("Form Filler  ["):
            self._anon_badge.pack(side="right", padx=(0, 8), pady=10)

        # --- CTkTabview as the notebook ---
        # [CTK] CTkTabview has built-in rounded tabs; no ttk.Notebook needed
        self.nb = ctk.CTkTabview(self.root, fg_color=BG(),
                                 segmented_button_fg_color=BG2(),
                                 segmented_button_selected_color=BG3(),
                                 segmented_button_selected_hover_color=BG3(),
                                 segmented_button_unselected_color=BG2(),
                                 text_color=FG2(), corner_radius=8)
        self.nb.pack(fill="both", expand=True, padx=0, pady=0)

        for tab_name in ("Setup", "Questions", "Run", "Debug", "History", "Analytics", "Customise", "Help"):
            self.nb.add(tab_name)

        self._tab_setup     = self.nb.tab("Setup")
        self._tab_questions = self.nb.tab("Questions")
        self._tab_run       = self.nb.tab("Run")
        self._tab_debug     = self.nb.tab("Debug")
        self._tab_history   = self.nb.tab("History")
        self._tab_analytics = self.nb.tab("Analytics")
        self._tab_theme     = self.nb.tab("Customise")
        self._tab_help      = self.nb.tab("Help")

        self._build_setup_tab()
        self._build_questions_tab()
        self._build_run_tab()
        self._build_debug_tab()
        self._build_history_tab()
        self._build_analytics_tab()
        self._build_theme_tab()
        self._build_help_tab()

        _apply_theme(self.root, self.nb, self._title_label)

    # -----------------------------------------------------------------------
    # Setup tab
    # -----------------------------------------------------------------------

    def _build_setup_tab(self):
        p = self._tab_setup
        p.columnconfigure(1, weight=1)

        def row_lbl(r, text):
            l = ctk.CTkLabel(p, text=text, text_color=FG(), fg_color="transparent",
                             font=_font(bold=True), anchor="w")
            l.grid(row=r, column=0, sticky="w", padx=(16,8), pady=8)
            _reg(l, "label_bold"); return l

        # URL
        row_lbl(0, "Form URL")
        self._url_var = tk.StringVar()
        ue = _entry(p, width=400)
        ue.configure(textvariable=self._url_var)
        ue.grid(row=0, column=1, sticky="ew", padx=(0,16), pady=(18,4))

        # [FIX issue-6] Saved Links row -- dropdown of named URL presets that persist
        # across sessions in saved_links.json.
        row_lbl(1, "Saved Links")
        self._saved_links = _load_saved_links()   # {name: url}
        self._saved_link_var = tk.StringVar(value="")

        lf = ctk.CTkFrame(p, fg_color="transparent"); lf.grid(row=1, column=1, sticky="w", pady=2)
        _reg(lf, "frame")

        self._saved_link_combo = ctk.CTkComboBox(
            lf, variable=self._saved_link_var,
            values=list(self._saved_links.keys()) or ["(no saved links)"],
            width=240, fg_color=BG3(), text_color=FG(),
            button_color=ACCENT(), dropdown_fg_color=BG2(),
            dropdown_text_color=FG(), font=_font(), state="readonly")
        self._saved_link_combo.pack(side="left", padx=(0, 6))
        _reg(self._saved_link_combo, "entry")

        def _load_link():
            name = self._saved_link_var.get()
            if name and name in self._saved_links:
                self._url_var.set(self._saved_links[name])

        def _save_link():
            url = self._url_var.get().strip()
            if not url:
                messagebox.showwarning("No URL", "Enter a URL first."); return
            # Ask for a name via a simple dialog
            dialog = ctk.CTkInputDialog(text="Enter a name for this link:", title="Save Link")
            name = dialog.get_input()
            if not name or not name.strip(): return
            name = name.strip()
            self._saved_links[name] = url
            _save_saved_links(self._saved_links)
            self._saved_link_combo.configure(values=list(self._saved_links.keys()))
            self._saved_link_var.set(name)
            messagebox.showinfo("Saved", f"Link saved as: {name}")

        def _delete_link():
            name = self._saved_link_var.get()
            if not name or name not in self._saved_links:
                messagebox.showwarning("Nothing selected", "Select a saved link to delete."); return
            if messagebox.askyesno("Delete", f"Delete saved link '{name}'?"):
                del self._saved_links[name]
                _save_saved_links(self._saved_links)
                vals = list(self._saved_links.keys()) or ["(no saved links)"]
                self._saved_link_combo.configure(values=vals)
                self._saved_link_var.set(vals[0])

        _button(lf, "Load", _load_link, width=60).pack(side="left", padx=2)
        _button(lf, "Save", _save_link, width=60).pack(side="left", padx=2)
        _button(lf, "Delete", _delete_link, role="btn_danger", width=60).pack(side="left", padx=2)

        # Backend
        row_lbl(2, "Backend")
        bf = ctk.CTkFrame(p, fg_color="transparent"); bf.grid(row=2, column=1, sticky="w")
        _reg(bf, "frame")
        for val, lbl in [("http", "HTTP  (fast, more CAPTCHAs)"),
                         ("chromium", "Chromium  (slower, fewer CAPTCHAs)")]:
            _radio(bf, lbl, self._backend_var, val,
                   command=self._on_backend_change).pack(side="left", padx=6)

        # Chromium options
        self._chrom_frame = ctk.CTkFrame(p, fg_color="transparent")
        self._chrom_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=0)
        self._chrom_frame.columnconfigure(1, weight=1)
        _reg(self._chrom_frame, "frame")

        pl = ctk.CTkLabel(self._chrom_frame, text="Perf Mode", text_color=FG(),
                          fg_color="transparent", font=_font(bold=True), anchor="w")
        pl.grid(row=0, column=0, sticky="w", padx=(0,8), pady=6); _reg(pl, "label_bold")
        pf = ctk.CTkFrame(self._chrom_frame, fg_color="transparent"); pf.grid(row=0, column=1, sticky="w")
        _reg(pf, "frame")
        for val, lbl in [("normal",   "Normal (visible, easiest to debug)"),
                         ("headless", "Headless (invisible, faster)"),
                         ("turbo",    "Turbo (headless + optimised, fastest)")]:
            _radio(pf, lbl, self._perf_var, val).pack(anchor="w", pady=1)

        il = ctk.CTkLabel(self._chrom_frame, text="Instances", text_color=FG(),
                          fg_color="transparent", font=_font(bold=True), anchor="w")
        il.grid(row=1, column=0, sticky="w", padx=(0,8), pady=6); _reg(il, "label_bold")
        if_ = ctk.CTkFrame(self._chrom_frame, fg_color="transparent"); if_.grid(row=1, column=1, sticky="w")
        _reg(if_, "frame")
        _spinbox(if_, 1, 50, self._instances_var).pack(side="left")
        ctk.CTkLabel(if_, text="  browser window(s)", text_color=FG2(), fg_color="transparent",
                     font=_font()).pack(side="left")

        self._chrom_frame.grid_remove()

        # Mode
        row_lbl(4, "Mode")
        self._mode_var = tk.StringVar(value="random")
        mf = ctk.CTkFrame(p, fg_color="transparent"); mf.grid(row=4, column=1, sticky="w")
        _reg(mf, "frame")
        for val, lbl in [("normal","Normal (pick once)"),("lazy","Lazy (required only)"),
                         ("random","Random"),("specific","Specific (repeat N times)")]:
            _radio(mf, lbl, self._mode_var, val).pack(side="left", padx=4)

        # Submissions
        row_lbl(5, "Submissions")
        tf = ctk.CTkFrame(p, fg_color="transparent"); tf.grid(row=5, column=1, sticky="w")
        _reg(tf, "frame")
        self._times_var = tk.StringVar(value="1")
        te = _entry(tf, width=80); te.configure(textvariable=self._times_var); te.pack(side="left")
        ctk.CTkLabel(tf, text="  (use 'inf' for unlimited)", text_color=FG2(),
                     fg_color="transparent", font=_font()).pack(side="left")

        # Workers
        self._workers_label = ctk.CTkLabel(p, text="Workers", text_color=FG(),
                                           fg_color="transparent", font=_font(bold=True), anchor="w")
        self._workers_label.grid(row=6, column=0, sticky="w", padx=(16,8), pady=8)
        _reg(self._workers_label, "label_bold")
        wf = ctk.CTkFrame(p, fg_color="transparent"); wf.grid(row=6, column=1, sticky="w")
        _reg(wf, "frame")
        self._workers_var = tk.IntVar(value=1)
        _spinbox(wf, 1, 200, self._workers_var, width=6).pack(side="left")
        self._workers_suffix = ctk.CTkLabel(wf, text="  concurrent HTTP workers",
                                            text_color=FG2(), fg_color="transparent", font=_font())
        self._workers_suffix.pack(side="left"); _reg(self._workers_suffix, "label2")

        # Delay
        row_lbl(7, "Delay (sec)")
        df = ctk.CTkFrame(p, fg_color="transparent"); df.grid(row=7, column=1, sticky="w")
        _reg(df, "frame")
        self._delay_lo = tk.StringVar(value="0")
        self._delay_hi = tk.StringVar(value="0")
        elo = _entry(df, width=70); elo.configure(textvariable=self._delay_lo); elo.pack(side="left")
        ctk.CTkLabel(df, text="  to  ", text_color=FG2(), fg_color="transparent",
                     font=_font()).pack(side="left")
        ehi = _entry(df, width=70); ehi.configure(textvariable=self._delay_hi); ehi.pack(side="left")
        ctk.CTkLabel(df, text="  seconds (0 = no delay)", text_color=FG2(),
                     fg_color="transparent", font=_font()).pack(side="left")

        # Scan button + config buttons
        sr = ctk.CTkFrame(p, fg_color="transparent"); sr.grid(row=8, column=0, columnspan=2,
                                                                pady=(18,8), padx=16, sticky="w")
        _reg(sr, "frame")
        _button(sr, "  Scan Form  ", self._scan).pack(side="left")
        # [NEW] Config save/load buttons -- form_filler.py has save_config/load_config
        # but they were never wired to the UI.
        _button(sr, "  Save Config  ", self._save_config).pack(side="left", padx=(8,0))
        _button(sr, "  Load Config  ", self._load_config).pack(side="left", padx=(4,0))
        self._scan_status = ctk.CTkLabel(sr, text="", text_color=FG2(), fg_color="transparent",
                                         font=_font())
        self._scan_status.pack(side="left", padx=12); _reg(self._scan_status, "label2")

    def _on_backend_change(self):
        if self._backend_var.get() == "chromium":
            self._chrom_frame.grid()
            self._workers_label.configure(text="HTTP Workers")
            self._workers_suffix.configure(text="  HTTP workers (unused for Chromium)")
        else:
            self._chrom_frame.grid_remove()
            self._workers_label.configure(text="Workers")
            self._workers_suffix.configure(text="  concurrent HTTP workers")

    # -----------------------------------------------------------------------
    # Questions tab
    # -----------------------------------------------------------------------

    def _build_questions_tab(self):
        pl = ctk.CTkLabel(self._tab_questions,
                          text="Scan a form first to see questions here.",
                          text_color=FG2(), fg_color="transparent", font=_font())
        pl.pack(pady=30); _reg(pl, "label2")

    def _populate_questions(self, questions):
        for w in self._tab_questions.winfo_children(): w.destroy()
        sf = _scrollframe(self._tab_questions)
        sf.pack(fill="both", expand=True)
        self.q_widgets = []
        for i, q in enumerate(questions):
            self.q_widgets.append(QuestionWidget(sf, q, i))
        bf = ctk.CTkFrame(self._tab_questions, fg_color="transparent"); bf.pack(fill="x", pady=8)
        _reg(bf, "frame")
        _button(bf, "  Done -- go to Run tab  ",
                lambda: self.nb.set("Run")).pack(pady=4)

    # -----------------------------------------------------------------------
    # Run tab
    # -----------------------------------------------------------------------

    def _build_run_tab(self):
        p = self._tab_run

        # Stat boxes
        stats = ctk.CTkFrame(p, fg_color="transparent"); stats.pack(fill="x", padx=16, pady=(16,6))
        _reg(stats, "frame")
        stats.columnconfigure((0,1,2,3,4), weight=1)

        def stat_box(col, label):
            f = ctk.CTkFrame(stats, fg_color=BG2(), corner_radius=10)
            f.grid(row=0, column=col, padx=6, sticky="ew"); _reg(f, "frame2")
            ctk.CTkLabel(f, text=label, text_color=FG2(), fg_color="transparent",
                         font=ctk.CTkFont(T["font_family"], 9, weight="bold")
                         ).pack(pady=(10,0))
            v = tk.StringVar(value="--")
            ctk.CTkLabel(f, textvariable=v, text_color=FG(), fg_color="transparent",
                         font=ctk.CTkFont(T["font_family"], 22, weight="bold")
                         ).pack(pady=(2,10))
            return v

        self._stat_submitted = stat_box(0, "SUBMITTED")
        self._stat_success   = stat_box(1, "SUCCESS")
        self._stat_failed    = stat_box(2, "FAILED")
        self._stat_rate      = stat_box(3, "PER MIN")
        # [NEW] Retry counter -- shows when Google is pushing back with heavy-traffic errors
        self._stat_retries   = stat_box(4, "RETRIES↺")

        # [4CHAN] Show a "No.XXXXXXX" style post counter below the stat boxes
        # when the 4chan theme is active -- mimics post numbers on the board.
        self._postcounter_label = ctk.CTkLabel(
            p, text="No.0000000", text_color=FG2(), fg_color="transparent",
            font=ctk.CTkFont(T["font_family"], 9))
        self._postcounter_label.pack(anchor="e", padx=20)
        _reg(self._postcounter_label, "label2")

        # Progress bar  [CTK] CTkProgressBar replaces ttk.Progressbar
        self._progress_var = tk.DoubleVar(value=0)
        self._progress = ctk.CTkProgressBar(p, variable=self._progress_var,
                                             fg_color=BG3(), progress_color=ACCENT(),
                                             corner_radius=6, height=14)
        self._progress.set(0)
        self._progress.pack(fill="x", padx=16, pady=6)
        _reg(self._progress, "progress")
        self._progress_label = ctk.CTkLabel(p, text="Ready.", text_color=FG2(),
                                             fg_color="transparent", font=_font())
        self._progress_label.pack(); _reg(self._progress_label, "label2")

        br = ctk.CTkFrame(p, fg_color="transparent"); br.pack(pady=10)
        _reg(br, "frame")
        self._start_btn = _button(br, "  Start Submitting  ", self._start_run)
        self._start_btn.pack(side="left", padx=8)
        self._stop_btn  = _button(br, "  Stop  ", self._stop_run, role="btn_danger")
        self._stop_btn.pack(side="left", padx=8)
        self._stop_btn.configure(state="disabled")

        log_hdr = ctk.CTkFrame(p, fg_color="transparent"); log_hdr.pack(fill="x", padx=16, pady=(8,2))
        _reg(log_hdr, "frame")
        ctk.CTkLabel(log_hdr, text="Log (this session):", text_color=FG2(), fg_color="transparent",
                     font=_font()).pack(side="left")
        # [NEW] Save log button -- exports the run log textbox to a .txt file
        _button(log_hdr, "  Save Log  ", self._save_run_log).pack(side="right")
        # [CTK] CTkTextbox replaces ScrolledText; built-in scrollbar, no line cap
        self._log_box = ctk.CTkTextbox(p, height=180, fg_color=BG2(), text_color=FG2(),
                                        border_color=BG3(), corner_radius=CR(),
                                        font=ctk.CTkFont(T["mono_family"], T["mono_size"]),
                                        state="disabled")
        self._log_box.pack(fill="both", expand=True, padx=16, pady=(0,14))
        _reg(self._log_box, "textbox")

    def _log(self, msg):
        # [FIX] No line cap -- full session history kept.
        # [COLOUR] Uses tk.Text tag_config on the underlying CTkTextbox widget
        #          to colour individual lines:
        #            success  -> SUCCESS() colour  (green, or #789922 on 4chan)
        #            fail/err -> FAIL() colour     (red on all themes)
        #            default  -> FG2() colour      (dim text)
        # [4CHAN] Success lines are also prefixed with > (greentext)
        def _do():
            is_4chan = T.get("title_text", "").startswith("Form Filler  [")
            low = msg.lower()

            is_success = any(k in low for k in ("ok","success","done","complete","submitted","✓"))
            is_fail    = any(k in low for k in ("error","fail","exception","traceback",
                                                 "warning","warn","timeout","refused","✗"))

            # Prefix for 4chan greentext / redtext
            if is_4chan and is_success:
                display = ">" + msg
            elif is_4chan and is_fail:
                display = msg   # red colour handles it visually
            else:
                display = msg

            # Determine tag name and colour
            if is_success:
                tag, colour = "log_success", SUCCESS()
            elif is_fail:
                tag, colour = "log_fail",    FAIL()
            else:
                tag, colour = "log_default", FG2()

            box = self._log_box
            box.configure(state="normal")

            # Access underlying tk.Text for tag support
            # [CTK] CTkTextbox exposes its inner tk.Text as ._textbox
            inner = box._textbox
            inner.tag_config("log_success", foreground=SUCCESS())
            inner.tag_config("log_fail",    foreground=FAIL())
            inner.tag_config("log_default", foreground=FG2())

            start = inner.index("end-1c")
            inner.insert("end", display + "\n")
            end   = inner.index("end-1c")
            inner.tag_add(tag, start, end)

            box.see("end")
            box.configure(state="disabled")

            # Update "No." post counter (4chan theme)
            try:
                total = int(self._stat_submitted.get() or "0")
                base  = 536053352
                self._postcounter_label.configure(text=f"No.{base + total}")
            except Exception:
                pass

            # Route errors to Debug tab
            if is_fail:
                self._debug_log(msg)

        self.root.after(0, _do)

    # -----------------------------------------------------------------------
    # Analytics tab  [NEW]
    # Per-question answer distribution charts using tk.Canvas (no matplotlib).
    # Supports pie charts (choice questions) and bar charts (text questions).
    # Live hover tooltips show exact counts and percentages.
    # -----------------------------------------------------------------------

    def _build_analytics_tab(self):
        p = self._tab_analytics

        # --- top bar: title + toggle + clear + export CSV ---
        top = ctk.CTkFrame(p, fg_color="transparent"); top.pack(fill="x", padx=16, pady=(12,4))
        _reg(top, "frame")
        _label(top, "Answer Analytics", role="label_bold").pack(side="left")
        _label(top, "  — live charts of submitted answer distributions", role="label2").pack(side="left")

        # [ANALYTICS] enable/disable toggle -- when off, tracking is skipped to save CPU
        # on high-volume runs.  State stored in self._analytics_enabled.
        self._analytics_toggle_var = tk.BooleanVar(value=True)
        def _toggle_tracking():
            self._analytics_enabled = self._analytics_toggle_var.get()
        toggle_chk = _check(top, "Enable tracking", self._analytics_toggle_var,
                            command=_toggle_tracking)
        toggle_chk.pack(side="right", padx=(8,0))

        def _clear_analytics():
            with self._analytics_lock:
                self._analytics_data.clear()
            self._analytics_refresh()
        def _export_analytics_csv():
            self._analytics_export_csv()

        _button(top, "  Export CSV  ", _export_analytics_csv).pack(side="right", padx=(0,4))
        _button(top, "  Clear  ", _clear_analytics).pack(side="right", padx=(0,4))

        # [ANALYTICS] placeholder label shown before any data arrives
        self._analytics_placeholder = _label(p, "Run a submission to see answer distributions here.",
                                              role="label2")
        self._analytics_placeholder.pack(pady=40)

        # Scrollable container for chart cards
        self._analytics_scroll = _scrollframe(p)
        # NOT packed yet -- shown on first data

        # Tooltip overlay: a floating label that follows the mouse
        # Built lazily in _analytics_show_tooltip so we can reference self.root
        self._analytics_tooltip = None

    def _on_answers_resolved(self, resolved: list):
        """[ANALYTICS] Called from form_filler (background thread) after each successful
        _resolve_planned().  Thread-safe: acquires self._analytics_lock, updates counts,
        then schedules a UI refresh on the main thread."""
        if not self._analytics_enabled:
            return
        QT = ff.QType
        with self._analytics_lock:
            for a in resolved:
                qtype = int(a.get("type", -1))
                title = a.get("title") or a.get("entry", "?")

                # Initialise bucket for this question if first time seen
                if title not in self._analytics_data:
                    self._analytics_data[title] = {"__type__": qtype, "__opts__": []}

                bucket = self._analytics_data[title]

                if qtype in (QT.RADIO, QT.DROPDOWN, QT.LINEAR, QT.STAR):
                    all_opts = a.get("all_opts", a.get("options", []))
                    choice   = a.get("choice")
                    if isinstance(choice, int) and all_opts and 0 <= choice < len(all_opts):
                        label = all_opts[choice]
                        bucket["__opts__"] = all_opts   # keep opts list updated
                        bucket[label] = bucket.get(label, 0) + 1

                elif qtype == QT.CHECKBOX:
                    all_opts = a.get("all_opts", a.get("options", []))
                    choices  = a.get("choice", [])
                    if not isinstance(choices, list): choices = [choices]
                    bucket["__opts__"] = all_opts
                    for idx in choices:
                        if isinstance(idx, int) and 0 <= idx < len(all_opts):
                            label = all_opts[idx]
                            bucket[label] = bucket.get(label, 0) + 1

                elif qtype in (QT.SHORT_TEXT, QT.LONG_TEXT):
                    val = str(a.get("value", ""))[:32]   # truncate long strings for display
                    bucket[val] = bucket.get(val, 0) + 1
                    # Cap text distribution at 30 unique values to avoid unbounded growth
                    non_meta = {k: v for k, v in bucket.items() if not k.startswith("__")}
                    if len(non_meta) > 30:
                        # Remove the least frequent entry
                        min_key = min(non_meta, key=non_meta.get)
                        del bucket[min_key]

        # Schedule chart redraw on the main thread (throttled: one per 250ms max)
        self.root.after(0, self._analytics_refresh)

    def _analytics_refresh(self):
        """[ANALYTICS] Rebuild chart cards from self._analytics_data.
        Must be called on the main thread (scheduled via root.after)."""
        with self._analytics_lock:
            snapshot = {k: dict(v) for k, v in self._analytics_data.items()}

        if not snapshot:
            self._analytics_placeholder.pack(pady=40)
            self._analytics_scroll.pack_forget()
            return

        # Show scroll frame, hide placeholder
        self._analytics_placeholder.pack_forget()
        self._analytics_scroll.pack(fill="both", expand=True, padx=16, pady=(0,12))

        # Destroy old chart cards and rebuild fresh
        for w in self._analytics_scroll.winfo_children():
            w.destroy()

        QT = ff.QType
        for q_title, bucket in snapshot.items():
            qtype    = bucket.get("__type__", -1)
            all_opts = bucket.get("__opts__", [])
            counts   = {k: v for k, v in bucket.items() if not k.startswith("__")}
            if not counts:
                continue

            self._analytics_draw_card(self._analytics_scroll, q_title, qtype, all_opts, counts)

    def _analytics_draw_card(self, parent, title, qtype, all_opts, counts):
        """[ANALYTICS] Draw a single chart card for one question."""
        QT      = ff.QType
        total   = sum(counts.values())
        PALETTE = ["#8b7cf8","#57e389","#f4786a","#58a6ff","#ffab40",
                   "#00ffcc","#ff6d00","#ff00ff","#79c0ff","#81c784",
                   "#ef9a9a","#facc15","#b3a9fa","#39ff14","#ff33cc"]

        card = ctk.CTkFrame(parent, fg_color=BG2(), corner_radius=10)
        card.pack(fill="x", padx=4, pady=6)
        _reg(card, "frame2")

        # Card header: question title + total count
        hdr = ctk.CTkFrame(card, fg_color="transparent"); hdr.pack(fill="x", padx=14, pady=(10,4))
        _reg(hdr, "frame")
        ctk.CTkLabel(hdr, text=title[:70], text_color=ACCENT2(), fg_color="transparent",
                     font=_font(bold=True), anchor="w").pack(side="left")
        ctk.CTkLabel(hdr, text=f"  n={total}", text_color=FG2(), fg_color="transparent",
                     font=_font()).pack(side="left")

        is_text = qtype in (QT.SHORT_TEXT, QT.LONG_TEXT)

        if is_text or len(counts) > 8:
            # Bar chart for text questions and wide distributions
            self._analytics_bar_chart(card, counts, total, PALETTE)
        else:
            # Pie chart for choice questions with <=8 options
            row = ctk.CTkFrame(card, fg_color="transparent"); row.pack(fill="x", padx=14, pady=(0,10))
            _reg(row, "frame")
            self._analytics_pie_chart(row, counts, total, PALETTE)
            self._analytics_legend(row, counts, total, PALETTE)

    def _analytics_pie_chart(self, parent, counts, total, palette):
        """[ANALYTICS] Draw a pie chart on a tk.Canvas with hover tooltips."""
        SIZE    = 180
        CX, CY  = SIZE // 2, SIZE // 2
        R       = SIZE // 2 - 12
        labels  = list(counts.keys())
        values  = [counts[l] for l in labels]

        canvas = tk.Canvas(parent, width=SIZE, height=SIZE,
                           bg=BG2(), highlightthickness=0)
        canvas.pack(side="left", padx=(0, 12))

        # Draw each slice
        start   = 0.0
        slices  = []   # [(label, value, arc_start, arc_extent, color)]
        for i, (lbl, val) in enumerate(zip(labels, values)):
            extent = (val / total) * 360.0 if total else 0
            color  = palette[i % len(palette)]
            # arc drawn from -90 (top) going clockwise
            arc_start = start - 90
            arc_id = canvas.create_arc(
                CX - R, CY - R, CX + R, CY + R,
                start=arc_start, extent=extent,
                fill=color, outline=BG2(), width=2
            )
            slices.append((lbl, val, arc_start, extent, color, arc_id))
            start += extent

        # Hover: detect which slice the mouse is over by angle + radius
        def _on_move(event, slices=slices, cx=CX, cy=CY, r=R):
            dx, dy = event.x - cx, event.y - cy
            dist   = (dx*dx + dy*dy) ** 0.5
            if dist > r:
                _hide_tooltip(); return
            import math
            angle = math.degrees(math.atan2(dy, dx)) + 90
            if angle < 0: angle += 360
            for lbl, val, arc_s, arc_e, color, arc_id in slices:
                norm_s = (arc_s + 90) % 360
                norm_e = (norm_s + arc_e) % 360
                in_slice = (norm_s <= angle < norm_e) if norm_s < norm_e \
                           else (angle >= norm_s or angle < norm_e)
                if in_slice:
                    pct = val / total * 100 if total else 0
                    _show_tooltip(event, f"{lbl}\n{val} ({pct:.1f}%)")
                    return
            _hide_tooltip()

        canvas.bind("<Motion>",  _on_move)
        canvas.bind("<Leave>",   lambda e: _hide_tooltip())

        def _show_tooltip(event, text):
            tt = self._get_tooltip()
            rx  = canvas.winfo_rootx() + event.x + 14
            ry  = canvas.winfo_rooty() + event.y - 10
            tt.configure(text=text)
            tt.place(x=rx - self.root.winfo_rootx(),
                     y=ry - self.root.winfo_rooty())
            tt.lift()

        def _hide_tooltip():
            tt = self._get_tooltip()
            tt.place_forget()

    def _analytics_legend(self, parent, counts, total, palette):
        """[ANALYTICS] Legend rows alongside a pie chart."""
        lf = ctk.CTkFrame(parent, fg_color="transparent"); lf.pack(side="left", anchor="n", pady=4)
        _reg(lf, "frame")
        for i, (lbl, val) in enumerate(counts.items()):
            color = palette[i % len(palette)]
            pct   = val / total * 100 if total else 0
            row   = ctk.CTkFrame(lf, fg_color="transparent"); row.pack(anchor="w", pady=1)
            _reg(row, "frame")
            # Colour swatch
            swatch = tk.Canvas(row, width=12, height=12, bg=color,
                               highlightthickness=0)
            swatch.pack(side="left", padx=(0, 5))
            ctk.CTkLabel(row, text=f"{lbl[:24]}  {val} ({pct:.1f}%)",
                         text_color=FG2(), fg_color="transparent",
                         font=ctk.CTkFont(T["font_family"], T["font_size"]-1),
                         anchor="w").pack(side="left")

    def _analytics_bar_chart(self, parent, counts, total, palette):
        """[ANALYTICS] Horizontal bar chart for text fields and wide distributions."""
        W      = 560
        BAR_H  = 22
        GAP    = 6
        LBLW   = 160
        BARW   = W - LBLW - 60   # remaining for the bar + count text
        items  = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:20]
        max_v  = max(v for _, v in items) if items else 1
        H      = len(items) * (BAR_H + GAP) + 20

        canvas = tk.Canvas(parent, width=W, height=H,
                           bg=BG2(), highlightthickness=0)
        canvas.pack(padx=14, pady=(4, 10), anchor="w")

        bar_regions = []   # [(x1,y1,x2,y2, label, val)]
        for i, (lbl, val) in enumerate(items):
            color  = palette[i % len(palette)]
            y_top  = 10 + i * (BAR_H + GAP)
            y_bot  = y_top + BAR_H
            bar_w  = int((val / max_v) * BARW) if max_v else 0

            # Label (truncated)
            canvas.create_text(LBLW - 6, y_top + BAR_H // 2,
                                text=lbl[:22], anchor="e",
                                fill=FG2(), font=(T["font_family"], T["font_size"]-1))
            # Bar
            bar_id = canvas.create_rectangle(LBLW, y_top, LBLW + bar_w, y_bot,
                                              fill=color, outline="")
            # Count + pct text
            pct = val / total * 100 if total else 0
            canvas.create_text(LBLW + bar_w + 6, y_top + BAR_H // 2,
                                text=f"{val} ({pct:.1f}%)", anchor="w",
                                fill=FG2(), font=(T["font_family"], T["font_size"]-1))

            bar_regions.append((LBLW, y_top, LBLW + bar_w, y_bot, lbl, val))

        def _on_move(event, regions=bar_regions):
            for x1, y1, x2, y2, lbl, val in regions:
                if x1 <= event.x <= max(x2, x1+4) and y1 <= event.y <= y2:
                    pct = val / total * 100 if total else 0
                    _show_tooltip(event, f"{lbl}\n{val} ({pct:.1f}%)")
                    return
            _hide_tooltip()

        canvas.bind("<Motion>", _on_move)
        canvas.bind("<Leave>",  lambda e: _hide_tooltip())

        def _show_tooltip(event, text):
            tt = self._get_tooltip()
            rx = canvas.winfo_rootx() + event.x + 14
            ry = canvas.winfo_rooty() + event.y - 10
            tt.configure(text=text)
            tt.place(x=rx - self.root.winfo_rootx(),
                     y=ry - self.root.winfo_rooty())
            tt.lift()

        def _hide_tooltip():
            self._get_tooltip().place_forget()

    def _get_tooltip(self):
        """[ANALYTICS] Lazily create the floating tooltip label."""
        if self._analytics_tooltip is None or not self._analytics_tooltip.winfo_exists():
            self._analytics_tooltip = ctk.CTkLabel(
                self.root, text="", fg_color=BG3(), text_color=FG(),
                corner_radius=6, font=_font(), justify="left",
                padx=8, pady=6)
        return self._analytics_tooltip

    def _analytics_export_csv(self):
        """[ANALYTICS] Export per-question answer distribution data to a CSV file."""
        with self._analytics_lock:
            snapshot = {k: dict(v) for k, v in self._analytics_data.items()}
        if not snapshot:
            messagebox.showinfo("Empty", "No analytics data to export."); return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
            title="Export Analytics CSV")
        if not path: return
        try:
            rows = []
            for q_title, bucket in snapshot.items():
                counts = {k: v for k, v in bucket.items() if not k.startswith("__")}
                total  = sum(counts.values())
                for label, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
                    pct = count / total * 100 if total else 0
                    rows.append({
                        "question":   q_title,
                        "answer":     label,
                        "count":      count,
                        "total":      total,
                        "percent":    f"{pct:.2f}",
                    })
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["question","answer","count","total","percent"])
                w.writeheader(); w.writerows(rows)
            messagebox.showinfo("Exported", f"Analytics exported to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    # -----------------------------------------------------------------------
    # History tab  [NEW]
    # -----------------------------------------------------------------------

    def _build_history_tab(self):
        p = self._tab_history

        hdr = ctk.CTkFrame(p, fg_color="transparent"); hdr.pack(fill="x", padx=16, pady=(12,4))
        _reg(hdr, "frame")
        _label(hdr, "Session History", role="label_bold").pack(side="left")
        _label(hdr, "  — every run this session, plus export", role="label2").pack(side="left")

        br = ctk.CTkFrame(p, fg_color="transparent"); br.pack(fill="x", padx=16, pady=(0,6))
        _reg(br, "frame")

        def _clear_hist():
            if messagebox.askyesno("Clear history", "Clear session history?"):
                self._session_history.clear()
                self._refresh_history_tab()

        def _export_csv():
            if not self._session_history:
                messagebox.showinfo("Empty", "No sessions to export."); return
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
                title="Export session history")
            if not path: return
            try:
                keys = list(self._session_history[0].keys())
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=keys)
                    w.writeheader(); w.writerows(self._session_history)
                messagebox.showinfo("Exported", f"History exported to:\n{path}")
            except Exception as e:
                messagebox.showerror("Export failed", str(e))

        def _export_json():
            if not self._session_history:
                messagebox.showinfo("Empty", "No sessions to export."); return
            path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("All files", "*.*")],
                title="Export session history")
            if not path: return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self._session_history, f, indent=2)
                messagebox.showinfo("Exported", f"History exported to:\n{path}")
            except Exception as e:
                messagebox.showerror("Export failed", str(e))

        _button(br, "  Clear  ", _clear_hist).pack(side="left", padx=(0,6))
        _button(br, "  Export CSV  ", _export_csv).pack(side="left", padx=(0,6))
        _button(br, "  Export JSON  ", _export_json).pack(side="left")

        # Scrollable list -- rebuilt by _refresh_history_tab
        self._history_scroll = _scrollframe(p)
        self._history_scroll.pack(fill="both", expand=True, padx=16, pady=(0,12))
        self._history_header_frame = ctk.CTkFrame(p, fg_color="transparent")  # placeholder

        # Column headers row
        cols = ["Time", "URL", "Backend", "Mode", "Total", "OK", "Failed", "Peak/min", "Retries"]
        hf = ctk.CTkFrame(self._history_scroll, fg_color=BG3(), corner_radius=6)
        hf.pack(fill="x", pady=(4, 2), padx=4); _reg(hf, "frame3")
        widths = [140, 260, 80, 80, 60, 60, 60, 80, 60]
        for col_txt, w in zip(cols, widths):
            ctk.CTkLabel(hf, text=col_txt, width=w, text_color=ACCENT2(),
                         fg_color="transparent", font=_font(bold=True),
                         anchor="w").pack(side="left", padx=4)

        self._history_rows_frame = ctk.CTkFrame(self._history_scroll, fg_color="transparent")
        self._history_rows_frame.pack(fill="x")
        _reg(self._history_rows_frame, "frame")

    def _refresh_history_tab(self):
        """[NEW] Rebuild the history rows from self._session_history."""
        def _do():
            if not hasattr(self, "_history_rows_frame"): return
            for w in self._history_rows_frame.winfo_children(): w.destroy()
            widths = [140, 260, 80, 80, 60, 60, 60, 80, 60]
            for i, rec in enumerate(reversed(self._session_history)):
                bg = BG2() if i % 2 == 0 else BG()
                row = ctk.CTkFrame(self._history_rows_frame, fg_color=bg, corner_radius=4)
                row.pack(fill="x", padx=4, pady=1); _reg(row, "frame2" if i % 2 == 0 else "frame")
                vals = [rec.get("time",""), rec.get("url","")[:38],
                        rec.get("backend",""), rec.get("mode",""),
                        str(rec.get("total",0)), str(rec.get("success",0)),
                        str(rec.get("failed",0)), str(rec.get("peak_rpm",0)),
                        str(rec.get("retries",0))]
                ok_ratio = rec.get("success",0) / max(rec.get("total",1), 1)
                for j, (val, w) in enumerate(zip(vals, widths)):
                    color = SUCCESS() if j == 5 and ok_ratio > 0.9 else \
                            FAIL()    if j == 6 and rec.get("failed",0) > 0 else FG2()
                    ctk.CTkLabel(row, text=val, width=w, text_color=color,
                                 fg_color="transparent", font=_font(), anchor="w"
                                 ).pack(side="left", padx=4, pady=3)
        self.root.after(0, _do)

    # -----------------------------------------------------------------------
    # Form shutdown alert system  [NEW]
    # -----------------------------------------------------------------------

    def _on_form_shutdown(self):
        """Called on the main thread when any backend detects the form has shut down."""
        self._log("[!] FORM SHUTDOWN DETECTED -- form is no longer accepting responses.")

        # Switch to Run tab and force a full layout pass so winfo_* calls are accurate
        try: self.nb.set("Run")
        except Exception: pass
        self.root.update_idletasks()

        # Stop the run (safe even if nothing is running)
        self._stop_run()

        # --- Alerts (each guarded individually so one failure doesn't block others) ---

        if T.get("sd_rainbow_text", True):
            try: self._log_rainbow("⚠  THE FORM HAS SHUT DOWN!  ⚠")
            except Exception: pass

        if T.get("sd_flash_taskbar", True):
            try: self._flash_titlebar()
            except Exception: pass

        # [FIX] Fire popup FIRST (it's a blocking modal), then show overlay AFTER it closes.
        # Old order (overlay at 120ms, popup at 200ms) caused the messagebox to bury the
        # place()-based overlay frame behind the app content when tkinter redraws on close.
        if T.get("sd_popup", True):
            # Show the messagebox now -- it blocks until the user clicks OK.
            # We wrap in after(0) so the current event finishes first.
            def _do_popup_then_overlay():
                messagebox.showwarning(
                    "Form Shutdown!", "THE FORM HAS SHUT DOWN!\n\nIt is no longer accepting responses.")
                # After the messagebox closes, show the overlay (if enabled)
                if T.get("sd_overlay", True):
                    self.root.after(50, self._show_shutdown_overlay)
                else:
                    try: self.root.deiconify(); self.root.lift()
                    except Exception: pass
                    if T.get("sd_sound", False):
                        try: self._play_alert_sound()
                        except Exception: pass
                    if T.get("sd_confetti", True):
                        self.root.after(50, self._start_confetti)
            self.root.after(50, _do_popup_then_overlay)
        else:
            # No popup -- show overlay directly
            if T.get("sd_overlay", True):
                self.root.after(120, self._show_shutdown_overlay)
            else:
                try: self.root.deiconify(); self.root.lift()
                except Exception: pass
                if T.get("sd_sound", False):
                    try: self._play_alert_sound()
                    except Exception: pass
                if T.get("sd_confetti", True):
                    self.root.after(120, self._start_confetti)

    def _flash_titlebar(self, flashes=6, interval=150):
        """Flash the title label colour to signal an alert -- no iconify needed."""
        orig_color = ACCENT2()
        flash_color = "#ffffff"
        _count = [0]

        def _toggle():
            if _count[0] >= flashes:
                try: self._title_label.configure(text_color=orig_color)
                except Exception: pass
                return
            color = flash_color if _count[0] % 2 == 0 else orig_color
            try: self._title_label.configure(text_color=color)
            except Exception: return
            _count[0] += 1
            self.root.after(interval, _toggle)

        _toggle()

    def _log_rainbow(self, msg):
        """[FIX issue-4] Write msg to the run log with cycling rainbow colours per character.
        The colours shift on each animation frame giving a moving/scrolling rainbow effect."""
        RAINBOW = ["#ff0000","#ff6600","#ffcc00","#33cc33","#0099ff","#9933ff","#ff33cc"]
        cycles  = int(T.get("sd_rainbow_cycles", 3))

        def _do():
            box   = self._log_box
            inner = box._textbox
            box.configure(state="normal")
            ts    = datetime.datetime.now().strftime("%H:%M:%S")
            full  = f"[{ts}] {msg}\n"
            start = inner.index("end-1c")
            inner.insert("end", full)

            # Build per-character tag names so we can recolour them in the animation loop
            char_tags = []
            for ci, ch in enumerate(full):
                colour = RAINBOW[(ci * cycles) % len(RAINBOW)]
                tag    = f"rb_{id(self)}_{ci}"
                char_tags.append(tag)
                char_idx = f"{start}+{ci}c"
                next_idx = f"{start}+{ci+1}c"
                inner.tag_add(tag, char_idx, next_idx)
                inner.tag_config(tag, foreground=colour)

            box.see("end")
            box.configure(state="disabled")

            # [FIX issue-4] Animate: shift colour offset each frame so the rainbow scrolls
            _offset = [0]
            _anim_frames = [0]
            MAX_ANIM_FRAMES = 60   # animate for ~3 seconds at 50ms/frame

            def _animate():
                if _anim_frames[0] >= MAX_ANIM_FRAMES:
                    return
                _offset[0] = (_offset[0] + 1) % len(RAINBOW)
                for ci, tag in enumerate(char_tags):
                    colour = RAINBOW[(ci * cycles + _offset[0]) % len(RAINBOW)]
                    try: inner.tag_config(tag, foreground=colour)
                    except Exception: return  # widget destroyed
                _anim_frames[0] += 1
                self.root.after(50, _animate)

            self.root.after(50, _animate)

        self.root.after(0, _do)

    def _play_alert_sound(self):
        """[NEW] Play alert.<ext> from the script folder if it exists.
        Supports mp3, wav, ogg, mp4, aac, flac, m4a via platform audio tools.
        Falls back to the system bell if no file is found or playback fails."""
        AUDIO_EXTS = ("mp3", "wav", "ogg", "mp4", "aac", "flac", "m4a", "oga", "opus")
        base_dir   = os.path.dirname(os.path.abspath(__file__))
        audio_path = None
        for ext in AUDIO_EXTS:
            candidate = os.path.join(base_dir, f"alert.{ext}")
            if os.path.isfile(candidate):
                audio_path = candidate
                break

        if audio_path is None:
            self.root.bell()
            return

        def _play():
            try:
                if sys.platform == "win32":
                    # Windows: use the built-in winsound for wav, otherwise playsound/os.startfile
                    if audio_path.lower().endswith(".wav"):
                        import winsound
                        winsound.PlaySound(audio_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    else:
                        # Try playsound (pip install playsound); silently fall back to bell
                        try:
                            import playsound
                            playsound.playsound(audio_path, block=False)
                        except Exception:
                            os.startfile(audio_path)
                elif sys.platform == "darwin":
                    import subprocess
                    subprocess.Popen(["afplay", audio_path],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    # Linux: try paplay, aplay, ffplay in order
                    import subprocess
                    for player in ("paplay", "aplay", "ffplay", "mpg123", "cvlc"):
                        try:
                            subprocess.Popen([player, audio_path],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            return
                        except FileNotFoundError:
                            continue
                    self.root.bell()
            except Exception:
                try: self.root.bell()
                except Exception: pass

        threading.Thread(target=_play, daemon=True).start()

    def _show_shutdown_overlay(self):
        """[REWRITE v3] In-app overlay drawn directly over the root window.

        Design goals:
        - NO new OS window -- a tk.Frame is placed over the existing app using place()
          covering 100% width and height, so it looks like part of the app itself
        - A card in the centre holds the message and Dismiss button (Roblox-style)
        - The dim backdrop behind the card intercepts all clicks (blocking background UI)
        - User CAN still minimize / maximize / hide the whole app via the OS title bar
          because those controls are on the OS frame, not inside our overlay frame
        - Dismiss button (or Esc/Enter) removes the overlay frame and restores the UI
        - Confetti animates on a canvas inside the overlay frame (behind the card)
        """
        # Already showing -- just lift it
        try:
            if self._shutdown_overlay and self._shutdown_overlay.winfo_exists():
                self._shutdown_overlay.lift()
                return
        except Exception:
            pass

        bg_color  = T.get("sd_overlay_color",    "#ff3333")
        text      = T.get("sd_overlay_text",     "THE FORM HAS SHUT DOWN!")
        fsize     = int(T.get("sd_overlay_font_size", 36))
        weight    = "bold" if T.get("sd_overlay_bold", True) else "normal"
        # Backdrop: semi-transparent dark scrim (achieved by a dark colour, not -alpha,
        # because -alpha applies to the whole window not an individual frame in tkinter)
        SCRIM     = "#111111"   # very dark -- gives the "dimmed background" feel
        CARD_BG   = "#2a2a3c"  # card colour -- matches app dark theme
        CARD_W    = 520
        CARD_H    = 260

        # --- Backdrop frame: covers the entire root window ---
        # [KEY FIX] place() with relwidth/relheight=1 fills the whole window.
        # This frame sits IN the root widget tree (not a separate OS window) so
        # the OS title bar / taskbar controls still work normally.
        backdrop = tk.Frame(self.root, bg=SCRIM, cursor="arrow")
        backdrop.place(x=0, y=0, relwidth=1, relheight=1)
        backdrop.lift()   # ensure it's above all other widgets

        # Eat all mouse clicks on the backdrop so nothing behind it is clickable
        backdrop.bind("<Button-1>", lambda e: None)
        backdrop.bind("<Button-2>", lambda e: None)
        backdrop.bind("<Button-3>", lambda e: None)

        # --- Card: rounded rectangle in the centre of the backdrop ---
        card = tk.Frame(backdrop, bg=CARD_BG, relief="flat", bd=0)
        # Centre the card by using place with anchor="center"
        card.place(relx=0.5, rely=0.5, anchor="center", width=CARD_W, height=CARD_H)

        # --- Message label inside card ---
        lbl = tk.Label(card, text=text, bg=CARD_BG, fg="#ffffff",
                       font=(T["font_family"], fsize, weight),
                       wraplength=CARD_W - 60, justify="center")
        lbl.place(relx=0.5, rely=0.38, anchor="center")

        def _do_dismiss(*_):
            """Remove the overlay frame -- restores the app UI underneath."""
            self._shutdown_overlay = None
            # Unbind keyboard shortcuts from root
            try: self.root.unbind("<Escape>")
            except Exception: pass
            try: self.root.unbind("<Return>")
            except Exception: pass
            try: backdrop.destroy()
            except Exception: pass

        # --- Dismiss button: top-right corner of card (like the Roblox mockup CLOSE btn) ---
        close_btn = tk.Button(
            card,
            text="CLOSE",
            command=_do_dismiss,
            bg="#cc2222", fg="#ffffff",
            font=(T["font_family"], 11, "bold"),
            relief="flat", cursor="hand2", bd=0,
            activebackground="#991111", activeforeground="#ffffff",
            padx=12, pady=5
        )
        # Place in top-right corner of the card
        close_btn.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)

        # Keyboard shortcuts bound to root (not backdrop) so they work even if
        # focus is on the main window after minimise/restore
        self.root.bind("<Escape>", _do_dismiss)
        self.root.bind("<Return>", _do_dismiss)

        # Bring the whole app to front once (normal window behaviour)
        try:
            self.root.deiconify()
            self.root.lift()
        except Exception: pass

        self._shutdown_overlay = backdrop

        # [NEW] Keep-on-top mode: either loop every 100ms or lift just once.
        # The loop prevents tab switches / redraws from burying the overlay.
        # The "once" mode is lighter and lets other windows go on top naturally.
        if T.get("sd_overlay_keep_on_top", True):
            def _keep_on_top():
                try:
                    if backdrop.winfo_exists():
                        backdrop.lift()
                        card.lift()
                        close_btn.lift()
                        self.root.after(100, _keep_on_top)
                except Exception:
                    pass
            self.root.after(100, _keep_on_top)
        else:
            # Lift once -- no loop
            try:
                backdrop.lift()
                card.lift()
                close_btn.lift()
            except Exception:
                pass

        # Sound
        if T.get("sd_sound", False):
            self._play_alert_sound()

        # Confetti: canvas inside backdrop (behind the card) -- fills the whole backdrop.
        # We delay one frame so the backdrop has been mapped and winfo_* values are valid.
        if T.get("sd_confetti", True):
            def _launch_confetti():
                try:
                    pw = backdrop.winfo_width()
                    ph = backdrop.winfo_height()
                    if pw < 10 or ph < 10:
                        self.root.after(50, _launch_confetti)
                        return
                    # [FIX v2] Pass card + close_btn as lift_above so every tick
                    # re-lifts them above the canvas -- canvas can never bury them.
                    self._start_confetti(parent=backdrop, pw=pw, ph=ph, bg=SCRIM,
                                         lift_above=[card, close_btn, lbl])
                except Exception:
                    pass
            self.root.after(50, _launch_confetti)

    def _start_confetti(self, parent=None, pw=None, ph=None, bg=None,
                        lift_above=None, on_done=None):
        """Animate falling confetti pieces over the given parent widget.
        [FIX v3] Canvas uses relwidth/relheight=1 so it always fills the parent frame.
                 Parent size is re-read every tick so window resize/move never breaks it.
                 lift_above: sibling widgets to re-lift above the canvas on every frame.
        [FIX v4] on_done: optional callback fired when animation ends naturally (MAX_FRAMES).
                 Used by the standalone confetti popup to auto-dismiss its scrim overlay."""
        speed  = max(1, min(5, int(T.get("sd_confetti_speed", 3))))
        count  = max(10, min(200, int(T.get("sd_confetti_count", 80))))
        COLORS = ["#ff0000","#ff8800","#ffff00","#00cc44","#0088ff","#cc00ff","#ff00cc","#ffffff"]

        if parent is None:
            # [FIX] Never draw on self.root directly -- caller must always supply a parent frame.
            return

        canvas_bg = bg or BG()
        canvas = tk.Canvas(parent, highlightthickness=0, bg=canvas_bg, bd=0)
        # [FIX v3] relwidth/relheight=1: canvas always matches its parent, no fixed px size.
        # This means resize/move of the root window never makes the canvas the wrong size.
        canvas.place(x=0, y=0, relwidth=1, relheight=1)
        canvas.lower()   # behind siblings initially

        # Immediately re-lift widgets that must stay above the canvas
        widgets_above = lift_above or []
        for w in widgets_above:
            try: w.lift()
            except Exception: pass

        # Seed initial piece positions using supplied or measured dimensions
        _pw = [pw if (pw and pw > 10) else (parent.winfo_width() or 800)]
        _ph = [ph if (ph and ph > 10) else (parent.winfo_height() or 600)]

        pieces = []
        for _ in range(count):
            cx    = random.randint(0, _pw[0])
            cy    = random.randint(-_ph[0], 0)
            dx    = random.uniform(-1.5, 1.5)
            dy    = random.uniform(1.5 * speed, 3.5 * speed)
            color = random.choice(COLORS)
            sz    = random.randint(5, 12)
            shape = canvas.create_rectangle if random.random() < 0.5 else canvas.create_oval
            item  = shape(cx, cy, cx+sz, cy+sz, fill=color, outline="")
            pieces.append([item, cx, cy, dx, dy, sz])

        _frames = [0]
        MAX_FRAMES = 300  # ~9 s at 30 ms/frame

        def _tick():
            try:
                if not canvas.winfo_exists():
                    return
                # [FIX] self.root.winfo_viewable() returns 0 in CTk even when the window
                # is fully visible, causing _tick to stall on the 200ms slow path forever.
                # Particles start above the view (cy < 0) and never fall in.
                # Check canvas.winfo_ismapped() instead -- reliably True while canvas lives.
                if not canvas.winfo_ismapped():
                    self.root.after(200, _tick)
                    return
            except Exception:
                return
            if _frames[0] >= MAX_FRAMES:
                try: canvas.destroy()
                except Exception: pass
                # [FIX v4] Let the caller clean up its own overlay container (e.g. the
                # standalone confetti popup scrim). Without this, when the animation
                # ends the scrim stays covering the whole app with no way to dismiss it.
                if on_done:
                    try: on_done()
                    except Exception: pass
                return

            # [FIX v3] Re-read parent size every tick so resize/move is always correct
            try:
                w = parent.winfo_width()
                h = parent.winfo_height()
                if w > 10: _pw[0] = w
                if h > 10: _ph[0] = h
            except Exception:
                pass

            for p in pieces:
                item, cx, cy, dx, dy, sz = p
                cx += dx; cy += dy
                if cy > _ph[0]:
                    cy = random.randint(-40, 0)
                    cx = random.randint(0, _pw[0])
                try: canvas.coords(item, cx, cy, cx+sz, cy+sz)
                except Exception: return
                p[1] = cx; p[2] = cy

            # Re-lift overlaid widgets every frame so canvas never buries them
            for w in widgets_above:
                try: w.lift()
                except Exception: pass

            _frames[0] += 1
            self.root.after(30, _tick)

        _tick()

    # -----------------------------------------------------------------------
    # Debug tab  [DEBUG TAB]
    # -----------------------------------------------------------------------

    def _build_debug_tab(self):
        p = self._tab_debug

        hdr = ctk.CTkFrame(p, fg_color="transparent"); hdr.pack(fill="x", padx=16, pady=(12,4))
        _reg(hdr, "frame")
        _label(hdr, "Debug / Error Log", role="label_bold").pack(side="left")
        _label(hdr, "  — errors and warnings captured here automatically",
               role="label2").pack(side="left")

        br = ctk.CTkFrame(p, fg_color="transparent"); br.pack(fill="x", padx=16, pady=(0,6))
        _reg(br, "frame")

        def _clear():
            self._debug_box.configure(state="normal")
            self._debug_box.delete("0.0", "end")
            self._debug_box.configure(state="disabled")

        def _copy():
            text = self._debug_box.get("0.0", "end").strip()
            if text:
                self.root.clipboard_clear(); self.root.clipboard_append(text)
                messagebox.showinfo("Copied", "Debug log copied to clipboard.")
            else:
                messagebox.showinfo("Empty", "Debug log is empty.")

        _button(br, "  Clear  ", _clear).pack(side="left", padx=(0,8))
        _button(br, "  Copy to Clipboard  ", _copy).pack(side="left")

        # [COLOUR] Debug box uses coloured lines too:
        #   errors/fails -> FAIL() red, warnings -> orange, rest -> FAIL() dim
        self._debug_box = ctk.CTkTextbox(p, fg_color=BG2(), text_color=FAIL(),
                                          border_color=BG3(), corner_radius=CR(),
                                          font=ctk.CTkFont(T["mono_family"], T["mono_size"]),
                                          state="disabled")
        self._debug_box.pack(fill="both", expand=True, padx=16, pady=(0,14))
        _reg(self._debug_box, "textbox")

    def _debug_log(self, msg):
        # [COLOUR] Colour debug lines by severity:
        #   "error"/"exception"/"traceback" -> FAIL() bright red
        #   "warning"/"warn"               -> orange (#f59e0b, visible on all themes)
        #   everything else                -> FAIL() at lower opacity (muted red)
        ts  = datetime.datetime.now().strftime("%H:%M:%S")
        low = msg.lower()
        if any(k in low for k in ("error","exception","traceback","refused")):
            tag, colour = "dbg_error",   FAIL()
        elif any(k in low for k in ("warning","warn","timeout")):
            tag, colour = "dbg_warning", "#f59e0b"   # amber -- visible on all themes
        else:
            tag, colour = "dbg_info",    FAIL()

        def _do():
            box   = self._debug_box
            inner = box._textbox
            inner.tag_config("dbg_error",   foreground=FAIL())
            inner.tag_config("dbg_warning", foreground="#f59e0b")
            inner.tag_config("dbg_info",    foreground=FAIL())

            box.configure(state="normal")
            start = inner.index("end-1c")
            inner.insert("end", f"[{ts}] {msg}\n")
            end   = inner.index("end-1c")
            inner.tag_add(tag, start, end)
            box.see("end")
            box.configure(state="disabled")
        self.root.after(0, _do)

    # -----------------------------------------------------------------------
    # Customise tab
    # -----------------------------------------------------------------------

    def _build_theme_tab(self):
        p  = self._tab_theme
        sf = _scrollframe(p); sf.pack(fill="both", expand=True)

        def section(text):
            f = ctk.CTkFrame(sf, fg_color=BG3(), corner_radius=8)
            f.pack(fill="x", padx=12, pady=(12,2)); _reg(f, "frame3")
            ctk.CTkLabel(f, text=f"  {text}  ", text_color=ACCENT2(), fg_color="transparent",
                         font=_font(bold=True), anchor="w").pack(fill="x", pady=6)

        # -- Presets --
        section("Presets")
        pf = ctk.CTkFrame(sf, fg_color="transparent"); pf.pack(fill="x", padx=24, pady=6)
        _reg(pf, "frame")
        self._preset_var = tk.StringVar(value="Dark Purple (default)")
        pm = ctk.CTkComboBox(pf, variable=self._preset_var, values=list(PRESETS.keys()),
                              width=260, fg_color=BG3(), text_color=FG(),
                              button_color=ACCENT(), dropdown_fg_color=BG2(),
                              dropdown_text_color=FG(), font=_font(), state="readonly")
        pm.pack(side="left", padx=(0,10)); _reg(pm, "entry")

        def apply_preset():
            name = self._preset_var.get()
            if name in PRESETS:
                T.update(PRESETS[name])
                self._refresh_theme_controls()
                _apply_theme(self.root, self.nb, self._title_label)
        _button(pf, "Apply Preset", apply_preset).pack(side="left", padx=4)

        # -- Colours --
        section("Colours")
        colour_rows = [
            ("bg","Background"),("bg2","Background 2"),("bg3","Background 3"),
            ("accent","Accent"),("accent2","Accent Light"),
            ("fg","Text"),("fg2","Text Dim"),("success","Success"),("fail","Fail / Stop"),
        ]
        csec = ctk.CTkFrame(sf, fg_color="transparent"); csec.pack(fill="x", padx=24, pady=4)
        _reg(csec, "frame")
        self._colour_btns = {}
        for i, (key, label) in enumerate(colour_rows):
            r, c = divmod(i, 3)
            cf = ctk.CTkFrame(csec, fg_color="transparent"); cf.grid(row=r, column=c, padx=6, pady=4, sticky="w")
            _reg(cf, "frame")
            ctk.CTkLabel(cf, text=label, text_color=FG2(), fg_color="transparent",
                         font=_font(), width=110, anchor="w").pack(side="left")
            # Colour swatch (plain tk.Label -- CTk has no clickable colour swatch)
            swatch = tk.Label(cf, text="      ", bg=T[key], relief="flat", cursor="hand2", bd=2)
            swatch.pack(side="left")
            _reg(swatch, "tk_sep")  # won't recolour bg but that's fine -- it IS the colour

            def _pick(k=key, sw=swatch):
                result = colorchooser.askcolor(color=T[k], title=f"Choose {k}")
                if result and result[1]:
                    T[k] = result[1]; sw.config(bg=result[1])
                    _apply_theme(self.root, self.nb, self._title_label)
            swatch.bind("<Button-1>", lambda e, fn=_pick: fn())
            self._colour_btns[key] = swatch

            hv = tk.StringVar(value=T[key])
            he = ctk.CTkEntry(cf, textvariable=hv, width=80, fg_color=BG3(),
                               text_color=FG(), border_color=BG3(), corner_radius=6,
                               font=_font())
            he.pack(side="left", padx=(4,0)); _reg(he, "entry")

            def _hex_change(var=hv, k=key, sw=swatch):
                val = var.get().strip()
                if len(val) == 7 and val.startswith("#"):
                    try:
                        sw.config(bg=val); T[k] = val
                        _apply_theme(self.root, self.nb, self._title_label)
                    except Exception: pass
            hv.trace_add("write", lambda *_, fn=_hex_change: fn())

        # -- Corner Radius --
        section("Corner Radius")
        cr_frame = ctk.CTkFrame(sf, fg_color="transparent"); cr_frame.pack(fill="x", padx=24, pady=4)
        _reg(cr_frame, "frame")
        ctk.CTkLabel(cr_frame, text="Roundness (px):", text_color=FG2(), fg_color="transparent",
                     font=_font(), width=160, anchor="w").pack(side="left")
        cr_var = tk.IntVar(value=T.get("corner_radius", 10))
        cr_sl  = ctk.CTkSlider(cr_frame, variable=cr_var, from_=0, to=24,
                                fg_color=BG3(), progress_color=ACCENT(), button_color=ACCENT2(),
                                width=200)
        cr_sl.pack(side="left", padx=8)
        ctk.CTkLabel(cr_frame, textvariable=cr_var, text_color=FG(), fg_color="transparent",
                     font=_font(), width=30).pack(side="left")

        def _cr_change(*_):
            T["corner_radius"] = cr_var.get()
            _apply_theme(self.root, self.nb, self._title_label)
        cr_var.trace_add("write", lambda *_: _cr_change())

        # -- Fonts --
        section("Fonts")
        try:    available_fonts = sorted(set(tkfont.families()))
        except: available_fonts = ["Segoe UI","Arial","Courier New","Consolas","Helvetica"]

        font_sec = ctk.CTkFrame(sf, fg_color="transparent"); font_sec.pack(fill="x", padx=24, pady=4)
        _reg(font_sec, "frame")

        def font_row(parent, label, fam_key, sz_key):
            fr = ctk.CTkFrame(parent, fg_color="transparent"); fr.pack(fill="x", pady=3)
            _reg(fr, "frame")
            ctk.CTkLabel(fr, text=label, width=160, anchor="w", text_color=FG2(),
                         fg_color="transparent", font=_font()).pack(side="left")
            fv = tk.StringVar(value=T[fam_key])
            fc = ctk.CTkComboBox(fr, variable=fv, values=available_fonts, width=200,
                                  fg_color=BG3(), text_color=FG(), button_color=ACCENT(),
                                  dropdown_fg_color=BG2(), dropdown_text_color=FG(),
                                  font=_font(), state="readonly")
            fc.pack(side="left", padx=(0,6)); _reg(fc, "entry")
            sv = tk.IntVar(value=T[sz_key])
            _spinbox(fr, 7, 28, sv, width=4).pack(side="left", padx=(0,8))

            def _upd(*_):
                T[fam_key] = fv.get(); T[sz_key] = sv.get()
                _apply_theme(self.root, self.nb, self._title_label)
            fv.trace_add("write", lambda *_: _upd())
            sv.trace_add("write", lambda *_: _upd())

        font_row(font_sec, "UI Font",     "font_family", "font_size")
        font_row(font_sec, "Mono (log)",  "mono_family", "mono_size")
        font_row(font_sec, "Title Font",  "font_family", "title_font_size")

        # -- Title bar --
        section("Title Bar")
        tb_frame = ctk.CTkFrame(sf, fg_color="transparent"); tb_frame.pack(fill="x", padx=24, pady=4)
        _reg(tb_frame, "frame")

        def tb_row(label, t_key, is_int=False, width=260):
            fr = ctk.CTkFrame(tb_frame, fg_color="transparent"); fr.pack(fill="x", pady=3)
            _reg(fr, "frame")
            ctk.CTkLabel(fr, text=label, width=180, anchor="w", text_color=FG2(),
                         fg_color="transparent", font=_font()).pack(side="left")
            if is_int:
                v = tk.IntVar(value=int(T.get(t_key, 48)))
                _spinbox(fr, 30, 80, v, width=6).pack(side="left")
            else:
                v = tk.StringVar(value=T.get(t_key, ""))
                e = ctk.CTkEntry(fr, textvariable=v, width=width, fg_color=BG3(),
                                  text_color=FG(), border_color=BG3(), corner_radius=CR(),
                                  font=_font())
                e.pack(side="left"); _reg(e, "entry")
            def _upd(*_):
                T[t_key] = v.get() if not is_int else int(v.get())
                _apply_theme(self.root, self.nb, self._title_label)
            v.trace_add("write", lambda *_: _upd())

        tb_row("Title text",      "title_text")
        tb_row("Title font size", "title_font_size", is_int=True)
        tb_row("Bar height (px)", "titlebar_height", is_int=True)

        # -- Opacity --
        section("Window Opacity")
        op_frame = ctk.CTkFrame(sf, fg_color="transparent"); op_frame.pack(fill="x", padx=24, pady=4)
        _reg(op_frame, "frame")
        op_row = ctk.CTkFrame(op_frame, fg_color="transparent"); op_row.pack(fill="x", pady=3)
        _reg(op_row, "frame")
        ctk.CTkLabel(op_row, text="Opacity (0.1 – 1.0)", width=180, anchor="w", text_color=FG2(),
                     fg_color="transparent", font=_font()).pack(side="left")
        self._opacity_var = tk.DoubleVar(value=T.get("opacity", 1.0))
        ctk.CTkSlider(op_row, variable=self._opacity_var, from_=0.1, to=1.0,
                      fg_color=BG3(), progress_color=ACCENT(), button_color=ACCENT2(),
                      width=200).pack(side="left", padx=8)
        ctk.CTkLabel(op_row, textvariable=self._opacity_var, width=40,
                     text_color=FG(), fg_color="transparent", font=_font()).pack(side="left")

        def _op_change(*_):
            T["opacity"] = round(self._opacity_var.get(), 2)
            try: self.root.attributes("-alpha", T["opacity"])
            except Exception: pass
        self._opacity_var.trace_add("write", _op_change)

        # -- Shutdown Alert (Debug/Alert Settings) --
        section("⚠  Form Shutdown Alert")
        sd_outer = ctk.CTkFrame(sf, fg_color="transparent"); sd_outer.pack(fill="x", padx=24, pady=4)
        _reg(sd_outer, "frame")

        ctk.CTkLabel(sd_outer,
            text="Configure what happens when a form is detected as shut down / no longer accepting responses.",
            text_color=FG2(), fg_color="transparent", font=_font(), wraplength=580, anchor="w"
        ).pack(fill="x", pady=(0,6))

        def _sd_toggle_row(parent, label, key, tooltip=""):
            row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", pady=2)
            _reg(row, "frame")
            v = tk.BooleanVar(value=bool(T.get(key, True)))
            sw = ctk.CTkSwitch(row, text=label, variable=v,
                               fg_color=BG3(), progress_color=ACCENT(), button_color=ACCENT2(),
                               text_color=FG(), font=_font())
            sw.pack(side="left")
            if tooltip:
                ctk.CTkLabel(row, text=f"  ({tooltip})", text_color=FG2(),
                             fg_color="transparent", font=_font(size=10)).pack(side="left")
            def _upd(*_): T[key] = v.get()
            v.trace_add("write", lambda *_: _upd())
            return v

        def _sd_slider_row(parent, label, key, lo, hi, is_float=False):
            row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", pady=3)
            _reg(row, "frame")
            ctk.CTkLabel(row, text=label, width=200, anchor="w", text_color=FG2(),
                         fg_color="transparent", font=_font()).pack(side="left")
            if is_float:
                v = tk.DoubleVar(value=float(T.get(key, lo)))
                sl = ctk.CTkSlider(row, variable=v, from_=lo, to=hi,
                                   fg_color=BG3(), progress_color=ACCENT(), button_color=ACCENT2(),
                                   width=180); sl.pack(side="left", padx=6)
                ctk.CTkLabel(row, textvariable=v, width=46, text_color=FG(),
                             fg_color="transparent", font=_font()).pack(side="left")
                def _upd(*_): T[key] = round(v.get(), 2)
            else:
                v = tk.IntVar(value=int(T.get(key, lo)))
                sl = ctk.CTkSlider(row, variable=v, from_=lo, to=hi,
                                   fg_color=BG3(), progress_color=ACCENT(), button_color=ACCENT2(),
                                   width=180); sl.pack(side="left", padx=6)
                ctk.CTkLabel(row, textvariable=v, width=40, text_color=FG(),
                             fg_color="transparent", font=_font()).pack(side="left")
                def _upd(*_): T[key] = int(v.get())
            v.trace_add("write", lambda *_: _upd())

        def _sd_colour_row(parent, label, key):
            row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", pady=3)
            _reg(row, "frame")
            ctk.CTkLabel(row, text=label, width=200, anchor="w", text_color=FG2(),
                         fg_color="transparent", font=_font()).pack(side="left")
            swatch = tk.Label(row, text="      ", bg=T.get(key,"#ff3333"),
                              relief="flat", cursor="hand2", bd=2)
            swatch.pack(side="left", padx=(0,6))
            hv = tk.StringVar(value=T.get(key,"#ff3333"))
            he = ctk.CTkEntry(row, textvariable=hv, width=80, fg_color=BG3(),
                               text_color=FG(), border_color=BG3(), corner_radius=6,
                               font=_font()); he.pack(side="left"); _reg(he, "entry")
            def _pick(k=key, sw=swatch):
                result = colorchooser.askcolor(color=T.get(k,"#ff3333"), title=f"Choose {k}")
                if result and result[1]:
                    T[k] = result[1]; sw.config(bg=result[1]); hv.set(result[1])
            swatch.bind("<Button-1>", lambda e, fn=_pick: fn())
            def _hex_chg(var=hv, k=key, sw=swatch):
                val = var.get().strip()
                if len(val) == 7 and val.startswith("#"):
                    try: sw.config(bg=val); T[k] = val
                    except Exception: pass
            hv.trace_add("write", lambda *_, fn=_hex_chg: fn())

        def _sd_text_row(parent, label, key, width=320):
            row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", pady=3)
            _reg(row, "frame")
            ctk.CTkLabel(row, text=label, width=200, anchor="w", text_color=FG2(),
                         fg_color="transparent", font=_font()).pack(side="left")
            v = tk.StringVar(value=str(T.get(key,"")))
            e = ctk.CTkEntry(row, textvariable=v, width=width, fg_color=BG3(),
                              text_color=FG(), border_color=BG3(), corner_radius=6, font=_font())
            e.pack(side="left"); _reg(e, "entry")
            def _upd(*_): T[key] = v.get()
            v.trace_add("write", lambda *_: _upd())

        # Toggles
        _sd_toggle_row(sd_outer, "Rainbow text in log",        "sd_rainbow_text",
                       "coloured per-character rainbow line in the run log")
        _sd_toggle_row(sd_outer, "Confetti animation",         "sd_confetti",
                       "confetti rains over the log area")
        _sd_toggle_row(sd_outer, "System popup (messagebox)",  "sd_popup",
                       "OS alert dialog, comes to front of all windows")
        _sd_toggle_row(sd_outer, "Window overlay",             "sd_overlay",
                       "translucent banner on top of the main window")
        _sd_toggle_row(sd_outer, "System bell / sound",        "sd_sound",
                       "terminal bell -- may be silent depending on OS settings")
        _sd_toggle_row(sd_outer, "Flash / raise window",       "sd_flash_taskbar",
                       "brings the app to the front and focuses it")

        _separator(sd_outer).pack(fill="x", pady=8)

        # [NEW] Sleep prevention toggles
        ctk.CTkLabel(sd_outer, text="Sleep & Power Settings", text_color=ACCENT2(),
                     fg_color="transparent", font=_font(bold=True)).pack(anchor="w", pady=(2,4))
        ctk.CTkLabel(sd_outer,
            text="Keep the computer awake while the app is open. Useful for long unattended runs.",
            text_color=FG2(), fg_color="transparent", font=_font(), wraplength=560, anchor="w"
        ).pack(fill="x", pady=(0,4))

        def _sleep_toggle_row(label, key, tooltip=""):
            """Like _sd_toggle_row but calls _apply_sleep_prevention on change."""
            row = ctk.CTkFrame(sd_outer, fg_color="transparent"); row.pack(fill="x", pady=2)
            _reg(row, "frame")
            v = tk.BooleanVar(value=bool(T.get(key, False)))
            sw = ctk.CTkSwitch(row, text=label, variable=v,
                               fg_color=BG3(), progress_color=ACCENT(), button_color=ACCENT2(),
                               text_color=FG(), font=_font())
            sw.pack(side="left")
            if tooltip:
                ctk.CTkLabel(row, text=f"  ({tooltip})", text_color=FG2(),
                             fg_color="transparent", font=_font(size=10)).pack(side="left")
            def _upd(*_):
                T[key] = v.get()
                _apply_sleep_prevention()   # apply immediately on toggle
            v.trace_add("write", lambda *_: _upd())

        _sleep_toggle_row("Prevent system sleep",
                          "prevent_system_sleep",
                          "stops the computer from sleeping while the app is running")
        _sleep_toggle_row("Prevent screen sleep / blank",
                          "prevent_screen_sleep",
                          "keeps the display on while the app is running")

        _separator(sd_outer).pack(fill="x", pady=8)

        # Overlay customisation
        ctk.CTkLabel(sd_outer, text="Overlay Settings", text_color=ACCENT2(),
                     fg_color="transparent", font=_font(bold=True)).pack(anchor="w", pady=(2,4))
        _sd_slider_row(sd_outer,  "Overlay transparency",    "sd_overlay_alpha",    0.1, 0.95, is_float=True)
        _sd_colour_row(sd_outer,  "Overlay background color","sd_overlay_color")
        _sd_text_row  (sd_outer,  "Overlay message text",    "sd_overlay_text")
        _sd_slider_row(sd_outer,  "Overlay font size",       "sd_overlay_font_size",12, 72)
        _sd_toggle_row(sd_outer,  "Overlay font bold",       "sd_overlay_bold")
        # [NEW] Keep-on-top mode toggle
        _sd_toggle_row(sd_outer,  "Keep overlay on top (loop every 100ms)",
                       "sd_overlay_keep_on_top",
                       "ON = re-lifts overlay constantly so nothing buries it  |  OFF = lift once only")

        _separator(sd_outer).pack(fill="x", pady=8)

        # Confetti + rainbow customisation
        ctk.CTkLabel(sd_outer, text="Confetti & Rainbow Settings", text_color=ACCENT2(),
                     fg_color="transparent", font=_font(bold=True)).pack(anchor="w", pady=(2,4))
        _sd_slider_row(sd_outer, "Confetti piece count",   "sd_confetti_count",  10, 200)
        _sd_slider_row(sd_outer, "Confetti speed (1–5)",   "sd_confetti_speed",   1, 5)
        _sd_slider_row(sd_outer, "Rainbow colour cycles",  "sd_rainbow_cycles",   1, 8)

        _separator(sd_outer).pack(fill="x", pady=8)

        # [NEW] Answer Validation Settings
        ctk.CTkLabel(sd_outer, text="Answer Validation", text_color=ACCENT2(),
                     fg_color="transparent", font=_font(bold=True)).pack(anchor="w", pady=(2,4))
        ctk.CTkLabel(sd_outer,
            text="Controls what happens when a text answer is too long / too short, "
                 "or a number is out of range, or a chosen option doesn't exist in the form.",
            text_color=FG2(), fg_color="transparent", font=_font(), wraplength=560, anchor="w"
        ).pack(fill="x", pady=(0,6))

        def _val_radio_row(parent, label, key, options_labels):
            """Row with radio buttons for a string-valued T key."""
            row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", pady=3)
            _reg(row, "frame")
            ctk.CTkLabel(row, text=label, width=220, anchor="w", text_color=FG2(),
                         fg_color="transparent", font=_font()).pack(side="left")
            v = tk.StringVar(value=str(T.get(key, options_labels[0][1])))
            for lbl, val in options_labels:
                _radio(row, lbl, v, val).pack(side="left", padx=(0,10))
            def _upd(*_): T[key] = v.get()
            v.trace_add("write", lambda *_: _upd())

        _val_radio_row(sd_outer,
            "If text is too long / number out of range:",
            "val_on_length_overflow",
            [("Truncate text", "truncate"),
             ("Skip answer (blank field)", "skip_answer"),
             ("Skip whole submission", "skip_submission")])

        _val_radio_row(sd_outer,
            "If a choice is invalid / not in list:",
            "val_on_invalid_choice",
            [("Skip that choice (leave blank)", "skip_choice"),
             ("Skip whole submission", "skip_submission")])

        # [FIX] btn_row_sd was used below but never created -- NameError on startup.
        btn_row_sd = ctk.CTkFrame(sd_outer, fg_color="transparent"); btn_row_sd.pack(pady=6)
        _reg(btn_row_sd, "frame")
        _button(btn_row_sd, "  Test Alert  ",
                lambda: self.root.after(0, self._on_form_shutdown)
                ).pack(side="left", padx=5)
        _label(btn_row_sd, "  ← fires all enabled shutdown alerts immediately", role="label2"
               ).pack(side="left")

        # [FIX] Confetti button -- in-app overlay frame (same technique as shutdown overlay).
        # No new OS window: a frame is placed over the root with place(relwidth/relheight=1).
        def _confetti_popup():
            # If one is already showing, do nothing
            if hasattr(self, "_confetti_overlay") and self._confetti_overlay:
                try:
                    if self._confetti_overlay.winfo_exists():
                        return
                except Exception:
                    pass

            SCRIM   = "#0a0a14"   # very dark scrim behind confetti
            CARD_BG = BG2()

            scrim = tk.Frame(self.root, bg=SCRIM, cursor="arrow")
            scrim.place(x=0, y=0, relwidth=1, relheight=1)
            scrim.lift()

            # Eat clicks on scrim so background UI is blocked
            scrim.bind("<Button-1>", lambda e: None)

            # Small card with close button
            card = tk.Frame(scrim, bg=CARD_BG, relief="flat", bd=0)
            card.place(relx=0.5, rely=0.5, anchor="center", width=340, height=120)

            lbl_card = tk.Label(card, text="🎉  Enjoy the confetti!", bg=CARD_BG, fg=T["fg"],
                     font=(T["font_family"], 14, "bold"))
            lbl_card.place(relx=0.5, rely=0.42, anchor="center")

            def _close_confetti(*_):
                self._confetti_overlay = None
                # [FIX] Unbind BEFORE destroying to avoid event-after-destroy errors
                try: self.root.unbind("<Escape>")
                except Exception: pass
                try: scrim.destroy()
                except Exception: pass

            close_btn_c = tk.Button(card, text="CLOSE", command=_close_confetti,
                      bg="#cc2222", fg="#ffffff",
                      font=(T["font_family"], 11, "bold"),
                      relief="flat", cursor="hand2", bd=0,
                      activebackground="#991111", activeforeground="#ffffff",
                      padx=12, pady=5)
            close_btn_c.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)

            self.root.bind("<Escape>", _close_confetti)
            self._confetti_overlay = scrim

            def _launch():
                try:
                    pw = scrim.winfo_width()
                    ph = scrim.winfo_height()
                    if pw < 10 or ph < 10:
                        self.root.after(50, _launch); return
                    # [FIX v4] Pass on_done so the scrim is auto-dismissed when the
                    # animation finishes. Previously only the canvas was destroyed,
                    # leaving a dead dark overlay blocking the whole app.
                    self._start_confetti(parent=scrim, pw=pw, ph=ph, bg=SCRIM,
                                         lift_above=[card, lbl_card, close_btn_c],
                                         on_done=_close_confetti)
                except Exception:
                    pass
            self.root.after(50, _launch)

            # [FIX v4] Keep scrim on top every 150 ms -- same pattern as the shutdown
            # overlay keep_on_top loop. Without this, CTk internal redraws can bury
            # the scrim below the content frame, making the CLOSE button unreachable.
            def _keep_scrim_top():
                try:
                    if scrim.winfo_exists():
                        scrim.lift()
                        card.lift()
                        self.root.after(150, _keep_scrim_top)
                except Exception:
                    pass
            self.root.after(150, _keep_scrim_top)

        _button(btn_row_sd, "  🎉 Confetti!  ", _confetti_popup
                ).pack(side="left", padx=(20, 5))

        # -- Save / Load / Reset --
        section("Save & Load")
        sl_frame = ctk.CTkFrame(sf, fg_color="transparent"); sl_frame.pack(fill="x", padx=24, pady=(4,20))
        _reg(sl_frame, "frame")
        btn_row = ctk.CTkFrame(sl_frame, fg_color="transparent"); btn_row.pack(pady=6)
        _reg(btn_row, "frame")

        def save_theme():
            _save_theme()
            messagebox.showinfo("Theme saved", f"Theme saved to:\n{THEME_FILE}\n\nLoads automatically next time.")
        def reset_theme():
            if messagebox.askyesno("Reset theme", "Reset to default Dark Purple theme?"):
                T.update(_default_theme()); self._refresh_theme_controls()
                _apply_theme(self.root, self.nb, self._title_label)
        def export_theme():
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(defaultextension=".json",
                                                filetypes=[("JSON theme","*.json"),("All files","*.*")],
                                                title="Export theme")
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as f: json.dump(T, f, indent=2)
                    messagebox.showinfo("Exported", f"Theme exported to:\n{path}")
                except Exception as e: messagebox.showerror("Export failed", str(e))
        def import_theme():
            from tkinter import filedialog
            path = filedialog.askopenfilename(filetypes=[("JSON theme","*.json"),("All files","*.*")],
                                              title="Import theme")
            if path:
                try:
                    with open(path, encoding="utf-8") as f: data = json.load(f)
                    base = _default_theme(); base.update(data); T.update(base)
                    self._refresh_theme_controls()
                    _apply_theme(self.root, self.nb, self._title_label)
                except Exception as e: messagebox.showerror("Import failed", str(e))

        for txt, fn in [("  Save Theme  ", save_theme), ("  Reset  ", reset_theme),
                        ("  Export…  ", export_theme), ("  Import…  ", import_theme)]:
            _button(btn_row, txt, fn).pack(side="left", padx=5)

        ctk.CTkLabel(sl_frame,
                     text="Theme auto-loads on startup if saved.  Export/Import to share themes.",
                     text_color=FG2(), fg_color="transparent",
                     font=ctk.CTkFont(T["font_family"], 9), wraplength=580
                     ).pack(pady=(0,8))

    def _refresh_theme_controls(self):
        for w in self._tab_theme.winfo_children(): w.destroy()
        self._build_theme_tab()

    # -----------------------------------------------------------------------
    # Help tab
    # -----------------------------------------------------------------------

    def _build_help_tab(self):
        """[NEW] Help tab -- documents every template token and general usage tips."""
        tab = self._tab_help
        sf = _scrollframe(tab)
        sf.pack(fill="both", expand=True, padx=0, pady=0)

        def _heading(text):
            lbl = ctk.CTkLabel(sf, text=text, text_color=ACCENT(),
                               fg_color="transparent",
                               font=ctk.CTkFont(T["font_family"], T["font_size"] + 3, "bold"),
                               anchor="w")
            lbl.pack(fill="x", padx=18, pady=(18, 4))
            _reg(lbl, "label_accent")
            # divider under heading
            _separator(sf).pack(fill="x", padx=18, pady=(0, 6))

        def _subheading(text):
            lbl = ctk.CTkLabel(sf, text=text, text_color=ACCENT2(),
                               fg_color="transparent",
                               font=ctk.CTkFont(T["font_family"], T["font_size"] + 1, "bold"),
                               anchor="w")
            lbl.pack(fill="x", padx=18, pady=(10, 2))
            _reg(lbl, "label_accent")

        def _row(token, description, example_in="", example_out=""):
            """Render one token row: token pill | description | example."""
            row = ctk.CTkFrame(sf, fg_color=BG2(), corner_radius=8)
            row.pack(fill="x", padx=18, pady=3)
            _reg(row, "frame2")

            # token pill (monospaced, accent-coloured)
            pill = ctk.CTkLabel(row, text=token,
                                text_color=ACCENT2(), fg_color=BG3(),
                                font=ctk.CTkFont(T["mono_family"], T["mono_size"], "bold"),
                                corner_radius=6, anchor="w", width=220)
            pill.grid(row=0, column=0, padx=(10, 6), pady=8, sticky="w")
            _reg(pill, "label_accent")

            # description
            desc_lbl = ctk.CTkLabel(row, text=description, text_color=FG(),
                                    fg_color="transparent", font=_font(), anchor="w",
                                    wraplength=340, justify="left")
            desc_lbl.grid(row=0, column=1, padx=6, pady=8, sticky="w")
            _reg(desc_lbl, "label")

            # example (if provided)
            if example_in:
                ex_text = f"{example_in}  →  {example_out}" if example_out else example_in
                ex_lbl = ctk.CTkLabel(row, text=ex_text, text_color=FG2(),
                                      fg_color="transparent",
                                      font=ctk.CTkFont(T["mono_family"], T["mono_size"]-1),
                                      anchor="w")
                ex_lbl.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 8), sticky="w")
                _reg(ex_lbl, "label2")

        def _note(text):
            lbl = ctk.CTkLabel(sf, text=text, text_color=FG2(),
                               fg_color="transparent", font=_font(),
                               anchor="w", wraplength=720, justify="left")
            lbl.pack(fill="x", padx=24, pady=(2, 4))
            _reg(lbl, "label2")

        # ── Section: Random Text Tokens ─────────────────────────────────────
        _heading("🎲  Random Text Tokens")
        _note("Use these tokens in any text field. Uncheck 'Random each submission' to enable the field, then type your template.")
        _note("Tokens are replaced per submission — each response gets a fresh random value.")

        _subheading("Letters only  (RND)")
        _row("<*RND_N*>",   "N random lowercase letters",  "<*RND_4*>",   "xqmz")
        _row("<*LRND_N*>",  "Same as RND — explicit lowercase", "<*LRND_4*>", "bkjp")
        _row("<*CRND_N*>",  "N random UPPERCASE letters",  "<*CRND_4*>",  "XQMZ")

        _subheading("Alphanumeric  (ANRND — letters + digits)")
        _row("<*ANRND_N*>",  "N random mixed-case letters + digits",  "<*ANRND_5*>",  "aB3xQ")
        _row("<*LANRND_N*>", "N random lowercase letters + digits",   "<*LANRND_5*>", "ab3xq")
        _row("<*CANRND_N*>", "N random UPPERCASE letters + digits",   "<*CANRND_5*>", "AB3XQ")

        _subheading("Full printable ASCII  (FRND — letters + digits + symbols)")
        _row("<*FRND_N*>",   "N random printable ASCII chars (any case)",  "<*FRND_5*>",  "aB3!k")
        _row("<*LFRND_N*>",  "Same but letters forced lowercase",           "<*LFRND_5*>", "ab3!k")
        _row("<*CFRND_N*>",  "Same but letters forced UPPERCASE",           "<*CFRND_5*>", "AB3!K")

        _note("N can be 1–256.  You can use multiple tokens in one field: test<*CRND_3*>_<*RND_2*>  →  testABC_xq")

        # [NEW] Range syntax documentation
        _subheading("Range syntax  (works on ALL token types)")
        _row("<*RND_N-M*>",   "Random LENGTH between N and M (inclusive)",  "<*RND_4-8*>",    "xqmzk  (5 chars)")
        _row("<*ANRND_N-M*>", "Same idea for alphanumeric",                  "<*ANRND_2-5*>",  "aB3")
        _row("<*FRND_N-M*>",  "Same idea for full ASCII",                    "<*FRND_3-10*>",  "aB3!kxq")
        _note("• N-M means a random INTEGER length chosen between N and M each submission.")
        _note("• If M < N the values are swapped automatically.  e.g. <*RND_6-4*> = same as <*RND_4-6*>")
        _note("• Works with all prefixes: <*CRND_4-8*>, <*LANRND_2-6*>, <*LURND_5-10*> etc.")

        _subheading("Username  (URND — a-z A-Z 0-9 _)")
        _row("<*URND_N*>",   "N username chars (mixed case + digits + _)",   "<*URND_8*>",   "cool_K3y")
        _row("<*LURND_N*>",  "Same but letters forced lowercase",             "<*LURND_8*>",  "cool_k3y")
        _row("<*CURND_N*>",  "Same but letters forced UPPERCASE",             "<*CURND_8*>",  "COOL_K3Y")

        _subheading("URL-safe  (URLRND — a-z A-Z 0-9 _ -)") # [NEW]
        _row("<*URLRND_N*>",  "N URL-safe chars (mixed case + digits + _ -)",  "<*URLRND_8*>",  "aB3_x-Qr")
        _row("<*LURLRND_N*>", "Same but letters forced lowercase",              "<*LURLRND_8*>", "ab3_x-qr")
        _row("<*CURLRND_N*>", "Same but letters forced UPPERCASE",              "<*CURLRND_8*>", "AB3_X-QR")
        _note("• Google Drive link: https://drive.google.com/file/d/1<*URLRND_34*>/view?usp=sharing")

        _subheading("Digits only  (NRND)")
        _row("<*NRND_N*>",   "N random digits 0–9",   "<*NRND_6*>",   "384729")
        _note("• Useful for phone numbers, IDs, codes:  +1<*NRND_3*>-<*NRND_3*>-<*NRND_4*>")

        _subheading("Symbols only  (SRND)")
        _row("<*SRND_N*>",   "N random punctuation / symbol chars",   "<*SRND_4*>",   "!@#$")
        _note("• Symbols pool: all printable non-alphanumeric ASCII  (! \" # $ % & ' ( ) * + , - . / : ; < = > ? @ [ \\ ] ^ _ ` { | } ~)")

        _subheading("Word  (WRND — letters only, lowercase)")
        _row("<*WRND_N*>",   "N random lowercase letters — alias for RND, explicit 'word' intent",   "<*WRND_5*>",   "plant")

        # ── Section: List Files ─────────────────────────────────────────────
        _heading("📄  List File Token")
        _row("<*filename.txt*>", "Pick a random entry from filename.txt\nin the same folder as ui.py",
             "<*colors.txt*>", "PURPLE")
        _note("• The .txt file must be in the same folder as ui.py.")
        _note("• Entries are separated by blank lines (one or more empty lines between each entry).")
        _note("• Example colors.txt content:    ORANGE\\n\\nPURPLE\\n\\nGREEN")
        _note("• Using a non-.txt extension (e.g. <*data.csv*>) outputs:  invalid file type")
        _note("• You can combine with other tokens:  <*names.txt*> scored <*RND_2*><*CRND_1*>!")

        # ── Section: Question Reference ──────────────────────────────────────
        _heading("🔗  Question Reference Token  (QSTN)")
        _row("<*QSTN_N*>", "Insert the resolved value of question N\n(1-based index) in the same submission",
             "<*QSTN_1*>", "(value of Q1)")
        _note("• Questions are numbered 1, 2, 3… in the order they appear in the form.")
        _note("• Works with any token in earlier questions — the already-expanded value is inserted.")
        _note("• Example:  Q1 answer = <*RND_4*>  (expands to e.g. 'xqmz')")
        _note("            Q3 answer = <*QSTN_1*>@gmail.com  →  xqmz@gmail.com")
        _note("• If you reference a question that hasn't been answered yet, the token is left as-is.")

        # ── Section: Alert Audio ─────────────────────────────────────────────
        _heading("🔊  Alert Sound File")
        _note("Drop an audio file named  alert.<ext>  in the same folder as ui.py.")
        _note("Supported formats:  mp3  wav  ogg  mp4  aac  flac  m4a  oga  opus")
        _note("When the form-shutdown overlay fires, this file plays automatically.")
        _note("If no alert file is found, the system bell is used as fallback.")
        _note("Example filename:  alert.mp3   or   alert.wav")

        # ── Section: Sleep Prevention ────────────────────────────────────────
        _heading("💤  Sleep & Power")
        _note("Toggle 'Prevent system sleep' and/or 'Prevent screen sleep' in the Customise tab.")
        _note("This keeps the computer / display awake during long unattended runs.")
        _note("Windows: uses SetThreadExecutionState.  macOS: uses caffeinate.  Linux: uses systemd-inhibit.")
        _note("Sleep prevention is automatically released when the app is closed.")

        # ── Section: Quick reference ────────────────────────────────────────
        _heading("📋  Quick Reference")

        # draw a compact summary table using a monospaced textbox
        summary = (
            "  Token              Case      Characters\n"
            "  ─────────────────────────────────────────────────────────────\n"
            "  <*RND_N*>          lower     a-z\n"
            "  <*LRND_N*>         lower     a-z  (same as RND)\n"
            "  <*CRND_N*>         UPPER     A-Z\n"
            "  <*ANRND_N*>        mixed     a-z A-Z 0-9\n"
            "  <*LANRND_N*>       lower     a-z 0-9\n"
            "  <*CANRND_N*>       UPPER     A-Z 0-9\n"
            "  <*FRND_N*>         mixed     a-z A-Z 0-9 + symbols\n"
            "  <*LFRND_N*>        lower     a-z 0-9 + symbols\n"
            "  <*CFRND_N*>        UPPER     A-Z 0-9 + symbols\n"
            "  <*filename.txt*>   —         random line from file\n"
            "  ─────────────────────────────────────────────────────────────\n"
            "  N = number of characters (1–64)\n"
            "  C prefix = UPPERCASE only     L prefix = lowercase only\n"
            "  No prefix on RND/LRND = lowercase    No prefix on ANRND/FRND = mixed\n"
        )
        tb = _textbox(sf, height=280)
        tb.pack(fill="x", padx=18, pady=(4, 16))
        tb.configure(state="normal")
        tb.insert("end", summary)
        tb.configure(state="disabled")

    # -----------------------------------------------------------------------
    # Scan
    # -----------------------------------------------------------------------

    def _scan(self):
        url = self._url_var.get().strip()
        # [NEW] Validate URL before opening a browser -- catches paste mistakes early
        err = _validate_form_url(url)
        if err:
            messagebox.showwarning("Invalid URL", err)
            return
        self._scan_status.configure(text="Scanning... (browser window will open)")
        self.root.update()

        def _do_scan():
            try:
                fa, pages, cookies, is_mp, fbzx = ff.scan_form(url)
                self.form_action = fa; self.pages = pages
                self.cookies = cookies; self.is_multipage = is_mp; self.seed_fbzx = fbzx
                all_q = [q for page in pages for q in page]
                self.root.after(0, lambda: self._scan_done(all_q))
            except ff.ScanAbortedError as e:
                # [FIX issue-3] Show the actual reason instead of vague "Scan aborted."
                reason = str(e)
                self.root.after(0, lambda r=reason: (
                    self._scan_status.configure(text=f"Scan aborted: {r[:60]}..."),
                    messagebox.showwarning("Scan Aborted", r)
                ))
            except SystemExit:
                # Kept as fallback in case of sys.exit anywhere else in the call chain
                self.root.after(0, lambda: self._scan_status.configure(text="Scan aborted."))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Scan failed", str(e)))

        threading.Thread(target=_do_scan, daemon=True).start()

    def _scan_done(self, questions):
        n = len(questions); pg = len(self.pages)
        self._scan_status.configure(
            text=f"✓  {n} question(s) across {pg} page(s). See Questions tab.")
        self._populate_questions(questions)
        self.nb.set("Questions")

    # [NEW] Config save/load -- form_filler.py had full save_config/load_config
    # functions but they were never called from the UI.
    def _save_config(self):
        if not self.form_action:
            messagebox.showwarning("Nothing to save", "Scan a form first."); return
        planned = self._collect_planned()
        if not planned:
            messagebox.showwarning("Nothing to save", "No answers collected yet."); return
        url     = self._url_var.get().strip()
        mode    = self._mode_var.get()
        try:
            times_raw = self._times_var.get().strip().lower()
            times = float("inf") if times_raw == "inf" else int(times_raw)
        except ValueError:
            times = 1
        workers = self._workers_var.get()
        lo      = float(self._delay_lo.get() or "0")
        hi      = float(self._delay_hi.get() or "0")
        ff.save_config(url, mode, times, workers, (lo, hi), planned)
        messagebox.showinfo("Saved", f"Config saved to:\n{ff.CONFIG_FILE}")

    def _load_config(self):
        cfg = ff.load_config()
        if not cfg:
            messagebox.showwarning("No config", f"No saved config found at:\n{ff.CONFIG_FILE}"); return
        self._url_var.set(cfg.get("url", ""))
        self._mode_var.set(cfg.get("mode", "random"))
        times = cfg.get("times", 1)
        self._times_var.set("inf" if times == float("inf") else str(int(times)))
        self._workers_var.set(cfg.get("workers", 1))
        lo, hi = cfg.get("delay", (0.0, 0.0))
        self._delay_lo.set(str(lo)); self._delay_hi.set(str(hi))
        self._log(f"[Config] Loaded config for: {cfg.get('url','')}")
        messagebox.showinfo("Loaded",
            "Config loaded.\nClick Scan Form to re-scan the form, then answers will be auto-filled.")

    # -----------------------------------------------------------------------
    # Run
    # -----------------------------------------------------------------------

    def _parse_run_settings(self):
        times_raw = self._times_var.get().strip().lower()
        times = float("inf") if times_raw == "inf" else int(times_raw)
        if isinstance(times, int) and times < 1: raise ValueError("Submissions must be >= 1 or 'inf'.")
        workers = self._workers_var.get()
        if workers < 1: raise ValueError("Workers must be >= 1.")
        lo = float(self._delay_lo.get() or "0")
        hi = float(self._delay_hi.get() or "0")
        if lo < 0 or hi < lo: raise ValueError("Delay: lo must be >= 0 and hi must be >= lo.")
        instances = self._instances_var.get()
        if instances < 1: raise ValueError("Instances must be >= 1.")
        return times, workers, (lo, hi), self._backend_var.get(), self._perf_var.get(), instances

    def _collect_planned(self):
        return [r for qw in self.q_widgets if (r := qw.resolve()) is not None]

    def _start_run(self):
        if not self.form_action:
            messagebox.showwarning("Not scanned", "Please scan a form first.")
            self.nb.set("Setup"); return
        if not self.q_widgets:
            messagebox.showwarning("No questions", "No questions to answer."); return
        try:
            times, workers, delay, backend, perf, instances = self._parse_run_settings()
        except ValueError as e:
            messagebox.showerror("Settings error", str(e)); return
        planned = self._collect_planned()
        if not planned:
            messagebox.showwarning("No answers", "No answers collected."); return
        if backend == "chromium" and not ff.SELENIUM_AVAILABLE:
            messagebox.showerror("Selenium not installed",
                                 "Chromium backend requires selenium and webdriver-manager.\n\n"
                                 "Run:  pip install selenium webdriver-manager"); return

        for sv in (self._stat_submitted, self._stat_success, self._stat_failed,
                   self._stat_rate, self._stat_retries):
            sv.set("0")
        self._progress.set(0)
        inf = times == float("inf")
        # [CTK] CTkProgressBar has no indeterminate mode; just leave at 0 for ∞ runs
        self._progress_label.configure(text="Running...")
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._stop_flag.clear()

        mode = self._mode_var.get(); url = self._url_var.get().strip()
        start = time.time(); target = None if inf else int(times)

        def update_ui(sub, suc, ret=0):
            self._stat_submitted.set(str(sub)); self._stat_success.set(str(suc))
            self._stat_failed.set(str(sub - suc))
            # [NEW] show retries live
            if ret > 0: self._stat_retries.set(str(ret))
            elapsed = time.time() - start
            rate = (sub / elapsed * 60) if elapsed > 0 else 0
            self._stat_rate.set(f"{rate:.1f}")
            if not inf and target:
                pct = min(1.0, sub / target)
                self._progress.set(pct)
                self._progress_label.configure(text=f"{sub} / {target}  ({pct*100:.0f}%)")
            else:
                self._progress_label.configure(text=f"{sub} submitted")

        def _run_http():
            fbzx = self.seed_fbzx or str(random.randint(-9007199254740992, 9007199254740992))
            self._log(f"[HTTP] Starting: {times if not inf else '∞'} submission(s), {workers} worker(s)")
            _orig = ff.print_stats
            # [NEW] Monkey-patch print_stats to also update the Retries stat box
            def _ui_stats(wrk, sub, suc, total, st, ret=0):
                _orig(wrk, sub, suc, total, st, ret)
                self.root.after(0, lambda s=sub, sc=suc, r=ret: update_ui(s, sc, r))
            ff.print_stats = _ui_stats
            # [NEW] Register shutdown callback so the UI reacts when form closes
            ff.set_form_shutdown_callback(lambda: self.root.after(0, self._on_form_shutdown))
            # [NEW] Register answer tracking callback for Analytics tab
            ff.set_answer_tracked_callback(self._on_answers_resolved)
            total_sub, total_ok, peak, retries = 0, 0, 0.0, 0
            try:
                if not self._stop_flag.is_set():
                    total_sub, total_ok, peak, retries = ff.submit_all(
                        self.form_action, self.pages, planned,
                        url, self.cookies, times, workers, mode,
                        self.is_multipage, fbzx, delay,
                        # [NEW] Pass validation policies from theme settings into the HTTP engine
                        val_overflow=T.get("val_on_length_overflow", "truncate"),
                        val_invalid_choice=T.get("val_on_invalid_choice", "skip_choice"))
            except Exception as e:
                self._log(f"[HTTP] Error: {e}")
            finally:
                ff.print_stats = _orig
                ff.set_form_shutdown_callback(None)
                ff.set_answer_tracked_callback(None)  # [NEW] unregister analytics hook
            self.root.after(0, lambda: self._run_done(total_sub, total_ok, peak, "http", retries))

        def _run_chromium():
            headless = perf in ("headless", "turbo")
            self._log(f"[Chromium/{perf}] Starting: {times if not inf else '∞'} submission(s), {instances} instance(s)")
            ff.chrom_total_submitted = 0; ff.chrom_start_time = time.time()
            # [NEW] Register shutdown callback for Chromium backend
            ff.set_form_shutdown_callback(lambda: self.root.after(0, self._on_form_shutdown))
            # [NEW] Register answer tracking callback for Analytics tab (Chromium backend)
            ff.set_answer_tracked_callback(self._on_answers_resolved)
            if inf:
                per_instance = per_instance_rem = None
            else:
                base = target // instances; remainder = target % instances
                per_instance = base; per_instance_rem = base + remainder
            window_rects = [(0,0,0,0)]*instances if headless else \
                           (ff.get_monitor_layout(instances) if hasattr(ff, "get_monitor_layout")
                            else [(0,0,1280,800)]*instances)
            _orig_cs = ff.chrom_print_stats
            def _ui_chrom(num_inst, iters, inf_flag):
                _orig_cs(num_inst, iters, inf_flag)
                with ff._chrom_stats_lock:
                    sub = ff.chrom_total_submitted
                self.root.after(0, lambda s=sub: update_ui(s, s))
            ff.chrom_print_stats = _ui_chrom
            chrom_planned = _http_planned_to_chrom_actions(planned)
            threads = []
            for i in range(instances):
                if self._stop_flag.is_set(): break
                iters = None if inf else (per_instance_rem if i == 0 else per_instance)
                t = threading.Thread(target=ff.chrom_run_instance,
                                     args=(i+1, url, chrom_planned, iters, inf,
                                           instances, window_rects[i], headless, perf),
                                     daemon=True)
                threads.append(t); t.start(); time.sleep(0.5)
            for t in threads: t.join()
            ff.chrom_print_stats = _orig_cs
            ff.set_form_shutdown_callback(None)
            ff.set_answer_tracked_callback(None)  # [NEW] unregister analytics hook
            total_sub = ff.chrom_total_submitted
            self.root.after(0, lambda: self._run_done(total_sub, total_sub, 0.0, "chromium", 0))

        self._run_thread = threading.Thread(
            target=_run_http if backend == "http" else _run_chromium, daemon=True)
        self._run_thread.start()

    def _stop_run(self):
        self._stop_flag.set()
        # Guard: _log_box and _progress_label may not be ready if nothing has run yet
        try: self._log("Stop requested...")
        except Exception: pass
        try: self._progress_label.configure(text="Stopping...")
        except Exception: pass
        if self._backend_var.get() == "chromium":
            try:
                ff.kill_all_drivers()
                try: self._log("Chromium: all browser windows closed.")
                except Exception: pass
            except Exception as e:
                try: self._log(f"Chromium stop error: {e}")
                except Exception: pass

    def _run_done(self, total, ok, peak, backend="http", retries=0):
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._stat_submitted.set(str(total)); self._stat_success.set(str(ok))
        self._stat_failed.set(str(total - ok))
        # [NEW] Update retries display on completion
        self._stat_retries.set(str(retries) if retries else "0")
        self._progress.set(1.0)
        if backend == "chromium":
            self._progress_label.configure(text=f"Done!  {total} submitted  [chromium]")
            self._log(f"[Chromium] Batch complete: {total} submitted")
        else:
            pk = f"  Peak: {peak:.1f}/min" if peak else ""
            ret_s = f"  Retries: {retries}" if retries else ""
            self._progress_label.configure(
                text=f"Done!  {ok}/{total} successful.{pk}{ret_s}  [http]")
            self._log(f"[HTTP] Batch complete: {ok}/{total} OK, peak {peak:.1f}/min"
                      + (f", {retries} retries" if retries else ""))
        # [NEW] Record this run in session history and export to results file
        self._record_session(total, ok, peak, backend, retries)

    def _record_session(self, total, ok, peak, backend, retries):
        """[NEW] Add run to in-memory history and append to the JSONL results file."""
        record = {
            "time":     datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "url":      self._url_var.get().strip(),
            "backend":  backend,
            "mode":     self._mode_var.get(),
            "total":    total,
            "success":  ok,
            "failed":   total - ok,
            "peak_rpm": round(peak, 1),
            "retries":  retries,
        }
        self._session_history.append(record)
        self._refresh_history_tab()
        # Also write to disk via form_filler's export function
        elapsed = 0.0  # approximate -- we don't track start time here
        ff.export_session_result(total, ok, total - ok, elapsed, 0, peak, retries,
                                  self._workers_var.get(),
                                  url=record["url"], mode=record["mode"],
                                  extra={"backend": backend})

    def _save_run_log(self):
        """[NEW] Save the run log textbox to a .txt file chosen by the user."""
        text = self._log_box.get("0.0", "end").strip()
        if not text:
            messagebox.showinfo("Empty", "Log is empty."); return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")],
            title="Save Run Log")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                messagebox.showinfo("Saved", f"Log saved to:\n{path}")
            except Exception as e:
                messagebox.showerror("Save failed", str(e))


# ===========================================================================
# Entry point
# ===========================================================================

def main():
    ctk.set_appearance_mode("dark")   # [CTK] suppress system theme override
    ctk.set_default_color_theme("blue")  # base; our T dict overrides everything
    root = ctk.CTk()
    app  = FormFillerApp(root)

    # [NEW] Release sleep prevention when the window is closed
    def _on_close():
        global _sleep_proc
        try:
            T["prevent_system_sleep"] = False
            T["prevent_screen_sleep"] = False
            _apply_sleep_prevention()
        except Exception: pass
        if _sleep_proc:
            try: _sleep_proc.terminate()
            except Exception: pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()

if __name__ == "__main__":
    main()