--[[ mwconsole commands: items and objects (additem, dupe, setownership, unlock, untrap). ]]
local util = require("mwconsole.commands.util")

return function(add)
    add({ name = "additem", description = "Give the target an item",
          arguments = { { index = 1, metavar = "id", required = true, argKind = "item" },
                        { index = 2, metavar = "count", required = false } },
          callback = function(argv, ctx)
              local ref = util.target(ctx)
              local item = tes3.getObject(argv[1])
              if not item then util.print(ctx, "additem: no item %s", argv[1]) return end
              local n = math.max(1, util.int(argv[2], 1))
              tes3.addItem({ reference = ref, item = item, count = n, playSound = false })
              util.print(ctx, "added %d x %s to %s", n, item.id, util.name(ref))
          end })

    add({ name = "dupe", description = "Add copies of the selected item to your inventory",
          arguments = { { index = 1, metavar = "count", required = false } },
          callback = function(argv, ctx)
              local ref = ctx.ref or tes3ui.getConsoleReference()
              if not ref then util.print(ctx, "dupe: select an item in the console first") return end
              local n = math.max(1, util.int(argv[1], 1))
              local ok = pcall(tes3.addItem, { reference = tes3.player, item = ref.object, count = n, playSound = false })
              util.print(ctx, ok and ("added %d x %s"):format(n, ref.object.id) or ("dupe: %s can't be carried"):format(ref.object.id))
          end })

    add({ name = "setownership", description = "Set the selected object's owner (an NPC or faction ID), or clear it",
          arguments = { { index = 1, metavar = "id", required = false, argKind = "object" } },
          callback = function(argv, ctx)
              local ref = ctx.ref or tes3ui.getConsoleReference()
              if not ref then util.print(ctx, "setownership: select an object in the console first") return end
              if not argv[1] then
                  tes3.setOwner({ reference = ref, remove = true })
                  util.print(ctx, "%s has no owner now", ref.id)
                  return
              end
              local owner = tes3.getObject(argv[1]) or tes3.getFaction(argv[1])
              if not owner then util.print(ctx, "setownership: no NPC or faction %s", argv[1]) return end
              tes3.setOwner({ reference = ref, owner = owner })
              util.print(ctx, "%s is owned by %s", ref.id, owner.id)
          end })

    add({ name = "unlock", description = "Unlock the selected door or container",
          callback = function(_, ctx)
              local ref = ctx.ref or tes3ui.getConsoleReference()
              if not ref then util.print(ctx, "unlock: select a door or container") return end
              tes3.unlock({ reference = ref })
              util.print(ctx, "unlocked %s", ref.id)
          end })

    add({ name = "untrap", description = "Remove the trap from the selected door or container",
          callback = function(_, ctx)
              local ref = ctx.ref or tes3ui.getConsoleReference()
              if not ref then util.print(ctx, "untrap: select a door or container") return end
              tes3.setTrap({ reference = ref, spell = nil })
              util.print(ctx, "untrapped %s", ref.id)
          end })
end
