LuaJIT syntax checker
=====================

This directory contains a local x64 build of LuaJIT 2.1, built from the
official LuaJIT repository at commit `c4b1e2f73a2e10fbcc637fcec474f639c38daafe`.
The upstream source repository is https://github.com/LuaJIT/LuaJIT.

The upstream MIT license and copyright notice are included in `COPYRIGHT`.
Keep that notice with the executable and DLL when redistributing this tool.

MWManager's Lua linter uses this executable only as a syntax checker when
`luac`/`luac5.1` is not available; it compiles temporary source to the Windows
`NUL` device and does not execute mod scripts.

To rebuild on Windows, use the x64 Visual Studio C++ tools and run
`src\msvcbuild.bat` from a checkout of the pinned source commit.
