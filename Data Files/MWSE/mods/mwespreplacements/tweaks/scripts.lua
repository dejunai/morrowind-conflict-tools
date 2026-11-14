local scripts = {}

function scripts.apply(config)
    if not config.enabled then return end

    -- 1. Stolen Goldbrand Eltonbrand Fix (replaces Stolen Goldbrand Eltonbrand Fix.ESP)
    -- Implemented via pure MWSE simulation hook (no engine script recompilation)
    if config.stolenGoldbrandEltonbrandFix then
        event.register(tes3.event.simulate, function()
            if tes3.getLegacyScriptRunning({ script = "blueScript" }) then
                local player = tes3.player
                if player and tes3.getItemCount({ reference = player, item = "katana_goldbrand_unique_x" }) == 1 then
                    if tes3.getItemCount({ reference = player, item = "gold_001" }) == 11171 then
                        tes3.removeItem({ reference = player, item = "katana_goldbrand_unique_x", count = 1 })
                        tes3.addItem({ reference = player, item = "katana_bluebrand_unique", count = 1 })
                        -- tes3.messageBox("Go to Hell, Carolina!")
                        tes3.stopLegacyScript({ script = "blueScript" })
                    end
                end
            end
        end)
    end

    -- 2. Sotha Sil Expanded Farmer Note Fix (replaces Sotha Sil Expanded - Script Fix.esp)
    -- Advances journal Sotha_farmer1 to 20 when reading or acquiring sotha_farmernote1
    if config.sothaSilExpandedNoteFix then
        event.register(tes3.event.bookGetText, function(e)
            if e.book and e.book.id:lower() == "sotha_farmernote1" then
                if tes3.getJournalIndex({ id = "Sotha_farmer1" }) < 20 then
                    tes3.updateJournal({ id = "Sotha_farmer1", index = 20 })
                end
            end
        end)
        event.register(tes3.event.itemTileUpdated, function(e)
            if e.item and e.item.id:lower() == "sotha_farmernote1" then
                if tes3.getJournalIndex({ id = "Sotha_farmer1" }) < 20 then
                    tes3.updateJournal({ id = "Sotha_farmer1", index = 20 })
                end
            end
        end, { filter = "MenuInventory" })
    end

    -- 3. DA Sobitur Level 40 Sleep Check Fix (replaces DA_Sobitur_Quest_Part_1 Clean - Script Fix.esp)
    -- Triggers the quest starter note upon sleeping when player level is 40 or higher
    if config.sobiturLevel40CheckFix then
        event.register(tes3.event.calcRestInterrupt, function(e)
            if e.resting and tes3.player and tes3.player.object.level >= 40 then
                if tes3.getJournalIndex({ id = "DA_sobitur_01" }) < 10 then
                    tes3.updateJournal({ id = "DA_sobitur_01", index = 10 })
                    tes3.addItem({ reference = tes3.player, item = "_DA_aryonnote_01", count = 1 })
                    tes3.addTopic({ topic = "disturbing revelation" })
                end
            end
        end)
    end
end

return scripts
