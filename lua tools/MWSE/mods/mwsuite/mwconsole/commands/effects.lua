--[[ mwconsole commands: the effect inspector family (showeffects, cleareffects and their aliases). ]]
local window = require("mwconsole.effects.window")

return function(add)
    add({ name = "showeffects", aliases = { "effects", "inspecteffects", "magiceffects", "/inspecteffects", "/showeffects" },
          description = "Inspect the magic effects, abilities, enchantments and visual effects on the target",
          callback = function(_, ctx)
              local ref = ctx.ref or window.defaultTarget()
              if ref then window.printSummary(ref) end
              window.open(ref)
          end })
    add({ name = "cleareffects", aliases = { "dispel", "purgeeffects", "removeeffects", "/cleareffects", "/dispel" },
          description = "Remove every active magic effect from the target",
          callback = function(_, ctx) window.purge(ctx.ref or window.defaultTarget()) end })
end
