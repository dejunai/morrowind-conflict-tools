"""doc_scan.py - keep the docs from going stale: every documented command-line switch must still
exist in the code, and every switch the code defines should be documented.

It only verifies. It never edits a doc or a source file.

What it reads
  The tools: every *.py beside this script (the CLIs). tests/, a local diag/ folder if present, this file and the private, untracked
helpers gather_steam_lua.py and sync.py are left out.
  The docs: README.md, docs/MORE_INFO.md, and the other docs/*.md except docs/dev/ and a local
  docs/CHANGES.md if one is present (a changelog that is not part of the package).

How switches are collected from the code
  argparse: ast of add_argument() string flags, and -h/--help when ArgumentParser (or the
  project's MT.parser wrapper) is created with the default add_help. A flag whose help is
  argparse.SUPPRESS is kept as a real switch (so a doc that mentions it still matches) but is
  not reported as undocumented: that is how a retired or dev-only switch is marked, in the
  code itself, rather than in a list here.
  Hand-rolled parsers: ast of comparisons and startswith() against a literal --flag, --flag=,
  or -x (deploy.py and anything like it). There is no hardcoded switch list.

How switches are collected from the docs
  --long and --opt=value (the value is dropped). Short -x only in backticks, or written next
  to a long option with / or , (for example -h/--help).

Which tool a mention belongs to
  A heading that names a tool (vortex_tidy, mwdialog_check.py, ...) sets the tool for the
  lines that follow; a deeper heading with no tool keeps it, a same-or-shallower heading
  without a tool clears it. A switch written immediately after a tool name
  (vortex_tidy --undo) is checked against that tool. With no tool named, the mention is
  checked against every tool's switches.

Third-party commands (ignored)
  A switch on the same line as one of these names, and after that name, is treated as an
  argument of that command and ignored: omw2mwse, luajit, luac, git, tes3cmd, mlox, pytest, pip.
  A switch that appears before the name on the same line is still ours. The standard help
  flags -h and --help are not reported as undocumented (every CLI has them).

Usage: python doc_scan.py [DIR]
       python doc_scan.py -h | --help

  DIR   the project to scan (default: the folder this script is in).

Exit 0 when every documented switch exists in the code and every code switch is documented.
Exit 1 when either list has entries. Exit 2 on an unknown switch. Nothing is written to disk.

Credit: dej (dejunai). Python 3.9+, standard library only.
"""
from __future__ import annotations

import ast
import os
import re
import sys

HELP = __doc__

HERE = os.path.dirname(os.path.abspath(__file__))

# Commands whose flags are not ours. Keep this list short and visible; see the module docstring.
THIRD_PARTY = ("omw2mwse", "luajit", "luac", "git", "tes3cmd", "mlox", "pytest", "pip")

# Standard help is defined by argparse (and by hand-rolled -h/--help). Docs need not list it.
STANDARD_HELP = frozenset(("-h", "--help"))

SKIP_DOCS = frozenset(("changes.md",))  # historical; names switches that were removed on purpose
LONG = re.compile(r"(?<!-)-{2}(?!-)([A-Za-z][\w-]*)")  # exactly two dashes: not a markdown --- or an em-dash
LINK_DEST = re.compile(r"(\]\()([^)]*)\)")
SHORT_TICK = re.compile(r"`-([A-Za-z])`")
SHORT_BESIDE = re.compile(
    r"(?:--[A-Za-z][\w-]*)\s*[,/]\s*-([A-Za-z])(?![A-Za-z0-9-])"
    r"|-([A-Za-z])(?![A-Za-z0-9-])\s*[,/]\s*--[A-Za-z]"
)
HEADING = re.compile(r"^(#{1,6})\s+(.*)")
FLAG = re.compile(r"^--[A-Za-z][\w-]*$|^-[A-Za-z]$")


def rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


# ---------------------------------------------------------------- code


def py_files(root):
    """CLI modules beside the script (or DIR). This checker is not one of the tools it checks."""
    # gather_steam_lua.py and sync.py: private, untracked helpers (.gitignore) that are not documented on purpose
    skip = {"doc_scan.py", "gather_steam_lua.py", "sync.py"}
    for name in sorted(os.listdir(root)):
        if name.endswith(".py") and name not in skip and not name.startswith("."):
            yield os.path.join(root, name), name


def _call_name(node):
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""


