# Powers debug: why the converted XML1 heroes' power wheel is empty (2026-09-28)

Symptom (in game 02:35, build/_heroes): holding Power (numpad 5) shows the wheel with all four slots EMPTY for XML1
Wolverine / Cyclops at level 1; a power assigned by hand in the skills screen does nothing in combat. XML2's own
heroes (build/xml1_tour) show the first power (Magneto: `power5` in the bottom slot). The skills screen lists the XML1
talents, so the per-hero talent files load.

Offline only (no game launched). Files compared: XML2 retail `Data/herostat.engb` (Magneto, Cyclops, Wolverine),
`Data/talents/{magneto,cyclops,wolverine}.engb`, `Data/powerstyles/ps_*.engb`, `Packages/generated/characters/
{magneto_2501,cyclops_0101,wolverine_0301,*_xml}.PKGB` against build/_heroes `herostat`, `talents/{cyclops,wolverine}`,
`powerstyles/x1_ps_*`, `cyclops_14101[_nc]`, `wolverine_14301[_nc]`, `*_xml`. Exe addresses are from
research/scripts/xml2_text.asm and the decompiles cited; XMen2.exe = research/characters/ghidra/XMen2.exe.

## 1. Root cause (two defects; both break every XML1 hero power)

### A. The hero's style is parsed before its talents are registered (package entry order)

Our combat packages list `fightstyle data/powerstyles/x1_ps_<hero>` **before** `xml_talents data/talents/<hero>`
(the XML1 bundle carries its own style entry, and heroes.py `_packages` appended `xml_talents` after it):

```
build/_heroes cyclops_14101.PKGB:  actorskin, actoranimdb, models, effects..., fightstyle x1_ps_cyclops, xml_talents data/talents/cyclops
XML2 cyclops_0101.PKGB:            actorskin, actoranimdb, texture icons, xml_talents data/talents/cyclops, models, effects..., fightstyle ps_cyclops
```

Scan of every package that carries `xml_talents`: **XML2 retail 380/380 list it before every fightstyle; build/_heroes
had all 38 XML1 hero combat packages (every costume of all 15 heroes) with the style first.**

