"""Shared path helpers: no hardcoded absolute paths.

The game root is the folder this script (or the calling tool) lives in. Vortex's Morrowind staging
and download folders come from Vortex's own settings (%APPDATA%\\Vortex). CLI flags override.
Recorded paths are stored relative to one of those bases, with a tag (staging:/downloads:/game:).
Readers still accept an older absolute path and convert it the next time the record is written.
"""
import json
import os
import re
import shutil
import sys

GAME_ID = "morrowind"
TAGS = ("staging", "downloads", "game")
DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")

# LevelDB / JSON keys Vortex uses for these paths
_DL_KEY = b"settings###downloads###path"
_INST_KEY = b"settings###mods###installPath"
_INST_GAME_KEY = b"settings###mods###installPath###"  # + game id


class VortexPathError(Exception):
    """Vortex settings could not be read, or the resolved folder is missing. args[0] is the message."""

    def __init__(self, message, kind=None, tried=None, reason=None):
        super().__init__(message)
        self.kind = kind
        self.tried = list(tried or [])
        self.reason = reason


class ToolNotFoundError(Exception):
    """An optional external tool (7-Zip) was needed and was not found."""


def script_dir(script_file=None):
    """Folder of the calling tool (or of this module if script_file is omitted)."""
    if script_file:
        return os.path.dirname(os.path.abspath(script_file))
    return os.path.dirname(os.path.abspath(__file__))


def game_root(script_file=None, data_dir=None):
    """The Morrowind install root: the parent of Data Files when data_dir is given, else the
    folder the calling script lives in."""
    if data_dir:
        data_dir = os.path.abspath(data_dir)
        base = os.path.basename(data_dir)
        if base.lower() == "data files":
            return os.path.dirname(data_dir)
        return data_dir
    return script_dir(script_file)


def is_abs_path(path):
    """True for a POSIX/Windows absolute path, including a drive-letter path on a non-Windows host."""
    if not path:
        return False
    return os.path.isabs(path) or bool(DRIVE_RE.match(path))


def _normkey(path):
    p = (path or "").replace("/", "\\").rstrip("\\")
    if len(p) == 2 and p[1] == ":":
        p += "\\"
    return p.lower()


def _is_under(path, base):
    a, b = _normkey(path), _normkey(base)
    return a == b or a.startswith(b + "\\")


def _rel_to(path, base):
    """path relative to base, using backslashes (the record format), preserving path case."""
    p = path.replace("/", "\\")
    b = base.replace("/", "\\").rstrip("\\")
    if _normkey(p) == _normkey(b):
        return ""
    # same length prefix as the normalised base; walk by segments to stay case-accurate
    ps, bs = p.split("\\"), b.split("\\")
    i = 0
    while i < len(ps) and i < len(bs) and ps[i].lower() == bs[i].lower():
        i += 1
    if i != len(bs):
        return os.path.relpath(path, base).replace("/", "\\")
    return "\\".join(ps[i:])


def vortex_appdata():
    """%APPDATA%\\Vortex, or None when APPDATA is unset."""
    app = os.environ.get("APPDATA")
    if not app:
        return None
    return os.path.join(app, "Vortex")


def vortex_search_dirs():
    """Folders we look in for Vortex settings, in order (may or may not exist)."""
    root = vortex_appdata()
    if not root:
        return []
    return [
        os.path.join(root, "state.v2"),
        os.path.join(root, "state"),
        os.path.join(root, "temp", "state_backups_full"),
    ]


def as_local(path):
    """Separators converted to this OS's, so a path from Vortex (often backslash) can be tested with isdir."""
    if not path:
        return path
    return os.path.normpath(path.replace("/", os.sep).replace("\\", os.sep))


def _expand(path, game_id=GAME_ID, userdata=None):
    if not path or not isinstance(path, str):
        return path
    if userdata is None:
        userdata = vortex_appdata() or ""
    return (path.replace("{USERDATA}", userdata)
                .replace("{userdata}", userdata)
                .replace("{game}", game_id)
                .replace("{GAME}", game_id))


def _json_string(raw):
    try:
        return json.loads(b'"' + raw + b'"')
    except (ValueError, TypeError):
        try:
            return json.loads(raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else raw)
        except (ValueError, TypeError):
            return None


