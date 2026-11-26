"""mwcriminal locked-notice MCM: the sound always plays; the toggle only controls the message."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwcriminal")


def test_locked_notice_mcm_says_the_sound_always_plays():
    mcm = open(os.path.join(MOD, "mcm.lua"), encoding="utf-8").read()
    main = open(os.path.join(MOD, "main.lua"), encoding="utf-8").read()
    assert "The locked door or chest sound always plays" in mcm
    fn = main[main.index("local function lockedFeedback"):main.index("local function restoreOpener")]
    assert "tes3.playSound" in fn
    assert "if config.lockedNotification then tes3ui.showNotifyMenu" in fn
    assert fn.index("tes3.playSound") < fn.index("if config.lockedNotification")
    # playSound is not behind the lockedNotification guard
    sound_line = [ln for ln in fn.splitlines() if "tes3.playSound" in ln][0]
    assert "lockedNotification" not in sound_line
