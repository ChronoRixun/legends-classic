# Automaps: how XML1 and XML2 draw a zone's map, and the XML1 -> XML2 conversion

2026-09-29. Static trace with the existing Ghidra project (`research/characters/ghidra`, `run_decomp.sh`; the
decompiles are local and gitignored: `research/automaps/decomp_am*.c`) and the text
disassemblies `research/scripts/xml2_text.asm` / `xml1_text.asm`. Implementation: SPEC.md section 26,
`tools/xml1build/automaps.py`, `automaps_selftest.py`, validator V20.

## 1. What each game ships

| | XML1 (Xbox, default.xbe) | XML2 (PC, XMen2.exe) |
|---|---|---|
| data | `textures/automap/**/*.igb`: 125 textures (+ 9 at `textures/automap/` root for the Arbiter decks), one igImage each, 256 or 512 px square/half (36 x 512x512, 34 x 512x256, 33 x 256x512, 22 x 256x256), igImage pfmt 15 = 4x4 blocks of 16 bytes (DXT3/5), alpha opaque in every block | `Automaps/**/*.zam`: 109 files, 8-66 KB (`act0`..`act5`, `bonus`, `dr`, `e3` copies, `svs`, `work` test maps) |
| named by | world entity `automap_texture="nyc_alison/nyc1_1_1"` + `automap_offset="14 -18"` (in 175 of 196 zone XMLs; 16 give a full `textures/automap/...` path) | zone package entry `<zam filename="automaps/<act>/<area>/<zone>"/>`, last in the package after `boy` (464 packages) |
| look | grey-scale art: black = nothing, grey 80-111 = floors / streets / terrain, white 224-255 = outlines; a little dither (16-79) at street ends | vector: white triangle strips, alpha 0xcb (outlines, 24 units thick) and 0x32 (floor fill) |

`build/_jh2/Automaps` (any build before section 26) = XML2's 109 files copied with the base install; XML1 zone
packages had no `zam` entry, so the XML2 HUD drew nothing for them, and they precached the dead XML1 texture
(`texture textures/automap/nyc_alison/nyc1_1_1` in nyc1_1_1's package, 64-256 KB each).

Zones with no `automap_texture` (no map in XML1 either): the 13 mocap briefings, `mansion/man3/danger_room`,
`mansion/man4/grso_debriefing`, `mansion/man5/subbasement4`, `mansion/man5/subbasement5b`, `menu/main_back`,
`muir_is/muir3/muir_brig`, `nyc/alison/blackbird`, `xjet/blackbird_arbiter`. Shared textures: the mansion hubs
(`mansion/jugrnt/jugrnt01` x10, `mansion/subbasement` x10, `mansion/mansion2` x8, `mansion/hangar` x3,
`mansion/backyard` x3), the demo / `dr_mag2` / `astroid_m/visit1` copies of other zones.

## 2. XML1 (default.xbe, image base 0x10000)

- World entity parser 0xbefa0: `automap_texture` (0x3d4c08) -> world+0x8c (0x40 chars, ".png" appended when there
  is no extension, like XML2), `automap_offset` (0x3d4bf8) -> `sscanf "%f %f"` into world+0xcc / +0xd0.
- CHudAutoMap (RTTI `.?AVCHudAutoMap@@`; no CMenuAutoMap in XML1 - the map is a HUD overlay):
  - 0x1523b0 finds the world entity ("worldent"), copies +0xcc/+0xd0 to the HUD's +0x210/+0x214 and returns +0x8c;
  - 0x152690 builds the path: the name as is when it contains `textures/automap` or `textures\automap`
    (0x3dd388 / 0x3dd374), else `textures/automap/%s` (0x3dd360); loads it, stores width / height (+0x208 / +0x20c),
    fog grid dims 64 x 64 scaled by the aspect (+0x21c / +0x220, 0x42800000), +0x218 = 64 / max(w, h);
  - 0x1528c0 world -> map: `p *= 1/12` (0x3dd314 = 0.0833333), `p.x -= [+0x210]`, `p.y -= [+0x214]`:
    **texture column = x / 12 - u, row = y / 12 - v; 12 world units per pixel.**
  - 0x1524d0 / 0x152880 / 0x1528a0: reveal / test of XML1's own 64 x 64 fog grid.
- Verified with the zone nav (world coordinates): the XML1 nav cells of every enclosed map fall inside the texture's
  outlines with this transform (1.000 for 7 sample zones; 0.141 with the rows flipped, 0.490 with the offset
  negated; `automaps_selftest` T4). The streets of the nyc maps are open-ended, which is why the whole-disc median
  there is lower; the nyc1_1_1 overlay was checked by eye (nav paths between the outlines, the subway rectangle on
  the subway).

## 3. XML2 (XMen2.exe, image base 0x400000)

Classes (RTTI -> vtable): CAutomapPrecacher 0x69b050, CAutoMap 0x69d5cc, CAutomapGenerator 0x69db84, CHudAutoMap
0x69db8c, CMenuAutoMap 0x69e4c4, CAutomapPlayfield 0x69cd84 (+0x69cd74), HUD manager 0x69dca4 (singleton 0x81d7e0,
getter 0x59ee20, ctor 0x59e740; holds CHudAutoMap at +0x21efe*4 with the generator at its +0x20).

### 3.1 Loading (per zone)

1. Package entry kind `zam` (registered with the precacher table by 0x562bc0). CAutomapPrecacher slot 0 0x561420:
   `FUN_00592520(name, 0, ".zam")` (0x69b0bc) appends the extension, then HUD vt+0x100 (0x59eca0) -> **0x5a02f0**.
2. Loader 0x5a02f0 (this = CHudAutoMap part of the HUD): frees the previous zam (pool 0x14), gets the file size
   through the file system (0x5642d0 vt+0x34), allocates (0x5605e0, pool 0x14, tag 0x36), reads it (vt+0x30),
   requires `*(s16*)data == 9`, keeps pointers to origin x (+2) and y (+4), tells CAutoMap the fog origin
   (vt+0x30 with origin * 240.0 (0x69ddf4)), vertices at +8, grid at `8 + 8n`, lists at `0x1a4c + 8n`; then walks
   the lists in file order and replaces every grid entry equal to the list's ordinal with its pointer
   (0x5a0400..0x5a0429; loop bound 0x1a44 = 41 * 41 * 4). Any bound check failing frees it (0x5a0020): no map.
3. Nothing reads the world's `automap_texture` / `automap_offset` (parsed at 0x4c7f90 into world+0x8c / +0xcc /
   +0xd0, like XML1; no getter, the HUD code never touches the world entity; the 14 XML2 zones that still carry an
   `automap_offset` are leftovers).

