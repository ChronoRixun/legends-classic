# XML2 effect XML format vs XML1, and the black-polygon question

Scope: how XMen2.exe (retail PC) parses `effects/*.xmlb`, what it tolerates, and whether the GRSO
nullifier / mp5 effects imported from XML1 can be the source of the large flat black jagged shapes.
Addresses are XMen2.exe VAs (research/characters/ghidra/XMen2.exe, decompiles decomp_fx1..13.c).
Data counts come from all 726 XML1 disc effect files and all 1166 retail XML2 effect files.

## 1. Load path and limits (verified)

- `0x418f80` builds `effects/<name>.xmlb`; `0x418e00` opens it, requires root `Effect`
  (string 0x681ec0), allocates an effect def (`0x418d90`; at most **220** defs, 0xdc) and parses
  root attributes with `0x4182c0`: `LoopTime` %f (+0x34), `RandLoopTime` %f (+0x38),
  `PersistLoop` %i -> bool (+0x3c), `name` ignored, anything else ignored. All name compares in
  this parser are `_stricmp`, so XML1's `LoopTime`/`Blend`/`Texture` capitalisation is irrelevant.
- Each child element (`0x418900`): the tag is looked up in the pair table at `0x6d5210`
  (`0x5602f0`, stricmp): Empty=1, ParticleCloud=2, Sprite=3, WeatherEffect=4, OrientedSprite=5,
  Spark=6, Line=7, Lightning=8, Cylinder=9, Model=10, FloorCrack=11, Light=12, AmbientLight=13,
  ScreenFlash=14, CameraShake=15, TesselatedMesh=16, Trail=17. **An unknown tag is skipped
  silently**; a known one gets a def from `0x4188a0` (at most **10 primitives per effect**, 816
  defs in total (0x330)), then every attribute goes through `0x4172d0`; its return value is
  ignored, so an unknown attribute or an unparsable value just leaves the default.
- Defaults are set by `0x416a30` before the attributes: colours 0xffffff (white), blend 1
  (additive), orient 0 (forward), count 1, life 1, delay 0, alpha curve constant 1, size/size2/
  length curve `0 -1 2`, uvscale 1, uvscroll 0, rotation 0, endarc 6.283, width 12, texture "".

## 2. Attribute parser `0x4172d0` (shared by every primitive type)

Value forms (all via sscanf on the attribute string):

| form | parser | meaning |
|---|---|---|
| pair `"a b"` | `0x415770` "%f %f" | stored as (a, b-a): a value and a random range |
| int | `0x4157c0` "%i" | |
| uint | `0x4157e0` "%u" | colours and flag words; a negative decimal wraps, as retail files rely on |
| float | `0x415810` "%f" | |
| vector `"x y z x2 y2 z2"` | `0x417140` "%f %f %f   %f %f %f", **fails if fewer than 6** | first triple + random lerp to the second; interned into a 710-slot pool (`0x416210`) |
| curve `"a b c a2 b2 c2 [max min]"` | `0x4171e0` "%f %f %f %f %f %f %f %f", **needs 6; 7th/8th default to 10000 / -10000** | v(t) = a*t^2 + b*t + c over the particle life, random lerp to the second triple, clamped to [min,max] (clamp: section 2.1); interned into a 900-slot pool (`0x416120`) |

So an 8-number XML1 curve is read exactly like XML2's 6-number form plus explicit clamps, and a
6-number form gets the same clamps XML1 writes. This is why trimming curves changed nothing.
Retail XML2 itself ships 8-value curves (14 Cylinder `alpha`, 62 `size`, 53 `size2`, 30 `endarc`).

Attribute -> parse form -> def offset (every primitive; nothing is type-specific in the parser):

