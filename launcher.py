"""
launcher.py  --  Form Filler Launcher
Drop this in the same folder as form_filler.py and ui.py, then run:

    python launcher.py

It will ask whether you want the GUI (ui.py) or the terminal (form_filler.py),
then hand off to the right script.  Everything else stays in those two files.
"""

import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

UI_SCRIPT  = os.path.join(HERE, "ui.py")
CLI_SCRIPT = os.path.join(HERE, "form_filler.py")


def _check_files():
    missing = [f for f in (UI_SCRIPT, CLI_SCRIPT) if not os.path.isfile(f)]
    if missing:
        print("ERROR: the following files are missing from this folder:")
        for f in missing:
            print(f"  {f}")
        print("\nMake sure launcher.py, ui.py, and form_filler.py are all in the same folder.")
        input("\nPress Enter to exit...")
        sys.exit(1)


def _ask(prompt, valid_map):
    """Ask a question, return the canonical answer from valid_map."""
    while True:
        raw = input(prompt).strip().lower()
        if raw in valid_map:
            return valid_map[raw]
        print(f"  Please enter one of: {', '.join(valid_map)}")


def main():
    print("=" * 50)
    print("        FORM FILLER  --  LAUNCHER")
    print("=" * 50)
    print()

    _check_files()

    # ── Choose UI or terminal ────────────────────────────────────────────────
    choice = _ask(
        "  Run as (u)i / (t)erminal? [u/t]: ",
        {"u": "ui", "ui": "ui", "t": "terminal", "terminal": "terminal"}
    )
    print()

    if choice == "ui":
        print("  Launching UI...")
        import platform
        if platform.system() == "Windows":
            # [FIX] Use run() with a short timeout instead of fire-and-forget Popen.
            # The old CREATE_NO_WINDOW Popen silently swallowed crash output -- if
            # ui.py errored on import (e.g. missing package) there was no feedback.
            # We wait up to 3s; if it's still alive after that it launched fine.
            import ctypes
            proc = subprocess.Popen(
                [sys.executable, UI_SCRIPT],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                creationflags=0x08000000,   # CREATE_NO_WINDOW
            )
            try:
                stdout, stderr = proc.communicate(timeout=3)
                # If communicate() returned within 3s, the process already exited -- it crashed.
                print("\n  ERROR: UI exited immediately. Traceback:")
                print("-" * 50)
                if stderr: print(stderr.decode(errors="replace"))
                if stdout: print(stdout.decode(errors="replace"))
                print("-" * 50)
                input("\nPress Enter to exit...")
            except subprocess.TimeoutExpired:
                # Still running after 3s -- good, it launched successfully.
                pass
        else:
            subprocess.Popen(
                [sys.executable, UI_SCRIPT],
                start_new_session=True,     # detach from terminal on Linux/macOS
            )
        return

    # ── Terminal mode: ask backend ───────────────────────────────────────────
    backend = _ask(
        "  Backend -- (h)ttp / (c)hromium? [h/c]: ",
        {"h": "http", "http": "http", "c": "chromium", "chromium": "chromium"}
    )
    print()

    if backend == "http":
        # form_filler.py terminal flow handles everything
        print("  Launching terminal (HTTP backend)...")
        subprocess.run([sys.executable, CLI_SCRIPT, "--backend", "http"])
        return

    # ── Chromium terminal: ask performance mode ──────────────────────────────
    print("  Chromium performance modes:")
    print("    normal   -- visible browser windows, easiest to watch and debug")
    print("    headless -- invisible (background) browsers, faster, no GUI overhead")
    print("    turbo    -- headless + all Chrome optimisations disabled (images off,")
    print("                extensions off, background networking off), fastest")
    print()

    perf = _ask(
        "  Perf mode -- (n)ormal / (h)eadless / (t)urbo? [n/h/t]: ",
        {
            "n": "normal",   "normal":   "normal",
            "h": "headless", "headless": "headless",
            "t": "turbo",    "turbo":    "turbo",
        }
    )
    print()

    print(f"  Launching terminal (Chromium / {perf})...")
    subprocess.run([sys.executable, CLI_SCRIPT, "--backend", "chromium", "--perf", perf])


if __name__ == "__main__":
    main()
