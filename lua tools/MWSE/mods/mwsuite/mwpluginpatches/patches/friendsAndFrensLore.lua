--[[
Friends & Frens gives some vanilla NPCs (Fargoth, for one) a partner script, and every partner script declares
`short nolore`. Generic responses ask "Not Local nolore = 0", so those NPCs lose them all. Here nolore becomes 1,
which passes that test, only where the partner script replaced a vanilla script (or none) that had no nolore.
Friends & Frens' own companions, and NPCs that were meant to have no lore, are left alone.

What an NPC's script was is read from the three vanilla masters: no list of NPCs. The value lives in the save.
]]

local this = {}

local MASTERS = { "Morrowind.esm", "Tribunal.esm", "Bloodmoon.esm" }
local vanillaScript                         -- NPC id -> its script's id in the vanilla masters ("" for none)

local function u32(bytes, at)
    local a, b, c, d = bytes:byte(at, at + 3)
    return a + b * 256 + c * 65536 + d * 16777216
end

local function readMaster(name, into)
    local file = io.open("Data Files\\" .. name, "rb")
    if not file then return end
    while true do
        local header = file:read(16)
        if not header or #header < 16 then break end
        local size = u32(header, 5)
        if header:sub(1, 4) ~= "NPC_" then
            if not file:seek("cur", size) then break end
        else
            local body = file:read(size)
            if not body or #body < size then break end
            local at, id, script = 1, nil, ""
            while at + 7 <= size do
                local length = u32(body, at + 4)
                local field = body:sub(at, at + 3)
                if field == "NAME" or field == "SCRI" then
                    local value = body:sub(at + 8, at + 7 + length):gsub("%z.*", ""):lower()
                    if field == "NAME" then id = value else script = value end
                end
                at = at + 8 + length
            end
            if id then into[id] = script end
        end
    end
    file:close()
end

local function lostLore(npcId)
    if not vanillaScript then
        vanillaScript = {}
        for _, name in ipairs(MASTERS) do readMaster(name, vanillaScript) end
    end
    local was = vanillaScript[npcId]
    if was == nil then return false end     -- not a vanilla NPC
    if was == "" then return true end
    local script = tes3.getScript(was)
    if not script then return false end
    for name in pairs(script:getVariableData() or {}) do
        if name:lower() == "nolore" then return false end
    end
    return true
end

local function restore(ref)
    local base = ref and ref.baseObject
    if not base or base.objectType ~= tes3.objectType.npc then return end
    local script = base.script
    if not script or not script.id:lower():find("^aa_partner") then return end
    local context = ref.context             -- nil until the reference has its own variables
    if not context or context.nolore ~= 0 or not lostLore(base.id:lower()) then return end
    context.nolore = 1                      -- not getVariableData().nolore.value: that table is a copy
    ref.modified = true
end

function this.init()
    event.register(tes3.event.mobileActivated, function(e) restore(e.reference) end)
    event.register(tes3.event.activate, function(e) restore(e.target) end)
    mwse.log("[mwpluginpatches] Friends & Frens: converted vanilla NPCs keep their generic dialogue.")
end

return this
