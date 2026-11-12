#!/usr/bin/env python3
"""mwdialog_luafix.py - find and patch bad habits in MWSE Lua mods that pass a syntax check.

Each .lua file under an MWSE\\mods folder is parsed (mwdialog_lua.py: a real Lua tokenizer and parser, not
regexes) and checked against the rules of "# Morrowind MWSE Lua Debugging & Repair Guide.MD" plus a few the
guide implies. Every finding has a confidence: "high" ones are patched by --apply, "medium" ones only with
--level medium, the rest are only reported. A patch is a few token-span edits; nothing else in the file
changes (encoding, line endings and every line number stay the same: helpers go at the start of line 1).

Rules (thresholds come from MWSE\\config\\mwguard.json when it exists - the same file mwguard reads at runtime):
  G1 absurd event priority (|p| >= priorityLimit, 10000) -> compressed to 1000..1999 (order kept)    fix
  G2 a per-frame handler (simulate/simulated/enterFrame) that only polls state -> runs every 0.35 s  fix
  G3 a repeating timer faster than 0.35 s whose callback only polls -> 0.35 s                          fix
  G4 a one-shot handler (done flag) that never unregisters -> unregisters once the flag is set         fix
  G5 per-frame costs: uncached lookups, config/file I/O, allocations, message boxes every frame      report
  A1 ref.data.x used without a guard -> (ref.data and ref.data.x) / if ref.data then ... end           fix
  A2 a keybind's .keyCode (.mouseButton ...) read with no check -> (key and key.keyCode)               fix
  A3 a tes3 lookup that can return nil (getObject, getReference, getPlayerTarget, findMenu...) used
     without a check -> guarded                                                                        fix
  A4 an event field that can be nil (damage e.attacker, attack e.targetMobile, cellChanged
     e.previousCell, uiObjectTooltip e.reference...) used without a check -> guarded                  fix
     Nil guards (A1-A4): inside a condition, an and-guard: (x and x.y == z); a standalone call or
     assignment: if x then ... end; a local's value: local v = (x and f(x.y)). Nothing changes while the
     value is there. Where none of these fits with certainty the finding stays a report, with the reason.
  B1 a UI element used after :destroy()                                                               report
  C1 an engine console command sent through tes3.runLegacyScript                                      report
  D1 an infoFilter handler reading e.info.text for every response -> returns early unless e.passes     fix
  F1 log spam (logging every frame, in loops, in frequent events, debug flags on) -> the mod's lines
     past its allowance go to Data Files\\MWSE\\logs\\<mod>.log; errors still reach MWSE.log            fix
  F2 a logger created at DEBUG/TRACE level -> INFO                                                     fix
  H1 event.register inside a load/cellChanged/... handler: a named handler -> isRegistered guard     fix
     (MWSE refuses the duplicate but prints a warning and a traceback every time); an anonymous one
     stacks a new copy each time                                                                      report
  H2 a repeating timer started in a handler that runs again (loaded, cellChanged...), never cancelled report
  H3 global variables a mod creates by accident (no local)                                            report
  H4 game data used at file load, before the initialized event                                        report
  H5 require cycles inside a mod                                                                      report
  H6 tes3.messageBox inside a loop                                                                    report

Never touched: MWSE's own code (only files under ...\\MWSE\\mods\\ are read; core, lib, config never), and
your own mods (mwcollide, mwfloatfix, mwguard, mwhangwatch, mwinfoloop, mwperformers, mwsoundguard,
mwstranded, MWManager) unless --include-own.

Edits are made in place (the file is rewritten through the same handle, so Vortex's hard links between
staging and Data Files keep sharing it). The file as it was is copied first to
mwdialog_backup\\luafix\\<run>\\..., every write is journaled, and --undo puts the last run back. A file is
only written when LuaJIT (or luac) compiles the patched text; if the original doesn't compile it is left alone.

    python mwdialog_luafix.py                        (plan for Data Files\\MWSE\\mods; nothing is changed)
    python mwdialog_luafix.py "G:\\Vortex Mods\\morrowind\\Some Mod"   (one folder)
    python mwdialog_luafix.py --apply                (patch the high-confidence findings)
    python mwdialog_luafix.py --undo                 (put back the files of the last --apply)
After --apply, mwdialog_luafix_plan.txt is blanked (a second --apply does nothing until plan mode runs again) or
cut down to the patches not written; a copy of it is kept in that run's mwdialog_backup\\luafix\\<run>\\.
vortex_tidy.py runs the same check on every staging mod (its plan shows it, --apply patches, --undo reverts;
--no-lua skips it, --lua-only does nothing else).
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_lua as L                                   # noqa: E402
import mwdialog_planfile as PF                             # noqa: E402

sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))

HERE = os.path.dirname(os.path.abspath(__file__))
JOURNAL = os.path.join(HERE, "mwdialog_luafix_journal.jsonl")
BACKUP_ROOT = os.path.join(HERE, "mwdialog_backup", "luafix")
CONFIG_FILE = os.path.join(HERE, "mwdialog_luafix.json")
PLAN_FILE = os.path.join(HERE, "mwdialog_luafix_plan.txt")
VERSION = 3
MARK = "mwdialog_luafix"

OWN_MODS = {"mwcollide", "mwfloatfix", "mwguard", "mwhangwatch", "mwinfoloop", "mwperformers", "mwsoundguard",
            "mwstranded", "mwmanager"}

# defaults; mwguard.json (shared with the runtime guard) and mwdialog_luafix.json override them
DEFAULTS = {
    "priorityLimit": 10000,          # mwguard: |priority| >= this is absurd (the guide says the same)
    "priorityClampTo": 1000,         # the old mwguard's runtime clamp (priorityMode "clamp"); the passive mwguard
                                     # only reports |priority| >= priorityLimit, which keepOrder stays under
    "priorityMode": "keepOrder",     # keepOrder: absurd priorities go to just under the limit (9000..9999), so
                                     # they still sort ahead of every ordinary priority; clamp: clampTo..2*clampTo
    "minInterval": 0.35,             # the guide: at least 0.35 s between repeating calls
    "exemptMods": sorted(OWN_MODS),
    "log": {                         # the log shim (F1): mwguard.json "luafix": { "log": { ... } } overrides
        "scope": "flagged",          # flagged: mods with log-spam signs; all: every mod that logs; off: none
        "budgetInit": 40,            # lines a mod may write to MWSE.log while the game starts
        "budget": 10,                # ... and after the initialized event
        "keepPatterns": ["error", "traceback", "exception", "fail", "warn", "stack", "attempt to", "assert",
                         "invalid", "%.lua:%d+:", "^lua:"],   # lines that always reach MWSE.log (Lua patterns)
        "perSecond": 50,             # the mod's own log takes at most this many lines a second (0: no cap)
        "maxMB": 2,                  # the mod's own log is rotated at this size ...
        "keepOld": 1,                # ... keeping the previous one as <mod>.old.log (0: none)
        "flushSeconds": 2,           # buffered lines reach the disk at least this often
        "errorRepeat": 0,            # > 0: the same error line past this many times goes to the mod's log only
        "exemptMods": [],            # mods that never get the shim (their output stays in MWSE.log)
    },
    "logSpamGuard": True,
    "enabled": True,
    "logShimWhenMwguard": False,     # also patch log spam when mwguard's runtime guard covers the mod
}

PER_FRAME = {"simulate", "simulated", "enterFrame"}
# nil guards
KEY_FIELDS = {"keyCode", "mouseButton", "mouseWheel", "isShiftDown", "isAltDown", "isControlDown", "isSuperDown"}
NIL_LOOKUPS = {"tes3.getObject", "tes3.getReference", "tes3.getPlayerTarget", "tes3.getEquippedItem", "tes3.getCell",
               "tes3.getFaction", "tes3.getSound", "tes3.getScript", "tes3.findDialogue",
               "tes3.getRegion", "tes3.findClass", "tes3ui.findMenu"}
_DMG = {"attacker", "attackerReference", "projectile", "magicSourceInstance", "magicEffectInstance"}
_ATK = {"targetMobile", "targetReference"}
_CAST = {"target"}
NULLABLE_EVENT_FIELDS = {
    "damage": _DMG, "damaged": _DMG, "damageHandToHand": _DMG, "damagedHandToHand": _DMG,
    "attack": _ATK, "attackHit": _ATK, "attackStart": _ATK, "calcHitChance": {"target", "targetMobile"},
    "cellChanged": {"previousCell"}, "activationTargetChanged": {"current", "previous"},
    "uiObjectTooltip": {"reference", "itemData"}, "itemTileUpdated": {"itemData"},
    "equip": {"itemData"}, "equipped": {"itemData"}, "unequipped": {"itemData"},
    "spellCast": _CAST, "spellCasted": _CAST, "spellCastedFailure": _CAST, "magicCasted": _CAST,
    "leveledItemPicked": {"pick", "spawner"}, "leveledCreaturePicked": {"pick", "spawner"}}
NIL_TMP = "mwluafix_v"
FRAME_EXEMPT_EVENTS = {"cameraControl", "calcMoveSpeed", "mouseAxis", "preventRest"}
ONCE_EVENTS = {"initialized", "modConfigReady", "initialize"}
FREQUENT_EVENTS = PER_FRAME | FRAME_EXEMPT_EVENTS | {
    "infoFilter", "calcHitChance", "damage", "damaged", "damageHandToHand", "attack", "spellTick", "itemTileUpdated",
    "uiObjectTooltip", "calcArmorRating", "calcBlockChance", "calcSpellmakingPrice", "keyDown", "keyUp",
    "mouseButtonDown", "mouseWheel", "absorbedMagic", "magicEffectRemoved", "playGroup", "bodyPartAssigned",
    "referenceActivated", "referenceDeactivated", "mobileActivated", "mobileDeactivated", "projectileExpire",
    "determineAction", "determinedAction", "activationTargetChanged", "weatherCycled", "combatStarted", "addSound",
    "addTempSound", "soundObjectPlay", "calcTravelPrice", "calcBarterPrice", "lockPick", "trapDisarm", "jump",
    "collision", "activate", "dialogueEnvironmentCreated", "postInfoResponse", "infoResponse", "spellCast",
    "spellCasted", "magicCasted", "exerciseSkill", "skillRaised"}

# per-frame hints, from mwguard's perFrameHints (matched on identifiers only, not comments or strings)
FRAME_HINTS = ("delta", "camera", "velocity", "orientation", "rotation", "animat", "drag", "mouse", "lerp",
               "smooth", "interpolat", "fade", "tes3ui", "menu", "controls", "keybind", "inputcontroller",
               "positioncell", "impulse", "scenegraph", "scenenode", "worldtransform", "iskeydown", "iskeypressed",
               "ismousebutton", "applymovement", "forcejump", "playanimation", "setplayercontrolstate",
               "updatelayout", "lookat", "facing")
FRAME_HINT_OK = {"menumode", "ismenumode"}            # reading the menu state is a poll
SELF_TIMED = {"os.clock", "os.time", "tes3.getSimulationTimestamp", "mwse.simulateTimers.clock",
              "mwse.realTimers.clock", "tes3.getRealTimestamp"}
QUERIES = {
    "tes3.getGlobal", "tes3.getJournalIndex", "tes3.getItemCount", "tes3.getPlayerCell", "tes3.getCurrentWeather",
    "tes3.getPlayerTarget", "tes3.getCurrentAIPackageId", "tes3.isAffectedBy", "tes3.hasOwnershipAccess",
    "tes3.getEquippedItem", "tes3.getReference", "tes3.getObject", "tes3.findGMST", "tes3.getLocked",
    "tes3.getTrap", "tes3.isModActive", "tes3.getRegion", "tes3.getCell", "tes3.getActiveCells", "tes3.menuMode",
    "tes3.is3rdPerson", "tes3.getPlayerEyePosition", "tes3.getPlayerEyeVector", "tes3.isInitialized",
    "tes3.getFaction", "tes3.getScript", "tes3.getSound", "tes3.getSkill", "tes3.getDaysInMonth",
    "tes3.testLineOfSight", "tes3.getDataHandler", "tes3.getWorldController", "tes3.getMobilePlayer",
    "tes3ui.menuMode", "tes3.getCumulativeDaysForMonth", "tes3.isLuaModActive", "tes3.getLegacyScriptRunning",
    "ipairs", "pairs", "next", "type", "tostring", "tonumber", "select", "unpack", "rawget", "rawequal",
    "assert", "pcall"}
ACTIONS = {
    "tes3.messageBox", "tes3.setGlobal", "tes3.updateJournal", "tes3.addItem", "tes3.removeItem", "tes3.playSound",
    "tes3.streamMusic", "tes3.addSpell", "tes3.removeSpell", "tes3.say", "tes3.addTopic", "tes3.setJournalIndex",
    "tes3.showMessageMenu", "tes3.createReference", "tes3.setEnabled", "tes3.setLockLevel", "tes3.unlock",
    "tes3.removeSound", "tes3.playItemPickupSound", "tes3.setAIFollow", "tes3.setAIWander", "tes3.setAITravel",
    "tes3.addJournalEntry", "tes3.cast", "tes3.applyMagicSource", "tes3.removeEffects",
    "mwse.log", "print", "event.unregister", "event.register", "event.trigger", "timer.start", "timer.delayOneFrame",
    "error"}
LIB_PREFIXES = ("string.", "math.", "table.")
SAFE_METHODS = {"getDistance", "distance", "contains", "find", "lower", "upper", "sub", "match", "gmatch",
                "format", "len", "iterateReferences", "iterate", "getActiveEffects", "isAffectedBy", "copy",
                "getSkillValue", "getSkillStatistic", "hasItemEquipped", "getActiveMagicEffects", "getFatigueTerm",
                "isBelowWater", "isPointInside", "cancel", "dot", "length", "normalized", "cross", "angle",
                "heading", "split", "startswith", "endswith", "getDayOfYear", "isActive", "hasEffect",
                "getObjectByName", "isDead"}
FRAME_METHODS = {"setRotation", "update", "updateLayout", "propagatePositionChange", "updateEffects",
                 "updateProperties", "updateNodeEffects", "detachChild", "attachChild", "setPosition",
                 "forceRecollision", "triggerEvent", "updateSceneGraph", "applyHealthDamage"}
LOOKUPS = {"tes3.getObject", "tes3.findGMST", "tes3.getReference", "tes3.getCell", "tes3.getScript",
           "tes3.getSound", "tes3.getFaction", "tes3.getRegion", "tes3.getSkill", "tes3ui.findMenu",
           "tes3ui.registerID"}
CONFIG_IO = {"mwse.loadConfig", "mwse.saveConfig", "json.loadfile", "json.savefile", "io.open", "io.lines",
             "json.decode", "json.encode", "dofile", "loadfile"}
LOGS = {"print", "mwse.log"}
# console-only commands; replacement suggestions follow the guide's table where it has one
CONSOLE_ONLY = {"togglepov": "tes3.togglePOV() (or tes3.force1stPerson() / tes3.force3rdPerson())",
                "tcl": "console only (no script command)", "tai": "console only (no script command)",
                "tfow": "console only", "tm": "console only", "tgm": "console only", "tcb": "console only",
                "tws": "console only", "twf": "console only", "tb": "console only", "tdt": "console only",
                "tfc": "console only", "tg": "console only", "ts": "console only", "tw": "console only",
                "tli": "console only", "tlb": "console only", "coc": "tes3.positionCell{...}",
                "coe": "tes3.positionCell{...}"}


# ---------------------------------------------------------------------------------------------------------- config
LEGACY_LOG = {"logBudgetInit": "budgetInit", "logBudget": "budget", "logKeepPatterns": "keepPatterns",
              "logExemptMods": "exemptMods"}


def load_config(game_dir=HERE, data_dir=None):
    """DEFAULTS, then MWSE\\config\\mwguard.json (mwguard's own file: one place for the thresholds both use),
    its "luafix" section, then mwdialog_luafix.json next to this script."""
    cfg = dict(DEFAULTS)
    cfg["log"] = dict(DEFAULTS["log"])
    data_dir = data_dir or os.path.join(game_dir, "Data Files")
    guard = os.path.join(data_dir, "MWSE", "config", "mwguard.json")
    src = []
    for path, section in ((guard, None), (guard, "luafix"), (os.path.join(game_dir, "mwdialog_luafix.json"), "")):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        if section:
            d = d.get(section) if isinstance(d.get(section), dict) else {}
        for k, v in d.items():
            if k == "log" and section is not None and isinstance(v, dict):
                cfg["log"] = dict(cfg["log"], **v)
            elif k in LEGACY_LOG and section is None:       # the old mwguard's log-spam keys
                cfg["log"] = dict(cfg["log"], **{LEGACY_LOG[k]: v})
            elif k == "log":
                continue
            elif section is not None or k in DEFAULTS or k == "logExemptMods":   # mwguard.json: shared keys only
                cfg[k] = v
            elif k == "throttleSeconds" and section is None and isinstance(v, (int, float)):
                cfg["minInterval"] = max(float(v), 0.05)       # mwguard v1's name for it
        if d:
            src.append(path + (f" [{section}]" if section else ""))
    cfg["_sources"] = src
    return cfg


def cfg_hash(cfg):
    keep = {k: v for k, v in cfg.items() if not k.startswith("_")}
    return hashlib.sha1(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:12] + f"v{VERSION}"


def mwguard_log_cover(data_dir, cfg, mod_key):
    """(covered, why): is mwguard's runtime log-spam guard clearly going to catch this mod's lines?"""
    main = os.path.join(data_dir or "", "MWSE", "mods", "mwguard", "main.lua")
    if not data_dir or not os.path.isfile(main):
        return False, "mwguard is not installed in Data Files"
    try:
        with open(main, encoding="latin-1") as f:
            txt = f.read()
    except OSError:
        return False, "mwguard's main.lua can't be read"
    if "logSpamGuard" not in txt:
        return False, ("the installed mwguard is a passive profiler with no log-spam redirect, so nothing else "
                       "keeps this out of MWSE.log")
    if not cfg.get("enabled", True) or not cfg.get("logSpamGuard", True):
        return False, "mwguard.json turns mwguard or its log-spam guard off"
    low = mod_key.lower()
    for m in (cfg.get("logExemptMods") or []) + list(cfg["log"].get("exemptMods") or []):
        m = str(m).lower().replace("\\", "/")
        if m == low or m == low.split("/")[0]:
            return False, "the mod is in mwguard's logExemptMods"
    return True, "mwguard's runtime log-spam guard covers it"


# ---------------------------------------------------------------------------------------------- syntax checkers
class LuaJITChecker:
    """luajit.exe -b <file> NUL: compiles to bytecode (thrown away), never runs the script. luac: -p."""

    def __init__(self, exe, kind="luajit"):
        self.exe, self.kind = exe, kind
        self.name = f"{kind} ({exe})"

    def check(self, text):
        fd, tmp = tempfile.mkstemp(suffix=".lua", prefix="luafix_")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(text.encode("latin-1"))
            null = "NUL" if os.name == "nt" else os.devnull
            cmd = [self.exe, "-b", tmp, null] if self.kind == "luajit" else [self.exe, "-p", tmp]
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=60, cwd=os.path.dirname(self.exe) or None,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.TimeoutExpired) as e:
                return False, f"checker failed to run: {e}"
            msg = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip().replace(tmp, "<file>")
            return r.returncode == 0, msg
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass


class LupaChecker:
    """The LuaJIT inside the lupa Python package (loadstring: compiles, never runs)."""

    def __init__(self):
        from lupa import luajit21 as lj                      # noqa
        self.rt = lj.LuaRuntime()
        self.fn = self.rt.eval("function(s) local f, e = loadstring(s, '=file') return e end")
        self.name = f"lupa ({self.rt.lua_implementation})"

    def check(self, text):
        e = self.fn(text.encode("latin-1"))
        return e is None, (e.decode("latin-1") if isinstance(e, bytes) else str(e or ""))


MWMANAGER_LUAJIT = r"G:\projects\MWManager\tools\luajit\luajit.exe"


def find_checker(explicit=None, game_dir=HERE):
    """The user's compiled LuaJIT first (MWManager's tools\\luajit, or one next to this script), then luajit /
    luac on PATH, then lupa; None if there is none."""
    exe = "luajit.exe" if os.name == "nt" else "luajit"
    cands = [explicit] if explicit else []
    cands += [os.path.join(game_dir, "tools", "luajit", exe), os.path.join(game_dir, exe), MWMANAGER_LUAJIT]
    for c in cands:
        if c and os.path.isfile(c):
            return LuaJITChecker(c, "luac" if "luac" in os.path.basename(c).lower() else "luajit")
    if explicit:
        return None
    for nm, kind in (("luajit", "luajit"), ("luac5.1", "luac"), ("luac", "luac")):
        p = shutil.which(nm)
        if p:
            return LuaJITChecker(p, kind)
    try:
        return LupaChecker()
    except Exception:
        return None


# ----------------------------------------------------------------------------------------------- name binding
class Binding:
    __slots__ = ("name", "kind", "decl", "value", "assigns", "reads", "func")

    def __init__(self, name, kind, decl, value=None, func=None):
        self.name, self.kind, self.decl, self.value = name, kind, decl, value
        self.assigns, self.reads, self.func = [], [], func       # func: the function the binding lives in


def resolve(tree):
    """Bind every Name node (n.binding: a Binding, or None for a global), with Lua's scoping rules. Returns
    (globals assigned: name -> [statements], global functions: name -> Function, global reads: name -> [nodes])."""
    gassign, gfuncs, greads = {}, {}, {}

    def lookup(scopes, nm):
        for sc in reversed(scopes):
            if nm in sc:
                return sc[nm]
        return None

    def expr(n, scopes, fn):
        if n is None:
            return
        if n.kind == "Name":
            b = lookup(scopes, n.id)
            n.binding = b
            if b is not None:
                b.reads.append(n)
            else:
                greads.setdefault(n.id, []).append(n)
        elif n.kind == "Function":
            func(n, scopes)
        else:
            for c in n.children():
                expr(c, scopes, fn)

    def func(f, scopes):
        sc = {p: Binding(p, "param", f, func=f) for p in f.params}
        block(f.body, scopes + [sc], f)

    def block(b, scopes, fn, extra=None):
        scopes = scopes + [dict(extra or {})]
        for st in b.stats:
            stat(st, scopes, fn)

    def stat(st, scopes, fn):
        k, sc = st.kind, scopes[-1]
        if k == "Local":
            for e in st.exprs:
                expr(e, scopes, fn)
            for i, nm in enumerate(st.names):
                val = st.exprs[i] if i < len(st.exprs) else None
                if i == len(st.exprs) - 1 and len(st.names) > len(st.exprs) and val is not None and \
                        val.kind in ("Call", "Method", "Vararg"):
                    val = None                               # local a, b = f(): a is not "f()" alone
                sc[nm] = Binding(nm, "local", st, val, func=fn)
        elif k == "LocalFunc":
            sc[st.name] = Binding(st.name, "localfunc", st, st.func, func=fn)
            func(st.func, scopes)
        elif k == "FuncStat":
            b = lookup(scopes, st.path[0])
            nm = L.Node("Name", st.name_s, st.name_s + len(st.path[0]), id=st.path[0])
            nm.binding = b
            if len(st.path) == 1:
                if b is not None:
                    b.assigns.append(st)
                else:
                    gassign.setdefault(st.path[0], []).append(st)
                    gfuncs.setdefault(st.path[0], st.func)
            elif b is not None:
                b.reads.append(nm)
            func(st.func, scopes)
        elif k == "Assign":
            for e in st.exprs:
                expr(e, scopes, fn)
            for t in st.targets:
                if t.kind == "Name":
                    b = lookup(scopes, t.id)
                    t.binding = b
                    if b is not None:
                        b.assigns.append(st)
                    else:
                        gassign.setdefault(t.id, []).append(st)
                else:
                    expr(t, scopes, fn)
        elif k == "CallStat":
            expr(st.call, scopes, fn)
        elif k == "Return":
            for e in st.exprs:
                expr(e, scopes, fn)
        elif k == "Do":
            block(st.body, scopes, fn)
        elif k == "While":
            expr(st.cond, scopes, fn)
            block(st.body, scopes, fn)
        elif k == "Repeat":
            inner = scopes + [{}]
            for s2 in st.body.stats:
                stat(s2, inner, fn)
            expr(st.cond, inner, fn)
        elif k == "If":
            for cond, b in st.clauses:
                expr(cond, scopes, fn)
                block(b, scopes, fn)
            if st.orelse is not None:
                block(st.orelse, scopes, fn)
        elif k == "NumFor":
            expr(st.start, scopes, fn)
            expr(st.stop, scopes, fn)
            expr(st.step, scopes, fn)
            block(st.body, scopes, fn, {st.var: Binding(st.var, "for", st, func=fn)})
        elif k == "GenFor":
            for e in st.exprs:
                expr(e, scopes, fn)
            block(st.body, scopes, fn, {nm: Binding(nm, "for", st, func=fn) for nm in st.names})

    block(tree.body, [], None)
    return gassign, gfuncs, greads


# ----------------------------------------------------------------------------------------------- helpers
def num_value(n):
    """The number a Number / -Number / math.huge node stands for, else None."""
    if n is None:
        return None
    if n.kind == "Unop" and n.op == "-":
        v = num_value(n.operand)
        return -v if v is not None else None
    if n.kind == "Paren":
        return num_value(n.expr)
    if n.kind == "Index" and L.dotted(n) == "math.huge":
        return math.inf
    if n.kind != "Number":
        return None
    raw = n.raw.rstrip("uUlLiI")
    try:
        if raw.lower().startswith("0x"):
            return float.fromhex(raw) if ("." in raw or "p" in raw.lower()) else int(raw, 16)
        return int(raw) if re.fullmatch(r"\d+", raw) else float(raw)
    except ValueError:
        return None


def table_field(tbl, name):
    if tbl is None or tbl.kind != "Table":
        return None
    for k, _kx, v in tbl.fields:
        if k == name:
            return v
    return None


def event_name(n):
    if n is None:
        return None
    if n.kind == "String":
        return L.string_value(n.raw)
    d = L.dotted(n)
    if d and d.startswith("tes3.event."):
        return d[len("tes3.event."):]
    return None


def compress_priority(p, cfg):
    """An absurd priority (|p| >= priorityLimit) made ordinary, keeping the order: base + 100*log10(|p| / limit),
    so (keepOrder, limit 10000) 10000 -> 9000, 1e6 -> 9200, 1e9 -> 9500, math.huge -> 9999. keepOrder puts them
    just under the limit, so a mod that used a huge number still runs before (or, negative, after) every mod
    with an ordinary priority, and before one that used a smaller huge number; mwguard no longer reports them.
    clamp: priorityClampTo (1000) .. 2*clampTo - 1, like mwguard's runtime clamp (which can reorder them against
    mods using 1000..9999)."""
    lim = cfg["priorityLimit"]
    if cfg.get("priorityMode", "keepOrder") == "clamp":
        base, top = cfg["priorityClampTo"], 2 * cfg["priorityClampTo"] - 1
    else:
        base, top = max(1, lim - 1000), lim - 1
    a = abs(p)
    v = top if a == math.inf else min(top, base + int(math.floor(100 * math.log10(a / lim))))
    return int(math.copysign(v, p))


def is_literalish(n):
    if n is None:
        return False
    return n.kind in ("Number", "String", "True", "False", "Nil") or (
        n.kind == "Unop" and n.op == "-" and n.operand.kind == "Number")


def side_effect_free(n):
    """A literal, a name, a dotted field chain, or a table of those (safe to evaluate twice)."""
    if n is None:
        return True
    if is_literalish(n) or n.kind == "Name" or (n.kind == "Index" and L.dotted(n)):
        return True
    if n.kind == "Table":
        return all((kx is None or side_effect_free(kx)) and side_effect_free(v) for _k, kx, v in n.fields)
    return False


def inside_loop(n):
    p = n.parent
    while p is not None:
        if p.kind == "Function":
            return False
        if p.kind in ("NumFor", "GenFor", "While", "Repeat"):
            return True
        p = p.parent
    return False


def stmt_of(n):
    p = n
    while p.parent is not None and p.parent.kind != "Block":
        p = p.parent
    return p


def ident_of(n):
    return n.id if n.kind == "Name" else n.field if n.kind == "Index" else n.name if n.kind == "Method" else None


# ----------------------------------------------------------------------------------------------- analysis
class Finding(dict):
    """rule, line, what, fix (proposal), conf (high | medium | report-high | report | trigger | covered | info),
    edits [(start, end, text)], needs (helpers the edits use: "gate", "shim")."""


REF_NAME = re.compile(r"(?i)(ref|reference|target|actor|npc|creature|container|item|door|companion|follower|"
                      r"mobile)s?$")
DEBUG_FLAG = re.compile(r"(?i)(debug|debugmode|debug_mode|verbose|logging|logdebug|log_debug|enablelogging|"
                        r"enabledebug|showdebug|debuglog|debugging)")


class FileAnalysis:
    def __init__(self, src, mod_key="", rel="", cfg=None):
        self.src, self.mod_key, self.rel = src, mod_key, rel
        self.cfg = cfg or dict(DEFAULTS)
        self.findings = []
        self.tree = L.parse(src)
        self.gassign, self.gfuncs, self.greads = resolve(self.tree)
        self.nodes = list(L.walk(self.tree))
        cut = src.find(SHIM_END)                  # our own log shim is not the mod's code
        if cut >= 0:
            cut += len(SHIM_END)
        else:
            m = SHIM_V1_RE.search(src)
            cut = m.end() if m else -1
        if cut >= 0:
            self.nodes = [n for n in self.nodes if n.s >= cut]
        self.old_shim = bool(SHIM_V1_RE.search(src))
        self.calls = [n for n in self.nodes if n.kind == "Call"]
        self._lines = None
        self.registrations = []          # (call, event, handler Function or None, handler arg, options)
        self.handler_events = {}         # id(Function) -> events it is registered for
        self._gate_next = 1 + max([int(x) for x in re.findall(r"mwluafix_gate\((\d+)", src)] or [0])
        for c in self.calls:
            if L.dotted(c.func) == "event.register" and len(c.args) >= 2:
                ev = event_name(c.args[0])
                fn = self.func_of(c.args[1])
                self.registrations.append((c, ev, fn, c.args[1], c.args[2] if len(c.args) > 2 else None))
                if fn is not None and ev:
                    self.handler_events.setdefault(id(fn), set()).add(ev)

    # --- small helpers
    def text(self, n):
        return self.src[n.s:n.e]

    def line(self, n):
        if self._lines is None:
            import bisect
            self._nl = [i for i, ch in enumerate(self.src) if ch == "\n"]
            self._lines = bisect
        return self._lines.bisect_left(self._nl, n.s) + 1

    def add(self, rule, node, what, fix="", conf="report", edits=(), needs=()):
        f = Finding(rule=rule, line=self.line(node) if node is not None else 1, what=what, fix=fix, conf=conf,
                    edits=list(edits), needs=set(needs))
        self.findings.append(f)
        return f

    def func_of(self, arg):
        """The function an argument stands for: a function expression, or a name always bound to one."""
        if arg is None:
            return None
        if arg.kind == "Function":
            return arg
        if arg.kind != "Name":
            return None
        b = getattr(arg, "binding", None)
        if b is None:
            f = self.gfuncs.get(arg.id)
            return f if f is not None and len(self.gassign.get(arg.id, [])) == 1 else None
        if b.value is not None and b.value.kind == "Function" and not b.assigns:
            return b.value
        if b.kind == "local" and b.value is None and len(b.assigns) == 1 and b.assigns[0].kind == "FuncStat":
            return b.assigns[0].func                      # local f ... function f() end
        return None

    def name_uses(self, arg):
        b = getattr(arg, "binding", None)
        return b.reads if b is not None else self.greads.get(arg.id, [])

    def events_of_function(self, f):
        return self.handler_events.get(id(f), set()) if f is not None else set()

    def closure(self, f, depth=4):
        """f and the same-file functions it calls by name (to depth); nested function expressions are part of
        the body they are in."""
        out, todo, seen = [], [(f, 0)], set()
        while todo:
            g, d = todo.pop()
            if id(g) in seen:
                continue
            seen.add(id(g))
            out.append(g)
            if d >= depth:
                continue
            for n in L.walk(g.body):
                if n.kind == "Call" and n.func.kind == "Name":
                    h = self.func_of(n.func)
                    if h is not None:
                        todo.append((h, d + 1))
        return out

    def classify(self, f):
        """(class, why) for running f less often than every frame: 'high' (only checks state and reacts),
        'medium' (can't be sure), 'frame' (frame-critical: leave it) or 'self' (already times itself)."""
        funcs = self.closure(f)
        known = {id(g) for g in funcs}
        signals, unknown, writes, counter, selftimed, has_if = [], [], [], [], [], False
        for g in funcs:
            for n in L.walk(g.body):
                k = n.kind
                ident = ident_of(n)
                if ident:
                    lo = ident.lower()
                    if lo not in FRAME_HINT_OK and any(h in lo for h in FRAME_HINTS):
                        signals.append(ident)
                if k == "If":
                    has_if = True
                elif k == "Call":
                    d = L.dotted(n.func)
                    if d in SELF_TIMED:
                        selftimed.append(d)
                    elif d in QUERIES or d in ACTIONS or (d and d.startswith(LIB_PREFIXES)):
                        pass
                    elif n.func.kind == "Name" and id(self.func_of(n.func) or 0) in known:
                        pass
                    else:
                        unknown.append(d or self.text(n.func)[:40])
                elif k == "Method":
                    if n.name in FRAME_METHODS:
                        signals.append(":" + n.name)
                    elif n.name not in SAFE_METHODS:
                        unknown.append(":" + n.name)
                elif k == "Assign":
                    for i, t in enumerate(n.targets):
                        v = n.exprs[i] if i < len(n.exprs) else None
                        if t.kind == "Index":
                            root = t
                            while root.kind == "Index":
                                root = root.obj
                            b = getattr(root, "binding", None) if root.kind == "Name" else None
                            # bookkeeping: a table of the mod's own (local x = {} in the file), or a local
                            # of this function
                            own = b is not None and (b.func is g or (b.value is not None and b.value.kind == "Table"))
                            if not own:
                                writes.append(self.text(t)[:40])
                        elif t.kind == "Name" and v is not None and v.kind == "Binop" and v.op in ("+", "-") and \
                                v.left.kind == "Name" and v.left.id == t.id and num_value(v.right) is not None:
                            b = getattr(t, "binding", None)
                            if b is None or b.func is not g:
                                counter.append(t.id)
        if signals:
            return "frame", "uses " + ", ".join(sorted(set(signals))[:4])
        if counter:
            return "frame", "counts frames (" + ", ".join(sorted(set(counter))[:3]) + ")"
        if selftimed:
            return "self", "already times itself (" + ", ".join(sorted(set(selftimed))) + ")"
        if not has_if:
            return "medium", "does its work unconditionally every frame (it may have to)"
        if writes:
            return "medium", "writes game state every frame (" + ", ".join(sorted(set(writes))[:3]) + ")"
        if unknown:
            return "medium", "calls code it can't see (" + ", ".join(sorted(set(unknown))[:4]) + ")"
        return "high", "only checks state and reacts to a change"

    def gated(self, f):
        return bool(f.body.stats) and "mwluafix_gate(" in self.text(f.body.stats[0])

    # --- rules
    def run(self):
        for r in (self.r_priority, self.r_per_frame, self.r_timers, self.r_one_shot, self.r_data_guard,
                  self.r_keycode, self.r_lookups, self.r_event_fields, self.r_destroy, self.r_console, self.r_info_filter, self.r_reregister,
                  self.r_reload_timers, self.r_globals, self.r_toplevel, self.r_loops, self.r_logger_level,
                  self.r_log_triggers, self.r_loggers):
            r()
        return self.findings

    def r_priority(self):
        lim = self.cfg["priorityLimit"]
        for c, ev, _fn, _h, opts in self.registrations:
            pv = table_field(opts, "priority")
            if pv is None:
                continue
            p = num_value(pv)
            if p is not None:
                if abs(p) >= lim:
                    q = compress_priority(p, self.cfg)
                    self.add("G1", pv, f"{ev or '?'} handler priority {self.text(pv)}", f"priority {q}", "high",
                             [(pv.s, pv.e, str(q))])
                continue
            if pv.kind == "Name":
                b = getattr(pv, "binding", None)
                v = num_value(b.value) if b is not None and b.value is not None else None
                if v is None or abs(v) < lim:
                    continue
                q = compress_priority(v, self.cfg)
                only_prio = all(r.parent is not None and r.parent.kind == "Table" and
                                any(k == "priority" and vv is r for k, _x, vv in r.parent.fields) for r in b.reads)
                if not b.assigns and only_prio:
                    self.add("G1", pv, f"{ev or '?'} handler priority {pv.id} = {self.text(b.value)}",
                             f"{pv.id} = {q}", "high", [(b.value.s, b.value.e, str(q))])
                else:
                    self.add("G1", pv, f"{ev or '?'} handler priority {pv.id} = {self.text(b.value)} (also used "
                             f"for something else)", f"use {q}")
            else:
                self.add("G1", pv, f"{ev or '?'} handler priority computed: {self.text(pv)[:60]}",
                         f"keep |priority| under {lim}")

    def _gate_edit(self, f):
        k = self._gate_next
        self._gate_next += 1
        return (f.params_end, f.params_end, f" if mwluafix_gate({k}, {self.cfg['minInterval']}) then return end")

    def r_per_frame(self):
        seen = set()
        for c, ev, fn, harg, opts in self.registrations:
            if ev not in PER_FRAME:
                continue
            if fn is None:
                self.add("G2", c, f"{ev} handler {self.text(harg)[:40]} can't be followed (not a local function)")
                continue
            if id(fn) in seen:
                continue
            seen.add(id(fn))
            name = harg.id if harg.kind == "Name" else "(inline function)"
            self.r_frame_costs(fn, ev, name)
            if self.gated(fn):
                continue
            cls, why = self.classify(fn)
            if cls in ("frame", "self"):
                self.add("G2", c, f"{ev} handler {name}: {why}", "left alone", "info")
                continue
            other = [r for r in (self.name_uses(harg) if harg.kind == "Name" else [])
                     if not (r.parent is not None and r.parent.kind == "Call" and
                             L.dotted(r.parent.func) in ("event.register", "event.unregister", "event.isRegistered"))]
            if other:
                cls, why = "medium", why + f"; also called directly (line {self.line(other[0])})"
            more = self.events_of_function(fn) - {ev}
            if more:
                cls, why = "medium", why + "; also handles " + ", ".join(sorted(more))
            self.add("G2", c, f"{ev} handler {name} every frame: {why}",
                     f"run it at most every {self.cfg['minInterval']} s", cls, [self._gate_edit(fn)], {"gate"})

    def r_frame_costs(self, fn, ev, name):
        look, io, cat, tbl, box, logs = [], [], 0, 0, 0, 0
        for g in self.closure(fn):
            for n in L.walk(g.body):
                if n.kind == "Call":
                    d = L.dotted(n.func) or ""
                    if d in LOOKUPS:
                        look.append(d)
                    elif d in CONFIG_IO or d.startswith("lfs."):
                        io.append(d)
                    elif d == "tes3.messageBox":
                        box += 1
                    elif d in LOGS:
                        logs += 1
                elif n.kind == "Method" and n.name in ("debug", "trace", "info"):
                    logs += 1
                elif n.kind == "Binop" and n.op == "..":
                    cat += 1
                elif n.kind == "Table":
                    tbl += 1
        parts = []
        if io:
            parts.append("file/config I/O (" + ", ".join(sorted(set(io))) + ")")
        if look:
            parts.append(f"{len(look)} uncached lookup(s) ({', '.join(sorted(set(look))[:3])})")
        if box:
            parts.append(f"{box} message box call(s)")
        if cat >= 3:
            parts.append(f"{cat} string joins")
        if tbl >= 3:
            parts.append(f"{tbl} new tables")
        if parts:
            self.add("G5", fn, f"{ev} handler {name}, every frame: " + "; ".join(parts),
                     "look things up once (initialized/loaded), keep I/O and allocations out of the frame",
                     "report-high" if io else "report")
        if logs:
            self.add("F1", fn, f"{ev} handler {name} logs every frame ({logs} call(s))", "log shim", "trigger")

    def r_timers(self):
        mi = self.cfg["minInterval"]
        for c in self.calls:
            if L.dotted(c.func) != "timer.start" or not c.args or c.args[0].kind != "Table":
                continue
            t = c.args[0]
            dur, it, cb = table_field(t, "duration"), table_field(t, "iterations"), table_field(t, "callback")
            dv, iv = num_value(dur), num_value(it)
            fn = self.func_of(cb)
            if fn is not None and iv is not None and (iv < 0 or iv > 1) and dv is not None and dv < 1 and any(
                    n.kind == "Call" and L.dotted(n.func) in LOGS for g in self.closure(fn) for n in L.walk(g.body)):
                self.add("F1", c, f"a {self.text(dur)} s repeating timer logs", "log shim", "trigger")
            if dv is None or iv is None or iv != -1 or dv >= mi:
                continue
            if fn is None:
                self.add("G3", c, f"timer every {self.text(dur)} s, forever; its callback can't be followed",
                         f"{mi} s if it only polls")
                continue
            if self.gated(fn):
                continue
            cls, why = self.classify(fn)
            if cls in ("frame", "self"):
                self.add("G3", c, f"timer every {self.text(dur)} s forever: {why}", "left alone", "info")
                continue
            self.add("G3", dur, f"timer every {self.text(dur)} s forever: {why}", f"duration {mi}", cls,
                     [(dur.s, dur.e, str(mi))])

    def r_one_shot(self):
        regs = {}
        for reg in self.registrations:
            regs.setdefault(id(reg[2]) if reg[2] is not None else id(reg[0]), []).append(reg)
        for lst in regs.values():
            c, ev, fn, harg, opts = lst[0]
            if fn is None or ev is None or ev in ONCE_EVENTS:
                continue
            flag, flag_set = self._done_flag(fn)
            if flag is None:
                continue
            if any(n.kind == "Call" and L.dotted(n.func) == "event.unregister" for n in L.walk(fn.body)):
                continue
            if any(table_field(r[4], "doOnce") is not None for r in lst):
                continue
            name = harg.id if harg.kind == "Name" else None
            b = getattr(flag_set.targets[0], "binding", None)
            assigns = b.assigns if b is not None else self.gassign.get(flag, [])
            rearm = [a for a in assigns if a is not flag_set and not (
                a.kind == "Assign" and all(e.kind == "True" for e in a.exprs))]
            if rearm:
                self.add("G4", c, f"{ev} handler {name or '(inline)'} is a one-shot ({flag}) that is re-armed at "
                         f"line {self.line(rearm[0])}", "left alone (re-armed)", "info")
                continue
            if name is None or self.func_of(harg) is None:
                self.add("G4", c, f"{ev} handler (inline function) does its job once ({flag}) and stays "
                         f"registered, called for nothing ever after", "make it a local function and "
                         "event.unregister it when done", "report")
                continue
            if len({self.text(r[0].args[0]) for r in lst}) > 1:
                self.add("G4", c, f"{name}: one-shot ({flag}) registered for several events", "unregister each")
                continue
            if opts is not None and opts.kind != "Table":
                self.add("G4", c, f"{ev} handler {name}: one-shot ({flag}); its options aren't literal",
                         "event.unregister it when done")
                continue
            filt = table_field(opts, "filter")
            if filt is not None and not (is_literalish(filt) or filt.kind == "Name" and
                                         getattr(filt, "binding", None) is not None and not filt.binding.assigns
                                         and filt.binding.decl.s < fn.s):
                self.add("G4", c, f"{ev} handler {name}: one-shot ({flag}); its filter {self.text(filt)[:30]} "
                         f"may change", "event.unregister it with the same filter")
                continue
            hb = harg.binding
            if hb is not None and not (hb.kind == "localfunc" and hb.value is fn) and hb.decl.s >= fn.s:
                self.add("G4", c, f"{ev} handler {name}: one-shot; its name isn't visible inside it",
                         "event.unregister it when done")
                continue
            ext = f", {{ filter = {self.text(filt)} }}" if filt is not None else ""
            call = f" event.unregister({self.text(c.args[0])}, {name}{ext})"
            self.add("G4", c, f"{ev} handler {name} does its job once ({flag} = true) and stays registered",
                     "event.unregister it when the flag is set", "high", [(flag_set.e, flag_set.e, call)])

    def _done_flag(self, fn):
        """(flag, the `flag = true` statement) for `if flag then return end ... flag = true` or
        `if not flag then ... flag = true ... end` (the whole body), flag a variable from outside fn."""
        st = fn.body.stats
        if not st or st[0].kind != "If" or len(st[0].clauses) != 1 or st[0].orelse is not None:
            return None, None
        cond, blk = st[0].clauses[0]
        flag = scope = None
        if cond.kind == "Name" and len(blk.stats) == 1 and blk.stats[0].kind == "Return" and not blk.stats[0].exprs:
            flag, scope = cond, fn.body
        elif cond.kind == "Unop" and cond.op == "not" and cond.operand.kind == "Name" and len(st) == 1:
            flag, scope = cond.operand, blk
        if flag is None:
            return None, None
        b = getattr(flag, "binding", None)
        if b is not None and b.func is fn:
            return None, None
        for n in L.walk_no_funcs(scope):
            if n.kind == "Assign" and len(n.targets) == 1 and n.targets[0].kind == "Name" and \
                    n.targets[0].id == flag.id and n.exprs and n.exprs[0].kind == "True" and \
                    getattr(n.targets[0], "binding", None) is b:
                return flag.id, n
        return None, None

    def r_data_guard(self):
        for n in self.nodes:
            if n.kind != "Index" or n.field is None:
                continue
            if n.parent is not None and n.parent.kind == "Index" and n.parent.obj is n:
                continue                                   # only the outermost field of a chain
            chain, cur = [], n
            while cur.kind == "Index" and cur.field is not None:
                chain.append(cur)
                cur = cur.obj
            datas = [x for x in chain if x.field == "data" and x is not n]
            if not datas:
                continue
            dnode = datas[-1]
            base = dnode.obj
            bt = L.dotted(base)
            if bt is None or bt in ("tes3.player", "tes3.player1stPerson", "tes3.mobilePlayer.reference"):
                continue
            last = bt.split(".")[-1]
            if not REF_NAME.search(last):
                continue                                   # self.data, config.data...: not a reference
            if base.kind == "Name" and getattr(base, "binding", None) is not None:
                v = base.binding.value
                if v is not None and L.dotted(v) in ("tes3.player", "tes3.mobilePlayer.reference"):
                    continue
            f = L.enclosing_function(n)
            if self._data_checked(f.body if f is not None else self.tree.body, bt):
                continue
            if not self._rvalue_slot(n):
                lv = sorted((x for x in chain if x.e >= dnode.e and x is not n), key=lambda x: x.e)
                g = " and ".join(self.src[n.s:x.e] for x in lv)
                if n.parent is not None and n.parent.kind == "Assign" and any(t is n for t in n.parent.targets) \
                        or n.parent is not None and n.parent.kind in ("Index", "Method", "Call", "Table", "Binop",
                                                                       "Return", "Local", "Assign", "Unop", "Paren"):
                    self._nil_fix("A1", n, g, f"{self.text(n)[:60]} used without checking {bt}.data (nil on "
                                  f"references that can't hold Lua data)")
                continue
            levels = sorted((x for x in chain if x.e >= dnode.e), key=lambda x: x.e)
            rep = "(" + " and ".join(self.src[n.s:x.e] for x in levels) + ")"
            self.add("A1", n, f"{self.text(n)[:60]} read without checking {bt}.data (nil on references that "
                     f"can't hold Lua data)", rep, "high", [(n.s, n.e, rep)])

    def _rvalue_slot(self, n):
        p = n.parent
        if p is None:
            return False
        if p.kind == "Local" and any(x is n for x in p.exprs) and len(p.exprs) <= len(p.names):
            return True
        if p.kind == "If" and any(cond is n for cond, _b in p.clauses):
            return True
        if p.kind == "Unop" and p.op == "not" or p.kind == "Binop" and p.op in ("==", "~=", "<", ">", "<=", ">="):
            return self._rvalue_slot(p) or self._in_condition(p)
        if p.kind == "Binop" and p.op in ("and", "or"):
            return self._in_condition(n)
        return False

    def _in_condition(self, n):
        p = n
        while p.parent is not None and p.parent.kind == "Binop" and p.parent.op in ("and", "or"):
            p = p.parent
        q = p.parent
        if q is None:
            return False
        if q.kind == "If":
            return any(c is p for c, _b in q.clauses)
        return q.kind == "While" and q.cond is p

    def _data_checked(self, scope, bt):
        want_d, want_s = bt + ".data", bt + ".supportsLuaData"
        for m in L.walk(scope):
            if m.kind != "Index":
                continue
            d = L.dotted(m)
            if d == want_s:
                return True
            if d == want_d:
                p = m.parent
                if p is not None and (p.kind == "Binop" and p.op in ("and", "or") and p.left is m or
                                      p.kind == "Unop" and p.op == "not" or
                                      p.kind == "Binop" and p.op in ("==", "~=") or
                                      p.kind == "If" or p.kind == "Assign" and any(t is m for t in p.targets)):
                    return True
        return False

    def r_keycode(self):
        for n in self.nodes:
            if n.kind != "Index" or n.field not in KEY_FIELDS:
                continue
            bt = L.dotted(n.obj)
            if not bt or not re.search(r"(?i)config|cfg|setting|key|bind", bt):
                continue
            if n.parent is not None and n.parent.kind == "Assign" and any(t is n for t in n.parent.targets):
                continue
            root = n.obj
            while root.kind == "Index":
                root = root.obj
            rb = getattr(root, "binding", None) if root.kind == "Name" else None
            if rb is not None and rb.kind == "for" and n.obj.kind == "Name":
                continue                                    # a loop variable is never nil
            f = L.enclosing_function(n)
            scope = f.body if f is not None else self.tree.body
            if self._guard_checked(scope, bt):
                continue
            self._nil_fix("A2", n, bt, f"{bt}.{n.field} read with no check (an unbound key is nil)")

    # --- nil guards (A1-A4)
    def _check_pos(self, m):
        """Is m (an x or x.y read) a nil check: x and ..., not x, if x, x == / ~= ..., type(x), assert(x)?"""
        p = m.parent
        if p is None:
            return False
        if p.kind == "Paren":
            return self._check_pos(p)
        if p.kind == "Binop" and (p.op in ("and", "or") and p.left is m or p.op in ("==", "~=")):
            return True
        if p.kind == "Binop" and p.op == "and" and p.right is m and (
                self._in_condition(m) or p.parent is not None and p.parent.kind == "Binop" and
                p.parent.op == "and" and p.parent.left is p):
            return True                                     # a and m and m.x / if a and m then
        if p.kind == "Unop" and p.op == "not":
            return True
        if p.kind == "If" and any(c is m for c, _b in p.clauses):
            return True
        if p.kind in ("While", "Repeat") and p.cond is m:
            return True
        if p.kind == "Call" and L.dotted(p.func) in ("type", "assert") and p.args and p.args[0] is m:
            return True
        return False

    def _guard_checked(self, scope, g, binding=None):
        key = (id(scope), g, id(binding))
        cache = self.__dict__.setdefault("_gcache", {})
        if key not in cache:
            hit = False
            for m in L.walk(scope):
                if m.kind not in ("Name", "Index") or L.dotted(m) != g:
                    continue
                if binding is not None and getattr(m, "binding", None) is not binding:
                    continue
                if self._check_pos(m) or (m.parent is not None and m.parent.kind == "Assign" and
                                          any(t is m for t in m.parent.targets)):
                    hit = True
                    break
            cache[key] = hit
        return cache[key]

    @staticmethod
    def _multi_tail(c):
        """c is the last expression of a list that can take several values (truncating it would change them)."""
        p = c.parent
        if c.kind not in ("Call", "Method", "Vararg") or p is None:
            return False
        if p.kind == "Local":
            return p.exprs and p.exprs[-1] is c and len(p.names) > len(p.exprs)
        if p.kind == "Return":
            return p.exprs and p.exprs[-1] is c
        if p.kind == "Assign":
            return p.exprs and p.exprs[-1] is c and len(p.targets) > len(p.exprs)
        return False

    def _wrap(self, node, g, how):
        L_ = node.e - node.s
        if how == "stmt":
            return [(node.s, node.s, f"if {g} then ", (1, -L_)), (node.e, node.e, " end", (0, L_))]
        return [(node.s, node.s, f"({g} and ", (1, -L_)), (node.e, node.e, ")", (0, L_))]

    def nil_plan(self, n, g):
        """(edits, how) guarding n (a read through g, which may be nil) so it is skipped when g is nil and
        nothing changes when it isn't; (None, why) when no rewrite is certain."""
        p = n.parent
        if p is None:
            return None, "no enclosing code"
        in_slot = p.kind in ("Local", "Return") and any(x is n for x in p.exprs) or \
            p.kind == "Assign" and any(x is n for x in p.exprs)
        # 1. the read itself is the value: x.y == z, if x.y, (in a condition) x.y and ..., local v = x.y
        if n.kind == "Index" or not self._multi_tail(n):
            if p.kind == "Binop" and p.op in ("==", "~=") or \
                    p.kind == "If" and any(c is n for c, _b in p.clauses) or \
                    p.kind == "While" and p.cond is n or \
                    p.kind == "Binop" and p.op in ("and", "or") and self._in_condition(n) or \
                    in_slot and p.kind != "Assign" and n.kind == "Index":
                return self._wrap(n, g, "expr"), "and-guard"
        # 2. climb to the condition operand, the local's value or the statement
        c, crossed_table = n, False
        while c.parent is not None and c.parent.kind not in ("Block", "Function", "If", "While", "Repeat", "Local",
                                                             "Assign", "Return", "CallStat") and \
                not (c.parent.kind == "Binop" and c.parent.op in ("and", "or")):
            crossed_table |= c.parent.kind == "Table"
            c = c.parent
        q = c.parent
        if q is not None and (q.kind == "Binop" and q.op in ("and", "or") and self._in_condition(c) or
                              q.kind == "If" and any(x is c for x, _b in q.clauses) or
                              q.kind == "While" and q.cond is c):
            return self._wrap(c, g, "expr"), "and-guard on the condition"
        if q is not None and q.kind == "Repeat" and q.cond is c:
            return None, "in a repeat-until condition (a guard there could loop forever)"
        if q is not None and q.kind in ("Local", "Return") and any(x is c for x in q.exprs):
            if crossed_table:
                return None, "inside a table constructor in a local/return value"
            if self._multi_tail(c):
                return None, "the value is a call whose extra return values are used"
            return self._wrap(c, g, "expr"), "and-guard on the value"
        st = stmt_of(n)
        if st.parent is None or st.parent.kind != "Block":
            return None, "not inside a statement"
        if st.kind == "CallStat" or st.kind == "Assign" and len(st.targets) == 1 and len(st.exprs) == 1:
            t = (L.dotted(st.targets[0]) or "") if st.kind == "Assign" else ""
            if st.kind == "Assign" and t and any(x == t or x.startswith(t + ".") for x in g.split(" and ")):
                return None, "the statement assigns the value being checked"
            return self._wrap(st, g, "stmt"), "if-guard on the statement"
        if q is not None and q.kind == "Binop":
            return None, "in an and/or expression outside a condition"
        return None, f"inside a {st.kind.lower()} statement that can't be wrapped without changing scope or flow"

    def _nil_fix(self, rule, n, g, what):
        edits, how = self.nil_plan(n, g)
        if edits is None:
            return self.add(rule, n, what, f"check {g} first - left as a report: {how}", "report")
        seen = self.__dict__.setdefault("_nil_seen", set())
        sig = tuple((s, e, t) for s, e, t, _o in edits)
        if sig in seen:                                      # same guard as another read in this place
            return self.add(rule, n, what, f"{how} on {g} (with the read above)", "high")
        seen.add(sig)
        tgt = (edits[0][0], edits[1][0])
        body = " ".join(self.src[tgt[0]:tgt[1]].split())
        prev = edits[0][2] + (body if len(body) <= 90 else body[:80] + " ... ") + edits[1][2]
        return self.add(rule, n, what, f"{how}: {prev}", "high", edits)

    def _uses_of(self, n):
        """n.x / n:m() reads of n (a nil-able value): the Index/Method nodes that would fail."""
        p = n.parent
        return p if p is not None and p.kind in ("Index", "Method") and p.obj is n else None

    def _guard_binding_uses(self, rule, b, g, what_of):
        if b.assigns or any(self._check_pos(r) for r in b.reads):
            return
        for r in b.reads:
            u = self._uses_of(r)
            if u is not None and u.s >= (self.nodes[0].s if self.nodes else 0):
                self._nil_fix(rule, u, g, what_of(u))

    def r_lookups(self):
        decl_b = {}
        for n in self.nodes:
            b = getattr(n, "binding", None) if n.kind == "Name" else None
            if b is not None and b.kind == "local":
                decl_b.setdefault(id(b.decl), {})[b.name] = b
        for st in self.nodes:
            if st.kind == "Local" and len(st.names) == 1 and len(st.exprs) == 1 and st.exprs[0].kind == "Call" \
                    and L.dotted(st.exprs[0].func) in NIL_LOOKUPS:
                d = L.dotted(st.exprs[0].func)
                b = decl_b.get(id(st), {}).get(st.names[0])
                if b is not None:
                    self._guard_binding_uses("A3", b, st.names[0], lambda u, d=d, nm=st.names[0]: (
                        f"{self.text(u)[:50]} - {nm} comes from {d}, which returns nil when nothing is found, and is "
                        f"never checked"))
        for c in self.calls:
            d = L.dotted(c.func)
            if d not in NIL_LOOKUPS or self._uses_of(c) is None:
                continue
            what = f"{self.text(c)[:50]} used directly ({d} returns nil when nothing is found)"
            st = stmt_of(c)
            head = st.call if st.kind == "CallStat" else st.targets[0] if st.kind == "Assign" and \
                len(st.targets) == 1 and len(st.exprs) == 1 else None
            while head is not None and head is not c and head.kind in ("Index", "Method", "Call"):
                head = head.obj if head.kind in ("Index", "Method") else head.func
            if head is c and st.parent is not None and st.parent.kind == "Block" and \
                    not any(m.kind == "Name" and m.id == NIL_TMP for m in L.walk(st)):
                pre = f"do local {NIL_TMP} = {self.text(c)} if {NIL_TMP} then {NIL_TMP}"
                L_ = st.e - st.s
                edits = [(c.s, c.e, pre, (1, -L_)), (st.e, st.e, " end end", (0, L_))]
                self.add("A3", c, what, f"held in a local and checked: do local {NIL_TMP} = {d}(...) if {NIL_TMP} "
                         f"then ... end end", "high", edits)
            else:
                self.add("A3", c, what, f"keep the result in a local and check it - left as a report: the lookup "
                         f"is indexed inside a bigger expression", "report")

    def r_event_fields(self):
        for c, ev, fn, harg, opts in self.registrations:
            fields = NULLABLE_EVENT_FIELDS.get(ev or "")
            if not fields or fn is None or not fn.params:
                continue
            p = fn.params[0]
            done = self.__dict__.setdefault("_ev_done", set())
            for n in L.walk(fn.body):
                if n.kind != "Index" or n.field not in fields or n.obj.kind != "Name" or n.obj.id != p:
                    continue
                b = getattr(n.obj, "binding", None)
                if b is None or b.kind != "param" or b.decl is not fn or id(n) in done:
                    continue
                done.add(id(n))
                g = f"{p}.{n.field}"
                if self._guard_checked(fn.body, g):
                    continue
                par = n.parent
                if par is not None and par.kind == "Local" and len(par.names) == 1 and len(par.exprs) == 1 and \
                        par.exprs[0] is n:                  # local t = e.target ... t.x
                    for m in L.walk(fn.body):
                        bb = getattr(m, "binding", None) if m.kind == "Name" else None
                        if bb is not None and bb.decl is par:
                            if id(bb) not in done:
                                done.add(id(bb))
                                self._guard_binding_uses("A4", bb, par.names[0], lambda u, g=g, nm=par.names[0]: (
                                    f"{self.text(u)[:50]} - {nm} is {g}, nil in some {ev} events, never checked"))
                            break
                    continue
                u = self._uses_of(n)
                if u is not None:
                    self._nil_fix("A4", u, g, f"{self.text(u)[:50]} - {g} is nil in some {ev} events and is "
                                  f"never checked")

    def r_destroy(self):
        for blk in (n for n in self.nodes if n.kind == "Block"):
            for i, st in enumerate(blk.stats):
                if not (st.kind == "CallStat" and st.call.kind == "Method" and st.call.name == "destroy"):
                    continue
                x = L.dotted(st.call.obj)
                if not x:
                    continue
                for later in blk.stats[i + 1:]:
                    if later.kind in ("Assign", "Local") and any(L.dotted(t) == x for t in getattr(
                            later, "targets", [])):
                        break
                    hit = next((m for m in L.walk(later) if m.kind in ("Index", "Name", "Method") and
                                L.dotted(m.obj if m.kind == "Method" else m) == x and not (
                                    m.parent is not None and m.parent.kind == "Assign" and
                                    any(t is m for t in m.parent.targets))), None)
                    if hit is not None:
                        self.add("B1", hit, f"{x} used after {x}:destroy() (line {self.line(st)}) - 'sol: self "
                                 f"argument is lua_nil'", "keep what you need (e.g. its parent) before destroying it")
                        break

    def r_console(self):
        for c in self.calls:
            if L.dotted(c.func) != "tes3.runLegacyScript" or not c.args:
                continue
            cmd = table_field(c.args[0], "command")
            if cmd is None or cmd.kind != "String":
                continue
            v = (L.string_value(cmd.raw) or "").strip()
            w = v.split()[0].lower() if v.split() else ""
            if w in CONSOLE_ONLY:
                self.add("C1", c, f"runLegacyScript \"{v[:40]}\": {w} is a console command, not a script command "
                         f"(fails to compile at runtime)", CONSOLE_ONLY[w])

    def r_info_filter(self):
        for c, ev, fn, harg, opts in self.registrations:
            if ev != "infoFilter" or fn is None or not fn.params:
                continue
            p = fn.params[0]
            reads, other_passes, returns = [], [], []
            for n in L.walk_no_funcs(fn.body):
                if n.kind == "Index" and L.dotted(n) == f"{p}.info.text":
                    reads.append(n)
                elif n.kind == "Index" and L.dotted(n) == f"{p}.passes":
                    par = n.parent
                    if par is not None and par.kind == "Assign" and any(t is n for t in par.targets):
                        i = [id(t) for t in par.targets].index(id(n))
                        if i < len(par.exprs) and par.exprs[i].kind == "False":
                            continue                       # blocking only: a no-op for responses that failed
                    other_passes.append(n)
                elif n.kind == "Return" and n.exprs:
                    returns.append(n)
            if not reads or (fn.body.stats and f"not {p}.passes" in self.text(fn.body.stats[0])):
                continue
            if other_passes:
                if other_passes[0].s > reads[0].s:
                    self.add("D1", reads[0], f"infoFilter reads {p}.info.text (a disk read) before checking "
                             f"{p}.passes", f"check {p}.passes and the dialogue type first")
                continue
            if returns:
                self.add("D1", reads[0], f"infoFilter reads {p}.info.text for every response; it returns a value, "
                         f"so returning early could change what it blocks", f"check {p}.passes first", "medium",
                         [(fn.params_end, fn.params_end, f" if not {p}.passes then return end")])
                continue
            self.add("D1", reads[0], f"infoFilter reads {p}.info.text for every response the engine tries (each one "
                     f"a disk read; a greeting search can freeze for minutes)", f"return early unless {p}.passes",
                     "high", [(fn.params_end, fn.params_end, f" if not {p}.passes then return end")])

    def _again_events(self, node):
        """The events (other than once-only ones) whose handler node's code is in, and that handler."""
        outer = L.enclosing_function(node)
        while outer is not None:
            evs = self.events_of_function(outer)
            if evs:
                return sorted(e for e in evs if e not in ONCE_EVENTS), outer
            outer = L.enclosing_function(outer)
        return [], None

    def r_reregister(self):
        for c, ev, fn, harg, opts in self.registrations:
            again, outer = self._again_events(c)
            if not again:
                continue
            if table_field(opts, "unregisterOnLoad") is not None or table_field(opts, "doOnce") is not None:
                continue
            p, guarded = c.parent, False
            while p is not None and p is not outer:
                if p.kind == "If" and any("isRegistered" in self.text(cond) for cond, _b in p.clauses):
                    guarded = True
                p = p.parent
            if guarded or any(n.kind == "Call" and L.dotted(n.func) == "event.unregister" and len(n.args) > 1 and
                              self.text(n.args[1]) == self.text(harg) for n in L.walk(outer.body)):
                continue
            where = "/".join(again)
            if harg.kind == "Name" and self.func_of(harg) is None:
                self.add("H1", c, f"{ev or '?'} handler {harg.id} registered again on every {where}; it isn't a "
                         f"function of this file, so it can't be guarded safely", "guard it with event.isRegistered")
                continue
            if harg.kind != "Name":
                self.add("H1", c, f"{ev or '?'} handler registered inside the {where} handler as a new function: "
                         f"one more copy runs every time {where} fires", "hoist it into a local function and "
                         "register it once (or guard with event.isRegistered)", "report-high")
                continue
            st = stmt_of(c)
            if st.kind != "CallStat" or st.call is not c or not side_effect_free(opts) or \
                    not side_effect_free(c.args[0]):
                self.add("H1", c, f"{ev} handler {harg.id} registered again on every {where}",
                         "guard it with event.isRegistered")
                continue
            o = f", {self.text(opts)}" if opts is not None else ""
            pre = f"if not event.isRegistered({self.text(c.args[0])}, {harg.id}{o}) then "
            self.add("H1", c, f"{ev} handler {harg.id} registered from the {where} handler with no isRegistered "
                     f"check (when it is still registered MWSE refuses the duplicate and logs a warning and a "
                     f"traceback)", "event.isRegistered guard (same behaviour, no log spam)", "high",
                     [(st.s, st.s, pre), (st.e, st.e, " end")])

    def r_reload_timers(self):
        cancels = any(n.kind == "Method" and n.name == "cancel" for n in self.nodes)
        for c in self.calls:
            if L.dotted(c.func) != "timer.start" or not c.args or c.args[0].kind != "Table":
                continue
            evs, _outer = self._again_events(c)
            if not evs:
                continue
            t = c.args[0]
            iv = num_value(table_field(t, "iterations"))
            typ = L.dotted(table_field(t, "type")) or "timer.simulate"
            if iv is None or not (iv == -1 or iv > 1):
                continue
            kept = c.parent is not None and c.parent.kind in ("Local", "Assign")
            if kept and cancels:
                continue
            if set(evs) <= {"loaded", "load"} and typ != "timer.real":
                continue                     # simulate/game timers are dropped when a save loads: fine to restart
            self.add("H2", c, f"repeating {typ} started in the {'/'.join(evs)} handler and never cancelled: one "
                     f"more runs each time it fires", "keep the handle; cancel the old timer before starting one",
                     "report-high")

    def r_globals(self):
        known = {"tes3", "mwse", "event", "timer", "tes3ui", "mge", "json", "lfs", "include", "require", "_G"}
        names = sorted(nm for nm in self.gassign if nm not in known)
        if names:
            self.add("H3", self.gassign[names[0]][0], f"{len(names)} global(s) set without local: "
                     f"{', '.join(names[:8])}" + (" ..." if len(names) > 8 else ""),
                     "add local (unless another mod reads them on purpose)")

    def r_toplevel(self):
        if not self.rel.lower().endswith("main.lua"):
            return                    # other files run when required, usually from an initialized handler
        hits = []
        for n in self.nodes:
            if n.kind not in ("Index", "Call"):
                continue
            d = L.dotted(n.func if n.kind == "Call" else n)
            if d in ("tes3.player", "tes3.mobilePlayer", "tes3.getObject", "tes3.getReference", "tes3.findGMST",
                     "tes3.getGlobal", "tes3.worldController", "tes3.getPlayerCell") and \
                    L.enclosing_function(n) is None:
                if n.kind == "Index" and n.parent is not None and n.parent.kind == "Call" and n.parent.func is n:
                    continue
                hits.append((n, d))
        if hits:
            n, d = hits[0]
            self.add("H4", n, f"{d} used when the file loads ({len(hits)} place(s)), before the game data exists",
                     "move it into an initialized (or loaded) handler")

    def r_loops(self):
        for c in self.calls:
            d = L.dotted(c.func)
            if d == "tes3.messageBox" and inside_loop(c):
                self.add("H6", c, "tes3.messageBox inside a loop", "collect the lines and show one box")
            elif d in LOGS and inside_loop(c):
                self.add("F1", c, f"{d} inside a loop", "log shim", "trigger")

    def r_logger_level(self):
        for c in self.nodes:
            if c.kind == "Method" and c.name in ("setLogLevel", "setLevel") and c.args and c.args[0].kind == "String" \
                    and (L.string_value(c.args[0].raw) or "").upper() in ("DEBUG", "TRACE"):
                self._level_edit(c.args[0], "logger level set to")
                continue
            if c.kind == "Call":
                fname = L.dotted(c.func) or ""
                ok = fname.lower().endswith(("logger.new", "logging.new"))
            elif c.kind == "Method":
                ok = c.name == "new" and "log" in (L.dotted(c.obj) or "").lower()
            else:
                continue
            if not ok or not c.args or c.args[0].kind != "Table":
                continue
            for key in ("logLevel", "level"):
                v = table_field(c.args[0], key)
                if v is not None and v.kind == "String" and (L.string_value(v.raw) or "").upper() in ("DEBUG", "TRACE"):
                    self._level_edit(v, "logger created at")

    def _level_edit(self, v, what):
        q = v.raw[0] if v.raw[0] in "'\"" else '"'
        self.add("F2", v, f"{what} {self.text(v)} (every debug line reaches MWSE.log)", "INFO", "high",
                 [(v.s, v.e, f"{q}INFO{q}")])

    def r_log_triggers(self):
        """Log-spam signs beyond the per-frame/loop/timer ones: debug flags on by default, logging in handlers
        of events that fire often."""
        for n in self.nodes:
            nm = val = None
            if n.kind == "Local":
                for i, x in enumerate(n.names):
                    if i < len(n.exprs) and n.exprs[i].kind == "True" and DEBUG_FLAG.fullmatch(x):
                        nm, val = x, n.exprs[i]
            elif n.kind == "Table":
                for k, _kx, v in n.fields:
                    if k and v.kind == "True" and DEBUG_FLAG.fullmatch(k):
                        nm, val = k, v
            if nm and self.log_calls():
                self.add("F1", val, f"debug flag {nm} = true by default", "log shim", "trigger")
        for c, ev, fn, harg, opts in self.registrations:
            if fn is None or ev not in FREQUENT_EVENTS or ev in PER_FRAME:
                continue
            if any(n.kind == "Call" and L.dotted(n.func) in LOGS for g in self.closure(fn, 2) for n in L.walk(g.body)):
                self.add("F1", c, f"the {ev} handler logs ({ev} fires often)", "log shim", "trigger")

    def log_calls(self):
        """How many print / mwse.log calls reach the global functions (not a local of the same name)."""
        n = 0
        for c in self.calls:
            if c.func.kind == "Name" and c.func.id == "print" and getattr(c.func, "binding", None) is None:
                n += 1
            elif c.func.kind == "Index" and L.dotted(c.func) == "mwse.log" and \
                    getattr(c.func.obj, "binding", None) is None:
                n += 1
        return n + len(self.logger_creations())

    def logger_creations(self):
        """mwse.Logger.new(...) / require("logging.logger").new(...) / .getLogger(...) calls (also through a
        local holding the library), not already wrapped: (call node) list."""
        out = []
        for c in self.calls:
            f = c.func
            if f.kind != "Index" or f.field not in ("new", "getLogger"):
                continue
            o = f.obj
            while o.kind == "Paren":
                o = o.expr
            if o.kind == "Name" and getattr(o, "binding", None) is not None and o.binding.value is not None \
                    and not o.binding.assigns:
                o = o.binding.value
            ok = (L.dotted(o) or "") in ("mwse.Logger", "mwseLogger")
            if not ok and o.kind == "Call" and o.func.kind == "Name" and o.func.id in ("require", "include") \
                    and o.args and o.args[0].kind == "String":
                ok = (L.string_value(o.args[0].raw) or "").lower() in ("logging.logger", "logger", "mwse.logger")
            if not ok:
                continue
            par = getattr(c, "parent", None)
            if par is not None and par.kind == "Call" and L.dotted(par.func) == "mwluafix_log.wrap":
                continue
            out.append(c)
        return out

    def r_loggers(self):
        for c in self.logger_creations():
            self.add("F1", c, "logger created here", "its trace/debug/info lines go through the log shim", "logger",
                     [(c.s, c.s, "mwluafix_log.wrap("), (c.e, c.e, ")")], ["shim"])

    def requires(self):
        out = []
        for c in self.calls:
            if c.func.kind == "Name" and c.func.id in ("require", "include") and c.args and \
                    c.args[0].kind == "String" and L.enclosing_function(c) is None:
                out.append(L.string_value(c.args[0].raw) or "")
        return out


# ---------------------------------------------------------------------------------------------- what we add
GATE_HELPER = ("local mwluafix_gate do local last, clock = {}, os.clock mwluafix_gate = function(k, s) "
               "local t = clock() local l = last[k] if l and t >= l and t - l < s then return true end "
               "last[k] = t return false end end ")


def log_name(mod_key):
    return re.sub(r"[^\w\- ]", ".", mod_key) or "mod"


def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


SHIM_END = "--[[/mwluafix_logshim]]"
# the version-1 shim (print / mwse.log only, no cap, no logger wrap): replaced by the current one on sight
SHIM_V1_RE = re.compile(r"local print, mwse = \(function\(_p, _m\) local fmt, find, lower, sub = string\.format, "
                        r"[^\n]*?\{ __index = _m, __newindex = _m \}\) end\)\(print, mwse\) ")
SHIM_V = 2
LOG_SHIM_LUA = r"""
local print, mwse, mwluafix_log = (function(_p, _m)
local S = package.loaded[@KEY@]
if type(S) == "table" and S.v == @V@ then return S.print, S.mwse, S end
S = { v = @V@, redirected = 0, dropped = 0, collapsed = 0 }
package.loaded[@KEY@] = S
local C = @CFG@
local G, MARK = _G, @MARK@
local find, lower, sub, gsub, concat, fmt, date, select, tostring, pcall = string.find, string.lower, string.sub, string.gsub, table.concat, string.format, os.date, select, tostring, pcall
local dir = "Data Files\\MWSE\\logs"
local path, oldPath = dir .. "\\" .. C.name .. ".log", dir .. "\\" .. C.name .. ".old.log"
local t0 = os.time() - math.floor(os.clock()) - 1
local init, run, started, redirected, f, dead, busy, fails = 0, 0, false, false, nil, false, false, 0
local bytes, dirty, last, lastN, sec, secN, dropped, errs, errKeys = 0, false, nil, 0, -1, 0, 0, {}, 0
local function isErr(t)
local l = lower(#t > 4096 and sub(t, 1, 4096) or t)
for i = 1, #C.keep do
local ok, h = pcall(find, l, C.keep[i])
if ok and h then return true end
end
return false
end
local function out(s)
f:write(date("[%H:%M:%S] "), s, "\n")
bytes = bytes + #s + 12
dirty = true
end
local function pending()
if lastN > 0 then out("[previous line repeated " .. lastN .. " more time(s)]") lastN = 0 end
if dropped > 0 then out("[" .. dropped .. " line(s) dropped: more than " .. C.perSecond .. " in one second]") dropped = 0 end
end
local function flushAll()
if f then pending() if dirty then dirty = false f:flush() end end
end
local function rotate()
if f then pcall(f.close, f) f = nil end
if C.keepOld > 0 then os.remove(oldPath) os.rename(path, oldPath) else os.remove(path) end
f = io.open(path, "w")
bytes, last = 0, nil
if f then
pcall(f.setvbuf, f, "full", 16384)
f:write(date("[%Y-%m-%d %H:%M:%S] "), C.name, ": lines past its MWSE.log allowance (", MARK, ")\n")
end
return f
end
local function open()
pcall(function() lfs.mkdir(dir) end)
local ok, m = pcall(function() return lfs.attributes(path, "modification") end)
if ok and type(m) == "number" and m >= t0 then
path, oldPath = dir .. "\\" .. C.name .. ".luafix.log", dir .. "\\" .. C.name .. ".luafix.old.log"
end
return rotate()
end
local function toFile(t)
if t == last then lastN = lastN + 1 S.collapsed = S.collapsed + 1 return end
local s = os.time()
if s ~= sec then sec, secN = s, 0 end
secN = secN + 1
if C.perSecond > 0 and secN > C.perSecond then dropped = dropped + 1 S.dropped = S.dropped + 1 return end
if bytes >= C.maxBytes and not rotate() then dead = true return end
pending()
last = t
out(t)
S.redirected = S.redirected + 1
if not started then dirty = false f:flush() end
end
S.start = function()
if started then return end
started = true
pcall(flushAll)
pcall(function() timer.start({ type = timer.real, duration = C.flushSeconds, iterations = -1, persist = false, callback = function() pcall(flushAll) end }) end)
end
local function route(t, force)
if not started then
local ok, v = pcall(function() return tes3.isInitialized() end)
if ok and v then S.start() end
end
if force or isErr(t) then
if C.errorRepeat > 0 then
local k = gsub(sub(t, 1, (find(t, "\n", 1, true) or 201) - 1), "%d+", "#")
local n = errs[k] or 0
if n == 0 then
if errKeys >= 500 then errs, errKeys = {}, 0 end
errKeys = errKeys + 1
end
errs[k] = n + 1
if n >= C.errorRepeat then
if f then toFile(t) end
return false
end
end
if f then pending() out(t) dirty = false f:flush() end
return true
end
local _, nl = gsub(t, "\n", "")
nl = nl + 1
if not redirected then
if started then
if run + nl <= C.after then run = run + nl return true end
elseif init + nl <= C.init then
init = init + nl
return true
end
redirected = true
if not open() then
dead = true
_p(fmt("[%s] %s writes a lot to MWSE.log, but %s can't be opened: leaving it here", MARK, C.name, path))
return true
end
_p(fmt("[%s] %s has written %d line(s) to MWSE.log; its further output goes to %s (errors still show here)", MARK, C.name, init + run, path))
end
if dead or not f then return true end
toFile(t)
return false
end
local function fail(e)
fails = fails + 1
if fails >= 10 then dead = true end
if fails == 1 then pcall(_p, fmt("[%s] %s: log shim error (the line went to MWSE.log): %s", MARK, C.name, tostring(e))) end
end
local function decidePrint(n, ...)
local t
if n <= 1 then
t = tostring((...))
else
local parts = {}
for i = 1, n do parts[i] = tostring((select(i, ...))) end
t = concat(parts, "\t")
end
return route(t, false)
end
S.print = function(...)
if busy or dead then return _p(...) end
busy = true
local ok, pass = pcall(decidePrint, select("#", ...), ...)
busy = false
if not ok then fail(pass) return _p(...) end
if pass then return _p(...) end
end
local function decideLog(f0, ...)
local ok, t = pcall(fmt, tostring(f0), ...)
if not ok then t = tostring(f0) end
return route(t, false)
end
S.mwse = setmetatable({ log = function(f0, ...)
if busy or dead then return _m.log(f0, ...) end
busy = true
local ok, pass = pcall(decideLog, f0, ...)
busy = false
if not ok then fail(pass) pass = true end
if pass then return _m.log(f0, ...) end
end }, { __index = _m, __newindex = _m })
local function back(g, ok, ...)
if G.print == S.print then G.print = g end
if not ok then error((...), 0) end
return ...
end
local wrapped = setmetatable({}, { __mode = "k" })
local LV = { trace = 5, debug = 4, info = 3 }
local function wrap(lg)
for name, lv in pairs(LV) do
local orig = lg[name]
if type(orig) == "function" then
rawset(lg, name, function(self, ...)
if dead or self ~= lg or G.print == S.print then return orig(self, ...) end
local sd = type(lg.makeRecord) == "function" and type(lg.writeRecord) == "function" and lg.sharedData
if sd and type(sd.level) == "number" then
if sd.level < lv then return end
local rec = lg:makeRecord(lv)
local g = G.print
G.print = S.print
return back(g, pcall(lg.writeRecord, lg, rec, ...))
end
local g = G.print
G.print = S.print
return back(g, pcall(orig, self, ...))
end)
end
end
end
S.wrap = function(lg)
if type(lg) == "table" and not wrapped[lg] then
wrapped[lg] = true
pcall(wrap, lg)
end
return lg
end
S.flush = flushAll
S.stats = function() return { init = init, run = run, redirected = redirected, dead = dead, path = path, fails = fails, started = started } end
pcall(function()
event.register("initialized", S.start)
for _, ev in ipairs({ "loaded", "save", "menuEnter" }) do event.register(ev, function() pcall(flushAll) end) end
end)
pcall(function()
local p = newproxy(true)
getmetatable(p).__gc = function() pcall(flushAll) end
S.gc = p
end)
return S.print, S.mwse, S
end)(print, mwse) --[[/mwluafix_logshim]]
"""


def log_shim(mod_key, cfg):
    """The log shim, on one line (so no line number moves): local print, mwse and mwluafix_log for this file
    only (nothing global changes). The state lives in package.loaded, one per mod, built by whichever of the
    mod's files loads first. Like the old mwguard's log-spam guard: the first budgetInit lines (budget more after
    the initialized event) and anything that looks like an error reach MWSE.log; the rest go to
    Data Files\\MWSE\\logs\\<mod>.log (<mod>.luafix.log when something else wrote that file this session),
    with identical lines collapsed, a per-second cap and rotation at maxMB. trace/debug/info of the mod's own
    loggers (wrapped where it creates them) are sent through the same route; warn/error are left alone. Every
    file operation is pcall'd or returns nil; ten internal errors and it passes everything through."""
    lc = cfg["log"]
    keep = ", ".join(lua_str(p) for p in lc["keepPatterns"])
    conf = (f'{{ name = {lua_str(log_name(mod_key))}, init = {int(lc["budgetInit"])}, after = {int(lc["budget"])}, '
            f'keep = {{ {keep} }}, perSecond = {int(lc["perSecond"])}, maxBytes = {int(float(lc["maxMB"]) * 1048576)}, '
            f'keepOld = {int(lc["keepOld"])}, flushSeconds = {float(lc["flushSeconds"])}, '
            f'errorRepeat = {int(lc["errorRepeat"])} }}')
    body = " ".join(l for l in LOG_SHIM_LUA.split("\n") if l)
    return (body.replace("@KEY@", lua_str("mwluafix_logshim:" + log_name(mod_key))).replace("@V@", str(SHIM_V))
            .replace("@CFG@", conf).replace("@MARK@", lua_str(MARK)) + " ")


MARK_RE = re.compile(r"--\[\[" + MARK + r" (\d+): ([^\]]*)\]\] ")


def insert_point(src):
    """Where helpers go: the start of line 1 (after a UTF-8 BOM), or of line 2 after a shebang line. Nothing
    is put on a line of its own, so every line number in tracebacks and mwguard's reports stays the same."""
    i = 3 if src.startswith("\xef\xbb\xbf") else 0
    if src.startswith("#", i):
        j = src.find("\n", i)
        return len(src) if j < 0 else j + 1
    return i


def build_patch(src, findings, mod_key, cfg, level="high", want_shim=False):
    """(new text, rules applied) for the findings at or above level; (None, []) when there is nothing to do."""
    ok_conf = {"high"} if level == "high" else {"high", "medium"}
    edits, rules, needs = [], [], set()
    for f in findings:
        if f["conf"] in ok_conf and f["edits"]:
            edits += [tuple(x) if len(x) > 3 else (x[0], x[1], x[2], (1, 0)) for x in f["edits"]]
            rules.append(f["rule"])
            needs |= set(f["needs"])
    v1 = SHIM_V1_RE.search(src)
    if (want_shim or v1) and SHIM_END not in src:
        needs.add("shim")
        rules.append("F1")
    if not edits and "shim" not in needs:
        return None, []
    edits.sort(key=lambda x: (x[0], x[1], x[3]))    # inserts at one place: closers inner-first, openers outer-first
    edits = [x[:3] for x in edits]
    kept, last_end = [], -1
    for s, e, t in edits:                          # overlapping edits: the first wins (the next run gets the rest)
        if s < last_end or (s == e and s < last_end):
            continue
        kept.append((s, e, t))
        last_end = max(last_end, e)
    out = src
    if v1 and "shim" in needs:                     # upgrade in place: the old shim's span becomes the new one
        kept = [x for x in kept if x[0] >= v1.end() or x[1] <= v1.start()]
        kept.append((v1.start(), v1.end(), log_shim(mod_key, cfg)))
        kept.sort(key=lambda x: (x[0], x[1]))
    for s, e, t in reversed(kept):
        out = out[:s] + t + out[e:]
    ip = insert_point(out)
    m = MARK_RE.match(out, ip)
    allr = sorted(set(m.group(2).split() if m else []) | set(rules))
    head = f"--[[{MARK} {VERSION}: {' '.join(allr)}]] "
    if "shim" in needs and not v1 and SHIM_END not in src:
        head += log_shim(mod_key, cfg)
    if "gate" in needs and "mwluafix_gate = function" not in src:
        head += GATE_HELPER
    out = out[:ip] + head + out[m.end() if m else ip:]
    return out, sorted(set(rules))


# ---------------------------------------------------------------------------------------------- files and mods
def mods_root_of(path):
    """(the ...\\MWSE\\mods folder, the path under it with /) for a file under one, else (None, None)."""
    parts = re.split(r"[\\/]+", os.path.abspath(path))
    low = [p.lower() for p in parts]
    for i in range(len(parts) - 2, 0, -1):
        if low[i] == "mods" and low[i - 1] == "mwse":
            return os.sep.join(parts[:i + 1]) or os.sep, "/".join(parts[i + 1:])
    return None, None


def mod_key_of(mods_root, rel):
    """The MWSE mod a file belongs to, named as MWSE names it ("abot/smartCompanions"): the nearest folder
    above it with a main.lua (MWSE runs each main.lua as a mod), else its first folder."""
    parts = rel.split("/")[:-1]
    for k in range(len(parts), 0, -1):
        if os.path.isfile(os.path.join(mods_root, *parts[:k], "main.lua")):
            return "/".join(parts[:k])
    return parts[0] if parts else os.path.splitext(rel)[0]


SKIP_DIRS = {"off", "extras", "docs", "bugreports", "openmw", "screenshots"}


def lua_files(root):
    if os.path.isfile(root):
        yield root
        return
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.lower().endswith((".disabled", ".mohidden"))
                         and d.lower() not in SKIP_DIRS)
        for fn in sorted(files):
            if fn.lower().endswith(".lua"):
                yield os.path.join(base, fn)


