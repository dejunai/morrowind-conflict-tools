--[[
    mwwarnsuppression.locate - finds the code this mod patches by what it does, not by a fixed address.

    Morrowind.exe differs between vendors and after the Code Patch, so nothing here assumes an address. Each
    block prints one warning text, and the executable refers to that text exactly once (a `push <address of
    the text>`). From that push, the instructions around it are checked byte for byte before anything is
    reported. A build where a text or block is missing, appears twice, or looks different (another patcher
    has been there) gives no entry for it, and main.lua leaves that code alone.

    Pure Lua on strings, so tests/test_warnlocate.py runs it outside the game against the file.
]]
local this = {}

local function le32(n)
    return string.char(n % 256, math.floor(n / 256) % 256, math.floor(n / 65536) % 256, math.floor(n / 16777216) % 256)
end

local function u16(s, i) local a, b = s:byte(i, i + 1) return a + b * 256 end
local function u32(s, i) local a, b, c, d = s:byte(i, i + 3) return a + b * 256 + c * 65536 + d * 16777216 end

--- The sections of a PE image. read(rva, length) returns that many bytes at that offset from the image base.
--- @return table[] { name, rva, size, raw, rawSize } in file order (raw: where it is in the file)
function this.sections(read)
    if read(0, 2) ~= "MZ" then return {} end
    local pe = u32(read(0x3C, 4), 1)
    if read(pe, 4) ~= "PE\0\0" then return {} end
    local count = u16(read(pe + 6, 2), 1)
    local first = pe + 24 + u16(read(pe + 20, 2), 1)
    local out = {}
    for i = 0, count - 1 do
        local h = read(first + 40 * i, 40)
        out[#out + 1] = { name = (h:sub(1, 8):gsub("%z+$", "")), size = u32(h, 9), rva = u32(h, 13),
                          rawSize = u32(h, 17), raw = u32(h, 21) }
    end
    return out
end

-- the one place `needle` occurs in `text` (1-based), or nil when it is missing or occurs twice
local function once(text, needle)
    local i = text:find(needle, 1, true)
    if not i or text:find(needle, i + 1, true) then return nil end
    return i
end

local function bytesAt(text, i, ...)
    local want = { ... }
    for k = 1, #want do
        if text:byte(i + k - 1) ~= want[k] then return false end
    end
    return true
end

--- image = { text = <the code section's bytes>, textAddress = <its address>,
---           data = { { bytes = ..., address = ... }, ... } }   (the sections the warning texts live in)
--- @return table name -> { address, length, bytes = { ... } or nil (nil: fill with no-ops) }
function this.find(image)
    local text, base = image.text, image.textAddress

    local function pushOf(str)                    -- index in text of the one `push <address of str>`
        local address
        for _, sec in ipairs(image.data) do
            local i = sec.bytes:find(str, 1, true)
            if i then
                if address or sec.bytes:find(str, i + 1, true) then return nil end
                address = sec.address + i - 1
            end
        end
        return address and once(text, "\104" .. le32(address))
    end

    local out = {}

    -- "Not able to find %s part in %s.": the whole call that prints it, 33 bytes -
    -- mov ecx,ebp / call / push eax / movsx eax,[ebp+38h] / mov ecx,[eax*4+..] / push ecx / push text / call / add esp,0Ch
    local p = pushOf("Not able to find %s part in %s.")
    if p and p > 20 then
        local s = p - 20
        if bytesAt(text, s, 0x8B, 0xCD, 0xE8) and bytesAt(text, s + 7, 0x50, 0x0F, 0xBE, 0x45, 0x38, 0x8B, 0x0C, 0x85)
            and bytesAt(text, s + 19, 0x51, 0x68) and bytesAt(text, s + 25, 0xE8) and bytesAt(text, s + 30, 0x83, 0xC4, 0x0C) then
            out.bodyPart = { address = base + s - 1, length = 33 }
        end
    end

    -- "ModelList still has %d NIF/KF files.": `jz rel32` / push eax / push text. The jz skips the dump when the
    -- list is empty; made unconditional (jmp rel32 is one byte shorter, so rel + 1, then a no-op).
    for name, str in pairs({ nif = "ModelList still has %d NIF", kf = "ModelList still has %d KF" }) do
        p = pushOf(str)
        if p and p > 7 then
            local j = p - 7
            if bytesAt(text, j, 0x0F, 0x84) and bytesAt(text, j + 6, 0x50) then
                local rel = u32(text, j + 2)
                if rel < 0x1000 then                 -- a short forward skip, as in every known build
                    local b = { 0xE9, (rel + 1) % 256, math.floor((rel + 1) / 256) % 256, 0, 0, 0x90 }
                    out[name] = { address = base + j - 1, length = 6, bytes = b }
                end
            end
        end
    end

    -- 'Texture "%s" count %d': mov byte [flag],1 / jz short <past the loop that prints it>. The nearest such jz
    -- before the push, whose jump lands beyond the push, is made unconditional (same length, same target).
    p = pushOf('Texture "%s" count %d')
    if p then
        for j = p - 2, math.max(8, p - 0x60), -1 do
            if bytesAt(text, j, 0x74) and bytesAt(text, j - 7, 0xC6, 0x05) and bytesAt(text, j - 1, 0x01)
                and j + 2 + text:byte(j + 1) > p and text:byte(j + 1) < 0x80 then
                out.texture = { address = base + j - 1, length = 2, bytes = { 0xEB, text:byte(j + 1) } }
                break
            end
        end
    end
    return out
end

return this
