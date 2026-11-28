local config = require("mwcriminal.config")
local inspectorUI = require("mwcriminal.inspectorUI")

local function save() mwse.saveConfig("mwcriminal", config) end

local template = mwse.mcm.createTemplate({ name = "mwcriminal", onClose = save })
local page = template:createSideBarPage({
    label = "Settings",
    description = "Sneaking, theft and door locks in one mod. Before turning a switch on, turn off the original mod "
        .. "it replaces (named in each description). Shift+activate on something adds it to the Blacklist, and "
        .. "mwcriminal leaves it alone after that.",
})

local function yesNo(parent, id, label, description)
    parent:createYesNoButton({ label = label, description = description,
        variable = mwse.mcm.createTableVariable({ id = id, table = config }) })
end

page:createYesNoButton({ label = "Enable crime and lock changes", description = "Master switch. While it is off, none of the options below (or the inspector key) do anything.",
    variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }) })

local theft = page:createCategory("Theft")
yesNo(theft, "sneakToSteal", "Must sneak to steal",
    "Things that belong to someone (items, containers) can only be taken or opened while sneaking, so a stray click is never a theft. Replaces Accidental Theft Protection.")
yesNo(theft, "factionOwnership", "Faction goods are owned for outsiders",
    "Some plugins (Tamriel Rebuilt most of all) give a faction's things no rank, and the game then lets anyone take them, or anything in a container like that, as if nobody owned them. With this on they belong to the faction: members of any rank take them freely, everyone else steals them (sneak first with 'Must sneak to steal'), in the inventory and in Quick Loot alike. Rank requirements a plugin does set work as in vanilla.")
yesNo(theft, "readStanding", "Read owned books standing (Take is red)",
    "Owned books and scrolls open for reading without sneaking; the Take button turns red because taking them is a crime. Replaces the mwpluginpatches book fix.")
yesNo(theft, "plainPaper", "Plain paper skips the scroll window",
    "Picking up a blank sheet of paper puts it straight in your inventory instead of opening it like a scroll. Replaces mwplainpaperfix.")
yesNo(theft, "plainPaperRequireSneak", "Require sneaking for owned plain paper",
    "Blank paper that belongs to someone can only be picked up while sneaking. ('Must sneak to steal' already does this when it is on.)")

local sneak = page:createCategory("Detection")
yesNo(sneak, "companionDetection", "Ignore detections from followers and listed actors",
    "Prevents followers and actors on the companion detection list from spotting you. Use the switches below to include escorts, creature followers or all creatures.")
yesNo(sneak, "includeCreatures", "Include creature followers",
    "Counts creature followers (pack guars, pets) as followers for the option above.")
yesNo(sneak, "includeEscorts", "Include escort quest targets",
    "Counts NPCs you are escorting on a quest as followers for the option above.")
yesNo(sneak, "blacklistAllCreatures", "Blacklist all creatures",
    "With detection protection on, all creatures count as blacklisted, including creatures that do not follow you.")
yesNo(sneak, "debugMode", "Log detection suppressions",
    "For troubleshooting: writes a line to MWSE\\logs\\mwcriminal.log each time a follower or blacklisted actor is stopped from noticing you.")
sneak:createKeyBinder({
    label = "Detection inspector hotkey",
    description = "Opens the detection inspector, which shows who can see you right now. Default: K. Works only while mwcriminal is on.",
    allowCombinations = true,
    variable = mwse.mcm.createTableVariable({ id = "inspectorKey", table = config }),
})
sneak:createButton({
    label = "Detection inspector",
    description = "Shows who is noticing you or getting suspicious right now, and how far away they are.",
    buttonText = "Open inspector",
    callback = function() inspectorUI.open() end,
})
sneak:createButton({
    label = "Companion blacklist",
    description = "Open the list of actors ignored by detection protection. This list is separate from the object Blacklist tab.",
    buttonText = "Manage blacklist",
    callback = function() inspectorUI.openBlacklist() end,
})
sneak:createButton({
    label = "Clear companion blacklist",
    description = "Immediately clears the companion detection list. The separate object blacklist is unaffected.",
    buttonText = "Clear blacklist",
    callback = function()
        config.companionBlacklist = {}
        save()
        tes3.messageBox("Companion detection blacklist cleared.")
    end,
})

local locks = page:createCategory("Locks and doors")
yesNo(locks, "interiorExit", "Never locked inside",
    "A door leading from inside a building to the outside is unlocked when you use it, so you can never be locked in.")
yesNo(locks, "sneakToPick", "Must sneak to pick locks",
    "A locked door or container you have no key for only rattles unless you sneak; sneaking starts lockpicking (Modern Lockpicking). "
        .. "If you have the key (also on a supported keyring), it opens normally without sneaking, even if it is owned.")
