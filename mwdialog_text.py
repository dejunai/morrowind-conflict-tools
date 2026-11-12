"""Human-readable text wrapping for the Morrowind conflict tools.

Console output, report text, argparse --help, and dated fix-log lines wrap at
WIDTH (115) characters. Continuation lines indent HANG (2) spaces beyond the
source line's leading indent, or align under a bullet or a log-prefix
(timestamp). A single token longer than the width is left intact.

Plan-file action lines, rules/records files, JSON, CSV/TSV, and Lua patch
content are not written through this module: wrap console previews only, and
leave those files as the tools built them.
"""
from __future__ import annotations

import argparse
import builtins
import io
import os
import re
import sys
import time
import textwrap

WIDTH = 115
HANG = 2
BULLET = "- "

# Drive- or tag-qualified paths, and relative paths that already contain a slash,
# so "Program Files" / "Data Files" in the middle of a path stay one token.
_PATH_RE = re.compile(
    r"(?:(?:[A-Za-z]:|staging:|downloads:|game:)[/\\](?:[^\\/\n]+[/\\])*"
    r"|(?<![^\s])(?:[^\\/\s\n]+[/\\])+)"
    r"[^\\/\s\n]*"
)
_STAMP_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\s+)")
_LOG_HEADER_RE = re.compile(r"^==== .* ====\s*$")


def _path_placeholder(i, length):
    """A space-free marker of the same length as the path (so wrap width stays honest)."""
    core = "\x00%d\x00" % i
    if length <= len(core):
        return core
    return core + ("X" * (length - len(core)))


def _protect_paths(text):
    """Replace path-like spans with space-free placeholders so wrap() will not
    break them at a space inside the path. Returns (text, restorers).

    Each placeholder is the same length as the path it stands for, so a long
    path is treated as one overlong token (it gets its own line) rather than
    shrinking the line and being expanded past WIDTH after the wrap.
    """
    found = []

    def repl(mo):
        p = mo.group(0)
        found.append(p)
        return _path_placeholder(len(found) - 1, len(p))

    return _PATH_RE.sub(repl, text), found


def _restore_paths(text, found):
    for i, path in enumerate(found):
        text = text.replace(_path_placeholder(i, len(path)), path)
    return text


def _base_indent(line, indent):
    if indent is not None:
        return indent
    return line[:len(line) - len(line.lstrip(" \t"))]


def _already_bulleted(body, bullet):
    return body.startswith(bullet) or body.startswith(("- ", "* ", "• "))


def wrap(text, width=WIDTH, hang=HANG, indent=None, prefix="", bullet=None):
    """Wrap human-readable text to `width` characters.

    Each input line is wrapped on its own (blank lines and existing breaks stay).
    Leading whitespace is kept as the base indent (or `indent` if given).
    Continuation lines use that indent plus `hang` extra spaces, except:
      * `bullet` (True, or a marker such as '- '): the marker is put after the
        indent on the first line and continuations align under the item text;
      * `prefix` (a timestamp etc.): kept on the first line, continuations
        align under the message that follows it.

    Words and path-like tokens are not split (break_long_words=False,
    break_on_hyphens=False). A single overlong token stays on its own line,
    even if it is wider than `width`. A trailing newline on the input is kept.
    Already-short lines are returned unchanged (idempotent).
    """
    if text is None:
        return text
    text = str(text)
    if text == "":
        return text
    trailing_nl = text.endswith("\n")
    if trailing_nl:
        text = text[:-1]
    # A lone "\n" (empty line) should still come back as "\n" when trailing_nl.
    parts = text.split("\n")
    out = [_wrap_one(p, width, hang, indent, prefix, bullet) for p in parts]
    result = "\n".join(out)
    if trailing_nl:
        result += "\n"
    return result


