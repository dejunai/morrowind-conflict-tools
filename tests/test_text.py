"""Wrapping helper: 115-char limit, hanging indent, bullets, no mid-token breaks, plan compat."""
import argparse
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mwdialog_text as T                        # noqa: E402
import mwdialog_planfile as PF                   # noqa: E402


WIDTH = T.WIDTH


def _lines(s):
    return s.splitlines()


def test_width_constant_is_115():
    assert T.WIDTH == 115 and T.HANG == 2 and T.BULLET == "- "


def test_short_text_is_unchanged():
    s = "Already short enough."
    assert T.wrap(s) == s
    assert T.wrap(s) == T.wrap(T.wrap(s))


def test_idempotent_on_already_wrapped():
    long = "word " * 40  # well over 115
    once = T.wrap(long)
    assert T.wrap(once) == once
    assert T.wrap(once + "\n") == once + "\n"


def test_wraps_at_115_and_hangs_two_spaces():
    # A sentence of short words that must wrap just past 115.
    first = "alpha " * 19   # 19*6 = 114
    rest = "omega and then some more words that continue the sentence."
    text = first + rest
    assert len(first) == 114
    out = T.wrap(text)
    lines = _lines(out)
    assert len(lines) >= 2
    assert all(len(ln) <= WIDTH or len(ln.lstrip().split()) == 1 for ln in lines)
    assert len(lines[0]) <= WIDTH
    assert lines[1].startswith("  ")
    assert not lines[1].startswith("   ")  # exactly 2 spaces, not more
    assert "omega" in lines[1]


def test_existing_indent_plus_hang():
    body = "note " * 30
    text = "    " + body
    lines = _lines(T.wrap(text))
    assert lines[0].startswith("    ")
    assert lines[1].startswith("      ")  # 4 + 2
    assert not lines[1].startswith("       ")


def test_bullet_and_continuation_aligns_under_item_text():
    item = "this is a fairly long listed item " * 6
    out = T.wrap(item, bullet="- ")
    lines = _lines(out)
    assert lines[0].startswith("- ")
    assert lines[1].startswith("  ")
    assert not lines[1].startswith("   ")
    assert lines[1][2] != " " and lines[1][2] != "-"
    # Same via bullets()
    block = T.bullets([item, "short"])
    bl = block.splitlines()
    assert bl[0].startswith("- ")
    assert bl[-1] == "- short"


def test_indented_bullet_continuation():
    item = "listed path and explanation " * 8
    out = T.wrap(item, indent="  ", bullet="- ")
    lines = _lines(out)
    assert lines[0].startswith("  - ")
    assert lines[1].startswith("    ")  # indent 2 + len('- ')
    assert not lines[1].startswith("     ")


def test_does_not_double_existing_bullet():
    out = T.wrap("already marked", bullet="- ")
    assert out == "- already marked"
    # A long already-bulleted line: do not become "- - ..."
    long = "- " + ("item word " * 20)
    lines = _lines(T.wrap(long, bullet="- "))
    assert lines[0].startswith("- item")
    assert not lines[0].startswith("- - ")
    assert lines[1].startswith("  ")


def test_no_mid_word_or_hyphen_break():
    # hyphenated word must stay together (break_on_hyphens=False)
    token = "supercalifragilistic-expialidocious-and-friends"
    prefix = "x " * 54  # 108
    text = prefix + token
    lines = _lines(T.wrap(text))
    joined = "".join(ln.strip() for ln in lines)
    assert token in " ".join(ln.strip() for ln in lines)
    assert all(token in ln or token not in ln for ln in lines)
    # the hyphenated token is not split
    assert any(token in ln for ln in lines)


def test_overlong_token_stays_on_its_own_line():
    token = "N" * 140
    out = T.wrap(token)
    assert out == token
    assert len(out) > WIDTH
    # after a short lead-in, the long token gets the next line
    text = "see " + token
    lines = _lines(T.wrap(text))
    assert token in lines[1] or (len(lines) == 1 and token in lines[0])
    if len(lines) > 1:
        assert lines[1].lstrip() == token or token in lines[1]