def _scan_leveldb_dir(folder, game_id):
    """Best-effort: pull downloads path and installPath from LevelDB .ldb/.log files."""
    downloads = staging_tmpl = None
    try:
        names = os.listdir(folder)
    except OSError:
        return None, None
    files = []
    for n in names:
        low = n.lower()
        if low.endswith((".log", ".ldb")) or n.upper() in {"LOG", "LOG.OLD"}:
            files.append(os.path.join(folder, n))
    files.sort(key=os.path.getmtime, reverse=True)
    inst_pat = re.compile(
        re.escape(_INST_KEY) + rb".{0,24}?(\{(?:[^{}]|\{[^{}]*\}){0,4000}\})", re.S)
    inst_game_pat = re.compile(
        re.escape(_INST_GAME_KEY + game_id.encode("ascii")) + rb".{0,24}?\"((?:[^\"\\]|\\.){1,500})\"", re.S)
    dl_pat = re.compile(
        re.escape(_DL_KEY) + rb".{0,24}?\"((?:[^\"\\]|\\.){1,500})\"", re.S)
    for fn in files:
        try:
            data = open(fn, "rb").read()
        except OSError:
            continue
        if downloads is None:
            hits = dl_pat.findall(data)
            if hits:
                v = _json_string(hits[-1])
                if v:
                    downloads = v
        if staging_tmpl is None:
            gm = inst_game_pat.findall(data)
            if gm:
                v = _json_string(gm[-1])
                if v:
                    staging_tmpl = v
        if staging_tmpl is None:
            m = inst_pat.search(data)
            if m:
                try:
                    obj = json.loads(m.group(1))
                except ValueError:
                    obj = None
                if isinstance(obj, dict) and obj.get(game_id):
                    staging_tmpl = obj[game_id]
                elif isinstance(obj, str):
                    staging_tmpl = obj
        if downloads and staging_tmpl:
            break
    return downloads, staging_tmpl


def _from_state_obj(data, game_id):
    if not isinstance(data, dict):
        return None, None
    settings = data.get("settings")
    if not isinstance(settings, dict):
        settings = (data.get("persistent") or {}).get("settings") or {}
    if not isinstance(settings, dict):
        return None, None
    dl = (settings.get("downloads") or {}).get("path") if isinstance(settings.get("downloads"), dict) else None
    inst = (settings.get("mods") or {}).get("installPath") if isinstance(settings.get("mods"), dict) else None
    staging = None
    if isinstance(inst, dict):
        staging = inst.get(game_id)
    elif isinstance(inst, str):
        staging = inst
    return dl, staging


def _scan_json_backup_dir(folder, game_id):
    try:
        names = [n for n in os.listdir(folder) if n.lower().endswith(".json")]
    except OSError:
        return None, None
    files = [os.path.join(folder, n) for n in names]
    files.sort(key=os.path.getmtime, reverse=True)
    for fn in files:
        try:
            with open(fn, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError, UnicodeError):
            continue
        dl, st = _from_state_obj(data, game_id)
        if dl or st:
            return dl, st
    return None, None


_SETTINGS_MEMO = {}


def read_vortex_settings(game_id=GAME_ID, refresh=False):
    """_read_vortex_settings, once per run and %APPDATA% (staging and downloads both ask). Only an answer that
    names a folder is kept, so a later call tries again after a failure; refresh=True reads Vortex again."""
    key = (game_id, os.environ.get("APPDATA"))
    info = None if refresh else _SETTINGS_MEMO.get(key)
    if info is None:
        info = _read_vortex_settings(game_id)
        if info.get("downloads_tmpl") or info.get("staging_tmpl"):
            _SETTINGS_MEMO[key] = info
        else:
            _SETTINGS_MEMO.pop(key, None)
    return {k: list(v) if isinstance(v, list) else v for k, v in info.items()}


def clear_vortex_settings_cache():
    """Forget what read_vortex_settings read (a long-running caller, after Vortex's settings changed)."""
    _SETTINGS_MEMO.clear()


def _read_vortex_settings(game_id=GAME_ID):
    """Read Vortex's download path and Morrowind install/staging path templates.

    Returns dict: downloads_tmpl, staging_tmpl, tried (folders looked at), reason (if nothing useful).
    Templates may still contain {game} / {USERDATA}; expand with _expand.
    """
    tried = []
    reason = None
    root = vortex_appdata()
    if not root:
        return {"downloads_tmpl": None, "staging_tmpl": None, "tried": [],
                "reason": "%APPDATA% is not set (Vortex stores its settings in %APPDATA%\\Vortex)."}
    if not os.path.isdir(root):
        return {"downloads_tmpl": None, "staging_tmpl": None, "tried": [root],
                "reason": f"Vortex AppData folder not found: {root}"}
    downloads = staging = None
    for folder in vortex_search_dirs():
        tried.append(folder)
        if not os.path.isdir(folder):
            continue
        base = os.path.basename(folder).lower()
        if base in {"state.v2", "state"}:
            d, s = _scan_leveldb_dir(folder, game_id)
        else:
            d, s = _scan_json_backup_dir(folder, game_id)
        downloads = downloads or d
        staging = staging or s
        if downloads and staging:
            break
    if not downloads and not staging:
        reason = ("Vortex's settings were found but they do not name a downloads path or a "
                  f"Morrowind staging (installPath.{game_id}) folder."
                  if any(os.path.isdir(p) for p in tried) else
                  "No Vortex state database or settings backup could be read in: " + "; ".join(tried))
    return {"downloads_tmpl": downloads, "staging_tmpl": staging, "tried": tried, "reason": reason}


