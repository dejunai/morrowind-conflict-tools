import json
import os
import shutil
import subprocess
import wave

import pytest

from conftest import m, plugin, rec, sub, z
import mwdialog_soundcache as cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
GUARD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwsoundguard", "main.lua")


def sound(name, filename=None, deleted=False):
    return rec("SOUN", sub("NAME", z(name))
               + (sub("FNAM", z(filename)) if filename is not None else b"")
               + (sub("DELE", bytes(4)) if deleted else b""))


def wav(path, frames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(8000)
        f.writeframes(bytes(frames * 2))


def read_cache(df):
    return json.loads((df / "MWSE" / "config" / cache.CACHE_NAME).read_text(encoding="utf-8"))["sounds"]


def test_cache_uses_winning_records_and_reuses_only_unchanged_files(tmp_path, monkeypatch):
    df = tmp_path / "Data Files"
    df.mkdir()
    wav(df / "Sound" / "first.wav", 4000)
    wav(df / "Sound" / "winner.wav", 8000)
    base, mod = df / "base.esm", df / "mod.esp"
    plugin(base, [], [sound("Sound A", "first.wav"), sound("deleted", "first.wav")])
    plugin(mod, [], [sound("SOUND A", "winner.wav"), sound("deleted", deleted=True),
                     sound("missing", "absent.wav"), sound("unsafe", "..\\outside.wav")])
    order = [(base.name, str(base)), (mod.name, str(mod))]
    assert cache.write_sound_cache(str(df), order) == 1
    data = read_cache(df)
    assert set(data) == {"sound a"}
    assert data["sound a"]["file"] == "winner.wav"
    assert data["sound a"]["length"] == 1
    assert data["sound a"]["size"] == (df / "Sound" / "winner.wav").stat().st_size

    original = cache.sound_duration
    calls = []

    def measure(path, probe):
        calls.append(path)
        return original(path, probe)
    monkeypatch.setattr(cache, "sound_duration", measure)
    cache.write_sound_cache(str(df), order)
    assert not calls
    wav(df / "Sound" / "winner.wav", 16000)
    cache.write_sound_cache(str(df), order)
    assert len(calls) == 1 and read_cache(df)["sound a"]["length"] == 2
    old_mtime = (df / "Sound" / "winner.wav").stat().st_mtime_ns
    with wave.open(str(df / "Sound" / "winner.wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(bytes(32000))
    os.utime(df / "Sound" / "winner.wav", ns=(old_mtime + 2_000_000_000, old_mtime + 2_000_000_000))
    cache.write_sound_cache(str(df), order)
    assert len(calls) == 2 and read_cache(df)["sound a"]["length"] == 1


def test_invalid_audio_is_reported_not_cached(tmp_path, capsys):
    df = tmp_path / "Data Files"
    df.mkdir()
    p = df / "broken.esp"
    plugin(p, [], [sound("broken", "broken.wav")])
    wav(df / "Sound" / "broken.wav", 8000)
    with open(df / "Sound" / "broken.wav", "r+b") as f:
        f.truncate(100)
    cache.write_sound_cache(str(df), [(p.name, str(p))])
    assert read_cache(df) == {}
    assert "truncated WAV data" in capsys.readouterr().err


def test_ffprobe_discovery_prefers_the_bundled_tools_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.MP, "TOOL_DIR", str(tmp_path))
    monkeypatch.setattr(cache.MP, "find_game_dir", lambda *a: None)
    monkeypatch.setattr(cache.MP.shutil, "which", lambda name: None)
    assert cache.find_ffprobe() is None
    sibling = tmp_path / "ffprobe.exe"
    sibling.touch()
    assert cache.find_ffprobe() == str(sibling)
    (tmp_path / "tools").mkdir()
    bundled = tmp_path / "tools" / "ffprobe.exe"
    bundled.touch()
    assert cache.find_ffprobe() == str(bundled)
    monkeypatch.setattr(cache.MP.shutil, "which", lambda name: "path-ffprobe")
    assert cache.find_ffprobe() == str(bundled)                     # tools\ wins over PATH


@pytest.mark.skipif(not shutil.which("ffmpeg") or not os.path.isfile(os.path.join(ROOT, "tools", "ffprobe.exe")),
                    reason="ffmpeg and bundled ffprobe needed to create and inspect MP3")
def test_cache_builds_mp3_with_bundled_ffprobe_without_path(tmp_path, monkeypatch):
    df = tmp_path / "Data Files"
    sound_dir = df / "Sound"
    sound_dir.mkdir(parents=True)
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", "-q:a", "3", str(sound_dir / "sample.mp3")], check=True)
    p = df / "base.esm"
    plugin(p, [], [sound("sample", "sample.mp3")])
    monkeypatch.setattr(cache.MP.shutil, "which", lambda name: None)
    assert cache.write_sound_cache(str(df), [(p.name, str(p))]) == 1
    assert read_cache(df)["sample"]["length"] == pytest.approx(2, abs=0.1)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="ffmpeg and ffprobe needed to create and inspect MP3")
def test_mp3_duration_from_real_encoded_file(tmp_path):
    path = tmp_path / "sound.mp3"
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", "-q:a", "3", str(path)], check=True)
    assert cache.sound_duration(str(path), shutil.which("ffprobe")) == pytest.approx(2, abs=0.1)


def test_fix_writes_cache_even_without_repairs_but_dry_run_does_not(tmp_path):
    df = tmp_path / "Data Files"
    df.mkdir()
    wav(df / "Sound" / "ok.wav", 8000)
    plugin(df / "Morrowind.esm", [], [sound("ok", "ok.wav")])
    args = [str(df), "--plugins", "Morrowind.esm", "--no-vortex", "--no-archive-lookup",
            "--no-doubled", "--no-bug-reports", "--fix", "--yes", "--no-follow-up",
            "--fix-log", str(tmp_path / "fix.log")]
    m.main(args + ["--dry-run"])
    assert not (df / "MWSE" / "config" / cache.CACHE_NAME).exists()
    m.main(args)
    assert read_cache(df)["ok"]["length"] == 1


@pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")
def test_guard_uses_length_and_original_pitch_and_falls_back_when_stale():
    script = r"""
now, size = 0, 40
os.clock = function() return now end
local function userdata(fields)
    local v = newproxy(true)
    getmetatable(v).__index = fields
    return v
end
local snd = userdata({id = "A", filename = "Fx\\a.wav"})
local obj = userdata({id = "object", objectType = 3})
local ref = userdata({id = "ref", object = obj})
local other = userdata({id = "other", object = obj})
local actor = userdata({id = "actor", object = userdata({objectType = 1})})
tes3 = {objectType = {npc = 1, creature = 2},
        event = {initialized = 1, loaded = 2, modConfigReady = 3, addSound = 4,
                 addTempSound = 5, referenceDeactivated = 6},
        getSoundPlaying = function() return false end}
mwse = {
    loadConfig = function(name, defaults)
        if name == "mwsoundguard_data" then
            return {version = 1, sounds = {a = {file = "Fx\\a.wav", length = 2, size = 40, mtime = 9}}}
        end
        return defaults
    end,
    log = function() end,
}
lfs = {attributes = function() return {size = size, modification = 9} end}
event = {register = function() end, unregister = function() end}
timer = {real = 1, start = function() return {cancel = function() end} end}
local guard = dofile(GUARD)
local function request(r, pitch, flags, voice)
    local e = {reference = r, sound = snd, pitch = pitch, flags = flags or 0, isVoiceover = voice}
    guard.guard(e)
    return e.block == true
end
local function check(ok, msg) if not ok then error(msg) end end
check(not request(ref, 2), "first starts")
now = 0.1
check(request(ref, 0.5), "original pitch governs the wait")
check(not request(other, 1), "different emitter starts")
now = 1
check(not request(ref, 0.5), "next request starts at the original deadline")
now = 4.9
check(request(ref, 1), "slower second start lasts four seconds")
now = 5
check(not request(ref, 1), "next request starts after four seconds")
size = 41
now = 5.1
check(not request(ref, 1), "changed file falls back to v2")
now = 5.2
check(not request(ref, 1), "fallback does not use a stale deadline")
size = 40
check(not request(actor, 1), "actors are exempt")
check(not request(ref, 1, 0, true), "voice is exempt")
local capped = userdata({id = "capped", object = obj})
guard.config.globalCap = 0
now = 6
check(request(capped, 1), "global cap blocks the request")
guard.config.globalCap = 32
now = 6.1
check(not request(capped, 1), "blocked request didn't start a cooldown")
local noId = userdata({filename = "Fx\\a.wav"})
local noIdEvent = {reference = other, sound = noId, pitch = 1, flags = 0}
guard.guard(noIdEvent)
check(not noIdEvent.block, "sound without an id falls back")
local loopref = userdata({id = "loop", object = obj})
check(not request(loopref, 1, 1), "first loop starts")
now = 6.2
check(request(loopref, 1, 1), "loop still uses v2")
print("ok")
""".replace("GUARD", "[[" + GUARD + "]]")
    result = subprocess.run([LUAJIT, "-"], input=script, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0 and result.stdout.strip() == "ok", result.stderr + result.stdout
