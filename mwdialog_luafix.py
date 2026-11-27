#!/usr/bin/env python3
"""mwdialog_luafix.py - find and patch bad habits in MWSE Lua mods that pass a syntax check.

Each .lua file under an MWSE\\mods folder is parsed (mwdialog_lua.py: a real Lua tokenizer and parser, not
regexes) and checked against the rules of the MWSE Lua guide (docs/dev/LUA-DEBUGGING.md) plus a few the
guide implies. Every finding has a confidence: "high" ones are patched by --apply, "medium" ones only with
--level medium, the rest are only reported. A patch is a few token-span edits; nothing else in the file
changes (encoding, line endings and every line number stay the same: helpers go at the start of line 1).

Rules (thresholds come from MWSE\\config\\mwguard.json when it exists - the same file mwguard reads at runtime):
  G1 absurd event priority (|p| >= priorityLimit, 10000) -> compressed to 1000..1999 (order kept)    fix
  G2 a per-frame handler (simulate/simulated/enterFrame) that only polls state -> runs every 0.35 s  fix
  G2S a per-frame handler G2 would leave at medium (unseen calls, state writes) that scans the world
     every frame (tes3.rayTest, iterateReferences, tes3.getReference...) and shows nothing
     frame-critical -> runs every 0.35 s (its own id: skipRules turns it off)                         fix
  G8 the same literal tes3.messageBox in a combat-event handler (damage, attack, spellTick...) ->
     shown at most once per messageInterval (10 s); in a per-frame handler                           report
  U1 a per-frame handler writing a createLabel/createBlock element's .text with the same kind of
     value every frame -> written only when it differs                                                fix
  G3 a repeating timer faster than 0.35 s whose callback only polls -> 0.35 s                          fix
  G4 a one-shot handler (done flag) that never unregisters -> unregisters once the flag is set         fix
  G5 per-frame costs: uncached lookups, config/file I/O, allocations, message boxes every frame      report
  A1 ref.data.x used without a guard -> (ref.data and ref.data.x) / if ref.data then ... end           fix
     (a name REF_NAME doesn't know, read with reference-only fields such as .baseObject or .mobile in the
     same function: medium; a write there is guarded with if x.supportsLuaData then ... end)
  A2 a keybind's .keyCode (.mouseButton ...) read with no check -> (key and key.keyCode)               fix
  A3 a tes3 lookup that can return nil (getObject, getReference, getPlayerTarget, findMenu, getCurrentWeather;
     getPlayerCell and getPlayerRef, nil only before a game is loaded, at medium...) used
     without a check -> guarded                                                                        fix
  A4 an event field that can be nil (damage e.attacker, attack e.targetMobile, cellChanged
     e.previousCell, uiObjectTooltip e.reference...) used without a check -> guarded                  fix
  A5 an NPC's .head / .hair (through .baseObject or .object) used without a check: nil for an NPC whose
     record names no such part, or one no loaded mod defines -> guarded                               fix
     Nil guards (A1-A5): inside a condition, an and-guard: (x and x.y == z); a standalone call or
     assignment: if x then ... end; a local's value: local v = (x and f(x.y)). Nothing changes while the
     value is there. Where none of these fits with certainty the finding stays a report, with the reason.
  B1 a UI element used after :destroy()                                                               report
  C1 an engine console command sent through tes3.runLegacyScript                                      report
  D1 an infoFilter handler doing costly work (e.info.text, tes3.getDialogueInfo, getReference, string work
     on the ids...) for every response before checking e.passes -> returns early unless e.passes      fix
  F1 log spam (logging every frame, in loops, in frequent events, debug flags on) -> the mod's lines
     past its allowance go to Data Files\\MWSE\\logs\\<mod>.log; errors still reach MWSE.log            fix
  F2 a logger created at DEBUG/TRACE level -> INFO                                                     fix
  F3 a value that can only be true/false (a comparison, not, a table slot the file only sets to true/false)
     concatenated into log text ('attempt to concatenate a boolean value') -> tostring(value)         fix
  H1 event.register inside a load/cellChanged/... handler: a named handler -> isRegistered guard     fix
     (MWSE refuses the duplicate but prints a warning and a traceback every time); an anonymous one
     stacks a new copy each time                                                                      report
  H2 a repeating timer started in a handler that runs again (cellChanged...), never cancelled        report
     (its handle kept in an upvalue, a global or a field: the old timer is cancelled first, medium)    fix
     (not loaded/load: MWSE cancels every timer, real ones too, just before loaded)
  G6 tes3.getReference (scans every cell) in a frequent handler or a fast repeating timer             report
  G7 tes3.rayTest every frame / in a frequent handler with no maxDistance, no root, or accurateSkinned report
  P1 ref.data written on a non-actor reference with no ref.modified = true (lost on reload)           report
  R1 a timer callback holding a reference from its event with no safe handle / :isValid() check -> a
     safe handle taken when it starts; the callback returns once that reference is gone              fix
  T1 timer.start{ callback = "name" } with no timer.register("name", ...) anywhere in the mod         report
  H3 global variables a mod creates by accident (no local)                                            report
  H4 game data used at file load, before the initialized event                                        report
     (local X = tes3.worldController.x / tes3.player.x / tes3.mobilePlayer.x at the top of main.lua,
     never assigned again: nil-safe at load and read again where used, (X or <chain>), medium)        fix
  H5 require cycles inside a mod                                                                      report
  I2 a repeating real-time timer that redraws UI keeps running through a save -> skips while saving fix
  I3 a config written inside a save handler (during the save) -> written the frame after it        fix
  H6 tes3.messageBox inside a loop                                                                    report
  H7 X.f() through local X = require(...) of the same mod, whose table never gets f                  report
  Y1 syntax LuaJIT always rejects, so the file never loads: a call's '(' on a later line than the function
     ('ambiguous syntax') -> the '(' moves up, the line break stays after it; two literals on separate
     lines in a table with no ',' -> the ','. May repair a file that doesn't compile (kept only if it
     then compiles)                                                                                    fix
  KB<n> a documented bug that requires editing its owning mod/core file -> its exact replacement     fix
     The rules run first: a Known Bugs part applies only where no rule matched (a whole-or-nothing part
     keeps its text and the overlapping rule edit gives way). A new KB entry must say in its description
     why no rule can express it: "(no rule can express this: <why>)" (tests/test_luafix_kb_policy.py).
  L1 a while loop that walks links (x = x.next) or counts down by a computed step -> capped at 10000   fix
  M1 an enterFrame handler (it also fires in menus) with no UI work -> returns in menu mode            fix
  S1 tes3.getSoundPlaying{ reference = <not the player> }: on a non-actor the engine can say "not
     playing" while a loop plays, so a restart on that answer repeats (mwsoundguard caps it)          report
  V1 number * vector, number + vector, number - vector (MWSE binds these with the vector first, so the
     number-first order errors every call) -> v * n, v + n, -v + n. Only flagged with vector evidence:
     a field or function MWSE documents as returning a vector, tes3vectorN.new, or a local set from one  fix

Never touched: MWSE's own code except exact KNOWN_BUGS fingerprints in named core and lib files, and
your own mods (the names in OWN_MODS, plus any in exemptMods) unless --include-own. Output of the OpenMW
converter (omw2mwse: a loader with its marker or manifest, its hosted scripts, the omwcompat runtime) is never
touched, --include-own or not: re-running the converter fixes it.

Edits are made in place (the file is rewritten through the same handle, so Vortex's hard links between
staging and Data Files keep sharing it). The file as it was is copied first to
<backups folder>\\luafix\\<run>\\..., every write is journaled, and --undo puts the last run back. A file is
only written when LuaJIT (or luac) compiles the patched text; an original that does not compile is left alone
unless an exact Known Bugs repair makes it compile (also when this tool's own parser rejects it). Known Bugs fingerprints are part of the analysis cache key,
so adding a repair causes existing files to be rechecked.

    python mwdialog_luafix.py                        (plan for Data Files\\MWSE\\mods; nothing is changed)
    python mwdialog_luafix.py "<staging>\\Some Mod"   (one folder)
    python mwdialog_luafix.py --apply                (patch the high-confidence findings)
    python mwdialog_luafix.py --undo                 (put back the files of the last --apply)
--apply patches only when the plan it works out lists the same actions as plans/mwdialog_luafix_plan.txt (else it
refuses, writes the new plan and keeps the old as mwdialog_luafix_plan.prev.txt; no plan: run plan mode first).
After --apply, mwdialog_luafix_plan.txt is blanked (a second --apply does nothing until plan mode runs again) or
cut down to the patches not written; a copy of it is kept in that run's <backups folder>\\luafix\\<run>\\.
vortex_tidy.py runs the same check on every staging mod (its plan shows it, --apply patches, --undo reverts;
--no-lua skips it, --lua-only does nothing else).
"""
import dataclasses
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
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_lua as L                                   # noqa: E402
import mwdialog_planfile as PF                             # noqa: E402
import mwdialog_text as MT                                 # noqa: E402
import mwdialog_paths as MP                                # noqa: E402
import mwdialog_staged as MS                               # noqa: E402
print = MT.printer()                                       # noqa: A001

sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))

HERE = __import__("mwdialog_paths").find_game_dir() or os.path.dirname(os.path.abspath(__file__))   # the game folder
JOURNAL = MP.state_path(HERE, "mwdialog_luafix_journal.jsonl")
BACKUP_ROOT = os.path.join(__import__("mwdialog_backup").backup_root(HERE), "luafix")
PLAN_FILE = MP.state_path(__import__("mwdialog_paths").PLANS_DIR, "mwdialog_luafix_plan.txt")
KNOWN_BUG_REPORT = MP.state_path(HERE, "mwdialog_luafix_known_bugs.txt")
VERSION = 5
MARK = "localpatch"            # what is written into a mod never carries this tool's name

# First-party MWSE mods, never patched unless --include-own. The live list is
# Data Files\\MWSE\\mods\\mwsuite\\ownmods.json (ships with mwsuite). That is a different thing from
# exemptMods (a user list in the settings / mwguard.json): ownMods is who we are, exemptMods is who the
# user asked us to leave alone. Both skip the same way. OWN_MODS_FALLBACK is used when the file is
# missing or unreadable, and a warning is printed.
OWN_MODS_REL = "mods/mwsuite/ownmods.json"          # under Data Files\\MWSE
OWN_MODS_FALLBACK = frozenset({
    "mwcollide", "mwcompanions", "mwconsole", "mwcriminal", "mwcustomclasspersistence",
    "mwexitguard", "mwfloatfix", "mwguard", "mwhangwatch", "mwinfoloop",
    "mwmouseguard", "mwperformers", "mwpersonaleffects", "mwplainpaperfix", "mwpluginpatches",
    "mwquicktoggle", "mwsaveguard", "mwsoundfix", "mwsoundguard", "mwstranded", "mwteleportguard",
    "mwwarnsuppression", "mwmanager", "mwmanagermenu", "mwsuite"})
OWN_MODS = OWN_MODS_FALLBACK                        # backward-compatible alias for the fallback list
_OWN_MODS_WARNED = set()

# under --include-own, first-party files (OWN_MODS and exemptMods) only get these rules applied
OWN_FIX_RULES = frozenset({"A1", "A2", "A3", "A4", "A5", "F1"})


def own_mods_path(data_dir):
    """The ownMods file under data_dir (a Data Files folder), or None. For staged files (a StagedData: before
    deploy) the first staged mod or lua tools folder that ships it; None when none does."""
    if not data_dir:
        return None
    if isinstance(data_dir, MS.StagedData):
        return data_dir.find(os.path.join("MWSE", *OWN_MODS_REL.split("/")))
    return os.path.join(data_dir, "MWSE", *OWN_MODS_REL.split("/"))


def load_own_mods(data_dir=None, log=None):
    """(frozenset of lowercase names, where they came from). Reads Data Files\\MWSE\\mods\\mwsuite\\ownmods.json
    (schema: {"version": 1, "ownMods": [...]}). Falls back to OWN_MODS_FALLBACK when the file is missing,
    unreadable, or not that schema. A warning is printed when the file should have been there (mwsuite is
    present) or exists but cannot be used; a tree with no mwsuite folder stays quiet."""
    path = own_mods_path(data_dir)
    reason, expected = "no Data Files folder was given", False
    if path:
        expected = os.path.isdir(os.path.dirname(path))
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and d.get("version") == 1 and isinstance(d.get("ownMods"), list):
                names = frozenset(str(m).lower().replace("\\", "/") for m in d["ownMods"] if str(m).strip())
                if names:
                    return names, path
                reason, expected = f"{path} has an empty ownMods list", True
            else:
                reason, expected = f"{path} is not a version-1 ownMods file", True
        except FileNotFoundError:
            reason = f"{path} is missing"
        except OSError as e:
            reason, expected = f"{path} could not be read ({e})", True
        except ValueError as e:
            reason, expected = f"{path} is not valid JSON ({e})", True
    if expected:
        key = path or reason
        if key not in _OWN_MODS_WARNED:
            _OWN_MODS_WARNED.add(key)
            (log or print)(f"warning: using the built-in first-party mod list; {reason}")
    return OWN_MODS_FALLBACK, "built-in fallback"


def ensure_own_mods(cfg, data_dir=None, log=None):
    """Put _ownMods / _ownModsSource on cfg when they are not there yet."""
    if cfg is None:
        return
    if cfg.get("_ownMods") is None:
        names, src = load_own_mods(data_dir, log)
        cfg["_ownMods"], cfg["_ownModsSource"] = names, src


def own_mod_names(cfg=None):
    """First-party names (from ownmods.json, or the built-in fallback) plus any names in cfg['exemptMods']
    (lowercase). Call ensure_own_mods first when a Data Files folder is known."""
    names = (cfg or {}).get("_ownMods")
    if names is None:
        names = OWN_MODS_FALLBACK
    return set(names) | {str(m).lower() for m in ((cfg or {}).get("exemptMods") or [])}

# defaults; mwguard.json (shared with the runtime guard) and mwdialog_luafix.json override them
DEFAULTS = {
    "priorityLimit": 10000,          # mwguard: |priority| >= this is absurd (the guide says the same)
    "priorityClampTo": 1000,         # the old mwguard's runtime clamp (priorityMode "clamp"); the passive mwguard
                                     # only reports |priority| >= priorityLimit, which keepOrder stays under
    "priorityMode": "keepOrder",     # keepOrder: absurd priorities go to just under the limit (9000..9999), so
                                     # they still sort ahead of every ordinary priority; clamp: clampTo..2*clampTo
    "minInterval": 0.35,             # the guide: at least 0.35 s between repeating calls
    "messageInterval": 10,           # G8: one literal message box in a combat-event handler at most this often
    "exemptMods": [],
    "log": {                         # the log shim (F1): mwguard.json "luafix": { "log": { ... } } overrides
        "scope": "all",              # every third-party mod that logs gets its own log
        "budgetInit": 0,             # routine lines never use MWSE.log; lifecycle/error lines below still do
        "budget": 0,
        "keepPatterns": ["error", "traceback", "exception", "fail", "warn", "stack", "attempt to", "assert",
                         "invalid", "%.lua:%d+:", "^lua:", "initializ", "register", "loaded", "ready",
                         "version", "active",
                         "] started",                # "[Mod] started"; not "Dialogue started with"
                         "%f[%w]starting%f[%W]",     # "Starting..." / "Starting translation"; not "restart"
                         "has started", "started successfully", "successfully started", "starting up",
                         ],  # errors and lifecycle lines always reach MWSE.log (Lua patterns)
        "perSecond": 25,             # the mod's own log takes at most this many lines a second (0: no cap)
        "maxMB": 2,                  # the mod's own log is rotated at this size ...
        "keepOld": 1,                # ... keeping the previous one as <mod>.old.log (0: none)
        "flushSeconds": 2,           # buffered lines reach the disk at least this often
        "lifecycleMax": 5,           # lifecycle lines (LIFECYCLE_PATTERNS) reach MWSE.log when the word is near
                                     # the start of the line, at most this many per word and mod; the next one
                                     # writes a single hand-off line naming the mod's own log
        "errorRepeat": 0,            # errors always reach MWSE.log, including repeats
        "exemptMods": sorted(OWN_MODS),    # our mods use native logging; never inject the generic shim
    },
    "logSpamGuard": True,
    "enabled": True,
    "logShimWhenMwguard": False,     # also patch log spam when mwguard's runtime guard covers the mod
    "skipKnown": [],                 # targeted patches (KB / KP / KR rule names) to report but never apply
    "skipRules": [],                 # generic rules (G2S, G8, U1...) to report but never apply
}

PER_FRAME = {"simulate", "simulated", "enterFrame"}
PLAYER_IDS = {"player", "playersavegame"}
# nil guards
KEY_FIELDS = {"keyCode", "mouseButton", "mouseWheel", "isShiftDown", "isAltDown", "isControlDown", "isSuperDown"}
NIL_LOOKUPS = {"tes3.getObject", "tes3.getReference", "tes3.getPlayerTarget", "tes3.getEquippedItem", "tes3.getCell",
               "tes3.getFaction", "tes3.getSound", "tes3.getScript", "tes3.findDialogue",
               "tes3.getRegion", "tes3.findClass", "tes3ui.findMenu",
               # nil right after a new game is started from inside a running one (KB10-KB12)
               "tes3.getCurrentWeather",
               # nil only before a game is loaded (main menu): guarded at medium (most callers run in a game)
               "tes3.getPlayerCell", "tes3.getPlayerRef"}
NIL_LOOKUPS_MEDIUM = {"tes3.getPlayerCell", "tes3.getPlayerRef"}
_DMG = {"attacker", "attackerReference", "projectile", "magicSourceInstance", "magicEffectInstance"}
_ATK = {"targetMobile", "targetReference"}
_CAST = {"target"}
# A5: an NPC's body parts that can be nil - its record names none, or one no loaded mod defines (a bodyPartAssigned
# handler reading baseObject.head.id failed for every such NPC: Tamriel Data's fixVampireHeadAssignment)
NULLABLE_OBJECT_FIELDS = {"head", "hair"}
OBJECT_HOLDERS = {"baseObject", "object"}

NULLABLE_EVENT_FIELDS = {
    "damage": _DMG, "damaged": _DMG, "damageHandToHand": _DMG, "damagedHandToHand": _DMG,
    "attack": _ATK, "attackHit": _ATK, "attackStart": _ATK, "calcHitChance": {"target", "targetMobile"},
    "cellChanged": {"previousCell"}, "activationTargetChanged": {"current", "previous"},
    "uiObjectTooltip": {"reference", "itemData"}, "itemTileUpdated": {"itemData"},
    "equip": {"itemData"}, "equipped": {"itemData"}, "unequipped": {"itemData"},
    "spellCast": _CAST, "spellCasted": _CAST, "spellCastedFailure": _CAST, "magicCasted": _CAST,
    "leveledItemPicked": {"pick", "spawner"}, "leveledCreaturePicked": {"pick", "spawner"}}
NIL_TMP = "localpatch_v"
# rules that may repair a file LuaJIT rejects (with the exact Known Bugs repairs): Y1 fixes only syntax that never compiles
SYNTAX_RULES = frozenset({"Y1"})
# F3: calls whose arguments are log text (a concatenation error there kills the handler for a log line)
LOG_FUNC_NAMES = frozenset({"log", "debuglog", "debug_log", "dlog", "logmessage", "logdebug", "logger"})
LOG_METHODS = frozenset({"trace", "debug", "info", "warn", "error"})
# A1 at medium: a name REF_NAME doesn't recognise is a reference when the same function also reads one of these on it
REF_ONLY_FIELDS = frozenset({"baseObject", "mobile", "sceneNode", "supportsLuaData", "tempData", "modified"})
# H4 fix: top-level captures of these are nil when the file loads and are read again where they are used
LOAD_NIL_ROOTS = ("tes3.worldController", "tes3.player", "tes3.mobilePlayer")
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
# G2S: a world scan that costs real time each call (G6/G7 vocabulary)
HEAVY_SCANS = {"tes3.rayTest", "tes3.getReference", "tes3.findActorsInProximity", "tes3.iterateObjects"}
HEAVY_SCAN_METHODS = {"iterateReferences", "iterateObjects"}
# G8: events fired per hit or per NPC decision, not by a player's own click (itemTileUpdated, uiObjectTooltip,
# activationTargetChanged: there a message is the answer to one action, so it is never throttled)
MESSAGE_EVENTS = {"damage", "damaged", "damageHandToHand", "damagedHandToHand", "attack", "attackHit", "attackStart",
                  "spellTick", "calcHitChance", "determineAction", "determinedAction", "combatStarted"}
# U1: elements whose .text a per-frame handler may rewrite with the value it already has
TEXT_ELEMENT_CREATORS = {"createLabel", "createBlock"}
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
# V1: names MWSE's docs (docs/source/types, apis) give a tes3vector2/3/4 return type and nothing else
VECTOR_NAMES = frozenset("""
activeVertices ambientDayColor ambientNightColor ambientSunriseColor ambientSunsetColor boundSize boundSize2D
calculateJumpVelocity cameraOffset center collisionPoint cross cullingPlanes currentFogColor currentSkyColor
direction fogDayColor fogNightColor fogSunriseColor fogSunsetColor forwardDirection get3rdPersonCameraOffset
getCameraPosition getCameraVector getClosestExteriorPosition getCursorPosition getForwardVector
getLandNormalAtPosition getLastExteriorPosition getPlayerEyePosition getPlayerEyeVector getRightVector
getUpVector globalTranslation gravity impulseVelocity initialAxis initialNormal interpolate intersection
lastPositionBeforeCombat listenerPosition normal normals objectPosAtCollision ones orientation planeEquation
point port positionDeltaMovementRoot rightDirection rotationAxis skyDayColor skyNightColor skySunriseColor
skySunsetColor startingOrientation startingPosition stormOrigin sunDayColor sunNightColor sunSunriseColor
sunSunsetColor sundiscSunsetColor sunglareFaderColor targetPosition terminalVelocity texCoords
thirdPersonOffset toEulerXYZ toEulerZYX toVector3 translation underwaterColor unitX unitY unitZ upDirection
velocity walkDestination windVelocityCurrWeather windVelocityNextWeather windowPointToRay worldBoundOrigin
worldDirection worldPointToScreenPoint worldRight worldUp xAxis yAxis zeroes""".split())
VECTOR_CTORS = {"tes3vector2.new", "tes3vector3.new", "tes3vector4.new"}
VECTOR_OF_SELF = {"normalized", "copy", "lerp"}           # a vector when what they're called on is one
POSITION_HOLDER = re.compile(r"(?i)(ref|reference|mobile|player|target|actor|npc|creature|node|scenenode|"
                             r"marker|item|door|object)s?$")
VECTOR_SWAP = {"*": "{r} * {l}", "+": "{r} + {l}", "-": "-{r} + {l}"}
# D1: costly work an infoFilter handler shouldn't do for responses that already failed
D1_CALLS = {"tes3.getDialogueInfo", "tes3.getReference", "tes3.iterateObjects", "tes3.isModActive"}
D1_METHODS = {"loadQuestName", "iterateReferences"}
STRING_METHODS = {"lower", "upper", "find", "match", "gmatch", "gsub", "format", "sub"}
# R1: event fields that hold a reference / mobile
REF_FIELDS = {"reference", "target", "mobile", "attacker", "attackerReference", "activator", "caster",
              "targetReference", "targetMobile", "actor", "current", "previous"}
