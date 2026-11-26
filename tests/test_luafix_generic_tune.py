"""luafix generic tuning rules (2026-11-25): G2S (per-frame world scans gated at high), G8 (a literal message box
in a combat-event handler shown at most once per messageInterval), U1 (a label's .text written only when it
differs), skipRules, and M1 + G2 sharing a handler's first line at --level medium."""
import pytest

from conftest import _load

L = _load("mwdialog_lua")
lf = _load("mwdialog_luafix")

CFG = dict(lf.DEFAULTS)


class OkChecker:
    name = "fake"

    def check(self, text):
        return True, ""


def analyse(src, cfg=None, rel="testmod/main.lua"):
    a = lf.FileAnalysis(src, "testmod", rel, cfg or CFG)
    a.run()
    return a


def found(a, rule):
    return [f for f in a.findings if f["rule"] == rule]


def patched(src, level="high", cfg=None):
    cfg = cfg or CFG
    a = analyse(src, cfg)
    new, rules = lf.build_patch(src, a.findings, "testmod", cfg, level, False)
    if new is None:
        return None, []
    res = lf.verify_patch(src, new, rules, OkChecker(), "testmod", "testmod/main.lua", cfg, level)
    assert res["ok"], res["why"]
    again, _r = lf.build_patch(new, analyse(new, cfg).findings, "testmod", cfg, level, False)
    assert again is None                                   # a second pass changes nothing
    return new, rules


# ------------------------------------------------------------------------------------------------ G2S
FLORA = """local common = require("x.common")
local last
local function playFlora()
    if not tes3.mobilePlayer then return end
    local pos = tes3.mobilePlayer.reference.position
    local hit = tes3.rayTest{ position = pos, direction = tes3vector3.new(0, 0, -1) }
    if hit and common.getMatch(hit.reference) then
        tes3.playSound{ sound = "flora" }
    end
end
event.register(tes3.event.simulate, playFlora)
"""

GUARDS = """local guards = true
event.register("simulate", function()
    if not guards then return end
    for ref in tes3.player.cell:iterateReferences(tes3.objectType.npc) do
        if ref.object.class.id == "Guard" then
            tes3.mobilePlayer.bounty = tes3.mobilePlayer.bounty + 1
        end
    end
end)
"""


@pytest.mark.parametrize("src", [FLORA, GUARDS])
def test_G2S_world_scan_every_frame_is_gated_at_high(src):
    a = analyse(src)
    assert [f["conf"] for f in found(a, "G2S")] == ["high"]
    assert not found(a, "G2")                              # replaces the medium G2 finding
    new, rules = patched(src)
    assert rules == ["G2S"] and "then return end" in new and "localpatch_gate(1, 0.35)" in new
    assert new.count("\n") == src.count("\n")


def test_G2S_frame_critical_or_player_lookup_is_not_promoted():
    cam = FLORA.replace("tes3.playSound{ sound = \"flora\" }", "tes3.getCamera().position = hit.intersection")
    assert not found(analyse(cam), "G2S")                  # camera: frame-critical, G2 leaves it alone
    plain = ("local m = require('x')\nlocal function poll() local p = tes3.getReference('player') "
             "if m.check(p) then m.go() end end\nevent.register('enterFrame', poll)\n")
    a = analyse(plain)
    assert not found(a, "G2S") and [f["conf"] for f in found(a, "G2")] == ["medium"]


def test_skipRules_reports_a_generic_rule_without_applying_it():
    cfg = dict(CFG, skipRules=["G2S"])
    f = found(analyse(FLORA, cfg), "G2S")
    assert [x["conf"] for x in f] == ["report"] and not f[0]["edits"] and "skipRules" in f[0]["what"]
    new, _r = lf.build_patch(FLORA, analyse(FLORA, cfg).findings, "testmod", cfg, "high", False)
    assert new is None


# ------------------------------------------------------------------------------------------------ G8
DAMAGE = """local config = { messages = true }
local function onDamage(e)
    if e.reference.baseObject.essential then
        e.damage = 0
        if config.messages then
            tes3.messageBox("This one is essential.")
        end
    end
end
event.register("damage", onDamage)
"""


