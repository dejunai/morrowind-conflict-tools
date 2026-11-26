--[[ mwconsole commands: help, cls, lookup, qqq, sel. ]]
local config = require("mwconsole.config")
local registry = require("mwconsole.registry")
local console_ui = require("mwconsole.console_ui")
local index = require("mwconsole.complete.index")
local util = require("mwconsole.commands.util")

local function quit()
    -- mwexitguard (if on) leaves through its clean fast exit, which has no public function: do the same
    local eg = config.compat.useMwexitguard and package.loaded["mwexitguard.config"]
    if type(eg) == "table" and eg.enabled then
        local okF, ffi = pcall(require, "ffi")
        if okF then
            pcall(ffi.cdef, "void ExitProcess(unsigned int uExitCode);")
            ffi.C.ExitProcess(0)
        end
    end
    os.exit()
end

return function(add)
    add({ name = "help", description = "List console commands, or show one: help <command>", needsGame = false,
          arguments = { { index = 1, metavar = "command", required = false } },
          callback = function(argv, ctx)
              if argv[1] then
                  local e = registry.resolve(argv[1])
                  if not e then util.print(ctx, "help: no command %s", argv[1]) return end
                  util.print(ctx, registry.usage(e))
                  util.print(ctx, "%s [%s]", e.description or "", e.source or "?")
                  if #e.aliases > 0 then util.print(ctx, "aliases: %s", table.concat(e.aliases, ", ")) end
                  return
              end
              for _, e in ipairs(registry.list()) do
                  util.print(ctx, "%-16s %s%s", e.name, e.description or "",
                      e.kind == "user" and " (user)" or (e.source ~= "mwconsole" and (" (" .. e.source .. ")") or ""))
              end
          end })

    add({ name = "cls", description = "Clear the console", needsGame = false,
          callback = function() console_ui.clear() end })

    add({ name = "lookup", description = "Find object IDs or names containing some text",
          arguments = { { index = 1, metavar = "name", required = true },
                        { index = 2, metavar = "objecttype", required = false } },
          callback = function(argv, ctx)
              local text = argv[1]:lower()
              local wantType = argv[2] and tes3.objectType[argv[2]] or nil
              if argv[2] and not wantType then
                  for k, v in pairs(tes3.objectType) do if k:lower() == argv[2]:lower() then wantType = v end end
              end
              local n = 0
              for obj in tes3.iterateObjects(wantType) do
                  local name = obj.name
                  if obj.id:lower():find(text, 1, true) or (type(name) == "string" and name:lower():find(text, 1, true)) then
                      n = n + 1
                      if n <= 50 then util.print(ctx, "%s  %s", obj.id, name or "") end
                  end
              end
              util.print(ctx, n > 50 and ("%d found, first 50 shown"):format(n) or ("%d found"):format(n))
          end })

    add({ name = "qqq", aliases = { "quitgame" }, description = "Quit the game now, without saving", needsGame = false,
          callback = function() quit() end })

    add({ name = "sel", aliases = { "selinfo" }, description = "Print the selection panel's details into the console (sel log: also MWSE.log)",
          arguments = { { index = 1, metavar = "log", required = false, choices = { "log" } } },
          callback = function(argv, ctx)
              require("mwconsole.selection.panel").printRows(ctx.ref, argv[1] == "log")
          end })

    add({ name = "mwconsole", description = "mwconsole status", needsGame = false,
          callback = function(_, ctx)
              local n = 0
              for _ in pairs(registry.commands) do n = n + 1 end
              util.print(ctx, "mwconsole: %d commands; ID list %s (%d IDs, %.0f ms)", n,
                  index.built and "built" or "not built yet", index.count, index.buildMs)
          end })
end
