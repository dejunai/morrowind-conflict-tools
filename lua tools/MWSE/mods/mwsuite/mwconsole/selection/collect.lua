--[[
    mwconsole selection data (no UI): rows describing one reference.
    row = { section, label, value, action = nil | "copy" | "copyjson" }
    Sections, in order: Object, Files, Owner, Spawned from, Script, Lock, Lua data, Actor, Placement.
    Other mods may append rows through the event "mwconsole:selectionRows" { reference, rows }.
]]
local effects = require("mwconsole.effects.collect")

local collect = {}

local function safe(fn, ...)
    local ok, v = pcall(fn, ...)
    if ok then return v end
    return nil
end

local typeNames
local function typeName(t)
    if not typeNames then
        typeNames = {}
        for name, v in pairs(tes3.objectType) do typeNames[v] = name end
    end
    return typeNames[t] or tostring(t)
end
collect.typeName = typeName

--- where a data file comes from: "loose" or the archive name (or "missing")
function collect.fileSource(path)
    if not path or path == "" then return "none" end
    local ok, src = pcall(tes3.getFileSource, path)
    if not ok or not src then return "missing" end
    if src == "file" then return "loose" end
    if src == "bsa" then
        local archive = safe(function()
            local archive = tes3.bsaLoader:findFile(path)
            return archive and archive.path
        end)
        if type(archive) == "string" then return (archive:match("[^\\/]+$") or archive) end
        return "BSA"
    end
    return tostring(src)
end

