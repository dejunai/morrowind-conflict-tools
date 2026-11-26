"""mwdialog_luafix_kb.py - Known Bugs rules that reproduce local hand repairs of third-party MWSE Lua.

Each rule is exact text from the mod as released (the archive copy) and the repaired text. A rule
applies whole or not at all (every part of it in a file matches, or nothing in that file is changed),
and once applied its text is gone, so a second run finds nothing. Paths are under MWSE\\mods, or
lib/... under MWSE for libraries. Data only: mwdialog_luafix adds these to KNOWN_BUGS."""

KB_WHOLE = {"KB20", "KB23", "KB25", "KB26", "KB29", "KB30", "KB31", "KB32", "KB33", "KB34", "KB35", "KB36", "KB37", "KB38", "KB39", "KB40", "KB41", "KB42", "KB43", "KB44", "KB45", "KB46", "KB47", "KB48", "KB49", "KB50"}

WHAT = {
    "KB20": ('the default effect icons and particle textures name .tga files that are not shipped (the textures are .dds); the names are corrected to .dds'),
    "KB23": ("the achievements compare tes3.getGlobal() with a number, and getGlobal returns nil when the ABtv_Ach_* globals are not loaded ('attempt to compare nil with number'); missing globals fall back to player data"),
    "KB25": ('four quest icons name \\Icons\\SSQN\\BA_Vamp.dds; the shipped icon is BA_Vampire.dds'),
    "KB26": ('icons.MT_S names \\Icons\\SSQN\\MT\\MT24MT_S.dds; the icon ships as \\Icons\\SSQN\\MT24MT_S.dds'),
    "KB29": ("swapping a reference copies item data and cell state without nil checks and raises when the target object, the new reference or the cell is missing; the copies are guarded and the swap is pcall'd"),
    "KB30": ('musicSelectTrack reads tes3.player.cell before a game is loaded (main menu music)'),
    "KB31": ('export/import checks, restocking and the barter/dialogue handlers index the player cell, region, service actor and reference data without nil checks'),
    "KB32": ('validCompanionCheck reads mobileActor.object.name before checking the actor exists'),
    "KB33": ('resident/stables lookups and activate handlers index .data, .object, .cell and .baseObject without nil checks, and write lua data on references that do not support it'),
    "KB34": ('body-part and restore-health handlers index bodyPartManager, data and sceneNode without nil checks'),
    "KB35": ('essentialSwitch iterates tes3.getPlayerCell() without checking for a cell'),
    "KB36": ("every handler reads tes3.getPlayerRef().data and its cleared-cell lists without nil checks, uses the undefined global typeCell, and resets the lists in 'load' on the previous game's player"),
    "KB37": ('each load registers journal and spellTick handlers again without unregistering, so they stack per load; tes3.getJournalIndex can return nil'),
    "KB38": ("the book handler concatenates a boolean into a log line ('attempt to concatenate a boolean value'), and every counter handler indexes player data tables and counters without nil checks"),
    "KB39": ('copying lute item data assigns to itemData.data, which MWSE exposes read-only; the copy only runs when both item data tables exist'),
    "KB40": ("the 'loaded' handler compares e.reference (which loaded events do not have) with the player, so the equipment refresh never runs"),
    "KB41": ('death/activate handlers index reference data without checking the reference supports lua data'),
    "KB42": ("the jump/cell checks and music selection read tes3.player.mobile and the cell without nil checks; MUSE switches to a folder before checking it has music, so an empty folder keeps the old playlist under the new path and every track is 'Music file not found'"),
    "KB43": ('each load starts another endless calm timer and registers simulate again (they stack per load); lights out reads the player cell and a trigger reference without nil checks'),
    "KB44": ('progress text and the hidden-achievement group call progress()/progressMax() and index menuAchievements[category][256] without nil checks'),
    "KB45": ("equip/unequip handlers index the reference's race and lua data without nil checks"),
    "KB46": ("the scroll equip handlers also run for NPC equips and call tes3.mobilePlayer:equipMagic with the NPC's item, which raises when the player does not carry it"),
    "KB47": ('condition watchers keep deleted references; enchantedBaseId reads itemData.data on item data that is not initialised during equip, which crashes'),
    "KB48": ('the lantern equip check indexes npcRef.object without checking it is an NPC'),
    "KB49": ("the pose blender blends the root bones (Bip01, NonAccum, Footsteps), which flips the actor 180 degrees against the engine's facing when dialogue ends"),
    "KB50": ("the services capture tes3.worldController.weatherController when the file loads and index weathers, regions and timers without nil checks; service timers are started again on every init without cancelling the last one, and the sky texture timer passes its event table as 'immediate'"),
}

