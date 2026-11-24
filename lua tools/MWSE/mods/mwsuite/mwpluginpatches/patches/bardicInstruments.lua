--[[
    Musical Instruments Patch
    Mod: Bardic Inspiration
    Bardic Inspiration knows only lutes (staticData.lutes / idMapping), so an innkeeper tells a player carrying a drum
    to "come back when you have an instrument". Items on config.musicalInstruments count as instruments too: using one
    from the inventory or a quick key does what readying a lute does. They aren't swapped for a lute weapon, so there
    is no lute in hand and no lute animation (that needs a node only lute meshes have); the music is the mod's own.
--]]

local config = require("mwpluginpatches.config")

local this = {}

local function isListed(item)
    return item ~= nil and config.musicalInstruments[item.id:lower()] == true
end

function this.init()
    local BI = "mer.bardicInspiration."
    local common = require(BI .. "common")
    local animate = require(BI .. "controllers.animationController")
    local songs = require(BI .. "controllers.songController")
    local performances = require(BI .. "data.performances")
    local messages = require(BI .. "messages.messages")

    local hasLute = common.hasLute
    common.hasLute = function(...)
        if hasLute(...) then return true end
        for _, stack in pairs(tes3.player.object.inventory) do
            if isListed(stack.object) then return true end
        end
        return false
    end

    local playLute = animate.play
    animate.play = function(...)
        local held = tes3.getEquippedItem({ actor = tes3.player, objectType = tes3.objectType.weapon })
        if held and common.isLute(held.object, held.itemData) then return playLute(...) end
        tes3.setVanityMode({ enabled = true })
        common.disableControls()
    end

    -- lutePlayController's conditions, which it keeps to itself
    local function perform()
        if common.data.songPlaying then return end
        local cell = tes3.mobilePlayer.cell
        if not cell.isInterior or cell.behavesAsExterior then
            if common.data.travelPlay then          -- a lute stops when put away; an instrument when used again
                common.stopMusic()
            else
                songs.playRandom()
            end
            return
        end
        local inTavern = false
        for ref in tes3.player.cell:iterateReferences(tes3.objectType.npc) do
            if common.isInnkeeper(ref) then
                inTavern = true
                break
            end
        end
        if not inTavern then return tes3.messageBox(messages.notTavern) end
        local gig = performances.getCurrent()
        if not gig then return tes3.messageBox(messages.noGigScheduled) end
        if tes3.worldController.hour.value <= 18 then return tes3.messageBox(messages.notNightTime) end
        if gig.state == performances.STATE.PLAYED then return tes3.messageBox(messages.alreadyPlayed) end
        if gig.state == performances.STATE.SKIP then return end
        songs.showMenu()
    end

    event.register("equip", function(e)
        if e.reference ~= tes3.player or not common.config.enabled or not isListed(e.item) then return end
        perform()
        return false
    end)

    mwse.log("[mwpluginpatches] Bardic Inspiration musical instrument whitelist active.")
end

return this