--- every texture file in a scene graph, case-insensitively deduplicated, sorted
function collect.textures(root)
    local seen, list = {}, {}
    if not root then return list end
    local visited = 0
    local function walk(node)
        if not node or visited > 5000 then return end
        visited = visited + 1
        local prop = safe(function() return node.texturingProperty end)
        if prop then
            safe(function()
                for _, map in ipairs(prop.maps) do
                    local tex = map and map.texture
                    local file = tex and tex.fileName
                    if type(file) == "string" and file ~= "" then
                        local low = file:lower()
                        if not seen[low] then seen[low] = true list[#list + 1] = file end
                    end
                end
            end)
        end
        local children = safe(function() return node.children end)
        if children then for _, c in ipairs(children) do walk(c) end end
    end
    walk(root)
    table.sort(list, function(a, b) return a:lower() < b:lower() end)
    return list
end

local function fmtNum(v)
    if type(v) ~= "number" then return tostring(v) end
    if v == math.floor(v) then return string.format("%d", v) end
    return string.format("%.2f", v)
end

--- the script's local variables, read only when the reference really has script variables attached
function collect.scriptVars(ref, script)
    local vars = {}
    local live = safe(function()
        local att = ref.attachments
        return att and att.variables ~= nil
    end)
    if not live then return vars end
    local data = safe(function() return script:getVariableData() end)    -- names and types
    if type(data) ~= "table" then return vars end
    for name, v in pairs(data) do
        local t = ({ s = "short", l = "long", f = "float" })[v.type] or tostring(v.type)
        local value = safe(function() return ref.context[name] end)          -- this reference's value
        vars[#vars + 1] = { name = name, type = t, value = value }
    end
    table.sort(vars, function(a, b) return a.name:lower() < b.name:lower() end)
    return vars
end

local function luaTable(t)
    return type(t) == "table" and next(t) ~= nil
end

--- JSON of a table; values JSON can't hold become strings
function collect.toJson(t)
    local function clean(v, depth)
        if depth > 20 then return "<too deep>" end
        local ty = type(v)
        if ty == "table" then
            local o = {}
            for k, x in pairs(v) do o[type(k) == "number" and k or tostring(k)] = clean(x, depth + 1) end
            return o
        elseif ty == "number" or ty == "string" or ty == "boolean" then
            return v
        end
        return tostring(v)
    end
    return json.encode(clean(t, 0), { indent = true })
end

function collect.rows(ref, opts)
    opts = opts or {}
    local rows = {}
    local function add(section, label, value, action)
        rows[#rows + 1] = { section = section, label = label, value = value ~= nil and tostring(value) or "", action = action }
    end
    if not ref then return rows end
    local obj = ref.object
    local base = ref.baseObject or obj

    -- Object
    add("Object", "Reference", string.format("%s (%s)", ref.id, ref.sourceMod or "created in game"), "copy")
    if base then
        add("Object", "Base", string.format("%s (%s)", base.id, base.sourceMod or "?"), "copy")
        add("Object", "Type", typeName(base.objectType))
        if base.name and base.name ~= "" then add("Object", "Name", base.name) end
    end
    local cell = ref.cell
    if cell then add("Object", "Cell", cell.editorName or cell.id) end

    -- Files
    local mesh = safe(function() return obj.mesh end)
    if mesh and mesh ~= "" then
        local path = "Meshes\\" .. mesh
        add("Files", "Mesh", string.format("%s [%s]", path, collect.fileSource(path)), "copy")
    end
    for _, tex in ipairs(collect.textures(ref.sceneNode)) do
        local path = tex:lower():find("^textures[\\/]") and tex or ("Textures\\" .. tex)
        add("Files", "Texture", string.format("%s [%s]", path, collect.fileSource(path)), "copy")
    end
    local icon = safe(function() return obj.icon end)
    if icon and icon ~= "" then
        local path = "Icons\\" .. icon
        add("Files", "Icon", string.format("%s [%s]", path, collect.fileSource(path)), "copy")
    end

    -- Owner
    local okOwner, owner, req = pcall(tes3.getOwner, { reference = ref })
    if not okOwner then owner = nil end
    if owner then
        add("Owner", "Owner", string.format("%s (%s)", owner.id, owner.sourceMod or "?"))
        if owner.objectType == tes3.objectType.faction then
            local rank = tonumber(req) or 0
            local rankName = safe(function() return owner:getRankName(rank) end)
                or safe(function() return owner.ranks[rank + 1].name end)
            add("Owner", "Rank needed", rankName and string.format("%s (%d)", rankName, rank) or tostring(rank))
        elseif req then
            local gid = type(req) ~= "number" and type(req) ~= "string" and safe(function() return req.id end) or tostring(req)
            add("Owner", "Global needed", gid)
        end
    end

    -- Spawned from
    local lev = safe(function() return ref.leveledBaseReference end)
    if lev then
        local lcell = safe(function() return lev.cell and (lev.cell.editorName or lev.cell.id) end) or "?"
        local p = lev.position
        add("Spawned from", "List reference", string.format("%s in %s at %s, %s, %s", lev.id, lcell,
            fmtNum(p and math.floor(p.x) or 0), fmtNum(p and math.floor(p.y) or 0), fmtNum(p and math.floor(p.z) or 0)))
    end

    -- Script
    local script = safe(function() return base.script end)
    if script then
        add("Script", "Script", string.format("%s (%s)", script.id, script.sourceMod or "?"), "copy")
        for _, v in ipairs(collect.scriptVars(ref, script)) do
            add("Script", string.format("%s (%s)", v.name, v.type), fmtNum(v.value))
        end
    end

    -- Lock
    local lockNode = safe(function() return ref.lockNode end)
    if lockNode then
        add("Lock", "Locked", lockNode.locked and string.format("yes, level %d", lockNode.level or 0) or "no")
        if lockNode.trap then add("Lock", "Trap", lockNode.trap.id) end
        if lockNode.key then add("Lock", "Key", lockNode.key.id, "copy") end
    end

    -- Lua data
    local data = safe(function() return ref.data end)
    local temp = safe(function() return ref.tempData end)
    if luaTable(data) then add("Lua data", "Saved data", "copy as JSON", "copyjson:data") end
    if luaTable(temp) then add("Lua data", "Temporary data", "copy as JSON", "copyjson:tempData") end

    -- Actor (extra)
    local mobile = ref.mobile
    if mobile and safe(function() return mobile.health end) then
        add("Actor", "Health", string.format("%d/%d", mobile.health.current or 0, mobile.health.base or 0))
        add("Actor", "Magicka", string.format("%d/%d", mobile.magicka.current or 0, mobile.magicka.base or 0))
        add("Actor", "Fatigue", string.format("%d/%d", mobile.fatigue.current or 0, mobile.fatigue.base or 0))
        add("Actor", "Active effects", #effects.active(ref))
        if effects.isDead(ref) then add("Actor", "State", "dead") end
    end

    -- Placement (extra)
    local pos, rot = ref.position, ref.orientation
    if pos then add("Placement", "Position", string.format("%.1f, %.1f, %.1f", pos.x, pos.y, pos.z), "copy") end
    if rot then
        add("Placement", "Rotation", string.format("%.1f, %.1f, %.1f", math.deg(rot.x), math.deg(rot.y), math.deg(rot.z)))
    end
    if ref.scale then add("Placement", "Scale", fmtNum(ref.scale)) end
    if ref.disabled then add("Placement", "Disabled", "yes") end
    if ref.deleted then add("Placement", "Deleted", "yes") end

    if not opts.noEvent then
        pcall(event.trigger, "mwconsole:selectionRows", { reference = ref, rows = rows })
    end
    return rows
end

--- every row as plain text lines
function collect.asText(rows)
    local lines, last = {}, nil
    for _, r in ipairs(rows) do
        if r.section ~= last then
            lines[#lines + 1] = "[" .. tostring(r.section) .. "]"
            last = r.section
        end
        lines[#lines + 1] = string.format("  %s: %s", tostring(r.label), tostring(r.value))
    end
    return lines
end

return collect
