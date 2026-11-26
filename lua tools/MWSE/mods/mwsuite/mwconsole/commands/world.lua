--[[ mwconsole commands: world (time, weather). ]]
local util = require("mwconsole.commands.util")

local WEATHERS = { "clear", "cloudy", "foggy", "overcast", "rain", "thunder", "ash", "blight", "snow", "blizzard" }

return function(add)
    add({ name = "time", description = "Set the hour: time 14 or time 14:30",
          arguments = { { index = 1, metavar = "time", required = true } },
          callback = function(argv, ctx)
              local h, m = argv[1]:match("^(%d+):?(%d*)$")
              h, m = tonumber(h), tonumber(m) or 0
              if not h or h > 23 or m > 59 then util.print(ctx, "time: use hours 0-23, e.g. time 7 or time 19:30") return end
              tes3.worldController.hour.value = h + m / 60
              util.print(ctx, "time is %02d:%02d", h, m)
          end })

    add({ name = "weather", aliases = { "forceweather", "fw" }, description = "Change the weather now",
          arguments = { { index = 1, metavar = "weather", required = true, choices = WEATHERS } },
          callback = function(argv, ctx)
              local idx = tes3.weather[argv[1]]
              if not idx then util.print(ctx, "weather: unknown %s", argv[1]) return end
              local wc = tes3.worldController.weatherController
              wc:switchImmediate(idx)
              pcall(function() wc:updateVisuals() end)
              util.print(ctx, "weather: %s", argv[1])
          end })
end