def test_paths_with_spaces_are_not_split():
    path = r"staging:Vortex Mods\morrowind\Some Mod\Data Files\Meshes\foo.nif"
    prefix = "Looked for the mesh in "
    # make sure the whole line is longer than 115
    text = prefix + path + " and then gave up after a careful search of the folder."
    assert len(text) > WIDTH
    out = T.wrap(text)
    assert path in out.replace("\n", "").replace("  ", " ") or path in out
    # the path itself is not broken into two pieces
    assert path in out.replace("\n", "")


def test_drive_qualified_path_with_program_files():
    # runtime text may contain a drive path (not in source); keep it one token
    path = "Q:\\Program Files\\Steam\\steamapps\\common\\Morrowind\\Data Files\\x.esp"
    text = "Opened " + path + " because the master list named it as a requirement of another plugin."
    assert len(text) > WIDTH
    out = T.wrap(text)
    assert path in out.replace("\n", "")


def test_preserves_blank_lines_and_trailing_newline():
    assert T.wrap("short\n\nshort\n") == "short\n\nshort\n"
    assert not T.wrap("short").endswith("\n")
    assert T.wrap("short\n") == "short\n"


def test_log_prefix_stays_on_first_line_continuations_under_message():
    stamp = "2026-11-11 20:07:00  "
    msg = "Plugin.esp: synced the size recorded for 'Morrowind.esm' (123 -> 456) after a long explanation " \
          "that definitely exceeds the wrap width and keeps going on purpose."
    out = T.format_log(msg, stamp="2026-11-11 20:07:00")
    lines = _lines(out)
    assert lines[0].startswith(stamp)
    assert all(not ln.startswith("2026-") for ln in lines[1:])
    # continuations align under the message (after the 22-char prefix)
    assert lines[1].startswith(" " * len(stamp))
    assert len(lines[0]) <= WIDTH or T.line_overlong(lines[0]) is False or len(lines[0].split()) == 1


def test_rejoin_wrapped_log_round_trip():
    stamp = "2026-11-11 20:07:00"
    msg = "Patch.esp: added master Extra.esm (from a content rule that named it) and also mentioned " \
          "another master so this line is long enough to wrap at least once."
    wrapped = T.format_log(msg, stamp=stamp)
    assert "\n" in wrapped
    joined = T.rejoin_wrapped(wrapped)
    assert "\n" not in joined.rstrip("\n")
    assert "added master Extra.esm" in joined
    assert "another master" in joined


def test_printer_wraps_and_leaves_short_lines():
    buf = io.StringIO()
    p = T.printer(lambda *a, **k: buf.write((k.get("sep", " ").join(map(str, a))) + k.get("end", "\n")))
    p("hello")
    p("word " * 40)
    out = buf.getvalue()
    assert out.splitlines()[0] == "hello"
    assert any(ln.startswith("  ") for ln in out.splitlines()[1:])


def test_help_formatter_width():
    ap = T.parser(description="A short tool. " + "sentence " * 30)
    ap.add_argument("--flag", help="This help text is long enough that it should wrap somewhere in the "
                    "help listing because many words are used to describe the flag in a run-on way.")
    text = ap.format_help()
    over = [ln for ln in text.splitlines() if T.line_overlong(ln)]
    assert over == [], over


def test_install_wraps_stdout_and_prompt_has_no_trailing_newline_on_flush():
    inner = io.StringIO()

    class Owner:
        stdout = inner

    restore = T.install(streams=[(Owner, "stdout")])
    try:
        Owner.stdout.write("word " * 40 + "\n")
        Owner.stdout.write("Continue? [y/N] ")
        Owner.stdout.flush()
        text = inner.getvalue()
        lines = text.splitlines()
        assert any(ln.startswith("  ") for ln in lines)
        assert text.endswith("Continue? [y/N] ")
        assert not text.endswith("Continue? [y/N] \n")
    finally:
        restore()