NON_ACTOR_TYPES = {"activator", "alchemy", "ammunition", "apparatus", "armor", "book", "clothing", "container",
                   "door", "ingredient", "light", "lockpick", "miscItem", "probe", "repairItem", "static", "weapon"}
RULES_REV = 6                  # bump when a rule changes, so cached findings are worked out again
                               # (6: the I1 image-path rule is gone: icons and textures stay as the mod ships them)
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
    its "luafix" section, then mwdialog_luafix.json in the game folder."""
    cfg = dict(DEFAULTS)
    cfg["log"] = dict(DEFAULTS["log"])
    data_dir = data_dir or os.path.join(game_dir, "Data Files")
    # MWSE\\config\\mwguard.json is the user's in-game settings (written by the game, never staged): one of the
    # documented read-only exceptions of the pre-deploy rule (mwdialog_staged), also for staged files
    guard = os.path.join(MS.data_path_of(data_dir) or os.path.join(game_dir, "Data Files"), "MWSE", "config",
                         "mwguard.json")
    src = []
    for path, section in ((guard, None), (guard, "luafix"), (MP.state_path(game_dir, "mwdialog_luafix.json"), "")):
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
    ensure_own_mods(cfg, data_dir)
    return cfg


def cfg_hash(cfg):
    keep = {k: v for k, v in cfg.items() if not k.startswith("_")}
    keep["_known_bugs"] = globals().get("KNOWN_BUGS", [])
    keep["_rules"] = RULES_REV
    keep["_shim"] = hashlib.sha1(f"{SHIM_V}:{LOG_SHIM_LUA}".encode("latin-1", "replace"), usedforsecurity=False).hexdigest()[:8]
    return hashlib.sha1(json.dumps(keep, sort_keys=True).encode(), usedforsecurity=False).hexdigest()[:12] + f"v{VERSION}"


def mwguard_log_cover(data_dir, cfg, mod_key):
    """(covered, why): is mwguard's runtime log-spam guard clearly going to catch this mod's lines?"""
    if isinstance(data_dir, MS.StagedData):          # before deploy: the mwguard that will be deployed
        main = (data_dir.find(os.path.join("MWSE", "mods", "mwsuite", "mwguard", "main.lua"))
                or data_dir.find(os.path.join("MWSE", "mods", "mwguard", "main.lua")))
        if not main:
            return False, "mwguard is not staged (nor in lua tools)"
    else:
        main = os.path.join(data_dir or "", "MWSE", "mods", "mwsuite", "mwguard", "main.lua")
        if not os.path.isfile(main):
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


def find_checker(explicit=None, game_dir=HERE):
    """LuaJIT at <game>\\tools\\luajit\\ first, then luajit / luac on PATH, then lupa; None if there is none."""
    for c in MP.luajit_candidates(game_dir, explicit):
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
def module_name(name):
    """A require name or path the way package.path sees it: "Spammer\\G7 Containers\\renamer",
    "mods/foo/bar.lua" and "foo.bar" all become "spammer.g7 containers.renamer" / "foo.bar"."""
    s = name.strip().lower().replace("\\", "/").replace("/", ".")
    if s.endswith(".lua"):
        s = s[:-4]
    i = s.rfind("mwse.mods.")
    if i >= 0:
        s = s[i + len("mwse.mods."):]
    elif s.startswith("mods."):
        s = s[5:]
    return s.strip(".")


class Finding(dict):
    """rule, line, what, fix (proposal), conf (high | medium | report-high | report | trigger | covered | shimmed | info),
    edits [(start, end, text)], needs (helpers the edits use: "gate", "shim")."""


REF_NAME = re.compile(r"(?i)(ref|reference|target|actor|npc|creature|container|item|door|companion|follower|"
                      r"mobile)s?$")
DEBUG_FLAG = re.compile(r"(?i)(debug|debugmode|debug_mode|verbose|logging|logdebug|log_debug|enablelogging|"
                        r"enabledebug|showdebug|debuglog|debugging)")
KEY_BIND_RE = re.compile(r"(?i)config|cfg|setting|key|bind")


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
        embedded = SHIM_RE.search(src) or SHIM_V1_RE.search(src)
        self.old_shim = bool(embedded and embedded.group(0) != log_shim(mod_key, self.cfg))
        self.shim_state = "none" if embedded is None else "old" if self.old_shim else "current"
        self.calls = [n for n in self.nodes if n.kind == "Call"]
        self._lines = None
        self.registrations = []          # (call, event, handler Function or None, handler arg, options)
        self.handler_events = {}         # id(Function) -> events it is registered for
        self._gate_next = 1 + max([int(x) for x in re.findall(r"localpatch_gate\((\d+)", src)] or [0])
        self._handle_next = 1 + max([int(x) for x in re.findall(r"\blocalpatch_h(\d+)\b", src)] or [0])
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
        if edits and rule in ((self.cfg or {}).get("skipRules") or ()):
            what, conf, edits, needs = what + " (skipRules: not applied)", "report", (), ()
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

    def leading_guards(self, f):
        """The conditions of the 'if <cond> then return end' statements a function starts with (where M1's
        menu-mode return and G2's gate go, in either order)."""
        out = []
        for st in f.body.stats:
            if not (st.kind == "If" and len(st.clauses) == 1 and st.orelse is None):
                break
            body = st.clauses[0][1].stats
            if not (len(body) == 1 and body[0].kind == "Return" and not body[0].exprs):
                break
            out.append(self.text(st.clauses[0][0]))
        return out

    def gated(self, f):
        return any("localpatch_gate(" in c for c in self.leading_guards(f))

    def menu_guarded(self, f):
        return any(re.search(r"\btes3(ui)?\.menuMode\(\)", c) for c in self.leading_guards(f))

    def heavy_scans(self, f):
        """World scans in f and the same-file functions it calls: (names) sorted."""
        out = set()
        for g in self.closure(f):
            for n in L.walk(g.body):
                if n.kind == "Call":
                    d = L.dotted(n.func) or ""
                    if d in HEAVY_SCANS:
                        if d == "tes3.getReference" and n.args and n.args[0].kind == "String" and \
                                (L.string_value(n.args[0].raw) or "").lower() in PLAYER_IDS:
                            continue                          # answered without a scan
                        out.add(d)
                elif n.kind == "Method" and n.name in HEAVY_SCAN_METHODS:
                    out.add(":" + n.name)
        return sorted(out)

    # --- rules
    def run(self):
        for r in (self.r_priority, self.r_per_frame, self.r_timers, self.r_one_shot, self.r_data_guard,
                  self.r_keycode, self.r_lookups, self.r_event_fields, self.r_object_fields, self.r_destroy, self.r_console, self.r_info_filter, self.r_reregister,
                  self.r_reload_timers, self.r_globals, self.r_toplevel, self.r_loops, self.r_logger_level,
                  self.r_log_triggers, self.r_loggers, self.r_save_safe, self.r_while_caps, self.r_menu_exit,
                  self.r_vector_order, self.r_sound_query, self.r_frequent_lookups,
                  self.r_timer_refs, self.r_ref_data_modified, self.r_message_repeat, self.r_text_rewrite,
                  self.r_split_calls, self.r_log_concat):
            r()
        self.r_known()                    # last: a Known Bugs part applies only where no rule matched
        self.findings[:] = rules_before_kb(self.findings)
        return self.findings

    def r_message_repeat(self):
        """G8: tes3.messageBox("<literal>") in a handler of an event that fires per hit or per NPC decision
        (MESSAGE_EVENTS) shows the same text again for every hit -> at most once per messageInterval. In a
        per-frame handler it is only reported (it is often behind a key or state check the rule can't see)."""
        iv = self.cfg.get("messageInterval", DEFAULTS["messageInterval"])
        try:
            iv = max(float(iv), 0.5)
        except (TypeError, ValueError):
            iv = float(DEFAULTS["messageInterval"])
        ivs = f"{iv:g}"
        seen = set()
        for c, ev, fn, _h, _o in self.registrations:
            if fn is None or not (ev in MESSAGE_EVENTS or ev in PER_FRAME):
                continue
            for g in self.closure(fn):
                for n in L.walk(g.body):
                    if n.kind != "CallStat" or n.call.kind != "Call" or id(n) in seen:
                        continue
                    call = n.call
                    if L.dotted(call.func) != "tes3.messageBox" or not call.args or call.args[0].kind != "String" \
                            or any(a.kind not in ("String", "Number") for a in call.args[1:]):
                        continue
                    seen.add(id(n))
                    blk = n.parent
                    guard = blk.parent if blk is not None else None
                    if guard is not None and guard.kind == "If" and \
                            any("localpatch_gate(" in self.text(cl[0]) for cl in guard.clauses):
                        continue                          # already throttled
                    msg = self.text(call.args[0])[:50]
                    if ev in PER_FRAME:
                        self.add("G8", n, f"{ev} handler shows tes3.messageBox({msg}) - every frame it is reached",
                                 "show it once per state change", "report")
                        continue
                    k = self._gate_next
                    self._gate_next += 1
                    self.add("G8", n, f"{ev} handler shows the same tes3.messageBox({msg}) for every hit",
                             f"at most once per {ivs} s", "high",
                             self._wrap(n, f"not localpatch_gate({k}, {ivs})", "stmt"), {"gate"})

    def text_elements(self):
        """Names / fields assigned an element from :createLabel / :createBlock anywhere in the file."""
        out = set()
        for n in self.nodes:
            if n.kind == "Assign":
                pairs = [(L.dotted(t), n.exprs[i] if i < len(n.exprs) else None) for i, t in enumerate(n.targets)]
            elif n.kind == "Local":
                pairs = [(nm, n.exprs[i] if i < len(n.exprs) else None) for i, nm in enumerate(n.names)]
            else:
                continue
            for d, v in pairs:
                if d and v is not None and v.kind == "Method" and v.name in TEXT_ELEMENT_CREATORS:
                    out.add(d if isinstance(d, str) else getattr(d, "id", str(d)))
        return out

    def r_text_rewrite(self):
        """U1: a per-frame handler setting a label's .text to a plain value (a name, a field, a literal) each
        frame -> only when it differs. Setting .text goes to the engine's setText every time; the guard reads
        the same property back, so the element ends up the same."""
        elems = None
        seen = set()
        for c, ev, fn, _h, _o in self.registrations:
            if ev not in PER_FRAME or fn is None:
                continue
            for g in self.closure(fn):
                for n in L.walk(g.body):
                    if n.kind != "Assign" or id(n) in seen or len(n.targets) != 1 or len(n.exprs) != 1:
                        continue
                    t, v = n.targets[0], n.exprs[0]
                    if t.kind != "Index" or t.field != "text" or not self.plain_value(v):
                        continue
                    seen.add(id(n))
                    if elems is None:
                        elems = self.text_elements()
                    obj = L.dotted(t.obj)
                    if not obj or obj not in elems:
                        continue
                    tgt, val = self.text(t), self.text(v)
                    blk = n.parent
                    guard = blk.parent if blk is not None else None
                    if guard is not None and guard.kind == "If" and len(blk.stats) == 1 and \
                            any(re.sub(r"\s+", "", self.text(cl[0])) == re.sub(r"\s+", "", f"{tgt}~={val}")
                                for cl in guard.clauses):
                        continue                          # already only written on a change
                    self.add("U1", n, f"{ev} handler sets {tgt} every frame", f"only when it differs: "
                             f"if {tgt} ~= {val} then ... end", "high", self._wrap(n, f"{tgt} ~= {val}", "stmt"))

    @staticmethod
    def plain_value(v):
        """A value reading it twice can't change: a literal, a name, or a field chain of names."""
        if v.kind in ("String", "Number", "Name"):
            return True
        if v.kind == "Index":
            return v.key.kind == "String" and FileAnalysis.plain_value(v.obj) if hasattr(v, "key") and \
                v.key is not None else False
        return False

    def r_split_calls(self):
        """Y1: f\n(args) - a call's '(' on a later line than the function. Lua 5.1 and LuaJIT reject it ('ambiguous
        syntax (function call x new statement)'), so the whole file never loads. The '(' moves up to the function and
        the line break stays after it (every line number stays the same)."""
        for n in self.nodes:
            if n.kind not in ("Call", "Method") or n.argkind != "paren":
                continue
            if n.kind == "Call":
                end = n.func.e
            else:
                i = self.src.find(":", n.obj.e)
                j = self.src.find(n.name, i + 1) if i >= 0 else -1
                if j < 0:
                    continue
                end = j + len(n.name)
            k = end
            while k < len(self.src) and self.src[k] in " \t\r\n\f\v":
                k += 1
            if k >= len(self.src) or self.src[k] != "(" or "\n" not in self.src[end:k]:
                continue
            gap = self.src[end:k]
            self.add("Y1", n, f"{self.src[n.s:end][-40:]} and its '(' are on different lines: LuaJIT rejects the file "
                     f"(ambiguous syntax), so it never loads", "the '(' moves up to the call; the line break stays",
                     "high", [(end, k + 1, "(" + gap)])

    def _log_call(self, n):
        if n.kind == "Method":
            return n.name in LOG_METHODS and "log" in (L.dotted(n.obj) or "").lower()
        if n.kind != "Call":
            return False
        d = L.dotted(n.func) or ""
        if d in LOGS:
            return getattr(n.func if n.func.kind == "Name" else n.func.obj, "binding", None) is None
        return d.split(".")[-1].lower() in LOG_FUNC_NAMES

    def _bool_slots(self):
        """Table slots this file only ever stores true/false in: {key} (key: the slot's text for x.f, or the
        table's text + '[]' for x[k])."""
        got, other = set(), set()
        for n in self.nodes:
            if n.kind != "Assign":
                continue
            for i, t in enumerate(n.targets):
                if t.kind != "Index":
                    continue
                v = n.exprs[i] if i < len(n.exprs) else None
                key = (" ".join(self.text(t.obj).split()) + "[]") if t.field is None else " ".join(self.text(t).split())
                (got if v is not None and v.kind in ("True", "False") else other).add(key)
        return got - other

    def r_log_concat(self):
        """F3: a value that can only be true/false concatenated into log text ('attempt to concatenate a boolean
        value': the handler stops at its log line). It is wrapped in tostring(), nothing else changes."""
        calls = [n for n in self.nodes if self._log_call(n)]
        if not calls:
            return
        slots = None
        done = set()
        for c in calls:
            for a in c.args:
                for m in L.walk_no_funcs(a):
                    if m.kind != "Binop" or m.op != "..":
                        continue
                    for x in (m.left, m.right):
                        if id(x) in done:
                            continue
                        v = x
                        while v.kind == "Paren":
                            v = v.expr
                        boolean = v.kind in ("True", "False") or v.kind == "Unop" and v.op == "not" or \
                            v.kind == "Binop" and v.op in ("==", "~=", "<", ">", "<=", ">=")
                        if not boolean and x.kind == "Index":
                            if slots is None:
                                slots = self._bool_slots()
                            key = (" ".join(self.text(x.obj).split()) + "[]") if x.field is None else \
                                " ".join(self.text(x).split())
                            boolean = key in slots
                        if boolean:
                            done.add(id(x))
                            self.add("F3", x, f"{self.text(x)[:50]} is true/false and is concatenated into log text "
                                     f"('attempt to concatenate a boolean value')", "tostring()", "high",
                                     [(x.s, x.s, "tostring("), (x.e, x.e, ")")])

    def r_known(self):
        """KB<n>: documented bugs that cannot be repaired from a separate Lua mod."""
        rel = self.rel.lower()
        parts = {}
        skip = set((self.cfg or {}).get("skipKnown") or ())
        for rule, plugin, path, old, new, what in KNOWN_BUGS:
            if rel != path:
                continue
            if "\r\n" in self.src:
                old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
            found = []
            start = 0
            while (i := self.src.find(old, start)) >= 0:
                off = rule in skip
                found.append(Finding(rule=rule, line=self.src.count("\n", 0, i) + 1,
                                     what=f"{plugin}: {what}" + (" (skipKnown: not applied)" if off else ""),
                                     fix="" if off else new, conf="report" if off else "high",
                                     edits=[] if off else [(i, i + len(old), new)], needs=set()))
                start = i + len(old)
            if rule in KNOWN_BUGS_WHOLE:
                parts.setdefault(rule, []).append((plugin, what, found))
            else:
                self.findings += found
        for rule, got in parts.items():                  # a rule in parts applies whole or not at all
            n = sum(1 for _p, _w, f in got if f)
            if n == len(got):
                self.findings += [x for _p, _w, f in got for x in f]
            elif n:
                plugin, what = got[0][:2]
                self.findings.append(Finding(
                    rule=rule, line=1, what=f"{plugin}: {what}. Only {n} of its {len(got)} parts match: this file "
                    "is neither the version the fix was written for nor the fixed one, so it is left as it is",
                    fix="", conf="report", edits=[], needs=set()))

    def r_sound_query(self):
        """S1: tes3.getSoundPlaying asked about a reference that is not the player. For a loop on a non-actor
        (door, activator, light, static) the engine can answer "not playing" while it plays, so code that
        restarts the loop on that answer starts it again and again. Report only: a safe rewrite needs to know
        where the mod stops the sound (see the guide, Category I); mwsoundguard keeps one copy at runtime."""
        starts_loops = any(L.dotted(c.func) == "tes3.playSound" and c.args and c.args[0].kind == "Table"
                           and (v := table_field(c.args[0], "loop")) is not None and self.text(v) == "true"
                           for c in self.calls)
        for c in self.calls:
            if L.dotted(c.func) != "tes3.getSoundPlaying" or not c.args:
                continue
            arg = c.args[0].expr if c.args[0].kind == "Paren" else c.args[0]
            ref = table_field(arg, "reference")
            if ref is None:
                continue
            who = self.text(ref)
            if re.search(r"(?i)player|mobile|\bmp\b|actor|npc|creature", who):
                continue                             # an actor: the engine tracks its sounds
            body = self.src[max(0, c.s - 600):c.e]
            if "tes3.objectType.npc" in body or "tes3.objectType.creature" in body:
                continue                             # the code already tells actors from other references
            self.add("S1", c, f"asks the engine whether a sound plays on {who}; for a loop on a door, activator, "
                     "light or static it can say no while it plays, so restarting on that answer repeats the loop"
                     + (" (this file starts looping sounds)" if starts_loops else "")
                     + ". Check MWSE\\logs\\mwsoundguard.log for this mod's runaway entries; mwsoundguard "
                     "keeps one copy at runtime.", conf="report")

    def r_while_caps(self):
        """L1: a while loop that walks a linked structure (x = x.next) or counts a field down by a computed step
        (t = t - d while t >= ...) hangs the game when the links cycle or the step is 0 -> capped at 10000 turns."""
        k = 1 + max([int(x) for x in re.findall(r"localpatch_n(\d+)", self.src)] or [0])
        for n in self.nodes:
            if n.kind != "While" or "localpatch_n" in self.text(n.cond):
                continue
            cond_names = {L.dotted(x) for x in L.walk(n.cond) if x.kind in ("Name", "Index")} - {None}
            why = None
            for st in L.walk_no_funcs(n.body):
                if st.kind not in ("Assign", "Local") or len(st.exprs) != 1:
                    continue
                tgt = L.dotted(st.targets[0]) if st.kind == "Assign" else st.names[0]
                ex = st.exprs[0]
                if tgt not in cond_names:
                    continue
                base = ex.obj if ex.kind in ("Index", "Method") else None
                if base is not None and L.dotted(base) == tgt:
                    why = f"walks {tgt} = {self.text(ex)[:40]}"
                elif (ex.kind == "Binop" and ex.op in ("-", "+") and L.dotted(ex.left) == tgt
                      and ex.right.kind != "Number" and n.cond.kind == "Binop" and L.dotted(n.cond.left) == tgt
                      and n.cond.op in ((">=", ">") if ex.op == "-" else ("<=", "<"))):
                    why = f"steps {tgt} by {self.text(ex.right)[:30]} (a step of 0 never ends it)"
                if why:
                    break
            if not why:
                continue
            v = f"localpatch_n{k}"
            k += 1
            self.add("L1", n, f"while loop {why}", "stop it after 10000 turns", "high",
                     [(n.s, n.s, f"local {v} = 0 "), (n.cond.s, n.cond.s, "("),
                      (n.cond.e, n.cond.e, f") and {v} < 10000"), (n.body.s, n.body.s, f" {v} = {v} + 1 ")])

    def r_menu_exit(self):
        """M1: an enterFrame handler (enterFrame also fires in menus; simulate doesn't) that does world work and
        no UI work -> returns at once in menu mode."""
        ui = re.compile(r"tes3ui|menu|Menu|findChild|updateLayout|createBlock|createLabel|\.visible|messageBox")
        seen = set()
        for c, ev, fn, harg, _opts in self.registrations:
            if ev != "enterFrame" or fn is None or id(fn) in seen:
                continue
            seen.add(id(fn))
            if self.menu_guarded(fn):             # already returns in menu mode (by hand or an earlier run)
                continue
            body = "".join(self.text(g.body) for g in self.closure(fn))
            if ui.search(body):
                continue
            name = harg.id if harg.kind == "Name" else "(inline function)"
            known = ("tes3.", "mwse.", "math.", "string.", "table.", "timer.", "event.", "os.")
            opaque = [x for g in self.closure(fn) for x in L.walk(g.body) if x.kind == "Call" and not (
                (L.dotted(x.func) or "").startswith(known) or L.dotted(x.func) in LOGS or self.func_of(x.func))]
            self.add("M1", c, f"enterFrame handler {name} also runs while a menu is open"
                     + (f" (calls {self.text(opaque[0].func)[:30]}, which may do UI work)" if opaque else ""),
                     "return in menu mode", "medium" if opaque else "high", [(fn.params_end, fn.params_end, " if tes3.menuMode() then return end", (0, 0))])

    def vector_evidence(self, n, depth=0):
        """'high' / 'medium' when n is known to be a vector (MWSE's docs give it a vector type, or it's a local
        set from one), else None. Names alone (pos, dir, vol...) are not evidence."""
        if n is None or depth > 4:
            return None
        k = n.kind
        if k == "Paren":
            return self.vector_evidence(n.expr, depth + 1)
        if k == "Unop" and n.op == "-":
            return self.vector_evidence(n.operand, depth + 1)
        if k == "Binop" and n.op in ("*", "/", "+", "-"):
            left = self.vector_evidence(n.left, depth + 1)
            if left or n.op == "/":
                return left
            return self.vector_evidence(n.right, depth + 1) if n.op in ("+", "-") else None
        if k == "Call":
            d = L.dotted(n.func) or ""
            if d in VECTOR_CTORS:
                return "high"
            if n.func.kind == "Index" and n.func.field in VECTOR_NAMES:
                return "high"
            return None
        if k == "Method":
            if n.name in VECTOR_NAMES:
                return "high"
            if n.name in VECTOR_OF_SELF:
                return self.vector_evidence(n.obj, depth + 1)
            return None
        if k == "Index":
            if n.field in VECTOR_NAMES:
                return "high"
            if n.field == "position":
                base = L.dotted(n.obj) or ""
                return "high" if POSITION_HOLDER.search(base.split(".")[-1] or "") else "medium"
            return None
        if k == "Name":
            b = getattr(n, "binding", None)
            if b is None or b.kind != "local" or b.value is None or b.assigns:
                return None
            return self.vector_evidence(b.value, depth + 1)
        return None

    def r_vector_order(self):
        """V1: number * vector, number + vector and number - vector have no metamethod for that order in MWSE
        (TES3VectorsLua.cpp binds them as members, the vector first) and error every call. Only flagged when the
        right operand is known to be a vector; the 2026-11-24 rule flagged any number on the left (355 plain
        number products like 2 * math.pi)."""
        for n in self.nodes:
            if n.kind != "Binop" or n.op not in VECTOR_SWAP:
                continue
            lt = n.left.operand if n.left.kind == "Unop" and n.left.op == "-" else n.left
            if lt.kind != "Number" or n.right.kind in ("Number", "Binop", "Unop", "String"):
                continue
            conf = self.vector_evidence(n.right)
            if conf is None:
                continue
            new = VECTOR_SWAP[n.op].format(r=self.text(n.right), l=self.text(n.left))
            self.add("V1", n, f"{self.text(n)[:40]}: a number on the left of {n.op} a vector",
                     f"vector first: {new[:40]}", conf, [(n.s, n.e, new)])

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
        # event.unregister / event.isRegistered name the same priority: rewrite their literals to the compressed
        # value too, so the pair still reads as one registration (MWSE matches on the callback, but a reader and
        # any mod that compares priorities should see the number event.register now uses)
        for c in self.calls:
            if L.dotted(c.func) not in ("event.unregister", "event.isRegistered") or len(c.args) < 3:
                continue
            pv = table_field(c.args[2], "priority")
            p = num_value(pv) if pv is not None else None
            if p is None or abs(p) < lim:
                continue
            q = compress_priority(p, self.cfg)
            ev = event_name(c.args[0])
            self.add("G1", pv, f"{ev or '?'} {L.dotted(c.func)} priority {self.text(pv)}", f"priority {q}", "high",
                     [(pv.s, pv.e, str(q))])

    def _gate_edit(self, f):
        k = self._gate_next
        self._gate_next += 1
        return (f.params_end, f.params_end, f" if localpatch_gate({k}, {self.cfg['minInterval']}) then return end")

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
            scans = self.heavy_scans(fn) if cls == "medium" and not other and not more and \
                why.startswith(("calls code it can't see", "writes game state")) else []
            if scans:                           # G2S: the world scan is the cost; its reactions can wait 0.35 s
                self.add("G2S", c, f"{ev} handler {name} scans the world every frame ({', '.join(scans[:3])}); "
                         + why, f"run it at most every {self.cfg['minInterval']} s", "high",
                         [self._gate_edit(fn)], {"gate"})
                continue
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

    def r_save_safe(self):
        """I2: a repeating real-time timer whose callback redraws UI (updateLayout) keeps redrawing while the game
        saves, which fights the save for the D3D device (a crash on a loading-screen autosave): it skips while a
        save runs. I3: a config written inside a save handler is written the frame after the save."""
        saves = set()
        for c in self.calls:
            if L.dotted(c.func) == "event.register" and len(c.args) >= 2 and event_name(c.args[0]) == "save":
                fn = self.func_of(c.args[1])
                if fn is not None:
                    saves.add(id(fn))
        for c in self.calls:
            d = L.dotted(c.func)
            if d == "timer.start" and c.args and c.args[0].kind == "Table":
                tb = c.args[0]
                ty, it = table_field(tb, "type"), num_value(table_field(tb, "iterations"))
                fn = self.func_of(table_field(tb, "callback"))
                if ty is None or L.dotted(ty) != "timer.real" or it != -1 or fn is None or not fn.body.stats:
                    continue
                if not any(n.kind == "Method" and n.name == "updateLayout" for g in self.closure(fn)
                           for n in L.walk(g.body)):
                    continue
                if "localpatch_save" in self.text(fn.body.stats[0]):
                    continue
                at = fn.body.stats[0].s
                self.add("I2", c, "a repeating real-time timer redraws UI and keeps running through a save",
                         "skips while a save is running", "high", [(at, at, "if localpatch_save.saving then return end ")],
                         {"savestate"})
            elif d in ("mwse.saveConfig", "json.savefile"):
                fn = L.enclosing_function(c)
                if fn is not None and id(fn) in saves:
                    self.add("I3", c, f"{d} inside a save handler: the config is written while the game saves",
                             "written the frame after the save", "high",
                             [(c.s, c.e, f"timer.delayOneFrame(function() {self.text(c)} end, timer.real)")])

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
            conf = "high"
            if not REF_NAME.search(last):
                f0 = L.enclosing_function(n)
                if f0 is None or not self._ref_evidence(f0, bt):
                    continue                               # self.data, config.data...: not a reference
                conf = "medium"                            # a reference by its fields, not by its name
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
                write = n.parent is not None and n.parent.kind == "Assign" and any(t is n for t in n.parent.targets)
                if conf == "medium" and write:
                    g = f"{bt}.supportsLuaData"            # the write is skipped on a reference that can't hold it
                if write or n.parent is not None and n.parent.kind in ("Index", "Method", "Call", "Table", "Binop",
                                                                        "Return", "Local", "Assign", "Unop", "Paren"):
                    self._nil_fix("A1", n, g, f"{self.text(n)[:60]} used without checking {bt}.data (nil on "
                                  f"references that can't hold Lua data)", conf)
                continue
            levels = sorted((x for x in chain if x.e >= dnode.e), key=lambda x: x.e)
            rep = "(" + " and ".join(self.src[n.s:x.e] for x in levels) + ")"
            self.add("A1", n, f"{self.text(n)[:60]} read without checking {bt}.data (nil on references that "
                     f"can't hold Lua data)", rep, conf, [(n.s, n.e, rep)])

    def _ref_evidence(self, f, bt):
        """Does function f read a field only references have (REF_ONLY_FIELDS) on bt?"""
        for m in L.walk(f.body):
            if m.kind == "Index" and m.field in REF_ONLY_FIELDS and L.dotted(m.obj) == bt:
                return True
        return False

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
                if self._check_pos(m) or p is not None and p.kind == "Assign" and any(t is m for t in p.targets):
                    return True
                guarded = m
                while guarded.parent is not None and guarded.parent.kind == "Index" and guarded.parent.obj is guarded:
                    guarded = guarded.parent
                p = guarded.parent
                if p is not None and p.kind == "Binop" and p.op == "and" and p.right is guarded and any(
                        x.kind in ("Name", "Index") and L.dotted(x) in (bt, want_d) for x in L.walk(p.left)):
                    return True
        return False

    def r_keycode(self):
        for n in self.nodes:
            if n.kind != "Index" or n.field not in KEY_FIELDS:
                continue
            bt = L.dotted(n.obj)
            if not bt or not KEY_BIND_RE.search(bt):
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
        if p.kind == "Binop" and p.op in ("and", "or"):
            st = stmt_of(n)
            if st.kind == "Assign" and any((L.dotted(t) or "").startswith(g + ".") for t in st.targets):
                return None, "the assignment itself gets the same guard"
            value = n
            while value.parent is not None and value.parent.kind == "Binop" and value.parent.op in ("and", "or"):
                value = value.parent
            length = value.e - value.s
            return ([(value.s, value.s, f"({g} and (", (1, -length)),
                     (value.e, value.e, "))", (0, length))], "and-guard on the value")
        if p.kind == "Table" and any(value is n and key is not n for _name, key, value in p.fields):
            return self._wrap(n, g, "expr"), "and-guard on the table value"
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
        if st.kind in ("CallStat", "GenFor") or st.kind == "Assign" and len(st.targets) == 1 and len(st.exprs) == 1:
            t = (L.dotted(st.targets[0]) or "") if st.kind == "Assign" else ""
            if st.kind == "Assign" and t and any(x == t or x.startswith(t + ".") for x in g.split(" and ")):
                return None, "the statement assigns the value being checked"
            return self._wrap(st, g, "stmt"), "if-guard on the statement"
        if q is not None and q.kind == "Binop":
            return None, "in an and/or expression outside a condition"
        return None, f"inside a {st.kind.lower()} statement that can't be wrapped without changing scope or flow"

    def _nil_fix(self, rule, n, g, what, conf="high"):
        edits, how = self.nil_plan(n, g)
        if edits is None:
            return self.add(rule, n, what, f"check {g} first - left as a report: {how}", "report")
        seen = self.__dict__.setdefault("_nil_seen", set())
        sig = tuple((s, e, t) for s, e, t, _o in edits)
        if sig in seen:                                      # same guard as another read in this place
            return self.add(rule, n, what, f"{how} on {g} (with the read above)", conf)
        seen.add(sig)
        tgt = (edits[0][0], edits[1][0])
        body = " ".join(self.src[tgt[0]:tgt[1]].split())
        prev = edits[0][2] + (body if len(body) <= 90 else body[:80] + " ... ") + edits[1][2]
        return self.add(rule, n, what, f"{how}: {prev}", conf, edits)

    def _uses_of(self, n):
        """n.x / n:m() reads of n (a nil-able value): the Index/Method nodes that would fail."""
        p = n.parent
        return p if p is not None and p.kind in ("Index", "Method") and p.obj is n else None

    def _guard_binding_uses(self, rule, b, g, what_of, conf="high"):
        if b.assigns or any(self._check_pos(r) for r in b.reads):
            return
        for r in b.reads:
            u = self._uses_of(r)
            if u is not None and u.s >= (self.nodes[0].s if self.nodes else 0):
                self._nil_fix(rule, u, g, what_of(u), conf)

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
                        f"never checked"), "medium" if d in NIL_LOOKUPS_MEDIUM else "high")
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
                         f"then ... end end", "medium" if d in NIL_LOOKUPS_MEDIUM else "high", edits)
            else:
                self.add("A3", c, what, "keep the result in a local and check it - left as a report: the lookup "
                         "is indexed inside a bigger expression", "report")

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

    def r_object_fields(self):
        """A5: x.baseObject.head.id (or .object.hair...) with no check that the NPC has that body part."""
        for n in self.nodes:
            if n.kind != "Index" or n.field not in NULLABLE_OBJECT_FIELDS or n.obj.kind != "Index" \
                    or n.obj.field not in OBJECT_HOLDERS or self._check_pos(n):
                continue
            g = L.dotted(n)
            u = self._uses_of(n)
            if g is None or u is None:
                continue
            scope = n.parent
            while scope is not None and scope.kind != "Function":
                scope = scope.parent
            if self._guard_checked(scope.body if scope is not None else self.nodes[0], g):
                continue
            self._nil_fix("A5", u, g, f"{self.text(u)[:50]} - {g} is nil for an NPC whose record names no "
                                      f"{n.field} (or one no loaded mod defines), and is never checked")

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

    def _d1_costly(self, n, p):
        """What n costs, if it's work an infoFilter handler shouldn't do for a response that already failed."""
        if n.kind == "Index" and L.dotted(n) == f"{p}.info.text":
            return "text"
        if n.kind == "Index" and n.field == "text" and (L.dotted(n.obj) or "").endswith(".script"):
            return "reads a script's text (file I/O)"
        if n.kind == "Call":
            d = L.dotted(n.func) or ""
            if d in D1_CALLS:
                return f"calls {d}"
            if d in ("string.lower", "string.find", "string.format", "string.match", "string.gsub") and n.args \
                    and (L.dotted(n.args[0]) or "") in (f"{p}.dialogue.id", f"{p}.info.id"):
                return f"string work on {L.dotted(n.args[0])}"
        if n.kind == "Method":
            if n.name in D1_METHODS:
                return f"calls :{n.name}()"
            if n.name in STRING_METHODS and (L.dotted(n.obj) or "") in (f"{p}.dialogue.id", f"{p}.info.id"):
                return f"string work on {L.dotted(n.obj)}"
        return None

    def _side_effects(self, fn, p):
        """True when fn does more than block lines: writes outside its own locals, logs, or calls actions."""
        for n in L.walk_no_funcs(fn.body):
            if n.kind == "Assign":
                for t in n.targets:
                    if t.kind == "Index" and L.dotted(t) == f"{p}.passes":
                        continue
                    if t.kind == "Name" and getattr(t, "binding", None) is not None and t.binding.func is fn:
                        continue
                    return True
            elif n.kind == "Call":
                d = L.dotted(n.func) or ""
                if d in ACTIONS or d in LOGS:
                    return True
                if n.func.kind == "Name" and self.func_of(n.func) is None and d not in QUERIES:
                    return True
            elif n.kind == "Method" and n.name not in SAFE_METHODS and n.name not in D1_METHODS:
                return True
        return False

    def r_info_filter(self):
        for c, ev, fn, harg, opts in self.registrations:
            if ev != "infoFilter" or fn is None or not fn.params:
                continue
            p = fn.params[0]
            reads, costly, other_passes, returns = [], [], [], []
            for n in L.walk_no_funcs(fn.body):
                why = self._d1_costly(n, p)
                if why == "text":
                    reads.append(n)
                elif why:
                    costly.append((n, why))
                if n.kind == "Index" and L.dotted(n) == f"{p}.passes":
                    par = n.parent
                    if par is not None and par.kind == "Assign" and any(t is n for t in par.targets):
                        i = [id(t) for t in par.targets].index(id(n))
                        if i < len(par.exprs) and par.exprs[i].kind == "False":
                            continue                       # blocking only: a no-op for responses that failed
                    other_passes.append(n)
                elif n.kind == "Return" and n.exprs:
                    returns.append(n)
            if not (reads or costly) or (fn.body.stats and f"not {p}.passes" in self.text(fn.body.stats[0])):
                continue
            if reads:
                if other_passes:
                    if other_passes[0].s > reads[0].s:
                        self.add("D1", reads[0], f"infoFilter reads {p}.info.text (a disk read) before checking "
                                 f"{p}.passes", f"check {p}.passes and the dialogue type first")
                    continue
                if returns:
                    self.add("D1", reads[0], f"infoFilter reads {p}.info.text for every response; it returns a "
                             f"value, so returning early could change what it blocks", f"check {p}.passes first",
                             "medium", [(fn.params_end, fn.params_end, f" if not {p}.passes then return end")])
                    continue
                self.add("D1", reads[0], f"infoFilter reads {p}.info.text for every response the engine tries "
                         f"(each one a disk read; a greeting search can freeze for minutes)",
                         f"return early unless {p}.passes", "high",
                         [(fn.params_end, fn.params_end, f" if not {p}.passes then return end")])
                continue
            first, why = costly[0]
            what = f"infoFilter {why} for every response the engine tries, before checking {p}.passes"
            if other_passes:
                if other_passes[0].s > first.s:
                    self.add("D1", first, what, f"check {p}.passes first")
                continue
            if returns or self._side_effects(fn, p):
                self.add("D1", first, what + " (it does more than block lines, so an early return is left to you)",
                         f"check {p}.passes first")
                continue
            self.add("D1", first, what, f"return early unless {p}.passes", "high",
                     [(fn.params_end, fn.params_end, f" if not {p}.passes then return end")])

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
            if set(evs) <= {"loaded", "load"}:
                continue                     # MWSE cancels every timer (real ones too) just before loaded
            what = f"repeating {typ} started in the {'/'.join(evs)} handler and never cancelled: one more runs " \
                   f"each time it fires"
            st = stmt_of(c)
            held = self._kept_handle(c, _outer)
            if held and st is not None and st.parent is not None and st.parent.kind == "Block" and \
                    side_effect_free(st.targets[0]):
                f = self.add("H2", c, what, f"the old timer is cancelled first: if {held} then {held}:cancel() end",
                             "medium", [(st.s, st.s, f"if {held} then {held}:cancel() end ")])
            else:
                f = self.add("H2", c, what, "keep the handle; cancel the old timer before starting one",
                             "report-high")
            f["events"] = list(evs)          # dropped later when each is a custom event fired only on loaded

    def _kept_handle(self, c, outer):
        """The name or field c (a timer.start call) is stored in, when it outlives the handler outer (an upvalue,
        a global or a table field): x = timer.start{...}. None otherwise."""
        p = c.parent
        if p is None or p.kind != "Assign" or len(p.targets) != 1 or len(p.exprs) != 1 or p.exprs[0] is not c:
            return None
        t = p.targets[0]
        d = L.dotted(t)
        if not d:
            return None
        if t.kind == "Name":
            b = getattr(t, "binding", None)
            if b is not None and outer is not None and b.func is not None and \
                    outer.s <= b.func.s and b.func.e <= outer.e:
                return None                  # a local of the handler: gone when it returns
        return d

    def _fast_timers(self):
        """[(timer.start call, callback Function)] for timers repeating faster than once a second."""
        out = []
        for c in self.calls:
            if L.dotted(c.func) != "timer.start" or not c.args or c.args[0].kind != "Table":
                continue
            t = c.args[0]
            dv, iv = num_value(table_field(t, "duration")), num_value(table_field(t, "iterations"))
            fn = self.func_of(table_field(t, "callback"))
            if fn is not None and dv is not None and dv < 1 and iv is not None and (iv < 0 or iv > 1):
                out.append((c, fn))
        return out

    def r_frequent_lookups(self):
        """G6: tes3.getReference in a frequent handler or a fast timer (it scans every cell's references; MWSE's
        docs: look it up once on load and keep a safe handle). G7: tes3.rayTest every frame or in a frequent
        handler with no maxDistance / no root, or with accurateSkinned (MWSE's rayTest performance tips)."""
        places = []
        for c, ev, fn, harg, _opts in self.registrations:
            if fn is not None and ev in FREQUENT_EVENTS:
                places.append((fn, ev, ev in PER_FRAME))
        for c, fn in self._fast_timers():
            places.append((fn, "fast timer", True))
        seen6, seen7 = set(), set()
        for fn, ev, per_frame in places:
            for g in self.closure(fn):
                for n in L.walk(g.body):
                    if n.kind != "Call":
                        continue
                    d = L.dotted(n.func)
                    if d == "tes3.getReference" and n.args and n.args[0].kind == "String" and \
                            (L.string_value(n.args[0].raw) or "").lower() in PLAYER_IDS:
                        continue                     # MWSE answers "player" without searching (TES3Util.cpp)
                    if d == "tes3.getReference" and ev not in PER_FRAME and id(n) not in seen6:
                        seen6.add(id(n))             # per-frame handlers: G5 counts it with the other lookups
                        self.add("G6", n, f"tes3.getReference in the {ev} handler (scans every cell's references "
                                 f"each call)", "look it up once on loaded and keep a tes3.makeSafeObjectHandle")
                    elif d == "tes3.rayTest" and id(n) not in seen7 and n.args and n.args[0].kind == "Table":
                        seen7.add(id(n))
                        t = n.args[0]
                        miss = [k for k in ("maxDistance", "root") if table_field(t, k) is None]
                        skinned = table_field(t, "accurateSkinned")
                        if skinned is not None and skinned.kind == "True":
                            miss.append("accurateSkinned = true")
                        if not miss:
                            continue
                        self.add("G7", n, f"tes3.rayTest in the {ev} handler: " + ", ".join(
                            ("no " + m) if m in ("maxDistance", "root") else m for m in miss),
                            "set maxDistance, pass a root (worldObjectRoot / worldPickRoot / worldLandscapeRoot), "
                            "drop accurateSkinned", "report-high" if per_frame and "maxDistance" in miss else "report")

    def _ref_source(self, n):
        """Where an expression holding a reference comes from (e.field / tes3.getReference), or None."""
        if n is None:
            return None
        if n.kind == "Index" and n.field in REF_FIELDS and n.obj.kind == "Name":
            b = getattr(n.obj, "binding", None)
            if b is not None and b.kind == "param":
                return L.dotted(n)
        if n.kind == "Call" and L.dotted(n.func) in ("tes3.getReference", "tes3.getPlayerTarget"):
            return L.dotted(n.func) + "()"
        return None

    def r_timer_refs(self):
        """R1: a timer callback using a reference it captured from its event (or tes3.getReference) with no safe
        handle or :isValid() check. MWSE's object-lifetimes guide: the reference can be gone when the timer
        fires; since MWSE 2026-05 that is a Lua error on each such call, not a crash."""
        for c in self.calls:
            if L.dotted(c.func) != "timer.start" or not c.args or c.args[0].kind != "Table":
                continue
            fn = table_field(c.args[0], "callback")
            if fn is None or fn.kind != "Function":
                continue
            body = self.text(fn)
            if re.search(r":(isValid|valid)\(|makeSafeObjectHandle|getObject\(", body):
                continue
            hit = None
            for n in L.walk(fn.body):
                if n.kind == "Name":
                    b = getattr(n, "binding", None)
                    if b is None or (b.func is not None and fn.s <= b.func.s and b.func.e <= fn.e):
                        continue                             # a global, or a local of the callback itself
                    src = self._ref_source(b.value) if b.kind == "local" and not b.assigns else None
                    if src:
                        hit = (n, f"{n.id} (= {src})", n.id if b.decl is not None and b.decl.e <= c.s else None)
                        break
                elif n.kind == "Index" and n.field in REF_FIELDS and n.obj.kind == "Name":
                    b = getattr(n.obj, "binding", None)
                    if b is not None and b.kind == "param" and b.func is not fn and not (
                            fn.s <= b.func.s and b.func.e <= fn.e):
                        hit = (n, L.dotted(n), L.dotted(n))
                        break
            if hit:
                what = f"timer callback uses {hit[1]} from when the timer started, with no safe handle or " \
                       f":isValid() check (the reference can be gone when it fires)"
                held = hit[2]
                st = stmt_of(c)
                if held and st is not None and st.parent is not None and st.parent.kind == "Block":
                    h = f"localpatch_h{self._handle_next}"
                    self._handle_next += 1
                    self.add("R1", hit[0], what, f"a safe handle taken when it starts; the callback returns once "
                             f"the reference is gone: local {h} = {held} and tes3.makeSafeObjectHandle({held})",
                             "high", [(st.s, st.s, f"local {h} = {held} and tes3.makeSafeObjectHandle({held}) "),
                                      (fn.params_end, fn.params_end, f" if {h} and not {h}:valid() then return end")])
                else:
                    self.add("R1", hit[0], what, "tes3.makeSafeObjectHandle(ref) when starting it; :valid() / "
                             ":getObject() in the callback")

    def timer_names(self):
        """([(name, line)] started by name, {names registered}) for T1."""
        started, registered = [], set()
        for c in self.calls:
            d = L.dotted(c.func)
            if d == "timer.start" and c.args and c.args[0].kind == "Table":
                cb = table_field(c.args[0], "callback")
                if cb is not None and cb.kind == "String":
                    started.append((L.string_value(cb.raw) or "", self.line(c)))
            elif d == "timer.register" and c.args and c.args[0].kind == "String":
                registered.add(L.string_value(c.args[0].raw) or "")
        return started, registered

    def r_ref_data_modified(self):
        """P1: ref.data written on a reference the code itself shows is not an actor (an item, door, container...)
        with no ref.modified = true in the same function: MWSE only saves .data on modified references
        (Storing Data guide)."""
        for fn in [n for n in self.nodes if n.kind == "Function"]:
            writes, modified, nonactor = [], set(), set()
            evs = self.events_of_function(fn)
            for n in L.walk_no_funcs(fn.body):
                if n.kind == "Assign":
                    for t in n.targets:
                        d = L.dotted(t) or ""
                        if d.endswith(".modified"):
                            modified.add(d[:-len(".modified")])
                        m = re.match(r"^(.+?)\.data\.", d + ".") if t.kind == "Index" else None
                        if m and ".data." in d + "." and not d.startswith(("tes3.player", "tes3.mobilePlayer")):
                            writes.append((t, m.group(1)))
                elif n.kind == "Binop" and n.op in ("==", "~="):
                    for a, b in ((n.left, n.right), (n.right, n.left)):
                        da, db = L.dotted(a) or "", L.dotted(b) or ""
                        if da.startswith("tes3.objectType.") and da.split(".")[-1] in NON_ACTOR_TYPES and \
                                db.endswith(".objectType"):
                            holder = db[:-len(".objectType")]
                            for suffix in (".object", ".baseObject"):
                                if holder.endswith(suffix):
                                    holder = holder[:-len(suffix)]
                            nonactor.add(holder)
            if "itemDropped" in evs and fn.params:
                nonactor.add(f"{fn.params[0]}.reference")
            seen = set()
            for t, holder in writes:
                if holder in nonactor and holder not in modified and holder not in seen:
                    seen.add(holder)
                    self.add("P1", t, f"{holder}.data written on a non-actor reference without "
                             f"{holder}.modified = true (MWSE doesn't save .data on an unmodified reference)",
                             f"set {holder}.modified = true")

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
                if self._nil_safe_chain(n):
                    continue
                hits.append((n, d))
        fixed = set()
        for n, d in hits:
            f = self._read_when_used(n)
            if f is not None:
                fixed.add(id(n))
        rest = [(n, d) for n, d in hits if id(n) not in fixed]
        if rest:
            n, d = rest[0]
            self.add("H4", n, f"{d} used when the file loads ({len(rest)} place(s)), before the game data exists",
                     "move it into an initialized (or loaded) handler")

    def _nil_safe_chain(self, n):
        """n is part of 'a.b and a.b.c ...' (the value H4's fix leaves): each step is checked before it is read."""
        top = n
        while top.parent is not None and top.parent.kind == "Index" and top.parent.obj is top:
            top = top.parent
        p, q = top.parent, None
        while p is not None and p.kind == "Binop" and p.op == "and":
            q, p = p, p.parent
        if q is None:
            return False
        parts = [x for x in re.split(r"\s+and\s+", self.text(q))]
        return len(parts) > 1 and all(re.fullmatch(r"[A-Za-z_][\w.]*", x) for x in parts) and \
            all(parts[i + 1].startswith(parts[i] + ".") for i in range(len(parts) - 1))

    def _read_when_used(self, n):
        """H4 fix: local X = tes3.worldController.weatherController (or a field chain of tes3.player /
        tes3.mobilePlayer) at the top of the file, never assigned again: the value is nil-safe when the file loads
        and each read is (X or <the chain>), so it is read again when it is used. None when the shape differs."""
        top = n
        while top.parent is not None and top.parent.kind == "Index" and top.parent.obj is top:
            top = top.parent
        st = top.parent
        if top.kind != "Index" or st is None or st.kind != "Local" or len(st.names) != 1 or len(st.exprs) != 1 or \
                st.exprs[0] is not top or st.parent is None or st.parent.kind != "Block":
            return None
        chain = L.dotted(top)
        if not chain or not any(chain == r or chain.startswith(r + ".") for r in LOAD_NIL_ROOTS):
            return None
        b = next((m.binding for m in self.nodes if m.kind == "Name" and getattr(m, "binding", None) is not None
                  and m.binding.decl is st), None)
        if b is None or b.assigns or not b.reads:
            return None
        parts = chain.split(".")
        safe = " and ".join(".".join(parts[:i]) for i in range(2, len(parts) + 1))
        edits = [(top.s, top.e, safe)] + [(r.s, r.e, f"({r.id} or ({safe}))") for r in b.reads]
        return self.add("H4", n, f"{st.names[0]} = {chain} is taken when the file loads, before the game data "
                        f"exists (nil then)", f"read when used: ({st.names[0]} or ({safe}))", "medium", edits)

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
        """How many print / mwse.log calls reach the global functions (not a local of the same name), plus
        append-mode io.open calls (a log the mod keeps itself: the shim's io starts it new each session)."""
        n = 0
        for c in self.calls:
            if c.func.kind == "Name" and c.func.id == "print" and getattr(c.func, "binding", None) is None:
                n += 1
            elif c.func.kind == "Index" and L.dotted(c.func) == "mwse.log" and \
                    getattr(c.func.obj, "binding", None) is None:
                n += 1
        for c in self.calls:                       # io.open(path, "a"): a log kept by the mod itself
            if c.func.kind == "Index" and L.dotted(c.func) == "io.open" and getattr(c.func.obj, "binding", None) is None \
                    and len(c.args) > 1 and c.args[1].kind == "String" \
                    and (L.string_value(c.args[1].raw) or "").startswith("a"):
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
            if par is not None and par.kind == "Call" and L.dotted(par.func) == "localpatch_log.wrap":
                continue
            out.append(c)
        return out

    def r_loggers(self):
        for c in self.logger_creations():
            self.add("F1", c, "logger created here", "its trace/debug/info lines go through the log shim", "logger",
                     [(c.s, c.s, "localpatch_log.wrap("), (c.e, c.e, ")")], ["shim"])

    LOADERS = ("require", "include", "dofile", "loadfile")
    BARE_NAME_RE = re.compile(r"^[A-Za-z_][\w .-]{0,59}$")

    def load_refs(self):
        """(names, prefixes, literals) for the dead-file pass: names this file loads (require / include / dofile
        / loadfile / pcall(require, ...)) anywhere in it, the leading text of each load whose name is built at
        run time ("" when nothing is known: the whole mod may be loaded that way), and every string literal
        that could name a module (a framework may require a name another file hands it)."""
        names, prefixes, lits = set(), set(), set()
        direct = set()
        for c in self.calls:
            f, args = c.func, c.args
            if f.kind == "Name" and f.id in ("pcall", "xpcall") and args and args[0].kind == "Name" and \
                    args[0].id in self.LOADERS:
                direct.add(id(args[0]))
                f, args = args[0], args[1:] if f.id == "pcall" else args[2:]
            if f.kind != "Name" or f.id not in self.LOADERS:
                continue
            direct.add(id(f))
            a = args[0] if args else None
            if a is not None and a.kind == "String":
                names.add(module_name(L.string_value(a.raw) or ""))
            else:
                lead = a
                while lead is not None and lead.kind == "Binop" and lead.op == "..":
                    lead = lead.left
                prefixes.add(module_name(L.string_value(lead.raw) or "") if lead is not None and
                             lead.kind == "String" else "")
        for n in self.nodes:
            if n.kind == "Name" and n.id in self.LOADERS and id(n) not in direct and \
                    getattr(n, "binding", None) is None:
                prefixes.add("")                     # require handed around or aliased: can't follow it
            elif n.kind == "String" and len(n.raw) < 260:
                v = L.string_value(n.raw) or ""
                if any(ch in v for ch in "./\\") and "\n" not in v:
                    lits.add(module_name(v))
                elif self.BARE_NAME_RE.match(v):
                    lits.add(v.lower())              # a bare module name a loader may join to a path
        return sorted(names), sorted(prefixes), sorted(lits - names)

    def event_triggers(self):
        """[(custom event, [events of the handler that fires it] or None)] for event.trigger("name", ...).
        None: fired outside a handler, or from a function the file also calls directly."""
        out = []
        for c in self.calls:
            if L.dotted(c.func) != "event.trigger" or not c.args or c.args[0].kind != "String":
                continue
            fn = L.enclosing_function(c)
            evs = sorted(self.events_of_function(fn)) if fn is not None else []
            if evs and any(n.kind == "Call" and n.func.kind == "Name" and self.func_of(n.func) is fn
                           for n in self.calls):
                evs = []
            out.append((L.string_value(c.args[0].raw) or "", evs or None))
        return out

    def requires(self):
        out = []
        for c in self.calls:
            if c.func.kind == "Name" and c.func.id in ("require", "include") and c.args and \
                    c.args[0].kind == "String" and L.enclosing_function(c) is None:
                out.append(L.string_value(c.args[0].raw) or "")
        return out

    def module_calls(self):
        """[(module, field, line)]: X.field(...) calls through a top-level `local X = require("module")`; line 0
        for a field this file adds to it (function X.field / X.field = ...)."""
        mods = {}
        for st in self.tree.body.stats:
            if st.kind == "Local" and len(st.names) == 1 and len(st.exprs) == 1:
                c = st.exprs[0]
                if c.kind == "Call" and c.func.kind == "Name" and c.func.id == "require" and c.args and \
                        c.args[0].kind == "String":
                    mods[st.names[0]] = L.string_value(c.args[0].raw) or ""
        reassigned = {L.dotted(t) for n in self.nodes if n.kind == "Assign" for t in n.targets}
        out = []
        for n in self.nodes:
            if n.kind == "FuncStat" and len(n.path) == 2 and n.path[0] in mods:
                out.append((mods[n.path[0]], n.path[1], 0))
            elif n.kind == "Assign":
                for t in n.targets:
                    if t.kind == "Index" and t.field and t.obj.kind == "Name" and t.obj.id in mods:
                        out.append((mods[t.obj.id], t.field, 0))
        for c in self.calls:
            f = c.func
            if f.kind == "Index" and f.field and f.obj.kind == "Name" and f.obj.id in mods \
                    and f.obj.id not in reassigned:
                out.append((mods[f.obj.id], f.field, self.line(c)))
        return out

    def module_fields(self):
        """The fields of the table this module returns (`local M = {...} ... return M`), or None when that
        can't be told for sure (built some other way, a metatable, M handed to other code)."""
        body = self.tree.body.stats
        if not body or body[-1].kind != "Return" or len(body[-1].exprs) != 1 or \
                any(L.dotted(c.func) in ("setmetatable", "rawset") for c in self.calls):
            return None
        r = body[-1].exprs[0]
        if r.kind == "Table":
            return {k for k, _ke, _v in r.fields if k}
        if r.kind != "Name":
            return None
        name, fields, made = r.id, set(), False
        for st in body:
            if st.kind == "Local" and st.names == [name] and len(st.exprs) == 1 and st.exprs[0].kind == "Table":
                fields |= {k for k, _ke, _v in st.exprs[0].fields if k}
                made = True
        if not made:
            return None
        for n in self.nodes:
            if n.kind == "FuncStat" and n.path[0] == name and len(n.path) == 2:
                fields.add(n.path[1])
            elif n.kind == "Assign":
                for t in n.targets:
                    if t.kind == "Name" and t.id == name:
                        return None                  # M itself replaced
                    if t.kind == "Index" and t.obj.kind == "Name" and t.obj.id == name:
                        if not t.field:
                            return None              # M[k] = ...: fields we can't name
                        fields.add(t.field)
            elif n.kind == "Call" and any(a.kind == "Name" and a.id == name for a in n.args):
                return None                          # M handed to code that may add to it
        return fields


