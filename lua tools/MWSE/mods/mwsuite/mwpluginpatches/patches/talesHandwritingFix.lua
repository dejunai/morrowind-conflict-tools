-- Clean Tales of Seyda Neen: the "illegible handwriting" topic is learned while den_bottle runs (10..69) and hidden
-- once it is finished (70). Only the half that the loaded game needs is registered: the journal hook that teaches
-- the topic while the quest is not finished, the response filter once it is. Each comes off when its part is
-- over; the loaded hook stays so another save in the same session is checked again. By dej (dejunai).

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local talesHandwritingFix = {}
local ready = false
local filtering, learning = false, false

local TOPIC, QUEST, STARTED, FINISHED = "illegible handwriting", "den_bottle", 10, 70

-- Never ask for the note here: An-Drazh's line hands it over after its text is read, and a topic with no passing
-- response at that moment is never learned. Finished is 70: Nallaia still answers the topic at 60.
local function onInfoFilter(e)
    if not e.passes then return end          -- first: infoFilter runs for every response tried
    if e.dialogue and e.dialogue.id and e.dialogue.id:lower() == "illegible handwriting" then
        local journal = tes3.getJournalIndex({ id = "den_bottle" }) or 0
        if journal >= FINISHED then
            e.passes = false
            return false
        end
    end
end

-- for a save that started the quest while the topic was being hidden
local function learn(index)
    if index >= STARTED and index < FINISHED then tes3.addTopic({ topic = TOPIC }) end
end

local onJournal

-- the parts the quest stage needs: learning before 70, the filter from 70 on
local function settle(index)
    local finished = index >= FINISHED
    if finished and not filtering then
        filtering = true
        event.register(tes3.event.infoFilter, onInfoFilter)
    elseif not finished and filtering then
        filtering = false
        event.unregister(tes3.event.infoFilter, onInfoFilter)
    end
    if not finished and not learning then
        learning = true
        event.register(tes3.event.journal, onJournal)
    elseif finished and learning then
        learning = false
        event.unregister(tes3.event.journal, onJournal)
    end
end

onJournal = function(e)
    if e.topic and e.topic.id:lower() == QUEST then
        learn(e.index)
        if e.index >= FINISHED and not filtering then
            filtering = true                             -- the filter goes on now, for the very next responses
            event.register(tes3.event.infoFilter, onInfoFilter)
        end
        if e.index >= FINISHED then                      -- this hook comes off after the journal event is over
            intercept.afterDispatch(function() settle(tes3.getJournalIndex({ id = QUEST }) or 0) end)
        end
    end
end

local function onLoaded()
    local index = tes3.getJournalIndex({ id = QUEST }) or 0
    learn(index)
    settle(index)
end

function talesHandwritingFix.state() return learning, filtering end   -- for tests

function talesHandwritingFix.init()
    if ready then return true end
    if not config.talesHandwritingFixEnabled or not config.isTalesOfSeydaNeenActive() then
        return false
    end

    event.register(tes3.event.loaded, onLoaded)
    ready = true
    if tes3.player and tes3.getJournalIndex then onLoaded() end
    mwse.log("[mwpluginpatches] Clean Tales of Seyda Neen 'illegible handwriting': journal hook before the quest ends, filter after.")
    return true
end

return talesHandwritingFix