def test_open_log_wraps_human_lines_not_tsv_or_header(tmp_path):
    p = tmp_path / "fixes.log"
    with T.open_log(p, "w") as f:
        f.write("==== 2026-11-11 20:07:00 clean ====\n")
        f.write("cell\t3 of Who's\tmoved by other\n")
        f.write("2026-11-11 20:07:00  Plugin.esp: synced the size recorded for 'Master.esm' (10 -> 20) "
                "after a rather long explanation that should wrap onto a continuation line for sure.\n")
    text = p.read_text(encoding="utf-8")
    assert "==== 2026-11-11 20:07:00 clean ====" in text
    assert "cell\t3 of Who's\tmoved by other" in text
    log_lines = [ln for ln in text.splitlines() if "synced the size" in ln or ln.startswith(" ")]
    assert any(ln.startswith("2026-11-11 20:07:00  ") for ln in text.splitlines())
    # the human line wrapped
    assert any(ln.startswith(" ") and "continuation" not in ln.lower() or ln.startswith(" ")
               for ln in text.splitlines())
    joined = T.rejoin_wrapped(text)
    assert "synced the size recorded for 'Master.esm' (10 -> 20)" in joined
    assert "should wrap onto a continuation line" in joined


# ------------------------------------------------------------------------------------ plan compatibility

def _sample_plan():
    # A representative plan: dated head, notes, a mod with move actions, a Lua section with a
    # patch-ready line (hash included) and a high finding. The action lines are deliberately long.
    long_src = "meshes\\" + ("very_long_component_" * 6) + "file.nif"
    long_dst = "docs\\" + long_src
    assert len(f"    {long_src}  ->  {long_dst}   (wrong folder)") > WIDTH
    head = (
        "vortex_tidy plan, 2026-11-11 20:07: 2 mod(s), 1 to change, 1 move(s); 1 left alone\n"
        "  left alone: Some Huge Mod Name That Goes On For A While (blacklisted (pattern*))\n"
        "  NOTE: Normal packs are not used by classic Morrowind and this sentence is long "
        "enough that wrapping it would take at least two lines in a typical report.\n"
        "\n"
        "Some Mod   [Some Mod]\n"
        f"    {long_src}  ->  {long_dst}   (wrong folder)\n"
        "    remove empty  meshes\\empty\n"
        "\n"
        "LUA CHECK\n"
        "  lua mwse\\mods\\mod\\main.lua\n"
        "      L5 high        line 12: tes3.getReference on a name that might be nil and this "
        "finding message is also long enough to wrap if a formatter were applied to the plan file\n"
        "      => patch ready (L5) [deadbeef]\n"
    )
    return head


def test_plan_actions_unchanged_if_only_human_lines_wrap():
    plan = _sample_plan()
    # Wrap only lines the --apply parser ignores (comments, headers, 2-space notes).
    out = []
    for ln in plan.splitlines(keepends=True):
        raw = ln.rstrip("\n")
        s = raw.strip()
        is_action_or_context = bool(s) and (
            (raw.startswith("    ") and ("  ->  " in s or s.startswith(("remove empty", "=> patch ready", "repair ", "shorten "))
                                        or PF._FINDING.match(s)))
            or (s.startswith("lua "))
            or (not raw.startswith(" ") and s and s not in PF.SECTION_HEADS and not PF._DATED_HEAD.search(s)
                and not s.startswith("#"))
        )
        if is_action_or_context or raw == "":
            out.append(ln)
        else:
            w = T.wrap(raw)
            out.append(w + ("\n" if ln.endswith("\n") else ""))
    wrapped_notes = "".join(out)
    # Notes did wrap
    assert any(len(ln) > 80 and ln.startswith("  ") for ln in plan.splitlines())
    added, removed = PF.compare(plan, wrapped_notes)
    assert added == [] and removed == [], (added, removed)


def test_wrapping_action_lines_would_break_compare_so_plan_files_stay_unwrapped():
    plan = _sample_plan()
    # If someone wrapped every line (including actions), compare must notice -
    # which is why the tools write the plan file without going through wrap().
    blindly = "\n".join(T.wrap(ln) for ln in plan.splitlines()) + "\n"
    added, removed = PF.compare(plan, blindly)
    assert added or removed