def excluded(path, include_own=False, cfg=None):
    """Why a file is never touched (None: it may be)."""
    mroot, rel = mods_root_of(path)
    if mroot is None:
        return ("MWSE's own code (not under MWSE\\mods)" if "/mwse/" in path.replace("\\", "/").lower()
                else "not under an MWSE\\mods folder")
    if os.path.basename(path).lower() == "initialize.lua":
        return "MWSE's own code"
    first = rel.split("/")[0].lower()
    own = set(OWN_MODS) | {str(m).lower() for m in ((cfg or {}).get("exemptMods") or [])}
    if not include_own and first in own:
        return "your own mod (--include-own checks it)"
    return None


def sha(b):
    return hashlib.sha1(b).hexdigest()


def write_in_place(path, data):
    """Rewrite the file through the same handle (r+b, then truncate): the file keeps its identity, so Vortex's
    hard link between staging and Data Files keeps sharing it."""
    with open(path, "r+b") as f:
        f.seek(0)
        f.write(data)
        f.truncate()
        f.flush()
        os.fsync(f.fileno())
        f.seek(0)
        if f.read() != data:                       # read back: a short write is an error, never a silent change
            raise OSError(f"{path}: the file reads back different after writing")


# ---------------------------------------------------------------------------------------------- checking mods
class Report:
    def __init__(self):
        self.files = {}        # path -> {"rel", "mod", "findings", "error", "patch", "logs", "requires", "sha"}
        self.skipped = []      # (path, why)
        self.mods = {}         # mod key -> {"shim": bool, "why": str}


