--[[ mwconsole commands: travel (coc, fly, mark, recall, position). Marks are kept in the save (player data). ]]
local util = require("mwconsole.commands.util")

local function marks()
    local data = tes3.player.data
    data.mwconsole = data.mwconsole or {}
    data.mwconsole.marks = data.mwconsole.marks or {}
    return data.mwconsole.marks
end

local function runConsole(line)
    return tes3.runLegacyScript({ command = line, source = tes3.compilerSource and tes3.compilerSource.console or nil })
end

return function(add)
    add({ name = "coc", description = "Go to a cell by name, or to exterior grid x y",
          arguments = { { index = 1, metavar = "cell", required = true, containsSpaces = true, argKind = "cell" } },
          caseSensitive = true,
          callback = function(argv, ctx)
              local x, y = argv[1]:match("^%s*(%-?%d+)[%s,]+(%-?%d+)%s*$")
              if x then
                  runConsole(string.format("COE %d %d", tonumber(x), tonumber(y)))
              else
                  local id = argv[1]:gsub('"', "")
                  if not tes3.getCell({ id = id }) then util.print(ctx, "coc: no cell %s", id) return end
                  runConsole(string.format('COC "%s"', id))
              end
          end })

    add({ name = "fly", description = "Turn levitation on or off for the player",
          callback = function(_, ctx)
              local m = tes3.mobilePlayer
              local on = (m.levitate or 0) <= 0
              m.levitate = on and 1 or 0
              util.print(ctx, on and "flying" or "not flying")
          end })

    add({ name = "mark", description = "Save where you are under a name (mark lists the saved places)",
          arguments = { { index = 1, metavar = "id", required = false } },
          callback = function(argv, ctx)
              local list = marks()
              if not argv[1] then
                  local any = false
                  for id, m in pairs(list) do
                      any = true
                      util.print(ctx, "%s: %s (%.0f, %.0f, %.0f)", id, m.cell or "exterior", m.x, m.y, m.z)
                  end
                  if not any then util.print(ctx, "no marks; use mark <id>") end
                  return
              end
              local p = tes3.player
              local cell = p.cell
              list[argv[1]] = { cell = cell.isInterior and cell.id or nil, x = p.position.x, y = p.position.y,
                                z = p.position.z, rz = p.orientation.z }
              util.print(ctx, "marked %s", argv[1])
          end })

    add({ name = "recall", description = "Go back to a place saved with mark",
          arguments = { { index = 1, metavar = "id", required = false } },
          callback = function(argv, ctx)
              local list = marks()
              local id = argv[1]
              if not id then for k in pairs(list) do id = k break end end
              local m = id and list[id]
              if not m then util.print(ctx, "recall: no mark %s", tostring(id)) return end
              tes3.positionCell({ reference = tes3.player, cell = m.cell, position = { m.x, m.y, m.z },
                                  orientation = { 0, 0, m.rz or 0 } })
          end })

    add({ name = "position", description = "Go to a character or object by its ID",
          arguments = { { index = 1, metavar = "id", required = true, argKind = "object" } },
          callback = function(argv, ctx)
              local ref = tes3.getReference(argv[1])
              if not ref or not ref.cell then util.print(ctx, "position: no loaded reference %s", argv[1]) return end
              tes3.positionCell({ reference = tes3.player, cell = ref.cell, position = ref.position,
                                  orientation = tes3.player.orientation })
          end })
end
