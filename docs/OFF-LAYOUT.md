# Off layout: one place for everything the tools set aside

Status: specification, implemented by `mwdialog_offlayout.py` (shared code) and `vortex_tidy.py`. Decided by dej
(dejunai). Applies to vortex_tidy, mwdialog_check, MWManager and the OpenMW converter (omw2mwse).

## 1. The layout

    <staged mod folder>\Off\<plugin>\<reason>\<path the file had in the mod>

* One `Off\` per staged mod. Managers never deploy it (MWManager keeps it in the staged folder), but Vortex
  deploys everything in staging, so every set-aside file sits under its `<plugin>` and `<reason>`.
* `<path>` is the file's path relative to the mod's folder, unchanged (`textures\tx\wall_n.dds`,
  `scripts\x\main.lua`). The reason folder holds paths and nothing else.
* Nothing else lives directly in `Off\`: no loose files, no reason folders, no `<path>` folders.
* One exception: the game install's own `Data Files\Off\` (files no mod owns) uses the same shape with a fixed
  owner name instead of a plugin (`Found at Setup`, `Official Add-Ons`); it is not a staged mod.

## 2. `<plugin>`

The mod's plugin stem, sanitised the converter's way (omw2mwse `mod_name_for`): every character that is not a
letter, a digit, `_` or `-` is removed; `OpenMWMod` when nothing is left.

One `<plugin>` per staged mod folder, chosen in this order:

1. the first plugin at the mod's root: `.esp`/`.esm` (names sorted without regard to case);
2. else the stem of the first `*.omwscripts` at the root (OpenMW-only mods: this is exactly the converter's
   `mod_name_for`, so `Off\wildlife_attacks_npc\OpenMW\` is the same folder for tidy and the converter), else
   the first `.omwaddon`/`.omwgame`;
3. else the first plugin already put aside in `Off\` (a disabled plugin);
4. else the mod's name (the staged folder name without Vortex's id, version and stamp), sanitised.

Several plugins: the first one decides, for the whole mod. A folder under `Off\` that is already in the layout
(only reason folders in it, plus the MAX_PATH list) and is the only one is kept as the owner whatever its name,
so a mod's owner does not change when its plugins do. Matching of every name is case-insensitive; names are
written exactly as in this document.

## 3. `<reason>`: the fixed list

Lower case except `OpenMW`. Spelled out, one meaning each. No other reason may be written; a tool that needs a new
one adds it here and to `mwdialog_offlayout.REASONS` first.

| reason | what is in it | older spellings it replaces |
|---|---|---|
| `OpenMW` | OpenMW-only content (scripts, l10n, a whole OpenMW package) that Morrowind cannot use | `openmw` |
| `normal maps` | normal-map textures; only OpenMW uses them | - |
| `broken` | an asset that can't be repaired (empty, wrong format, truncated, crashes the game); a stand-in took its place | `damaged assets` |
| `orphaned animations` | animation files whose model exists nowhere | `orphan`, `orphaned` |
| `unused assets` | textures and sounds nothing refers to, and empty files | `unused` |
| `ascii` | a file whose name has non-standard (non-ASCII) characters; the original under its old name | `names`, `non-ascii`, `reprocessed filenames` |
| `shortened paths` | the original of a file whose too-long path was shortened (or that was edited to name the short path) | `long paths`, `longpaths` |
| `converted sounds` | the original of a sound that was converted or repaired | `reprocessed sounds`, `sound` |
| `converted textures` | the original of a texture that was converted or reduced | `reprocessed textures`, `textures` |
| `converted splash screens` | the original of a splash screen that was converted | `splash screens` |
| `fixed text keys` | the original of an animation or model whose text keys were fixed | `reprocessed unix line joins`, `text keys` |
| `fixed texture paths` | the original of a model whose texture paths were fixed | `reprocessed texture paths`, `texture paths` |
| `plugin repairs` | a plugin as it was before a tool changed it (masters added, header or dead references fixed) | `added masters`, `cell references`, `original plugin headers`, `plugin-repair`, `plugin-repairs`, `reprocessed plugin headers` |
| `repaired originals` | the original of a file a tool changed, when no more specific reason applies | `converted`, `repair` |
| `lua repairs` | a Lua file as it was before a tool patched it | `luarepair`, `luarepairs` |
| `disabled plugins` | plugin files (and their archives) put aside by hand or by a tool so they don't load | - |
| `superseded plugins` | plugin files a newer install replaced | - |
| `duplicate omwaddon` | an .omwaddon kept because its .esp name was already taken | `openmw-addon-duplicate` |
| `redundant splash sources` | splash images a better copy made redundant | `splash` |
| `executables` | programs, libraries and scripts a mod shipped; never deployed into Data Files | - |
| `packaging metadata` | installer and packaging files that are not part of the mod | - |
| `packed into bsa` | loose files that were packed into a BSA archive | `bsa packed`, `bsa-pack` |
| `unused fomod options` | plugin choices of FOMOD options that were not installed | `fomod option plugin choices` |
| `replaced files` | files an install replaced | `replaced` |
| `protected textures` | textures kept when an install would have replaced them | - |
| `altered assets` | files a plugin deployed that changed afterwards, kept instead of deleted | - |

Reasons are never nested (`Off\<plugin>\<reason>\<reason>\` does not exist: a folder inside a reason is part
of a `<path>`, even when it is called `sound` or `broken`).

## 4. Older layouts tidy recognises, and what it does

vortex_tidy plans (and `--apply` does) the migration for every staged mod it handles; it is part of the same plan
and the same journal as every other move. A mod on the blacklist, or one that installs into the game folder, is
not touched.

| older layout | becomes |
|---|---|
| a loose file in `Off\` (plugin, `.bsa`) | `Off\<plugin>\disabled plugins\<file>` |
| a loose `.omwscripts` / a program (`.exe .dll .bat .cmd .pl .py .ps1 .sh .asi .jar`) in `Off\` | `OpenMW` / `executables` |
| `Off\<older reason>\<plugin>\<path>` (`normal maps`, `broken`, `names`, `sound`, `textures`, `unused`, `orphaned`, `longpaths`, `text keys`, `texture paths`, `splash screens`, `added masters`, `cell references`, `converted`) | `Off\<plugin>\<reason>\<path>`, reason by the table above |
| `Off\OpenMW\<mod>\<path>` (hybrid mods; the older tidy) | `Off\<plugin>\OpenMW\<path>` |
| `Off\<path>` and `Off\<name>\<path>`, the path starting at a game folder (`meshes\`, `textures\`, `sound\`...) | `Off\<plugin>\repaired originals\<path>` |
| `Off\<name>\<plugin file>` | `Off\<plugin>\disabled plugins\<file>` |
| `Off\<name>\<older reason spelling>\` (MWManager's `Damaged assets`, `Unused assets`...) | `Off\<plugin>\<reason>\` |

Left alone, with one NOTE per mod: anything else (a loose file of another type, an unknown folder), a folder
already in the layout, anything an omw2mwse manifest lists (the converter places those), and a mod's legacy
`Off\OpenMW\` while that mod holds converter output (the converter relocates it on its next run). Those
`Off\OpenMW\<mod>\` folders of an OpenMW-only mod that is not converted go with the mod's whole package
to `Off\<plugin>\OpenMW\`.

Only the older reason names at the top of `Off\` (`Off\sound\<plugin>\...`) are told apart from a path folder
(`Off\sound\...` is a path): it is the reason layout only when everything in it is a folder holding a game
folder.

## 5. Collisions

A destination that exists, or that another move of the same plan uses, is not overwritten: a folder is merged
(its entries move one by one), a file gets ` (2)`, ` (3)` before its extension. Case differences between the
names are not differences. Nothing is deleted; a folder is removed only when empty.

## 6. MAX_PATH

A path over 259 characters (MAX_PATH 260 with the closing NUL) is never moved, and neither is a file whose new
path would be: moving it would only make it worse. Such a file stays where it is, and
`Off\<plugin>\max_path_too_long.txt` lists it: one path per line, relative to the mod's staged folder (backslashes),
sorted without regard to case, no repeats, UTF-8. The list is the offenders of this run plus earlier lines whose
file is still there and is still too long, either at that path or at its Off destination (a short source whose
copy under `Off\<plugin>\...` would exceed MAX_PATH stays listed, so tidy and the converter agree and a refresh
is idempotent). A run that finds nothing new rewrites nothing, and the file is removed when nothing is too long any more. A folder with such a file inside is
moved piece by piece; the rest of it moves.

## 7. Journal and undo

Every move, including the migration, is journaled before it is made (`vortex_tidy_journal.jsonl`) and one
`--undo` reverses the whole last `--apply` in reverse order, byte for byte (files are renamed, never copied).
The MAX_PATH list is journaled with its previous text; `--undo` puts that text back, or removes the file when
there was none (`--undo --force` also overwrites a list that was edited since). The migration is idempotent: what has
moved is no longer an older layout, so a second plan lists nothing.

## 8. Who writes what

* `mwdialog_generated.off_dest` / `backup_asset_original`: originals of asset repairs, broken, unused, orphaned,
  names, long paths, text keys, texture paths, masters (via `mwdialog_offlayout.off_path`).
* `vortex_tidy`: OpenMW (hybrid and whole packages), normal maps, broken dummies, the migration, the MAX_PATH list.
* MWManager and omw2mwse: see the change lists in the hand-over notes (owner = plugin, the reasons above).
* Records that name an Off path (`mwdialog_unused_assets.txt`) keep working after a migration:
  `mwdialog_offlayout.relocated` finds the file where it moved to.
