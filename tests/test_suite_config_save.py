"""A suite mod whose config table holds functions must not save it whole: MWSE can't encode a function as JSON
("Failed to encode JSON ... type 'function' is not supported"). Such mods save a plain copy via config.save()."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODS = os.path.join(ROOT, "Data Files", "MWSE", "mods", "mwsuite")


def test_configs_with_functions_are_not_saved_whole():
    bad = []
    for name in sorted(os.listdir(MODS)):
        texts = {}
        for base, _dirs, files in os.walk(os.path.join(MODS, name)):
            for f in files:
                if f.endswith(".lua"):
                    texts[os.path.relpath(os.path.join(base, f), MODS)] = open(os.path.join(base, f),
                                                                               encoding="utf-8").read()
        holds_functions = any(re.search(r"^\s*function\s+config[.:]|^\s*config\.\w+\s*=\s*function\b", t, re.M)
                              for t in texts.values())
        if not holds_functions:
            continue
        for rel, t in texts.items():
            if re.search(r"saveOnClose\([^)]*\bconfig\s*\)|mwse\.saveConfig\([^,]+,\s*config\s*\)", t):
                bad.append(rel)
    assert not bad, bad
