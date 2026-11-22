# mwcompanions: inventory and design (updated 2026-11-22)

## 0. What is installed today

The three mods are not installed as released. They sit in one Vortex mod, **Companion Suite - MWSE**
(`<staging>\Companion Suite - MWSE`, made 2026-11-02 by an earlier agent). No download archive of any
of the three exists in `<downloads>`, so the suite is the only baseline (`LUA_EDIT_AUDIT.md` and
`LUA_MOD_CHANGES.md` list it as "no archive to compare against"). Edits found:

| File | Change | Source |
|---|---|---|
| `Easy Escort\main.lua` | gutted to a 12-line log shim; `interop.lua` emptied; `mcm.lua` never loaded (and would crash: it calls interop functions that no longer exist) | suite merge |
| `config\Easy Escort.json` | the 170-id ignore list is still there, but **nothing reads it** | — |
| `abot\Smart Companions\main.lua` | `companionBlacklist` (170 ids: 152 abotWaterLife creatures + 18 guards, ordinators and uniques; the same list as Easy Escort's JSON) prepended and checked first in `validFollower`; luafix A1 nil guards and log shim | suite merge, luafix 2026-11-11 |
| `AttendMeMWSE\config.lua` | `enableHUD = false` (HUD Companion Health Bar is used instead); same 170-id blacklist | suite merge |
| `AttendMeMWSE\followers.lua` | `isGuard()` (isGuard flag, **class id/name contains "guard"**, MoreAttentiveGuards follower); safe `companion` read (`scriptHasLocal`, `instanceScriptLive`, never on creatures, never on Immersive Travel `rfuzzo_noscript` refs) | AG 2026-11-15 (BUGS #30, audit "overreach"), crash fixes |
| `AttendMeMWSE\main.lua` | `mobileActivated` kept light (no script-local reads); HUD destroyed on cellChanged (interior↔exterior CTD) | crash fixes |
| `AttendMeMWSE\recruit.lua` | luafix A1 | luafix |
| `config\AttendMeMWSE.json` (user) | `teleportFollowers = false`, `checkFollowersEveryMs = 1000`, hotkey Ctrl+O, `pickpocketFailCombat = true` | user |
| `config\abotSmart_Companions.json` (user) | `warpDistance = 2000`, `warpLevitate = 2`, `followersResiliency = 2`, `scanInterval = 0.35`, `fixAnim = true` | user |

Our own mods that touch companions: **mwcriminal** owns stealth detection (the former **mwcompanionsneak** code,
inspector, blacklist and settings are fully absorbed there), **mwteleportguard** (defers dialogue `Player->PositionCell` and moves companions along with
`teleportCompanions`), **mwpluginpatches** `autoStartup` (MCA_NoCompanions global) and `jiubDelay` (quest timing). None
of these warps or commands followers; they stay as they are.

Not installed: abot's Scenic Travel plugins (`ab01boSailAbility` etc. never exist), so Smart Companions' scenic
travelling does nothing here. Installed and relevant: abotWaterLife (+TR addon), Immersive Travel (rfuzzo),
MoreAttentiveGuards (celediel), Sails and Sales, HUD Companion Health Bar, Companion Leveler, CompanionCombatCommunication.

## 1. Inventory: who does each behavior today

| Behavior | Done today by | Edge cases handled there |
|---|---|---|
| Who counts as a follower | **Smart Companions** `validFollower` (and Attend Me `isFollower` for its menu) | follow/escort package targeting the player, or `companion = 1`; blacklist first; can't move / fatigue ≤ 0 / dead → no; guards with a follow package → no (MoreAttentiveGuards gives them a temporary follow); `ab01*` creatures and scripts → no, except `ab01guguarpackmount`; dummies/mannequins (invisible race, dummy meshes) → no; wander + one-time-move companions → yes |
| Reading `companion` safely | **Attend Me** `getCompanionVar` | never on creatures (Sails and Sales, water-life native crash), never when the instance script is stripped (Immersive Travel passengers, `rfuzzo_noscript`), only if the script declares the local. Smart Companions' `isCompanion2` (used by the voice mute) reads `context.companion` **unguarded** |
| Warp to player when far | **Smart Companions** `warpFollowers` (repeating timer, 0.48–0.58 s), any follower, 2000 units | not while travelling; companions and summons not warped back while fighting; placed in an arc behind the player, on pathgrid nodes when possible; z aligned; mount riders get a smaller bound box; Immersive Travel actors skipped. Attend Me's warp is off (user), Easy Escort's is gone |
| Follow through doors / cell change | **Smart Companions** `cellChanged` → `autoMove` | skipped while travelling; position history cleared on interior↔exterior; engine also moves AI-follow actors itself |
| Levitation and water walking while warping | **Smart Companions** (`warpLevitate = 2`, `warpWaterWalk = 2`) | gives its own levitate / water walk spell to followers while the player levitates / water walks, removes it after; fixes `levitate < 0`; `clampLevitate` clamps constant levitate abilities |
| Water breathing, acrobatics, athletics, 0 alarm | **Smart Companions** fixes | NPC followers only |
| Escort quests | **engine** (AI escort package); Smart Companions only treats escorts as followers if `companion = 1`; Attend Me refuses to recruit someone with an escort package | `autoBurden` (off) would make escorts trivial |
| No friendly fire | **Smart Companions** `damage` + `spellResist` (option 4: any follower, no aggro) | player soul-trapping a follower still works |
| Resilient followers (collapse, not death) | **Smart Companions** (option 2: any follower) | 90 s collapse, health restored to 75 % (max 500) |
| Followers attack your enemies | **Smart Companions** `combatStarted` (option 1: companions only) | mannequin/practice-dummy attacks ignored |
| Mute Attack/Hello on cell change | **Smart Companions** `infoFilter` (option 1: followers) | uses the unguarded `companion` read (see above) |
| Wait / follow / wander / move / attack / loot / share / swap / pick lock / pickpocket | **Attend Me** command menu (Ctrl+O, mouse wheel) | job timers; Modern Lockpicking check; pickpocket failure may start combat (user: on, 33 %) |
| Recruit any NPC / dismiss | **Attend Me** recruit mode | not hostile (fight > 70), no escort package, living NPC only; `ref.data.attendMeCompanion` flag |
| Companion loots containers / opens doors on Alt+Activate | **Smart Companions** (`allowLooting = 1`, probes, lockpicks, Open spells) | value/weight ≥ 5, organic always, 384 units, no overburdening |
| Skip activating a follower while sneaking | **Smart Companions** | — |
| AI / transparency / encumbrance / looping-anim / const-enchant fixes on activate | **Smart Companions** | AI fix for companions only |
| Travel services (boats, striders) | **engine** moves followers on travel; Smart Companions' scenic travel is inactive (plugins absent) | Immersive Travel passengers are never moved |
| Dialogue teleports | **mwteleportguard** | stays separate |
| Health bars | **HUD Companion Health Bar** (Attend Me HUD off) | out of scope |

## 2. Conflicts our adjustments resolve (kept in mwcompanions)

1. **Three warpers** (Easy Escort, Attend Me, Smart Companions) → one. mwcompanions has the only warp.
2. **Guards on a temporary follow** (MoreAttentiveGuards) treated as companions → excluded by `isGuard` flag, the
   guard id list, and MoreAttentiveGuards' interop. **Dropped:** the "class name contains guard" match (the audit
   calls it too broad; it rejects real companions with a guard class). Say if it should stay.
3. **Native crash reading `companion`** on creatures and script-stripped refs → one safe reader, used everywhere
   (also by the voice mute, which today reads it unguarded).
4. **Water life following / being warped** → the 152 water-life ids, plus `ab01*` creatures, minus `ab01guguarpackmount`.
5. **Immersive Travel actors** → never warped or moved.
6. **Two HUDs** → none in mwcompanions; HUD Companion Health Bar stays.

## 3. Design (built 2026-11-21; scope: core only, user)

```
mwcompanions/
  main.lua     handlers (each returns at once while its switch is off), the 1 s timer, collapse and escort recovery
  core.lua     pure decisions: followerKind(mob) 0/1/2, isFollower, isCompanion, isEscort, isSelfDefense,
               companionVar(ref), isGuard(ref), isBlacklisted(ref), areFriends, shouldWarp, warpSpot
  config.lua   defaults: enabled = false, every feature false; blacklist imported once from the suite's 170 ids
  mcm.lua      Settings page (one Yes/No each + distance/time sliders), Blacklist page (Remove buttons)
```

- **Who is a follower** (`followerKind`): follow package on the player → follower (2 if `companion = 1`); escort
  package → only a companion; no package → only a companion; wander/travel (told to wait) → no. Never blacklisted
  ids, `ab01*` creatures (except the pack guar), guards (`isGuard` flag or MoreAttentiveGuards' current follower),
  dead or disabled actors. `companion` is read only on NPCs with a live instance script that declares it, and
  never on Immersive Travel refs.
- **State:** nothing cached. `ref.data` flags (collapsed; levitation/water walk we gave); a persistent recovery timer
  per collapsed follower; an in-memory list of escorts down right now (cleared on recovery and on load).
- **Timers:** one 1 s timer only while `warp`, `levitateWater` or `followerTraits` is on; a 0.5 s timer only
  while an escort is down. No `simulate`/`enterFrame` handler.

| Switch | Event | Replaces |
|---|---|---|
| `warp` (+ `warpDistance` 2000) | 1 s timer, `cellChanged` | Smart Companions autoWarp, autoMoveCC; Attend Me teleport; Easy Escort |
| `levitateWater` | 1 s timer | warpLevitate, warpWaterWalk |
| `followerTraits` | 1 s timer | 0 alarm, water breathing, acrobatics 150, athletics 220 |
| `noFriendlyFire` | `damage`, `spellResist` | noFriendlyFireDamage/Magic (any follower, no aggro), soul-trap exception |
| `resilient` (+ 90 s, 75 %) | `damage`, persistent timer | followersResiliency |
| `assist` | `combatStarted` | autoAttack (companions only; escorts never sent in) |
| `escortSelfDefense` | `combatStarted` | new (user): an escort fights only whoever attacks it |
| `escortProtection` | `damage`, 0.5 s timer | new (user): an escort can't die; fatigue drains to 0 instead, it gets up when nobody fights it or the player |
| `muteOnCellChange` | `infoFilter` (3 s after a cell change) | muteCC |
| `noSneakActivate` | `activate` | skipActivatingFollowerWhileSneaking |

- **Interop:** `require("mwcompanions.core").isFollower(mobile)` for mwcriminal's `companionDetection`.
  Attend Me is optional: mwcompanions recognizes its `attendMeCompanion` recruitment API, but respects Attend Me's
  Wait/Move/Wander orders. If Attend Me's automatic teleport is enabled, mwcompanions delegates warping to it;
  otherwise mwcompanions warps only actively-following Attend Me recruits.

## 4. Retiring the originals, one at a time

Each step: turn the mwcompanions switch on, turn the original's own option off (it stays installed), play, compare.
mwcompanions logs one warning at `initialized` when a switch overlaps a Smart Companions option (or Attend Me's
teleport) that is still on.

1. **Easy Escort**: nothing to replace (it is a no-op). Delete its three files and its JSON from the suite.
2. `warp` + `levitateWater` → Smart Companions autoWarp = 0, autoMoveCC off, warpLevitate/WaterWalk = 0.
3. `noFriendlyFire`, `resilient`, `assist` → the matching Smart Companions Fight options to 0.
4. `followerTraits`, `muteOnCellChange`, `noSneakActivate` → the matching Misc options off.
   Then Smart Companions is uninstalled.
5. **Attend Me stays** (command menu and recruit are out of scope, user 2026-11-21) with `teleportFollowers = false`.

## 5. Dropped from the originals (say if any is wanted)

- Smart Companions' scenic travelling (its plugins are not installed), Alt+Activate companion looting and lock use
  (Attend Me's Loot / Pick lock commands remain), AI / transparency / encumbrance / looping-anim /
  constant-enchantment fixes on activate, `clampLevitate` (it edits spell records), mannequin-attack ignore,
  pathgrid placement (the warp uses Attend Me's arc behind the player).
- A follower in an unloaded cell isn't warped (its mobile doesn't exist; the engine's door following still works).
- The "class name contains guard" test (section 2).
- A plain hit now collapses a follower only when it would kill; at half health only for magic (it can't be
  blocked). Smart Companions collapsed at half health for any hit.
