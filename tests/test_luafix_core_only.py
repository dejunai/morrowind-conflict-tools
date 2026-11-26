"""mwdialog_luafix --core-only: check and patch only the MWSE core files a Known Bugs rule names (KB3/KB4 on
ExclusionsPage.lua), with a result per file, a dry run, the journal and --undo, and the usual refusals."""
import json
import os
import shutil

import pytest

from conftest import _load

lf = _load("mwdialog_luafix")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "mwse")
REL = "core/mcm/components/pages/exclusionspage.lua"
DISK = ("MWSE", "core", "mcm", "components", "pages", "ExclusionsPage.lua")
CFG = dict(lf.DEFAULTS)


class OkChecker:
    name = "fake"

    def __init__(self, reject_new=False):
        self.reject_new = reject_new

    def check(self, text):
        if self.reject_new and "localpatch" in text:
            return False, "line 1: rejected"
        return True, ""


def stock():
    with open(os.path.join(FIX, "ExclusionsPage.lua"), "rb") as f:
        return f.read().replace(b"\r\n", b"\n")           # the fixtures are LF whatever the checkout did


def paged():
    with open(os.path.join(FIX, "ExclusionsPage.paged.lua"), "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


class Game:
    def __init__(self, tmp_path, text=None):
        self.game = tmp_path / "Morrowind"
        self.data = self.game / "Data Files"
        self.core = self.data.joinpath(*DISK)
        self.journal = str(tmp_path / "state" / "journal.jsonl")
        self.backups = str(tmp_path / "state" / "backups")
        if text is not False:
            self.core.parent.mkdir(parents=True)
            self.core.write_bytes(stock() if text is None else text)
        else:
            self.data.mkdir(parents=True)

    def run(self, dry_run=False, checker=None, **kw):
        return lf.apply_core_known_bugs(str(self.data), dry_run, game_dir=str(self.game), cfg=CFG,
                                        checker=OkChecker() if checker is None else checker,
                                        journal=self.journal, backup_root=self.backups, **kw)

    def journal_runs(self):
        return lf._read_runs(self.journal) if os.path.exists(self.journal) else []


def one(results):
    (r,) = results
    return r


def test_applied_writes_once_with_backup_and_journal_entry(tmp_path):
    g = Game(tmp_path)
    r = one(g.run())
    assert r.status == "applied" and r.written and not r.dry_run
    assert r.kb_ids == ["KB3", "KB4"] and r.rel == REL
    assert (r.parts_matched, r.parts_total) == (4, 4)
    assert os.path.normcase(r.path) == os.path.normcase(str(g.core))
    new = g.core.read_bytes()
    assert new.startswith(b"--[[localpatch ") and new.split(b"]] ", 1)[1] == paged()
    assert r.sha1_before == lf.sha(stock()) and r.sha1_after == lf.sha(new)
    (run,) = g.journal_runs()
    assert run["head"]["core_only"] is True and run["head"]["entry"] == r.journal_entry
    (op,) = run["ops"]
    assert op["luafix"] == r.path and op["backup"] == r.backup and op["rules"] == ["KB3", "KB4"]
    with open(r.backup, "rb") as f:
        assert f.read() == stock()                                   # the file as it was
    assert [k["state"] for k in r.kbs] == ["matches", "matches"]


def test_dry_run_reports_applied_but_writes_nothing(tmp_path):
    g = Game(tmp_path)
    r = one(g.run(dry_run=True))
    assert r.status == "applied" and r.dry_run and not r.written
    assert r.journal_entry is None and r.backup is None
    assert r.sha1_after == lf.sha(b"--[[localpatch %d: KB3 KB4]] " % lf.VERSION + paged())
    assert g.core.read_bytes() == stock()
    assert not os.path.exists(g.journal) and not os.path.exists(g.backups)


def test_undo_after_applied_puts_the_original_back(tmp_path):
    g = Game(tmp_path)
    r = one(g.run())
    assert g.core.read_bytes() != stock()
    logs = []
    assert lf.undo(journal=g.journal, log=logs.append) == 0
    assert g.core.read_bytes() == stock()
    assert g.journal_runs() == []
    assert r.status == "applied"
    again = one(g.run(dry_run=True))                                 # fixable again
    assert again.status == "applied"


def test_undo_refuses_a_core_file_changed_since(tmp_path):
    g = Game(tmp_path)
    one(g.run())
    g.core.write_bytes(g.core.read_bytes() + b"\n-- edited by hand\n")
    assert lf.undo(journal=g.journal, log=lambda s: None) == 1       # the journal's SHA-1 check still applies


def test_already_patched_has_header_and_no_fingerprint(tmp_path):
    g = Game(tmp_path)
    one(g.run())
    patched = g.core.read_bytes()
    r = one(g.run())
    assert r.status == "already-patched" and not r.written and r.journal_entry is None
    assert r.parts_matched == 0 and [k["state"] for k in r.kbs] == ["already-patched"] * 2
    assert g.core.read_bytes() == patched
    assert len(g.journal_runs()) == 1                                # no second run was journaled


def test_no_match_when_upstream_fixed_it(tmp_path):
    g = Game(tmp_path, text=b"-- upstream rewrote this page\nlocal x = 1\n")
    before = g.core.read_bytes()
    r = one(g.run())
    assert r.status == "no-match" and not r.written and r.parts_matched == 0
    assert r.parts_total == 4 and [k["state"] for k in r.kbs] == ["no-match"] * 2
    assert g.core.read_bytes() == before and not os.path.exists(g.journal)


def test_the_fixed_upstream_file_is_no_match_not_already_patched(tmp_path):
    g = Game(tmp_path, text=paged())                                 # the repaired text, with no header
    assert one(g.run()).status == "no-match"


def test_partial_when_a_whole_rule_matches_only_some_parts(tmp_path):
    changed = stock().replace(b"\n\n--- Constructor", b"\n-- changed upstream\n--- Constructor")
    assert changed != stock()
    g = Game(tmp_path, text=changed)
    r = one(g.run())
    assert r.status == "partial" and not r.written
    assert (r.parts_matched, r.parts_total) == (3, 4)                # KB3 1 of 1, KB4 2 of 3
    assert "KB4: only 2 of its 3 parts" in r.reason
    assert [(k["kb"], k["state"]) for k in r.kbs] == [("KB3", "matches"), ("KB4", "partial")]
    assert g.core.read_bytes() == changed                            # not even KB3, which does match
    assert not os.path.exists(g.journal)


def test_refused_when_the_core_file_is_missing(tmp_path):
    g = Game(tmp_path, text=False)
    r = one(g.run())
    assert r.status == "refused" and "not found" in r.reason and r.rel == REL and not r.written


def test_refused_without_a_syntax_checker_and_allowed_with_no_syntax_check(tmp_path):
    g = Game(tmp_path)
    r = one(lf.apply_core_known_bugs(str(g.data), False, game_dir=str(g.game), cfg=CFG, checker=None,
                                     journal=g.journal, backup_root=g.backups))
    assert r.status == "refused" and "syntax check" in r.reason and not r.written
    assert g.core.read_bytes() == stock()
    r = one(lf.apply_core_known_bugs(str(g.data), False, game_dir=str(g.game), cfg=CFG, checker=None,
                                     no_syntax_check=True, journal=g.journal, backup_root=g.backups))
    assert r.status == "applied" and r.written


def test_refused_when_the_checker_rejects_the_patched_text(tmp_path):
    g = Game(tmp_path)
    r = one(g.run(checker=OkChecker(reject_new=True)))
    assert r.status == "refused" and "rejects the patched text" in r.reason and not r.written
    assert g.core.read_bytes() == stock() and not os.path.exists(g.journal)


def test_refused_when_the_file_changed_after_it_was_checked(tmp_path, monkeypatch):
    g = Game(tmp_path)
    real = lf.apply_report

    def changed_meanwhile(rep, *a, **kw):
        g.core.write_bytes(stock() + b"\n-- MWSE-Update ran just now\n")
        return real(rep, *a, **kw)

    monkeypatch.setattr(lf, "apply_report", changed_meanwhile)
    r = one(g.run())
    assert r.status == "refused" and "changed since it was checked" in r.reason
    assert not r.written and r.journal_entry is None and r.sha1_after is None
    assert g.core.read_bytes().endswith(b"-- MWSE-Update ran just now\n")


def test_applied_with_the_real_luajit_syntax_check(tmp_path):
    pytest.importorskip("lupa.luajit21")                             # the lupa tests run on Python 3.14
    g = Game(tmp_path)
    r = one(g.run(checker=lf.LupaChecker()))
    assert r.status == "applied" and r.written
    assert lf.LupaChecker().check(g.core.read_bytes().decode("latin-1"))[0]


def test_crlf_core_file_is_patched_with_crlf(tmp_path):
    crlf = stock().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    g = Game(tmp_path, text=crlf)
    r = one(g.run())
    assert r.status == "applied" and r.written
    assert g.core.read_bytes().split(b"]] ", 1)[1] == paged().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def test_core_folder_names_need_not_match_the_rules_case(tmp_path):
    g = Game(tmp_path, text=False)
    odd = g.data / "mwse" / "CORE" / "MCM" / "components" / "pages" / "exclusionspage.LUA"
    odd.parent.mkdir(parents=True)
    odd.write_bytes(stock())
    r = one(g.run(dry_run=True))
    assert r.status == "applied" and os.path.normcase(r.path) == os.path.normcase(str(odd))


def test_no_other_file_is_read_for_patching_or_written(tmp_path):
    g = Game(tmp_path)
    mod = g.data / "MWSE" / "mods" / "AttendMeMWSE" / "followers.lua"
    mod.parent.mkdir(parents=True)
    fingerprint = b"if ref and ref.mobile and not ref.mobile.isDead then\nend\n"      # a KB1 fingerprint
    mod.write_bytes(fingerprint)
    other_core = g.data / "MWSE" / "core" / "other.lua"
    other_core.write_bytes(b"local x = nil\nx.y = 1\n")
    results = g.run()
    assert [r.rel for r in results] == [REL]
    assert mod.read_bytes() == fingerprint and other_core.read_bytes() == b"local x = nil\nx.y = 1\n"


def test_skipknown_leaves_a_rule_out(tmp_path):
    g = Game(tmp_path)
    cfg = dict(CFG, skipKnown=["KB3", "KB4"])
    r = one(lf.apply_core_known_bugs(str(g.data), True, game_dir=str(g.game), cfg=cfg, checker=OkChecker(),
                                     journal=g.journal, backup_root=g.backups))
    assert r.status == "no-match" and [k["state"] for k in r.kbs] == ["skipped", "skipped"]


def test_json_shape_and_exit_codes(tmp_path):
    g = Game(tmp_path)
    results = g.run(dry_run=True)
    doc = lf.core_result_json(results, str(g.data), True, journal=g.journal)
    json.dumps(doc)
    assert set(doc) == {"tool", "mode", "version", "dry_run", "data_dir", "journal", "exit_code", "counts", "files"}
    assert doc["mode"] == "core-only" and doc["dry_run"] is True and doc["exit_code"] == 0
    assert doc["counts"] == {"applied": 1, "already-patched": 0, "no-match": 0, "partial": 0, "refused": 0}
    assert set(doc["files"][0]) == {"path", "rel", "kb_ids", "status", "parts_matched", "parts_total", "reason",
                                    "journal_entry", "dry_run", "written", "backup", "sha1_before", "sha1_after", "kbs"}
    assert set(doc["files"][0]["kbs"][0]) == {"kb", "state", "parts_matched", "parts_total"}
    ok = lf.CoreResult("p", "r", [], "no-match")
    part = lf.CoreResult("p", "r", [], "partial")
    ref = lf.CoreResult("p", "r", [], "refused")
    assert lf.core_exit_code([ok]) == 0 and lf.core_exit_code([]) == 0
    assert lf.core_exit_code([ok, part]) == lf.CORE_EXIT_PARTIAL == 3
    assert lf.core_exit_code([part, ref]) == lf.CORE_EXIT_REFUSED == 2


def test_core_data_dir_takes_the_game_folder_or_data_files(tmp_path):
    g = Game(tmp_path)
    for given in (g.game, g.data):
        game, data = lf.core_data_dir(str(given))
        assert os.path.normcase(data) == os.path.normcase(str(g.data))
        assert os.path.normcase(game) == os.path.normcase(str(g.game))
    with pytest.raises(ValueError):
        lf.core_data_dir(str(tmp_path / "nowhere"))


# ------------------------------------------------------------------------------------------------ the CLI
@pytest.fixture
def cli(tmp_path, monkeypatch):
    g = Game(tmp_path)
    monkeypatch.setattr(lf, "JOURNAL", g.journal)
    monkeypatch.setattr(lf, "BACKUP_ROOT", g.backups)
    monkeypatch.setattr(lf.undo, "__defaults__", (g.journal, False, print))      # bound when undo was defined
    monkeypatch.setattr(lf, "find_checker", lambda explicit=None, game_dir=None: OkChecker())
    monkeypatch.setattr(lf, "load_config", lambda game_dir=None, data_dir=None: dict(CFG))
    return g


def test_cli_dry_run_json_to_stdout_is_pure_json(cli, capsys):
    rc = lf.main(["--core-only", "--dry-run", "--json", "-", str(cli.game)])
    out, err = capsys.readouterr()
    doc = json.loads(out)                                            # nothing but JSON on stdout
    assert rc == 0 and doc["exit_code"] == 0 and doc["dry_run"] is True
    assert doc["files"][0]["status"] == "applied" and doc["files"][0]["written"] is False
    assert "APPLIED" in err and "Nothing changed (dry run)" in err
    assert cli.core.read_bytes() == stock() and not os.path.exists(cli.journal)


def test_cli_applies_then_undo_restores(cli, capsys):
    assert lf.main(["--core-only", str(cli.data)]) == 0
    out, _err = capsys.readouterr()
    assert "APPLIED: " + REL in out and "journal entry" in out
    assert cli.core.read_bytes().startswith(b"--[[localpatch ")
    assert lf.main(["--core-only", str(cli.data)]) == 0              # a second run: already patched
    assert "ALREADY-PATCHED" in capsys.readouterr()[0]
    assert lf.main(["--undo"]) == 0
    assert cli.core.read_bytes() == stock()


def test_cli_json_file_and_exit_code_2_for_refused(cli, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(lf, "find_checker", lambda explicit=None, game_dir=None: None)
    target = tmp_path / "result.json"
    rc = lf.main(["--core-only", "--json", str(target), str(cli.data)])
    assert rc == lf.CORE_EXIT_REFUSED == 2
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc["files"][0]["status"] == "refused" and doc["exit_code"] == 2
    assert cli.core.read_bytes() == stock()


def test_cli_exit_code_3_for_partial(tmp_path, monkeypatch, capsys):
    g = Game(tmp_path, text=stock().replace(b"\n\n--- Constructor", b"\n-- changed upstream\n--- Constructor"))
    monkeypatch.setattr(lf, "find_checker", lambda explicit=None, game_dir=None: OkChecker())
    monkeypatch.setattr(lf, "load_config", lambda game_dir=None, data_dir=None: dict(CFG))
    assert lf.main(["--core-only", "--dry-run", str(g.data)]) == lf.CORE_EXIT_PARTIAL == 3
    assert "PARTIAL" in capsys.readouterr()[0]


def test_cli_exit_code_4_for_a_folder_that_is_not_morrowind(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert lf.main(["--core-only", "--dry-run", str(empty)]) == lf.CORE_EXIT_USAGE == 4
    assert "not a Morrowind folder" in " ".join(capsys.readouterr()[1].split())


def test_cli_exit_code_1_when_another_tool_holds_the_lock(cli, monkeypatch, capsys):
    monkeypatch.setattr(lf.MP, "acquire_game_lock", lambda game_dir: False)
    assert lf.main(["--core-only", str(cli.data)]) == lf.CORE_EXIT_LOCKED == 1
    assert cli.core.read_bytes() == stock()
    assert lf.main(["--core-only", "--dry-run", str(cli.data)]) == 0   # a dry run takes no lock


def test_cli_rejects_combinations_that_make_no_sense(cli):
    for argv in (["--core-only", "--apply"], ["--core-only", "--undo"], ["--dry-run"], ["--core-only", "a", "b"]):
        with pytest.raises(SystemExit) as e:
            lf.main(argv)
        assert e.value.code == 2