def _cache(game_dir):
    try:
        import mwdialog_assets as ah
        return ah, ah.shared_cache(game_dir)
    except Exception:
        return None, None


def _analyse(src, key, rel, cfg):
    a = FileAnalysis(src, key, rel, cfg)
    a.run()
    return a


def log_exempt(cfg, key):
    low = key.lower()
    for m in list(cfg["log"].get("exemptMods") or []) + list(cfg.get("logExemptMods") or []):
        m = str(m).lower().replace("\\", "/")
        if m == low or m == low.split("/")[0]:
            return True
    return False


def check_paths(paths, cfg, include_own=False, checker=None, level="high", data_dir=None, use_cache=True,
                log_shim_always=False, game_dir=HERE, log_scope=None):
    """Check every Lua file under paths; patches are prepared (and verified) but nothing is written."""
    rep = Report()
    ah, cache = _cache(game_dir) if use_cache else (None, None)
    ch = cfg_hash(cfg)
    by_mod = {}
    for root in paths:
        for p in lua_files(root):
            why = excluded(p, include_own, cfg)
            if why:
                rep.skipped.append((p, why))
                continue
            mroot, rel = mods_root_of(p)
            by_mod.setdefault((mroot, mod_key_of(mroot, rel)), []).append((p, rel))
    fix_conf = ("high",) if level == "high" else ("high", "medium")
    for (mroot, key), files in sorted(by_mod.items()):
        analyses = {}
        for p, rel in files:
            ent = {"rel": rel, "mod": key, "findings": [], "error": None, "patch": None, "logs": 0, "requires": []}
            rep.files[p] = ent
            try:
                st = os.stat(p)
            except OSError as e:
                ent["error"] = str(e)
                continue
            ckey = "luafix1:" + os.path.normcase(os.path.abspath(p))
            if cache is not None:
                hit = cache.get(ckey, ah.stamp_of(st))
                if hit is not None and hit.get("cfg") == ch:
                    ent.update(error=hit.get("err"), logs=hit.get("logs", 0), requires=hit.get("req", []),
                               sha=hit.get("sha"), cached=True, old_shim=hit.get("v1", False),
                               findings=[Finding(f, edits=[], needs=set(f.get("needs", []))) for f in hit["f"]])
                    continue
            with open(p, "rb") as f:
                b = f.read()
            ent["sha"] = sha(b)
            try:
                a = analyses[p] = _analyse(b.decode("latin-1"), key, rel, cfg)
                ent.update(findings=a.findings, logs=a.log_calls(), requires=a.requires(), old_shim=a.old_shim)
            except L.LuaSyntaxError as e:
                ent["error"] = f"can't be parsed ({e}); left alone"
            except RecursionError:
                ent["error"] = "too deeply nested to analyse; left alone"
            if cache is not None:
                cache.put(ckey, ah.stamp_of(st), {
                    "cfg": ch, "err": ent["error"], "logs": ent["logs"], "req": ent["requires"], "sha": ent["sha"],
                    "v1": ent.get("old_shim", False),
                    "f": [dict({k: v for k, v in f.items() if k not in ("edits", "needs")}, needs=sorted(f["needs"]),
                               fixable=bool(f["edits"])) for f in ent["findings"]]})
        _require_cycles(rep, files)
        # F1: does the mod need the log shim? (decided per mod, like mwguard's per-mod allowance)
        scope = log_scope or cfg["log"].get("scope") or "flagged"
        f1 = [f for p, _r in files for f in rep.files[p]["findings"] if f["rule"] == "F1"]
        triggers = [f for f in f1 if f["conf"] == "trigger"]
        logs = any(rep.files[p]["logs"] for p, _r in files if not rep.files[p]["error"])
        shim, why = False, "the log shim is off (--lua-log off / log.scope)"
        if scope != "off" and (triggers or (scope == "all" and logs)):
            covered, why = mwguard_log_cover(data_dir, cfg, key)
            if log_exempt(cfg, key):
                why = "the mod is in the log shim's exemptMods"
            else:
                shim = not covered or log_shim_always or bool(cfg.get("logShimWhenMwguard"))
                if not triggers:
                    why = "--lua-log all" + (f"; {why}" if not shim else "")
            rep.mods[key] = {"shim": shim, "why": why}
        lc = cfg["log"]
        for f in triggers:
            if shim:
                f["conf"] = "high"
                f["fix"] = (f"log shim: past its first {lc['budgetInit']}+{lc['budget']} lines, MWSE\\logs\\"
                            f"{log_name(key)}.log (at most {lc['perSecond']}/s, repeats collapsed, rotated at "
                            f"{lc['maxMB']} MB); errors still reach MWSE.log ({why})")
            else:
                f["conf"], f["fix"] = "covered", f"nothing to patch: {why}"
        for p, _r in files:                        # logger wraps only travel with the shim
            ent = rep.files[p]
            if shim:
                for f in ent["findings"]:
                    if f["rule"] == "F1" and f["what"] == "logger created here":
                        f["conf"] = "high"
            else:
                ent["findings"] = [f for f in ent["findings"] if not (f["rule"] == "F1" and f["what"] ==
                                                                     "logger created here")]
        for p, rel in files:
            ent = rep.files[p]
            if ent["error"]:
                continue
            want_shim = shim and ent["logs"] > 0 or bool(analyses.get(p) and analyses[p].old_shim) or \
                bool(ent.get("old_shim"))
            fixable = any((f["edits"] or f.get("fixable")) and f["conf"] in fix_conf for f in ent["findings"])
            if not (fixable or want_shim):
                continue
            a = analyses.get(p)
            if a is None:                              # from the cache: read it again to build the patch
                with open(p, "rb") as fh:
                    b = fh.read()
                ent["sha"] = sha(b)
                try:
                    a = _analyse(b.decode("latin-1"), key, rel, cfg)
                except (L.LuaSyntaxError, RecursionError) as e:
                    ent["error"] = f"can't be parsed ({e}); left alone"
                    continue
                old = {(f["rule"], f["line"], f["what"]): f["conf"] for f in ent["findings"]}
                for f in a.findings:
                    if f["rule"] == "F1":
                        f["conf"] = old.get((f["rule"], f["line"], f["what"]), f["conf"])
                ent["findings"] = a.findings + [f for f in ent["findings"] if f["rule"] == "H5"]
            new, rules = build_patch(a.src, a.findings, key, cfg, level, want_shim)
            if new is not None:
                ent["patch"] = verify_patch(a.src, new, rules, checker, key, rel, cfg, level)
    return rep