# ---------------------------------------------------------------------------------------------- what we add
SAVE_HELPER = ('local localpatch_save do localpatch_save = package.loaded["localpatch_savestate"] '
               'if type(localpatch_save) ~= "table" then localpatch_save = { saving = false } '
               'package.loaded["localpatch_savestate"] = localpatch_save '
               'event.register("save", function() localpatch_save.saving = true end, { priority = 9999 }) '
               'event.register("saved", function() localpatch_save.saving = false end) '
               'event.register("loaded", function() localpatch_save.saving = false end) '
               'event.register("menuExit", function() localpatch_save.saving = false end) end end ')

# (rule, owner, path under MWSE\mods or MWSE, exact vulnerable text, replacement, bug description)
KNOWN_BUGS = [
    ("KB1", "AttendMeMWSE", "attendmemwse/followers.lua",
     "if ref and ref.mobile and not ref.mobile.isDead then",
     "local localpatch_ok, localpatch_alive = pcall(function() return ref.mobile and not ref.mobile.isDead end) "
     "if ref and localpatch_ok and localpatch_alive then",
     "refresh() reads .mobile on the references it kept from the last pass; one that was deleted since raises "
     "'sol: received nil for self' every timer tick, and the list is never rebuilt (MWSE.log 2026-11-18)"),
    ("KB2", "UI Expansion", "ui expansion/menudialog.lua",
     'element:getPropertyObject("") or dialogue:getInfo({ actor = mobileActor })',
     'element:getPropertyObject("MenuDialog_UIEXP_info") or dialogue:getInfo({ actor = mobileActor })',
     "the topic updater queries an empty property key, so actor-unique topics never reuse their cached info"),
    ("KB3", "MWSE Core", "core/mcm/components/pages/exclusionspage.lua",
     "self.elements.outerContainer.parent:destroyChildren()\n\tself:create(self.elements.outerContainer.parent)",
     "local parent = self.elements.outerContainer.parent\n\tparent:destroyChildren()\n\tself:create(parent)",
     "ExclusionsPage destroys outerContainer and then dereferences that destroyed element's parent"),
]

