# MWRecompile 1.0.0

MWRecompile recompiles the MWScript in a Morrowind plugin from the command line,
without opening a window. It uses MWEdit's script compiler.

```
MWRecompile.exe MyPlugin.esp -d "C:\Games\Morrowind\Data Files" -o MyPlugin_fixed.esp
```

For every SCPT record it compiles the source text (SCTX) and writes new
bytecode (SCDT), a new header (SCHD: local counts and sizes) and a new local
variable list (SCVR). Record sizes are fixed up. Every other record is copied
byte for byte.

## Usage

```
MWRecompile <plugin.esp|.esm> [options]

  -o, --output FILE     write the result to FILE (default: overwrite the input
                        after copying the original to <input>.bak)
  --no-backup           do not make <input>.bak when overwriting in place
  -n, --check           dry run: compile and report, write nothing
  -k, --keep-going      write the file even if some scripts fail; failing
                        scripts keep their old compiled data (exit code 1)
  -s, --script ID       only recompile this script (can be repeated)
  --changed-from FILE   only recompile scripts whose source differs from FILE
                        (for example your unedited copy of the plugin)
  -d, --data DIR        folder to search for masters (can be repeated;
                        default: the plugin's own folder)
  -m, --master FILE     load exactly these masters, in order (can be repeated)
  --extra-file FILE     also look up IDs in this plugin
  --mwse                allow MWSE/MWEdit extended functions
  --no-tribunal / --no-bloodmoon   reject expansion functions
  --warn weak|default|strong       compiler warning level
  -l, --list            list every script and its status
  -w, --warnings        print compiler warnings
  --report FILE         write a tab-separated report, one row per script
  -q, --quiet           print errors only
```

Exit codes:
- 0: OK.
- 1: compile errors. Nothing is written unless you pass `-k`.
- 2: usage error, file error or missing master.

Errors are printed as `plugin: ScriptName: line L, col C: message`.

Masters are found by reading the MAST list in the plugin's header. MWRecompile
looks for them in the `-d` folders, without regard to case.

The output is written to a temporary file first and then moved into place, so a
failed run never leaves a half-written plugin. A script whose new compiled data
is byte-identical to its old data is left untouched.

## Validation (the vanilla masters, recompiled from their own source)

| Master       | Scripts | Compiled | Byte-identical to the CS output |
|--------------|---------|----------|---------------------------------|
| Morrowind    | 632     | 631      | 628 (99.5%)                     |
| Tribunal     | 263     | 255      | 254 (99.6%)                     |
| Bloodmoon    | 336     | 330      | 330 (100%)                      |
| **Total**    | 1231    | 1216     | 1212 (99.7%)                    |

Running `-k` over Bloodmoon.esm gives back a file that is byte-identical to the
original.

