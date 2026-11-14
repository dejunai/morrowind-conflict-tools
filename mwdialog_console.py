"""mwdialog_console.py - talking to the person at the keyboard: questions with a default, the window title,
and the dated fix log.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_text as MT  # noqa: E402
from mwdialog_backup import (  # noqa: E402
    BACKUP_DIR, game_dir_of)
print = MT.printer()  # noqa: A001


def console_interactive():
    """(True, "") when questions can be answered here: stdin is a console - or, on Windows, it isn't (a
    launcher or wrapper redirected it) but the output is on screen and the console's input (CONIN$) can be
    opened. Else (False, why not)."""
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            return True, ""
    except (AttributeError, ValueError, OSError):
        pass
    try:
        out_tty = sys.stdout.isatty()
    except (AttributeError, ValueError, OSError):
        out_tty = False
    if os.name == "nt" and out_tty:
        try:
            with open("CONIN$", "r"):
                return True, ""
        except OSError:
            pass
    return False, ("the input isn't a console (redirected, or run by another program)" if out_tty else
                   "the output isn't on screen (redirected to a file or a pipe)")


def ask(prompt):
    """One answer from the console (lowercased, stripped); None when there is no answer to read. Output is
    flushed first so the prompt and everything before it is on screen."""
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except (AttributeError, ValueError, OSError):
        pass
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            return input(prompt).strip().lower()
        if os.name == "nt":                          # stdin redirected: read the console directly
            sys.stdout.write(prompt)
            sys.stdout.flush()
            with open("CONIN$", "r") as con:
                return con.readline().strip().lower()
        return input(prompt).strip().lower()
    except (EOFError, OSError, KeyboardInterrupt):
        print()
        return None


def fix_log_line(args, game_dir, text):
    """One dated line in the fix log (mwdialog_fixes.log next to the game, unless --fix-log says otherwise)."""
    try:
        with MT.open_log(os.path.join(game_dir, getattr(args, "fix_log", "") or "mwdialog_fixes.log"), "a",
                  encoding="utf-8") as lf:
            lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {text}\n")
    except OSError:
        pass


def set_title(text):
    """The console window's title bar (Windows), so you can see what a long run is doing."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(text)
    except (ImportError, AttributeError, OSError):
        pass


FIX_LOG_CAP = 20 * 1024 * 1024

FIX_LOG_ARCHIVE = "fixes.archive.txt"            # in mwdialog_backup\\


def cap_fix_log(args):
    """Keep the fix log at 20 MB or less: its oldest runs (whole "==== date ====" sections) are moved, in
    order, to the end of mwdialog_backup\\fixes.archive.txt."""
    if args is None:
        return
    for path in {os.path.abspath(getattr(args, "fix_log", "") or "mwdialog_fixes.log"),
                 os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(args.data_dir)),
                                              getattr(args, "fix_log", "") or "mwdialog_fixes.log"))}:
        if not os.path.isfile(path) or os.path.getsize(path) <= FIX_LOG_CAP:
            continue
        with open(path, "rb") as f:
            data = f.read()
        cut = len(data) - FIX_LOG_CAP
        k = data.find(b"\n==== ", cut)              # start of the first whole run within the last 20 MB
        k = k + 1 if k >= 0 else data.find(b"\n", cut) + 1
        if k <= 0:
            continue
        arch = os.path.join(game_dir_of(path), BACKUP_DIR, FIX_LOG_ARCHIVE)
        os.makedirs(os.path.dirname(arch), exist_ok=True)
        with open(arch, "ab") as f:
            f.write(data[:k])
        with open(path + ".tmp", "wb") as f:
            f.write(data[k:])
        os.replace(path + ".tmp", path)
        print(f"Fix log trimmed to {(len(data) - k) / 1048576:.1f} MB; {k / 1048576:.1f} MB of older runs moved to "
              f"{BACKUP_DIR}\\{FIX_LOG_ARCHIVE}")