KNOWN_BUGS_WHOLE = {"KB4", "KB11", "KB13", "KB14", "KB16", "KB17", "KB19"}    # rules whose parts depend on each other: every part matches, or none is applied
KB4 = ("ExclusionsPage builds one UI element per item, unbounded (thousands with Tamriel Data); pages of 100 "
       "per column keep every match. Exact text of MWSE's ExclusionsPage.lua as shipped since 2024-07-19; all of "
       "KB4 applies or none of it")
KNOWN_BUGS += [
    ("KB4", "MWSE Core", "core/mcm/components/pages/exclusionspage.lua",
     'local placeholderText = mwse.mcm.i18n("Search...")\n\n--- Constructor',
     '''local placeholderText = mwse.mcm.i18n("Search...")
local PAGE_SIZE = 100

local function addPager(self, content, listName, total)
	local pages = math.max(1, math.ceil(total / PAGE_SIZE))
	self.pages = self.pages or {}
	local page = math.min(math.max(self.pages[listName] or 1, 1), pages)
	self.pages[listName] = page
	local first, last = (page - 1) * PAGE_SIZE + 1, page * PAGE_SIZE
	if pages == 1 then
		return first, last
	end

	local row = content:createBlock()
	row.flowDirection = tes3.flowDirection.leftToRight
	row.autoHeight = true
	row.widthProportional = 1.0
	row.childAlignX = 0.5
	local function changePage(delta)
		self.pages[listName] = page + delta
		if listName == "leftList" then
			self:distributeLeft(self.currentItems)
		else
			self:distributeRight(self.currentItems)
		end
		local menu = self.elements.outerContainer and self.elements.outerContainer:getTopLevelMenu()
		if menu then menu:updateLayout() end
	end
	if page > 1 then
		row:createButton{ text = "< Previous" }:register(tes3.uiEvent.mouseClick, function() changePage(-1) end)
	end
	local label = row:createLabel{ text = string.format("Page %d / %d (%d items)", page, pages, total) }
	label.borderLeft, label.borderRight = 8, 8
	if page < pages then
		row:createButton{ text = "Next >" }:register(tes3.uiEvent.mouseClick, function() changePage(1) end)
	end
	return first, last
end

--- Constructor''', KB4),
    ("KB4", "MWSE Core", "core/mcm/components/pages/exclusionspage.lua",
     '''function ExclusionsPage:toggle(e)
	-- toggle an item between blocked / allowed

	-- delete element
	local list = e.source.parent.parent.parent
	local text = e.source.text
	e.source:destroy()

	-- toggle blocked
	if list == self.elements.leftList then
		list = self.elements.rightList
		local var = self.variable.value
		var[text] = false
		self.variable.value = var
	else
		list = self.elements.leftList
		local var = self.variable.value
		var[text] = true
		self.variable.value = var
	end
	--- @cast list tes3uiElement

	-- create element
	list:createTextSelect{ id = itemID, text = text }:register(tes3.uiEvent.mouseClick, function(e)
		self:toggle(e)
	end)

	-- update sorting
	local container = list:getContentElement()
	container:sortChildren(function(a, b)
			return a.text < b.text
	end)

	-- update display
	self.elements.outerContainer:getTopLevelMenu():updateLayout()
end

--- @param listName mwseMCMExclusionsPageListId
function ExclusionsPage:updateSearch(listName)

	local searchString = self.elements.searchBarInput[listName].text:lower() --[[@as string]]
	local thisList = self.elements[listName] --[[@as tes3uiElement]]
	local child = thisList:findChild(itemID)

	if child then
		local itemList = child.parent.children
		for _, item in ipairs(itemList) do
			if item.text:lower():find(searchString, 1, true) then
				item.visible = true
			else
				item.visible = false
			end
		end
	end

	self.elements[listName].widget:contentsChanged()
	self.elements.outerContainer:getTopLevelMenu():updateLayout()
end

--- @param items string[]
function ExclusionsPage:distributeLeft(items)
	-- distribute items between blocked / allowed

	self.elements.leftList:getContentElement():destroyChildren()

	if self.showAllBlocked then
		-- show all items
		for name, blocked in pairs(self.variable.value) do
			if blocked then
				self.elements.leftList:createTextSelect{ id = itemID, text = name }:register(tes3.uiEvent.mouseClick, function(e)
					self:toggle(e)
				end)
			end
		end
	else
		for i, name in pairs(items) do
			if self.variable.value[name] then
				self.elements.leftList:createTextSelect{ id = itemID, text = name }:register(tes3.uiEvent.mouseClick, function(e)
					self:toggle(e)
				end)
			end
		end
	end
end

--- @param items string[]
function ExclusionsPage:distributeRight(items)
	-- distribute items between blocked / allowed

	self.elements.rightList:getContentElement():destroyChildren()
	for i, name in pairs(items) do
		if not self.variable.value[name] then
			self.elements.rightList:createTextSelect{ id = itemID, text = name }:register(tes3.uiEvent.mouseClick, function(e)
				self:toggle(e)
			end)
		end
	end
end

--- @param listName mwseMCMExclusionsPageListId
function ExclusionsPage:toggleFiltered(listName)
	-- Move all items currently filtered to opposite list

	local thisList = self.elements[listName] --[[@as tes3uiElement]]
	local child = thisList:findChild(itemID)

	if child then
		local itemList = child.parent.children
		for _, item in ipairs(itemList) do
			if item.visible then
				local list = item.parent.parent.parent
				if list == self.elements.leftList then
					list = self.elements.rightList
					local var = self.variable.value
					var[item.text] = false
					self.variable.value = var
				else
					list = self.elements.leftList
					local var = self.variable.value
					var[item.text] = true
					self.variable.value = var
				end
			end
		end
	end
	--destroy and recreate page
	self.elements.outerContainer.parent:destroyChildren()
	self:create(self.elements.outerContainer.parent)
end

''',
     '''function ExclusionsPage:toggle(e)
	-- toggle an item between blocked / allowed
	local text = e.source.text
	local list = e.source.parent.parent.parent
	local isLeft = (list == self.elements.leftList)

	local var = self.variable.value
	var[text] = not isLeft
	self.variable.value = var

	local items = self.currentItems or {}
	self:distributeLeft(items)
	self:distributeRight(items)

	-- update display
	local topMenu = self.elements.outerContainer and self.elements.outerContainer:getTopLevelMenu()
	if topMenu then
		topMenu:updateLayout()
	elseif self.elements.outerContainer then
		self.elements.outerContainer:updateLayout()
	end
end

--- @param listName mwseMCMExclusionsPageListId
function ExclusionsPage:updateSearch(listName)
	local items = self.currentItems or {}
	self.pages = self.pages or {}
	self.pages[listName] = 1
	if listName == "leftList" then
		self:distributeLeft(items)
	else
		self:distributeRight(items)
	end

	local topMenu = self.elements.outerContainer and self.elements.outerContainer:getTopLevelMenu()
	if topMenu then
		topMenu:updateLayout()
	elseif self.elements.outerContainer then
		self.elements.outerContainer:updateLayout()
	end
end

--- @param items string[]
function ExclusionsPage:distributeLeft(items)
	-- distribute items between blocked / allowed
	self.currentItems = items or self.currentItems or {}
	local content = self.elements.leftList:getContentElement()
	content:destroyChildren()

	local searchString = ""
	if self.elements.searchBarInput and self.elements.searchBarInput.leftList then
		local txt = self.elements.searchBarInput.leftList.text
		if txt and txt ~= placeholderText then
			searchString = txt:lower()
		end
	end

	local totalMatches = 0
	local sourceList = {}
	if self.showAllBlocked then
		for name, blocked in pairs(self.variable.value) do
			if blocked then
				sourceList[#sourceList + 1] = name
			end
		end
		table.sort(sourceList)
	else
		for _, name in ipairs(self.currentItems) do
			if self.variable.value[name] then
				sourceList[#sourceList + 1] = name
			end
		end
	end

	for _, name in ipairs(sourceList) do
		if searchString == "" or name:lower():find(searchString, 1, true) then
			totalMatches = totalMatches + 1
		end
	end
	local first, last = addPager(self, content, "leftList", totalMatches)
	local match = 0
	for _, name in ipairs(sourceList) do
		if searchString == "" or name:lower():find(searchString, 1, true) then
			match = match + 1
			if match >= first and match <= last then
				content:createTextSelect{ id = itemID, text = name }:register(tes3.uiEvent.mouseClick, function(e)
					self:toggle(e)
				end)
			end
		end
	end
	self.elements.leftList.widget:contentsChanged()
end

--- @param items string[]
function ExclusionsPage:distributeRight(items)
	-- distribute items between blocked / allowed
	self.currentItems = items or self.currentItems or {}
	local content = self.elements.rightList:getContentElement()
	content:destroyChildren()

	local searchString = ""
	if self.elements.searchBarInput and self.elements.searchBarInput.rightList then
		local txt = self.elements.searchBarInput.rightList.text
		if txt and txt ~= placeholderText then
			searchString = txt:lower()
		end
	end

	local totalMatches = 0
	for _, name in ipairs(self.currentItems) do
		if not self.variable.value[name] then
			if searchString == "" or name:lower():find(searchString, 1, true) then
				totalMatches = totalMatches + 1
			end
		end
	end
	local first, last = addPager(self, content, "rightList", totalMatches)
	local match = 0
	for _, name in ipairs(self.currentItems) do
		if not self.variable.value[name] then
			if searchString == "" or name:lower():find(searchString, 1, true) then
				match = match + 1
				if match >= first and match <= last then
					content:createTextSelect{ id = itemID, text = name }:register(tes3.uiEvent.mouseClick, function(e)
						self:toggle(e)
					end)
				end
			end
		end
	end
	self.elements.rightList.widget:contentsChanged()
end

--- @param listName mwseMCMExclusionsPageListId
function ExclusionsPage:toggleFiltered(listName)
	-- Move all items currently filtered to opposite list
	local searchString = ""
	if self.elements.searchBarInput and self.elements.searchBarInput[listName] then
		local txt = self.elements.searchBarInput[listName].text
		if txt and txt ~= placeholderText then
			searchString = txt:lower()
		end
	end

	local var = self.variable.value
	local items = self.currentItems or {}
	if listName == "leftList" then
		for _, name in ipairs(items) do
			if var[name] and (searchString == "" or name:lower():find(searchString, 1, true)) then
				var[name] = false
			end
		end
	else
		for _, name in ipairs(items) do
			if not var[name] and (searchString == "" or name:lower():find(searchString, 1, true)) then
				var[name] = true
			end
		end
	end
	self.variable.value = var

	self:distributeLeft(items)
	self:distributeRight(items)

	local topMenu = self.elements.outerContainer and self.elements.outerContainer:getTopLevelMenu()
	if topMenu then
		topMenu:updateLayout()
	elseif self.elements.outerContainer then
		self.elements.outerContainer:updateLayout()
	end
end

''', KB4),
    ("KB4", "MWSE Core", "core/mcm/components/pages/exclusionspage.lua",
     '\t\t\tself:clickFilter(button)\n\t\t\tself:distributeLeft(items)',
     '\t\t\tself:clickFilter(button)\n\t\t\tself.pages = {}\n\t\t\tself:distributeLeft(items)', KB4),
]


