--[[ mwconsole commands: actors (emptyinventory, follow, kill, killall, peace, resurrect, showinventory, spawn,
     wander). Commands that would act on the player ask for the word "player" first. ]]
local config = require("mwconsole.config")
local util = require("mwconsole.commands.util")

local function activeActors()
    local list = {}
    for _, cell in ipairs(tes3.getActiveCells()) do
        for ref in cell:iterateReferences({ tes3.objectType.npc, tes3.objectType.creature }) do
            if ref.mobile and not ref.disabled and not ref.deleted then list[#list + 1] = ref end
        end
    end
    return list
end

local function companionsCore()
    if not config.compat.useMwcompanions then return nil end
    return include("mwcompanions.core")
end

return function(add)
    add({ name = "emptyinventory", description = "Remove everything the target carries (type 'player' for yourself)",
          arguments = { { index = 1, metavar = "player", required = false, choices = { "player" } } },
          callback = function(argv, ctx)
              local ref = util.target(ctx)
              if util.isPlayer(ref) and argv[1] ~= "player" then
                  util.print(ctx, "emptyinventory: this is you; type emptyinventory player to empty your own inventory")
                  return
              end
              local stacks = {}
              for _, stack in pairs(ref.object.inventory) do stacks[#stacks + 1] = { stack.object, stack.count } end
              for _, s in ipairs(stacks) do
                  pcall(tes3.removeItem, { reference = ref, item = s[1], count = math.abs(s[2]), playSound = false })
              end
              util.print(ctx, "emptied %s (%d stacks)", util.name(ref), #stacks)
          end })

    add({ name = "follow", description = "Make the selected character follow you",
          callback = function(_, ctx)
              local ref = util.target(ctx)
              if util.isPlayer(ref) or not util.needMobile(ctx, ref) then return end
              tes3.setAIFollow({ reference = ref, target = tes3.player })
              local core = companionsCore()
              local note = ""
              if core and core.isFollower then
                  local ok, yes = pcall(core.isFollower, ref.mobile)
                  if ok and yes then note = " (mwcompanions counts them as a companion)" end
              end
              util.print(ctx, "%s follows you%s", util.name(ref), note)
          end })

    add({ name = "kill", description = "Kill the target (type 'player' for yourself)",
          arguments = { { index = 1, metavar = "player", required = false, choices = { "player" } } },
          callback = function(argv, ctx)
              local ref = util.target(ctx)
              if util.isPlayer(ref) and argv[1] ~= "player" then
                  util.print(ctx, "kill: this is you; type kill player to really do it")
                  return
              end
              if not util.needMobile(ctx, ref) then return end
              ref.mobile:kill()
              util.print(ctx, "killed %s", util.name(ref))
          end })

    add({ name = "killall", description = "Kill every hostile-capable character and creature nearby (not you, not essential ones)",
          callback = function(_, ctx)
              local n = 0
              for _, ref in ipairs(activeActors()) do
                  local essential = false
                  pcall(function() essential = ref.object.isEssential end)
                  if ref ~= tes3.player and not essential and not ref.mobile.isDead then
                      pcall(function() ref.mobile:kill() end)
                      n = n + 1
                  end
              end
              util.print(ctx, "killed %d", n)
          end })

    add({ name = "peace", description = "Stop all fights nearby",
          callback = function(_, ctx)
              local n = 0
              for _, ref in ipairs(activeActors()) do
                  if ref ~= tes3.player then
                      pcall(function()
                          ref.mobile:stopCombat(true)
                          ref.mobile.fight = math.min(ref.mobile.fight or 0, 30)
                      end)
                      n = n + 1
                  end
              end
              util.print(ctx, "calmed %d", n)
          end })

    add({ name = "resurrect", description = "Bring the target back to life, keeping its inventory",
          callback = function(_, ctx)
              local ref = util.target(ctx)
              if not util.needMobile(ctx, ref) then return end
              ref.mobile:resurrect({ resetState = false })
              util.print(ctx, "resurrected %s", util.name(ref))
          end })

    add({ name = "showinventory", description = "List what the target carries",
          callback = function(_, ctx)
              local ref = util.target(ctx)
              local inv = ref.object and ref.object.inventory
              if not inv then util.print(ctx, "%s has no inventory", util.name(ref)) return end
              local n = 0
              for _, stack in pairs(inv) do
                  n = n + 1
                  util.print(ctx, "%5d x %s (%s)", math.abs(stack.count), stack.object.name or "", stack.object.id)
              end
              if n == 0 then util.print(ctx, "%s carries nothing", util.name(ref)) end
          end })

    add({ name = "spawn", aliases = { "summon" }, description = "Place a new copy of an object in front of you",
          arguments = { { index = 1, metavar = "id", required = true, argKind = "object" } },
          callback = function(argv, ctx)
              local obj = tes3.getObject(argv[1])
              if not obj then util.print(ctx, "spawn: no object %s", argv[1]) return end
              local p = tes3.player
              local fwd = p.forwardDirection or tes3vector3.new(0, 1, 0)
              local pos = p.position + fwd * 128
              tes3.createReference({ object = obj, position = pos, orientation = p.orientation, cell = p.cell })
              util.print(ctx, "spawned %s", obj.id)
          end })

    add({ name = "wander", description = "Make the selected character wander where they are",
          callback = function(_, ctx)
              local ref = util.target(ctx)
              if util.isPlayer(ref) or not util.needMobile(ctx, ref) then return end
              tes3.setAIWander({ reference = ref, range = 400, idles = { 40, 30, 30, 0, 0, 0, 0, 0 } })
              util.print(ctx, "%s wanders", util.name(ref))
          end })
end
