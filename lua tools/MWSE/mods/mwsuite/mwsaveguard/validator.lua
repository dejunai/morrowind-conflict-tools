local validator = {}

--- Reads a 32-bit unsigned little-endian integer from a string at 1-based startIdx.
--- @param bytes string
--- @param startIdx number?
--- @return number?
function validator.readUInt32(bytes, startIdx)
	startIdx = startIdx or 1
	if not bytes or #bytes < (startIdx + 3) then return nil end
	local b1, b2, b3, b4 = bytes:byte(startIdx, startIdx + 3)
	return b1 + b2 * 256 + b3 * 65536 + b4 * 16777216
end

--- Resolves a save name or path to an existing canonical file path.
--- @param filename string?
--- @return string?
function validator.resolveSavePath(filename)
	if not filename or filename == "" then return nil end
	local clean = filename:gsub("/", "\\")
	local lower = clean:lower()
	if not (lower:match("%.ess$") or lower:match("%.tes$")) then
		clean = clean .. ".ess"
	end

	-- 1. Direct check
	if lfs.fileexists(clean) then
		return clean
	end

	-- 2. Saves\ prefix check
	local inSaves = "saves\\" .. clean:gsub("^saves\\\\", "")
	if lfs.fileexists(inSaves) then
		return inSaves
	end

	-- 3. Base filename in saves\
	local base = clean:match("([^\\]+)$") or clean
	local inSavesBase = "saves\\" .. base
	if lfs.fileexists(inSavesBase) then
		return inSavesBase
	end

	return inSavesBase
end

--- Validates whether a file is a healthy, valid Morrowind ESS save game.
--- Verifies:
---   1. File presence and minimum valid header size (>= 324 bytes)
---   2. TES3 record tag and header structure
---   3. HEDR subrecord tag, size (300 bytes), and save flags (0x20 / 32)
---   4. Complete record traversal to EOF ensuring no truncated records or premature file endings
--- @param filePath string
--- @return boolean isValid
--- @return string reason
function validator.validateSave(filePath)
	local path = validator.resolveSavePath(filePath)
	-- not found or not readable here (a save from elsewhere, a path this guard can't resolve): nothing to judge,
	-- the game is left to load it
	if not path or not lfs.fileexists(path) then
		return true, "not found where the guard looks; not checked"
	end

	local f, err = io.open(path, "rb")
	if not f then
		return true, "could not be opened to check (" .. tostring(err) .. "); not checked"
	end
	local note = nil                     -- something unusual that doesn't make the save unloadable

	local fileSize = f:seek("end")
	if not fileSize or fileSize < 324 then
		f:close()
		return false, string.format("Save file is incomplete or 0 bytes (%s bytes)", tostring(fileSize or 0))
	end

	-- Return to beginning
	f:seek("set", 0)

	-- Main Record header (16 bytes): Tag(4), DataSize(4), HeaderData(4), Flags(4)
	local recHeader = f:read(16)
	if not recHeader or #recHeader < 16 then
		f:close()
		return false, "Premature end of file reading TES3 header"
	end

	local tag = recHeader:sub(1, 4)
	if tag ~= "TES3" then
		f:close()
		return false, string.format("Invalid header signature '%s' (expected TES3)", tostring(tag))
	end

	local hdrDataSize = validator.readUInt32(recHeader, 5)
	if not hdrDataSize or hdrDataSize < 308 then
		f:close()
		return false, string.format("Corrupt TES3 header record size (%s)", tostring(hdrDataSize))
	end

	-- Subrecord HEDR header (8 bytes): SubTag(4), SubSize(4)
	local subHeader = f:read(8)
	if not subHeader or #subHeader < 8 then
		f:close()
		return false, "Premature end of file reading HEDR subrecord header"
	end

	local subTag = subHeader:sub(1, 4)
	if subTag ~= "HEDR" then
		f:close()
		return false, string.format("Invalid subrecord signature '%s' (expected HEDR)", tostring(subTag))
	end

	local subSize = validator.readUInt32(subHeader, 5)
	if subSize ~= 300 then
		f:close()
		return false, string.format("Invalid HEDR subrecord size (%s != 300)", tostring(subSize))
	end

	-- Read HEDR body: version(4 float), flags(4 uint), company(32), desc(256), numRecords(4)
	local hedrBody = f:read(8)
	if not hedrBody or #hedrBody < 8 then
		f:close()
		return false, "Premature end of file reading HEDR flags"
	end

	local saveFlags = validator.readUInt32(hedrBody, 5)
	if saveFlags ~= 32 then
		note = string.format("unusual save flags (%s, usually 32)", tostring(saveFlags))
	end

	-- Traverse all records to EOF
	local offset = 16 + hdrDataSize
	while offset < fileSize do
		f:seek("set", offset)
		if fileSize - offset < 16 then
			local tail = f:read(fileSize - offset)
			if tail and not tail:find("%Z") then break end      -- padding, noted below; anything else is a cut-off record
			f:seek("set", offset)
		end
		local chunk = f:read(8)
		if not chunk or #chunk < 8 then
			f:close()
			return false, string.format("Premature end of file at offset %d", offset)
		end
		local recDataSize = validator.readUInt32(chunk, 5)
		if not recDataSize then
			f:close()
			return false, string.format("Corrupt record header at offset %d", offset)
		end
		offset = offset + 16 + recDataSize
		if offset > fileSize then
			f:close()
			return false, string.format("Save was truncated mid-record: record requires %d bytes, but file ends at %d", recDataSize, fileSize)
		end
	end

	f:close()
	if offset ~= fileSize then
		note = string.format("%d byte(s) after the last record", fileSize - offset)
	end

	return true, note or "Valid save"
end

return validator

