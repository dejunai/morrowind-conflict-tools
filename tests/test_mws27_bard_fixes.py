"""MWS-27: the bard fixes. (1) mwsaveguard reads MWSE's event table through any number of wrapped event.register
functions (mwguard's origRegister, mwhangwatch's realRegister, mwpluginpatches' nativeRegister), so the WBSR bard lift
and the swallowed-save handler list work. (2) It logs the final save name and whether the renamers were reached, and
asks again for a swallowed save. (3) mwperformers counts MWSE's "Animation file failed to load" for a plain animation
as loaded (the model was swapped before the throw), so the performer's own animation comes back, with a backstop."""
import subprocess

from test_cr18_suite_logging import SAVEGUARD, LUAJIT, need_lua, own_log, run, wbsr_harness
from test_performers_bards import ANIM_SCRIPT, CELL_SCRIPT, MOD

import pytest

# the three wrappers of the game, innermost first, each keeping the register it wraps under its own name
WRAPPED = r'''
do
  local origRegister = event.register                              -- mwguard
  event.register = function(n, cb, o) return origRegister(n, cb, o) end
  local realRegister = event.register                              -- mwhangwatch
  event.register = function(n, cb, o) return realRegister(n, cb, o) end
  local nativeRegister = event.register                            -- mwpluginpatches
  local wrapperFor = function(cb) return cb end
  event.register = function(n, cb, o, ...) return nativeRegister(n, wrapperFor(cb), o, ...) end
end
'''


@need_lua
def test_wbsr_bard_lift_works_behind_wrapped_event_register(tmp_path):
    script = wbsr_harness().replace("\nfunction event.unregister(name, cb)", WRAPPED + "\nfunction event.unregister(name, cb)", 1)
    run(tmp_path, script + r'''
assert(BARD and BARD.present() and BARD.enabled(), "WBSR is found through three wrappers")
assert(BARD.stats().bookends == 9000)
local raflod = { id = "raflod the braggart00000000", object = { name = "Raflod the Braggart", id = "raflod the braggart" } }
event.trigger("addTempSound", { path = "Vo\\Bard\\Red Diamond.mp3", reference = raflod, isVoiceover = true })
assert(not WBSR.blocking(), "WBSR's save block is lifted for a bard song")
local blocker = load("return function() return false end", "@Data Files\\MWSE\\mods\\someone\\else.lua")()
event.register("save", blocker, { priority = 9000 })
event.trigger("save", { filename = "quiksave", name = "Quicksave" })
nextFrame()
local hit
for _, l in ipairs(logged) do if l:find("swallowed by another mod") then hit = l end end
assert(hit and hit:find("someone\\else.lua:1 (priority 9000)", 1, true), "the handler list is read: " .. tostring(hit))
print("OK")
''')


@need_lua
def test_final_save_name_and_whether_the_renamer_was_reached(tmp_path):
    run(tmp_path, SAVEGUARD + r'''
event.register("save", function(e)                     -- Sophisticated Save System: default priority
  if e.filename == "quiksave" then e.filename = "sss_q_1795779230" e.name = "Quicksave (11/26/26 19:33:50)" end
end)
-- 1. a save that goes ahead: the final name is logged
event.trigger("save", { filename = "quiksave", name = "Quicksave" })
nextFrame()
-- 2. held back above the renamer (WBSR, 9147): nothing renamed it
local hold = true
event.register("save", function() if hold then return false end end, { priority = 9147 })
event.trigger("save", { filename = "quiksave", name = "Quicksave" })
nextFrame()
local no
for _, l in ipairs(logged) do if l:find("swallowed by another mod") then no = l end end
assert(no and no:find("Renamers reached: no, a handler above priority 0", 1, true), tostring(no))
-- 3. held back below it: renamed first
hold = false
logged = {}
event.register("save", function() return false end, { priority = -500 })
event.trigger("save", { filename = "quiksave", name = "Quicksave" })
nextFrame()
local yes
for _, l in ipairs(logged) do if l:find("swallowed by another mod") then yes = l end end
assert(yes and yes:find("Renamers reached: yes, it was renamed to 'sss_q_1795779230'", 1, true), tostring(yes))
print("OK")
''')
    log = own_log(tmp_path, "mwsaveguard.log")
    assert "Save goes ahead as: file='sss_q_1795779230', name='Quicksave (11/26/26 19:33:50)' (requested as 'quiksave')" in log
    assert "Save requested (name as asked, before any renamer): file='quiksave'" in log
    assert "renamers reached: no" in log and "renamers reached: yes, it was renamed to 'sss_q_1795779230'" in log