def _format_error(kind, flag, tried, reason):
    label = {"staging": "staging folder", "downloads": "download folder"}[kind]
    lines = [
        f"Could not determine Vortex's Morrowind {label}.",
        "",
        "Looked for Vortex settings in:",
    ]
    if tried:
        lines.extend(f"  {p}" for p in tried)
    else:
        lines.append("  (no Vortex folders to search: %APPDATA% is not set)")
    if reason:
        lines.append(f"Reason: {reason}")
    lines.append("")
    lines.append(f"Pass {flag} to set the {label} explicitly.")
    return "\n".join(lines)


def resolve_staging(cli=None, required=True, game_id=GAME_ID):
    """The Morrowind staging folder. `cli` (e.g. --staging) wins when given.

    When `required` and the folder cannot be determined (or does not exist), raises VortexPathError.
    Otherwise returns None.
    """
    if cli:
        path = os.path.abspath(cli)
        if os.path.isdir(path):
            return path
        if required:
            raise VortexPathError(
                f"Staging folder not found: {path}\nPass --staging DIR to set it explicitly.",
                kind="staging", tried=[path], reason=f"the folder does not exist: {path}")
        return None
    info = read_vortex_settings(game_id)
    tmpl = info.get("staging_tmpl")
    path = as_local(_expand(tmpl, game_id)) if tmpl else None
    if path and os.path.isdir(path):
        return os.path.abspath(path)
    if not required:
        return None
    if path and not os.path.isdir(path):
        reason = f"Vortex's staging folder does not exist: {path}"
    else:
        reason = info.get("reason") or "Vortex settings have no Morrowind installPath."
    raise VortexPathError(
        _format_error("staging", "--staging DIR", info.get("tried") or vortex_search_dirs(), reason),
        kind="staging", tried=info.get("tried"), reason=reason)


def resolve_downloads(cli=None, required=True, game_id=GAME_ID):
    """The Morrowind download folder. `cli` (e.g. --vortex-downloads / --downloads) wins when given."""
    if cli:
        path = os.path.abspath(cli)
        if os.path.isdir(path):
            return path
        # a path that already includes the game leaf, or its parent
        if required:
            raise VortexPathError(
                f"Download folder not found: {path}\n"
                f"Pass --vortex-downloads DIR (or --downloads DIR) to set it explicitly.",
                kind="downloads", tried=[path], reason=f"the folder does not exist: {path}")
        return None
    info = read_vortex_settings(game_id)
    tmpl = info.get("downloads_tmpl")
    path = as_local(_expand(tmpl, game_id)) if tmpl else None
    # Vortex's path usually already contains {game}; also try joining 'morrowind' if needed
    cands = []
    if path:
        cands.append(path)
        if os.path.basename(path).lower() != game_id:
            cands.append(os.path.join(path, game_id))
    for c in cands:
        if c and os.path.isdir(c):
            return os.path.abspath(c)
    if not required:
        return None
    if path and not any(os.path.isdir(c) for c in cands if c):
        reason = f"Vortex's download folder does not exist: {path}"
    else:
        reason = info.get("reason") or "Vortex settings have no downloads path."
    raise VortexPathError(
        _format_error("downloads", "--vortex-downloads DIR (or --downloads DIR)",
                      info.get("tried") or vortex_search_dirs(), reason),
        kind="downloads", tried=info.get("tried"), reason=reason)


def path_bases(game_dir, staging=None, downloads=None):
    """{tag: absolute folder} for any base that was given."""
    out = {}
    if game_dir:
        out["game"] = os.path.abspath(game_dir)
    if staging:
        out["staging"] = os.path.abspath(staging)
    if downloads:
        out["downloads"] = os.path.abspath(downloads)
    return out


