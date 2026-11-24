# MWRecompile changes to MWEdit

**Upstream:** MWEdit 0.7.0 by Walrus Tech, commit `6dfaf72` (MIT licence). MWEdit was originally written by Dave Humphrey.

Every change in the source is marked with a `MWRecompile` comment. The complete patch against upstream is in `CHANGES-vendor.diff`.

**Changed upstream files:**
- `Common/dl_base.h`
- `Common/String/SString.cpp`
- `project/EsmScriptCompile.cpp`
- `project/EsmScriptCompile.h`
- `project/EsmScriptDefs.cpp`
- `project/EsmScriptFuncs.cpp`

All other files in `vendor/` are upstream copies, unchanged.

**Files not copied:**
- The MFC/GUI parts of MWEdit.
- `esm/EsmWinUtils*` and `mwcommon*`.

`cli/stub/` replaces them (see section 4).

---

## 1. Bug fixes

- **`EsmScriptCompile.cpp: InsertScriptDataRef`.** The quotes around an object reference are now stripped before the `memmove`. Upstream shifted the data 2 bytes too far for `"quoted id"->Func` and left stale bytes in the output.

- **`EsmScriptCompile.h/.cpp: AddError / AddWarning / AddMessage`.** These were renamed to `...Raw`, and variadic template wrappers (`MwrArg`) now pass `CSString` arguments as `const char*`.
  - **Why:** MSVC passes a `CSString` through `...` as its string pointer. GCC passes the object itself, so every error message came out garbled.
  - **Added:** `GetLastErrorMessage()`.

- **`EsmScriptCompile.cpp: ParseFuncEnd`.** After the optional-argument count is written, `m_FuncOptCount` and `m_FuncOptPos` are reset.
  - **Why:** without the reset, a later function call, for example one inside an IF expression, overwrote AiWander's idle count with a wrong value such as `fd ff`.

- **`EsmScriptCompile.cpp: ParseFuncEnd` (AiWander, opcode 0x10F9).** The idle count is now the number of idle shorts actually written, and is never negative.

- **`Common/String/SString.cpp` (`s_pSDataNull`, `s_pSStringNull`).** These are now compile-time constants.
  - **Why:** GCC initialised them at run time. A global `CSString` in another file could be constructed first and end up with a NULL buffer.
  - **Effect:** at exit, its destructor freed address -8. Real Windows aborts on that with heap corruption 0xC0000374; Wine did not catch it.

- **`Common/dl_base.h`.** Under `#ifdef MWRECOMPILE`, `DEFINE_FILE()` expands to nothing.
  - **Why:** this avoids a duplicate `ThisFile` symbol when the code is linked as a single console exe.

## 2. Reproducing the Construction Set's output byte for byte

Each of these was checked against the vanilla Morrowind, Tribunal and Bloodmoon scripts.

### Looking up IDs

- **`EsmScriptCompile.cpp: InsertScriptDataRef`, `ParseVarRef1`.** Two changes:
  - The ID is written with the case of the object record's own ID (via `FindObjectRecord`).
  - `Foo.var` resolves to the object record first, then to a script, then to any record. Upstream could pick a dialogue topic with the same name.

- **`EsmScriptCompile.cpp: MwrRefTypeForID` (new), used by `MwrOutputFuncArgID`.** The type letter written for an expression argument comes from the record the ID really names:
  - ` t` for a faction, ` a` for a race, ` d` for a dialogue topic;
  - ` d` again for a GetPCCell name that is not a cell but is a topic;
  - ` d` for `GetPCRank "House Telvanni"`.

- **`EsmScriptCompile.cpp: MwrOutputFuncArgID` (new; replaces `OutputFuncArgStrSym` and `OutputFuncArgSym`).** IDs shorter than 4 characters are NUL-padded to 4 bytes, for example `GetRace "Orc"` and `StartCombat Ken`.

- **`EsmScriptCompile.cpp: CheckFuncArg`, `MwrIsIDOnlyArg`, `OutputFuncArgGlobal`, `OutputFuncArgLocal`.** An argument that only accepts an ID is written as an ID even when a variable has the same name, as in `StartScript MatchMakeGoval` and `StopScript Contract_Calvus`.

