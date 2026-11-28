-- Friends & Frens: hold back the Jiub companion rumor until a configurable number of minutes after
-- the player leaves chargen (Census Office / journal enabled, CharGenState == -1), and keep it from
-- NPCs still in the Census Office or named as chargen staff while the delay is running. Optionally
-- copy the vanilla chargen Jiub's head and hair onto aa_comp_jiub.
--
-- Once the delay has been reached, or on a save load where it already has, every handler this patch
-- registered is removed (simulate, infoFilter, mobileActivated) and nothing of it stays resident
-- for the rest of the session. A thin loaded handler is kept so a new game started later in the
-- same session can re-arm. Appearance is synced once more as the handlers come off. By dej (dejunai).

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local jiubDelay = {}

local JIUB_RUMOR_INFO_ID = "1453113367223718194"

local ready = false
local armed = false
local counting = false
local infoRegistered = false
local mobileRegistered = false

local function getPlayerData()
    if not tes3.player then return nil end
    local data = tes3.player.data
    if not data then return nil end
    data.mwpluginpatches_jiub = data.mwpluginpatches_jiub or data.FriendsAndFrensJiub or {
        secondsSinceCensus = 0,
        unlockedLogged = false,
    }
    return data.mwpluginpatches_jiub
end

local function syncJiubAppearance()
    if not config.jiubSyncAppearance then return end

    local vanillaJiub = tes3.getObject("chargen name")
    local compJiub = tes3.getObject("aa_comp_jiub")

    if vanillaJiub and compJiub then
        if compJiub.head ~= vanillaJiub.head or compJiub.hair ~= vanillaJiub.hair then
            compJiub.head = vanillaJiub.head
            compJiub.hair = vanillaJiub.hair
            mwse.log("[mwpluginpatches] Synchronized aa_comp_jiub appearance with chargen name (Head: %s, Hair: %s)",
                vanillaJiub.head and vanillaJiub.head.id or "default",
                vanillaJiub.hair and vanillaJiub.hair.id or "default")
        end
    end
end

-- globals are base objects that live as long as the game
local charGenGlobal
local function charGenState()
    if not charGenGlobal then charGenGlobal = tes3.findGlobal("CharGenState") end
    return charGenGlobal
end

local function requiredSeconds()
    return math.max(0, (config.jiubDelayMinutes or 5) * 60)
end

local function delayReached()
    local data = getPlayerData()
    return data ~= nil and (data.secondsSinceCensus or 0) >= requiredSeconds()
end

local onInfoFilter, onMobileActivated, onLoaded, unload

local function onSimulate(e)
    if not config.jiubDelayEnabled then return end

    -- Check if character generation is complete (journal enabled, Census Office exited)
    local cg = charGenState()
    if not cg or cg.value ~= -1 then
        return
    end

    local data = getPlayerData()
    if not data then return end

    data.secondsSinceCensus = (data.secondsSinceCensus or 0) + e.delta

    if data.secondsSinceCensus >= requiredSeconds() then
        if not data.unlockedLogged then
            data.unlockedLogged = true
            mwse.log("[mwpluginpatches] Post-census delay of %s minutes reached. Jiub companion rumor is now eligible to appear.",
                config.jiubDelayMinutes)
        end
        intercept.afterDispatch(function()
            if armed then unload("delay reached; handlers removed.") end
        end)
    end
end

local function startCounting()
    if counting then return end
    counting = true
    event.register(tes3.event.simulate, onSimulate)
end

local function stopCounting()
    if not counting then return end
    counting = false
    event.unregister(tes3.event.simulate, onSimulate)
end

unload = function(reason)
    stopCounting()
    if infoRegistered then
        event.unregister(tes3.event.infoFilter, onInfoFilter)
        infoRegistered = false
    end
    if mobileRegistered then
        event.unregister(tes3.event.mobileActivated, onMobileActivated)
        mobileRegistered = false
    end
    syncJiubAppearance()
    armed = false
    if reason then
        mwse.log("[mwpluginpatches] Friends & Frens Jiub companion delay: %s", reason)
    end
end

local function arm()
    if armed then return end
    armed = true
    syncJiubAppearance()
    if not infoRegistered then
        event.register(tes3.event.infoFilter, onInfoFilter)
        infoRegistered = true
    end
    if not mobileRegistered then
        event.register(tes3.event.mobileActivated, onMobileActivated)
        mobileRegistered = true
    end
    startCounting()
end


onInfoFilter = function(e)
    if not e.passes or not e.info then return end
    if not config.jiubDelayEnabled then return end

    local isJiubRumor = (tostring(e.info.id) == JIUB_RUMOR_INFO_ID)
    if not isJiubRumor then return end

    -- 1. Exclude while still in CharGen (before journal / release papers)
    local cg = charGenState()
    if cg and cg.value ~= -1 then
        e.passes = false
        return
    end

    -- 2. Exclude NPCs located inside the Census & Excise Office
    if config.jiubExcludeCensusOffice then
        local cell = e.reference and e.reference.cell
        if cell then
            local cellId = cell.id:lower()
            local editorName = cell.editorName and cell.editorName:lower() or ""
            if string.find(cellId, "census and excise") or string.find(editorName, "census and excise") then
                e.passes = false
                return
            end
        end

        local actorId = e.reference and e.reference.object.id:lower() or ""
        if string.find(actorId, "chargen") or actorId == "socucius ergalla" or actorId == "sellus gravius" then
            e.passes = false
            return
        end
    end

    -- 3. Check post-census gameplay timer
    local data = getPlayerData()
    if not data or (data.secondsSinceCensus or 0) < requiredSeconds() then
        startCounting()
        e.passes = false
        return
    end

    -- the delay is already reached; this call is allowed, and the handlers come off after this event
    intercept.afterDispatch(function()
        if armed then unload("delay already reached; handlers removed.") end
    end)
end

onMobileActivated = function(e)
    if not config.jiubSyncAppearance then return end
    if e.reference and e.reference.object.id:lower() == "aa_comp_jiub" then
        syncJiubAppearance()
    end
end

onLoaded = function()
    charGenGlobal = nil   -- a new load may have a different global object
    if not config.jiubDelayEnabled then
        unload()
        return
    end
    if delayReached() then
        unload("already reached on this save; handlers not kept loaded.")
    else
        arm()
    end
end

function jiubDelay.init()
    if ready then return true end
    if not config.jiubDelayEnabled or not config.isFriendsAndFrensActive() then
        return false
    end
    if type(event) ~= "table" or type(event.register) ~= "function" then return false end
    event.register(tes3.event.loaded, onLoaded)
    ready = true
    if tes3.player then onLoaded() end
    mwse.log("[mwpluginpatches] Friends & Frens Jiub Companion Delayer will arm after a load while the delay is pending, then unload.")
    return true
end

return jiubDelay