def _wrap_one(line, width, hang, indent, prefix, bullet):
    if line == "":
        return line
    # Progress / carriage-return lines: leave them alone.
    if "\r" in line:
        return line
    base = _base_indent(line, indent)
    body = line[len(line) - len(line.lstrip(" \t")):] if indent is None else line.lstrip(" \t")
    if indent is not None:
        # When a base indent is supplied, do not keep a second copy of it.
        body = line[len(base):] if line.startswith(base) else line.lstrip(" \t")

    first_extra = ""
    cont_extra = " " * hang

    if prefix:
        first_extra = prefix
        cont_extra = " " * len(prefix)
    elif bullet:
        mark = BULLET if bullet is True else str(bullet)
        if not _already_bulleted(body, mark):
            first_extra = mark
            cont_extra = " " * len(mark)
        else:
            # Already has a marker: continuations align under the item text.
            existing = next((b for b in (mark, "- ", "* ", "• ") if body.startswith(b)), mark)
            first_extra = ""
            cont_extra = " " * len(existing)

    # If the body already starts with our prefix (a pre-stamped log line),
    # treat that as the prefix rather than doubling it.
    if prefix and body.startswith(prefix):
        first_extra = ""
        body_after = body[len(prefix):]
        cont_extra = " " * len(prefix)
        body = body_after

    initial = base + first_extra
    subsequent = base + cont_extra

    # Nothing to wrap, and no prefix/bullet to add: keep the line as-is.
    if not prefix and not (bullet and first_extra) and len(line) <= width:
        return line

    protected, found = _protect_paths(body)
    wrap_width = width
    # textwrap requires width > indent length; if the indent already fills
    # the line, leave the token on that line un-rewrapped.
    min_w = max(len(initial), len(subsequent)) + 1
    if wrap_width < min_w:
        return initial + _restore_paths(protected, found) if (first_extra or prefix) else line

    wrapper = textwrap.TextWrapper(
        width=wrap_width,
        break_long_words=False,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=True,
        initial_indent=initial,
        subsequent_indent=subsequent,
    )
    # TextWrapper.fill collapses a leading/trailing empty; wrap() on a single
    # paragraph is what we want.
    try:
        wrapped = wrapper.fill(protected)
    except ValueError:
        wrapped = initial + protected if (first_extra or prefix) else line
    wrapped = _restore_paths(wrapped, found)
    return wrapped


def wrap_lines(lines, **opts):
    """Wrap each string in `lines`; returns a new list (one or more lines per input)."""
    out = []
    for ln in lines:
        w = wrap(ln, **opts)
        out.extend(w.split("\n") if w != "" else [""])
    return out


def bullets(items, indent="", bullet=BULLET, width=WIDTH):
    """Format `items` as bulleted, wrapped lines (a single string)."""
    mark = BULLET if bullet is True else str(bullet)
    return "\n".join(wrap(str(it), width=width, indent=indent, bullet=mark) for it in items)


def format_log(message, stamp=None, width=WIDTH):
    """A dated fix-log entry, wrapped so continuations sit under the message."""
    if stamp is None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    # Allow the caller to pass an already-stamped line.
    mo = _STAMP_RE.match(message)
    if mo:
        prefix, body = mo.group(1), message[mo.end():]
    else:
        prefix, body = stamp + "  ", message
    return wrap(body, width=width, prefix=prefix)


def write_log(fh, message, stamp=None, width=WIDTH):
    fh.write(format_log(message, stamp=stamp, width=width) + "\n")


def rejoin_wrapped(text):
    """Rebuild logical lines from wrap() output (for parsers that read one fact per line).

    A line that starts with whitespace and has no leading timestamp is a
    continuation of the previous line: it is joined with a single space.
    """
    if not text:
        return text
    trailing_nl = str(text).endswith("\n")
    out, pending = [], None
    for ln in str(text).splitlines():
        if pending is not None and ln[:1] in " \t" and not _STAMP_RE.match(ln.lstrip()):
            pending = pending + " " + ln.strip()
            continue
        if pending is not None:
            out.append(pending)
        pending = ln
    if pending is not None:
        out.append(pending)
    result = "\n".join(out)
    if trailing_nl:
        result += "\n"
    return result


def rejoin_wrapped_bytes_lines(lines):
    """The same join, over an iterable of bytes lines (complete, including newline).

    Yields joined logical lines as bytes, each ending with b'\\n' when the last
    piece did. A final incomplete line is yielded as-is (caller decides).
    """
    pending = None
    for raw in lines:
        if not raw:
            continue
        is_cont = raw[:1] in (b" ", b"\t")
        if pending is not None and is_cont:
            piece = raw.lstrip().rstrip(b"\r\n")
            # pending still has its original ending until we append
            if pending.endswith(b"\r\n"):
                pending = pending[:-2] + b" " + piece + b"\r\n"
            elif pending.endswith(b"\n"):
                pending = pending[:-1] + b" " + piece + b"\n"
            else:
                pending = pending + b" " + piece
            continue
        if pending is not None:
            yield pending
        pending = raw
    if pending is not None:
        yield pending


def printer(builtin_print=None):
    """A print() that wraps each logical line at WIDTH before writing."""
    bp = builtin_print or builtins.print

    def _print(*args, **kwargs):
        sep = kwargs.pop("sep", " ")
        end = kwargs.get("end", "\n")
        text = sep.join(str(a) for a in args)
        if "\r" in text or end == "\r":
            return bp(*args, **kwargs)
        wrapped = wrap(text)
        # wrap() already joined the arguments; do not pass sep again.
        kwargs = dict(kwargs)
        kwargs.pop("sep", None)
        return bp(wrapped, **kwargs)

    return _print