### 3.2 `.zam` format

```
s16 version = 9
s16 origin_x, origin_y          in 240-unit cells (world = origin * 240)
s16 n                           vertex count
n x { s16 x, s16 y, u32 ARGB }  world units; alpha = intensity (retail: 0xcbffffff lines, 0x32ffffff fill)
u32 grid[41 * 41]               index = cell_x * 41 + cell_y; value = ordinal of the cell's list, 0xFFFFFFFF none
lists until EOF: { s16 count, s16 vertex_index[count] }   one triangle strip per cell, degenerate joins inside
```

Checked on all 109 retail files: every one parses and re-packs byte for byte; 18,781 of 18,789 lists have their
vertex centroid inside the cell the grid gives them (x = index / 41, y = index % 41; the other 8 are authoring
sloppiness); 88% of retail coordinates are multiples of 12 - Raven built them from 12-unit-per-pixel images, the
same scale as XML1's textures. Example (act4/newyork/newyork2): origin (-1, 5), 1,577 vertices, 202 lists; list 0 =
cell (0, 16) = x -240..0, y 5040..5280: a strip of dim fill quads 120 wide then a 24-unit bright wall band.

### 3.3 Drawing (every frame)

- Generator 0x59fa70 (CAutomapGenerator slot 0): locks the builder (vt+8 = 0x584010: position / colour / uv
  pointers, strides, **capacity - used** into 0x8a61bc), then for cell x in [px - r, px + r) and y in
  [py - r, py + r), clamped to [0, 40) (0x59fb23..0x59fb32: cell 40 is never drawn), grid index `x * 41 + y`
  (0x59fba3): before each list after the first it emits the previous list's last vertex and this list's first vertex
  with colour 0 (strip join), then every vertex of the list as (x - player.x, height, y - player.y) * scale, colour
  = white with the vertex alpha, where the fog applies: vertex in an unexplored fog cell -> alpha 0; explored but
  a neighbour 240 units away unexplored -> colour 0x000077 (0x59fef7); distance fade in the small map (mode 1).
  Anything beyond the capacity is dropped (`if (count < max)`). Unlock / draw vt+0x18(1, count).
- CProcGeometryBuilder draw 0x584720: prim 1 -> `igGeometryAttr` primitive 4 = **triangle strip** (0 -> 5 fan).
- The automap playfield is playfield type 5 (factory switch 0x584c60): CAutomapPlayfield (ctor 0x588fa0) with its
  **own builder of 0x2000 = 8,192 vertices** (0x584dc3). Types 0/3 share a 0x1000 builder, 1/4 a 0x1400 one, 2 has
  its own 0x100.
