local config = require("mwcompanions.config")

local function save()
    mwse.saveConfig("mwcompanions", config)
    event.trigger("mwcompanions:changed")
end

local template = mwse.mcm.createTemplate({ name = "mwcompanions", onClose = save })
local page = template:createSideBarPage({
    label = "Settings",
    description = "Followers, warping and follower combat in one mod. Turn a switch on only after turning the "
        .. "matching option off in Smart Companions (or Attend Me's teleport); mwcompanions logs a warning when both are on.",
})

local function yesNo(parent, id, label, description)
    parent:createYesNoButton({ label = label, description = description,
        variable = mwse.mcm.createTableVariable({ id = id, table = config }) })
end

local function slider(parent, id, label, min, max, step)
    parent:createSlider({ label = label, min = min, max = max, step = step, jump = step * 10,
        variable = mwse.mcm.createTableVariable({ id = id, table = config }) })
end

page:createYesNoButton({ label = "Enable mwcompanions", description = "Master switch. Nothing below does anything while this is off.",
    variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }) })

local move = page:createCategory("Following")
yesNo(move, "warp", "Warp followers to the player",
    "Followers farther away than the distance below, or left in another loaded cell, appear behind the player. Companions and summons in a fight stay in it. Replaces Smart Companions' warp. When Attend Me's auto-teleport is enabled, Attend Me handles warping instead.")
slider(move, "warpDistance", "Warp distance: %s", 500, 8000, 100)
yesNo(move, "levitateWater", "Followers levitate and water walk with the player",
    "While the player levitates or walks on water, followers do too; it ends when the player's does.")
yesNo(move, "followerTraits", "Follower traits",
    "Followers never raise an alarm; follower NPCs breathe water and get acrobatics 150 and athletics 220, so they keep up.")
yesNo(move, "muteOnCellChange", "Quiet followers after a cell change",
    "Followers' attack and greeting lines are skipped for 3 seconds after entering a cell.")
yesNo(move, "noSneakActivate", "Don't activate followers while sneaking",
    "Activating a follower while sneaking does nothing, so a companion isn't pickpocketed by accident.")

local fight = page:createCategory("Combat")
yesNo(fight, "noFriendlyFire", "No friendly fire",
    "The player and followers can't hurt each other with weapons or harmful spells, and a stray hit doesn't turn them hostile. Soul-trapping a non-companion follower still works.")
yesNo(fight, "resilient", "Followers collapse instead of dying",
    "A killing blow knocks a follower out instead; it wakes up after the time below and follows again.")
slider(fight, "collapseSeconds", "Collapse time: %s s", 10, 300, 5)
slider(fight, "collapseHealth", "Health after a collapse: %s%%", 10, 100, 5)
yesNo(fight, "assist", "Companions defend the player",
    "Companions attack whoever starts a fight with the player. Escorted NPCs never do.")
yesNo(fight, "escortSelfDefense", "Escorted NPCs only defend themselves",
    "An NPC escorted by the player fights only someone who attacks it, never in the player's defense.")
yesNo(fight, "escortProtection", "Escorted NPCs can't die",
    "A killing blow to an escorted NPC drains its fatigue to zero instead; it stays down while the fight lasts and gets up when it is over.")

-- built each time the page opens, so the list is current
local blacklist = template:createPage({ label = "Blacklist" })
blacklist:createCategory({
    label = "Never followers (water life, guards and the companion suite's list)",
    postCreate = function(self)
        local box = self.elements.subcomponentsContainer
        local ids = {}
        for id in pairs(config.blacklist) do ids[#ids + 1] = id end
        table.sort(ids)
        if #ids == 0 then box:createLabel({ text = "The blacklist is empty." }) end
        for _, id in ipairs(ids) do
            local row = box:createBlock()
            row.flowDirection = tes3.flowDirection.leftToRight
            row.widthProportional = 1.0
            row.autoHeight = true
            row:createButton({ text = "Remove" }):register("mouseClick", function()
                config.blacklist[id] = nil
                mwse.saveConfig("mwcompanions", config)
                row:destroy()
                box:getTopLevelMenu():updateLayout()
            end)
            local label = row:createLabel({ text = id })
            label.borderLeft = 8
            label.borderTop = 4
        end
    end,
})

template:register()
