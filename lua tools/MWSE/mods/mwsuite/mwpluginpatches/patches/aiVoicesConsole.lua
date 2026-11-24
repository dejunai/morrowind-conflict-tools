-- Voices of Vvardenfell prints every line it plays or looks for to the player's console. That is the mod's own
-- behaviour, not a bug, so its file is left as released and only those two messages are held back here.

local this = {}

local PLAYING, MISSING = "VoV: Playing Line at ", "VoV: Missing Line at "

function this.init()
    local logToConsole = tes3ui.logToConsole
    tes3ui.logToConsole = function(text, ...)
        if type(text) == "string" and (text:sub(1, #PLAYING) == PLAYING or text:sub(1, #MISSING) == MISSING) then
            return
        end
        return logToConsole(text, ...)
    end
    mwse.log("[mwpluginpatches] Voices of Vvardenfell: routine console lines are suppressed.")
end

return this