- Modes (HUD 0x5a0150, global 0x8a61c4; the map key cycles 0 -> 1 -> 2 at 0x5a04f0): 0 off; 1 small map: scale 0.05,
  radius 8 cells, icon size 16; 2 overlay and 3 pause-menu Automap (CMenuAutoMap 0x5afae0 -> HUD vt+0xa0(3)): scale
  0.175 (0.15 when a display flag, vt+0x50 of 0x5f6df0's object, is clear), radius 10 cells, icon 24. A draw window is therefore at most 20 x 20 cells.
- Icons (heroes, enemies, objectives, extraction points) are drawn separately (0x5a0bb0 -> HUD vt+0x4c).
- Retail's own worst window by this count: 9,934 strip vertices (act5/egypt/egypt2), i.e. some retail maps can lose
  far cells in the densest spot; the conversion keeps every XML1 zone under 7,700.

### 3.4 Fog of war and saves

- CAutoMap (singleton 0x815e98, getter 0x596890, vtable 0x69d5cc): 211 dwords of bits = 82 x 82 cells of 120 units
  (1/120 = 0x6e433c) from the zam origin, flag byte +0x354 bit 0 = enabled.
  vt: +0x04 reset, +0x08 data pointer, +0x0c load 211 dwords (0x596600), +0x10 fog all (0x596620), +0x14 / +0x1c
  test / reveal a circle (0x5966d0 with 1 / 0), +0x18 is-fogged at a position (0x596640), +0x20 reveal all
  (0x596830), +0x24 enable (0x596500), +0x28 fog all + disable (0x5964d0), +0x2c / +0x30 origin.
- 0x4664d0 copies the bits into the current-zone record at +0x5278 (the save / push-zone record); 0x465630 restores
  them; zone shutdown 0x484631 calls vt+0x28; the zone start path 0x4867e0 enables it and reveals all when the
  loaded zone is the current act's town centre (as read: game vt+0x274, the act's town-centre record, named
  through 0x468530's table, stricmp against the map's zone name) - hubs have no fog. The player's position reveals as he walks (0x42dbcc
  vt+0x1c). So a save keeps the fog of the zone it was made in; other zones start fogged. Nothing XML1-specific.

## 4. Conversion (implemented, SPEC 26)

A faithful copy is not possible without an engine hook (XMen2.exe has no texture automap path left), but the
`.zam` can carry XML1's art: same scale (12 units per pixel), same coordinates (texture pixel (u, v) = world
((u + ou) * 12, (v + ov) * 12)), same outlines. Per zone `zones.automap` converts the texture the XML1 world names
(`automaps.build`):

1. luminance = max(R, G, B) of the DXT colour blocks (the alpha half is 0xff everywhere);
2. grey area = 5 x 5 majority of lum >= 48 (drops the dither and HAARP's snow speckle), white = lum >= 160;
3. per 240-unit cell (20 x 20 px), each level -> vertical chains of row runs -> left / right edge polylines
   (Douglas-Peucker 0.75 px white, 1.5 px grey), a forced break at the 120-unit mid row (fog cell), one strip
   segment per chain (2 vertices per break), grey (alpha 0x50) under white (0xcb);
4. `Automaps/<zone>.zam` + `<zam filename="automaps/<zone>"/>` after `boy`; the bundle's
   `texture textures/automap/*` entries are dropped.

| measure (175 XML1 automaps) | result |
|---|---|
| format problems (V20 / `automaps.problems`) | 0 |
| worst draw window (20 x 20 cells) | 7,646 of 8,192 (astroid_m/visit1/asteroid1_2); median ~3,500 |
| size | 5.2 MB total, 19-58 KB each (retail 8-66 KB), <= 4,475 vertices |
| white outlines, rasterised back onto the texture | recall >= 0.946 (median 0.994), precision >= 0.928 (0.995) |
| grey area IoU | >= 0.909 (median 0.965) |
| conversion time | ~35 s for all zones (mansion hubs converted once) |

Parameter search (scratch prototypes): per-pixel quads cost 14,160 strip vertices for nyc1_1_1 alone; 2 levels +
trapezoids 5,202; chains + DP + majority smoothing brought the worst zone from 13,728 to 7,230 (7,646 with the fog
mid-row breaks). Splitting chains at every 120 units in x as well (retail's fill quads are 120 x 120) would exceed the
builder in 9 zones, so the fog granularity is 120 units in y and 240 in x.

## 5. In game (2026-09-29, build/_automap) and open items

Verified (SPEC 26.6; `screenshots/automap_*.png`): the pause-menu Automap and the HUD small map draw XML1's maps in
`nyc/alison/nyc1_1_1`, `mansion/man1a/mansion1a_1` and `astroid_m/visit1/asteroid1_2` (the densest), aligned with the
hero marker and the rooms, fog of war active (only the explored start area until the bits were cleared in the test
process), no dropped cells, no exception. Live reads in that process: the fog origin followed the zam origin
(nyc1_1_1: 0,-2 fog cells = zam origin 0,-1); modes 1 (small map, scale 0.05, radius 8) and 3 (menu, 0.175, 10).

Open:
- fog reveal over a long walk, save / load of the fog, an act town centre revealing all (read statically only);
- XML1's HUD overlay semantics (its own 64 x 64 fog, Back-button overlay) are not reproduced; XMen2.exe's modes apply;
- the pool the loader allocates from (0x5605e0 pool 0x14) was not sized; the converted files stay under retail's
  largest (66 KB).
- XML1's HUD overlay semantics (its own 64 x 64 fog, Back-button overlay) are not reproduced; XMen2.exe's modes apply.
- The pool the loader allocates from (0x5605e0 pool 0x14) was not sized; the converted files stay under retail's
  largest (66 KB).