def verify_patch(old, new, rules, checker, key, rel, cfg, level):
    """{"text", "rules", "ok", "why"}: the patched text parses, a second pass changes nothing more, and the
    syntax checker compiles it (the original first: one that doesn't compile is left alone)."""
    res = {"text": new, "rules": rules, "ok": False, "why": ""}
    if checker is not None:
        ok, msg = checker.check(old)
        if not ok:
            res["why"] = f"the original doesn't compile ({msg[:200]}); left alone"
            res["orig_bad"] = True
            return res
    try:
        b = _analyse(new, key, rel, cfg)
    except (L.LuaSyntaxError, RecursionError) as e:
        res["why"] = f"the patched text doesn't parse ({e}) - patch rejected"
        return res
    again, _r = build_patch(new, [f for f in b.findings if f["rule"] != "F1"], key, cfg, level, False)
    if again is not None:
        res["why"] = "a second pass would change it again - patch rejected"
        return res
    if checker is not None:
        ok, msg = checker.check(new)
        if not ok:
            res["why"] = f"{checker.name} rejects the patched text ({msg[:200]}) - patch rejected"
            return res
    res["ok"] = True
    return res


def _require_cycles(rep, files):
    mod_of = {}
    for p, rel in files:
        name = rel[:-4].replace("/", ".")
        mod_of[name.lower()] = p
        if name.lower().endswith(".init"):
            mod_of[name[:-5].lower()] = p
    graph = {p: [mod_of[r.lower()] for r in rep.files[p].get("requires") or [] if r.lower() in mod_of]
             for p, _r in files}
    color, stack, found = {}, [], set()

    def dfs(u):
        color[u] = 1
        stack.append(u)
        for v in graph.get(u, ()):
            if color.get(v) == 1:
                cyc = stack[stack.index(v):] + [v]
                sig = frozenset(cyc)
                if sig not in found:
                    found.add(sig)
                    rep.files[u]["findings"].append(Finding(
                        rule="H5", line=1, what="require cycle at load: " + " -> ".join(rep.files[x]["rel"] for x in cyc),
                        fix="require one of them inside a function, or move the shared part to a third module",
                        conf="report", edits=[], needs=set()))
            elif color.get(v) is None:
                dfs(v)
        stack.pop()
        color[u] = 2

    for p in graph:
        if color.get(p) is None:
            dfs(p)


