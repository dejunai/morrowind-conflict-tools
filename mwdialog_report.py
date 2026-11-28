r"""mwdialog_report.py - vortex_tidy.py --pack-report: one scrubbed archive of the tools' logs for a bug report.

What goes in (and nothing else): MWSE.log (the game folder), everything under Data Files\MWSE\logs\ (the logs
luafix's shim redirects there) and <game>\conflict-tools\generated\ (the tools' own records and logs). A source that
is missing is skipped and noted in the summary. Every path comes from the usual game / staging / downloads
detection (mwdialog_paths); nothing is hardcoded.

Read-only on the game: files are COPIED into a temporary work folder (the system temp folder, removed afterwards)
and scrubbed there; the originals are never changed, moved or deleted. Reading Data Files\MWSE\logs is the one
documented read this switch does there (mwdialog_staged.PACK_REPORT_READS); nothing is written to Data Files.

Scrub (copies only): the user's absolute paths become <MORROWIND> (the game folder), <STAGING> (Vortex's or
MWManager's staging folders), <DOWNLOADS> (the downloads folder) and <USERPROFILE> (the Windows profile), the
longest match first (a staging folder inside the profile is <STAGING>), with either slash style, doubled
backslashes (as JSON writes them) and any letter case. The Windows user name is replaced by <USERNAME> wherever it
appears as a whole token, in any case.

Non-text files (an SQLite cache, anything with a NUL byte or a binary extension, UTF-16 text) are EXCLUDED, not
scrubbed: a binary can hold the same names in forms no text scrub can promise to find. Links, unreadable files and
files over MAX_FILE_BYTES are excluded too. The summary lists every exclusion by name, with the reason and no
contents. scrub-summary.txt holds only the number of replacements per file and the skipped / excluded lists.

The archive is a .zip made with the bundled 7-Zip (find_7z): testers can open a .zip with Windows alone, and
GitHub and Discord accept it, while a .7z needs 7-Zip. It goes in <game>\conflict-tools\reports\ (created only
when there is an archive to put in it) as conflict-tools-report-YYYYMMDD-HHMMSS.zip. Rule by dej (dejunai).

Python 3.9+.
"""
import getpass
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import mwdialog_paths as MP
import mwdialog_version

ARCHIVE_PREFIX = "conflict-tools-report-"
ARCHIVE_EXT = ".zip"
SUMMARY_NAME = "scrub-summary.txt"
MAX_FILE_BYTES = 128 * 1024 * 1024
BINARY_EXT = {".sqlite", ".sqlite3", ".db", ".bin", ".dll", ".exe", ".esp", ".esm", ".omwaddon", ".bsa", ".nif",
              ".kf", ".dds", ".tga", ".png", ".jpg", ".jpeg", ".bmp", ".zip", ".7z", ".rar", ".gz", ".dmp",
              ".mp3", ".wav", ".ogg", ".mpg", ".bik", ".pyc"}
PLACEHOLDERS = ("<MORROWIND>", "<STAGING>", "<DOWNLOADS>", "<USERPROFILE>")
USERNAME_PLACEHOLDER = "<USERNAME>"


class ReportError(Exception):
    """The report could not be made; str() is the message for the user."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------------------------------- scrubbing
def _path_regex(path):
    """A regex source matching `path` (absolute) in any letter case, with / or \\ or doubled \\\\ between the
    parts, and an optional \\\\?\\ prefix. Not followed by a name character, so a sibling folder isn't cut."""
    p = os.path.abspath(path).replace("/", "\\").rstrip("\\")
    m = re.match(r"^(\\\\\?\\)?([A-Za-z]:|\\\\)?(.*)$", p)
    drive, rest = m.group(2) or "", m.group(3)
    parts = [x for x in rest.split("\\") if x]
    if not parts and not drive:
        return None
    sep = r"[\\/]+"
    if drive == "\\\\":                                   # UNC: \\server\share\...
        head = r"[\\/]{2}"
        body = sep.join(re.escape(x) for x in parts)
    elif drive:
        head = re.escape(drive)
        body = "".join(sep + re.escape(x) for x in parts)
    else:                                                 # a POSIX root
        head = ""
        body = "".join(sep + re.escape(x) for x in parts)
    return r"(?:[\\/]{2}\?[\\/])?" + head + body + r"(?![\w.-])"