The 4 compiled scripts that do not match:
- **DagothUrCreature1, LorkhanHeart and EndGame (Morrowind.esm).** These are
  `PlayGroup` animation-group numbers. Morrowind.esm was compiled by the
  original, pre-Tribunal Construction Set, which used an older animation table.
  The Tribunal-era CS output (Tribunal's own EndGame) matches MWRecompile.
- **TestMoveRock (Tribunal).** In `if ( a - b < 30 )` the CS writes the `-`
  after the right-hand side. This is a CS bug that appears once in the vanilla
  data. MWRecompile writes the expression the normal way.

The 15 vanilla scripts that still do not compile are broken source that
the CS somehow accepted, for example:
- `if player->(GetItemCount ...)`
- `if [ ... ]`
- `<==`
- a stray `(` line
- a backtick inside a variable name
- `begin` used as a script name

With `-k` these scripts keep their existing compiled data.

## Construction Set quirks reproduced

Matching the CS byte for byte meant adding these behaviours to MWEdit's
compiler. Every change is marked `MWRecompile` in the source.

**Bug fixes**
- InsertScriptDataRef shifted data 2 bytes too far for quoted IDs.
- A stale optional-argument count position let a later function overwrite
  AiWander's idle count.
- Under GCC, error messages printed garbage. This came from passing CSString
  through varargs and is fixed with template wrappers.

**Lookups and ID types**
- IDs resolve to the record of the right kind: objects before dialogue topics
  of the same name.
- IDs are written using the record's own capitalisation.
- An expression argument's type letter comes from the record the ID actually
  names (` t` faction, ` d` topic, ` a` race, ` c` cell).
- IDs shorter than 4 characters are padded with NULs to 4 bytes.
- An ID argument that matches a variable name is still treated as an ID.

**Bytecode details**
- A comma before an ID argument is kept in expressions.
- A leading negative number in SET is written as `-1 N *`.
- The source spacing around comparison operators and numbers is kept, and
  `.75` is accepted as a number.
- `Random N` writes the CS's extra digits after the value.
- The AiWander/AiTravel "reset" byte is the text length of that argument.
- The AiWander idle count is set correctly.
- A variable passed to a numeric argument of a function that cannot take one
  becomes 0.
- A function nested in a statement's arguments becomes 0.

**Lenient syntax the CS accepts**
- `=` as a comparison.
- `if x == 1` without brackets.
- Extra arguments at the end of a statement, which are ignored.
- Text after `else` on the same line, which is ignored.
- `endif`, `else` and `elseif` that match no `if`, compiled as plain
  statements.
- Locals named like functions or keywords (`short move`, `short end`).
- Locals declared twice.
- A SET target that was never declared (written as `V 1`).
- Several `a.var` references on one line, and `a.var` in SET expressions.
- A bare topic ID inside an IF.
- A cell that does not exist, or an ID of the wrong kind, gives a warning
  instead of an error.
- The script name after `Begin` is taken as the first word on the line.
- ModRegion with 8 weather values; the CS pads the rest with 0.

Warnings for the lenient cases appear with `-w`.

## Known limitations
- The PlayGroup animation numbers follow the Tribunal-era table, not the
  pre-Tribunal one used for Morrowind.esm.
- Scripts that even the CS could compile only by accident (see the list above)
  are still rejected.
- MWSE extended functions are only available with `--mwse`.
- The masters must be available, because IDs, globals and remote locals are
  looked up in the plugin and its masters.

## Building from source

The tool was cross-compiled on Linux with mingw-w64, linked statically, with no
MFC. It needs GCC 14 g++-posix and GNU make:

```
make                # builds MWRecompile.exe
```

Source layout:
- `vendor/`: the MWEdit sources used, namely `Common/`, `esm/` and the
  `project/` script compiler, function tables and data files.
- `cli/stub/`: small headless stand-ins for the MFC/GUI pieces (StdAfx,
  options and the document).
- `cli/src/main.cpp`: the command-line front end and the ESP reader and
  writer.
- `cli/tools/`: Python scripts used for validation, such as comparing scripts
  between two ESMs and building test plugins.

## Credits

- **MWRecompile** by dej (dejunai), built with Grok Bot (Code Review agent).
- Based on **MWEdit 0.7.0** by Walrus Tech
  (https://github.com/Walrus-Tech/MWEdit, tag 0.7.0, commit `6dfaf72`).
- Original **MWEdit** by Dave Humphrey (UESP).

The script compiler itself is MWEdit's. MWRecompile's changes to it are
marked `MWRecompile` in the source and listed in CHANGES.md
(CHANGES-vendor.diff has the full patch).

## License

MIT, so you are free to use, copy, modify and redistribute it. See
LICENSE.txt.

- MWRecompile's own code and its changes to MWEdit:
  Copyright (c) 2026 dej (dejunai), MIT.
- The MWEdit code it is built on stays under its original MIT licence,
  Copyright 2025 Walrus Tech. That notice is kept in LICENSE.txt and
  `vendor/LICENSE-MWEdit.txt`, and must be kept in any copy you redistribute.
