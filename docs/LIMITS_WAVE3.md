# Limits wave 3: the builder side (`--limits-wave3`)

XML2 Fix's wave 3 raises the engine tables a graphics or character mod fills first: fight styles, style events,
FightMoves, effect files / definitions, primitive definitions, effect vectors, primitives per effect, the attached
powerups and the powers' callback nodes, and (later) the
script pools and the particle scratch. This page is the builder's half: which `xml2-fix.ini` keys a build writes, how the
build refuses a DLL that cannot honour them, and how the validator counts what a finished build asks of each table.

Nothing here changes a default build. **`--limits-wave3` is off by default**, and with it off the build, its
`xml2-fix.ini`, its `report.json` and its `validate.json` are the ones the builder wrote before the option existed. The
DLL rows are not written yet; the option stays off until they land.

## The option

| | |
|---|---|
| `build_xml1.py --limits-wave3 {off,on,all}` | `off` (default): nothing. `on`: the nine rows below. `all`: also `ScriptPools` and `ParticleScratch`. |
| `xml1-builder build --limits-wave3 {off,on,all}` | the same, passed through to the content build |
| `_build/report.json` `build.limits_wave3` | recorded **only** when the option is on (so an off build's record is unchanged) |
| not in `CONTENT_OPTS` | it changes the ini and the validation, not a content module, so the stamp's profile (and every existing build's state) is unchanged |

An off rebuild drops every wave-3 key again (`fix_ini.PORT_OWNED`) and `FightStyles` is 32.

## The keys

| Key | Retail | Written with `on` | Rule | DLL gate (the install line the DLL must carry) |
|---|---:|---:|---|---|
| `FightStyles` | 19 (32 today) | **64** | 35 revision 2 | required only above 32 |
| `StyleEvents` | 1,064 | 4,096 | 53 | `StyleEvents: rule 53 revision 1 installed {4096,0,0,0}` |
| `FightMoves` | 332 | 1,024 | 54 | `FightMoves: rule 54 ...` |
| `EffectTemplates` | 220 | 512 | 55 | `EffectTemplates: rule 55 ...` |
| `PrimitiveDefs` | 816 | 2,048 | 56 | `PrimitiveDefs: rule 56 ...` |
| `EffectVectors` | 710 | 4,096 | 57 | `EffectVectors: rule 57 ...` |
| `PrimitivesPerEffect` | 10 | 32 | 58 | `PrimitivesPerEffect: rule 58 ...` |
| `AttachedPowerups` | 128 | 256 (the only value the DLL accepts) | 61 | `limits: %s 256 (allocation 0x%X): %s; %s` |
| `VFNodes` | 192 | 256 (the only value the DLL accepts) | 62 | the same power-pools install line |
| `ScriptPools` (`all`) | 620 / 1,556 / 120 / 30 | `x1` = 4,096 / 8,192 / 512 / 128 | 59 | `ScriptPools: rule 59 ... {4096,8192,512,128}` |
| `ParticleScratch` (`all`) | 40 | 40 (the clamp) | 60 | `ParticleScratch: rule 60 ... {40,0,0,0}` |

`EffectCurves` stays at its released 3,600 and `MoveTriggers` at 64.

* **The gate.** `fix_ini.check_release_dll` refuses an existing DLL that lacks a key's UTF-16 name **or** its rule's
  install line, and names the rule (`[Limits] FightMoves (rule 54)`). The key name alone cannot certify a rule; an older DLL
  reads `FightStyles` up to 32 and silently ignores the rest. The harness and `xml1-builder` use the same function.
* **Markers.** `fix_ini.WAVE3_MARKERS` holds each row's real install-line format string from XML2 Fix 1.9.0
  (w3/integrated; `WAVE3_MARKERS_ARE_PLACEHOLDERS` is False). The style manager (35 r2 + 53) and the effect pools
  (56 + 57) and the power pools (61 + 62) are one owner each and share their install line; the UTF-16 key names tell the rows apart. The rule ids come from the coordinator's
  list (35 revision 2, 53-62).
* **Dependencies.** `PrimitivesPerEffect` needs `EffectTemplates` (its side table is indexed by the definition slot); a late
  row needs the nine (`fix_ini.check_wave3_keys`).

## The checks