### Commas, spacing and numbers

- **`EsmScriptCompile.cpp: ParseFuncComma`, `MwrOutputFuncArgID`, `OutputFunction`, `OutputFuncArgNum`, `GetNextToken`.** A comma typed before an ID argument is kept, as in `X<op>, r<len>Player`. Commas before numeric arguments are dropped. This uses a new flag, `m_MwrPendingComma`.

- **`EsmScriptCompile.cpp: ParsePushToken`, `OutputSet`, `OutputIf`, `OutputElseIf`, `OutputWhile`.** A leading negative number in SET is written as `-1 N *`. Elsewhere it stays `-N`.

- **`EsmScriptCompile.cpp: ParsePushToken` (NUMBER), `OutputIfRelOp`, `OutputIfRNumber`.** The source spacing in IF expressions is kept: `<=256` stays `<=256`. A number written as `.75` follows the operator with no space.

- **`EsmScriptCompile.cpp: GetNextToken`.** `.75` is tokenised as a number.

- **`EsmScriptDefs.cpp: GetESMScriptOpToken`.** A lone `=` is a comparison operator and is written as `=`.

### Function arguments

- **`EsmScriptCompile.cpp: OutputFuncArgNum` (Random, opcode 0x1021).** After the short value, the CS writes the rest of the number's text after its first character, so `Random 101` becomes `101,"01"`.

- **`EsmScriptCompile.cpp: OutputFuncArgNum`, `ParseFuncEnd` (reset byte).** The AiTravel/AiFollow/AiWander reset byte is the text length of that argument:
  - `0` → 1, `90` → 2, `180` → 3;
  - for AiWander, it is the length of Idle2.

- **`EsmScriptCompile.cpp: MwrOutputZeroArgForVar` (new), `OutputFuncArgGlobal`, `OutputFuncArgLocal`.** A variable passed to a numeric argument of a function that cannot take variables is written as zero, as in `PlaceAtPC id 1 distVar 1`. This is skipped with `--mwse`.

- **`EsmScriptCompile.cpp: GetSymbolToken`.** A function used inside a statement's argument list is written as `0`. Examples: `RemoveItem Gold_001 GetPCCrimeLevel` and `SetAngle, y, GetStartingAngle, y`.

- **`EsmScriptFuncs.cpp: ModRegion`.** The 9th and 10th weather values (snow and blizzard) are optional. The CS pads them with 0.

## 3. Lenient syntax the Construction Set accepts

Each of these produces a warning, shown with `-w`.

**IF blocks**
- **`l_IfBlock`, `l_ElseIfBlock`, `l_WhileBlock`, `ParseTableOne`.** The brackets around an IF, ELSEIF or WHILE condition are optional: `if x == 1`.
- **`l_MwrTopStatementBlock`, `l_MwrStrayElseIfBlock`, `l_MwrStrayElseBlock` (new), with `MwrOutputStrayEndIf`, `MwrOutputStrayElse`, `MwrOutputStrayElseIf`.** An `endif`, `else` or `elseif` with no matching `if` at script level is compiled as a statement, as the CS does.
- **`OutputElse`.** Text after `else` on the same line is ignored. `else set x to 8` compiles as an empty `else`.

**Arguments and references**
- **`ParseFuncEnd`, `OutputLineFunction`, `MwrOutputRefLineFunction` (new; `l_ObjRefFuncBlock`).** Extra arguments after a statement-level function are ignored. Examples: `disable "id"`, `StopCombat Player`, `AiFollow Player 0 0 0 0 0 0`.
- **`GetOperatorToken`.** Several `a.var` references are allowed on one line. Only a second `->` is still an error.
- **`l_RightIDBlock`, `ParseVarRef1`.** `a.var` is accepted in a SET expression (`set a.x to a.x + 1`). The SET length position is kept.
- **`MwrParseIfSymbol` (new; `l_IfRFactorBlock`).** A bare ID in an IF expression (`if ( BM_BearHunt1 == 0 )`) is written as a typed reference, for example ` d<len>ID`.
- **`CheckFuncID1`.** An unknown cell name, or an ID of the wrong kind, gives a warning instead of an error.

