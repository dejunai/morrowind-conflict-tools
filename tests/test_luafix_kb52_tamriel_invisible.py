"""KB52: Tamriel Data's Detect Invisibility opacity pass failing every frame on a stale reference.

The tables invisibleReferences / invisibleOpacityModifiedReferences are file-local and nothing emptied them on a
load; `actor.mobile` on a reference the engine freed raises "sol: received nil for 'self' argument", the error ends
the pass before the entry is removed, and it repeats every simulate (MWSE.log 2026-11-26: 1,876 errors, ~20/s).

The fixtures are excerpts of two real magic.lua files: tamrieldata_magic_old.lua (26.08 as shipped, loop with no
guard) and tamrieldata_magic_new.lua (a later release, `if actor.mobile then`, with KB8's loading wait applied)."""
import os

import pytest

from conftest import _load

lf = _load("mwdialog_luafix")

try:
    from lupa import luajit21 as _lj
    HAVE_LUA = True
except Exception:                                    # the execution tests need a real LuaJIT
    HAVE_LUA = False
need_lua = pytest.mark.skipif(not HAVE_LUA, reason="lupa (LuaJIT) not installed")

CFG = dict(lf.DEFAULTS)
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "mwse")
FORMS = ["old", "new"]
REL = "tamrieldata/magic.lua"


def fixture_text(form):
    with open(os.path.join(FIX, f"tamrieldata_magic_{form}.lua"), "rb") as f:
        return f.read().decode("utf-8")


def run_luafix(tmp_path, text, name="magic.lua"):
    """luafix's check over a mods folder holding the one file: its entry (patch, error, ...)."""
    mods = tmp_path / "Data Files" / "MWSE" / "mods"
    path = mods / "TamrielData" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    rep = lf.check_paths([str(mods)], CFG, checker=None, use_cache=False, data_dir=str(tmp_path / "Data Files"))
    ent = next(e for p, e in rep.files.items() if p.lower().endswith(name))
    assert ent["error"] is None, ent["error"]
    return ent


def kb52_text(tmp_path, form, eol="\n"):
    ent = run_luafix(tmp_path, fixture_text(form).replace("\n", eol))
    assert ent["patch"] and ent["patch"]["ok"], ent.get("patch")
    assert "KB52" in ent["patch"]["rules"], ent["patch"]["rules"]
    return ent["patch"]["text"]


# ---------------------------------------------------------------------------------------------- the entry
def test_KB52_is_one_whole_or_nothing_rule_with_its_reason():
    parts = [k for k in lf.KNOWN_BUGS if k[0] == "KB52"]
    assert len(parts) == 2 and all(p[2] == REL and p[1] == "Tamriel Data" for p in parts)
    assert "KB52" in lf.KNOWN_BUGS_WHOLE
    what = parts[0][5]
    assert "no rule can express this" in what and "local upvalues" in what and "mwpluginpatches" in what
    for _r, _pl, _path, old, new, _w in parts:
        assert old and old != new


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KB52_applies_to_both_forms_of_the_file_and_keeps_the_line_ends(tmp_path, form, eol):
    text = kb52_text(tmp_path, form, eol)
    bare = text.replace("\r\n", "\n")
    assert "local function readMobile(ref) return ref.mobile end" in bare
    assert "event.register(tes3.event.load, function()\n\tfor ref in pairs(invisibleReferences)" in bare
    assert "if not pcall(readMobile, actor) then" in bare
    assert bare.count("pcall(readMobile, actor)") == 1
    if eol == "\r\n":
        assert "\n" not in text.replace("\r\n", "")      # no bare LF came in with the patch
    # the loop it protects is still there, after the clean-up pass
    assert bare.index("pcall(readMobile, actor)") < bare.index("---@cast actor tes3reference")


@pytest.mark.parametrize("form", FORMS)
def test_KB52_second_run_changes_nothing(tmp_path, form):
    first = kb52_text(tmp_path, form)
    again = run_luafix(tmp_path / "again", first)
    assert again["patch"] is None or "KB52" not in (again["patch"]["rules"] or [])
    assert first.count("local function readMobile") == 1


@pytest.mark.parametrize("anchor", [
    "local invisibleReferences = {}\nlocal invisibleOpacityModifiedReferences = {}\n",
    "\t\tfor actor in pairs(invisibleReferences) do\n\t\t\t---@cast actor tes3reference\n",
])
@pytest.mark.parametrize("form", FORMS)
def test_KB52_skips_whole_when_an_anchor_is_missing(tmp_path, form, anchor):
    """A version of the file that moved one anchor gets neither half: no table clearing without the loop guard."""
    text = fixture_text(form)
    assert anchor in text
    changed = text.replace(anchor, anchor.replace("invisibleReferences", "seenInvisible").replace(
        "invisibleOpacityModifiedReferences", "seenOpacity"))
    ent = run_luafix(tmp_path, changed)
    patched = (ent["patch"] or {}).get("text") or ""
    assert "readMobile" not in patched and "KB52" not in ((ent["patch"] or {}).get("rules") or [])


def test_KB52_is_not_applied_to_other_files(tmp_path):
    ent = run_luafix(tmp_path, fixture_text("new"), name="other.lua")
    assert ent["patch"] is None or "KB52" not in (ent["patch"]["rules"] or [])


