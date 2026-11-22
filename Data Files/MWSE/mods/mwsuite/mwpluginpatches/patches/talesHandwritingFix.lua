local config = require("mwpluginpatches.config")

local talesHandwritingFix = {}

local function onInfoFilter(e)
    if e.dialogue and e.dialogue.id and e.dialogue.id:lower() == "illegible handwriting" then
        local journal = tes3.getJournalIndex({ id = "den_bottle" }) or 0
        if journal >= 50 then
            e.passes = false
            return false
        end
        if tes3.getItemCount({ reference = tes3.player, item = "den_message_bottle2" }) <= 0 then
            e.passes = false
            return false
        end
    end
end

function talesHandwritingFix.init()
    if not config.talesHandwritingFixEnabled or not config.isTalesOfSeydaNeenActive() then
        return
    end

    event.register(tes3.event.infoFilter, onInfoFilter)
    mwse.log("[mwpluginpatches] Clean Tales of Seyda Neen 'illegible handwriting' filter active.")
end

return talesHandwritingFix
