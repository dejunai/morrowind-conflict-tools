# luafix KP1-KP4: handoff to mwsuite (intercept candidates)

Written 2026-11-26 when KP1-KP4 were removed from `mwdialog_luafix.py`. luafix fixes outright Lua bugs only; these
four were performance patches (each kept what the mod does and did less work for it), so they belong with mwsuite's
runtime intercepts, not with exact-text patches of third-party Lua.

## What happens to files already patched

- A mod file luafix already patched with a KP entry keeps that patch: luafix no longer knows the KP text, so it
  neither re-applies nor removes it. The file's `--[[localpatch N: ...]]` header still lists the KP id.
- `python mwdialog_luafix.py --undo` (or `vortex_tidy --undo`) of the run that applied it puts the original back,
  as before; reinstalling the mod in Vortex does too.
- An intercept that mwsuite adds for one of these must expect either form of the file (patched or original), or
  check for the `-- local fix (KPn)` comment and stand down, so the two never apply together.

## The four items

### KP1: Attend Me MWSE (`MWSE\mods\attendmemwse\actions.lua`)

rayWorld casts the same 65536-unit eye ray up to four times in one frame while the command wheel is open (refreshDynamicLabels every 5th frame: Move, Loot and Action each cast one; updateContextTargetHud every 3rd); within one onSimulate pass the world does not change, so one ray per ignore set gives the same answer (those callers read only .reference; MWSE reuses one result object per rayTest, so the frame keeps the reference, not the result)

One eye ray per ignore set per frame while the command wheel is open. Intercept idea: wrap the mod's `simulate` handler (or `tes3.rayTest` for the duration of that handler only) with a per-frame memo keyed by the ignore set, keeping only `.reference` from each result (MWSE reuses one result object per rayTest). The memo must be cleared when the handler returns, also on error.

The luafix patch as it was (3 exact-text parts, whole or none):

Part 1, as released:

```lua
local function rayWorld(ignoreExtra)
    local ignore = { tes3.player }
    if ignoreExtra then table.insert(ignore, ignoreExtra) end
    return tes3.rayTest({
        position = tes3.getPlayerEyePosition(),
        direction = tes3.getPlayerEyeVector(),
        maxDistance = 8192 * 8,
        ignore = ignore,
    })
end
```

patched to:

```lua
local localpatch_rays -- local fix (KP1): set while onSimulate runs: one eye ray per ignore set per frame
local function rayWorld(ignoreExtra)
    local memo, key = localpatch_rays, ignoreExtra or false
    if memo and memo[key] ~= nil then return memo[key] or nil end
    local ignore = { tes3.player }
    if ignoreExtra then table.insert(ignore, ignoreExtra) end
    local hit = tes3.rayTest({
        position = tes3.getPlayerEyePosition(),
        direction = tes3.getPlayerEyeVector(),
        maxDistance = 8192 * 8,
        ignore = ignore,
    })
    if memo then -- MWSE reuses one result object per rayTest: keep the reference, which is all onSimulate reads
        memo[key] = hit and { reference = hit.reference } or false
        return memo[key] or nil
    end
    return hit
end
local function localpatch_frameRays(fn) -- local fix (KP1): rays are shared only while fn runs
    return function(...)
        localpatch_rays = {}
        local ok, err = xpcall(fn, debug.traceback, ...)
        localpatch_rays = nil
        if not ok then error(err, 0) end
    end
end
```

Part 2, as released:

```lua
    local hit = tes3.rayTest({
        position = tes3.getPlayerEyePosition(),
        direction = tes3.getPlayerEyeVector(),
        maxDistance = 8192 * 8,
        ignore = { tes3.player },
    })
    if hit and hit.reference == companionRef then
```

patched to:

```lua
    local hit = rayWorld() -- local fix (KP1): the same ray (only the player ignored), shared within a frame
    if hit and hit.reference == companionRef then
```

Part 3, as released:

```lua
    event.register(tes3.event.simulate, onSimulate)

```

patched to:

```lua
    event.register(tes3.event.simulate, localpatch_frameRays(onSimulate)) -- local fix (KP1)

```

### KP2: Attend Me MWSE (`MWSE\mods\attendmemwse\recruit.lua`)