RETRY = r'''
local boxes, timers = {}, {}
tes3.messageBox = function(m) boxes[#boxes + 1] = type(m) == "table" and m.message or m end
tes3.player = { id = "player" }
tes3.onMainMenu = function() return false end
tes3.saveGame = function(p)
  local e = event.trigger("save", { filename = p.file, name = p.name })
  if not e.block then event.trigger("saved", { filename = e.filename, name = e.name }) end
end
timer.start = function(t) local h = { cb = t.callback, cancelled = false } h.cancel = function() h.cancelled = true end
                          timers[#timers + 1] = h return h end
local function tick() local l = timers timers = {} for _, h in ipairs(l) do if not h.cancelled then h.cb() end end end
local holding = true
event.register("save", function() if holding then return false end end, { priority = 9147 })
local function press(file) event.trigger("save", { filename = file, name = "Quicksave" }) nextFrame() end
'''


@need_lua
def test_a_swallowed_quicksave_is_asked_for_again_until_it_goes_through(tmp_path):
    run(tmp_path, SAVEGUARD + RETRY + r'''
press("quiksave")
assert(#timers == 1, "a retry is waiting")
assert(#boxes == 1 and boxes[1]:find("holding saves back", 1, true), "the player is told once")
CLOCK = 101
tick()                                                   -- try 1: still held back
nextFrame()
assert(#boxes == 1 and #timers == 1, "no second message; asking again")
press("autosave")                                        -- an autosave never replaces the save you asked for
assert(#timers == 1 and #boxes == 1)
CLOCK = 102
holding = false
tick()                                                   -- try 2 goes through
nextFrame()
assert(boxes[2] == "mwsaveguard: saved." and #boxes == 2, tostring(boxes[2]))
assert(#timers == 0, "nothing left to retry")
print("OK")
''')
    log = own_log(tmp_path, "mwsaveguard.log")
    assert "Asking again for save 'quiksave' (try 1)." in log and "(try 2)." in log
    assert "The save went through on try 2." in log


@need_lua
def test_a_save_that_stays_held_back_is_given_up_with_a_message(tmp_path):
    run(tmp_path, SAVEGUARD + RETRY + r'''
press("quiksave")
CLOCK = 101
tick(); nextFrame()
CLOCK = 130                                              -- past the 20 s
tick()
assert(#timers == 0, "given up")
assert(boxes[#boxes]:find("did not go through", 1, true), tostring(boxes[#boxes]))
print("OK")
''')
    assert "Gave up on save 'quiksave'" in own_log(tmp_path, "mwsaveguard.log")


@need_lua
def test_a_swallowed_autosave_is_retried_quietly(tmp_path):
    run(tmp_path, SAVEGUARD + RETRY + r'''
press("autosave")
assert(#timers == 1 and #boxes == 0, "retried, no message for a save nobody asked for")
CLOCK = 101
holding = false
tick(); nextFrame()
assert(#boxes == 1 and boxes[1] == "mwsaveguard: saved.", tostring(boxes[1]))
print("OK")
''')


@need_lua
def test_retry_can_be_switched_off(tmp_path):
    script = (SAVEGUARD.replace("c.logToMWSE = true", "c.logToMWSE = true c.retrySwallowedSaves = false")
              + RETRY + r'''
press("quiksave")
assert(#timers == 0 and #boxes == 0, "only logged")
print("OK")
''')
    run(tmp_path, script)


def test_retry_setting_is_in_the_mcm():
    from test_cr18_suite_logging import src
    main = src("mwsaveguard", "main.lua")
    assert "retrySwallowedSaves = true" in main
    assert 'id = "retrySwallowedSaves"' in main


def lua(script):
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout


THROWS = ('loadAnimation = function(p) calls[#calls + 1] = "load:" .. tostring(p.file or "own") '
          'if p.file then error("Animation file failed to load.") end end,')


