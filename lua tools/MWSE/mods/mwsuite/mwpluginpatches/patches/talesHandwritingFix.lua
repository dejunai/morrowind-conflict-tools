local config = require("mwpluginpatches.config")

local talesHandwritingFix = {}

local TOPIC, QUEST, STARTED, FINISHED = "illegible handwriting", "den_bottle", 10, 70

-- Never ask for the note here: An-Drazh's line hands it over after its text is read, and a topic with no passing
-- response at that moment is never learned. Finished is 70: Nallaia still answers the topic at 60.
local function onInfoFilter(e)
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

local function onJournal(e)
    if e.topic and e.topic.id:lower() == QUEST then learn(e.index) end
end

local function onLoaded()
    learn(tes3.getJournalIndex({ id = QUEST }) or 0)
end

function talesHandwritingFix.init()
    if not config.talesHandwritingFixEnabled or not config.isTalesOfSeydaNeenActive() then
        return
    end

    event.register(tes3.event.infoFilter, onInfoFilter)
    event.register(tes3.event.journal, onJournal)
    event.register(tes3.event.loaded, onLoaded)
    mwse.log("[mwpluginpatches] Clean Tales of Seyda Neen 'illegible handwriting' filter active.")
end

return talesHandwritingFix
