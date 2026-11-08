#!/bin/sh
set -e
cd "$(dirname "$0")"
clang --target=wasm32 -O2 -nostdlib -ffreestanding -mbulk-memory -fno-builtin \
  -Wno-everything -DDOOM_IMPLEMENT_ASSERT=0 \
  -Wl,--no-entry -Wl,--allow-undefined -Wl,--initial-memory=33554432 -Wl,--max-memory=134217728 \
  -Wl,-z,stack-size=2097152 -Wl,--strip-all -Wl,--export-memory \
  -o doom.wasm wrapper.c
cp doom.wasm ../../dashboard/static/activity/doom.wasm
cp doom1.wad ../../dashboard/static/activity/doom1.wad
