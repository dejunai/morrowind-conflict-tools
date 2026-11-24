"""Build mwsoundguard's sound-duration cache from winning SOUN records and loose files."""
import json
import math
import os
import subprocess
import sys
import wave

import mwdialog_paths as MP
from mwdialog_tes3 import atomic_open, cstr, first_sub, iter_records, read_plugin_bytes

CACHE_NAME = "mwsoundguard_data.json"


def winning_sounds(plugins):
    sounds = {}
    for _name, path in plugins:
        for _off, tag, _flags, body in iter_records(read_plugin_bytes(path)):
            if tag != "SOUN":
                continue
            name = first_sub(body, b"NAME")
            if not name:
                continue
            key = cstr(name).lower()
            filename = first_sub(body, b"FNAM")
            sounds[key] = None if first_sub(body, b"DELE") is not None or not filename else cstr(filename)
    return sounds


def sound_duration(path, ffprobe):
    if path.lower().endswith(".wav"):
        try:
            with wave.open(path, "rb") as wav:
                rate = wav.getframerate()
                if rate > 0 and wav.getnframes() > 0:
                    wav.setpos(wav.getnframes() - 1)
                    if len(wav.readframes(1)) != wav.getnchannels() * wav.getsampwidth():
                        raise ValueError("truncated WAV data")
                    return wav.getnframes() / rate
        except (wave.Error, EOFError):
            pass
    if not ffprobe:
        raise ValueError("ffprobe is unavailable for this format")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as e:
        raise ValueError("ffprobe timed out") from e
    if result.returncode:
        raise ValueError("ffprobe failed: " + result.stderr.strip()[-200:])
    try:
        duration = float(result.stdout.strip())
    except ValueError as e:
        raise ValueError("ffprobe returned no duration") from e
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid sound duration")
    return duration


def find_ffprobe():
    return MP.find_program("ffprobe", MP.find_game_dir())


def write_sound_cache(data_dir, plugins):
    cache_path = os.path.join(data_dir, "MWSE", "config", CACHE_NAME)
    old = {}
    try:
        with open(cache_path, encoding="utf-8") as f:
            previous = json.load(f)
        if previous.get("version") == 1 and isinstance(previous.get("sounds"), dict):
            old = previous["sounds"]
    except FileNotFoundError:
        pass
    except (OSError, ValueError, AttributeError) as e:
        print(f"  sound cache: cannot reuse existing cache ({e}); rebuilding", file=sys.stderr)

    ffprobe = find_ffprobe()
    sounds = winning_sounds(plugins)
    entries, measured, failed = {}, {}, []
    for sound_id, filename in sounds.items():
        if not filename:
            continue
        parts = filename.replace("/", "\\").split("\\")
        if any(not p or p in (".", "..") or ":" in p for p in parts):
            failed.append((sound_id, "invalid sound path"))
            continue
        full = os.path.join(data_dir, "Sound", *parts)
        try:
            stat = os.stat(full)
        except OSError as e:
            failed.append((sound_id, str(e)))
            continue
        stamp = (stat.st_size, stat.st_mtime_ns)
        prior = old.get(sound_id)
        if (isinstance(prior, dict) and prior.get("file") == filename
                and prior.get("size") == stat.st_size and prior.get("mtime_ns") == str(stat.st_mtime_ns)
                and isinstance(prior.get("length"), (int, float))
                and math.isfinite(prior["length"]) and prior["length"] > 0):
            duration = prior["length"]
        else:
            key = (os.path.normcase(full), stamp)
            if key not in measured:
                try:
                    duration = sound_duration(full, ffprobe)
                    after = os.stat(full)
                    if (after.st_size, after.st_mtime_ns) != stamp:
                        raise ValueError("file changed while reading")
                    measured[key] = duration
                except (OSError, ValueError) as e:
                    failed.append((sound_id, str(e)))
                    continue
            duration = measured[key]
        entries[sound_id] = {"file": filename, "length": duration, "size": stat.st_size,
                             "mtime": int(stat.st_mtime), "mtime_ns": str(stat.st_mtime_ns)}
        if len(entries) % 500 == 0:
            print(f"  sound cache: {len(entries)} sounds measured...", file=sys.stderr, flush=True)

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with atomic_open(cache_path, encoding="utf-8") as f:
        json.dump({"version": 1, "sounds": entries}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"  sound cache: {len(entries)} sound(s) cached; {len(failed)} missing or unreadable")
    for sound_id, why in failed[:10]:
        print(f"    {sound_id}: {why}", file=sys.stderr)
    if len(failed) > 10:
        print(f"    ... and {len(failed) - 10} more", file=sys.stderr)
    return len(entries)
