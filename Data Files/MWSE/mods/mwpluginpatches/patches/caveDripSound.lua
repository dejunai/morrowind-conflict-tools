--[[
Cave Drips.ESP: R0_Sound_Cave_Drip_scr, run in Lua.

The original runs every frame on each drip activator:
    if ( CellChanged == 0 )
        if ( GetSoundPlaying "Cave Drip" == 0 )
            PlayLoopSound3DVP "Cave Drip", 1.0, 1.0
and the engine can answer "not playing" while the loop plays, so the loop is started again every frame
(mwsoundguard logged over 22,000 blocked restarts on one activator). Here the loop is started once per
activator while it stays loaded; the engine stops it when the activator unloads, and it starts again on return.
The rest of the script (placing the drip visuals once, at the water level when the cell has water) is kept
as it was, with its own "visset" variable, so a save stays the same if this patch is turned off.
]]

local caveDripSound = {}

local SCRIPT = "R0_Sound_Cave_Drip_scr"
local SOUND = "Cave Drip"

local started = setmetatable({}, { __mode = "k" })   -- activators whose loop this patch started

local function place(id, ref, position)
    tes3.createReference({ object = id, position = position, orientation = { 0, 0, 0 }, cell = ref.cell })
end

local function run(e)
    local ref = e.reference
    if not ref then
        return
    end
    if not started[ref] then
        if not tes3.getSoundPlaying({ sound = SOUND, reference = ref }) then
            tes3.playSound({ sound = SOUND, reference = ref, loop = true, volume = 1.0, pitch = 1.0 })
        end
        started[ref] = true
    end

    local context = ref.context
    if not context or context.visset == 1 then
        return
    end
    local pos = ref.position
    local water = ref.cell and ref.cell.waterLevel                -- nil: no water (GetWaterLevel's -10000 case)
    if water and water > -10000 then
        place("R0_Sound_Cave_Drip_vis", ref, { pos.x, pos.y, water })
        place("R0_Sound_Cave_Drip_dmy", ref, { pos.x, pos.y, water })
    else
        place("R0_Sound_Cave_Drip_vis", ref, { pos.x, pos.y, pos.z })   -- PlaceAtMe, distance 0
    end
    context.visset = 1
end

local function onDeactivated(e)
    started[e.reference] = nil                   -- unloaded: the engine stopped its sounds
end

function caveDripSound.init()
    if not tes3.getScript(SCRIPT) then
        return
    end
    mwse.overrideScript(SCRIPT, run)
    event.register(tes3.event.referenceDeactivated, onDeactivated)
    mwse.log("[mwpluginpatches] Cave Drips: %s runs in Lua (one loop per drip, no per-frame restarts).", SCRIPT)
end

return caveDripSound
