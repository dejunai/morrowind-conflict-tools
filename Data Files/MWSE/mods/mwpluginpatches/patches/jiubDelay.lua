local config = require("mwpluginpatches.config")

local jiubDelay = {}

local JIUB_RUMOR_INFO_ID = "1453113367223718194"

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

local function onSimulate(e)
    if not config.jiubDelayEnabled or not config.isFriendsAndFrensActive() then return end

    -- Check if character generation is complete (journal enabled, Census Office exited)
    local charGenState = tes3.findGlobal("CharGenState")
    if not charGenState or charGenState.value ~= -1 then
        return
    end

    local data = getPlayerData()
    if not data then return end

    data.secondsSinceCensus = (data.secondsSinceCensus or 0) + e.delta

    local requiredSeconds = math.max(0, (config.jiubDelayMinutes or 5) * 60)
    if data.secondsSinceCensus >= requiredSeconds and not data.unlockedLogged then
        data.unlockedLogged = true
        mwse.log("[mwpluginpatches] Post-census delay of %s minutes reached. Jiub companion rumor is now eligible to appear.",
            config.jiubDelayMinutes)
    end
end

local function onInfoFilter(e)
    if not config.jiubDelayEnabled or not config.isFriendsAndFrensActive() then return end
    if not e.passes or not e.info then return end

    local isJiubRumor = (tostring(e.info.id) == JIUB_RUMOR_INFO_ID)
    if not isJiubRumor then return end

    -- 1. Exclude while still in CharGen (before journal / release papers)
    local charGenState = tes3.findGlobal("CharGenState")
    if charGenState and charGenState.value ~= -1 then
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
    local requiredSeconds = math.max(0, (config.jiubDelayMinutes or 5) * 60)
    if not data or (data.secondsSinceCensus or 0) < requiredSeconds then
        e.passes = false
        return
    end
end

local function onMobileActivated(e)
    if not config.jiubSyncAppearance then return end
    if e.reference and e.reference.object.id:lower() == "aa_comp_jiub" then
        syncJiubAppearance()
    end
end

function jiubDelay.init()
    if not config.jiubDelayEnabled or not config.isFriendsAndFrensActive() then
        return
    end

    syncJiubAppearance()
    event.register(tes3.event.simulate, onSimulate)
    event.register(tes3.event.infoFilter, onInfoFilter)
    event.register(tes3.event.mobileActivated, onMobileActivated)
    event.register(tes3.event.loaded, syncJiubAppearance)

    mwse.log("[mwpluginpatches] Friends & Frens Jiub Companion Delayer patch active.")
end

return jiubDelay