KNOWN_BUGS += [
    ("KB6", "OpenUI - MWSE", "spammer/openui - mwse/mod.lua",
     "        weacon.widget.current = weapon.itemData.condition\n        weacon.widget.max = weapon.object.maxCondition\n        if weapon.itemData then",
     "        weacon.widget.current = weapon.itemData and weapon.itemData.condition or weapon.object.maxCondition\n        weacon.widget.max = weapon.object.maxCondition\n        if weapon.itemData then",
     "the enchanted weapon HUD dereferences absent item data each frame; a weapon without instance data is at full condition"),
]


KNOWN_BUGS += [
    ("KB7", "Friends & Frens", "danae/frens/main.lua",
     '''    if e.newGame then
        randomiseCompanions()
    end
end

event.register("loaded", loaded)''',
     '''    if e.newGame then
        randomiseCompanions()
    end
end

-- local fix: %Sign is no dialogue variable; the sign is the companion's script local "birthsign" (1-13)
local birthsigns = { "Tower", "Ritual", "Steed", "Apprentice", "Mage", "Thief", "Lady", "Lover", "Shadow",
                     "Serpent", "Lord", "Warrior", "Atronach" }

local function nameBirthsign(e)
    local speaker = tes3ui.getServiceActor()
    local reference = speaker and speaker.reference
    local context = reference and reference.context
    local sign = context and context.birthsign
    if not sign then return end
    local text = e.text or e:loadOriginalText()
    if not text or not text:find("%Sign", 1, true) then return end
    local name = birthsigns[sign]
    if name then
        e.text = text:gsub("%%Sign", name)
    else
        e.text = text:gsub("the sign of the %%Sign", "a sign I never learned")
    end
end
event.register("infoGetText", nameBirthsign)

event.register("loaded", loaded)''',
     "the Abilities response prints '%Sign', which is no dialogue variable: each companion's sign is in the script "
     "local 'birthsign', which dialogue text cannot show, so it is filled in as the text is read"),
]


KB8 = ("detect invisibility reads actors' spell lists while a save is loading, when they can still hold the saved "
       "ids instead of spells (CS_Casimir1: 'unknown object type 0x736f6867', the text 'ghos'); it waits for loaded")
KNOWN_BUGS += [
    ("KB8", "Tamriel Data", "tamrieldata/magic.lua",
     '''local function detectInvisibilityValid(ref)
\tif ref == tes3.player or not ref.mobile then return false end
''',
     '''local function detectInvisibilityValid(ref)
\tif this.loadingInvisible then return false end\t-- local fix: spell lists are not resolved until a save has loaded
\tif ref == tes3.player or not ref.mobile then return false end
''', KB8),
    ("KB8", "Tamriel Data", "tamrieldata/magic.lua",
     '''function this.onInvisibilityEffectActivated(e)
\tif e.target and e.target ~= tes3.player and not invisibleReferences[e.target] then
\t\tif detectInvisibilityValid(e.target) then
''',
     '''function this.judgeLoadedInvisible()\t-- simulate too: a load can be cancelled
\tlocal waiting = this.loadingInvisible
\tif not waiting then return end
\tthis.loadingInvisible = nil
\tfor _, handle in ipairs(waiting) do
\t\tlocal ref = handle:valid() and handle:getObject()
\t\tif ref and detectInvisibilityValid(ref) then invisibleReferences[ref] = true end
\tend
end
event.register(tes3.event.load, function() this.loadingInvisible = {} end)
event.register(tes3.event.loaded, this.judgeLoadedInvisible)
event.register(tes3.event.simulate, this.judgeLoadedInvisible)

function this.onInvisibilityEffectActivated(e)
\tif e.target and e.target ~= tes3.player and not invisibleReferences[e.target] then
\t\tif this.loadingInvisible then
\t\t\ttable.insert(this.loadingInvisible, tes3.makeSafeObjectHandle(e.target))
\t\telseif detectInvisibilityValid(e.target) then
''', KB8),
]


KB9 = ("the interior sunray pass calls the engine's updateSun through FFI every frame without checking for a current "
       "weather; right after a new game is started from the game there is none yet, and the engine crashes "
       "(WeatherController::updateSun access violation, MWSE.log 2026-11-22)")
KNOWN_BUGS += [
    ("KB9", "Directional Sunrays", "directionalsunrays/main.lua",
     '''local function updateSun()
    local this = ffi.cast("void*", mwse.memory.addressOf(tes3.worldController.weatherController))
    TES3_WeatherController_updateSun(this, tes3.worldController.hour.value)''',
     '''local function updateSun()
    local weatherController = tes3.worldController.weatherController
    if not (weatherController and weatherController.currentWeather) then return false end\t-- local fix: no weather yet
    local this = ffi.cast("void*", mwse.memory.addressOf(weatherController))
    TES3_WeatherController_updateSun(this, tes3.worldController.hour.value); return true''', KB9),
    ("KB9", "Directional Sunrays", "directionalsunrays/main.lua",
     "\t\t\tupdateSun()\n\t\t\tlocal sunPosition",
     "\t\t\tif not updateSun() then return end\n\t\t\tlocal sunPosition", KB9),
]


KB10 = ("isBadWeather, findHat, and getHatFromWeather dereference weather.index / weather.name without checking "
        "for nil; right after starting a new game from inside a running game tes3.getCurrentWeather() is nil "
        "(MWSE.log 2026-11-24)")
KNOWN_BUGS += [
    ("KB10", "Robe'n'Hood", "robenhood/main.lua",
     "local function isBadWeather(weather)\n"
     "    weather = weather or tes3.getCurrentWeather()\n"
     "    local weatherIsBad = staticConfig.itemWeatherMap[weather.index] ~= nil",
     "local function isBadWeather(weather)\n"
     "    weather = weather or tes3.getCurrentWeather()\n"
     "    if not weather then return false end -- local fix: no current weather yet after in-game new game\n"
     "    local weatherIsBad = staticConfig.itemWeatherMap[weather.index] ~= nil", KB10),
    ("KB10", "Robe'n'Hood", "robenhood/main.lua",
     "local function getHatFromWeather(npc, weather)\n"
     '    logger:trace("Getting hat from weather")\n'
     "    local item",
     "local function getHatFromWeather(npc, weather)\n"
     "    if not weather then return nil end -- local fix: guard nil weather\n"
     '    logger:trace("Getting hat from weather")\n'
     "    local item", KB10),
    ("KB10", "Robe'n'Hood", "robenhood/main.lua",
     "local function findHat(npc, weather)\n"
     '    logger:debug("findHat: finding hat for %s in weather %s", npc, weather.name)',
     "local function findHat(npc, weather)\n"
     '    logger:debug("findHat: finding hat for %s in weather %s", npc, weather and weather.name or "nil")', KB10),
]


KB11 = ("util.isNiceWeather indexes currentWeather.index without a nil check (nil right after a new game is "
        "started inside a running game), and EffectManager caches activeEffects/nextUpdateTimestamp across saves "
        "without resetting on load (MWSE.log 2026-11-24)")
KNOWN_BUGS += [
    ("KB11", "Nocturnal Moths", "nocturnal moths/util/init.lua",
     "function util.isNiceWeather()\n"
     "\treturn niceWeather[tes3.worldController.weatherController.currentWeather.index] or false\n"
     "end",
     "function util.isNiceWeather()\n"
     "\tlocal weather = tes3.worldController.weatherController.currentWeather\n"
     "\treturn weather and niceWeather[weather.index] or false -- local fix: nil right after in-game new game\n"
     "end", KB11),
    ("KB11", "Nocturnal Moths", "nocturnal moths/effectmanager.lua",
     "\tself.__index = self\n"
     "\treturn t\n"
     "end\n\n\n"
     "-- Sets appCulled state of moths node on given reference.",
     "\tself.__index = self\n"
     "\treturn t\n"
     "end\n\n"
     "function EffectManager:reset()\n"
     "\tfor reference, _ in pairs(self.activeEffects) do\n"
     "\t\tpcall(util.stopSound, reference) -- local fix: stop moth loops before dropping refs on load\n"
     "\tend\n"
     "\tself.activeEffects = {}\n"
     "\tself.nextUpdateTimestamp = -1\n"
     "\tself.lastUpdateState = {}\n"
     "end\n\n"
     "-- Sets appCulled state of moths node on given reference.", KB11),   # reset() as KB14 leaves it: one pass
    ("KB11", "Nocturnal Moths", "nocturnal moths/main.lua",
     "event.register(tes3.event.cellChanged, onCellChanged)\n\n"
     "event.register(tes3.event.keyDown,",
     "event.register(tes3.event.cellChanged, onCellChanged)\n"
     "event.register(tes3.event.load, function() effectManager:reset() end) -- local fix: drop stale refs/timestamps on load\n\n"
     "event.register(tes3.event.keyDown,", KB11),
]


KB12 = ("changeStormOrigin writes `if weather and weather.index == ... or weather.index == ...` where Lua's `and` "
        "precedence leaves the `or` branch unguarded when weather is nil, and silenceCreatures indexes "
        "tes3.getCurrentWeather().index directly without a nil check (MWSE.log 2026-11-24)")
KNOWN_BUGS += [
    ("KB12", "Tamriel Data", "tamrieldata/weather.lua",
     "\tif weather and weather.index == tes3.weather.ash or weather.index == tes3.weather.blight then",
     "\tif weather and (weather.index == tes3.weather.ash or weather.index == tes3.weather.blight) then", KB12),
    ("KB12", "Tamriel Data", "tamrieldata/weather.lua",
     '\tif e.sound.id == "T_SndCrea_SeagullScream1" or e.sound.id == "T_SndCrea_SeagullScream2" or e.sound.id == "T_SndCrea_SeagullFlap" then\t-- Could also account for T_SndCrea_MastreeveMoan, T_SndCrea_MastreeveRoar, T_SndCrea_MastreeveScream?\n'
     "\t\tif tes3.getCurrentWeather().index == tes3.weather.ash then",
     '\tif e.sound.id == "T_SndCrea_SeagullScream1" or e.sound.id == "T_SndCrea_SeagullScream2" or e.sound.id == "T_SndCrea_SeagullFlap" then\t-- Could also account for T_SndCrea_MastreeveMoan, T_SndCrea_MastreeveRoar, T_SndCrea_MastreeveScream?\n'
     "\t\tlocal weather = tes3.getCurrentWeather()\n"
     "\t\tif weather and weather.index == tes3.weather.ash then", KB12),
]


KB13 = ("createElements registers destroy cleanup for iconFiltersBlock and buttonFiltersBlock but not for "
        "searchBlock (or filter.iconElement / filter.buttonElement), so menuEnter calls clearFilter() on destroyed "
        "tes3uiElement userdata after a new game or load (MWSE.log 2026-11-24)")
KNOWN_BUGS += [
    ("KB13", "UI Expansion", "ui expansion/common.lua",
     "\tself.searchBlock = common.createSearchBar(searchBarParams)\n\n"
     "\t-- Create icons for filtering.",
     "\tself.searchBlock = common.createSearchBar(searchBarParams)\n"
     '\tself.searchBlock.border:registerBefore("destroy", function()\n'
     "\t\tself.searchBlock = nil\n"
     "\tend)\n\n"
     "\t-- Create icons for filtering.", KB13),
    ("KB13", "UI Expansion", "ui expansion/common.lua",
     "\t\tself.iconFiltersBlock = block\n"
     '\t\tblock:registerBefore("destroy", function()\n'
     "\t\t\tself.iconFiltersBlock = nil\n"
     "\t\tend)",
     "\t\tself.iconFiltersBlock = block\n"
     '\t\tblock:registerBefore("destroy", function()\n'
     "\t\t\tself.iconFiltersBlock = nil\n"
     "\t\t\tfor _, filter in pairs(self.filtersOrdered) do\n"
     "\t\t\t\tfilter.iconElement = nil\n"
     "\t\t\tend\n"
     "\t\tend)", KB13),
    ("KB13", "UI Expansion", "ui expansion/common.lua",
     "\t\tself.buttonFiltersBlock = block\n"
     '\t\tblock:registerBefore("destroy", function()\n'
     "\t\t\tself.buttonFiltersBlock = nil\n"
     "\t\tend)",
     "\t\tself.buttonFiltersBlock = block\n"
     '\t\tblock:registerBefore("destroy", function()\n'
     "\t\t\tself.buttonFiltersBlock = nil\n"
     "\t\t\tfor _, filter in pairs(self.filtersOrdered) do\n"
     "\t\t\t\tfilter.buttonElement = nil\n"
     "\t\t\tend\n"
     "\t\tend)", KB13),
]

KB14 = ("util.playSound starts a looped R0_moths_fluttering without tes3.getSoundPlaying, and EffectManager:reset() "
        "(added by KB11) drops activeEffects without tes3.removeSound, so a load or in-game new game plus later "
        "uncull/cellChanged stacks another copy on each lantern (mwsoundguard.log 2026-11-24: dozens of duplicate "
        "R0_moths_fluttering starts)")
KNOWN_BUGS += [
    ("KB14", "Nocturnal Moths", "nocturnal moths/util/init.lua",
     "function util.playSound(reference)\n"
     "\tif not config.enableSound then return end\n"
     "\ttes3.playSound({\n"
     "\t\treference = reference,\n"
     "\t\tsound = sound,\n"
     "\t\tloop = true,\n"
     "\t\tvolume = config.soundVolume,\n"
     "\t})\n"
     "end",
     "function util.playSound(reference)\n"
     "\tif not config.enableSound then return end\n"
     "\tif not reference or reference.disabled or reference.deleted then return end\n"
     "\tif tes3.getSoundPlaying({ reference = reference, sound = sound }) then return end -- local fix: don't stack moth loops\n"
     "\ttes3.playSound({\n"
     "\t\treference = reference,\n"
     "\t\tsound = sound,\n"
     "\t\tloop = true,\n"
     "\t\tvolume = config.soundVolume,\n"
     "\t})\n"
     "end", KB14),
    ("KB14", "Nocturnal Moths", "nocturnal moths/effectmanager.lua",
     "function EffectManager:reset()\n"
     "\tself.activeEffects = {}\n"
     "\tself.nextUpdateTimestamp = -1\n"
     "\tself.lastUpdateState = {}\n"
     "end",
     "function EffectManager:reset()\n"
     "\tfor reference, _ in pairs(self.activeEffects) do\n"
     "\t\tpcall(util.stopSound, reference) -- local fix: stop moth loops before dropping refs on load\n"
     "\tend\n"
     "\tself.activeEffects = {}\n"
     "\tself.nextUpdateTimestamp = -1\n"
     "\tself.lastUpdateState = {}\n"
     "end", KB14),
]


KB15 = ("common.getTrackPlaying trusts tes3.getSoundPlaying, which the engine often answers as false for a "
        "still-playing 3D loop; AURA's 1s windoor/exterior-door timers then call play / playImmediate again "
        "(interiorToExterior, interiorWeather, outdoor, wind). mwsoundguard.log 2026-11-24: RUNAWAY IE_tav_imp_1 on "
        "Seyda Neen doors, plus S_q_4 and swa_d_3 one-shot/loop restarts on doors and windows")
KNOWN_BUGS += [
    ("KB15", "AURA", "tew/aura/common.lua",
     "function this.getTrackPlaying(track, ref)\n"
     "\tif track and ref and tes3.getSoundPlaying { sound = track, reference = ref } then\n"
     "\t\treturn track\n"
     "\tend\n"
     "end",
     "function this.getTrackPlaying(track, ref)\n"
     "\t-- local fix: tes3.getSoundPlaying often says a still-playing 3D loop is not playing,\n"
     "\t-- which made AURA's 1s door/window timers restart IE_tav / S_q_* / swa_* loops\n"
     "\tif track and ref then\n"
     "\t\treturn track\n"
     "\tend\n"
     "end", KB15),
]


KB16 = ("On cellChanged, Flies plays a looped 'Flies' sound on every qualifying corpse without tes3.getSoundPlaying "
        "or tes3.removeSound, and never stops the loop on referenceDeactivated or loaded. Re-entering the cell "
        "stacks copies. mwsoundguard cannot see this: it skips NPCs and creatures (mwsoundguard main.lua guard()) "
        "(found reading mwsoundguard.log 2026-11-24)")
KNOWN_BUGS += [
    ("KB16", "Flies", "spammer/flies/main.lua",
     "            and ref.data.spa_fliesCountDown < (tes3.getSimulationTimestamp() - 24) then\n"
     "            tes3.playSound { sound = \"Flies\", reference = ref, loop = true, volume = 0.5, pitch = 1.0 }\n"
     "        end",
     "            and ref.data.spa_fliesCountDown < (tes3.getSimulationTimestamp() - 24) then\n"
     "            -- local fix: don't stack loops on re-entry; soundguard skips NPC/creature sounds\n"
     "            if not (ref.data and ref.data.spa_Flies) and not tes3.getSoundPlaying { sound = \"Flies\", reference = ref } then\n"
     "                tes3.playSound { sound = \"Flies\", reference = ref, loop = true, volume = 0.5, pitch = 1.0 }\n"
     "            end\n"
     "        end", KB16),
    ("KB16", "Flies", "spammer/flies/main.lua",
     "    refDelete(e.cell)\n"
     "end)\n"
     "\n"
     "\n"
     "---@param e table|menuExitEventData\n"
     "event.register(\"menuExit\", function(e)\n"
     "    refDelete(tes3.player.cell)\n"
     "end)",
     "    refDelete(e.cell)\n"
     "end)\n"
     "\n"
     "event.register(\"referenceDeactivated\", function(e)\n"
     "    if e.reference then\n"
     "        tes3.removeSound { sound = \"Flies\", reference = e.reference } -- local fix: stop corpse fly loops when the ref unloads\n"
     "    end\n"
     "end)\n"
     "event.register(\"loaded\", function()\n"
     "    if tes3.player and tes3.player.cell then\n"
     "        for ref in tes3.player.cell:iterateReferences({ tes3.objectType.npc, tes3.objectType.creature }) do\n"
     "            tes3.removeSound { sound = \"Flies\", reference = ref }\n"
     "        end\n"
     "    end\n"
     "end)\n"
     "\n"
     "---@param e table|menuExitEventData\n"
     "event.register(\"menuExit\", function(e)\n"
     "    refDelete(tes3.player.cell)\n"
     "end)", KB16),
]


KB17 = ("addLevitation plays a looped 2D 'forcefield' without tes3.getSoundPlaying, and there is no loaded handler "
        "to clear the loop or the levitating flag after a load or in-game new game (found reading mwsoundguard.log "
        "2026-11-24)")
KNOWN_BUGS += [
    ("KB17", "Tel Raloran", "telraloran/levpad.lua",
     "    tes3.playSound{\n"
     "        sound = \"forcefield\",\n"
     "        loop = true,\n"
     "        pitch = 1.2\n"
     "    }",
     "    if not tes3.getSoundPlaying{ sound = \"forcefield\" } then -- local fix: don't stack the 2D loop\n"
     "        tes3.playSound{\n"
     "            sound = \"forcefield\",\n"
     "            loop = true,\n"
     "            pitch = 1.2\n"
     "        }\n"
     "    end", KB17),
    ("KB17", "Tel Raloran", "telraloran/levpad.lua",
     "event.register(\"simulate\", levitate)\n",
     "event.register(\"simulate\", levitate) -- local fix: also cleared on loaded\n"
     "event.register(\"loaded\", function() -- local fix: clear 2D forcefield loop and flag after load / in-game new game\n"
     "    levitating = false\n"
     "    timeEnteredPad = nil\n"
     "    tes3.removeSound{ sound = \"forcefield\" }\n"
     "end)\n", KB17),
]


KB19 = ("refreshCell matches an existing drip activator with a 0.01-unit position test, and on a miss it "
        "tes3.createReference a new furn_*_kegstand_dr then deletes the old one. The drip activator's own one-shot "
        "dripKeg sound starts again each time. cellActivated / the 3s puddle timer made mwsoundguard.log "
        "(2026-11-24) record up to 19 blocked dripKeg restarts on furn_com_kegstand_dr in a single summary window.")
KNOWN_BUGS += [
    ("KB19", "Keg Drip", "kegdrip/main.lua",
     "local function samePlacement(effect, keg)\n"
     "    return effect.position:distance(keg.position) < 0.01\n"
     "        and effect.orientation:distance(keg.orientation) < 0.001\n"
     "        and math.abs(effect.scale - keg.scale) < 0.001\n"
     "end",
     "local function samePlacement(effect, keg)\n"
     "    -- local fix: tight 0.01 matching was deleting and recreating the drip activator, restarting dripKeg\n"
     "    return effect.position:distance(keg.position) < 2.0\n"
     "        and effect.orientation:distance(keg.orientation) < 0.05\n"
     "        and math.abs(effect.scale - keg.scale) < 0.05\n"
     "end", KB19),
    ("KB19", "Keg Drip", "kegdrip/main.lua",
     "                if not effect then\n"
     "                    effect = tes3.createReference {\n"
     "                        object = definition.id,\n"
     "                        cell = cell,\n"
     "                        position = keg.position,\n"
     "                        orientation = keg.orientation,\n"
     "                        scale = keg.scale,\n"
     "                        updateCollisionGroups = false,\n"
     "                    }\n"
     "                    effect.modified = false\n"
     "                end",
     "                if not effect then\n"
     "                    -- local fix: recycle an unused drip of the same id instead of create+delete, which retriggers dripKeg\n"
     "                    for _, candidate in ipairs(effects) do\n"
     "                        if not used[candidate] and available(candidate)\n"
     "                            and candidate.object.id:lower() == definition.id then\n"
     "                            effect = candidate\n"
     "                            effect.position = keg.position\n"
     "                            effect.orientation = keg.orientation\n"
     "                            effect.scale = keg.scale\n"
     "                            break\n"
     "                        end\n"
     "                    end\n"
     "                end\n"
     "                if not effect then -- local fix: only create when no drip could be reused\n"
     "                    effect = tes3.createReference {\n"
     "                        object = definition.id,\n"
     "                        cell = cell,\n"
     "                        position = keg.position,\n"
     "                        orientation = keg.orientation,\n"
     "                        scale = keg.scale,\n"
     "                        updateCollisionGroups = false,\n"
     "                    }\n"
     "                    effect.modified = false\n"
     "                end", KB19),
    ("KB19", "Keg Drip", "kegdrip/main.lua",
     "        if not used[effect] then\n"
     "            effect:delete()\n"
     "            effect.modified = false\n"
     "        end",
     "        if not used[effect] then\n"
     "            tes3.removeSound({ reference = effect }) -- local fix: stop dripKeg before deleting a leftover drip\n"
     "            effect:delete()\n"
     "            effect.modified = false\n"
     "        end", KB19),
]


