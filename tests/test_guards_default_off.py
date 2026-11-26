"""Every mw* MWSE mod starts disabled: it is switched on in its own MCM (memory crashes were traced to the guards
running unasked)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODS = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite")


def test_no_mw_mod_defaults_to_enabled():
    found = []
    for name in sorted(os.listdir(MODS)):
        if not name.startswith("mw"):
            continue
        for base, _dirs, files in os.walk(os.path.join(MODS, name)):
            for file in files:
                if file.endswith(".lua"):
                    text = open(os.path.join(base, file), encoding="utf-8").read()
                    text = re.sub(r"setVanityMode\(\{[^}]*\}\)", "", text)      # the camera's switch, not a default
                    if re.search(r"\benabled\s*=\s*true\b|\benabled\s*=\s*saved\.enabled\s*~=\s*false", text):
                        found.append(f"{name}/{file}")
    assert not found, found


def test_every_mw_mod_has_an_enabled_switch():
    missing = []
    for name in sorted(os.listdir(MODS)):
        # mwsoundfix isn't a guard: it is the runtime half of the --soundfix patch, idle unless that patch is
        # active, and with it off the patched loops wouldn't come back when their cell does
        if not name.startswith("mw") or name in ("mwmanagermenu", "mwsoundfix"):
            continue
        text = "".join(open(os.path.join(base, f), encoding="utf-8").read()
                       for base, _d, files in os.walk(os.path.join(MODS, name)) for f in files if f.endswith(".lua"))
        if not re.search(r'id\s*=\s*"enabled"|configKey\s*=\s*"enabled"', text):
            missing.append(name)
    assert not missing, missing


def test_exit_guard_enable_setting_warns_that_it_needs_a_restart():
    text = open(os.path.join(MODS, "mwexitguard", "mcm.lua"), encoding="utf-8").read()
    assert "Restart the game after turning it on" in text