def identity():
    """(user profile folders, Windows user names) of whoever runs this, from the environment."""
    profiles, names = [], []
    for p in (os.environ.get("USERPROFILE"), os.path.expanduser("~")):
        if p and p != "~" and os.path.normcase(p) not in [os.path.normcase(x) for x in profiles]:
            profiles.append(p)
    cands = [os.environ.get("USERNAME")]
    try:
        cands.append(getpass.getuser())
    except Exception:
        pass
    cands += [os.path.basename(p.rstrip("\\/")) for p in profiles]
    for n in cands:
        if n and n.lower() not in [x.lower() for x in names]:
            names.append(n)
    return profiles, names


class Scrubber:
    """scrub(text) -> (text, number of replacements). Built from the paths of THIS run."""

    def __init__(self, game, staging=(), downloads=(), profiles=(), names=()):
        bases = []
        for tag, paths in (("<MORROWIND>", [game]), ("<STAGING>", staging), ("<DOWNLOADS>", downloads),
                           ("<USERPROFILE>", profiles)):
            for p in paths:
                if p:
                    rx = _path_regex(p)
                    if rx:
                        bases.append((len(os.path.abspath(p)), tag, rx))
        bases.sort(key=lambda b: -b[0])                   # longest match first
        self.tags = []
        parts = []
        for i, (_n, tag, rx) in enumerate(bases):
            parts.append(f"(?P<p{i}>{rx})")
            self.tags.append(tag)
        self.paths = re.compile("|".join(parts), re.I) if parts else None
        toks = sorted({n for n in names if n}, key=lambda n: -len(n))
        self.user = re.compile(r"(?<![A-Za-z0-9_])(?:" + "|".join(re.escape(n) for n in toks) +
                               r")(?![A-Za-z0-9_])", re.I) if toks else None

    def scrub(self, text):
        n = 0
        if self.paths:
            def tag(m):
                return self.tags[int(m.lastgroup[1:])]
            text, k = self.paths.subn(tag, text)
            n += k
        if self.user:
            text, k = self.user.subn(USERNAME_PLACEHOLDER, text)
            n += k
        return text, n

    def scrub_bytes(self, data):
        """(scrubbed bytes, count) for a text file: UTF-8 (BOM kept) when it decodes, else byte-for-byte Latin-1."""
        try:
            text, enc = data.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            text, enc = data.decode("latin-1"), "latin-1"
        text, n = self.scrub(text)
        return (text.encode(enc) if n else data), n


# --------------------------------------------------------------------------------------------------- sources
def tools_dir(game):
    return os.path.join(game, "conflict-tools")


def sources(game):
    """[(archive folder or file name, label for the summary, absolute path, is_dir)]: the only things included."""
    return [("MWSE.log", "MWSE.log", os.path.join(game, "MWSE.log"), False),
            ("MWSE-logs", "Data Files\\MWSE\\logs\\", os.path.join(game, "Data Files", "MWSE", "logs"), True),
            ("generated", "conflict-tools\\generated\\", os.path.join(tools_dir(game), "generated"), True)]


def _is_text(path, size):
    """(True, "") for a text file, else (False, reason)."""
    if os.path.splitext(path)[1].lower() in BINARY_EXT:
        return False, "binary file type"
    if size > MAX_FILE_BYTES:
        return False, f"over {MAX_FILE_BYTES // (1024 * 1024)} MB"
    try:
        with open(path, "rb") as f:
            head = f.read(65536)
    except OSError as e:
        return False, f"unreadable ({e.strerror or 'error'})"
    if b"\0" in head:
        return False, "binary or UTF-16 content"
    return True, ""


def _walk_files(folder):
    for base, dirs, files in os.walk(folder):
        dirs.sort()
        for fn in sorted(files):
            yield os.path.join(base, fn)