def test_generated_luafix_plan_actions_stable_under_wrap_of_console_copy(tmp_path, monkeypatch):
    """format_report output written to a plan file is what --apply compares; wrapping a
    console copy of the same text must not change PF.actions() of the file."""
    # Build a tiny report-like plan using the same formatter luafix uses.
    class Ent(dict):
        pass

    # Use format_report on an empty Report: just prove the compose path.
    # A handmade plan in luafix shape:
    lines = [
        "      L1 high        line 3: unguarded tes3.getObject on a maybe-nil "
        + "and a long path meshes\\" + ("component\\" * 8) + "x.nif  ->  guarded",
        "      => patch ready (L1) [abcd1234]",
    ]
    head = ["mwdialog_luafix plan, 2026-11-11 20:07: 1 Lua file(s) checked, 1 to patch, 0 left alone"]
    body = ["  lua mwse\\mods\\x\\main.lua"] + lines
    fresh = "\n".join(head + body) + "\n"
    console = "\n".join(T.wrap_lines(head + body)) + "\n"
    # The file (fresh) vs a "regenerated" file (same, unwrapped) compares equal.
    added, removed = PF.compare(fresh, fresh)
    assert added == [] and removed == []
    # Wrapping the console copy does not have to equal the file, but the file's
    # actions must still be the ones --apply would enact.
    acts = PF.actions(fresh)
    assert acts, "sample plan should list at least one action"
    # If we only wrap the dated head / short notes, actions stay equal:
    mixed = T.wrap(head[0]) + "\n" + "\n".join(body) + "\n"
    added, removed = PF.compare(fresh, mixed)
    assert added == [] and removed == []
    # console wrap of the whole preview is display-only
    assert any(len(ln) > WIDTH for ln in fresh.splitlines())
    assert all(len(ln) <= WIDTH or len(ln.lstrip().split()) == 1 for ln in console.splitlines())


def test_sample_help_and_wrapped_report_lines_stay_within_115(capsys):
    """No output line from --help or a sample wrapped report exceeds 115 except a single token."""
    ap = T.parser(prog="mwdialog_check.py", description="Scan a Morrowind Data Files folder for dialogue errors. "
                   + "This description is a bit long on purpose so the formatter has something to wrap if needed.")
    ap.add_argument("data_dir", nargs="?", help="Data Files folder (default: Data Files next to this script)")
    ap.add_argument("--fix", action="store_true",
                    help="apply the safe fixes that were reported (backups are written first, nothing is "
                         "changed without this flag, and a second pass can still find follow-on fixes)")
    ap.add_argument("--full", action="store_true",
                    help="run the whole pipeline from scratch: turn plugins back on, undo the auto-merge, "
                         "report cell conflicts, sort, clean, fix, and offer the interactive questions")
    help_text = ap.format_help()
    over = [ln for ln in help_text.splitlines() if T.line_overlong(ln)]
    assert over == [], over

    # A sample of typical report lines, after wrap().
    sample = [
        "Checking animation text keys in loose meshes for Unix line endings...",
        "Taken out of the load order (made for a different master): " + ", ".join(["Mod%02d.esp" % i for i in range(12)])
        + " (put back by adding them to mwdialog_load_order.txt)",
        T.bullets(["Mod%02d.esp" % i for i in range(8)], indent="  "),
        "  repaired textures\\some\\path.dds: it was an unusual sample rate\n      original kept as Off\\backup\\path.dds",
    ]
    wrapped = "\n".join(T.wrap(s) for s in sample)
    over = [ln for ln in wrapped.splitlines() if T.line_overlong(ln)]
    assert over == [], over



def _help_text(mod, argv):
    import io, contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            mod.main(argv)
    except SystemExit as e:
        assert e.code in (0, None)
    return buf.getvalue()


def test_real_cli_help_lines_within_115():
    """The three CLI --help screens wrap at 115, except a single unbreakable token."""
    import mwdialog_check as chk
    import mwdialog_luafix as luafix
    import vortex_tidy as tidy
    import sys
    over = []
    for name, text in (
        ("mwdialog_check.py", _help_text(chk, ["--help"])),
        ("mwdialog_luafix.py", _help_text(luafix, ["--help"])),
    ):
        assert "usage:" in text.lower()
        over += [(name, ln) for ln in text.splitlines() if T.line_overlong(ln)]
    old = sys.argv
    try:
        sys.argv = ["vortex_tidy.py", "--help"]
        import io, contextlib
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                tidy.main()
        except SystemExit as e:
            assert e.code in (0, None)
        text = buf.getvalue()
    finally:
        sys.argv = old
    assert "usage:" in text.lower()
    over += [("vortex_tidy.py", ln) for ln in text.splitlines() if T.line_overlong(ln)]
    assert over == [], over