# ---------------------------------------------------------------------------------------------- behaviour
LUA_HARNESS = r'''
local src, name = ...
local handlers = {}
local errors = 0
tes3 = {
    event = { load = "load", loaded = "loaded", simulate = "simulate" },
    effect = { T_mysticism_DetInvisibility = 1 },
    spellType = { ability = 1 },
}
event = { register = function(ev, fn) handlers[ev] = handlers[ev] or {}; table.insert(handlers[ev], fn) end }
function table.size(t) local n = 0 for _ in pairs(t) do n = n + 1 end return n end
function math.clamp(v, lo, hi) return math.max(lo, math.min(hi, v)) end
local near = { distance = function() return 0 end }
tes3.player = { position = near }
tes3.mobilePlayer = { getActiveMagicEffects = function() return { { magnitude = 10 } } end }

local chunk = assert(loadstring(src, name))
local this = chunk()

local function upvalue(fn, wanted)
    local i = 1
    while true do
        local n, v = debug.getupvalue(fn, i)
        if not n then return nil end
        if n == wanted then return v end
        i = i + 1
    end
end
local refs = upvalue(this.detectInvisibilityOpacity, "invisibleReferences")
local modified = upvalue(this.detectInvisibilityOpacity, "invisibleOpacityModifiedReferences")

-- a reference the engine freed: any read of .mobile raises what MWSE.log showed
local function stale()
    return setmetatable({}, { __index = function(_, k)
        if k == "mobile" then error("sol: received nil for 'self' argument") end
    end })
end
local function live()
    return { position = near, mobile = { chameleon = 0, invisibility = 0, animationController = { opacity = 1 } } }
end

local api = {}
function api.add_stale() local r = stale(); refs[r] = true; modified[r] = true; return r end
function api.add_live() local r = live(); refs[r] = true; return r end
function api.step()
    local ok, err = pcall(this.detectInvisibilityOpacity, {})
    if not ok then errors = errors + 1 end
    return ok, err
end
function api.fire(ev) for _, fn in ipairs(handlers[ev] or {}) do fn({}) end end
function api.errors() return errors end
function api.sizes() return table.size(refs), table.size(modified) end
function api.has(r) return refs[r] == true end
function api.has_modified(r) return modified[r] == true end
function api.opacity(r) return r.mobile.animationController.opacity end
return api
'''


def harness(text, name="magic"):
    rt = _lj.LuaRuntime(unpack_returned_tuples=True)
    return rt.eval("function(...) " + LUA_HARNESS + " end")(text, name)


@need_lua
@pytest.mark.parametrize("form", FORMS)
def test_without_KB52_a_stale_reference_fails_every_frame_and_is_never_removed(form):
    """The bug itself, on the file as released: the pass raises on every simulate, forever."""
    h = harness(fixture_text(form))
    stale = h.add_stale()
    for _ in range(50):
        ok, err = h.step()
        assert not ok and "received nil for 'self' argument" in str(err)
    assert h.errors() == 50 and h.has(stale)


@need_lua
@pytest.mark.parametrize("form", FORMS)
def test_with_KB52_a_stale_reference_is_dropped_on_the_first_frame_and_the_rest_still_works(tmp_path, form):
    h = harness(kb52_text(tmp_path, form))
    stale1, stale2, good = h.add_stale(), h.add_stale(), h.add_live()
    ok, err = h.step()
    assert ok, err
    assert not h.has(stale1) and not h.has(stale2) and h.has(good)
    assert not h.has_modified(stale1) and not h.has_modified(stale2)
    assert h.sizes() == (1, 0) or h.sizes() == (1, 1)        # the good actor may be marked as modified
    assert h.opacity(good) == pytest.approx(0.99999)          # the live actor was still processed this frame
    for _ in range(100):
        ok, err = h.step()
        assert ok, err
    assert h.errors() == 0


@need_lua
@pytest.mark.parametrize("form", FORMS)
def test_with_KB52_both_tables_are_emptied_on_load(tmp_path, form):
    h = harness(kb52_text(tmp_path, form))
    for _ in range(3):
        h.add_stale()
    good = h.add_live()
    h.step()
    assert h.has(good) and h.has_modified(good)
    h.add_stale()
    assert h.sizes()[0] >= 2
    h.fire("load")
    assert h.sizes() == (0, 0)
    ok, err = h.step()
    assert ok, err
    assert h.errors() == 0 and not h.has(good)


@need_lua
def test_with_KB52_a_stale_reference_after_a_load_does_not_error_in_a_loop(tmp_path):
    """The log's shape: a save loads, a stale entry is present a second later, and the pass runs ~20 times a second."""
    h = harness(kb52_text(tmp_path, "new"))
    h.add_stale()
    h.fire("load")                       # the entry belonged to the game being left
    h.fire("loaded")
    for _ in range(1876):
        ok, err = h.step()
        assert ok, err
    assert h.errors() == 0
    stale_late = h.add_stale()           # one that turns up after the load (a freed actor re-added by an effect)
    for _ in range(50):
        ok, err = h.step()
        assert ok, err
    assert not h.has(stale_late) and h.errors() == 0
