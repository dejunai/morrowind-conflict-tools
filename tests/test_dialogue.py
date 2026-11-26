"""Dialogue checks on the merged topics (World._load_dial/_load_info, _check_chain, _check_info,
_check_condition, _check_result), each on a small generated plugin."""
import struct
import types

from conftest import m, plugin, rec, sub, z


def dial(name, dtype=0, deleted=False):
    body = (sub("NAME", z(name)) if name is not None else b"") + sub("DATA", bytes([dtype]))
    if deleted:
        body += sub("DELE", b"\0\0\0\0")
    return rec("DIAL", body)


def info(iid, prev="", nxt="", disp=0, text="Hello.", actor=None, conds=(), result=None, deleted=False,
         extra=b""):
    body = b""
    if iid is not None:
        body += sub("INAM", z(iid))
    body += sub("PNAM", z(prev)) + sub("NNAM", z(nxt))
    body += sub("DATA", struct.pack("<B3xibbbx", 0, disp, -1, -1, -1))
    if actor:
        body += sub("ONAM", z(actor))
    body += sub("NAME", text.encode("cp1252"))
    for raw, value in conds:
        body += sub("SCVR", raw.encode("cp1252"))
        if value is not None:
            body += sub("INTV", struct.pack("<i", value))
    if result is not None:
        body += sub("BNAM", result.encode("cp1252"))
    if deleted:
        body += sub("DELE", b"\0\0\0\0")
    return rec("INFO", body + extra)


def npc(id_, script=None):
    body = sub("NAME", z(id_)) + sub("FNAM", z("Someone"))
    if script:
        body += sub("SCRI", z(script))
    return rec("NPC_", body)


def script(id_, locals_=(), deleted=False):
    schd = id_.encode("cp1252").ljust(32, b"\0") + struct.pack("<5I", len(locals_), 0, 0, 0, 0)
    body = sub("SCHD", schd) + sub("SCVR", b"".join(n.encode("cp1252") + b"\0" for n in locals_))
    if deleted:
        body += sub("DELE", b"\0\0\0\0")
    return rec("SCPT", body)


def load(tmp_path, *files):
    """files: (file name, [records]); loaded in this order, then checked (no sound files)."""
    report = m.Report()
    world = m.World(report)
    for name, records in files:
        path = tmp_path / name
        plugin(path, [], records)
        world.load_plugin(str(path), name)
    world.check(None)
    return world, report


def issues(report, needle=""):
    return [i for i in report.issues if needle in i[4]]


def fix_for(report, needle):
    hits = [f for f in report.fixes if needle in f[4]]
    assert len(hits) == 1, (needle, report.fixes)
    return hits[0]


# ---------------------------------------------------------------- response chain (PNAM/NNAM)

def test_a_plugins_own_pnam_loop_is_an_error_with_a_relink_fix(tmp_path):
    _w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1", prev="2"), info("2", prev="1")]))
    hit = issues(r, "form a loop of 2 response(s)")
    assert len(hit) == 1 and hit[0][0] == "ERROR" and hit[0][1] == "a.esp"
    op = fix_for(r, "form a loop")[2]
    assert op[0] == "relink" and op[1] == frozenset({"1", "2"})


def test_links_from_different_plugins_never_count_as_a_loop(tmp_path):
    # b.esp moves the master's response 1 after 2: normal re-ordering, not a circle of b's own links
    _w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1"), info("2", prev="1")]),
                 ("b.esp", [dial("foo"), info("1", prev="2")]))
    assert not issues(r, "loop")


def test_self_link_and_missing_links(tmp_path):
    _w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1", prev="1"), info("2", prev="nosuch"),
                                      info("3", prev="2", nxt="gone")]))
    assert fix_for(r, "previous (PNAM) link points to itself")[2][0] == "relink"
    missing = issues(r, "points to 'nosuch', which does not exist")
    assert missing[0][0] == "ERROR" and fix_for(r, "'nosuch'")[2][0] == "relink"
    nnam = issues(r, "next (NNAM) link points to 'gone'")
    assert nnam[0][0] == "INFO"                  # the game places responses by PNAM; NNAM is advisory