# ---------------------------------------------------------------------------------------------- apply / undo
def run_backup_dir(backup_root=BACKUP_ROOT):
    return os.path.join(backup_root, time.strftime("%Y%m%d-%H%M%S"))


def apply_report(rep, journal=JOURNAL, backup_root=BACKUP_ROOT, head_extra=None, log=print, bdir=None, done=None):
    """Write every verified patch in place, after copying the file to backup_root\\<run>\\ (or bdir). Every write
    is journaled first; done (a list) gets each path as it is written, so an interrupted run knows what is left.
    Returns (written, refused [(path, why)])."""
    todo = [(p, e) for p, e in sorted(rep.files.items()) if e.get("patch")]
    refused = [(p, e["patch"]["why"]) for p, e in todo if not e["patch"]["ok"]]
    todo = [(p, e) for p, e in todo if e["patch"]["ok"]]
    if not todo:
        return 0, refused
    bdir = bdir or run_backup_dir(backup_root)
    written = 0
    os.makedirs(os.path.dirname(os.path.abspath(journal)), exist_ok=True)
    with open(journal, "a", encoding="utf-8") as j:
        head = {"run": time.strftime("%Y-%m-%d %H:%M:%S"), "what": "luafix"}
        head.update(head_extra or {})
        j.write(json.dumps(head) + "\n")
        for p, e in todo:
            try:
                with open(p, "rb") as f:
                    b = f.read()
                if e.get("sha") and sha(b) != e["sha"]:
                    refused.append((p, "changed since it was checked"))
                    continue
                drive, tail = os.path.splitdrive(os.path.abspath(p))
                bpath = os.path.join(bdir, drive.rstrip(":\\/") or "root", tail.lstrip("\\/"))
                os.makedirs(os.path.dirname(bpath), exist_ok=True)
                with open(bpath, "wb") as f:
                    f.write(b)
                new = e["patch"]["text"].encode("latin-1")
                j.write(json.dumps({"luafix": p, "backup": bpath, "before": sha(b), "after": sha(new),
                                    "rules": e["patch"]["rules"]}) + "\n")
                j.flush()
                write_in_place(p, new)
                written += 1
                if done is not None:
                    done.append(p)
                log(f"    patched {e['mod']}: {e['rel']} ({', '.join(e['patch']['rules'])})")
            except OSError as ex:
                refused.append((p, str(ex)))
    return written, refused


