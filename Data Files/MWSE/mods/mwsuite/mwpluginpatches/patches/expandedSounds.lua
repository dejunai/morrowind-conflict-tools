-- Expanded Sounds' Float and the vanilla Sound_Boat_Creak script restart loops every frame when
-- GetSoundPlaying lies. Run both in Lua so each loaded source starts one loop.

local this = {}

local started = setmetatable({}, { __mode = "k" })

local function start(ref, sound, volume)
    if started[ref] ~= sound then
        if not tes3.getSoundPlaying({ sound = sound, reference = ref }) then
            tes3.playSound({ sound = sound, reference = ref, loop = true, volume = volume, pitch = 1.0 })
        end
        started[ref] = sound
    end
end

local function runFloat(e)
    local ref = e.reference
    if not ref then
        return
    end
    start(ref, "plx_ES_Water", 0.6)

    local context = ref.context
    local delta = e.delta or 0
    if not context or delta <= 0 then
        return
    end
    context.swingTime = 1
    context.timer = (context.timer or 0) + delta
    if context.timer < 1 then
        ref.orientation.x = ref.orientation.x + math.rad(2) * delta
    elseif context.timer < 3 then
        ref.orientation.x = ref.orientation.x - math.rad(2) * delta
    elseif context.timer < 4 then
        ref.orientation.x = ref.orientation.x + math.rad(2) * delta
    else
        context.timer = 0
        ref.orientation.x = ref.startingOrientation.x
    end
end

local function runBoatCreak(e)
    if e.reference then
        start(e.reference, "Boat Creak", 0.4)
    end
end

local function runBoatHull(e)
    if e.reference then
        start(e.reference, "Boat Hull", 0.4)
    end
end

local function runWaterSpout(e)
    if e.reference then
        start(e.reference, "Cave_Waterfall", 1.0)
    end
end

local function onDeactivated(e)
    started[e.reference] = nil
end

function this.init()
    if tes3.getScript("Float") then
        mwse.overrideScript("Float", runFloat)
    end
    if tes3.getScript("Sound_Boat_Creak") then
        mwse.overrideScript("Sound_Boat_Creak", runBoatCreak)
    end
    if tes3.getScript("Sound_Boat_Hull") then
        mwse.overrideScript("Sound_Boat_Hull", runBoatHull)
    end
    if tes3.getScript("Sound_Water_Spout") then
        mwse.overrideScript("Sound_Water_Spout", runWaterSpout)
    end
    event.register(tes3.event.referenceDeactivated, onDeactivated)
    mwse.log("[mwpluginpatches] Expanded Sounds: Float and boat/water loops run in Lua (one loop per source).")
end

return this