KB52 = ("Tamriel Data's Detect Invisibility opacity pass (detectInvisibilityOpacity, every simulate) walks the "
        "file-local tables invisibleReferences / invisibleOpacityModifiedReferences, which nothing empties on a "
        "load. A reference the engine freed in the game being left stays in the table, `actor.mobile` on it raises "
        "'sol: received nil for self argument', and the error ends the pass before the entry can go, so it repeats "
        "every frame (MWSE.log 2026-11-26: 1,876 errors at magic.lua:2127, about 20 a second, from one second "
        "after a load). The tables are emptied on load, and a reference whose mobile can't be read is dropped "
        "(no rule can express this: both tables are local upvalues of magic.lua that only code inside the module can "
        "empty or prune, and no general rule can know a local table keyed by references must be cleared on load; "
        "mwpluginpatches intercepts act on events and engine calls and cannot reach them)")
KNOWN_BUGS += [
    ("KB52", "Tamriel Data", "tamrieldata/magic.lua",
     "local invisibleReferences = {}\nlocal invisibleOpacityModifiedReferences = {}\n",
     "local invisibleReferences, invisibleOpacityModifiedReferences = {}, {}\n"
     "\n"
     "-- local fix (KB52): both tables hold references of the game being left; a stale one makes the opacity pass fail every frame\n"
     "local function readMobile(ref) return ref.mobile end\n"
     "event.register(tes3.event.load, function()\n"
     "\tfor ref in pairs(invisibleReferences) do invisibleReferences[ref] = nil end\n"
     "\tfor ref in pairs(invisibleOpacityModifiedReferences) do invisibleOpacityModifiedReferences[ref] = nil end\n"
     "end)\n", KB52),
    ("KB52", "Tamriel Data", "tamrieldata/magic.lua",
     "\t\tfor actor in pairs(invisibleReferences) do\n\t\t\t---@cast actor tes3reference\n",
     "\t\tfor actor in pairs(invisibleReferences) do\t-- local fix (KB52): drop a reference whose mobile can't be read, or it errors every frame\n"
     "\t\t\tif not pcall(readMobile, actor) then\n"
     "\t\t\t\tinvisibleReferences[actor] = nil\n"
     "\t\t\t\tinvisibleOpacityModifiedReferences[actor] = nil\n"
     "\t\t\tend\n"
     "\t\tend\n"
     "\n"
     "\t\tfor actor in pairs(invisibleReferences) do\t-- (KB52: the stale ones are gone)\n\t\t\t---@cast actor tes3reference\n", KB52),
]
KNOWN_BUGS_WHOLE |= {"KB52"}


# ---- Timer safe handles (KR), asked for site by site (2026-11-25). skipKnown (mwguard.json "luafix") turns one off.
# (KP1-KP4, the frame-drain patches, were removed on 2026-11-26: not bugs; mwpluginpatches has intercepts for KP1, KP2 and KP4.)
KR1 = ("the fade timers keep the sound's reference and call tes3.getSoundPlaying / tes3.removeSound on it for the "
       "whole fade; a reference deleted mid-fade now ends the fade as 'not playing' instead of being used")
KNOWN_BUGS += [
    ("KR1", "AURA", "tew/aura/fader.lua",
     "    local iterCount = 0\n"
     "\n"
     "    local function fader()\n",
     "    local iterCount = 0\n"
     "    local localpatch_handle = ref and tes3.makeSafeObjectHandle(ref) -- local fix (KR1): ref can go mid-fade\n"
     "\n"
     "    local function fader()\n", KR1),
    ("KR1", "AURA", "tew/aura/fader.lua",
     "(ref and not tes3.getSoundPlaying { sound = track, reference = ref }) then",
     "(ref and (not localpatch_handle:valid() or not tes3.getSoundPlaying { sound = track, reference = ref })) then",
     KR1),
    ("KR1", "AURA", "tew/aura/fader.lua",
     "            if (ref) and (fadeType == \"out\") and (removeTrack == true) then",
     "            if (ref) and localpatch_handle:valid() and (fadeType == \"out\") and (removeTrack == true) then", KR1),
]

KR2 = ("forceFollow's and travelThen's repeating timers read ref.mobile on the companion they started with every "
       "tick; one deleted meanwhile (a summoned or scripted companion) now just ends the job")
KNOWN_BUGS += [
    ("KR2", "Attend Me MWSE", "attendmemwse/actions.lua",
     "    local job = {}\n"
     "    local function tick()\n"
     "        ticks = ticks + 1\n"
     "        if not ref or not ref.mobile or ref.mobile.isDead then\n",
     "    local job = {}\n"
     "    local localpatch_handle = ref and tes3.makeSafeObjectHandle(ref) -- local fix (KR2): ref can go between ticks\n"
     "    local function tick()\n"
     "        ticks = ticks + 1\n"
     "        if not ref or not localpatch_handle:valid() or not ref.mobile or ref.mobile.isDead then\n", KR2),
    ("KR2", "Attend Me MWSE", "attendmemwse/actions.lua",
     "    local job = {}\n"
     "    job.timer = timer.start({\n"
     "        type = timer.simulate,\n"
     "        duration = tickInterval,\n"
     "        iterations = -1,\n"
     "        callback = function()\n"
     "            if not ref or not ref.mobile or ref.mobile.isDead then\n",
     "    local job = {}\n"
     "    local localpatch_handle = ref and tes3.makeSafeObjectHandle(ref) -- local fix (KR2): ref can go between ticks\n"
     "    job.timer = timer.start({\n"
     "        type = timer.simulate,\n"
     "        duration = tickInterval,\n"
     "        iterations = -1,\n"
     "        callback = function()\n"
     "            if not ref or not localpatch_handle:valid() or not ref.mobile or ref.mobile.isDead then\n", KR2),
]

KR3 = ("dismissCompanion's 3-second timer reads ref.mobile on the companion it started with (inside pcall, so a "
       "deleted one only raised a swallowed error); it now checks a safe handle first")
KNOWN_BUGS += [
    ("KR3", "Attend Me MWSE", "attendmemwse/recruit.lua",
     "    playRecallVisual(ref)\n"
     "    timer.start({\n"
     "        type = timer.simulate,\n"
     "        duration = 3.0,\n"
     "        iterations = 1,\n"
     "        callback = function()\n"
     "            if not ref then return end\n",
     "    playRecallVisual(ref)\n"
     "    local localpatch_handle = tes3.makeSafeObjectHandle(ref) -- local fix (KR3): ref can go before it fires\n"
     "    timer.start({\n"
     "        type = timer.simulate,\n"
     "        duration = 3.0,\n"
     "        iterations = 1,\n"
     "        callback = function()\n"
     "            if not ref or not localpatch_handle:valid() then return end\n", KR3),
]
KNOWN_BUGS_WHOLE |= {"KR1", "KR2"}

# KB23 and KB29 up: local hand repairs of third-party Lua (syntax, nil guards, handlers registered again on
# every load), kept as exact text so the mod can go back to its released files and still get them.
import mwdialog_luafix_kb as KBH                             # noqa: E402
KNOWN_BUGS += KBH.RULES
KNOWN_BUGS_WHOLE |= KBH.KB_WHOLE
KB_ROOTS = ("core/", "lib/")    # rule paths under MWSE itself (MWSE's core, shared libraries), not under MWSE\mods



def known_core_files(mwse_dir):
    """The MWSE core and lib files a Known Bugs rule names that exist under mwse_dir (a Data Files\\MWSE folder,
    or a mod's MWSE folder)."""
    rels = sorted({rel for _rule, _plugin, rel, _old, _new, _what in KNOWN_BUGS if rel.startswith(KB_ROOTS)})
    out = []
    for rel in rels:
        p = os.path.join(mwse_dir, *rel.split("/"))
        if os.path.isfile(p):
            out.append(p)
        else:                                       # the folder names on disk need not match the rule's case
            d, found = mwse_dir, True
            for part in rel.split("/"):
                hit = next((n for n in (os.listdir(d) if os.path.isdir(d) else []) if n.lower() == part), None)
                if hit is None:
                    found = False
                    break
                d = os.path.join(d, hit)
            if found and os.path.isfile(d):
                out.append(d)
    return out


def known_core_context(path):
    """Return an explicitly authorized core or lib file identity; every other MWSE core and lib file remains
    excluded. Such a file gets its Known Bugs repairs only."""
    norm = os.path.abspath(path).replace("\\", "/")
    low = norm.lower()
    for _rule, plugin, rel, _old, _new, _what in KNOWN_BUGS:
        if rel.startswith(KB_ROOTS) and low.endswith("/mwse/" + rel):
            return norm[:-(len(rel) + 1)], rel, plugin
    return None

GATE_HELPER = ("local localpatch_gate do local last, clock = {}, os.clock localpatch_gate = function(k, s) "
               "local t = clock() local l = last[k] if l and t >= l and t - l < s then return true end "
               "last[k] = t return false end end ")


def log_name(mod_key):
    return (re.sub(r"[^\w\- ]", ".", mod_key) or "mod").lower()


def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


SHIM_END = "--[[/localpatch_logshim]]"
# keepPatterns that mark a start-up line, not an error: "Registered recipe N" x500 must not flood MWSE.log.
# Not the bare substring "start": it also matches "Dialogue started with", "restart" and "AutoStartup".
LIFECYCLE_PATTERNS = frozenset({
    "initializ", "register", "loaded", "ready", "version", "active",
    "] started", "%f[%w]starting%f[%W]", "has started",
    "started successfully", "successfully started", "starting up",
})
# the version-1 shim (print / mwse.log only, no cap, no logger wrap): replaced by the current one on sight
SHIM_V1_RE = re.compile(r"local print, mwse = \(function\(_p, _m\) local fmt, find, lower, sub = string\.format, "
                        r"[^\n]*?\{ __index = _m, __newindex = _m \}\) end\)\(print, mwse\) ")
SHIM_V = 7
SHIM_RE = re.compile(r"local print, mwse, localpatch_log(?:, io)? = \(function\(_p, _m\).*?" +
                     re.escape(SHIM_END) + r" ")
LOG_SHIM_LUA = r"""
local print, mwse, localpatch_log, io = (function(_p, _m)
local S = package.loaded[@KEY@]
if type(S) == "table" and S.v == @V@ then return S.print, S.mwse, S, S.io end
S = { v = @V@, redirected = 0, dropped = 0, collapsed = 0 }
package.loaded[@KEY@] = S
local C = @CFG@
local G = _G
local find, lower, sub, gsub, concat, fmt, date, select, tostring, pcall = string.find, string.lower, string.sub, string.gsub, table.concat, string.format, os.date, select, tostring, pcall
local dir = "Data Files\\MWSE\\logs"
local path, oldPath = dir .. "\\" .. C.name .. ".log", dir .. "\\" .. C.name .. ".old.log"
local t0 = os.time() - math.floor(os.clock()) - 1
local init, run, started, redirected, f, dead, busy, fails = 0, 0, false, false, nil, false, false, 0
local bytes, dirty, last, lastN, sec, secN, dropped, errs, errKeys = 0, false, nil, 0, -1, 0, 0, {}, 0
local function compile(list)
local out = {}
for i = 1, #(list or {}) do
local p = list[i]
if type(p) == "string" and pcall(find, "", p) then out[#out + 1] = { p, not find(p, "[%^%$%(%)%%%.%[%]%*%+%-%?]") } end
end
return out
end
local KEEP, LIFE, lifeN = compile(C.keep), compile(C.life), {}
local function matches(l, list)
for i = 1, #list do
if find(l, list[i][1], 1, list[i][2]) then return i end
end
return nil
end
local function isErr(t)
local l = lower(#t > 4096 and sub(t, 1, 4096) or t)
if matches(l, KEEP) then return true end
local word = matches(sub(l, 1, 160), LIFE)
if not word then return false end
local n = lifeN[word] or 0
if n >= C.lifeMax then
if n == C.lifeMax then
lifeN[word] = n + 1
pcall(_p, fmt("[log redirect] %s: further '%s' lines only in %s", C.name, LIFE[word][1], path))
end
return false
end
lifeN[word] = n + 1
return "life"
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
local realIo = io
local function oldOf(p)
return sub(p, 1, -5) .. ".old.log"
end
local function stale(p)
local ok, m = pcall(function() return lfs.attributes(p, "modification") end)
return ok and type(m) == "number" and m < t0
end
local function setAside(p, o)
if C.keepOld > 0 then os.remove(o) os.rename(p, o) else os.remove(p) end
end
local function rotate()
if f then pcall(f.close, f) f = nil end
if C.keepOld > 0 then os.remove(oldPath) os.rename(path, oldPath) else os.remove(path) end
f = io.open(path, "w")
bytes, last = 0, nil
if f then
pcall(f.setvbuf, f, "full", 16384)
f:write(date("[%Y-%m-%d %H:%M:%S] "), C.name, " log\n")
end
return f
end
local function open()
pcall(function() lfs.mkdir(dir) end)
local ok, m = pcall(function() return lfs.attributes(path, "modification") end)
if ok and type(m) == "number" and m >= t0 then
path, oldPath = dir .. "\\" .. C.name .. ".routine.log", dir .. "\\" .. C.name .. ".routine.old.log"
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
local function startFlush()
if S.flushTimer then pcall(function() S.flushTimer:cancel() end) end
local ok, t = pcall(timer.start, { type = timer.real, duration = C.flushSeconds, iterations = -1, persist = false, callback = function() pcall(flushAll) end })
S.flushTimer = ok and t or nil
end
S.start = function()
if started then return end
started = true
if not f then
pcall(function()
for _, n in ipairs({ C.name, C.name .. ".routine" }) do
local p = dir .. "\\" .. n .. ".log"
if stale(p) then setAside(p, oldOf(p)) end
end
end)
end
pcall(flushAll)
startFlush()
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
if not f and not dead then open() end
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
if not f and not open() then
dead = true
_p(fmt("[log redirect] %s: %s can't be opened, logging here", C.name, path))
return true
end
end
if dead or not f then return true end
toFile(t)
return false
end
local function fail(e)
fails = fails + 1
if fails >= 10 then dead = true end
if fails == 1 then pcall(_p, fmt("[log redirect] %s: log write failed, logging here: %s", C.name, tostring(e))) end
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
S.fresh = {}
local function ownLog(p)
if type(p) ~= "string" then return nil end
local k = gsub(p, "/", "\\")
k = lower(k)
if sub(k, -4) == ".log" and sub(k, -8) ~= ".old.log" and find(k, "mwse\\logs\\", 1, true) then return k end
return nil
end
local function openOwn(p, mode, ...)
if type(mode) == "string" and sub(mode, 1, 1) == "a" then
local k = ownLog(p)
if k and not S.fresh[k] then
S.fresh[k] = true
local ok, old = pcall(stale, p)
if ok and old then
pcall(setAside, p, oldOf(p))
local ok2, h = pcall(realIo.open, p, "w" .. sub(mode, 2))
if ok2 and h then return h end
end
end
end
return realIo.open(p, mode, ...)
end
S.io = setmetatable({ open = openOwn }, { __index = realIo, __newindex = realIo })
S.flush = flushAll
S.stats = function() return { init = init, run = run, redirected = redirected, dead = dead, path = path, fails = fails, started = started } end
pcall(function()
event.register("initialized", S.start)
for _, ev in ipairs({ "save", "menuEnter" }) do event.register(ev, function() pcall(flushAll) end) end
event.register("loaded", function() pcall(flushAll) if started then startFlush() end end)
end)
pcall(function()
local p = newproxy(true)
getmetatable(p).__gc = function() pcall(flushAll) end
S.gc = p
end)
return S.print, S.mwse, S, S.io
end)(print, mwse) --[[/localpatch_logshim]]
"""


def log_shim(mod_key, cfg):
    """The log shim, on one line (so no line number moves): local print, mwse, localpatch_log and io for this file
    only (nothing global changes). The state lives in package.loaded, one per mod, built by whichever of the
    mod's files loads first. Like the old mwguard's log-spam guard: the first budgetInit lines (budget more after
    the initialized event), errors and the first few start-up lines of each kind reach MWSE.log, with no
    line of this tool's own; the rest go to
    Data Files\\MWSE\\logs\\<mod>.log (<mod>.routine.log when something else wrote that file this session),
    with identical lines collapsed, a per-second cap and rotation at maxMB. trace/debug/info of the mod's own
    loggers (wrapped where it creates them) are sent through the same route; warn/error are left alone.
    Fresh logs: every log is new in each game session, like MWSE.log. The shim's own log is set aside as
    <mod>.old.log (replacing an older one; with keepOld 0 it is deleted) the first time it is opened in a
    session, and a log from an earlier session that nothing wrote to this session is set aside when the
    initialized event fires. The shim's io.open does the same for a log the mod keeps itself: the first
    append-mode open of a *.log under MWSE\\logs\\ in a session starts the file new (the old one goes to
    <name>.old.log) unless it was already written this session; later opens append. Every
    file operation is pcall'd or returns nil; ten internal errors and it passes everything through."""
    lc = cfg["log"]
    keep = ", ".join(lua_str(p) for p in lc["keepPatterns"] if p not in LIFECYCLE_PATTERNS)
    life = ", ".join(lua_str("initiali" if p == "initializ" else p)          # also "initialised"
                     for p in lc["keepPatterns"] if p in LIFECYCLE_PATTERNS)
    conf = (f'{{ name = {lua_str(log_name(mod_key))}, init = {int(lc["budgetInit"])}, after = {int(lc["budget"])}, '
            f'keep = {{ {keep} }}, life = {{ {life} }}, lifeMax = {int(lc.get("lifecycleMax", 5))}, perSecond = {int(lc["perSecond"])}, maxBytes = {int(float(lc["maxMB"]) * 1048576)}, '
            f'keepOld = {int(lc["keepOld"])}, flushSeconds = {float(lc["flushSeconds"])}, '
            f'errorRepeat = {int(lc["errorRepeat"])} }}')
    body = " ".join(l for l in LOG_SHIM_LUA.split("\n") if l)
    return (body.replace("@KEY@", lua_str("localpatch_logshim:" + log_name(mod_key))).replace("@V@", str(SHIM_V))
            .replace("@CFG@", conf) + " ")


def _kb_rule(rule):
    return rule.startswith(("KB", "KR"))


def rules_before_kb(findings):
    """Known Bugs parts apply only where no rule matched: a part whose text a high-confidence rule edit also changes
    is dropped (the rule fixes it). A Known Bugs rule that applies whole (KNOWN_BUGS_WHOLE) can't lose one part, so
    there the rule's overlapping edits give way instead (reported). A medium rule edit overlapping a part that stays
    gives way too, so the result is the same at every --level."""
    kb = [f for f in findings if _kb_rule(f["rule"]) and any(x[0] != x[1] or x[2] for x in f["edits"])]
    if not kb:
        return findings
    rules = [f for f in findings if not _kb_rule(f["rule"]) and f["edits"] and f["conf"] in ("high", "medium")]

    def spans(f):
        return [(x[0], x[1]) for x in f["edits"]]

    def ov(s1, e1, s2, e2):                        # shared text, or an insert inside (or at the edge of) the other
        return max(s1, s2) < min(e1, e2) or s1 == e1 and s2 <= s1 <= e2 or s2 == e2 and s1 <= s2 <= e1

    def hits(a, b):
        return any(ov(s1, e1, s2, e2) for s1, e1 in spans(a) for s2, e2 in spans(b))
    drop, demote = set(), set()
    for k in kb:
        over = [r for r in rules if hits(k, r)]
        if not over:
            continue
        if k["rule"] in KNOWN_BUGS_WHOLE or not any(r["conf"] == "high" for r in over):
            demote |= {id(r) for r in over}
        else:
            drop.add(id(k))
            for r in over:
                r.setdefault("covers", []).append(k["rule"])
    out = []
    for f in findings:
        if id(f) in drop:
            continue
        if id(f) in demote:
            kbs = sorted({k["rule"] for k in kb if id(k) not in drop and hits(k, f)})
            f = Finding(f, conf="report", edits=[], needs=set(f["needs"]),
                        fix=f"{f['fix']} - not applied: Known Bugs {', '.join(kbs)} repairs this text")
        out.append(f)
    return out


def unbrand(src):
    """A file patched by version 4 or older, with this tool's name taken out of what was injected."""
    if "mwluafix" not in src and "mwdialog_luafix" not in src:
        return src
    return (src.replace("mwdialog_luafix", MARK).replace("-- mwluafix KB7:", "-- local fix:")
            .replace("mwluafix_", "localpatch_"))


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
    old = SHIM_RE.search(src) or SHIM_V1_RE.search(src)
    replacement = log_shim(mod_key, cfg)
    outdated = bool(old and old.group(0) != replacement)
    if want_shim and (old is None or outdated) or outdated:
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
    if old and "shim" in needs:                    # upgrade the embedded policy in place
        kept = [x for x in kept if x[0] >= old.end() or x[1] <= old.start()]
        kept.append((old.start(), old.end(), replacement))
        kept.sort(key=lambda x: (x[0], x[1]))
    for s, e, t in reversed(kept):
        out = out[:s] + t + out[e:]
    ip = insert_point(out)
    m = MARK_RE.match(out, ip)
    allr = sorted(set(m.group(2).split() if m else []) | set(rules))
    head = f"--[[{MARK} {VERSION}: {' '.join(allr)}]] "
    if "shim" in needs and old is None:
        head += replacement
    if "gate" in needs and "localpatch_gate = function" not in src:
        head += GATE_HELPER
    if "savestate" in needs and "localpatch_savestate" not in src:
        head += SAVE_HELPER
    out = out[:ip] + head + out[m.end() if m else ip:]
    return out, sorted(set(rules))


def remove_log_shim(src):
    """Remove our shim when a mod has its own logger; keep any other luafix marker rules."""
    old = SHIM_RE.search(src) or SHIM_V1_RE.search(src)
    if old is None:
        return None
    out = src[:old.start()] + src[old.end():]
    ip = insert_point(out)
    mark = MARK_RE.match(out, ip)
    if mark:
        rules = sorted(set(mark.group(2).split()) - {"F1"})
        head = f"--[[{MARK} {VERSION}: {' '.join(rules)}]] " if rules else ""
        out = out[:ip] + head + out[mark.end():]
    return out


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
OFF_SUFFIXES = (".disabled", ".mohidden", "-off", "_off", " off")    # "MWSE-off", "mods_off": switched off


def skipped_dir(parent, d):
    """A folder MWSE never loads Lua from: switched off (MWSE-off, .disabled, ...), extras / docs, or
    MWSE\backups (copies of mods set aside, e.g. by a suite relocation)."""
    lo = d.lower()
    return lo in SKIP_DIRS or lo.endswith(OFF_SUFFIXES) or (
        lo == "backups" and os.path.basename(os.path.normpath(parent)).lower() == "mwse")


def lua_files(root):
    if os.path.isfile(root):
        yield root
        return
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not skipped_dir(base, d))
        for fn in sorted(files):
            if fn.lower().endswith(".lua"):
                yield os.path.join(base, fn)


def generated(path):
    """Why a file is omw2mwse output, never patched here, --include-own or not (None: it is not). Recognised by
    the converter's markers (mwdialog_paths.omw_generated): its manifest, the generated loader's header or its
    use of omwcompat, and the omwcompat runtime in MWSE\\lib. The converter fixes these at the source."""
    why = MP.omw_generated(path)
    return f"{why}; the OpenMW converter fixes it at the source (re-run omw2mwse)" if why else None