@need_lua
def test_the_dialogue_animation_comes_back_though_the_plain_load_throws():
    script = ANIM_SCRIPT.replace("DIALOGUE_ANIMATION", "true").replace("[[MOD]]", "[[" + MOD + "]]")
    old = 'loadAnimation = function(p) calls[#calls + 1] = "load:" .. tostring(p.file or "own") end,'
    assert old in script
    script = script.replace(old, THROWS)
    head = script.split('\nfire("initialized")\n')[0]
    lua(head + r'''
fire("initialized")
local function has(s) for _, c in ipairs(calls) do if c == s then return true end end return false end
-- Raflod: a script performer whose own animation is am\am_bard2.nif. The plain load swaps his model, then throws.
speaker = performer("am\\am_bard2.nif", "DM_Bard_script", { 0, 0, 255 }, true)
fire("uiActivated")
check(calls[1] == "load:base_anim.nif", "the plain animation was asked for")
check(calls[2] == "play group=0" and calls[3] == "update t=0", "the dialogue goes on to the idle after the throw")
fire("menuExit")
check(not has("load:own"), "he waits plain for the pause")
fireTimers()
check(has("load:own"), "his own animation is given back although the plain load threw")
local n = #calls
fire("menuExit"); fireTimers(); fire("cellChanged")
check(#calls == n, "nothing more is done once it is back")

-- the backstop: the restore itself missed him (his handle flapped), so the next menuExit gives it back
reset()
local flapNext = false
local real = tes3.makeSafeObjectHandle
tes3.makeSafeObjectHandle = function(r)
  return { valid = function() if flapNext then flapNext = false return false end return true end,
           getObject = function() return r end }
end
speaker = performer("am\\am_bard2.nif", "DM_Bard_script", { 0, 0, 255 }, true)
fire("uiActivated")
check(not has("load:own"), "not given back yet")
fire("menuExit")
check(not has("load:own"), "waiting out the pause")
flapNext = true                              -- the restore does not find him ...
fireTimers()
check(has("load:own"), "... the backstop gives his own animation back")
tes3.makeSafeObjectHandle = real

-- a dead performer is never touched by the backstop
reset()
speaker = performer("am\\am_bard2.nif", "DM_Bard_script", { 0, 0, 255 }, true)
fire("uiActivated")
speaker.reference.mobile.isDead = true
fire("menuExit"); fireTimers(); fire("cellChanged")
check(not has("load:own"), "a dead performer is left as he is")
print("ok")
''')


@need_lua
def test_one_performer_per_inn_when_the_plain_load_throws():
    script = CELL_SCRIPT.replace("[[MOD]]", "[[" + MOD + "]]")
    old = 'loadAnimation = function(p) anims[p.reference] = p.file or "own"; p.reference.sceneNode = { n = 2 } end,'
    assert old in script
    script = script.replace(old, 'loadAnimation = function(p) anims[p.reference] = p.file or "own"; p.reference.sceneNode = { n = 2 } '
                                 'if p.file then error("Animation file failed to load.") end end,')
    assert "mwse = { log = function() end," in script and script.rstrip().endswith('print("ok")')
    script = script.replace("mwse = { log = function() end,",
                            "NOTES = {}; mwse = { log = function(f, ...) NOTES[#NOTES + 1] = string.format(f, ...) end,")
    script = script.rstrip()[:-len('print("ok")')] + '''
assert(#NOTES >= 1 and NOTES[1]:find("expected and harmless", 1, true) and NOTES[1]:find("lutist", 1, true), tostring(NOTES[1]))
print("ok")
'''
    lua(script)

def test_restore_pause_is_a_game_time_timer_with_a_slider():
    with open(MOD, encoding="utf-8") as f:
        main = f.read()
    assert "restoreDelay = 3" in main and "type = timer.simulate" in main
    assert 'id = "restoreDelay"' in main and "createSlider" in main

@need_lua
def test_expected_animation_error_is_announced_in_mwse_log_before_it_happens():
    script = ANIM_SCRIPT.replace("DIALOGUE_ANIMATION", "true").replace("[[MOD]]", "[[" + MOD + "]]")
    head = script.split('\nfire("initialized")\n')[0]
    lua(head + r'''
fire("initialized")
speaker = performer("am\\am_bard2.nif", "DM_Bard_script", { 0, 0, 255 }, true)
speaker.reference.object.name = "Raflod the Braggart"
local orderAtThrow
tes3.loadAnimation = function(p) if p.file then orderAtThrow = #MWLOG end calls[#calls + 1] = "load:" .. tostring(p.file or "own") end
fire("uiActivated")
check(#MWLOG == 1 and orderAtThrow == 1, "the notice is written before the swap: " .. tostring(orderAtThrow))
local m = MWLOG[1]
check(m:find("NOTICE", 1, true) and m:find("Raflod the Braggart (bard)", 1, true), "it names the NPC: " .. m)
check(m:find("'base_anim.nif'", 1, true), "it names the file: " .. m)
check(m:find("Animation file failed to load", 1, true) and m:find("expected and harmless", 1, true)
      and m:find("restore of the performer's own animation are unaffected", 1, true), "it says what follows is harmless: " .. m)
fire("menuExit"); fireTimers()
check(#MWLOG == 1, "the restore is not announced: it does not throw")
print("ok")
''')