| attribute | form | offset | attribute | form | offset |
|---|---|---|---|---|---|
| name | ignored | - | startColor1/2, midColor1/2, endColor1/2 | uint | +0x74..+0x88 |
| count, life, delay | pair | +0x14, +0x1c, +0xc | alpha, size, size2 | curve | +0x8c, +0x54, +0xe6 |
| origin, velocity, acceleration | vector | +0x24, +0x26, +0x28 | length, width, offset | curve | +0xd4, +0xd8, +0xd6 |
| gravity, drag | pair | +0x34, +0x2c | rotation, rotationRadius | curve | +0xda, +0xdc |
| origin2, velocity2, acceleration2 | vector | +0xe8, +0xea, +0xec | chaos, attenuation | curve | +0xde, +0xe0 |
| gravity2, drag2 | pair | +0xf8, +0xf0 | startarc, endarc | curve | +0xe2, +0xe4 |
| radius, radius2, height | pair | +0x5c, +0x64, +0x6c | uvscroll, uvscale | curve | +0x100, +0x102 |
| viewoffset | float | +0x58 | transformRotation | vector | +0x106 |
| primitiveFlags, spawnFlags | uint, **OR-ed** into +0x40 / +0x44 | | pLifeScale, numsegments | int | +0x108, +0x104 |
| Interval | float | +0x50 | DeathFxFile, IntervalFxFile | effect path, loaded via `0x419430` | +0x48, +0x4c |
| texture, modelName | string copied verbatim, 63 chars (`0x415c40`) | +0x8e | shaketype, shakescale, shakespeed | int, float, float | +0x114, +0x110, +0x10c |
| blend | `0x415850`: `alpha`=0, `additive`=1, `subtractive`=2, else ignored (default additive) | +0xd0 | orient | `0x4158d0`, table 0x6d51ec: forward 0, up 1, right 2, random 3, up45 4, up30 5, up15 6 | +0x3c |

Not in the parser (ignored): `red`, `green`, `blue`, `volume`, `soundfile`, and any Sound element.

### 2.1 Colours

`0x4155e0` builds each colour channel's curve from the three packed colours: channel byte via
`0x415560` (bits 0-7 = red, 8-15 = green, 16-23 = blue; the callers `0x415710/30/50` ask for
channels 0, 2, 1 only, so **the top byte (alpha) is never read**). With s/m/e = start/mid/end
(each lerped between colour1 and colour2 by one random number) the curve is
a = 2s - 4m + 2e, b = -3s + 4m - e, c = s (constants 4.0 at 0x6819a8, 3.0 at 0x6819ac), i.e. the
quadratic through (0,s), (0.5,m), (1,e); clamps 10000/-10000. Opacity comes only from `alpha`.
Verified against the one Rosetta pair: XML1 test/redsquare `red="0 0 1 ..."` is XML2
test/redsquare `startcolor1="2130706687"` = 0x7F0000FF (R in the low byte; the 0x7F alpha byte
is where Raven folded the constant alpha 0.5, but XMen2.exe ignores it - the port's
x1schema.convert_effect_colors already does this conversion, and build/_wpn files have no
red/green/blue left).

## 3. Texture, blend and flags at spawn time (verified)

- Spawn (`0x408e50`) resolves the texture as `"<package scope>:<name>"` (`0x5647f0` "%i:%s") and
  hands it to the instance (`0x414d20` -> texture manager `0x5872d0`, lookup `0x586e50`): the
  4-char extension is cut (`textures/line.png` -> `textures/line`), the name is tried in the
  current scope, then scope 2 (the permanent package), then loaded on demand (vt+0x14), and if
  all fail the manager's **fallback texture** is used. Retail XML2 files use the same `.png`
  spellings; XML1's are identical (2327 `.png`, one `.igb`, one bare name).
- The instance is registered (`0x407370`) only if the texture handle is non-zero (Model, Light
  and Empty excepted); 374 live instances max (0x176). `0x413ac0` then builds the material key
  from the texture id plus the blend word and primitiveFlags bit 21 (`0x417fb0`, `0x418140`),
  so `blend` is honoured per primitive: an additive primitive cannot draw opaque black.
- spawnFlags bits are translated to instance flags by `0x4039d0` (0x1000000, 0x4000000,
  0x20000000, 0x8000000); primitiveFlags are copied whole to instance +0xfc.
- The effect pools are freed with the def; per-zone pressure is similar for both games (mean
  non-default curves per effect XML1 4.4 vs XML2 3.0, vectors 3.3 vs 2.7; no XML1 effect has more
  than 10 primitives).

## 4. The four suspect files against retail

Decoded (tools/xmlb.py) and compared with retail Spark/Line primitives attribute by attribute:

- `weapons/m_nullifier/null_shot` (2 Lines): origin `-5 0 0`, origin2 `1 0 0`, size `12.8 -27.8 15`
  (15 -> 0), alpha `-4 3 1` (1 -> 1.56 -> 0), blend additive, primitiveflags 256, spawnflags
  1074790400 (0x40100800), texture fx_avalanche / levelup_rain. Retail beam effects used by
  `beameffect` (char/iceman/p1_power, char/magnet/p2_power, char/apoc/p3_power, 26 files) are
  the same shape: Line, origin2 `1 0 0`, primitiveflags 256, spawnflags 0x100800 or
  0x40100800, additive, fx_avalanche/bolt_sharp, alpha `-8 8 0` (peaks at 2.0, so >1 alpha is
  normal).
