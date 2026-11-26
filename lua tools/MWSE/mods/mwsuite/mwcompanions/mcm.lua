local config = require("mwcompanions.config")

local function save()
    mwse.saveConfig("mwcompanions", config)
    event.trigger("mwcompanions:changed")
end

local template = mwse.mcm.createTemplate({ name = "mwcompanions", onClose = save })
local page = template:createSideBarPage({
    label = "Settings",
    description = "Followers, warping and follower combat in one mod. Before turning a switch on here, turn off the "
        .. "matching option in Smart Companions (or Attend Me's teleport); if both are on, a warning is logged.",
})

local function yesNo(parent, id, label, description)
    parent:createYesNoButton({ label = label, description = description,
        variable = mwse.mcm.createTableVariable({ id = id, table = config }) })
end

local function slider(parent, id, label, description, min, max, step)
    parent:createSlider({ label = label, description = description, min = min, max = max, step = step, jump = step * 10,
        variable = mwse.mcm.createTableVariable({ id = id, table = config }) })
end

page:createYesNoButton({ label = "Enable mwcompanions", description = "Master switch. While it is off, none of the options below do anything.",
    variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }) })

local move = page:createCategory("Following")
yesNo(move, "warp", "Warp followers to the player",
    "Followers who fall farther behind than the distance below, or get left in another nearby area, appear right behind you. Followers in a fight stay in it. Replaces Smart Companions' warp; if Attend Me's auto-teleport is on, Attend Me does the warping instead.")
slider(move, "warpDistance", "Warp distance: %s",
    "How far a follower can fall behind before being warped to you (1000 is about 14 metres). Lower it to keep followers closer; raise it if they warp too often.", 500, 8000, 100)
yesNo(move, "levitateWater", "Followers levitate and water walk with the player",
    "While you levitate or walk on water, your followers do too, so they don't get left behind or sink. It ends when yours does.")
yesNo(move, "followerTraits", "Follower traits",
    "Followers never report your crimes, and NPC followers can breathe underwater and get Acrobatics 150 and Athletics 220 so they keep up with you.")
yesNo(move, "muteOnCellChange", "Quiet followers after a cell change",
    "Followers skip their attack and greeting lines for 3 seconds after you go through a door, so they don't all talk at once.")
yesNo(move, "noSneakActivate", "Don't activate followers while sneaking",
    "Pressing activate on a follower while sneaking does nothing, so you don't pickpocket a companion by accident.")

local fight = page:createCategory("Combat")
yesNo(fight, "noFriendlyFire", "No friendly fire",
    "You and your followers can't hurt each other with weapons or harmful spells, and a stray hit won't turn them against you. You can still soul-trap a follower who isn't a companion.")
yesNo(fight, "resilient", "Followers collapse instead of dying",
    "A killing blow knocks a follower out instead of killing them; they get up after the time set below and follow you again.")
slider(fight, "collapseSeconds", "Collapse time: %s s",
    "How long a knocked-out follower stays down before getting up. Used by 'Followers collapse instead of dying'.", 10, 300, 5)
slider(fight, "collapseHealth", "Health after a collapse: %s%%",
    "How much health a knocked-out follower is left with, as a share of their full health.", 10, 100, 5)
yesNo(fight, "sheatheAfterCombat", "Companions put their weapon away after a fight",
    "Sometimes a companion keeps their weapon out after a fight. With this on, about a second after the fighting stops "
        .. "(and once your own weapon and spell are put away), they put theirs away too.")
yesNo(fight, "assist", "Companions defend the player",
    "Companions attack anyone who starts a fight with you. NPCs you are escorting never join in.")
yesNo(fight, "escortSelfDefense", "Escorted NPCs only defend themselves",
    "An NPC you are escorting only fights someone who attacks them, and never jumps into your fights.")
yesNo(fight, "escortProtection", "Escorted NPCs can't die",
    "An NPC you are escorting can't be killed: a killing blow knocks them down instead, and they get up once the fight is over.")

local function getFollowers()
    local list = {}
    local seen = {}
    local player = tes3.mobilePlayer
    if player and player.friendlyActors then
        for actor in tes3.iterate(player.friendlyActors) do
            if actor ~= player and actor.reference then
                local ref = actor.reference
                local base = ref.baseObject or ref.object
                local id = base and base.id or ref.id
                if id and not seen[id] then
                    seen[id] = true
                    table.insert(list, id)
                end
            end
        end
    end
    table.sort(list)
    return list
end

template:createExclusionsPage({
    label = "Blacklist",
    description = "Actors on the left are never treated as followers by this mod: no warping, no combat protection, no other changes. Click a name to move it to the other list.",
    leftListLabel = "Never Followers (Blacklisted)",
    rightListLabel = "Available Actors",
    showAllBlocked = true,
    variable = mwse.mcm.createTableVariable({ id = "blacklist", table = config }),
    filters = {
        { label = "Followers", callback = getFollowers },
        { label = "NPCs", type = "Object", objectType = tes3.objectType.npc },
        { label = "Creatures", type = "Object", objectType = tes3.objectType.creature },
    },
})

-- Credits: the mods whose ideas mwcompanions borrows (listed with their authors and pages)
local CREDITS = {
    { mod = "Smart Companions", author = "abot",
      idea = "Who counts as a follower; warping followers to you and moving them with you through doors; levitating and water walking with you; follower traits; no friendly fire; followers who collapse instead of dying; companions who join your fights; quiet followers after a cell change; not activating a follower while sneaking.",
      url = "https://www.nexusmods.com/morrowind/mods/49848" },
    { mod = "Easy Escort", author = "NullCascade",
      idea = "Warping followers who fall far behind or get left in another cell, and the list of actors that are never followers (its ignore list was imported).",
      url = "https://www.nexusmods.com/morrowind/mods/45712" },
    { mod = "Attend Me Expanded MWSE", author = "drekar51 (MWSE port of Attend Me by urm)",
      idea = "Spreading warped followers in an arc behind you, and reading the companion variable safely so it cannot crash the game.",
      url = "https://www.nexusmods.com/morrowind/mods/60810" },
}
local credits = template:createPage({ label = "Credits" })
credits:createInfo({ text = "mwcompanions is by dejunai. It borrows ideas from the mods below. Each link opens the original mod's page; please support their authors." })
for _, c in ipairs(CREDITS) do
    local cat = credits:createCategory(c.mod .. " - by " .. c.author)
    cat:createInfo({ text = c.idea })
    if c.url then cat:createHyperlink({ text = c.url, url = c.url }) end
end

template:register()
