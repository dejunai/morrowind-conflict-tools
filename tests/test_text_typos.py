"""--fix corrects AFFresh.esm's "fried" for "friend" in the ESM fixes patch; the master is never edited."""
import struct

import pytest

from conftest import m, plugin, rec, records_of, sub, z

TYPO = "Fine-Mouth in Seyda Neen asked me to find his fried, Sky-Crest, who may have been captured."
FIXED = TYPO.replace("his fried,", "his friend,")
SPOKEN = "You found Sky-Crest and freed him? Please, bring him to me. He is true friend of mine."


def topic(kind, *texts):
    out = [rec("DIAL", sub("NAME", z("AF_Test%d" % kind)) + sub("DATA", bytes([kind])))]
    for n, text in enumerate(texts):
        out.append(rec("INFO", sub("INAM", z("%d%d" % (kind, n + 1))) + sub("PNAM", z("%d%d" % (kind, n) if n else ""))
                       + sub("NNAM", z("")) + sub("DATA", struct.pack("<B3xibbbb", kind, 10 * (n + 1), -1, -1, -1, 0))
                       + sub("NAME", text.encode("cp1252"))))
    return out


def scan(*plugins):
    w = m.World(m.Report())
    w.file_sizes = {}
    for name, path in plugins:
        w.load_plugin(str(path), name)
    w.check(set())
    return w, [f for f in w.r.fixes if f[2][0] == "set_text"]


@pytest.mark.parametrize("kind", [0, 4])                       # dialogue, journal
def test_affresh_friend_typo_is_fixed_in_the_patch_only(tmp_path, kind):
    esm = tmp_path / "AFFresh.esm"
    before = plugin(esm, [], topic(kind, TYPO, "He sells fried kwama eggs."))
    w, fixes = scan(("AFFresh.esm", esm))
    assert len(fixes) == 1

    esp_plans, esm_plans, _skipped, _manual = m.plan_fixes(w.r, w, [("AFFresh.esm", str(esm))], None, True)
    assert not esp_plans
    entries = []
    m.apply_plan(str(esm), "AFFresh.esm", esm_plans["AFFresh.esm"], w, [], collect=entries)
    patch = tmp_path / m.PATCH_NAME
    m.write_patch(str(patch), entries, [("AFFresh.esm", str(esm))], [], backup=False)
    texts = [bytes(m.first_sub(b, b"NAME")).decode("cp1252") for _o, t, _f, b in records_of(patch) if t == "INFO"]
    assert texts == [FIXED]
    assert esm.read_bytes() == before

    assert not scan(("AFFresh.esm", esm), (m.PATCH_NAME, patch))[1]     # fixed: not found again


def test_fine_mouths_missing_word_is_put_back(tmp_path):
    esm = tmp_path / "AFFresh.esm"
    plugin(esm, [], topic(0, SPOKEN))
    assert [f[2][1] for f in scan(("AFFresh.esm", esm))[1]] == [SPOKEN.replace("is true", "is a true")]


def test_other_mods_text_is_left_alone(tmp_path):
    esm = tmp_path / "Other.esm"
    plugin(esm, [], topic(4, TYPO))
    assert not scan(("Other.esm", esm))[1]