recruitment mode casts a 65536-unit eye ray and re-lays-out MenuMulti every frame just to label the NPC under the crosshair; the label is refreshed every 3rd frame instead (the command wheel's own TARGET_HUD_EVERY). The click still casts its own ray, so who is recruited or dismissed is unchanged

The recruit-mode aim label is refreshed every 3rd frame instead of every frame (the click still casts its own ray). Intercept idea: gate the mod's recruit `simulate` handler to one frame in three (re-register it through a wrapper), leaving the click handler alone.

The luafix patch as it was (1 exact-text part, whole or none):

Part 1, as released:

```lua
local function onSimulate()
    if not active then return end
    if tes3.menuMode() then return end

    local hit = rayTarget()

```

patched to:

```lua
local localpatch_frame = 0 -- local fix (KP2): the aim label every 3rd frame, like the wheel's target HUD
local function onSimulate()
    if not active then return end
    if tes3.menuMode() then return end
    localpatch_frame = localpatch_frame + 1
    if localpatch_frame % 3 ~= 1 then return end

    local hit = rayTarget()

```

### KP3: Keg Drip (`MWSE\mods\kegdrip\main.lua`)

refreshCell runs at every refresh (once a second as shipped) over every reference of every active cell and normalises each one's mesh path with lower() and two gsub()s; the same path always gives the same answer, so it is worked out once per path

`normalizeMesh` (lower + two gsub) is memoised per mesh path. Intercept idea: the function is local, so an intercept can't replace it directly; either wrap `refreshCell`'s caller (the 1 s timer) to run less often, or leave it: the cost is one string pass per reference per second.

The luafix patch as it was (1 exact-text part, whole or none):

Part 1, as released:

```lua
local function normalizeMesh(mesh)
    return mesh and mesh:lower():gsub("/", "\\"):gsub("^meshes\\", "")
end
```

patched to:

```lua
local localpatch_meshes = {} -- local fix (KP3): each mesh path normalised once, not per reference per refresh
local function normalizeMesh(mesh)
    if not mesh then return mesh end
    local n = localpatch_meshes[mesh]
    if not n then
        n = mesh:lower():gsub("/", "\\"):gsub("^meshes\\", "")
        localpatch_meshes[mesh] = n
    end
    return n
end
```

### KP4: MWSE Containers Extended (`MWSE\mods\spammer\g7 containers\main.lua`)

checkData runs tes3.getReference (a search of every cell's references) for each container item on each inventory tile update, uiObjectTooltip and equip; the linked container is found once and kept as a safe handle, looked up again only when that handle is no longer valid or the reference was deleted

`checkData` looked the linked container up with `tes3.getReference` (a scan of every cell) on every tile update, tooltip and equip; the patch kept a safe handle per id. Intercept idea: wrap `tes3.getReference` while the mod's `itemTileUpdated` / `uiObjectTooltip` / `equip` handlers run, with a per-id safe-handle cache (re-look-up when the handle is invalid or the reference deleted).

The luafix patch as it was (1 exact-text part, whole or none):

Part 1, as released:

```lua
local function checkData(itemData)
    local data = itemData and itemData.data and itemData.data.g7containers
    if data then
        return tes3.getReference(data.linkedRef), data.baseObject
    end
end
```

patched to:

```lua
local localpatch_linked = {} -- local fix (KP4): the linked container found once, kept as a safe handle
local function checkData(itemData)
    local data = itemData and itemData.data and itemData.data.g7containers
    if data then
        local id = data.linkedRef
        if type(id) ~= "string" then return tes3.getReference(id), data.baseObject end
        local h = localpatch_linked[id]
        local ref = h and h:valid() and h:getObject() or nil
        if not ref or ref.deleted then
            ref = tes3.getReference(id)
            localpatch_linked[id] = ref and tes3.makeSafeObjectHandle(ref) or nil
        end
        return ref, data.baseObject
    end
end
```

## Status: taken over by mwsuite (2026-11-26)

| KP | Intercept (mwpluginpatches) | MCM switch | How it works | Stays loaded? | Old luafix edit present |
|---|---|---|---|---|---|
| KP1 | `patches/attendMeRays.lua` | `attendMeRaysEnabled` | wraps the `simulate` handler registered from `attendmemwse/actions.lua`; while it runs, `tes3.rayTest` answers a repeat of the same plain ray (same position, direction, maxDistance and ignore list) with `{ reference = ... }` of the first answer; any other call passes through; put back on return or error | yes: the handler runs every frame | stands down (actions.lua contains `-- local fix (KP1)`) |
| KP2 | `patches/attendMeRecruitLabel.lua` | `attendMeRecruitLabelEnabled` | wraps the `simulate` handler registered from `attendmemwse/recruit.lua` so it runs one non-menu frame in three; the click handler is untouched | yes: recruit mode can start any time | stands down (recruit.lua contains `-- local fix (KP2)`) |
| KP3 | none | none | `normalizeMesh` is a local of KegDrip\main.lua and its callers are locals too, so there is nothing to intercept without editing the file or hooking string functions for every mod. `kegDripCadence` already calls its refresh at most every 3 s (MCM slider, 1-10 s) instead of every second, which cuts this cost by the same factor | n/a | the old edit, if present, keeps working beside `kegDripCadence` |
| KP4 | `patches/g7ContainersLinkCache.lua` | `g7ContainersLinkCacheEnabled` | wraps the `itemTileUpdated`, `uiObjectTooltip`, `equip` and `equipped` handlers registered from `spammer/g7 containers/main.lua`; while they run, `tes3.getReference(id)` for a plain string id is answered from a safe handle per id (looked up again when the handle is invalid or the reference deleted; all handles dropped on `load`); put back on return or error | yes: runs whenever an inventory is open | stands down (main.lua contains `-- local fix (KP4)`) |

The marker check reads the mod's file once when mwpluginpatches loads (`config.modFileHas`). Undoing the old luafix edit
(`--undo`) or reinstalling the mod lets the intercept take over on the next start. Tests: `tests/test_kp_intercepts.py`.
No credits: these are performance fixes, not borrowed ideas.