def test_G8_literal_message_in_a_combat_event_is_throttled():
    new, rules = patched(DAMAGE)
    assert "G8" in rules
    assert 'if not localpatch_gate(1, 10) then tes3.messageBox("This one is essential.") end' in new
    assert new.count("\n") == DAMAGE.count("\n")


def test_G8_interval_comes_from_messageInterval():
    new, _r = patched(DAMAGE, cfg=dict(CFG, messageInterval=15))
    assert "localpatch_gate(1, 15)" in new


@pytest.mark.parametrize("change", [
    ('register("damage"', 'register("itemTileUpdated"'),          # the answer to the player's own action
    ('tes3.messageBox("This one is essential.")', 'tes3.messageBox("%s is essential.", e.reference.id)'),
])
def test_G8_leaves_user_feedback_and_dynamic_text_alone(change):
    assert not found(analyse(DAMAGE.replace(*change)), "G8")


def test_G8_per_frame_message_is_report_only():
    src = "event.register('simulate', function(e) if tes3.mobilePlayer.isFlying then tes3.messageBox('Too high') end end)\n"
    f = found(analyse(src), "G8")
    assert [x["conf"] for x in f] == ["report"] and not f[0]["edits"]


# ------------------------------------------------------------------------------------------------ U1
CLOCK = """local label
event.register("uiActivated", function(e)
    label = e.element:createBlock({ id = "x" }):createLabel({ id = "y" })
end, { filter = "MenuMulti" })
local function onClock()
    local now = os.date("%H:%M")
    if label then
        label.text = now
    end
end
event.register("enterFrame", onClock)
"""


def test_U1_label_text_is_written_only_when_it_differs():
    a = analyse(CLOCK)
    assert [f["conf"] for f in found(a, "U1")] == ["high"]
    new, _r = patched(CLOCK)
    assert "if label.text ~= now then label.text = now end" in new


@pytest.mark.parametrize("change", [
    ("label.text = now", "label.text = string.format('%s', now)"),     # a call: reading it twice differs
    (':createLabel({ id = "y" })', ':findChild("y")'),                  # not an element U1 knows it made
    ('register("enterFrame", onClock)', 'register("loaded", onClock)'),  # not per frame
])
def test_U1_only_plain_values_on_known_elements_per_frame(change):
    assert not found(analyse(CLOCK.replace(*change)), "U1")


# ------------------------------------------------------------------------------------------------ M1 + G2
CLOCK_UI_GLOBAL = """event.register("uiActivated", function(e)
    UI_Clock = e.element:createLabel({ id = "c" })
end, { filter = "MenuMulti" })
local function onClockUpdate()
    local t = os.date("*t")
    local s = t.hour .. ":" .. t.min
    if UI_Clock ~= nil then
        UI_Clock.text = s
    end
end
event.register("enterFrame", onClockUpdate)
"""


@pytest.mark.parametrize("level", ["high", "medium"])
def test_M1_and_G2_share_the_first_line_and_a_second_pass_is_a_no_op(level):
    new, rules = patched(CLOCK_UI_GLOBAL, level)
    assert {"M1", "U1"} <= set(rules)
    head = "local function onClockUpdate() if tes3.menuMode() then return end"
    if level == "medium":
        assert "G2" in rules and head + " if localpatch_gate(1, 0.35) then return end\n" in new
    else:
        assert "G2" not in rules and head + "\n" in new
    assert "if UI_Clock.text ~= s then UI_Clock.text = s end" in new


def test_gated_and_menu_guarded_see_either_order():
    for first, second in (("tes3.menuMode()", "localpatch_gate(1, 0.35)"), ("localpatch_gate(1, 0.35)", "tes3.menuMode()")):
        src = (f"local function f() if {first} then return end if {second} then return end local x = 1 end\n"
               "event.register('enterFrame', f)\n")
        a = analyse(src)
        fn = a.registrations[0][2]
        assert a.gated(fn) and a.menu_guarded(fn)
        assert not found(a, "M1") and not [g for g in found(a, "G2") if g["edits"]]


def test_KP3_wording_matches_the_shipped_keg_drip():
    assert "checkInterval" not in lf.KP3 and "once a second as shipped" in lf.KP3
