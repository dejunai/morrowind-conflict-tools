# mwsuite resume notes (2026-11-25)

Paused for usage limits. Credit: dej (dejunai).

## Done and pushed
- 66dcf71 MCM window buttons need a loaded game; safe open/close (6 mods).
- f95bce2 mwconsole (replaces Console Suite, Smart Console, MCC, ECC, Selection Details).
- 05a1d7c mweffectinspector removed; mwconsole owns showeffects; Alt+I opens Selection details.
- 6fe86e6 MWCA interop stub in mwpluginpatches (gated on consumer, default off); mwcriminal test fix.
- Verified: box LuaJIT tests all pass; repo pytest our tests pass.

## Left to do
- Deploy: on next lua tools sync to Steam, delete mwsuite\mweffectinspector\ and
  mweffectinspector-metadata.toml by hand (copy-over will not remove them).
- In-game checks: mwconsole checklist, Alt+I details + Show Effects, MWCA addons
  with Plugin Compatibility Patches on, Smart Heads on vampires/full helmets.
- Conflict Tools (owner, uncommitted WIP): OWN_MODS -> ownmods.json with
  mwconsole in place of mweffectinspector; MUSE DebugLog KB (cell/combat/interior/
  region.lua fail to load); --play prune of removed mods (files, toml, configs),
  retire mwpersonaleffects.json, savedCustomClasses config mapping.
- 92 remaining hand edits (survey /workspace/lua-survey) -> luafix rules or
  mwsuite intercepts; never patch third-party Lua directly.
- Offered, not answered: mwcriminal text box focus, mwexitguard Alt+F4 stacking.
- Optional: empty Smart Battle Music folder and Data Files\calm_ghosties_raw.lua.