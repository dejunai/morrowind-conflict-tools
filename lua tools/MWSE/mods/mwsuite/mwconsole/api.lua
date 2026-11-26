--[[
    mwconsole extension API for other mods:  local api = include("mwconsole.api")   (nil without mwconsole)
      api.registerCommand{ name, description, callback(argv, ctx), aliases?, arguments?, context = "lua"|"any",
                           needsGame = true, override = false }      ctx = { ref, context, print, raw, words }
      api.unregisterCommand(name)            only the mod that registered it
      api.registerCompletion(kind, provider(prefix) -> list)   a new ID kind for argKind
      api.openWindow{ id, build(menu, win), onClose?, modal = true, needsGame = true }   follows mwconsole's
                                             window rules (game check, error capture, one close path; Esc closes
                                             the window on top; every window closes when menu mode ends)
      mwconsole's built-ins (showeffects, cleareffects and their aliases among them) can't be taken: a name or
      alias that is already mwconsole's is refused on both routes, override included.
      api.isGameLoaded(), api.version
    Events: "mwconsole:selectionRows" { reference, rows } (append rows), "mwconsole:commandRun" { name, source, ok }.
    The owning mod is read from the calling file's folder (call the API directly, not as `return api.x(...)`).
    Mods that should also work with More Console Commands can use include("JosephMcKean.commands.interop") instead.
]]
local registry = require("mwconsole.registry")
local guard = require("mwconsole.guard")
local index = require("mwconsole.complete.index")
local compat = require("mwconsole.compat_mcc")

local api = { version = "1.0.0" }

function api.registerCommand(def)
    if type(def) ~= "table" then return false, "registerCommand needs a table" end
    local source = compat.callerSource(3)
    return registry.register(def, { source = source, kind = "mod", native = true, override = def.override == true })
end

function api.unregisterCommand(name)
    return registry.unregister(tostring(name), compat.callerSource(3))
end

function api.registerCompletion(kind, provider)
    if type(kind) ~= "string" or type(provider) ~= "function" then return false end
    index.registerProvider(kind, provider)
    return true
end

function api.openWindow(spec)
    if type(spec) ~= "table" or type(spec.id) ~= "string" or type(spec.build) ~= "function" then
        return nil, "openWindow needs id and build"
    end
    return guard.openWindow({ id = spec.id, title = spec.title, where = spec.where or ("open " .. spec.id),
        build = spec.build, onClose = spec.onClose, modal = spec.modal, needsGame = spec.needsGame,
        dragFrame = spec.dragFrame })
end

function api.isGameLoaded() return guard.isGameLoaded() end

return api