def collect(game, work, scrubber):
    """Copy the sources into `work` (scrubbed). (counts {archive path: replacements}, missing [label],
    excluded [(archive path, reason)])."""
    counts, missing, excluded = {}, [], []

    def one(src, arc):
        arc_s, n_name = scrubber.scrub(arc.replace("\\", "/"))
        try:
            st = os.lstat(src)
        except OSError:
            excluded.append((arc_s, "unreadable (error)"))
            return
        if os.path.islink(src):
            excluded.append((arc_s, "link"))
            return
        ok, why = _is_text(src, st.st_size)
        if not ok:
            excluded.append((arc_s, why))
            return
        try:
            with open(src, "rb") as f:
                data = f.read()
        except OSError as e:
            excluded.append((arc_s, f"unreadable ({e.strerror or 'error'})"))
            return
        data, n = scrubber.scrub_bytes(data)
        dst = os.path.join(work, *arc_s.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(data)
        counts[arc_s] = n + n_name

    for name, label, path, is_dir in sources(game):
        if is_dir:
            if not os.path.isdir(path):
                missing.append(label)
                continue
            for src in _walk_files(path):
                one(src, name + "/" + os.path.relpath(src, path).replace("\\", "/"))
        else:
            if not os.path.isfile(path):
                missing.append(label)
                continue
            one(path, name)
    return counts, missing, excluded


def summary_text(counts, missing, excluded, stamp):
    lines = ["conflict-tools report: scrub summary",
             f"version: {mwdialog_version.__version__}",
             f"made: {stamp}", "",
             "Replacements per file (paths and the user name were replaced in copies only):"]
    lines += [f"  {n:6d}  {name}" for name, n in sorted(counts.items())] or ["  (no files)"]
    lines += [f"  {sum(counts.values()):6d}  total", "", "Skipped (not found):"]
    lines += [f"  {m}" for m in missing] or ["  none"]
    lines += ["", "Excluded (not scrubbed, not included):"]
    lines += [f"  {name}  ({why})" for name, why in sorted(excluded)] or ["  none"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------------- archive
def _unique(path):
    base, ext = os.path.splitext(path)
    n, p = 1, path
    while os.path.exists(p):
        n += 1
        p = f"{base}-{n}{ext}"
    return p


def pack_report(game_dir, staging=(), downloads=(), out_dir=None, now=None, seven_zip=None, temp_root=None,
                profiles=None, names=None):
    """Make the report; returns the archive's path. out_dir: where it goes (tests, a smoke run); the default is
    <game>\\conflict-tools\\reports\\, which is created only here, once the archive exists. Raises ReportError."""
    game = os.path.abspath(game_dir)
    z = seven_zip or MP.find_7z(game_dir=game)
    if not z:
        raise ReportError("Could not make the report: 7-Zip (7z) was not found. Place 7z.exe and 7z.dll in "
                          "conflict-tools\\tools\\7z\\, or install 7-Zip and add it to PATH.", code=2)
    if profiles is None or names is None:
        p, n = identity()
        profiles, names = (p if profiles is None else profiles), (n if names is None else names)
    scrubber = Scrubber(game, staging, downloads, profiles, names)
    stamp = time.strftime("%Y%m%d-%H%M%S", now or time.localtime())
    work = tempfile.mkdtemp(prefix="ct-report-", dir=temp_root)
    try:
        if MP._is_under(work, game):
            raise ReportError("The system temp folder is inside the game folder; set TEMP elsewhere.")
        files = os.path.join(work, "files")
        os.makedirs(files)
        counts, missing, excluded = collect(game, files, scrubber)
        with open(os.path.join(files, SUMMARY_NAME), "w", encoding="utf-8", newline="\n") as f:
            f.write(summary_text(counts, missing, excluded, time.strftime("%Y-%m-%d %H:%M:%S", now or time.localtime())))
        built = os.path.join(work, ARCHIVE_PREFIX + stamp + ARCHIVE_EXT)
        try:
            r = subprocess.run([z, "a", "-tzip", "-mx=5", "-bd", "-y", built, "*"], cwd=files,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as e:
            raise ReportError(f"Could not run 7-Zip ({z}): {e}", code=2)
        if r.returncode or not os.path.isfile(built):
            tail = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip().splitlines()[-1:]
            raise ReportError(f"7-Zip failed (exit code {r.returncode}){': ' + tail[0] if tail else ''}.")
        dest_dir = out_dir or os.path.join(tools_dir(game), "reports")
        os.makedirs(dest_dir, exist_ok=True)
        dest = _unique(os.path.join(dest_dir, os.path.basename(built)))
        shutil.copyfile(built, dest)
        return dest
    finally:
        shutil.rmtree(work, ignore_errors=True)


def plain_line(text):
    """Print one line exactly as given: past mwdialog_text's line wrapping (a long path must stay one line)."""
    out = sys.stdout
    try:
        out.flush()
    except Exception:
        pass
    while hasattr(out, "_inner"):
        out = out._inner
    out.write(text + "\n")
    out.flush()


def main(game_dir, staging=(), downloads=(), out_dir=None, **kw):
    """The --pack-report switch: prints exactly one line, the archive path, and returns 0; an error is one line on
    stderr and a non-zero code (2: no 7-Zip)."""
    try:
        path = pack_report(game_dir, staging, downloads, out_dir=out_dir, **kw)
    except ReportError as e:
        print(str(e), file=sys.stderr)
        return e.code
    plain_line(path)
    return 0