--[[
    mwconsole parser: turns a console line into a command word and arguments.
    * surrounding whitespace and backticks are dropped
    * "word(a, b)" is read as "word a b" (people type lua-style calls in the lua console)
    * double or single quotes keep words together; the quotes are removed
    * tokens keep their start/end positions so completion can replace the word under the cursor
]]
local parser = {}

local function trim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end

function parser.clean(text)
    if type(text) ~= "string" then return "" end
    local s = trim(text)
    s = s:gsub("^`+", ""):gsub("`+$", "")
    s = trim(s)
    local word, inner = s:match("^([%w_/]+)%s*%((.*)%)%s*;?$")
    if word then
        s = word .. " " .. inner:gsub(",", " ")
        s = trim(s)
    end
    return s
end

--- tokens: { { text = "...", quoted = bool, s = start, e = end, open = unterminated quote } ... }
function parser.tokenize(s)
    local tokens = {}
    local i, n = 1, #s
    while i <= n do
        local c = s:sub(i, i)
        if c:match("%s") then
            i = i + 1
        elseif c == '"' or c == "'" then
            local j = s:find(c, i + 1, true)
            if j then
                tokens[#tokens + 1] = { text = s:sub(i + 1, j - 1), quoted = true, s = i, e = j }
                i = j + 1
            else
                tokens[#tokens + 1] = { text = s:sub(i + 1), quoted = true, open = true, s = i, e = n }
                i = n + 1
            end
        else
            local j = i
            while j <= n and not s:sub(j, j):match("[%s\"']") do j = j + 1 end
            tokens[#tokens + 1] = { text = s:sub(i, j - 1), quoted = false, s = i, e = j - 1 }
            i = j
        end
    end
    return tokens
end

--- returns name (lowercase), args (list of strings, case kept), rest (raw text after the command word)
function parser.split(text)
    local s = parser.clean(text)
    if s == "" then return nil, {}, "" end
    local toks = parser.tokenize(s)
    if #toks == 0 then return nil, {}, "" end
    local first = toks[1]
    local name = first.text:lower()
    local args = {}
    for k = 2, #toks do args[#args + 1] = toks[k].text end
    local rest = trim(s:sub(first.e + 1))
    return name, args, rest
end

return parser
