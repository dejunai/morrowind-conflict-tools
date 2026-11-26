"""mwsaveguard WBSR MCM switch can be turned on at the pre-game main menu; runtime work waits for loaded."""
from test_cr18_suite_logging import need_lua, run, src, wbsr_harness


@need_lua
def test_wbsr_bard_can_be_toggled_at_the_main_menu(tmp_path):
    script = wbsr_harness().replace('event.trigger("loaded", {})\n', "")
    run(tmp_path, script + r"""
assert(tes3.player == nil and tes3.mobilePlayer == nil, "the stub is the main menu: no player")
assert(BARD.wanted(), "on by default once WBSR is installed, even before a game is loaded")
assert(BARD.stats().bookends == nil, "no bookends until a game is loaded")
BARD.setWanted(false)
assert(BARD.wanted() == false and not BARD.enabled(), "turning it off at the menu is saved")
assert(BARD.stats().bookends == nil)
BARD.setWanted(true)
assert(BARD.wanted() == true)
assert(BARD.stats().bookends == nil, "toggling on at the menu only saves the setting")
tes3.player = { id = "player" }
tes3.mobilePlayer = { reference = tes3.player }
event.trigger("loaded", {})
assert(BARD.present() and BARD.enabled())
assert(BARD.stats().bookends == 9000, "runtime work runs on loaded")
BARD.setWanted(false)
assert(not BARD.enabled() and BARD.stats().bookends == nil, "in-game off removes the bookends")
tes3.player, tes3.mobilePlayer = nil, nil
BARD.setWanted(true)
assert(BARD.wanted() == true and BARD.stats().bookends == nil)
print("OK")
""")


def test_wbsr_mcm_switch_is_not_in_game_only():
    main = src("mwsaveguard", "main.lua")
    bard = src("mwsaveguard", "wbsr_bard.lua")
    section = main[main.index("Let saves through while a bard sings"):]
    assert "getter = function() return wbsrBard.wanted() end" in section
    assert "wbsrBard.setWanted(v)" in section
    assert "inGameOnly = false" in section
    assert "function M.wanted()" in bard and "function M.setWanted(v)" in bard
    setter = bard[bard.index("function M.setWanted"):]
    assert "tes3.player and tes3.mobilePlayer" in setter
