"""Icons and textures stay as the mod ships them (Dej, 2026-11-26): luafix has no rule that rewrites an image path,
an extension (.tga, .dds, .bmp) or a folder under icons\\ or textures\\. The general rule I1 and the hand-repair
entries KB20, KB25 and KB26 did, and were removed. It rewrote Tamriel Data's td_s_passwall(.alt).tga to .dds in
the same files KB52 patches, and More Quickloot's, UI Expansion's and Map Icons' icon names (even a help text)."""
import os
import re

import pytest

from conftest import _load

lf = _load("mwdialog_luafix")
KBH = _load("mwdialog_luafix_kb")

CFG = dict(lf.DEFAULTS)
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "mwse")
IMG = re.compile(r"[\w\\/. -]*\.(?:tga|dds|bmp)\b", re.I)

# every shape the removed rule rewrote: a .tga whose .dds is there, a doubled extension, a path one folder off,
# a name inside prose, a texture and an icon path with forward slashes
ICONS = r'''local passwallIcon = "td\\s\\td_s_passwall.tga"
if config.passwallAlteration then
	passwallIcon = "td\\s\\td_s_passwall_alt.tga"
end
local kept = "td\\s\\td_s_passwall.dds"
local doubled = { chapel = "Textures\\Map\\temple.dds.dds" }
local off = "\\Icons\\SSQN\\MT\\MT24MT_S.dds"
local cols = { "icons/gold.tga", "textures/menu_icon_magic.tga", "Splash\\a.bmp" }
local help = [[Enter the icon path (e.g. "Textures/compass.tga", "Icons/c/c_ring_khajiit.dds")]]
'''
FILES = ["icons/td/s/td_s_passwall.dds", "icons/td/s/td_s_passwall_alt.dds", "textures/Map/temple.dds",
         "icons/SSQN/MT24MT_S.dds", "icons/gold.dds", "textures/menu_icon_magic.dds", "Splash/a.dds",
         "textures/compass.dds"]


def fixture(form):
    with open(os.path.join(FIX, f"tamrieldata_magic_{form}.lua"), "rb") as f:
        return f.read().decode("utf-8")


def data_with_the_dds_files(tmp_path):
    data = tmp_path / "Data Files"
    for rel in FILES:                      # the .dds each .tga name has, with a real header: what I1 looked for
        p = data / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"DDS " + b"\0" * 124)
    return data


def run(tmp_path, text, rel="TamrielData/magic.lua"):
    data = data_with_the_dds_files(tmp_path)
    path = data / "MWSE" / "mods" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    rep = lf.check_paths([str(data / "MWSE" / "mods")], CFG, checker=None, use_cache=False, data_dir=str(data))
    return next(e for p, e in rep.files.items() if p.lower().endswith(os.path.basename(rel).lower()))


def test_no_image_rule_is_left():
    assert not hasattr(lf, "image_findings") and not hasattr(lf, "bsa_names")
    assert lf.RULES_REV >= 6                       # files patched with I1 are worked out again


def test_no_known_bug_changes_an_image_path_or_extension():
    """For every entry, the image names in the text it replaces and in its replacement are the same."""
    for rule, plugin, path, old, new, _what in lf.KNOWN_BUGS:
        assert IMG.findall(old) == IMG.findall(new), f"{rule} ({plugin}, {path}) rewrites an image name"
    ids = {r[0] for r in lf.KNOWN_BUGS}
    assert not ids & {"KB20", "KB21", "KB22", "KB24", "KB25", "KB26", "KB27"}
    assert not {"KB20", "KB25", "KB26"} & set(KBH.WHAT)


@pytest.mark.parametrize("form", ["old", "new"])
@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_a_file_with_KB52_applied_keeps_every_icon_string_and_only_KB52_changes(tmp_path, form, eol):
    src = ICONS + fixture(form)
    ent = run(tmp_path, src.replace("\n", eol))
    assert ent["error"] is None
    assert not [f for f in ent["findings"] if f["rule"] == "I1"]
    patch = ent["patch"]
    assert patch and patch["ok"], patch
    assert "KB52" in patch["rules"] and "I1" not in patch["rules"], patch["rules"]
    text = patch["text"]
    # the image names are the same list, in the same order: nothing was rewritten
    assert IMG.findall(text) == IMG.findall(src.replace("\n", eol))
    for lit in ('"td\\\\s\\\\td_s_passwall.tga"', '"td\\\\s\\\\td_s_passwall_alt.tga"', '"Textures\\\\Map\\\\temple.dds.dds"',
                '"\\\\Icons\\\\SSQN\\\\MT\\\\MT24MT_S.dds"', '"icons/gold.tga"', '"textures/menu_icon_magic.tga"',
                '"Splash\\\\a.bmp"', '"Textures/compass.tga"'):
        assert lit in text, lit


def test_a_file_that_only_names_icons_is_left_alone(tmp_path):
    src = "local this = {}\n" + ICONS + "return this\n"
    ent = run(tmp_path, src, rel="Other/main.lua")
    assert ent["error"] is None
    assert not [f for f in ent["findings"] if f["rule"] == "I1"]
    assert ent["patch"] is None or not ent["patch"]["ok"] or IMG.findall(ent["patch"]["text"]) == IMG.findall(src)


def test_the_hand_repair_text_the_removed_entries_carried_is_not_applied(tmp_path):
    """KB20 (Magicka Expanded .tga -> .dds), KB25 and KB26 (SSQN icon names) used to match this exact text."""
    for rel, text in (
        ("lib/operatorjack/magickaexpanded/effects/alteration.lua",
         '        icon = params.icon or "RFD\\\\RFD_ms_alteration.tga",\n'
         '        particleTexture = params.particleTexture or "vfx_alt_glow.tga",\n'),
        ("cz/ssqnpatches/main.lua", '\t\tssqn.registerQIcon("vaba06_mastrius","\\\\Icons\\\\SSQN\\\\BA_Vamp.dds")\n'),
        ("ssqn/iconlist.lua", 'icons.MT_S = "\\\\Icons\\\\SSQN\\\\MT\\\\MT24MT_S.dds"\n'),
    ):
        src = "local t = {\n" + text + "}\nreturn t\n"
        out, found = lf.known_text_repair(src, rel.lower())
        assert out == src and not found, rel