def _str_const(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _is_suppress(node):
    if isinstance(node, ast.Attribute) and node.attr == "SUPPRESS":
        return True
    return isinstance(node, ast.Name) and node.id == "SUPPRESS"


def _kw(call, name):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _add_help(call):
    """True unless add_help=False is passed to ArgumentParser / MT.parser."""
    v = _kw(call, "add_help")
    if v is None:
        return True
    return not (isinstance(v, ast.Constant) and v.value is False)


def _flag_strings(call):
    out = []
    for a in call.args:
        s = _str_const(a)
        if s and FLAG.match(s):
            out.append(s)
    return out


def _literal_strings(node):
    """String literals in a compare operand, including those inside a tuple/list/set."""
    s = _str_const(node)
    if s is not None:
        return [s]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        out = []
        for e in node.elts:
            t = _str_const(e)
            if t is not None:
                out.append(t)
        return out
    return []


def _norm_lit(s):
    """--flag or --flag=... or -x -> the flag, or None if it is not a switch name."""
    if s.startswith("--") and s.endswith("=") and len(s) > 3:
        s = s[:-1]
    return s if FLAG.match(s) else None


def switches_in_source(text, filename=""):
    """{flag: suppressed} defined in one module. suppressed means help=SUPPRESS (dev/retired)."""
    tree = ast.parse(text, filename=filename)
    found = {}
    has_parser = False
    parser_help = False
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        name = _call_name(n)
        if name in ("ArgumentParser", "parser"):
            has_parser = True
            parser_help = parser_help or _add_help(n)
        if name != "add_argument":
            continue
        suppressed = _is_suppress(_kw(n, "help")) if _kw(n, "help") is not None else False
        for f in _flag_strings(n):
            found[f] = found.get(f, False) or suppressed
    if has_parser and parser_help:
        for f in STANDARD_HELP:
            found.setdefault(f, False)
    for n in ast.walk(tree):
        lits = []
        if isinstance(n, ast.Compare):
            for x in [n.left] + list(n.comparators):
                lits.extend(_literal_strings(x))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "startswith" and n.args:
            lits.extend(_literal_strings(n.args[0]))
        else:
            continue
        for s in lits:
            f = _norm_lit(s)
            if f:
                found.setdefault(f, False)
    return found


def collect_code(root):
    """tool filename -> {flag: suppressed}."""
    tools = {}
    for path, name in py_files(root):
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        try:
            found = switches_in_source(text, path)
        except SyntaxError:
            print("doc_scan: could not parse %s; that tool's switches were skipped." % name, file=sys.stderr)
            continue
        if found:
            tools[name] = found
    return tools


# ---------------------------------------------------------------- docs


def doc_files(root):
    out = []
    readme = os.path.join(root, "README.md")
    if os.path.isfile(readme):
        out.append(readme)
    docs = os.path.join(root, "docs")
    if os.path.isdir(docs):
        for name in sorted(os.listdir(docs)):
            if not name.lower().endswith((".md", ".markdown")):
                continue
            if name.lower() in SKIP_DOCS:
                continue
            out.append(os.path.join(docs, name))
    return out


def known_tools(tool_files):
    """Names that identify a tool in a heading or a sentence: 'vortex_tidy', 'vortex_tidy.py'.

    The bare stem is used only when it is distinctive (contains '_'), so a sentence that says
    'Deploy after --apply' is not attributed to deploy.py.
    """
    names = {}
    for fn in tool_files:
        base, ext = os.path.splitext(fn)
        names[fn.lower()] = fn
        if "_" in base:
            names[base.lower()] = fn
    return names


def tool_on_text(text, names):
    """Tool filenames named in text, in the order they appear. Longest name first so .py wins."""
    found, spots = [], []
    low = text.lower()
    for label in sorted(names, key=len, reverse=True):
        start = 0
        while True:
            i = low.find(label, start)
            if i < 0:
                break
            end = i + len(label)
            left = low[i - 1] if i else ""
            right = low[end] if end < len(low) else ""
            # 'mwdialog_check' must not eat the prefix of 'mwdialog_check.py' twice as two tools,
            # and must not match inside a longer identifier.
            if (not left or not (left.isalnum() or left == "_")) and (not right or not (right.isalnum() or right == "_")):
                spots.append((i, names[label]))
            start = end
    seen = set()
    for _, tool in sorted(spots):
        if tool not in seen:
            seen.add(tool)
            found.append(tool)
    return found


def tool_just_before(line, pos, names):
    """The tool named immediately before a switch: 'vortex_tidy --undo' or 'mwdialog_check.py --play'."""
    m = re.search(r"([A-Za-z_][A-Za-z0-9_.]*)\s*$", line[:pos])
    if not m:
        return None
    return names.get(m.group(1).lower())


def third_party_pos(line):
    """Index of the first third-party command name on the line, or -1."""
    low = line.lower()
    first = -1
    for name in THIRD_PARTY:
        start = 0
        while True:
            i = low.find(name, start)
            if i < 0:
                break
            end = i + len(name)
            left = low[i - 1] if i else ""
            right = low[end] if end < len(low) else ""
            if (not left or not (left.isalnum() or left == "_")) and (not right or not (right.isalnum() or right == "_")):
                if first < 0 or i < first:
                    first = i
                break
            start = end
    return first


def mask_link_destinations(line):
    """Blank the URL/anchor inside markdown ](...) so a TOC slug like #exit-codes--environment
    is not read as the switch --environment."""
    def repl(m):
        return m.group(1) + (" " * len(m.group(2))) + ")"
    return LINK_DEST.sub(repl, line)


def mentions_in_line(line):
    """(index, flag) for each switch mention. --opt=value is recorded as --opt."""
    line = mask_link_destinations(line)
    out, seen = [], set()
    for m in LONG.finditer(line):
        # a typographic em-dash sometimes appears as two hyphens; require a letter after --
        flag = "--" + m.group(1)
        key = (m.start(), flag)
        if key not in seen:
            seen.add(key)
            out.append(key)
    for m in SHORT_TICK.finditer(line):
        flag = "-" + m.group(1)
        key = (m.start(), flag)
        if key not in seen:
            seen.add(key)
            out.append(key)
    for m in SHORT_BESIDE.finditer(line):
        letter = m.group(1) or m.group(2)
        flag = "-" + letter
        key = (m.start(), flag)
        if key not in seen:
            seen.add(key)
            out.append(key)
    out.sort()
    return out


def collect_docs(root, tool_files):
    """List of (relpath, line_no, flag, tool_or_None, ignored). line_no is 1-based."""
    names = known_tools(tool_files)
    mentions = []
    for path in doc_files(root):
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        current, depth = None, 0
        r = rel(root, path)
        for n, line in enumerate(text.splitlines(), 1):
            hm = HEADING.match(line)
            if hm:
                d = len(hm.group(1))
                named = tool_on_text(hm.group(2), names)
                if named:
                    current, depth = named[0], d
                elif d <= depth:
                    current, depth = None, d
                # a deeper heading with no tool (#### under "### mwdialog_check Switches") keeps the tool
            after = third_party_pos(line)
            for pos, flag in mentions_in_line(line):
                ignored = after >= 0 and pos > after
                beside = tool_just_before(line, pos, names)
                attributed = [beside] if beside else ([current] if current else [])
                mentions.append((r, n, flag, attributed, ignored))
    return mentions


# ---------------------------------------------------------------- report


def union_flags(tools):
    u = set()
    for flags in tools.values():
        u.update(flags)
    return u


def problems(tools, mentions):
    """(stale, undocumented): stale is (where, flag, detail); undocumented is (tool, flag)."""
    all_flags = union_flags(tools)
    stale, seen_ok = [], set()
    for path, line, flag, named, ignored in mentions:
        if ignored:
            continue
        if named:
            # ok if any named tool that we scanned defines it; a name we did not scan
            # (a tool not in this tree) falls back to the union.
            scanned = [t for t in named if t in tools]
            if scanned:
                if any(flag in tools[t] for t in scanned):
                    seen_ok.add(flag)
                    continue
                who = scanned[0] if len(scanned) == 1 else " / ".join(scanned)
                stale.append((path, line, flag, "not a switch of %s" % who))
                continue
        if flag in all_flags:
            seen_ok.add(flag)
        else:
            stale.append((path, line, flag, "not a switch of any tool"))
    undocumented = []
    for tool, flags in sorted(tools.items()):
        for flag, suppressed in sorted(flags.items()):
            if suppressed or flag in STANDARD_HELP or flag in seen_ok:
                continue
            # a code switch is documented if any mention (attributed or not, and not ignored)
            # used that name. Attribution is not required the other way: a mention in a
            # general section still documents it.
            undocumented.append((tool, flag))
    # unique undocumented flags: if two tools share --yes and it was documented once, seen_ok covers both
    return stale, undocumented


def format_stale(item):
    path, line, flag, detail = item
    return "%s:%d: %s: %s" % (path, line, flag, detail)


def format_undoc(item):
    tool, flag = item
    return "%s: %s is not documented" % (tool, flag)


def scan(root):
    tools = collect_code(root)
    mentions = collect_docs(root, list(tools))
    return tools, mentions, problems(tools, mentions)


def render(root, stale, undocumented, mentions):
    lines = []
    for item in stale:
        lines.append(format_stale(item))
    for item in undocumented:
        lines.append(format_undoc(item))
    n_doc = sum(1 for _p, _n, _f, _t, ign in mentions if not ign)
    if stale or undocumented:
        lines.append("%d documented switch(es) not in the code, %d undocumented."
                     % (len(stale), len(undocumented)))
    else:
        lines.append("OK: %d documented switch mention(s) match the code; no undocumented switches."
                     % n_doc)
    return "\n".join(lines) + "\n"


def main(argv=None, root=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if any(a in ("-h", "--help") for a in argv):
        sys.stdout.write(HELP)
        return 0
    bad = [a for a in argv if a.startswith("-")]
    paths = [a for a in argv if not a.startswith("-")]
    if bad or len(paths) > 1:
        sys.stderr.write("doc_scan.py: unknown switch or argument: %s\n"
                         "Nothing was done. Run: python doc_scan.py --help\n" % " ".join(bad or paths))
        return 2
    root = os.path.abspath(paths[0] if paths else (root or HERE))
    if not os.path.isdir(root):
        sys.stderr.write("doc_scan.py: not a folder: %s\n" % root)
        return 2
    _tools, mentions, (stale, undocumented) = scan(root)
    sys.stdout.write(render(root, stale, undocumented, mentions))
    return 1 if stale or undocumented else 0


if __name__ == "__main__":
    raise SystemExit(main())