"""Suite MCM settings and actions must explain what they do."""
from pathlib import Path

import mwdialog_lua


ROOT = Path(__file__).resolve().parents[1]
MODS = ROOT / "Data Files" / "MWSE" / "mods" / "mwsuite"
CONTROLS = {
    "createYesNoButton", "createOnOffButton", "createSlider", "createDropdown",
    "createKeyBinder", "createMouseBinder", "createButton", "createExclusionsPage",
}


def test_suite_mcm_controls_have_descriptions():
    missing = []
    for mod in sorted(MODS.iterdir()):
        if not (mod / "main.lua").is_file():
            continue
        if mod.name == "mwmanagermenu":
            continue
        for path in mod.rglob("*.lua"):
            tokens = mwdialog_lua.tokenize(path.read_text(encoding="utf-8"))
            for i, token in enumerate(tokens[:-2]):
                if token.v not in CONTROLS or i == 0 or tokens[i - 1].v != ":":
                    continue
                j = i + 1
                if tokens[j].v == "(":
                    j += 1
                if tokens[j].v != "{":
                    continue
                depth, fields = 0, set()
                for k in range(j, len(tokens) - 1):
                    value = tokens[k].v
                    if value == "{":
                        depth += 1
                    elif value == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    elif depth == 1 and tokens[k + 1].v == "=":
                        fields.add(value)
                # Native UI buttons use text, not the MCM buttonText property.
                if token.v == "createButton" and "text" in fields and "buttonText" not in fields:
                    continue
                if "description" not in fields:
                    missing.append(f"{path.relative_to(MODS)}:{token.line}")
    assert not missing, missing


def test_every_suite_settings_page_is_registered():
    missing = []
    for mod in sorted(MODS.iterdir()):
        if not (mod / "main.lua").is_file() or mod.name == "mwmanagermenu":
            continue
        code = "\n".join(p.read_text(encoding="utf-8") for p in mod.rglob("*.lua"))
        if "createTemplate" in code and not any(call in code for call in (
                ":register()", "mcm.register(", "registerModConfig(", "mcm.registerMCM(")):
            missing.append(mod.name)
    assert not missing, missing
