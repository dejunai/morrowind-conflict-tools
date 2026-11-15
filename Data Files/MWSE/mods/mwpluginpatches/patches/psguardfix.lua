local config = require("mwpluginpatches.config")

local psguardfix = {}

local SCRIPTS = {
    "ABM_ll_DetectPCCrimeScript",
    "ABM_ll_StopIntruderScript",
    "ABM_PutItBackScript",
}

local wasRunning = {}

-- ABM_ll_GuardCallCell: 1 Hlaalu, 2 Redoran, 3 Telvanni, 4 Temple, 5 Imperial (6 Mournhold: P&S's own)
local NAMES = { "Hlaalu", "Redoran", "Telvanni", "Temple", "Imperial" }

-- mesh file names (lower, no folder), vanilla prefixes and the names Tamriel Data / other mods use
local KINDS = {
    { 1, { "^in_h_", "^ex_h_", "hlaalu" } },
    { 2, { "^in_r_", "^ex_r_", "redoran", "redwall" } },
    { 3, { "^in_t_", "^ex_t_", "telvanni", "_tel_" } },
    { 4, { "temple", "ordinator", "_shrine" } },
    { 5, { "^in_imp", "^ex_imp", "imperial", "_imp_", "legion", "fort_", "_fort" } },
    { 0, { "cave", "cavern", "grotto", "mine", "tomb", "crypt", "barrow", "ruin", "dwrv", "dwemer",
           "daedr", "^in_dae", "^ex_dae", "velothi", "stronghold", "sewer", "lava", "ashl", "^in_py", "^in_mold",
           "^in_bone", "^in_mud", "_bm_ice", "ancestral", "burial" } },
}

-- the cell's name says it outright
local CELL_NAMES = {
    { 0, { "cave", "cavern", "grotto", "mine", "tomb", "crypt", "barrow", "ruin", "sewer", "shrine of",
           "daedric", "dwemer", "egg mine", "stronghold", "lair" } },
    { 4, { "temple", "ordinator" } },
    { 5, { "fort ", "legion", "imperial", "garrison", "census", "excise" } },
    { 1, { "hlaalu" } }, { 2, { "redoran" } }, { 3, { "telvanni" } },
}

local detected = {}

local function matches(text, pats)
    for _, p in ipairs(pats) do
        if text:find(p) then return true end
    end
    return false
end

local function countModels(cell, score, near)
    for ref in cell:iterateReferences({ tes3.objectType.static, tes3.objectType.activator, tes3.objectType.door }) do
        local m = ref.object.mesh
        if m and (not near or ref.position:distance(near) < 4096) then
            local base = m:lower():gsub("^.*[\\/]", "")
            for _, k in ipairs(KINDS) do
                if matches(base, k[2]) then
                    score[k[1]] = (score[k[1]] or 0) + 1
                    break
                end
            end
        end
    end
end

-- whose guards for this place: value, how it was decided
local function detectGuards(cell)
    local id = cell.id:lower()
    if detected[id] then return detected[id][1], detected[id][2] end
    local name = (cell.name or cell.id):lower()
    local v, why
    for _, k in ipairs(CELL_NAMES) do
        if matches(name, k[2]) then
            v, why = k[1], "the place's name"
            break
        end
    end
    if not v then
        local score = {}
        if cell.isInterior then
            countModels(cell, score)
        else
            for _, c in pairs(tes3.getActiveCells()) do
                countModels(c, score, tes3.player.position)
            end
        end
        local best, n, clan = 0, 0, 0
        for k = 1, 5 do
            clan = clan + (score[k] or 0)
            if (score[k] or 0) > n then
                best, n = k, score[k]
            end
        end
        if (score[0] or 0) >= 5 and (score[0] or 0) > clan then
            v, why = 0, string.format("%d cave/tomb/ruin meshes", score[0])
        elseif n >= 5 then
            v, why = best, string.format("%d %s meshes", n, NAMES[best])
        elseif cell.isInterior then
            v, why = 5, "an interior not recognised (default)"
        else
            v, why = 0, "an exterior not recognised (default)"
        end
    end
    detected[id] = { v, why }
    return v, why
end

local function global(id)
    return tes3.findGlobal(id)
end

local function guardNearby()
    for _, cell in pairs(tes3.getActiveCells()) do
        for ref in cell:iterateReferences(tes3.objectType.npc) do
            local id = ref.baseObject.id:lower()
            if id:find("^abm_thguard") and not ref.disabled and not ref.deleted then
                return true
            end
        end
    end
    return false
end

local function fadeBackIn()
    tes3.fadeIn({ fader = tes3.worldController.transitionFader, duration = 0.3 })
end

local function check()
    local callCell = global("ABM_ll_GuardCallCell")
    if not callCell then return end
    for _, name in ipairs(SCRIPTS) do
        local running = tes3.getLegacyScriptRunning({ script = name })
        if running and callCell.value == 0 and tes3.player and tes3.player.cell then
            local v, why = detectGuards(tes3.player.cell)
            if v > 0 then
                callCell.value = v
                mwse.log("[mwpluginpatches] %s: %s guards (%s)", tes3.player.cell.id, NAMES[v], why)
            end
        end
        if running and callCell.value == 0 then
            -- no guards for this place: don't let it fade out
            tes3.stopLegacyScript({ script = name })
            local putBack = global("ABM_PutItBack")
            if putBack and putBack.value ~= 3 then putBack.value = 0 end
            running = false
            mwse.log("[mwpluginpatches] stopped %s (no guards for %s)", name,
                tes3.player and tes3.player.cell.id or "?")
            timer.start({
                type = timer.real,
                duration = 0.5,
                callback = function()
                    if not guardNearby() then fadeBackIn() end
                end
            })
        elseif wasRunning[name] and not running then
            -- script finished: a guard should be here and fading us back in
            timer.start({
                type = timer.real,
                duration = 1.0,
                callback = function()
                    if not guardNearby() then
                        mwse.log("[mwpluginpatches] %s ended with no guard; fading in", name)
                        fadeBackIn()
                    end
                end
            })
        end
        wasRunning[name] = running
    end
end

local function onInfoFilter(e)
    if e.dialogue and e.dialogue.id then
        local id = e.dialogue.id:lower()
        if id:find("%(target%)") then
            local topicVal = tes3.getGlobal("ABM_Topic") or 0
            local targetVal = tes3.getGlobal("ABM_TargetGlobal") or 0
            if topicVal <= 0 and targetVal <= 0 then
                e.passes = false
                return false
            end
        end
    end
end

function psguardfix.init()
    if not config.psGuardFixEnabled or not config.isPsGuardActive() then
        return
    end

    event.register(tes3.event.loaded, function()
        wasRunning = {}
    end)

    event.register(tes3.event.infoFilter, onInfoFilter)

    timer.start({
        type = timer.real,
        duration = 0.35,
        iterations = -1,
        persist = false,
        callback = function()
            if tes3.player then check() end
        end
    })

    mwse.log("[mwpluginpatches] Privileges & Services guard call, fade, and target-topic filter active.")
end

return psguardfix
