#!/usr/bin/env python3
"""
mwdialog_check.py - scan a Morrowind "Data Files" folder for dialogue errors.

Loads every plugin (.esm/.esp) in load order, merges topics and their INFO
entries the way the game does (later files override earlier ones by ID), then
checks the merged result for problems such as:

  Structure      INFO with no parent DIAL, missing INFO IDs, duplicate INFO IDs,
                 truncated/corrupt records, missing or misordered masters,
                 topic type changed by a later plugin
  Link chain     PNAM/NNAM pointing at entries that don't exist, self-links,
                 loops in the previous-entry chain
  Speaker        ONAM/RNAM/CNAM/FNAM/DNAM/ANAM filters naming actors, races,
                 classes, factions or cells that don't exist; rank without a
                 faction; bad sex/disposition values
  Conditions     malformed SCVR entries, missing values, Global/Journal/Item/
                 Dead/NotID/NotFaction/NotClass/NotRace/NotCell names that don't
                 exist, Local/NotLocal variables the speaker's script lacks
  Result script  AddTopic for topics that don't exist, Journal/SetJournalIndex
                 for quests or stages that don't exist
  Journal        duplicate stage indexes, quest flags on non-journal entries
  Voice files    SNAM sound files missing from loose files and registered BSAs
  Topics         topics left with no live responses

Python 3.8+, standard library only.

Usage examples:
  python mwdialog_check.py "Data Files"
  python mwdialog_check.py "Data Files" --only MyMod.esp
  python mwdialog_check.py "Data Files" --csv report.csv --min-severity WARN
  python mwdialog_check.py "Data Files" --openmw-cfg "<openmw.cfg>"

Load order, in priority:
  --plugins A.esm B.esp ...   exactly these files, in this order
  --openmw-cfg PATH           content= lines (and data= folders) from openmw.cfg
  (automatic)                 mwdialog_load_order.txt next to Data Files (made from
                              Morrowind.ini's [Game Files] the first time; --play writes it back)
  --ini PATH                  another Morrowind.ini
  (otherwise)                 Morrowind.ini next to Data Files if present,
                              otherwise every .esm then every .esp in the folder
Vanilla Morrowind sorts masters first, then by file modification date; the
tool reproduces that for the ini and folder-scan modes.
"""

import argparse
import bisect
import json
import math
import copy
import csv
import os
import hashlib
import re
import shutil
import struct
import subprocess
import sys
import time
from collections import Counter, OrderedDict, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_paths as MP  # noqa: E402
import mwdialog_text as MT  # noqa: E402
import mwdialog_tes3  # noqa: E402
print = MT.printer()  # noqa: A001

# One module, whatever name it runs under: mwdialog_assets.py and vortex_tidy.py import it as
# "mwdialog_check" and must see this run's settings (--encoding...), not a second fresh copy.
if sys.modules.get(__name__) is not None:
    sys.modules.setdefault("mwdialog_check", sys.modules[__name__])

# The reusable parts live in smaller modules; every name is imported back, so mwdialog_check.X still works.
from mwdialog_tes3 import (  # noqa: E402,F401
    ACTOR_TAGS, ASSET_SUBS, cell_key, COMPARE_OPS, CONDITION_TYPES, cstr, dec,
    DIAL_TYPES, digest, ENAM_TAGS, enc, first_sub, forget_cached, FormatError,
    has_sub, ICON_TAGS, ID_TAGS, ITEM_TAGS, iter_records, iter_subs, JOURNAL,
    MODEL_TAGS, _mw_bytes_errors, MW_ERRORS, pack_str, pack_sub, plugin_masters, _READ_CACHE,
    _READ_CACHE_MAX, read_header_masters, read_plugin_bytes, record_id, REF_TAGS, safe_write_bytes, set_hedr_count,
    set_link, SUBTYPE_AT, _tag, _TAGS, validate_plugin_bytes, write_plugin_bytes)
from mwdialog_bsa import (  # noqa: E402,F401
    _bsa_directory, _bsa_file_names, bsa_file_names, _bsa_index, bsa_index, _BSA_MEMO, _bsa_memo)
from mwdialog_media import (  # noqa: E402,F401
    DDS_BLOCK_FOURCC, DDS_DXGI_BLOCK, DDS_DXGI_BPP, dds_info, dds_level_size, dds_reduce, DUMMY_KF,
    DUMMY_NIF, mp3_first_frame, _NIF_EXT_RE, nif_is_empty, _NIF_TEX_CHARS, _NIF_TEX_OK, nif_text_keys_lf,
    nif_texture_names, nif_texture_refs, placeholder_dds, placeholder_icon, silent_audio, sound_file_problem, _SOUND_PROBLEMS,
    SOUND_ROOTS, stand_in_bytes, TEXT_KEY_TAG, TEXTURE_MAX_EDGE)
from mwdialog_backup import (  # noqa: E402,F401
    backup_candidates, BACKUP_DIR, backup_index, backup_path, bak_home, chain_tail, game_dir_of,
    index_dir)
from mwdialog_loadorder import (  # noqa: E402,F401
    BAD_RULE_ENTRIES, default_ini, game_files_overflow, ini_game_files, INI_SECTION_LIMIT, LOAD_ORDER_FILE, LOAD_ORDER_WRITTEN,
    name_matcher, parse_rules, PLUGIN_EXTS, read_ini_sections, read_load_order, rule_entry_lines, rule_entry_ok,
    RULE_TAG, set_game_files, sort_vanilla, truncated_game_files, warn_overflow, write_ini_game_files, write_load_order)
from mwdialog_records import (  # noqa: E402,F401
    block_digest, block_key, clean_cell, COND_KINDS, defined_names, extract_record, height_at,
    index_masters, JUNKCELL_SUBTYPES, land_heights, merge_fields, MERGE_FILE_FIELDS, MERGE_GROUPS, merge_levlist,
    MERGE_LISTS, merge_object, MERGE_REF_FIELDS, parse_levlist, plugin_references, record_refs, remap_frmr,
    rewrite_cell_refs, SPEAKER_SUBS, split_cell, unresolved_refs)
from mwdialog_state import (  # noqa: E402,F401
    ADDED_MASTERS_RECORD, CELL_WINNER_PATCH, CELL_WINNERS_FILE, CONFLICT_ANSWERS_FILE, CONFLICT_BLACKLIST_DEFAULT, CONFLICT_BLACKLIST_FILE, conflict_blacklisted,
    CONFLICT_RULE_NOTE, CONFLICT_RULES_HEADER, DISABLED_RECORD, mark_merge_rebuild, MERGE_REBUILD_RECORD, MERGE_RECORD, merged_away,
    NORMAL_MAP_RE, note_promoted_rules, PROMOTED_END, PROMOTED_START, read_added_masters, read_cell_winners, read_conflict_answers,
    read_conflict_blacklist, read_disabled, read_generated_record, read_merge_rebuild, read_merge_record, read_redundant, record_bases,
    REDUNDANT_RECORD, RULES_FILE, split_conflict_rules, write_added_masters, write_cell_winners, write_conflict_answers, write_disabled,
    write_generated_record, write_merge_rebuild, write_merge_record, write_redundant)
from mwdialog_cellmods import (  # noqa: E402,F401
    COLLIDE_ANY_RADIUS, COLLIDE_DATA, COLLIDE_RADIUS, COLLIDE_SKIP_TAGS, COLLIDE_STRUCTURE_RE, INVISIBLE_RE, _OBJECT_INFO,
    object_info, RELOCATE_MIN_NEW, report_rearranged, REWORK_FRACTION, REWORK_MIN_DELETED, STRANDED_DATA, STRANDED_DISTANCE,
    STRANDED_KEEP_TAGS, STRANDED_MOVE_TAGS, write_collide_data, write_stranded_data)
from mwdialog_datatree import (  # noqa: E402,F401
    asset_health_module, asset_owner_folder, collect_sound_files, DataTree, GENERATED_RECORD, generated_rels, hard_link_names,
    IGNORED_MAP_RE, longpaths_module, mastercheck_module, ModelAssets, _real_dir, sound_names_under, VortexRepo)
from mwdialog_console import (  # noqa: E402,F401
    ask, cap_fix_log, console_interactive, FIX_LOG_ARCHIVE, FIX_LOG_CAP, fix_log_line, set_title)
from mwdialog_masters import (  # noqa: E402,F401
    add_master, added_master_in_use, check_masters_for_play, covered_by_patches, FIXABLE_EXT, master_closure, _refs_use_master,
    remove_master, write_inplace)
from mwdialog_patchfile import (  # noqa: E402,F401
    apply_item_fixes, fix_item_body, next_free_date, PATCH_NAME, patch_supports, PLACEHOLDER_CELL, placeholder_cell,
    placeholder_record, write_patch)
from mwdialog_redundant import (  # noqa: E402,F401
    AUTO_SKIP_TAGS, describe_overlap, describe_plugin, find_redundant, _id_text, lua_named_plugins, lua_required_plugins,
    _OBJECT_USE, object_use, OUR_PATCHES, PATCH_WORD_RE, PERFORMER_PATCH, PLACE_PATCH_NAME, plugin_profile,
    plugin_summary, REDUNDANT_MAX_VERSIONS, REDUNDANT_VARIANT_MIN, REDUNDANT_VARIANT_SAME, REDUNDANT_VARIANT_SHARE, relied_on, relied_on_text,
    _same_mod_name, _type_text, USE_OBJ_TAGS, vortex_mod_name)
from mwdialog_generated import (  # noqa: E402,F401
    _ASSET_BACKUP_OF, backup_asset_original, find_vortex_root, FOLLOWUP_RE, FULLSIZE_DIR, keep_new_original, off_dest,
    original_mod_guess, reduce_textures, REDUCED_RECORD, _repaired_hashes, REPAIRED_SIDECAR, replace_asset_in_place, run_remove_generated,
    run_restore_textures, _sha256_file, write_generated)
from mwdialog_restore import (  # noqa: E402,F401
    BAK_RE, CLEANUP_BAK_RE, DATES_UNDO_FILE, restore_all, restore_backups, restore_dates, run_clean_up)

ENC = "cp1252"


ASSET_UNREMOVABLE = {"LTEX"}       # a plugin's land refers to its landscape textures by number
# not placed objects: a missing file always matters (BODY: worn armor and clothing and races' bodies use body
# parts by name, which isn't counted as "placed or used")
ASSET_ALWAYS_USED = {"SOUN", "LTEX", "BSGN", "BODY"}


PLACEHOLDER_TOPIC = "error topic name"

SEVERITIES = ["ERROR", "WARN", "INFO"]
SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}


# --------------------------------------------------------------------------
# Shared helpers: lossless text codec, cached reads, safe in-place writes
# --------------------------------------------------------------------------


_OURS_LOWER = None


def is_our_patch(name):
    """One of the plugins these tools generate (any case: Windows file names aren't case-sensitive)."""
    global _OURS_LOWER
    if _OURS_LOWER is None:
        _OURS_LOWER = frozenset(x.lower() for x in OUR_PATCHES)
    return (name or "").lower() in _OURS_LOWER


# --------------------------------------------------------------------------
# Low-level TES3 reading
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Merged game data
# --------------------------------------------------------------------------

class Info:
    __slots__ = ("id", "topic", "source", "prev", "next", "deleted", "dtype",
                 "disp", "rank", "sex", "pcrank", "actor", "race", "cls",
                 "faction", "cell", "pcfaction", "sound", "text", "conditions",
                 "result", "qstn", "qstf", "qstr", "off")

    def __init__(self):
        self.prev = self.next = ""
        self.off = None
        self.deleted = False
        self.dtype = None
        self.disp = 0
        self.rank = self.sex = self.pcrank = -1
        self.actor = self.race = self.cls = self.faction = ""
        self.cell = self.pcfaction = self.sound = self.text = self.result = ""
        self.conditions = []
        self.qstn = self.qstf = self.qstr = False


class Topic:
    __slots__ = ("name", "key", "dtype", "source", "deleted", "infos", "file_links", "defined_by")

    def __init__(self, name, dtype, source):
        self.name, self.dtype, self.source = name, dtype, source
        self.key = name.lower()
        self.deleted = False
        self.infos = OrderedDict()   # lowercase info id -> Info
        self.file_links = defaultdict(dict)   # plugin lower -> {info id lower: (prev lower, Info)}
        self.defined_by = defaultdict(list)   # info id lower -> plugin names (lower) that contain it, in load order


def issue_label(topic, info, msg):
    return f"{'[' + topic + '] ' if topic else ''}{info + ': ' if info else ''}{msg}"


class Report:
    """Collects issues. An issue may carry a proposed fix: (record offset, op, description)."""

    def __init__(self):
        self.issues = []
        self.fixes = []    # (plugin, offset, op, description, issue message)

    def add(self, sev, plugin, topic, info, msg, fix=None):
        self.issues.append((sev, plugin or "", topic or "", info or "", msg))
        if fix is not None and sev == "ERROR":
            off, op, desc = fix
            self.fixes.append((plugin, off, op, desc, issue_label(topic, info, msg), topic, info))


class World:
    def __init__(self, report):
        self.r = report
        self.ids = defaultdict(set)        # tag -> lowercase ids
        self.all_ids = {}                  # lowercase id -> tag
        self.actor_script = {}             # actor id -> script id
        self.script_locals = {}            # script id -> set of local names
        self.cell_names = {"wilderness"}   # lowercase names of real cells, plus the unnamed-exterior default
        self.region_names = set()          # lowercase region names (not cells, as far as the game's checks go)
        self.paths = {}                    # plugin name lower -> file path
        self.levlists = OrderedDict()      # (LEVC|LEVI, id lower) -> [(plugin, body, deleted)] in load order
        self.fogcells = {}                 # interior cell name lower -> (plugin, NAME, DATA, AMBI) with fog 0
        self.rencells = {}                 # exterior (x, y) -> tes3cmd cell-rename tracking
        self.cell_heads = {}               # cell key -> header subrecords [(name, data)] of its latest record
        self.ref_mods = []                 # references a plugin makes to its masters' cell objects
        self.persist_mismatch = defaultdict(int)   # master file -> references filed in the wrong group
        self.size_mismatch = []            # (plugin, master, size saved against, size now)
        self.hedr_count = {}               # plugin -> record count its header claims
        self.real_count = {}               # plugin -> records actually in it
        self.ref_error_masters = set()     # (plugin lower, master lower) with reference errors
        self.defined_by_obj = {}           # object id -> first plugin that defined it
        self.last_def_obj = {}             # object id -> (last plugin that defined it, record type)
        self.pending_placed = []           # this plugin's references to objects not defined (yet)
        self.missing_placed = []           # (plugin, cell offset, cell label, FRMR, object) missing at load
        self.early_needed = {}             # object id lower -> (plugin defining it, type, [who needs it])
        self.first_def_at = {}             # object id lower -> (load index, plugin) of its first definition
        self.first_placed_at = {}          # object id lower -> (load index, plugin) of its first placed copy
        self.first_persist_at = {}         # ... of its first persistent placed copy
        self.script_at = {}                # script id lower -> load index of the plugin defining it
        self.early_placed = {}             # object id lower -> {id, by, users}: placed early, hidden
        self.trace = set()                 # --trace: object ids (lower) to follow through the load order
        self.trace_log = []
        self.deleted_by_obj = {}           # object id -> plugin that deleted it (if it is gone now)
        self.script_src = {}               # script id -> (plugin, script name, source text)
        self.missing_objects = {}          # object id lower -> {id, arrow (used as X->), used_by}
        self.placed = defaultdict(int)     # object id lower -> placed copies in the world
        self.ref_gone = set()              # (owner, cell, index) of master references deleted so far
        self.unplaced_by = {}              # object id lower -> plugin that deleted a placed copy
        self.arrow_targets = {}            # object id lower -> {id, used_by} for "X->" in scripts
        self.unplaced = {}                 # defined objects scripts act on, with no placed copy
        self.gold_template = None          # body of the gold_001 MISC record, for placeholders
        self.topics = OrderedDict()        # lowercase topic -> Topic
        self.info_home = {}                # lowercase info id -> topic key
        self.loaded = []                   # plugin names, in order
        self.unfixable = {}                # plugin name lower -> reason it must not be auto-fixed
        self.nameless_seen = {}            # plugin name lower -> nameless topics seen in it
        self.placeholder_used = set()      # placeholder topic names already handed out
        self.masters = {}                  # plugin name lower -> [master names]
        self.obj_refs = defaultdict(list)  # object id lower -> [(plugin, tag, id, refs or None if deleted)]
        self.obj_events = {}               # object id lower -> [(load index, plugin, tag, deleted?)]
        self.item_fixes = []               # dangling SCRI/ENAM/NPCO in the winning record (see _check_item_refs)
        self.cell_regions = {}             # exterior cell key -> [(plugin, region or None)] in load order
        self.cell_name_hist = {}           # cell key -> [(plugin, name)] in load order
        self.cell_final = {}               # cell key -> the name it ends up with
        self.undelete = {}                 # (deleting plugin, tag, id) -> (id, placing plugin, message)
        self.script_cells = set()          # cell names scripts ask for (lowercase)
        self.cell_name_at = {}             # cell key -> [(load index, plugin, name)] in load order
        self.info_cells = []               # (load index, plugin, topic, info id, cell filter) as loaded
        self.restored_cells = set()        # (cell key, plugin) already given its name back
        self.region_at = {}                # lowercase region name (FNAM) -> load index it first appears at
        self.cell_loads = []               # (load index, plugin, cell key, name, references in the record)
        self.door_dest = defaultdict(set)  # lowercase interior name a door leads to -> plugins with that door
        self.models = defaultdict(list)    # (tag, id lower) -> [(load index, plugin, {(sub, kind): file}, deleted, id)]
        self.ini_path = None               # Morrowind.ini, for its font and sky texture settings
        self.subtypes = {}                 # (tag, id lower) -> subtype (clothing/armour/weapon/body part kind)
        self.generated = []                # (path under Data Files, why[, source]): files --fix puts in Data Files
        self.vortex = None                 # VortexRepo: undeployed files in Vortex mod folders
        self.missing_by_plugin = defaultdict(int)   # plugin -> files it needs that exist nowhere
        self.lev_win = {}                  # (LEVI|LEVC, id lower) -> (plugin, id, [entry ids]) of the winning list
        self.obj_used_at = defaultdict(set)  # object id lower -> load indexes of plugins that place/hold/list it
        self.assets = None                 # ModelAssets, when model files are checked

    # ---- per-plugin loading ------------------------------------------------

    def load_plugin(self, path, name):
        r = self.r
        self.paths[name.lower()] = path
        try:
            data = read_plugin_bytes(path)
        except OSError as e:
            r.add("ERROR", name, "", "", f"could not read file: {e}")
            return

        n_records = 0
        current = None          # Topic currently receiving INFOs
        seen_in_topic = {}      # info id -> offset, under current DIAL in this file
        first = True
        try:
            for off, tag, flags, body in iter_records(data):
                if first:
                    first = False
                    if tag != "TES3":
                        r.add("ERROR", name, "", "", "file does not start with a TES3 header; not a Morrowind plugin")
                        return
                    self._check_header(body, name)
                    continue
                n_records += 1
                if self.trace:
                    self._trace_record(name, tag, flags, body)

                if tag == "DIAL":
                    current, seen_in_topic = self._load_dial(body, flags, name, off), {}
                elif tag == "INFO":
                    self._load_info(body, flags, name, off, current, seen_in_topic)
                elif tag == "CELL":
                    current = None
                    self._load_cell(body, name, off)
                else:
                    current = None
                    self._load_other(tag, body, flags, name)
        except FormatError as e:
            r.add("ERROR", name, current.name if current else "", "", f"corrupt data, stopped reading file: {e}")
            self.unfixable.setdefault(name.lower(), "the file is corrupt or truncated")
        else:
            self.real_count[name] = n_records
        self.missing_placed += [x for x in self.pending_placed if x[4].lower() not in self.all_ids]
        self.pending_placed = []
        self.loaded.append(name.lower())

    def _check_header(self, body, name):
        r = self.r
        master_name = None
        for sname, sdata in iter_subs(body):
            if sname == "MAST":
                master_name = cstr(sdata)
                self.masters.setdefault(name.lower(), []).append(master_name)
                if master_name.lower() not in self.loaded:
                    r.add("ERROR", name, "", "", f"requires master '{master_name}', which is not loaded before it")
                    self.unfixable.setdefault(name.lower(), f"its master '{master_name}' is missing, so its references can't be judged")
            elif sname == "DATA" and master_name:
                expected = struct.unpack_from("<Q", sdata)[0] if len(sdata) >= 8 else None
                actual = self.file_sizes.get(master_name.lower())
                if expected is not None and actual is not None and expected != actual:
                    self.size_mismatch.append((name, master_name, expected, actual))
                master_name = None
            elif sname == "HEDR" and len(sdata) >= 300:
                self.hedr_count[name] = struct.unpack_from("<I", sdata, 296)[0]

    def _load_other(self, tag, body, flags, name=""):
        deleted = has_sub(body, b"DELE") or bool(flags & 0x20)
        if tag in ("LEVC", "LEVI") and multipatch_source(name):
            nm = first_sub(body, b"NAME")
            if nm is not None:
                self.levlists.setdefault((tag, cstr(nm).lower()), []).append((name, body, deleted))
        if tag == "GMST":
            nm = first_sub(body, b"NAME")
            if nm is not None and cstr(nm).lower() == "sdefaultcellname":
                sv = first_sub(body, b"STRV")
                if sv:
                    self.cell_names.add(cstr(sv).lower())
            return
        if tag == "LTEX":                   # landscape textures: only their file is of interest
            nm = first_sub(body, b"NAME")
            dt = first_sub(body, b"DATA")
            if nm is not None:
                fields = {("DATA", "texture"): cstr(dt).strip()} if dt is not None and cstr(dt).strip() else {}
                self.models[("LTEX", cstr(nm).lower())].append((len(self.loaded), name, fields, deleted, cstr(nm)))
            return
        if tag not in ID_TAGS:
            return
        if tag == "SCPT":   # script ID lives in the first 32 bytes of SCHD
            hd = first_sub(body, b"SCHD")
            nm = hd[:32] if hd is not None else None
        else:
            nm = first_sub(body, b"NAME")
        if nm is None:
            return
        rid = cstr(nm).lower()
        if tag in SUBTYPE_AT and not deleted:
            sub, fmt, at = SUBTYPE_AT[tag]
            sd = first_sub(body, sub)
            if sd is not None and len(sd) >= at + struct.calcsize(fmt):
                self.subtypes[(tag, rid)] = struct.unpack_from(fmt, sd, at)[0]
        if tag in ASSET_SUBS:
            fields = {}
            for sub, kind in ASSET_SUBS[tag]:
                v = first_sub(body, sub.encode("ascii"))
                if v is not None and cstr(v).strip():
                    fields[(sub, kind)] = cstr(v).strip()
            self.models[(tag, rid)].append((len(self.loaded), name, fields, deleted, cstr(nm)))
        if tag in ("LEVI", "LEVC"):
            if deleted:
                self.lev_win.pop((tag, rid), None)
            else:
                self.lev_win[(tag, rid)] = (name, cstr(nm), [cstr(d) for s, d in iter_subs(body) if s in ("INAM", "CNAM")])
        if not deleted and tag in ("CONT", "NPC_", "CREA", "LEVI", "LEVC"):
            for sname, sdata in iter_subs(body):
                if sname == "NPCO" and len(sdata) >= 36:
                    self.obj_used_at[cstr(sdata[4:36]).lower()].add(len(self.loaded))
                elif sname in ("INAM", "CNAM") and tag in ("LEVI", "LEVC"):
                    self.obj_used_at[cstr(sdata).lower()].add(len(self.loaded))
        if tag in REF_TAGS:
            self.obj_refs[rid].append((name, tag, cstr(nm), None if deleted else record_refs(tag, body)))
        self.obj_events.setdefault(rid, []).append((len(self.loaded), name, tag, deleted))
        if deleted:
            self.ids[tag].discard(rid)
            self.all_ids.pop(rid, None)
            if rid in self.defined_by_obj:
                self.deleted_by_obj[rid] = name
            return
        self.ids[tag].add(rid)
        if tag == "MISC" and rid == "gold_001":
            self.gold_template = body
        self.defined_by_obj.setdefault(rid, name)
        self.first_def_at.setdefault(rid, (len(self.loaded), name))
        self.last_def_obj[rid] = (name, tag)
        self.deleted_by_obj.pop(rid, None)
        self.all_ids[rid] = tag
        if tag == "REGN":
            fn = first_sub(body, b"FNAM")
            if fn:
                self.region_names.add(cstr(fn).lower())
                self.region_at.setdefault(cstr(fn).lower(), len(self.loaded))
        elif tag in ACTOR_TAGS:
            sc = first_sub(body, b"SCRI")
            if sc is not None:
                self.actor_script[rid] = cstr(sc).lower()
            else:
                self.actor_script.pop(rid, None)
        elif tag == "SCPT":
            names = set()
            for sname, sdata in iter_subs(body):
                if sname == "SCVR":
                    names.update(n.lower() for n in sdata.decode(ENC, MW_ERRORS).split("\0") if n)
                elif sname == "SCTX" and not names:
                    for m in re.finditer(r"^\s*(?:short|long|float)\s+(\w+)", sdata.decode(ENC, MW_ERRORS), re.I | re.M):
                        names.add(m.group(1).lower())
            self.script_locals[rid] = names
            tx = first_sub(body, b"SCTX")
            self.script_src[rid] = (name, cstr(nm), tx.decode(ENC, MW_ERRORS) if tx else "")
            self.script_at[rid] = len(self.loaded)

    def _load_cell(self, body, name, off):
        key, label = cell_key(body)
        if multipatch_source(name, cells=True):
            self._track_multipatch_cell(body, name, key)
        nm = first_sub(body, b"NAME")
        if nm is not None and cstr(nm):
            self.cell_names.add(cstr(nm).lower())
        if key is None:
            return
        self._check_cell_region(body, name, key, label)
        self._check_cell_name(body, name, key)
        # one pass: count the references, note door destinations (interior cell names), and split the cell
        # into reference blocks: FRMR value, object id, deleted?
        nrefs = 0
        blocks, cur, temporary = [], None, False
        for sname, sdata in iter_subs(body):
            if sname == "FRMR":
                nrefs += 1
                if len(sdata) >= 4:
                    cur = [struct.unpack_from("<I", sdata)[0], "", False, temporary]
                    blocks.append(cur)
                    continue
            elif sname == "DNAM" and nrefs:
                self.door_dest[cstr(sdata).strip().lower()].add(name)
            if sname == "NAM0":
                cur, temporary = None, True
            elif sname == "MVRF":
                cur = None
            elif cur is not None:
                if sname == "NAME" and not cur[1]:
                    cur[1] = cstr(sdata)
                elif sname == "DELE":
                    cur[2] = True
        self.cell_loads.append((len(self.loaded), name, key, cstr(nm or b"").strip(), nrefs))
        masters = self.masters.get(name.lower(), [])
        for v, obj, deleted, temp in blocks:
            k = v >> 24
            o = obj.lower()
            if not deleted and o and o not in self.all_ids:
                self.pending_placed.append((name, off, label, v, obj))
            if not deleted and o:
                self.obj_used_at[o].add(len(self.loaded))
                self.first_placed_at.setdefault(o, (len(self.loaded), name))
                if not temp:                           # scripts can only act on a persistent copy
                    self.first_persist_at.setdefault(o, (len(self.loaded), name))
            if k == 0:
                if not deleted:
                    self.placed[o] += 1                   # a new placed copy
                continue
            if k > len(masters):
                continue
            self.ref_mods.append((name, off, key, label, v, obj, temp))   # FRMR high byte = 1-based master
            rkey = (masters[k - 1].lower(), key, v & 0xFFFFFF)
            if deleted and rkey not in self.ref_gone:
                self.ref_gone.add(rkey)
                self.placed[o] -= 1
                self.unplaced_by[o] = name
            elif not deleted and rkey in self.ref_gone:   # a later plugin restores it
                self.ref_gone.discard(rkey)
                self.placed[o] += 1

    # functions whose first argument is an object ID (a quoted or bare name)
    OBJ_FUNCS = ("additem", "removeitem", "getitemcount", "equip", "hasitemequipped", "placeatpc",
                 "placeatme", "placeitem", "placeitemcell", "getdeadcount", "drop", "getdistance",
                 "startcombat", "aifollow", "aiescort", "aiactivate", "getdetected", "getlos",
                 "getlineofsight", "getcurrentaipackage", "addsoulgem", "dropsoulgem", "position")
    RE_ARROW = re.compile(r'(?:"([^"]+)"|\b([A-Za-z0-9_][\w\-\.\']*))\s*->')
    RE_OBJARG = re.compile(r'\b(' + "|".join(OBJ_FUNCS) + r')\b[\s,]*(?:"([^"]+)"|([A-Za-z_][\w\-\.\']*))', re.I)

    def _check_cell_name(self, body, name, key):
        """Track each cell's name through the load order (see _check_script_cells)."""
        raw = cstr(first_sub(body, b"NAME") or b"")
        self.cell_name_hist.setdefault(key, []).append((name, raw))
        self.cell_name_at.setdefault(key, []).append((len(self.loaded), name, raw.strip()))
        self.cell_final[key] = raw.strip()

    def _lost_cell_names(self):
        """Exterior cells whose winning record has lost a name an earlier plugin gave them: a blank name
        (or only spaces) after 'Caldera' or 'Caldera Priory', or any rename away from a master's (.esm)
        name. name lower -> [(key, winner, giver, name, raw)]. Only names something uses get fixed."""
        lost = defaultdict(list)
        for key, hist in self.cell_name_hist.items():
            if key[0] != "e" or not hist:
                continue
            final = hist[-1][1].strip()
            # a master (.esm) named this cell: its name wins over any later plugin's rename or blank
            esm = next(((p, n.strip()) for p, n in reversed(hist) if n.strip() and p.lower().endswith(".esm")), None)
            if esm and final.lower() != esm[1].lower():
                lost[esm[1].lower()].append((key, hist[-1][0], esm[0], esm[1], hist[-1][1]))
                continue
            if final:
                continue
            prev = next(((p, n) for p, n in reversed(hist) if n.strip()), None)
            if prev:
                lost[prev[1].strip().lower()].append((key, hist[-1][0], prev[0], prev[1].strip(), hist[-1][1]))
        return lost

    def _restore_cell_name(self, entries, why, done):
        for key, winner, giver, cname, raw in entries:
            if (key, winner.lower()) in done:
                continue
            done.add((key, winner.lower()))
            x, y = key[1], key[2]
            if raw.strip():
                msg = (f"cell ({x}, {y}): renamed '{raw.strip()}', but {giver} calls it '{cname}' and "
                       f"{why} looks for '{cname}'")
            else:
                what = "is only spaces" if raw else "is empty"
                msg = (f"cell ({x}, {y}): its name {what}, which renames '{cname}' (from {giver}) to nothing, "
                       f"and {why} looks for '{cname}'")
            self.r.add("ERROR", winner, "", "", msg)
            self.item_fixes.append({"plugin": winner, "tag": "CELL", "id": f"({x}, {y})", "key": key,
                                    "set": {"NAME": cname}, "npco": set(), "head_only": True,
                                    "msgs": [(msg, f"name it '{cname}' again, as {giver} does")]})

    def _check_script_cells(self):
        """Cell names scripts ask for (GetPCCell, PositionCell, PlaceItemCell, AI...Cell, COC) and dialogue
        cell filters, checked against the names cells end up with. A name that a later plugin erased
        (Tamrielic Treasures saving Caldera as 33 spaces) stops the game with "Unable to find cell id":
        that cell gets its name back. Script names must match a cell exactly; dialogue filters match
        any cell whose name starts with them."""
        final = {v.lower() for v in self.cell_final.values() if v} | set(self.region_names) | {"wilderness"}
        ever = {c.strip() for c in self.cell_names if c.strip()}
        lost = self._lost_cell_names()
        done = self.restored_cells
        self.script_cells = set()
        pat = re.compile(r'\b(GetPCCell|PositionCell|PlaceItemCell|AIFollowCell|AIEscortCell|CenterOnCell|COC)\b'
                         r'[^"\n;]*"([^"\n]+)"', re.I)
        for sid, (plugin, sname, text) in self.script_src.items():
            seen = set()
            for line in text.splitlines():
                code = line.split(";", 1)[0]
                for m in pat.finditer(code):
                    cell = m.group(2).strip()
                    if m.group(1).lower() == "placeitemcell":     # PlaceItemCell "obj" "cell" ...
                        m2 = re.match(r'\s*,?\s*"([^"\n]+)"', code[m.end():])
                        if not m2:
                            continue
                        cell = m2.group(1).strip()
                    low = cell.lower()
                    if low:
                        self.script_cells.add(low)
                    if not low or low in seen or low in final:
                        continue
                    seen.add(low)
                    if low in lost:
                        self._restore_cell_name(lost[low], f"script {sname} ({plugin})", done)
                    elif low in ever:
                        self.r.add("WARN", plugin, f"script {sname}", "",
                                   f"{m.group(1)} names cell '{cell}', but a later plugin renamed that cell; "
                                   f"the game stops with 'Unable to find cell id' when this runs")
                    else:
                        self.r.add("INFO", plugin, f"script {sname}", "",
                                   f"{m.group(1)} names cell '{cell}', which no plugin has (often unused "
                                   f"or test code; the game errors only if that line runs)")
        if lost:
            ordered, known = sorted(final), {}     # "some name starts with c": a binary search, once per filter
            for t in self.topics.values():
                for info in t.infos.values():
                    c = (info.cell or "").strip().lower()
                    if not c or info.deleted:
                        continue
                    hit = known.get(c)
                    if hit is None:
                        i = bisect.bisect_left(ordered, c)
                        hit = known[c] = i < len(ordered) and ordered[i].startswith(c)
                    if hit:
                        continue
                    hits = [n for n in lost if n.startswith(c)]
                    for n in hits:
                        self._restore_cell_name(lost[n], f"dialogue in {info.source} ({t.name})", done)

    def _check_load_time_cells(self):
        """The game checks each dialogue response's cell filter as its plugin loads, against the cells that
        exist at that moment, and needs a cell with exactly that name ("Gorne, Temple" doesn't count for
        "Gorne"). A cell an .esm names can be renamed or blanked by a plugin that loads earlier (Legend of
        Chemua blanking TR's 'Gorne') and named again by one that loads later, so the final names look
        fine while the game still warns "Cell 'Gorne' not found for dialogue type Greeting".
        Fix: the plugin that took a master's (.esm) name away gets that name back in its version of the
        cell (the .esm name wins). A name that only an .esp gave, or that a plugin loading later adds,
        is reported with the load order that would work."""
        by_name = defaultdict(set)                 # lowercase name -> cell keys that ever had it
        for key, hist in self.cell_name_at.items():
            for _i, _p, n in hist:
                if n:
                    by_name[n.lower()].add(key)
        default = {c for c in self.cell_names if c == "wilderness"}
        reported = set()
        for idx, plugin, topic, iid, cell in self.info_cells:
            c = cell.strip().lower()
            if not c or c in default or c not in by_name:
                continue                           # never a cell name: the filter check reports it
            if self.region_at.get(c, 1 << 30) <= idx:
                continue                           # a region with exactly that name also satisfies the game
            ok, clobbered, later = False, [], []
            for key in by_name[c]:
                hist = self.cell_name_at[key]
                before = [h for h in hist if h[0] <= idx]
                if before and before[-1][2].lower() == c:
                    ok = True
                    break
                gave = [h for h in before if h[2].lower() == c]
                if gave:
                    clobbered.append((key, gave[-1], before[-1], hist))
                else:
                    first = next(h for h in hist if h[2].lower() == c)
                    later.append((key, first))
            if ok or (plugin.lower(), c) in reported:
                continue
            reported.add((plugin.lower(), c))
            self.script_cells.add(c)                   # keep the Multipatch from renaming it again
            why = f"dialogue in {plugin} ({topic}), which loads after it,"
            fixed = False
            for key, gave, took, hist in clobbered:
                esm = next((h for h in reversed(hist) if h[0] <= gave[0] and h[2].lower() == c
                            and h[1].lower().endswith(".esm")), None)
                if esm and took[1].lower() != esm[1].lower():
                    raw = took[2]
                    self._restore_cell_name([(key, took[1], esm[1], esm[2], raw)], why, self.restored_cells)
                    fixed = True
            if fixed:
                continue
            if clobbered:
                key, gave, took, hist = clobbered[0]
                back = next((h for h in hist if h[0] > idx and h[2].lower() == c), None)
                what = f"renamed it '{took[2]}'" if took[2] else "blanked its name"
                hint = (f"load it before {took[1]}" + (f" or after {back[1]}, which names it again" if back else ""))
                self.r.add("ERROR", plugin, topic, iid,
                           f"cell filter '{cell}' is not found when this plugin loads: {gave[1]} names the cell, "
                           f"but {took[1]} {what} first (the game warns \"Cell '{cell}' not found\"); {hint}")
            elif later:
                key, first = later[0]
                if plugin.lower().endswith(".esm") and not first[1].lower().endswith(".esm"):
                    hint = "an .esm always loads before every .esp, so the game warns about this at every start (harmless otherwise)"
                    sev = "INFO"
                else:
                    hint, sev = f"load {plugin} after {first[1]}", "ERROR"
                self.r.add(sev, plugin, topic, iid,
                           f"cell filter '{cell}' is not found when this plugin loads: the first plugin to "
                           f"have that cell is {first[1]}, which loads after it; {hint}")

    def _check_cell_kind_clash(self):
        """An interior and an exterior cell can't share a name: when the second of them loads the game
        says "Interior Cell 'Akuband' trying to become Exterior Cell (23, -22)!". Usually a plugin made for
        an older Tamriel Rebuilt still carries an interior TR has since turned into (or renamed after) a
        town. Fix: remove the plugin's interior record when nothing is lost by it: it holds no objects
        (only lighting or settings for an interior that no longer exists), or no door or script leads
        to it. Names this run gives back to exterior cells are taken into account."""
        pending = {}                               # (key, plugin lower) -> name a fix gives it
        for fx in self.item_fixes:
            if fx.get("tag") == "CELL" and fx.get("key") and fx["key"][0] == "e" and fx["set"].get("NAME"):
                pending[(fx["key"], fx["plugin"].lower())] = fx["set"]["NAME"]
        ext_hist = {}
        for key, hist in self.cell_name_at.items():
            if key[0] == "e":
                ext_hist[key] = [(i, p, pending.get((key, p.lower()), n)) for i, p, n in hist]
        by_name = defaultdict(set)
        for key, hist in ext_hist.items():
            for _i, _p, n in hist:
                if n:
                    by_name[n.lower()].add(key)

        def ext_at(n, idx):
            for key in by_name.get(n, ()):
                before = [h for h in ext_hist[key] if h[0] <= idx]
                if before and before[-1][2].lower() == n:
                    return key
            return None

        done = set()
        for idx, plugin, key, nm, nrefs in self.cell_loads:
            n = nm.lower()
            if not n:
                continue
            # only an interior record loading while an exterior has its name trips the game; an exterior
            # named after an interior that loaded earlier (Guarded Dungeon Entrances naming (13, -32)
            # 'Ald Volos') loads quietly
            if key[0] != "i":
                continue
            ext = ext_at(n, idx)
            clash_int = [(idx, plugin, nrefs, nm)] if ext else []
            for i_idx, i_plugin, i_refs, i_nm in clash_int:
                if (i_plugin.lower(), n) in done:
                    continue
                done.add((i_plugin.lower(), n))
                x, y = ext[1], ext[2]
                msg = (f"Interior Cell '{i_nm}' trying to become Exterior Cell ({x}, {y}): this plugin has an "
                       f"interior named like that exterior cell")
                reach = sorted(self.door_dest.get(n, ())) + (["a script"] if n in self.script_cells else [])
                if not i_plugin.lower().endswith(FIXABLE_EXT) or is_our_patch(i_plugin):
                    self.r.add("ERROR", i_plugin, "", "", msg + " (in a master; not changed)")
                    continue
                if i_refs and reach:
                    self.r.add("ERROR", i_plugin, "", "", msg + f"; its {i_refs} object(s) are reached from "
                               f"{', '.join(reach[:3])}, so it isn't removed automatically: rename it in the "
                               f"Construction Set (and the doors that lead to it)")
                    continue
                if i_refs:
                    action = (f"remove the interior record and its {i_refs} object(s): no door or script "
                              f"leads there, so nothing in the game can reach them")
                else:
                    action = ("remove the interior record: it holds no objects, only lighting or settings for "
                              "an interior that no longer exists by that name")
                self.r.add("ERROR", i_plugin, "", "", msg)
                if any(f.get("drop_record") and f.get("key") == ("i", n) and f["plugin"] == i_plugin
                       for f in self.item_fixes):
                    continue
                self.item_fixes.append({"plugin": i_plugin, "tag": "CELL", "id": i_nm, "key": ("i", n),
                                        "set": {}, "npco": set(), "drop_record": True,
                                        "msgs": [(msg, action)]})

    def _check_models(self):
        """Files records name (models and their textures, inventory icons, sound files, landscape and
        birthsign textures), checked across every plugin's version of the record:
          - a broken version that a later plugin replaces with a working one is never used by the game;
            --fix removes it from its plugin, unless something placed or listed between the two needs
            the object defined (then it would be missing there). Landscape textures are only reported.
          - a broken winning version is reported (with the earlier plugin that has a working one)."""
        A = self.assets
        r = self.r

        def problems(fields):
            return [p for p in (A.field_problem(k, v) for (_s, k), v in sorted(fields.items())) if p]

        for (tag, rid), vers in self.models.items():
            if not vers or vers[-1][3]:
                continue
            win = vers[-1]
            wprobs = problems(win[2])
            if wprobs:
                used = tag in ASSET_ALWAYS_USED or self.placed.get(rid, 0) > 0 or rid in self.obj_used_at
                ph_model = any(k == "mesh" and A.placeholder(v) for (_s, k), v in win[2].items())
                if not used and ph_model:
                    # model still the editor's "Add World Art": nothing places or lists it. A script that names
                    # it (or acts on it) keeps it, as a coin; otherwise --fix (clean) removes the record.
                    scripted = rid in self.arrow_targets or any(
                        rid in text.lower() for _p, _n, text in self.script_src.values())
                    msg = f"{tag} '{win[4]}': model not set (still the editor's placeholder)"
                    if scripted:
                        self.r.add("WARN", win[1], "", win[4], msg + "; a script names it: --fix makes it a coin")
                        self.item_fixes.append({"plugin": win[1], "tag": tag, "id": win[4], "npco": set(),
                                                "set": {s_: PLACEHOLDER_COIN for (s_, k), v in win[2].items()
                                                        if k == "mesh" and A.placeholder(v)},
                                                "msgs": [(msg, f"give it the coin model {PLACEHOLDER_COIN}")]})
                    elif win[1].lower().endswith(FIXABLE_EXT) and not is_our_patch(win[1]):
                        self.r.add("WARN", win[1], "", win[4], msg + "; nothing uses it: --fix removes it")
                        if not any(f.get("drop_record") and f["plugin"] == win[1] and f["tag"] == tag
                                   and f["id"].lower() == rid for f in self.item_fixes):
                            self.item_fixes.append({"plugin": win[1], "tag": tag, "id": win[4], "set": {},
                                                    "npco": set(), "drop_record": True,
                                                    "msgs": [(msg, "remove the unfinished, unused object")]})
                    elif not is_our_patch(win[1]):
                        # in a master: the ESM patch deletes it (rebuilt every --fix, so a mod that starts
                        # using it later simply keeps it)
                        self.r.add("WARN", win[1], "", win[4], msg + f"; nothing uses it: --fix deletes it in "
                                                                     f"{PATCH_NAME}")
                        self.item_fixes.append({"plugin": win[1], "tag": tag, "id": win[4], "set": {},
                                                "npco": set(), "drop_record": True, "delete_in_patch": True,
                                                "msgs": [(msg, f"deleted in {PATCH_NAME} (unfinished, unused)")]})
                    continue
                if not used:
                    continue
                good = next((v for v in reversed(vers[:-1]) if not v[3] and v[2] and not problems(v[2])), None)
                hint = ""
                if good and good[1].lower().endswith(".esp") and win[1].lower().endswith(".esp"):
                    hint = f"; {good[1]} has a working version (or load it after {win[1]})"
                elif good:
                    hint = f"; {good[1]} has a working version"
                fatal = any(A.fatal(p) for p in wprobs)
                where = "" if tag in ASSET_ALWAYS_USED else "; it is placed or used in the game"
                msg = f"{tag} '{win[4]}': {'; '.join(wprobs)}{where}{hint}"
                if not fatal:
                    r.add("INFO", win[1], "", win[4], msg)
                    self._texture_stand_ins(win)
                    continue
                self._stand_in(tag, rid, win, msg)
                self._texture_stand_ins(win)
                continue
            for i, v in enumerate(vers[:-1]):
                idx, plugin, fields, deleted, oid = v
                if deleted or not plugin.lower().endswith(FIXABLE_EXT) or is_our_patch(plugin):
                    continue
                probs = problems(fields)
                if not probs:
                    continue
                later = next((w[1] for w in vers[i + 1:] if not w[3] and not problems(w[2])), win[1])
                msg = f"{tag} '{oid}': {'; '.join(probs)}, but {later} (loading later) replaces it with a working version"
                if tag in ASSET_UNREMOVABLE:
                    r.add("INFO", plugin, "", oid, msg + " (a landscape texture: left in place)")
                    continue
                nxt = vers[i + 1][0]
                earlier = any(not w[3] for w in vers[:i])
                users = sorted(u for u in self.obj_used_at.get(rid, ()) if idx <= u < nxt)
                if users and not earlier:
                    who = self.loaded[users[0]] if users[0] < len(self.loaded) else "?"
                    r.add("INFO", plugin, "", oid, msg + f"; kept, because {who} places or lists it before "
                                                         f"that version loads")
                    continue
                r.add("WARN", plugin, "", oid, msg)
                if any(f.get("drop_record") and f["plugin"] == plugin and f["tag"] == tag
                       and f["id"].lower() == rid for f in self.item_fixes):
                    continue
                self.item_fixes.append({"plugin": plugin, "tag": tag, "id": oid, "set": {}, "npco": set(),
                                        "drop_record": True,
                                        "msgs": [(msg, "remove this broken version (the later one is what the game "
                                                       "uses)")]})
        self._check_script_assets()
        self._check_ini_assets()
        self._check_lua_orphans()
        self._check_big_textures()
        self._check_text_keys()
        ign = sorted(getattr(self.assets, "ignored_normals", ()))
        if ign:
            try:
                gd = os.path.dirname(os.path.abspath(getattr(self, "args_data_dir", ".")))
                with open(os.path.join(gd, IGNORED_NORMALS_RECORD), "w", encoding="utf-8") as f:
                    f.write("; normal maps models name that don't exist: --fix puts a flat stand-in in place of "
                            "each (the game loads them; a missing one is a warning)\n")
                    for model, tex in ign:
                        f.write(f"{model}\tTextures\\{tex}\n")
            except OSError:
                pass
            self.r.add("INFO", "Data Files", "", "", f"{len(ign)} missing normal map(s) named by models; --fix "
                                                     f"puts a flat stand-in in place; listed in {IGNORED_NORMALS_RECORD}")
        try:
            asset_health_module().check(self, sys.modules[__name__])
        except Exception as e:                      # never let the extra checks stop the scan
            self.asset_health = []
            print(f"(asset health checks failed: {e})", file=sys.stderr)
        vortex_mods = []
        if self.vortex is not None:
            try:
                vortex_mods = os.listdir(self.vortex.root)
            except OSError:
                pass
        for plugin, n in sorted(self.missing_by_plugin.items()):
            guess = original_mod_guess(plugin)
            if not guess:
                continue
            near = [d for d in vortex_mods if guess.lower() in d.lower()][:3]
            self.r.add("WARN", plugin, "", "",
                       f"{n} file(s) this plugin uses exist nowhere. Its name suggests it is a patch or a newer "
                       f"version of another mod ('{guess}'): those files usually come with the original, so install "
                       f"it (or its Meshes/Textures/Sound folders)"
                       + (f"; Vortex has: {', '.join(near)}" if near else ""))

    def _check_leveled(self):
        """Leveled lists whose entries name objects that exist nowhere: the entries are dropped from the
        winning list (in the plugin, or through the ESM patch for a master)."""
        for (tag, rid), (plugin, oid, entries) in self.lev_win.items():
            gone = {e.lower() for e in entries if e and e.lower() not in self.all_ids}
            if not gone or is_our_patch(plugin):
                continue
            msg = (f"{tag} '{oid}' lists {len(gone)} object(s) that exist nowhere: "
                   f"{', '.join(sorted(gone)[:4])}" + (" ..." if len(gone) > 4 else ""))
            self.r.add("ERROR", plugin, "", oid, msg)
            self.item_fixes.append({"plugin": plugin, "tag": tag, "id": oid, "set": {}, "npco": set(),
                                    "lev_drop": gone, "msgs": [(msg, "drop those entries from the list")]})

    def _texture_stand_ins(self, win):
        """A used object's model exists but some of its textures don't: put the real texture in from an
        undeployed Vortex folder, or a small placeholder (the model then draws instead of failing)."""
        A = self.assets
        for (sub, kind), v in win[2].items():
            if kind != "mesh" or not A.mesh_exists(v):
                continue
            for t in A.missing_textures(v):
                rel_t = re.sub(r"^[\\/]+", "", t)
                orphan = A.find_orphaned("textures", rel_t, any_ext=True)
                if orphan:
                    self.generated.append((os.path.join("Textures", os.path.splitext(rel_t)[0] + os.path.splitext(orphan)[1]),
                                           f"model '{v}'", orphan, win[1]))
                    continue
                hit = self.vortex.find("textures", rel_t, any_ext=True) if self.vortex is not None else None
                if hit:
                    rel = os.path.join("Textures", os.path.splitext(rel_t)[0] + os.path.splitext(hit[0])[1].lower())
                    self.generated.append((rel, f"model '{v}' from Vortex mod '{hit[1]}'", hit[0], win[1]))
                else:
                    self.generated.append((os.path.join("Textures", os.path.splitext(rel_t)[0] + ".dds"),
                                           f"model '{v}' ({win[1]})", None, win[1]))

    def _fallback_pool(self):
        """Working files by (record type, subtype, field), counted over the winning records."""
        if getattr(self, "_pool", None) is not None:
            return self._pool
        A = self.assets
        pool = defaultdict(Counter)
        for (tag, rid), vers in self.models.items():
            if not vers or vers[-1][3]:
                continue
            st = self.subtypes.get((tag, rid))
            vanilla = vers[0][1].lower() in ("morrowind.esm", "tribunal.esm", "bloodmoon.esm")
            for (sub, kind), v in vers[-1][2].items():
                if A.field_problem(kind, v) is None:
                    pool[(tag, st, sub)][v] += 1
                    pool[(tag, None, sub)][v] += 1
                    if vanilla:                            # the game's own objects make the plainest stand-ins
                        pool[(tag, st, sub, "vanilla")][v] += 1
        self._pool = pool
        return pool

    def _stand_in(self, tag, rid, win, msg):
        """A winning record names a file the game can't load: point it at a working one of the same
        kind (the closest name, else the most common), so the object still works. Statics and
        activators get the invisible editor marker; lights and NPCs simply lose the model; a sound
        record keeps its name and gets a silent file created there."""
        import difflib
        A = self.assets
        pool = self._fallback_pool()
        st = self.subtypes.get((tag, rid))
        new, notes = {}, []
        vers = self.models[(tag, rid)]
        for (sub, kind), v in win[2].items():
            prob = A.field_problem(kind, v)
            if not A.fatal(prob):
                continue
            real = not A.placeholder(v) and not (kind == "icon" and v.lower().endswith(".nif"))
            top0 = {"mesh": "meshes", "icon": "icons", "texture": "textures", "sound": "sound"}[kind]
            orphan = A.find_orphaned(top0, A.rel(v, top0), any_ext=kind != "mesh") if real else None
            if orphan:                                    # 0. moved away by the orphan isolator
                rel = os.path.join(top0.capitalize(), A.rel(v, top0))
                if kind != "mesh":
                    rel = os.path.splitext(rel)[0] + os.path.splitext(orphan)[1]
                self.generated.append((rel, f"{tag} '{win[4]}'", orphan, win[1]))
                notes.append("move it back from .Orphaned (TextureAudit's orphan isolator moved it)")
                continue
            if real and self.vortex is not None:          # 1. the real file, never deployed
                top = {"mesh": "meshes", "icon": "icons", "texture": "textures", "sound": "sound"}[kind]
                hit = self.vortex.find(top, A.rel(v, top), any_ext=kind != "mesh")
                if hit:
                    src_path, mod = hit
                    rel = os.path.join(top.capitalize(), A.rel(v, top))
                    if kind != "mesh" and os.path.splitext(src_path)[1].lower() != os.path.splitext(rel)[1].lower():
                        rel = os.path.splitext(rel)[0] + os.path.splitext(src_path)[1].lower()
                    self.generated.append((rel, f"{tag} '{win[4]}' from Vortex mod '{mod}'", src_path, win[1]))
                    notes.append(f"copy '{os.path.relpath(src_path, self.vortex.root)}' (in Vortex, never deployed) "
                                 f"into Data Files")
                    continue
            if kind == "mesh" and A.placeholder(v) and sub == "MODL" and tag not in ("NPC_", "LIGH"):
                new[sub] = PLACEHOLDER_COIN          # unfinished object that is placed or used: shown as a coin
                notes.append(f"give it the coin model {PLACEHOLDER_COIN} (its model was never set)")
                continue
            if real and kind in ("mesh", "icon"):
                # 2. a stand-in FILE at the exact path the record names; the plugin is not changed, so the
                # real file (a mod installed later) simply replaces it
                here = os.path.dirname(os.path.abspath(__file__))
                if kind == "icon":
                    rel = os.path.join("Icons", os.path.splitext(A.rel(v, "icons"))[0] + ".dds")
                    src, what = None, "a placeholder icon"
                elif v.lower().endswith(".nif"):
                    rel = os.path.join("Meshes", A.rel(v, "meshes"))
                    dummy = (DUMMY_MARKER_NIF if tag in ("STAT", "ACTI", "LIGH") else
                             DUMMY_ANIM_NIF if tag in ("NPC_", "CREA") and sub == "MODL" and tag == "NPC_" else DUMMY_NIF)
                    src = os.path.join(here, dummy)
                    what = {DUMMY_MARKER_NIF: "the invisible editor marker", DUMMY_ANIM_NIF: "the default skeleton",
                            DUMMY_NIF: "a small coin"}[dummy]
                else:
                    rel = None
                if rel and (src is None or os.path.exists(src)):
                    self.generated.append((rel, f"{tag} '{win[4]}'", src, win[1]))
                    notes.append(f"put {what} at '{v}' (the record is left as it is)")
                    continue
            older = next((w for w in reversed(vers[:-1]) if not w[3] and w[2].get((sub, kind))
                          and A.field_problem(kind, w[2][(sub, kind)]) is None), None)
            if older:                                     # 2. what an earlier version of the record uses
                new[sub] = older[2][(sub, kind)]
                notes.append(f"use '{new[sub]}', the {A.KIND_NAMES[kind]} {older[1]} gives it")
                continue
            if real and kind != "icon":
                self.missing_by_plugin[win[1]] += 1
            if kind == "icon" and real:                   # 3. a dummy icon at the path the record names
                self.generated.append((os.path.join("Icons", os.path.splitext(A.rel(v, "icons"))[0] + ".dds"),
                                       f"{tag} '{win[4]}'", None, win[1]))
                notes.append(f"create a placeholder icon at '{v}'")
                continue
            if tag == "SOUN" and kind == "sound" and not A.placeholder(v):
                self.generated.append((os.path.join("Sound", A.rel(v, "sound")), f"sound record '{win[4]}'", None, win[1]))
                notes.append(f"create a silent '{v}'")
                continue
            if sub == "MODL" and tag in ("LIGH", "NPC_"):
                new[sub] = None
                notes.append("remove the model (a light works without one)" if tag == "LIGH"
                             else "remove the model (the NPC uses the default skeleton)")
                continue
            if sub == "MODL" and tag in ("STAT", "ACTI") and A.mesh_exists("EditorMarker.nif"):
                new[sub] = "EditorMarker.nif"
                notes.append("use the invisible editor marker as its model")
                continue
            cands = pool.get((tag, st, sub)) or pool.get((tag, None, sub))
            if not cands:
                if kind == "mesh" and real and v.lower().endswith(".nif"):   # a small coin at that path
                    self.generated.append((os.path.join("Meshes", A.rel(v, "meshes")), f"{tag} '{win[4]}'",
                                           None, win[1]))
                    notes.append(f"create a placeholder model (a small coin) at '{v}'")
                continue
            base = os.path.basename(v.replace("\\", "/")).lower()
            names = {os.path.basename(c.replace("\\", "/")).lower(): c for c in cands}
            close = difflib.get_close_matches(base, list(names), n=1, cutoff=0.6) if not A.placeholder(v) else []
            plain = pool.get((tag, st, sub, "vanilla"))
            pick = names[close[0]] if close else (plain or cands).most_common(1)[0][0]
            new[sub] = pick
            notes.append(f"use '{pick}' as its {A.KIND_NAMES[kind]}")
        if not new and not notes:
            self.r.add("WARN", win[1], "", win[4], msg + " (no stand-in of that kind found)")
            return
        self.r.add("ERROR", win[1], "", win[4], msg)
        if new:
            self.item_fixes.append({"plugin": win[1], "tag": tag, "id": win[4], "set": new, "npco": set(),
                                    "msgs": [(msg, "; ".join(notes))]})

    SCRIPT_FILE_RE = re.compile(r'\b(StreamMusic|PlayBink|Say)\b\s*,?\s*"([^"\n]+)"', re.I)

    def _check_script_assets(self):
        """Files scripts play: StreamMusic (Music), Say (Sound), PlayBink (Video). Found only when the
        line runs, so a missing one is a WARN on the script; scripts are never changed."""
        kinds = {"streammusic": "music", "playbink": "video", "say": "sound"}
        for sid, (plugin, sname, text) in self.script_src.items():
            seen = set()
            for line in text.splitlines():
                code = line.split(";", 1)[0]
                for m in self.SCRIPT_FILE_RE.finditer(code):
                    kind = kinds[m.group(1).lower()]
                    path = m.group(2).strip()
                    if (kind, path.lower()) in seen:
                        continue
                    seen.add((kind, path.lower()))
                    prob = self.assets.field_problem(kind, path)
                    if not prob:
                        if kind == "sound" and SOUND_ROOTS:
                            bad = sound_file_problem(os.path.join("sound", path.strip().replace("/", os.sep)))
                            if bad:
                                self.r.add("ERROR", plugin, "", sname,
                                           f"script plays 'Sound\\{path}', which {bad}: the game can freeze or crash "
                                           f"when that line runs (scripts aren't changed: repair or replace the file)")
                        continue
                    if kind in ("sound", "music") and not self.assets.placeholder(path):
                        top = "Sound" if kind == "sound" else "Music"
                        rel = os.path.join(top, self.assets.rel(path, top.lower()))
                        hit = self.vortex.find(top.lower(), self.assets.rel(path, top.lower()), any_ext=True) \
                            if self.vortex is not None else None
                        if hit:
                            if os.path.splitext(hit[0])[1].lower() != os.path.splitext(rel)[1].lower():
                                rel = os.path.splitext(rel)[0] + os.path.splitext(hit[0])[1].lower()
                            self.generated.append((rel, f"script {sname} ({plugin}), from Vortex mod '{hit[1]}'", hit[0], plugin))
                            what = f"--fix copies it from Vortex mod '{hit[1]}', where it was never deployed"
                        else:
                            self.generated.append((rel, f"script {sname} ({plugin})", None, plugin))
                            self.missing_by_plugin[plugin] += 1
                            what = "--fix creates a silent stand-in there"
                        self.r.add("WARN", plugin, f"script {sname}", "", f"{m.group(1)}: {prob} ({what})")
                    elif kind == "video":
                        hit = self.vortex.find("video", self.assets.rel(path, "video")) if self.vortex is not None else None
                        if hit:
                            self.generated.append((os.path.join("Video", self.assets.rel(path, "video")),
                                                   f"script {sname} ({plugin}), from Vortex mod '{hit[1]}'", hit[0], plugin))
                            self.r.add("WARN", plugin, f"script {sname}", "",
                                       f"{m.group(1)}: {prob} (--fix copies it from Vortex mod '{hit[1]}')")
                        else:
                            self.r.add("INFO", plugin, f"script {sname}", "",
                                       f"{m.group(1)}: {prob} (the game skips the video)")
                    else:
                        self.r.add("WARN", plugin, f"script {sname}", "",
                                   f"{m.group(1)}: {prob} (the game skips it when this line runs)")

    LUA_ASSET_RE = re.compile(r'["\']([^"\'\n]{3,200}\.(?:nif|dds|tga|bmp|kf))["\']', re.I)
    LUA_DIR_RE = re.compile(r'["\']([A-Za-z0-9_ #\-]{3,40})[\\/]+[^"\'\n]*["\']')
    SHARED_DIRS = {"a", "b", "c", "d", "e", "f", "i", "k", "l", "m", "n", "o", "r", "s", "w", "x", "bm", "xbase",
                   "base", "tr", "pc", "sky", "oaab", "anim", "animation", "textures", "meshes"}

    def _check_lua_orphans(self):
        """Meshes and textures MWSE Lua mods load by name (no plugin names them, so TextureAudit's orphan
        isolator moved them to .Orphaned and the game says 'Model Load Error ... cannot load file'):
        --fix moves them back, the exact files and every file in a folder a Lua mod builds names in."""
        A = self.assets
        if not A.orphaned or not self.ini_path:
            return
        mwse = os.path.join(os.path.dirname(self.ini_path), "Data Files", "MWSE")
        exact, dirs = set(), set()
        for dp, _d, fns in os.walk(mwse):
            for fn in fns:
                if not fn.lower().endswith((".lua", ".json", ".toml")):
                    continue
                try:
                    with open(os.path.join(dp, fn), encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except OSError:
                    continue
                for s in self.LUA_ASSET_RE.findall(text):
                    s = s.replace("/", "\\").replace("\\\\", "\\").lower().lstrip("\\")
                    for pre in ("data files\\", "meshes\\", "textures\\"):
                        if s.startswith(pre):
                            s = s[len(pre):]
                    exact.add(s)
                    if "\\" in s and s.split("\\")[0] not in self.SHARED_DIRS:
                        dirs.add(s.split("\\")[0])
                for s in self.LUA_DIR_RE.findall(text):
                    s = s.strip().lower()
                    if s not in self.SHARED_DIRS:
                        dirs.add(s)
        back = []
        for (top, rel), full in A.orphaned.items():
            if top not in ("meshes", "textures") or not os.path.splitext(rel)[1]:
                continue
            if rel in exact or rel.split("\\")[0] in dirs:
                back.append((os.path.join(top.capitalize(), rel), "an MWSE Lua mod", full))
        if back:
            self.generated += back
            self.r.add("WARN", "Data Files", "", "",
                       f"{len(back)} mesh/texture file(s) that MWSE Lua mods load by name are in .Orphaned (moved there "
                       f"by TextureAudit's orphan isolator); the game can't find them ('Model Load Error'). "
                       f"--fix moves them back")

    def _check_big_textures(self):
        """Loose textures with an edge over 2048: a 32-bit Morrowind has 4 GB of address space, and a
        4096x4096 texture takes four times what a 2048x2048 one does. --fix keeps each file's own
        2048 version (its mipmaps) and drops the larger levels; the originals are kept."""
        A = self.assets
        self.texture_reductions = []
        stuck = []
        for full, rel, size in A.big_textures:
            try:
                with open(full, "rb") as f:
                    head = f.read(148)
            except OSError:
                continue
            info = dds_info(head)
            if info is None:
                continue
            w, h, mips, _hdr, _b, _bpp = info
            if max(w, h) <= TEXTURE_MAX_EDGE:
                continue
            k = 0
            while max(w >> k, 1) > TEXTURE_MAX_EDGE or max(h >> k, 1) > TEXTURE_MAX_EDGE:
                k += 1
            if mips <= k:
                stuck.append(rel)
                continue
            self.texture_reductions.append((full, rel, w, h, size))
        if self.texture_reductions:
            total = sum(t[4] for t in self.texture_reductions)
            self.r.add("WARN", "Data Files", "", "",
                       f"{len(self.texture_reductions)} texture(s) are larger than {TEXTURE_MAX_EDGE} on an edge "
                       f"({total / 2**30:.1f} GB); in a 32-bit game they use up the 4 GB of memory. --fix reduces "
                       f"them to {TEXTURE_MAX_EDGE} (from the smaller copies inside each file), keeping the "
                       f"originals; --restore-textures puts them back")
        if stuck:
            self.r.add("INFO", "Data Files", "", "",
                       f"{len(stuck)} texture(s) over {TEXTURE_MAX_EDGE} have no smaller copies inside (mipmaps) and "
                       f"are left as they are, e.g. {stuck[0]}")

    def _check_text_keys(self):
        """Loose .nif/.kf files whose animation text keys use Unix line endings (LF without CR): a hard crash
        when the animation plays. --fix rewrites the keys with CR LF; the original is kept."""
        A = self.assets
        self.text_key_fixes = []
        try:
            asset_health_module()              # the asset health pass reads every model once and does this too
            return
        except Exception:
            pass
        print("Checking animation text keys in loose meshes for Unix line endings...", file=sys.stderr)
        for rel, full in A.mesh_loose.items():
            if not rel.endswith((".nif", ".kf")):
                continue
            try:
                with open(full, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            if TEXT_KEY_TAG not in data:
                continue
            bad, _new = nif_text_keys_lf(data)
            if bad:
                self.text_key_fixes.append((full, "meshes\\" + rel, bad))
        for full, rel, bad in self.text_key_fixes:
            self.r.add("ERROR", "Data Files", "", "",
                       f"{rel}: {bad} animation text key(s) use Unix line endings (LF without CR); the game can "
                       f"crash when the animation plays. --fix rewrites them with Windows line endings (original kept)")

    def _check_ini_assets(self):
        """Morrowind.ini's fonts ([Fonts] Font N = name -> Fonts\\name.fnt) and sky textures
        ([Weather ...] ... Texture = file -> Textures)."""
        ini = self.ini_path
        if not ini or not os.path.isfile(ini):
            return
        try:
            secs = read_ini_sections(ini)
        except OSError:
            return
        for k, v in secs.get("fonts", []):
            if k.lower().startswith("font") and v.strip():
                f = v.strip() if v.strip().lower().endswith(".fnt") else v.strip() + ".fnt"
                prob = self.assets.field_problem("font", f)
                if prob:
                    self.r.add("WARN", "Morrowind.ini", "[Fonts]", k, prob)
        for sec, items in secs.items():
            if not sec.startswith("weather"):
                continue
            for k, v in items:
                if "texture" in k.lower() and v.strip():
                    prob = self.assets.field_problem("texture", v.strip())
                    if prob:
                        self.r.add("WARN", "Morrowind.ini", f"[{sec}]", k, prob)

    def _check_cell_region(self, body, name, key, label):
        """An exterior cell names its region (RGNN) when its plugin loads; a region nothing has defined
        by then gives "Unable to find Region 'X' in Load for Cell 'Y'". Usually a plugin made for an
        older version of its master, which has since renamed the region. Fix: use the region the
        newest earlier version of the cell has, or drop RGNN if no earlier version has a working one."""
        if key[0] != "e":
            return
        rg = first_sub(body, b"RGNN")
        hist = self.cell_regions.setdefault(key, [])
        region = cstr(rg) if rg is not None else None
        if region and region.lower() not in self.ids["REGN"]:
            fixed, src = None, None
            for p2, r2 in reversed(hist):
                if r2 is None or r2.lower() in self.ids["REGN"]:
                    fixed, src = r2, p2
                    break
            if src and fixed:
                action = f"use '{fixed}', the region {src} gives this cell"
            elif src:
                action = f"remove it ({src}, the version it overrides, gives the cell no region)"
            else:
                action = "remove it (no earlier version of this cell has a working region)"
            lab = (label or "").strip()
            shown = lab if lab and not lab.startswith("(") else f"Wilderness {lab}"
            msg = f"cell '{shown}': region '{region}' isn't defined when this plugin loads"
            self.r.add("ERROR", name, "", "", msg)
            self.item_fixes.append({"plugin": name, "tag": "CELL", "id": shown, "key": key,
                                    "set": {"RGNN": fixed}, "npco": set(), "msgs": [(msg, action)]})
            region = fixed
        hist.append((name, region))

    def _check_item_refs(self):
        """The winning version of each object: does its script, enchantment and inventory exist?
        A stale override (e.g. a price or balance mod made for an older version of its master) often
        names an enchantment or script the master has since renamed or removed. Fix: take the field
        from the newest earlier version that still works, or drop it if no version has a working one;
        inventory entries for items that don't exist are dropped."""
        r = self.r
        targets = {"ENAM": ("ENCH", "enchantment"), "SCRI": ("SCPT", "script")}
        for rid, defs in self.obj_refs.items():
            plugin, tag, oid, refs = defs[-1]
            if refs is None or rid not in self.all_ids:
                continue
            setf, drop, msgs = {}, [], []
            for field, (ttag, what) in targets.items():
                val = refs.get(field)
                if not val or val.lower() in self.ids[ttag]:
                    continue
                fixed, src = None, None
                for p2, _t2, _o2, refs2 in reversed(defs[:-1]):
                    if refs2 is None:
                        continue
                    v2 = refs2.get(field)
                    if not v2 or v2.lower() in self.ids[ttag]:
                        fixed, src = v2, p2
                        break
                setf[field] = fixed
                others = [d[0] for d in defs[:-1] if d[3] is not None]
                if src and fixed:
                    action = f"use '{fixed}', the {what} {src} gives it"
                elif src:
                    action = f"remove it ({src}, the version it overrides, has no {what})"
                elif others:
                    action = f"remove it (no earlier version has a working {what})"
                else:
                    action = f"remove it (no other plugin defines {oid}, so there is no working {what} to take)"
                msgs.append((f"{tag} '{oid}': {what} '{val}' doesn't exist", action))
            for item in refs.get("NPCO", ()):
                if item.lower() not in self.all_ids and item.lower() not in drop:
                    drop.append(item.lower())
                    msgs.append((f"{tag} '{oid}': inventory item '{item}' doesn't exist", "remove it from the inventory"))
            if not msgs:
                continue
            for msg, action in msgs:
                r.add("ERROR", plugin, "", "", msg)
            self.item_fixes.append({"plugin": plugin, "tag": tag, "id": oid, "set": setf,
                                    "npco": set(drop), "msgs": msgs})

    def _check_scripts(self):
        """Object IDs a script names that don't exist once everything is loaded (the game logs
        'Unable to find referenced object' for these). Reported, not fixed: scripts are compiled."""
        r = self.r
        known = set(self.all_ids) | {"player", "playersavegame"}
        keywords = {"to", "if", "elseif", "else", "endif", "set", "and", "or", "not", "return",
                    "begin", "end", "while", "endwhile", "short", "long", "float"}
        for sid, (plugin, sname, text) in self.script_src.items():
            seen, timed = set(), set()
            locals_ = set(self.script_locals.get(sid, ()))
            for mt in re.finditer(r"^\s*(?:short|long|float)\s+(\w+)", text, re.I | re.M):
                locals_.add(mt.group(1).lower())       # MWSE keeps references in locals: ref->AddItem
            for line in text.splitlines():
                code = line.split(";", 1)[0]
                if not code.strip():
                    continue
                def outside_quotes(mt):
                    return code.count('"', 0, mt.start()) % 2 == 0   # the match starts in code, not text
                found = [((mt.group(1) or mt.group(2)), True) for mt in self.RE_ARROW.finditer(code)
                         if outside_quotes(mt)]
                found += [((mt.group(2) or mt.group(3)), False) for mt in self.RE_OBJARG.finditer(code)
                          if outside_quotes(mt)
                          # "set position to 0" is a variable named like a function, not a call
                          and not code[:mt.start()].rstrip().lower().endswith("set")]
                for obj, arrow in found:
                    obj = obj.strip()
                    if obj.lower() in self.missing_objects and arrow:
                        self.missing_objects[obj.lower()]["arrow"] = True
                    if arrow and obj.lower() not in locals_ and obj.lower() not in keywords \
                            and obj.lower() not in ("player", "playersavegame"):
                        t = self.arrow_targets.setdefault(obj.lower(), {"id": obj, "used_by": []})
                        if (plugin, sname) not in t["used_by"]:
                            t["used_by"].append((plugin, sname))
                    o = obj.lower()
                    if o in known and o not in locals_ and o not in keywords \
                            and o not in ("player", "playersavegame") and (o, arrow) not in timed:
                        timed.add((o, arrow))
                        self._script_timing(plugin, sname, sid, obj, arrow)
                    if not o or o in known or o in seen or o.replace(".", "").isdigit() \
                            or o in keywords or o in locals_:
                        continue
                    seen.add(o)
                    if o in self.deleted_by_obj:
                        why = (f"'{self.defined_by_obj.get(o, '?')}' defines it but "
                               f"'{self.deleted_by_obj[o]}' deletes it")
                    elif o in self.script_locals or o in self.ids.get("GLOB", ()):
                        continue                       # a script or global name, not an object
                    else:
                        why = "no loaded plugin defines it (a required mod may be missing)"
                        miss = self.missing_objects.setdefault(o, {"id": obj, "arrow": False, "used_by": []})
                        miss["arrow"] |= arrow
                        miss["used_by"].append((plugin, sname))
                    r.add("WARN", plugin, f"script {sname}", obj,
                          f"script names object '{obj}', which doesn't exist: {why}")

    PLACEABLE = ITEM_TAGS | ACTOR_TAGS | {"ACTI", "CONT", "DOOR", "STAT", "LEVC"}

    def _trace_record(self, name, tag, flags, body):
        """--trace: report every record in this plugin that defines, places, deletes or mentions a traced id."""
        low = bytes(body).lower()
        hits = [t for t in self.trace if t.encode(ENC, MW_ERRORS) in low]
        if not hits:
            return
        at = f"[{len(self.loaded) + 1:>3}] {name}"
        deleted = bool(flags & 0x20) or has_sub(body, b"DELE")
        rid = record_id(tag, body)
        for t in hits:
            if rid and rid[1] == t and tag != "CELL":
                self.trace_log.append((t, f"{at}: {'DELETES' if deleted else 'defines'} {tag} '{t}'"
                                      + (" (references persist)" if flags & HDR_PERSISTENT else "")))
            elif tag == "CELL":
                key, label = cell_key(body)
                masters = [m.lower() for m in self.masters.get(name.lower(), [])]
                head, pers, _nam0, temp = split_cell(body)
                for group, blocks in (("persistent", pers), ("temporary", temp)):
                    for b in blocks:
                        obj = next((cstr(d) for n, d in b if n == "NAME"), "")
                        if obj.lower() != t:
                            continue
                        bk = block_key(b, masters, name.lower())
                        gone = any(n == "DELE" for n, _d in b)
                        src = f"ref #{bk[1]} of {bk[0]}" if bk else "moved reference"
                        self.trace_log.append((t, f"{at}: cell '{label}': {'DELETES' if gone else 'places'} '{obj}' "
                                              f"({group}, {src})"))
            elif tag == "SCPT":
                hd = first_sub(body, b"SCHD")
                sname = cstr(hd[:32]) if hd else "?"
                tx = first_sub(body, b"SCTX")
                if tx is None:
                    self.trace_log.append((t, f"{at}: script '{sname}' mentions '{t}' in its compiled data, but has no "
                                          f"source text (the checker reads source text, so it can't see this use)"))
                else:
                    for line in tx.decode(ENC, MW_ERRORS).splitlines():
                        if t in line.lower():
                            self.trace_log.append((t, f"{at}: script '{sname}': {line.strip()}"))
            else:
                self.trace_log.append((t, f"{at}: {tag} {rid[1] if rid else ''} mentions '{t}'"))

    def _script_timing(self, plugin, sname, sid, obj, arrow):
        """The game resolves a script's references when the script loads: an object it names must be
        defined by then, and one it acts on ("X->") must already have a placed copy."""
        r = self.r
        o = obj.lower()
        at = self.script_at.get(sid)
        if at is None or is_our_patch(plugin) or self.all_ids.get(o) not in self.PLACEABLE:
            return
        esp = plugin.lower().endswith(FIXABLE_EXT)
        d_at, d_by = self.first_def_at.get(o, (None, None))
        late_def = d_at is not None and d_at > at
        p_at, p_by = self.first_persist_at.get(o, (None, None))
        late_place = arrow and p_at is not None and p_at > at
        only_temp = arrow and p_at is None and o in self.first_placed_at
        if not (late_def or late_place or only_temp):
            return
        if only_temp:
            t_by = self.first_placed_at[o][1]
            what = (f"acts on '{obj}', but every placed copy of it is temporary (the first is in '{t_by}'); "
                    f"a script can only act on a persistent copy")
        elif late_place:
            what = (f"acts on '{obj}', but no persistent copy of it is placed yet when this script loads: the "
                    f"first is placed by '{p_by}', which loads later")
        else:
            what = f"names '{obj}', which isn't defined yet when this script loads: '{d_by}' defines it and loads later"
        msg = what + "; the game logs 'Unable to find referenced object'"
        if not esp:
            r.add("WARN", plugin, f"script {sname}", obj, msg + " (this script is in a master; a patch loads too "
                                                             "late to help, only load order can)")
            return
        r.add("WARN", plugin, f"script {sname}", obj, msg)
        if late_def or (self.first_def_at.get(o, (0,))[0] >= self.first_esp_at()):
            last, tag = self.last_def_obj.get(o, (d_by, self.all_ids[o]))
            need = self.early_needed.setdefault(o, (last, tag, []))
            need[2].append(plugin)
        if late_place or only_temp:
            e = self.early_placed.setdefault(o, {"id": obj, "by": p_by if late_place else
                                                 f"{self.first_placed_at[o][1]} (temporary copies only)",
                                                 "users": []})
            e["users"].append(plugin)

    def first_esp_at(self):
        """Load index of the first .esp: everything before it loads before the ESM patch."""
        for i, n in enumerate(self.loaded):
            if n.endswith(FIXABLE_EXT):
                return i
        return len(self.loaded)

    def _check_placed(self):
        """A script that acts on an object ("X->...") needs a copy of it placed in the world;
        the game logs 'Unable to find referenced object' when none is."""
        r = self.r
        for o, v in sorted(self.arrow_targets.items()):
            if self.placed.get(o, 0) > 0 or o in self.missing_objects:
                continue                       # placed, or already reported as not defined at all
            if self.all_ids.get(o) not in self.PLACEABLE:
                continue
            gone = self.unplaced_by.get(o)
            why = (f"'{gone}' deleted the last placed copy" if gone
                   else f"'{self.defined_by_obj.get(o, '?')}' defines it but no mod places it")
            self.unplaced[o] = dict(v, tag=self.all_ids[o], why=why)
            for plugin, sname in v["used_by"]:
                r.add("WARN", plugin, f"script {sname}", v["id"],
                      f"script acts on '{v['id']}', but no copy of it is placed in the world: {why}")

    def _check_missing_placed(self):
        """The game resolves a placed reference when its plugin loads: the object must exist by then
        ('Missing object ... for reference during cell ... load')."""
        r = self.r
        order = {n: i for i, n in enumerate(self.loaded)}
        for plugin, off, label, v, obj in self.missing_placed:
            if is_our_patch(plugin):
                continue
            o = obj.lower()
            esp = plugin.lower().endswith(FIXABLE_EXT)
            pi = order.get(plugin.lower())
            ev = [e for e in self.obj_events.get(o, []) if pi is not None and e[0] < pi]
            if o in self.all_ids and ev and ev[-1][3]:
                # it existed, but a plugin loading in between deleted the whole record
                _di, d_by, d_tag, _d = ev[-1]
                again = next((e[1] for e in self.obj_events.get(o, []) if e[0] > pi and not e[3]), None)
                msg = (f"places '{obj}', but '{d_by}' (loading earlier) deletes that {d_tag} record"
                       + (f", and only '{again}' (loading later) defines it again" if again else "")
                       + "; the game logs 'Missing object ... during cell load'")
                if d_by.lower().endswith(FIXABLE_EXT) and not is_our_patch(d_by):
                    r.add("ERROR", plugin, f"cell {label}", obj, msg)
                    self.undelete.setdefault((d_by, d_tag, o), [obj, set()])[1].add(plugin)
                else:
                    r.add("ERROR", plugin, f"cell {label}", obj, msg + " (the deletion is in a master; not changed)")
                continue
            if o in self.all_ids:
                q = self.defined_by_obj.get(o, "?")
                last, tag = self.last_def_obj.get(o, (q, self.all_ids[o]))
                msg = (f"places '{obj}', which isn't defined yet when this plugin loads: '{q}' defines it and "
                       f"loads later; the game logs 'Missing object ... during cell load'")
                if esp:
                    need = self.early_needed.setdefault(o, (last, tag, []))
                    need[2].append(plugin)
                    r.add("ERROR", plugin, f"cell {label}", obj, msg)
                elif q.lower().endswith(FIXABLE_EXT):
                    r.add("ERROR", plugin, f"cell {label}", obj,
                          msg + f" (this is a master, and only '{q}', an .esp, defines it: .esp files always load "
                                f"after masters, so a mod that defines it as a master is missing)")
                else:
                    r.add("ERROR", plugin, f"cell {label}", obj,
                          msg + f" (this is a master: '{q}' must load before it)")
                continue
            gone = self.deleted_by_obj.get(o)
            why = f"'{gone}' deletes it" if gone else "no loaded mod defines it"
            msg = f"places '{obj}', which doesn't exist ({why}); the game logs 'Missing object ... during cell load'"
            if esp:
                desc = ("removed the edit, so the master's own object is used again" if v >> 24
                        else "removed the reference (the game skips it anyway)")
                r.add("ERROR", plugin, f"cell {label}", obj, msg, fix=(off, ("drop_ref", v), desc))
            else:
                r.add("ERROR", plugin, f"cell {label}", obj, msg + " (in a master; not changed)")
        for (d_by, d_tag, o), (obj, placers) in self.undelete.items():
            dmsg = (f"{d_tag} '{obj}': this plugin deletes the record, but {', '.join(sorted(placers))} "
                    f"(loading later) still place{'s' if len(placers) == 1 else ''} it")
            r.add("ERROR", d_by, "", "", dmsg)
            self.item_fixes.append({"plugin": d_by, "tag": d_tag, "id": obj, "set": {}, "npco": set(),
                                    "drop_record": True,
                                    "msgs": [(dmsg, "remove the deletion, so the object exists for them")]})

    def _master_guard(self):
        """Patches made for a different master than the installed one (mwdialog_mastercheck): their header
        size and dead references are not 'repaired' (that would hide the mismatch), only reported."""
        self.master_verdicts = {}
        if getattr(self, "args_data_dir", None) is None or getattr(getattr(self, "args", None), "no_master_guard", False):
            return
        try:
            mc = mastercheck_module()
            self.master_verdicts = mc.check(self, sys.modules[__name__], getattr(self, "args", None))
            bad = mc.mismatched(self.master_verdicts, getattr(getattr(self, "args", None), "mismatch_threshold", None)
                                or mc.DIFFERENT_AT)
        except Exception as e:                 # never let it stop the scan
            print(f"(master check failed: {e})", file=sys.stderr)
            return
        self.mismatched_plugins = bad
        if bad:
            self.item_fixes = [f for f in self.item_fixes if str(f.get("plugin", "")).lower() not in bad]
            self.r.fixes = [f for f in self.r.fixes if not (str(f[0]).lower() in bad
                                                             and f[2][0] in ("drop_ref", "move_ref", "sync_master"))]

    def _check_headers(self):
        """tes3cmd header --synchronize: record counts and master sizes."""
        r = self.r
        for plugin, claimed in self.hedr_count.items():
            real = self.real_count.get(plugin)
            if real is None or real == claimed or is_our_patch(plugin):
                continue
            if plugin.lower().endswith(FIXABLE_EXT):
                r.add("ERROR", plugin, "", "", f"header says {claimed} record(s), the file has {real}",
                      fix=(0, ("fix_count",), f"set the header's record count to {real}"))
            else:
                r.add("INFO", plugin, "", "", f"header says {claimed} record(s), the file has {real} (a master; not changed)")
        for plugin, master, expected, actual in self.size_mismatch:
            if is_our_patch(plugin):
                continue
            msg = f"master '{master}' has changed size since this plugin was saved; the game warns at startup"
            if not plugin.lower().endswith(FIXABLE_EXT):
                r.add("INFO", plugin, "", "", msg + " (a master; not changed)")
            elif getattr(self, "master_verdicts", {}).get((plugin.lower(), master.lower()), {}).get("kind") == "different mod":
                v = self.master_verdicts[(plugin.lower(), master.lower())]
                r.add("WARN", plugin, "", "", msg + f"; not synced: it looks made for a different '{master}' "
                                                   f"(confidence {int(round(v['confidence'] * 100))}%), so the size "
                                                   f"is the evidence, not the error")
            elif (plugin.lower(), master.lower()) in self.ref_error_masters:
                # the mismatch may be the only hint that this plugin no longer lines up with its master
                r.add("WARN", plugin, "", "", msg + "; not synced, because some of its references don't line up "
                                                   "with that master (fix those first)")
            else:
                r.add("ERROR", plugin, "", "", msg,
                      fix=(0, ("sync_master", master, actual),
                           f"synced the size recorded for '{master}' ({expected} -> {actual}); its references all "
                           f"line up with the current master"))

    def _track_multipatch_cell(self, body, name, key):
        """tes3cmd multipatch: fog-bugged interiors and reverted exterior cell names."""
        if key is None:
            return
        d = first_sub(body, b"DATA")
        nm = first_sub(body, b"NAME")
        if d is None or len(d) < 12:
            return
        try:
            self.cell_heads[key] = [(n, bytes(x)) for n, x in split_cell(body)[0]]
        except FormatError:
            pass
        flags = struct.unpack_from("<I", d)[0]
        if key[0] == "i":
            if flags & 0x80:                       # "behave like exterior": no fog bug
                return
            ambi = first_sub(body, b"AMBI")
            if ambi is None or len(ambi) < 16:
                return
            fog_data, fog_ambi = struct.unpack_from("<f", d, 8)[0], struct.unpack_from("<f", ambi, 12)[0]
            if fog_data == 0.0 or fog_ambi == 0.0:
                self.fogcells[key[1]] = (name, bytes(nm or b"\0"), bytes(d), bytes(ambi))
            else:
                self.fogcells.pop(key[1], None)    # a later plugin corrected it
            return
        cname = cstr(nm or b"").strip()            # a name of only spaces is no name (CS artifact)
        coord = (key[1], key[2])
        t = self.rencells.get(coord)
        if t is None:
            self.rencells[coord] = {"orig": cname, "name": cname, "plug": name, "rec": None, "reverted": False}
        elif t["name"] != cname:
            if cname == t["orig"]:
                t["reverted"] = True               # a later plugin put the original name back
            elif cname:
                t.update(name=cname, plug=name, rec=(bytes(nm), bytes(d)))

    def _check_refs(self):
        """Every master reference a plugin edits must exist in that master (the game warns otherwise)."""
        r = self.r
        needed = defaultdict(set)          # master lower -> cell keys
        resolved = []
        for plugin, off, key, label, v, obj, temp in self.ref_mods:
            masters = self.masters.get(plugin.lower(), [])
            k = v >> 24
            if k > len(masters):
                continue
            m = masters[k - 1].lower()
            needed[m].add(key)
            resolved.append((plugin, off, key, label, v, obj, m, temp))
        present = {}
        for m, keys in needed.items():
            path = self.paths.get(m)
            if not path:
                continue
            try:
                data = read_plugin_bytes(path)
                for moff, tag, flags, body in iter_records(data):
                    if tag != "CELL":
                        continue
                    key, _ = cell_key(body)
                    if key in keys:
                        idx = present.setdefault((m, key), {})     # ref index -> (object id, temporary?)
                        pending, mtemp = None, False
                        for sname, sdata in iter_subs(body, moff):
                            if sname == "NAM0":
                                mtemp = True
                            elif sname == "FRMR" and len(sdata) >= 4:
                                fv = struct.unpack_from("<I", sdata)[0]
                                pending = fv if not fv >> 24 else None
                            elif sname == "NAME" and pending is not None:
                                idx[pending] = (cstr(sdata).lower(), mtemp)
                                pending = None
            except (OSError, FormatError):
                continue
        for plugin, off, key, label, v, obj, m, temp in resolved:
            if (m, key) not in present and m not in self.paths:
                continue
            master_name = self.masters[plugin.lower()][(v >> 24) - 1]
            found = present.get((m, key), {}).get(v & 0xFFFFFF)
            if found is None:
                self.ref_error_masters.add((plugin.lower(), m))
            there, mtemp = found if found else (None, None)
            if there is not None and mtemp != temp:
                # Mods often file a master's reference in the other group on purpose (e.g. a scripted object
                # a script acts on must be persistent). Moving it breaks those scripts, so only note it.
                want = "temporary" if mtemp else "persistent"
                self.persist_mismatch[plugin] += 1
                r.add("INFO", plugin, f"cell {label}", obj,
                      f"edits reference #{v & 0xFFFFFF} from '{master_name}' as {'temporary' if temp else 'persistent'}, "
                      f"but the master has it as {want} (left as the mod made it)")
                continue
            if there is None:
                r.add("ERROR", plugin, f"cell {label}", obj,
                      f"changes reference #{v & 0xFFFFFF} in master '{master_name}', which no longer exists in that cell",
                      fix=(off, ("drop_ref", v), "removed the edit to a reference the master no longer has "
                                                 "(the game already ignores it)"))
            elif there != obj.lower():
                # replacer mods swap the object at an existing reference on purpose; the game accepts it
                r.add("INFO", plugin, f"cell {label}", obj,
                      f"replaces '{there}' at reference #{v & 0xFFFFFF} in master '{master_name}'")

    def _load_dial(self, body, flags, name, off):
        r = self.r
        tname, dtype, deleted = None, None, bool(flags & 0x20)
        for sname, sdata in iter_subs(body, off):
            if sname == "NAME":
                tname = cstr(sdata)
            elif sname == "DATA" and sdata:
                dtype = sdata[0]
            elif sname == "DELE":
                deleted = True
        if not tname:
            k = self.nameless_seen[name.lower()] = self.nameless_seen.get(name.lower(), 0) + 1
            if name.lower().endswith(FIXABLE_EXT):
                new, n = PLACEHOLDER_TOPIC, 2
                while new.lower() in self.topics or new.lower() in self.placeholder_used:
                    new, n = f"{PLACEHOLDER_TOPIC} {n}", n + 1
                how = f"named the topic '{new}' so it can be found in the editor"
            else:
                # a master can't be renamed; the patch moves its responses into a topic with this name
                new = f"{PLACEHOLDER_TOPIC} ({name})" + (f" {k}" if k > 1 else "")
                how = f"moved its responses into a topic named '{new}' so they can be found in the editor"
            self.placeholder_used.add(new.lower())
            if name != PATCH_NAME:     # the patch's own nameless topic only holds deletions, on purpose
                r.add("ERROR", name, new, "", f"topic at offset {off} has no name (shown here as '{new}')",
                      fix=(off, ("set_name", new), how))
            tname, key = PLACEHOLDER_TOPIC, ""
        else:
            key = tname.lower()
        topic = self.topics.get(key)
        if dtype not in DIAL_TYPES and not deleted:
            r.add("ERROR", name, tname, "", f"topic has unknown dialogue type {dtype!r}")
        if topic is None:
            topic = Topic(tname, dtype, name)
            topic.key = key
            self.topics[key] = topic
        elif dtype is not None and topic.dtype is not None and dtype != topic.dtype and not deleted:
            r.add("ERROR", name, tname, "",
                  f"changes topic type from {DIAL_TYPES.get(topic.dtype, topic.dtype)} "
                  f"(set by {topic.source}) to {DIAL_TYPES.get(dtype, dtype)}")
        topic.deleted = deleted
        return topic

    def _load_info(self, body, flags, name, off, topic, seen):
        r = self.r
        if topic is None:
            r.add("ERROR", name, "", "", f"INFO record at offset {off} is not preceded by a DIAL topic (orphaned response)",
                  fix=(off, ("delete", "local"), "deleted orphaned response (it belongs to no topic)"))
            return
        info = Info()
        info.source, info.topic, info.dtype, info.off = name, topic.name, topic.dtype, off
        info.deleted = bool(flags & 0x20)
        info.id = None
        pending = None
        for sname, sdata in iter_subs(body, off):
            if sname == "INAM":
                info.id = cstr(sdata)
            elif sname == "PNAM":
                info.prev = cstr(sdata)
            elif sname == "NNAM":
                info.next = cstr(sdata)
            elif sname == "DATA":
                if len(sdata) >= 12:
                    _t, info.disp, info.rank, info.sex, info.pcrank = struct.unpack_from("<B3xibbb", sdata)
                else:
                    r.add("ERROR", name, topic.name, info.id, f"INFO DATA is {len(sdata)} bytes, expected 12")
            elif sname == "ONAM":
                info.actor = cstr(sdata)
            elif sname == "RNAM":
                info.race = cstr(sdata)
            elif sname == "CNAM":
                info.cls = cstr(sdata)
            elif sname == "FNAM":
                info.faction = cstr(sdata)
            elif sname == "ANAM":
                info.cell = cstr(sdata)
                self.info_cells.append((len(self.loaded), name, topic.name, info.id or "", info.cell))
            elif sname == "DNAM":
                info.pcfaction = cstr(sdata)
            elif sname == "SNAM":
                info.sound = cstr(sdata)
            elif sname == "NAME":
                info.text = sdata.decode(ENC, MW_ERRORS).rstrip("\0")
            elif sname == "SCVR":
                if pending is not None:
                    info.conditions.append((pending, None))
                pending = cstr(sdata)
            elif sname in ("INTV", "FLTV"):
                if pending is not None:
                    if len(sdata) >= 4:
                        val = struct.unpack_from("<i" if sname == "INTV" else "<f", sdata)[0]
                    else:
                        val = None
                    info.conditions.append((pending, val))
                    pending = None
            elif sname == "BNAM":
                info.result = sdata.decode(ENC, MW_ERRORS).rstrip("\0")
            elif sname == "QSTN":
                info.qstn = True
            elif sname == "QSTF":
                info.qstf = True
            elif sname == "QSTR":
                info.qstr = True
            elif sname == "DELE":
                info.deleted = True
        if pending is not None:
            info.conditions.append((pending, None))

        if not info.id:
            r.add("ERROR", name, topic.name, "", f"INFO record at offset {off} has no INAM (response ID)",
                  fix=(off, ("delete", "local"), "deleted response with no ID (nothing can reference it)"))
            return
        key = info.id.lower()
        if key in seen:
            r.add("ERROR", name, topic.name, info.id, "response ID appears twice under this topic in the same file",
                  fix=(seen[key], ("delete", "local"), "deleted the earlier duplicate copy (the game only uses the last one)"))
        seen[key] = off

        home = self.info_home.get(key)
        tkey = topic.key
        if home is not None and home != tkey:
            # IDs only need to be unique within a topic; Morrowind.esm reuses them across topics
            r.add("INFO", name, topic.name, info.id,
                  f"response ID is also used under topic '{self.topics[home].name}' (harmless)")
        else:
            self.info_home[key] = tkey
        topic.infos[key] = info
        if name.lower() not in topic.defined_by[key]:
            topic.defined_by[key].append(name.lower())
        if not info.deleted:
            topic.file_links[name.lower()][key] = (info.prev.lower(), info)

    # ---- checks on the merged result --------------------------------------

    def check(self, sound_files):
        r = self.r
        self._check_item_refs()
        self._check_script_cells()
        self._check_load_time_cells()
        self._check_cell_kind_clash()
        self._check_leveled()
        if self.assets is not None:
            self._check_models()
        self._check_refs()
        self._check_missing_placed()
        self._master_guard()
        self._check_headers()
        self._check_scripts()
        self._check_placed()
        quest_stages = defaultdict(set)
        for tkey, t in self.topics.items():
            if t.dtype == JOURNAL:
                for info in t.infos.values():
                    if not info.deleted:
                        quest_stages[tkey].add(info.disp)

        for tkey, t in self.topics.items():
            if t.deleted:
                continue
            live = [i for i in t.infos.values() if not i.deleted]
            if not live:
                r.add("INFO", t.source, t.name, "", "topic has no live responses")
            self._check_chain(t)
            stage_seen = {}
            for info in live:
                self._check_info(info, t, quest_stages, sound_files)
                if t.dtype == JOURNAL:
                    if info.disp in stage_seen:
                        r.add("INFO", info.source, t.name, info.id,
                              f"journal index {info.disp} is also used by response {stage_seen[info.disp]}")
                    else:
                        stage_seen[info.disp] = info.id

    def _check_chain(self, t):
        r = self.r
        infos = t.infos
        for key, info in infos.items():
            if info.deleted:
                continue
            for field, val, sev in (("previous (PNAM)", info.prev, "ERROR"), ("next (NNAM)", info.next, "INFO")):
                if not val:
                    continue
                target = infos.get(val.lower())
                relink = None
                if field.startswith("previous"):
                    relink = (info.off, ("relink", frozenset({key})), "re-linked to a valid previous response")
                if val.lower() == key:
                    r.add("ERROR", info.source, t.name, info.id, f"{field} link points to itself",
                          fix=relink if relink else (info.off, ("set_next", ""), "cleared self-pointing next link"))
                elif target is None:
                    r.add(sev, info.source, t.name, info.id,
                          f"{field} link points to '{val}', which does not exist in this topic", fix=relink)
                elif target.deleted:
                    if not field.startswith("previous"):
                        # the game places responses by PNAM; a stale NNAM does nothing
                        r.add("INFO", info.source, t.name, info.id, f"{field} link points to '{val}', which has been deleted")
                        continue
                    # walk back past deleted responses to the slot the deleted one occupied
                    cur, seen = val.lower(), set()
                    while cur and cur in infos and infos[cur].deleted and cur not in seen:
                        seen.add(cur)
                        cur = infos[cur].prev.lower()
                    if not cur or (cur in infos and not infos[cur].deleted and cur != key):
                        new = infos[cur].id if cur else ""
                        fix = (info.off, ("set_prev", new),
                               f"re-linked to '{new}', the response before the deleted one" if new
                               else "moved to the top of the topic, where the deleted response was")
                    else:
                        fix = (info.off, ("relink", frozenset({key})), "re-linked to a valid previous response")
                    r.add("ERROR", info.source, t.name, info.id,
                          f"{field} link points to '{val}', which has been deleted (a later plugin deleted it): "
                          f"the game's list of responses can end up in a circle, freezing it in an endless loop "
                          f"when it picks a response from this topic", fix=fix)
        # Loops in the PNAM chain. The game places each response as it loads,
        # file by file, so links from different plugins can never deadlock;
        # a plugin that re-orders master responses is normal. Only a circle
        # made entirely of one plugin's own links is a real error.
        for plugin, links in t.file_links.items():
            reported, walked = set(), set()
            for start in links:
                if start in walked:                 # an earlier walk went through here: nothing new beyond it
                    continue
                path, cur, seen_here = [], start, set()
                while cur and cur in links and cur not in seen_here and cur not in walked:
                    seen_here.add(cur)
                    path.append(cur)
                    cur = links[cur][0]
                walked |= seen_here
                if cur and cur in seen_here:
                    loop = frozenset(path[path.index(cur):])
                    if len(loop) > 1 and loop not in reported:   # self-links are reported above
                        reported.add(loop)
                        first = links[cur][1]
                        r.add("ERROR", first.source, t.name, first.id,
                              f"this plugin's own previous-entry (PNAM) links form a loop of {len(loop)} response(s)",
                              fix=(first.off, ("relink", loop), "broke the loop by re-linking to a response outside it"))

    def _exists(self, tags, value):
        return any(value.lower() in self.ids[tg] for tg in tags)

    def _cell_exists(self, value):
        v = value.lower()
        key = (len(self.cell_names), len(self.region_names))
        cache = getattr(self, "_cell_union", None)
        if cache is None or cache[0] != key:         # build the union once, not on every call
            cache = (key, sorted(self.cell_names | self.region_names))
            self._cell_union = cache
        i = bisect.bisect_left(cache[1], v)          # the first name >= v is the only one that can start with it
        return i < len(cache[1]) and cache[1][i].startswith(v)

    def _check_info(self, info, t, quest_stages, sound_files):
        r = self.r

        shared = len(set(t.defined_by.get((info.id or "").lower(), []))) > 1

        def add(sev, msg, op=None, desc=None):
            if op is not None and op[0] == "delete" and op != ("delete", "local") and shared:
                # other plugins have this response too: deleting it takes a link out of the middle of the
                # game's response chain, and a plugin still pointing at it can freeze the game in a loop.
                # One that can never play is harmless left in place.
                if sev in ("ERROR", "WARN"):
                    sev = "INFO"                 # nothing to do about it: it never plays, and stays harmless
                msg += " (left in place: other plugins have this response too, and deleting it can freeze " \
                       "the game's list of responses; it still never plays)"
                op = desc = None
            r.add(sev, info.source, t.name, info.id, msg, fix=(info.off, op, desc) if op else None)

        DELETE = ("delete",)
        never = "deleted response: its filter names something that doesn't exist, so it can never play"

        # speaker filters
        if info.actor and not self._exists(ACTOR_TAGS, info.actor):
            add("ERROR", f"speaker ID (ONAM) '{info.actor}' is not an NPC or creature", DELETE, never)
        if info.race and not self._exists({"RACE"}, info.race):
            add("ERROR", f"race filter '{info.race}' does not exist", DELETE, never)
        if info.cls and not self._exists({"CLAS"}, info.cls):
            add("ERROR", f"class filter '{info.cls}' does not exist", DELETE, never)
        if info.faction and info.faction.upper() != "FFFF" and not self._exists({"FACT"}, info.faction):
            add("ERROR", f"faction filter '{info.faction}' does not exist", DELETE, never)
        if info.pcfaction and info.pcfaction.upper() != "FFFF" and not self._exists({"FACT"}, info.pcfaction):
            add("ERROR", f"PC faction filter '{info.pcfaction}' does not exist", DELETE, never)
        if info.cell and info.cell.lower() not in self.cell_names:
            if info.cell.lower() in self.region_names:
                add("INFO", f"cell filter '{info.cell}' is a region name, not a cell; "
                            f"the game may warn 'Cell not found' at load")
            else:
                add("WARN", f"cell filter '{info.cell}' does not name an existing cell; "
                            f"the game warns 'Cell not found' at load")
        if info.rank != -1 and not info.faction:
            add("INFO", f"rank filter {info.rank} is set but there is no faction filter (checks the speaker's own faction)")
        if info.sex not in (-1, 0, 1):
            add("ERROR", f"sex filter has invalid value {info.sex}")
        if t.dtype != JOURNAL and not (0 <= info.disp <= 100):
            add("WARN", f"disposition filter {info.disp} is outside 0-100")
        if t.dtype != JOURNAL and (info.qstn or info.qstf or info.qstr):
            for flag, on in (("QSTN", info.qstn), ("QSTF", info.qstf), ("QSTR", info.qstr)):
                if on:
                    add("ERROR", f"quest flag {flag} set on a non-journal response",
                        ("drop_sub", flag), f"removed the {flag} quest flag (it does nothing outside a journal)")

        # conditions
        for raw, value in info.conditions:
            self._check_condition(info, raw, value, add)

        # result script
        if info.result:
            self._check_result(info.result, quest_stages, add)

        # voice / sound file
        if info.sound and sound_files is not None:
            p = ("sound/" + info.sound.replace("\\", "/")).lower()
            if p not in sound_files:
                if t.dtype == 1:
                    add("ERROR", f"sound file 'Sound\\{info.sound}' not found in Data Files or any loaded BSA",
                        DELETE, "deleted voice response whose sound file doesn't exist")
                else:
                    add("ERROR", f"sound file 'Sound\\{info.sound}' not found in Data Files or any loaded BSA",
                        ("drop_sub", "SNAM"), "removed the missing sound file; the text still plays")
            else:
                bad = sound_file_problem(p.replace("/", os.sep))
                if bad:
                    add("ERROR", f"sound file 'Sound\\{info.sound}' {bad}: the game can freeze or crash playing it",
                        ("drop_sub", "SNAM"), "stopped it using the broken sound file; the text still shows")

        if not info.text.strip() and t.dtype in (0, 2, 3) and not info.result.strip():
            add("INFO", "response has no text and no result script")
        if t.dtype == JOURNAL and info.qstn and not info.text.strip():
            add("ERROR", "the quest's name entry has no text (the game logs 'QuestName info in Journal ... has no "
                         "name string', and the quest has no title in the journal)",
                ("set_text", t.name), f"gave the quest its topic's name, '{t.name}'")

    @staticmethod
    def _zero_passes(op, value):
        """Would a count/index of 0 pass this comparison?"""
        return {"0": 0 == value, "1": 0 != value, "2": 0 > value,
                "3": 0 >= value, "4": 0 < value, "5": 0 <= value}[op]

    def _check_condition(self, info, raw, value, add):
        drop = ("drop_cond", raw)
        if len(raw) < 5:
            add("ERROR", f"malformed condition '{raw}'", drop, "removed the unreadable condition")
            return
        idx, ctype, _func, op, cname = raw[0], raw[1], raw[2:4], raw[4], raw[5:]
        label = CONDITION_TYPES.get(ctype)
        if idx not in "012345" or label is None or op not in COMPARE_OPS:
            add("ERROR", f"malformed condition '{raw}'", drop, "removed the unreadable condition")
            return
        if value is None:
            add("ERROR", f"condition {int(idx) + 1} ({label} {cname}) has no comparison value",
                drop, "removed the condition that has no value to compare against")
            return
        if ctype == "1":
            return
        if not cname:
            add("ERROR", f"condition {int(idx) + 1} ({label}) has no variable/ID name",
                drop, "removed the condition that names nothing")
            return
        n = cname.lower()

        def zero_based(msg, what):
            # Counts of a missing item/actor, or the index of a missing quest, are always 0.
            if self._zero_passes(op, value):
                add("ERROR", msg, drop, f"removed the condition: {what} is always 0, so it always passes")
            else:
                add("ERROR", msg, ("delete",), f"deleted response: {what} is always 0, so the condition can never pass")

        if ctype == "2" and n not in self.ids["GLOB"]:
            add("ERROR", f"condition uses global '{cname}', which does not exist", ("delete",),
                "deleted response: it depends on a global variable that doesn't exist")
        elif ctype == "4":
            jt = self.topics.get(n)
            if jt is None or jt.deleted:
                zero_based(f"condition checks journal '{cname}', which does not exist", f"the index of missing quest '{cname}'")
            elif jt.dtype != JOURNAL:
                add("ERROR", f"condition checks journal '{cname}', but that topic is a {DIAL_TYPES.get(jt.dtype)}")
        elif ctype == "5":
            if not self._exists(ITEM_TAGS, cname):
                if n in self.all_ids:
                    add("WARN", f"item condition names '{cname}', which is a {self.all_ids[n]} rather than an item")
                else:
                    zero_based(f"item condition names '{cname}', which does not exist", f"the count of missing item '{cname}'")
        elif ctype == "6":
            if not self._exists(ACTOR_TAGS, cname):
                zero_based(f"Dead condition names '{cname}', which is not an NPC or creature", f"the death count of missing actor '{cname}'")
        elif ctype in "789A":
            table = {"7": ACTOR_TAGS, "8": {"FACT"}, "9": {"CLAS"}, "A": {"RACE"}}[ctype]
            if not self._exists(table, cname):
                add("ERROR", f"{label} condition names '{cname}', which does not exist",
                    drop, f"removed the condition: nothing can be '{cname}', so '{label}' always passes")
        elif ctype == "B" and not self._cell_exists(cname):
            add("WARN", f"Not Cell condition names '{cname}', which matches no cell or region")
        elif ctype in "3C" and info.actor:
            script = self.actor_script.get(info.actor.lower())
            if script is None:
                # "Not Local" on a missing variable always passes (vanilla NoLore pattern); "Local" can never pass
                if ctype == "3":
                    add("ERROR", f"Local condition on '{cname}', but speaker '{info.actor}' has no script",
                        ("delete",), "deleted response: the speaker has no script, so this Local condition can never pass")
                else:
                    add("INFO", f"{label} condition on '{cname}', but speaker '{info.actor}' has no script")
            elif script in self.script_locals and n not in self.script_locals[script]:
                if ctype == "3":
                    add("ERROR", f"Local condition on '{cname}', which is not declared in speaker's script '{script}'",
                        ("delete",), f"deleted response: '{script}' has no variable '{cname}', so this Local condition can never pass")
                else:
                    add("INFO", f"{label} condition on '{cname}', which is not declared in speaker's script '{script}'")

    RE_ADDTOPIC = re.compile(r'\bAddTopic\b[\s,]*(?:"([^"]+)"|([^\s,;"]+))', re.I)
    RE_JOURNAL = re.compile(r'\b(?:Journal|SetJournalIndex)\b[\s,]*(?:"([^"]+)"|([^\s,;"]+))[\s,]+(-?\d+)', re.I)

    def _check_result(self, script, quest_stages, add):
        for full in script.splitlines():
            line = full.split(";", 1)[0]
            comment = ("comment", full)
            cdesc = f"commented out result-script line: {full.strip()}"
            for m in self.RE_ADDTOPIC.finditer(line):
                name = (m.group(1) or m.group(2)).strip()
                t = self.topics.get(name.lower())
                if t is None or t.deleted:
                    add("ERROR", f"result script adds topic '{name}', which does not exist", comment, cdesc)
                elif t.dtype != 0:
                    add("ERROR", f"result script adds topic '{name}', which is a {DIAL_TYPES.get(t.dtype)}, not a Topic", comment, cdesc)
            for m in self.RE_JOURNAL.finditer(line):
                name = (m.group(1) or m.group(2)).strip()
                stage = int(m.group(3))
                t = self.topics.get(name.lower())
                if t is None or t.deleted:
                    add("ERROR", f"result script sets journal '{name}', which does not exist", comment, cdesc)
                elif t.dtype != JOURNAL:
                    add("ERROR", f"result script sets journal '{name}', which is a {DIAL_TYPES.get(t.dtype)}", comment, cdesc)
                elif stage not in quest_stages.get(name.lower(), ()):
                    add("INFO", f"result script sets journal '{name}' to index {stage}, which has no entry")


# --------------------------------------------------------------------------
# Load order and archives
# --------------------------------------------------------------------------


REPAIRING_INI = []


def split_exact_groups(args):
    """[Exact] groups from the rules file that the sort can keep together but that are apart in the
    current load order (usually because one of them was resaved and got today's date, which makes
    it load last). [(source, members, [(plugin between, date)], [(member, date) with a new date])]"""
    if getattr(args, "plugins", None) or getattr(args, "openmw_cfg", None):
        return []
    game_dir = os.path.dirname(os.path.abspath(args.data_dir))
    rules_path = os.path.join(game_dir, RULES_FILE)
    if not os.path.exists(rules_path):
        return []
    exact = [r for r in parse_rules(rules_path)[0] if r[0] == "exact"]
    if not exact:
        return []
    quiet = Report()
    old_err, sys.stderr = sys.stderr, open(os.devnull, "w")
    try:
        plugins = resolve(args, quiet)[0]
    finally:
        sys.stderr.close()
        sys.stderr = old_err
    names = [n for n, _p in plugins]
    low = [n.lower() for n in names]
    paths = dict(plugins)
    _order, notes = compute_order(plugins, [exact], names)
    grid = lambda t: (int(t) - DATE_BASE) % 86400 == 0 and int(t) >= DATE_BASE
    out = []
    for src, members, problem, _missing in notes.get("exact", []):
        if problem or len(members) < 2:
            continue
        idx = [low.index(m.lower()) for m in members]
        if idx == list(range(idx[0], idx[0] + len(idx))):
            continue
        lo, hi = min(idx), max(idx)
        between = [(names[i], os.path.getmtime(paths[names[i]])) for i in range(lo, hi + 1) if i not in idx]
        fresh = [(m, os.path.getmtime(paths[m])) for m in members if not grid(os.path.getmtime(paths[m]))]
        out.append((src, members, between, fresh))
    return out


def resolve(args, report):
    """Return (list of (name, path) in load order, list of BSA paths)."""
    data_dirs = [args.data_dir]
    plugin_names, bsa_names = None, None
    preserve_order = False

    if args.plugins:
        plugin_names, preserve_order = list(args.plugins), True
    elif args.openmw_cfg:
        plugin_names, bsa_names, preserve_order = [], [], True
        with open(args.openmw_cfg, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                s = line.strip()
                if "=" not in s or s.startswith("#"):
                    continue
                k, v = (x.strip() for x in s.split("=", 1))
                v = v.strip('"')
                if k == "content":
                    plugin_names.append(v)
                elif k == "data":
                    data_dirs.append(os.path.expandvars(os.path.expanduser(v)))
                elif k == "fallback-archive":
                    bsa_names.append(v)
        if "morrowind.bsa" not in (b.lower() for b in bsa_names):
            bsa_names.insert(0, "Morrowind.bsa")
    else:
        ini = default_ini(args)
        plugin_names = read_load_order(args)
        if plugin_names is not None:
            sec = read_ini_sections(ini) if os.path.isfile(ini) else {}
            bsa_names = ["Morrowind.bsa"] + [v for k, v in sec.get("archives", []) if k.lower().startswith("archive")]
            print(f"Load order from {LOAD_ORDER_FILE}", file=sys.stderr)

    lookup = {}
    for d in reversed(data_dirs):   # later data= folders win in OpenMW; first dir is primary
        lookup.update(index_dir(d))

    if plugin_names is None:
        plugin_paths = [p for n, p in lookup.items() if n.endswith((".esm", ".esp", ".omwaddon", ".omwgame"))]
        bsa_paths = [p for n, p in lookup.items() if n.endswith(".bsa")]
    else:
        plugin_paths, bsa_paths = [], []
        total, _cut = game_files_overflow(plugin_names)
        for i, n in enumerate(plugin_names):
            p = lookup.get(n.lower())
            if p:
                plugin_paths.append(p)
                continue
            longer = [k for k in lookup if k.startswith(n.lower()) and k.endswith((".esp", ".esm"))]
            if i == len(plugin_names) - 1 and total >= INI_SECTION_LIMIT - 64 and len(longer) == 1:
                report.add("ERROR", n, "", "",
                           f"listed in the load order, but the name is cut off (the file is "
                           f"'{os.path.basename(lookup[longer[0]])}'): the [Game Files] list reached Windows' "
                           f"{INI_SECTION_LIMIT:,}-character ini section limit, so Vortex cut it here and dropped "
                           f"every plugin after it. Use fewer plugins (--auto-merge), then --add-all-esp")
            else:
                report.add("ERROR", n, "", "", "listed in the load order but not found in Data Files")
        for n in bsa_names or []:
            p = lookup.get(n.lower())
            if p:
                bsa_paths.append(p)

    if not preserve_order:
        plugin_paths = sort_vanilla(plugin_paths)
    return [(os.path.basename(p), p) for p in plugin_paths], bsa_paths, data_dirs


def grass_plugin_paths(game_dir):
    """Plugins MGE XE lists as generator-only grass (never meant to be in the load order)."""
    toml = os.path.join(game_dir, "mgeXE.toml")
    out = set()
    try:
        text = open(toml, "r", encoding="utf-8", errors="replace").read()
    except OSError:
        return out
    m = re.search(r"^\s*grass_plugins\s*=\s*\[(.*?)\]", text, re.S | re.M)
    if m:
        for q in re.findall(r"'([^']+)'|\"([^\"]+)\"", m.group(1)):
            p = q[0] or q[1]
            out.add(os.path.normcase(os.path.abspath(p)))
    return out


def run_add_all_esp(args):
    """Put every .esm/.esp in Data Files into the load order (mwdialog_load_order.txt), masters first,
    then by date."""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    current = read_load_order(args)
    if current is None:
        current = []

    grass = grass_plugin_paths(game_dir)
    away = merged_away(game_dir, data_dir)
    turned_off = {n.lower() for n in read_disabled(game_dir)}
    redundant_off = {n.lower() for n in read_redundant(game_dir)[0]}
    found, skipped, merged_skip, off_skip, red_skip = [], [], [], [], []
    for fn in os.listdir(data_dir):
        p = os.path.join(data_dir, fn)
        if not fn.lower().endswith((".esm", ".esp")) or not os.path.isfile(p):
            continue
        if os.path.normcase(os.path.abspath(p)) in grass:
            skipped.append(fn)
            continue
        if fn.lower() in away:
            merged_skip.append(fn)
            continue
        if fn.lower() in turned_off:
            off_skip.append(fn)
            continue
        if fn.lower() in redundant_off:
            red_skip.append(fn)
            continue
        found.append(p)
    order = [os.path.basename(p) for p in sort_vanilla(found)]

    on_disk = {n.lower() for n in order}
    active = {n.lower() for n in current}
    added = [n for n in order if n.lower() not in active]
    missing = [n for n in current if n.lower() not in on_disk]

    print(f"{os.path.join(game_dir, LOAD_ORDER_FILE)}")
    print(f"  {len(current)} plugins active now, {len(order)} .esm/.esp in Data Files")
    print(f"  {len(added)} to add, {len(missing)} listed but not in Data Files (dropped), "
          f"{len(skipped)} MGE XE grass plugins left out")
    for n in added:
        print(f"    + {n}")
    for n in missing:
        print(f"    - {n} (not in Data Files)")
    for n in skipped:
        print(f"    ~ {n} (grass plugin, generator only)")
    if merged_skip:
        print(f"  {len(merged_skip)} plugin(s) left out because a merged plugin replaces them ({MERGE_RECORD})")
    if off_skip:
        print(f"  {len(off_skip)} plugin(s) left out because --fix turned them off as doubled ({DISABLED_RECORD}; "
              f"--reenable puts them back)")
    if red_skip:
        print(f"  {len(red_skip)} plugin(s) left out because --redundant turned them off ({REDUNDANT_RECORD}; "
              f"--redundant-undo puts them back)")
    if len(order) > 255:
        print(f"  Note: {len(order)} plugins is over the original engine's 255 limit; MWSE is needed to load them all.")
    if not added and not missing and [n.lower() for n in current] == [n.lower() for n in order]:
        print("  Nothing to change.")
        return 0
    if args.dry_run:
        print(f"  Dry run: {LOAD_ORDER_FILE} not changed.")
        return 0
    bak = write_load_order(game_dir, order, "--add-all-esp")
    print(f"  Wrote {len(order)} plugins, masters first then by date (old list saved as {bak}).")
    return 0


STEAM_APPID = "22320"          # The Elder Scrolls III: Morrowind GOTY on Steam
PLAY_REQUEST = []              # set by main() when --play was given; the game starts after main() returns
GAME_STARTED = []              # --play on its own started the game inside main()


def launch_game(args):
    """Start Morrowind.exe directly (no Launcher), the way Vortex does.

    The Steam copy of Morrowind.exe hands itself back to Steam when it is started on its own,
    and Steam then opens its launch target, the Morrowind Launcher. Setting SteamAppId (and
    SteamGameId) in the environment tells it that Steam already started it, so it runs."""
    game_dir = os.path.dirname(os.path.abspath(args.data_dir))
    exe = os.path.join(game_dir, args.exe)
    if not os.path.isfile(exe):
        print(f"--play: {exe} not found", file=sys.stderr)
        return 2
    # the load order lives in mwdialog_load_order.txt; the game reads Morrowind.ini, so it gets the list now
    order = read_load_order(args)
    if order:                                   # a listed plugin that isn't there is left out of the ini
        lookup = index_dir(os.path.abspath(args.data_dir))
        gone = [n for n in order if n.lower() not in lookup]
        if gone:
            print(f"--play: {len(gone)} plugin(s) in {LOAD_ORDER_FILE} aren't in Data Files and are left out: "
                  + ", ".join(gone[:6]) + (" ..." if len(gone) > 6 else ""))
            order = [n for n in order if n.lower() in lookup]
    if order and not getattr(args, "play_anyway", False):
        problems = check_masters_for_play(args, order)
        if problems:
            missing = [p for p in problems if "not in the load order" in p or "isn't in Data Files" in p
                       or "not in Data Files" in p]
            late = [p for p in problems if "loads after it" in p]
            other = [p for p in problems if p not in missing and p not in late]
            print("--play: NOT starting the game. The load order has problems the game would stop on "
                  "(\"Required master file not found\") or load wrongly:", file=sys.stderr)
            if missing:
                print(f"\n  Missing masters / plugins ({len(missing)}): turn the master on (--add-all-esp), install "
                      f"it, or turn off the plugin that needs it:", file=sys.stderr)
                for p in missing:
                    print("    " + p, file=sys.stderr)
            if late:
                print(f"\n  Load order ({len(late)}): a master must load before the plugins that use it; "
                      f"--sort fixes this:", file=sys.stderr)
                for p in late:
                    print("    " + p, file=sys.stderr)
            for p in other:
                print("    " + p, file=sys.stderr)
            print("\n  (--play-anyway starts the game regardless)", file=sys.stderr)
            return 3
    ini = default_ini(args)
    if order and os.path.isfile(ini):
        if [n.lower() for n in ini_game_files(ini)] != [n.lower() for n in order]:
            bak = write_ini_game_files(ini, order)
            print(f"--play: Morrowind.ini's [Game Files] set from {LOAD_ORDER_FILE} ({len(order)} plugins; "
                  f"previous ini kept as {bak}).")
        else:
            print(f"--play: Morrowind.ini already lists the {len(order)} plugins of {LOAD_ORDER_FILE}.")
        total, _cut = game_files_overflow(order)
        if _cut is not None:
            print(f"--play: note: the list is {total:,} characters, more than the {INI_SECTION_LIMIT:,} Vortex keeps "
                  f"when it rewrites Morrowind.ini; that no longer matters as long as the game is started with "
                  f"--play (Play Morrowind.bat), which writes the whole list each time.")
    env = dict(os.environ)
    env["SteamAppId"] = env["SteamGameId"] = str(args.steam_appid)
    kwargs = {"cwd": game_dir, "env": env, "close_fds": True}
    if os.name == "nt":
        try:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"],
                                 capture_output=True, text=True, timeout=10).stdout
            if "steam.exe" not in out.lower():
                print("--play: Steam doesn't seem to be running. If the game doesn't start, start Steam first.")
        except (OSError, subprocess.SubprocessError):
            pass
        kwargs["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([exe], **kwargs)
    except OSError as e:
        print(f"--play: could not start {exe}: {e}", file=sys.stderr)
        return 2
    print(f"Started {args.exe} in {game_dir} (SteamAppId {args.steam_appid}, no Launcher).")
    return 0


SAY_SOUND_RE = re.compile(r'\b(?:say|playsound|playsoundvp|playsound3d|playsound3dvp|playloopsound3d|'
                          r'playloopsound3dvp)\b\s*,?\s*"([^"\n]+\.(?:mp3|wav))"', re.I)


def run_repair_sounds(args):
    """--repair-sounds: sound files that plugins play (dialogue, sound records, scripts) and the game can hang
    or crash on, re-saved with the same name: WAVs as 16-bit PCM, MP3s without their damaged or oversized
    tag. Needs ffmpeg. Originals go to <mod folder>\\Off\\<plugin>\\<path> first; no plugin is changed."""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    print("=" * 70 + "\nREPAIR SOUNDS\n" + "=" * 70)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("  ffmpeg isn't installed (or not on PATH): install it (winget install ffmpeg) and run this again.")
        return 2
    SOUND_ROOTS[:] = [data_dir]
    names = read_load_order(args) or []
    used = defaultdict(set)
    for n in names:
        p = os.path.join(data_dir, n)
        try:
            data = open(p, "rb").read()
        except OSError:
            continue
        for _off, tag, _fl, b in iter_records(data):
            if tag == "INFO":
                v = first_sub(b, b"SNAM")
            elif tag == "SOUN":
                v = first_sub(b, b"FNAM")
            elif tag == "SCPT":
                for x in SAY_SOUND_RE.findall((first_sub(b, b"SCTX") or b"").decode(ENC, MW_ERRORS)):
                    used[os.path.join("Sound", x.strip().replace("/", os.sep))].add(n)
                continue
            else:
                continue
            if v:
                used[os.path.join("Sound", cstr(v).strip().replace("/", os.sep))].add(n)
    print(f"  {len(used)} sound file(s) named by the active plugins; checking them...", file=sys.stderr)
    fixed, failed = [], []
    for rel, who in sorted(used.items()):
        full = os.path.join(data_dir, rel)
        if not os.path.isfile(full):
            continue                                 # in a BSA, or missing (--asset-check reports those)
        prob = sound_file_problem(rel.lower())
        if not prob:
            continue
        if args.dry_run:
            print(f"  would repair {rel}: it {prob}")
            continue
        tmp = os.path.join(game_dir, "_mwdialog_sound" + os.path.splitext(rel)[1])
        if rel.lower().endswith(".mp3"):
            cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", full, "-map_metadata", "-1",
                   "-id3v2_version", "0", "-write_xing", "0", "-c:a", "copy", tmp]
        else:
            cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", full, "-c:a", "pcm_s16le",
                   "-map_metadata", "-1", "-fflags", "+bitexact", tmp]
        try:
            ok = subprocess.run(cmd, capture_output=True).returncode == 0 and os.path.getsize(tmp) >= 64
        except OSError:
            ok = False
        if not ok:
            failed.append(rel)
            print(f"  FAILED {rel} ({prob}): ffmpeg couldn't re-save it")
            continue
        backup = backup_asset_original(data_dir, rel, plugin=sorted(who)[0], feature="sound")
        replace_asset_in_place(full, open(tmp, "rb").read())
        os.remove(tmp)
        _SOUND_PROBLEMS.pop(rel.lower(), None)
        fixed.append((rel, prob, backup))
        print(f"  repaired {rel}: it {prob}\n      original kept as {backup}")
    if fixed and not args.dry_run:
        with MT.open_log(os.path.join(game_dir, args.fix_log), "a", encoding="utf-8") as lf:
            for rel, prob, backup in fixed:
                lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {rel}: it {prob} -> re-saved under the same name; "
                         f"original kept as {backup}\n")
    print(f"\n  {len(fixed)} repaired, {len(failed)} couldn't be." if fixed or failed else "  Nothing to repair.")
    return 1 if failed else 0


# every character a Windows file name may have (@, &, apostrophes, brackets...): a NIF string is preceded by
# its length, whose last byte is 0 for any texture name, so the match can't run into the bytes before it
NIF_TEXTURE_RE = re.compile(rb"([a-zA-Z0-9_\-\\/ \.@#$%&'()+,;=\[\]{}~!]+\.(?:dds|tga|bmp))", re.I)


for _c in _NIF_TEX_CHARS:
    _NIF_TEX_OK[_c] = 1


IGNORED_NORMALS_RECORD = "mwdialog_ignored_normal_maps.txt"


PLACEHOLDER_COIN = "m\\misc_dwrv_coin00.nif"     # vanilla (Morrowind.bsa): model for objects never given one


DUMMY_MARKER_NIF = "mwdialog_dummy_marker.nif"   # the game's EditorMarker.nif (invisible): statics, activators, lights
DUMMY_ANIM_NIF = "mwdialog_dummy_anim.nif"       # the game's base_anim.nif (default skeleton): NPC models


# --------------------------------------------------------------------------
# Fixing
# --------------------------------------------------------------------------


FIX_TAG = "; [mwdialog_check] "


def plan_fixes(report, world, plugins, only, patch_esm):
    """Group proposed fixes by plugin.
    Returns (esp_plans, esm_plans, skipped, manual) where each plans dict is
    {plugin: {offset: [(op, desc, msg), ...]}} and manual is a list of issue labels per plugin."""
    paths = {n.lower(): p for n, p in plugins}
    esp_plans, esm_plans, skipped = {}, {}, {}
    manual = defaultdict(list)
    for plugin, off, op, desc, msg, _topic, _info in report.fixes:
        pl = plugin.lower()
        if only is not None and pl not in only:
            continue
        if pl in world.unfixable:
            skipped.setdefault(plugin, world.unfixable[pl])
            continue
        if pl not in paths or off is None:
            continue
        if pl.endswith(FIXABLE_EXT):
            esp_plans.setdefault(plugin, defaultdict(list))[off].append((op, desc, msg))
        elif not patch_esm:
            skipped.setdefault(plugin, "masters are not changed; add --patch-esm to fix them with a patch plugin")
        elif patch_supports(op):
            esm_plans.setdefault(plugin, defaultdict(list))[off].append((op, desc, msg))
        else:
            manual[plugin].append(f"{msg}  (a patch can't do this)")

    planned = {(p.lower(), x[2]) for plans in (esp_plans, esm_plans)
               for p, pp in plans.items() for items in pp.values() for x in items}
    involved = set(esp_plans) | set(esm_plans)
    for sev, plugin, topic, info, msg in report.issues:
        label = issue_label(topic, info, msg)
        if sev == "ERROR" and plugin in involved and (plugin.lower(), label) not in planned \
                and not any(label in m for m in manual[plugin]):
            manual[plugin].append(label)
    return esp_plans, esm_plans, skipped, manual


def apply_plan(path, plugin, plan, world, log, collect=None, backup=True):
    """Rewrite one plugin according to its plan. Returns number of changes made.
    With `collect` (a list), nothing is written: each changed INFO is appended as
    (DIAL record bytes, new INFO record bytes) for building a patch plugin."""
    with open(path, "rb") as f:
        data = f.read()
    records = list(iter_records(data))
    pl = plugin.lower()

    deleted_offs = {off for off, ops in plan.items() if any(o[0][0] == "delete" for o in ops)}
    new_names = {off: o[0][1] for off, ops in plan.items() for o in ops if o[0][0] == "set_name"}

    def dial_key(off, body):
        nm = first_sub(body, b"NAME")
        return cstr(nm).lower() if nm is not None else ""      # all nameless topics are one topic in game

    # First pass: per INFO, its topic, id and links; remember deleted ones for splicing.
    meta = {}                 # off -> dict(topic, id, prev, next)
    current = None
    for off, tag, flags, body in records:
        if tag == "DIAL":
            current = dial_key(off, body)
        elif tag == "INFO":
            g = lambda n: cstr(first_sub(body, n) or b"")
            meta[off] = {"topic": current, "id": g(b"INAM"), "prev": g(b"PNAM"), "next": g(b"NNAM")}
        else:
            current = None

    kept_ids = defaultdict(set)   # topic -> ids of INFOs that survive in this file
    for off, m in meta.items():
        if off not in deleted_offs and m["id"]:
            kept_ids[m["topic"]].add(m["id"].lower())
    gone = defaultdict(dict)      # topic -> id -> (prev, next) of deleted INFOs whose id no longer exists here
    for off in deleted_offs:
        m = meta.get(off)
        if m and m["id"] and m["id"].lower() not in kept_ids[m["topic"]]:
            gone[m["topic"]][m["id"].lower()] = (m["prev"], m["next"])

    def resolve(topic, link, idx):
        seen = set()
        while link and link.lower() in gone[topic] and link.lower() not in seen:
            seen.add(link.lower())
            link = gone[topic][link.lower()][idx]
        return link

    topic_obj = world.topics
    def known(topic, link):
        t = topic_obj.get(topic)
        if link.lower() in kept_ids[topic]:
            return True
        i = t.infos.get(link.lower()) if t else None
        return i is not None and not i.deleted and i.source.lower() != pl

    def earlier_copy(topic, info_id):
        t = topic_obj.get(topic)
        if not t or not info_id:
            return False
        users = t.defined_by.get(info_id.lower(), [])
        return any(u != pl for u in users[:users.index(pl)] if pl in users) if pl in users else False

    def owns(topic, info_id):
        t = topic_obj.get(topic)
        i = t.infos.get(info_id.lower()) if t and info_id else None
        return i is not None and i.source.lower() == pl

    def pick_prev(topic, exclude):
        choice = next((x for x in reversed(prev_kept_in_block) if x.lower() not in exclude), None)
        if choice is not None:
            return choice, "the response before it in this plugin"
        choice = chain_tail(world, topic, pl)
        if choice and choice.lower() not in exclude:
            return choice, "the end of the topic from earlier files"
        return "", "the top of the topic"

    changes = 0
    stubs = 0
    out = []
    cur_dial_raw = None
    rename_to = None
    prev_kept_in_block = []   # ids of kept INFOs earlier in the current DIAL block
    current = None
    for off, tag, flags, body in records:
        header_rest = data[off + 8:off + 16]   # unused field + flags, preserved
        if tag == "DIAL":
            current = dial_key(off, body)
            prev_kept_in_block = []
            cur_dial_raw = data[off:off + 16 + len(body)]
            rename_to = None
            if off in new_names and collect is not None:
                # Patch: delete this master's responses from the nameless topic and re-add them
                # under a named topic (built here), since a master's own topic can't be renamed.
                subs = [[n, d] for n, d in iter_subs(body, off) if n not in ("NAME", "DELE")]
                subs.insert(0, ["NAME", pack_str(new_names[off])])
                nb = b"".join(pack_sub(n, d) for n, d in subs)
                rename_to = tag.encode("ascii") + struct.pack("<I", len(nb)) + header_rest + nb
                collect.append((rename_to, None))      # the named topic exists even with no responses
                for op, desc, msg in plan[off]:
                    log.append((plugin, msg, desc))
                changes += 1
                continue
            if off in new_names:
                subs = [[n, d] for n, d in iter_subs(body, off) if n != "NAME"]
                subs.insert(0, ["NAME", pack_str(new_names[off])])
                nb = b"".join(pack_sub(n, d) for n, d in subs)
                out.append(tag.encode("ascii") + struct.pack("<I", len(nb)) + header_rest + nb)
                for op, desc, msg in plan[off]:
                    log.append((plugin, msg, desc))
                changes += 1
                continue
        elif tag != "INFO":
            current = None
            rename_to = None

        if off in deleted_offs:
            m = meta.get(off, {})
            local_only = any(o[0] == ("delete", "local") for o in plan[off])
            if (tag == "INFO" and not local_only and collect is None
                    and earlier_copy(m.get("topic"), m.get("id"))):
                # Another file has this response too. Deleting it would take a link out of the middle of
                # the game's chain of responses, and any plugin still pointing at it (now, or after an
                # update) can turn that chain into a circle the game freezes in. A response that can never
                # play does no harm left where it is: kept as it is.
                for op, desc, msg in plan[off]:
                    if op[0] == "delete":
                        log.append((plugin, msg, "left in place, not deleted: other plugins have this response "
                                                 "too, and deleting it can freeze the game's response list "
                                                 "(it still can never play)"))
                        break
                out.append(data[off:off + 16 + len(body)])
                continue
            for op, desc, msg in plan[off]:
                if op[0] == "delete":
                    log.append((plugin, msg, desc))
                    break
            changes += 1
            if tag == "INFO" and not local_only and (collect is not None or earlier_copy(m.get("topic"), m.get("id"))):
                # A deleted marker, not removal: removing it would let an earlier file's copy play again.
                keep = [pack_sub(n, d) for n, d in iter_subs(body, off) if n in ("INAM", "PNAM", "NNAM", "DATA")]
                nb = b"".join(keep) + pack_sub("DELE", b"\0\0\0\0")
                stub = tag.encode("ascii") + struct.pack("<I", len(nb)) + header_rest + nb
                if collect is not None:
                    collect.append((cur_dial_raw, stub))
                else:
                    out.append(stub)
                    stubs += 1
            continue

        if tag == "TES3" and off in plan:
            hsubs = [[n, d] for n, d in iter_subs(body, off)]
            cur_m = None
            for item in hsubs:
                if item[0] == "MAST":
                    cur_m = cstr(item[1]).lower()
                elif item[0] == "DATA" and cur_m is not None:
                    for op, desc, msg in plan[off]:
                        if op[0] == "sync_master" and op[1].lower() == cur_m:
                            item[1] = struct.pack("<Q", op[2])
                    cur_m = None
            for op, desc, msg in plan[off]:
                log.append((plugin, msg, desc))
                changes += 1
            nb = b"".join(pack_sub(n, d) for n, d in hsubs)
            out.append(tag.encode("ascii") + struct.pack("<I", len(nb)) + header_rest + nb)
            continue
        if tag == "CELL" and off in plan:
            drops = {op[1] for op, _d, _m in plan[off] if op[0] == "drop_ref"}
            moves = {op[1]: op[2] for op, _d, _m in plan[off] if op[0] == "move_ref"}
            nb, removed = rewrite_cell_refs(body, off, drops, moves)
            if removed:
                out.append(tag.encode("ascii") + struct.pack("<I", len(nb)) + header_rest + nb)
                for op, desc, msg in plan[off]:
                    log.append((plugin, msg, desc))
                changes += removed
                continue
        if tag != "INFO":
            out.append(data[off:off + 16 + len(body)])
            continue

        m = meta[off]
        if collect is not None and not owns(m["topic"], m["id"]):
            # another plugin's copy of this response wins in game; overriding this one would resurrect it
            out.append(data[off:off + 16 + len(body)])
            if m["id"]:
                prev_kept_in_block.append(m["id"])
            continue
        subs = [[n, d] for n, d in iter_subs(body, off)]
        touched = False

        for op, desc, msg in plan.get(off, []):
            kind = op[0]
            if kind == "drop_cond":
                new, i, hit = [], 0, False
                while i < len(subs):
                    n, d = subs[i]
                    if not hit and n == "SCVR" and cstr(d) == op[1]:
                        hit = True
                        i += 1
                        if i < len(subs) and subs[i][0] in ("INTV", "FLTV"):
                            i += 1
                        continue
                    new.append(subs[i])
                    i += 1
                if hit:
                    subs = new
            elif kind == "drop_sub":
                subs = [s for s in subs if s[0] != op[1]]
            elif kind == "set_text":
                if any(x[0] == "NAME" for x in subs):
                    for x in subs:
                        if x[0] == "NAME":
                            x[1] = op[1].encode(ENC, MW_ERRORS)
                else:
                    # NAME (the text) follows INAM/PNAM/NNAM/DATA and the speaker filters, before conditions
                    head = ("INAM", "PNAM", "NNAM", "DATA", "ONAM", "RNAM", "CNAM", "FNAM", "ANAM", "DNAM", "SNAM")
                    pos = max([k + 1 for k, x in enumerate(subs) if x[0] in head] or [len(subs)])
                    subs.insert(pos, ["NAME", op[1].encode(ENC, MW_ERRORS)])
            elif kind == "set_prev":
                set_link(subs, "PNAM", pack_str(op[1]))
                m["prev"] = op[1]
            elif kind == "set_next":
                set_link(subs, "NNAM", pack_str(op[1]))
            elif kind == "comment":
                for s in subs:
                    if s[0] == "BNAM":
                        had_null = s[1].endswith(b"\0")
                        text = s[1].rstrip(b"\0").decode(ENC, MW_ERRORS)
                        lines = text.splitlines(keepends=True)
                        for j, ln in enumerate(lines):
                            if ln.rstrip("\r\n") == op[1] and not ln.lstrip().startswith(FIX_TAG.strip()):
                                lines[j] = FIX_TAG + ln
                        s[1] = "".join(lines).encode(ENC, MW_ERRORS) + (b"\0" if had_null else b"")
            elif kind == "relink":
                choice, where = pick_prev(m["topic"], set(op[1]))
                set_link(subs, "PNAM", pack_str(choice))
                m["prev"] = choice
                desc = f"{desc}: now follows '{choice}' ({where})" if choice else f"{desc}: moved to {where}"
            log.append((plugin, msg, desc))
            touched = True
            changes += 1

        # splice links that pointed at responses deleted from this file
        for s in subs:
            if s[0] in ("PNAM", "NNAM"):
                cur = cstr(s[1])
                fixed = resolve(m["topic"], cur, 0 if s[0] == "PNAM" else 1)
                if fixed != cur and fixed and not known(m["topic"], fixed):
                    # the deleted response's own link was broken too
                    fixed = pick_prev(m["topic"], {m["id"].lower()})[0] if s[0] == "PNAM" else ""
                if fixed != cur:
                    s[1] = pack_str(fixed)
                    log.append((plugin, f"[{m['topic']}] {m['id']}: {s[0]} pointed at a deleted response",
                                f"re-linked {s[0]} from '{cur}' to '{fixed or '(none)'}'"))
                    touched = True
                    changes += 1

        if m["id"]:
            prev_kept_in_block.append(m["id"])
        if touched:
            nb = b"".join(pack_sub(n, d) for n, d in subs)
            out.append(tag.encode("ascii") + struct.pack("<I", len(nb)) + header_rest + nb)
            if collect is not None and rename_to is None:
                collect.append((cur_dial_raw, out[-1]))
        else:
            out.append(data[off:off + 16 + len(body)])
        if collect is not None and rename_to is not None and m["id"]:
            keep = [pack_sub(n, d) for n, d in iter_subs(body, off) if n in ("INAM", "PNAM", "NNAM", "DATA")]
            sb = b"".join(keep) + pack_sub("DELE", b"\0\0\0\0")
            collect.append((cur_dial_raw, tag.encode("ascii") + struct.pack("<I", len(sb)) + header_rest + sb))
            collect.append((rename_to, out[-1]))
            changes += 0 if touched else 1

    if not changes or collect is not None:
        return changes

    # update the record count in the TES3 header
    out[0] = set_hedr_count(out[0], len(out) - 1)     # the true count

    st = os.stat(path)
    if backup:
        bak = backup_path(path)
        shutil.copy2(path, bak)
    # checked temp copy first, then in place (keeps hard links, e.g. Vortex deployments) and the date,
    # so load order doesn't change
    write_plugin_bytes(path, b"".join(out), keep_times=st)
    if backup:
        log.append((plugin, "", f"backup saved as {os.path.basename(bak)}"))
    return changes


def scan(args, plugins, bsas, data_dirs, report):
    world = World(report)
    world.trace = {t.lower() for t in (getattr(args, "trace", None) or [])}
    world.file_sizes = {}
    for name, path in plugins:
        try:
            world.file_sizes[name.lower()] = os.path.getsize(path)
        except OSError:
            pass
    for i, (name, path) in enumerate(plugins, 1):
        print(f"[{i}/{len(plugins)}] reading {name}", file=sys.stderr)
        world.load_plugin(path, name)
    tree = None
    if getattr(args, "asset_check", False):
        print("Indexing meshes, textures, icons, sounds, music, video and fonts...", file=sys.stderr)
        tree = DataTree(os.path.abspath(args.data_dir))     # the one walk of Data Files for this pass
    sounds = None if args.no_sounds else collect_sound_files(data_dirs, bsas, tree)
    if tree is not None:
        game_dir = os.path.dirname(os.path.abspath(args.data_dir))
        world.tree = tree
        world.assets = ModelAssets(data_dirs, bsas, tree=tree, cache=asset_health_module().shared_cache(game_dir),
                                   generated=generated_rels(game_dir))
        world.ini_path = None if (args.plugins or args.openmw_cfg) else default_ini(args)
        vroot = getattr(args, "vortex_dir", None)
        if vroot and os.path.isdir(vroot) and not getattr(args, "no_vortex", False):
            world.vortex = VortexRepo(vroot)
    world.args_data_dir = args.data_dir
    world.args = args
    world.plugin_paths = [p for _n, p in plugins]
    if tree is not None:                       # paths too long for Windows (before the missing-file checks)
        try:
            longpaths_module().check(world, sys.modules[__name__])
        except Exception as e:                 # never let it stop the scan
            print(f"(long-path check failed: {e})", file=sys.stderr)
    world.check(sounds)
    bad = getattr(world, "mismatched_plugins", None)
    if bad and getattr(args, "disable_mismatched", False) and not getattr(args, "dry_run", False) \
            and not getattr(args, "_mismatched_done", False):
        args._mismatched_done = True
        try:
            order = read_load_order(args) or [n for n, _p in plugins]
            gone = mastercheck_module().disable(os.path.dirname(os.path.abspath(args.data_dir)), order, bad,
                                                sys.modules[__name__], getattr(args, "fix_log", None))
            if gone:
                print("Taken out of the load order (made for a different master) (put back by adding them to " + LOAD_ORDER_FILE + "):", file=sys.stderr)
                print(MT.bullets(gone, indent="  "), file=sys.stderr)
        except (OSError, UnicodeError) as e:
            print(f"(could not take mismatched plugins out of the load order: {e})", file=sys.stderr)
    return world


def patch_contents(path):
    """(topic lower, response id lower) pairs that an existing patch already overrides."""
    covered = set()
    try:
        with open(path, "rb") as f:
            data = f.read()
        topic = None
        for off, tag, flags, body in iter_records(data):
            if tag == "DIAL":
                topic = cstr(first_sub(body, b"NAME") or b"").lower()
                covered.add((topic, ""))
            elif tag == "INFO" and topic is not None:
                covered.add((topic, cstr(first_sub(body, b"INAM") or b"").lower()))
            elif tag == "MISC":
                covered.add(("script-object", cstr(first_sub(body, b"NAME") or b"").lower()))
                covered.add(("early-object", cstr(first_sub(body, b"NAME") or b"").lower()))
            elif tag in World.PLACEABLE:
                covered.add(("early-object", cstr(first_sub(body, b"NAME") or b"").lower()))
            elif tag == "CELL" and cstr(first_sub(body, b"NAME") or b"") in (PLACEHOLDER_CELL, EARLY_CELL):
                kind = "placed-object" if cstr(first_sub(body, b"NAME")) == PLACEHOLDER_CELL else "early-placed"
                pend = False
                for sn, sd in iter_subs(body, off):
                    if sn == "FRMR":
                        pend = True
                    elif sn == "NAME" and pend:
                        covered.add((kind, cstr(sd).lower()))
                        pend = False
    except (OSError, FormatError):
        pass
    return covered


EARLY_CELL = "mwdialog_check early placeholders"       # in the ESM patch, so it loads before any .esp


def print_plan(title, plans, hidden=frozenset()):
    total = 0
    for plugin, plan in plans.items():
        shown = {off: items for off, items in plan.items()
                 if not all((plugin, x[2]) in hidden for x in items)}
        carried = len(plan) - len(shown)
        total += carried
        if not shown:
            print(f"\n  {plugin}{title}: {carried} fix(es) already in the patch, carried over")
            continue
        print(f"\n  {plugin}{title}")
        if carried:
            print(f"    ({carried} more already in the patch, carried over)")
        for off, items in shown.items():
            deletes = [x for x in items if x[0][0] == "delete"]
            if deletes:
                total += 1
                for op, desc, msg in items:
                    print(f"    - {msg}")
                print(f"        -> {deletes[0][1]}")
            else:
                for op, desc, msg in items:
                    total += 1
                    print(f"    - {msg}\n        -> {desc}")
    return total


def run_fix(args, plugins, bsas, data_dirs, report, world, only, hidden=frozenset()):
    esp_plans, esm_plans, skipped, manual = plan_fixes(report, world, plugins, only, True)
    print("\n" + "=" * 70)
    print("FIX PLAN (ERRORs only)")
    print("=" * 70)
    for plugin, why in skipped.items():
        print(f"  SKIP {plugin}: {why}")

    # stand-in gold coins for objects that scripts name but no loaded mod defines, and a hidden
    # cell with a placed copy of every object a script acts on ("X->") that nothing places
    placeholders, placements = {}, {}
    if not args.no_placeholders:
        for o, v in sorted(world.missing_objects.items()):
            if only is not None and not any(pl.lower() in only for pl, _s in v["used_by"]):
                continue
            if world.gold_template is not None and len(v["id"]) <= 31:
                placeholders[o] = v
                if v["arrow"]:
                    placements[o] = dict(v, tag="MISC", why="placeholder coin")
        for o, v in sorted(world.unplaced.items()):
            if only is None or any(pl.lower() in only for pl, _s in v["used_by"]):
                placements[o] = v
    early = {o: v for o, v in world.early_needed.items()
             if only is None or any(p.lower() in only for p in v[2])}
    early_placed = {o: v for o, v in world.early_placed.items()
                    if only is None or any(p.lower() in only for p in v["users"])}
    # scripts / enchantments / inventory items that point at nothing (stale overrides)
    item_esp, item_esm = {}, {}
    for fx in world.item_fixes:
        pl = fx["plugin"]
        if only is not None and pl.lower() not in only:
            continue
        if pl.lower() in world.unfixable:
            if pl not in skipped:
                print(f"  SKIP {pl}: {world.unfixable[pl.lower()]}")
                skipped[pl] = world.unfixable[pl.lower()]
            continue
        (item_esp if pl.lower().endswith(FIXABLE_EXT) else item_esm).setdefault(pl, []).append(fx)
    generated = list({g[0].lower(): g for g in world.generated}.values()) if (only is None) else []
    shrink = list(getattr(world, "texture_reductions", [])) if only is None else []
    keyfix = list(getattr(world, "text_key_fixes", [])) if only is None else []
    health = list(getattr(world, "asset_health", [])) if only is None else []
    if not esp_plans and not esm_plans and not placeholders and not placements and not early and not early_placed \
            and not item_esp and not item_esm and not generated and not shrink and not keyfix and not health \
            and not (only is None and getattr(world, "longpath_plan", None)):
        print("  Nothing that can be fixed automatically.")
        return
    total = print_plan("", esp_plans)
    total += print_plan(f"   (fixed through {PATCH_NAME})", esm_plans, hidden)
    if item_esp or item_esm:
        print("\n  Scripts, enchantments, inventory items and cell regions that point at nothing (usually an override made "
              "for an older version of its master):")
        in_patch = set()
        try:
            with open(os.path.join(args.data_dir, PATCH_NAME), "rb") as f:
                pdata = f.read()
            for _o, ptag, _f, pbody in iter_records(pdata):
                pn = first_sub(pbody, b"NAME") if ptag in REF_TAGS else None
                if pn is not None:
                    in_patch.add((ptag, cstr(pn).lower()))
        except (OSError, FormatError):
            pass
        for group, title in ((item_esp, ""), (item_esm, f"   (fixed through {PATCH_NAME})")):
            for plugin, fixes in group.items():
                carried = [fx for fx in fixes if group is item_esm and (fx["tag"], fx["id"].lower()) in in_patch]
                if carried and len(carried) == len(fixes):
                    print(f"\n  {plugin}{title}: {len(carried)} record(s) already in the patch, carried over")
                    total += sum(len(fx["msgs"]) for fx in carried)
                    continue
                print(f"\n  {plugin}{title}")
                for fx in fixes:
                    for msg, action in fx["msgs"]:
                        print(f"    - {msg}\n        -> {action}")
                        total += 1
    if placeholders:
        place_has = patch_contents(os.path.join(args.data_dir, PLACE_PATCH_NAME))
        already = {o for o in placeholders if ("script-object", o) in place_has}
        new = [v for o, v in placeholders.items() if o not in already]
        print(f"\n  Placeholder objects (a single gold coin each, added to {PLACE_PATCH_NAME})"
              + (f": {len(already)} already in the patch, carried over" if already else ""))
        for v in new:
            users = ", ".join(sorted({f"{pl}: {sc}" for pl, sc in v["used_by"]}))
            print(f"    - {v['id']}  (named by {users})")
        total += len(placeholders)
    if early:
        have = patch_contents(os.path.join(args.data_dir, PATCH_NAME))
        already = {o for o in early if ("early-object", o) in have}
        print(f"\n  Defined early in {PATCH_NAME} (a copy of the real definition, so plugins that place or "
              f"script these find them when they load)" + (f": {len(already)} already in the patch, carried over"
                                                    if already else ""))
        for o, (src, tag, users) in early.items():
            if o not in already:
                print(f"    - {o}  ({tag} from {src}; needed by {', '.join(sorted(set(users)))})")
        total += len(early)
    if early_placed:
        have = patch_contents(os.path.join(args.data_dir, PATCH_NAME))
        already = {o for o in early_placed if ("early-placed", o) in have}
        print(f"\n  Placed early in the hidden cell '{EARLY_CELL}' ({PATCH_NAME}), so scripts that load before "
              f"the real copy find one" + (f": {len(already)} already in the patch, carried over" if already else ""))
        for o, v in early_placed.items():
            if o not in already:
                print(f"    - {v['id']}  (first placed by {v['by']}; acted on by scripts in "
                      f"{', '.join(sorted(set(v['users'])))})")
        total += len(early_placed)
    if placements:
        covered_now = patch_contents(os.path.join(args.data_dir, PLACE_PATCH_NAME))
        already = {o for o in placements if ("placed-object", o) in covered_now}
        print(f"\n  Placed in the hidden cell '{PLACEHOLDER_CELL}' (scripts act on these directly)"
              + (f": {len(already)} already in the patch, carried over" if already else ""))
        for o, v in placements.items():
            if o not in already:
                users = ", ".join(sorted({pl for pl, _s in v["used_by"]}))
                print(f"    - {v['id']}  ({v['why']}; used by {users})")
        total += len(placements)
    manual = {p: [x for x in m if (p, x) not in hidden
                  and not ("isn't defined yet" in x and any(f"'{o}'" in x.lower() for o in early))]
              for p, m in manual.items()}
    manual = {p: m for p, m in manual.items() if m}
    if manual:
        print("\n  Left for you to fix by hand:")
        for plugin, items in manual.items():
            for label in items:
                print(f"    - {plugin} {label}")

    if shrink:
        tbytes = sum(t[4] for t in shrink)
        print(f"\n  Textures to reduce to {TEXTURE_MAX_EDGE} on their longest edge ({len(shrink)}, {tbytes / 2**30:.1f} GB "
              f"now, about {tbytes * 0.75 / 2**30:.1f} GB less after; the smaller copies inside each file are used, "
              f"originals kept, --restore-textures undoes it):")
        for full, rel, w, h, size in sorted(shrink, key=lambda t: -t[4])[:10]:
            print(f"    - {rel}   {w}x{h}, {size / 2**20:.0f} MB")
        if len(shrink) > 10:
            print(f"    ... and {len(shrink) - 10} more")
        total += len(shrink)
    if generated:
        print(f"\n  Files to put in Data Files ({len(generated)}): copies of files found in Vortex mod folders but never "
              f"deployed, silent stand-ins for sounds and music, and placeholder textures for models whose textures "
              f"no mod has (listed in {GENERATED_RECORD}; --remove-generated deletes them):")
        for item in generated[:12]:
            rel, why, source = (item + (None,))[:3]
            kind = (("back from .Orphaned" if ".orphaned" in source.lower() else
                     "stand-in model, " + os.path.basename(source) if os.path.basename(source).lower().startswith(
                         "mwdialog_dummy") else "copy of " + source) if source
                    else ("placeholder texture" if rel.lower().endswith(".dds") else "silent"))
            print(f"    + {rel}   ({kind}; {why})")
        if len(generated) > 12:
            print(f"    ... and {len(generated) - 12} more")
        total += len(generated)
    if keyfix:
        print(f"\n  Models/animations whose text keys get Windows line endings ({len(keyfix)}, originals kept):")
        for full, rel, bad in keyfix[:10]:
            print(f"    - {rel}   ({bad} key(s))")
        total += len(keyfix)
    if health:
        from collections import Counter as _C
        kinds = _C(k for k, *_x in health)
        names = {"tex": "texture(s) to convert (DXT / mipmaps / power-of-two size, texconv)",
                 "abs": "model(s) whose absolute texture paths become relative",
                 "snd": "sound(s) to convert (mono / 44.1 kHz, ffmpeg)",
                 "unused": "unused or empty file(s) to move to their mod's Off\\unused\\ (--restore-unused)",
                 "broken": "broken file(s) to keep in Off\\...\\broken\\, a stand-in put in their place",
                 "orphan": "orphaned animation(s) to move to Off\\...\\orphaned\\"}
        print("\n  Asset health:")
        for k, n in kinds.items():
            print(f"    {n:6d} {names[k]}")
            for kind, full, rel, job in [h for h in health if h[0] == k][:5]:
                print(f"           e.g. {rel}")
        total += len(health)
    lp_plan = getattr(world, "longpath_plan", []) if only is None else []
    if lp_plan:
        print(f"\n  Paths too long for Windows: files to move to a short path ({len(lp_plan)}; the records and "
              f"models that name them follow; listed in mwdialog_longpaths.json, --longpaths-undo puts them back):")
        for line in longpaths_module().plan_lines(world)[:15]:
            print(line)
        total += len(lp_plan)
    if args.dry_run:
        print("\nDry run: no files were changed.")
        return
    if not args.yes:
        if not sys.stdin.isatty():
            print("\nNot running interactively; add --yes to apply these fixes.")
            return
        parts = []
        if esp_plans:
            parts.append(f"{len(esp_plans)} plugin(s), each backed up first")
        if item_esp and not esp_plans:
            parts.append(f"{len(item_esp)} plugin(s), each backed up first")
        elif item_esp:
            parts[0] = f"{len(set(esp_plans) | set(item_esp))} plugin(s), each backed up first"
        if esm_plans or placeholders or placements or early or early_placed or item_esm:
            parts.append("the patch plugin")
        ans = input(f"\nApply {total} fix(es) to {' and '.join(parts)}? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("No changes made.")
            return

    paths = {n: p for n, p in plugins}
    log = []
    for plugin, plan in esp_plans.items():
        try:
            n = apply_plan(paths[plugin], plugin, plan, world, log)
            print(f"  {plugin}: {n} change(s) written")
        except Exception as e:                       # one plugin's problem never stops the others halfway
            print(f"  {plugin}: NOT changed ({type(e).__name__}: {e})")

    if lp_plan or getattr(world, "longpath_nifs", None):
        failed = longpaths_module().apply(world, sys.modules[__name__], os.path.abspath(args.data_dir), log)
        if failed:                                    # a file that didn't move keeps its records' old path
            for group in (item_esp, item_esm):
                for pl in list(group):
                    group[pl] = [fx for fx in group[pl] if fx.get("longpath") not in failed]
                    if not group[pl]:
                        del group[pl]
        print(f"  Data Files: {len(lp_plan) - len(failed)} file(s) moved to a short path"
              + (f", {len(failed)} could not be" if failed else ""))
    for plugin, fixes in item_esp.items():
        try:
            n = apply_item_fixes(paths[plugin], plugin, fixes, log, backup=plugin not in esp_plans)
            print(f"  {plugin}: {n} record(s) corrected")
        except Exception as e:                       # one plugin's problem never stops the others halfway
            print(f"  {plugin}: NOT changed ({type(e).__name__}: {e})")
    if generated:
        made = write_generated(os.path.abspath(args.data_dir), os.path.dirname(os.path.abspath(args.data_dir)),
                               generated, log)
        print(f"  Data Files: {len(made)} silent stand-in file(s) created")
    if shrink:
        n, saved = reduce_textures(os.path.abspath(args.data_dir), os.path.dirname(os.path.abspath(args.data_dir)),
                                   shrink, log)
        print(f"  Data Files: {n} texture(s) reduced to {TEXTURE_MAX_EDGE}, {saved / 2**30:.1f} GB smaller. Vortex may "
              f"report them as changed outside Vortex: keep the changes, or choose Revert to get the full size back "
              f"(don't save them into the mod, or the staging folder loses its full-size copies).")

    if keyfix:
        dd = os.path.abspath(args.data_dir)
        done = 0
        for full, rel, bad in keyfix:
            try:
                with open(full, "rb") as f:
                    data = f.read()
                n, new = nif_text_keys_lf(data)
                if not new:
                    continue
                bak = backup_asset_original(dd, rel, feature="text keys")
                replace_asset_in_place(full, new)
                done += 1
                log.append(("Data Files", f"'{rel}': {n} animation text key(s) with Unix line endings",
                            f"rewritten with Windows line endings (original: {bak})"))
            except OSError as e:
                print(f"  {rel}: NOT changed ({e})")
        print(f"  Data Files: {done} mesh/animation file(s) had their text keys rewritten with Windows line endings")

    if health:
        dd = os.path.abspath(args.data_dir)
        print("  Data Files: " + asset_health_module().apply(health, dd, os.path.dirname(dd), sys.modules[__name__],
                                                             log, dry=args.dry_run))

    patch_path = os.path.join(args.data_dir, PATCH_NAME)
    place_path = os.path.join(args.data_dir, PLACE_PATCH_NAME)
    patch_log = []                     # ESM patch: rebuilt (and re-logged) after follow-on fixes
    place_log = []
    patch_built = [False]
    place_built = [False]

    def write_dated(path, *a, **kw):
        """Write a patch; a brand-new one gets the day after the newest plugin (date-based load order)."""
        is_new = not os.path.exists(path)
        result = write_patch(path, *a, **kw)
        if is_new:
            when = next_free_date(args.data_dir, os.path.basename(path))
            if when:
                os.utime(path, (when, when))
        return result

    def build_patch():
        """(Re)build the ESM patch from every master fix planned so far. It loads right after the masters."""
        patch_log.clear()
        entries = []
        for name, path in plugins:                      # load order keeps the patch tidy
            if name in esm_plans:
                apply_plan(path, name, esm_plans[name], world, patch_log, collect=entries)
        masters = master_closure(world, plugins, esm_plans)
        extra = []
        paths_l = {n.lower(): p for n, p in plugins}
        for name, fixes in item_esm.items():          # corrected copies of masters' records
            apply_item_fixes(paths_l[name.lower()], name, fixes, patch_log, collect=extra)
        for o, (src, tag, users) in early.items():
            raw = extract_record(paths_l[src.lower()], tag, o) if src.lower() in paths_l else None
            if raw:
                extra.append(raw)
                patch_log.append((PATCH_NAME, f"'{o}' is placed by {', '.join(sorted(set(users)))} before "
                                              f"{src} defines it", "copied its definition into the patch"))
        if early_placed:
            extra.append(placeholder_cell([v["id"] for v in early_placed.values()], EARLY_CELL))
            for v in early_placed.values():
                patch_log.append((PATCH_NAME, f"scripts in {', '.join(sorted(set(v['users'])))} act on '{v['id']}' "
                                              f"before {v['by']} places it",
                                  f"placed a hidden copy in '{EARLY_CELL}'"))
        topics, recs = write_dated(patch_path, entries, masters, patch_log, backup=not patch_built[0],
                                   extra=extra)
        patch_built[0] = True
        print(f"  {PATCH_NAME}: written with {recs} response override(s) in {topics} topic(s)"
              + (f", {len(early)} object(s) defined early" if early else "")
              + (f", {len(early_placed)} placed early" if early_placed else "")
              + (f"; masters: {', '.join(n for n, _ in masters)}" if masters else ""))
        patch_log.append((PATCH_NAME, "", f"written ({recs} responses in {topics} topics)"))

    def build_place():
        """(Re)build the placeholder patch: coins and the hidden cell. It loads last."""
        extra = [r for r in (placeholder_record(world, v["id"]) for v in placeholders.values()) if r]
        if placements:
            extra.append(placeholder_cell([v["id"] for v in placements.values()]))
        write_dated(place_path, [], [], place_log, backup=not place_built[0], extra=extra,
                    description="Placeholder objects and hidden cell for missing script objects, "
                                "generated by mwdialog_check.py. Load this LAST.")
        place_built[0] = True
        print(f"  {PLACE_PATCH_NAME}: written with {len(placeholders)} placeholder object(s) and "
              f"{len(placements)} hidden placed object(s)")
        for v in placeholders.values():
            place_log.append((PLACE_PATCH_NAME, f"script object '{v['id']}' is not defined by any loaded mod",
                              "added a placeholder gold coin with that ID"))
        for v in placements.values():
            place_log.append((PLACE_PATCH_NAME, f"scripts act on '{v['id']}' but no copy is placed ({v['why']})",
                              f"placed one in the hidden cell '{PLACEHOLDER_CELL}'"))

    if esm_plans or early or early_placed or item_esm or os.path.exists(patch_path):
        build_patch()                      # also clears out what older versions put in it
    if placeholders or placements or os.path.exists(place_path):
        build_place()

    def rescan_list():
        """The load order as the game will see it: ESM patch where it loads, placeholder patch last."""
        order = list(plugins)
        if patch_built[0]:
            pos = min(getattr(args, "esm_patch_pos", len(order)), len(order))
            order.insert(pos, (PATCH_NAME, patch_path))
        if place_built[0]:
            order.append((PLACE_PATCH_NAME, place_path))
        return order

    backed_up = set(esp_plans) | set(item_esp)
    fresh = None                       # a scan that already reflects every change made
    # The re-scans below look at what the fixes changed in the plugins; the files on disk (models,
    # textures, sounds) don't change between them, so the asset check (minutes) isn't repeated.
    rescan_args = copy.copy(args)
    rescan_args.asset_check = False
    if getattr(args, "asset_check", False):
        print("\n(Re-scans after the fixes skip the asset check: the files on disk haven't changed.)")
    for _ in range(0 if getattr(args, "no_follow_fix", False) else 4):
        # Fixes can expose new ones, e.g. a plugin or master linking to a response that was just deleted.
        report2 = Report()
        world2 = scan(rescan_args, rescan_list(), bsas, data_dirs, report2)
        follow, follow_esm, _skip, _man = plan_fixes(report2, world2, rescan_list(), only, True)
        follow.pop(PATCH_NAME, None)
        follow.pop(PLACE_PATCH_NAME, None)
        for plugin in list(follow_esm):        # already in the patch (e.g. a master's nameless topic)
            for off in list(follow_esm[plugin]):
                have = esm_plans.get(plugin, {}).get(off, [])
                follow_esm[plugin][off] = [x for x in follow_esm[plugin][off] if x not in have]
                if not follow_esm[plugin][off]:
                    del follow_esm[plugin][off]
            if not follow_esm[plugin]:
                del follow_esm[plugin]
        for plugin, off, op, desc, msg, topic, info_id in report2.fixes:
            if plugin != PATCH_NAME or not patch_supports(op):
                continue
            t = world.topics.get(topic.lower())
            owner = t.infos.get(info_id.lower()) if t and info_id else None
            if owner is None or owner.off is None or owner.source not in dict(plugins) \
                    or owner.source.lower().endswith(FIXABLE_EXT):
                continue
            items = follow_esm.setdefault(owner.source, defaultdict(list))[owner.off]
            if (op, desc, msg) not in items:
                items.append((op, desc, msg))
        if not follow and not follow_esm:
            fresh = report2
            break
        print("\nFollow-on fixes made possible by the changes above:")
        n = print_plan("", follow) + print_plan(f"   (fixed through {PATCH_NAME})", follow_esm)
        if not args.yes:
            if not sys.stdin.isatty() or input(f"Apply these {n} follow-on fix(es)? [y/N] ").strip().lower() not in ("y", "yes"):
                break
        for plugin, plan in follow.items():
            try:
                k = apply_plan(paths[plugin], plugin, plan, world, log, backup=plugin not in backed_up)
                backed_up.add(plugin)
                esp_plans.setdefault(plugin, {})
                print(f"  {plugin}: {k} change(s) written")
            except (OSError, FormatError) as e:
                print(f"  {plugin}: NOT changed ({e})")
        if follow_esm:
            for plugin, plan in follow_esm.items():
                dest = esm_plans.setdefault(plugin, defaultdict(list))
                for off, items in plan.items():
                    for item in items:
                        if item not in dest[off]:
                            dest[off].append(item)
            build_patch()
    log.extend(patch_log)
    log.extend(place_log)
    patch_path = patch_path if patch_built[0] else None

    with MT.open_log(args.fix_log, "a", encoding="utf-8") as f:
        import datetime
        f.write(f"\n==== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ====\n")
        for plugin, msg, desc in log:
            f.write(f"{plugin}: {msg + ' -> ' if msg else ''}{desc}\n")
    print(f"Fix log appended to {args.fix_log}")

    if fresh is not None:
        report2 = fresh
        print("\nFinal check" + (" (patches in their load-order positions):" if patch_path else ":"))
    else:
        print("\nRe-scanning" + (" with the patches in their load-order positions..." if patch_path else "..."))
        report2 = Report()
        scan(rescan_args, rescan_list(), bsas, data_dirs, report2)
    covered = set()
    for pp in (patch_path, place_path if place_built[0] else None):
        if pp:
            covered |= patch_contents(pp)
    report2.issues = [i for i in report2.issues if not covered_by_patches(i, covered)]
    report2.fixes = [f for f in report2.fixes
                     if f[0].lower().endswith(FIXABLE_EXT) or (f[5].lower(), f[6].lower()) not in covered]
    for plugin in list(dict.fromkeys(list(esp_plans) + list(item_esp) + list(esm_plans) + list(item_esm))) \
            + ([PATCH_NAME] if patch_path else []) \
            + ([PLACE_PATCH_NAME] if place_built[0] else []):
        left = sum(1 for i in report2.issues if i[0] == "ERROR" and i[1] == plugin)
        print(f"  {plugin}: {left} ERROR(s) remaining")
    done = set(esp_plans) | set(esm_plans) | set(item_esp) | set(item_esm) | set(OUR_PATCHES)
    others = sum(1 for i in report2.issues if i[0] == "ERROR" and i[1] not in done)
    print(f"  other plugins: {others} ERROR(s)")
    more = sum(1 for f in report2.fixes if not is_our_patch(f[0])
               and (only is None or f[0].lower() in only) and f[0].lower() not in world.unfixable)
    if more:
        print(f"\n{more} more fix(es) became possible because of these changes "
              f"(e.g. links to responses that were just deleted). Run --fix again to apply them.")
    if patch_path or place_built[0]:
        print("\nLoad order for the patches (activate them in the Morrowind Launcher or your mod manager):")
        if patch_path:
            print(f"  - {PATCH_NAME}: right after the masters (.esm), where it is now")
        if place_built[0]:
            print(f"  - {PLACE_PATCH_NAME}: LAST, after every other plugin")


# --------------------------------------------------------------------------
# Cleaning (ported from tes3cmd "clean"; in place, .bak first, file date kept)
# --------------------------------------------------------------------------

# Evil GMSTs: (subrecord type, exact value) the Construction Set slips into plugins. From tes3cmd
# (MIT License, Copyright (c) 2016 John Moonsugar): 11 Tribunal and 61 Bloodmoon entries.
EVIL_GMSTS = {
    # Tribunal
    'scompanionshare': ('STRV', b'Companion Share'),
    'scompanionwarningbuttonone': ('STRV', b'Let the mercenary quit.'),
    'scompanionwarningbuttontwo': ('STRV', b'Return to Companion Share display.'),
    'scompanionwarningmessage': ('STRV', b'Your mercenary is poorer now than when he contracted with you.  Your mercenary will quit if you do not give him gold or goods to bring his Profit Value to a positive value.'),
    'sdeletenote': ('STRV', b'Delete Note?'),
    'seffectsummonfabricant': ('STRV', b'sEffectSummonFabricant'),
    'slevitatedisabled': ('STRV', b'Levitation magic does not work here.'),
    'smagicfabricantid': ('STRV', b'Fabricant'),
    'smaxsale': ('STRV', b'Max Sale'),
    'sprofitvalue': ('STRV', b'Profit Value'),
    'steleportdisabled': ('STRV', b'Teleportation magic does not work here.'),
    # Bloodmoon
    'fcombatdistancewerewolfmod': ('FLTV', b'\x9a\x99\x99>'),
    'ffleedistance': ('FLTV', b'\x00\x80;E'),
    'fwerewolfacrobatics': ('FLTV', b'\x00\x00\x16C'),
    'fwerewolfagility': ('FLTV', b'\x00\x00\x16C'),
    'fwerewolfalchemy': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfalteration': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfarmorer': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfathletics': ('FLTV', b'\x00\x00\x16C'),
    'fwerewolfaxe': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfblock': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfbluntweapon': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfconjuration': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfdestruction': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfenchant': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfendurance': ('FLTV', b'\x00\x00\x16C'),
    'fwerewolffatigue': ('FLTV', b'\x00\x00\xc8C'),
    'fwerewolfhandtohand': ('FLTV', b'\x00\x00\xc8B'),
    'fwerewolfhealth': ('FLTV', b'\x00\x00\x00@'),
    'fwerewolfheavyarmor': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfillusion': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfintellegence': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolflightarmor': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolflongblade': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfluck': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfmagicka': ('FLTV', b'\x00\x00\xc8B'),
    'fwerewolfmarksman': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfmediumarmor': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfmerchantile': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfmysticism': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfpersonality': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfrestoration': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfrunmult': ('FLTV', b'\x00\x00\xc0?'),
    'fwerewolfsecurity': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfshortblade': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfsilverweapondamagemult': ('FLTV', b'\x00\x00\xc0?'),
    'fwerewolfsneak': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfspear': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfspeechcraft': ('FLTV', b'\x00\x00\x80?'),
    'fwerewolfspeed': ('FLTV', b'\x00\x00\x16C'),
    'fwerewolfstrength': ('FLTV', b'\x00\x00\x16C'),
    'fwerewolfunarmored': ('FLTV', b'\x00\x00\xc8B'),
    'fwerewolfwillpower': ('FLTV', b'\x00\x00\x80?'),
    'iwerewolfbounty': ('INTV', b"\x10'\x00\x00"),
    'iwerewolffightmod': ('INTV', b'd\x00\x00\x00'),
    'iwerewolffleemod': ('INTV', b'd\x00\x00\x00'),
    'iwerewolfleveltoattack': ('INTV', b'\x14\x00\x00\x00'),
    'seditnote': ('STRV', b'Edit Note'),
    'seffectsummoncreature01': ('STRV', b'sEffectSummonCreature01'),
    'seffectsummoncreature02': ('STRV', b'sEffectSummonCreature02'),
    'seffectsummoncreature03': ('STRV', b'sEffectSummonCreature03'),
    'seffectsummoncreature04': ('STRV', b'sEffectSummonCreature04'),
    'seffectsummoncreature05': ('STRV', b'sEffectSummonCreature05'),
    'smagiccreature01id': ('STRV', b'sMagicCreature01ID'),
    'smagiccreature02id': ('STRV', b'sMagicCreature02ID'),
    'smagiccreature03id': ('STRV', b'sMagicCreature03ID'),
    'smagiccreature04id': ('STRV', b'sMagicCreature04ID'),
    'smagiccreature05id': ('STRV', b'sMagicCreature05ID'),
    'swerewolfalarmmessage': ('STRV', b'You have been detected changing from a werewolf state.'),
    'swerewolfpopup': ('STRV', b'Werewolf'),
    'swerewolfrefusal': ('STRV', b'You cannot do this as a werewolf.'),
    'swerewolfrestmessage': ('STRV', b'You cannot rest in werewolf form.'),
}


# record types tes3cmd's --dups compares against the masters
CLEAN_DUP_TYPES = {"ACTI", "ALCH", "APPA", "ARMO", "BODY", "BOOK", "BSGN", "CELL", "CLAS", "CLOT", "CONT",
                   "CREA", "DOOR", "ENCH", "FACT", "GLOB", "GMST", "INFO", "INGR", "LAND", "LEVC", "LEVI",
                   "LIGH", "LOCK", "MGEF", "MISC", "NPC_", "PGRD", "PROB", "RACE", "REGN", "REPA", "SCPT",
                   "SKIL", "SNDG", "SOUN", "SPEL", "SSCR", "STAT", "WEAP"}


HDR_PERSISTENT = 0x400
# merged/patch plugins that are never cleaned or merged from (tes3cmd's lists, plus ours)
NOT_A_MOD = {"multipatch.esp", "mashed lists.esp", "merged_leveled_lists.esp", "merged_objects.esp",
             "merged_dialogs.esp", "fogpatch.esp", "cellnamepatch.esp"}


# --------------------------------------------------------------------------
# Merging plugins (--merge): several .esp files into one
# --------------------------------------------------------------------------

def merge_input_files(items):
    """Expand files and folders (searched recursively) into a list of .esp/.esm paths, in order."""
    out, seen = [], set()
    for it in items:
        paths = []
        if os.path.isdir(it):
            for root, _dirs, files in os.walk(it):
                for fn in sorted(files, key=str.lower):
                    if fn.lower().endswith((".esp", ".esm")):
                        paths.append(os.path.join(root, fn))
        elif os.path.isfile(it):
            paths.append(it)
        else:
            print(f"--merge: {it} not found", file=sys.stderr)
        for p in paths:
            k = os.path.normcase(os.path.abspath(p))
            if k not in seen:
                seen.add(k)
                out.append(p)
    return out


def build_merge(inputs, out_name, load_order, file_sizes, log, master_paths=None, object_merges=None):
    """Merge `inputs` [(name, data)] in order. Later inputs win on conflicts, as if loaded in that order.
    master_paths (name lower -> path) gives the size of a master file_sizes doesn't have.
    object_merges ((tag, id lower) -> raw record): objects several inputs change, already merged field by
    field (merged_objects); they replace the last input's whole record.
    Returns the merged plugin's bytes and a summary dict."""
    # masters: every input's masters, in load order (unknown ones at the end, in first-seen order)
    pos = {n.lower(): i for i, n in enumerate(load_order)}
    mnames = {}
    for name, data in inputs:
        for m in plugin_masters(data):
            mnames.setdefault(m.lower(), m)
    input_l = {n.lower() for n, _d in inputs}
    for m in list(mnames):
        if m in input_l:
            raise ValueError(f"'{mnames[m]}' is a master of another input; merge its dependants separately")
    masters = sorted(mnames, key=lambda m: (not m.endswith(".esm"), pos.get(m, 10 ** 6), m))
    merged_index = {m: i + 1 for i, m in enumerate(masters)}

    records = OrderedDict()        # (tag, id) -> raw record, for ordinary records (last input wins)
    winner = {}                    # (tag, id) -> input name
    topics = OrderedDict()         # topic lower -> {"dial": raw, "infos": OrderedDict(id -> raw), "src": set}
    cells = OrderedDict()          # cell key -> {"head": [...], "refs": OrderedDict(key -> (temp?, block))}
    conflicts = []
    own_counter = [0]
    stats = Counter()
    for name, data in inputs:
        mfrom = plugin_masters(data)
        own_map = {}
        topic = None
        for off, tag, flags, body in iter_records(data):
            raw = data[off:off + 16 + len(body)]
            if tag == "TES3":
                continue
            stats[tag] += 1
            if tag == "DIAL":
                nm = cstr(first_sub(body, b"NAME") or b"")
                topic = topics.setdefault(nm.lower(), {"dial": raw, "infos": OrderedDict(), "src": set()})
                if bytes(first_sub(body, b"DATA") or b"")[:1] != bytes(first_sub(topic["dial"][16:], b"DATA") or b"")[:1]:
                    log.append(f"warning: topic '{nm}' has a different type in {name}; the first one is kept")
                elif not (flags & 0x20 or has_sub(body, b"DELE")):
                    topic["dial"] = raw                # the later input's topic record wins, as in the game
                topic["src"].add(name)
                continue
            if tag == "INFO":
                if topic is None:
                    log.append(f"warning: {name} has a response outside any topic at offset {off}; skipped")
                    continue
                iid = cstr(first_sub(body, b"INAM") or b"").lower()
                if iid in topic["infos"]:
                    conflicts.append(("INFO", iid, name))
                    del topic["infos"][iid]        # the later version takes the later position
                topic["infos"][iid] = raw
                continue
            topic = None
            if tag == "CELL":
                key, label = cell_key(body)
                if key is None:
                    log.append(f"warning: {name} has a cell without DATA at offset {off}; skipped")
                    continue
                head, pers, _nam0, temp = split_cell(body, off)
                c = cells.setdefault(key, {"head": head, "refs": OrderedDict(), "label": label})
                c["head"] = head                   # the later input's cell settings win
                c["flags"] = flags                 # ... and its record flags (persistent, blocked...)
                for is_temp, blocks in ((False, pers), (True, temp)):
                    for b in blocks:
                        b = [list(x) for x in b]
                        rkey = None
                        for x in b:
                            if x[0] in ("FRMR", "MVRF") and len(x[1]) >= 4:
                                nv, k2 = remap_frmr(struct.unpack_from("<I", x[1])[0], mfrom, merged_index,
                                                    own_map, own_counter)
                                if nv is None:
                                    raise ValueError(f"{name}: reference in {label} names master #{struct.unpack_from('<I', x[1])[0] >> 24}, "
                                                     f"which the plugin doesn't list")
                                x[1] = struct.pack("<I", nv) + bytes(x[1][4:])
                                if x[0] == "FRMR":
                                    rkey = k2
                                elif rkey is None:
                                    rkey = ("moved",) + k2
                        if rkey in c["refs"]:
                            conflicts.append(("ref", f"{label} #{rkey[1]}", name))
                        c["refs"][rkey] = (is_temp, b)
                continue
            rid = record_id(tag, body)
            if rid is None:
                log.append(f"warning: {name} has a {tag} record with no ID at offset {off}; skipped")
                continue
            if rid in records:
                conflicts.append((tag, rid[1] if len(rid) == 2 else rid, name))
            records[rid] = raw
            winner[rid] = name

    out = []
    stats["objects merged"] = 0
    for rid, raw in records.items():
        if object_merges and rid in object_merges:
            raw = object_merges[rid]
            stats["objects merged"] += 1
        out.append(raw)
    for key, c in cells.items():
        pers = [b for t, b in c["refs"].values() if not t]
        temp = [b for t, b in c["refs"].values() if t]
        subs = [x for x in c["head"]] + [x for b in pers for x in b]
        if temp:
            subs.append(["NAM0", struct.pack("<I", len(temp))])
            subs += [x for b in temp for x in b]
        nb = b"".join(pack_sub(n, d) for n, d in subs)
        out.append(b"CELL" + struct.pack("<III", len(nb), 0, c.get("flags", 0)) + nb)
    for tkey, t in topics.items():
        out.append(t["dial"])
        out.extend(t["infos"].values())

    desc = ("Merged by mwdialog_check.py from: " + ", ".join(n for n, _d in inputs))[:255]
    hedr = struct.pack("<fI", 1.3, 0) + b"mwdialog_check merge".ljust(32, b"\0") \
        + desc.encode(ENC, MW_ERRORS).ljust(256, b"\0") + struct.pack("<I", len(out))
    head = pack_sub("HEDR", hedr)
    for m in masters:
        size = file_sizes.get(m)
        if size is None and master_paths and m in master_paths:
            try:
                size = os.path.getsize(master_paths[m])
            except OSError:
                size = None
        if size is None:
            log.append(f"warning: size of master '{mnames[m]}' unknown (not installed?); written as 0 - "
                       f"the game may warn about it until the merge is resaved in the CS")
            size = 0
        head += pack_sub("MAST", mnames[m].encode(ENC, MW_ERRORS) + b"\0")
        head += pack_sub("DATA", struct.pack("<Q", size))
    tes3 = b"TES3" + struct.pack("<III", len(head), 0, 0) + head
    summary = {"records": len(out), "masters": [mnames[m] for m in masters], "conflicts": conflicts,
               "topics": len(topics), "infos": sum(len(t["infos"]) for t in topics.values()),
               "cells": len(cells), "own_refs": own_counter[0], "stats": stats}
    return tes3 + b"".join(out), summary


def run_merge(args, plugins, bsas, data_dirs):
    """--merge OUT INPUT...: merge plugins into one, after checking each input's targets are installed."""
    out_name, items = args.merge[0], args.merge[1:]
    if not out_name.lower().endswith((".esp", ".esm")):
        print("--merge: the first name is the merged plugin to write, e.g. \"My Merge.esp\"", file=sys.stderr)
        return 2
    paths = merge_input_files(items)
    if not paths:
        print("--merge: no .esp/.esm files found in the inputs given", file=sys.stderr)
        return 2
    data_abs = os.path.normcase(os.path.abspath(args.data_dir))

    def original_folder(p):
        """Where an input really lives: its own folder, or for a file deployed into Data Files, the
        folder of its hard-linked original (its Vortex mod folder)."""
        ap = os.path.abspath(p)
        if os.path.normcase(os.path.dirname(ap)) == data_abs:
            for other in hard_link_names(ap):
                if not os.path.normcase(other).startswith(data_abs + os.sep):
                    return os.path.dirname(other)
        return os.path.dirname(ap)
    if os.path.dirname(out_name):
        out_path = out_name                                   # a path given: written exactly there
    else:
        folders = [original_folder(p) for p in paths]
        out_dir = folders[0]
        if len({os.path.normcase(f) for f in folders}) > 1:
            print(f"--merge: the inputs come from {len(set(map(os.path.normcase, folders)))} folders; the merged "
                  f"plugin goes with the first one's ({out_dir}). Give a full path as the name to choose.")
        out_path = os.path.join(out_dir, out_name)
    in_data = os.path.normcase(os.path.dirname(os.path.abspath(out_path))) == data_abs
    inputs = []
    for p in paths:
        with open(p, "rb") as f:
            inputs.append((os.path.basename(p), f.read()))
    names_l = [n.lower() for n, _d in inputs]
    if len(set(names_l)) != len(names_l):
        print("--merge: two inputs have the same file name; rename one first", file=sys.stderr)
        return 2

    # What does the installed load order (plus --merge-with plugins) define?
    context = []
    for p in merge_input_files(args.merge_with or []):
        context.append((os.path.basename(p), p))
    active_l = {n.lower() for n, _p in plugins}
    scan_list = [x for x in plugins if x[0].lower() not in names_l and x[0].lower() != os.path.basename(out_path).lower()]
    scan_list += [x for x in context if x[0].lower() not in active_l]
    print(f"Reading what the load order ({len(scan_list)} plugins) defines...", file=sys.stderr)
    known = defaultdict(set)
    cells, topics = {"wilderness"}, set()
    sizes = {}
    def add_defs(data):
        nonlocal cells, topics
        ids, cl, tp = defined_names(data)
        for k, v in ids.items():
            known[k].update(v)
        cells |= cl
        topics |= tp
    for i, (n, p) in enumerate(scan_list, 1):
        try:
            with open(p, "rb") as f:
                data = f.read()
            sizes[n.lower()] = len(data)
            add_defs(data)
        except (OSError, FormatError) as e:
            print(f"  could not read {n}: {e}", file=sys.stderr)
    for _n, data in inputs:                              # inputs can refer to each other
        add_defs(data)

    print("\n" + "=" * 70 + f"\nMERGE into {os.path.basename(out_path)}\n" + "=" * 70)
    chosen, left_out = [], []
    for name, data in inputs:
        masters = plugin_masters(data)
        missing_m = [m for m in masters if m.lower() not in active_l]
        refs = plugin_references(data)
        miss = unresolved_refs(refs, known, cells, topics)
        n_miss = sum(miss.values())
        ok = not missing_m and n_miss == 0
        status = "ok" if ok else ("master not active: " + ", ".join(missing_m) if missing_m else
                                 f"{n_miss} of {len(refs)} references point at nothing")
        print(f"\n  {'+' if ok or args.merge_all else '-'} {name}: {status}")
        if miss:
            for (kind, nm), cnt in miss.most_common(6):
                print(f"      {kind} '{nm}'" + (f" (x{cnt})" if cnt > 1 else ""))
            if len(miss) > 6:
                print(f"      ... and {len(miss) - 6} more")
        (chosen if ok or args.merge_all else left_out).append((name, data))
    if left_out:
        print(f"\n  {len(left_out)} input(s) left out: the mods they patch don't seem to be installed "
              f"(add --merge-all to merge them anyway).")
    if not chosen:
        print("\nNothing to merge.")
        return 1

    log = []
    try:
        merged, summary = build_merge(chosen, os.path.basename(out_path), [n for n, _p in plugins], sizes, log,
                                      {n.lower(): p for n, p in plugins})
    except ValueError as e:
        print(f"\n--merge: {e}", file=sys.stderr)
        return 2
    for line in log:
        print(f"  {line}")
    print(f"\n  {len(chosen)} plugin(s) -> {os.path.basename(out_path)}: {summary['records']} records "
          f"({summary['topics']} topics, {summary['infos']} responses, {summary['cells']} cells"
          + (f", {summary['own_refs']} new references renumbered" if summary['own_refs'] else "") + ")")
    print(f"  masters: {', '.join(summary['masters'])}")
    if summary["conflicts"]:
        print(f"  {len(summary['conflicts'])} record(s) defined by more than one input; the later input wins:")
        for tag, rid, by in summary["conflicts"][:15]:
            print(f"    {tag} {rid}  (kept {by}'s)")

    # check the result the way the game will see it: the load order with the merge instead of its inputs
    tmp = out_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(merged)
    try:
        r_sep, r_mrg = Report(), Report()
        base = [x for x in scan_list]
        print("\nChecking: inputs loaded separately vs. the merged plugin...", file=sys.stderr)
        sep_paths = {os.path.basename(p): p for p in paths}
        quick = copy.copy(args)              # comparing records: the asset files are the same either way
        quick.asset_check = False
        scan(quick, base + [(n, sep_paths[n]) for n, _d in chosen], bsas, data_dirs, r_sep)
        scan(quick, base + [(os.path.basename(out_path), tmp)], bsas, data_dirs, r_mrg)
        chosen_l = {n.lower() for n, _d in chosen}
        mname = os.path.basename(out_path)
        def norm(r, mine):
            return Counter((("merge" if i[1].lower() in mine else i[1]), i[2], i[3], i[4])
                           for i in r.issues if i[0] == "ERROR")
        a, b = norm(r_sep, chosen_l), norm(r_mrg, {mname.lower()})
        print(f"  ERRORs in the whole load order: {sum(a.values())} with the inputs loaded separately, "
              f"{sum(b.values())} with the merged plugin instead")
        gone, new = a - b, b - a
        for title, diff, label in (("only with the inputs loaded separately (fixed by merging)", gone, "an input"),
                                   ("new with the merged plugin", new, mname)):
            if diff:
                print(f"  {sum(diff.values())} {title}:")
                for (pl, topic, info, msg), _c in list(diff.items())[:12]:
                    where = (label if pl == "merge" else pl) + (f" [{topic}]" if topic else "") + (f" {info}" if info else "")
                    print(f"    - {where}: {msg}")
    finally:
        pass

    if args.dry_run:
        os.remove(tmp)
        print("\nDry run: the merged plugin was not written.")
        return 0
    existed = os.path.exists(out_path)
    if existed:
        bak = backup_path(out_path)
        st = os.stat(out_path)
        shutil.copy2(out_path, bak)
        os.replace(tmp, out_path)
        os.utime(out_path, ns=(st.st_atime_ns, st.st_mtime_ns))
        print(f"\n  Replaced {out_path} (old version saved as {os.path.basename(bak)}, date kept)")
    else:
        os.replace(tmp, out_path)
        when = next_free_date(args.data_dir, os.path.basename(out_path))
        if when:
            os.utime(out_path, (when, when))
        print(f"\n  Wrote {out_path}" + (" (dated after the newest plugin, so it loads last)" if when else ""))
    with MT.open_log(args.fix_log, "a", encoding="utf-8") as f:
        import datetime
        f.write(f"\n==== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} merge ====\n")
        f.write(f"{os.path.basename(out_path)}: merged {', '.join(n for n, _d in chosen)}\n")
    if not in_data:
        print("\n  It's beside the originals, not in Data Files: deploy in Vortex (or copy it into Data Files) "
              "so the game sees it.")
    print("\n  Next: deactivate the merged inputs (they are in the merge now) and activate "
          f"{os.path.basename(out_path)}, e.g. with --add-all-esp. Keep the mods they patch active.")
    return 0


# --------------------------------------------------------------------------
# --auto-merge: fold small, script-free, cell-free plugins into one
# --------------------------------------------------------------------------

AUTO_MERGE_NAME = "mwdialog_check AutoMerge.esp"


NAME_SUBS_REF = {"NPCO", "ENAM", "SCRI", "INAM", "CNAM", "ONAM", "ANAM", "RNAM", "FNAM", "NAME", "PNAM",
                 "NNAM", "SNAM", "BNAM", "XSCL"}


def run_auto_merge(args, plugins, bsas, data_dirs):
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    ini = args.ini or os.path.join(game_dir, "Morrowind.ini")
    out_name = args.merge_name or AUTO_MERGE_NAME
    out_path = os.path.join(data_dir, out_name)
    rec = read_merge_record(game_dir)
    if out_name in rec and os.path.exists(out_path):
        # Rebuild: the old merge is set aside (.bak), its plugins are active again and sorted, and the
        # candidates are chosen from scratch against today's load order.
        inputs = rec[out_name]
        print("=" * 70)
        print(f"'{out_name}' already merges {len(inputs)} plugin(s): rebuilding it from scratch.")
        lookup = index_dir(data_dir)
        if args.dry_run:
            print("  Dry run: judging the candidates as if the old merge were undone (nothing is changed).")
            print("=" * 70)
            keep = [p for n, p in plugins if n.lower() != out_name.lower()]
            back = [lookup[r.lower()] for r in inputs if r.lower() in lookup]
            plugins = [(os.path.basename(p), p) for p in sort_vanilla(keep + back)]
            rec = {k: v for k, v in rec.items() if k != out_name}
        else:
            print("  Step 1: undo the old merge (kept as .bak) and make its plugins active again")
            a2 = copy.copy(args)
            a2.unmerge = [out_name]
            rc = run_unmerge(a2, plugins)
            if rc:
                return rc
            print("  Step 2: sort, so the returning plugins are in place before choosing again")
            argv2 = [args.data_dir, "--sort", "--yes", "--no-follow-up", "--fix-log", args.fix_log,
                     "--encoding", args.encoding]
            if args.no_mlox_rules:
                argv2.append("--no-mlox-rules")
            if args.no_content_order:
                argv2.append("--no-content-order")
            if args.ini:
                argv2 += ["--ini", args.ini]
            REPAIRING_INI.append(True)
            try:
                main(argv2)
            finally:
                REPAIRING_INI.clear()
            print("  Step 3: choose and merge the candidates again")
            print("=" * 70)
            plugins, bsas, data_dirs = resolve(args, Report())
            rec = read_merge_record(game_dir)
    if not os.path.isfile(ini):
        print(f"--auto-merge: {ini} not found", file=sys.stderr)
        return 2

    order = [(n, p) for n, p in plugins if n.lower() != out_name.lower()]
    pos = {n.lower(): i for i, (n, _p) in enumerate(order)}
    print(f"Reading {len(order)} plugins...", file=sys.stderr)
    profs = {}
    for i, (n, p) in enumerate(order, 1):
        try:
            profs[n.lower()] = plugin_profile(p)
        except (OSError, FormatError) as e:
            print(f"  could not read {n}: {e}", file=sys.stderr)
    # This tool's own patches (Multipatch, Cell Fixes, ...) are rebuilt after the merge, so their masters
    # and their changes don't hold a plugin back.
    ours = {x.lower() for x in OUR_PATCHES}
    is_master_of_other = {m.lower() for k, pr in profs.items() if k not in ours for m in pr["masters"]}
    lua_names = lua_named_plugins(data_dir)
    other_merges = {o.lower() for o in rec}
    reasons = {}
    cands = []
    for n, _p in order:
        low = n.lower()
        pr = profs.get(low)
        why = None
        if pr is None:
            why = "could not be read"
        elif not low.endswith(".esp"):
            why = None if False else "master file"
        elif is_our_patch(n) or low in other_merges or low in NOT_A_MOD:
            why = "made by mwdialog_check"
        elif pr["scripts"]:
            why = "has scripts"
        elif pr["cells"]:
            why = "edits cells, land or pathgrids"
        elif low in is_master_of_other:
            why = "another plugin lists it as a master"
        elif low in lua_names:
            why = "an MWSE Lua mod looks for it by name"
        elif any(m.lower() not in pos for m in pr["masters"]):
            why = "a master isn't active"
        if why:
            reasons[n] = why
        else:
            cands.append(n)
    if args.only:
        only = {o.lower() for o in args.only}
        for n in list(cands):
            if n.lower() not in only:
                cands.remove(n)
                reasons[n] = "not in --only"

    # who defines / refers to what, by load position (non-candidates only matter)
    definers = defaultdict(list)       # key -> [pos]
    first_pos = {}                     # id lower -> first position defining it
    referrers = defaultdict(list)      # name lower -> [pos]
    info_at = defaultdict(list)        # info id -> [pos]
    linkers = defaultdict(list)        # info id -> [pos] of plugins whose responses link to it
    for n, _p in order:
        low = n.lower()
        pr = profs.get(low)
        if pr is None or low in ours:
            continue
        i = pos[low]
        for k in pr["keys"]:
            definers[k].append(i)
        for x in pr["ids"]:
            first_pos.setdefault(x, i)
        for x in pr["refs"]:
            referrers[x].append(i)
        for x in pr["infos"]:
            info_at[x].append(i)
        for x in pr["links"]:
            linkers[x].append(i)

    # Two inputs changing the same leveled list: separately, the Multipatch combines their entries;
    # inside one merge only the later version would survive. Keep the first, leave the rest separate.
    lev_owner = {}
    for c in list(cands):
        clash = next((k for k in profs[c.lower()]["keys"] if k[0] in ("LEVI", "LEVC") and k in lev_owner), None)
        if clash:
            cands.remove(c)
            reasons[c] = (f"{lev_owner[clash]} (also merged) changes leveled list '{clash[1]}' too; "
                          f"left separate so the Multipatch can combine them")
            continue
        for k in profs[c.lower()]["keys"]:
            if k[0] in ("LEVI", "LEVC"):
                lev_owner[k] = c
    cset = {c.lower() for c in cands}
    end_patches = {PLACE_PATCH_NAME.lower(), MULTI_PATCH_NAME.lower()}
    # The merge always loads last (only the Multipatch and the placeholder patch come after it), so
    # every plugin after an input must leave it alone.
    P_end = max((i for i, (n, _p) in enumerate(order) if n.lower() not in end_patches | ours),
                default=len(order) - 1)
    changed = True
    while changed and cands:
        changed = False
        P = P_end
        non_c = lambda i: order[i][0].lower() not in cset
        for c in list(cands):
            pr, ci = profs[c.lower()], pos[c.lower()]
            between = lambda i: ci < i <= P and non_c(i)
            why = None
            for k in pr["keys"]:
                if k[0] == "DIAL":
                    continue
                hit = next((i for i in definers[k] if between(i)), None)
                if hit is not None:
                    why = f"{order[hit][0]} (loads between it and the merge) also changes {k[0]} '{k[-1]}'"
                    break
            if not why:
                for x in pr["ids"]:
                    if first_pos.get(x) == ci:
                        hit = next((i for i in referrers[x] if between(i)), None)
                        if hit is not None:
                            why = f"{order[hit][0]} (loads between it and the merge) uses '{x}', which it adds"
                            break
            if not why:
                for x in pr["links"]:
                    hit = next((i for i in info_at[x] if between(i)), None)
                    if hit is not None:
                        why = f"its responses link to response {x} from {order[hit][0]}, which loads between"
                        break
            if not why:
                for x in pr["infos"]:
                    hit = next((i for i in linkers[x] if between(i)), None)
                    if hit is not None:
                        why = f"{order[hit][0]} (loads between) links to its response {x}"
                        break
            if why:
                cands.remove(c)
                cset.discard(c.lower())
                reasons[c] = why
                changed = True
    if len(cands) < 2:
        print("\n--auto-merge: fewer than two plugins can be merged safely; nothing to do.")
        return 0

    total = sum(profs[c.lower()]["size"] for c in cands)
    P = P_end
    print("\n" + "=" * 70 + f"\nAUTO-MERGE into {out_name}\n" + "=" * 70)
    print(f"\n  {len(cands)} plugin(s), {total / 1048576:.1f} MB; the merge loads last, after {order[P][0]} "
          f"(only {MULTI_PATCH_NAME} and {PLACE_PATCH_NAME} load after it):")
    for c in cands:
        print(f"    + {c}")
    shown = Counter(reasons.values())
    print(f"\n  {len(order) - len(cands)} plugin(s) left as they are:")
    for why, cnt in sorted(shown.items(), key=lambda kv: -kv[1]):
        if why in ("master file",):
            continue
        if "between" in why or "links" in why or "Multipatch" in why:
            continue
        print(f"    {cnt:4d}  {why}")
    order_conf = [(c, w) for c, w in reasons.items() if "between" in w or "links" in w or "Multipatch" in w]
    if order_conf:
        print(f"    {len(order_conf):4d}  would change what wins against a plugin loading between it and the merge:")
        for c, w in order_conf[:25]:
            print(f"            {c}: {w}")
        if len(order_conf) > 25:
            print(f"            ... and {len(order_conf) - 25} more")

    inputs = []
    for c in cands:
        with open(dict(order)[c], "rb") as f:
            inputs.append((c, f.read()))
    sizes = {n.lower(): profs[n.lower()]["size"] for n, _p in order if n.lower() in profs}
    log = []
    # Objects two or more inputs change: the merge would keep only the last input's whole record, and
    # with every input's masters on one plugin the Multipatch can no longer tell what that input changed.
    # Merge them field by field now, each input measured against its own masters (as the Multipatch did
    # while they were separate plugins).
    shared = Counter(k for c in cands for k in profs[c.lower()]["keys"] if k[0] in MERGE_TAGS)
    shared = {k for k, cnt in shared.items() if cnt >= 2}
    omerge = {}
    if shared and not getattr(args, "no_merge_objects", False):
        print(f"  Merging {len(shared)} object(s) that several of the merged plugins change...", file=sys.stderr)
        mi = merged_inputs_of(game_dir, data_dir)
        for key, raw, note in object_merges(order, file_ok=merge_file_check(args, None), merged_inputs=mi,
                                            only=shared):
            omerge[key] = raw
            if len(omerge) <= 12:
                log.append("object merge: " + note)
        if len(omerge) > 12:
            log.append(f"object merge: ... and {len(omerge) - 12} more")
        if omerge:
            log.append(f"{len(omerge)} object(s) merged field by field from the inputs that change them")
    try:
        merged, summary = build_merge(inputs, out_name, [n for n, _p in order], sizes, log,
                                      {n.lower(): p for n, p in order}, object_merges=omerge)
    except ValueError as e:
        print(f"\n--auto-merge: {e}", file=sys.stderr)
        return 2
    for line in log:
        print(f"  {line}")
    print(f"\n  -> {out_name}: {summary['records']} records ({summary['topics']} topics, "
          f"{summary['infos']} responses); masters: {', '.join(summary['masters'])}")
    if len(summary["masters"]) > 255:
        print("--auto-merge: the merge would need more than 255 masters", file=sys.stderr)
        return 2

    tmp = out_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(merged)
    cl = {c.lower() for c in cands}
    new_order = [x for x in order if x[0].lower() not in cl]
    new_order.insert(P + 1 - sum(1 for c in cands if pos[c.lower()] <= P), (out_name, tmp))
    print("\nChecking the load order before and after...", file=sys.stderr)
    r_a, r_b = Report(), Report()
    # compared without this tool's own patches: they still name the merged plugins as masters until they
    # are rebuilt (--full does that next), which isn't an error the merge makes
    scan(args, [x for x in order if x[0].lower() not in ours], bsas, data_dirs, r_a)
    scan(args, [x for x in new_order if x[0].lower() not in ours], bsas, data_dirs, r_b)
    def norm(r):
        return Counter((("merge" if i[1].lower() in cl or i[1].lower() == tmp_l else i[1]), i[2], i[3], i[4])
                       for i in r.issues if i[0] == "ERROR")
    tmp_l = out_name.lower()
    a, b = norm(r_a), norm(r_b)
    print(f"  ERRORs in the whole load order: {sum(a.values())} now, {sum(b.values())} with the merge")
    gone, new = a - b, b - a
    for title, diff in (("go away", gone), ("are NEW with the merge", new)):
        if diff:
            print(f"  {sum(diff.values())} {title}:")
            for (pl, topic, info, msg), _c in list(diff.items())[:12]:
                print(f"    - {'(merged plugins)' if pl == 'merge' else pl}"
                      f"{' [' + topic + ']' if topic else ''}{' ' + info if info else ''}: {msg}")
    if new and not args.yes and not args.dry_run:
        print("\nThe merge adds errors; not applied. Add --yes to apply it anyway.")
        os.remove(tmp)
        return 1
    if args.dry_run:
        os.remove(tmp)
        print("\nDry run: nothing written, nothing deactivated.")
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            os.remove(tmp)
            print("\nNot running interactively; add --yes to apply.")
            return 1
        if input(f"\nWrite {out_name} and deactivate the {len(cands)} plugins it replaces? [y/N] ").strip().lower() \
                not in ("y", "yes"):
            os.remove(tmp)
            print("Nothing changed.")
            return 0
    if os.path.exists(out_path):
        shutil.copy2(out_path, backup_path(out_path))
    os.replace(tmp, out_path)
    when = os.path.getmtime(order[P][1]) + 60     # just after the last plugin (before our end patches)
    os.utime(out_path, (when, when))
    ini_order = [n for n, _p in new_order]
    bak = set_game_files(ini, ini_order, "auto-merge")
    rec[out_name] = list(cands)
    write_merge_record(game_dir, rec)
    with MT.open_log(args.fix_log, "a", encoding="utf-8") as f:
        import datetime
        f.write(f"\n==== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} auto-merge ====\n")
        f.write(f"{out_name}: merged and deactivated {', '.join(cands)}\n")
    print(f"\n  Wrote {out_path} (dated just after {order[P][0]}, so it loads last; --sort keeps it there)")
    print(f"  {LOAD_ORDER_FILE}: {len(cands)} plugin(s) deactivated, {out_name} activated (old list saved as {bak})")
    print(f"  Recorded in {MERGE_RECORD}; --add-all-esp will leave the merged plugins out. "
          f"Undo with --unmerge \"{out_name}\".")
    stale = [n for n, _p in new_order if n.lower() in ours]
    if stale:
        print(f"  Rebuild this tool's patches before playing ({', '.join(stale)} still name the merged plugins "
              f"as masters): --full does it next; otherwise run --sort --fix --multipatch.")
    args.merged_now = True
    return 0


def run_unmerge(args, plugins):
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    ini = args.ini or os.path.join(game_dir, "Morrowind.ini")
    rec = read_merge_record(game_dir)
    names = args.unmerge or list(rec)
    todo = [n for n in rec if n.lower() in {x.lower() for x in names}]
    if not todo:
        print("--unmerge: no recorded merge by that name. Recorded: " + (", ".join(rec) or "none"))
        return 1
    active = [n for n, _p in plugins]
    restore = []
    for out in todo:
        restore += rec[out]
        p = os.path.join(data_dir, out)
        if os.path.exists(p):
            bak = backup_path(p)
            os.replace(p, bak)
            print(f"  {out}: removed (kept as {os.path.basename(bak)})")
        del rec[out]
    lookup = index_dir(data_dir)
    keep = [n for n in active if n.lower() not in {t.lower() for t in todo}]
    red_off = {n.lower() for n in read_redundant(game_dir)[0]}
    left_off = [r for r in restore if r.lower() in red_off]      # --redundant turned these off: they stay off
    back = [lookup[r.lower()] for r in restore if r.lower() in lookup and r.lower() not in red_off]
    missing = [r for r in restore if r.lower() not in lookup]
    full = sort_vanilla([lookup[n.lower()] for n in keep if n.lower() in lookup] + back)
    bak = set_game_files(ini, [os.path.basename(p) for p in full], "unmerge")
    write_merge_record(game_dir, rec)
    pending = read_merge_rebuild(game_dir)
    if pending:                                   # undone: nothing left to rebuild without those plugins
        write_merge_rebuild(game_dir, OrderedDict((k, v) for k, v in pending.items()
                                                  if k.lower() not in {t.lower() for t in todo}))
    print(f"  {len(back)} plugin(s) active again" + (f"; not found: {', '.join(missing)}" if missing else "")
          + (f"; left off ({REDUNDANT_RECORD}): {', '.join(left_off)}" if left_off else "")
          + f" (old list saved as {bak}).")
    return 0


def clean_targets(plugins, only):
    for name, path in plugins:
        low = name.lower()
        if not low.endswith(FIXABLE_EXT) or low in NOT_A_MOD or is_our_patch(name):
            continue
        if only is not None and low not in only:
            continue
        yield name, path


def run_clean(args, plugins, only):
    """tes3cmd clean, in place: duplicate instances, AMBI/WHGT, duplicate records, Evil GMSTs, junk cells."""
    lookup = {n.lower(): p for n, p in plugins}
    targets = list(clean_targets(plugins, only))
    print(f"\nCLEAN: checking {len(targets)} plugin(s) against their masters...", file=sys.stderr)
    needs, info = defaultdict(lambda: (set(), set())), {}
    for name, path in targets:
        with open(path, "rb") as f:
            data = f.read()
        try:
            masters = plugin_masters(data)
            missing = [m for m in masters if m.lower() not in lookup]
            persistent, wanted = set(), []
            for off, tag, flags, body in iter_records(data):
                if tag == "TES3":
                    continue
                if flags & HDR_PERSISTENT:
                    nm = first_sub(body, b"NAME")
                    if nm is not None:
                        persistent.add(cstr(nm).lower())
                rid = record_id(tag, body)
                if rid is not None:
                    wanted.append((tag, rid))
        except FormatError as e:
            print(f"  SKIP {name}: corrupt ({e})")
            continue
        if missing:
            print(f"  SKIP {name}: master '{missing[0]}' is not loaded")
            continue
        for m in (x.lower() for x in masters):
            for tag, rid in wanted:
                if tag in CLEAN_DUP_TYPES:
                    needs[m][0].add(rid)
                if tag == "CELL":
                    needs[m][1].add(rid[1])
        info[name] = (path, masters, persistent)
    recs, cells = index_masters(needs, lookup)

    results = {}                                      # name -> (records out, Counter, details)
    load_pos = {n.lower(): i for i, (n, _p) in enumerate(plugins)}
    for name, (path, masters, persistent) in info.items():
        with open(path, "rb") as f:
            data = f.read()
        masters_l = [m.lower() for m in masters]         # MAST order: what FRMR master numbers count
        by_load = sorted(masters_l, key=lambda x: load_pos.get(x, -1))   # load order: the last one wins
        out, stats, details = [], Counter(), []
        for off, tag, flags, body in iter_records(data):
            raw = data[off:off + 16 + len(body)]
            if tag == "TES3":
                out.append(raw)
                continue
            rid = record_id(tag, body)
            if tag == "GMST" and rid and rid[1] in EVIL_GMSTS:
                t, v = EVIL_GMSTS[rid[1]]
                if first_sub(body, t.encode("ascii")) == v:
                    stats["Evil GMST"] += 1
                    details.append(f"Evil GMST {rid[1]}")
                    continue
            if tag in CLEAN_DUP_TYPES and rid is not None and masters_l:
                dg = (digest(body), flags)
                # compare with the version this plugin overrides (the last master that has the record), not
                # with any master: a copy of an earlier master's version deliberately undoes a later one
                winner = next((recs[m][rid] for m in reversed(by_load) if rid in recs.get(m, {})), None)
                if winner == dg:
                    stats["duplicate record"] += 1
                    details.append(f"duplicate record {tag} {rid[1] if tag != 'CELL' else cell_key(body)[1]}")
                    continue
            if tag == "CELL" and masters_l:
                key, label = cell_key(body)
                infos = [cells[m][key] for m in by_load if key in cells.get(m, {})]
                if infos:
                    nb, what = clean_cell(body, off, masters_l, name.lower(), infos, persistent)
                    for w in what:
                        stats["duplicate instance" if w.startswith("duplicate object instance")
                              else "junk cell" if w.startswith("junk") else w] += 1
                        details.append(f"[cell {label}] {w}")
                    if nb is None:
                        continue
                    if what:
                        out.append(b"CELL" + struct.pack("<I", len(nb)) + data[off + 8:off + 16] + nb)
                        continue
            out.append(raw)
        if stats:
            results[name] = (path, out, stats, details)

    if not results:
        print("  Nothing to clean.")
        return {}
    for name, (_p, _o, stats, _d) in results.items():
        print(f"  {name}: " + ", ".join(f"{n} {k}" for k, n in sorted(stats.items())))
    if args.dry_run:
        print("Dry run: no files were changed.")
        return {}
    if not args.yes:
        if not sys.stdin.isatty() or input(f"\nClean {len(results)} plugin(s) in place? Each is backed up "
                                           f"first and keeps its date. [y/N] ").strip().lower() not in ("y", "yes"):
            print("Nothing cleaned.")
            return {}
    import datetime
    with MT.open_log(args.fix_log, "a", encoding="utf-8") as f:
        f.write(f"\n==== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} clean ====\n")
        for name, (path, out, stats, details) in results.items():
            try:
                bak = write_inplace(path, out)
            except Exception as e:                   # one plugin's problem never stops the others halfway
                print(f"  {name}: NOT cleaned ({type(e).__name__}: {e})")
                continue
            f.write("".join(f"{name}: cleaned {d}\n" for d in details))
            f.write(f"{name}: backup saved as {os.path.basename(bak)}\n")
    print(f"  Cleaned {len(results)} plugin(s); details in {args.fix_log}")
    return {n: True for n in results}


# --------------------------------------------------------------------------
# Multipatch (ported from tes3cmd "multipatch"): merged leveled lists, fog bug, cell names
# --------------------------------------------------------------------------

MULTI_PATCH_NAME = "mwdialog_check Multipatch.esp"
BETHESDA_MASTERS = {"morrowind.esm", "tribunal.esm", "bloodmoon.esm"}


def multipatch_source(plugin, cells=False):
    """Plugins the multipatch reads from. tes3cmd skips merged/patch plugins, and for cells also the
    Bethesda masters."""
    low = (plugin or "").lower()
    if low in NOT_A_MOD or low in [x.lower() for x in OUR_PATCHES]:
        return False
    return not (cells and low in BETHESDA_MASTERS)


# --------------------------------------------------------------------------
# Merged objects (like TES3Merge): when several mods change the same object, the game uses the last one's
# whole record; this combines what each of them changed
# --------------------------------------------------------------------------

MERGE_TAGS = ("NPC_", "CREA", "ARMO", "CLOT", "WEAP", "MISC", "BOOK", "ALCH", "INGR", "LIGH", "APPA", "LOCK",
              "PROB", "REPA", "CONT", "ACTI", "DOOR", "SPEL", "ENCH", "CLAS", "RACE", "BSGN", "BODY")


def merge_file_check(args, world):
    """For the object merge: does a model/icon path load? The asset index when this run built one, else a
    quick look at loose files and the game's own archives."""
    A = getattr(world, "assets", None)
    if A is not None:
        def ok_indexed(kind, v):
            if ModelAssets.fatal(A.field_problem(kind, v)):
                return False
            if kind == "mesh":
                try:
                    return not nif_is_empty(A._mesh_bytes(A.norm(v)) or b"")
                except OSError:
                    return True
            return True
        return ok_indexed
    data_dir = os.path.abspath(args.data_dir)
    bsa = set()
    for b in ("Morrowind.bsa", "Tribunal.bsa", "Bloodmoon.bsa"):
        try:
            bsa |= {n.replace("/", "\\") for n in bsa_file_names(os.path.join(data_dir, b))}
        except (OSError, FormatError, NameError):
            pass
    cache = {}

    def ok(kind, v):
        top = {"mesh": "meshes", "icon": "icons"}[kind]
        rel = (top + "\\" + v.strip().lower().replace("/", "\\")).replace("\\\\", "\\")
        if rel in cache:
            return cache[rel]
        full = os.path.join(data_dir, rel)
        good = False
        if os.path.isfile(full):
            if kind == "mesh":
                try:
                    with open(full, "rb") as f:
                        data = f.read(65536)
                    good = data.startswith((b"NetImmerse File Format", b"Gamebryo File Format")) \
                        and not nif_is_empty(data)
                except OSError:
                    good = False
            else:
                good = True
        elif rel in bsa:
            good = True
        elif kind == "icon":                         # icons: a .dds may stand for the named .tga
            stem = os.path.splitext(rel)[0]
            good = any(os.path.isfile(os.path.join(data_dir, stem + e)) or stem + e in bsa
                       for e in (".dds", ".tga", ".bmp"))
        cache[rel] = good
        return good
    return ok


def merged_objects(plugins, known=None, file_ok=None, merged_inputs=None, only=None):
    """Records of MERGE_TAGS that several plugins change in different ways, merged field by field: what each
    plugin changed (compared with the version it was made against: its masters' latest, or the original)
    is kept; where two changed the same field, the later one wins. Returns ([record bytes], [notes]).
    merged_inputs: {merged plugin lower: [(input name, path)]} - see object_merges. only: a set of
    (tag, id lower) to look at, the rest is skipped."""
    out = object_merges(plugins, known, file_ok, merged_inputs, only)
    return [r for _k, r, _n in out], [n for _k, _r, n in out]


def expand_merged(plugins, merged_inputs):
    """The load order with each merged plugin (--merge/--auto-merge) replaced by the plugins it was built
    from, in their order, when all of them can still be read. A merged plugin lists every input's masters,
    so measured as one plugin its records look like they were made against all of those: an input made
    against Morrowind.esm alone then seems to undo what another master changed (Expanded Sounds' script
    and sound on the prison ship lanterns). Measured as its inputs, each record is compared with the
    version its own plugin was made against. Returns (order, {input lower: merged plugin lower})."""
    if not merged_inputs:
        return list(plugins), {}
    active = {n.lower() for n, _p in plugins}
    out, owner = [], {}
    for n, p in plugins:
        ins = merged_inputs.get(n.lower())
        if ins and all(ip and os.path.isfile(ip) for _i, ip in ins) \
                and not any(i.lower() in active for i, _ip in ins):
            for i, ip in ins:
                out.append((i, ip))
                owner[i.lower()] = n.lower()
        else:
            out.append((n, p))
    return out, owner


def object_merges(plugins, known=None, file_ok=None, merged_inputs=None, only=None):
    """merged_objects' work: [((tag, id), record bytes, note)]. With merged_inputs, a merged plugin is
    looked at as the plugins it was built from (expand_merged); a result the merged plugin already has
    is left out."""
    real = [(n, p) for n, p in plugins if multipatch_source(n)]
    vorder, owner = expand_merged(real, merged_inputs)
    real_path = {n.lower(): p for n, p in real}
    order = [(n, p) for n, p in vorder if multipatch_source(n)]
    names = [n.lower() for n, _p in order]
    masters = {}
    for n, p in order:
        try:
            masters[n.lower()] = [m.lower() for m in read_header_masters(p)]
        except (OSError, FormatError):
            masters[n.lower()] = []
    closure = {}

    def deps(n):
        if n not in closure:
            seen, stack = set(), list(masters.get(n, []))
            while stack:
                x = stack.pop()
                if x not in seen:
                    seen.add(x)
                    stack += masters.get(x, [])
            closure[n] = seen
        return closure[n]
    print("  Reading objects several plugins change...", file=sys.stderr)
    want = set(MERGE_TAGS)
    versions = defaultdict(list)                     # (tag, id) -> [(plugin index, digest, offset, deleted)]
    defined = set()                                  # every id an active plugin defines (scripts too)
    for i, (n, p) in enumerate(order):
        try:
            data = read_plugin_bytes(p)
            recs_i = list(iter_records(data))        # a damaged file is left out, not half-read
        except (OSError, FormatError) as e:
            print(f"  {n}: left out of the object merge ({e})", file=sys.stderr)
            continue
        for pos, tag, fl, body in recs_i:
            try:
                if tag == "SCPT":
                    hd = first_sub(body, b"SCHD")
                    if hd:
                        defined.add(cstr(hd[:32]).lower())
                elif tag not in ("CELL", "INFO", "DIAL", "LAND", "PGRD", "TES3"):
                    nm = first_sub(body, b"NAME")
                    if nm:
                        defined.add(cstr(nm).lower())
                if tag in want:
                    nm = first_sub(body, b"NAME")
                    if nm and (only is None or (tag, cstr(nm).lower()) in only):
                        dele = bool(fl & 0x20) or first_sub(body, b"DELE") is not None
                        versions[(tag, cstr(nm).lower())].append((i, hashlib.md5(body).digest(), pos, dele))
            except FormatError:
                continue
    cands = {k: v for k, v in versions.items() if len(v) >= 3 and not any(x[3] for x in v)
             and len({x[1] for x in v[1:]}) >= 2}
    need = defaultdict(set)
    for v in cands.values():
        for i, _d, off, _x in v:
            need[i].add(off)
    bodies = {}
    for i, offs in need.items():
        data = read_plugin_bytes(order[i][1])
        for off in offs:
            size, _u, fl = struct.unpack_from("<III", data, off + 4)
            bodies[(i, off)] = (data[off + 16:off + 16 + size], fl)
    merged_recs = {}                                 # merged plugin lower -> {(tag, id): body}

    def merged_body(mp, key):
        if mp not in merged_recs:
            got = {}
            try:
                for _o, t, _f, b in iter_records(read_plugin_bytes(real_path[mp])):
                    if t in want:
                        nm = first_sub(b, b"NAME")
                        if nm:
                            got[(t, cstr(nm).lower())] = b
            except (OSError, FormatError, KeyError):
                pass
            merged_recs[mp] = got
        return merged_recs[mp].get(key)
    out = []
    for (tag, rid), v in sorted(cands.items()):
        vers = [(i, bodies[(i, off)][0]) for i, _d, off, _x in v]

        def parent_of(k, vers=vers):
            seen = deps(names[vers[k][0]])
            return next((j for j in range(k - 1, -1, -1) if names[vers[j][0]] in seen), 0)
        try:
            body = merge_object(tag, vers, parent_of, known, defined, file_ok)
        except FormatError:
            continue
        if body is None:
            continue
        mp = owner.get(names[v[-1][0]])
        if mp is not None and merged_body(mp, (tag, rid)) == body:
            continue                                 # the merged plugin already has it (its own object merge)
        fl = bodies[(v[-1][0], v[-1][2])][1]
        out.append(((tag, rid), tag.encode("ascii") + struct.pack("<III", len(body), 0, fl) + body,
                    f"{tag} {rid}: merged from " + ", ".join(order[i][0] for i, *_r in v[1:])))
    return out


def merged_inputs_of(game_dir, data_dir):
    """{merged plugin lower: [(input name, path or None)]} from mwdialog_merged.txt."""
    files = index_dir(data_dir)
    return {k.lower(): [(i, files.get(i.lower())) for i in ins] for k, ins in read_merge_record(game_dir).items()}


def run_multipatch(args, plugins, world):
    """Build MULTI_PATCH_NAME: reverted cell names, fog-bugged cells, merged leveled lists."""
    print("\n" + "=" * 70 + "\nMULTIPATCH\n" + "=" * 70)
    if any(n.lower() == "multipatch.esp" for n, _p in plugins):
        print("  WARNING: tes3cmd's multipatch.esp is active. Deactivate it: two merged-list plugins override\n"
              "  each other, and the last one loaded wins completely.")
    recs, notes = [], []
    used = getattr(world, "script_cells", set())
    renamed = [(c, t) for c, t in sorted(world.rencells.items()) if t["reverted"] and t["rec"]
               and t["orig"].strip().lower() not in used]       # a master's name that scripts use wins
    heads = getattr(world, "cell_heads", {})

    def cell_header(key, nm, d, ambi=None):
        """The latest header of the cell (region, water, map colour... as the winning record has them), with
        only NAME (and for fog, DATA and AMBI) changed; just NAME/DATA(/AMBI) if no header was seen."""
        head = heads.get(key)
        if not head:
            subs = [("NAME", nm), ("DATA", d)] + ([("AMBI", ambi)] if ambi is not None else [])
        else:
            subs = []
            for n, v in head:
                if n == "NAME":
                    v = nm
                elif n == "DATA" and ambi is not None:
                    v = d
                elif n == "AMBI" and ambi is not None:
                    v = ambi
                subs.append((n, v))
            if not any(n == "NAME" for n, _v in subs):
                subs.insert(0, ("NAME", nm))
            if ambi is not None and not any(n == "AMBI" for n, _v in subs):
                subs.append(("AMBI", ambi))
        return b"".join(pack_sub(n, v) for n, v in subs)
    for (x, y), t in renamed:
        nm, d = t["rec"]
        nb = cell_header(("e", x, y), nm, d)
        recs.append(b"CELL" + struct.pack("<III", len(nb), 0, 0) + nb)
        notes.append(f"cell ({x}, {y}): keeps the name '{t['name']}' given by {t['plug']}")
    for low in sorted(world.fogcells):
        plugin, nm, d, ambi = world.fogcells[low]
        d = d[:8] + struct.pack("<f", 0.01) + d[12:]
        ambi = ambi[:12] + struct.pack("<f", 0.01) + ambi[16:]
        nb = cell_header(("i", low), nm, d, ambi)
        recs.append(b"CELL" + struct.pack("<III", len(nb), 0, 0) + nb)
        notes.append(f"cell '{cstr(nm)}': fog density 0 (from {plugin}) set to 0.01")
    counts = Counter()
    known = set(getattr(world, "all_ids", {}) or ()) or None     # ids an active plugin defines
    mclosure = {}

    def masters_of(plugin):
        """Every master of `plugin` (lowercase), masters' masters included."""
        if plugin not in mclosure:
            seen, stack = set(), [m.lower() for m in world.masters.get(plugin, [])]
            while stack:
                x = stack.pop()
                if x not in seen:
                    seen.add(x)
                    stack += [m.lower() for m in world.masters.get(x, [])]
            mclosure[plugin] = seen
        return mclosure[plugin]
    for tag in ("LEVC", "LEVI"):
        for (t, low), defs in sorted(world.levlists.items()):
            if t != tag:
                continue
            if defs[-1][2]:
                continue                             # the last plugin deletes the list: leave it deleted
            defs = [x for x in defs if not x[2]]
            if len(defs) < 3:
                continue                             # once: nothing to merge; twice: the last already wins
            rec, n = merge_levlist(tag, defs, known, masters_of)
            recs.append(rec)
            counts[tag] += 1
            notes.append(f"{tag} {cstr(first_sub(defs[-1][1], b'NAME'))}: merged from "
                         f"{len(defs)} plugins ({n} entries)")
    mrecs, mnotes = ([], []) if getattr(args, "no_merge_objects", False) else \
        merged_objects(plugins, known, file_ok=merge_file_check(args, world),
                       merged_inputs=merged_inputs_of(os.path.dirname(os.path.abspath(args.data_dir)),
                                                      args.data_dir))
    recs += mrecs
    notes += mnotes
    print(f"  {len(renamed)} cell name(s) protected, {len(world.fogcells)} fog-bugged cell(s), "
          f"{counts['LEVC']} creature and {counts['LEVI']} item list(s) merged, {len(mrecs)} object(s) several "
          f"mods change merged")
    if args.dry_run:
        print("Dry run: no files were changed.")
        return
    path = os.path.join(args.data_dir, MULTI_PATCH_NAME)
    is_new = not os.path.exists(path)
    if is_new and not recs:
        print("  No patching necessary; the multipatch was not created.")
        return
    write_patch(path, [], [], [], extra=recs,
                description="Merged leveled lists, fog bug and cell name fixes (tes3cmd multipatch), "
                            "generated by mwdialog_check.py. Load this LAST.")
    if is_new:
        when = next_free_date(args.data_dir, MULTI_PATCH_NAME)
        if when:
            os.utime(path, (when, when))
    import datetime
    with MT.open_log(args.fix_log, "a", encoding="utf-8") as f:
        f.write(f"\n==== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} multipatch ====\n")
        f.write("".join(f"{MULTI_PATCH_NAME}: {n}\n" for n in notes))
    print(f"  {MULTI_PATCH_NAME}: written with {len(recs)} record(s)" + (" (new: load it LAST)" if is_new else ""))
    # back in the load order (last) if it isn't there: new, or set aside by --full until now
    if not args.dry_run:
        cur = read_load_order(args) or []
        if cur and MULTI_PATCH_NAME.lower() not in {n.lower() for n in cur}:
            game_dir = os.path.dirname(os.path.abspath(args.data_dir))
            set_game_files(args.ini or os.path.join(game_dir, "Morrowind.ini"), cur + [MULTI_PATCH_NAME],
                           "--multipatch")
            print(f"  {MULTI_PATCH_NAME}: added to the load order (last)")


# --------------------------------------------------------------------------
# Header (ported from tes3cmd "header": show/set Author and Description)
# --------------------------------------------------------------------------

AUTH_OFF, AUTH_LEN = 16 + 8 + 8, 32           # TES3 record header, HEDR header, version + file type
DESC_OFF, DESC_LEN = AUTH_OFF + AUTH_LEN, 256


CELL_SETTING_NAMES = {"AMBI": "lighting and fog", "WHGT": "water height", "INTV": "water height",
                      "RGNN": "region", "FLAGS": "cell flags (water / no sleeping / behaves like exterior)"}


def _cell_settings(head):
    """The settings a cell header carries, comparable across plugins."""
    out = {}
    for n, d in head:
        if n == "DATA" and len(d) >= 4:
            out["FLAGS"] = struct.unpack_from("<I", d)[0] & 0x86
        elif n == "AMBI" and len(d) >= 16:
            amb, sun, fog = d[0:4], d[4:8], d[8:12]
            dens = struct.unpack_from("<f", d, 12)[0]
            out["AMBI"] = (amb, sun, fog, round(dens, 3))
        elif n == "WHGT" and len(d) >= 4:
            out["WHGT"] = round(struct.unpack_from("<f", d)[0], 1)
        elif n == "INTV" and len(d) >= 4:
            out["WHGT"] = float(struct.unpack_from("<i", d)[0])
        elif n == "RGNN":
            out["RGNN"] = cstr(d).lower()
    return out


def _show_setting(field, v):
    if field == "AMBI":
        col = lambda b: "#%02x%02x%02x" % (b[0], b[1], b[2])
        return f"ambient {col(v[0])}, sun {col(v[1])}, fog {col(v[2])} density {v[3]}"
    if field == "FLAGS":
        bits = [t for b, t in ((0x02, "water"), (0x04, "no sleeping"), (0x80, "like exterior")) if v & b]
        return ", ".join(bits) or "none"
    return str(v)


                                                # leads somewhere of its own), containers (their contents)


def run_cell_conflicts(args, plugins, collect=False):
    """--cell-conflicts: plugins that don't know about each other (neither is a master of the other)
    but work on the same cells: both add many new objects in the same spot, both change the same
    placed objects differently, or both change the same cell settings. Report only."""
    if not collect:
        print("\n" + "=" * 70 + "\nCELL CONFLICTS\n" + "=" * 70)
    min_new = getattr(args, "conflict_min", 5)
    skip = {x.lower() for x in OUR_PATCHES} | {AUTO_MERGE_NAME.lower(), CELL_WINNER_PATCH.lower()}
    black = read_conflict_blacklist(os.path.dirname(os.path.abspath(args.data_dir)))
    left_out = [n for n, _p in plugins if conflict_blacklisted(n, black)]
    skip |= {n.lower() for n in left_out}
    if left_out and not collect:
        print(f"  left out ({CONFLICT_BLACKLIST_FILE}: they always lose): " + ", ".join(left_out))
    order = [(n, p) for n, p in plugins if n.lower() not in skip]
    pos = {n.lower(): i for i, (n, _p) in enumerate(order)}
    name_of = {n.lower(): n for n, _p in order}
    masters = {}
    for n, p in order:
        try:
            masters[n.lower()] = [m.lower() for m in read_header_masters(p)]
        except (OSError, FormatError):
            masters[n.lower()] = []
    closure = {}

    def deps(n):
        if n not in closure:
            closure[n] = set()
            seen, stack = set(), list(masters.get(n, []))
            while stack:
                x = stack.pop()
                if x not in seen:
                    seen.add(x)
                    stack += masters.get(x, [])
            closure[n] = seen
        return closure[n]

    related = lambda a, b: a in deps(b) or b in deps(a)
    labels = {}
    new_objs = defaultdict(dict)          # cell key -> plugin -> [(id, x, y, z)]
    settings = defaultdict(list)          # cell key -> [(plugin, {field: value})]
    edits = defaultdict(list)             # (owner, index) -> [(plugin, digest, deleted, object, cell key)]
    cells_of = defaultdict(set)           # plugin -> cells it has a record for (patches are judged by these)
    own_pos = defaultdict(dict)           # interior -> (owner, index) -> (object, x, y, z, owner)
    deletions = defaultdict(lambda: defaultdict(set))   # interior -> plugin -> master references it deletes
    door_final = {}                       # door ref -> (plugin index, cell key, (x,y,z), dest cell, (x,y,z,rz), deleted)
    moved = {}                            # (interior, ref) -> (plugin index, x, y, z): the last plugin to place it

    # interiors where you chose whose version wins (CELL_WINNERS_FILE): the Cell Fixes patch takes the
    # loser's work there out, so it doesn't count against anyone in that place
    game_dir = os.path.dirname(os.path.abspath(args.data_dir))
    lost_in = {("i", k): l.lower() for k, (_c, w, l) in read_cell_winners(game_dir).items()
               if w.lower() in pos and l.lower() in pos}

    def read(n, p, keys=None, own_digests=None):
        try:
            data = open(p, "rb").read()
        except OSError:
            return
        mast = masters.get(n.lower(), [])
        esm = n.lower().endswith(".esm")
        for off, tag, flags, body in iter_records(data):
            if tag != "CELL":
                continue
            key, label = cell_key(body)
            if key is None or (keys is not None and key not in keys and own_digests is None):
                continue
            head, pers, _n0, temp = split_cell(body)
            if own_digests is None and lost_in.get(key) == n.lower():
                cells_of[n.lower()].add(key)
                continue                         # its version of this place is set aside
            if own_digests is None:
                cells_of[n.lower()].add(key)
                labels.setdefault(key, label)
                st = _cell_settings(head)
                if st:
                    settings[key].append((n.lower(), st))
            pts = []
            for block in pers + temp:
                bk = block_key(block, mast, n.lower())
                if bk is None:
                    continue
                if own_digests is not None:
                    if bk in own_digests:
                        own_digests[bk] = block_digest(block)
                    continue
                oid = next((cstr(d) for s, d in block if s == "NAME"), "")
                deleted = any(s == "DELE" for s, _d in block)
                # the last version of each door's destination (.esm files are read after the .esp files,
                # so the load order position decides, not the reading order)
                dt = next((d for s, d in block if s == "DODT" and len(d) >= 24), None)
                prev = door_final.get(bk)
                if (dt is not None or (deleted and prev)) and (prev is None or prev[0] <= pos[n.lower()]):
                    if dt is None:
                        door_final[bk] = (pos[n.lower()],) + prev[1:5] + (True,)
                    else:
                        dn = next((cstr(d).lower() for s, d in block if s == "DNAM"), "")
                        dd = next((d for s, d in block if s == "DATA" and len(d) >= 24), None)
                        to = struct.unpack_from("<6f", dt)
                        door_final[bk] = (pos[n.lower()], key, struct.unpack_from("<3f", dd) if dd else None,
                                          dn, (to[0], to[1], to[2], to[5]), deleted)
                if bk[0] == n.lower():
                    if deleted:
                        continue
                    dd = next((d for s, d in block if s == "DATA" and len(d) >= 24), None)
                    if dd is not None:
                        x, y, z = struct.unpack_from("<3f", dd)
                        pts.append((oid, x, y, z))
                        if key[0] == "i":
                            own_pos[key][bk] = (oid, x, y, z, n.lower())
                else:
                    if deleted and key[0] == "i":
                        deletions[key][n.lower()].add(bk)
                    elif key[0] == "i":            # moved by a later plugin (a patch): where it ends up
                        dd = next((d for s, d in block if s == "DATA" and len(d) >= 24), None)
                        if dd is not None and moved.get((key, bk), (-1,))[0] < pos[n.lower()]:
                            moved[(key, bk)] = (pos[n.lower()],) + struct.unpack_from("<3f", dd)
                    if not esm:
                        edits[bk].append((n.lower(), block_digest(block), deleted, oid, key))
            if pts:
                new_objs[key][n.lower()] = pts

    print(f"  Reading cells in {len(order)} plugins...", file=sys.stderr)
    for n, p in order:                     # the .esp files first: they decide which cells matter
        if not n.lower().endswith(".esm"):
            read(n, p)
    esp_cells = set(new_objs) | set(settings)
    for n, p in order:
        if n.lower().endswith(".esm"):
            read(n, p, keys=esp_cells)
    for (key, bk), (_pi, x, y, z) in moved.items():
        v = own_pos.get(key, {}).get(bk)
        if v is not None and pos.get(v[4], -1) < _pi:
            own_pos[key][bk] = (v[0], x, y, z, v[4])
    # the master's own version of each contested reference, so unchanged ("dirty") copies don't count
    contested = {bk: v for bk, v in edits.items() if len({d for _p, d, _x, _o, _k in v}) > 1
                 and len({p for p, *_r in v}) > 1}
    by_owner = defaultdict(dict)
    for bk in contested:
        by_owner[bk[0]][bk] = None
    for owner, want in by_owner.items():
        p = dict((n.lower(), pp) for n, pp in order).get(owner)
        if p:
            read(name_of[owner], p, keys=set(), own_digests=want)

    pairs = defaultdict(lambda: {"place": [], "refs": [], "settings": [], "score": 0})

    def pair_key(a, b):
        return (a, b) if pos[a] < pos[b] else (b, a)

    # 1. new objects in the same spot
    for key, per in new_objs.items():
        big = [(pl, pts) for pl, pts in per.items() if len(pts) >= min_new]
        if len(big) < 2:
            continue
        radius = 256.0 if key[0] == "e" else 128.0
        for i in range(len(big)):
            for j in range(i + 1, len(big)):
                (a, pa), (b, pb) = big[i], big[j]
                if related(a, b):
                    continue
                grid = defaultdict(list)
                for o in pb:
                    grid[(int(o[1] // radius), int(o[2] // radius))].append(o)
                close, dup, example = 0, 0, None
                for o in pa:
                    gx, gy = int(o[1] // radius), int(o[2] // radius)
                    near = [q for dx in (-1, 0, 1) for dy in (-1, 0, 1) for q in grid.get((gx + dx, gy + dy), ())
                            if (q[1] - o[1]) ** 2 + (q[2] - o[2]) ** 2 <= radius * radius and abs(q[3] - o[3]) <= radius]
                    if near:
                        close += 1
                        example = example or (o[0], near[0][0])
                        if any(q[0].lower() == o[0].lower() and (q[1] - o[1]) ** 2 + (q[2] - o[2]) ** 2 < 64 for q in near):
                            dup += 1
                frac = close / min(len(pa), len(pb))
                if close < 3:
                    continue
                major = close >= 10 and frac >= 0.25
                pk = pair_key(a, b)
                if dup:
                    example = next(((o[0], o[0]) for o in pa for q in grid.get((int(o[1] // radius), int(o[2] // radius)), ())
                                    if q[0].lower() == o[0].lower() and (q[1] - o[1]) ** 2 + (q[2] - o[2]) ** 2 < 64), example)
                pairs[pk]["place"].append((key, len(per[pk[0]]), len(per[pk[1]]), close, dup, example, major))
                pairs[pk]["score"] += (100 if major else 10) + close + 5 * dup
    # 2. the same placed objects changed differently
    master_dig = {}
    for owner, want in by_owner.items():
        master_dig.update(want)
    for bk, v in contested.items():
        md = master_dig.get(bk)
        real = [(p, d, x, o, k) for p, d, x, o, k in v if d != md]
        for i in range(len(real)):
            for j in range(i + 1, len(real)):
                a, b = real[i], real[j]
                if a[0] == b[0] or a[1] == b[1] or related(a[0], b[0]):
                    continue
                pk = pair_key(a[0], b[0])
                pairs[pk]["refs"].append((a[4], a[3] or b[3], a[2] or b[2]))
                pairs[pk]["score"] += 2
    # 3. cell settings
    for key, hist in settings.items():
        base = {}
        for pl, st in hist:
            if pl.endswith(".esm"):
                base.update(st)
        for field in CELL_SETTING_NAMES:
            ch = [(pl, st[field]) for pl, st in hist if not pl.endswith(".esm") and field in st
                  and st[field] != base.get(field)]
            for i in range(len(ch)):
                for j in range(i + 1, len(ch)):
                    (a, va), (b, vb) = ch[i], ch[j]
                    if a == b or va == vb or related(a, b):
                        continue
                    pk = pair_key(a, b)
                    later_v, earlier_v = (vb, va) if pos[b] > pos[a] else (va, vb)
                    pairs[pk]["settings"].append((key, field, earlier_v, later_v))
                    pairs[pk]["score"] += 3
    if args.only:
        only = {o.lower() for o in args.only}
        pairs = {k: v for k, v in pairs.items() if k[0] in only or k[1] in only}
    if not pairs and not collect:
        print("  No conflicts found between plugins that don't know about each other.")
        return 0

    def cell_name(key):
        lab = (labels.get(key) or "").strip()
        if key[0] == "i":
            return f"'{lab}'"
        return f"{lab}" if lab and not lab.startswith("(") else f"Wilderness ({key[1]}, {key[2]})"

    total_new = Counter()
    for per in new_objs.values():
        for pl, pts in per.items():
            total_new[pl] += len(pts)
    for (a, b), c in pairs.items():                 # nearly everything placed twice: two versions of one mod
        dups = sum(p[4] for p in c["place"])
        c["doubled"] = dups >= 20 and dups >= 0.6 * min(total_new[a], total_new[b])
        c["dups"] = dups
        if c["doubled"]:
            c["score"] += 100000
    # a patch for both - a plugin with both as masters that has records for every cell where they conflict -
    # has already decided those cells: the conflict is void. One that covers only some cells is mentioned.
    patched = {}
    active = list(pos)
    for (a, b), c in list(pairs.items()):
        cells = {t[0] for t in c["place"]} | {t[0] for t in c["refs"]} | {t[0] for t in c["settings"]}
        best, best_n = [], 0
        for pl in active:
            if pl in (a, b) or not ({a, b} <= deps(pl)):
                continue
            n = len(cells & cells_of.get(pl, set()))
            if n == len(cells):
                best.append(pl)
            elif n > best_n:
                best_n, partial = n, pl
        if best:
            patched[(a, b)] = (c, best)
            del pairs[(a, b)]
        elif best_n:
            c["patched_some"] = (partial, best_n, len(cells))
    if collect:
        return {"pairs": pairs, "name_of": name_of, "total_new": total_new, "pos": pos, "masters": masters}
    if not args.dry_run:
        try:
            write_collide_data(args, order, new_objs, labels, pos, name_of, deps, cells_of)
        except (OSError, ValueError) as e:
            print(f"  (could not write {COLLIDE_DATA}: {e})", file=sys.stderr)
    doors_at, arrivals = defaultdict(list), defaultdict(list)
    for bk, (_pi, ckey, at, dest, to, dele) in door_final.items():
        if dele:
            continue
        arrivals[dest].append(to)
        doors_at[ckey].append((at, dest, to))
    lost = []
    report_rearranged(order, own_pos, deletions, new_objs, labels, pos, name_of, deps, cells_of,
                      doors_at, arrivals, lost)
    if not args.dry_run:
        try:
            write_stranded_data(args, order, lost)
        except (OSError, ValueError) as e:
            print(f"  (could not write {STRANDED_DATA}: {e})", file=sys.stderr)
    if patched:
        print(f"  {len(patched)} pair(s) already handled by a patch (a plugin made for both, covering every cell "
              f"where they conflict); not counted below:")
        for (a, b), (c, pls) in sorted(patched.items(), key=lambda kv: -kv[1][0]["score"]):
            print(f"    {name_of[a]}  vs  {name_of[b]}: patched by {', '.join(name_of[x] for x in pls)}")
        if not pairs:
            print("  No other conflicts.")
            return 0
    # pairs whose only trouble is a few objects near each other (no layout clash, no object changed both
    # ways, no cell setting, nothing placed twice): mwcollide hides what actually overlaps as the cell loads,
    # and the rest is just two mods' clutter side by side. Counted, not asked about.
    def collide_only(c):
        return (not c["refs"] and not c["settings"] and not c.get("doubled") and c["place"]
                and not any(p[6] for p in c["place"]))
    by_collide = {k: c for k, c in pairs.items() if collide_only(c)}
    if by_collide:
        pairs = {k: c for k, c in pairs.items() if k not in by_collide}
        print(f"  {len(by_collide)} pair(s) only put a few objects near each other: mwcollide hides the ones that "
              f"overlap as the cell loads; not counted below (--conflict-all-places lists them)")
        if getattr(args, "conflict_all_places", False):
            for (a, b), c in sorted(by_collide.items(), key=lambda kv: -kv[1]["score"]):
                print(f"    {name_of[a]}  vs  {name_of[b]}: {sum(p[3] for p in c['place'])} object(s) near each "
                      f"other in {len(c['place'])} cell(s)")
        if not pairs:
            print("  No other conflicts.")
            return 0
    ranked = sorted(pairs.items(), key=lambda kv: -kv[1]["score"])
    majors = [kv for kv in ranked if any(p[6] for p in kv[1]["place"]) or len(kv[1]["refs"]) >= 20]
    doubled = [kv for kv in ranked if kv[1]["doubled"]]
    print(f"  {len(pairs)} pair(s) of plugins conflict; {len(majors)} major"
          + (f", {len(doubled)} of them DOUBLED (the same objects placed twice)" if doubled else "")
          + ". Most serious first.")
    print("  (pairs where one plugin is a master of the other are left out: one was made with the other in view)")
    shown = ranked if args.conflict_all else ranked[:args.conflict_top]
    remembered = read_conflict_answers(os.path.dirname(os.path.abspath(args.data_dir)))
    _rp = os.path.join(os.path.dirname(os.path.abspath(args.data_dir)), RULES_FILE)
    try:                                           # every [Order]/[Exact] rule in the rules file
        _rt = open(_rp, encoding="cp1252", errors="replace").read() if os.path.exists(_rp) else ""
        _rules = [[e.lower() for e in ents] for k, ents, _s in parse_rules(_rp, _rt)[0] if k in ("order", "exact")]
    except Exception:
        _rules = []

    def ruled_first(a, b):
        """The plugin your rules load first of the two, or None."""
        for r in _rules:
            if a in r and b in r:
                return a if r.index(a) < r.index(b) else b
        return None

    def answer_text(a, b):
        r_ = remembered.get("|".join(sorted((a, b))))
        if not r_ or r_.get("do") == "skip":
            first = ruled_first(a, b)
            if first:
                second = b if first == a else a
                return (f"decided by an [Order] rule in {RULES_FILE}: {name_of.get(second, second)} loads after "
                        f"{name_of.get(first, first)}, so its version wins; not asked")
            if a.lower().endswith(".esm") != b.lower().endswith(".esm"):
                return ("not asked: an .esm always loads before an .esp, so the .esp's version wins and no "
                        "order can change it (turn one off, or a patch that moves one, if it looks wrong)")
            return "no answer yet (you'll be asked)"
        who, when = r_.get("plugin", ""), r_.get("when", "")
        other = next((x for x in r_.get("pair", []) if x.lower() != who.lower()), "the other")
        what = {"order": f"{other} wins ([Order] rule: {who} loads first)",
                "cell": f"{who}'s version of the rebuilt interior(s) wins (Cell Fixes)",
                "off": f"turn off {who}",
                "skip": "skipped (left as it is)"}.get(r_.get("do"), str(r_.get("do")))
        return what + (f"  [{when}]" if when else "")

    for (a, b), c in shown:
        major = any(p[6] for p in c["place"]) or len(c["refs"]) >= 20
        kind = "DOUBLED" if c["doubled"] else "MAJOR" if major else "minor"
        print(f"\n=== {kind}: {name_of[a]}  vs  {name_of[b]}")
        print(f"    your answer: {answer_text(a, b)}")
        if c["doubled"]:
            print(f"    {c['dups']} identical objects are placed twice in the same spot (of {total_new[a]} and "
                  f"{total_new[b]} new objects): these look like two versions of the same mod, or one already "
                  f"contains the other. Keep only one of them active")
        print(f"    {name_of[b]} loads later, so where they disagree its version wins")
        if c.get("patched_some"):
            pl, k, t = c["patched_some"]
            print(f"    {name_of[pl]} patches the two of them, but only in {k} of the {t} cell(s) where they conflict")
        if c["place"]:
            places = sorted(c["place"], key=lambda t: -t[3])
            print(f"    builds in the same spot in {len(places)} cell(s):")
            for key, na, nb, close, dup, ex, mj in places[:6]:
                extra = f"; {dup} identical object(s) placed twice" if dup else ""
                print(f"      {cell_name(key)}: adds {na} vs {nb} new objects, {close} of them within "
                      f"{'256' if key[0] == 'e' else '128'} units of the other's{extra}"
                      + (f" (e.g. '{ex[0]}' next to '{ex[1]}')" if ex else ""))
            if len(places) > 6:
                print(f"      ... and {len(places) - 6} more cell(s)")
        if c["refs"]:
            cells = Counter(k for k, _o, _d in c["refs"])
            dels = sum(1 for _k, _o, d in c["refs"] if d)
            print(f"    both change {len(c['refs'])} of the same placed objects differently"
                  + (f" ({dels} deleted by one of them)" if dels else "") + ", in " +
                  ", ".join(f"{cell_name(k)} ({n})" for k, n in cells.most_common(4))
                  + (f" and {len(cells) - 4} more cell(s)" if len(cells) > 4 else ""))
        if c["settings"]:
            print("    both change the same cell settings:")
            for key, field, ev, lv in c["settings"][:5]:
                print(f"      {cell_name(key)} {CELL_SETTING_NAMES[field]}: {_show_setting(field, ev)}  ->  "
                      f"{_show_setting(field, lv)} (wins)")
            if len(c["settings"]) > 5:
                print(f"      ... and {len(c['settings']) - 5} more")
        if c["doubled"]:
            pass
        elif c["place"]:
            print("    -> the two build over each other: expect overlapping or floating objects. Usually only "
                  "one of them should be used there, or a compatibility patch that moves one")
        elif c["refs"] or c["settings"]:
            print(f"    -> if {name_of[a]}'s changes should win, load it after {name_of[b]} "
                  f"(an [Order] rule); if both matter, a patch that combines them is needed")
    if len(ranked) > len(shown):
        print(f"\n  ... and {len(ranked) - len(shown)} smaller conflict(s) (--conflict-all lists them all)")
    interactive = (sys.stdin.isatty() and sys.stdout.isatty() and not args.dry_run
                   and not getattr(args, "no_interactive", False))
    if interactive or (getattr(args, "use_answers", False) and not args.dry_run):
        # every pair is asked (or replayed), not only the ones printed above: --conflict-top limits the summary
        return conflict_session(args, ranked, name_of, masters, total_new, plugins, labels)
    return 0


# --------------------------------------------------------------------------
# Who uses whose objects: a plugin can be turned off only if no other active plugin relies on what it adds
# --------------------------------------------------------------------------


NEW_CONFLICTS_FILE = "mwdialog_new_conflicts.txt"     # pairs the last --use-answers run had no answer for


POSTPONED = []                                       # pairs postponed ([s]) in this session


def conflict_session(args, ranked, name_of, masters, total_new, plugins=(), labels=None):
    """The session, then: if you postponed any, an offer to go over them again - from scratch, so the
    blacklist, the load order (plugins turned off meanwhile), the rules and your answers are read anew,
    and only what is still unanswered is asked."""
    POSTPONED.clear()
    rc = _conflict_session(args, ranked, name_of, masters, total_new, plugins, labels)
    if POSTPONED and not args.dry_run and not getattr(args, "use_answers", False) and sys.stdin.isatty():
        try:
            ans = input(f"\nYou put off {len(POSTPONED)} conflict(s). Go over them again now (everything is read "
                        f"again first: blacklist, turned-off plugins, rules, answers)? [y/N] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans in ("y", "yes"):
            argv2 = [args.data_dir, "--cell-conflicts", "--only-new"]
            if args.ini:
                argv2 += ["--ini", args.ini]
            return main(argv2)
    return rc


def _conflict_session(args, ranked, name_of, masters, total_new, plugins=(), labels=None):
    """--cell-conflicts in a console: go through the conflicts, most serious first, and for each one
    add an [Order] rule (either way) or turn one of the two plugins off. Offers --sort at the end."""
    game_dir = os.path.dirname(os.path.abspath(args.data_dir))
    rules_path = os.path.join(game_dir, RULES_FILE)
    needed = {m for ms in masters.values() for m in ms}            # masters of something active
    # what earlier runs of this session added is replaced, not added to: this run's answers are the ones that count
    text = open(rules_path, encoding="cp1252", errors="replace").read() if os.path.exists(rules_path) else ""
    own_text, earlier = split_conflict_rules(text)
    existing = [[e.lower() for e in ents] for k, ents, _s in parse_rules(rules_path, own_text)[0]
                if k in ("order", "exact")]
    earlier_l = {(a.lower(), b.lower()) for a, b in earlier}
    if earlier and not args.dry_run:
        # wiped before anything is read or asked: this session starts from your own rules only
        shutil.copy2(rules_path, f"{bak_home(rules_path)}.mwdialog-{time.strftime('%Y%m%d-%H%M%S')}.bak")
        with open(rules_path, "w", encoding="cp1252", errors="replace", newline="\r\n") as f:
            f.write(own_text)
        print(f"\nRemoved the {len(earlier)} [Order] rule(s) earlier --cell-conflicts runs added to {RULES_FILE} "
              f"(backed up first); a pair an earlier run decided shows what it chose.")

    def has_rule(first, second):
        return any(first in r and second in r and r.index(first) < r.index(second) for r in existing)

    labels = labels or {}
    winners = read_cell_winners(game_dir)
    new_winners = {}

    def rebuilt(c):
        """The interiors both rebuilt (major: much of each built over the other)."""
        return [p[0] for p in c["place"] if p[6] and p[0][0] == "i"]

    def chosen(a, b, c):
        cs = rebuilt(c)
        return bool(cs) and all(k[1] in winners and {winners[k[1]][1].lower(), winners[k[1]][2].lower()} == {a, b}
                                for k in cs)

    new_rules, turned_off = [], []
    answers = read_conflict_answers(game_dir)        # last time's answers: the defaults
    answered = {}
    use_all = bool(getattr(args, "use_answers", False))     # --use-answers: last time's answer for every pair
    auto_known = False                                       # [a]: the same, but new pairs are still asked

    def forget_now(k):
        """An old "skip" answer is dropped: a postponed pair has no answer."""
        if args.dry_run:
            return
        try:
            cur = read_conflict_answers(game_dir)
            if cur.pop(k, None) is not None:
                write_conflict_answers(game_dir, cur)
            answers.pop(k, None)
        except (OSError, ValueError):
            pass

    def save_now(k):
        """Each answer is written to the answers file the moment it's given: a crash or a closed window
        loses nothing. Run again and those pairs come back answered ([a] or --only-new takes them)."""
        if args.dry_run or getattr(args, "use_answers", False) and use_all:
            return
        try:
            cur = read_conflict_answers(game_dir)
            cur[k] = answered[k]
            write_conflict_answers(game_dir, cur)
        except (OSError, ValueError):
            pass
    only_new = bool(getattr(args, "only_new", False))       # --only-new: replay answered pairs, ask the new ones
    unanswered = []                                         # pairs with no answer yet (left for you)
    # An .esm always loads before every .esp, so an [Order] rule can't change who wins between them:
    # list those pairs as warnings and only ask about the rest.
    # (one that both rebuilt an interior is still asked: whose version of the place wins doesn't depend on order)
    mixed = lambda k: k[0].endswith(".esm") != k[1].endswith(".esm")
    esm_vs_esp = [(k, c) for k, c in ranked if mixed(k) and not rebuilt(c)]
    if esm_vs_esp:
        print("\n" + "=" * 70 + f"\nWARNINGS: {len(esm_vs_esp)} conflict(s) between an .esm and an .esp"
              "\n(an .esm always loads first, so the .esp always wins; no [Order] rule can change that)\n" + "=" * 70)
        for (a, b), c in esm_vs_esp:
            esm, esp = (name_of[a], name_of[b]) if a.endswith(".esm") else (name_of[b], name_of[a])
            parts = []
            if c["place"]:
                parts.append(f"same spot in {len(c['place'])} cell(s)")
            if c["refs"]:
                parts.append(f"{len(c['refs'])} same objects")
            if c["settings"]:
                parts.append(f"{len(c['settings'])} cell setting(s)")
            extra = f"; {c['dups']} objects placed twice" if c.get("doubled") else ""
            print(f"  WARN {esp} overrides {esm}: {', '.join(parts)}{extra}")
        ranked = [(k, c) for k, c in ranked if not mixed(k) or rebuilt(c)]
    # interiors where you already chose whose version wins: decided
    picked = [(k, c) for k, c in ranked if chosen(k[0], k[1], c)]
    if picked:
        print("\n" + "=" * 70 + f"\nREBUILT INTERIORS ALREADY CHOSEN: {len(picked)} conflict(s) (not asked; "
              f"{CELL_WINNERS_FILE})\n" + "=" * 70)
        for (a, b), c in picked:
            for k in rebuilt(c):
                cell, w, _l = winners[k[1]]
                print(f"  WARN '{cell}': {w}'s version wins ({name_of[a]} vs {name_of[b]})")
        picked_keys = {k for k, _c in picked}
        ranked = [(k, c) for k, c in ranked if k not in picked_keys]
    # pairs your own rules already order: decided, so only a warning
    ruled = [(k, c) for k, c in ranked if has_rule(k[0], k[1]) or has_rule(k[1], k[0])]
    if ruled:
        print("\n" + "=" * 70 + f"\nALREADY DECIDED BY YOUR RULES: {len(ruled)} conflict(s) (not asked)\n" + "=" * 70)
        for (a, b), c in ruled:
            first, second = (a, b) if has_rule(a, b) else (b, a)
            extra = f"; {c['dups']} objects placed twice" if c.get("doubled") else ""
            print(f"  WARN {name_of[second]} wins over {name_of[first]} where they conflict (your [Order] rule){extra}")
        ruled_keys = {k for k, _c in ruled}
        ranked = [(k, c) for k, c in ranked if k not in ruled_keys]
    if not ranked:
        print("\nNo conflicts left to decide.")
        return 0
    print("\n" + "=" * 70 + "\nCHOOSE WHAT TO DO (most serious first; Enter takes last time's answer, or skips; "
          "s skips, a takes last time's answers for the rest, q stops)\n" + "=" * 70)
    for i, ((a, b), c) in enumerate(ranked, 1):
        if a in {x.lower() for x, _w in turned_off} or b in {x.lower() for x, _w in turned_off}:
            continue
        A, B = name_of[a], name_of[b]
        kind = "DOUBLED" if c.get("doubled") else "MAJOR" if (any(p[6] for p in c["place"]) or len(c["refs"]) >= 20) else "minor"
        parts = []
        if c["place"]:
            parts.append(f"build in the same spot in {len(c['place'])} cell(s)")
        if c["refs"]:
            parts.append(f"change {len(c['refs'])} of the same objects")
        if c["settings"]:
            parts.append(f"change {len(c['settings'])} cell setting(s)")
        print(f"\n[{i}/{len(ranked)}] {kind}: {A}  vs  {B}")
        print(f"    they {', '.join(parts)}; {B} loads later, so its version wins now")
        if c.get("patched_some"):
            pl, k, t = c["patched_some"]
            print(f"    ({name_of.get(pl, pl)} patches the two of them, but only in {k} of these {t} cell(s))")
        if c.get("doubled"):
            print(f"    {c['dups']} identical objects are placed twice: two versions of one mod, keep only one")
        if (a, b) in earlier_l:
            print(f"    (an earlier run chose: {B} after {A})")
        elif (b, a) in earlier_l:
            print(f"    (an earlier run chose: {A} after {B})")
        if mixed((a, b)):
            opts = {}
            print("    (an .esm always loads before an .esp, so no [Order] rule changes who wins elsewhere)")
        else:
            opts = {"1": ("order", A, B, f"keep {B} winning"), "2": ("order", B, A, f"make {A} win")}
            print(f"  [1] keep  {B} winning   (adds [Order] {A} > {B})")
            print(f"  [2] make  {A} win   (adds [Order] {B} > {A})")
        rb = rebuilt(c)
        if rb:
            names = ", ".join(f"'{labels.get(k, k[1])}'" for k in rb[:4]) + (f" and {len(rb) - 4} more" if len(rb) > 4 else "")
            print(f"    both rebuilt {names}")
            opts["5"] = ("cell", B, A, f"{B}'s version of the rebuilt interior(s)")
            opts["6"] = ("cell", A, B, f"{A}'s version of the rebuilt interior(s)")
            print(f"  [5] use {B}'s version of {'that place' if len(rb) == 1 else 'those places'}: {A}'s objects "
                  f"there are removed and its doors in arrive in {B}'s layout")
            print(f"  [6] use {A}'s version of {'that place' if len(rb) == 1 else 'those places'} (the same, the "
                  f"other way round)")
        for key, n in (("3", A), ("4", B)):
            hit = relied_on(plugins, n, [x for x, _w in turned_off]) if plugins and n.lower() not in needed else {}
            if n.lower() in needed:
                print(f"  [{key}] (can't turn off {n}: another active plugin needs it as a master)")
            elif hit:
                print(f"  [{key}] (can't turn off {n}: {relied_on_text(hit, name_of)})")
            else:
                opts[key] = ("off", n, A if n == B else B, f"turn off {n}")
                print(f"  [{key}] turn off {n}")
        pair_key = "|".join(sorted((a, b)))
        last = answers.get(pair_key) or {}
        if last.get("do") == "skip":
            last = {}                                # skipped = postponed: asked again, never an answer
        default = ""
        if last.get("do") and last.get("plugin"):
            want = last["plugin"].lower()
            default = next((k for k, (w, x, _y, _l) in opts.items()
                            if w == last["do"] and x.lower() == want), "")
        if default:
            shown = f"[{default}] {opts[default][3]}"
            print(f"  [Enter] last time: {shown}   [s] later (ask again next run)   [a] last time's answers "
                  f"for the rest   [q] stop")
        else:
            print("  [Enter] or [s] later (ask again next run)   [a] last time's answers for the rest   [q] stop"
                  + ("   (last time's answer no longer fits)" if last else ""))
        if (use_all or only_new) and not last:
            unanswered.append(pair_key)
            if use_all:
                print("  > (new conflict: no answer yet; left for you)")
                continue
        if use_all or ((only_new or auto_known) and last):
            ans = default or "s"
            print(f"  > {ans}  (last time's answer)")
        else:
            valid = set(opts) | {"", "s", "a", "q"}
            try:
                ans = input("  > ").strip().lower()
                while ans not in valid:              # a slip ("2\\", "`"): ask again, nothing is decided
                    print(f"    '{ans}' isn't one of the choices ({', '.join(sorted(k for k in valid if k))}, or "
                          f"Enter); try again")
                    ans = input("  > ").strip().lower()
            except EOFError:
                break
            if ans == "q":
                break
            if ans == "a":
                # last time's answers for every pair that has one; a new pair is still asked
                auto_known = True
                if last:
                    ans = default or "s"
                    print("    (taking last time's answers from here on; new conflicts are still asked)")
                else:
                    print("    (taking last time's answers from here on; new conflicts like this one are still "
                          "asked)")
                    try:
                        ans = input("  > ").strip().lower()
                        while ans not in valid:
                            print(f"    '{ans}' isn't one of the choices; try again")
                            ans = input("  > ").strip().lower()
                    except EOFError:
                        break
                    if ans == "q":
                        break
                    if ans in ("", "a"):
                        ans = default or "s"
            elif ans == "":
                ans = default or "s"
        if ans not in opts:
            if ans == "s":                           # postponed: not remembered, asked again next run
                POSTPONED.append(pair_key)
                if pair_key not in unanswered:
                    unanswered.append(pair_key)
                if pair_key in answers and answers[pair_key].get("do") == "skip":
                    forget_now(pair_key)
            continue
        what, x, y, label = opts[ans]
        answered[pair_key] = {"do": what, "plugin": x, "pair": [A, B], "when": time.strftime("%Y-%m-%d %H:%M")}
        save_now(pair_key)
        if what == "cell":
            for k in rebuilt(c):
                new_winners[k[1]] = (labels.get(k, k[1]), x, y)
            print(f"    -> {label} ({x} wins, built by --fix as {CELL_WINNER_PATCH})")
            continue
        if what == "order":
            new_rules.append((x, y, label))
            existing.append([x.lower(), y.lower()])
            print(f"    -> [Order] {x} > {y}")
        else:
            turned_off.append((x, f"turned off by --cell-conflicts (conflicts with {y})"))
            print(f"    -> {x} will be turned off")
    if not args.dry_run:                             # what is still unanswered, for --full's last question
        try:
            with open(os.path.join(game_dir, NEW_CONFLICTS_FILE), "w", encoding="utf-8") as _nf:
                _nf.write("\n".join(p_ for p_ in unanswered if p_ not in answered))
        except OSError:
            pass
    if answered and not args.dry_run:
        answers.update(answered)
        write_conflict_answers(game_dir, answers)
        print(f"\nRemembered {len(answered)} answer(s) in {CONFLICT_ANSWERS_FILE}: next time they're the default.")
    if new_winners and not args.dry_run:
        winners.update(new_winners)
        write_cell_winners(game_dir, winners)
        print(f"\nRecorded {len(new_winners)} rebuilt interior choice(s) in {CELL_WINNERS_FILE}.")
    if not new_rules and not turned_off and not new_winners:
        print("\nNo new rules and no plugins turned off." + (" (Earlier runs' conflict rules were removed; run --sort so the order follows your own rules.)" if earlier and not args.dry_run else ""))
        return 0
    stamp = time.strftime("%Y-%m-%d %H:%M")
    if new_rules:
        if os.path.exists(rules_path):
            shutil.copy2(rules_path, f"{bak_home(rules_path)}.mwdialog-{time.strftime('%Y%m%d-%H%M%S')}.bak")
        with open(rules_path, "w", encoding="cp1252", errors="replace", newline="\r\n") as f:
            f.write(own_text.rstrip("\n") + "\n" if own_text.strip() else "")
            f.write(f"\n{CONFLICT_RULES_HEADER} {stamp} ----\n")
            for x, y, label in new_rules:
                f.write(f"\n[Order]\n{x}\n{y}\n; {label} where they conflict\n")
        print(f"\nWrote {len(new_rules)} [Order] rule(s) to {RULES_FILE}"
              + (f", replacing the {len(earlier)} from earlier --cell-conflicts runs" if earlier else "")
              + " (old file backed up).")
    if turned_off:
        gone = {n.lower() for n, _w in turned_off}
        cur = read_load_order(args) or []
        set_game_files(default_ini(args), [n for n in cur if n.lower() not in gone], "--cell-conflicts")
        rec = read_disabled(game_dir)
        for n, w in turned_off:
            rec[n] = w
        write_disabled(game_dir, rec)
        print(f"Turned off {len(turned_off)} plugin(s): {', '.join(n for n, _w in turned_off)} "
              f"(listed in {DISABLED_RECORD}; --reenable NAME turns one back on).")
    if IN_FULL:
        print("(--full sorts next, so the changes take effect.)")
        return 0
    what = "--sort --fix --multipatch" if (turned_off or new_winners) else "--sort"
    if use_all and getattr(args, "use_answers", False):
        ans = "y"
        print(f"\nRunning {what} so the changes take effect (--use-answers).")
    else:
        try:
            ans = input(f"\nRun {what} now so the changes take effect? [Y/n] ").strip().lower()
        except EOFError:
            ans = "n"
    if ans in ("", "y", "yes"):
        argv2 = [args.data_dir, "--sort", "--yes", "--fix-log", args.fix_log, "--encoding", args.encoding]
        if turned_off or new_winners:
            # a plugin gone leaves the others' order as it was, but the multipatch's merged lists and
            # the fix patch were built with it: rebuild them, or they still name its objects
            argv2 += ["--fix", "--multipatch"]
        if args.ini:
            argv2 += ["--ini", args.ini]
        return main(argv2)
    print(f"Run mwdialog_check.bat {what} when you're ready.")
    return 0


PERFORMER_ANIM = re.compile(r"am_bard|luteplay|drummer|bard")
PERFORMER_SCRIPT = re.compile(rb"vo\\bard|streammusic|am_lute|am_drum")


def find_double_performers(plugins):
    """Interiors where two plugins each put on a performer (an NPC with a bard/lute/drummer animation, or a
    script that plays bard music). Returns [(cell label, cell key, head, keep [...], drop [...], left [...])]:
    the performers of the plugin loading last stay; the others go when the same plugin both added and
    placed them (an added bard), and are only reported when they are someone else's NPC made to perform."""
    order = {n.lower(): i for i, (n, _p) in enumerate(plugins)}
    npc, creator, scr = {}, {}, {}
    cells, heads, labels = defaultdict(dict), {}, {}
    for n, path in plugins:
        if n.lower() == PERFORMER_PATCH.lower():
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
            ms = [x.lower() for x in plugin_masters(data)]
            recs = list(iter_records(data))
        except (OSError, FormatError):
            continue
        for off, tag, flags, body in recs:
            if tag == "NPC_":
                nm = first_sub(body, b"NAME")
                if nm is None:
                    continue
                rid = cstr(nm).lower()
                creator.setdefault(rid, n)
                npc[rid] = (cstr(first_sub(body, b"MODL") or b"").lower(), cstr(first_sub(body, b"SCRI") or b"").lower(),
                            cstr(first_sub(body, b"FNAM") or b""), n)
            elif tag == "SCPT":
                hd = first_sub(body, b"SCHD")
                if hd:
                    scr[cstr(hd[:32]).lower()] = ((first_sub(body, b"SCTX") or b"").lower(), n)
            elif tag == "CELL":
                key, label = cell_key(body)
                if not key or key[0] != "i":
                    continue
                head, pers, _n0, temp = split_cell(body, off)
                heads[key], labels[key] = head, label
                refs = cells[key]
                for grp, blks in (("p", pers), ("t", temp)):
                    for blk in blks:
                        bk = block_key(blk, ms, n.lower())
                        if not bk:
                            continue
                        prev = refs.get(bk)
                        oid = next((cstr(d) for s_, d in blk if s_ == "NAME"), "") or (prev[0] if prev else "")
                        if prev is None and oid.lower() not in npc and not any(s_ == "DELE" for s_, _d in blk):
                            continue            # only actors matter here (an NPC defined later is caught below)
                        refs[bk] = (oid, any(s_ == "DELE" for s_, _d in blk), grp, blk)

    def performer(oid):
        d = npc.get(oid.lower())
        if not d:
            return None
        anim, sid, name, by = d
        if PERFORMER_ANIM.search(anim):
            return name or oid, by
        if sid in scr and PERFORMER_SCRIPT.search(scr[sid][0]):
            return name or oid, scr[sid][1]
        return None

    out = []
    for key, refs in cells.items():
        perf = []
        for bk, (oid, dele, grp, blk) in refs.items():
            if dele:
                continue
            pr = performer(oid)
            if pr:
                perf.append(dict(oid=oid, name=pr[0], by=pr[1], owner=bk[0], idx=bk[1], grp=grp, blk=blk,
                                 added=bk[0] == pr[1].lower()))     # placed by the plugin that makes it perform
        if len({x["by"].lower() for x in perf}) < 2:
            continue
        last = max({x["by"] for x in perf}, key=lambda b: order.get(b.lower(), -1))
        keep = [x for x in perf if x["by"] == last]
        drop = [x for x in perf if x["by"] != last and x["added"]]
        left = [x for x in perf if x["by"] != last and not x["added"]]
        out.append((labels[key], key, heads[key], keep, drop, left))
    out.sort(key=lambda t: t[0].lower())
    return out


def fix_performers(args, plugins):
    """--fix: where two plugins each put a performing bard in the same interior, keep the bards of the
    plugin loading last and remove the earlier plugin's added bards, through PERFORMER_PATCH (rebuilt each
    time; the plugins themselves are not changed)."""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    print("\n" + "=" * 70 + "\nDOUBLED PERFORMERS (two plugins' bards in one inn)\n" + "=" * 70)
    print("  Looking for interiors with performers from two plugins...", file=sys.stderr)
    found = find_double_performers(plugins)
    out_path = os.path.join(data_dir, PERFORMER_PATCH)
    drops = []
    for label, key, head, keep, drop, left in found:
        print(f"  {label}: keeping {', '.join(x['name'] for x in keep)} ({keep[0]['by']}, loads last)")
        for x in drop:
            print(f"      remove {x['name']} ({x['oid']}), added by {x['by']}")
        for x in left:
            print(f"      left in: {x['name']} ({x['oid']}) is {x['owner']}'s NPC that {x['by']} makes perform; "
                  f"only the bard plugin itself can change that")
        if drop:
            drops.append((label, key, head, drop))
    if not found:
        print("  None.")
    if not drops:
        if os.path.exists(out_path) and not args.dry_run:
            bak = backup_path(out_path)
            os.replace(out_path, bak)
            cur = read_load_order(args) or []
            set_game_files(args.ini or os.path.join(game_dir, "Morrowind.ini"),
                           [n for n in cur if n.lower() != PERFORMER_PATCH.lower()], "--fix (performers)")
            print(f"  {PERFORMER_PATCH} no longer needed: removed (kept as {os.path.basename(bak)}).")
        return 0
    n_drop = sum(len(d) for *_x, d in drops)
    if args.dry_run:
        print(f"  Dry run: {PERFORMER_PATCH} would remove {n_drop} performer(s) in {len(drops)} interior(s).")
        return 0
    if not args.yes and (not sys.stdin.isatty() or input(f"\nRemove {n_drop} doubled performer(s) through "
                                                         f"{PERFORMER_PATCH}? [y/N] ").strip().lower() not in ("y", "yes")):
        print("  Nothing changed.")
        return 0
    lookup = index_dir(data_dir)
    order = {n.lower(): i for i, (n, _p) in enumerate(plugins)}
    owners = sorted({x["owner"] for *_x, d in drops for x in d}, key=lambda o: order.get(o, 0))
    masters = [os.path.basename(lookup[o]) for o in owners if o in lookup]
    midx = {m.lower(): i + 1 for i, m in enumerate(masters)}
    recs = b""
    for label, key, head, drop in drops:
        pers, temp = [], []
        for x in drop:
            # a deleted reference is FRMR, NAME, DELE and nothing else (the Construction Set's form): the
            # game ends the reference at DELE, and anything after it (its DATA) makes it reload the cell
            oid = next((d for s_, d in x["blk"] if s_ == "NAME"), x["oid"].encode(ENC, MW_ERRORS) + b"\0")
            blk = [["FRMR", struct.pack("<I", (midx[x["owner"]] << 24) | x["idx"])], ["NAME", oid],
                   ["DELE", struct.pack("<I", 0)]]
            (pers if x["grp"] == "p" else temp).append(blk)
        body = b"".join(pack_sub(s_, d) for s_, d in head)
        for blk in pers:
            body += b"".join(pack_sub(s_, d) for s_, d in blk)
        if temp:
            body += pack_sub("NAM0", struct.pack("<I", len(temp)))
            for blk in temp:
                body += b"".join(pack_sub(s_, d) for s_, d in blk)
        recs += b"CELL" + struct.pack("<III", len(body), 0, 0) + body
    desc = "Doubled bards: keeps the performers of the plugin loading last (rebuilt by mwdialog_check --fix)"
    hedr = (struct.pack("<fI", 1.3, 0) + b"mwdialog_check".ljust(32, b"\0")
            + desc.encode(ENC, MW_ERRORS)[:255].ljust(256, b"\0") + struct.pack("<I", len(drops)))
    subs = [pack_sub("HEDR", hedr)]
    for mname in masters:
        subs += [pack_sub("MAST", mname.encode(ENC, MW_ERRORS) + b"\0"),
                 pack_sub("DATA", struct.pack("<Q", os.path.getsize(os.path.join(data_dir, mname))))]
    hb = b"".join(subs)
    if os.path.exists(out_path):
        shutil.copy2(out_path, backup_path(out_path))
    write_plugin_bytes(out_path, b"TES3" + struct.pack("<III", len(hb), 0, 0) + hb + recs)
    when = max(os.path.getmtime(os.path.join(data_dir, mname)) for mname in masters) + 60
    os.utime(out_path, (when, when))
    cur = read_load_order(args) or []
    if PERFORMER_PATCH.lower() not in {n.lower() for n in cur}:
        tail = {PLACE_PATCH_NAME.lower(), MULTI_PATCH_NAME.lower()}      # after the auto-merge, before these
        at = next((i for i, n in enumerate(cur) if n.lower() in tail), len(cur))
        set_game_files(args.ini or os.path.join(game_dir, "Morrowind.ini"), cur[:at] + [PERFORMER_PATCH] + cur[at:],
                       "--fix (performers)")
    with MT.open_log(os.path.join(game_dir, args.fix_log), "a", encoding="utf-8") as lf:
        lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {PERFORMER_PATCH}: removed {n_drop} doubled performer(s): "
                 + "; ".join(f"{label}: " + ", ".join(x['oid'] for x in d) for label, _k, _h, d in drops) + "\n")
    print(f"  Wrote {PERFORMER_PATCH}: {n_drop} performer(s) removed in {len(drops)} interior(s); it is in the load "
          f"order (after its masters). --fix rebuilds it; --no-performers skips this step.")
    return 0


def fix_cell_winners(args, plugins):
    """--fix: for each interior in CELL_WINNERS_FILE, the winning plugin's version of the place is used as if
    the losing plugin had never touched it, through CELL_WINNER_PATCH (rebuilt each time; no plugin changed):
      - the loser's own objects there are deleted (not its people and creatures, nor objects its scripts or
        dialogue name: those are kept and listed, as a quest may need them)
      - the objects the loser changed or deleted there get the version they'd have without it back
      - the cell's lighting/water/flags and its pathgrid are the ones they'd be without the loser
      - every door into the place (any plugin's, anywhere) that the loser set up is pointed at an arrival
        spot of the winner's layout: the one used from the same place if there is one, else the main one"""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    print("\n" + "=" * 70 + "\nCELL FIXES: rebuilt interiors, door arrivals, objects on reshaped land\n" + "=" * 70)
    entries = read_cell_winners(game_dir)
    out_path = os.path.join(data_dir, CELL_WINNER_PATCH)
    ours = {x.lower() for x in OUR_PATCHES} | {CELL_WINNER_PATCH.lower(), PERFORMER_PATCH.lower()}
    order = [(n, p) for n, p in plugins if n.lower() not in ours]
    pos = {n.lower(): i for i, (n, _p) in enumerate(order)}
    name_of = {n.lower(): n for n, _p in order}
    cells = {}
    for k, (cell, w, l) in entries.items():
        if w.lower() not in pos or l.lower() not in pos:
            print(f"  '{cell}': {w if w.lower() not in pos else l} isn't active, so there's nothing to choose; skipped")
            continue
        cells[k] = (cell, w.lower(), l.lower())

    def drop_patch():
        cur = read_load_order(args) or []
        if os.path.exists(out_path) and not args.dry_run:
            os.replace(out_path, backup_path(out_path))
            set_game_files(args.ini or os.path.join(game_dir, "Morrowind.ini"),
                           [n for n in cur if n.lower() != CELL_WINNER_PATCH.lower()], "--fix (cell winners)")
            print(f"  {CELL_WINNER_PATCH} no longer needed: removed.")
    if not cells:
        print("  Rebuilt interiors: none chosen (--cell-conflicts offers it for interiors two mods both rebuilt).")
    losers = {l for _c, _w, l in cells.values()}
    masters_of = {}                              # plugin -> its masters (lower)
    ipos = {}                                    # (interior, ref key) -> (plugin, x, y, z, deleted): latest version
    iorig = {}                                   # (interior, ref key) -> (x, y, z, z-rotation, id): its owner's version
    int_recs = defaultdict(list)                 # interior -> [(plugin index, offset)] of its CELL records
    item_ids = set()                             # things that get picked up and moved about: never anchors
    interiors = set()
    land_vers = defaultdict(list)                # (x, y) -> [(plugin index, VHGT digest, offset)] in load order
    ext_recs = defaultdict(list)                 # (x, y) -> [(plugin index, offset)] of exterior CELL records
    print("  Reading every plugin's cells, doors and pathgrids...", file=sys.stderr)
    actor_ids, cont_ids, loser_text = set(), set(), defaultdict(list)
    heads = {}                                   # cell key -> latest head
    xheads = defaultdict(list)                   # chosen interior -> [(plugin, head)] in load order
    xver = defaultdict(list)                     # (interior, ref key) -> [(plugin, group, block)]
    xpgrd = defaultdict(list)                    # interior -> [(plugin, raw PGRD record)]
    door_hist = defaultdict(list)                # ref key -> [(plugin, group, block, cell key)] of doors into them
    for pi, (n, p) in enumerate(order):
        low = n.lower()
        try:
            data = open(p, "rb").read()
            ms = [x.lower() for x in plugin_masters(data)]
            recs = list(iter_records(data))
        except (OSError, FormatError):
            continue
        masters_of[low] = ms
        for off, tag, fl, body in recs:
            if tag == "LAND":
                iv, vh = first_sub(body, b"INTV"), first_sub(body, b"VHGT")
                if iv and vh and len(iv) >= 8 and len(vh) >= 4 + 65 * 65:
                    land_vers[struct.unpack_from("<ii", iv)].append((pi, hashlib.md5(vh[:4 + 65 * 65]).digest(), off))
                continue
            if tag in ("MISC", "BOOK", "WEAP", "ARMO", "CLOT", "ALCH", "INGR", "APPA", "LOCK", "PROB", "REPA",
                       "LEVI"):
                nm = first_sub(body, b"NAME")
                if nm:
                    item_ids.add(cstr(nm).lower())
            if tag in ("NPC_", "CREA", "LEVC", "CONT"):
                nm = first_sub(body, b"NAME")
                if nm:
                    (cont_ids if tag == "CONT" else actor_ids).add(cstr(nm).lower())
            elif tag == "SCPT" and low in losers:
                loser_text[low].append((first_sub(body, b"SCTX") or b"").lower())
            elif tag == "INFO" and low in losers:
                loser_text[low].append((first_sub(body, b"BNAM") or b"").lower())
            elif tag == "PGRD":
                nm = cstr(first_sub(body, b"NAME") or b"").lower()
                if nm in cells:
                    xpgrd[nm].append((low, b"PGRD" + struct.pack("<III", len(body), 0, fl) + body))
            elif tag == "CELL":
                key, _label = cell_key(body)
                if key is None:
                    continue
                head, pers, _n0, temp = split_cell(body, off)
                heads[key] = head
                if key[0] == "e":
                    ext_recs[(key[1], key[2])].append((pi, off))
                else:
                    interiors.add(key[1])
                    int_recs[key[1]].append((pi, off))
                inx = key[0] == "i" and key[1] in cells
                if inx:
                    xheads[key[1]].append((low, head))
                for grp, blks in (("p", pers), ("t", temp)):
                    for blk in blks:
                        bk = block_key(blk, ms, low)
                        if bk is None:
                            continue
                        if inx:
                            xver[(key[1], bk)].append((low, grp, blk))
                        if key[0] == "i":
                            dd = next((d for s_, d in blk if s_ == "DATA" and len(d) >= 12), None)
                            dele = any(s_ == "DELE" for s_, _d in blk)
                            if dd is not None or dele:
                                x, y, z = struct.unpack_from("<3f", dd) if dd is not None else (0.0, 0.0, 0.0)
                                ipos[(key[1], bk)] = (low, x, y, z, dele)
                                if bk[0] == low and dd is not None and not dele:
                                    rz = struct.unpack_from("<f", dd, 20)[0] if len(dd) >= 24 else 0.0
                                    oid = next((cstr(d) for s_, d in blk if s_ == "NAME"), "").lower()
                                    iorig[(key[1], bk)] = (x, y, z, rz, oid)
                        if bk in door_hist or any(s_ == "DNAM" for s_, _d in blk):
                            door_hist[bk].append((low, grp, blk, key))

    def has(blk, sub):
        return any(s_ == sub for s_, _d in blk)

    def name_in(blk):
        return next((cstr(d) for s_, d in blk if s_ == "NAME"), "")

    out = defaultdict(dict)                      # cell key -> {(owner, index): (group, block to write)}
    out_heads, pgrds, used = {}, [], set()
    kept_bk = defaultdict(set)                   # interior -> the loser's objects left in

    def put(key, grp, bk, blk):
        out[key][bk] = (grp, blk)
        used.add(bk[0])

    for cl, (cell, w, l) in sorted(cells.items()):
        key = ("i", cl)
        hs = xheads.get(cl, [])
        if not hs:
            print(f"  '{cell}': no plugin has this interior any more; skipped")
            continue
        others = [h for pl, h in hs if pl != l]
        out_heads[key] = others[-1] if others else hs[-1][1]
        removed, kept, restored, gone_doors = [], [], 0, []
        text = b"\n".join(loser_text[l])
        for (c, bk), vers in xver.items():
            if c != cl or vers[-1][0] != l:
                continue                               # a plugin after the loser decides this one
            pl, grp, blk = vers[-1]
            if bk[0] == l:                             # the loser's own object
                if has(blk, "DELE"):
                    continue
                oid = name_in(blk)
                if oid.lower() in actor_ids or (oid and oid.lower().encode(ENC, MW_ERRORS) in text):
                    kept.append(oid)
                    kept_bk[cl].add(bk)
                    continue
                dest = next((cstr(d) for s_, d in blk if s_ == "DNAM"), None)
                if dest:
                    gone_doors.append(dest)
                nm = next((d for s_, d in blk if s_ == "NAME"), oid.encode(ENC, MW_ERRORS) + b"\0")
                put(key, grp, bk, [["FRMR", b""], ["NAME", nm], ["DELE", struct.pack("<I", 0)]])
                removed.append(oid)
            else:                                      # someone else's object the loser changed or deleted
                prev = [v for v in vers if v[0] != l]
                if not prev:
                    continue
                _pl, grp2, blk2 = prev[-1]
                if has(blk2, "DELE"):
                    nm = next((d for s_, d in blk2 if s_ == "NAME"), b"\0")
                    put(key, grp2, bk, [["FRMR", b""], ["NAME", nm], ["DELE", struct.pack("<I", 0)]])
                else:
                    put(key, grp2, bk, [list(x) for x in blk2])
                restored += 1
        pg = xpgrd.get(cl, [])
        if pg and pg[-1][0] == l:
            other_pg = [r for pl, r in pg if pl != l]
            if other_pg:
                pgrds.append(other_pg[-1])
        print(f"  '{cell}': {name_of[w]}'s version wins over {name_of[l]}'s: {len(removed)} of its object(s) "
              f"removed, {restored} changed object(s) put back")
        if kept:
            print(f"      kept (people, creatures, or named by its scripts or dialogue - may stand in the other "
                  f"layout's walls): {', '.join(sorted(set(kept))[:12])}{' ...' if len(set(kept)) > 12 else ''}")
        for dn in sorted(set(gone_doors)):
            print(f"      its door from here to '{dn}' goes too: check that place can still be reached")

    # doors into the chosen interiors
    good = defaultdict(list)                     # interior -> [(DODT, source cell key)]
    final = {}
    for bk, hist in door_hist.items():
        pl, grp, blk, ck = hist[-1]
        if has(blk, "DELE"):
            continue
        dn = next((cstr(d).lower() for s_, d in blk if s_ == "DNAM"), None)
        if dn not in cells or ck == ("i", dn):
            continue
        final[bk] = (pl, grp, blk, ck, dn)
        src = blk if pl != cells[dn][2] else next((h[2] for h in reversed(hist) if h[0] != cells[dn][2]
                                                   and not has(h[2], "DELE")), None)
        if src is not None and next((cstr(d).lower() for s_, d in src if s_ == "DNAM"), None) == dn:
            dodt = next((d for s_, d in src if s_ == "DODT" and len(d) >= 24), None)
            if dodt:
                good[dn].append((dodt, ck))     # the winner's (or the original) arrival spot
    fixed_doors, unfixable = 0, []
    for bk, (pl, grp, blk, ck, dn) in final.items():
        cell, w, l = cells[dn]
        if pl != l:
            continue
        hist = door_hist[bk]
        prev = [h for h in hist if h[0] != l and not has(h[2], "DELE")]
        if bk[0] != l and prev:                  # someone else's door the loser redirected: theirs again
            _p, g2, b2, ck2 = prev[-1]
            put(ck2, g2, bk, [list(x) for x in b2])
            out_heads.setdefault(ck2, heads.get(ck2))
            fixed_doors += 1
            continue
        dodt = next((d for s_, d in blk if s_ == "DODT" and len(d) >= 24), None)
        if dodt is None or not good[dn]:
            unfixable.append((dn, ck))
            continue
        x, y, z = struct.unpack_from("<3f", dodt)
        if any((struct.unpack_from("<3f", g)[0] - x) ** 2 + (struct.unpack_from("<3f", g)[1] - y) ** 2
               + (struct.unpack_from("<3f", g)[2] - z) ** 2 < 256 ** 2 for g, _c in good[dn]):
            continue                             # it already arrives where the winner's doors do
        same = [g for g, c in good[dn] if c == ck]
        target = (same or [g for g, _c in good[dn]])[0]
        nb = [[s_, target[:24] if s_ == "DODT" else d] for s_, d in blk]
        put(ck, grp, bk, nb)
        out_heads.setdefault(ck, heads.get(ck))
        fixed_doors += 1
    if fixed_doors:
        print(f"  {fixed_doors} door(s) into those places now arrive in the winning layout")
    for dn, ck in unfixable:
        print(f"  WARNING: a door of {cells[dn][2]} into '{cells[dn][0]}' (from {ck}) has no arrival spot of the "
              f"winning layout to use; check it in the game")
    # ---- every other door into an interior: one that leads to a place no plugin has, or arrives where
    # nothing stands any more (the place was rebuilt and the door still uses the old layout's spot)
    # what mwstranded moves or hides (--cell-conflicts) isn't part of the place: a door arriving among it
    # arrives in the void of the old layout
    cut_off = defaultdict(set)
    try:
        with open(os.path.join(os.path.abspath(args.data_dir), "MWSE", "config", STRANDED_DATA),
                  encoding="utf-8") as f:
            for cl, c in (json.load(f).get("cells") or {}).items():
                for o in c.get("objects", ()):
                    cut_off[cl.lower()].add(tuple(int(round(v)) for v in o["pos"]))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    stand, gone_n = defaultdict(list), Counter()
    for (c, _bk), (_pl, x, y, z, dele) in ipos.items():
        if dele:
            gone_n[c] += 1
        elif (int(round(x)), int(round(y)), int(round(z))) in cut_off.get(c, ()):
            gone_n[c] += 1
        else:
            stand[c].append((x, y, z))
    arrivals = defaultdict(list)
    missing_dest = defaultdict(set)
    for bk, hist in door_hist.items():
        pl, grp, blk, ck = hist[-1]
        if has(blk, "DELE"):
            continue
        dn_raw = next((cstr(d) for s_, d in blk if s_ == "DNAM"), None)
        if not dn_raw:
            continue
        dn = dn_raw.lower()
        if dn in cells:
            continue                             # handled above
        if dn not in interiors:
            missing_dest[dn_raw].add(name_of.get(pl, pl))
            continue
        dodt = next((d for s_, d in blk if s_ == "DODT" and len(d) >= 24), None)
        if dodt is not None and ck != ("i", dn):
            arrivals[dn].append((bk, dodt, ck, pl, grp, blk))
    for dn_raw, by in sorted(missing_dest.items()):
        print(f"  WARNING: door(s) of {', '.join(sorted(by))} lead to '{dn_raw}', a place no active plugin has")
    VOID = 600.0
    door_fixed, door_removed = [], []
    for dn, arr in arrivals.items():
        pts = stand.get(dn, [])
        if (gone_n[dn] < 10 and dn not in cut_off) or len(pts) < 20:
            continue                             # not rebuilt: the arrival spots are the original ones
        grid = defaultdict(list)
        for x, y, z in pts:
            grid[(int(x // VOID), int(y // VOID))].append((x, y, z))

        def in_void(d):
            x, y, z = struct.unpack_from("<3f", d)
            gx, gy = int(x // VOID), int(y // VOID)
            return not any((a - x) ** 2 + (b - y) ** 2 + (c - z) ** 2 < VOID ** 2
                           for dx in (-1, 0, 1) for dy in (-1, 0, 1) for a, b, c in grid.get((gx + dx, gy + dy), ()))
        okay = [(d, ck) for _bk, d, ck, *_r in arr if not in_void(d)]
        for bk, d, ck, pl, grp, blk in arr:
            if not in_void(d):
                continue
            if not okay:
                # nowhere safe to send it: remove the door, so nobody walks through it into the void
                nm = next((d for s_, d in blk if s_ == "NAME"), b"")
                put(ck, grp, bk, [["FRMR", b""], ["NAME", nm], ["DELE", struct.pack("<I", 0)]])
                out_heads.setdefault(ck, heads.get(ck))
                door_removed.append(f"{name_of.get(pl, pl)}: door into '{dn}' (from {ck})")
                continue
            same = [g for g, c in okay if c == ck]
            target = (same or [g for g, _c in okay])[0]
            base = out[ck][bk][1] if bk in out.get(ck, {}) else [list(x) for x in blk]
            put(ck, grp, bk, [[s_, target[:24] if s_ == "DODT" else dd] for s_, dd in base])
            out_heads.setdefault(ck, heads.get(ck))
            door_fixed.append(f"{name_of.get(pl, pl)}: door into '{dn}'")
    if door_fixed:
        print(f"  Doors: {len(door_fixed)} arrived in the void of a rebuilt place; now they arrive where another "
              f"door into it does:")
        for t in door_fixed[:15]:
            print(f"      {t}")
        if len(door_fixed) > 15:
            print(f"      ... and {len(door_fixed) - 15} more")
    if door_removed:
        print(f"  Doors: {len(door_removed)} arrived in the void of a rebuilt place with no other way in to send "
              f"them to; removed (in the Cell Fixes patch only):")
        for t in door_removed:
            print(f"      {t}")

    # ---- objects that came with something another mod moved: a mod puts its own objects by an original
    # piece (logs in a fireplace, a candle on a shelf), and another mod it doesn't know about moves that
    # piece across the room. Its objects stay where the piece used to be; they're moved after it.
    closure_all = {}

    def knows(a, b):
        """Plugin a has b among its masters (directly or not)."""
        if a not in closure_all:
            seen, stack = set(), list(masters_of.get(a, []))
            while stack:
                x = stack.pop()
                if x not in seen:
                    seen.add(x)
                    stack += masters_of.get(x, [])
            closure_all[a] = seen
        return b in closure_all[a]
    FOLLOW_MOVED, FOLLOW_NEAR = 128.0, 128.0           # "moved": over this far; "by it": this close (across)
    anchors = defaultdict(list)                        # interior -> [(original x, y, z, rz, final x, y, z, mover)]
    for (c, bk), (pl, x, y, z, dele) in ipos.items():
        if dele or c in cells or pl == bk[0]:
            continue
        o = iorig.get((c, bk))
        if not o or o[4] in item_ids or o[4] in actor_ids:
            continue
        if math.hypot(x - o[0], y - o[1]) < FOLLOW_MOVED:
            continue
        anchors[c].append((o, (x, y, z), pl, bk))
    follow = defaultdict(list)                         # interior -> [(ref key, plugin, offset x/y/z, anchor)]
    for (c, bk), (pl, x, y, z, dele) in ipos.items():
        if dele or c not in anchors or pl != bk[0]:
            continue                                   # only a mod's own objects, where it put them
        o_self = iorig.get((c, bk))
        if not o_self or o_self[4] in actor_ids:
            continue
        best = None
        for o, fin, mover, abk in anchors[c]:
            if pl in (mover, abk[0]) or knows(pl, mover):
                continue                               # made with the move in view
            dn = math.hypot(x - o[0], y - o[1])
            if dn <= FOLLOW_NEAR and abs(z - o[2]) <= 512 and math.hypot(x - fin[0], y - fin[1]) > FOLLOW_NEAR:
                if best is None or dn < best[0]:
                    best = (dn, o, fin, mover)
        if best:
            follow[c].append((bk, pl, best))
    followed = Counter()
    if follow:
        by_plugin = defaultdict(set)
        for c, items in follow.items():
            for bk, pl, _b in items:
                by_plugin[pl].add(c)
        want = {(c, bk): (pl, b) for c, items in follow.items() for bk, pl, b in items}
        for pi, (n, p) in enumerate(order):
            low = n.lower()
            if low not in by_plugin:
                continue
            try:
                data = open(p, "rb").read()
            except OSError:
                continue
            ms = masters_of.get(low, [])
            for c in by_plugin[low]:
                for rpi, off in int_recs.get(c, ()):
                    if rpi != pi:
                        continue
                    size = struct.unpack_from("<I", data, off + 4)[0]
                    head, pers, _n0, temp = split_cell(data[off + 16:off + 16 + size], off)
                    for grp, blks in (("p", pers), ("t", temp)):
                        for blk in blks:
                            bk = block_key(blk, ms, low)
                            hit = want.get((c, bk))
                            if not hit or hit[0] != low:
                                continue
                            _pl, (_dn, o, fin, mover) = hit
                            base = out[("i", c)][bk][1] if bk in out.get(("i", c), {}) else blk
                            dd = next((d for s_, d in base if s_ == "DATA" and len(d) >= 24), None)
                            if dd is None:
                                continue
                            x, y, z, r1, r2, r3 = struct.unpack_from("<6f", dd)
                            nd = struct.pack("<6f", x + fin[0] - o[0], y + fin[1] - o[1], z + fin[2] - o[2],
                                             r1, r2, r3) + dd[24:]
                            put(("i", c), grp, bk, [[s_, nd if s_ == "DATA" else d] for s_, d in base])
                            out_heads.setdefault(("i", c), heads.get(("i", c)))
                            followed[(name_of.get(low, low), name_of.get(mover, mover), c)] += 1
    if followed:
        print(f"  Moved pieces: {sum(followed.values())} object(s) put back with the piece they were placed by, "
              f"which another mod moved:")
        for (who, mover, c), n in sorted(followed.items(), key=lambda kv: -kv[1])[:15]:
            print(f"      - {n} of {who}'s in '{c}' (moved by {mover})")
        if len(followed) > 15:
            print(f"      ... and {len(followed) - 15} more (all listed in mwdialog_cell_fixes.txt)")
        try:
            with open(os.path.join(game_dir, "mwdialog_cell_fixes.txt"), "w", encoding="utf-8") as lf:
                lf.write("; objects the Cell Fixes patch moves with the piece they were placed by, which another mod "
                         "moved (rewritten by each --fix)\n")
                for (who, mover, c), n in sorted(followed.items(), key=lambda kv: (kv[0][2], -kv[1])):
                    lf.write(f"{c}\t{n} of {who}'s\tmoved by {mover}\n")
        except OSError:
            pass

    # ---- reshaped land: where two plugins change the same land's heights, the last one's land is used, and
    # objects put down on the land another plugin saw float or sink. They move up or down with the land.
    contested = {g for g, v in land_vers.items() if len({d for _i, d, _o in v}) >= 2}
    if contested:
        print(f"  Reading the {len(contested)} exterior cell(s) whose land two or more plugins reshape...",
              file=sys.stderr)
        names = [n.lower() for n, _p in order]
        closure = {}

        def deps(n):
            if n not in closure:
                seen, stack = set(), list(masters_of.get(n, []))
                while stack:
                    x = stack.pop()
                    if x not in seen:
                        seen.add(x)
                        stack += masters_of.get(x, [])
                closure[n] = seen | {n}
            return closure[n]
        need = defaultdict(list)
        for g in contested:
            for pi, _d, off in land_vers[g]:
                need[pi].append(("L", g, off))
            for pi, off in ext_recs.get(g, ()):
                need[pi].append(("C", g, off))
        land_h = {}                              # (plugin index, grid) -> heights
        refs = {}                                # ref key -> (plugin, group, block, cell key): latest version
        for pi in sorted(need):
            try:
                data = open(order[pi][1], "rb").read()
            except OSError:
                continue
            ms = masters_of.get(names[pi], [])
            for kind, g, off in need[pi]:
                size = struct.unpack_from("<I", data, off + 4)[0]
                body = data[off + 16:off + 16 + size]
                if kind == "L":
                    land_h[(pi, g)] = land_heights(first_sub(body, b"VHGT"))
                    continue
                head, pers, _n0, temp = split_cell(body, off)
                for grp, blks in (("p", pers), ("t", temp)):
                    for blk in blks:
                        bk = block_key(blk, ms, names[pi])
                        if bk is not None:
                            refs[bk] = (names[pi], grp, blk, ("e", g[0], g[1]))
        land_digest = {g: {pi: d for pi, d, _o in v} for g, v in land_vers.items() if g in contested}

        def seen_land(pl, g):
            """The land version plugin pl was made against: its own or its masters' latest."""
            dep = deps(pl)
            vs = land_vers[g]
            return next((pi for pi, _d, _o in reversed(vs) if names[pi] in dep), vs[0][0])

        def shift(pl, x, y, z):
            g = (int(math.floor(x / 8192)), int(math.floor(y / 8192)))
            if g not in contested:
                return None
            last = land_vers[g][-1][0]
            saw = seen_land(pl, g)
            if land_digest[g][saw] == land_digest[g][last]:
                return None
            h_old = height_at(land_h.get((saw, g)), g, x, y)
            h_new = height_at(land_h.get((last, g)), g, x, y)
            if h_old is None or h_new is None:
                return None
            dz = h_new - h_old
            if abs(dz) < 16 or abs(z - h_old) > 400:
                return None                      # the land barely moved, or it isn't standing on the land
            return dz
        moved_by = Counter()
        for bk, (pl, grp, blk, ck) in refs.items():
            if has(blk, "DELE"):
                continue
            base = out[ck][bk][1] if bk in out.get(ck, {}) else blk
            dd = next((d for s_, d in base if s_ == "DATA" and len(d) >= 24), None)
            if dd is None:
                continue
            x, y, z, r1, r2, r3 = struct.unpack_from("<6f", dd)
            dz = shift(pl, x, y, z)
            if dz is None:
                continue
            nd = struct.pack("<6f", x, y, z + dz, r1, r2, r3) + dd[24:]
            put(ck, grp, bk, [[s_, nd if s_ == "DATA" else d] for s_, d in base])
            out_heads.setdefault(ck, heads.get(ck))
            g = (int(math.floor(x / 8192)), int(math.floor(y / 8192)))
            moved_by[(name_of.get(pl, pl), order[land_vers[g][-1][0]][0])] += 1
        # doors that arrive outside, on land that moved under them
        arrive_fixed = 0
        for bk, hist in door_hist.items():
            pl, grp, blk, ck = hist[-1]
            if has(blk, "DELE") or any(s_ == "DNAM" for s_, _d in blk):
                continue
            base = out[ck][bk][1] if bk in out.get(ck, {}) else blk
            dodt = next((d for s_, d in base if s_ == "DODT" and len(d) >= 24), None)
            if dodt is None:
                continue
            x, y, z, r1, r2, r3 = struct.unpack_from("<6f", dodt)
            dz = shift(pl, x, y, z)
            if dz is None:
                continue
            nd = struct.pack("<6f", x, y, z + dz, r1, r2, r3)
            put(ck, grp, bk, [[s_, nd if s_ == "DODT" else d] for s_, d in base])
            out_heads.setdefault(ck, heads.get(ck))
            arrive_fixed += 1
        total = sum(moved_by.values())
        print(f"  Reshaped land: {len(contested)} exterior cell(s) whose land two or more plugins change; "
              f"{total} object(s) moved up or down onto the land that's used"
              + (f", {arrive_fixed} door arrival(s) too" if arrive_fixed else ""))
        for (who, land), n in moved_by.most_common(12):
            print(f"      {n:6} of {who}'s, onto {land}'s land")
        if len(moved_by) > 12:
            print(f"      ... and {len(moved_by) - 12} more")

    # people, creatures, containers (and what the loser left in) standing where the winner built nothing - in
    # the void of a layout that isn't there any more - are moved to the place's arrival spot, a little apart
    def data_pos(blk):
        d = next((d for s_, d in blk if s_ == "DATA" and len(d) >= 24), None)
        return struct.unpack_from("<6f", d) if d else None
    for cl, (cell, w, l) in sorted(cells.items()):
        key = ("i", cl)
        spots = [g for g, _c in good.get(cl, [])]
        if not spots:
            continue
        sx, sy, sz, _r1, _r2, sr = struct.unpack_from("<6f", spots[0])
        layout, movers = [], []
        for (c, bk), vers in xver.items():
            if c != cl:
                continue
            if bk in out[key]:
                grp, blk = out[key][bk]
                prov = "patch"
            else:
                prov, grp, blk = vers[-1]
            if has(blk, "DELE"):
                continue
            p6 = data_pos(blk)
            if p6 is None:
                continue
            oid = name_in(blk).lower()
            if oid in actor_ids or oid in cont_ids or bk in kept_bk[cl]:
                movers.append((bk, grp, blk, p6, oid))
            elif prov != l:                      # what still stands there: the winner's, and the original's it kept
                layout.append(p6[:3])
        if len(layout) < 10:
            continue                             # too little of the winner's own to judge what's in the void
        grid = defaultdict(list)
        for x, y, z in layout:
            grid[(int(x // 300), int(y // 300))].append((x, y, z))

        def near(x, y, z):
            gx, gy = int(x // 300), int(y // 300)
            return any((a - x) ** 2 + (b - y) ** 2 + (c - z) ** 2 < 300 ** 2
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1) for a, b, c in grid.get((gx + dx, gy + dy), ()))
        moved = []
        for bk, grp, blk, p6, oid in movers:
            if near(*p6[:3]):
                continue
            i = len(moved)
            ang = i * 0.9
            r = 48 + 24 * (i // 7)
            nd = struct.pack("<6f", sx + r * math.cos(ang), sy + r * math.sin(ang), sz + 8, p6[3], p6[4], p6[5])
            nb = [[s_, nd if s_ == "DATA" else d] for s_, d in blk]
            put(key, grp, bk, nb)
            moved.append(name_in(blk))
        if moved:
            print(f"  '{cell}': {len(moved)} left in the void of the old layout, moved to the entrance: "
                  f"{', '.join(moved[:10])}{' ...' if len(moved) > 10 else ''}")

    if not any(out.values()) and not pgrds:
        print("  Nothing to change.")
        drop_patch()
        return 0
    if args.dry_run:
        print(f"  Dry run: {CELL_WINNER_PATCH} not written.")
        return 0
    lookup = index_dir(data_dir)
    needed = used | {w for _c, w, _l in cells.values()} | losers
    masters = [os.path.basename(lookup[m]) for m in sorted(needed, key=lambda m: pos.get(m, -1)) if m in lookup]
    if len(masters) > 250:
        print(f"  WARNING: the fixes touch objects of {len(masters)} plugins, more than a plugin can name as "
              f"masters (255); the rest are left out")
        masters = masters[:250]
    midx = {m.lower(): i + 1 for i, m in enumerate(masters)}
    recs, count = b"", 0
    for key, refs in out.items():
        if not refs:
            continue
        head = out_heads.get(key) or heads.get(key)
        if head is None:
            continue
        body = b"".join(pack_sub(s_, d) for s_, d in head)
        for grp in ("p", "t"):
            blocks = []
            for (owner, idx), (g, blk) in refs.items():
                if g != grp:
                    continue
                if owner not in midx:
                    continue
                blk[0] = ["FRMR", struct.pack("<I", (midx[owner] << 24) | idx)]
                blocks.append(blk)
            if grp == "t" and blocks:
                body += pack_sub("NAM0", struct.pack("<I", len(blocks)))
            for blk in blocks:
                body += b"".join(pack_sub(s_, d) for s_, d in blk)
        recs += b"CELL" + struct.pack("<III", len(body), 0, 0) + body
        count += 1
    for key, head in out_heads.items():          # head only: the cell's settings without the loser
        if not out.get(key) and head is not None:
            body = b"".join(pack_sub(s_, d) for s_, d in head)
            recs += b"CELL" + struct.pack("<III", len(body), 0, 0) + body
            count += 1
    for r in pgrds:
        recs += r
        count += 1
    desc = "Rebuilt interiors: the chosen mod's version wins (rebuilt by mwdialog_check --fix)"
    hedr = (struct.pack("<fI", 1.3, 0) + b"mwdialog_check".ljust(32, b"\0")
            + desc.encode(ENC, MW_ERRORS)[:255].ljust(256, b"\0") + struct.pack("<I", count))
    subs = [pack_sub("HEDR", hedr)]
    for mname in masters:
        subs += [pack_sub("MAST", mname.encode(ENC, MW_ERRORS) + b"\0"),
                 pack_sub("DATA", struct.pack("<Q", os.path.getsize(os.path.join(data_dir, mname))))]
    hb = b"".join(subs)
    if os.path.exists(out_path):
        shutil.copy2(out_path, backup_path(out_path))
    write_plugin_bytes(out_path, b"TES3" + struct.pack("<III", len(hb), 0, 0) + hb + recs)
    when = max(os.path.getmtime(os.path.join(data_dir, m)) for m in masters) + 60
    os.utime(out_path, (when, when))
    cur = read_load_order(args) or []
    if CELL_WINNER_PATCH.lower() not in {n.lower() for n in cur}:
        tail = {PLACE_PATCH_NAME.lower(), MULTI_PATCH_NAME.lower()}
        at = next((i for i, n in enumerate(cur) if n.lower() in tail), len(cur))
        set_game_files(args.ini or os.path.join(game_dir, "Morrowind.ini"), cur[:at] + [CELL_WINNER_PATCH] + cur[at:],
                       "--fix (cell winners)")
    with MT.open_log(os.path.join(game_dir, args.fix_log), "a", encoding="utf-8") as lf:
        lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {CELL_WINNER_PATCH}: "
                 + "; ".join(f"{c}: {name_of[w]} over {name_of[l]}" for c, w, l in cells.values()) + "\n")
    print(f"  Wrote {CELL_WINNER_PATCH} ({count} record(s)); it loads near the end, before the Multipatch.")
    return 0


def fix_omwaddon_masters(args):
    """--fix: plugins whose header names a master as "<name>.omwaddon" when Data Files has "<name>.esp" (or .esm)
    and no such .omwaddon in the load order (an OpenMW plugin renamed for Morrowind, as vortex_tidy does): the
    master's name and size in the header are changed to the .esp's. .bak first, file date kept; an .esm is
    never changed, only reported."""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    lookup = index_dir(data_dir)
    active = {n.lower() for n in (read_load_order(args) or [])}
    todo = []
    for low, path in sorted(lookup.items()):
        if not low.endswith((".esp", ".esm", ".omwaddon")):
            continue
        try:
            with open(path, "rb") as f:
                head = f.read(16)
                if head[:4] != b"TES3":
                    continue
                data = head + f.read(struct.unpack_from("<I", head, 4)[0])
            masters = plugin_masters(data)
        except (OSError, FormatError, struct.error, StopIteration):
            continue
        changes = []
        for mname in masters:
            ml = mname.lower()
            if not ml.endswith(".omwaddon") or (ml in lookup and ml in active):
                continue
            stem = mname[:-len(".omwaddon")]
            for ext in (".esp", ".esm"):
                if (stem + ext).lower() in lookup:
                    changes.append((mname, os.path.basename(lookup[(stem + ext).lower()])))
                    break
        if changes:
            todo.append((os.path.basename(path), path, changes))
    if not todo:
        return 0
    print("\n" + "=" * 70 + "\nMASTERS NAMED .omwaddon THAT ARE .esp FILES HERE\n" + "=" * 70)
    fixed = 0
    for name, path, changes in todo:
        what = "; ".join(f"{a} -> {b}" for a, b in changes)
        if name.lower().endswith(".esm"):
            print(f"  {name}: {what} (an .esm: not changed, as --fix never changes .esm files; fix its header by hand)")
            continue
        if args.dry_run:
            print(f"  {name}: would change {what}")
            continue
        with open(path, "rb") as f:
            data = f.read()
        recs = [data[off:off + 16 + len(body)] for off, _t, _f, body in iter_records(data)]
        _off, _tag, flags, body = next(iter_records(data))
        subs, ren, i = list(iter_subs(body)), {a.lower(): b for a, b in changes}, 0
        out_subs = []
        while i < len(subs):
            sname, sdata = subs[i]
            if sname == "MAST" and cstr(sdata).lower() in ren:
                new = ren[cstr(sdata).lower()]
                out_subs.append(("MAST", new.encode(ENC, MW_ERRORS) + b"\0"))
                if i + 1 < len(subs) and subs[i + 1][0] == "DATA":
                    out_subs.append(("DATA", struct.pack("<Q", os.path.getsize(os.path.join(data_dir, new)))))
                    i += 1
            else:
                out_subs.append((sname, sdata))
            i += 1
        nb = b"".join(pack_sub(n, d) for n, d in out_subs)
        recs[0] = b"TES3" + struct.pack("<III", len(nb), struct.unpack_from("<I", data, 8)[0], flags) + nb
        bak = write_inplace(path, recs)
        fixed += 1
        print(f"  {name}: {what} (backup {os.path.basename(bak)})")
        with MT.open_log(os.path.join(game_dir, args.fix_log), "a", encoding="utf-8") as lf:
            lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {name}: master renamed {what}\n")
    if fixed:
        print(f"  {fixed} plugin header(s) fixed.")
    return fixed


SHORT_MESH_RECORD = "mwdialog_short_meshes.txt"
LIMITED_MODEL_TAGS = ("BODY", "ARMO", "CLOT")      # their model path must fit in 31 characters
NO_ID_TAGS = {"CELL", "DIAL", "INFO", "TES3", "LAND", "PGRD", "GMST", "SCPT", "SNDG", "REGN", "SSCR", "LTEX",
              "SKIL", "MGEF", "BSGN"}


def _short_mesh(path):
    """A path for `path` (relative to Meshes) that fits in 31 characters: same folder and the start of the
    file name, plus a short hash of the full path so two long names can't end up the same."""
    import hashlib
    folder, fn = os.path.split(path)
    stem, ext = os.path.splitext(fn)
    tag = hashlib.md5(path.lower().encode("latin-1", "replace")).hexdigest()[:4]
    room = 31 - (len(folder) + 1 if folder else 0) - len(ext) - 5
    if room < 4:
        folder, room = "mwd", 31 - 4 - len(ext) - 5
    return os.path.join(folder, f"{stem[:room]}_{tag}{ext}") if folder else f"{stem[:room]}_{tag}{ext}"


def _rebuild(raw, subs):
    body = b"".join(pack_sub(n, d) for n, d in subs)
    return raw[:4] + struct.pack("<I", len(body)) + raw[8:16] + body


# string fields that hold another object's id (outside INFO/SCPT/DIAL, which are only reported)
ID_REF_FIELDS = frozenset(("ENAM", "SCRI", "NPCS", "BNAM", "CNAM", "RNAM", "ANAM", "KNAM", "TNAM", "XSOL"))


def fix_long_names(args, plugins, bsas):
    """--fix: strings longer than the game keeps (it cuts them at 31 characters and warns at startup):
      - BODY/ARMO/CLOT model paths: the mesh gets a copy under a shorter name (a hard link where it can,
        so it takes no space), and the record points to that
      - object ids of 32+ characters: renamed to their first 31 (what the game already cuts them to), in
        every active plugin: the record, inventories (NPCO/NPCS), leveled lists, placed references and the
        other fields that name an object (script, enchantment, owner, key, trap, soul, race, class, body
        part...). Ids that scripts or dialogue use are only reported, as are ids whose short name another
        id already has or shares (renaming would merge two objects).
    .esp files only (.bak first, dates kept); an .esm is reported. With --openmw-cfg it only reports (the
    data folders there aren't one Data Files folder to put short meshes in)."""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    report_only = bool(getattr(args, "openmw_cfg", None))
    models, ids, users = [], {}, set()
    all_ids = set()
    datas = {}
    for name, path in plugins:
        if is_our_patch(name):
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
            recs = list(iter_records(data))
        except (OSError, FormatError):
            continue
        datas[name] = (path, data, recs)
        for off, tag, flags, body in recs:
            if tag in NO_ID_TAGS:
                continue
            nm = first_sub(body, b"NAME")
            if nm is not None:
                all_ids.add(cstr(nm).lower())
            if nm is not None and len(cstr(nm)) > 31:
                ids.setdefault(cstr(nm).lower(), (cstr(nm), name, tag))
            if tag in LIMITED_MODEL_TAGS:
                for sn, d in iter_subs(body):
                    if sn == "MODL" and len(cstr(d)) > 31:
                        models.append((name, tag, cstr(nm or b""), cstr(d)))
    if not models and not ids:
        return 0
    # ids scripts or dialogue mention can't be renamed safely (compiled scripts hold them too)
    for name, (path, data, recs) in datas.items():
        low = data.lower()
        for idl in list(ids):
            if idl.encode(ENC, MW_ERRORS) in low:
                for off, tag, flags, body in recs:
                    if tag in ("SCPT", "INFO") and idl.encode(ENC, MW_ERRORS) in body.lower():
                        users.add(idl)
                        break
    print("\n" + "=" * 70 + "\nNAMES LONGER THAN THE GAME KEEPS (31 characters)\n" + "=" * 70)
    in_bsa = {}
    for b in bsas:
        try:
            for nm, where in bsa_index(b).items():
                if nm.startswith("meshes\\"):
                    in_bsa.setdefault(nm[7:], (b, where))
        except (OSError, struct.error, FormatError) as e:
            print(f"  note: couldn't read {os.path.basename(b)} ({e})")
    renames = {}                                     # long model (lower) -> short
    for name, tag, rid, mpath in models:
        key = mpath.lower().replace("/", "\\")
        if key in renames:
            continue
        renames[key] = _short_mesh(mpath.replace("/", "\\"))
    new_ids = {}
    prefixes = Counter(idl[:31] for idl in ids)
    for idl, (orig, by, tag) in ids.items():
        if idl in users:
            print(f"  {tag} '{orig}' ({by}): {len(orig)} characters, but scripts or dialogue use it; not renamed")
            continue
        if prefixes[idl[:31]] > 1 or idl[:31] in all_ids:
            print(f"  {tag} '{orig}' ({by}): {len(orig)} characters, but its first 31 ('{orig[:31]}') would be "
                  f"the same as another object's id; not renamed (rename one of them in the CS)")
            continue
        new_ids[idl] = orig[:31]
    for name, tag, rid, mpath in models:
        print(f"  {name}: {tag} {rid}: model '{mpath}' -> '{renames[mpath.lower().replace('/', chr(92))]}'")
    for idl, new in new_ids.items():
        print(f"  {ids[idl][2]} '{ids[idl][0]}' ({ids[idl][1]}) -> '{new}' in every plugin that uses it")
    if report_only and (renames or new_ids):
        print("  (--openmw-cfg: only reported; run without it, on the Data Files setup, to change anything)")
    if args.dry_run or report_only:
        return 0
    # the short meshes
    made = []
    for longp, short in renames.items():
        dst = os.path.join(data_dir, "Meshes", short)
        if os.path.exists(dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        src = os.path.join(data_dir, "Meshes", longp)
        src = src if os.path.isfile(src) else None
        try:
            if src:
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
            elif longp in in_bsa:
                b, (off, size) = in_bsa[longp]
                with open(b, "rb") as f:
                    f.seek(off)
                    blob = f.read(size)
                with open(dst, "wb") as f:
                    f.write(blob)
            else:
                print(f"  (mesh '{longp}' not found in Data Files or a BSA: the record is changed anyway)")
                continue
            made.append((longp, short))
        except OSError as e:
            print(f"  could not make Meshes\\{short}: {e}")
    if made:
        with open(os.path.join(game_dir, SHORT_MESH_RECORD), "a", encoding="utf-8") as f:
            for longp, short in made:
                f.write(f"{short}\t{longp}\n")
    # the plugins
    fixed = 0

    def id_hit(d):
        """The new id if string field `d` names a renamed id (whole value; a full 32-byte field may hold the
        id cut without its NUL), else None."""
        z = d.find(b"\0")
        if z >= 0 and d[z:].strip(b"\0"):
            return None                              # not a plain string field
        item = cstr(d).lower()
        if item in new_ids:
            return new_ids[item]
        if len(d) == 32 and len(item) == 32:
            return next((v for k, v in new_ids.items() if k.startswith(item)), None)
        return None
    for name, (path, data, recs) in datas.items():
        if not name.lower().endswith(FIXABLE_EXT):
            if name in {m[0] for m in models} or any(v[1] == name for v in ids.values()):
                print(f"  {name}: an .esm, not changed (--fix never changes .esm files)")
            continue
        out, changed = [], 0
        for off, tag, flags, body in recs:
            raw = data[off:off + 16 + len(body)]
            subs, touched = list(iter_subs(body)), False
            in_ref = False                           # CELL: past the first FRMR, NAME is the placed object
            for i, (sn, d) in enumerate(subs):
                if sn == "FRMR":
                    in_ref = True
                if not new_ids or tag in ("INFO", "SCPT", "DIAL"):
                    pass
                elif (sn in ID_REF_FIELDS or (sn == "NAME" and tag == "CELL" and in_ref)) and len(d) >= 32:
                    hit = id_hit(d)
                    if hit:
                        nb = hit.encode(ENC, MW_ERRORS)
                        subs[i] = (sn, nb.ljust(len(d), b"\0") if sn == "NPCS" else nb + b"\0")
                        touched = True
                        continue
                if sn == "MODL" and tag in LIMITED_MODEL_TAGS:
                    k = cstr(d).lower().replace("/", "\\")
                    if k in renames:
                        subs[i] = (sn, renames[k].encode(ENC, MW_ERRORS) + b"\0")
                        touched = True
                elif sn == "NAME" and tag not in NO_ID_TAGS and cstr(d).lower() in new_ids:
                    subs[i] = (sn, new_ids[cstr(d).lower()].encode(ENC, MW_ERRORS) + b"\0")
                    touched = True
                elif sn == "NPCO" and len(d) >= 36:
                    item = d[4:36].split(b"\0")[0].decode("latin-1").lower()
                    hit = next((v for k, v in new_ids.items() if k == item or (len(item) == 32 and k.startswith(item))), None)
                    if hit:
                        subs[i] = (sn, d[:4] + hit.encode(ENC, MW_ERRORS).ljust(32, b"\0") + d[36:])
                        touched = True
                elif sn in ("INAM", "CNAM") and tag in ("LEVI", "LEVC") and cstr(d).lower() in new_ids:
                    subs[i] = (sn, new_ids[cstr(d).lower()].encode(ENC, MW_ERRORS) + b"\0")
                    touched = True
            if touched:
                raw = _rebuild(raw, subs)
                changed += 1
            out.append(raw)
        if changed:
            bak = write_inplace(path, out)
            fixed += 1
            print(f"  {name}: {changed} record(s) changed (backup {os.path.basename(bak)})")
            with MT.open_log(os.path.join(game_dir, args.fix_log), "a", encoding="utf-8") as lf:
                lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {name}: {changed} record(s): names cut to "
                         f"31 characters (short meshes in {SHORT_MESH_RECORD})\n")
    if made:
        print(f"  {len(made)} mesh(es) given a short name (listed in {SHORT_MESH_RECORD}).")
    return fixed


def fix_ref_groups(args, plugins):
    """--fix: a reference the master keeps in its temporary group, but a plugin changes as a persistent one:
    the game looks for it among the master's persistent references, can't find it ("Object reference ...
    missing in master file" at startup, once per plugin) and the change is lost. Such references are moved
    to the temporary group. Only references owned by an .esp master are affected: the game finds an .esm's
    references in either group. (A master's persistent reference listed as temporary is found; left alone.)
    .esp files only (.bak first, dates kept)."""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    paths = {n.lower(): p for n, p in plugins}
    wanted = defaultdict(set)              # owner -> cells to read
    found = []                             # (plugin, path, data, recs)
    for name, path in plugins:
        if is_our_patch(name) or not name.lower().endswith(FIXABLE_EXT):
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
            ms = [x.lower() for x in plugin_masters(data)]
            recs = list(iter_records(data))
        except (OSError, FormatError):
            continue
        hit = False
        for off, tag, flags, body in recs:
            if tag != "CELL":
                continue
            key = cell_key(body)[0]
            if key is None:
                continue
            head, pers, _n0, temp = split_cell(body)
            for blk in pers + temp:
                bk = block_key(blk, ms, name.lower())
                if bk and bk[0] != name.lower():
                    wanted[bk[0]].add(key)
                    hit = True
        if hit:
            found.append((name, path, data, ms, recs))
    # a script or dialogue result that names the object needs it persistent: those are reported, not moved
    texts = []
    for name, path in plugins:
        try:
            with open(path, "rb") as f:
                d = f.read()
            for off, tag, flags, body in iter_records(d):
                if tag == "SCPT":
                    texts.append((first_sub(body, b"SCTX") or b"").lower())
                elif tag == "INFO":
                    texts.append((first_sub(body, b"BNAM") or b"").lower())
        except (OSError, FormatError):
            continue
    script_text = b"\n".join(texts)
    groups = {}                            # (owner, cell key, index) -> "p" / "t" in the owner itself
    for owner, keys in wanted.items():
        p = paths.get(owner)
        if not p:
            continue
        try:
            with open(p, "rb") as f:
                odata = f.read()
            oms = [x.lower() for x in plugin_masters(odata)]
            for off, tag, flags, body in iter_records(odata):
                if tag != "CELL":
                    continue
                key = cell_key(body)[0]
                if key not in keys:
                    continue
                head, pers, _n0, temp = split_cell(body)
                for grp, blks in (("p", pers), ("t", temp)):
                    for blk in blks:
                        bk = block_key(blk, oms, owner)
                        if bk and bk[0] == owner:
                            groups[(owner, key, bk[1])] = grp
        except (OSError, FormatError):
            continue
    todo = []
    for name, path, data, ms, recs in found:
        out, moved, scripted = [], [], []
        for off, tag, flags, body in recs:
            raw = data[off:off + 16 + len(body)]
            if tag == "CELL":
                key, label = cell_key(body)
                if key is not None:
                    head, pers, n0, temp = split_cell(body)
                    np_, nt = [], []
                    change = False
                    for grp, blks in (("p", pers), ("t", temp)):
                        for blk in blks:
                            bk = block_key(blk, ms, name.lower())
                            want = groups.get((bk[0], key, bk[1])) if bk and bk[0] != name.lower() else None
                            # Only an .esp master trips the game ("missing in master file"); references of an .esm
                            # are found in either group, and scripts may rely on the plugin making them persistent.
                            if bk and bk[0].endswith(".esm"):
                                want = None
                            # only this direction loses the reference: kept temporary by the master but listed
                            # as persistent here ("missing in master file"). The other way round the game copes.
                            oid = cstr(next((d for s_, d in blk if s_ == "NAME"), b""))
                            # The game only ever looks in the master's group, so a reference a script names is
                            # moved too (persistent here can't help the script: the lookup fails either way).
                            if want == "t" and grp == "p" and oid and oid.lower().encode(ENC, MW_ERRORS) in script_text:
                                scripted.append((label, oid))
                            if want == "t" and grp == "p":
                                change = True
                                moved.append((label, oid, "temporary"))
                                nt.append(blk)
                            else:
                                (np_ if grp == "p" else nt).append(blk)
                    if change:
                        nb = b"".join(pack_sub(s_, d) for s_, d in head)
                        for blk in np_:
                            nb += b"".join(pack_sub(s_, d) for s_, d in blk)
                        if nt:
                            nb += pack_sub("NAM0", struct.pack("<I", len(nt)))
                            for blk in nt:
                                nb += b"".join(pack_sub(s_, d) for s_, d in blk)
                        raw = raw[:4] + struct.pack("<I", len(nb)) + raw[8:16] + nb
            out.append(raw)
        if moved or scripted:
            todo.append((name, path, out, moved, scripted))
    if not todo:
        return 0
    print("\n" + "=" * 70 + "\nMASTER REFERENCES IN THE WRONG GROUP (the game can't find them)\n" + "=" * 70)
    changed = 0
    for name, path, out, moved, scripted in todo:
        if scripted:
            print(f"  {name}: {len(scripted)} of them named by a script or dialogue (moved anyway: the master "
                  f"keeps them temporary, so the game only finds them there): "
                  + ", ".join(f"{o} in {c}" for c, o in scripted[:4]) + (" ..." if len(scripted) > 4 else ""))
        if not moved:
            continue
        print(f"  {name}: {len(moved)} reference(s) to the temporary group, e.g. "
              + ", ".join(f"{o} in {c}" for c, o, g in moved[:3]))
        if args.dry_run:
            continue
        changed += 1
        bak = write_inplace(path, out)
        print(f"    moved to the master's group (backup {os.path.basename(bak)})")
        with MT.open_log(os.path.join(game_dir, args.fix_log), "a", encoding="utf-8") as lf:
            lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {name}: {len(moved)} master reference(s) moved to "
                     f"the master's group: " + "; ".join(f"{o} in {c}" for c, o, g in moved) + "\n")
    return changed


def drop_performers_patch(args):
    """Doubled bards are handled in the game by the mwperformers MWSE mod (it hides them, so they can be
    shown again). The patch that deleted them would keep them from coming back, so it's taken out."""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    path = os.path.join(data_dir, PERFORMER_PATCH)
    cur = read_load_order(args) or []
    if not os.path.exists(path) and PERFORMER_PATCH.lower() not in {n.lower() for n in cur}:
        return 0
    if os.path.exists(path):
        bak = backup_path(path)
        os.replace(path, bak)
    if PERFORMER_PATCH.lower() in {n.lower() for n in cur}:
        set_game_files(args.ini or os.path.join(game_dir, "Morrowind.ini"),
                       [n for n in cur if n.lower() != PERFORMER_PATCH.lower()], "--fix (performers now in MWSE)")
    print(f"\n  {PERFORMER_PATCH} removed: doubled performers are now hidden in the game by the mwperformers "
          f"MWSE mod (one band per inn, follows the load order). --fix --performers-patch builds the patch instead.")
    return 1


def fix_doubled(args, plugins):
    """--fix: turn off plugins that another active plugin already duplicates (the same objects placed
    twice in the same spots: two versions of one mod, or one containing the other). Which one stays:
    never a plugin another active plugin needs as a master goes; else the bigger one stays when it
    contains the other; else the one loading later (its version already wins). Pairs you keep together
    in an [Exact] rule are left alone. Returns the names turned off (or that would be, with --dry-run)."""
    game_dir = os.path.dirname(os.path.abspath(args.data_dir))
    print("\n" + "=" * 70 + "\nDOUBLED PLUGINS (the same objects placed twice)\n" + "=" * 70)
    print("  Looking for plugins that place the same objects twice...", file=sys.stderr)
    ctx = run_cell_conflicts(args, plugins, collect=True)
    pairs, name_of, total, pos, masters = (ctx["pairs"], ctx["name_of"], ctx["total_new"], ctx["pos"],
                                           ctx["masters"])
    exact = [{e.lower() for e in ents} for k, ents, _s in parse_rules(os.path.join(game_dir, RULES_FILE))[0]
             if k == "exact"]
    needed = {m for ms in masters.values() for m in ms}          # masters of something active
    doubled = [(a, b) for (a, b), c in pairs.items() if c["doubled"]]
    kept_exact = [(a, b) for a, b in doubled if any(a in g and b in g for g in exact)]
    doubled = [p for p in doubled if p not in kept_exact]
    if not doubled:
        print("  None." + (f" ({len(kept_exact)} doubled pair(s) left alone: you keep them together in an [Exact] rule)"
                           if kept_exact else ""))
        return []
    parent = {}

    def root(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in doubled:
        parent[root(a)] = root(b)
    groups = defaultdict(list)
    for x in list(parent):
        groups[root(x)].append(x)
    dpairs = {frozenset(p) for p in doubled}
    off = []
    for members in groups.values():
        members.sort(key=lambda n: pos[n])
        keep = max(members, key=lambda n: (n in needed, total[n], pos[n]))
        why_keep = ("other active plugins need it as a master" if keep in needed else
                    "it has the most objects (it contains the other's)" if total[keep] > 1.1 * min(total[m] for m in members if m != keep)
                    else "it loads later, so its version already wins")
        for m in members:
            if m == keep:
                continue
            if m in needed:
                print(f"  {name_of[m]}: doubled with {name_of[keep]}, but other active plugins need it as a master; "
                      f"left on")
                continue
            hit = relied_on(plugins, m, [x for x, _w in off])
            if hit:
                print(f"  {name_of[m]}: doubled with {name_of[keep]}, but {relied_on_text(hit, name_of)}; left on")
                continue
            if frozenset((m, keep)) not in dpairs and not any(frozenset((m, k)) in dpairs for k in members if k != m):
                continue
            c = pairs.get((m, keep)) or pairs.get((keep, m)) or {}
            dups = c.get("dups", 0)
            print(f"  turn off {name_of[m]}: {dups or 'most'} of its {total[m]} new objects are already placed, in the "
                  f"same spots, by {name_of[keep]} (kept: {why_keep})")
            off.append((name_of[m], f"doubled with {name_of[keep]}"))
    for a, b in kept_exact:
        print(f"  left alone: {name_of[a]} + {name_of[b]} (you keep them together in an [Exact] rule)")
    if not off:
        return []
    if args.dry_run:
        print("  Dry run: nothing turned off.")
        return [n for n, _w in off]
    if not args.yes and (not sys.stdin.isatty() or input(f"\nTurn off {len(off)} doubled plugin(s)? [y/N] ")
                         .strip().lower() not in ("y", "yes")):
        print("  Nothing turned off.")
        return []
    ini = args.ini or os.path.join(game_dir, "Morrowind.ini")
    gone = {n.lower() for n, _w in off}
    cur = read_load_order(args) or []
    backup = set_game_files(ini, [n for n in cur if n.lower() not in gone], "--fix (doubled plugins)")
    rec = read_disabled(game_dir)
    for n, w in off:
        rec[n] = w
    write_disabled(game_dir, rec)
    print(f"  Turned off {len(off)} plugin(s) (old list saved as {backup}); listed in {DISABLED_RECORD} so "
          f"--add-all-esp leaves them out. --reenable NAME turns one back on.")
    return [n for n, _w in off]


WINNER_RE = re.compile(r"(?:doubled with|conflicts with) (?P<w>.+?)\)?$")


def release_lost_winners(args):
    """Each plugin in mwdialog_disabled.txt was turned off in favour of another (the "winner": doubled with
    it, or conflicting with it). When that winner is gone - not in Data Files, or no longer active (in the
    load order or inside an active merge) - the plugin that lost is turned back on. Runs at the start of
    every run that isn't a dry run."""
    if getattr(args, "plugins", None) or getattr(args, "openmw_cfg", None) or args.dry_run:
        return 0
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    rec = read_disabled(game_dir)
    if not rec:
        return 0
    lookup = index_dir(data_dir)
    active = {n.lower() for n in (read_load_order(args) or [])} | merged_away(game_dir, data_dir)
    lost = []
    for loser, why in rec.items():
        m = WINNER_RE.search(why)
        if not m:
            continue
        winner = m.group("w").strip()
        if winner.lower() not in lookup:
            lost.append((loser, winner, "is no longer in Data Files"))
        elif winner.lower() not in active:
            lost.append((loser, winner, "is no longer in the load order"))
    lost = [x for x in lost if x[0].lower() in lookup]
    if not lost:
        return 0
    print("\nPlugins turned off in favour of another that is gone:")
    for loser, winner, how in lost:
        print(f"  {loser}: turned off for {winner}, which {how}; turning {loser} back on")
    a2 = copy.copy(args)
    a2.reenable = [l for l, _w, _h in lost]
    a2.dry_run = False
    run_reenable(a2)
    return len(lost)


def run_reenable(args):
    """--reenable [NAME...]: turn plugins --fix turned off (doubled) back on."""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    rec = read_disabled(game_dir)
    want = {x.lower() for x in args.reenable} if args.reenable else {n.lower() for n in rec}
    todo = [n for n in rec if n.lower() in want]
    if not todo:
        print("--reenable: none of those were turned off by --fix. Turned off: " + (", ".join(rec) or "none"))
        return 1
    ini = args.ini or os.path.join(game_dir, "Morrowind.ini")
    lookup = index_dir(data_dir)
    cur = read_load_order(args) or []
    paths = [lookup[n.lower()] for n in cur if n.lower() in lookup] + \
            [lookup[n.lower()] for n in todo if n.lower() in lookup and n.lower() not in {c.lower() for c in cur}]
    if args.dry_run:
        print("--reenable would turn back on: " + ", ".join(todo))
        return 0
    backup = set_game_files(ini, [os.path.basename(p) for p in sort_vanilla(paths)], "reenable")
    for n in todo:
        del rec[n]
    write_disabled(game_dir, rec)
    print(f"  Turned back on: {', '.join(todo)} (old list saved as {backup}).")
    return 0


# --------------------------------------------------------------------------
# --redundant: plugins doing the same job as another
# --------------------------------------------------------------------------


def run_redundant(args):
    """--redundant / --redundant-auto: find plugins doing the same job as another, describe each and how they
    overlap, and (asking, or with --redundant-auto for the sure ones) turn the redundant one off."""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    print("\n" + "=" * 70 + "\nREDUNDANT PLUGINS (two plugins doing the same job)\n" + "=" * 70)
    lookup = index_dir(data_dir)
    cur = read_load_order(args) or []
    plugins = [(os.path.basename(lookup[n.lower()]), lookup[n.lower()]) for n in cur if n.lower() in lookup]
    # an AutoMerge (or --merge) is measured as the plugins it was built from: one of them can be redundant
    # too (it is then left out of the merge's next rebuild)
    plugins, merge_owner = expand_merged(plugins, merged_inputs_of(game_dir, data_dir))
    paths = {n.lower(): p for n, p in plugins}
    off_rec, both = read_redundant(game_dir)
    print(f"  Comparing the records of {len(plugins)} active plugins...", file=sys.stderr)
    ours = {n.lower() for n, _p in plugins if is_our_patch(n) or not multipatch_source(n)}
    ours |= {k.lower() for k in read_merge_record(game_dir)}
    soft = set()
    for dep, mods in read_added_masters(game_dir).items():
        for mod in (mods or {}):
            p = paths.get(dep.lower())
            try:
                if p and not added_master_in_use(p, mod):
                    soft.add((dep.lower(), mod.lower()))
            except (OSError, FormatError, IndexError):
                pass
    res = find_redundant(plugins, lua=lua_required_plugins(data_dir), keep_both=both, no_candidates=ours,
                         soft_masters=soft)
    vroot = None
    if not getattr(args, "no_vortex", False):
        try:
            vroot = args.vortex_dir
        except (OSError, AttributeError):
            vroot = None
    N = res["names"]
    exact, variant = res["exact"], res["variant"]
    if off_rec:
        print(f"  Turned off earlier (in {REDUNDANT_RECORD}; --redundant-undo puts them back): "
              + ", ".join(f"{n} (kept {k})" for n, (k, _w) in off_rec.items()))
    if both:
        print(f"  Already answered, not asked again (keep both, in {REDUNDANT_RECORD}; --redundant-undo forgets): "
              + "; ".join(" + ".join(N.get(x, x) for x in sorted(pair)) for pair in sorted(both, key=sorted)))
    if not exact and not variant:
        print("  None found.")
        return 0
    groups = []
    if exact:
        print(f"\n  Doing nothing another plugin doesn't already do ({len(exact)}): taking one out changes no "
              f"record in the game.")
    for e in exact:
        l, k = e["plugin"], e["keep"]
        nonitm = e["records"] - e["itm"]
        print(f"\n  [{e['confidence']}] {N[l]}  ->  turn off, keep {N[k]}")
        others = "" if e["confidence"] == "high" else \
            f" ({e['copies'][k]} of them) and of " + ", ".join(N[x] for x in e["copies"] if x != k)
        if not nonitm:
            what = f"all {e['records']} of its records are identical to the version loading before them (ITM)"
        elif not e["itm"]:
            what = f"all {e['records']} of its records are identical copies of {N[k]}'s{others}"
        else:
            what = (f"{e['itm']} of its {e['records']} records are identical to the version loading before them "
                    f"(ITM); the other {nonitm} are identical copies of {N[k]}'s{others}")
        print(f"    why: {what}. Taking it out changes no record's winner and loses no record.")
        for line in describe_plugin(res, l, vroot, paths) + describe_plugin(res, k, vroot, paths):
            print("  " + line)
        for line in describe_overlap(res, l, k):
            print("  " + line)
        groups.append(("exact", e))
    if variant:
        print(f"\n  Two versions of one mod, both active ({len(variant)}): most records shared and identical. "
              f"Their differences are real conflicts, so nothing here is turned off unless you choose to.")
    for v in variant:
        a, b = v["a"], v["b"]
        print(f"\n  [choice] {N[a]}  vs  {N[b]}")
        for line in describe_plugin(res, a, vroot, paths) + describe_plugin(res, b, vroot, paths) \
                + describe_overlap(res, a, b):
            print("  " + line)
        for x, why in v["blocked"].items():
            print(f"    {N[x]} can't be turned off: {why}")
        groups.append(("variant", v))
    console, why_not_console = console_interactive()
    interactive = console and not getattr(args, "no_interactive", False)
    auto = getattr(args, "redundant_auto", False)
    sure = [g for kind, g in groups if kind == "exact" and g["confidence"] == "high" and g["plugin"].endswith(".esp")]
    if not interactive:
        why = "--no-interactive was given" if console else why_not_console
        print(f"\n  Not asking: {why}. " + (f"Turning off the {len(sure)} high-confidence duplicate(s) (--redundant-auto); "
                                           f"the other {len(groups) - len(sure)} group(s) are only reported."
                                           if auto else "Reporting only; nothing is turned off."))
    elif auto and sure:
        print(f"\n  --redundant-auto: the {len(sure)} high-confidence duplicate(s) are turned off without asking; "
              f"asking about the other {len(groups) - len(sure)}.")
    turn_off, new_both = [], set()
    quit_asking = False
    for kind, g in groups:
        if quit_asking:
            break
        if kind == "exact":
            l, k = g["plugin"], g["keep"]
            if auto and g["confidence"] == "high" and l.endswith(".esp"):
                turn_off.append((l, k, "doubles " + N[k] + (" (all ITM)" if g["itm"] == g["records"] else "")))
                continue
            if not interactive:
                continue
            ans = ask(f"\n  [{g['confidence']}] {N[l]}: [o] turn it off (keep {N[k]})  [k] keep both  "
                      f"[s] skip (ask again next time)  [q] stop asking > ")
            if ans is None or ans.startswith("q"):
                quit_asking = True
                continue
            if ans.startswith("o"):
                turn_off.append((l, k, "doubles " + N[k]))
            elif ans.startswith("k"):
                new_both.add(frozenset((l, k)))
        else:
            a, b = g["a"], g["b"]
            if not interactive:
                continue
            opts = [x for x in (a, b) if x not in g["blocked"]]
            if not opts:
                continue
            prompt = "\n  " + "  ".join(f"[{c}] keep {N[keep]}, turn off {N[x]}" for c, keep, x in
                                        (("a", a, b), ("b", b, a)) if x in opts) + "  [k] keep both  [s] skip > "
            ans = ask(prompt.replace(" > ", "  [q] stop asking > "))
            if ans is None or ans.startswith("q"):
                quit_asking = True
                continue
            if ans.startswith("a") and b in opts:
                turn_off.append((b, a, "another version of " + N[a] + " (your choice)"))
            elif ans.startswith("b") and a in opts:
                turn_off.append((a, b, "another version of " + N[b] + " (your choice)"))
            elif ans.startswith("k"):
                new_both.add(frozenset((a, b)))
    if not turn_off and not new_both:
        if not interactive and not auto:
            print("\n  Report only (nothing changed). --redundant in a console asks about each; --redundant-auto "
                  "turns off the high-confidence ones by itself.")
        return 1
    if args.dry_run:
        print("\n  Dry run: would turn off " + (", ".join(N[l] for l, _k, _w in turn_off) or "nothing") + ".")
        return 1
    if turn_off:
        gone = {l for l, _k, _w in turn_off}
        ini = args.ini or os.path.join(game_dir, "Morrowind.ini")
        backup = None
        if any(n.lower() in gone for n in cur):
            backup = set_game_files(ini, [n for n in cur if n.lower() not in gone], "--redundant")
        rebuild = OrderedDict()
        for l, k, w in turn_off:
            off_rec[N[l]] = (N[k], w)
            owner = merge_owner.get(l)
            if owner:
                merged = next((m for m in read_merge_record(game_dir) if m.lower() == owner), owner)
                rebuild.setdefault(merged, []).append(N[l])
                print(f"  turned off {N[l]} (kept {N[k]}): it is merged into {merged}, which must be rebuilt "
                      f"without it")
            else:
                print(f"  turned off {N[l]} (kept {N[k]})")
            fix_log_line(args, game_dir, f"--redundant: turned off {N[l]} (kept {N[k]}; {w})"
                         + (f"; merged into {owner}: marked for rebuild" if owner else ""))
        if rebuild:
            mark_merge_rebuild(game_dir, rebuild)
            print(f"  Marked for rebuild ({MERGE_REBUILD_RECORD}): " + ", ".join(rebuild)
                  + " - --auto-merge (or --full) rebuilds it without the plugins turned off.")
        print((f"  Old load order saved as {backup}; listed" if backup else "  Listed") + f" in {REDUNDANT_RECORD}. "
              f"--redundant-undo NAME turns one back on.")
        if any((d, l) in res["soft"] for l in gone for d in res["dependents"].get(l, [])):
            drop_vanished_added_masters(args)          # now, so no plugin is left listing a master that's off
    write_redundant(game_dir, off_rec, both | new_both, names=N)
    for pair in new_both:
        print("  keeping both: " + " + ".join(N[x] for x in sorted(pair)) + " (not asked again)")
    return 1


def run_redundant_undo(args):
    """--redundant-undo [NAME...]: turn back on what --redundant turned off (all of it, and forget the
    keep-both choices, with no name)."""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    off_rec, both = read_redundant(game_dir)
    want = {x.lower() for x in args.redundant_undo} if args.redundant_undo else {n.lower() for n in off_rec}
    todo = [n for n in off_rec if n.lower() in want]
    if not todo and not (not args.redundant_undo and both):
        print("--redundant-undo: nothing to undo. Turned off by --redundant: " + (", ".join(off_rec) or "none"))
        return 1
    if args.dry_run:
        print("--redundant-undo would turn back on: " + (", ".join(todo) or "nothing")
              + ("" if args.redundant_undo else f"; and forget {len(both)} keep-both choice(s)"))
        return 0
    if todo:
        lookup = index_dir(data_dir)
        cur = read_load_order(args) or []
        have = {c.lower() for c in cur} | merged_away(game_dir, data_dir)   # still inside a merge: stays there
        back = [lookup[n.lower()] for n in todo if n.lower() in lookup and n.lower() not in have]
        order = list(cur)
        for p in sort_vanilla(back):                # back where it loaded among the rest: by date, masters first
            name = os.path.basename(p)
            mt = os.path.getmtime(p)
            at = len(order)
            for i, c in enumerate(order):
                cp = lookup.get(c.lower())
                if cp and not c.lower().endswith(".esm") and not name.lower().endswith(".esm") \
                        and os.path.getmtime(cp) > mt:
                    at = i
                    break
            order.insert(at, name)
        backup = set_game_files(args.ini or os.path.join(game_dir, "Morrowind.ini"), order, "--redundant-undo")
        print(f"  Turned back on: {', '.join(todo)} (old list saved as {backup}). --sort puts them in their place.")
    for n in todo:
        del off_rec[n]
        fix_log_line(args, game_dir, f"--redundant-undo: turned {n} back on")
    pending = read_merge_rebuild(game_dir)
    if pending and todo:                     # a merge waiting to drop it no longer needs to
        low = {n.lower() for n in todo}
        pending = OrderedDict((k, [i for i in v if i.lower() not in low]) for k, v in pending.items())
        write_merge_rebuild(game_dir, OrderedDict((k, v) for k, v in pending.items() if v))
    if not args.redundant_undo and both:
        print(f"  Forgot {len(both)} keep-both choice(s).")
        both = set()
    write_redundant(game_dir, off_rec, both)
    return 0


def release_redundant(args):
    """A plugin --redundant turned off comes back on when the plugin kept in its place is gone (not in Data
    Files, or no longer active)."""
    if getattr(args, "plugins", None) or getattr(args, "openmw_cfg", None) or args.dry_run:
        return 0
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    off_rec, _both = read_redundant(game_dir)
    if not off_rec:
        return 0
    lookup = index_dir(data_dir)
    active = {n.lower() for n in (read_load_order(args) or [])} | merged_away(game_dir, data_dir)
    lost = [(n, k) for n, (k, _w) in off_rec.items() if n.lower() in lookup
            and (k.lower() not in lookup or k.lower() not in active)]
    if not lost:
        return 0
    print("\nPlugins --redundant turned off whose kept plugin is gone:")
    for n, k in lost:
        print(f"  {n}: turned off for {k}, which is gone; turning {n} back on")
    a2 = copy.copy(args)
    a2.redundant_undo = [n for n, _k in lost]
    a2.dry_run = False
    run_redundant_undo(a2)
    return len(lost)


def run_header(args):
    lookup = index_dir(args.data_dir)
    code = 0
    for want in args.header:
        path = lookup.get(want.lower())
        if not path:
            print(f"{want}: not found in Data Files")
            code = 1
            continue
        name = os.path.basename(path)
        with open(path, "rb") as f:
            head = f.read(DESC_OFF + DESC_LEN)
        if head[:4] != b"TES3" or head[16:20] != b"HEDR":
            print(f"{name}: not a Morrowind plugin")
            code = 1
            continue
        author = cstr(head[AUTH_OFF:AUTH_OFF + AUTH_LEN])
        desc = cstr(head[DESC_OFF:DESC_OFF + DESC_LEN])
        changes = {}
        for field, value, off, size in (("Author", args.set_author, AUTH_OFF, AUTH_LEN),
                                        ("Description", args.set_description, DESC_OFF, DESC_LEN)):
            if value is None:
                continue
            value = value.replace("\\n", "\r\n")
            new = ((author if field == "Author" else desc) + value[1:]) if value.startswith("+") else value
            raw = new.encode(ENC, MW_ERRORS)
            if len(raw) > size - 1:
                print(f"{name}: {field} is {len(raw)} bytes; only {size - 1} fit, so it was cut short")
                raw = raw[:size - 1]
            changes[off] = raw.ljust(size, b"\0")
        if not changes:
            print(f"{name}:\n  Author:      {author}\n  Description: " + desc.replace("\r\n", "\n               "))
            continue
        if not name.lower().endswith(FIXABLE_EXT):
            print(f"{name}: masters (.esm) are never changed")
            code = 1
            continue
        if args.dry_run:
            print(f"{name}: would set " + ", ".join("Author" if o == AUTH_OFF else "Description" for o in changes))
            continue
        st = os.stat(path)
        bak = backup_path(path)
        shutil.copy2(path, bak)
        with open(path, "r+b") as f:                 # in place: the header keeps its size
            for off, raw in changes.items():
                f.seek(off)
                f.write(raw)
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
        forget_cached(path)                          # same size and date: the read cache can't tell
        print(f"{name}: updated (backup {os.path.basename(bak)})")
    return code


# --------------------------------------------------------------------------
# Load order (mlox-style): masters first, then [Order]/[NearStart]/[NearEnd] rules; dates set to match
# --------------------------------------------------------------------------


DATE_BASE = 946684800                 # 2000-01-01 00:00 UTC: Morrowind.esm, then one day per plugin


DEFAULT_RULES = f"""; {RULES_FILE}: load order rules for mwdialog_check.py --sort
;
; The same format as mlox rules (mlox_user.txt / mlox_base.txt). Rules here win over mlox's own:
; files are read in this order, and a rule that contradicts an earlier one is skipped.
;
;   [Order]          each plugin listed loads before the next one
;   [NearStart]      these plugins load as early as their masters allow (in this order)
;   [NearEnd]        these plugins load as late as possible; the FIRST one listed loads LAST
;                    (mlox's convention, so the patch that must win goes first)
;   [Exact]          these plugins load one right after the other, in exactly this order, with
;                    nothing in between (exact names, no wildcards). Not applied, with a note, if
;                    masters make it impossible.
;
; One plugin per line; ";" starts a comment. Names are not case-sensitive and may use
; the wildcards * and ? and mlox's <VER> (a version number). A plugin always loads after its
; masters, and every .esm before every .esp, whatever the rules say.

[NearStart]
{PATCH_NAME}

[NearEnd]
{PERFORMER_PATCH}
{PLACE_PATCH_NAME}
{MULTI_PATCH_NAME}
"""


# Built-in rules, below your rules file (and the content rules) and above mlox's, so your file can override them.
# Major masters with a documented place in the order: Patch for Purists (the unofficial patch; its masters are
# the three Bethesda files) loads right after Bloodmoon.esm, before Tamriel_Data, OAAB_Data and other masters.
BUILTIN_RULES_NAME = "mwdialog_check (built-in)"
BUILTIN_RULES = """[NearStart]
Patch for Purists.esm
"""


def builtin_rules():
    return parse_rules(BUILTIN_RULES_NAME, BUILTIN_RULES)[0]


def compute_order(plugins, rule_sets, current_order):
    """Stable topological sort. Returns (new order, notes)."""
    names = [n for n, _p in plugins]
    low = {n.lower(): n for n in names}
    pos = {n: i for i, n in enumerate(current_order)}
    esp = {n: n.lower().endswith(FIXABLE_EXT) for n in names}
    succ = defaultdict(set)
    edge_src = {}                                # (a, b) -> what put a before b ("master" or a rule source)
    notes = {"missing_master": [], "cycles": [], "esm_after_esp": 0, "applied": 0, "rules": 0,
             "steps": {}}                        # (rule source, entry index) -> {"applied", "skipped"}

    def path_between(a, b):
        """The chain of edges by which b already follows a: [(x, y, source)], or []."""
        parent, stack = {a: None}, [a]
        while stack:
            x = stack.pop()
            if x == b:
                out = []
                while parent[x] is not None:
                    p = parent[x]
                    out.append((p, x, edge_src.get((p, x), "master")))
                    x = p
                return out[::-1]
            for y in succ[x]:
                if y not in parent:
                    parent[y] = x
                    stack.append(y)
        return []

    def reaches(a, b):
        """Is b reachable from a?"""
        stack, seen = [a], {a}
        while stack:
            x = stack.pop()
            if x == b:
                return True
            for y in succ[x]:
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        return False

    # hard: masters before the plugins using them
    for n, path in plugins:
        try:
            for m in read_header_masters(path):
                ml = m.lower()
                if ml not in low and ml.endswith(".omwaddon"):     # an OpenMW name for a plugin here as
                    for ext in (".esp", ".esm"):                    # .esp/.esm (--fix renames it in the header)
                        if ml[:-len(".omwaddon")] + ext in low:
                            ml = ml[:-len(".omwaddon")] + ext
                            break
                if ml in low:
                    succ[low[ml]].add(n)
                    edge_src[(low[ml], n)] = "master"
                else:
                    notes["missing_master"].append((n, m))
        except (OSError, FormatError):
            pass

    def expand(entry):
        rx = name_matcher(entry)
        if rx is None:
            return [low[entry.lower()]] if entry.lower() in low else []
        return [n for n in all_names if rx.match(n)]

    all_names = names
    # [Exact]: the listed plugins load one right after the other, in exactly that order. Each group is
    # sorted as a single block; names are taken literally (no wildcards).
    notes["exact"] = []                          # (source, members, problem or None)
    in_group, groups_ok = {}, []

    def reach_set(starts, edges):
        seen, stack = set(starts), list(starts)
        while stack:
            for y in edges[stack.pop()]:
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        return seen

    pred = defaultdict(set)
    for a in list(succ):
        for b in succ[a]:
            pred[b].add(a)
    for rules in rule_sets:
        for kind, entries, src in rules:
            if kind != "exact":
                continue
            members = [low[e.lower()] for e in entries if e.lower() in low]
            missing = [e for e in entries if e.lower() not in low]
            members = list(dict.fromkeys(members))
            problem = None
            if len(members) < 2:
                problem = "fewer than two of its plugins are active"
            elif any(m in in_group for m in members):
                problem = f"{next(m for m in members if m in in_group)} is already in another [Exact] group"
            elif len({esp[m] for m in members}) > 1:
                problem = "it mixes .esm and .esp files, which can't load side by side"
            else:
                idx = {m: i for i, m in enumerate(members)}
                for m in members:
                    for s in succ[m]:
                        if s in idx and idx[s] < idx[m]:
                            problem = f"{m} is a master of {s}, so it can't load after it"
                if problem is None:
                    gset = set(members)
                    down = reach_set([s for m in members for s in succ[m] if s not in gset], succ)
                    up = reach_set([p for m in members for p in pred[m] if p not in gset], pred)
                    between = (down & up) - gset
                    if between:
                        problem = (f"{sorted(between)[0]} must load between two of them (masters)")
            notes["exact"].append((src, members, problem, missing))
            if problem is None:
                for m in members:
                    in_group[m] = members[0]
                groups_ok.append(members)

    if groups_ok:                                # contract each group to its first member
        rep_of = lambda n: in_group.get(n, n)
        new_succ = defaultdict(set)
        for a in list(succ):
            for b in succ[a]:
                ra, rb = rep_of(a), rep_of(b)
                if ra != rb:
                    new_succ[ra].add(rb)
                    edge_src.setdefault((ra, rb), edge_src.get((a, b), "master"))
        succ.clear()
        succ.update(new_succ)
        members_of = {g[0]: g for g in groups_ok}
        for g in groups_ok:
            pos[g[0]] = min(pos.get(m, 0) for m in g)
        all_names = names
        names = [n for n in names if rep_of(n) == n]
    else:
        rep_of = lambda n: n
        members_of = {}
        all_names = names

    near_start, near_end = {}, {}
    for rules in rule_sets:                      # highest priority first
        for kind, entries, src in rules:
            notes["rules"] += 1
            if kind == "exact":
                continue
            egroups = [(ei, list(dict.fromkeys(rep_of(n) for n in g)))
                       for ei, g in enumerate(expand(e) for e in entries) if g]
            groups = [g for _ei, g in egroups]
            if kind == "nearstart":
                for g in groups:
                    for n in g:
                        near_start.setdefault(n, len(near_start))
                continue
            if kind == "nearend":
                for g in groups:
                    for n in g:
                        near_end.setdefault(n, len(near_end))
                continue
            for (_ea, a_grp), (eb, b_grp) in zip(egroups, egroups[1:]):
                step = notes["steps"].setdefault((src, eb), {"applied": 0, "skipped": [], "entries": entries})
                for a in a_grp:
                    for b in b_grp:
                        if a == b:
                            continue
                        if b in succ[a]:
                            continue                            # already so from elsewhere: changes nothing
                        if esp[a] and not esp[b]:
                            notes["esm_after_esp"] += 1       # an .esp can never load before an .esm
                            step["skipped"].append((a, b, "esm"))
                            continue
                        if reaches(b, a):
                            notes["cycles"].append((a, b, src))
                            step["skipped"].append((a, b, path_between(b, a)))
                            continue
                        succ[a].add(b)
                        edge_src[(a, b)] = src
                        step["applied"] += 1
                        notes["applied"] += 1

    indeg = Counter()
    for a in list(succ):
        for b in succ[a]:
            indeg[b] += 1
    import heapq

    def key(n):
        band = 0 if n in near_start else 2 if n in near_end else 1
        # mlox: in [NearStart] the first listed loads first; in [NearEnd] the first listed loads LAST
        rank = near_start.get(n, 0) if band == 0 else -near_end.get(n, 0) if band == 2 else pos.get(n, 0)
        return (esp[n], band, rank, n.lower())

    ready = [(key(n), n) for n in names if indeg[n] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        _k, n = heapq.heappop(ready)
        order.append(n)
        for b in succ[n]:
            indeg[b] -= 1
            if indeg[b] == 0:
                heapq.heappush(ready, (key(b), b))
    if len(order) != len(names):                 # a cycle among masters themselves: keep the rest as is
        left = [n for n in current_order if n not in set(order) and rep_of(n) == n]
        order += left
        notes["cycles"].append(("(masters)", ", ".join(left[:3]), "plugin headers"))
    order = [m for n in order for m in members_of.get(n, [n])]

    def outside_groups(i):
        """An insertion point that doesn't split an [Exact] group: inside one, move to its start."""
        for g in groups_ok:
            if g[0] in order and g[-1] in order:
                s = order.index(g[0])
                if s < i < s + len(g):
                    return s
        return i

    # Hard rule: the ESM fixes patch is always the first .esp (it only patches masters, and the
    # objects it defines early must exist before any .esp loads).
    pin = low.get(PATCH_NAME.lower())
    if pin in order:
        try:
            ok = all(m.lower().endswith(".esm") for m in read_header_masters(dict(plugins)[pin]))
        except (OSError, FormatError):
            ok = True
        if ok:
            order.remove(pin)
            first_esp = next((i for i, n in enumerate(order) if esp.get(n, n.lower().endswith(".esp"))), len(order))
            order.insert(outside_groups(first_esp), pin)
        else:
            notes.setdefault("pin_failed", True)
    # Hard rule: plugins in the conflict blacklist always lose: each loads as early as its masters allow
    # (an .esm among the .esm files, an .esp right after them / the ESM fixes patch)
    try:
        black = read_conflict_blacklist(os.path.dirname(os.path.dirname(os.path.abspath(plugins[0][1]))), create=False)
    except (IndexError, OSError):
        black = []
    if black:
        paths_ = dict(plugins)
        for n in [x for x in order if conflict_blacklisted(x, black)]:
            try:
                ms = {m.lower() for m in read_header_masters(paths_[n])}
            except (OSError, FormatError, KeyError):
                continue
            order.remove(n)
            is_esp = esp.get(n, n.lower().endswith(".esp"))
            at = 0
            for i, x in enumerate(order):
                if x.lower() in ms or (is_esp and (not esp.get(x, x.lower().endswith(".esp")) or x == pin)):
                    at = i + 1                       # after every master (and, for an .esp, every .esm)
            order.insert(outside_groups(at), n)
            notes.setdefault("always_lose", []).append(n)
    # Hard rule: this tool's end patches load last, whatever the rules say: the auto-merge, the performers
    # patch (its deletions then win over every other plugin's edits of those inns), the placeholder patch,
    # then the Multipatch (which must see, and win over, every plugin). One that is in an [Exact] group
    # takes its whole group with it.
    tail = []
    # every auto-merge (the default one and any made with --merge-name), in the order they were made: each
    # was checked against a load order with it at the end
    try:
        merges = list(read_merge_record(os.path.dirname(os.path.dirname(os.path.abspath(plugins[0][1])))))
    except (IndexError, OSError):
        merges = []
    if AUTO_MERGE_NAME not in merges:
        merges.insert(0, AUTO_MERGE_NAME)
    for want in merges + [PERFORMER_PATCH, CELL_WINNER_PATCH, PLACE_PATCH_NAME, MULTI_PATCH_NAME]:
        n = low.get(want.lower())
        if n not in order or n in tail:
            continue
        grp = next((g for g in groups_ok if n in g), [n])
        tail += [m for m in grp if m in order and m not in tail]
    if tail:
        order = [n for n in order if n not in tail] + tail
    for g in groups_ok:                          # last check: every applied group is still one block
        idx = [order.index(m) for m in g if m in order]
        if idx != list(range(idx[0], idx[0] + len(idx))) if idx else False:
            notes.setdefault("exact_split", []).append(g)
    return order, notes


CONTENT_SKIP_TAGS = {"TES3", "DIAL", "CELL", "LAND", "PGRD", "GMST", "SKIL", "MGEF"}


def drop_vanished_added_masters(args):
    """A master a sort added (a promoted content rule) whose plugin is gone from Data Files or from the load
    order: taken back out of the patch's header, so the patch still loads (it never needed that master
    for its records). Runs first thing, before anything checks for missing masters."""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    rec = read_added_masters(game_dir)
    if not rec:
        return
    present = {fn.lower(): os.path.join(data_dir, fn) for fn in os.listdir(data_dir)}
    active = {n.lower() for n in (read_load_order(args) or [])}
    changed = False
    for patch, mods in list(rec.items()):
        ppath = present.get(patch.lower())
        if not ppath:
            continue                                  # the patch itself is gone: nothing to fix
        for mod in list(mods or {}):
            gone = mod.lower() not in present
            off = bool(active) and mod.lower() not in active and patch.lower() in active
            if not (gone or off):
                continue
            try:
                bak = remove_master(ppath, mod)
                del mods[mod]
                changed = True
                why = "is no longer in Data Files" if gone else "is no longer in the load order"
                print(f"  {patch}: master {mod} (added by a sort from a content rule) taken out again: {mod} {why}"
                      + (f" (backup {os.path.basename(bak)})" if bak else ""))
                try:
                    with MT.open_log(os.path.join(game_dir, getattr(args, "fix_log", "") or "mwdialog_fixes.log"), "a",
                              encoding="utf-8") as lf:
                        lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {patch}: added master {mod} removed ({why})\n")
                except OSError:
                    pass
            except (OSError, FormatError) as e:
                print(f"  {patch}: could not take out master {mod} ({e})")
    if changed:
        write_added_masters(game_dir, rec)


def rule_puts_before(rules, first, second):
    """True when an order rule (of `rules`) puts `first` before `second` (wildcards allowed)."""
    import fnmatch as _fn
    a, b = first.lower(), second.lower()
    for kind, names, _src in rules:
        if kind != "order":
            continue
        ia = next((i for i, n in enumerate(names) if _fn.fnmatch(a, str(n).lower())), None)
        ib = next((i for i, n in enumerate(names) if _fn.fnmatch(b, str(n).lower())), None)
        if ia is not None and ib is not None and ia < ib:
            return True
    return False


def content_rules(plugins):
    """Patches load after the mod they patch, judged by content: when most of the records an .esp
    changes (leaving out anything a master .esm defines) are records another, much bigger .esp adds,
    the smaller one is a patch for the bigger one and must load after it. Returns rules in the [Order] form: [("order", [mod, patch], why)]."""
    owners = defaultdict(list)                 # record id -> [plugin index]
    counts = []
    ours = {x.lower() for x in OUR_PATCHES} | {AUTO_MERGE_NAME.lower()} | {
        k.lower() for k in read_merge_record(os.path.dirname(os.path.dirname(os.path.abspath(plugins[0][1]))))
    } if plugins else set()
    esps = [(n, p) for n, p in plugins if n.lower().endswith(".esp") and n.lower() not in ours]
    # Records a master (.esm) defines are overridden by many unrelated mods (two NPC replacers both
    # change vanilla NPCs); only records an .esp itself adds say "this one patches that one".
    esm_ids = set()
    for n, p in plugins:
        if n.lower().endswith(".esm"):
            try:
                with open(p, "rb") as f:
                    data = f.read()
                for off, tag, flags, body in iter_records(data):
                    if tag not in CONTENT_SKIP_TAGS:
                        rid = record_id(tag, body)
                        if rid is not None:
                            esm_ids.add(rid)
            except (OSError, FormatError):
                pass
    for i, (n, p) in enumerate(esps):
        ids = set()
        try:
            with open(p, "rb") as f:
                data = f.read()
            for off, tag, flags, body in iter_records(data):
                if tag in CONTENT_SKIP_TAGS:
                    continue
                rid = record_id(tag, body)
                if rid is not None and rid not in esm_ids:
                    ids.add(rid)
        except (OSError, FormatError):
            pass
        counts.append(len(ids))
        for rid in ids:
            owners[rid].append(i)
    shared = Counter()
    for rid, who in owners.items():
        if 1 < len(who) <= 6:                  # records many plugins touch say nothing about pairs
            for a in who:
                for b in who:
                    if a != b:
                        shared[(a, b)] += 1
    rules = []
    masters = {}
    for a_b, k in shared.items():
        x, y = a_b                            # x shares k records with y
        if counts[x] and k >= max(1, 0.5 * counts[x]) and k < 0.5 * counts[y] and counts[y] > 2 * counts[x]:
            xn, yn = esps[x][0], esps[y][0]
            if xn not in masters:
                try:
                    masters[xn] = {m.lower() for m in read_header_masters(esps[x][1])}
                except (OSError, FormatError):
                    masters[xn] = set()
            if yn.lower() in masters[xn]:
                continue                       # already a master: the hard rule covers it
            rules.append(("order", [yn, xn], f"content: {k} of {xn}'s {counts[x]} records are {yn}'s"))
    return rules


CONTEXT_BEGIN = "[Context]"
CONTEXT_END = "; ---- end of [Context] ----"


def write_context_rules(rules_path, crules, skipped):
    """Put the content rules --sort found at the top of the rules file as a [Context] section.
    Every line is a comment, so the section is only for reading; it is rewritten on every --sort."""
    import datetime
    try:
        with open(rules_path, "r", encoding="cp1252", errors="replace") as f:
            text = f.read()
    except OSError:
        return False
    lines = text.splitlines()
    if lines and lines[0].strip().lower() == CONTEXT_BEGIN.lower():   # drop the old section
        end = next((i for i, l in enumerate(lines) if l.strip() == CONTEXT_END), None)
        if end is not None:
            lines = lines[end + 1:]
            while lines and not lines[0].strip():
                lines = lines[1:]
    by_patch = defaultdict(list)
    for _kind, (mod, patch), why in crules:
        by_patch[patch].append((mod, why))
    block = [CONTEXT_BEGIN,
             f"; Written by --sort on {datetime.datetime.now():%Y-%m-%d %H:%M}. For reading only: every line here is",
             "; a comment, and --sort rewrites this section each time. Edit the rules below it instead.",
             ";",
             "; These are the patch-after-mod rules --sort works out from what the plugins change: when most of",
             "; the records a small .esp changes are records a much bigger .esp adds (not counting anything an",
             "; .esm defines), the small one is a patch for the big one and loads after it.",
             "; They rank below the rules in this file and above mlox's. To override one, add an [Order] rule",
             "; below; to turn them all off, use --no-content-order.",
             ";",
             f"; {len(crules)} rule(s) found" + (f", {len(skipped)} skipped because an earlier rule or a master says otherwise"
                                                 if skipped else "") + ":",
             ";"]
    for patch in sorted(by_patch, key=str.lower):
        for mod, why in sorted(by_patch[patch], key=lambda t: t[0].lower()):
            n = why.split(":", 1)[1].strip().split(" ", 1)[0] if ":" in why else "?"
            total = re.search(r"'s (\d+) records", why)
            mark = "   (SKIPPED)" if (mod.lower(), patch.lower()) in skipped else ""
            block.append(f";   {mod}")
            block.append(f";     -> {patch}   [{n} of its {total.group(1) if total else '?'} records are the mod's]{mark}")
    if not crules:
        block.append(";   (none)")
    block += [CONTEXT_END, ""]
    new = "\r\n".join(block + lines) + "\r\n"
    if new.replace("\r\n", "\n").split("\n", 2)[2:] == text.replace("\r\n", "\n").split("\n", 2)[2:]:
        return False                            # same rules (only the date line would change)
    with open(rules_path, "w", encoding="cp1252", errors="replace", newline="") as f:
        f.write(new)
    return True


def sync_ini_order(args, order):
    """Morrowind loads by file date; the [Game Files] list order is only cosmetic. Rewrite it to match
    the load order --sort set, so the ini reads the way the game loads (same plugins, new order)."""
    if getattr(args, "plugins", None) or getattr(args, "openmw_cfg", None) or args.dry_run:
        return
    ini = default_ini(args)
    cur = read_load_order(args)
    if cur is None:
        return
    if [n.lower() for n in cur] == [n.lower() for n in order]:
        return
    if sorted(n.lower() for n in cur) != sorted(n.lower() for n in order):
        return                                   # different plugins: leave that to --add-all-esp
    by_low = {n.lower(): n for n in cur}         # keep the spelling the ini uses
    backup = set_game_files(ini, [by_low[n.lower()] for n in order], "")
    print(f"  {LOAD_ORDER_FILE} rewritten in the new load order (old list saved as {backup}).")


def sort_rule_sources(args, plugins, quiet=False):
    """The rule sets --sort uses, highest priority first: your rules file, the content rules, the built-in
    rules (BUILTIN_RULES), then mlox_user.txt and mlox_base.txt. Returns (rule_sets, {file basename: path})."""
    game_dir = os.path.dirname(os.path.abspath(args.data_dir))
    rules_path = os.path.join(game_dir, RULES_FILE)
    sources = [rules_path]
    if not getattr(args, "no_mlox_rules", False):
        sources += [os.path.join(game_dir, "mlox", "mlox_user.txt"), os.path.join(game_dir, "mlox", "mlox_base.txt")]
    rule_sets, files = [], {}
    for s in sources:
        if os.path.exists(s):
            rule_sets.append(parse_rules(s)[0])
            files[os.path.basename(s)] = s
        elif s == rules_path:
            rule_sets.append(parse_rules(s, DEFAULT_RULES)[0])
        else:
            rule_sets.append([])
    rule_sets.insert(1, builtin_rules())
    if not getattr(args, "no_content_order", False):
        if not quiet:
            print("  Reading plugins to find patches that must follow the mods they change...", file=sys.stderr)
        rule_sets.insert(1, content_rules(plugins))
    return rule_sets, files


def describe_edge(x, y, why):
    if why == "master":
        return f"{y} has {x} as a master"
    if str(why).startswith("content:"):
        return f"context: {y} patches {x} ({why[8:].strip()})"
    f = str(why)
    if f.lower().startswith(RULES_FILE.lower()):
        return f"your rule at {f} ({x} before {y})"
    return f"mlox rule at {f} ({x} before {y})"


def run_update_rules(args):
    """--update-rules: remove the mlox rules the sort skips because something stronger says otherwise
    (a master, [Exact], your own rules file, a context rule, an earlier mlox rule) or because they put
    an .esp before an .esm. Only the contradicting step of an [Order] rule goes; the rest of the rule
    stays. Your own rules file is never edited: its contradictions are listed to fix by hand."""
    print("\n" + "=" * 70 + "\nUPDATE RULES\n" + "=" * 70)
    report = Report()
    plugins = resolve(args, report)[0]
    if not plugins:
        print("No plugins found.")
        return 2
    rule_sets, files = sort_rule_sources(args, plugins)
    _order, notes = compute_order(plugins, rule_sets, [n for n, _p in plugins])
    cuts = defaultdict(lambda: defaultdict(list))        # file -> tag line -> [(entry index, reasons)]
    by_hand, partial = [], []
    for (src, eb), st in notes["steps"].items():
        if not st["skipped"]:
            continue
        fname, _, line = str(src).rpartition(":")
        reasons = []
        for a, b, why in st["skipped"]:
            if why == "esm":
                reasons.append(f"{a} before {b}: puts an .esp before an .esm, which the game never does")
            else:
                if len(why) <= 3:
                    chain = "; ".join(describe_edge(x, y, w) for x, y, w in why) or "an earlier rule"
                else:                                    # long chains: where it starts and which rules make it
                    srcs = list(dict.fromkeys("masters" if w == "master" else "context rules"
                                              if str(w).startswith("content:") else str(w) for _x, _y, w in why))
                    chain = (f"a chain of {len(why)} rules putting {b} before {a} "
                             f"({why[0][0]} > ... > {why[-1][1]}), from {', '.join(srcs)}")
                reasons.append(f"{a} before {b}: contradicts {chain}")
        if fname.lower() == RULES_FILE.lower():
            by_hand.append((src, reasons))
        elif st["applied"]:
            partial.append((src, st["entries"][eb], reasons))
        elif fname in files and line.isdigit():
            cuts[fname][int(line)].append((eb, st["entries"], reasons))
    if not cuts and not by_hand and not partial:
        print("  No rule is contradicted: nothing to remove.")
        return 0
    for fname in sorted(cuts):
        print(f"\n  {fname}: {sum(len(v) for v in cuts[fname].values())} contradicting step(s) to remove")
        for tag_line in sorted(cuts[fname]):
            for eb, entries, reasons in cuts[fname][tag_line]:
                prev = next((entries[i] for i in range(eb - 1, -1, -1)), "?")
                print(f"    line {tag_line}: [Order] ... {prev}  >  {entries[eb]} ...")
                for r in reasons[:3]:
                    print(f"        {r}")
                if len(reasons) > 3:
                    print(f"        ... and {len(reasons) - 3} more pair(s)")
    if partial:
        print(f"\n  Left alone ({len(partial)}): wildcard steps that partly apply; removing them would change the order")
        for src, entry, reasons in partial[:10]:
            print(f"    {src} at '{entry}': {reasons[0]}")
    if by_hand:
        print(f"\n  Your own {RULES_FILE} contradicts itself or a master ({len(by_hand)}); not edited, fix by hand:")
        for src, reasons in by_hand:
            print(f"    {src}: {reasons[0]}")
    if args.dry_run:
        print("\n  Dry run: no rule files changed.")
        return 0
    if not cuts:
        return 0
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for fname, rules in cuts.items():
        path = files[fname]
        raw = open(path, "rb").read()
        lines = raw.decode("latin-1").splitlines(keepends=True)
        nl = "\r\n" if raw.count(b"\r\n") * 2 > raw.count(b"\n") else "\n"
        for tag_line in sorted(rules, reverse=True):     # bottom up: insertions don't shift earlier rules
            idxs = rule_entry_lines(lines, tag_line)
            cut_at = {eb for eb, _e, _r in rules[tag_line]}
            segs, cur = [], []
            for k, li in enumerate(idxs):
                if k in cut_at and cur:
                    segs.append(cur)
                    cur = []
                cur.append(li)
            segs.append(cur)
            why = "; ".join(r for _eb, _e, rs in rules[tag_line] for r in rs[:1])
            for si in range(len(segs) - 1, -1, -1):
                seg = segs[si]
                if len(seg) < 2:                         # one plugin alone orders nothing
                    lines[seg[0]] = "; " + lines[seg[0]]
                elif si > 0:
                    lines.insert(seg[0], "[Order]" + nl)
            if all(len(s) < 2 for s in segs):
                lines[tag_line - 1] = "; " + lines[tag_line - 1]
            lines.insert(tag_line - 1, f";; mwdialog_check --update-rules {stamp}: {why}"[:400] + nl)
        backup = f"{bak_home(path)}.mwdialog-{stamp}.bak"
        with open(backup, "wb") as f:
            f.write(raw)
        safe_write_bytes(path, "".join(lines).encode("latin-1"))
        print(f"\n  {fname}: {sum(len(v) for v in rules.values())} step(s) removed (old file saved as {os.path.basename(backup)}).")
    print("  The sort's result is unchanged: these rules were already being skipped.")
    return 0


def run_sort(args, plugins):
    """--sort: compute the load order and set file dates to match (one day apart from 2000-01-01)."""
    print("\n" + "=" * 70 + "\nLOAD ORDER\n" + "=" * 70)
    game_dir = os.path.dirname(os.path.abspath(args.data_dir))
    rules_path = os.path.join(game_dir, RULES_FILE)
    if not os.path.exists(rules_path) and not args.dry_run:
        with open(rules_path, "w", encoding="cp1252", newline="\r\n") as f:
            f.write(DEFAULT_RULES)
        print(f"  Created {RULES_FILE} with the default rules (edit it to add your own).")
    sources = [rules_path]
    if not args.no_mlox_rules:
        sources += [os.path.join(game_dir, "mlox", "mlox_user.txt"), os.path.join(game_dir, "mlox", "mlox_base.txt")]
    rule_sets, ignored = [], Counter()
    BAD_RULE_ENTRIES.clear()
    for src in sources:
        if os.path.exists(src):
            rules, ign = parse_rules(src)
        elif src == rules_path:                  # dry run before the file exists: use the defaults
            rules, ign = parse_rules(src, DEFAULT_RULES)
        else:
            rules, ign = [], Counter()
        if rules or ign:
            print(f"  {os.path.relpath(src, game_dir)}: {len(rules)} order rule(s)"
                  + (f", {sum(ign.values())} other rule(s) ignored" if ign else ""))
        rule_sets.append(rules)
        ignored += ign
    rule_sets.insert(1, builtin_rules())         # after your rules file, before mlox's
    mine = [b for b in BAD_RULE_ENTRIES if os.path.normcase(b[0]) == os.path.normcase(rules_path)]
    for src, no, entry in BAD_RULE_ENTRIES:
        if (src, no, entry) not in mine:
            print(f"  WARN {os.path.relpath(src, game_dir)} line {no}: '{entry}' isn't a plugin (.esp/.esm); "
                  f"left out of that rule")
    if mine:
        print(f"\n  ERROR {RULES_FILE}: {len(mine)} rule entr{'y is' if len(mine) == 1 else 'ies are'} not a plugin "
              f"(every entry must be an .esp or .esm name, or a wildcard ending in * that can match one):")
        for _src, no, entry in mine:
            print(f"    line {no}: {entry}")
        print(f"  Fix {RULES_FILE} and sort again; nothing was changed.")
        return 2
    added_rec = read_added_masters(game_dir)
    if added_rec and not args.dry_run:
        # a master this tool added, and your own rule now wants the patch BEFORE that mod: take it out again
        paths0 = dict(plugins)
        for patch, mods in list(added_rec.items()):
            for mod in list(mods):
                if patch in paths0 and rule_puts_before(rule_sets[0], patch, mod):
                    try:
                        bak = remove_master(paths0[patch], mod)
                        del mods[mod]
                        print(f"  {patch}: master {mod} (added by an earlier sort) taken out again, because "
                              f"{RULES_FILE} puts {patch} first" + (f" (backup {os.path.basename(bak)})" if bak else ""))
                    except (OSError, FormatError) as e:
                        print(f"  {patch}: could not take out master {mod} ({e}); your rule can't apply")
        write_added_masters(game_dir, added_rec)
    if not args.no_content_order:
        print("  Reading plugins to find patches that must follow the mods they change...", file=sys.stderr)
        crules = content_rules(plugins)
        rule_sets.insert(1, crules)            # after your rules file, before mlox's
        print(f"  content: {len(crules)} patch-after-mod rule(s) found from what the plugins change")
    current = [n for n, _p in plugins]
    order, notes = compute_order(plugins, rule_sets, current)
    if not args.no_content_order and not args.dry_run and os.path.exists(rules_path):
        skipped = {(a.lower(), b.lower()) for a, b, s in notes["cycles"] if str(s).startswith("content:")}
        if write_context_rules(rules_path, crules, skipped):
            print(f"  Listed the {len(crules)} content rule(s) in a [Context] section at the top of {RULES_FILE}.")
    if not args.no_content_order and not getattr(args, "no_add_masters", False):
        # A patch that changes another mod's records without listing it as a master: make it a real master
        # (then the order is a hard rule and the [Context] line goes away on the next sort). .esp only.
        paths_ = dict(plugins)
        pos_ = {n.lower(): i for i, n in enumerate(order)}
        skipped = {(a.lower(), b.lower()) for a, b, s in notes["cycles"] if str(s).startswith("content:")}
        merged = {k.lower() for k in read_merge_record(os.path.dirname(os.path.abspath(args.data_dir)))}
        added = []
        for _k, (mod, patch), why in crules:
            if (mod.lower(), patch.lower()) in skipped or not patch.lower().endswith(FIXABLE_EXT) \
                    or is_our_patch(patch) or patch.lower() in merged or patch.lower() in NOT_A_MOD \
                    or pos_.get(mod.lower(), 10 ** 9) > pos_.get(patch.lower(), -1):
                continue
            if rule_puts_before(rule_sets[0], patch, mod):
                continue                         # your rules want the patch first: no master
            if args.dry_run:
                added.append((patch, mod, None, why))
                continue
            try:
                arch = backup_asset_original(os.path.abspath(args.data_dir), patch, plugin=patch, feature="added masters",
                                             track_new=False)
                bak = add_master(paths_[patch], mod, paths_[mod])
            except (OSError, FormatError, KeyError) as e:
                print(f"  {patch}: could not add master {mod} ({e})")
                continue
            if bak:
                added.append((patch, mod, bak, why))
                added_rec.setdefault(patch, {})[mod] = (time.strftime("%Y-%m-%d %H:%M:%S") + f"; original: {arch}"
                                                        + f"; why: {why}")
        if added:
            print(f"\n  {len(added)} patch(es) now list the mod they change as a master"
                  + (" (dry run: not written)" if args.dry_run else "") + ":")
            for patch, mod, bak, why in added[:15]:
                print(f"    {patch}  +master  {mod}   ({why})")
            if len(added) > 15:
                print(f"    ... and {len(added) - 15} more")
            if not args.dry_run:
                write_added_masters(os.path.dirname(os.path.abspath(args.data_dir)), added_rec)
                with MT.open_log(args.fix_log, "a", encoding="utf-8") as lf:
                    for patch, mod, bak, why in added:
                        lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {patch}: added master {mod} ({why}); "
                                 f"backup {os.path.basename(bak)}\n")

    for n, m in notes["missing_master"]:
        print(f"  WARNING: {n} needs master '{m}', which is not active")
    for src, members, problem, missing in notes.get("exact", []):
        if problem:
            print(f"  [Exact] at {src} NOT applied: {problem}")
        else:
            print(f"  [Exact] at {src}: {len(members)} plugins kept together in that order")
    for g in notes.get("exact_split", []):
        print(f"  WARNING: [Exact] group starting {g[0]} came apart; please report this (the rest of the sort is fine)")
        if missing:
            print(f"      not active (left out of the group): {', '.join(missing)}")
    if notes["cycles"]:
        print(f"  {len(notes['cycles'])} rule(s) skipped because they contradict an earlier rule or a master:")
        for a, b, src in notes["cycles"][:10]:
            print(f"    {a}  before  {b}   ({src})")
        if len(notes["cycles"]) > 10:
            print(f"    ... and {len(notes['cycles']) - 10} more")
    if notes.get("always_lose"):
        print(f"  {len(notes['always_lose'])} plugin(s) from {CONFLICT_BLACKLIST_FILE} load as early as their masters "
              f"allow (they always lose): " + ", ".join(notes["always_lose"]))
    if notes["esm_after_esp"]:
        print(f"  {notes['esm_after_esp']} rule(s) skipped: they put an .esp before an .esm, which the game never does")

    paths = dict(plugins)
    want = {n: DATE_BASE + 86400 * i for i, n in enumerate(order)}
    changes = [(n, paths[n]) for n in order if int(os.path.getmtime(paths[n])) != want[n]]
    moved = [(current.index(n), i, n) for i, n in enumerate(order) if current.index(n) != i]
    print(f"\n  {len(order)} active plugins; {len(moved)} change position, {len(changes)} need a new date")
    shown = [(a, b, n) for a, b, n in moved if abs(a - b) > 1 or len(moved) <= 40]
    for a, b, n in shown[:60]:
        print(f"    {a + 1:>4} -> {b + 1:<4} {n}")
    if len(shown) > 60:
        print(f"    ... and {len(shown) - 60} more")
    if not changes:
        print("  Load order already matches; nothing to change.")
        sync_ini_order(args, order)
        return
    if args.dry_run:
        print("Dry run: no dates were changed.")
        return
    if not args.yes:
        if not sys.stdin.isatty() or input(f"\nSet new dates on {len(changes)} plugin(s)? The old dates are "
                                           f"saved for --restore-dates. [y/N] ").strip().lower() not in ("y", "yes"):
            print("No dates changed.")
            return
    import datetime
    undo = os.path.join(game_dir, DATES_UNDO_FILE)
    with open(undo, "a", encoding="utf-8") as f:
        f.write(f"==== {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
        for n, p in changes:
            st = os.stat(p)
            f.write(f"{n}\t{st.st_atime_ns}\t{st.st_mtime_ns}\n")
    for n, p in changes:
        os.utime(p, (want[n], want[n]))         # hard links share the date, so Vortex's copy follows
    print(f"  Dates set on {len(changes)} plugin(s). Old dates saved in {DATES_UNDO_FILE} "
          f"(undo with --restore-dates).")
    sync_ini_order(args, order)
    # only a different order calls for --fix and --multipatch again; new dates on the same order don't
    args.sort_changed = bool(moved)
    if not moved:
        print("  The order itself is the same (only dates changed), so --fix and --multipatch aren't needed.")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def full_reset(args, game_dir):
    """--full starts from scratch: undo what earlier runs decided, so this run decides it all again.
    (Restored .bak copies are not part of it: plugins --fix repaired stay repaired.)
      - plugins turned off (doubled by --fix, or by --cell-conflicts) are turned back on
      - the [Order] rules --cell-conflicts added are taken out of the rules file
      - the stand-in files the asset check made are removed (the asset check makes what's still needed)
    (Our generated patches need nothing: --fix and --multipatch always rebuild them from scratch.)
    The auto-merge is undone as the step before this one."""
    rec = read_disabled(game_dir)
    rules_path = os.path.join(game_dir, RULES_FILE)
    text = open(rules_path, encoding="cp1252", errors="replace").read() if os.path.exists(rules_path) else ""
    own_text, earlier = split_conflict_rules(text)
    gen_path = os.path.join(game_dir, GENERATED_RECORD)
    has_gen = os.path.exists(gen_path) and any(l.strip() and not l.startswith(";")
                                                 for l in open(gen_path, encoding="utf-8", errors="replace"))
    print(f"  plugins turned off by earlier runs, back on: {', '.join(rec) or 'none'}")
    print(f"  [Order] rules from earlier --cell-conflicts runs removed: {len(earlier)}")
    print(f"  stand-in files from earlier asset checks removed: {'yes' if has_gen else 'none recorded'}")
    print(f"  rebuilt-interior choices from earlier --cell-conflicts runs removed: {len(read_cell_winners(game_dir))}")
    if args.dry_run:
        print("  (dry run: nothing changed)")
        return 0
    if rec:
        main([args.data_dir, "--reenable"] + (["--ini", args.ini] if args.ini else []))
    if earlier:
        shutil.copy2(rules_path, backup_path(rules_path))
        with open(rules_path, "w", encoding="cp1252", errors="replace", newline="\r\n") as f:
            f.write(own_text)
    if has_gen:
        main([args.data_dir, "--remove-generated"])
    if read_cell_winners(game_dir) and not getattr(args, "use_answers", False):
        write_cell_winners(game_dir, {})     # --use-answers keeps them: the rebuilt-place choices stand
    return 0


def full_missing_masters(args, game_dir):
    """Masters that aren't in Data Files at all, for every plugin in the load order and every plugin an
    auto-merge took in (not this tool's own patches, which --full rebuilds). [(plugin, master)]. A master
    named X.omwaddon counts as there when X.esp is."""
    lookup = index_dir(os.path.abspath(args.data_dir))
    names = list(read_load_order(args) or [])
    for inputs in read_merge_record(game_dir).values():
        names += inputs
    # this tool's own patches are rebuilt by --full against what's there now: their masters don't count here
    # (--sort and --play still check them)
    ours = {x.lower() for x in OUR_PATCHES} | {CELL_WINNER_PATCH.lower(), PERFORMER_PATCH.lower(),
                                                AUTO_MERGE_NAME.lower()} | {k.lower() for k in read_merge_record(game_dir)}
    missing, seen = [], set(ours)
    for n in names:
        if n.lower() in seen:
            continue
        seen.add(n.lower())
        path = lookup.get(n.lower())
        if not path:
            continue
        try:
            masters = read_header_masters(path)
        except (OSError, FormatError):
            continue
        for mname in masters:
            ml = mname.lower()
            if ml in lookup:
                continue
            if ml.endswith(".omwaddon") and any(ml[:-9] + e in lookup for e in (".esp", ".esm")):
                continue
            missing.append((n, mname))
    return missing


def full_check(args, game_dir, stage):
    """The plain scan, like double-clicking the batch file: report to mwdialog_report.txt. If it has any
    ERROR, open it and say so. Returns the number of errors."""
    report_path = os.path.join(game_dir, "mwdialog_report.txt")
    print(f"\n--full: checking for errors after {stage} (report: mwdialog_report.txt)...")
    import contextlib
    with open(report_path, "w", encoding="utf-8", errors="replace") as f, contextlib.redirect_stdout(f):
        main([args.data_dir] + (["--ini", args.ini] if args.ini else []))
    errors = 0
    with open(report_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.lstrip().startswith("ERROR"):
                errors += 1
    if errors:
        print(f"--full: {errors} error(s) left after {stage}; stopping here so nothing builds on them.")
        try:
            subprocess.Popen(["notepad", report_path])
        except OSError:
            print(f"Open {report_path} to see them.")
    else:
        print("--full: no errors.")
    return errors


IN_FULL = False


def multipatch_aside(args, game_dir):
    """--full: take the Multipatch out of the load order (the file stays) until it is rebuilt after the
    auto-merge, so the unmerged checks don't see a stale one."""
    cur = read_load_order(args) or []
    if MULTI_PATCH_NAME.lower() not in {n.lower() for n in cur}:
        print(f"  {MULTI_PATCH_NAME} isn't in the load order; nothing to set aside.")
        return 0
    if args.dry_run:
        print(f"  Dry run: {MULTI_PATCH_NAME} would be taken out of the load order until it is rebuilt.")
        return 0
    set_game_files(args.ini or os.path.join(game_dir, "Morrowind.ini"),
                   [n for n in cur if n.lower() != MULTI_PATCH_NAME.lower()], "--full (Multipatch set aside)")
    print(f"  {MULTI_PATCH_NAME} taken out of the load order; --all after the auto-merge rebuilds it.")
    return 0


def full_redundant_step(args, common):
    """--full's redundant-plugins step: in a console, --redundant asks about every group (with the
    descriptions and the overlap), --yes or not; with --redundant-auto the sure ones go without asking and
    the rest is asked. With nobody to ask (no console, or --no-interactive) the high-confidence duplicates
    are turned off and the rest is reported, saying why. --dry-run (in `common`) only reports."""
    # --yes doesn't answer these: turning a mod off is asked about whenever someone is there to answer;
    # only --redundant-auto turns the sure ones off without asking in a console
    console, _why = console_interactive()
    auto = getattr(args, "redundant_auto", False)
    if console and not getattr(args, "no_interactive", False):
        return ("redundant plugins (asks about each)",
                ["--redundant"] + (["--redundant-auto"] if auto else []) + [c for c in common if c != "--no-interactive"])
    return ("redundant plugins (nobody to ask: sure ones turned off, the rest reported)", ["--redundant-auto"] + common)


def run_full(args):
    """--full, from scratch:
        turn back on what earlier runs turned off (and drop their conflict rules and asset stand-ins),
        undo the auto-merge, turn off redundant plugins (asking in a console; --no-redundant skips it; the
        choices, in mwdialog_redundant.txt, are kept), report cell conflicts, sort, set the old Multipatch aside, clean and fix with
        the asset check, sort again;
        stop and open the report if any error is left; otherwise auto-merge, sort, --all, sort again;
        stop and open the report if any error is left; otherwise offer the interactive --cell-conflicts.
    It doesn't start at all while a plugin's master is missing from Data Files."""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    set_title("mwdialog_check --full - checking masters")
    missing = full_missing_masters(args, game_dir)
    if missing:
        set_title("mwdialog_check --full - stopped: missing masters")
        print("\n--full: ERROR - plugins whose masters aren't in Data Files. Install the masters, or take these "
              "plugins out of the load order, then run --full again:\n")
        for n, mname in missing:
            print(f"  - {n}  needs  {mname}")
        return 2
    # your remembered --cell-conflicts answers are replayed by default (the rebuilt-interior winners and the
    # [Order] rules come back before --fix builds the Cell Fixes patch); --fresh-answers starts clean
    if not getattr(args, "fresh_answers", False) and not getattr(args, "use_answers", False) \
            and read_conflict_answers(game_dir):
        args.use_answers = True
        print(f"--full: replaying your {len(read_conflict_answers(game_dir))} remembered conflict answer(s) from "
              f"{CONFLICT_ANSWERS_FILE} (--fresh-answers to start without them)")
    common = ["--fix-log", args.fix_log, "--encoding", args.encoding, "--no-interactive"] + (["--yes"] if args.yes else [])
    for flag in ("dry_run", "no_sounds", "no_mlox_rules", "no_content_order", "no_vortex", "no_doubled",
                 "no_performers", "no_placeholders", "no_merge_objects"):
        if getattr(args, flag, False):
            common.append("--" + flag.replace("_", "-"))
    if getattr(args, "collide_radius", COLLIDE_ANY_RADIUS) != COLLIDE_ANY_RADIUS:
        common += ["--collide-radius", f"{args.collide_radius:g}"]
    if args.ini:
        common += ["--ini", args.ini]
    if args.vortex_dir:
        common += ["--vortex-dir", args.vortex_dir]
    first = [("turn back on what earlier runs turned off", None)]
    if read_merge_record(game_dir):
        first.append(("undo the auto-merge", ["--unmerge", "--no-follow-up"]))
    if args.add_all_esp:
        first.append(("add every plugin in Data Files", ["--add-all-esp"]))
    if not getattr(args, "no_redundant", False):
        # early: once the plugin list is whole (merges undone, masters checked), before anything reads the
        # plugins - a plugin turned off here is not cleaned, fixed, merged, patched or asset-checked
        first.append(full_redundant_step(args, common))
    first += [
        (("cell conflicts (your remembered answers)", ["--cell-conflicts", "--use-answers"])
         if getattr(args, "use_answers", False) else
         ("cell conflicts (report)", ["--cell-conflicts", "--no-interactive"])),
        ("sort", ["--sort", "--no-follow-up"]),
        # The Multipatch is built once, after the auto-merge (which ignores this tool's patches): before it,
        # the old one is set aside and only clean + fix (+ the asset check) run on the unmerged order.
        ("set the old Multipatch aside (rebuilt after the auto-merge)", "multipatch_aside"),
        ("clean and fix with the asset check (no Multipatch yet)", ["--clean", "--fix", "--asset-check"]),
        # the fixes can change the plugin list (a plugin turned back on or off): sort again, without the
        # follow-up (it would rebuild the patches, which the second half does)
        ("sort again (after the fixes)", ["--sort", "--no-follow-up"]),
    ]
    second = [
        ("auto-merge", ["--auto-merge", "--no-follow-up"]),
        ("sort (merged)", ["--sort", "--no-follow-up"]),
        ("--all (merged)", ["--all"]),
        ("sort again (after --all's changes)", ["--sort"]),
    ]
    if args.dry_run:
        print("--full --dry-run: each step only shows its plan, so later steps see the load order as it is now.")
    global IN_FULL
    IN_FULL = True
    done, stopped = [], None
    total = len(first) + len(second)
    try:
        for phase, steps in ((1, first), (2, second)):
            for what, extra in steps:
                n = len(done) + 1
                set_title(f"mwdialog_check --full - step {n}/{total}: {what}")
                print("\n" + "#" * 70 + f"\n# --full step {n}/{total}: {what}"
                      + (f"\n#   mwdialog_check {' '.join(extra)}" if isinstance(extra, list) else "")
                      + "\n" + "#" * 70)
                start = time.time()
                try:
                    if extra is None:
                        rc = full_reset(args, game_dir)
                    elif extra == "multipatch_aside":
                        rc = multipatch_aside(args, game_dir)
                    elif extra and extra[0] in ("--redundant", "--redundant-auto"):
                        rc = main([args.data_dir] + extra)       # carries its own copy of the common flags
                    else:
                        rc = main([args.data_dir] + extra + common)
                except KeyboardInterrupt:
                    stopped = "stopped (Ctrl+C)"
                    break
                rc = rc or 0
                done.append((what, rc, time.time() - start))
                if rc not in (0, 1):
                    stopped = f"'{what}' failed (exit {rc})"
                    break
            if stopped:
                break
            if not args.dry_run:
                set_title(f"mwdialog_check --full - checking for errors ({'before' if phase == 1 else 'after'} the auto-merge)")
                errs = full_check(args, game_dir, "the unmerged load order" if phase == 1 else "the auto-merge")
                if errs:
                    stopped = f"{errs} error(s) after {'the unmerged load order' if phase == 1 else 'the auto-merge'}"
                    break
    finally:
        IN_FULL = False
    set_title("mwdialog_check --full - " + (f"stopped: {stopped}" if stopped else "finished"))
    print("\n" + "=" * 70 + "\n--full summary\n" + "=" * 70)
    for what, rc, secs in done:
        state = "ok" if rc == 0 else "issues reported" if rc == 1 else str(rc)
        print(f"  {what:62} {state:16} {secs:6.0f}s")
    try:
        rec = read_merge_record(game_dir)
        total = sum(len(v) for v in rec.values())
        if rec:
            print("\n  Auto-merge: " + "; ".join(f"{len(v)} plugin(s) merged into {k}" for k, v in rec.items())
                  + (f" ({total} in all)" if len(rec) > 1 else ""))
        cur = read_load_order(args) or []
        print(f"  Active plugins now: {len(cur)}" + (f" ({len(cur) + total - len(rec)} before merging)" if rec else ""))
    except (OSError, ValueError):
        pass
    if stopped:
        print(f"\n--full stopped: {stopped}. Fix what the report shows, then run --full again.")
        return 2
    if args.dry_run:
        return 0
    print("\n--full finished with no errors.")
    try:
        new_pairs = [l for l in open(os.path.join(game_dir, NEW_CONFLICTS_FILE), encoding="utf-8").read().split("\n") if l]
    except OSError:
        new_pairs = []
    if new_pairs:
        print(f"\n{len(new_pairs)} new conflict(s) have no remembered answer yet: "
              + ", ".join(p_.replace("|", " vs ") for p_ in new_pairs[:5]) + (" ..." if len(new_pairs) > 5 else ""))
        if not args.yes and sys.stdin.isatty():
            try:
                ans = input("Answer them now (only the new ones are asked)? [Y/n] ").strip().lower()
            except EOFError:
                ans = "n"
            if ans in ("", "y", "yes"):
                set_title("mwdialog_check --full - the new conflicts")
                main([args.data_dir, "--cell-conflicts", "--only-new"] + (["--ini", args.ini] if args.ini else []))
                new_pairs = None                         # answered: don't offer the full session too
        else:
            print("Answer them with:  mwdialog_check --cell-conflicts --only-new")
    if new_pairs is not None and not args.yes and sys.stdin.isatty():
        try:
            ans = input("Run --cell-conflicts now, to choose rules or turn plugins off conflict by conflict? [y/N] ")
        except EOFError:
            ans = ""
        if ans.strip().lower() in ("y", "yes"):
            set_title("mwdialog_check --full - interactive --cell-conflicts")
            main([args.data_dir, "--cell-conflicts"] + (["--ini", args.ini] if args.ini else []))
    if args.play:
        print("\n--full: starting the game")
        return main([args.data_dir, "--play"] + (["--play-anyway"] if args.play_anyway else [])
                    + (["--ini", args.ini] if args.ini else []))
    return 0


def _ensure_vortex_paths(args):
    """Fill args.vortex_dir and args.vortex_downloads from Vortex settings when the user did not pass
    them. Errors out (VortexPathError) when they are needed and cannot be determined. --no-vortex
    skips staging; --no-archive-lookup or --no-master-guard skips downloads."""
    # explicit flags already set the attribute; resolve_staging/downloads still validate a given dir
    want_staging = not getattr(args, "no_vortex", False)
    # --no-vortex means "don't use Vortex" (staging and, unless --vortex-downloads is given, downloads)
    want_downloads = (not getattr(args, "no_archive_lookup", False)
                      and not getattr(args, "no_master_guard", False)
                      and (want_staging or bool(getattr(args, "vortex_downloads", None))))
    if want_staging:
        cli = getattr(args, "vortex_dir", None)
        args.vortex_dir = MP.resolve_staging(cli=cli, required=True)
        src = "--vortex-dir" if cli else "Vortex settings"
        print(f"Vortex staging: {args.vortex_dir}  (from {src})")
    if want_downloads:
        cli = getattr(args, "vortex_downloads", None)
        args.vortex_downloads = MP.resolve_downloads(cli=cli, required=True)
        src = "--vortex-downloads" if cli else "Vortex settings"
        print(f"Vortex downloads: {args.vortex_downloads}  (from {src})")


def _main(argv=None):
    global ENC
    ap = MT.parser(description="Scan a Morrowind Data Files folder for dialogue errors.")
    ap.add_argument("data_dir", help='path to the "Data Files" folder')
    ap.add_argument("--plugins", nargs="+", metavar="FILE", help="explicit load order (file names in Data Files)")
    ap.add_argument("--ini", help=f"Morrowind.ini (its [Archives]; the plugin list is {LOAD_ORDER_FILE}, made from "
                                  f"this ini the first time, and written back into it whenever a run changes it, and by --play)")
    ap.add_argument("--openmw-cfg", help="openmw.cfg to read content= and data= from")
    ap.add_argument("--only", nargs="+", metavar="FILE", help="report (and fix) only issues coming from these plugins")
    ap.add_argument("--min-severity", choices=SEVERITIES, default="WARN", help="lowest severity to report (default WARN; use INFO to also see harmless notes)")
    ap.add_argument("--no-sounds", action="store_true", help="skip checking that voice/sound files exist")
    ap.add_argument("--csv", metavar="PATH", help="also write the report to a CSV file")
    ap.add_argument("--encoding", default="cp1252", help="text encoding of plugin strings (cp1252 for English, cp1251 Russian, cp1250 Polish)")
    fx = ap.add_argument_group("fixing (ERRORs only; .esp files are backed up to .esp.bak first, .esm files are never changed)")
    fx.add_argument("--fix", action="store_true",
                    help="after the report, show a fix plan and apply it after you confirm; .esp files are fixed "
                         "in place, masters (.esm) through the patch plugin '" + PATCH_NAME + "'")
    fx.add_argument("--dry-run", action="store_true", help="with --fix: show the plan but change nothing")
    fx.add_argument("--yes", action="store_true", help="with --fix: apply without asking")
    fx.add_argument("--patch-esm", action="store_true",
                    help="same as --fix (kept for older batch notes)")
    fx.add_argument("--restore", nargs="+", metavar="FILE", help="undo: put each plugin's newest .bak back (keeps the file date) and exit")
    tc = ap.add_argument_group("tes3cmd features (in place, .bak first, file dates kept)")
    tc.add_argument("--multipatch", action="store_true",
                    help=f"build '{MULTI_PATCH_NAME}' like 'tes3cmd multipatch': merged leveled lists, "
                         f"fog-bugged cells, reverted cell names, plus objects several mods change merged field "
                         f"by field (load it last)")
    tc.add_argument("--disable-mismatched", action="store_true",
                    help="take plugins made for a different master than the installed one (mwdialog_mastercheck: "
                         "references that don't resolve, original header size) out of the load order")
    tc.add_argument("--mismatch-threshold", type=float, default=None, metavar="0-1",
                    help="confidence from which a master counts as a different mod (default 0.75)")
    tc.add_argument("--vortex-downloads", "--downloads", default=None, dest="vortex_downloads", metavar="DIR",
                    help="Vortex download folder, to read a plugin's original header from its download archive "
                         "when --fix has rewritten it (default: Vortex's own setting)")
    tc.add_argument("--no-archive-lookup", action="store_true", help="don't open download archives for the master check")
    tc.add_argument("--no-master-guard", action="store_true", help="skip the master mismatch check")
    tc.add_argument("--longpaths-undo", action="store_true",
                    help="put back every file --fix or vortex_tidy moved to a short path (mwdialog_longpaths.json) "
                         "and the paths in plugins and models; the next --fix rebuilds the ESM patch without them")
    tc.add_argument("--restore-unused", action="store_true",
                    help="put back the unused textures/sounds --asset-check --fix moved to Off\\unused\\")
    tc.add_argument("--repair-sounds", action="store_true",
                    help="re-save sound files the active plugins play that the game can hang or crash on (24/32-bit "
                         "or odd-codec WAVs, MP3s with damaged or huge tags), same names, no plugin changed; needs "
                         "ffmpeg; originals go to <mod folder>\\Off\\<plugin>\\<path>")
    tc.add_argument("--no-merge-objects", action="store_true",
                    help="with --multipatch: don't merge objects several mods change (by default the Multipatch "
                         "combines what each changed in an NPC, creature, item or spell, like TES3Merge)")
    tc.add_argument("--all", action="store_true", help="--clean, then --fix, then --multipatch")
    tc.add_argument("--full", action="store_true",
                    help="everything, from scratch. Aborts first if a plugin's master isn't in Data Files. Then: "
                         "turn back on what earlier runs turned off (and drop their conflict rules and asset "
                         "stand-ins), --unmerge, --cell-conflicts (report), --sort, --all --asset-check; if any "
                         "ERROR is left, stop and open mwdialog_report.txt; else --auto-merge, --sort, --all; if "
                         "any ERROR is left, stop and open the report; else offer the interactive "
                         "--cell-conflicts. --yes: no questions; --add-all-esp: add every plugin first; --play: "
                         "start the game at the end")
    tc.add_argument("--header", nargs="+", metavar="FILE",
                    help="show a plugin's Author and Description, or set them with --set-author/--set-description")
    tc.add_argument("--set-author", metavar="TEXT", help="with --header: new Author ('+text' appends)")
    tc.add_argument("--set-description", metavar="TEXT",
                    help="with --header: new Description ('+text' appends; \\n starts a new line)")
    lo = ap.add_argument_group("load order (sets plugin dates; masters first, then mlox-style rules)")
    lo.add_argument("--sort", action="store_true",
                    help=f"sort the active plugins: masters before the plugins using them, then the rules in "
                         f"{RULES_FILE} and mlox's mlox_user.txt/mlox_base.txt; dates are set one day apart")
    lo.add_argument("--no-mlox-rules", action="store_true", help=f"with --sort: use only {RULES_FILE}")
    lo.add_argument("--update-rules", action="store_true",
                    help="remove the steps of mlox's rules (Morrowind\\mlox\\mlox_user.txt, mlox_base.txt) that the "
                         "sort skips because a master, your rules, a context rule or an earlier mlox rule says "
                         "otherwise; --dry-run shows the plan and the reason for each. Your own rules file is "
                         "only reported, never edited")
    lo.add_argument("--bug-reports", action="store_true",
                    help="write <plugin>.bugreport.txt for plugins with problems of their own (also done by "
                         "--fix and --asset-check)")
    lo.add_argument("--no-bug-reports", action="store_true", help="don't write <plugin>.bugreport.txt files")
    lo.add_argument("--no-add-masters", action="store_true",
                    help="--sort: don't add a mod as a master to the patch that changes its records (keep "
                         "only the [Context] order rule)")
    lo.add_argument("--no-content-order", action="store_true",
                    help="with --sort: don't add the automatic patch-after-mod rules (a small .esp most of whose "
                         "records are another .esp's loads after it)")
    lo.add_argument("--restore-dates", action="store_true", help="undo the last --sort (put the old dates back)")
    lo.add_argument("--add-all-esp", action="store_true",
                    help=f"activate every .esm/.esp in Data Files in {LOAD_ORDER_FILE} (masters first, then by date; "
                         "MGE XE grass plugins left out; the old ini is backed up). Use --dry-run to preview")
    mg = ap.add_argument_group("merging")
    mg.add_argument("--merge", nargs="+", metavar=("OUT.esp", "INPUT"),
                    help="merge plugins into one: --merge \"Merged.esp\" FILE_OR_FOLDER... (written beside the "
                         "inputs' originals - for files deployed into Data Files, their Vortex mod folder - unless "
                         "the name includes a path). Inputs whose "
                         "masters aren't active, or whose dialogue refers to things no installed mod defines, "
                         "are left out (their target mod isn't installed). Later inputs win conflicts")
    mg.add_argument("--auto-merge", action="store_true",
                    help=f"find active .esp plugins with no scripts and no cell/land/pathgrid edits that can move "
                         f"together without changing what wins against any other plugin, merge them into one "
                         f"('{AUTO_MERGE_NAME}', or --merge-name), and deactivate them (recorded in {MERGE_RECORD}; "
                         f"--add-all-esp leaves them out). Use --dry-run first")
    mg.add_argument("--merge-name", metavar="NAME.esp", help="with --auto-merge: the merged plugin's name")
    mg.add_argument("--no-follow-up", "--no-follow-fix", dest="no_follow_fix", action="store_true",
                    help="don't run the usual follow-ups: --fix --multipatch after --auto-merge or a --sort "
                         "that changed the order, --add-all-esp --sort after --unmerge, and --fix's own re-scans "
                         "for follow-on fixes (one final check still runs)")
    mg.add_argument("--unmerge", nargs="*", metavar="NAME.esp",
                    help="undo an --auto-merge: reactivate the plugins it replaced and remove the merged plugin "
                         "(all recorded merges if no name is given)")
    mg.add_argument("--merge-all", action="store_true", help="with --merge: include every input anyway")
    mg.add_argument("--merge-with", nargs="+", metavar="PLUGIN",
                    help="with --merge: plugins (not merged) that count as installed when checking the inputs, "
                         "e.g. the base mod the patches are for, if it isn't active yet")
    gm = ap.add_argument_group("game")
    gm.add_argument("--play", action="store_true",
                    help="start Morrowind.exe directly, skipping the Morrowind Launcher (after any other steps "
                         "given, e.g. --sort --play). Sets SteamAppId so Steam doesn't redirect to the Launcher")
    gm.add_argument("--steam-appid", default=STEAM_APPID, help=f"with --play: Steam app id (default {STEAM_APPID})")
    gm.add_argument("--play-anyway", action="store_true",
                    help="with --play: start the game even if a plugin's master is missing or loads after it")
    gm.add_argument("--exe", default="Morrowind.exe", help="with --play: the game executable (default Morrowind.exe)")
    tc.add_argument("--conflict-all-places", action="store_true",
                    help="--cell-conflicts: also list the pairs that only put a few objects near each other "
                         "(left to mwcollide, not asked about)")
    tc.add_argument("--cell-conflicts", action="store_true",
                    help="report plugins that don't know about each other but build in the same spot, change the "
                         "same placed objects, or change the same cell settings; in a console it then asks, "
                         "conflict by conflict: an [Order] rule, turn one off, or for an interior both rebuilt, "
                         "whose version of the place wins (" + CELL_WINNERS_FILE + "; --fix builds "
                         + CELL_WINNER_PATCH + ")")
    tc.add_argument("--only-new", action="store_true",
                    help="with --cell-conflicts: replay every remembered answer and ask only about the conflicts "
                         "that have none yet")
    tc.add_argument("--fresh-answers", action="store_true",
                    help="with --full: don't replay the answers remembered in " + CONFLICT_ANSWERS_FILE +
                         " (by default --full replays them, so your rebuilt-interior winners and [Order] choices "
                         "stand); the conflicts are only reported and you are asked at the end")
    tc.add_argument("--use-answers", action="store_true",
                    help="with --cell-conflicts: no questions, take every answer remembered in "
                         + CONFLICT_ANSWERS_FILE + " (a pair with none is skipped), then run what it needs "
                         "(--sort, and --fix --multipatch if a plugin is turned off or a place's winner chosen). "
                         "With --full: keeps " + CELL_WINNERS_FILE + " and replays the answers in its conflict step")
    tc.add_argument("--conflict-min", type=int, default=5, metavar="N",
                    help="with --cell-conflicts: a plugin must add at least N new objects to a cell to count (default 5)")
    tc.add_argument("--conflict-top", type=int, default=40, metavar="N",
                    help="with --cell-conflicts: print the N most serious pairs in the summary (default 40); "
                         "the questions still go through every pair")
    tc.add_argument("--conflict-all", action="store_true", help="with --cell-conflicts: show every pair")
    tc.add_argument("--collide-radius", type=float, default=COLLIDE_ANY_RADIUS, metavar="UNITS",
                    help="with --cell-conflicts: for the mwcollide MWSE mod, hide anything of the earlier of two "
                         f"unrelated mods within this many units of something of the later one's (default "
                         f"{COLLIDE_ANY_RADIUS:g}; 0: only the same object or model, within {COLLIDE_RADIUS:g})")
    tc.add_argument("--no-interactive", action="store_true",
                    help="with --cell-conflicts: only report, don't ask what to do about each conflict "
                         "(also the case when the output goes to a file)")
    tc.add_argument("--vortex-dir", metavar="PATH",
                    help="Vortex's mod staging folder, searched for files that exist there but were never deployed "
                         "(default: Vortex's own setting)")
    tc.add_argument("--no-vortex", action="store_true", help="don't search the Vortex mod folders")
    tc.add_argument("--restore-textures", action="store_true",
                    help=f"put back the full-size textures --asset-check --fix reduced to {TEXTURE_MAX_EDGE} (see {REDUCED_RECORD})")
    tc.add_argument("--remove-generated", action="store_true",
                    help=f"delete the silent stand-in sound/music files --fix created (see {GENERATED_RECORD})")
    tc.add_argument("--asset-check", action="store_true",
                    help="also check the files records, scripts and Morrowind.ini name (models and their textures, "
                         "icons, sounds, music, videos, fonts), search Vortex mod folders and .Orphaned for missing "
                         "ones, and with --fix put them back or use stand-ins (adds a few minutes)")
    tc.add_argument("--no-models", action="store_true", help=argparse.SUPPRESS)   # the old opt-out; now the default
    tc.add_argument("--performers-patch", action="store_true",
                    help="with --fix: delete doubled bards with mwdialog_check Performers Patch.esp, instead of "
                         "leaving them to the mwperformers MWSE mod (which hides them in the game)")
    tc.add_argument("--no-performers", action="store_true",
                    help="with --fix: don't remove doubled bards (two plugins' performers in one inn)")
    tc.add_argument("--no-doubled", action="store_true",
                    help="with --fix: don't look for (or turn off) plugins that place the same objects twice")
    tc.add_argument("--reenable", nargs="*", metavar="NAME",
                    help=f"turn back on plugins --fix turned off as doubled (all of them with no name; see {DISABLED_RECORD})")
    tc.add_argument("--redundant", action="store_true",
                    help="find plugins doing the same job as another (nothing of theirs would be missed, or two "
                         "versions of one mod), describe each and how they overlap, and ask which to keep "
                         f"(report only when not in a console, or with --no-interactive; remembered in {REDUNDANT_RECORD})")
    tc.add_argument("--redundant-auto", action="store_true",
                    help="--redundant, turning off the high-confidence ones (an .esp that changes nothing in the "
                         "game and that nothing needs) without asking; two versions of one mod are still only asked about")
    tc.add_argument("--no-redundant", action="store_true",
                    help="with --full: skip the redundant-plugins step (by default it runs early, so plugins doing "
                         "nothing another doesn't already do are turned off before anything else reads them)")
    tc.add_argument("--redundant-undo", nargs="*", metavar="NAME",
                    help="turn back on plugins --redundant turned off (all of them, and forget the keep-both "
                         "choices, with no name)")
    tc.add_argument("--trace", nargs="+", metavar="ID",
                    help="follow object IDs through the load order: who defines, places, deletes or scripts them")
    tc.add_argument("--clean", action="store_true",
                    help="clean .esp plugins like 'tes3cmd clean': duplicate object instances, redundant AMBI/WHGT, "
                         "records duplicated from masters, Evil GMSTs, junk cells")
    fx.add_argument("--no-placeholders", action="store_true",
                    help="with --fix: don't add stand-in gold coins for objects that scripts name but no mod defines")
    fx.add_argument("--restore-all", action="store_true",
                    help="undo everything: put every plugin back to its oldest .bak (the original), remove all its backups, and exit")
    fx.add_argument("--clean-up", action="store_true",
                    help="delete .bak backups of plugins that are no longer in Data Files, and keep only the most "
                         "recent .bak of each remaining plugin (use --dry-run to preview)")
    fx.add_argument("--fix-log", default="mwdialog_fixes.log", help="where to append a record of fixes (default mwdialog_fixes.log)")
    args = ap.parse_args(argv)
    ENC = args.encoding
    mwdialog_tes3.ENC = ENC                   # dec/enc/cstr live there
    try:
        _ensure_vortex_paths(args)
    except (MP.VortexPathError, MP.ToolNotFoundError) as e:
        print(str(e), file=sys.stderr)
        return 2
    if MAIN_DEPTH == 1:
        global TOP_ARGS
        TOP_ARGS = args
        if getattr(args, "data_dir", None) and os.path.isdir(args.data_dir) and not getattr(args, "dry_run", False):
            try:
                drop_vanished_added_masters(args)
            except (OSError, UnicodeError, ValueError) as e:
                print(f"(could not check {ADDED_MASTERS_RECORD}: {e})", file=sys.stderr)
        if getattr(args, "data_dir", None) and os.path.isdir(args.data_dir) and not args.reenable:
            try:
                release_lost_winners(args)
            except (OSError, UnicodeError) as e:
                print(f"(could not check {DISABLED_RECORD}: {e})", file=sys.stderr)
        if getattr(args, "data_dir", None) and os.path.isdir(args.data_dir) and args.redundant_undo is None:
            try:
                release_redundant(args)
            except (OSError, UnicodeError) as e:
                print(f"(could not check {REDUNDANT_RECORD}: {e})", file=sys.stderr)
        if getattr(args, "data_dir", None) and os.path.isdir(args.data_dir) and not (args.full or args.auto_merge):
            pend = read_merge_rebuild(os.path.dirname(os.path.abspath(args.data_dir)))
            if pend:
                print(f"Note: {', '.join(pend)} still contain{'s' if len(pend) == 1 else ''} plugin(s) --redundant "
                      f"turned off ({', '.join(i for v in pend.values() for i in v)}); --auto-merge or --full "
                      f"rebuilds without them.", file=sys.stderr)
    if args.all:
        args.clean = args.fix = args.multipatch = True
    if args.play_anyway:
        args.play = True
    if args.full:
        return run_full(args)
    if getattr(args, "longpaths_undo", False):
        dd = os.path.abspath(args.data_dir)
        return longpaths_module().undo(os.path.dirname(dd), dd, sys.modules[__name__])
    if getattr(args, "restore_unused", False):
        dd = os.path.abspath(args.data_dir)
        return asset_health_module().restore_unused(os.path.dirname(dd), dd)
    if getattr(args, "repair_sounds", False):
        return run_repair_sounds(args)
    if not REPAIRING_INI and os.path.isdir(args.data_dir) and not (args.add_all_esp and args.sort) \
            and not (args.header or args.restore or args.restore_all or args.restore_dates):
        cut = truncated_game_files(args)
        if cut:
            last, full, count = cut
            print("=" * 70)
            print(f"Morrowind.ini's plugin list was cut off: it stops after {count} entries at '{last}'"
                  + (f" (the file is '{full}')" if full else "") + ".")
            print(f"The list reached Windows' {INI_SECTION_LIMIT:,}-character ini section limit and Vortex dropped "
                  f"every plugin after that point.")
            if args.dry_run:
                print("--dry-run: not repairing it. Without --dry-run this runs --add-all-esp --sort --yes first.")
                print("=" * 70)
            else:
                print("Repairing it first: --add-all-esp --sort --yes")
                print("=" * 70)
                argv2 = [args.data_dir, "--add-all-esp", "--sort", "--yes",
                         "--fix-log", args.fix_log, "--encoding", args.encoding]
                if args.no_mlox_rules:
                    argv2.append("--no-mlox-rules")
                if args.no_content_order:
                    argv2.append("--no-content-order")
                if args.ini:
                    argv2 += ["--ini", args.ini]
                REPAIRING_INI.append(True)
                try:
                    rc = main(argv2)
                finally:
                    REPAIRING_INI.clear()
                if rc:
                    print(f"(The repair's own checks ended with code {rc}; carrying on.)")
                print("\n" + "=" * 70 + "\nLoad order repaired; now running what was asked.\n" + "=" * 70)
    if not REPAIRING_INI and os.path.isdir(args.data_dir) and not args.sort \
            and not (args.header or args.restore or args.restore_all or args.restore_dates or args.add_all_esp):
        split = split_exact_groups(args)
        if split:
            print("=" * 70)
            for src, members, between, fresh in split:
                print(f"[Exact] group at {src} has come apart in the load order: {' / '.join(members)}")
                for m, t in fresh:
                    print(f"  {m} has the date {time.strftime('%Y-%m-%d %H:%M', time.localtime(t))}: it was "
                          f"saved or replaced since the last --sort, so it now loads in the wrong place")
                if between:
                    shown = ", ".join(n for n, _t in between[:4]) + (f" and {len(between) - 4} more" if len(between) > 4 else "")
                    print(f"  loading in between now: {shown}")
            if args.dry_run:
                print("--dry-run: not re-sorting. Without --dry-run this runs --sort --yes first.")
                print("=" * 70)
            else:
                print("Putting it back together first: --sort --yes")
                print("=" * 70)
                argv2 = [args.data_dir, "--sort", "--yes", "--fix-log", args.fix_log, "--encoding", args.encoding]
                if args.no_mlox_rules:
                    argv2.append("--no-mlox-rules")
                if args.no_content_order:
                    argv2.append("--no-content-order")
                if args.ini:
                    argv2 += ["--ini", args.ini]
                REPAIRING_INI.append(True)
                try:
                    rc = main(argv2)
                finally:
                    REPAIRING_INI.clear()
                if rc:
                    print(f"(The re-sort's own checks ended with code {rc}; carrying on.)")
                print("\n" + "=" * 70 + "\nLoad order re-sorted; now running what was asked.\n" + "=" * 70)
    if args.play:
        actions = (args.sort, args.add_all_esp, args.clean, args.fix, args.multipatch, args.patch_esm,
                   args.header, args.trace, args.restore, args.restore_all, args.restore_dates, args.csv,
                   args.clean_up, args.merge, args.auto_merge, args.unmerge is not None, args.cell_conflicts, args.reenable is not None, args.remove_generated,
                   args.redundant, args.redundant_auto, args.redundant_undo is not None, args.restore_textures,
                   args.update_rules)
        if not any(actions):                 # --play on its own: just start the game
            GAME_STARTED.append(True)
            return launch_game(args)
        elif args.dry_run:
            print("--play: skipped because of --dry-run.")
        else:
            PLAY_REQUEST.append(args)        # otherwise start it after the other steps

    if not os.path.isdir(args.data_dir):
        ap.error(f"not a folder: {args.data_dir}")

    if args.header:
        return run_header(args)
    if args.update_rules:
        rc = run_update_rules(args)
        if rc or not (args.sort or args.clean or args.fix or args.multipatch):
            return rc
    if args.restore_dates:
        return restore_dates(args)
    if args.add_all_esp:
        rc = run_add_all_esp(args)
        if rc or args.dry_run or not (args.sort or args.clean or args.fix or args.multipatch):
            return rc
    if args.clean_up:
        rc = run_clean_up(args)
        if rc or not (args.sort or args.clean or args.fix or args.multipatch):
            return rc
    if args.reenable is not None:
        return run_reenable(args)
    if args.redundant_undo is not None:
        return run_redundant_undo(args)
    if args.redundant or args.redundant_auto:
        return run_redundant(args)
    if args.remove_generated:
        return run_remove_generated(args)
    if args.restore_textures:
        return run_restore_textures(args)
    if args.restore_all:
        return restore_all(args.data_dir, args.yes, args.fix_log)
    if args.restore:
        return restore_backups(args.restore, args.data_dir)

    report = Report()
    plugins, bsas, data_dirs = resolve(args, report)
    if args.unmerge is not None:
        rc = run_unmerge(args, plugins)
        if rc == 0 and not args.no_follow_fix:
            # the merged plugins are back: activate everything and put it in rule order
            print("\n" + "=" * 70 + "\nFOLLOW-UP: --add-all-esp --sort\n" + "=" * 70)
            argv2 = [args.data_dir, "--add-all-esp", "--sort", "--fix-log", args.fix_log, "--encoding", args.encoding]
            if args.yes:
                argv2.append("--yes")
            if args.no_mlox_rules:
                argv2.append("--no-mlox-rules")
            if args.no_content_order:
                argv2.append("--no-content-order")
            if args.ini:
                argv2 += ["--ini", args.ini]
            return main(argv2)
        return rc
    if args.auto_merge:
        rc = run_auto_merge(args, plugins, bsas, data_dirs)
        if rc == 0 and getattr(args, "merged_now", False) and not args.no_follow_fix:
            # the load order changed: rebuild the patches and fix what the new order exposes
            print("\n" + "=" * 70 + "\nFOLLOW-UP: --fix --multipatch with the merged load order\n" + "=" * 70)
            argv2 = [args.data_dir, "--fix", "--multipatch", "--fix-log", args.fix_log, "--encoding", args.encoding]
            if args.yes:
                argv2.append("--yes")
            if args.no_sounds:
                argv2.append("--no-sounds")
            if args.ini:
                argv2 += ["--ini", args.ini]
            return main(argv2)
        return rc
    if args.merge:
        if len(args.merge) < 2:
            ap.error("--merge needs the merged plugin's name and at least one input file or folder")
        return run_merge(args, plugins, bsas, data_dirs)
    if args.cell_conflicts:
        return run_cell_conflicts(args, plugins)
    if args.fix and fix_omwaddon_masters(args) and not args.dry_run:
        if not args.sort and not IN_FULL:                    # their masters may load after them: sort
            print("\n" + "=" * 70 + "\nSORT: plugin headers now name different masters\n" + "=" * 70)
            run_sort(args, resolve(args, Report())[0])
        plugins, bsas, data_dirs = resolve(args, report)     # those plugins now find their masters
    if args.fix:
        fix_ref_groups(args, plugins)
    if args.fix and fix_long_names(args, plugins, bsas) and not args.dry_run:
        plugins, bsas, data_dirs = resolve(args, report)
    if args.fix and not args.no_doubled:
        gone = {n.lower() for n in fix_doubled(args, plugins)}
        if gone:
            plugins = [(n, p) for n, p in plugins if n.lower() not in gone]
    if args.fix and args.performers_patch and not args.no_performers:
        fix_performers(args, plugins)
    elif args.fix and not args.dry_run:
        drop_performers_patch(args)       # the mwperformers MWSE mod decides in the game now
    if args.fix:
        fix_cell_winners(args, plugins)
    loaded_patches = {n.lower() for n, _p in plugins} & {x.lower() for x in OUR_PATCHES}
    if args.fix or args.patch_esm or args.multipatch:   # rebuilt from scratch: leave them out of the scan
        names = [n.lower() for n, _p in plugins]
        if PATCH_NAME.lower() in names:            # where the ESM patch really loads
            args.esm_patch_pos = sum(1 for n in names[:names.index(PATCH_NAME.lower())]
                                     if n not in [x.lower() for x in OUR_PATCHES])
        else:                                      # new: right after the masters
            args.esm_patch_pos = sum(1 for n in names if n.endswith(".esm"))
        plugins = [(n, p) for n, p in plugins if n.lower() not in [x.lower() for x in OUR_PATCHES]]
    if not plugins:
        print("No plugins found.", file=sys.stderr)
        return 2

    only = {o.lower() for o in args.only} if args.only else None
    if args.sort:
        run_sort(args, resolve(args, Report())[0])     # every active plugin, our patches included
        if getattr(args, "sort_changed", False) and not args.no_follow_fix and not (args.fix and args.multipatch):
            # a new order can undo what the patches fixed (a later plugin now blanking 'Caldera Priory',
            # leveled lists merged in the old order): rebuild them and fix what the new order exposes
            print("\n" + "=" * 70 + "\nFOLLOW-UP: --fix --multipatch with the new load order\n" + "=" * 70)
            args.fix = args.multipatch = True
        if not (args.clean or args.fix or args.multipatch):
            return 0
        plugins, bsas, data_dirs = resolve(args, report)   # dates changed: read the new order
        if (args.fix or args.patch_esm or args.multipatch) and not hasattr(args, "esm_patch_pos"):
            args.esm_patch_pos = sum(1 for n, _p in plugins if n.lower().endswith(".esm"))
        plugins = [(n, p) for n, p in plugins if n.lower() not in [x.lower() for x in OUR_PATCHES]] \
            if (args.fix or args.patch_esm or args.multipatch) else plugins
    if args.clean:
        run_clean(args, plugins, only)        # cleaned files are what the checks below see

    world = scan(args, plugins, bsas, data_dirs, report)
    if args.trace:
        print("\n" + "=" * 70 + "\nTRACE (load position, plugin: what it does)\n" + "=" * 70)
        for t in sorted(world.trace):
            lines = [x for tt, x in world.trace_log if tt == t]
            print(f"\n{t}:" + ("" if lines else "  not mentioned by any loaded plugin"))
            for x in lines:
                print("  " + x)
            print(f"  -> at the end: {'defined as ' + world.all_ids[t] if t in world.all_ids else 'NOT defined'}, "
                  f"{max(world.placed.get(t, 0), 0)} placed copy/copies")
        print()

    limit = SEV_RANK[args.min_severity]
    hidden = set()      # (plugin, issue label) for master issues the existing patch already fixes
    if args.fix or args.patch_esm or loaded_patches:
        covered = set()
        for pn in (PATCH_NAME, PLACE_PATCH_NAME):       # the patches that fix issues (the others merge or move)
            covered |= patch_contents(os.path.join(args.data_dir, pn))
        for sev, plugin, topic, info, msg in report.issues:
            if covered_by_patches((sev, plugin, topic, info, msg), covered):
                hidden.add((plugin, issue_label(topic, info, msg)))
    issues = [i for i in report.issues
              if SEV_RANK[i[0]] <= limit and (only is None or i[1].lower() in only)
              and not is_our_patch(i[1])
              and (i[1], issue_label(i[2], i[3], i[4])) not in hidden]
    order = {n.lower(): k for k, (n, _p) in enumerate(plugins)}
    issues.sort(key=lambda i: (order.get(i[1].lower(), -1), i[1].lower(), i[2].lower(), SEV_RANK[i[0]], i[3]))

    counts = defaultdict(int)
    last_plugin = last_topic = None
    for sev, plugin, topic, info, msg in issues:
        counts[sev] += 1
        if plugin != last_plugin:
            print(f"\n=== {plugin or '(load order)'} ===")
            last_plugin, last_topic = plugin, None
        if topic != last_topic:
            print(f"  [{topic}]" if topic else "  [file]")
            last_topic = topic
        loc = f" {info}:" if info else ""
        print(f"    {sev:<5}{loc} {msg}")

    print(f"\nLoaded {len(plugins)} plugin(s), {len(world.topics)} topic(s), "
          f"{sum(len(t.infos) for t in world.topics.values())} response(s).")
    print("Found " + ", ".join(f"{counts[s]} {s}" for s in SEVERITIES) + ".")
    if world.persist_mismatch and SEV_RANK["INFO"] > limit:
        print("\nReferences filed as persistent/temporary differently from their master "
              "(left as the mods made them; see them with --min-severity INFO):")
        for plugin in sorted(world.persist_mismatch, key=lambda n: order.get(n.lower(), 0)):
            if only is None or plugin.lower() in only:
                print(f"  {plugin}: {world.persist_mismatch[plugin]}")
    if hidden:
        print(f"({len(hidden)} issue(s) in masters are already fixed by '{PATCH_NAME}' and not listed; "
              f"they are carried over when the patch is rebuilt.)")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["severity", "plugin", "topic", "response_id", "message"])
            w.writerows(issues)
        print(f"CSV written to {args.csv}")

    if (args.fix or args.asset_check or getattr(args, "bug_reports", False)) and not args.dry_run \
            and not getattr(args, "no_bug_reports", False) and only is None:
        try:
            write_bug_reports(args, plugins, report, world)
        except Exception as e:                       # a report is a courtesy: never stop the run for it
            print(f"(bug reports not written: {e})", file=sys.stderr)
    if args.fix or args.patch_esm:
        run_fix(args, plugins, bsas, data_dirs, report, world, only, hidden)
    if args.multipatch:
        run_multipatch(args, plugins, world)

    return 1 if counts["ERROR"] else 0


# messages about a plugin's dealings with OTHER plugins: not the author's own bug
NOT_OWN_BUG = re.compile(r"later plugin|another plugin|other plugin|loads (?:after|before|between)|deleted by|"
                         r"replaces it|conflict|load order|is a master of|lists it as a master|both change|"
                         r"winner|loses to|overrid|already fixed by|carried over|not active", re.I)


def write_bug_reports(args, plugins, report, world):
    """<plugin>.bugreport.txt for every plugin with problems of its own (section "mwdialog_check"): its
    errors and warnings, files it needs that no mod has, and what --fix repairs for it."""
    ah = asset_health_module()
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    names = {n.lower(): (n, p) for n, p in plugins}
    per = defaultdict(lambda: {"ERROR": [], "WARN": [], "repaired": [], "missing": []})
    for sev, plugin, topic, info, msg in report.issues:
        if sev not in ("ERROR", "WARN") or is_our_patch(plugin) or plugin.lower() not in names \
                or NOT_OWN_BUG.search(msg):
            continue
        where = " / ".join(x for x in (f"[{topic}]" if topic else "", info) if x)
        per[plugin.lower()][sev].append(f"  - {where + ': ' if where else ''}{msg}")
    for plugin, off, op, desc, label, topic, info in report.fixes:
        if plugin and plugin.lower() in names and not is_our_patch(plugin):
            per[plugin.lower()]["repaired"].append(f"  - {label}: {desc}")
    for item in getattr(world, "generated", []):
        rel, why = item[0], item[1]
        pl = item[3] if len(item) > 3 else ""
        if pl and pl.lower() in names and not is_our_patch(pl) and not (len(item) > 2 and item[2]):
            per[pl.lower()]["missing"].append(f"  - {rel} (needed by {why}); a stand-in was put in its place")
    # the scan saw every plugin: one that is clean now loses an old section
    written = cleared = 0
    for low, (name, path) in names.items():
        if is_our_patch(name) or low in NOT_A_MOD:
            continue
        d = per.get(low)
        lines = []
        if d:
            for title, key in (("Errors (the game reports these, or the content breaks)", "ERROR"),
                               ("Warnings", "WARN"),
                               ("Files the plugin needs that no mod provides", "missing"),
                               ("Repaired by mwdialog_check --fix (the author may want to fix these in the plugin)",
                                "repaired")):
                if d[key]:
                    lines.append(f"{title}: {len(d[key])}")
                    lines += sorted(set(d[key]))[:300]
                    lines.append("")
        out = ah.bug_report_path(data_dir, game_dir, name, sys.modules[__name__])
        if not lines and not os.path.exists(out):
            continue
        ah.update_bug_report(out, "mwdialog_check", ah.bug_report_header(path, sys.modules[__name__]), lines)
        written += bool(lines)
        cleared += not lines
    if written or cleared:
        print(f"\nBug reports: {written} plugin(s) have <plugin>.bugreport.txt in their mod folder (or in "
              f"bugreports\\)" + (f"; {cleared} cleared" if cleared else "") + ".")



MAIN_DEPTH = 0
TOP_ARGS = None


def apply_load_order_to_ini(args):
    """At the end of a run that changed mwdialog_load_order.txt (a sort, --add-all-esp, a merge, a plugin
    turned off...), write it into Morrowind.ini's [Game Files] too: tools that read the ini, like MGE XE's
    distant land generator, then see the same load order. Plugins that aren't in Data Files are left out."""
    if args is None or getattr(args, "plugins", None) or getattr(args, "openmw_cfg", None):
        return
    game_dir = os.path.dirname(os.path.abspath(args.data_dir))
    if game_dir not in LOAD_ORDER_WRITTEN:
        return
    ini = default_ini(args)
    order = read_load_order(args)
    if not order or not os.path.isfile(ini):
        return
    lookup = index_dir(os.path.abspath(args.data_dir))
    order = [n for n in order if n.lower() in lookup]
    if [n.lower() for n in ini_game_files(ini)] == [n.lower() for n in order]:
        return
    bak = write_ini_game_files(ini, order)
    print(f"\nMorrowind.ini's [Game Files] updated from {LOAD_ORDER_FILE} ({len(order)} plugins; previous ini kept "
          f"as {bak}), so MGE XE's distant land generator and other tools see this load order.")


def main(argv=None):
    MT.install()
    global MAIN_DEPTH
    MAIN_DEPTH += 1
    finished = False
    try:
        rc = _main(argv)
        finished = True
        return rc
    finally:
        MAIN_DEPTH -= 1
        if MAIN_DEPTH == 0:
            if finished:
                # only a run that ended normally writes its load order into Morrowind.ini; after a crash or
                # Ctrl-C the list may be half done (mwdialog_load_order.txt keeps it; --play writes it in)
                try:
                    apply_load_order_to_ini(TOP_ARGS)
                except (OSError, UnicodeError) as e:
                    print(f"\nCould not update Morrowind.ini's [Game Files]: {e}", file=sys.stderr)
            elif TOP_ARGS is not None and LOAD_ORDER_WRITTEN:
                print(f"\nThe run stopped early: Morrowind.ini's [Game Files] was NOT updated from "
                      f"{LOAD_ORDER_FILE}.", file=sys.stderr)
            LOAD_ORDER_WRITTEN.clear()
            try:
                cap_fix_log(TOP_ARGS)
            except OSError as e:
                print(f"\nCould not trim the fix log: {e}", file=sys.stderr)


if __name__ == "__main__":
    rc = main()
    if PLAY_REQUEST:
        play_rc = launch_game(PLAY_REQUEST[0])
        rc = rc if play_rc == 0 else play_rc
    # started from Explorer or a shortcut (the batch file says so): keep the window open - but only when the
    # output is on screen; redirected to a file, nobody would see the prompt and it would just hang
    # (and not after starting the game: there's nothing to read, the game is what you're waiting for)
    if os.environ.get("MWDIALOG_PAUSE") and not PLAY_REQUEST and not GAME_STARTED and sys.stdout.isatty() and sys.stdin.isatty():
        what = {0: "done", 1: "done, issues reported"}.get(rc or 0, "failed")
        try:
            input(f"\n==== finished: exit code {rc or 0} ({what}) ====\nPress Enter to close this window.")
        except (EOFError, KeyboardInterrupt):
            pass
    sys.exit(rc)
