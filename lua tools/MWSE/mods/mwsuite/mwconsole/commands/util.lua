--[[ mwconsole command helpers: target, output, small parsers. ]]
local util = {}

function util.print(ctx, fmt, ...)
    local ok, line = pcall(string.format, fmt, ...)
    line = ok and line or tostring(fmt)
    if ctx and ctx.print then ctx.print(line) else pcall(tes3ui.log, "%s", line) end
end

--- the console selection, or the player
function util.target(ctx)
    return (ctx and ctx.ref) or tes3ui.getConsoleReference() or tes3.player
end

function util.name(ref)
    local obj = ref and (ref.object or ref.baseObject)
    return (obj and obj.name and obj.name ~= "" and obj.name) or (ref and ref.id) or "?"
end

function util.isPlayer(ref) return ref == tes3.player end

function util.int(s, default)
    local n = tonumber(s)
    if not n then return default end
    return math.floor(n)
end

--- "long blade" / "longblade" / "Long Blade" -> skill id; attributes likewise
local function key(s) return (tostring(s or ""):lower():gsub("[%s_%-]", "")) end

function util.skillId(name)
    local k = key(name)
    for id, n in pairs(tes3.skillName) do if key(n) == k then return id end end
    for n, id in pairs(tes3.skill) do if key(n) == k then return id end end
    return nil
end

function util.attributeId(name)
    local k = key(name)
    for id, n in pairs(tes3.attributeName) do if key(n) == k then return id end end
    for n, id in pairs(tes3.attribute) do if key(n) == k then return id end end
    return nil
end

function util.needMobile(ctx, ref)
    if not ref or not ref.mobile then
        util.print(ctx, "%s isn't a character or creature", util.name(ref))
        return nil
    end
    return ref.mobile
end

return util
