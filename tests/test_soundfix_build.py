"""--soundfix end to end with the real MWRecompile: the fidelity gate, the patch plugin, its helper data, its
load-order slot, and undo. Builds a tiny game; skipped when tools\\MWRecompile\\ isn't there."""
import json
import os
import struct
import subprocess
import types
import wave

import pytest

from conftest import m, plugin, rec, sub, z
import mwdialog_soundfix as SF  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "tools", "MWRecompile", "MWRecompile.exe")
pytestmark = pytest.mark.skipif(not os.path.isfile(EXE), reason="MWRecompile not available")

LOOP = 'Begin LoopScript\r\nshort done\r\nif ( GetSoundPlaying "Hum" == 0 )\r\n\tPlayLoopSound3DVP "Hum" 0.5, 1.0\r\nendif\r\nEnd\r\n'
SHOT = 'Begin ShotScript\r\nif ( GetSoundPlaying "Bell" == 0 )\r\n\tPlaySound3D "Bell"\r\nendif\r\nEnd\r\n'
STALE = 'Begin StaleScript\r\nif ( GetSoundPlaying "Hum" == 0 )\r\n\tPlayLoopSound3DVP "Hum" 0.5, 1.0\r\nendif\r\nEnd\r\n'


def scpt(name, text):
    return rec("SCPT", sub("SCHD", z(name).ljust(32, b"\0")[:32] + struct.pack("<5I", 0, 0, 0, 0, 0)) + sub("SCTX", text.encode()))


def soun(name, fn):
    return rec("SOUN", sub("NAME", z(name)) + sub("FNAM", z(fn)) + sub("DATA", bytes([200, 0, 255])))


@pytest.fixture
def game(tmp_path):
    game = tmp_path / "Morrowind"
    data = game / "Data Files"
    (data / "Sound" / "fx").mkdir(parents=True)
    with wave.open(str(data / "Sound" / "fx" / "bell.wav"), "wb") as w:   # a 2-second bell
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(22050), w.writeframes(b"\0\0" * 44100)
    src = data / "src.esm"
    plugin(src, [], [soun("Hum", "fx\\hum.wav"), soun("Bell", "fx\\bell.wav"),
                     scpt("LoopScript", LOOP), scpt("ShotScript", SHOT), scpt("StaleScript", STALE)])
    r = subprocess.run([EXE, str(src), "-o", str(data / "Morrowind.esm"), "--no-backup", "-q", "-d", str(data)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    src.unlink()
    # a mod edited StaleScript's source after it was compiled: its bytecode no longer matches it
    esm = data / "Morrowind.esm"
    raw = esm.read_bytes()
    stale = STALE.encode()
    assert raw.count(stale) == 1
    raw = raw.replace(stale, stale.replace(b"0.5, 1.0", b"0.9, 1.0"))  # same length: the record stays valid
    esm.write_bytes(raw)
    (game / "Morrowind.ini").write_text("[Game Files]\nGameFile0=Morrowind.esm\n", encoding="utf-8")
    plugin(data / "mwdialog_check Multipatch.esp", [("Morrowind.esm", len(raw))], [])
    m.write_load_order(str(game), ["Morrowind.esm", "mwdialog_check Multipatch.esp"], "test")
    return game


def args_for(game, **kw):
    a = dict(data_dir=str(game / "Data Files"), ini=str(game / "Morrowind.ini"), dry_run=False, soundfix_report=False,
             soundfix_loop_mode="flag", mwrecompile=EXE)
    a.update(kw)
    return types.SimpleNamespace(**a)


def plugins_of(game):
    data = game / "Data Files"
    return [(n, str(data / n)) for n in ("Morrowind.esm", "mwdialog_check Multipatch.esp")]


def scripts_in(path):
    out = {}
    for _o, tag, _f, body in SF.iter_records(SF.read_plugin_bytes(str(path))):
        if tag == "SCPT":
            out[SF.cstr(SF.first_sub(body, b"SCHD")[:32]).lower()] = SF.dec(SF.first_sub(body, b"SCTX"))
    return out


def test_patch_built_gated_slotted_and_undone(game):
    assert SF.run_soundfix(args_for(game), plugins_of(game), []) == 0
    patch = game / "Data Files" / SF.SOUNDFIX_NAME
    got = scripts_in(patch)
    assert set(got) == {"loopscript", "shotscript"}                       # StaleScript failed the gate
    assert "if ( mwsfOn1 == 0 )" in got["loopscript"]
    assert "set mwsfT1 to ( 2.0000 - GetSecondsPassed )" in got["shotscript"]
    report = (game / SF.REPORT_FILE).read_text(encoding="utf-8")
    assert "stalescript" in report and "doesn't recompile to the bytecode it ships with" in report
    assert m.read_load_order(args_for(game)) == ["Morrowind.esm", SF.SOUNDFIX_NAME, "mwdialog_check Multipatch.esp"]
    data = json.loads((game / "Data Files" / "MWSE" / "config" / SF.DATA_JSON).read_text(encoding="utf-8"))
    assert data["scripts"]["loopscript"]["loopFlags"] == ["mwsfOn1"] and data["scripts"]["shotscript"]["loopFlags"] == []
    assert data["scripts"]["loopscript"]["repairs"] == ["loop: hum"]               # shown in its MCM page
    assert data["scripts"]["shotscript"]["repairs"] == ["one-shot: bell"]
    # a second build reads the originals, not its own patch, and gives the same scripts
    assert SF.run_soundfix(args_for(game), plugins_of(game) + [(SF.SOUNDFIX_NAME, str(patch))], []) == 0
    assert scripts_in(patch) == got
    SF.undo(args_for(game))
    assert not patch.exists() and m.read_load_order(args_for(game)) == ["Morrowind.esm", "mwdialog_check Multipatch.esp"]


def test_dry_run_installs_nothing(game):
    assert SF.run_soundfix(args_for(game, dry_run=True), plugins_of(game), []) == 0
    assert not (game / "Data Files" / SF.SOUNDFIX_NAME).exists() and (game / SF.REPORT_FILE).exists()