They run only for a build made with the option (a default build's `validate.json` has no such entries) and read their
capacities from the `[Limits]` the build asks for, else the game's own value. Every check covers each finished (converted)
zone and every allowed four-hero party: the two special Professor X forms (`ProfXAstral`, `ProfXGladiator`) are never a
party member, and a forced mission's seated heroes (`talent_budget.mission_parties`) replace "any hero" where the build
has the plan. Each reports the count, the capacity and the witness zone and party; **error above the capacity, warning at
equality or above half of it** (the 2x rule: one warning, for the worst zone).

| Check | What it counts (DESIGN section 3, binding) | Capacity |
|---|---|---|
| **V23** (V-STYLES) | distinct style filenames of the permanent packages, the zone, its CHRB characters and the party (as before); with the option: the raised registry, a witness, the 50 % warning | `FightStyles` |
| **V-MOVES** | every direct `FightMove` child of every registered style file, `data/shared_nodes` included; an inheriting move copies events but allocates no extra move. Also the largest per-style count | `FightMoves`; per style 150 |
| **V-EVENTS** | a trigger instantiates its event; a move that inherits copies every inherited trigger event; a trigger whose tag matches modifies and adds nothing; `reset` frees; style / shared event definitions are temporary. Final and transient-peak occupancy, unresolved triggers listed (for example Juggernaut's `grabstart` / `pickup_sound`) | `StyleEvents` |
| **V-EFFECT-FILES** | one definition + one file-table entry per successful non-empty `<Effect>` load, recursively through `DeathFxFile` / `IntervalFxFile`, plus literal `spawnEffect` / `spawnEffectBone` names in the zone's scripts. Unresolvable references are listed, not guessed | `EffectTemplates` |
| **V-PRIMITIVES** | direct children with attributes and a recognised primitive type (`Sound` is none), admitted up to `PrimitivesPerEffect`; extra children are errors; globally against `PrimitiveDefs` | `PrimitiveDefs`; per effect `PrimitivesPerEffect` |
| **V-VECTORS** | 84 reserved presets + one slot per non-preset vector attribute (six floats read as minimum, maximum - minimum; a preset only when both three-component squared distances are below 0.001; equal non-presets are not de-duplicated) | `EffectVectors` |
| **V-CURVES** | the same for the 14 curve attributes with 140 presets, and the **combined effect budget**: files, definitions, primitives, vectors, curves, each against its capacity, naming the table that binds first | `EffectCurves` |
| **V-SCRIPTS** | retained statement nodes (statements minus `else` / `endif`, which take a node and free it again, minus skipped `def` / `__name__` lines) plus one compile-time temporary; values = literals + the largest distinct local set + one temporary; compiled scripts per zone. Replaces V7's "622 statements > 620" wording, which counted source lines | `ScriptPools` |

V7's three pool warnings (statements / literals / scripts against 620 / 1,556 / 120) are replaced by V-SCRIPTS when the
option is on; the zone-var error stays.

### What the 080c build gives (the self-test)

`python -m xml1build.limits_wave3 --out <finished build> [--mode on|off|all] [--json file]` replays the rules over a
build folder (read-only, no game, no validator context) and compares the static report's witnesses:

| Row | Value | Witness |
|---|---:|---|
| styles | 24 | `sewers/grso/sewers3_1_3`, Beast / Colossus / Cyclops / Phoenix |
| FightMoves | 306 | `astral/ast3/astral3_4`, Gambit / Nightcrawler / Rogue / Wolverine |
| largest style | 108 (of 150) | `data/shared_nodes` |
| style events | 831 | `astroid_m/visit1/asteroid2_1`, the same party |
| Master Mold 2 script nodes | 585 (622 source lines, 37 else/endif) | `mastermold/mastermold2`, 27 scripts, 784 literals, 9 locals |

The corrected count makes `nyc/riots/nyc3_2_1` (589 retained nodes, 612 source lines) the largest script load, not Master
Mold 2. Effect totals at `mastermold/mastermold2` (provisional, see below): 207 files, 627 primitive definitions, 647
vectors; 910 curves at `astroid_m/visit1/asteroid2_1`. With the raised tables no row is above 40 % (effect files 207 of
512 = 40 %, styles 24 of 64 = 38 %, primitive definitions 31 %, FightMoves 30 %, curves 25 %, events 20 %, vectors 16 %);
at the stock capacities the same build warns on seven rows (the effect-file table is 94 % full), which is the case for
the raise.

### What is still an estimate

* **Effect scope.** The `%i` of the effect key (0x5647f0) is the loader caller's. The model treats every package load as
  one scope; the report also gives the upper bound with every owning package its own scope (255 files at Master Mold 2).
  The scripted-load set is only literal `spawnEffect` / `spawnEffectBone` names. The pool diagnostics (D) measure it.
* **Unresolved references.** Thirteen effect names that the zones' packages or other effects name have no loadable file
  (`explode/{lrg,med,sm}exp1.xml` from two Death/Interval references, `powers/wolvfrenzyimpact` which is an empty file, six
  bone-named package entries such as `bip01 head`, and four missing power effects). They are listed under
  `details.unresolved_effects` with who names them and counted nowhere; the engine may load a `.xml` reference as the
  `.xmlb` of the same name, which the model does not assume (`--xml-refs strip` on the self-test shows that reading).
* **Curves.** The attribute list (14) and the preset file (`defaultquads`) are the engine's; the engine's compare
  tolerance for curves is modelled like the vectors'.
* **Transient peak.** Reported at the events witness (final + the largest single-style excess); an upper bound, not a
  trace of the parser.
* **Running contexts** (30 / 128) cannot be counted statically; D reads them.