def restore_op(op, force=False):
    """Put one journaled file back, in place. (True, msg) when it is as it was, else (False, why)."""
    p = op["luafix"]
    try:
        with open(p, "rb") as f:
            cur = f.read()
    except OSError as e:
        return False, f"{p}: {e}"
    if sha(cur) == op["before"]:
        return True, f"{p}: already as it was"
    if sha(cur) != op["after"] and not force:
        return False, f"{p}: changed since it was patched (not put back; --force overwrites it)"
    try:
        with open(op["backup"], "rb") as f:
            old = f.read()
    except OSError as e:
        return False, f"{p}: the backup is missing ({e})"
    if sha(old) != op["before"]:
        return False, f"{p}: the backup doesn't match the journal"
    write_in_place(p, old)
    return True, f"{p}: put back"


def _read_runs(journal):
    runs, cur = [], None
    with open(journal, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if "run" in rec:
                cur = {"head": rec, "ops": []}
                runs.append(cur)
            elif cur is not None:
                cur["ops"].append(rec)
    return runs


def _write_runs(journal, runs):
    tmp = journal + ".tmp"
    with open(tmp, "w", encoding="utf-8") as j:
        for r in runs:
            j.write(json.dumps(r["head"]) + "\n")
            for op in r["ops"]:
                j.write(json.dumps(op) + "\n")
    os.replace(tmp, journal)


def undo(journal=JOURNAL, force=False, log=print):
    if not os.path.exists(journal):
        log("Nothing to undo (no journal).")
        return 1
    runs = _read_runs(journal)
    if not runs:
        log("Nothing to undo.")
        return 1
    last = runs.pop()
    left, n = [], 0
    for op in reversed(last["ops"]):
        ok, msg = restore_op(op, force)
        if ok:
            n += 1
        else:
            left.append(op)
            log("  " + msg)
    if left:
        runs.append({"head": last["head"], "ops": list(reversed(left))})
    _write_runs(journal, runs)
    log(f"Put back {n} Lua file(s) patched by the run of {last['head']['run']}.")
    return 1 if left else 0


# ---------------------------------------------------------------------------------------------- report
CONF_ORDER = {"high": 0, "report-high": 1, "medium": 2, "report": 3, "trigger": 4, "covered": 5, "info": 6}


def format_report(rep, show_info=False, indent="  "):
    lines, counts = [], {}
    for p, e in sorted(rep.files.items(), key=lambda x: (x[1]["mod"].lower(), x[1]["rel"].lower())):
        for f in e["findings"]:
            counts[(f["rule"], f["conf"])] = counts.get((f["rule"], f["conf"]), 0) + 1
        fs = [f for f in e["findings"] if show_info or f["conf"] not in ("info",)]
        if not fs and not e["error"] and not e.get("patch"):
            continue
        lines.append(f"{indent}lua {e['rel']}")
        if e["error"]:
            lines.append(f"{indent}    ! {e['error']}")
        for f in sorted(fs, key=lambda f: (CONF_ORDER.get(f["conf"], 9), f["line"])):
            lines.append(f"{indent}    {f['rule']} {f['conf']:<11} line {f['line']}: {f['what']}"
                         + (f"  -> {f['fix']}" if f["fix"] else ""))
        pt = e.get("patch")
        if pt:
            lines.append(f"{indent}    => " + (f"patch ready ({', '.join(pt['rules'])})" if pt["ok"]
                                               else f"NOT patched: {pt['why']}"))
    return lines, counts


def pending_lines(rep, done=(), indent="  "):
    """The plan lines of the patches not written yet (verified ones only: a refused patch is not an action)."""
    done = set(done)
    left = Report()
    for p, e in rep.files.items():
        if e.get("patch") and e["patch"]["ok"] and p not in done:
            left.files[p] = e
    lines, _c = format_report(left, False, indent)
    return lines


def summary_lines(counts, indent="  "):
    by_rule = {}
    for (r, c), n in counts.items():
        by_rule.setdefault(r, {})[c] = n
    return [f"{indent}{r}: " + ", ".join(f"{n} {c}" for c, n in sorted(by_rule[r].items(),
                                                                       key=lambda x: CONF_ORDER.get(x[0], 9)))
            for r in sorted(by_rule)]


# ---------------------------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="Check MWSE Lua mods for bad habits and patch the safe ones.")
    ap.add_argument("paths", nargs="*", help="folders or files (default: Data Files\\MWSE\\mods next to this script)")
    ap.add_argument("--apply", action="store_true", help="patch (without it, only the plan is shown)")
    ap.add_argument("--yes", action="store_true", help="with --apply: don't ask first")
    ap.add_argument("--undo", action="store_true", help="put back the files the last --apply patched")
    ap.add_argument("--force", action="store_true", help="with --undo: also put back files changed since")
    ap.add_argument("--level", choices=("high", "medium"), default="high",
                    help="what gets patched: high (default) or also the medium-confidence findings")
    ap.add_argument("--include-own", action="store_true", help="also check your own mods (mwguard, mwcollide...)")
    ap.add_argument("--luajit", help="the LuaJIT (or luac) to check syntax with")
    ap.add_argument("--no-syntax-check", action="store_true", help="patch even with no LuaJIT/luac (parser only)")
    ap.add_argument("--log-shim-always", action="store_true", help="add the log shim even where mwguard covers it")
    ap.add_argument("--lua-log", choices=("flagged", "all", "off"),
                    help="which mods get the log shim: flagged (default: mods with log-spam signs), all (every mod "
                         "that logs), off")
    ap.add_argument("--no-cache", action="store_true", help="read every file again")
    ap.add_argument("--all", action="store_true", help="also list what was left alone on purpose")
    ap.add_argument("--json", help="also write the findings as JSON to this file")
    ap.add_argument("--diff", action="store_true", help="show each patch as a diff")
    args = ap.parse_args(argv)
    if args.undo:
        return undo(force=args.force)             # works from the journal; the plan file plays no part
    if args.apply and PF.state(PLAN_FILE) == "applied":
        print(PF.refuse_message(PLAN_FILE, "mwdialog_luafix.py"))
        return 0
    reviewed = PF.read(PLAN_FILE) if args.apply else None
    data_dir = os.path.join(HERE, "Data Files")
    paths = args.paths or [os.path.join(data_dir, "MWSE", "mods")]
    cfg = load_config(HERE, data_dir)
    checker = None if args.no_syntax_check else find_checker(args.luajit, HERE)
    print(f"mwdialog_luafix {VERSION}: syntax check {checker.name if checker else 'NONE'}; priority limit "
          f"{cfg['priorityLimit']} (-> {compress_priority(cfg['priorityLimit'], cfg)}..."
          f"{compress_priority(math.inf, cfg)}), interval "
          f"{cfg['minInterval']} s" + (f"; settings from {', '.join(cfg['_sources'])}" if cfg["_sources"] else ""))
    if args.apply and checker is None and not args.no_syntax_check:
        print("No LuaJIT/luac found (--luajit PATH): not patching without a syntax check (--no-syntax-check "
              "relies on the parser alone).", file=sys.stderr)
        return 2
    rep = check_paths(paths, cfg, args.include_own, checker, args.level, data_dir, not args.no_cache,
                      args.log_shim_always, log_scope=args.lua_log)
    lines, counts = format_report(rep, args.all)
    n_ok = sum(1 for e in rep.files.values() if e.get("patch") and e["patch"]["ok"])
    head = [f"mwdialog_luafix plan, {time.strftime('%Y-%m-%d %H:%M')}: {len(rep.files)} Lua file(s) checked, "
            f"{n_ok} to patch, {len(rep.skipped)} left alone (MWSE's own code / your mods)"] + summary_lines(counts)
    PF.write_atomic(PLAN_FILE, "\n".join(head + lines) + "\n")
    print("\n".join(head))
    print("\n".join(lines[:300]))
    if len(lines) > 300:
        print(f"... ({len(lines) - 300} more lines in {PLAN_FILE})")
    if args.diff:
        for line in diff_lines(rep):
            print(line)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report_json(rep), f, indent=1)
    if not args.apply:
        print(f"\n{n_ok} file(s) would be patched. Nothing changed (--apply patches them).")
        return 0
    if reviewed is not None and not PF.same_actions(reviewed, PF.read(PLAN_FILE)):
        print("NOTE: --apply recomputed the plan and it differs from the plan file you last reviewed (both are "
              "kept in the run's backup folder).")
    bdir = run_backup_dir(BACKUP_ROOT)
    if not n_ok:
        print("Nothing to patch.")
        PF.finish(PLAN_FILE, "mwdialog_luafix.py", [], bdir, reviewed, note="there was nothing to patch")
        return 0
    if not args.yes and input(f"\nPatch {n_ok} file(s)? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing changed.")
        return 0
    done, refused, finished = [], [], False
    enacted = PF.read(PLAN_FILE)
    try:
        w, refused = apply_report(rep, journal=JOURNAL, backup_root=BACKUP_ROOT, bdir=bdir, done=done,
                                  head_extra={"plan_copy": os.path.join(bdir, "plan_enacted.txt")})
        finished = True
    finally:                                      # also on Ctrl+C: what was written leaves the plan
        left = pending_lines(rep, done)
        PF.finish(PLAN_FILE, "mwdialog_luafix.py", left, bdir, reviewed, enacted,
                  note="" if finished else "the run was interrupted")
    for p, why in refused:
        print(f"  not patched: {p}: {why}")
    print(f"Patched {w} file(s). Journal: {JOURNAL} (--undo puts them back).")
    return 0 if not left else 1


def diff_lines(rep):
    import difflib
    out = []
    for p, e in sorted(rep.files.items()):
        pt = e.get("patch")
        if not pt or not pt["ok"]:
            continue
        with open(p, "rb") as f:
            old = f.read().decode("latin-1")
        out += list(difflib.unified_diff(old.splitlines(), pt["text"].splitlines(), e["rel"], e["rel"] + " (patched)",
                                         n=0, lineterm=""))
    return out


def report_json(rep):
    return {p: {"rel": e["rel"], "mod": e["mod"], "error": e["error"],
                "findings": [{k: (sorted(v) if isinstance(v, set) else v) for k, v in x.items() if k != "edits"}
                             for x in e["findings"]],
                "patch": ({k: v for k, v in e["patch"].items() if k != "text"} if e.get("patch") else None)}
            for p, e in rep.files.items()}


if __name__ == "__main__":
    sys.exit(main())
