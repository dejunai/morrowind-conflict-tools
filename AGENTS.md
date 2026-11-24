# Morrowind Conflict Tools
Language: Python tooling; Lua 5.1/LuaJIT for MWSE mods.
Purpose: Deeply review and improve the tools; extract cohesive reusable modules from `mwdialog_check.py` when useful.
Users: Morrowind players and maintainers of the conflict-tools workflow.
Distribution: Shared with MWManager; exclude private Regional Splash files, tests, and data.
Constraints: Preserve mod originals and backups. Directly repair third-party Lua only for confirmed bugs, with documentation and regression coverage. Do not implement automatic large-scale relocation or script recompilation.

# AI strategy
Use Haiku for simple tasks; Sonnet for main dev; Opus for complex arch or if Sonnet fails 2x.
Keep context low: Grep before Read, targeted reads only.

# Rules
Concise responses. No overengineering. No unrequested extras.