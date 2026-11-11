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
  A1 ref.data.x read without a guard -> (ref.data and ref.data.x)                                      fix
  A2 a keybind's .keyCode read with no check                                                          report
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

sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))

HERE = os.path.dirname(os.path.abspath(__file__))
JOURNAL = os.path.join(HERE, "mwdialog_luafix_journal.jsonl")
BACKUP_ROOT = os.path.join(HERE, "mwdialog_backup", "luafix")
CONFIG_FILE = os.path.join(HERE, "mwdialog_luafix.json")
PLAN_FILE = os.path.join(HERE, "mwdialog_luafix_plan.txt")
VERSION = 1
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
    "logBudgetInit": 40,             # mwguard: lines a mod may write to MWSE.log while the game starts
    "logBudget": 10,                 # ... and after that
    "logKeepPatterns": ["error", "traceback", "exception", "fail", "warn", "stack", "attempt to", "assert",
                        "invalid", "%.lua:%d+:", "^lua:"],
    "logSpamGuard": True,
    "enabled": True,
    "logShimWhenMwguard": False,     # also patch log spam when mwguard's runtime guard covers the mod
}

PER_FRAME = {"simulate", "simulated", "enterFrame"}
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
def load_config(game_dir=HERE, data_dir=None):
    """DEFAULTS, then MWSE\\config\\mwguard.json (mwguard's own file: one place for the thresholds both use),
    its "luafix" section, then mwdialog_luafix.json next to this script."""
    cfg = dict(DEFAULTS)
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
            if section is not None or k in DEFAULTS or k == "logExemptMods":   # mwguard.json: shared keys only
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
        return False, ("the installed mwguard leaves MWSE.log alone (the passive profiler of 2026-11-11 has no "
                       "log-spam redirect)")
    if not cfg.get("enabled", True) or not cfg.get("logSpamGuard", True):
        return False, "mwguard.json turns mwguard or its log-spam guard off"
    low = mod_key.lower()
    for m in cfg.get("logExemptMods") or []:
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
                  self.r_keycode, self.r_destroy, self.r_console, self.r_info_filter, self.r_reregister,
                  self.r_reload_timers, self.r_globals, self.r_toplevel, self.r_loops, self.r_logger_level,
                  self.r_log_triggers):
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
            if not self._rvalue_slot(n):
                continue
            f = L.enclosing_function(n)
            if self._data_checked(f.body if f is not None else self.tree.body, bt):
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
            if n.kind != "Index" or n.field != "keyCode":
                continue
            bt = L.dotted(n.obj)
            if not bt or not re.search(r"(?i)config|cfg|setting|key|bind", bt):
                continue
            if n.parent is not None and n.parent.kind == "Assign" and any(t is n for t in n.parent.targets):
                continue
            f = L.enclosing_function(n)
            scope = f.body if f is not None else self.tree.body
            checked = any(m.kind in ("Index", "Name") and L.dotted(m) == bt and m.parent is not None and (
                m.parent.kind == "Binop" and m.parent.op in ("and", "or") and m.parent.left is m or
                m.parent.kind == "Unop" and m.parent.op == "not" or m.parent.kind == "If") for m in L.walk(scope))
            if not checked:
                self.add("A2", n, f"{bt}.keyCode read with no check (an unbound key is nil)",
                         f"check {bt} first (the guide's isUnbound pattern)")

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
        return n

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


def log_shim(mod_key, cfg):
    """One line that rebinds print and mwse.log for this file only (locals; nothing global changes). Like
    mwguard's runtime guard: the mod's first logBudgetInit lines (+ logBudget once the game has started) and
    anything that looks like an error or warning reach MWSE.log unchanged; the rest go to
    Data Files\\MWSE\\logs\\<mod>.log. The count is shared by all the mod's files (kept in package.loaded)."""
    safe = log_name(mod_key)
    path = "Data Files\\MWSE\\logs\\" + safe + ".log"
    pats = ", ".join(lua_str(p) for p in cfg["logKeepPatterns"])
    key = lua_str("mwluafix_logshim:" + safe)
    note = lua_str(f"[{MARK}] {safe}: its further MWSE.log output goes to {path} (errors still show here)")
    return (
        "local print, mwse = (function(_p, _m) local fmt, find, lower, sub = string.format, string.find, "
        "string.lower, string.sub "
        f"local st = package.loaded[{key}] if type(st) ~= \"table\" then st = {{ n = 0, f = false }} "
        f"package.loaded[{key}] = st end local keep = {{ {pats} }} "
        "local function pass(t) local l = lower(sub(t, 1, 4096)) for i = 1, #keep do "
        "local ok, h = pcall(find, l, keep[i]) if ok and h then return true end end "
        "local started = tes3 and tes3.isInitialized and tes3.isInitialized() "
        f"if st.n < {cfg['logBudgetInit']} + (started and {cfg['logBudget']} or 0) then st.n = st.n + 1 return true end "
        "if st.f == false then pcall(function() lfs.mkdir(\"Data Files\\\\MWSE\\\\logs\") end) "
        f"st.f = io.open({lua_str(path)}, \"a\") or nil if st.f then _m.log({note}) end end "
        "if not st.f then return true end st.f:write(os.date(\"[%Y-%m-%d %H:%M:%S] \"), t, \"\\n\") st.f:flush() "
        "return false end "
        "return function(...) local parts = {} for i = 1, select(\"#\", ...) do parts[i] = tostring((select(i, ...))) "
        "end if pass(table.concat(parts, \"\\t\")) then return _p(...) end end, "
        "setmetatable({ log = function(f, ...) local ok, t = pcall(fmt, tostring(f), ...) "
        "if not ok then t = tostring(f) end if pass(t) then return _m.log(f, ...) end end }, "
        "{ __index = _m, __newindex = _m }) end)(print, mwse) ")


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
            edits += [(s, e, t) for s, e, t in f["edits"]]
            rules.append(f["rule"])
            needs |= set(f["needs"])
    if want_shim and "mwluafix_logshim:" not in src:
        needs.add("shim")
        rules.append("F1")
    if not edits and "shim" not in needs:
        return None, []
    edits.sort(key=lambda x: (x[0], x[1]))
    kept, last_end = [], -1
    for s, e, t in edits:                          # overlapping edits: the first wins (the next run gets the rest)
        if s < last_end or (s == e and s < last_end):
            continue
        kept.append((s, e, t))
        last_end = max(last_end, e)
    out = src
    for s, e, t in reversed(kept):
        out = out[:s] + t + out[e:]
    ip = insert_point(out)
    m = MARK_RE.match(out, ip)
    allr = sorted(set(m.group(2).split() if m else []) | set(rules))
    head = f"--[[{MARK} {VERSION}: {' '.join(allr)}]] "
    if "shim" in needs and "mwluafix_logshim:" not in src:
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