Why the order matters (all read in the exe):
1. `FUN_00561d40` (package load) walks the `<packagedef>` children in document order and calls each entry's handler
   immediately (`FUN_00561b90(tag)` -> handler vt+4 -> `FUN_00561040` reads `filename` -> vt+0). `xml_talents` =
   `FUN_00561510` (talent mgr vt+8 -> registers the file's talents and their talentvalue names); `fightstyle` =
   `FUN_005614a0` -> fightstyle manager (`FUN_004ffe20`, vtable 0x694194) vt+0x1c = `0x4ffb30`.
2. `0x4ffb30` looks the style up by name; a new name is allocated and parsed now (`0x4ffbf5 call 0x501240`), an
   already-loaded name is **not re-parsed** when arg3 = 0 (the package handler passes 0: `0x4ffbb8 cmp [esp+0x18],1`).
3. While parsing, each FightMove `<require>` is built by the require class (vtable 0x68d9c0) parse method
   `FUN_004ac470` (decomp_heroes5.c:487): for `cat="skill"` (category 0) the item name is resolved **now** -
   `talent mgr vt+0x2c(name)` (known?) then `vt+0x1c(name)` -> talent id stored as a short at +0x12. An unregistered
   name leaves the id at **0** (`local_38 = 0`). The name itself is not kept.
4. The evaluator (vt+0xc = `0x4acf10`, jump table 0x4ad0e0 entry 0 = `0x4acf35`) reads the hero's rank of talent
   id [+0x12] (`0x4692f0` -> `0x43ade0`). Talent id 0 is the first shared talent = `fightstyle_finesse1`, which no
   XML1 hero owns, so every `power1/2/3/9` of our heroes requires a talent the hero never has.
5. Same for `%talentvalue` attributes: talent-value manager vt+0x18 = `0x4c1580` resolves `%name` to an id at parse
   time (`0x4c15fd`); unknown -> id 0 and the float value 0 (`0x4c1593 mov [edi],ecx` with ecx = 0).

Consequence: all four assigned slots (herostat `power1..4` = `power1 power2 power3 power9`) name FightMoves whose
requirement can never be met -> the wheel shows no slot and a hand-assigned power never starts. This matches XML2's
own behaviour: Magneto has four assigned slots (`power5 power2 power1 power9`) but at level 1 only `power5`
(`mag_telekinesis`, herostat level 1) is shown - the wheel hides slots whose FightMove requirement fails. Ours hid
all four, including `power1` whose talent is rank 1.

### B. Every talentvalue name was 20-31 chars; the exe only accepts <= 19

heroes.py named talentvalues `x1_<hero>_<talent>_<short>` capped at 31 chars (`TALENTVALUE_NAME_MAX = 31`), e.g.
`x1_cyclops_cyclops_beam_dmg` (27), `x1_wolverine_wolv_frenzy_dmg_t1` (31). **All 274 XML1 hero talentvalue names were
>= 20 chars.** XML2 retail: 1075 names across 23 files, max 19 (`wolv_regen_health_t`, `toa_tongue_mast_req`); its 575
powerstyle `%` references: max 19. The exe:
- registrar vt+0x1c = `0x4c1860` (called per `<talentvalue>` by `FUN_004bdc20`): `strlen(name)`,
  `0x4c188c cmp eax,0x14 / jae 0x4c1945` -> returns id 0 (not registered) for 20+ chars. Capacity 300 names
  (`0x4c18d9 cmp [ebx+0x2a7c],0x12c`).
- `%name` parse `0x4c1580` and lookup vt+0x24 = `0x4c16b0`: `strncpy(buf, name, 0x14)` + NUL at 0x13 -> looked up as its
  first 19 chars, never found -> id 0, value 0.
- talent apply `0x4bf640`: `0x4bf77b call [vt+0x24]` -> id 0 -> `je 0x4bf927` (value skipped).

So even with A fixed, every `damage`, `powerusage`, `knockback`, `life`, `level` ... that the style collapse turned into
a `%reference` would be a literal 0: powers doing 0 damage for 0 energy, buffs with life 0 (instant expiry).
A and B share a cause in spirit: the style's references are resolved against the talent files at parse time.

## 2. Everything compared (Cyclops / Wolverine vs XML2 Cyclops / Magneto / Wolverine)

| item | XML2 (works) | build/_heroes | verdict |
|---|---|---|---|
| package entry order | `xml_talents` before `fightstyle` (380/380) | style first in all 38 hero combat packages | **defect A** |
| talentvalue name length | <= 19 (1075 names) | 20-31 (274 names) | **defect B** |
| herostat `power1..4` | FightMove names (`power1 power3 power7 power9` Cyclops, `power5 power2 power1 power9` Magneto) | `power1 power2 power3 power9`, all exist in `x1_ps_<hero>` | OK |
| talent `power=` | FightMove name | `power1/2/3/9`, each a FightMove of the style (V-H3) | OK |
| herostat starting talent | `<talent level="1" name="cyclops_beam"/>` (per-hero file) | `cyclops_beam` / `wolv_slash` level 1, defined in the hero file | OK |
| boot pending-talent table (`FUN_0043ba60`, 64 max) | 29 entries | 21 entries | OK |
| herostat `level="0"` children | XML2 omits `level` | `level="0"`: `FUN_0043bb80` queues only level/limit > 0 -> harmless | OK |
| talent id range | (statsIdx+1)*100 | Cyclops 500.., Wolverine 1700.. (< 65536) | OK |
| `<require cat="skill">` targets | talents of the same file | all resolve (file or shared, V-H3) | OK (once A is fixed) |
| `%refs` resolve by name | yes | yes by name, but names unusable (B) | fixed by B |
| `<level>` form | 1-2 `<level count=N>` | one `<level count="1">` per XML1 rank (11 for cyclops_beam) | OK: count sum = ranks |
| FightMove `aitype` / `priority` | powers carry both (217/233 skill-gated moves priority 5) | 41/50 priority 5; Wolverine `power1` has none (XML1 `eviscerate1` has none either) | minor, faithful |
| Wolverine power2 `cat="counter"` require | XML2 uses counter only on loop moves | `only_looped="true"` kept from XML1 `clawfrenzy1` | OK |
| iconfile / icon_texture | 4x4 `<hero>_icons1.png` | XML1 2x2 `<hero>_all.png` (SPEC 7.2 #4, `--hero-icons generic` fallback) | cosmetic only |
| `xml_talents` entry | combat, `_nc`, `_xml` | present in all three | OK |
| autospend | `support_heavy`, `bruiser` | same classes, exist in autospend.xmlb | OK |
| talentvalue registry | 300 names (0x4c18d9) | 285 names for shared + all 15 XML1 files | OK even if names are never unregistered |

## 3. Fix (implemented in tools/xml1build/heroes.py, 2026-09-28)

1. `HeroBuilder._styles_last(root)` (new, called in `_packages` for every costume package just before it is stored):
   moves every `<fightstyle>` entry to the end of the package, preserving their order (XML2 retail form; also keeps
   `xml data/entities/*` before the style).
2. `TALENTVALUE_NAME_MAX = 19` (was 31) with the exe evidence in a comment, `TALENTVALUE_NAMES_CAP = 300`,
   `TALENTVALUE_CODES` and `talentvalue_code()`; `talentvalue_name()` now emits `<code>_<talent>_<short>`: code =
   `x` + two hero letters (`xcy`, `xwo`, ... - no XML2 name starts `x??_`), the talent part drops a leading token the
   hero name starts with (`cyclops_beam` -> `beam`, `wolv_frenzy` -> `frenzy`, `night_shadow` -> `shadow`) and is
   truncated to fit 19; clashes get a digit. Results: `xcy_beam_dmg`, `xcy_sweep_kb_t3`, `xwo_frenzy_dmg_t1`,
   `xph_telekinesis_pwr` (longest, 19).
3. Validator: V-H6 errors when an `xml_talents` / `xml` entry follows the first `fightstyle` of a hero package;
   V-H3 errors on a talentvalue name > 19, on a name defined by two files (the registry is global: name -> one id),
   and on more than 300 names in total (count `talentvalue_names`). Run against the old build/_heroes these new checks
   report 314 errors (274 long names, 39 package-order, 1 summary); against the new build 0.
4. SPEC_heroes.md sections 5, 6 and the V-H3/V-H6 rows updated.

Rebuild `python tools/build_xml1.py --out build/_heroes_powerfix --no-movies`: OK, 0 errors
(heroes 0 errors / 4 warnings, heroes_validate 0 errors / 5 warnings - the same pre-existing warnings as before).
`heroes_selftest.py build/_heroes_powerfix`: PASS (2329 rank values still equal the XML1 rungs). Standalone
`xml1build.validate --no-movies`: 0 errors. Re-scan of build/_heroes_powerfix: 544/544 packages talents-first, 878
talentvalue names, max 19, 0 unresolved `%refs` in x1_ps_cyclops / x1_ps_wolverine.

## 4. Remaining risk (not fixed; check in game)

**C. Zone packages load playable heroes' styles.** In build/_heroes(_powerfix) `x1_ps_cyclops` is also an entry of the
zone packages `nyc/alison/nyc1_1_2b`, `nyc/alison/nyc1_1_3`, `mansion/dr_mag2/mag_nyc3`, `mag_nyc4`,
`xjet/blackbird_arbiter`; `x1_ps_wolverine` of `weapon_x/old/wx2_2` and `blackbird_arbiter` (the NPC doubles XML1
spawns by the hero's stats name). XML2 retail never does this: its only hero-named style in a zone package is
`ps_pyro` (genosha3), which belongs to the NPC `Pyro`; the playable hero uses `ps_pyro_hero`, and NPC doubles use
`ps_cyclops_dopple` / `ps_wolverine_dopple` / `ps_sin_wolverine`. If a zone package parses the style while that hero's
talents are not registered (e.g. nyc1_1_3 after Cyclops joins, if the zone package loads before his character
package), the style is cached with id-0 requires / zero `%values` and that hero's powers break exactly like A until the
style is freed. Whether the zone package or the party packages load first, and when a zone-owned style is freed, is
**UNVERIFIED**. If it shows up: give the NPC doubles their own npcstat entry and style copy (`x1_ps_<hero>_npc`,
XML2's `_dopple` pattern) in zones/characters so zone packages never list `x1_ps_<playable hero>`.

Minor, unrelated to the wheel: 15 NPC packages from characters.py (grso_*, haarpleader/soldier, weapxguard*) list
`xml data/entities/*` after their powerstyle, which XML2 never does; matters only if the style parse resolves
entities (UNVERIFIED).

## 5. In-game verification (main session)

1. Install the harness into build/_heroes_powerfix exactly as for build/_heroes (the build sweeps proxy files; use
   the xml2-fix DLL that has the NewGameTeam patch, `[Game] NewGameTeam=wolverine`, `ResetUnlocks=0`).
2. New Game -> nyc1_1_1 as Wolverine. Hold numpad 5: expect **one** filled slot (Wolverine `power1`, the claw power,
   XML1 icon cell 0 - may look quartered, cosmetic) and three empty ones (frenzy/berserk need level 5, xtreme 15).
   Screenshot the wheel (fixinput.py screenshot).
3. Fire it at an enemy: the eviscerate animation plays, energy drops by 10 (`xwo_slash_pwr` rank 1), damage 25-31
   (`xwo_slash_dmg`). Energy not dropping / no damage = defect B not cured (check the talent file names).
4. Skills screen (F1): `wolv_slash` rank 1, assign/unassign works; after a level-up spend a point in `wolv_slash`
   and confirm the damage/energy numbers rise (rank 2: 50-63, 15 energy).
5. Walk to nyc1_1_3 so Cyclops joins, then hold numpad 5 with Cyclops active: `power1` (optic beam) must show and
   fire (10 energy, 9-11 damage). An empty wheel here only = risk C (zone package parsed `x1_ps_cyclops` first); leave
   the zone and come back to confirm, then apply the C fix.
6. Optional: cheat a level (5+) and use Cyclops tactics (`power3`) - the buff must last 15 s (`xcy_tactics_lif_t1`),
   not vanish at once.
