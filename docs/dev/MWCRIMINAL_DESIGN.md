# mwcriminal: inventory and implementation (updated 2026-11-22)

The inventory below describes the pre-consolidation setup. The old door-lock compatibility patch has been
retired; `mwcriminal` supplies its lock features, while duplicate doors are hidden with mwfloatfix's blacklist.

## 1. Inventory: who does each behavior today

Activation order today (higher runs first): mwpluginpatches doorLockCompatibility 9200 → abot Door Locks 9100 →
NAT book fix 100 → mwplainpaperfix 10 → Accidental Theft Protection 0 and Modern Lockpicking 0 → Revolving Doors Blocker -1110.

| Behavior (user's words) | Done today by | Edge cases handled there |
|---|---|---|
| Must sneak to steal | **Accidental Theft Protection** (mer, edited by us) | doors exempt when player is in an interior, door leads outside, or door unlocked; books exempt (read instead); blank scrolls not exempt; exclusion list (ids that may be taken standing); NPCs/containers/items all blocked when owned |
| Must sneak to pick locks | **doorLockCompatibility** (doors only) | key holder passes standing; sets abot's `ab01drlkbl` so abot lets Modern Lockpicking open; **locked containers are not gated at all** (ML opens them standing) |
| Lockpick minigame requires sneaking | same as above; minigame is **Modern Lockpicking** | ML skips when the player has the key, lock level 0, sneak+Shift/Alt (abot blacklist chord); no-pick / no-knife / impossible-lock messages |
| Companions and creatures don't affect detection | **mwcriminal** (absorbed from mwcompanionsneak) | follow/escort package, `friendlyActors`, Attend Me, or declared `companion` script variable; excludes guards and attackers; configurable creature/escort treatment and actor-ID blacklist; clears Stealth Overhaul suspicion; 0.35 s sweep and the detector/blacklist inspector |
| Read books standing, Take is red | **ATP** lets owned books open + **noAccidentalTheftBookFix** tints Take (or hides it) | only when not sneaking and no ownership access; MenuBook and MenuScroll; Take still steals if clicked |
| Can't be locked in an interior leading outside | **doorLockCompatibility** | unlocks the door on activation when source is a true interior and dest is exterior/behaves-as-exterior; abot already skips such doors |
| Owned doors locked in the evening | **abot Door Locks** | open 7–19; locks only loading doors into interiors; skips persistent, chargen, scripted LD/LCV doors (`dl_`, `_doorlock`, `ld_*lock`), lock level 0 and 1, doors the player/scripts changed first, same-cell non-trapdoors, ab01houses, dest names cave/tomb/sewer/ship/propylon/… ; needs same location prefix or a house/service/whitelisted name; 1-hour hysteresis; lock 38, bank/vault 58; tents/yurts never |
| Public places not locked | **abot** (by name and class) | publican / bed-renting NPC → open except 2–7; lighthouse/tower/castle pub-like; district/plaza/market/council hall cells pass through; guarded dest (jail, prison, district, bank) unlocked by day |
| Faction houses not locked to members | **abot** | faction member inside (not a guard) always opens, knocking at night |
| Knocking is default; opener moved to the door | **abot** | knock 17–22 (houses), any hour for pubs/faction; who answers: alive, enabled, not a dummy, not asleep, not a child, fight ≤ 75, disposition ≥ 33, within 3048 / 172 z of the dest marker; faction-rank greeting text; opener moved to marker + 72 forward, turned to face; position restored on `mobileDeactivated` (or `RA` when same place); knock sound `abot\knockdoor.wav` |
| Empty interiors not locked unless owned by a living NPC | **abot** `lockEmptyHouses` (houses only) + **doorLockCompatibility** "absent owner → lock 38" | doorLockCompat locks whenever the door's NPC owner isn't in the dest cell (alive or not: it doesn't check death) |
| NPC homes unlocked once the NPC is dead | **nobody** | abot ignores dead NPCs when looking for openers, so a dead owner's house stays locked |
| Plain paper skips the blank scroll window; owned needs sneak | **mwplainpaperfix** (ATP refuses blank scrolls standing) | blank = scroll type, no text after stripping tags, no `<img`; ids cached in config; moves itemData off the world ref before delete (save crash); marks stolen + triggers theft |
| Locked door plays the locked sound, optional notification | **doorLockCompatibility** (`LockedDoor`, "The Door is Locked") | doors only; containers get nothing extra |
| Keyrings | **abot** | key inside `g7_inventory_KEYS` / `invhlp_keyring` containers opens the door |
| Arrille's Tradehouse duplicate trapdoor | **mwfloatfix** blacklist | plugin conflict, not crime; the hardcoded patch was retired |

Out of scope (not on the list, stay as they are): Stealth Overhaul (detection model, stealth bar, sneak strikes,
guards spotting stolen goods, XP), Skillful Sneaking and M1PE sneak addon (movement), MoreAttentiveGuards,
Revolving Doors Blocker, Doors Anti Stuck, coast guard contraband (dialogue turn-in, not crime/locks), Modern
Lockpicking itself (it remains the minigame; mwcriminal only gates it).

## 2. Design

```
mwcriminal/
  main.lua    one activate handler (priority 9300), one detectSneak handler, one uiActivated(MenuBook/MenuScroll)
  core.lua    ownership, doors, detection, follower classification and blacklists
  interop.lua companion detection API and Stealth Overhaul suspicion clearing
  inspectorUI.lua detector inspector and actor-ID blacklist UI
  config.lua  master switch defaults off; old companion settings migrate once
  mcm.lua     feature switches, detection options, inspector and blacklist controls
```

- **Core** answers questions on demand at activation time (no per-frame handler, no repeating timer, no cache that
  grows for criminal/lock checks): ownership, access, residents, exits, public cells, keyrings, and detection state.
- The only state written: `ref.data.mwcriminalLocked = true` on doors **mwcriminal** locked, so it only ever unlocks
  its own locks (plugin and quest locks are left alone, except for the dead-owner and member rules). One local for the
  current knock opener (restored on `cellChanged`).
- **Activation, one pass, first match wins:**
  1. excluded id → leave to the engine.
  2. door, `interiorExit` on, exit → unlock, pass.
  3. door into an interior, `eveningLocks` on → apply lock rules (below).
  4. locked door/container: key → pass; sneaking (`sneakToPick`) → pass to Modern Lockpicking; standing →
     `knocking` (doors) else locked sound/notify, block.
  5. book: blank sheet + `plainPaper` → into inventory (owned: only sneaking, marks stolen + theft);
     owned + `readStanding` + not sneaking → open, flag for the red Take button.
  6. owned + `sneakToSteal` + not sneaking → block.
- **Lock rules for a door into an interior** (only doors with no lock, or with mwcriminal's own lock):
  public dest → unlocked; faction-owned and player meets the rank → unlocked; NPC owner dead → unlocked
  (also clears a plugin lock); no living NPC inside and no living NPC owner → unlocked; otherwise evening
  (outside 7–19) or NPC owner not inside → locked at 38 (58 for bank/vault names).
- **Detection:** `detectSneak` at priority 2000: followers, configured creature cases, and blacklisted actor IDs →
  `isDetected = false`, clear SO suspicion via its interop if installed. The absorbed 0.35 s sweep and inspector
  preserve their original behavior. Guards and actors fighting the player remain eligible to detect.

- **Blacklist (user, 2026-11-21):** Shift+activate adds the target to the blacklist (message box confirms) and
  mwcriminal then ignores it entirely (engine and other mods decide). Companion actor IDs have a separate blacklist;
  they do not accidentally suppress unrelated theft or door-lock features. Doors and containers are listed per reference
  (key: cell id + object id + position rounded to 64 units, since they don't move); items and actors by object id.
  The MCM has a Blacklist page listing every entry by name and cell with a Remove button each. ATP's and
  mwcompanionsneak's existing settings and IDs are imported once. Shift is also the default Run key, so Shift+activate while
  running adds an entry too; the message box makes that visible and the MCM undoes it.

## 3. Retiring the originals, one at a time

Each step: turn the mwcriminal switch on, turn the original's own MCM switch off (it stays installed), play, compare;
only then uninstall the original. mwcriminal logs one warning at `initialized` if a switch overlaps an original that
is still enabled.

1. `plainPaper` absorbs **mwplainpaperfix** and migrates its enabled and owned-paper settings.
2. `readStanding` replaces the retired **noAccidentalTheftBookFix**; `sneakToSteal` replaces **Accidental Theft Protection**.
3. `companionDetection` absorbs and retires **mwcompanionsneak**; its inspector, blacklist management, options,
   Attend Me/Stealth Overhaul interop, and sweep now live in mwcriminal.
4. `interiorExit` + `sneakToPick` + locked feedback replace **doorLockCompatibility** (retired, with the Arrille resolver).
5. `eveningLocks` + `knocking` → retire **abot Door Locks**

## 4. Dropped from the originals (say if any is wanted)

abot's scripted-door overrides (its per-door blacklist is replaced by ours, Shift+activate); abot's rotating greeting
texts (one line kept); mwplainpaperfix's saved blank-id list; NAT fix "hidden" Take mode (red only, per the user's words).