class _WrapWriter(io.TextIOBase):
    """Wrap complete lines written to an underlying text stream."""

    def __init__(self, inner, width=WIDTH, log_mode=False, close_inner=False):
        self._inner = inner
        self._buf = ""
        self._width = width
        self._log_mode = log_mode
        self._close_inner = close_inner

    def write(self, s):
        if not isinstance(s, str):
            return self._inner.write(s)
        self._buf += s
        # A progress line that uses CR and no newline: pass through.
        if "\r" in self._buf and "\n" not in self._buf:
            n = self._inner.write(self._buf)
            self._buf = ""
            return n
        out = []
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            out.append(self._wrap_line(line))
        if out:
            self._inner.write("\n".join(out) + "\n")
        return len(s)

    def _wrap_line(self, line):
        if self._log_mode:
            if "\t" in line or _LOG_HEADER_RE.match(line) or not line:
                return line
            mo = _STAMP_RE.match(line)
            if mo:
                return wrap(line[mo.end():], width=self._width, prefix=mo.group(1))
        return wrap(line, width=self._width)

    def flush(self):
        # input() prompts (and similar) flush a partial line: wrap it, do not
        # add a newline, so the cursor stays on the last prompt line.
        if self._buf:
            self._inner.write(self._wrap_line(self._buf))
            self._buf = ""
        return self._inner.flush()

    def close(self):
        # When wrapping sys.stdout/stderr we must not close the real stream
        # (IOBase.__del__ calls close() when a leftover wrapper is collected).
        try:
            self.flush()
        finally:
            if self._close_inner:
                self._inner.close()

    @property
    def closed(self):
        return self._inner.closed

    @property
    def encoding(self):
        return getattr(self._inner, "encoding", None)

    @property
    def name(self):
        return getattr(self._inner, "name", None)

    def fileno(self):
        return self._inner.fileno()

    def isatty(self):
        return self._inner.isatty()

    def writable(self):
        return True

    def readable(self):
        return False

    def __getattr__(self, name):
        return getattr(self._inner, name)


def open_log(path, mode="a", encoding="utf-8", **kwargs):
    """open() for a human fix-log: written lines are wrapped, TSV and '====' headers are not."""
    fh = open(path, mode, encoding=encoding, **kwargs)
    return _WrapWriter(fh, log_mode=True, close_inner=True)


def install(streams=None, width=WIDTH):
    """Wrap sys.stdout / sys.stderr (or the given streams) so complete lines wrap at WIDTH.

    Safe to call more than once. Returns a callable that restores the previous
    streams. input() prompts go through stdout and are wrapped on flush; the
    last prompt line is left without a trailing newline so typing still works.
    """
    if streams is None:
        streams = (sys, "stdout", sys, "stderr")
        # unpack as pairs below
    restored = []

    def _wrap_one_stream(owner, attr):
        inner = getattr(owner, attr)
        if isinstance(inner, _WrapWriter):
            return
        wrapped = _WrapWriter(inner, width=width)
        setattr(owner, attr, wrapped)
        restored.append((owner, attr, inner))

    # Allow install() with no args (sys.stdout/stderr) or an explicit list of (owner, attr).
    if streams is None or streams == (sys, "stdout", sys, "stderr"):
        _wrap_one_stream(sys, "stdout")
        _wrap_one_stream(sys, "stderr")
    else:
        for owner, attr in streams:
            _wrap_one_stream(owner, attr)

    def restore():
        for owner, attr, inner in restored:
            current = getattr(owner, attr)
            if isinstance(current, _WrapWriter):
                try:
                    current.flush()
                except Exception:
                    pass
            setattr(owner, attr, inner)

    return restore


class HelpFormatter(argparse.HelpFormatter):
    """argparse help wrapped at WIDTH, with the same hanging indent as wrap()."""

    def __init__(self, prog, indent_increment=2, max_help_position=24, width=None):
        super().__init__(prog, indent_increment, max_help_position, width if width is not None else WIDTH)

    def _fill_text(self, text, width, indent):
        text = re.sub(r"\s+", " ", text).strip()
        return wrap(text, width=width, indent=indent)

    def _split_lines(self, text, width):
        text = re.sub(r"\s+", " ", text).strip()
        return wrap(text, width=width).splitlines() or [""]


def parser(*args, **kwargs):
    """argparse.ArgumentParser with HelpFormatter (width WIDTH) as the default."""
    kwargs.setdefault("formatter_class", HelpFormatter)
    return argparse.ArgumentParser(*args, **kwargs)


# Used by tests and by callers that want a one-shot wrap of already-printed help.
def line_overlong(line, width=WIDTH):
    """True if `line` is wider than `width` and is not a single unbreakable token
    (after its leading indent is stripped)."""
    s = line.rstrip("\n")
    if len(s) <= width:
        return False
    body = s.lstrip(" \t")
    return len(body.split()) > 1
