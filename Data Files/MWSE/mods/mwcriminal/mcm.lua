local config = require("mwcriminal.config")

local function save() mwse.saveConfig("mwcriminal", config) end

local template = mwse.mcm.createTemplate({ name = "mwcriminal", onClose = save })
local page = template:createSideBarPage({
    label = "Settings",
    description = "Sneaking, theft and door locks in one mod. Turn a switch on only after turning the original mod "
        .. "it replaces off in that mod's settings. Shift+activate adds the target to the blacklist (mwcriminal then "
        .. "ignores it).",
})

local function yesNo(parent, id, label, description)
    parent:createYesNoButton({ label = label, description = description,
        variable = mwse.mcm.createTableVariable({ id = id, table = config }) })
end

page:createYesNoButton({ label = "Enable mwcriminal", description = "Master switch. Nothing below does anything while this is off.",
    variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }) })

local theft = page:createCategory("Theft")
yesNo(theft, "sneakToSteal", "Must sneak to steal",
    "Owned items, containers and other owned things can only be activated while sneaking. Replaces Accidental Theft Protection.")
yesNo(theft, "readStanding", "Read owned books standing (Take is red)",
    "Owned books and scrolls open standing; the Take button is tinted red because taking it is theft. Replaces the mwpluginpatches book fix.")
yesNo(theft, "plainPaper", "Plain paper skips the scroll window",
    "Blank sheets go straight into the inventory; owned ones only while sneaking. Replaces mwplainpaperfix.")

local sneak = page:createCategory("Detection")
yesNo(sneak, "companionDetection", "Companions and creatures don't detect you",
    "Followers, escorts, creatures and blacklisted actors never detect the sneaking player. Guards and anyone fighting you still do. Replaces mwcompanionsneak.")

local locks = page:createCategory("Locks and doors")
yesNo(locks, "interiorExit", "Never locked inside",
    "A door from an interior out to an exterior is unlocked when used. Replaces part of mwpluginpatches door lock compatibility.")
yesNo(locks, "sneakToPick", "Must sneak to pick locks",
    "A locked door or container without its key plays the locked sound unless you sneak; sneaking opens the lockpicking (Modern Lockpicking).")
yesNo(locks, "lockedNotification", "Show a notice for locked things", "For players who play without sound.")
yesNo(locks, "lockedCrosshair", "Tint the crosshair on locked things",
    "With Essential Indicators installed, the crosshair turns orange on a locked door or container you have no key for.")
yesNo(locks, "eveningLocks", "Owned homes lock in the evening",
    "Homes lock outside opening hours and whenever their living owner is away; public places never lock, faction houses open to members, a dead owner's home is unlocked, empty unowned interiors stay open. Replaces abot Door Locks.")
yesNo(locks, "knocking", "Knock on locked doors",
    "Using a locked door standing knocks; someone inside who is willing opens and meets you at the door. Replaces abot Door Locks knocking.")
for _, s in ipairs({
    { "openHour", "Doors open at", 5, 10 },
    { "closeHour", "Doors lock at", 16, 23 },
    { "knockUntilHour", "Nobody answers knocks after", 18, 24 },
}) do
    locks:createSlider({ label = s[2] .. " %s:00", min = s[3], max = s[4], step = 1, jump = 1,
        variable = mwse.mcm.createTableVariable({ id = s[1], table = config }) })
end

-- built each time the page opens, so entries added in game show up
local blacklist = template:createPage({ label = "Blacklist" })
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

template:register()