def test_a_link_to_a_deleted_response_walks_back_to_the_last_live_one(tmp_path):
    _w, r = load(tmp_path,
                 ("a.esp", [dial("foo"), info("1"), info("2", prev="1"), info("3", prev="2"), info("4", prev="3")]),
                 ("b.esp", [dial("foo"), info("2", prev="1", deleted=True), info("3", prev="2", deleted=True)]))
    hit = issues(r, "points to '3', which has been deleted")
    assert len(hit) == 1 and hit[0][0] == "ERROR" and hit[0][3] == "4"
    assert r.bug_context[hit[0]][0] == frozenset({"b.esp"})
    assert fix_for(r, "points to '3'")[2] == ("set_prev", "1")


def test_a_deleted_first_response_moves_the_next_one_to_the_top(tmp_path):
    _w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1"), info("2", prev="1")]),
                 ("b.esp", [dial("foo"), info("1", deleted=True)]))
    assert fix_for(r, "points to '1', which has been deleted")[2] == ("set_prev", "")


def test_a_next_link_to_a_deleted_response_is_only_info(tmp_path):
    _w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1", nxt="2"), info("2", prev="1")]),
                 ("b.esp", [dial("foo"), info("2", prev="1", deleted=True)]))
    hit = issues(r, "next (NNAM) link points to '2', which has been deleted")
    assert hit and hit[0][0] == "INFO" and not r.fixes


# ---------------------------------------------------------------- conditions

def cond(idx, ctype, op, name, func="XX"):
    return f"{idx}{ctype}{func}{op}{name}"


def test_missing_item_condition_that_always_passes_drops_the_condition(tmp_path):
    raw = cond(0, "5", "0", "no_such_item")        # count == 0: a missing item's count is always 0
    _w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1", conds=[(raw, 0)])]))
    assert fix_for(r, "item condition names 'no_such_item'")[2] == ("drop_cond", raw)


def test_missing_item_condition_that_never_passes_deletes_the_response(tmp_path):
    raw = cond(0, "5", "2", "no_such_item")        # count > 0: never, for a missing item
    _w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1", conds=[(raw, 0)])]))
    assert fix_for(r, "item condition names 'no_such_item'")[2] == ("delete",)


def test_an_item_condition_naming_an_npc_is_a_warning(tmp_path):
    _w, r = load(tmp_path, ("a.esp", [npc("some_npc"), dial("foo"),
                                      info("1", conds=[(cond(0, "5", "0", "some_npc"), 1)])]))
    hit = issues(r, "which is a NPC_ rather than an item")
    assert hit and hit[0][0] == "WARN"


def test_missing_quest_condition(tmp_path):
    never = cond(0, "4", "2", "no_quest")          # index > 10: never, for a missing quest (always 0)
    always = cond(1, "4", "4", "no_quest")         # index < 10: always
    _w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1", conds=[(never, 10)]), info("2", prev="1", conds=[(always, 10)])]))
    ops = sorted(f[2][0] for f in r.fixes if "journal 'no_quest'" in f[4])
    assert ops == ["delete", "drop_cond"]


def test_a_journal_condition_on_a_plain_topic_is_an_error(tmp_path):
    _w, r = load(tmp_path, ("a.esp", [dial("plain"), info("p1"),
                                      dial("foo"), info("1", conds=[(cond(0, "4", "0", "plain"), 1)])]))
    hit = issues(r, "condition checks journal 'plain', but that topic is a Topic")
    assert hit and hit[0][0] == "ERROR"


def test_global_and_malformed_and_valueless_conditions(tmp_path):
    _w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1", conds=[(cond(0, "2", "0", "no_global"), 1)]),
                                      info("2", prev="1", conds=[("0Z", 1)]),
                                      info("3", prev="2", conds=[(cond(0, "5", "0", "gold_001"), None)])]))
    assert fix_for(r, "global 'no_global'")[2] == ("delete",)
    assert fix_for(r, "malformed condition '0Z'")[2] == ("drop_cond", "0Z")
    assert fix_for(r, "has no comparison value")[2][0] == "drop_cond"


def local_world(tmp_path, ctype, var, speaker="talker", with_script=True):
    records = [npc("talker", "talkerscript" if with_script else None), script("talkerscript", ["myvar"]),
               dial("foo"), info("1", actor=speaker, conds=[(cond(0, ctype, "0", var), 1)])]
    return load(tmp_path, ("a.esp", records))


def test_local_on_an_undeclared_variable_can_never_pass(tmp_path):
    _w, r = local_world(tmp_path, "3", "othervar")
    assert fix_for(r, "not declared in speaker's script 'talkerscript'")[2] == ("delete",)