def check_paths(paths, cfg, include_own=False, checker=None, level="high", data_dir=None, use_cache=True,
                log_shim_always=False, game_dir=HERE):
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
                               sha=hit.get("sha"), cached=True,
                               findings=[Finding(f, edits=[], needs=set(f.get("needs", []))) for f in hit["f"]])
                    continue
            with open(p, "rb") as f:
                b = f.read()
            ent["sha"] = sha(b)
            try:
                a = analyses[p] = _analyse(b.decode("latin-1"), key, rel, cfg)
                ent.update(findings=a.findings, logs=a.log_calls(), requires=a.requires())
            except L.LuaSyntaxError as e:
                ent["error"] = f"can't be parsed ({e}); left alone"
            except RecursionError:
                ent["error"] = "too deeply nested to analyse; left alone"
            if cache is not None:
                cache.put(ckey, ah.stamp_of(st), {
                    "cfg": ch, "err": ent["error"], "logs": ent["logs"], "req": ent["requires"], "sha": ent["sha"],
                    "f": [dict({k: v for k, v in f.items() if k not in ("edits", "needs")}, needs=sorted(f["needs"]),
                               fixable=bool(f["edits"])) for f in ent["findings"]]})
        _require_cycles(rep, files)
        # F1: does the mod need the log shim? (decided per mod, like mwguard's per-mod allowance)
        triggers = [f for p, _r in files for f in rep.files[p]["findings"] if f["rule"] == "F1"]
        shim = False
        if triggers:
            covered, why = mwguard_log_cover(data_dir, cfg, key)
            shim = not covered or log_shim_always or bool(cfg.get("logShimWhenMwguard"))
            rep.mods[key] = {"shim": shim, "why": why}
            for f in triggers:
                if shim:
                    f["conf"] = "high"
                    f["fix"] = (f"log shim: past its first {cfg['logBudgetInit']} lines, MWSE\\logs\\{log_name(key)}"
                                f".log; errors still reach MWSE.log ({why})")
                else:
                    f["conf"], f["fix"] = "covered", f"nothing to patch: {why}"
        for p, rel in files:
            ent = rep.files[p]
            if ent["error"]:
                continue
            want_shim = shim and ent["logs"] > 0
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
def apply_report(rep, journal=JOURNAL, backup_root=BACKUP_ROOT, head_extra=None, log=print):
    """Write every verified patch in place, after copying the file to backup_root\\<run>\\. Every write is
    journaled first. Returns (written, refused [(path, why)])."""
    todo = [(p, e) for p, e in sorted(rep.files.items()) if e.get("patch")]
    refused = [(p, e["patch"]["why"]) for p, e in todo if not e["patch"]["ok"]]
    todo = [(p, e) for p, e in todo if e["patch"]["ok"]]
    if not todo:
        return 0, refused
    bdir = os.path.join(backup_root, time.strftime("%Y%m%d-%H%M%S"))
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
    ap.add_argument("--no-cache", action="store_true", help="read every file again")
    ap.add_argument("--all", action="store_true", help="also list what was left alone on purpose")
    ap.add_argument("--json", help="also write the findings as JSON to this file")
    ap.add_argument("--diff", action="store_true", help="show each patch as a diff")
    args = ap.parse_args(argv)
    if args.undo:
        return undo(force=args.force)
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
                      args.log_shim_always)
    lines, counts = format_report(rep, args.all)
    n_ok = sum(1 for e in rep.files.values() if e.get("patch") and e["patch"]["ok"])
    head = [f"mwdialog_luafix plan, {time.strftime('%Y-%m-%d %H:%M')}: {len(rep.files)} Lua file(s) checked, "
            f"{n_ok} to patch, {len(rep.skipped)} left alone (MWSE's own code / your mods)"] + summary_lines(counts)
    with open(PLAN_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(head + lines) + "\n")
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
    if not n_ok:
        print("Nothing to patch.")
        return 0
    if not args.yes and input(f"\nPatch {n_ok} file(s)? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing changed.")
        return 0
    w, refused = apply_report(rep)
    for p, why in refused:
        print(f"  not patched: {p}: {why}")
    print(f"Patched {w} file(s). Journal: {JOURNAL} (--undo puts them back).")
    return 0


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