yesNo(locks, "noLoadDoorOnPick", "Picking a loading door only unlocks it",
    "Modern Lockpicking opens a door the moment you pick it. With this on, a door that leads somewhere else is "
        .. "only unlocked, so you choose when to go through. Other doors and containers open as before.")
yesNo(locks, "lockedNotification", "Show a notice for locked things",
    "Shows a 'Locked' message when something you try is locked. The locked door or chest sound always plays, "
        .. "whether this is on or off; the notice is there if you play without sound.")
yesNo(locks, "lockedCrosshair", "Tint the crosshair on locked things",
    "With Essential Indicators installed, the crosshair turns orange over a locked door or container you have no key for.")
yesNo(locks, "eveningLocks", "Owned homes lock in the evening",
    "Homes lock outside opening hours (set below) and whenever their owner is away. Public places never lock, guild halls stay open to members, a dead owner's home is unlocked, and empty unowned rooms stay open. Replaces abot Door Locks.")
yesNo(locks, "knocking", "Knock on locked doors",
    "Using a locked door without sneaking knocks on it and waits a few seconds. If someone inside is willing, they open up and meet you at the door; if not, a brief message says there is no response. Replaces abot Door Locks knocking.")
for _, s in ipairs({
    { "openHour", "Doors open at", 5, 10, "The hour homes unlock in the morning (with 'Owned homes lock in the evening')." },
    { "closeHour", "Doors lock at", 16, 23, "The hour homes lock for the night (with 'Owned homes lock in the evening')." },
    { "knockUntilHour", "Nobody answers knocks after", 18, 24, "After this hour, until doors open in the morning, only members of a faction you have joined answer your knock." },
}) do
    locks:createSlider({ label = s[2] .. " %s:00", description = s[5], min = s[3], max = s[4], step = 1, jump = 1,
        variable = mwse.mcm.createTableVariable({ id = s[1], table = config }) })
end

-- built each time the page opens, so entries added in game show up
local blacklist = template:createPage({ label = "Blacklist" })
blacklist:createInfo({ text = "Click Remove to take an entry off the list, so mwcriminal handles it again." })
blacklist:createCategory({
    label = "Objects mwcriminal ignores (Shift+activate adds one)",
    postCreate = function(self)
        local box = self.elements.subcomponentsContainer
        local keys = {}
        for key in pairs(config.blacklist) do keys[#keys + 1] = key end
        table.sort(keys, function(a, b) return tostring(config.blacklist[a]) < tostring(config.blacklist[b]) end)
        if #keys == 0 then box:createLabel({ text = "The blacklist is empty." }) end
        for _, key in ipairs(keys) do
            local row = box:createBlock()
            row.flowDirection = tes3.flowDirection.leftToRight
            row.widthProportional = 1.0
            row.autoHeight = true
            row:createButton({ text = "Remove" }):register("mouseClick", function()
                config.blacklist[key] = nil
                save()
                row:destroy()
                box:getTopLevelMenu():updateLayout()
            end)
            local label = row:createLabel({ text = tostring(config.blacklist[key]) })
            label.borderLeft = 8
            label.borderTop = 4
        end
    end,
})

-- Credits: the mods whose ideas mwcriminal borrows (listed with their authors and pages)
local CREDITS = {
    { mod = "Accidental Theft Protection", author = "Merlord",
      idea = "Owned items and containers can only be taken or opened while sneaking, with a list of things that may be taken standing.",
      url = "https://www.nexusmods.com/morrowind/mods/48264" },
    { mod = "Door Locks (abotDoorLocks)", author = "abot",
      idea = "Homes lock by time of day, place, faction and owner while public places stay open; knocking on a locked door and someone answering it; opening doors with keys kept on a keyring.",
      url = "https://www.nexusmods.com/morrowind/mods/54754" },
    { mod = "mwcompanionsneak", author = "dej (dejunai)",
      idea = "Companion and creature sneak detection: followers, escorts and blacklisted actors never notice you sneaking (inspector, blacklist and settings), now part of mwcriminal." },
}
local credits = template:createPage({ label = "Credits" })
credits:createInfo({ text = "mwcriminal is by dejunai. It borrows ideas from the mods below. Each link opens the original mod's page; please support their authors." })
for _, c in ipairs(CREDITS) do
    local cat = credits:createCategory(c.mod .. " - by " .. c.author)
    cat:createInfo({ text = c.idea })
    if c.url then cat:createHyperlink({ text = c.url, url = c.url }) end
end

template:register()
