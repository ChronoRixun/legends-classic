# Owned Alchemy resource lifetime test

`online_assets_lifetime.cpp` loads the player's Alchemy DLLs in a native unit
process. It never starts XMen2.exe, creates a renderer, or reads desktop input.
Run it on a private Windows desktop, with copied DLLs and scratch files in the
test workspace. Do not redistribute those DLLs or generated model fixtures.

Build with MSVC Win32, at Idle priority and with one build worker:

```
cmake -S tests/native -B <scratch-build> -A Win32
cmake --build <scratch-build> --config Release -- /m:1 /nr:false
```

Each list is UTF-8/ASCII text containing one absolute IGB path per line. Include
the authored scene and every `ui/models/lc_o_*` model from one co-op menu's
package. Test Hub, Host setup, Join by code, Browse, both lobbies, and Party.
The test holds the complete set until close and then unloads it in reverse order.
It requires nonempty information lists, so failed loads cannot pass as flat memory.

```
online_assets_lifetime.exe <copied-dll-directory> <screen-model-list> 10 2 0
```

Arguments after the list are measured cycles, warm-up cycles, and whether a leak
is expected. After warm-up it asserts private-memory range <= 256 KiB and an
unchanged Windows handle count. On the fixed 060s resource fixtures both ranges
are exactly zero on every screen. A final `1` instead checks that memory grows
by more than 1 MiB; use only a few cycles for the negative control.

The 060s `static_model` bug shortened `igInfoList.count` but retained its old
capacity and serialized reference buffer. Alchemy retains every serialized
reference; list cleanup releases only `count` entries. The old Browse backdrop
retains about 8.5 MiB per load/unload; a buffer containing only the live scene
and matching count/capacity has flat memory. Synthetic unit coverage in
`test_menu_scene.py` pins the serialized ownership invariant without owned input.
The native test also covers the loader, typed-reference resolution and cleanup,
which the parser-only tests previously did not exercise.
