--[[ mwconsole commands: stats (cure, join, levelup, max, set, skills, speedy). ]]
local util = require("mwconsole.commands.util")

local function setBase(ref, kind, id, value)
    tes3.setStatistic({ reference = ref, [kind] = id, value = value })
end

--- Skills Module (or the older OtherSkills) custom skills, read at runtime; nil if not installed
local function customSkill(id)
    local sm = include("SkillsModule")
    if sm and sm.getSkill then
        local ok, s = pcall(sm.getSkill, id)
        if ok and s then return s, "SkillsModule" end
    end
    local os2 = include("OtherSkills.skillModule")
    if os2 and os2.getSkill then
        local ok, s = pcall(os2.getSkill, id)
        if ok and s then return s, "OtherSkills" end
    end
    return nil
end

return function(add)
    add({ name = "cure", description = "Cure the target's diseases, blight, poison and drained stats",
          callback = function(_, ctx)
              local ref = util.target(ctx)
              local mobile = util.needMobile(ctx, ref)
              if not mobile then return end
              for _, t in ipairs({ tes3.spellType.disease, tes3.spellType.blight, tes3.spellType.curse }) do
                  pcall(tes3.removeEffects, { reference = ref, castType = t, removeSpell = true })
              end
              for _, eff in ipairs({ "poison", "drainAttribute", "drainSkill", "damageAttribute", "damageSkill",
                                     "drainHealth", "drainMagicka", "drainFatigue", "paralyze", "silence", "blind" }) do
                  if tes3.effect[eff] then pcall(tes3.removeEffects, { reference = ref, effect = tes3.effect[eff] }) end
              end
              for i = 0, 7 do
                  pcall(function()
                      local stat = mobile.attributes[i + 1]
                      if stat.current < stat.base then tes3.setStatistic({ reference = ref, attribute = i, current = stat.base }) end
                  end)
              end
              util.print(ctx, "cured %s", util.name(ref))
          end })

    add({ name = "join", aliases = { "addtofaction" }, description = "Make the player join a faction at a rank (1-10)",
          arguments = { { index = 1, metavar = "faction-id", required = true, argKind = "faction" },
                        { index = 2, metavar = "rank", required = false } },
          callback = function(argv, ctx)
              local faction = tes3.getFaction(argv[1])
              if not faction then util.print(ctx, "join: no faction %s", argv[1]) return end
              local rank = math.max(1, math.min(10, util.int(argv[2], 1)))
              faction.playerJoined = true
              faction.playerExpelled = false
              faction.playerRank = rank - 1
              util.print(ctx, "joined %s at rank %d", faction.name or faction.id, rank)
          end })

    add({ name = "levelup", description = "Raise a Skills Module skill (or a vanilla skill) of the player",
          arguments = { { index = 1, metavar = "skillname", required = true }, { index = 2, metavar = "value", required = false } },
          callback = function(argv, ctx)
              local by = util.int(argv[2], 1)
              local vanilla = util.skillId(argv[1])
              if vanilla then
                  tes3.modStatistic({ reference = tes3.player, skill = vanilla, value = by })
                  util.print(ctx, "%s raised by %d", tes3.skillName[vanilla], by)
                  return
              end
              local skill, lib = customSkill(argv[1])
              if not skill then util.print(ctx, "levelup: no skill %s", argv[1]) return end
              local ok = pcall(function()
                  if lib == "SkillsModule" and skill.levelUp then
                      for _ = 1, by do skill:levelUp() end
                  elseif skill.levelUpSkill then
                      skill:levelUpSkill(by)
                  else
                      skill.current = (skill.current or skill.value or 0) + by
                  end
              end)
              util.print(ctx, ok and ("%s raised by %d"):format(argv[1], by) or ("levelup: couldn't raise " .. argv[1]))
          end })

    add({ name = "max", description = "Set all attributes and skills of the target to a value",
          arguments = { { index = 1, metavar = "value", required = true } },
          callback = function(argv, ctx)
              local ref = util.target(ctx)
              if not util.needMobile(ctx, ref) then return end
              local v = util.int(argv[1])
              if not v then util.print(ctx, "max: give a number") return end
              for i = 0, 7 do setBase(ref, "attribute", i, v) end
              if ref.mobile.skills then for i = 0, 26 do pcall(setBase, ref, "skill", i, v) end end
              util.print(ctx, "%s: attributes and skills set to %d", util.name(ref), v)
          end })

    add({ name = "set", description = "Set one attribute, skill, or health/magicka/fatigue of the target",
          arguments = { { index = 1, metavar = "name", required = true }, { index = 2, metavar = "value", required = true } },
          callback = function(argv, ctx)
              local ref = util.target(ctx)
              if not util.needMobile(ctx, ref) then return end
              local v = tonumber(argv[2])
              if not v then util.print(ctx, "set: give a number") return end
              local n = argv[1]:lower()
              if n == "health" or n == "magicka" or n == "fatigue" then
                  tes3.setStatistic({ reference = ref, name = n, value = v })
              elseif util.attributeId(n) then
                  setBase(ref, "attribute", util.attributeId(n), v)
              elseif util.skillId(n) then
                  setBase(ref, "skill", util.skillId(n), v)
              else
                  util.print(ctx, "set: no attribute or skill called %s", argv[1])
                  return
              end
              util.print(ctx, "%s: %s set to %s", util.name(ref), argv[1], argv[2])
          end })

    add({ name = "skills", description = "List the target's skills",
          callback = function(_, ctx)
              local ref = util.target(ctx)
              local mobile = util.needMobile(ctx, ref)
              if not mobile then return end
              if not mobile.skills then util.print(ctx, "%s has no skills (creature)", util.name(ref)) return end
              for i = 0, 26 do
                  local s = mobile.skills[i + 1]
                  if s then util.print(ctx, "%-14s %d (base %d)", tes3.skillName[i] or i, s.current, s.base) end
              end
          end })

    add({ name = "speedy", description = "Set the player's Speed and Athletics to 200",
          callback = function(_, ctx)
              setBase(tes3.player, "attribute", tes3.attribute.speed, 200)
              setBase(tes3.player, "skill", tes3.skill.athletics, 200)
              util.print(ctx, "speed and athletics set to 200")
          end })
end
