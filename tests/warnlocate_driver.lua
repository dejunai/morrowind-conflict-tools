-- Run by test_warnlocate.py: luajit warnlocate_driver.lua <mods folder> <Morrowind.exe> [break]
-- Prints what mwwarnsuppression.locate finds in the file, one "name address length bytes" line each.
package.path = arg[1] .. "\\?.lua;" .. package.path
local locate = require("mwwarnsuppression.locate")
local f = assert(io.open(arg[2], "rb"))
local file = f:read("*a")
f:close()
local function header(rva, length) return file:sub(rva + 1, rva + length) end
local image = { data = {} }
for _, sec in ipairs(locate.sections(header)) do
    local bytes = file:sub(sec.raw + 1, sec.raw + math.min(sec.size, sec.rawSize))
    if sec.name == ".text" then
        if arg[3] == "break" then                -- as if another patcher had already changed the code
            bytes = bytes:gsub("\15\132", "\15\133")
        end
        image.text, image.textAddress = bytes, 0x400000 + sec.rva
    elseif sec.name == ".rdata" or sec.name == ".data" then
        image.data[#image.data + 1] = { bytes = bytes, address = 0x400000 + sec.rva }
    end
end
local found = locate.find(image)
for _, name in ipairs({ "bodyPart", "texture", "nif", "kf" }) do
    local s = found[name]
    if s then
        local hex = {}
        for _, b in ipairs(s.bytes or {}) do hex[#hex + 1] = string.format("%02X", b) end
        print(string.format("%s 0x%X %d %s", name, s.address, s.length, table.concat(hex, " ")))
    else
        print(name .. " none")
    end
end