def excluded(path, include_own=False, cfg=None):
    """Why a file is never touched (None: it may be)."""
    gen = generated(path)
    if gen:
        return gen
    parts = re.split(r"[\\/]+", os.path.abspath(path))
    for i, d in enumerate(parts[:-1]):
        lo = d.lower()
        if lo == "backups" and i and parts[i - 1].lower() == "mwse":
            return "a backup copy (MWSE\\backups): MWSE never loads it"
        if lo.endswith(OFF_SUFFIXES):
            return f"a switched-off folder ({d}): MWSE never loads it"
    mroot, rel = mods_root_of(path)
    if mroot is None:
        return ("MWSE's own code (not under MWSE\\mods)" if "/mwse/" in path.replace("\\", "/").lower()
                else "not under an MWSE\\mods folder")
    if os.path.basename(path).lower() == "initialize.lua":
        return "MWSE's own code"
    first = rel.split("/")[0].lower()
    if not include_own and first in own_mod_names(cfg):
        return "your own mod (--include-own checks it)"
    return None


def sha(b):
    return hashlib.sha1(b, usedforsecurity=False).hexdigest()


def write_in_place(path, data):
    """Rewrite the file through the same handle (r+b, then truncate): the file keeps its identity (deploy-time use,
    --core-only). Before deploy (a staged run, mwdialog_staged) a staged file is replaced by a new one instead, so
    a Vortex hard link into Data Files is broken, never written through, and a write into Data Files is refused."""
    if MS.active():
        MS.check_write(path)
        if MS.must_replace(path):
            MS.replace_bytes(path, data)               # writes, reads back, then replaces
            return
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


def known_text_repair(src, rel, cfg=None):
    """(text, findings): src with the Known Bugs rules for rel applied as plain text, for a file this tool's
    parser rejects (a rule can be what repairs the syntax). Rules in KNOWN_BUGS_WHOLE apply only when every part
    matches; skipKnown rules are left out. Each finding carries an empty edit, so the rule is recorded in the
    patch header while the text itself is already repaired."""
    rel = rel.lower()
    skip = set((cfg or {}).get("skipKnown") or ())
    groups = {}
    for rule, plugin, path, old, new, what in KNOWN_BUGS:
        if rel != path or rule in skip:
            continue
        if "\r\n" in src:
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        groups.setdefault(rule, []).append((plugin, old, new, what, src.count(old)))
    out, found = src, []
    for rule, got in groups.items():
        if rule in KNOWN_BUGS_WHOLE and not all(n for *_x, n in got):
            continue
        for plugin, old, new, what, n in got:
            if n:
                found.append(Finding(rule=rule, line=src.count("\n", 0, src.find(old)) + 1,
                                     what=f"{plugin}: {what}", fix=new, conf="high", edits=[(0, 0, "")],
                                     needs=set()))
                out = out.replace(old, new)
    return out, found


def syntax_text_repair(src, limit=50):
    """(text, findings) for a file the parser rejects because a table lists two literals with no comma between
    them on separate lines ("a"\n"b"): that never compiles, so a ',' goes after the first (Y1). Stops at the first
    error of any other kind; the findings carry an empty edit (the text is already repaired)."""
    out, found = src, []
    for _ in range(limit):
        try:
            L.parse(out)
            return out, found
        except L.LuaSyntaxError as e:
            if "'}' expected" not in str(e):
                break
            try:
                toks = L.tokenize(out)
            except L.LuaSyntaxError:
                break
            i = next((j for j, t in enumerate(toks) if t.s == e.pos), None)
            if not i or toks[i].t not in ("str", "num") or toks[i - 1].t not in ("str", "num") or \
                    toks[i - 1].line >= toks[i].line:
                break
            p = toks[i - 1].e
            found.append(Finding(rule="Y1", line=toks[i - 1].line, what=f"no ',' after {out[toks[i - 1].s:p][:40]} "
                                 f"in a table: the file doesn't compile, so it never loads", fix="the ',' is added",
                                 conf="high", edits=[(0, 0, "")], needs=set()))
            out = out[:p] + "," + out[p:]
    return src, []


def _analyse(src, key, rel, cfg):
    try:
        a = FileAnalysis(src, key, rel, cfg)
    except L.LuaSyntaxError:
        fixed, found = syntax_text_repair(src)           # rules first, then the exact Known Bugs repairs
        fixed, kfound = known_text_repair(fixed, rel, cfg)
        found += kfound
        if not found:
            raise
        a = FileAnalysis(fixed, key, rel, cfg)    # still raises when the repair is not enough
        a.run()
        a.findings += found
        return a
    a.run()
    return a


def log_exempt(cfg, key):
    low = key.lower()
    if low == "mwsuite" or low.startswith("mwsuite/"):
        return True
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
    ensure_own_mods(cfg, data_dir)
    by_mod, kb_only = {}, set()                     # kb_only: MWSE core/lib files, which get Known Bugs repairs only
    for root in paths:
        for p in lua_files(root):
            gen = generated(p)                        # converter output: not even Known Bugs repairs
            core = None if gen else known_core_context(p)
            why = gen or excluded(p, include_own, cfg)
            if why and not core:
                rep.skipped.append((p, why))
                continue
            if core:
                mroot, rel, key = core
                kb_only.add((mroot, key))
            else:
                mroot, rel = mods_root_of(p)
                key = mod_key_of(mroot, rel)
            by_mod.setdefault((mroot, key), []).append((p, rel))
    fix_conf = ("high",) if level == "high" else ("high", "medium")
    analyses = {}
    for (mroot, key), files in sorted(by_mod.items()):
        for p, rel in files:
            ent = {"rel": rel, "mod": key, "findings": [], "error": None, "patch": None, "logs": 0, "requires": [],
                   "mcalls": [], "mfields": None, "tstart": [], "treg": [], "loads": ([], [], []), "etrig": []}
            rep.files[p] = ent
            try:
                st = os.stat(p)
            except OSError as e:
                ent["error"] = str(e)
                continue
            ckey = "luafix1:" + os.path.normcase(os.path.abspath(p))
            if cache is not None and (mroot, key) not in kb_only:     # a cached finding has no edits to patch with
                hit = cache.get(ckey, ah.stamp_of(st))
                if hit is not None and hit.get("cfg") == ch and "mc" in hit and "ts" in hit and "ld" in hit and "ss" in hit:
                    ent.update(error=hit.get("err"), logs=hit.get("logs", 0), requires=hit.get("req", []),
                               loads=tuple(hit["ld"]), etrig=[(n, e) for n, e in hit.get("et", [])],
                               mcalls=[tuple(x) for x in hit["mc"]],
                               tstart=[tuple(x) for x in hit["ts"]], treg=list(hit.get("tr", [])),
                               mfields=set(hit["mf"]) if hit.get("mf") is not None else None,
                               sha=hit.get("sha"), cached=True, old_shim=hit.get("v1", False), branded=hit.get("br", False),
                               shim_state=hit["ss"],
                               findings=[Finding(f, edits=[], needs=set(f.get("needs", []))) for f in hit["f"]])
                    continue
            with open(p, "rb") as f:
                b = f.read()
            ent["sha"] = sha(b)
            try:
                raw = b.decode("latin-1")
                src = unbrand(raw)
                ent["branded"] = src != raw
                a = analyses[p] = _analyse(src, key, rel, cfg)
                tstart, treg = a.timer_names()
                ent.update(findings=a.findings, logs=a.log_calls(), requires=a.requires(), old_shim=a.old_shim,
                           shim_state=a.shim_state,
                           mcalls=a.module_calls(), mfields=a.module_fields(), tstart=tstart, treg=sorted(treg),
                           loads=a.load_refs(), etrig=a.event_triggers())
            except L.LuaSyntaxError as e:
                ent["error"] = f"can't be parsed ({e}); left alone"
            except RecursionError:
                ent["error"] = "too deeply nested to analyse; left alone"
            if cache is not None:
                cache.put(ckey, ah.stamp_of(st), {
                    "cfg": ch, "err": ent["error"], "logs": ent["logs"], "req": ent["requires"], "sha": ent["sha"],
                    "v1": ent.get("old_shim", False), "ss": ent.get("shim_state", "none"), "br": ent.get("branded", False),
                    "mc": ent["mcalls"],
                    "mf": sorted(ent["mfields"]) if ent["mfields"] is not None else None,
                    "ts": ent["tstart"], "tr": ent["treg"], "ld": list(ent["loads"]), "et": ent["etrig"],
                    "f": [dict({k: v for k, v in f.items() if k not in ("edits", "needs")}, needs=sorted(f["needs"]),
                               fixable=bool(f["edits"])) for f in ent["findings"]]})
    _mark_dead(rep, by_mod, paths, data_dir)
    for (mroot, key), files in sorted(by_mod.items()):
        if (mroot, key) in kb_only:
            for p, rel in files:
                ent = rep.files[p]
                ent["findings"] = [f for f in ent["findings"] if f["rule"].startswith("KB")]
                if ent["error"] or not any(f["edits"] and f["conf"] in fix_conf for f in ent["findings"]):
                    continue
                a = analyses[p]
                findings = [f for f in a.findings if f["rule"].startswith("KB")]
                new, rules = build_patch(a.src, findings, key, cfg, level, False)
                if new is not None:
                    ent["patch"] = verify_patch(a.src, new, rules, checker, key, rel, cfg, level,
                                                {f["rule"] for f in findings})
            continue
        _require_cycles(rep, files)
        _missing_fields(rep, files)
        _unregistered_timers(rep, files)
        loadlike = _load_like_events(rep, files)
        for p, _r in files:
            rep.files[p]["findings"] = _drop_load_like(rep.files[p]["findings"], loadlike)
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
            own_rules = set(OWN_FIX_RULES) if include_own and \
                key.split("/", 1)[0].lower() in own_mod_names(cfg) else None
            if log_exempt(cfg, key):
                with open(p, encoding="latin-1") as fh:
                    old_text = unbrand(fh.read())
                new_text = remove_log_shim(old_text)
                if new_text is not None:
                    ent["patch"] = verify_patch(old_text, new_text, ["F1"], checker, key, rel, cfg, level, own_rules)
                    continue
            want_shim = shim and ent["logs"] > 0 or bool(analyses.get(p) and analyses[p].old_shim) or \
                bool(ent.get("old_shim"))
            fixable = any((f["edits"] or f.get("fixable")) and f["conf"] in fix_conf and
                          (own_rules is None or f["rule"] in own_rules) for f in ent["findings"])
            if not (fixable or want_shim or ent.get("branded")):
                continue
            a = analyses.get(p)
            if a is None:                              # from the cache: read it again to build the patch
                with open(p, "rb") as fh:
                    b = fh.read()
                ent["sha"] = sha(b)
                try:
                    a = _analyse(unbrand(b.decode("latin-1")), key, rel, cfg)
                except (L.LuaSyntaxError, RecursionError) as e:
                    ent["error"] = f"can't be parsed ({e}); left alone"
                    continue
                # F1 is decided per mod above (shim or not, and the fix text naming the budgets, the log and why):
                # the fresh analysis only has the analyser's defaults ("log shim"), so each F1 finding takes the
                # decided conf and fix, and one the per-mod pass dropped (a logger without the shim) stays out.
                # Otherwise a cached file's plan line differs from an uncached one and --apply refuses the plan.
                old = {(f["rule"], f["line"], f["what"]): f for f in ent["findings"] if f["rule"] == "F1"}
                kept = []
                for f in a.findings:
                    if f["rule"] == "F1":
                        was = old.get((f["rule"], f["line"], f["what"]))
                        if was is None:
                            continue
                        f["conf"], f["fix"] = was["conf"], was["fix"]
                    kept.append(f)
                a.findings[:] = kept
                ent["findings"] = _drop_load_like(a.findings, loadlike) + [
                    f for f in ent["findings"] if f["rule"] in ("H5", "H7", "T1")]
            ent["findings"] = rules_before_kb(ent["findings"])
            findings = rules_before_kb(a.findings)
            if own_rules is not None:
                findings = [f for f in findings if f["rule"] in own_rules]
            new, rules = build_patch(a.src, findings, key, cfg, level, want_shim)
            if new is None and ent.get("branded"):
                new, rules = a.src, ["N1"]                # only the names left by an older version
            if new is not None:
                ent["patch"] = verify_patch(a.src, new, rules, checker, key, rel, cfg, level, own_rules)
        _settle_f1(rep, files)
    for ent in rep.files.values():                  # unreferenced files: report-only findings listed apart
        if ent.get("dead"):
            ent["dead_findings"] = [f for f in ent["findings"] if not (f["edits"] or f.get("fixable"))]
            ent["findings"] = [f for f in ent["findings"] if f["edits"] or f.get("fixable")]
    return rep


def _settle_f1(rep, files):
    """An F1 trigger the per-mod pass made "high" stays high only where the shim patch reaches it: its own file
    gets the shim patch, or the mod has a logger the patch wraps. "shimmed" where the current shim is already
    embedded (nothing to do). "report" where no patch can reach it (its lines go through a logger made somewhere
    the shim doesn't wrap: nothing is planned, so it is not a repair to count)."""
    ents = [rep.files[p] for p, _r in files]

    def planned(e):
        return bool(e.get("patch") and "F1" in e["patch"]["rules"])
    mod_logger = any(f["rule"] == "F1" and f["what"] == "logger created here" and f["conf"] == "high"
                     for e in ents for f in e["findings"])
    mod_shimmed = any(e.get("shim_state") == "current" for e in ents)
    for e in ents:
        for f in e["findings"]:
            if f["rule"] != "F1" or f["conf"] != "high" or f["edits"] or f.get("fixable"):
                continue                               # a "logger created here" has its own edit: it is patched
            if planned(e):
                continue
            if e.get("shim_state") == "current" or (mod_shimmed and not mod_logger):
                f["conf"], f["fix"] = "shimmed", f"already handled by the log shim (v{SHIM_V})"
            elif not mod_logger:
                f["conf"] = "report"
                f["fix"] = ("no repair planned: the log shim wraps print, mwse.log, mwse.Logger and logging.logger "
                            "calls, and this mod's lines go through something else")


def _load_like_events(rep, files):
    """Custom events that only ever fire from a loaded (or load) handler, directly or through another such event:
    a timer started in their handlers runs once per load, like one started in loaded (MWSE clears timers first).
    Bardic Inspiration's "BardicInspiration:DataLoaded" is one."""
    sites = {}
    for p, _r in files:
        for name, evs in rep.files[p].get("etrig") or ():
            sites.setdefault(name, []).append(evs)
    like, grew = set(), True
    while grew:
        grew = False
        for name, got in sites.items():
            if name not in like and all(evs and set(evs) <= {"loaded", "load"} | like for evs in got):
                like.add(name)
                grew = True
    return like


def _drop_load_like(findings, loadlike):
    ok = {"loaded", "load"} | set(loadlike)
    return [f for f in findings if not (f["rule"] == "H2" and f.get("events") and set(f["events"]) <= ok)]


ENTRY_FILES = {"main.lua", "mod_init.lua", "init.lua", "interop.lua"}
_EXTERNAL_REFS = {}


def _external_refs(data_dir):
    """Module names any Lua file under Data Files\\MWSE (mods and lib) quotes (cached per process): what other
    mods may load, when a check covers one staged mod at a time."""
    tops = [os.path.join(r, "MWSE") for r in MS.roots_of(data_dir)]      # staged: every staged mod and lua tools
    tops = [t for t in tops if os.path.isdir(t)]
    if not tops:
        return None
    stamp = tuple(os.stat(d).st_mtime_ns for t in tops for d in (t, os.path.join(t, "mods")) if os.path.isdir(d))
    key = (tuple(os.path.normcase(os.path.abspath(t)) for t in tops), stamp)   # a mod folder added or removed: read again
    if key not in _EXTERNAL_REFS:
        got = set()
        for base, dirs, files in (w for t in tops for w in os.walk(t)):
            dirs[:] = [d for d in dirs if not skipped_dir(base, d)]
            for fn in files:
                if fn.lower().endswith(".lua"):
                    try:
                        with open(os.path.join(base, fn), encoding="latin-1") as f:
                            text = f.read()
                    except OSError:
                        continue
                    got.update(module_name(m) for m in QUOTED_RE.findall(text))
        _EXTERNAL_REFS[key] = got
    return _EXTERNAL_REFS[key]


QUOTED_RE = re.compile(r"""["']([^"'\r\n]{1,200}?[./\\][^"'\r\n]{0,200}?)["']""")


def _mark_dead(rep, by_mod, paths, data_dir):
    """ent["dead"] for a file of a mod with a main.lua that no Lua names: no file of this check and no Lua file under
    Data Files\\MWSE requires it or quotes its module name, its folder or (in its own mod) its bare name, and its mod
    builds no require name at run time. Such a file is most likely never run (G7 Containers' backup.lua and
    notmain.lua), but it can still be loaded another way (an ESP's dialogue or script, another mod's folder scan),
    so it is checked and patched like any other; only its report-only findings are listed apart. Without a Data
    Files\\MWSE folder to read the other mods from, nothing is called unreferenced."""
    ext = _external_refs(data_dir)
    if ext is None:
        return                                        # what other mods load can't be told
    names, lits, prefixes_by_mod, prefixes, mod_lits = set(), set(), {}, set(), {}
    for (mroot, key), files in by_mod.items():
        for p, _rel in files:
            n, pre, li = rep.files[p].get("loads") or ([], [], [])
            names.update(n)
            lits.update(li)
            mod_lits.setdefault((mroot, key), set()).update(li)
            prefixes_by_mod.setdefault((mroot, key), set()).update(pre)
            prefixes.update(x for x in pre if x)
    refs = names | lits | ext
    for (mroot, key), files in by_mod.items():
        if not mroot or key == "MWSE Core" or "" in prefixes_by_mod.get((mroot, key), ()):
            continue
        if not any(os.path.isfile(os.path.join(mroot, *key.split("/"), e)) for e in ("main.lua", "mod_init.lua")):
            continue                                  # a library folder: others load it by name
        own = mod_lits.get((mroot, key), set())
        for p, rel in files:
            low = rel.lower()
            if os.path.basename(low) in ENTRY_FILES or "/i18n/" in "/" + low:
                continue
            m = module_name(rel)
            parts = m.split(".")
            if m in refs or (m.endswith(".init") and m[:-5] in refs) or parts[-1] in own:
                continue
            if any(".".join(parts[:k]) in refs for k in range(2, len(parts))):
                continue                              # its folder is named: scanned with lfs, most likely
            if any(m.startswith(x) for x in prefixes):
                continue
            rep.files[p]["dead"] = ("no Lua file requires or names it: unused, or loaded another way (an ESP's "
                                    "dialogue or script, another mod's folder scan)")


def verify_patch(old, new, rules, checker, key, rel, cfg, level, only_rules=None):
    """{"text", "rules", "ok", "why"}: the patched text parses, a second pass changes nothing more, and the
    syntax checker compiles it. Only exact Known Bugs fixes and Y1 (syntax that never compiles) may repair a
    non-compiling original: one must be among the rules (others may come with it, e.g. the log shim), and the patched
    text must compile."""
    res = {"text": new, "rules": rules, "ok": False, "why": ""}
    if checker is not None:
        ok, msg = checker.check(old)
        known_rules = {rule for rule, *_ in KNOWN_BUGS} | SYNTAX_RULES
        known_fix = any(rule in known_rules for rule in rules)
        if not ok and not known_fix:
            res["why"] = f"the original doesn't compile ({msg[:200]}); left alone"
            res["orig_bad"] = True
            return res
    try:
        b = _analyse(new, key, rel, cfg)
    except (L.LuaSyntaxError, RecursionError) as e:
        res["why"] = f"the patched text doesn't parse ({e}) - patch rejected"
        return res
    remaining = [f for f in b.findings if f["rule"] != "F1" and (only_rules is None or f["rule"] in only_rules)]
    again, _r = build_patch(new, remaining, key, cfg, level, False)
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


def _missing_fields(rep, files):
    """H7: X.f() through `local X = require("m")` where m is a file of the same mod whose returned table never
    gets f (seen 2026-11-18: AURA files still calling common.log after common.lua was restored without it)."""
    mod_of = {}
    for p, rel in files:
        name = rel[:-4].replace("/", ".").lower()
        mod_of[name] = p
        if name.endswith(".init"):
            mod_of[name[:-5]] = p
    added = {(m.lower(), f) for p, _r in files for m, f, ln in rep.files[p].get("mcalls") or () if ln == 0}
    for p, _rel in files:
        ent = rep.files[p]
        if ent["error"]:
            continue
        for mod, field, line in ent.get("mcalls") or ():
            q = mod_of.get(mod.lower())
            have = rep.files[q].get("mfields") if q and not rep.files[q]["error"] else None
            if line and have is not None and field not in have and (mod.lower(), field) not in added:
                ent["findings"].append(Finding(
                    rule="H7", line=line, what=f"calls {field}() from {rep.files[q]['rel']}, which never defines it "
                                               f"(errors when this line runs)",
                    fix="put both files back from the same release (one restored, one still edited?)",
                    conf="report", edits=[], needs=set()))


def _unregistered_timers(rep, files):
    """T1: timer.start{ callback = "name" } where no file of the mod calls timer.register("name", ...): the timer
    errors when it fires (and after a load). MWSE's docs: a named callback must be timer.register'ed."""
    registered = {n for p, _r in files for n in rep.files[p].get("treg") or ()}
    for p, _rel in files:
        ent = rep.files[p]
        if ent["error"]:
            continue
        for name, line in ent.get("tstart") or ():
            if name and name not in registered:
                ent["findings"].append(Finding(
                    rule="T1", line=line, what=f'timer.start with callback "{name}", which this mod never '
                                               f'timer.register()s (errors when the timer fires)',
                    fix=f'timer.register("{name}", fn) at file load, or pass the function itself',
                    conf="report", edits=[], needs=set()))


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