def test_not_local_on_an_undeclared_variable_is_only_info(tmp_path):
    _w, r = local_world(tmp_path, "C", "othervar")
    hit = issues(r, "not declared in speaker's script")
    assert hit and hit[0][0] == "INFO" and not r.fixes


def test_local_on_a_declared_variable_is_fine(tmp_path):
    _w, r = local_world(tmp_path, "3", "MyVar")              # case-insensitive
    assert not issues(r, "condition")


def test_local_when_the_speaker_has_no_script(tmp_path):
    (tmp_path / "local").mkdir()
    (tmp_path / "notlocal").mkdir()
    _w, r = local_world(tmp_path / "local", "3", "myvar", with_script=False)
    assert fix_for(r, "but speaker 'talker' has no script")[2] == ("delete",)
    _w, r = local_world(tmp_path / "notlocal", "C", "myvar", with_script=False)
    hit = issues(r, "but speaker 'talker' has no script")
    assert hit and hit[0][0] == "INFO" and not r.fixes


def test_a_deleted_speaker_and_script_leave_no_stale_script_data(tmp_path):
    w, r = load(tmp_path, ("a.esp", [npc("talker", "talkerscript"), script("talkerscript", ["myvar"])]),
                ("b.esp", [rec("NPC_", sub("NAME", z("talker")) + sub("DELE", b"\0\0\0\0")),
                           script("talkerscript", deleted=True),
                           dial("foo"), info("1", actor="talker", conds=[(cond(0, "3", "0", "othervar"), 1)])]))
    assert "talker" not in w.actor_script and "talkerscript" not in w.script_locals
    # the missing speaker is the one thing reported, not a second, misleading "has no script"
    assert issues(r, "speaker ID (ONAM) 'talker' is not an NPC or creature")
    assert not issues(r, "Local condition")


# ---------------------------------------------------------------- result scripts

def test_result_script_addtopic_and_journal(tmp_path):
    result = "\n".join([
        'AddTopic "nosuch"',              # missing: commented out by the fix
        'addtopic "REAL TOPIC"',          # any case, quoted with a space: fine
        "AddTopic greet",                 # a Greeting, not a Topic
        '; AddTopic "commented"',         # already a comment: ignored
        'Journal "myquest" 20',           # quest exists, stage 20 doesn't
        "SetJournalIndex, myquest, 10",   # fine
        'Journal "real topic" 10',        # not a journal
        'GetJournalIndex "nosuchquest"',  # a function, not Journal: ignored
    ])
    _w, r = load(tmp_path, ("a.esp", [dial("real topic"), info("t1"), dial("greet", 2), info("g1"),
                                      dial("myquest", 4), info("q1", disp=10),
                                      dial("foo"), info("1", result=result)]))
    msgs = sorted(i[4] for i in r.issues if "result script" in i[4])
    assert msgs == ["result script adds topic 'greet', which is a Greeting, not a Topic",
                    "result script adds topic 'nosuch', which does not exist",
                    "result script sets journal 'myquest' to index 20, which has no entry",
                    "result script sets journal 'real topic', which is a Topic"]
    op = fix_for(r, "adds topic 'nosuch'")[2]
    assert op == ("comment", 'AddTopic "nosuch"')


# ---------------------------------------------------------------- topics and records

def test_unknown_dialogue_type(tmp_path):
    _w, r = load(tmp_path, ("a.esp", [dial("foo", 7), info("1")]))
    assert issues(r, "topic has unknown dialogue type 7")


def test_topic_type_change_current_behavior(tmp_path):
    """Documents CURRENT behavior only: the change is reported, and the topic keeps the first plugin's type
    for every later response. Which type the game itself uses is unverified; don't read this as the spec."""
    w, r = load(tmp_path, ("a.esp", [dial("foo", 0), info("1")]),
                ("b.esp", [dial("foo", 4), info("2", disp=10)]))
    hit = issues(r, "changes topic type from Topic (set by a.esp) to Journal")
    assert hit and hit[0][0] == "ERROR" and hit[0][1] == "b.esp"
    assert w.topics["foo"].dtype == 0 and w.topics["foo"].infos["2"].dtype == 0


def test_deleted_then_re_added_topic_current_behavior(tmp_path):
    """Documents CURRENT behavior only: responses from before the topic was deleted stay in it once a later
    plugin adds the topic back, so a link to them is not flagged. Whether the game drops them is unverified."""
    w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1")]),
                ("b.esp", [dial("foo", deleted=True)]),
                ("c.esp", [dial("foo"), info("2", prev="1")]))
    assert list(w.topics["foo"].infos) == ["1", "2"] and not w.topics["foo"].deleted
    assert not issues(r, "link")


