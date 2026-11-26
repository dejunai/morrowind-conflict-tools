--[[ mwconsole commands: gold. ]]
local util = require("mwconsole.commands.util")

local GOLD = "gold_001"

local function addGold(ctx, ref, n)
    tes3.addItem({ reference = ref, item = GOLD, count = n, playSound = false })
    util.print(ctx, "%s now has %d gold", util.name(ref), tes3.getItemCount({ reference = ref, item = GOLD }))
end

return function(add)
    add({ name = "kaching", description = "Give the target 1,000 gold",
          callback = function(_, ctx) addGold(ctx, util.target(ctx), 1000) end })
    add({ name = "motherlode", description = "Give the target 50,000 gold",
          callback = function(_, ctx) addGold(ctx, util.target(ctx), 50000) end })
    add({ name = "money", description = "Set the target's gold to an amount",
          arguments = { { index = 1, metavar = "goldcount", required = true, help = "how much gold to have" } },
          callback = function(argv, ctx)
              local ref = util.target(ctx)
              local want = util.int(argv[1])
              if not want or want < 0 then util.print(ctx, "money: give a number, e.g. money 500") return end
              local have = tes3.getItemCount({ reference = ref, item = GOLD })
              if have > want then
                  tes3.removeItem({ reference = ref, item = GOLD, count = have - want, playSound = false })
              elseif want > have then
                  tes3.addItem({ reference = ref, item = GOLD, count = want - have, playSound = false })
              end
              util.print(ctx, "%s now has %d gold", util.name(ref), want)
          end })
end