**Local variables**
- **`ParseNewLocalVar`, `MwrIsIdentifier`.** Locals can be named like functions or keywords (`short move`, `short end`, `short journal`) and can be declared twice. The declared name keeps its case even when a global has the same name. This uses a new member, `m_MwrRawToken`.
- **`GetSymbolToken`.** A local with a function's or keyword's name counts as the local everywhere except at the start of a statement or after `->`. In those two places the function wins.
- **`MwrParseSetSymbol` (new; `l_SetVarBlock`).** `set undeclared to N` is compiled as `V 01 00`, as the CS does.

**Script name**
- **`MwrOutputBegin` (new; `l_MainBlock`), `GetNextToken`.** The script name is the first word after `Begin`, and the rest of that line is ignored. Examples: `begin changeWater_-550_400`, `Begin Float`, `Begin Museum RobeLich`.

## 4. Headless and no-MFC stand-ins (`cli/stub/`, new files)

| File | Purpose |
|---|---|
| `project/StdAfx.h` | Replaces the MFC precompiled header; includes `windows.h`, `tchar.h` and the C runtime instead |
| `Windows/WinUtil.h` | Empty stand-in for the GUI helper header |
| `project/EsmGlobOptions.cpp` | Supplies the `GetEsmOpt*()` settings from command-line options (`g_MwrOptions`) instead of the registry or GUI. Defaults: extended functions off, Tribunal and Bloodmoon on, default warning level |
| `project/EsmGlobOptions.h`, `EsmOptionsDef.h` | Upstream copies |
| `project/MWEditDoc.h/.cpp` | A headless `CMWEditDoc`: an ID index over the loaded masters and plugin (later files override earlier ones), plus `FindRecord`, `FindRecordCarryable`, `GetGlobal` and the new `FindObjectRecord` (which prefers placeable object types) |
| `cli_options.h` | Command-line option struct |

## 5. Command-line front end (`cli/src/`, new)

`main.cpp` reads and writes the ESP directly.
- Only SCPT and TES3 records are parsed; everything else is copied byte for byte.
- Masters are found from the TES3 MAST list, by case-insensitive search of `-d` folders, or given explicitly with `-m`.
- Masters and the plugin are loaded through MWEdit's `CEsmFile`.
- Scripts are compiled in two passes. Pass 1 applies the new locals, so `Foo.var` sees them.
- Line endings are normalised to CRLF before compiling.

**Writing changed scripts**
- Subrecords are written in CS order: SCHD, SCVR, SCDT, SCTX.
- The original SCHD name bytes are kept.
- SCVR is left out when the script has no locals.
- A script whose output is unchanged is not rewritten.

**Safety**
- The output goes to a temporary file, which is then moved into place.
- When overwriting in place, a `.bak` copy is made.
- If any script fails, nothing is written unless `-k` is given.

**Options:**
- **Output:** `-o`, `--no-backup`, `-n/--check`, `-k`
- **Which scripts:** `-s`, `--changed-from`
- **Masters and lookups:** `-d`, `-m`, `--extra-file`, `--mwse`, `--no-tribunal`, `--no-bloodmoon`, `--warn`
- **Reporting:** `-l`, `-w`, `--report`, `-q`
- **Debugging:** `--compile-text`

**Exit codes:** 0 OK, 1 compile errors, 2 usage or file error.

`thisfile.cpp` defines the single `ThisFile` symbol.

## 6. Build and validation tools (new)

- **`Makefile`:** mingw-w64 g++ 14, statically linked, `-DMWRECOMPILE`, cp1252 input.
- **`cli/tools/*.py`:** script extraction and comparison (`espscripts`, `compare`, `firstdiffs`, `diff1`, `dump`, `src`, `errlines`) and a test-plugin builder (`mkplugin`).
- **`val/run.sh`:** rebuilds the exe and compares against the vanilla masters.
