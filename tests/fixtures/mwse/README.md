# MWSE fixtures

- `ExclusionsPage.lua`: MWSE's own `Data Files\MWSE\core\mcm\components\pages\ExclusionsPage.lua`, unchanged, as
  shipped since 2024-07-19 (github.com/MWSE/MWSE, MIT licence). Known Bugs KB3 and KB4 are written against it.
- `ExclusionsPage.paged.lua`: the same file after KB3 and KB4 (without the `localpatch` line luafix puts first).

Neither is deployed: luafix and vortex_tidy patch the player's own copy in place.