def apply_report(rep, journal=JOURNAL, backup_root=BACKUP_ROOT, head_extra=None, log=print, bdir=None, done=None,
                 *, backup_relative_to=None):
    """Write every verified patch in place, after copying the file to backup_root\\<run>\\ (or bdir). Every write
    is journaled first; backup_relative_to keeps package-local backups free of host paths. done (a list) gets each
    path as it is written, so an interrupted run knows what is left.
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
                if backup_relative_to:
                    relative = os.path.relpath(p, backup_relative_to)
                    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
                        refused.append((p, f"outside backup-relative root {backup_relative_to}"))
                        continue
                    bpath = os.path.join(bdir, relative)
                else:
                    drive, tail = os.path.splitdrive(os.path.abspath(p))
                    bpath = os.path.join(bdir, drive.rstrip(":\\/") or "root", tail.lstrip("\\/"))
                os.makedirs(os.path.dirname(bpath), exist_ok=True)
                with open(bpath, "wb") as f:
                    f.write(b)
                    f.flush()
                    os.fsync(f.fileno())                # the backup and its journal line are on disk before
                new = e["patch"]["text"].encode("latin-1")   # the original changes: --undo always has both
                j.write(json.dumps({"luafix": p, "backup": bpath, "before": sha(b), "after": sha(new),
                                    "rules": e["patch"]["rules"]}) + "\n")
                j.flush()
                os.fsync(j.fileno())
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
            try:
                rec = json.loads(line)
            except ValueError:                        # a line cut short when an --apply was interrupted
                print(f"  (skipped an unreadable journal line: {line[:80]!r})", file=sys.stderr)
                continue
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
CONF_ORDER = {"high": 0, "report-high": 1, "medium": 2, "report": 3, "trigger": 4, "covered": 5, "shimmed": 5, "info": 6}


KNOWN_LABELS = {"KB": "(Known Bugs)", "KR": "(Ref Safety)"}


def known_label(rule):
    """The label of a targeted patch rule (KB: a known bug; KP: a frame-drain fix asked for site by site; KR: a
    safe handle for a reference a timer keeps), or None for the generic rules."""
    return KNOWN_LABELS.get(rule[:2]) if re.match(r"K[BPR]\d", rule) else None


def finding_status(f, pt, written):
    """After --apply: PATCHED (fixed in the written file), NOT PATCHED (had a fix, the file was not written),
    UNCONFIGURED (should be fixed, no fix exists for it), REPORTED (report only)."""
    if f["conf"] == "shimmed":
        return "SHIMMED"
    if f["fix"]:
        return "PATCHED" if written and pt and pt["ok"] and f["rule"] in pt["rules"] else "NOT PATCHED"
    return "UNCONFIGURED" if f["conf"] in ("high", "medium") else "REPORTED"


def format_report(rep, show_info=False, indent="  ", done=None, refused=None):
    """The report lines. With done (paths written by apply_report) each finding is prefixed with its status and
    the file's last line says PATCHED or NOT PATCHED (refused: {path: why})."""
    if done is not None:
        return _format_applied(rep, show_info, indent, set(done), refused or {})
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
            label = f"{known_label(f['rule'])} {f['rule']}:" if known_label(f["rule"]) else f"{f['rule']} {f['conf']:<11}"
            lines.append(f"{indent}    {label} line {f['line']}: {f['what']}"
                         + (f"  -> {f['fix']}" if f["fix"] else ""))
        pt = e.get("patch")
        if pt:
            lines.append(f"{indent}    => " + (f"patch ready ({', '.join(pt['rules'])}) "
                                               f"[{sha(pt['text'].encode('latin-1'))[:8]}]" if pt["ok"]
                                               else f"NOT patched: {pt['why']}"))
    lines += dead_lines(rep, indent)
    return lines, counts


def dead_lines(rep, indent="  "):
    """Unreferenced files: one line each, with the report-only findings set aside from the plan and the counts."""
    out = []
    for e in sorted((e for e in rep.files.values() if e.get("dead")), key=lambda e: e["rel"].lower()):
        fs = e.get("dead_findings") or []
        rules = ", ".join(sorted({f["rule"] for f in fs}))
        out.append(f"{indent}unreferenced {e['rel']}: {len(fs)} report-only finding(s) set aside"
                   + (f" ({rules})" if rules else "") + f"; {e['dead']}")
    return out


def _format_applied(rep, show_info, indent, done, refused):
    lines, counts = [], {}
    for p, e in sorted(rep.files.items(), key=lambda x: (x[1]["mod"].lower(), x[1]["rel"].lower())):
        for f in e["findings"]:
            counts[(f["rule"], f["conf"])] = counts.get((f["rule"], f["conf"]), 0) + 1
        fs = [f for f in e["findings"] if show_info or f["conf"] not in ("info",)]
        pt = e.get("patch")
        if not fs and not e["error"] and not pt:
            continue
        lines.append(f"{indent}lua {e['rel']}")
        if e["error"]:
            lines.append(f"{indent}    ! {e['error']}")
        for f in sorted(fs, key=lambda f: (CONF_ORDER.get(f["conf"], 9), f["line"])):
            label = f"{known_label(f['rule'])} {f['rule']}:" if known_label(f["rule"]) else f"{f['rule']}"
            lines.append(f"{indent}    {finding_status(f, pt, p in done)}: {label} line {f['line']}: {f['what']}"
                         + (f"  -> {f['fix']}" if f["fix"] else ""))
        if pt:
            why = refused.get(p) or (None if pt["ok"] else pt["why"]) or "not written"
            lines.append(f"{indent}    => " + (f"PATCHED ({', '.join(pt['rules'])}) [{sha(pt['text'].encode('latin-1'))[:8]}]"
                                               if p in done else f"NOT PATCHED: {why}"))
    lines += dead_lines(rep, indent)
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


def known_bug_report_lines(rep, done=None, refused=None):
    """Stable author-facing lines for exact KB findings; unlike the plan, these survive an apply."""
    done, refused = None if done is None else set(done), refused or {}
    out = []
    for p, ent in sorted(rep.files.items(), key=lambda x: x[1]["rel"].lower()):
        pt = ent.get("patch")
        for f in sorted((x for x in ent["findings"] if x["rule"].startswith("KB")), key=lambda x: x["line"]):
            status = "DETECTED" if done is None else finding_status(f, pt, p in done)
            if p in refused:
                status = "NOT PATCHED"
            out.append(f"{status}: (Known Bugs) {f['rule']}: {f['what']} [{ent['rel']}:{f['line']}]")
    return out


def write_known_bug_report(rep, done=None, refused=None, path=None):
    path = path or KNOWN_BUG_REPORT
    lines = known_bug_report_lines(rep, done, refused)
    body = [f"luafix known-bug report, {PF.stamp()}",
            "Exact source fingerprints only; general MWSE Core scanning remains disabled.", ""]
    body += lines or ["No vulnerable known-bug fingerprints detected."]
    PF.write_atomic(path, "\n".join(body) + "\n")
    return path


# ---------------------------------------------------------------------------------------------- core-only
# A small entry point for callers that only want MWSE's own core files repaired (MWManager, after MWSE-Update.exe):
# the files a KNOWN_BUGS rule names under core/ (KB3 and KB4 on exclusionspage.lua today), nothing else.
CORE_STATUSES = ("applied", "already-patched", "no-match", "partial", "refused")
CORE_EXIT_OK, CORE_EXIT_LOCKED, CORE_EXIT_REFUSED, CORE_EXIT_PARTIAL, CORE_EXIT_USAGE = 0, 1, 2, 3, 4
_AUTO = object()


@dataclasses.dataclass
class CoreResult:
    """What core-only found for one core file. status is one of CORE_STATUSES:
    applied (patched; with dry_run, would be), already-patched (our header present, no fingerprint left),
    no-match (no fingerprint, no header: upstream fixed it or changed it), partial (a rule whose parts must all match
    matches only some: nothing written), refused (the reason says why; nothing written)."""
    path: str
    rel: str
    kb_ids: list
    status: str
    parts_matched: int = 0
    parts_total: int = 0
    reason: str = ""
    journal_entry: Optional[str] = None
    dry_run: bool = False
    written: bool = False
    backup: Optional[str] = None
    sha1_before: Optional[str] = None
    sha1_after: Optional[str] = None
    kbs: list = dataclasses.field(default_factory=list)

    def to_dict(self):
        return dataclasses.asdict(self)


def _kb_order(rule):
    return (int(re.sub(r"\D", "", rule) or 0), rule)


def core_rels():
    """The core/ paths (lower case, as in KNOWN_BUGS) a Known Bugs rule names."""
    return sorted({rel for _rule, _plugin, rel, _old, _new, _what in KNOWN_BUGS if rel.startswith("core/")})


def _child_ci(folder, name):
    try:
        return next((os.path.join(folder, n) for n in os.listdir(folder) if n.lower() == name.lower()), None)
    except OSError:
        return None


def core_data_dir(path):
    """(game folder, Data Files folder) for a path that is either the Morrowind folder or its Data Files folder.
    ValueError when it is neither."""
    path = os.path.abspath(path)
    if os.path.basename(path).lower() == "data files" and os.path.isdir(path):
        return os.path.dirname(path), path
    sub = _child_ci(path, "Data Files")
    if sub and os.path.isdir(sub):
        return path, sub
    if os.path.isdir(path) and _child_ci(path, "MWSE"):
        return os.path.dirname(path), path
    raise ValueError(f"{path}: not a Morrowind folder or a Data Files folder")


def _core_parts(src, rel, skip=()):
    """{rule: (parts that match, parts)} for each KNOWN_BUGS rule on rel, counted as FileAnalysis.r_known does."""
    crlf = "\r\n" in src
    out = {}
    for rule, _plugin, path, old, _new, _what in KNOWN_BUGS:
        if path != rel or rule in skip:
            continue
        if crlf:
            old = old.replace("\n", "\r\n")
        m, n = out.get(rule, (0, 0))
        out[rule] = (m + (1 if old in src else 0), n + 1)
    return out


def _banner_rules(src):
    """The rule names in this tool's header at the top of the file (empty: no header)."""
    m = MARK_RE.match(src, insert_point(src))
    return set(m.group(2).split()) if m else set()


def apply_core_known_bugs(data_dir, dry_run=False, *, game_dir=None, cfg=None, checker=_AUTO, no_syntax_check=False,
                          journal=None, backup_root=None):
    """Check, and unless dry_run patch in place, only the MWSE core files a Known Bugs rule names, under
    data_dir (the Data Files folder; core_data_dir() finds it from the game folder). No other file is read for
    patching and nothing is planned: a file is written the way --apply writes it (backed up first, journaled,
    refused when it changed after it was checked, only when the syntax checker accepts the patched text), so
    --undo puts the run back. Without a checker (no LuaJIT/luac/lupa and no_syntax_check) a patch is refused.
    Returns a list of CoreResult, one per core file a rule names (a missing file is a refused one)."""
    data_dir = os.path.abspath(data_dir)
    game_dir = game_dir or HERE
    journal = journal or JOURNAL
    backup_root = backup_root or BACKUP_ROOT
    cfg = cfg if cfg is not None else load_config(game_dir, data_dir)
    if checker is _AUTO:
        checker = None if no_syntax_check else find_checker(None, game_dir)
    elif no_syntax_check:
        checker = None
    skip = set(cfg.get("skipKnown") or ())
    mwse = _child_ci(data_dir, "MWSE") or os.path.join(data_dir, "MWSE")
    found = {}
    for p in known_core_files(mwse):
        ctx = known_core_context(p)
        if ctx:
            found[ctx[1]] = p
    results = []

    def kb_ids_of(rel):
        return sorted({r for r, _pl, path, _o, _n, _w in KNOWN_BUGS if path == rel}, key=_kb_order)

    for rel in core_rels():
        if rel not in found:
            results.append(CoreResult(path=os.path.join(mwse, *rel.split("/")), rel=rel, kb_ids=kb_ids_of(rel),
                                      status="refused", dry_run=dry_run,
                                      reason="the core file was not found (is MWSE installed here?)"))
    rep = check_paths([found[r] for r in sorted(found)], cfg, False, checker, "high", None, use_cache=False,
                      game_dir=game_dir) if found else Report()
    pending, by_path = [], {}
    for rel in sorted(found):
        p = found[rel]
        ent = rep.files.get(p) or {"error": "not checked", "patch": None}
        res = CoreResult(path=p, rel=rel, kb_ids=kb_ids_of(rel), status="refused", dry_run=dry_run,
                         sha1_before=ent.get("sha"))
        by_path[p] = res
        results.append(res)
        try:
            with open(p, "rb") as f:
                src = unbrand(f.read().decode("latin-1"))
        except OSError as e:
            res.reason = str(e)
            continue
        parts = _core_parts(src, rel, skip)
        banner = _banner_rules(src)
        res.parts_matched = sum(m for m, _n in parts.values())
        res.parts_total = sum(n for _m, n in parts.values())
        partial = []
        for rule in res.kb_ids:
            m, n = parts.get(rule, (0, 0))
            if rule in skip:
                state = "skipped"
            elif rule in KNOWN_BUGS_WHOLE and 0 < m < n:
                state = "partial"
                partial.append(f"{rule}: only {m} of its {n} parts match")
            elif m:
                state = "matches"
            else:
                state = "already-patched" if rule in banner else "no-match"
            res.kbs.append({"kb": rule, "state": state, "parts_matched": m, "parts_total": n})
        patch = ent.get("patch")
        if ent.get("error"):
            res.reason = ent["error"]
        elif partial:
            res.status = "partial"
            res.reason = ("; ".join(partial) + ": this file is neither the version the fix was written for nor "
                          "the fixed one, so nothing was written")
            ent["patch"] = None                    # no part of a file that does not match whole is written
        elif patch and not patch["ok"]:
            res.reason = patch["why"] or "the patch was rejected"
            ent["patch"] = None
        elif patch:
            res.sha1_after = sha(patch["text"].encode("latin-1"))
            if checker is None and not no_syntax_check:
                res.reason = ("no LuaJIT/luac found (" + MP.describe_luajit_search(game_dir) + "); not patching "
                              "without a syntax check (--luajit, or --no-syntax-check)")
                res.sha1_after = None
                ent["patch"] = None
            else:
                res.status = "applied"
                res.reason = ("would patch " if dry_run else "patched ") + ", ".join(patch["rules"])
                pending.append(p)
        elif res.parts_matched:
            res.reason = "a fingerprint matches but no patch was built"
        elif any(r in banner for r in res.kb_ids):
            res.status = "already-patched"
            res.reason = "this tool's header is there and no fingerprint is left"
        else:
            res.status = "no-match"
            res.reason = "no fingerprint matches and there is no header: MWSE fixed or changed this file"
    if pending and not dry_run:
        bdir = run_backup_dir(backup_root)
        entry = os.path.basename(bdir)
        done = []
        _w, refused = apply_report(rep, journal=journal, backup_root=backup_root, bdir=bdir, done=done,
                                   head_extra={"core_only": True, "entry": entry}, log=lambda s: None)
        why = dict(refused)
        backups = {}
        try:
            runs = _read_runs(journal)
            if runs and runs[-1]["head"].get("entry") == entry:
                backups = {op["luafix"]: op["backup"] for op in runs[-1]["ops"]}
        except OSError:
            pass
        for p in pending:
            res = by_path[p]
            if p in done:
                res.written, res.journal_entry, res.backup = True, entry, backups.get(p)
            else:
                res.status, res.sha1_after = "refused", None
                res.reason = why.get(p) or "not written"
    return sorted(results, key=lambda r: r.rel)


def core_exit_code(results):
    """CORE_EXIT_REFUSED when any file was refused, else CORE_EXIT_PARTIAL when any was partial, else 0."""
    states = {r.status for r in results}
    return CORE_EXIT_REFUSED if "refused" in states else CORE_EXIT_PARTIAL if "partial" in states else CORE_EXIT_OK


def core_result_json(results, data_dir, dry_run, journal=None):
    counts = {s: sum(1 for r in results if r.status == s) for s in CORE_STATUSES}
    return {"tool": "mwdialog_luafix", "mode": "core-only", "version": VERSION, "dry_run": bool(dry_run),
            "data_dir": os.path.abspath(data_dir), "journal": journal or JOURNAL, "exit_code": core_exit_code(results),
            "counts": counts, "files": [r.to_dict() for r in results]}


def core_result_lines(results, dry_run):
    out = [f"mwdialog_luafix --core-only{' --dry-run' if dry_run else ''}: {len(results)} MWSE core file(s)"]
    for r in results:
        out.append(f"  {r.status.upper()}: {r.rel} ({' '.join(r.kb_ids)}; parts {r.parts_matched}/{r.parts_total})")
        out.append(f"      {r.reason}")
        if r.written:
            out.append(f"      journal entry {r.journal_entry}; backup {r.backup}")
    out.append("Nothing changed (dry run)." if dry_run else "--undo puts back what was written.")
    return out


def _raw_stdout():
    s = sys.stdout
    while hasattr(s, "_inner"):                    # MT.install()'s wrapper would wrap JSON lines
        s.flush()
        s = s._inner
    return s


def _core_only_main(args, ap):
    for flag in ("apply", "yes", "undo", "diff", "include_own"):
        if getattr(args, flag):
            ap.error(f"--core-only does not combine with --{flag.replace('_', '-')} (it applies by itself; "
                     "--dry-run only checks; --undo puts back the last run)")
    if len(args.paths) > 1:
        ap.error("--core-only takes one folder: the Morrowind folder or its Data Files folder")
    to_stdout = args.json == "-"
    log = sys.stderr if to_stdout else sys.stdout
    try:
        game_dir, data_dir = core_data_dir(args.paths[0] if args.paths else os.path.join(HERE, "Data Files"))
    except ValueError as e:
        print(f"{e}", file=sys.stderr)
        return CORE_EXIT_USAGE
    if not args.dry_run and (not MP.acquire_run_lock() or not MP.acquire_game_lock(game_dir)):
        print(MP.RUN_LOCKED_MESSAGE, file=sys.stderr)
        return CORE_EXIT_LOCKED
    checker = None if args.no_syntax_check else find_checker(args.luajit, game_dir)
    results = apply_core_known_bugs(data_dir, args.dry_run, game_dir=game_dir, checker=checker,
                                    no_syntax_check=args.no_syntax_check)
    for line in core_result_lines(results, args.dry_run):
        print(line, file=log)
    doc = core_result_json(results, data_dir, args.dry_run)
    if to_stdout:
        out = _raw_stdout()
        out.write(json.dumps(doc, indent=1) + "\n")
        out.flush()
    elif args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1)
    return doc["exit_code"]

# ---------------------------------------------------------------------------------------------- CLI
def main(argv=None):
    MT.install()
    ap = MT.parser(description="Check MWSE Lua mods for bad habits and patch the safe ones.")
    ap.add_argument("paths", nargs="*", help="staged mod folders or files (default: every staged mod with an MWSE "
                                             "folder; Data Files is never checked or patched before deploy)")
    ap.add_argument("--staging", help="the staging folder (Vortex's or MWManager's; default: from Vortex's settings)")
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
    ap.add_argument("--json", help="also write the findings as JSON to this file (with --core-only: the result; - "
                                   "prints it to stdout and the summary goes to stderr)")
    ap.add_argument("--diff", action="store_true", help="show each patch as a diff")
    ap.add_argument("--core-only", action="store_true",
                    help="check and patch only the MWSE core files a Known Bugs rule names (KB3, KB4: Data Files\\"
                         "MWSE\\core\\...\\ExclusionsPage.lua), at once, with no plan: one folder (the Morrowind "
                         "folder or its Data Files folder; default: Data Files of the Morrowind folder). Exit 0: "
                         "applied / already patched / nothing matches; 1: another tool holds the lock; 2: a file "
                         "was refused; 3: partial match, nothing written; 4: no such folder")
    ap.add_argument("--dry-run", action="store_true", help="with --core-only: only check, write nothing")
    args = ap.parse_args(argv)
    if args.dry_run and not args.core_only:
        ap.error("--dry-run goes with --core-only (plan mode is already a dry run)")
    if args.core_only:
        return _core_only_main(args, ap)            # the deploy step's MWSE core repair (writes Data Files)
    staged = staged_targets(args, ap)
    if staged is None:
        return 2
    if not MP.acquire_run_lock() or not MP.acquire_game_lock(HERE):
        print(MP.RUN_LOCKED_MESSAGE, file=sys.stderr)
        return 1
    with MS.staged_run(staged[1] or staged[0], HERE):
        return _main_staged(args, staged)


def staged_targets(args, ap=None):
    """(paths to check, staging folder or None, StagedData) for a plan or --apply before deploy: the given
    folders/files, else every staged mod with an MWSE folder. A path inside Data Files is refused (the pre-deploy
    rule: mwdialog_staged; --core-only is the deploy step's way to patch MWSE core there). None when refused."""
    data_files = os.path.join(HERE, "Data Files")
    bad = [(p, MS.write_root_problem(p, HERE, data_files, mode="luafix")) for p in args.paths]
    bad = [(p, why) for p, why in bad if why]
    if getattr(args, "staging", None):
        why = MS.write_root_problem(args.staging, HERE, data_files, mode="luafix")
        if why:
            bad.insert(0, (args.staging, why))
    if bad:
        print(f"Not checking {bad[0][0]}: it is in Data Files ({bad[0][1]}). mwdialog_luafix works on staged mod "
              f"folders before deploy (pass a staged mod folder, or --core-only for MWSE core at deploy).",
              file=sys.stderr)
        return None
    staging = getattr(args, "staging", None)
    try:
        staging = MP.resolve_staging(staging, required=not args.paths and not args.undo)
    except MP.VortexPathError as e:
        print(f"{e}\n(mwdialog_luafix checks staged mods before deploy; pass --staging or folders.)", file=sys.stderr)
        return None
    if args.paths:
        roots = [os.path.abspath(p) if os.path.isdir(p) else os.path.dirname(os.path.abspath(p)) for p in args.paths]
        data = MS.StagedData(staging, HERE, extra=(MP.LUA_TOOLS_DIR,), mods=None if staging else roots)
        return list(args.paths), staging, data
    mods = MS.StagedData(staging, HERE).roots if staging else []
    paths = [r for r in mods if any(e.lower() == "mwse" for e in os.listdir(r))]
    return paths, staging, MS.StagedData(staging, HERE, extra=(MP.LUA_TOOLS_DIR,))


def _main_staged(args, staged):
    paths, _staging, data_dir = staged
    if args.undo:
        return undo(force=args.force)             # works from the journal; the plan file plays no part
    reviewed = PF.read(PLAN_FILE) if args.apply else None
    if args.apply and (PF.state(PLAN_FILE) != "pending" or not PF.has_any_actions(reviewed)):
        print(PF.no_plan_message(PLAN_FILE, "mwdialog_luafix.py"))
        return 2
    cfg = load_config(HERE, data_dir)
    checker = None if args.no_syntax_check else find_checker(args.luajit, HERE)
    print(f"mwdialog_luafix {VERSION}: syntax check {checker.name if checker else 'NONE'}; priority limit "
          f"{cfg['priorityLimit']} (-> {compress_priority(cfg['priorityLimit'], cfg)}..."
          f"{compress_priority(math.inf, cfg)}), interval "
          f"{cfg['minInterval']} s" + (f"; settings from {', '.join(cfg['_sources'])}" if cfg["_sources"] else ""))
    if args.apply and checker is None and not args.no_syntax_check:
        print("No LuaJIT/luac found. " + MP.describe_luajit_search(HERE)
              + " Not patching without a syntax check.", file=sys.stderr)
        return 2
    rep = check_paths(paths, cfg, args.include_own, checker, args.level, data_dir, not args.no_cache,
                      args.log_shim_always, log_scope=args.lua_log)
    write_known_bug_report(rep)
    lines, counts = format_report(rep, args.all)
    n_ok = sum(1 for e in rep.files.values() if e.get("patch") and e["patch"]["ok"])
    head = [f"mwdialog_luafix plan, {time.strftime('%Y-%m-%d %H:%M')}: {len(rep.files)} Lua file(s) checked, "
            f"{n_ok} to patch, {len(rep.skipped)} left alone (MWSE's own code / your mods)"] + summary_lines(counts)
    fresh = "\n".join(head + lines) + "\n"
    if args.apply:                                # enact only the plan that was reviewed
        added, removed = PF.compare(reviewed, fresh)
        if added or removed:
            PF.refuse_mismatch(PLAN_FILE, fresh, added, removed, "mwdialog_luafix.py")
            return 2
    else:
        PF.write_atomic(PLAN_FILE, fresh)
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
    print("The plan matches the one you reviewed.")
    bdir = run_backup_dir(BACKUP_ROOT)
    if not n_ok:
        print("Nothing to patch.")
        PF.finish(PLAN_FILE, "mwdialog_luafix.py", [], bdir, reviewed, fresh, note="there was nothing to patch")
        return 0
    if not args.yes and input(f"\nPatch {n_ok} file(s)? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing changed.")
        return 0
    done, refused, finished = [], [], False
    enacted = fresh
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
    write_known_bug_report(rep, done, dict(refused))
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
