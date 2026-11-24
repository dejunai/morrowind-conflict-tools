--[[
Yet Another Better Sounds Patch: SwampSoundScript (on Sound_Swamp_1..3), run in Lua.

The original runs every frame outdoors: by day (after 6:00, before 21:00) it stops the night loops and keeps one
of "swamp 2" / "swamp 3" playing; by night one of "swampNight" / "swampNight 2"; in weather 5 and worse (ash,
blight, snow, blizzard) it stops them all. It decides from GetSoundPlaying, and the engine can answer "not
playing" while a loop plays, so it started a new random loop every frame (mwsoundguard: "RUNAWAY loop: swamp 2").
Here the same choices are made, but the loop this patch started on each activator is remembered until the
activator unloads, so each one gets a single loop that changes only with day, night and weather.
The script's "daytim" variable is used as before (it keeps its value between 0:00 and 6:00).
]]

local swampSound = {}

local SCRIPT = "SwampSoundScript"
local DAY = { "swamp 2", "swamp 3" }
local NIGHT = { "swampNight", "swampNight 2" }

local started = setmetatable({}, { __mode = "k" })   -- activator -> the loop this patch started on it

local function inList(id, list)
    return id == list[1] or id == list[2]
end

local function stop(ref, list)
    for _, id in ipairs(list) do
        if started[ref] == id or tes3.getSoundPlaying({ sound = id, reference = ref }) then
            tes3.removeSound({ sound = id, reference = ref })
        end
    end
    if started[ref] and inList(started[ref], list) then
        started[ref] = nil
    end
end

local function run(e)
    local ref = e.reference
    local cell = ref and ref.cell
    if not cell or cell.isInterior then
        return                                                -- GetInterior == 0 only
    end
    local weather = tes3.getCurrentWeather()
    if not weather or weather.index >= 5 then
        stop(ref, DAY)
        stop(ref, NIGHT)
        return
    end
    local context = ref.context
    local hour = tes3.worldController.hour.value
    local daytim = context and context.daytim or 0
    if hour < 21 then
        if hour > 6 then
            daytim = 1
            stop(ref, NIGHT)
        end
    else
        daytim = 0
        stop(ref, DAY)
    end
    if context then
        context.daytim = daytim
    end
    local want = daytim == 1 and DAY or NIGHT
    if started[ref] and inList(started[ref], want) then
        return                                                -- this period's loop is already ours
    end
    for _, id in ipairs(want) do
        if tes3.getSoundPlaying({ sound = id, reference = ref }) then
            started[ref] = id
            return
        end
    end
    local id = want[math.random(2)]
    tes3.playSound({ sound = id, reference = ref, loop = true, volume = 1.0, pitch = 1.0 })
    started[ref] = id
end

local function onDeactivated(e)
    started[e.reference] = nil                   -- unloaded: the engine stopped its sounds
end

function swampSound.init()
    if not tes3.getScript(SCRIPT) then
        return
    end
    mwse.overrideScript(SCRIPT, run)
    event.register(tes3.event.referenceDeactivated, onDeactivated)
    mwse.log("[mwpluginpatches] Yet Another Better Sounds Patch: %s runs in Lua (one loop per swamp sound).",
        SCRIPT)
end

return swampSound