def store_path(path, bases):
    """Store `path` as 'tag:relative' under the longest matching base. Absolute paths that do not
    sit under a base are returned unchanged (the reader still accepts them). Already-tagged values
    are re-resolved and re-stored so a write migrates them."""
    if not path:
        return path
    resolved = resolve_stored(path, bases, missing_ok=True)
    if not is_abs_path(resolved):
        # still relative and untagged, and we couldn't resolve it
        return path
    best = None
    for tag, base in (bases or {}).items():
        if not base or tag not in TAGS:
            continue
        if _is_under(resolved, base):
            score = len(_normkey(base))
            if best is None or score > best[0]:
                best = (score, tag, _rel_to(resolved, base))
    if best:
        return f"{best[1]}:{best[2]}"
    return resolved


def resolve_stored(stored, bases, missing_ok=False):
    """Turn a stored path (tag:rel, or an older absolute path) into an absolute path.

    If the tag's base is missing and missing_ok is False, raises VortexPathError.
    """
    if not stored:
        return stored
    stored = stored.strip()
    tag, sep, rest = stored.partition(":")
    if sep and tag.lower() in TAGS:
        base = (bases or {}).get(tag.lower())
        if not base:
            if missing_ok:
                return stored
            raise VortexPathError(
                f"Cannot resolve {tag}:{rest}: the {tag} folder is not known. "
                f"Pass --staging / --vortex-downloads, or fix Vortex settings.",
                kind=tag.lower())
        rest = rest.replace("/", os.sep).replace("\\", os.sep)
        return os.path.normpath(os.path.join(base, rest))
    return stored


def rewrite_original_meta(meta, bases):
    """Rewrite the 'original: PATH' field inside an added-masters metadata string."""
    if not meta:
        return meta
    parts = [x.strip() for x in str(meta).split(";")]
    out = []
    for p in parts:
        if p.lower().startswith("original:"):
            orig = p.split(":", 1)[1].strip()
            out.append(f"original: {store_path(orig, bases)}" if orig else p)
        else:
            out.append(p)
    return "; ".join(out)


def original_from_meta(meta):
    """The original: path in an added-masters metadata string, or ''."""
    for p in (x.strip() for x in str(meta or "").split(";")):
        if p.lower().startswith("original:"):
            return p.split(":", 1)[1].strip()
    return ""


def convert_added_masters(rec, bases):
    """A copy of the added-masters dict with original: fields stored as tagged relative paths."""
    out = {}
    for patch, mods in (rec or {}).items():
        inner = {}
        for mod, meta in (mods or {}).items():
            inner[mod] = rewrite_original_meta(meta, bases)
        out[patch] = inner
    return out


def convert_reduced_row(rel, kind, keep, bases):
    return rel, kind, store_path(keep, bases)


def find_7z(game_dir=None, required=False):
    """7-Zip: PATH first (shutil.which('7z')), then <game>\\tools\\7z\\ (optional).

    No registry lookup and no hardcoded Program Files paths. When `required` and nothing is
    found, raises ToolNotFoundError with a clear message.
    """
    found = shutil.which("7z")
    if found and os.path.isfile(found):
        return found
    tried_tools = []
    if game_dir:
        for rel in (os.path.join("tools", "7z", "7z.exe"),
                    os.path.join("tools", "7z", "7z"),
                    os.path.join("tools", "7z.exe"),
                    os.path.join("tools", "7z")):
            p = os.path.join(game_dir, rel)
            tried_tools.append(p)
            if os.path.isfile(p):
                return p
    if not required:
        return None
    lines = [
        "Could not find 7-Zip (7z).",
        "Looked on PATH (shutil.which('7z'))",
    ]
    if tried_tools:
        lines.append("and in:")
        lines.extend(f"  {p}" for p in tried_tools)
    else:
        lines.append("and did not have a game folder to check for tools\\7z.")
    lines.append("Install 7-Zip and add it to PATH, or place 7z.exe in <game>\\tools\\7z\\.")
    raise ToolNotFoundError("\n".join(lines))


def luajit_candidates(game_dir, explicit=None):
    """Paths to try for a LuaJIT / luac executable, in order (existing or not)."""
    exe = "luajit.exe" if os.name == "nt" else "luajit"
    cands = []
    if explicit:
        cands.append(explicit)
    if game_dir:
        cands.append(os.path.join(game_dir, "tools", "luajit", exe))
        if os.name == "nt":
            cands.append(os.path.join(game_dir, "tools", "luajit", "luajit"))
        cands.append(os.path.join(game_dir, exe))
    return cands


def describe_luajit_search(game_dir):
    root = game_dir or "<game>"
    exe = "luajit.exe" if os.name == "nt" else "luajit"
    return (f"Looked in {os.path.join(root, 'tools', 'luajit', exe)}, then on PATH. "
            f"Pass --luajit PATH to use a specific binary, or --no-syntax-check to rely on the parser alone.")