# (rule, owner, path, exact text as released, repaired text); the description is WHAT[rule]
PARTS = [
    ("KB20", 'Magicka Expanded', 'lib/operatorjack/magickaexpanded/effects/alteration.lua',
     "        icon = params.icon or \"RFD\\\\RFD_ms_alteration.tga\",\n"
     "        particleTexture = params.particleTexture or \"vfx_alt_glow.tga\",\n",
     "        icon = params.icon or \"RFD\\\\RFD_ms_alteration.dds\",\n"
     "        particleTexture = params.particleTexture or \"vfx_alt_glow.dds\",\n"),
    ("KB20", 'Magicka Expanded', 'lib/operatorjack/magickaexpanded/effects/conjuration.lua',
     "        -- Graphics/sounds.\n"
     "        icon = params.icon or \"RFD\\\\RFD_ms_conjuration.tga\",\n"
     "        particleTexture = params.particleTexture or \"vfx_conj_flare02.tga\",\n"
     "        castSound = params.castSound or \"conjuration cast\",\n",
     "        -- Graphics/sounds.\n"
     "        icon = params.icon or \"RFD\\\\RFD_ms_conjuration.dds\",\n"
     "        particleTexture = params.particleTexture or \"vfx_conj_flare02.dds\",\n"
     "        castSound = params.castSound or \"conjuration cast\",\n"),
    ("KB20", 'Magicka Expanded', 'lib/operatorjack/magickaexpanded/effects/conjuration.lua',
     "        nonRecastable = true,\n"
     "        casterLinked = true,\n"
     "\n"
     "        -- Graphics/sounds.\n"
     "        icon = params.icon or \"RFD\\\\RFD_ms_conjuration.tga\",\n"
     "        particleTexture = params.particleTexture or \"vfx_conj_flare02.tga\",\n"
     "        lighting = {0.99, 0.95, 0.67},\n"
     "\n"
     "        -- Required callbacks.\n"
     "        onTick = function(e) e:triggerBoundArmor(params.armorId, params.armorId2) end\n",
     "        nonRecastable = true,\n"
     "        casterLinked = true,\n"
     "\n"
     "        -- Graphics/sounds.\n"
     "        icon = params.icon or \"RFD\\\\RFD_ms_conjuration.dds\",\n"
     "        particleTexture = params.particleTexture or \"vfx_conj_flare02.dds\",\n"
     "        lighting = {0.99, 0.95, 0.67},\n"
     "\n"
     "        -- Required callbacks.\n"
     "        onTick = function(e) e:triggerBoundArmor(params.armorId, params.armorId2) end\n"),
    ("KB20", 'Magicka Expanded', 'lib/operatorjack/magickaexpanded/effects/conjuration.lua',
     "        nonRecastable = true,\n"
     "        casterLinked = true,\n"
     "\n"
     "        -- Graphics/sounds.\n"
     "        icon = params.icon or \"RFD\\\\RFD_ms_conjuration.tga\",\n"
     "        particleTexture = params.particleTexture or \"vfx_conj_flare02.tga\",\n"
     "        lighting = {0.99, 0.95, 0.67},\n"
     "\n"
     "        -- Required callbacks.\n"
     "        onTick = function(e) e:triggerBoundWeapon(params.weaponId) end\n",
     "        nonRecastable = true,\n"
     "        casterLinked = true,\n"
     "\n"
     "        -- Graphics/sounds.\n"
     "        icon = params.icon or \"RFD\\\\RFD_ms_conjuration.dds\",\n"
     "        particleTexture = params.particleTexture or \"vfx_conj_flare02.dds\",\n"
     "        lighting = {0.99, 0.95, 0.67},\n"
     "\n"
     "        -- Required callbacks.\n"
     "        onTick = function(e) e:triggerBoundWeapon(params.weaponId) end\n"),
    ("KB20", 'Magicka Expanded', 'lib/operatorjack/magickaexpanded/effects/conjuration.lua',
     "        hasNoMagnitude = true,\n"
     "        casterLinked = true,\n"
     "\n"
     "        -- Graphics/sounds.\n"
     "        icon = params.icon or \"RFD\\\\RFD_ms_conjuration.tga\",\n"
     "        particleTexture = params.particleTexture or \"vfx_conj_flare02.tga\",\n"
     "        lighting = {0.99, 0.95, 0.67},\n"
     "\n"
     "        -- Required callbacks.\n",
     "        hasNoMagnitude = true,\n"
     "        casterLinked = true,\n"
     "\n"
     "        -- Graphics/sounds.\n"
     "        icon = params.icon or \"RFD\\\\RFD_ms_conjuration.dds\",\n"
     "        particleTexture = params.particleTexture or \"vfx_conj_flare02.dds\",\n"
     "        lighting = {0.99, 0.95, 0.67},\n"
     "\n"
     "        -- Required callbacks.\n"),
    ("KB20", 'Magicka Expanded', 'lib/operatorjack/magickaexpanded/effects/conjuration.lua',
     "        -- Graphics/sounds.\n"
     "        icon = params.icon or \"RFD\\\\RFD_ms_conjuration.tga\",\n"
     "        lighting = {0.99, 0.95, 0.67},\n",
     "        -- Graphics/sounds.\n"
     "        icon = params.icon or \"RFD\\\\RFD_ms_conjuration.dds\",\n"
     "        lighting = {0.99, 0.95, 0.67},\n"),
    ("KB20", 'Magicka Expanded', 'lib/operatorjack/magickaexpanded/effects/destruction.lua',
     "        icon = params.icon or \"RFD\\\\RFD_ms_destruction.tga\",\n"
     "        particleTexture = params.particleTexture or \"vfx_alpha_bolt01.tga\",\n",
     "        icon = params.icon or \"RFD\\\\RFD_ms_destruction.dds\",\n"
     "        particleTexture = params.particleTexture or \"vfx_alpha_bolt01.dds\",\n"),
    ("KB20", 'Magicka Expanded', 'lib/operatorjack/magickaexpanded/effects/illusion.lua',
     "        icon = params.icon or \"RFD\\\\RFD_ms_illusion.tga\",\n"
     "        particleTexture = params.particleTexture or \"vfx_grnflare.tga\",\n",
     "        icon = params.icon or \"RFD\\\\RFD_ms_illusion.dds\",\n"
     "        particleTexture = params.particleTexture or \"vfx_grnflare.dds\",\n"),
    ("KB20", 'Magicka Expanded', 'lib/operatorjack/magickaexpanded/effects/mysticism.lua',
     "        icon = params.icon or \"RFD\\\\RFD_ms_mysticism.tga\",\n"
     "        particleTexture = params.particleTexture or \"vfx_myst_flare01.tga\",\n",
     "        icon = params.icon or \"RFD\\\\RFD_ms_mysticism.dds\",\n"
     "        particleTexture = params.particleTexture or \"vfx_myst_flare01.dds\",\n"),
    ("KB20", 'Magicka Expanded', 'lib/operatorjack/magickaexpanded/effects/restoration.lua',
     "        icon = params.icon or \"RFD\\\\RFD_ms_restoration.tga\",\n"
     "        particleTexture = params.particleTexture or \"vfx_bluecloud.tga\",\n",
     "        icon = params.icon or \"RFD\\\\RFD_ms_restoration.dds\",\n"
     "        particleTexture = params.particleTexture or \"vfx_bluecloud.dds\",\n"),
    ("KB20", 'Magicka Expanded', 'operatorjack/magickaexpanded-lorefriendlypack/effects/banishdaedraeffect.lua',
     "    particleTexture = \"vfx_myst_flare01.tga\",\n",
     "    particleTexture = \"vfx_myst_flare01.dds\",\n"),
    ("KB23", 'OAAB Grazelands', 'oaab/grazelands/achievements.lua',
     "-- Track the MWSE summon even when the achievement framework is absent.\n"
     "local function observeVerminoth()\n",
     "-- Track the MWSE summon even when the achievement framework is absent.\n"
     "local function getGlobal(var)\n"
     "    local val = tes3.getGlobal(var)\n"
     "    if val ~= nil then\n"
     "        return val\n"
     "    end\n"
     "    if tes3.player and tes3.player.data and tes3.player.data[\"oaab_grazelands_achievements\"] then\n"
     "        return tes3.player.data[\"oaab_grazelands_achievements\"][var] or 0\n"
     "    end\n"
     "    return 0\n"
     "end\n"
     "\n"
     "local function setGlobal(var, value)\n"
     "    if tes3.findGlobal(var) then\n"
     "        return tes3.setGlobal(var, value)\n"
     "    end\n"
     "    if tes3.player then\n"
     "        tes3.player.data[\"oaab_grazelands_achievements\"] = tes3.player.data[\"oaab_grazelands_achievements\"] or {}\n"
     "        tes3.player.data[\"oaab_grazelands_achievements\"][var] = value\n"
     "        return true\n"
     "    end\n"
     "    return false\n"
     "end\n"
     "\n"
     "local function observeVerminoth()\n"),
    ("KB23", 'OAAB Grazelands', 'oaab/grazelands/achievements.lua',
     "    if not tes3.mobilePlayer or tes3.getGlobal(\"ABtv_Ach_Daedrat\") >= 1 then\n",
     "    if not tes3.mobilePlayer or getGlobal(\"ABtv_Ach_Daedrat\") >= 1 then\n"),
    ("KB23", 'OAAB Grazelands', 'oaab/grazelands/achievements.lua',
     "                tes3.setGlobal(\"ABtv_Ach_Daedrat\", 1)\n",
     "                setGlobal(\"ABtv_Ach_Daedrat\", 1)\n"),
    ("KB23", 'OAAB Grazelands', 'oaab/grazelands/achievements.lua',
     "            achievement.progress = function() return tes3.getGlobal(variable) end\n",
     "            achievement.progress = function() return getGlobal(variable) end\n"),
    ("KB23", 'OAAB Grazelands', 'oaab/grazelands/achievements.lua',
     "            achievement.condition = function() return tes3.getGlobal(variable) >= threshold end\n",
     "            achievement.condition = function() return getGlobal(variable) >= threshold end\n"),
    ("KB25", 'SSQN Patches', 'cz/ssqnpatches/main.lua',
     "\t\tssqn.registerQIcon(\"vaba06_mastrius\",\"\\\\Icons\\\\SSQN\\\\BA_Vamp.dds\")\n",
     "\t\tssqn.registerQIcon(\"vaba06_mastrius\",\"\\\\Icons\\\\SSQN\\\\BA_Vampire.dds\")\n"),
    ("KB25", 'SSQN Patches', 'cz/ssqnpatches/main.lua',
     "\t\tssqn.registerQIcon(\"vabamm02_vampire\",\"\\\\Icons\\\\SSQN\\\\BA_Vamp.dds\")\n",
     "\t\tssqn.registerQIcon(\"vabamm02_vampire\",\"\\\\Icons\\\\SSQN\\\\BA_Vampire.dds\")\n"),
    ("KB25", 'SSQN Patches', 'cz/ssqnpatches/main.lua',
     "\t\tssqn.registerQIcon(\"vabamm04_serano\",\"\\\\Icons\\\\SSQN\\\\BA_Vamp.dds\")\n"
     "\t\tssqn.registerQIcon(\"vabamm05_dulo\",\"\\\\Icons\\\\SSQN\\\\BA_Vamp.dds\")\n",
     "\t\tssqn.registerQIcon(\"vabamm04_serano\",\"\\\\Icons\\\\SSQN\\\\BA_Vampire.dds\")\n"
     "\t\tssqn.registerQIcon(\"vabamm05_dulo\",\"\\\\Icons\\\\SSQN\\\\BA_Vampire.dds\")\n"),
    ("KB26", 'SSQN LE', 'ssqn/iconlist.lua',
     "icons.MT_S = \"\\\\Icons\\\\SSQN\\\\MT\\\\MT24MT_S.dds\"\n",
     "icons.MT_S = \"\\\\Icons\\\\SSQN\\\\MT24MT_S.dds\"\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "local function cloneReferenceData(newRef, oldRef)\n"
     "    -- Copy over basic item data.\n",
     "local function cloneReferenceData(newRef, oldRef)\n"
     "    if not newRef or not oldRef then return end\n"
     "\n"
     "    -- Copy over basic item data.\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "        newItemData.charge = oldItemData.charge\n"
     "        -- newItemData.count = oldItemData.count\n"
     "        newItemData.condition = oldItemData.condition\n"
     "        newItemData.owner = oldItemData.owner\n"
     "        newItemData.requirement = oldItemData.requirement\n",
     "        if newItemData then\n"
     "            if oldItemData.charge ~= nil then\n"
     "                pcall(function() newItemData.charge = oldItemData.charge end)\n"
     "            end\n"
     "            if oldItemData.condition ~= nil then\n"
     "                pcall(function() newItemData.condition = oldItemData.condition end)\n"
     "            end\n"
     "            if oldItemData.timeLeft ~= nil then\n"
     "                pcall(function() newItemData.timeLeft = oldItemData.timeLeft end)\n"
     "            end\n"
     "            if oldItemData.soul ~= nil then\n"
     "                pcall(function() newItemData.soul = oldItemData.soul end)\n"
     "            end\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "        -- Copy over script variable data.\n"
     "        if (newRef.object.script and newRef.object.script ==\n"
     "            oldRef.object.script) then\n"
     "            local newContext = newItemData.context\n"
     "            local oldContext = oldItemData.context\n"
     "            for name, oldVarData in pairs(oldContext:getVariableData()) do\n"
     "                newContext[name] = oldVarData.value\n",
     "            if oldItemData.owner ~= nil then\n"
     "                pcall(function() newItemData.owner = oldItemData.owner end)\n"
     "                if newItemData.owner ~= nil and oldItemData.requirement ~= nil then\n"
     "                    pcall(function()\n"
     "                        newItemData.requirement = oldItemData.requirement\n"
     "                    end)\n"
     "                end\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "            end\n"
     "        end\n"
     "\n",
     "            end\n"
     "\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "        -- Copy over lua data.\n"
     "        -- TODO: Figure out if this is safe.\n"
     "        if oldRef.data then\n"
     "            table.copy(oldRef.data, newRef.data)\n"
     "            table.copy(oldRef.tempData, newRef.tempData)\n",
     "            -- Copy over script variable data.\n"
     "            if (newRef.object.script and newRef.object.script ==\n"
     "                oldRef.object.script) then\n"
     "                pcall(function()\n"
     "                    local newContext = newItemData.context\n"
     "                    local oldContext = oldItemData.context\n"
     "                    if newContext and oldContext then\n"
     "                        for name, oldVarData in pairs(oldContext:getVariableData()) do\n"
     "                            newContext[name] = oldVarData.value\n"
     "                        end\n"
     "                    end\n"
     "                end)\n"
     "            end\n"
     "\n"
     "            -- Copy over lua data.\n"
     "            if oldRef.data and newRef.data then\n"
     "                pcall(function()\n"
     "                    table.copy(oldRef.data, newRef.data)\n"
     "                    table.copy(oldRef.tempData, newRef.tempData)\n"
     "                end)\n"
     "            end\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "    if ref.disabled or ref.deleted then return end\n",
     "    if not ref or ref.disabled or ref.deleted then return end\n"
     "    if not newObj or not newObj.newObject then return end\n"
     "\n"
     "    local baseObj = tes3.getObject(newObj.newObject)\n"
     "    if not baseObj then\n"
     "        mwse.log(\"[Object Replacer] Target object '%s' does not exist! Skipping replacement.\", tostring(newObj.newObject))\n"
     "        return\n"
     "    end\n"
     "\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "    local cell_modified = cell.modified\n",
     "    local cell_modified = cell and cell.modified\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "    })\n"
     "    cloneReferenceData(newRef, ref)\n",
     "    })\n"
     "    if not newRef then\n"
     "        mwse.log(\"[Object Replacer] Failed to create reference for '%s'!\", tostring(newObj.newObject))\n"
     "        return\n"
     "    end\n"
     "\n"
     "    cloneReferenceData(newRef, ref)\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "    ref.modified = ref_modified\n"
     "    cell.modified = cell_modified\n",
     "    ref.modified = ref_modified\n"
     "    if cell then\n"
     "        cell.modified = cell_modified\n"
     "    end\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "function OR.checkForCell(cellList, refCell)\n"
     "    for _, cell in pairs(cellList) do\n",
     "function OR.checkForCell(cellList, refCell)\n"
     "    if not cellList or not refCell then return false end\n"
     "    for _, cell in pairs(cellList) do\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "        local cellString1 = string.trim(string.upper(cell.cellName))\n"
     "        local cellString2 = string.trim(string.upper(refCell))\n"
     "        if ((cell.cellName and\n"
     "            (string.find(cellString2, cellString1) or cellString2 == cellString1)) or\n"
     "            not cell) then return true end\n"
     "    end\n",
     "        if not cell then\n"
     "            return true\n"
     "        elseif cell.cellName then\n"
     "            local cellString1 = string.trim(string.upper(cell.cellName))\n"
     "            local cellString2 = string.trim(string.upper(refCell))\n"
     "            if string.find(cellString2, cellString1, 1, true) or cellString2 == cellString1 then\n"
     "                return true\n"
     "            end\n"
     "        end\n"
     "    end\n"
     "    return false\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "                ref.data.GPDOR = {}\n",
     "                ref.data.GPDOR = ref.data.GPDOR or {}\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "                    specificCell = OR.checkForCell(newObj.specificCell,\n"
     "                                                   ref.cell.id)\n",
     "                    specificCell = OR.checkForCell(newObj.specificCell,\n"
     "                                                   ref.cell and ref.cell.id)\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "                    excludedCell = OR.checkForCell(newObj.excludedCell,\n"
     "                                                   ref.cell.id)\n",
     "                    excludedCell = OR.checkForCell(newObj.excludedCell,\n"
     "                                                   ref.cell and ref.cell.id)\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "                        actuallyReplaced = true\n"
     "                        OR.swapObjects(ref, ref.cell, newObj)\n",
     "                        actuallyReplaced = true\n"
     "                        pcall(OR.swapObjects, ref, ref.cell, newObj)\n"),
    ("KB29", 'Dynamic Object Replacer', 'lib/dor/gpobjectreplacer.lua',
     "                            OR.swapObjects(ref, ref.cell, newObj)\n",
     "                            pcall(OR.swapObjects, ref, ref.cell, newObj)\n"),
    ("KB30", 'Secrets of the Crystal City', 'aa22/music/main.lua',
     "    if isMassamaCell(tes3.player.cell) then\n",
     "    if tes3.player and isMassamaCell(tes3.player.cell) then\n"),
    ("KB31", 'Buying Game', 'buyinggame/common.lua',
     "common.isExport = function(item)\n"
     "\tlocal cell = string.sub(tes3.player.cell.id, string.find(tes3.player.cell.id, \"^[%w -]+\"))\n",
     "common.isExport = function(item)\n"
     "\tif not item or not tes3.player or not tes3.player.cell then return false end\n"
     "\tlocal cellId = tes3.player.cell.id\n"
     "\tif not cellId then return false end\n"
     "\tlocal s, e = string.find(cellId, \"^[%w -]+\")\n"
     "\tlocal cell = s and string.sub(cellId, s, e) or cellId\n"),
    ("KB31", 'Buying Game', 'buyinggame/common.lua',
     "\n"
     "\tif common.config[cell] then\n"
     "\t\tif common.config[cell].export and common.config[cell].export[item] then\n",
     "\n"
     "\tif common.config and common.config[cell] then\n"
     "\t\tif common.config[cell].export and common.config[cell].export[item] then\n"),
    ("KB31", 'Buying Game', 'buyinggame/common.lua',
     "\t\tlocal region = tes3.getCell{id = cell}.region or tes3.getRegion{useDoors = true}\n"
     "\t\treturn common.config[region.id] and common.config[region.id].export and common.config[region.id].export[item]\n"
     "\tend\n",
     "\t\tlocal cellObj = tes3.getCell{id = cell}\n"
     "\t\tlocal region = (cellObj and cellObj.region) or tes3.getRegion{useDoors = true}\n"
     "\t\tif region and region.id and common.config and common.config[region.id] then\n"
     "\t\t\treturn common.config[region.id].export and common.config[region.id].export[item]\n"
     "\t\tend\n"
     "\tend\n"
     "\treturn false\n"),
    ("KB31", 'Buying Game', 'buyinggame/common.lua',
     "\tlocal cell = string.sub(tes3.player.cell.id, string.find(tes3.player.cell.id, \"^[%w -]+\"))\n"
     "\tif common.config[cell] then\n",
     "\tif not item or not tes3.player or not tes3.player.cell then return false end\n"
     "\tlocal cellId = tes3.player.cell.id\n"
     "\tif not cellId then return false end\n"
     "\tlocal s, e = string.find(cellId, \"^[%w -]+\")\n"
     "\tlocal cell = s and string.sub(cellId, s, e) or cellId\n"
     "\n"
     "\tif common.config and common.config[cell] then\n"),
    ("KB31", 'Buying Game', 'buyinggame/common.lua',
     "\t\tlocal region = tes3.getCell{id = cell}.region or tes3.getRegion{useDoors = true}\n"
     "\t\treturn common.config[region.id] and common.config[region.id].import and common.config[region.id].import[item]\n"
     "\tend\n",
     "\t\tlocal cellObj = tes3.getCell{id = cell}\n"
     "\t\tlocal region = (cellObj and cellObj.region) or tes3.getRegion{useDoors = true}\n"
     "\t\tif region and region.id and common.config and common.config[region.id] then\n"
     "\t\t\treturn common.config[region.id].import and common.config[region.id].import[item]\n"
     "\t\tend\n"
     "\tend\n"
     "\treturn false\n"),
    ("KB31", 'Buying Game', 'buyinggame/main.lua',
     "\t\t\t\tif not mobileActor.reference.data.buyingGame then\n",
     "\t\t\t\tif not (mobileActor.reference and mobileActor.reference.data and mobileActor.reference.data.buyingGame) then\n"),
    ("KB31", 'Buying Game', 'buyinggame/main.lua',
     "\tif not tes3.player.data or not tes3.player.data.buyingGame or not tes3.player.data.buyingGame.reequip or not tes3.player.data.buyingGame.reequip[e.reference.id] then\n",
     "\tif not e or not e.reference or not e.mobile or not tes3.player or not tes3.player.data then\n"
     "\t\treturn\n"
     "\tend\n"
     "\tif not tes3.player.data.buyingGame or not tes3.player.data.buyingGame.reequip or not tes3.player.data.buyingGame.reequip[e.reference.id] then\n"),
    ("KB31", 'Buying Game', 'buyinggame/main.lua',
     "\tlocal timestamp = e.reference.data.buyingGame and e.reference.data.buyingGame.timestamp\n",
     "\tlocal timestamp = e.reference.data and e.reference.data.buyingGame and e.reference.data.buyingGame.timestamp\n"
     "\tif not timestamp then return end\n"),
    ("KB31", 'Buying Game', 'buyinggame/main.lua',
     "\tlocal newTimestamp = tes3.getSimulationTimestamp()\n"
     "\t\n",
     "\tlocal newTimestamp = tes3.getSimulationTimestamp()\n"
     "\tlocal resetDelay = tes3.findGMST(tes3.gmst.fBarterGoldResetDelay)\n"
     "\tif not resetDelay then return end\n"
     "\t\n"),
    ("KB31", 'Buying Game', 'buyinggame/main.lua',
     "\tif newTimestamp - timestamp >= tes3.findGMST(tes3.gmst.fBarterGoldResetDelay).value * common.config.restockTime then\n"
     "\t\n",
     "\tif newTimestamp - timestamp >= resetDelay.value * common.config.restockTime then\n"),
    ("KB31", 'Buying Game', 'buyinggame/main.lua',
     "\n"
     "\t\tfor i, item in ipairs(equipment) do\n"
     "\t\t\te.mobile:equip{item = item, addItem = true}\n",
     "\t\tif equipment then\n"
     "\t\t\tfor i, item in ipairs(equipment) do\n"
     "\t\t\t\te.mobile:equip{item = item, addItem = true}\n"
     "\t\t\tend\n"),
    ("KB31", 'Buying Game', 'buyinggame/main.lua',
     "\tlocal merchant = tes3ui.getServiceActor().reference\n"
     "\t\n"
     "\t-- if doesn't have buyingGame table then we are using grandmaster perk, the npc is no merchant - no need to remove items\n"
     "\t\n"
     "\tif not merchant.data.buyingGame then\n",
     "\tlocal serviceActor = tes3ui.getServiceActor()\n"
     "\tlocal merchant = serviceActor and serviceActor.reference\n"
     "\tif not merchant or not merchant.data or not merchant.data.buyingGame then\n"),
    ("KB31", 'Buying Game', 'buyinggame/main.lua',
     "\tlocal actor = tes3ui.getServiceActor().reference\n"
     "\tlocal barter = e.element:findChild(tes3ui.registerID(\"MenuDialog_service_barter\"))\n",
     "\tlocal service = tes3ui.getServiceActor()\n"
     "\tif not service or not service.reference then return end\n"
     "\tlocal actor = service.reference\n"
     "\tlocal barter = e.element and e.element:findChild(tes3ui.registerID(\"MenuDialog_service_barter\"))\n"
     "\tif not barter then return end\n"),
    ("KB31", 'Buying Game', 'buyinggame/main.lua',
     "\ttimer.frame.delayOneFrame(function()\n"
     "\t\tif barter.visible then\n",
     "\ttimer.frame.delayOneFrame(function()\n"
     "\t\tif not e.element or not barter then return end\n"
     "\t\tif barter.visible then\n"),
    ("KB31", 'Buying Game', 'buyinggame/main.lua',
     "\t\t\tif actor.data.buyingGame and actor.data.buyingGame.investment then return end\n",
     "\t\t\tif actor.data and actor.data.buyingGame and actor.data.buyingGame.investment then return end\n"),
    ("KB32", 'Companion Leveler', 'companionleveler/functions/common.lua',
     "function this.validCompanionCheck(mobileActor)\n"
     "\tlog:trace(\"Checking \" .. mobileActor.object.name .. \"...\")\n",
     "function this.validCompanionCheck(mobileActor)\n"
     "\tif not mobileActor or not mobileActor.object then\n"
     "\t\treturn false\n"
     "\tend\n"
     "\n"
     "\tlog:trace(\"Checking \" .. mobileActor.object.name .. \"...\")\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "    local name = resident.data.tgw and resident.data.tgw.name or resident.object.name\n",
     "    if not resident then return \"Companion\" end\n"
     "    local name = resident.data and resident.data.tgw and resident.data.tgw.name or (resident.object and resident.object.name) or resident.id\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "    local nearbyCompanions = {}\n"
     "    for mobile in tes3.iterate(tes3.mobilePlayer.friendlyActors) do\n",
     "    local nearbyCompanions = {}\n"
     "    if not tes3.mobilePlayer or not tes3.mobilePlayer.friendlyActors then\n"
     "        return nearbyCompanions\n"
     "    end\n"
     "    for mobile in tes3.iterate(tes3.mobilePlayer.friendlyActors) do\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "        if tes3.getCurrentAIPackageId(mobile) == tes3.aiPackage.follow then\n",
     "        if mobile and mobile.reference and tes3.getCurrentAIPackageId(mobile) == tes3.aiPackage.follow then\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "    local creatures = {}\n"
     "    for _, companion in ipairs(companions) do\n",
     "    local creatures = {}\n"
     "    if not companions then return creatures end\n"
     "    for _, companion in ipairs(companions) do\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "        if companion.baseObject.objectType == tes3.objectType.creature then\n",
     "        if companion and companion.baseObject and companion.baseObject.objectType == tes3.objectType.creature then\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "    logger:debug(\"Getting Resident\")\n"
     "    local residentID = stables.data.guarStablesResident\n",
     "    logger:debug(\"Getting Resident\")\n"
     "    if not stables or not stables.data then return end\n"
     "    local residentID = stables.data.guarStablesResident\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "    for reference in stables.cell:iterateReferences() do\n"
     "        if reference then\n",
     "    if not stables.cell then return end\n"
     "    for reference in stables.cell:iterateReferences() do\n"
     "        if reference and reference.baseObject then\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "    for reference in resident.cell:iterateReferences() do\n"
     "        if reference then\n",
     "    if not resident or not resident.cell then return end\n"
     "    for reference in resident.cell:iterateReferences() do\n"
     "        if reference and reference.baseObject then\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "                if reference.data.guarStablesResident == resident.baseObject.id:lower() then\n",
     "                if reference.data and reference.data.guarStablesResident == resident.baseObject.id:lower() then\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "    logger:debug(\"Releasing Resident %s\", resident.object.id)\n",
     "    if not resident then return end\n"
     "    logger:debug(\"Releasing Resident %s\", resident.object and resident.object.id or resident.id)\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "    if resident.data.tgw then\n"
     "        resident.data.tgw.aiState = \"following\"\n"
     "        resident.data.tgw.followingRef = \"player\"\n",
     "    if resident.data then\n"
     "        if resident.data.tgw then\n"
     "            resident.data.tgw.aiState = \"following\"\n"
     "            resident.data.tgw.followingRef = \"player\"\n"
     "        end\n"
     "        resident.data.inGuarStables = nil\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "    if stables then\n",
     "    if stables and stables.data then\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "        logger:error(\"unable to find stables for resident %s\", resident.object.id)\n",
     "        logger:error(\"unable to find stables for resident %s\", resident.object and resident.object.id or resident.id)\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "    end\n"
     "    resident.data.inGuarStables = nil\n",
     "    end\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "    logger:debug(\"Housing Resident %s\", resident.object.id)\n",
     "    if not stables or not resident then return end\n"
     "    logger:debug(\"Housing Resident %s\", resident.object and resident.object.id or resident.id)\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "    --Guar whisperer shit...\n"
     "    if resident.data.tgw then\n"
     "        resident.data.tgw.aiState = \"waiting\"\n",
     "    --Guar whisperer shit...\n"
     "    if resident.data and resident.data.tgw then\n"
     "        resident.data.tgw.aiState = \"waiting\"\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "    stables.data.guarStablesResident = resident.baseObject.id:lower()\n"
     "    resident.data.inGuarStables = true\n",
     "    if stables.supportsLuaData then\n"
     "        stables.data.guarStablesResident = resident.baseObject.id:lower()\n"
     "    end\n"
     "    if resident.supportsLuaData then\n"
     "        resident.data.inGuarStables = true\n"
     "    end\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "                logger:debug(\"Selected %s to house\", companion.object.id)\n",
     "                logger:debug(\"Selected %s to house\", companion.object and companion.object.id or companion.id)\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "local function onActivate(e)\n"
     "    local playerActivating = e.activator == tes3.player\n",
     "local function onActivate(e)\n"
     "    if not e.target or not e.target.baseObject then return end\n"
     "    local playerActivating = e.activator == tes3.player\n"),
    ("KB33", 'Imperial Stables', 'danae/stables/main.lua',
     "local function activateHousedResident(e)\n"
     "    local isResident = e.target.data.inGuarStables\n",
     "local function activateHousedResident(e)\n"
     "    if not e.target or not e.target.data then return end\n"
     "    local isResident = e.target.data.inGuarStables\n"),
    ("KB34", 'Elemental Effects', 'elemental effects/main.lua',
     "    return coroutine.wrap(function()\n"
     "        for name, index in pairs(tes3.activeBodyPart) do\n",
     "    return coroutine.wrap(function()\n"
     "        if not ref or not ref.bodyPartManager then return end\n"
     "        for name, index in pairs(tes3.activeBodyPart) do\n"),
    ("KB34", 'Elemental Effects', 'elemental effects/main.lua',
     "local function updateExposedStates(ref, effect)\n"
     "    local updated = false\n",
     "local function updateExposedStates(ref, effect)\n"
     "    if not ref or not ref.data or not ref.bodyPartManager then return false end\n"
     "    local updated = false\n"),
    ("KB34", 'Elemental Effects', 'elemental effects/main.lua',
     "local function onRestoreHealth(e)\n"
     "    if e.effect.id == tes3.effect.restoreHealth or e.effect.id == tes3.effect.absorbHealth then\n",
     "local function onRestoreHealth(e)\n"
     "    if not e or not e.effect or not e.target then return end\n"
     "    if e.effect.id == tes3.effect.restoreHealth or e.effect.id == tes3.effect.absorbHealth then\n"),
    ("KB34", 'Elemental Effects', 'elemental effects/main.lua',
     "        if e.target.data.ee then\n",
     "        if e.target.data and e.target.data.ee then\n"),
    ("KB34", 'Elemental Effects', 'elemental effects/main.lua',
     "            removeEffectDecals(e.target.sceneNode)\n"
     "\t\t\tapplyDisfigureSpell(e.target)\n"
     "            if e.target == tes3.player then\n",
     "            if e.target.sceneNode then\n"
     "                removeEffectDecals(e.target.sceneNode)\n"
     "            end\n"
     "            applyDisfigureSpell(e.target)\n"
     "            if e.target == tes3.player and tes3.mobilePlayer and tes3.mobilePlayer.firstPersonReference and tes3.mobilePlayer.firstPersonReference.sceneNode then\n"),
    ("KB34", 'Elemental Effects', 'elemental effects/main.lua',
     "    -- ignore unaffected actors\n"
     "    local exposedStates = ref.data.ee\n",
     "    -- ignore unaffected actors\n"
     "    if not ref or not ref.data then return end\n"
     "    local exposedStates = ref.data.ee\n"),
    ("KB35", 'Essential Indicators', 'essential indicators/main.lua',
     "\tfor ref in tes3.getPlayerCell():iterateReferences(tes3.objectType.actor) do\n",
     "\tlocal playerCell = tes3.getPlayerCell()\n"
     "\tif not playerCell then return end\n"
     "\tfor ref in playerCell:iterateReferences(tes3.objectType.actor) do\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "local mapMarkerLib = include(\"diject.mapMarkerLib.interop\")\n"
     "local records = {}\n",
     "local mapMarkerLib = include(\"diject.mapMarkerLib.interop\")\n"
     "if not mapMarkerLib then\n"
     "    return\n"
     "end\n"
     "local records = {}\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\n"
     "\tlocal data = tes3.getPlayerRef().data\n",
     "\t\n"
     "\tlocal player = tes3.getPlayerRef() or tes3.player\n"
     "\tif not player or not player.data then return end\n"
     "\tlocal data = player.data\n"
     "\tif not (data.listClearedIntCells and data.listClearedExtCells) then return end\n"
     "\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\tlocal activeCells = tes3.getActiveCells()\t\n"
     "\tfor _, cell in pairs(activeCells) do\n",
     "\tlocal activeCells = tes3.getActiveCells()\t\n"
     "\tif not activeCells then return end\n"
     "\tfor _, cell in pairs(activeCells) do\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\t\tif door.destination and door.destination.cell then\n"
     "\t\t\t\tif data.listClearedIntCells[door.destination.cell.id:lower()] or data.listClearedExtCells[door.destination.cell.id:lower()] then\n",
     "\t\t\tif door.destination and door.destination.cell and door.destination.cell.id then\n"
     "\t\t\t\tlocal destId = door.destination.cell.id:lower()\n"
     "\t\t\t\tif data.listClearedIntCells[destId] or data.listClearedExtCells[destId] then\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "local function DrawOneExtMarker(cell)\n"
     "\tlocal data = tes3.getPlayerRef().data\n",
     "local function DrawOneExtMarker(cell)\n"
     "\tif not cell or not cell.id then return end\n"
     "\tlocal player = tes3.getPlayerRef() or tes3.player\n"
     "\tif not player or not player.data then return end\n"
     "\tlocal data = player.data\n"
     "\tif not data.listClearedExtCells then data.listClearedExtCells = {} end\n"
     "\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\tif extCells[cell.id:lower()] then\n"
     "\t\tlocal cellType = extCells[cell.id:lower()]\n"
     "\t\tif typeCell ~= \"\" then \n",
     "\tlocal cellId = cell.id:lower()\n"
     "\tif extCells[cellId] then\n"
     "\t\tlocal cellType = extCells[cellId]\n"
     "\t\tif cellType and cellType ~= \"\" then \n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\t\tif doubleExtCells[cell.id:lower()] then\n"
     "\t\t\t\tlocal cellType = doubleExtCells[cell.id:lower()]\n"
     "\t\t\t\tcreateMarkerForPosition(path..cellType..\".dds\", scale, ShiftX, ShiftY, '', 0, true, cell, X, Y)\n",
     "\t\t\tif doubleExtCells[cellId] then\n"
     "\t\t\t\tlocal doubleType = doubleExtCells[cellId]\n"
     "\t\t\t\tcreateMarkerForPosition(path..doubleType..\".dds\", scale, ShiftX, ShiftY, '', 0, true, cell, X, Y)\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\tif data.listClearedExtCells[cell.id:lower()] then\n",
     "\tif data.listClearedExtCells[cellId] then\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\tif tes3.getPlayerRef() then\n"
     "\t\tlocal data = tes3.getPlayerRef().data\n",
     "\tlocal player = tes3.getPlayerRef() or tes3.player\n"
     "\tif player and player.data then\n"
     "\t\tlocal data = player.data\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\tif config.ShowAllMarkersMap == true then sourceCells = tes3.dataHandler.nonDynamicData.cells else sourceCells = data.listMarkersOpenCells end\t\t\t\n",
     "\t\tif config.ShowAllMarkersMap == true then\n"
     "\t\t\tsourceCells = (tes3.dataHandler and tes3.dataHandler.nonDynamicData and tes3.dataHandler.nonDynamicData.cells) or {}\n"
     "\t\telse\n"
     "\t\t\tsourceCells = data.listMarkersOpenCells or {}\n"
     "\t\tend\t\t\t\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\t\tif config.ShowAllMarkersMap == true then cell = cellData else cell = tes3.getCell({x = cellData.pos.x, y = cellData.pos.y}) end\n"
     "\t\t\tif cell.name ~= nil and not cell.isInterior then\n",
     "\t\t\tif config.ShowAllMarkersMap == true then\n"
     "\t\t\t\tcell = cellData\n"
     "\t\t\telseif cellData and cellData.pos then\n"
     "\t\t\t\tcell = tes3.getCell({x = cellData.pos.x, y = cellData.pos.y})\n"
     "\t\t\tend\n"
     "\t\t\tif cell and cell.name ~= nil and not cell.isInterior then\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\tmapMarkerLib.updateLocalMarkers(true)\n"
     "\t\tmapMarkerLib.updateWorldMarkers(true)\n",
     "\t\tif mapMarkerLib and mapMarkerLib.updateLocalMarkers then\n"
     "\t\t\tmapMarkerLib.updateLocalMarkers(true)\n"
     "\t\tend\n"
     "\t\tif mapMarkerLib and mapMarkerLib.updateWorldMarkers then\n"
     "\t\t\tmapMarkerLib.updateWorldMarkers(true)\n"
     "\t\tend\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\tif menu and e.menu == menu then\n"
     "\t\tlocal data = tes3.getPlayerRef().data\t\n",
     "\tif menu and e and e.menu == menu then\n"
     "\t\tlocal player = tes3.getPlayerRef() or tes3.player\n"
     "\t\tif not player or not player.data then return end\n"
     "\t\tlocal data = player.data\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\tlocal name = cell.displayName\n",
     "\t\tif not cell then return end\n"
     "\t\tlocal name = cell.displayName or cell.editorName or \"\"\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\t\tif data.listClearedIntCells[cell.id:lower()] or data.listClearedExtCells[cell.id:lower()] then \n",
     "\t\t\tif (data.listClearedIntCells and cell.id and data.listClearedIntCells[cell.id:lower()]) or (data.listClearedExtCells and cell.id and data.listClearedExtCells[cell.id:lower()]) then \n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "    if e.object and e.object.objectType == tes3.objectType.door and e.reference.destination and e.reference.destination.cell then\n",
     "    if e and e.object and e.object.objectType == tes3.objectType.door and e.reference and e.reference.destination and e.reference.destination.cell then\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\tlocal data = tes3.getPlayerRef().data\t\n"
     "\t\tif data.listClearedIntCells[cell.id:lower()] or data.listClearedExtCells[cell.id:lower()] then\n"
     "\t\t\tlocal destCell = e.tooltip:findChild(\"HelpMenu_destinationCell\")\n",
     "\t\tlocal player = tes3.getPlayerRef() or tes3.player\n"
     "\t\tif not player or not player.data then return end\n"
     "\t\tlocal data = player.data\n"
     "\t\tif not (data.listClearedIntCells and data.listClearedExtCells) then return end\n"
     "\t\tif cell.id and (data.listClearedIntCells[cell.id:lower()] or data.listClearedExtCells[cell.id:lower()]) then\n"
     "\t\t\tlocal destCell = e.tooltip and e.tooltip:findChild(\"HelpMenu_destinationCell\")\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "    local cell = tes3.getPlayerCell()\n"
     "\tlocal data = tes3.getPlayerRef().data\n",
     "    local cell = tes3.getPlayerCell()\n"
     "    if not cell or not cell.id then return end\n"
     "    local player = tes3.getPlayerRef() or tes3.player\n"
     "    if not player or not player.data then return end\n"
     "    local data = player.data\n"
     "    if not data.listClearedExtCells then data.listClearedExtCells = {} end\n"
     "    if not data.listClearedIntCells then data.listClearedIntCells = {} end\n"
     "\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\t\tDrawOneExtMarker(cell)\n"
     "\t\t\ttes3.messageBox(string.format(\"%s added to the list of cleared cells\", cell.name))\n",
     "\t\t\tDrawOneExtMarker(cell)\n"
     "\t\t\ttes3.messageBox(string.format(\"%s added to the list of cleared cells\", cell.name or cell.id))\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\t\tDrawOneExtMarker(cell)\n"
     "\t\t\ttes3.messageBox(string.format(\"%s removed from the list of cleared cells\", cell.name))\n",
     "\t\t\tDrawOneExtMarker(cell)\n"
     "\t\t\ttes3.messageBox(string.format(\"%s removed from the list of cleared cells\", cell.name or cell.id))\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\t\tdrawLocalsMarkers()\n"
     "\t\t\ttes3.messageBox(string.format(\"%s added to the list of cleared cells\", cell.name))\n",
     "\t\t\tdrawLocalsMarkers()\n"
     "\t\t\ttes3.messageBox(string.format(\"%s added to the list of cleared cells\", cell.name or cell.id))\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\t\tdrawLocalsMarkers()\n"
     "\t\t\ttes3.messageBox(string.format(\"%s removed from the list of cleared cells\", cell.name))\n",
     "\t\t\tdrawLocalsMarkers()\n"
     "\t\t\ttes3.messageBox(string.format(\"%s removed from the list of cleared cells\", cell.name or cell.id))\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "event.register(\"modConfigReady\", registerConfig)\n"
     "\n"
     "local function NewGame(e)\n",
     "event.register(\"modConfigReady\", registerConfig)\n"
     "\n"
     "local isNewGame = false\n"
     "\n"
     "local function NewGame(e)\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\tif e.newGame then\n"
     "\t\tlocal data = tes3.getPlayerRef().data\n"
     "\t\tdata.listMarkersOpenCells = {}\n"
     "\t\tdata.listClearedIntCells = {}\n"
     "\t\tdata.listClearedExtCells = {}\n",
     "\tif e and e.newGame then\n"
     "\t\tisNewGame = true\n"
     "\t\tlocal player = tes3.getPlayerRef() or tes3.player\n"
     "\t\tif player and player.data then\n"
     "\t\t\tlocal data = player.data\n"
     "\t\t\tdata.listMarkersOpenCells = {}\n"
     "\t\t\tdata.listClearedIntCells = {}\n"
     "\t\t\tdata.listClearedExtCells = {}\n"
     "\t\tend\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\tlocal data = tes3.getPlayerRef().data\n"
     "\tlocal player = tes3.getPlayerRef()\n",
     "\tlocal player = tes3.getPlayerRef() or tes3.player\n"
     "\tif not player or not player.data then return end\n"
     "\tlocal data = player.data\n"
     "\tif isNewGame then\n"
     "\t\tdata.listMarkersOpenCells = {}\n"
     "\t\tdata.listClearedIntCells = {}\n"
     "\t\tdata.listClearedExtCells = {}\n"
     "\t\tisNewGame = false\n"
     "\tend\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "local function cellChangedCallback(e)\n"
     "\tlocal data = tes3.getPlayerRef().data\n",
     "local function cellChangedCallback(e)\n"
     "\tif not (e and e.cell) then return end\n"
     "\tlocal player = tes3.getPlayerRef() or tes3.player\n"
     "\tif not player or not player.data then return end\n"
     "\tlocal data = player.data\n"
     "\tif not data.listMarkersOpenCells then data.listMarkersOpenCells = {} end\n"),
    ("KB36", 'Improved Global Map Markers', 'improved global map markers/main.lua',
     "\t\tif not data.listMarkersOpenCells[e.cell.editorName:lower()] then\n"
     "\t\t\tdata.listMarkersOpenCells[e.cell.editorName:lower()] = {cell = e.cell.id:lower(), pos = {x = e.cell.gridX, y = e.cell.gridY}}\n",
     "\t\tlocal editorName = e.cell.editorName and e.cell.editorName:lower()\n"
     "\t\tif editorName and not data.listMarkersOpenCells[editorName] then\n"
     "\t\t\tdata.listMarkersOpenCells[editorName] = {cell = (e.cell.id and e.cell.id:lower()) or editorName, pos = {x = e.cell.gridX, y = e.cell.gridY}}\n"),
    ("KB37", 'Lucid Disturbing Dreams', 'kdd/lucid-disturbing-dreams/main.lua',
     "        -- Last dream has finished, no reason to register this event\n"
     "        return\n",
     "        -- Last dream has finished, no reason to register this event\n"
     "        if event.isRegistered(tes3.event.journal, this.onJournalUpdated) then\n"
     "            event.unregister(tes3.event.journal, this.onJournalUpdated)\n"
     "        end\n"
     "        return\n"),
    ("KB37", 'Lucid Disturbing Dreams', 'kdd/lucid-disturbing-dreams/main.lua',
     "    this.registerJournalEvent()\n"
     "    for _, dream in ipairs(dreams) do\n",
     "    this.registerJournalEvent()\n"
     "    local index = tes3.getJournalIndex({ id = \"A1_Dreams\" }) or 0\n"
     "    for _, dream in ipairs(dreams) do\n"),
    ("KB37", 'Lucid Disturbing Dreams', 'kdd/lucid-disturbing-dreams/main.lua',
     "        local index = tes3.getJournalIndex({ id = \"A1_Dreams\" })\n"
     "        if index and index < dreamJournalIndices[dream] then\n"
     "            event.register(tes3.event.spellTick, this.onDreamSpellAdded, { filter = (dream):lower() })\n",
     "        local filter = (dream):lower()\n"
     "        if index < dreamJournalIndices[dream] then\n"
     "            if not event.isRegistered(tes3.event.spellTick, this.onDreamSpellAdded, { filter = filter }) then\n"
     "                event.register(tes3.event.spellTick, this.onDreamSpellAdded, { filter = filter })\n"
     "            end\n"
     "        else\n"
     "            if event.isRegistered(tes3.event.spellTick, this.onDreamSpellAdded, { filter = filter }) then\n"
     "                event.unregister(tes3.event.spellTick, this.onDreamSpellAdded, { filter = filter })\n"
     "            end\n"),
    ("KB38", 'Morrowind Achievement Collection', 'mac/playerdata.lua',
     "function pData.countBooks(e)\n"
     "    local myData = pData.getData()\n",
     "function pData.countBooks(e)\n"
     "    if not (e and e.book and e.book.id) then return end\n"
     "    local myData = pData.getData()\n"
     "    if not (myData and myData[\"BooksRead\"]) then return end\n"),
    ("KB38", 'Morrowind Achievement Collection', 'mac/playerdata.lua',
     "        myData[\"BooksCount\"] = myData[\"BooksCount\"] + 1\n",
     "        myData[\"BooksCount\"] = (myData[\"BooksCount\"] or 0) + 1\n"),
    ("KB38", 'Morrowind Achievement Collection', 'mac/playerdata.lua',
     "        mwse.log(\"Book read\" .. myData[\"BooksRead\"][e.book.id])\n",
     ""),
    ("KB38", 'Morrowind Achievement Collection', 'mac/playerdata.lua',
     "function pData.countKills(e)\n"
     "    local myData = pData.getData()\n",
     "function pData.countKills(e)\n"
     "    if not (e and e.reference and e.reference.baseObject and e.reference.baseObject.id) then return end\n"
     "    local myData = pData.getData()\n"),
    ("KB38", 'Morrowind Achievement Collection', 'mac/playerdata.lua',
     "    if (myData[\"Daedra\"][e.reference.baseObject.id:lower()] == false) then\n"
     "        myData[\"Daedra\"][e.reference.baseObject.id:lower()] = true\n"
     "        myData[\"DaedraCount\"] = myData[\"DaedraCount\"] + 1\n"
     "    elseif (string.find(e.reference.baseObject.id:lower(),\"dagoth\") and not myData[\"Dagoths\"][e.reference.baseObject.id:lower()]) then\n"
     "        myData[\"Dagoths\"][e.reference.baseObject.id:lower()] = true\n"
     "        myData[\"DagothsCount\"] = myData[\"DagothsCount\"] + 1\n",
     "    if not (myData and myData[\"Daedra\"] and myData[\"Dagoths\"]) then return end\n"
     "    local objId = e.reference.baseObject.id:lower()\n"
     "    if (myData[\"Daedra\"][objId] == false) then\n"
     "        myData[\"Daedra\"][objId] = true\n"
     "        myData[\"DaedraCount\"] = (myData[\"DaedraCount\"] or 0) + 1\n"
     "    elseif (string.find(objId, \"dagoth\") and not myData[\"Dagoths\"][objId]) then\n"
     "        myData[\"Dagoths\"][objId] = true\n"
     "        myData[\"DagothsCount\"] = (myData[\"DagothsCount\"] or 0) + 1\n"),
    ("KB38", 'Morrowind Achievement Collection', 'mac/playerdata.lua',
     "    --count every time a quest is finished\n"
     "    local myData = pData.getData()\n",
     "    --count every time a quest is finished\n"
     "    if not (e and e.info and e.info.isQuestFinished) then return end\n"
     "    local myData = pData.getData()\n"),
    ("KB38", 'Morrowind Achievement Collection', 'mac/playerdata.lua',
     "    if (e.info.isQuestFinished) then\n"
     "        myData[\"Quests\"] = myData[\"Quests\"] + 1\n"
     "    end\n",
     "    if not myData then return end\n"
     "    myData[\"Quests\"] = (myData[\"Quests\"] or 0) + 1\n"),
    ("KB38", 'Morrowind Achievement Collection', 'mac/playerdata.lua',
     "    if (tes3.mobilePlayer.inJail == false) then\n",
     "    if not myData then return end\n"
     "    if (tes3.mobilePlayer and tes3.mobilePlayer.inJail == false) then\n"),
    ("KB38", 'Morrowind Achievement Collection', 'mac/playerdata.lua',
     "    myData[\"Enchant\"] = myData[\"Enchant\"] + 1\n",
     "    if not myData then return end\n"
     "    myData[\"Enchant\"] = (myData[\"Enchant\"] or 0) + 1\n"),
    ("KB38", 'Morrowind Achievement Collection', 'mac/playerdata.lua',
     "function pData.countDwem(e)\n"
     "    local myData = pData.getData()\n",
     "function pData.countDwem(e)\n"
     "    if not (e and e.cell and e.cell.editorName) then return end\n"
     "    local myData = pData.getData()\n"),
    ("KB38", 'Morrowind Achievement Collection', 'mac/playerdata.lua',
     "    if (myData[\"DwemerRuins\"][e.cell.editorName:lower()] == false) then\n"
     "        mwse.log(e.cell.editorName:lower())\n"
     "        myData[\"DwemerRuins\"][e.cell.editorName:lower()] = true\n"
     "        myData[\"DwemerRuinsCount\"] = myData[\"DwemerRuinsCount\"] + 1\n",
     "    if not (myData and myData[\"DwemerRuins\"]) then return end\n"
     "    local cellName = e.cell.editorName:lower()\n"
     "    if (myData[\"DwemerRuins\"][cellName] == false) then\n"
     "        myData[\"DwemerRuins\"][cellName] = true\n"
     "        myData[\"DwemerRuinsCount\"] = (myData[\"DwemerRuinsCount\"] or 0) + 1\n"),
    ("KB39", 'Bardic Inspiration', 'mer/bardicinspiration/controllers/lutecontroller.lua',
     "    if sourceItemData and sourceItemData.data then\n"
     "        targetItemData.data = targetItemData.data or {}\n"
     "        for key, value in pairs(sourceItemData.data) do\n",
     "    if sourceItemData and sourceItemData.data and targetItemData and targetItemData.data then\n"
     "                for key, value in pairs(sourceItemData.data) do\n"),
    ("KB39", 'Bardic Inspiration', 'mer/bardicinspiration/controllers/lutecontroller.lua',
     "        addedItemData.data = addedItemData.data or {}\n"
     "        addedItemData.data[ORIGINAL_LUTE_KEY] = originalLuteData\n",
     "                addedItemData.data[ORIGINAL_LUTE_KEY] = originalLuteData\n"),
    ("KB40", 'Hidden Robe Armor', 'mer/hiddenrobearmor/main.lua',
     "    if tes3.player == e.reference then\n",
     "    if tes3.player and (e == nil or e.reference == nil or e.reference == tes3.player) then\n"),
    ("KB41", 'Just Drop It', 'mer/justdropit/main.lua',
     "local function onNPCDying(e)\n"
     "    if config.mcmConfig.enabled and config.mcmConfig.orientOnDeath then\n",
     "local function onNPCDying(e)\n"
     "    if not e or not e.reference then return end\n"
     "    if config.mcmConfig.enabled and config.mcmConfig.orientOnDeath then\n"),
    ("KB41", 'Just Drop It', 'mer/justdropit/main.lua',
     "            if not e.reference.data.justDropItOrientedOnDeath then\n",
     "            if not (e.reference.data and e.reference.data.justDropItOrientedOnDeath) then\n"),
    ("KB41", 'Just Drop It', 'mer/justdropit/main.lua',
     "                    orient.orientRef(e.reference, result)\n"
     "                    e.reference.data.justDropItOrientedOnDeath = true\n",
     "                    orient.orientRef(e.reference, result)\n"
     "                    if e.reference.supportsLuaData then\n"
     "                        e.reference.data.justDropItOrientedOnDeath = true\n"
     "                    end\n"),
    ("KB41", 'Just Drop It', 'mer/justdropit/main.lua',
     "local function onRefResurrected(e)\n"
     "    if validObjectTypes[e.reference.baseObject.objectType] then\n",
     "local function onRefResurrected(e)\n"
     "    if not e or not e.reference or not e.reference.baseObject then return end\n"
     "    if validObjectTypes[e.reference.baseObject.objectType] then\n"),
    ("KB41", 'Just Drop It', 'mer/justdropit/main.lua',
     "        orient.resetXYOrientation(e.reference)\n"
     "        e.reference.data.justDropItOrientedOnDeath = nil\n",
     "        orient.resetXYOrientation(e.reference)\n"
     "        if e.reference.data then\n"
     "            e.reference.data.justDropItOrientedOnDeath = nil\n"
     "        end\n"),
    ("KB42", 'MUSE 2.02', 'music/depthsnair.lua',
     "\n"
     "    if(player.mobile.isJumping == false) then\n",
     "    if player and player.mobile and (player.mobile.isJumping == false) then\n"),
    ("KB42", 'MUSE 2.02', 'music/depthsnair.lua',
     "\n"
     "    if(cell.isInterior == true) then\n",
     "    if not player or not cell or cell.isInterior == true then\n"),
    ("KB42", 'MUSE 2.02', 'music/main.lua',
     "local function OnCellEnter()\n"
     "    local player = tes3.player.mobile\n",
     "local function OnCellEnter()\n"
     "    if not tes3.player or not tes3.player.mobile then return end\n"
     "    local player = tes3.player.mobile\n"),
    ("KB42", 'MUSE 2.02', 'music/muse.lua',
     "function MUSE.SetMusicDir(path, musicType)\n"
     "    musicPathCurrent = path .. \"/\"\n"
     "\n",
     "function MUSE.SetMusicDir(path, musicType)\n"
     "    -- local fix: only switch to a folder that has music in it. MUSE used to switch first and check\n"
     "    -- after, so an empty or missing folder (general/underwater/) kept the old playlist under the new\n"
     "    -- path and every track came up \"Music file not found\".\n"
     "    local rootBefore = musicPathRootCurrent\n"),
    ("KB42", 'MUSE 2.02', 'music/muse.lua',
     "        musicPathRootCurrent = musicPathMain\n"
     "    end\n"
     "\n"
     "    ------------\n",
     "        musicPathRootCurrent = musicPathMain\n"
     "    end\n"
     "    if(MUSE.CheckMusicDir(path) == false) then\n"
     "        musicPathRootCurrent = rootBefore\n"
     "        return\n"
     "    end\n"
     "    musicPathCurrent = path .. \"/\"\n"
     "\n"
     "    ------------\n"),
    ("KB43", 'Memento Mori (Ossuaries of the Ghostfence)', 'ossuaries of the ghostfence/calm ghosties.lua',
     "event.register(\"initialized\", function(e)\n"
     "\tevent.register(\"simulate\", skellyShallNotPass)\n",
     "local calmTimer = nil\n"
     "\n"
     "local function onLoaded()\n"
     "\tif calmTimer then\n"
     "\t\tcalmTimer:cancel()\n"
     "\tend\n"
     "\tcalmTimer = timer.start { iterations = -1, duration = 1, persist = false, callback = calmGhosties }\n"
     "end\n"
     "\n"
     "event.register(\"initialized\", function(e)\n"
     "\tif not event.isRegistered(\"simulate\", skellyShallNotPass) then\n"
     "\t\tevent.register(\"simulate\", skellyShallNotPass)\n"
     "\tend\n"),
    ("KB43", 'Memento Mori (Ossuaries of the Ghostfence)', 'ossuaries of the ghostfence/calm ghosties.lua',
     "\tevent.register(\"loaded\", function()\n"
     "\t\ttimer.start { iterations = -1, duration = 1, callback = calmGhosties }\n"
     "\tend)\n",
     "\tif not event.isRegistered(\"loaded\", onLoaded) then\n"
     "\t\tevent.register(\"loaded\", onLoaded)\n"
     "\tend\n"),
    ("KB43", 'Memento Mori (Ossuaries of the Ghostfence)', 'ossuaries of the ghostfence/lights out.lua',
     "\tif tes3.player.cell.id ~= \"Ghostfence, Western Catacombs\" then\n",
     "\tif not tes3.player or not tes3.player.cell or tes3.player.cell.id ~= \"Ghostfence, Western Catacombs\" then\n"),
    ("KB43", 'Memento Mori (Ossuaries of the Ghostfence)', 'ossuaries of the ghostfence/lights out.lua',
     "\tif tes3.getReference(\"GG_sc_invisibility_west\").disabled then\n",
     "\tlocal triggerRef = tes3.getReference(\"GG_sc_invisibility_west\")\n"
     "\tif triggerRef and triggerRef.disabled then\n"),
    ("KB43", 'Memento Mori (Ossuaries of the Ghostfence)', 'ossuaries of the ghostfence/lights out.lua',
     "\t\tif equippedLight then\n",
     "\t\tif equippedLight and tes3.player.mobile then\n"),
    ("KB44", 'The Achievement Framework', 'sb_achievements/main.lua',
     "local popupAchievements = {}\n"
     "\n"
     "--- @param e enterFrameEventData\n",
     "local popupAchievements = {}\n"
     "\n"
     "local function getConditionProgress(achievement)\n"
     "    if not achievement or achievement.conditionType == 1 then\n"
     "        return \"\"\n"
     "    end\n"
     "    local cur = achievement.progress and achievement.progress()\n"
     "    local max = achievement.progressMax and achievement.progressMax()\n"
     "    if not cur or not max then\n"
     "        return \"\"\n"
     "    end\n"
     "    if achievement.conditionType == 2 then\n"
     "        return \" (\" .. tostring(cur) .. \"/\" .. tostring(max) .. \")\"\n"
     "    elseif achievement.conditionType == 3 and max > 0 then\n"
     "        return \" (\" .. tostring(math.min(100, math.round((cur / max) * 100, 1))) .. \"%)\"\n"
     "    end\n"
     "    return \"\"\n"
     "end\n"
     "\n"
     "--- @param e enterFrameEventData\n"),
    ("KB44", 'The Achievement Framework', 'sb_achievements/main.lua',
     "                local conditionCheck = (achievement.conditionType == 1 and (achievement.condition() == true)) or ((achievement.conditionType == 2 or achievement.conditionType == 3) and achievement.progress() >= achievement.progressMax())\n",
     "                local conditionCheck = false\n"
     "                if achievement.conditionType == 1 then\n"
     "                    conditionCheck = (achievement.condition and achievement.condition() == true)\n"
     "                elseif achievement.conditionType == 2 or achievement.conditionType == 3 then\n"
     "                    local cur = achievement.progress and achievement.progress()\n"
     "                    local max = achievement.progressMax and achievement.progressMax()\n"
     "                    if cur and max then\n"
     "                        conditionCheck = (cur >= max)\n"
     "                    end\n"
     "                end\n"),
    ("KB44", 'The Achievement Framework', 'sb_achievements/main.lua',
     "                        local conditionProgress = (achievement.conditionType == 1 and \"\") or (achievement.conditionType == 2 and \" (\" .. achievement.progress() .. \"/\" .. achievement.progressMax() .. \")\") or (achievement.conditionType == 3 and \" (\" .. math.min(100, math.round((achievement.progress() / achievement.progressMax()) * 100, 1)) .. \"%)\")\n",
     "                        local conditionProgress = getConditionProgress(achievement)\n"),
    ("KB44", 'The Achievement Framework', 'sb_achievements/main.lua',
     "            local hiddentCount = interop.countHiddenAchievements(category, mcm.config.showHiddenAchievements)\n"
     "            if (hiddentCount > 0) then\n",
     "            local hiddentCount = interop.countHiddenAchievements(category, mcm.config.showHiddenAchievements)\n"
     "            local hiddenGroup = menuAchievements[category] and menuAchievements[category][256]\n"
     "            if (hiddentCount > 0) then\n"),
    ("KB44", 'The Achievement Framework', 'sb_achievements/main.lua',
     "                menuAchievements[category][256].element.visible = true\n"
     "                menuAchievements[category][256].desc.text = tostring(hiddentCount) .. i18n(\"menuAchiev.remaining\")\n"
     "                menuAchievements[category][256].icon.imageScaleX = mcm.config.iconSize\n"
     "                menuAchievements[category][256].icon.imageScaleY = mcm.config.iconSize\n"
     "                menuAchievements[category][256].subIcon.imageScaleX = mcm.config.iconSize\n"
     "                menuAchievements[category][256].subIcon.imageScaleY = mcm.config.iconSize\n"
     "                menuAchievements[category][256].title.parent.borderLeft = 4\n"
     "                menuAchievements[category][256].desc.borderTop = 4\n",
     "                if hiddenGroup then\n"
     "                    hiddenGroup.element.visible = true\n"
     "                    hiddenGroup.desc.text = tostring(hiddentCount) .. i18n(\"menuAchiev.remaining\")\n"
     "                    hiddenGroup.icon.imageScaleX = mcm.config.iconSize\n"
     "                    hiddenGroup.icon.imageScaleY = mcm.config.iconSize\n"
     "                    hiddenGroup.subIcon.imageScaleX = mcm.config.iconSize\n"
     "                    hiddenGroup.subIcon.imageScaleY = mcm.config.iconSize\n"
     "                    hiddenGroup.title.parent.borderLeft = 4\n"
     "                    hiddenGroup.desc.borderTop = 4\n"
     "                end\n"),
    ("KB44", 'The Achievement Framework', 'sb_achievements/main.lua',
     "                menuAchievements[category][256].element.visible = false\n",
     "                if hiddenGroup then\n"
     "                    hiddenGroup.element.visible = false\n"
     "                end\n"),
    ("KB44", 'The Achievement Framework', 'sb_achievements/main.lua',
     "                end\n"
     "                local conditionProgress = (achievement.conditionType == 1 and \"\") or (achievement.conditionType == 2 and \" (\" .. achievement.progress() .. \"/\" .. achievement.progressMax() .. \")\") or (achievement.conditionType == 3 and \" (\" .. math.min(100, math.round((achievement.progress() / achievement.progressMax()) * 100, 1)) .. \"%)\")\n",
     "                end\n"
     "                local conditionProgress = getConditionProgress(achievement)\n"),
    ("KB44", 'The Achievement Framework', 'sb_achievements/main.lua',
     "        for category, _ in ipairs(menuCategories) do\n"
     "            menuAchievements[category][256] = ui.createHiddenGroup(menu[category], category)\n",
     "        for category, _ in ipairs(menuCategories) do\n"
     "            if menu[category] then\n"
     "                menuAchievements[category] = menuAchievements[category] or {}\n"
     "                menuAchievements[category][256] = ui.createHiddenGroup(menu[category], category)\n"
     "            end\n"),
    ("KB44", 'The Achievement Framework', 'sb_achievements/main.lua',
     "            end\n"
     "            local conditionProgress = (achievement.conditionType == 1 and \"\") or (achievement.conditionType == 2 and \" (\" .. achievement.progress() .. \"/\" .. achievement.progressMax() .. \")\") or (achievement.conditionType == 3 and \" (\" .. math.min(100, math.round((achievement.progress() / achievement.progressMax()) * 100, 1)) .. \"%)\")\n",
     "            end\n"
     "            local conditionProgress = getConditionProgress(achievement)\n"),
    ("KB44", 'The Achievement Framework', 'sb_achievements/main.lua',
     "    for category, _ in ipairs(menuCategories) do\n"
     "        menuAchievements[category][256] = ui.createHiddenGroup(menu[category], category)\n",
     "    for category, _ in ipairs(menuCategories) do\n"
     "        if menu[category] then\n"
     "            menuAchievements[category] = menuAchievements[category] or {}\n"
     "            menuAchievements[category][256] = ui.createHiddenGroup(menu[category], category)\n"
     "        end\n"),
    ("KB45", 'Onion - Layered Accessories', 'sb_onion/main.lua',
     "local function onEquip(e)\n"
     "    -- must be a valid wearable\n",
     "local function onEquip(e)\n"
     "    if not e or not e.item or not e.reference or not e.reference.object or not e.reference.object.race then\n"
     "        return\n"
     "    end\n"
     "    -- must be a valid wearable\n"),
    ("KB45", 'Onion - Layered Accessories', 'sb_onion/main.lua',
     "    if ((wearable and wearable.raceSub[e.reference.object.race.name] == \"\") or (layer and layer.raceSub[e.reference.object.race.name] == \"\")) then\n",
     "    local raceName = e.reference.object.race.name\n"
     "    if ((wearable and wearable.raceSub[raceName] == \"\") or (layer and layer.raceSub[raceName] == \"\")) then\n"),
    ("KB45", 'Onion - Layered Accessories', 'sb_onion/main.lua',
     "local function onEquipped(e)\n"
     "    -- must be a valid wearable or layer\n",
     "local function onEquipped(e)\n"
     "    if not e or not e.item or not e.reference or not e.reference.object or not e.reference.object.race then\n"
     "        return\n"
     "    end\n"
     "    -- must be a valid wearable or layer\n"),
    ("KB45", 'Onion - Layered Accessories', 'sb_onion/main.lua',
     "    for _, bodyPart in ipairs(wearable and wearable.cull or layer.cull) do\n"
     "        e.reference.data.onionCulls = e.reference.data.onionCulls or {}\n"
     "        e.reference.data.onionCulls[interop.bodyParts[bodyPart]] = e.reference.data.onionCulls[interop.bodyParts[bodyPart]] or {}\n"
     "        local alreadyCulled = false\n"
     "        for _, node in ipairs(e.reference.data.onionCulls[interop.bodyParts[bodyPart]]) do\n"
     "            if (node == (wearable and wearable.id or layer.id)) then\n"
     "                alreadyCulled = true\n"
     "                break\n",
     "    if e.reference.supportsLuaData then\n"
     "        for _, bodyPart in ipairs(wearable and wearable.cull or layer.cull) do\n"
     "            e.reference.data.onionCulls = e.reference.data.onionCulls or {}\n"
     "            e.reference.data.onionCulls[interop.bodyParts[bodyPart]] = e.reference.data.onionCulls[interop.bodyParts[bodyPart]] or {}\n"
     "            local alreadyCulled = false\n"
     "            for _, node in ipairs(e.reference.data.onionCulls[interop.bodyParts[bodyPart]]) do\n"
     "                if (node == (wearable and wearable.id or layer.id)) then\n"
     "                    alreadyCulled = true\n"
     "                    break\n"
     "                end\n"),
    ("KB45", 'Onion - Layered Accessories', 'sb_onion/main.lua',
     "        end\n"
     "        if (alreadyCulled == false) then\n"
     "            table.insert(e.reference.data.onionCulls[interop.bodyParts[bodyPart]], wearable and wearable.id or layer.id)\n",
     "            if (alreadyCulled == false) then\n"
     "                table.insert(e.reference.data.onionCulls[interop.bodyParts[bodyPart]], wearable and wearable.id or layer.id)\n"
     "            end\n"),
    ("KB45", 'Onion - Layered Accessories', 'sb_onion/main.lua',
     "    for _, bodyPart in ipairs(wearable and wearable.cull or layer.cull) do\n"
     "        if (e.reference.data.onionCulls and e.reference.data.onionCulls[interop.bodyParts[bodyPart]]) then\n"
     "            table.removevalue(e.reference.data.onionCulls[interop.bodyParts[bodyPart]], wearable and wearable.id or layer.id)\n"
     "        end\n"
     "        if (#e.reference.data.onionCulls[interop.bodyParts[bodyPart]] == 0) then\n"
     "            e.reference.data.onionCulls[interop.bodyParts[bodyPart]] = nil\n",
     "    if e.reference.data and e.reference.data.onionCulls then\n"
     "        for _, bodyPart in ipairs(wearable and wearable.cull or layer.cull) do\n"
     "            local bpNode = interop.bodyParts[bodyPart]\n"
     "            if bpNode and e.reference.data.onionCulls[bpNode] then\n"
     "                table.removevalue(e.reference.data.onionCulls[bpNode], wearable and wearable.id or layer.id)\n"
     "                if #e.reference.data.onionCulls[bpNode] == 0 then\n"
     "                    e.reference.data.onionCulls[bpNode] = nil\n"
     "                end\n"
     "            end\n"),
    ("KB45", 'Onion - Layered Accessories', 'sb_onion/main.lua',
     "    if (e.reference.data.onionCulls) then\n",
     "    if (e.reference.data and e.reference.data.onionCulls) then\n"),
    ("KB46", 'Small QoL Improvements', 'spammer/qol improvements/main.lua',
     "    if not cf.scroll then return end\n"
     "    local scroll = e.item\n",
     "    if not cf.scroll then return end\n"
     "    if e.reference ~= tes3.player then return end\n"
     "    local scroll = e.item\n"),
    ("KB46", 'Small QoL Improvements', 'spammer/qol improvements/main.lua',
     "        tes3.mobilePlayer:equipMagic({\n"
     "            source = e.item, itemData = e.itemData, equipItem = true\n"
     "        })\n",
     "        if not tes3.player or not tes3.mobilePlayer then return end\n"
     "        local inv = tes3.player.object and tes3.player.object.inventory\n"
     "        if not inv or not inv:contains(e.item) then return end\n"
     "        pcall(function()\n"
     "            tes3.mobilePlayer:equipMagic({\n"
     "                source = e.item, itemData = e.itemData, equipItem = true\n"
     "            })\n"
     "        end)\n"),
    ("KB46", 'Small QoL Improvements', 'spammer/qol improvements/main.lua',
     "    if not cf.scroll then return end\n"
     "    if (e.item and e.item.objectType == tes3.objectType.weapon) then return end\n",
     "    if not cf.scroll then return end\n"
     "    if e.reference ~= tes3.player then return end\n"
     "    if (e.item and e.item.objectType == tes3.objectType.weapon) then return end\n"),
    ("KB46", 'Small QoL Improvements', 'spammer/qol improvements/main.lua',
     "        timer.frame.delayOneFrame(function() tes3.mobilePlayer:equipMagic({ source = e.item, itemData = e.itemData, equipItem = false }) end)\n",
     "        local item = e.item\n"
     "        local itemData = e.itemData\n"
     "        timer.frame.delayOneFrame(function()\n"
     "            if not tes3.player or not tes3.mobilePlayer then return end\n"
     "            local inv = tes3.player.object and tes3.player.object.inventory\n"
     "            if not inv or not inv:contains(item) then return end\n"
     "            pcall(function()\n"
     "                tes3.mobilePlayer:equipMagic({\n"
     "                    source = item,\n"
     "                    itemData = itemData,\n"
     "                    equipItem = (itemData == nil),\n"
     "                })\n"
     "            end)\n"
     "        end)\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonus/conditions.lua',
     "local appliedCond = setmetatable({}, { __mode = \"k\" }) -- appliedCond[ref] = { [subSpellId] = true }\n"
     "\n"
     "local function setHasConditionals(set)\n",
     "local appliedCond = setmetatable({}, { __mode = \"k\" }) -- appliedCond[ref] = { [subSpellId] = true }\n"
     "\n"
     "local function isRefAlive(ref)\n"
     "    if not ref then return false end\n"
     "    local ok, res = pcall(function()\n"
     "        return not ref.deleted and ref.object ~= nil\n"
     "    end)\n"
     "    return ok and res\n"
     "end\n"
     "\n"
     "local function isActorAlive(ref)\n"
     "    if not ref then return false end\n"
     "    local ok, res = pcall(function()\n"
     "        return not ref.deleted and ref.object ~= nil and ref.mobile ~= nil\n"
     "    end)\n"
     "    return ok and res\n"
     "end\n"
     "\n"
     "local function setHasConditionals(set)\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonus/conditions.lua',
     "    if not (ref and ref.object) then return end\n",
     "    if not isRefAlive(ref) then return end\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonus/conditions.lua',
     "    if not settings.conditionalBonuses then return end\n"
     "    local set = e.set\n",
     "    if not settings.conditionalBonuses then return end\n"
     "    if not isRefAlive(e.reference) then return end\n"
     "    local set = e.set\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonus/conditions.lua',
     "        if ref and ref.object and ref.mobile then\n",
     "        if isActorAlive(ref) then\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonus/conditions.lua',
     "                if set then reconcile(ref, set, tier or nil) end\n"
     "            end\n"
     "        end\n",
     "                if set then reconcile(ref, set, tier or nil) end\n"
     "            end\n"
     "        else\n"
     "            watch[ref] = nil\n"
     "        end\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonus/conditions.lua',
     "        if ref and ref.object then\n",
     "        if isRefAlive(ref) then\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonus/conditions.lua',
     "    if not (e and e.reference and e.id) then return end\n",
     "    if not (e and isRefAlive(e.reference) and e.id) then return end\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonus/main.lua',
     "local function enchantedBaseId(itemData)\n"
     "    local d = itemData and itemData.data\n"
     "    local b = d and d.ncceEnchantedFrom\n",
     "local function enchantedBaseId(obj, itemData)\n"
     "    -- Fast exit: only runtime-minted player-enchanted items (obj.sourceMod == nil)\n"
     "    -- can carry Consistent Enchanting metadata. Static items defined in ESM/ESP plugins\n"
     "    -- never have ncceEnchantedFrom; accessing .data on uninitialized itemData structs\n"
     "    -- during equip calls crashes MWSE's DataHandler.\n"
     "    if not obj or not obj.enchantment or obj.sourceMod ~= nil then\n"
     "        return nil\n"
     "    end\n"
     "    local id = obj.id and obj.id:lower()\n"
     "    if id and config.setLinks[id] then\n"
     "        return nil\n"
     "    end\n"
     "    if not itemData then\n"
     "        return nil\n"
     "    end\n"
     "    local ok, d = pcall(function() return itemData.data end)\n"
     "    if not ok or type(d) ~= \"table\" then\n"
     "        return nil\n"
     "    end\n"
     "    local b = d.ncceEnchantedFrom\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonus/main.lua',
     "        if obj and ALLOWED_TYPES[obj.objectType] then\n"
     "            local baseId = enchantedBaseId(stackItemData(stack))\n"
     "            if objInSet(obj, setName, baseId) then count = count + 1 end\n",
     "        if obj and ALLOWED_TYPES[obj.objectType] then\n"
     "            local baseId = enchantedBaseId(obj, stackItemData(stack))\n"
     "            if objInSet(obj, setName, baseId) then count = count + 1 end\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonus/main.lua',
     "    if not obj then return end\n"
     "    local names = setsForObject(obj, enchantedBaseId(e.itemData))\n",
     "    if not obj then return end\n"
     "    local names = setsForObject(obj, enchantedBaseId(obj, e.itemData))\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonus/main.lua',
     "    if not names then return end\n"
     "    if e.reference ~= tes3.player and not settings.npcBonuses then return end\n",
     "    if not names then return end\n"
     "    if not e.reference or not e.reference:isValid() then return end\n"
     "    if e.reference ~= tes3.player and not settings.npcBonuses then return end\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonus/main.lua',
     "        if obj and ALLOWED_TYPES[obj.objectType] then\n"
     "            local baseId = enchantedBaseId(stackItemData(stack))\n"
     "            local names = setsForObject(obj, baseId)\n",
     "        if obj and ALLOWED_TYPES[obj.objectType] then\n"
     "            local baseId = enchantedBaseId(obj, stackItemData(stack))\n"
     "            local names = setsForObject(obj, baseId)\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonus/main.lua',
     "    if not obj or not ALLOWED_TYPES[obj.objectType] then return end\n"
     "    local names = setsForObject(obj, enchantedBaseId(e.itemData))\n",
     "    if not obj or not ALLOWED_TYPES[obj.objectType] then return end\n"
     "    local names = setsForObject(obj, enchantedBaseId(obj, e.itemData))\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonusflags/main.lua',
     "local function push(id, value)\n"
     "    if last[id] == value then return end -- only on change (avoids re-eval spam)\n",
     "local function push(id, value)\n"
     "    if not tes3.player then return end\n"
     "    if last[id] == value then return end -- only on change (avoids re-eval spam)\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonusflags/main.lua',
     "local function poll()\n"
     "    local mp = tes3.mobilePlayer\n",
     "local function poll()\n"
     "    if tes3.menuMode() then return end\n"
     "    local mp = tes3.mobilePlayer\n"),
    ("KB47", 'MWSE Set Bonus', 'static/setbonusflags/main.lua',
     "    if not mp then return end\n",
     "    if not mp or not tes3.player then return end\n"),
    ("KB48", 'MWSE Lanterns', 'syanide/magiclanternlights/main.lua',
     "local function checkLantern(npcRef)\n"
     "    local ok, LanternItem = pcall(tes3.getEquippedItem, {\n",
     "local function checkLantern(npcRef)\n"
     "    if not npcRef or not npcRef.object or npcRef.object.objectType ~= tes3.objectType.npc then\n"
     "        return\n"
     "    end\n"
     "\n"
     "    local ok, LanternItem = pcall(tes3.getEquippedItem, {\n"),
    ("KB49", 'Animated Dialogue', 'tauer/animated-dialogue/services/actors/actorposeblender.lua',
     "        local index              = self.count + 1\n"
     "        self.count               = index\n"
     "        self.nodes[index]        = node --[[@as niNode]]\n"
     "        self.rotations[index]    = node.rotation:toQuaternion()\n"
     "        self.translations[index] = node.translation:copy()\n",
     "        local name = node.name\n"
     "        -- Never blend root transform bones (Bip01, Bip01 NonAccum, Bip01 Footsteps).\n"
     "        -- Blending root bones on dialogue exit causes a 180-degree flip desync with the engine's facing.\n"
     "        if name ~= \"Bip01\" and name ~= \"Bip01 NonAccum\" and name ~= \"Bip01 Footsteps\" and name ~= \"Root Bone\" then\n"
     "            local index              = self.count + 1\n"
     "            self.count               = index\n"
     "            self.nodes[index]        = node --[[@as niNode]]\n"
     "            self.rotations[index]    = node.rotation:toQuaternion()\n"
     "            self.translations[index] = node.translation:copy()\n"
     "        end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/common.lua',
     "    local module = info.short_src:match(\"^.+\\\\(.+).lua$\")\n"
     "    local prepend = (\"[%s.%s.%s:%s]:\"):format(metadata.package.name, metadata.package.version, module, info.currentline)\n",
     "    local module = (info and info.short_src and info.short_src:match(\"^.+\\\\(.+).lua$\")) or \"unknown\"\n"
     "    local line = (info and info.currentline) or 0\n"
     "    local pkgName = (metadata and metadata.package and metadata.package.name) or \"Watch the Skies\"\n"
     "    local pkgVer = (metadata and metadata.package and metadata.package.version) or \"\"\n"
     "    local prepend = (\"[%s.%s.%s:%s]:\"):format(pkgName, pkgVer, module, line)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/common.lua',
     "    mwse.log(aligned .. \" -- \" .. string.format(\"%s\", message))\n",
     "    mwse.log(aligned .. \" -- \" .. tostring(message or \"\"))\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\ttarget._registeredEvents = {}\n",
     "\tif not (target and list) then return end\n"
     "\ttarget._registeredEvents = target._registeredEvents or {}\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\t\tevent.register(info.event, info.func, info.opts)\n"
     "\t\ttable.insert(target._registeredEvents, info)\n",
     "\t\tif info and info.event and info.func then\n"
     "\t\t\tevent.register(info.event, info.func, info.opts)\n"
     "\t\t\ttable.insert(target._registeredEvents, info)\n"
     "\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\tif not target._registeredEvents then return end\n",
     "\tif not (target and target._registeredEvents) then return end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\tfor _, info in ipairs(target._registeredEvents) do\n"
     "\t\tevent.unregister(info.event, info.func, info.opts)\n",
     "\tfor _, info in ipairs(target._registeredEvents) do\n"
     "\t\tif info and info.event and info.func then\n"
     "\t\t\tevent.unregister(info.event, info.func, info.opts)\n"
     "\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\t\tdebugLog(\"Stopping particleMesh service...\")\n"
     "\t\tunregisterEvents(events.services.particleMesh)\n",
     "\t\tdebugLog(\"Stopping particleMesh service...\")\n"
     "\t\tlocal particleMesh = require(\"tew.Watch the Skies.services.particleMesh\")\n"
     "\t\tunregisterEvents(events.services.particleMesh)\n"
     "\t\tif particleMesh.stop then\n"
     "\t\t\tparticleMesh.stop()\n"
     "\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\t\tunregisterEvents(events.services.particleAmount)\n"
     "\t\tsvc.restoreDefaults()\n",
     "\t\tunregisterEvents(events.services.particleAmount)\n"
     "\t\tif svc.stopTimer then\n"
     "\t\t\tsvc.stopTimer()\n"
     "\t\tend\n"
     "\t\tsvc.restoreDefaults()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\t\tunregisterEvents(events.services.skyTexture)\n"
     "\t\tskyTexture.restoreDefaults()\n",
     "\t\tunregisterEvents(events.services.skyTexture)\n"
     "\t\tif skyTexture.stopTimer then\n"
     "\t\t\tskyTexture.stopTimer()\n"
     "\t\tend\n"
     "\t\tskyTexture.restoreDefaults()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\t\tlocal config = require(\"tew.Watch the Skies.config\")\n"
     "\t\tif not config.skyTexture then\n"
     "\t\t\tdebugLog(\"variableRain service skipped: skyTexture setting is disabled\")\n",
     "\t\tlocal config = require(\"tew.Watch the Skies.config\")\n"
     "\t\tif not config or not config.skyTexture then\n"
     "\t\t\tdebugLog(\"variableRain service skipped: skyTexture setting is disabled\")\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\t\tlocal config = require(\"tew.Watch the Skies.config\")\n"
     "\t\tif not config.skyTexture then\n"
     "\t\t\treturn\n",
     "\t\tlocal config = require(\"tew.Watch the Skies.config\")\n"
     "\t\tif not config or not config.skyTexture then\n"
     "\t\t\treturn\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\t\tunregisterEvents(events.services.dynamicWeatherChanges)\n"
     "\t\tsvc.restoreDefaults()\n",
     "\t\tunregisterEvents(events.services.dynamicWeatherChanges)\n"
     "\t\tif svc.stopTimer then\n"
     "\t\t\tsvc.stopTimer()\n"
     "\t\tend\n"
     "\t\tsvc.restoreDefaults()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\t\tunregisterEvents(events.services.cloudSpeed)\n"
     "\t\tsvc.restoreDefaults()\n",
     "\t\tunregisterEvents(events.services.cloudSpeed)\n"
     "\t\tif svc.stopTimer then\n"
     "\t\t\tsvc.stopTimer()\n"
     "\t\tend\n"
     "\t\tsvc.restoreDefaults()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\t\tunregisterEvents(events.services.seasonalWeather)\n"
     "\t\tsvc.restoreDefaults()\n",
     "\t\tunregisterEvents(events.services.seasonalWeather)\n"
     "\t\tif svc.stopTimer then\n"
     "\t\t\tsvc.stopTimer()\n"
     "\t\tend\n"
     "\t\tsvc.restoreDefaults()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\t\tunregisterEvents(events.services.seasonalDaytime)\n"
     "\t\tsvc.restoreDefaults()\n",
     "\t\tunregisterEvents(events.services.seasonalDaytime)\n"
     "\t\tif svc.stopTimer then\n"
     "\t\t\tsvc.stopTimer()\n"
     "\t\tend\n"
     "\t\tsvc.restoreDefaults()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/components/events.lua',
     "\t\tdebugLog(\"Stopping interiorTransitions service...\")\n"
     "\t\tunregisterEvents(events.services.interiorTransitions)\n",
     "\t\tdebugLog(\"Stopping interiorTransitions service...\")\n"
     "\t\tlocal svc = require(\"tew.Watch the Skies.services.interiorTransitions\")\n"
     "\t\tunregisterEvents(events.services.interiorTransitions)\n"
     "\t\tif svc.stopTimer then\n"
     "\t\t\tsvc.stopTimer()\n"
     "\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/main.lua',
     "\tif not (metadata) then\n",
     "\tif not (metadata and metadata.package and metadata.package.version) then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/main.lua',
     "\tif config.modEnabled then\n",
     "\tif config and config.modEnabled and events and events.services then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/main.lua',
     "\t\t\tif config[serviceName] then\n",
     "\t\t\tif config[serviceName] and service and type(service.init) == \"function\" then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/mcm.lua',
     "    name = metadata.package.name,\n",
     "    name = (metadata and metadata.package and metadata.package.name) or \"Watch the Skies\",\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/mcm.lua',
     "    mwse.saveConfig(configPath, config)\n"
     "\n"
     "    -- Handle overall mod disable\n",
     "    mwse.saveConfig(configPath, config)\n"
     "\n"
     "    if not events or not events.services then return end\n"
     "\n"
     "    -- Handle overall mod disable\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/mcm.lua',
     "        for _, service in pairs(events.services) do\n"
     "            service.stop()\n",
     "        for _, service in pairs(events.services) do\n"
     "            if service and type(service.stop) == \"function\" then\n"
     "                service.stop()\n"
     "            end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/mcm.lua',
     "            if config[serviceName] then\n",
     "            if config[serviceName] and service and type(service.init) == \"function\" then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/mcm.lua',
     "            if newEnabled then\n",
     "            if newEnabled and service and type(service.init) == \"function\" then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/mcm.lua',
     "                service.init()\n"
     "            else\n",
     "                service.init()\n"
     "            elseif not newEnabled and service and type(service.stop) == \"function\" then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/util.lua',
     "\tlocal WtC = tes3.worldController.weatherController\n",
     "\tlocal wc = tes3.worldController\n"
     "\tlocal WtC = wc and wc.weatherController\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/util.lua',
     "\t-- if WtC.nextWeather then\n"
     "\t-- \tlocal t = WtC.transitionScalar\n"
     "\t-- \tWtC:switchTransition(WtC.nextWeather.index)\n"
     "\t-- \tWtC.transitionScalar = t\n"
     "\t-- else\n"
     "\t-- \tWtC:switchImmediate(WtC.currentWeather.index)\n"
     "\t-- end\n"
     "\n"
     "\tif tes3.player then\n",
     "\tif tes3.player and WtC.updateVisuals then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/util.lua',
     "\tlocal seasonalChances = require(\"tew.Watch the Skies.components.seasonalChances\")\n"
     "\n",
     "\tlocal seasonalChances = require(\"tew.Watch the Skies.components.seasonalChances\")\n"
     "\tif not (tes3.dataHandler and tes3.dataHandler.nonDynamicData and tes3.dataHandler.nonDynamicData.regions) then\n"
     "\t\treturn\n"
     "\tend\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/util.lua',
     "\t\tif not seasonalChances[region.id] then\n",
     "\t\tif region and region.id and not seasonalChances[region.id] then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/util.lua',
     "\t\t\t\tregion.weatherChanceClear,\n"
     "\t\t\t\tregion.weatherChanceCloudy,\n"
     "\t\t\t\tregion.weatherChanceFoggy,\n"
     "\t\t\t\tregion.weatherChanceOvercast,\n"
     "\t\t\t\tregion.weatherChanceRain,\n"
     "\t\t\t\tregion.weatherChanceThunder,\n"
     "\t\t\t\tregion.weatherChanceAsh,\n"
     "\t\t\t\tregion.weatherChanceBlight,\n"
     "\t\t\t\tregion.weatherChanceSnow,\n"
     "\t\t\t\tregion.weatherChanceBlizzard\n",
     "\t\t\t\tregion.weatherChanceClear or 0,\n"
     "\t\t\t\tregion.weatherChanceCloudy or 0,\n"
     "\t\t\t\tregion.weatherChanceFoggy or 0,\n"
     "\t\t\t\tregion.weatherChanceOvercast or 0,\n"
     "\t\t\t\tregion.weatherChanceRain or 0,\n"
     "\t\t\t\tregion.weatherChanceThunder or 0,\n"
     "\t\t\t\tregion.weatherChanceAsh or 0,\n"
     "\t\t\t\tregion.weatherChanceBlight or 0,\n"
     "\t\t\t\tregion.weatherChanceSnow or 0,\n"
     "\t\t\t\tregion.weatherChanceBlizzard or 0\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/util.lua',
     "\t\t\t\tregion.name,\n",
     "\t\t\t\tregion.name or region.id,\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/util.lua',
     "function util.matryoshka(fun)\n"
     "\tfun()\n",
     "function util.matryoshka(fun)\n"
     "\tif type(fun) ~= \"function\" then return end\n"
     "\tfun()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/util.lua',
     "\t\tcallback = fun,\n",
     "\t\tcallback = function()\n"
     "\t\t\tif type(fun) == \"function\" then\n"
     "\t\t\t\tfun()\n"
     "\t\t\tend\n"
     "\t\tend,\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/util.lua',
     "\ttimer.delayOneFrame(fun)\n",
     "\ttimer.delayOneFrame(function()\n"
     "\t\tif type(fun) == \"function\" then\n"
     "\t\t\tfun()\n"
     "\t\tend\n"
     "\tend)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/cloudspeed.lua',
     "local WtC = tes3.worldController.weatherController\n",
     "local function getWtC()\n"
     "\tlocal wc = tes3.worldController\n"
     "\treturn wc and wc.weatherController\n"
     "end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/cloudspeed.lua',
     "local defaultCloudSpeeds = {}\n"
     "\n",
     "local defaultCloudSpeeds = {}\n"
     "local cloudSpeedTimer = nil\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/cloudspeed.lua',
     "\tfor i, w in pairs(WtC.weathers) do\n"
     "\t\tdefaultCloudSpeeds[i] = w.cloudsSpeed\n",
     "\tlocal WtC = getWtC()\n"
     "\tif not (WtC and WtC.weathers) then return end\n"
     "\tfor i, w in pairs(WtC.weathers) do\n"
     "\t\tif w and w.cloudsSpeed ~= nil then\n"
     "\t\t\tdefaultCloudSpeeds[i] = w.cloudsSpeed\n"
     "\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/cloudspeed.lua',
     "function cloudSpeed.restoreDefaults()\n"
     "\tfor i, w in pairs(WtC.weathers) do\n",
     "function cloudSpeed.restoreDefaults()\n"
     "\tlocal WtC = getWtC()\n"
     "\tif not (WtC and WtC.weathers) then return end\n"
     "\tfor i, w in pairs(WtC.weathers) do\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/cloudspeed.lua',
     "\t\tif defaultCloudSpeeds[i] then\n",
     "\t\tif w and defaultCloudSpeeds[i] ~= nil then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/cloudspeed.lua',
     "function cloudSpeed.randomise()\n"
     "\tlocal currentWeatherIndex = WtC.currentWeather.index\n",
     "function cloudSpeed.randomise()\n"
     "\tif tes3.menuMode() or not tes3.player then return end\n"
     "\tlocal WtC = getWtC()\n"
     "\tif not (WtC and WtC.currentWeather and WtC.weathers) then return end\n"
     "\n"
     "\tlocal currentWeatherIndex = WtC.currentWeather.index\n"
     "\tlocal mode = (config and config.cloudSpeedMode) or 100\n"
     "\tif mode <= 0 then mode = 100 end\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/cloudspeed.lua',
     "\t\tif i == currentWeatherIndex then goto continue end\n",
     "\t\tif not w or i == currentWeatherIndex then goto continue end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/cloudspeed.lua',
     "\t\tlocal cloudSpeedDataForWeather = cloudSpeedData[i]\n"
     "\t\tlocal randomIndex = math.random(#cloudSpeedDataForWeather)\n",
     "\t\tlocal cloudSpeedDataForWeather = cloudSpeedData[i]\n"
     "\t\tif not cloudSpeedDataForWeather or #cloudSpeedDataForWeather == 0 then goto continue end\n"
     "\t\tlocal randomIndex = math.random(#cloudSpeedDataForWeather)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/cloudspeed.lua',
     "\t\tw.cloudsSpeed = cloudSpeedDataForWeather[randomIndex] / config.cloudSpeedMode\n",
     "\t\tlocal speed = cloudSpeedDataForWeather[randomIndex]\n"
     "\t\tif speed then\n"
     "\t\t\tw.cloudsSpeed = speed / mode\n"
     "\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/cloudspeed.lua',
     "\n"
     "function cloudSpeed.startTimer()\n"
     "\tcloudSpeed.storeDefaults()\n",
     "\n"
     "function cloudSpeed.stopTimer()\n"
     "\tif cloudSpeedTimer then\n"
     "\t\tcloudSpeedTimer:cancel()\n"
     "\t\tcloudSpeedTimer = nil\n"
     "\t\tdebugLog(\"Cloud speed timer stopped.\")\n"
     "\tend\n"
     "end\n"
     "\n"
     "function cloudSpeed.startTimer()\n"
     "\tcloudSpeed.stopTimer()\n"
     "\tcloudSpeed.storeDefaults()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/cloudspeed.lua',
     "\ttimer.start {\n"
     "\t\tduration = common.centralTimerDuration,\n"
     "\t\tcallback = cloudSpeed.randomise,\n",
     "\tcloudSpeedTimer = timer.start {\n"
     "\t\tduration = common.centralTimerDuration or 8,\n"
     "\t\tcallback = function()\n"
     "\t\t\tif tes3.menuMode() or not tes3.player then return end\n"
     "\t\t\tcloudSpeed.randomise()\n"
     "\t\tend,\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/dynamicweatherchanges.lua',
     "local WtC = tes3.worldController.weatherController\n",
     "local function getWtC()\n"
     "\tlocal wc = tes3.worldController\n"
     "\treturn wc and wc.weatherController\n"
     "end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/dynamicweatherchanges.lua',
     "local defaultHoursBetweenWeatherChanges\n"
     "\n",
     "local defaultHoursBetweenWeatherChanges\n"
     "local weatherChangesTimer = nil\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/dynamicweatherchanges.lua',
     "\tif defaultHoursBetweenWeatherChanges then return end\n"
     "\tdefaultHoursBetweenWeatherChanges = WtC.hoursBetweenWeatherChanges\n",
     "\tif defaultHoursBetweenWeatherChanges then return end\n"
     "\tlocal WtC = getWtC()\n"
     "\tif not WtC or WtC.hoursBetweenWeatherChanges == nil then return end\n"
     "\tdefaultHoursBetweenWeatherChanges = WtC.hoursBetweenWeatherChanges\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/dynamicweatherchanges.lua',
     "\tdebugLog(\"Default hoursBetweenWeatherChanges stored: \" .. defaultHoursBetweenWeatherChanges)\n",
     "\tdebugLog(\"Default hoursBetweenWeatherChanges stored: \" .. tostring(defaultHoursBetweenWeatherChanges))\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/dynamicweatherchanges.lua',
     "\tif defaultHoursBetweenWeatherChanges then\n",
     "\tlocal WtC = getWtC()\n"
     "\tif WtC and defaultHoursBetweenWeatherChanges then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/dynamicweatherchanges.lua',
     "\t\tdebugLog(\"hoursBetweenWeatherChanges restored to default: \" .. defaultHoursBetweenWeatherChanges)\n",
     "\t\tdebugLog(\"hoursBetweenWeatherChanges restored to default: \" .. tostring(defaultHoursBetweenWeatherChanges))\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/dynamicweatherchanges.lua',
     "function dynamicWeatherChanges.randomise()\n"
     "\tlocal hours = math.random(3, 8)\n",
     "function dynamicWeatherChanges.randomise()\n"
     "\tif tes3.menuMode() or not tes3.player then return end\n"
     "\tlocal WtC = getWtC()\n"
     "\tif not WtC then return end\n"
     "\n"
     "\tlocal hours = math.random(3, 8)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/dynamicweatherchanges.lua',
     "\tdebugLog(\"Current time between weather changes: \" .. WtC.hoursBetweenWeatherChanges)\n",
     "\tdebugLog(\"Current time between weather changes: \" .. tostring(WtC.hoursBetweenWeatherChanges))\n"
     "end\n"
     "\n"
     "function dynamicWeatherChanges.stopTimer()\n"
     "\tif weatherChangesTimer then\n"
     "\t\tweatherChangesTimer:cancel()\n"
     "\t\tweatherChangesTimer = nil\n"
     "\t\tdebugLog(\"Dynamic weather changes timer stopped.\")\n"
     "\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/dynamicweatherchanges.lua',
     "function dynamicWeatherChanges.startTimer()\n"
     "\tdynamicWeatherChanges.randomise()\n",
     "function dynamicWeatherChanges.startTimer()\n"
     "\tdynamicWeatherChanges.stopTimer()\n"
     "\tdynamicWeatherChanges.randomise()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/dynamicweatherchanges.lua',
     "\ttimer.start {\n"
     "\t\tduration = common.centralTimerDuration,\n"
     "\t\tcallback = dynamicWeatherChanges.randomise,\n",
     "\tweatherChangesTimer = timer.start {\n"
     "\t\tduration = common.centralTimerDuration or 8,\n"
     "\t\tcallback = function()\n"
     "\t\t\tif tes3.menuMode() or not tes3.player then return end\n"
     "\t\t\tdynamicWeatherChanges.randomise()\n"
     "\t\tend,\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "local WtC = tes3.worldController.weatherController\n",
     "local function getWtC()\n"
     "\tlocal wc = tes3.worldController\n"
     "\treturn wc and wc.weatherController\n"
     "end\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "--------------------------------------------------------------------------------------\n"
     "\n"
     "-- Main function controlling weather changes in interiors --\n",
     "--------------------------------------------------------------------------------------\n"
     "\n"
     "function interiorTransitions.stopTimer()\n"
     "\tif intWeatherTimer then\n"
     "\t\tintWeatherTimer:cancel()\n"
     "\t\tintWeatherTimer = nil\n"
     "\t\tdebugLog(\"Interior transitions timer stopped.\")\n"
     "\tend\n"
     "end\n"
     "\n"
     "-- Main function controlling weather changes in interiors --\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "function interiorTransitions.progress()\n"
     "\tif WtC.nextWeather then return end\n",
     "function interiorTransitions.progress()\n"
     "\tif tes3.menuMode() or not tes3.player then return end\n"
     "\n"
     "\tlocal WtC = getWtC()\n"
     "\tif not (WtC and WtC.currentWeather) then return end\n"
     "\tif WtC.nextWeather then return end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\tlocal currentWeather = WtC.currentWeather.index -- 0-indexed\n"
     "\tlocal newWeather = nil\n",
     "\tlocal currentWeather = WtC.currentWeather.index -- 0-indexed\n"
     "\tif not currentWeather then return end\n"
     "\n"
     "\tlocal newWeather = nil\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\tdebugLog(\"Weather before randomisation: \" .. currentWeather)\n",
     "\tdebugLog(\"Weather before randomisation: \" .. tostring(currentWeather))\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\tif not region then return end\n",
     "\tif not region or not region.weatherChances then return end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\t\ttable.insert(availableWeathers, { weather = weather0, chance = chance })\n"
     "\t\t\tif chance > 0 then\n",
     "\t\t\ttable.insert(availableWeathers, { weather = weather0, chance = chance or 0 })\n"
     "\t\t\tif chance and chance > 0 then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\telseif chance < 100 then\n",
     "\t\telseif chance and chance < 100 then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\t\ttotalChance = totalChance + w.chance\n",
     "\t\t\ttotalChance = totalChance + (w.chance or 0)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\tlocal roll = math.random() * totalChance\n"
     "\t\tlocal cumulative = 0\n"
     "\t\tfor _, w in ipairs(availableWeathers) do\n"
     "\t\t\tcumulative = cumulative + w.chance\n"
     "\t\t\tif roll <= cumulative then\n"
     "\t\t\t\tnewWeather = w.weather\n"
     "\t\t\t\tbreak\n",
     "\t\tif totalChance <= 0 then\n"
     "\t\t\tnewWeather = currentWeather\n"
     "\t\telse\n"
     "\t\t\tlocal roll = math.random() * totalChance\n"
     "\t\t\tlocal cumulative = 0\n"
     "\t\t\tfor _, w in ipairs(availableWeathers) do\n"
     "\t\t\t\tcumulative = cumulative + (w.chance or 0)\n"
     "\t\t\t\tif roll <= cumulative then\n"
     "\t\t\t\t\tnewWeather = w.weather\n"
     "\t\t\t\t\tbreak\n"
     "\t\t\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\tif newWeather ~= currentWeather then\n",
     "\tif newWeather and newWeather ~= currentWeather then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\tdebugLog(\"Weather randomised. New weather: \" .. WtC.nextWeather.index)\n",
     "\t\tlocal nextIndex = WtC.nextWeather and WtC.nextWeather.index\n"
     "\t\tdebugLog(\"Weather randomised. New weather: \" .. tostring(nextIndex or newWeather))\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\tdebugLog(\"Weather remains the same: \" .. currentWeather)\n",
     "\t\tdebugLog(\"Weather remains the same: \" .. tostring(currentWeather))\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\tif not e then return end\n"
     "\tlocal cell = e.cell\n"
     "\tif not cell then return end\n",
     "\tif tes3.menuMode() or not tes3.player then return end\n"
     "\n"
     "\tlocal cell = (e and e.cell) or tes3.getPlayerCell()\n"
     "\tif not cell then return end\n"
     "\n"
     "\tlocal WtC = getWtC()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\tif intWeatherTimer then\n"
     "\t\t\tintWeatherTimer:pause()\n"
     "\t\t\tintWeatherTimer:cancel()\n"
     "\t\t\tintWeatherTimer = nil\n"
     "\t\tend\n",
     "\t\tinteriorTransitions.stopTimer()\n"
     "\n"
     "\t\tlocal hours = (WtC and WtC.hoursBetweenWeatherChanges) or 4\n"
     "\t\tif hours <= 0 then hours = 4 end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\t\tduration = WtC.hoursBetweenWeatherChanges,\n"
     "\t\t\tcallback = interiorTransitions.progress,\n",
     "\t\t\tduration = hours,\n"
     "\t\t\tcallback = function()\n"
     "\t\t\t\tif tes3.menuMode() or not tes3.player then return end\n"
     "\t\t\t\tinteriorTransitions.progress()\n"
     "\t\t\tend,\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\tdebugLog(\"Player in interior. Resuming interior timer. Hours to weather change: \" ..\n"
     "\t\t\tWtC.hoursBetweenWeatherChanges)\n",
     "\t\tdebugLog(\"Player in interior. Resuming interior timer. Hours to weather change: \" .. tostring(hours))\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "function interiorTransitions.stopSounds(e)\n"
     "\tlocal cell = tes3.getPlayerCell()\n",
     "function interiorTransitions.stopSounds(e)\n"
     "\tif not tes3.player then return end\n"
     "\n"
     "\tlocal cell = tes3.getPlayerCell()\n"
     "\tif not cell or cell.isOrBehavesAsExterior then return end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\tif not cell.isOrBehavesAsExterior then\n"
     "\t\tlocal cw = WtC.currentWeather\n"
     "\t\tlocal rs = cw.rainLoopSound\n"
     "\t\tlocal as = cw.ambientLoopSound\n",
     "\tlocal WtC = getWtC()\n"
     "\tif not (WtC and WtC.currentWeather) then return end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\tlocal currentSound = e and e.sound\n",
     "\tlocal cw = WtC.currentWeather\n"
     "\tlocal rs = cw.rainLoopSound\n"
     "\tlocal as = cw.ambientLoopSound\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\tif currentSound then\n"
     "\t\t\tlocal function nukeWeatherSounds()\n"
     "\t\t\t\tif currentSound.id == (rs and rs.id) or currentSound.id == (as and as.id) then\n"
     "\t\t\t\t\tif rs then rs:stop() end\n"
     "\t\t\t\t\tif as then as:stop() end\n"
     "\t\t\t\tend\n",
     "\tlocal currentSound = e and e.sound\n"
     "\n"
     "\tif currentSound then\n"
     "\t\tlocal function nukeWeatherSounds()\n"
     "\t\t\tif (rs and rs.id and currentSound.id == rs.id) or (as and as.id and currentSound.id == as.id) then\n"
     "\t\t\t\tif rs and rs.stop then rs:stop() end\n"
     "\t\t\t\tif as and as.stop then as:stop() end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\t\tutil.matryoshka(nukeWeatherSounds)\n"
     "\t\telse\n"
     "\t\t\tlocal function nukeWeatherSounds()\n"
     "\t\t\t\tif rs and rs:isPlaying() then\n"
     "\t\t\t\t\trs:stop()\n"
     "\t\t\t\tend\n",
     "\t\tend\n"
     "\t\tutil.matryoshka(nukeWeatherSounds)\n"
     "\telse\n"
     "\t\tlocal function nukeWeatherSounds()\n"
     "\t\t\tif rs and rs.isPlaying and rs:isPlaying() then\n"
     "\t\t\t\trs:stop()\n"
     "\t\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\t\t\tif as and as:isPlaying() then\n"
     "\t\t\t\t\tas:stop()\n"
     "\t\t\t\tend\n",
     "\t\t\tif as and as.isPlaying and as:isPlaying() then\n"
     "\t\t\t\tas:stop()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/interiortransitions.lua',
     "\t\t\tutil.matryoshka(nukeWeatherSounds)\n"
     "\t\tend\n",
     "\t\tend\n"
     "\t\tutil.matryoshka(nukeWeatherSounds)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "local WtC = tes3.worldController.weatherController\n",
     "local function getWtC()\n"
     "\tlocal wc = tes3.worldController\n"
     "\treturn wc and wc.weatherController\n"
     "end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "local defaultValues = {}\n"
     "\n",
     "local defaultValues = {}\n"
     "local particleAmountTimer = nil\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "\tif not table.empty(defaultValues) then return end\n"
     "\tfor index, weather in ipairs(WtC.weathers) do\n",
     "\tif not table.empty(defaultValues) then return end\n"
     "\tlocal WtC = getWtC()\n"
     "\tif not (WtC and WtC.weathers) then return end\n"
     "\n"
     "\tfor index, weather in ipairs(WtC.weathers) do\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "\t\tif table.contains(allowedIndexes, index) then\n",
     "\t\tif weather and table.contains(allowedIndexes, index) then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "function particleAmount.restoreDefaults()\n"
     "\tfor index, values in pairs(defaultValues) do\n",
     "function particleAmount.restoreDefaults()\n"
     "\tlocal WtC = getWtC()\n"
     "\tif not (WtC and WtC.weathers) then return end\n"
     "\n"
     "\tfor index, values in pairs(defaultValues) do\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "\t\tif WtC.weathers[index] then\n",
     "\t\tif WtC.weathers[index] and values then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "function particleAmount.init()\n"
     "\tparticleAmount.storeDefaults()\n",
     "function particleAmount.init()\n"
     "\tlocal WtC = getWtC()\n"
     "\tparticleAmount.storeDefaults()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "\tWtC.weathers[5].particleRadius = 1500\n"
     "\tWtC.weathers[6].particleRadius = 1700\n"
     "\tWtC.weathers[9].particleRadius = 2000\n",
     "\tif WtC and WtC.weathers then\n"
     "\t\tif WtC.weathers[5] then WtC.weathers[5].particleRadius = 1500 end\n"
     "\t\tif WtC.weathers[6] then WtC.weathers[6].particleRadius = 1700 end\n"
     "\t\tif WtC.weathers[9] then WtC.weathers[9].particleRadius = 2000 end\n"
     "\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "function particleAmount.randomise()\n"
     "\tlocal currentWeatherIndex = WtC.currentWeather.index\n",
     "function particleAmount.randomise()\n"
     "\tif tes3.menuMode() or not tes3.player then return end\n"
     "\tlocal WtC = getWtC()\n"
     "\tif not (WtC and WtC.currentWeather and WtC.weathers) then return end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "\tif WtC.nextWeather then return end\n"
     "\n"
     "\tfor weather, values in pairs(particleAmountData) do\n",
     "\tif WtC.nextWeather then return end\n"
     "\n"
     "\tlocal currentWeatherIndex = WtC.currentWeather.index\n"
     "\tif not currentWeatherIndex then return end\n"
     "\n"
     "\tfor weather, values in pairs(particleAmountData) do\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "\t\tif (currentWeatherIndex + 1 ~= weather) then\n",
     "\t\tif (currentWeatherIndex + 1 ~= weather) and WtC.weathers[weather] and values then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "\tdebugLog(\"Rain particles: \" .. WtC.weathers[5].maxParticles)\n"
     "\tdebugLog(\"Thunderstorm particles: \" .. WtC.weathers[6].maxParticles)\n"
     "\tdebugLog(\"Snow particles: \" .. WtC.weathers[9].maxParticles)\n",
     "\tif WtC.weathers[5] then debugLog(\"Rain particles: \" .. tostring(WtC.weathers[5].maxParticles)) end\n"
     "\tif WtC.weathers[6] then debugLog(\"Thunderstorm particles: \" .. tostring(WtC.weathers[6].maxParticles)) end\n"
     "\tif WtC.weathers[9] then debugLog(\"Snow particles: \" .. tostring(WtC.weathers[9].maxParticles)) end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "\n"
     "function particleAmount.startTimer()\n"
     "\tparticleAmount.randomise()\n",
     "\n"
     "function particleAmount.stopTimer()\n"
     "\tif particleAmountTimer then\n"
     "\t\tparticleAmountTimer:cancel()\n"
     "\t\tparticleAmountTimer = nil\n"
     "\t\tdebugLog(\"Particle amount timer stopped.\")\n"
     "\tend\n"
     "end\n"
     "\n"
     "function particleAmount.startTimer()\n"
     "\tparticleAmount.stopTimer()\n"
     "\tparticleAmount.randomise()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particleamount.lua',
     "\ttimer.start {\n"
     "\t\tduration = common.centralTimerDuration,\n"
     "\t\tcallback = particleAmount.randomise,\n",
     "\tparticleAmountTimer = timer.start {\n"
     "\t\tduration = common.centralTimerDuration or 8,\n"
     "\t\tcallback = function()\n"
     "\t\t\tif tes3.menuMode() or not tes3.player then return end\n"
     "\t\t\tparticleAmount.randomise()\n"
     "\t\tend,\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "local WtC = tes3.worldController.weatherController\n",
     "local function getWtC()\n"
     "\tlocal wc = tes3.worldController\n"
     "\treturn wc and wc.weatherController\n"
     "end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\t\t\tparticleList[i] = tes3.loadMesh(\n",
     "\t\t\tlocal mesh = tes3.loadMesh(\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\t\t\t\t.. particle\n"
     "\t\t\t)\n"
     "\t\tend\n",
     "\t\t\t\t.. particle\n"
     "\t\t\t)\n"
     "\t\t\tif mesh then\n"
     "\t\t\t\tparticleList[i] = mesh\n"
     "\t\t\tend\n"
     "\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\treturn math.clamp(math.lerp(comp, 1.0, point), 0.03, 0.88)\n",
     "\treturn math.clamp(math.lerp(comp or 0, 1.0, point or 0.1), 0.03, 0.88)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\tlocal colours\n"
     "\n"
     "\tif (WtC.currentWeather.name) == \"Snow\"\n"
     "\t\tor (WtC.nextWeather and WtC.nextWeather.name == \"Snow\")\n"
     "\tthen\n"
     "\t\tcolours = {\n"
     "\t\t\tr = getBleachedColour(weatherColour.r, SNOW_POINT),\n"
     "\t\t\tg = getBleachedColour(weatherColour.g, SNOW_POINT),\n"
     "\t\t\tb = getBleachedColour(weatherColour.b, SNOW_POINT),\n"
     "\t\t}\n"
     "\telse\n"
     "\t\tcolours = {\n"
     "\t\t\tr = getBleachedColour(weatherColour.r, RAIN_POINT),\n"
     "\t\t\tg = getBleachedColour(weatherColour.g, RAIN_POINT),\n"
     "\t\t\tb = getBleachedColour(weatherColour.b, RAIN_POINT),\n"
     "\t\t}\n",
     "\tif not weatherColour then\n"
     "\t\treturn { r = 0.5, g = 0.5, b = 0.5 }\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\treturn colours\n",
     "\tlocal WtC = getWtC()\n"
     "\tlocal isSnow = false\n"
     "\tif WtC then\n"
     "\t\tif WtC.currentWeather and WtC.currentWeather.name == \"Snow\" then\n"
     "\t\t\tisSnow = true\n"
     "\t\telseif WtC.nextWeather and WtC.nextWeather.name == \"Snow\" then\n"
     "\t\t\tisSnow = true\n"
     "\t\tend\n"
     "\tend\n"
     "\n"
     "\tlocal point = isSnow and SNOW_POINT or RAIN_POINT\n"
     "\treturn {\n"
     "\t\tr = getBleachedColour(weatherColour.r or 0.5, point),\n"
     "\t\tg = getBleachedColour(weatherColour.g or 0.5, point),\n"
     "\t\tb = getBleachedColour(weatherColour.b or 0.5, point),\n"
     "\t}\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "function particleMesh.reColourParticleMesh()\n"
     "\tframeCounter = frameCounter + 1\n",
     "function particleMesh.reColourParticleMesh()\n"
     "\tif tes3.menuMode() or not tes3.player then return end\n"
     "\n"
     "\tframeCounter = frameCounter + 1\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\tif not particleMesh.isValidWeather()\n"
     "\t\tor not newParticleMesh\n"
     "\tthen\n",
     "\tlocal WtC = getWtC()\n"
     "\tif not WtC or not particleMesh.isValidWeather() or not newParticleMesh then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\tlocal weatherColour = WtC.currentFogColor\n"
     "\tlocal colours = particleMesh.getModifiedColour(weatherColour)\n",
     "\tlocal weatherColour = WtC.currentFogColor\n"
     "\tif not weatherColour then return end\n"
     "\n"
     "\tlocal colours = particleMesh.getModifiedColour(weatherColour)\n"
     "\tif not colours then return end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\tif not particleNode then\n",
     "\tif not particleNode and newParticleMesh.getObjectByName then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\tif particleNode then\n",
     "\tif particleNode and particleNode.materialProperty then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\n"
     "\t\tif materialProperty then\n"
     "\t\t\tmaterialProperty.emissive = colours\n"
     "\t\t\tmaterialProperty.specular = colours\n"
     "\t\t\tmaterialProperty.diffuse = colours\n"
     "\t\t\tmaterialProperty.ambient = colours\n"
     "\t\tend\n",
     "\t\tmaterialProperty.emissive = colours\n"
     "\t\tmaterialProperty.specular = colours\n"
     "\t\tmaterialProperty.diffuse = colours\n"
     "\t\tmaterialProperty.ambient = colours\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "function particleMesh.isValidWeather()\n"
     "\tlocal current = WtC.currentWeather.name\n",
     "function particleMesh.isValidWeather()\n"
     "\tlocal WtC = getWtC()\n"
     "\tif not (WtC and WtC.currentWeather and WtC.currentWeather.name) then\n"
     "\t\treturn false\n"
     "\tend\n"
     "\n"
     "\tlocal current = WtC.currentWeather.name\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\t\tor not particle.rainRoot\n"
     "\tthen\n",
     "\t\tor not particle.rainRoot\n"
     "\t\tor not newParticleMesh\n"
     "\tthen\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\tlocal old = particle.object\n"
     "\n",
     "\tlocal old = particle.object\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\n"
     "\tparticle.rainRoot:attachChild(new)\n"
     "\n"
     "\tnew.appCulled = old.appCulled\n"
     "\n"
     "\tparticle.object = new\n",
     "\tif new then\n"
     "\t\tparticle.rainRoot:attachChild(new)\n"
     "\t\tnew.appCulled = old.appCulled\n"
     "\t\tparticle.object = new\n"
     "\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "local function processSwapQueue()\n"
     "\tif not swapQueue then\n",
     "local function processSwapQueue()\n"
     "\tif tes3.menuMode() or not tes3.player then return end\n"
     "\n"
     "\tif not swapQueue then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\t\tif WtC.sceneRainRoot then\n",
     "\t\tlocal WtC = getWtC()\n"
     "\t\tif WtC and WtC.sceneRainRoot and WtC.sceneRainRoot.updateEffects then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\tnewParticleMesh = table.choice(particleList)\n"
     "\n",
     "\tnewParticleMesh = table.choice(particleList)\n"
     "\tif not newParticleMesh then return end\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\tlocal particleTables = {\n"
     "\t\tWtC.particlesActive,\n"
     "\t\tWtC.particlesInactive,\n"
     "\t}\n",
     "\tlocal WtC = getWtC()\n"
     "\tif not WtC then return end\n"
     "\n"
     "\tlocal particleTables = {}\n"
     "\tif WtC.particlesActive then table.insert(particleTables, WtC.particlesActive) end\n"
     "\tif WtC.particlesInactive then table.insert(particleTables, WtC.particlesInactive) end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\t\tfor _, particle in pairs(particleTable) do\n"
     "\t\t\ttable.insert(swapQueue, particle)\n",
     "\t\tfor _, particle in pairs(particleTable) do\n"
     "\t\t\tif particle then\n"
     "\t\t\t\ttable.insert(swapQueue, particle)\n"
     "\t\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\n"
     "\tevent.register(tes3.event.enterFrame, processSwapQueue)\n",
     "\n"
     "\tif #swapQueue > 0 then\n"
     "\t\tevent.register(tes3.event.enterFrame, processSwapQueue)\n"
     "\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\tlocal weatherNow\n",
     "\tif tes3.menuMode() or not tes3.player then return end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\tif WtC.nextWeather then\n"
     "\t\tweatherNow = WtC.nextWeather\n"
     "\n"
     "\t\tlocal particleWeatherType =\n"
     "\t\t\tweatherChecklist[weatherNow.name]\n",
     "\tlocal WtC = getWtC()\n"
     "\tif not WtC then return end\n"
     "\n"
     "\tlocal weatherNow = WtC.nextWeather or WtC.currentWeather\n"
     "\tif not (weatherNow and weatherNow.name) then return end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\n"
     "\t\tif particleWeatherType ~= nil then\n"
     "\t\t\ttimer.start {\n",
     "\n"
     "\tlocal particleWeatherType = weatherChecklist[weatherNow.name]\n"
     "\tif particleWeatherType ~= nil then\n"
     "\t\tif WtC.nextWeather then\n"
     "\t\t\ttimer.start {\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\t\t\t\t\tparticleMesh.changeParticleMesh(\n"
     "\t\t\t\t\t\tparticleWeatherType\n"
     "\t\t\t\t\t)\n",
     "\t\t\t\t\tif tes3.menuMode() or not tes3.player then return end\n"
     "\t\t\t\t\tparticleMesh.changeParticleMesh(particleWeatherType)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/particlemesh.lua',
     "\t\tend\n"
     "\telse\n"
     "\t\tweatherNow = WtC.currentWeather\n"
     "\n"
     "\t\tlocal particleWeatherType =\n"
     "\t\t\tweatherChecklist[weatherNow.name]\n"
     "\n"
     "\t\tif particleWeatherType ~= nil then\n"
     "\t\t\tparticleMesh.changeParticleMesh(\n"
     "\t\t\t\tparticleWeatherType\n"
     "\t\t\t)\n"
     "\t\tend\n"
     "\tend\n",
     "\t\telse\n"
     "\t\t\tparticleMesh.changeParticleMesh(particleWeatherType)\n"
     "\t\tend\n"
     "\tend\n"
     "end\n"
     "\n"
     "function particleMesh.stop()\n"
     "\tevent.unregister(tes3.event.enterFrame, processSwapQueue)\n"
     "\tswapQueue = nil\n"
     "\tswapIndex = 1\n"
     "\tparticleNode = nil\n"
     "\tnewParticleMesh = nil\n"
     "\tdebugLog(\"particleMesh stopped and cleared.\")\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonaldaytime.lua',
     "local WtC = tes3.worldController.weatherController\n",
     "local function getWtC()\n"
     "\tlocal wc = tes3.worldController\n"
     "\treturn wc and wc.weatherController\n"
     "end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonaldaytime.lua',
     "local defaultDaytimeValues = {}\n"
     "\n",
     "local defaultDaytimeValues = {}\n"
     "local seasonalDaytimeTimer = nil\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonaldaytime.lua',
     "\tif not table.empty(defaultDaytimeValues) then return end\n"
     "\tdefaultDaytimeValues = {\n",
     "\tif not table.empty(defaultDaytimeValues) then return end\n"
     "\tlocal WtC = getWtC()\n"
     "\tif not WtC then return end\n"
     "\tdefaultDaytimeValues = {\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonaldaytime.lua',
     "\tif next(defaultDaytimeValues) then\n",
     "\tlocal WtC = getWtC()\n"
     "\tif WtC and next(defaultDaytimeValues) then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonaldaytime.lua',
     "\tif not tes3.player then return end\n"
     "\tlocal month = tes3.worldController.month.value\n"
     "\tlocal day = tes3.worldController.day.value\n",
     "\tif tes3.menuMode() or not tes3.player or not tes3.player.position then return end\n"
     "\tlocal wc = tes3.worldController\n"
     "\tif not (wc and wc.month and wc.day and wc.weatherController) then return end\n"
     "\tlocal WtC = wc.weatherController\n"
     "\n"
     "\tlocal month = wc.month.value\n"
     "\tlocal day = wc.day.value\n"
     "\tif not month or not day then return end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonaldaytime.lua',
     "\t\tdebugLog(\"Previous values: \" ..\n"
     "\t\t\tWtC.sunriseHour .. \" \" .. WtC.sunriseDuration .. \" \" .. WtC.sunsetHour .. \" \" .. WtC.sunsetDuration)\n",
     "\t\tdebugLog(\"Previous values: \" ..\n"
     "\t\t\ttostring(WtC.sunriseHour) .. \" \" .. tostring(WtC.sunriseDuration) .. \" \" .. tostring(WtC.sunsetHour) .. \" \" .. tostring(WtC.sunsetDuration))\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonaldaytime.lua',
     "\t\tdebugLog(\"Current values: \" ..\n"
     "\t\t\tWtC.sunriseHour .. \" \" .. WtC.sunriseDuration .. \" \" .. WtC.sunsetHour .. \" \" .. WtC.sunsetDuration)\n",
     "\t\tdebugLog(\"Current values: \" ..\n"
     "\t\t\ttostring(WtC.sunriseHour) .. \" \" .. tostring(WtC.sunriseDuration) .. \" \" .. tostring(WtC.sunsetHour) .. \" \" .. tostring(WtC.sunsetDuration))\n"
     "\tend\n"
     "end\n"
     "\n"
     "function seasonalDaytime.stopTimer()\n"
     "\tif seasonalDaytimeTimer then\n"
     "\t\tseasonalDaytimeTimer:cancel()\n"
     "\t\tseasonalDaytimeTimer = nil\n"
     "\t\tdebugLog(\"Seasonal daytime timer stopped.\")\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonaldaytime.lua',
     "function seasonalDaytime.startTimer()\n"
     "\tseasonalDaytime.calculate()\n",
     "function seasonalDaytime.startTimer()\n"
     "\tseasonalDaytime.stopTimer()\n"
     "\tseasonalDaytime.calculate()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonaldaytime.lua',
     "\ttimer.start {\n"
     "\t\tduration = common.centralTimerDuration,\n"
     "\t\tcallback = seasonalDaytime.calculate,\n",
     "\tseasonalDaytimeTimer = timer.start {\n"
     "\t\tduration = common.centralTimerDuration or 8,\n"
     "\t\tcallback = function()\n"
     "\t\t\tif tes3.menuMode() or not tes3.player then return end\n"
     "\t\t\tseasonalDaytime.calculate()\n"
     "\t\tend,\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "local defaultWeatherChances = {}\n"
     "\n",
     "local defaultWeatherChances = {}\n"
     "local seasonalWeatherTimer = nil\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\tif not table.empty(defaultWeatherChances) then return end\n"
     "\tfor region in tes3.iterate(tes3.dataHandler.nonDynamicData.regions) do\n",
     "\tif not table.empty(defaultWeatherChances) then return end\n"
     "\tif not (tes3.dataHandler and tes3.dataHandler.nonDynamicData and tes3.dataHandler.nonDynamicData.regions) then\n"
     "\t\treturn\n"
     "\tend\n"
     "\n"
     "\tfor region in tes3.iterate(tes3.dataHandler.nonDynamicData.regions) do\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\t\tdefaultWeatherChances[region.id] = {\n"
     "\t\t\tclear = region.weatherChanceClear,\n"
     "\t\t\tcloudy = region.weatherChanceCloudy,\n"
     "\t\t\tfoggy = region.weatherChanceFoggy,\n"
     "\t\t\tovercast = region.weatherChanceOvercast,\n"
     "\t\t\train = region.weatherChanceRain,\n"
     "\t\t\tthunder = region.weatherChanceThunder,\n"
     "\t\t\tash = region.weatherChanceAsh,\n"
     "\t\t\tblight = region.weatherChanceBlight,\n"
     "\t\t\tsnow = region.weatherChanceSnow,\n"
     "\t\t\tblizzard = region.weatherChanceBlizzard,\n"
     "\t\t}\n",
     "\t\tif region and region.id then\n"
     "\t\t\tdefaultWeatherChances[region.id] = {\n"
     "\t\t\t\tclear = region.weatherChanceClear,\n"
     "\t\t\t\tcloudy = region.weatherChanceCloudy,\n"
     "\t\t\t\tfoggy = region.weatherChanceFoggy,\n"
     "\t\t\t\tovercast = region.weatherChanceOvercast,\n"
     "\t\t\t\train = region.weatherChanceRain,\n"
     "\t\t\t\tthunder = region.weatherChanceThunder,\n"
     "\t\t\t\tash = region.weatherChanceAsh,\n"
     "\t\t\t\tblight = region.weatherChanceBlight,\n"
     "\t\t\t\tsnow = region.weatherChanceSnow,\n"
     "\t\t\t\tblizzard = region.weatherChanceBlizzard,\n"
     "\t\t\t}\n"
     "\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "function seasonalWeather.restoreDefaults()\n"
     "\tfor region in tes3.iterate(tes3.dataHandler.nonDynamicData.regions) do\n",
     "function seasonalWeather.restoreDefaults()\n"
     "\tif not (tes3.dataHandler and tes3.dataHandler.nonDynamicData and tes3.dataHandler.nonDynamicData.regions) then\n"
     "\t\treturn\n"
     "\tend\n"
     "\n"
     "\tfor region in tes3.iterate(tes3.dataHandler.nonDynamicData.regions) do\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\t\tlocal defaults = defaultWeatherChances[region.id]\n"
     "\t\tif defaults then\n"
     "\t\t\tregion.weatherChanceClear = defaults.clear\n"
     "\t\t\tregion.weatherChanceCloudy = defaults.cloudy\n"
     "\t\t\tregion.weatherChanceFoggy = defaults.foggy\n"
     "\t\t\tregion.weatherChanceOvercast = defaults.overcast\n"
     "\t\t\tregion.weatherChanceRain = defaults.rain\n"
     "\t\t\tregion.weatherChanceThunder = defaults.thunder\n"
     "\t\t\tregion.weatherChanceAsh = defaults.ash\n"
     "\t\t\tregion.weatherChanceBlight = defaults.blight\n"
     "\t\t\tregion.weatherChanceSnow = defaults.snow\n"
     "\t\t\tregion.weatherChanceBlizzard = defaults.blizzard\n",
     "\t\tif region and region.id then\n"
     "\t\t\tlocal defaults = defaultWeatherChances[region.id]\n"
     "\t\t\tif defaults then\n"
     "\t\t\t\tregion.weatherChanceClear = defaults.clear\n"
     "\t\t\t\tregion.weatherChanceCloudy = defaults.cloudy\n"
     "\t\t\t\tregion.weatherChanceFoggy = defaults.foggy\n"
     "\t\t\t\tregion.weatherChanceOvercast = defaults.overcast\n"
     "\t\t\t\tregion.weatherChanceRain = defaults.rain\n"
     "\t\t\t\tregion.weatherChanceThunder = defaults.thunder\n"
     "\t\t\t\tregion.weatherChanceAsh = defaults.ash\n"
     "\t\t\t\tregion.weatherChanceBlight = defaults.blight\n"
     "\t\t\t\tregion.weatherChanceSnow = defaults.snow\n"
     "\t\t\t\tregion.weatherChanceBlizzard = defaults.blizzard\n"
     "\t\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "function seasonalWeather.checkVv(region)\n"
     "\treturn table.find(vvRegions, region) ~= nil\n",
     "function seasonalWeather.checkVv(region)\n"
     "\tif not region then return false end\n"
     "\treturn table.find(vvRegions, region) ~= nil\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\t\tlocal index = tes3.getJournalIndex { id = entry.id }\n",
     "\t\tlocal index = tes3.getJournalIndex { id = entry.id } or 0\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "function seasonalWeather.calculate()\n"
     "\t-- Get month and region and buzz off if there's no change --\n",
     "function seasonalWeather.calculate()\n"
     "\tif tes3.menuMode() or not tes3.player then return end\n"
     "\n"
     "\tlocal wc = tes3.worldController\n"
     "\tif not (wc and wc.month) then return end\n"
     "\n"
     "\t-- Get month and region and buzz off if there's no change --\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\tlocal month = tes3.worldController.month.value + 1\n"
     "\tlocal regionNow = tes3.getRegion(true)\n",
     "\tlocal month = (wc.month.value or 0) + 1\n"
     "\tlocal regionNow = tes3.getRegion({ useDoors = true }) or tes3.getRegion(true)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\t\tdebugLog(\"Same month and region. Returning.\")\n"
     "\t\treturn\n"
     "\tend\n"
     "\n"
     "\t-- If either month or region has changed, we need to reapply values--\n"
     "\t-- Get the current MQ state to use in Blight calculations --\n"
     "\tlocal questStage = seasonalWeather.getMQState()\n",
     "\t\tdebugLog(\"Same month and region. Returning.\")\n"
     "\t\treturn\n"
     "\tend\n"
     "\n"
     "\tif not (tes3.dataHandler and tes3.dataHandler.nonDynamicData and tes3.dataHandler.nonDynamicData.regions) then\n"
     "\t\treturn\n"
     "\tend\n"
     "\n"
     "\t-- If either month or region has changed, we need to reapply values--\n"
     "\t-- Get the current MQ state to use in Blight calculations --\n"
     "\tlocal questStage = seasonalWeather.getMQState()\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\tdebugLog(\"Selected blight chance: \" .. questStage)\n",
     "\tdebugLog(\"Selected blight chance: \" .. tostring(questStage))\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\tfor region in tes3.iterate(tes3.dataHandler.nonDynamicData.regions) do\n"
     "\t\t-- Special handling for Red Mountain - use either full Blight or normal regional weather after MQ --\n",
     "\tfor region in tes3.iterate(tes3.dataHandler.nonDynamicData.regions) do\n"
     "\t\tif not (region and region.id) then goto continueRegion end\n"
     "\n"
     "\t\t-- Special handling for Red Mountain - use either full Blight or normal regional weather after MQ --\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\t\t\tif tes3.getJournalIndex { id = \"C3_DestroyDagoth\" } < 20 then\n",
     "\t\t\tlocal dagothState = tes3.getJournalIndex { id = \"C3_DestroyDagoth\" } or 0\n"
     "\t\t\tif dagothState < 20 then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\t\t\t\tdebugLog(\"Dagoth Ur is dead. Reverting to regular RM weather. Removing blight cloud.\")\n"
     "\t\t\t\tregion.weatherChanceClear = seasonalChances[region.id][month][1]\n"
     "\t\t\t\tregion.weatherChanceCloudy = seasonalChances[region.id][month][2]\n"
     "\t\t\t\tregion.weatherChanceFoggy = seasonalChances[region.id][month][3]\n"
     "\t\t\t\tregion.weatherChanceOvercast = seasonalChances[region.id][month][4]\n"
     "\t\t\t\tregion.weatherChanceRain = seasonalChances[region.id][month][5]\n"
     "\t\t\t\tregion.weatherChanceThunder = seasonalChances[region.id][month][6]\n"
     "\t\t\t\tregion.weatherChanceAsh = seasonalChances[region.id][month][7]\n"
     "\t\t\t\tregion.weatherChanceBlight = seasonalChances[region.id][month][8]\n"
     "\t\t\t\tregion.weatherChanceSnow = seasonalChances[region.id][month][9]\n"
     "\t\t\t\tregion.weatherChanceBlizzard = seasonalChances[region.id][month][10]\n",
     "\t\t\t\tdebugLog(\"Dagoth Ur is dead. Reverting to regular RM weather. Removing blight cloud.\")\n"
     "\t\t\t\tlocal chances = seasonalChances[region.id] and seasonalChances[region.id][month]\n"
     "\t\t\t\tif chances then\n"
     "\t\t\t\t\tregion.weatherChanceClear = chances[1] or 0\n"
     "\t\t\t\t\tregion.weatherChanceCloudy = chances[2] or 0\n"
     "\t\t\t\t\tregion.weatherChanceFoggy = chances[3] or 0\n"
     "\t\t\t\t\tregion.weatherChanceOvercast = chances[4] or 0\n"
     "\t\t\t\t\tregion.weatherChanceRain = chances[5] or 0\n"
     "\t\t\t\t\tregion.weatherChanceThunder = chances[6] or 0\n"
     "\t\t\t\t\tregion.weatherChanceAsh = chances[7] or 0\n"
     "\t\t\t\t\tregion.weatherChanceBlight = chances[8] or 0\n"
     "\t\t\t\t\tregion.weatherChanceSnow = chances[9] or 0\n"
     "\t\t\t\t\tregion.weatherChanceBlizzard = chances[10] or 0\n"
     "\t\t\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\t\t\t\t-- Disable the blight cloud object from Dagoth Ur volcano --\n"
     "\t\t\t\tmwscript.disable { reference = \"blight cloud\" }\n",
     "\t\t\t\t-- Disable the blight cloud object from Dagoth Ur volcano --\n"
     "\t\t\t\tpcall(function()\n"
     "\t\t\t\t\tmwscript.disable { reference = \"blight cloud\" }\n"
     "\t\t\t\tend)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\t\telseif region.id == \"Mournhold Region\"\n"
     "\t\t\tand tes3.findGlobal(\"MournWeather\").value == 1\n"
     "\t\t\tor tes3.findGlobal(\"MournWeather\").value == 2\n"
     "\t\t\tor tes3.findGlobal(\"MournWeather\").value == 3\n"
     "\t\t\tor tes3.findGlobal(\"MournWeather\").value == 4\n"
     "\t\t\tor tes3.findGlobal(\"MournWeather\").value == 5\n"
     "\t\t\tor tes3.findGlobal(\"MournWeather\").value == 6\n"
     "\t\t\tor tes3.findGlobal(\"MournWeather\").value == 7 then\n"
     "\t\t\tdebugLog(\"Weather machine running: \" .. tes3.findGlobal(\"MournWeather\").value)\n"
     "\t\t\tregion.weatherChanceClear = 0\n"
     "\t\t\tregion.weatherChanceCloudy = 0\n"
     "\t\t\tregion.weatherChanceFoggy = 0\n"
     "\t\t\tregion.weatherChanceOvercast = 0\n"
     "\t\t\tregion.weatherChanceRain = 0\n"
     "\t\t\tregion.weatherChanceThunder = 0\n"
     "\t\t\tregion.weatherChanceAsh = 0\n"
     "\t\t\tregion.weatherChanceBlight = 0\n"
     "\t\t\tregion.weatherChanceSnow = 0\n"
     "\t\t\tregion.weatherChanceBlizzard = 0\n"
     "\t\t\tif tes3.findGlobal(\"MournWeather\").value == 1 then\n"
     "\t\t\t\tregion.weatherChanceClear = 100\n"
     "\t\t\telseif tes3.findGlobal(\"MournWeather\").value == 2 then\n"
     "\t\t\t\tregion.weatherChanceCloudy = 100\n"
     "\t\t\telseif tes3.findGlobal(\"MournWeather\").value == 3 then\n"
     "\t\t\t\tregion.weatherChanceFoggy = 100\n"
     "\t\t\telseif tes3.findGlobal(\"MournWeather\").value == 4 then\n"
     "\t\t\t\tregion.weatherChanceOvercast = 100\n"
     "\t\t\telseif tes3.findGlobal(\"MournWeather\").value == 5 then\n"
     "\t\t\t\tregion.weatherChanceRain = 100\n"
     "\t\t\telseif tes3.findGlobal(\"MournWeather\").value == 6 then\n"
     "\t\t\t\tregion.weatherChanceThunder = 100\n"
     "\t\t\telseif tes3.findGlobal(\"MournWeather\").value == 7 then\n"
     "\t\t\t\tregion.weatherChanceAsh = 100\n",
     "\t\telseif region.id == \"Mournhold Region\" then\n"
     "\t\t\tlocal mournGlobal = tes3.findGlobal(\"MournWeather\")\n"
     "\t\t\tlocal mournVal = mournGlobal and mournGlobal.value\n"
     "\t\t\tif mournVal and mournVal >= 1 and mournVal <= 7 then\n"
     "\t\t\t\tdebugLog(\"Weather machine running: \" .. tostring(mournVal))\n"
     "\t\t\t\tregion.weatherChanceClear = 0\n"
     "\t\t\t\tregion.weatherChanceCloudy = 0\n"
     "\t\t\t\tregion.weatherChanceFoggy = 0\n"
     "\t\t\t\tregion.weatherChanceOvercast = 0\n"
     "\t\t\t\tregion.weatherChanceRain = 0\n"
     "\t\t\t\tregion.weatherChanceThunder = 0\n"
     "\t\t\t\tregion.weatherChanceAsh = 0\n"
     "\t\t\t\tregion.weatherChanceBlight = 0\n"
     "\t\t\t\tregion.weatherChanceSnow = 0\n"
     "\t\t\t\tregion.weatherChanceBlizzard = 0\n"
     "\t\t\t\tif mournVal == 1 then\n"
     "\t\t\t\t\tregion.weatherChanceClear = 100\n"
     "\t\t\t\telseif mournVal == 2 then\n"
     "\t\t\t\t\tregion.weatherChanceCloudy = 100\n"
     "\t\t\t\telseif mournVal == 3 then\n"
     "\t\t\t\t\tregion.weatherChanceFoggy = 100\n"
     "\t\t\t\telseif mournVal == 4 then\n"
     "\t\t\t\t\tregion.weatherChanceOvercast = 100\n"
     "\t\t\t\telseif mournVal == 5 then\n"
     "\t\t\t\t\tregion.weatherChanceRain = 100\n"
     "\t\t\t\telseif mournVal == 6 then\n"
     "\t\t\t\t\tregion.weatherChanceThunder = 100\n"
     "\t\t\t\telseif mournVal == 7 then\n"
     "\t\t\t\t\tregion.weatherChanceAsh = 100\n"
     "\t\t\t\tend\n"
     "\t\t\telseif seasonalChances[region.id] and seasonalChances[region.id][month] then\n"
     "\t\t\t\tlocal chances = seasonalChances[region.id][month]\n"
     "\t\t\t\tregion.weatherChanceClear = chances[1] or 0\n"
     "\t\t\t\tregion.weatherChanceCloudy = chances[2] or 0\n"
     "\t\t\t\tregion.weatherChanceFoggy = chances[3] or 0\n"
     "\t\t\t\tregion.weatherChanceOvercast = chances[4] or 0\n"
     "\t\t\t\tregion.weatherChanceRain = chances[5] or 0\n"
     "\t\t\t\tregion.weatherChanceThunder = chances[6] or 0\n"
     "\t\t\t\tregion.weatherChanceAsh = chances[7] or 0\n"
     "\t\t\t\tregion.weatherChanceBlight = chances[8] or 0\n"
     "\t\t\t\tregion.weatherChanceSnow = chances[9] or 0\n"
     "\t\t\t\tregion.weatherChanceBlizzard = chances[10] or 0\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\t\t\tif seasonalWeather.checkVv(region.id) == true then\n"
     "\t\t\t\tregion.weatherChanceClear = (seasonalChances[region.id][month][1]) - questStage\n"
     "\t\t\t\tregion.weatherChanceCloudy = seasonalChances[region.id][month][2]\n"
     "\t\t\t\tregion.weatherChanceFoggy = seasonalChances[region.id][month][3]\n"
     "\t\t\t\tregion.weatherChanceOvercast = seasonalChances[region.id][month][4]\n"
     "\t\t\t\tregion.weatherChanceRain = seasonalChances[region.id][month][5]\n"
     "\t\t\t\tregion.weatherChanceThunder = seasonalChances[region.id][month][6]\n"
     "\t\t\t\tregion.weatherChanceAsh = seasonalChances[region.id][month][7]\n"
     "\t\t\t\tregion.weatherChanceBlight = (seasonalChances[region.id][month][8]) + questStage\n"
     "\t\t\t\tregion.weatherChanceSnow = seasonalChances[region.id][month][9]\n"
     "\t\t\t\tregion.weatherChanceBlizzard = seasonalChances[region.id][month][10]\n"
     "\t\t\telseif seasonalChances[region.id] then\n",
     "\t\t\tif seasonalWeather.checkVv(region.id) and seasonalChances[region.id] and seasonalChances[region.id][month] then\n"
     "\t\t\t\tlocal chances = seasonalChances[region.id][month]\n"
     "\t\t\t\tregion.weatherChanceClear = math.max(0, (chances[1] or 0) - questStage)\n"
     "\t\t\t\tregion.weatherChanceCloudy = chances[2] or 0\n"
     "\t\t\t\tregion.weatherChanceFoggy = chances[3] or 0\n"
     "\t\t\t\tregion.weatherChanceOvercast = chances[4] or 0\n"
     "\t\t\t\tregion.weatherChanceRain = chances[5] or 0\n"
     "\t\t\t\tregion.weatherChanceThunder = chances[6] or 0\n"
     "\t\t\t\tregion.weatherChanceAsh = chances[7] or 0\n"
     "\t\t\t\tregion.weatherChanceBlight = (chances[8] or 0) + questStage\n"
     "\t\t\t\tregion.weatherChanceSnow = chances[9] or 0\n"
     "\t\t\t\tregion.weatherChanceBlizzard = chances[10] or 0\n"
     "\t\t\telseif seasonalChances[region.id] and seasonalChances[region.id][month] then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\t\t\t\t-- Otherwise just use regular stored values --\n"
     "\t\t\t\tregion.weatherChanceClear = seasonalChances[region.id][month][1]\n"
     "\t\t\t\tregion.weatherChanceCloudy = seasonalChances[region.id][month][2]\n"
     "\t\t\t\tregion.weatherChanceFoggy = seasonalChances[region.id][month][3]\n"
     "\t\t\t\tregion.weatherChanceOvercast = seasonalChances[region.id][month][4]\n"
     "\t\t\t\tregion.weatherChanceRain = seasonalChances[region.id][month][5]\n"
     "\t\t\t\tregion.weatherChanceThunder = seasonalChances[region.id][month][6]\n"
     "\t\t\t\tregion.weatherChanceAsh = seasonalChances[region.id][month][7]\n"
     "\t\t\t\tregion.weatherChanceBlight = seasonalChances[region.id][month][8]\n"
     "\t\t\t\tregion.weatherChanceSnow = seasonalChances[region.id][month][9]\n"
     "\t\t\t\tregion.weatherChanceBlizzard = seasonalChances[region.id][month][10]\n",
     "\t\t\t\t-- Otherwise just use regular stored values --\n"
     "\t\t\t\tlocal chances = seasonalChances[region.id][month]\n"
     "\t\t\t\tregion.weatherChanceClear = chances[1] or 0\n"
     "\t\t\t\tregion.weatherChanceCloudy = chances[2] or 0\n"
     "\t\t\t\tregion.weatherChanceFoggy = chances[3] or 0\n"
     "\t\t\t\tregion.weatherChanceOvercast = chances[4] or 0\n"
     "\t\t\t\tregion.weatherChanceRain = chances[5] or 0\n"
     "\t\t\t\tregion.weatherChanceThunder = chances[6] or 0\n"
     "\t\t\t\tregion.weatherChanceAsh = chances[7] or 0\n"
     "\t\t\t\tregion.weatherChanceBlight = chances[8] or 0\n"
     "\t\t\t\tregion.weatherChanceSnow = chances[9] or 0\n"
     "\t\t\t\tregion.weatherChanceBlizzard = chances[10] or 0\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\t\t\tend\n"
     "\t\tend\n"
     "\tend\n"
     "\n",
     "\t\t\tend\n"
     "\t\tend\n"
     "\n"
     "\t\t::continueRegion::\n"
     "\tend\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\t\t\tregionNow.name,\n"
     "\t\t\tregionNow.weatherChanceClear,\n"
     "\t\t\tregionNow.weatherChanceCloudy,\n"
     "\t\t\tregionNow.weatherChanceFoggy,\n"
     "\t\t\tregionNow.weatherChanceOvercast,\n"
     "\t\t\tregionNow.weatherChanceRain,\n"
     "\t\t\tregionNow.weatherChanceThunder,\n"
     "\t\t\tregionNow.weatherChanceAsh,\n"
     "\t\t\tregionNow.weatherChanceBlight,\n"
     "\t\t\tregionNow.weatherChanceSnow,\n"
     "\t\t\tregionNow.weatherChanceBlizzard\n",
     "\t\t\ttostring(regionNow.name or regionNow.id),\n"
     "\t\t\ttostring(regionNow.weatherChanceClear),\n"
     "\t\t\ttostring(regionNow.weatherChanceCloudy),\n"
     "\t\t\ttostring(regionNow.weatherChanceFoggy),\n"
     "\t\t\ttostring(regionNow.weatherChanceOvercast),\n"
     "\t\t\ttostring(regionNow.weatherChanceRain),\n"
     "\t\t\ttostring(regionNow.weatherChanceThunder),\n"
     "\t\t\ttostring(regionNow.weatherChanceAsh),\n"
     "\t\t\ttostring(regionNow.weatherChanceBlight),\n"
     "\t\t\ttostring(regionNow.weatherChanceSnow),\n"
     "\t\t\ttostring(regionNow.weatherChanceBlizzard)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\n"
     "function seasonalWeather.startTimer()\n"
     "\tmonthLast, regionLast = nil, nil\n",
     "\n"
     "function seasonalWeather.stopTimer()\n"
     "\tif seasonalWeatherTimer then\n"
     "\t\tseasonalWeatherTimer:cancel()\n"
     "\t\tseasonalWeatherTimer = nil\n"
     "\t\tdebugLog(\"Seasonal weather timer stopped.\")\n"
     "\tend\n"
     "end\n"
     "\n"
     "function seasonalWeather.startTimer()\n"
     "\tseasonalWeather.stopTimer()\n"
     "\tmonthLast, regionLast = nil, nil\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/seasonalweather.lua',
     "\ttimer.start {\n"
     "\t\tduration = common.centralTimerDuration,\n"
     "\t\tcallback = seasonalWeather.calculate,\n",
     "\tseasonalWeatherTimer = timer.start {\n"
     "\t\tduration = common.centralTimerDuration or 8,\n"
     "\t\tcallback = function()\n"
     "\t\t\tif tes3.menuMode() or not tes3.player then return end\n"
     "\t\t\tseasonalWeather.calculate()\n"
     "\t\tend,\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "local WtC = tes3.worldController.weatherController\n",
     "local function getWtC()\n"
     "\tlocal wc = tes3.worldController\n"
     "\treturn wc and wc.weatherController\n"
     "end\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "local variableRain = require(\"tew.Watch the Skies.services.variableRain\")\n"
     "\n",
     "local variableRain = require(\"tew.Watch the Skies.services.variableRain\")\n"
     "local skyTextureTimer = nil\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "function skyTexture.storeDefaults()\n"
     "\tfor i, w in ipairs(WtC.weathers) do\n",
     "function skyTexture.storeDefaults()\n"
     "\tlocal WtC = getWtC()\n"
     "\tif not (WtC and WtC.weathers) then return end\n"
     "\tfor i, w in ipairs(WtC.weathers) do\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\tif defaultSkyTextures[i] == \"\" then\n",
     "\t\tif w and defaultSkyTextures[i] == \"\" and w.cloudTexture then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\tskyTexture.storeDefaults()\n"
     "\tfor i, w in ipairs(WtC.weathers) do\n",
     "\tskyTexture.storeDefaults()\n"
     "\tlocal WtC = getWtC()\n"
     "\tif not (WtC and WtC.weathers) then return end\n"
     "\tfor i, w in ipairs(WtC.weathers) do\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\tif defaultSkyTextures[i] then\n",
     "\t\tif w and defaultSkyTextures[i] and defaultSkyTextures[i] ~= \"\" then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\t\tdebugLog(\"Restored default texture for weather: \" .. w.name .. \" - \" .. defaultSkyTextures[i])\n",
     "\t\t\tdebugLog(\"Restored default texture for weather: \" .. tostring(w.name) .. \" - \" .. tostring(defaultSkyTextures[i]))\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\tfor i = #list, 1, -1 do\n"
     "\t\t\tif list[i] == texturePath then\n"
     "\t\t\t\ttable.remove(list, i)\n"
     "\t\t\tend\n",
     "\t\tif list and texturePath and texturePath ~= \"\" then\n"
     "\t\t\tfor i = #list, 1, -1 do\n"
     "\t\t\t\tif list[i] == texturePath then\n"
     "\t\t\t\t\ttable.remove(list, i)\n"
     "\t\t\t\tend\n"
     "\t\t\tend\n"
     "\t\t\ttable.insert(list, texturePath)\n"
     "\t\t\tdebugLog(\"Vanilla texture added: \" .. texturePath)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\ttable.insert(list, texturePath)\n"
     "\t\tdebugLog(\"Vanilla texture added: \" .. texturePath)\n",
     ""),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\tfor i = #list, 1, -1 do\n"
     "\t\t\tif list[i] == texturePath then\n"
     "\t\t\t\ttable.remove(list, i)\n"
     "\t\t\t\tdebugLog(\"Vanilla texture removed: \" .. texturePath)\n",
     "\t\tif list and texturePath and texturePath ~= \"\" then\n"
     "\t\t\tfor i = #list, 1, -1 do\n"
     "\t\t\t\tif list[i] == texturePath then\n"
     "\t\t\t\t\ttable.remove(list, i)\n"
     "\t\t\t\t\tdebugLog(\"Vanilla texture removed: \" .. texturePath)\n"
     "\t\t\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "local function getNonRepeating(currentTexture, textureList)\n"
     "\tif #textureList == 1 then\n",
     "local function getNonRepeating(currentTexture, textureList)\n"
     "\tif not textureList or #textureList == 0 then return nil end\n"
     "\tif #textureList == 1 then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\tlocal weatherNow = WtC and WtC.currentWeather\n"
     "\tif WtC.nextWeather then return end\n",
     "\tif tes3.menuMode() or not tes3.player then return end\n"
     "\n"
     "\tlocal WtC = getWtC()\n"
     "\tif not (WtC and WtC.currentWeather and WtC.weathers) then return end\n"
     "\tif WtC.nextWeather then return end\n"
     "\n"
     "\tlocal isImmediate = (immediate == true)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\tlocal currentTexture = weatherNow.cloudTexture\n",
     "\tlocal weatherNow = WtC.currentWeather\n"
     "\tlocal currentTexture = weatherNow and weatherNow.cloudTexture\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\tfor index, weather in ipairs(WtC.weathers) do\n"
     "\t\t-- Skip the currently active weather if not immediate\n",
     "\tfor index, weather in ipairs(WtC.weathers) do\n"
     "\t\tif not weather then goto continue end\n"
     "\n"
     "\t\t-- Skip the currently active weather if not immediate\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\tif weatherNow and weatherNow.index == index and not immediate then\n",
     "\t\tif weatherNow and weatherNow.index == index and not isImmediate then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\tlocal textureList = skyTextures[index]\n"
     "\n",
     "\t\tlocal textureList = skyTextures[index]\n"
     "\t\tif not textureList then goto continue end\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\tif config.variableRain then\n",
     "\t\tif config and config.variableRain then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\t\t\tdebugLog(\"Detected rain type: \" .. rainType .. \", setting glare to: \" .. tostring(glare))\n",
     "\t\t\t\tdebugLog(\"Detected rain type: \" .. tostring(rainType) .. \", setting glare to: \" .. tostring(glare))\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\t\t\tcommon.rainType = rainType -- For interop\n"
     "\t\t\t\ttextureList = rainTextures[rainType]\n",
     "\t\t\t\tcommon.rainType = rainType -- For interop\n"
     "\t\t\t\tif rainTextures[rainType] and #rainTextures[rainType] > 0 then\n"
     "\t\t\t\t\ttextureList = rainTextures[rainType]\n"
     "\t\t\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\t\t\tvariableRain.adjustColours(rainType)\n"
     "\t\t\telse\n",
     "\t\t\t\tvariableRain.adjustColours(rainType)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\tlocal listUsed = (index == 5) and (\"rainTextures[\" .. variableRain.getRainType(weather.maxParticles or 0) .. \"]\") or\n",
     "\t\tlocal listUsed = (index == 5) and (\"rainTextures[\" .. tostring(variableRain.getRainType(weather.maxParticles or 0)) .. \"]\") or\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\t\tweather.name, listUsed, #textureList\n",
     "\t\t\ttostring(weather.name), listUsed, #textureList\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\t\t\tweather.cloudTexture = texturePath\n"
     "\t\t\tdebugLog(\"Cloud texture path set: \" .. weather.name .. \" >> \" .. weather.cloudTexture)\n",
     "\t\t\tif texturePath then\n"
     "\t\t\t\tweather.cloudTexture = texturePath\n"
     "\t\t\t\tdebugLog(\"Cloud texture path set: \" .. tostring(weather.name) .. \" >> \" .. tostring(weather.cloudTexture))\n"
     "\t\t\tend\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "\tif immediate then\n",
     "\tif isImmediate then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/skytexture.lua',
     "function skyTexture.startTimer()\n"
     "\t-- skyTexture.randomise() -- auto switch bug?\n"
     "\ttimer.start {\n"
     "\t\tduration = common.centralTimerDuration,\n"
     "\t\tcallback = skyTexture.randomise,\n",
     "function skyTexture.stopTimer()\n"
     "\tif skyTextureTimer then\n"
     "\t\tskyTextureTimer:cancel()\n"
     "\t\tskyTextureTimer = nil\n"
     "\t\tdebugLog(\"Sky texture timer stopped.\")\n"
     "\tend\n"
     "end\n"
     "\n"
     "function skyTexture.startTimer()\n"
     "\tskyTexture.stopTimer()\n"
     "\tskyTextureTimer = timer.start {\n"
     "\t\tduration = common.centralTimerDuration or 8,\n"
     "\t\tcallback = function()\n"
     "\t\t\tif tes3.menuMode() or not tes3.player then return end\n"
     "\t\t\tskyTexture.randomise(false)\n"
     "\t\tend,\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablefog.lua',
     "local function computeSeasonCurve(region, weatherIndex)\n"
     "    if not region then return 1.0 end\n",
     "local function computeSeasonCurve(region, weatherIndex)\n"
     "    if not (region and region.id) then return 1.0 end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablefog.lua',
     "    local month = tes3.worldController.month.value + 1\n",
     "    local wc = tes3.worldController\n"
     "    if not (wc and wc.month) then return 1.0 end\n"
     "\n"
     "    local month = (wc.month.value or 0) + 1\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablefog.lua',
     "    ----------------------------------------------------------------------------------\n"
     "    mge.weather.setDistantFog({\n",
     "    ----------------------------------------------------------------------------------\n"
     "    if not (mge and mge.weather and mge.weather.setDistantFog) then return end\n"
     "\n"
     "    mge.weather.setDistantFog({\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablefog.lua',
     "function variableFog.applyFog()\n"
     "    local region = tes3.getRegion(true)\n",
     "function variableFog.applyFog()\n"
     "    if tes3.menuMode() or not tes3.player then return end\n"
     "    if not (mge and mge.weather and mge.weather.setDistantFog) then return end\n"
     "\n"
     "    local region = tes3.getRegion({ useDoors = true }) or tes3.getRegion(true)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablefog.lua',
     "    if not (e and e.cell) then return end\n"
     "    local region = tes3.getRegion(true)\n",
     "    if tes3.menuMode() or not tes3.player then return end\n"
     "    local cell = (e and e.cell) or tes3.getPlayerCell()\n"
     "    if not cell then return end\n"
     "\n"
     "    local region = tes3.getRegion({ useDoors = true }) or tes3.getRegion(true)\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablefog.lua',
     "function variableFog.restoreDefaults()\n"
     "    for weatherIndex, preset in pairs(defaultFog) do\n",
     "function variableFog.restoreDefaults()\n"
     "    if not (mge and mge.weather and mge.weather.setDistantFog) then return end\n"
     "\n"
     "    for weatherIndex, preset in pairs(defaultFog) do\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablerain.lua',
     "    debugLog(\"Adjusting colours for rainType '\" .. rainType .. \"'\")\n",
     "    if tes3.menuMode() or not tes3.player then return end\n"
     "    if not rainType then return end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablerain.lua',
     "    local WtC        = tes3.worldController.weatherController\n"
     "    local srcIndex   = rainLookup[rainType].colourSource or 5\n"
     "    local src        = WtC.weathers[srcIndex]\n"
     "    local dst        = WtC.weathers[5]\n",
     "    local typeData = rainLookup[rainType] or rainLookup.light\n"
     "    if not typeData then return end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablerain.lua',
     "    local glare      = rainLookup[rainType].glare or defaultGlare\n"
     "    local brightness = rainLookup[rainType].brightness or 0.9\n"
     "    local desat      = rainLookup[rainType].desaturation or 0.72\n"
     "    local t          = 0.55\n",
     "    debugLog(\"Adjusting colours for rainType '\" .. tostring(rainType) .. \"'\")\n"
     "\n"
     "    local wc = tes3.worldController\n"
     "    local WtC = wc and wc.weatherController\n"
     "    if not (WtC and WtC.weathers) then return end\n"
     "\n"
     "    local srcIndex = typeData.colourSource or 5\n"
     "    local src = WtC.weathers[srcIndex]\n"
     "    local dst = WtC.weathers[5]\n"
     "    if not (src and dst) then return end\n"
     "\n"
     "    local glare = typeData.glare or defaultGlare\n"
     "    local brightness = typeData.brightness or 0.9\n"
     "    local desat = typeData.desaturation or 0.72\n"
     "    local t = 0.55\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablerain.lua',
     "        if src == dst then goto continue end\n"
     "\n",
     "        if src == dst then goto continue end\n"
     "        if not (src[key] and dst[key]) then goto continue end\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablerain.lua',
     "function variableRain.restoreDefaultRainColours()\n"
     "    local WtC = tes3.worldController.weatherController\n",
     "function variableRain.restoreDefaultRainColours()\n"
     "    local wc = tes3.worldController\n"
     "    local WtC = wc and wc.weatherController\n"
     "    if not (WtC and WtC.weathers) then return end\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablerain.lua',
     "    local rainWeather = WtC.weathers[5]\n"
     "    if not defaultColors then\n",
     "    local rainWeather = WtC.weathers[5]\n"
     "    if not rainWeather then return end\n"
     "\n"
     "    if not defaultColors then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablerain.lua',
     "    for name, col in pairs(defaultColors) do\n"
     "        rainWeather[name] = col\n",
     "    for name, col in pairs(defaultColors) do\n"
     "        if name ~= \"glareView\" and rainWeather[name] then\n"
     "            rainWeather[name] = col\n"
     "        end\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablerain.lua',
     "    rainWeather.glareView = defaultGlare\n",
     "    rainWeather.glareView = defaultColors.glareView or defaultGlare\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablerain.lua',
     "    local WtC = tes3.worldController.weatherController\n"
     "    if not WtC then\n",
     "    local wc = tes3.worldController\n"
     "    local WtC = wc and wc.weatherController\n"
     "    if not (WtC and WtC.weathers) then\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablerain.lua',
     "    local rainWeather = WtC.weathers[5]\n"
     "\n",
     "    local rainWeather = WtC.weathers[5]\n"
     "    if not rainWeather then return end\n"
     "\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablerain.lua',
     "        glareView = rainWeather.glareView,\n",
     "        glareView = rainWeather.glareView or defaultGlare,\n"),
    ("KB50", 'Watch the Skies', 'tew/watch the skies/services/variablerain.lua',
     "\n"
     "        defaultColors[key] = {\n"
     "            r = c.r,\n"
     "            g = c.g,\n"
     "            b = c.b,\n"
     "        }\n",
     "        if c then\n"
     "            defaultColors[key] = {\n"
     "                r = c.r,\n"
     "                g = c.g,\n"
     "                b = c.b,\n"
     "            }\n"
     "        end\n"),
]

RULES = [(rule, owner, path, old, new, WHAT[rule]) for rule, owner, path, old, new in PARTS]