def test_a_deleted_topic_is_not_checked(tmp_path):
    _w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1", prev="nosuch")]),
                 ("b.esp", [dial("foo", deleted=True)]))
    assert not issues(r, "nosuch") and not issues(r, "no live responses")


def test_duplicate_response_in_one_dial_block(tmp_path):
    _w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1"), info("1")]))
    f = fix_for(r, "response ID appears twice under this topic in the same file")
    first_info_off = [off for off, tag, _f, _b in m.iter_records((tmp_path / "a.esp").read_bytes()) if tag == "INFO"][0]
    assert f[1] == first_info_off and f[2] == ("delete", "local")


def test_duplicate_response_across_two_blocks_of_one_topic_in_one_file(tmp_path):
    _w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1"), dial("bar"), info("x"), dial("FOO"), info("1")]))
    assert len(issues(r, "appears twice under this topic in the same file")) == 1


def test_same_id_in_another_topic_or_file_is_not_a_duplicate(tmp_path):
    _w, r = load(tmp_path, ("a.esp", [dial("foo"), info("1"), dial("bar"), info("1")]),
                 ("b.esp", [dial("foo"), info("1")]))
    assert not issues(r, "appears twice")
    hit = issues(r, "response ID is also used under topic 'foo' (harmless)")
    assert hit and hit[0][0] == "INFO"


def test_orphaned_response_and_response_without_id(tmp_path):
    glob = rec("GLOB", sub("NAME", z("g")) + sub("FNAM", b"s") + sub("FLTV", struct.pack("<f", 0)))
    _w, r = load(tmp_path, ("a.esp", [info("lost"), dial("foo"), info("1"), glob, info("2"), dial("bar"), info(None)]))
    orphans = issues(r, "is not preceded by a DIAL topic")
    assert len(orphans) == 2 and all(f[2] == ("delete", "local") for f in r.fixes if "orphaned" in f[4])
    assert fix_for(r, "has no INAM")[2] == ("delete", "local")


def test_nameless_topics_get_placeholder_names(tmp_path):
    _w, r = load(tmp_path, ("a.esp", [dial(None), info("1"), dial(None), info("2")]))
    names = [f[2] for f in r.fixes if f[2][0] == "set_name"]
    assert names == [("set_name", "error topic name"), ("set_name", "error topic name 2")]


def test_a_nameless_topic_in_a_master_is_moved_by_the_patch(tmp_path):
    _w, r = load(tmp_path, ("a.esm", [dial(None), info("1")]))
    hit = issues(r, "has no name (shown here as 'error topic name (a.esm)')")
    assert hit and "moved its responses" in fix_for(r, "has no name")[3]


# ---------------------------------------------------------------- plugin count limits

def test_plugin_limit_notes():
    assert m.plugin_limit_notes(m.VANILLA_PLUGIN_LIMIT) == []
    assert "MWSE is needed" in m.plugin_limit_notes(m.VANILLA_PLUGIN_LIMIT + 1)[0]
    assert m.plugin_limit_notes(m.PLUGIN_LIMIT)[0].startswith("Note:")
    over = m.plugin_limit_notes(m.PLUGIN_LIMIT + 3)
    assert over[0].startswith("WARNING:") and "the last 3 won't load" in over[0]


def test_load_order_past_the_plugin_limit_is_reported(tmp_path):
    data = tmp_path / "Data Files"
    data.mkdir()
    names = [f"p{i:04d}.esm" for i in range(m.PLUGIN_LIMIT + 2)]
    for n in names:
        (data / n).write_bytes(b"")
    args = types.SimpleNamespace(data_dir=str(data), plugins=names, openmw_cfg=None)
    r = m.Report()
    plugins = m.resolve(args, r)[0]
    assert len(plugins) == m.PLUGIN_LIMIT + 2
    hit = issues(r, f"MWSE/MGE XE load at most {m.PLUGIN_LIMIT}")
    assert len(hit) == 1 and hit[0][0] == "WARN" and hit[0][1] == names[m.PLUGIN_LIMIT]
    r2 = m.Report()
    m.resolve(types.SimpleNamespace(data_dir=str(data), plugins=names[:m.PLUGIN_LIMIT], openmw_cfg=None), r2)
    assert not r2.issues
