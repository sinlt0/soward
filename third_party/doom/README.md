# Doom engine for the Games app

`doom.wasm` is built from `wrapper.c` and `PureDOOM.h` with `build.sh` (clang with the wasm32 target, no libc, no emscripten).

- `PureDOOM.h` is the PureDOOM single-header port of the Doom source code by Daivuk, licensed GPL-2.0 (see `LICENSE.PureDOOM`). One change was made: the check that refuses `-file` add-on WADs with the shareware IWAD was removed, so custom WADs work with the bundled Doom 1.
- `wrapper.c` is the small host layer: a memory allocator, a file system that calls back into JavaScript, a virtual clock that advances exactly one game tick per `step`, and the exported functions the Activity uses.
- `doom1.wad` is the shareware version of Doom 1 from id Software, which may be redistributed unmodified.

The compiled engine and WAD are copied to `dashboard/static/activity/` by `build.sh`.