- `weapons/mp5/mp5_tracer` (Spark): primitiveflags 33024 (0x8100), spawnflags 0x40000000, texture
  textures/line.png, length `-42.4 92.4 50`, velocity `2000 0 0`. Retail Sparks: primitiveflags
  {260, 256, 33028, 33024, 388, 384}, spawnflags {0x60040000, 0, 0x40000000, ...}, textures
  l_graystreak / line / muzzle2 - identical vocabulary.
- `null_muzzle` (Cylinder + 2 Sprites), `null_charge` (2 Sprites): `numsegments="0"` is what 904
  of 1166 retail Cylinders carry; spawnflags/primitiveflags values all occur in retail.
- The textures they name are byte-identical in build/_wpn/Textures and the retail install
  (fx_avalanche, levelup_rain, line, misc_hitflash, whitestar, sun: same size and md5), and
  fx_avalanche / line / misc_hitflash / whitestar live in retail permanent.PKGB (scope 2), which
  is why the officer package lists only levelup_rain (and that is listed).
- The port's XMLB encoder round-trips a retail file byte-for-byte (char/magnet/p2_power).

Conclusion: nothing in these four files is outside what retail XML2 effects use, and the parser
has no path that turns them into an opaque black primitive. The black shapes are not explained
by the effect XML. Flag bit usage per primitive type (bits 7, 8, 15, 24-31) matches between the
two games' whole effect sets (scratch inventory, flags.py).

## 5. Where the black polygons must come from instead (not verified in-game)

1. **A model, not an effect.** Flat black jagged geometry is the classic look of a mesh whose
   material/vertex format the PC Alchemy build does not understand. In combat the officer bolts
   `models/weapons/m_nullifier` (weapons.eng) and the beam hit spawns `null_impact`; the mp5
   soldier bolts the mp5 model. Test: `spawnEffect` null_shot / mp5_tracer alone in a quiet
   scene (as was done for mystique_morph and flame_shot). If they draw in colour, the shapes are
   the weapon models (XML1 Xbox IGBs) or another bolt-on, and effect conversion is a dead end.
2. **Beam scaling.** `ce_atk_beam` (0x451cc0, weapon_events.md section 2) spawns `beameffect`
   oriented along the ray; the retail beam Lines have origin2 `1 0 0` like null_shot, so if the
   beam code scales by ray length the two behave identically. Not traced further.
3. **Texture fallback** (section 3): a name that resolves nowhere draws with the manager's
   fallback texture, not black; and all four files' textures resolve.

## 6. Conversion recipe XML1 -> XML2 effect XML (what XMen2.exe needs)

Verified requirements (everything else can be left exactly as XML1 wrote it):
1. `red`/`green`/`blue` curves -> `startcolor1/2`, `midcolor1/2`, `endcolor1/2` packed as
   `A<<24 | B<<16 | G<<8 | R` (A unused by the exe), evaluated at t = 0, 0.5, 1 - already done by
   tools/xml1build/x1schema.convert_effect_colors; keep `alpha`.
2. Drop `Sound` elements (unknown tag, skipped anyway) and `volume`/`soundfile`.
3. A vector or curve with fewer than 6 numbers is rejected and keeps the default (one XML1
   Cylinder has a 2-number `uvscale`): pad to 6 if the value matters.
4. Keep `persistloop`, `plifescale`, `transformrotation`, 8-value curves, `.png` texture names,
   `blend="additive"`, `orient` words, numeric flags: all read as-is.
5. Element and attribute names are case-insensitive; attribute order is irrelevant.
Inferred, not required: trimming curves to 6 values and dropping `10000 -10000` is cosmetic.

No "smallest change" exists in the XML that would stop the black polygons: the files are already
in the form XMen2.exe renders retail beams and tracers from. Next step is the in-game isolation
test in section 5.1.

## 7. Open points

- At spawn `0x4037d0` picks the instance's curve as 5 floats: (a,b,c) = first triple + r * (second
  minus first), then max, min (verified). That the renderer clamps the evaluated value to
  [min, max] is inferred from the 10000 / -10000 defaults; the evaluation site was not traced.
- The runtime effect of primitiveFlags bits beyond bit 1 (spawn offset select at 0x4090c0) and
  bit 21 (material flag) was not traced; both games use the same bits.
- Whether the beam code scales a Line's origin2 by ray length was not traced.
