# XML2 engine contract for the playable roster (XMen2.exe)

Topic B of the XML1 hero conversion. Everything below was read from XMen2.exe (research/characters/ghidra/XMen2.exe,
same SHA-1 as the install) with tools/disasm.py and Ghidra headless decompiles. New decompiles produced for this
report: `research/heroes/decomp_heroes1.c` .. `decomp_heroes7.c` (function index at the end). Older ones cited as
`research/characters/ghidra/decomp*.c`. Addresses are VAs. Anything not read in the exe is marked **UNVERIFIED**.

Singletons used throughout (getter -> vtable):
- **registry** = CStats registry, getter `FUN_0044b8f0`, vtable `0x68544c` (slot map in section 1.3).
- **game** = getter `FUN_0046dce0`, vtable `0x686e1c`.
- **talent mgr** = getter `FUN_004c05b0`, vtable `0x68ec24` (object 0x3228 bytes, ctor `FUN_004c0370`).
- **unlock mgr** = getter `FUN_0048fed0` (vt+0x38 = is stats index unlocked, vt+0x2c = level-up notify).
- **console** = getter `FUN_0055c890` (vt+0x18 run command now, vt+0x1c queue).

## 0. Executive summary (what the conversion must respect)

1. herostat is parsed first, so heroes get stats indices 1..N; the exe keeps 22 per-hero persistence records indexed
   by stats index (`FUN_00449b40`, `0x449b40`, loop `< 0x16`), the 21-slot ordinal map (`0x44bb13`) and a 21-entry
   roster list (`FUN_005db590`, `0x5db590`, `iVar7 < 0x15`). **21 heroes is the practical maximum; fewer is code-safe.**
2. New Game hardcodes the party **by name**: `magneto`, `cyclops`, `wolverine`, `storm` (`FUN_004a7b10` = script
   function `startFirstMission`, string pushes at `0x4a7b41/0x4a7b50/0x4a7b7b/0x4a7b8a/0x4a7bb5/0x4a7bc4/0x4a7bef/0x4a7bfe`,
   slot writes via game vt+0xf0 = `FUN_0046c810`). Names are stored without validation; they are resolved at the first
   zone load (`FUN_00486dd0` -> game vt+0x18c = `FUN_0046a6c0` "Hero_%s"). An unknown name reaches `FUN_004498d0`, which
   returns the *fallback CStats* for stats index 0 -> behaviour UNVERIFIED (assume broken hero or crash). Either keep
   those four names in herostat, or make sure the team menu (`loadMapChooseTeam`) replaces the slots before the first
   `loadmap`, or patch the four string pointers.
3. There is **no script function that adds/removes a party member** (confirmed against the full 289-entry table): the
   only writers of the party slots (game+0x14..+0x20) are startFirstMission, the team menu (`0x5e252a`, `0x5e3859`,
   confirm `0x5f464b`), the danger room (`0x4d1a50`...), save load (`0x484c87`) and resetgame (`0x5f3082`).
4. **Talent capacity is 100 simultaneously registered talents** (name nodes `FUN_004bdfb0`, objects `FUN_004be7b0`,
   id nodes `FUN_004be010`, all `cmp ecx,0x64`; drop path `FUN_004c0080` when any pool count == 100). Shared talents
   (ids 0..98) count against it. XML2 retail: 34 shared + 4 party files of <=15 = <=94. **The pipeline's XML1-mode
   shared_talents has 88 entries (52 empty NPC talents were added) -> only 12 slots remain and the party heroes'
   talent files are already truncated silently in the current builds.** Budget rule: shared + sum(party heroes' file
   talents) <= 100, keep margin for danger-room extras.
5. Per-hero talents load **only** through the character package's `xml_talents` entry (handler `FUN_00561510`):
   basename of the entry (`FUN_00560550`) must equal the stats name; file = `data/talents/<statsname>.xmlb`
   (`FUN_004c05f0`, format string `0x68ea28`), ids = (statsIndex+1)*100 .. +99 (`FUN_004bdc00`).
6. herostat `power1..power4` are the four *assigned power slots* (CStats+0xc4, +0xd9, +0xee, +0x103; stores at
   `0x4ba0c7/0x4ba0f3/0x4ba11f`), talent `power="powerN"` names a FightMove of the hero's powerstyle; both are FightMove
   names, not indices. An unknown `ch_*` handler degrades to the `%default%` handler (`FUN_004fd860`, `0x4fd860`).
7. Skins: prefix byte + 2-digit variant; `skin_<costume>` only for the 9 names in table `0x6d8aa0`; loading screens are
   `textures/loading/%02d%02d.igb` with the **prefix and a variant 1..3** (not the costume) chosen among unlocked
   heroes (`FUN_00487000`, `FUN_004871d0`); HUD/UI heads are `hud/hud_head_<skin>`, `ui/models/characters/<skin>`,
   `ui/hud/characters/<skin>` with fallbacks current costume -> default costume -> variant 01 (`FUN_005f4ec0`).
8. Saves are **positional by stats index** (no names in the hero section, `FUN_00449a60`/`FUN_0044b970`): any change
   of herostat order/count between builds invalidates saves. Not a blocker for development; document for players.

---

## 1. Boot: how herostat is loaded and mapped

### 1.1 Boot sequence (`FUN_0044bab0`, registry vt+0; decomp1.c:480)
```
registry vt+0x10 ("data/herostat.xmlb", 0)      ; 0x44bab4   FUN_0044c030
registry vt+0x10 ("data/npcstat.xmlb", 0)       ; 0x44bac7
console vt+0x18 ("runscript unlockCharacter('','astonishing')")   ; 0x44bad1  (0x685538)
registry vt+0xa8 (0)                            ; FUN_0044a760 -> FUN_00449b40: init hero records block 0
for i in 0..20:  DAT_00a6a800[ vt+0x4c(i) ] = i ; 0x44bb13 cmp esi,0x15 ; vt+0x4c = FUN_0044b6e0 = short[+0x120dc+2i]
```
- `DAT_00a6a800` maps *stats index -> hero ordinal*. Its only reader is `0x5fa2ca` in `FUN_005f9eb0` (multiplayer
  pad/menu code: ordinal of the active hero into `DAT_00a6a7fc`). With fewer than 21 heroes the extra iterations read
  0 from the zero-filled list and write `DAT_00a6a800[0]` (harmless). With more than 21 the extra heroes have no
  ordinal (UI-only consequence).
- `FUN_00449b40` (0x449b40) walks stats indices 0..21 (`iVar1 < 0x16`) and initialises the 0x160-byte persistence
  record of every index that is a loaded hero. **Records exist only for stats indices < 22.** herostat is loaded
  first, so heroes occupy indices 1..N; keep N <= 21.

### 1.2 The stats file loader (`FUN_0044c030`, registry vt+0x10; decomp1.c:591, disasm 0x44c250..0x44c330)
Per `<stats>` element under `<characters>`:
- `platform` attribute -> `FUN_004bdb30` vt+0xc (platform match; XML2's two `platform="PC"` heroes count on PC).
- `name` -> registry vt+0x3c lookup (`FUN_0044acc0`: strncpy 0xff, lowercase `FUN_00602080`, hash). New name: index =
  `++count` (count at +0xbba8 starts at 1; `0x44c1a7 cmp eax,0x129` -> **296 usable names**, extra silently skipped).
- Entry record, 0x1c bytes at `this+0x9b28 + 0x1c*idx`:
  | off | field | set at |
  |---|---|---|
  | +0x00 | name (interned string handle) | 0x44c2xx (`FUN_0041a320`) |
  | +0x04 | charactername | `0x44c270 lea ecx,[esi+4]; call FUN_00425df0` |
  | +0x08 | skin string | `0x44c28e lea ecx,[esi+8]` |
  | +0x0c | characteranims | `0x44c2ac lea ecx,[esi+0xc]` |
  | +0x10 | CStats handle (0 = not loaded) | LAB_0044c3c9 |
  | +0x14 | level (byte, atoi) | `0x44c2f3` |
  | +0x15 | team enum (byte) via `FUN_0045fbd0`: hero=0x1d, enemy=0x1e, altenemy=0x1f, else 0 | `0x44c2d2` |
  | +0x16 | textureicon (short, atoi) | `0x44c32a` |
  | +0x18 | flags: bit0 = from herostat, bit1 = unlocked, bit2 = playable (`'t'`/`'T'` first char, `0x44c30c`), bit3 = preload, bit4 = loading, bit5 = misc (vt+0x94) | 0x44c2xx |
- `is hero` = the file name compares equal to "data/herostat.xmlb" (`_stricmp` at 0x44c0xx, decomp1.c:631). Heroes are
  appended to the hero list `short[+0x120dc]` (count `+0x12330`), which has room for 298 entries (no bound check).
- **Heroes' full CStats are built at boot** (LAB_0044c3c9: `test al,1` at 0x44c3e4 -> load now): pool check
  `0x44c3fb cmp [ebp+0x9aa0],0x1f` (31 CStats objects total, `FUN_004496d0` wraps at 0x1e), allocate `FUN_0044ab00`,
  parse with `FUN_0044bda0`: every attribute through `FUN_004b9c40`, then children `FUN_0044bcf0` (co-op level bump for
  non-heroes), `FUN_00448ba0` (`Talent`), `FUN_004489c0` (`FlyEffect`), `FUN_004495e0` (`Multipart`), `FUN_00449dc0`
  (`pattern`), `FUN_00448a40` (`Race`, table `0x6d9710`). NPC stats are only loaded on demand (bit3/param_3), and
  `FUN_0044b090` (vt+0x1c) unloads preloaded NPCs, never heroes. So 21 heroes hold 21 of the 31 CStats slots
  permanently, which is XML2 retail's own situation.
- Second registration of an existing name (npcstat entry also in herostat): `sVar5 != 0` -> LAB_0044c3c9 with the
  existing index; the npcstat definition is **not** parsed for a hero that is already loaded (`param_1[idx*7+0x26ce]
  != 0` -> skip). The herostat entry wins, the npcstat duplicate is dead data.

### 1.3 Registry vtable (0x68544c) slots that matter
| slot | func | meaning |
|---|---|---|
| +0x00 | 0x44bab0 | boot load (1.1) |
| +0x08 | 0x448960 | reset: talent mgr vt+0xc(7..10), vt+0xac(0), vt+0xa8(0) |
| +0x10 | 0x44c030 | load stats file |
| +0x14 | 0x4495a0 | mark entry for preload (bit3) |
| +0x18 | 0x448940 | preload by name |
| +0x1c | 0x44b090 | unload preloaded NPC stats |
| +0x2c | 0x449c00 | unlock(index): index 0 -> return; sets bit1, appends to unlocked list +0x11e84 (count +0x120d8), unlock mgr vt+0x28 |
| +0x30 | 0x449540 | clear all unlocks |
| +0x38 | 0x449430 | `_HERO<n>` placeholder rewrite (see 2.5) |
| +0x3c | 0x44acc0 | name -> index (0 if unknown) |
| +0x40 | 0x4498d0 | name -> CStats*; **unknown or unloaded -> `FUN_00448c60` fallback object (pool slot of handle 0)** |
| +0x44 | 0x44b6a0 | total names (+0xbba8) |
| +0x48 | 0x44b6b0 | hero count (+0x12330) |
| +0x4c | 0x44b6e0 | hero list[i] -> stats index |
| +0x5c | 0x44b6f0 | unlocked list[i] |
| +0x60/+0x64/+0x68/+0x6c | 0x44b700/0x44b720/0x44b740/0x44b760 | entry name / charactername / skin / characteranims |
| +0x70 | 0x44b780 | entry team byte |
| +0x74 | 0x44b890 | index -> CStats* (fallback object if unloaded) |
| +0x78 | 0x44b7a0 | is loaded |
| +0x7c | 0x44b7c0 | is hero (bit0) |
| +0x80 | 0x44b7e0 | playable (bit2) |
| +0x84 | 0x44b800 | unlocked (bit1) |
| +0x88 | 0x449d20 | level (CStats level if loaded hero, else entry byte) |
| +0x90 | 0x44b840 | textureicon |
| +0xa0 / +0xa4 | 0x449a60 / 0x44b970 | save / load (section 5) |
| +0xa8 | 0x44a760 | init hero record block 0/1 |
| +0xb0/+0xb4/+0xb8 | 0x449e60/0x449eb0/0x449f00 | load / unload character package by name / unload all |
| +0xbc/+0xc0 | 0x44b670/0x44b680 | get/set `DAT_006d970c` (new-game-in-progress byte, set by startFirstMission) |
| +0xc4/+0xc8/+0xd0 | 0x44b6d0/0x44b690/0x448a90 | max XP (=XP(99)+1) / 99 / XP threshold for level 1..100 |
| +0xd4 | 0x449fe0 | award XP to all loaded heroes (team 0x1d) |
| +0xdc | 0x44be40 | level-up hero by N (clamps to 99) |

### 1.4 Attributes the per-character parser accepts (`FUN_004b9c40`, decomp3.c:5-945)
Recognised (strcmp chain, case-insensitive): name (0x20 chars -> CStats+0x150), charactername (0x1f), leadername,
leaderpowerup, sounddir, skirmish_boost, skin, effect_skin_*, skin_*, leaderskin, mutantskin, mutatechance,
characteranims, footstepfx, deathnode, grabbolt, powerstyle, power1, power2, power3, power4, moveset1, level,
experience, xpaward, strength, speed, body, mind, weapon (accepted, ignored: 0x4ba373-0x4ba383), material, counter,
heaviness, npchealthscale, specific_health, specific_attack, specific_defense, size, team, large, selectable,
scale_factor, resurrect, aiclasstype, alertradius, attackrange, meleetimeroffset, meleetimerrandomadd,
rangedtimeroffset, grabchance, pickupthrowchance, scriptlevel, willflee, teleportpathfail, canFly, canSeeStealthed,
fleeDistance, dangerRating, ailevel, aipower, xpexempt, canthrowally, aiforceranged, ainocover, combolevel, ainomelee,
ainostraffe, aimaxcoverheight, canbeallythrown, ignoreboundsscaling, inherit/playable/textureicon (consumed by the
loader only, skipped here: decomp3.c:884-886), nonhumanoidskeleton, scaleattacks, targetheight, autospend.
Unknown attribute -> `return 0` (decomp3.c:911-912); `FUN_0044bda0` ignores the return value, so **unknown attributes
are silent** (XML1's RatingMelee/RatingRanged/RatingSupport/RatingDurability, leader, throwally, weapon are ignored).

Hero-only attributes and where they land:
- `power1..power4` -> `FUN_004b7f30(CStats+0xc4 / +0xd9 / +0xee / +0x103, value)` (0x4ba0c7, 0x4ba0f3, 0x4ba11f, next
  block): the four **assigned power slots**, 0x15 bytes each (0x14 chars + NUL). Also written at runtime by
  `FUN_004b84b0(slot, name)` and searched by `FUN_004b8450(name)`; saved (5.1).
- `autospend` -> CStatsHero vt+0x90(name) (decomp3.c:914). Classes come from `data/autospend.xmlb`
  (`FUN_0043d0c0`, 0x43d0eb): `<AutoSpend><CharacterClass name body mind speed strength><bonus rate start body mind
  speed strength/>` (<=4 bonus rows, `FUN_0043d370` `!= 4`). XML2 classes: bruiser, bruiser_light, support,
  support_heavy. Unknown class name at spend time: UNVERIFIED (probably no auto-spend). XML1 herostat has no
  `autospend`; the converter must choose one per hero (or add classes to autospend.xmlb, the format allows it).
- `textureicon` -> entry +0x16 (section 3.4). `playable` -> entry bit2 (section 3).
- `leadername/leaderskin/mutantskin/mutatechance/leaderpowerup/skirmish_boost` -> CStatsHero vt+0xc0/0xd0/0xe0/0xe8/
  0xdc/0xac: danger-room/leader mechanics; XML2 heroes only use `skirmish_boost` (optional).
- `skin_<costume>` (0x4b9e8d): `FUN_00488400(name+5)` looks the suffix up in the costume table `0x6d8aa0`
  (default=0, astonishing=1, aoa=2, 60s=3, 70s=4, weaponx=5, future=6, winter=7, civilian=8); accepted `0 <= idx < 10`,
  value `atoi` -> byte at CStats+0x255+idx (decomp3.c:920-926). Unknown suffix (XML1 `skin_magmacivilian`) is ignored.
- `effect_skin_<costume>` (0x4b9e9f) -> interned effect name for that costume (0x4b9e9f..; XML2 Sunfire aoa).

### 1.5 Fewer than 21 / more than 21 / names absent from XML2's list
- Fewer than 21: every consumer is count-driven (`vt+0x48` hero count, `vt+0x44` total, per-index flag checks). The
  only fixed-21 loop is 0x44bb13 (harmless, see 1.1). Save/load iterate by flags (5.1). **Memory-safe, untested in game.**
- More than 21: hero list holds 298, but stats indices >= 22 get no persistence record (`FUN_00449b40`), no ordinal
  (1.1), and the roster screen lists at most 21 (`FUN_005db590`). Do not exceed 21.
- Names absent from XML2's herostat: nothing in the loader depends on XML2's names. The exe itself names heroes in
  exactly these places: startFirstMission (2.1), the newgame/resetgame default unlock list (2.3: magneto, bishop,
  juggernaut, wolverine, cyclops, storm, and 11 more behind `DAT_006f3c2d == 0`), builddefaultteam ini defaults
  (magneto, cyclops, wolverine, bishop), danger-room tables (`FUN_004d1d80`, `0x4d1fb8`, `0x4d21d7`, `0x4d22a6`,
  `0x4d223e`: wolverine, colossus, storm), and six gameplay special cases on the string "wolverine"
  (`FUN_0041c760` 0x41c7ea, `FUN_00422b40` 0x422e93, `FUN_0042fca0` 0x430219, `FUN_00430d40` 0x43153c,
  `FUN_004ee2d0` 0x4ee345: `_stricmp("wolverine", stats+0x150)` gates entity vt+0x1f8/vt+0x1f4(3, ...) calls, i.e.
  a wolverine-only animation/state; what it does exactly is UNVERIFIED). Unlock of an unknown name is a no-op
  (vt+0x3c -> 0 -> `FUN_00449c00` returns at `param_2 != 0`). **Keep XML1's Wolverine named exactly `Wolverine`.**
- Name limits: stats name <= 31 chars (strncpy 0x20 at CStats+0x150), **< 19 chars to appear in the roster screen**
  (`FUN_005db590`: `(len) < 0x13`), lookups are case-insensitive.

---

## 2. New Game and every way to set the starting team

### 2.1 `startFirstMission` = `FUN_004a7b10` (script function table entry; decomp_heroes1.c:1-95)
```
FUN_004b2880()->vt+0x44()                 ; 0x4a7b1a
game->vt+0x280(1)                         ; FUN_00469d60: game+0x616 bit2 = 1 ("new game")
registry->vt+0xc0(1)                      ; FUN_0044b680: DAT_006d970c = 1
for (i, name) in [(0,"magneto"),(1,"cyclops"),(2,"wolverine"),(3,"storm")]:
    interned = FUN_0041a320(lower(name))  ; strings 0x682504 / 0x682548 / 0x6824a8 / 0x6824c4
    game->vt+0xf0(i, &interned)           ; FUN_0046c810: party slot i = name (game+0x14+4i)
if game->vt+0x268() < 2:                  ; FUN_00469d30 = game+0x60c = difficulty (set by setDifficultyLevel -> vt+0x26c = 0x469d40)
    console->vt+0x18("runscript menus/new_game")        ; 0x4a7c42, string 0x68d63c
else:
    console->vt+0x18("runscript menus/new_game_hard")   ; 0x4a7c57, string 0x68d61c
```
- `FUN_0046c810` (0x46c810): slot 0..3 only; lowercases the name (`FUN_005602b0`), compares with the current slot
  name; if the slot held a different non-empty name it calls registry vt+0x40(oldname) and `FUN_004c1dd0` vt+0x10 on
  it (drops that hero's talent values), then stores the interned name. **No herostat validation.**
- The names are used **by name** later: `FUN_00486dd0` (0x486dd0, called at zone load) loops slots 0..3 via game
  vt+0xe0 (`FUN_0046c510`, returns &game+0x14+4i) and for each non-empty slot calls game vt+0x18c =
  `FUN_0046a6c0(name)`: builds `"Hero_%s"` (0x6870cc at 0x46a759), creates an `actor` entity through
  `FUN_004625c0`->vt+0x1c("actor", name) and `FUN_004612e0`, forces team 0x1d (`FUN_0041d3e0(0x1d)`), registers it with
  game vt+0x184 and runs `FUN_004bc8e0` (stats -> actor). The actor's CStats come from registry vt+0x40(name): for a
  name that is not a stats name this is the **fallback object of handle 0** (`FUN_004498d0` -> `FUN_00448c60`), so
  the hero would spawn with empty stats (no skin/anims). Consequence UNVERIFIED but must be avoided:
  **every name that can be in a party slot at `loadmap` time must be a herostat name.**
- Alternatives for a different first party, in order of cost:
  1. Keep entries named `magneto`, `cyclops`, `wolverine`, `storm` in the converted herostat (XML1 has Cyclops,
     Wolverine, Storm; `magneto` would have to be an alias/extra entry).
  2. Make the first `loadmap` go through the team menu (`loadMapChooseTeam`, 2.4): the menu rewrites all four slots
     (`FUN_005f464b`, 0x5f464b: game vt+0xf0 x4 then `"loadmap %s 1"`) before anything is spawned, so the hardcoded
     names never reach `FUN_0046a6c0`. The pipeline's new_game.py already ends in `loadMapChooseTeam` (SPEC 12.6);
     `--start-zone` / `--tour` hooks use `loadMapKeepTeam` and therefore DO spawn the four names.
  3. Exe patch: the eight `push imm32` string pointers (two per name) at 0x4a7b41/0x4a7b50, 0x4a7b7b/0x4a7b8a,
     0x4a7bb5/0x4a7bc4, 0x4a7bef/0x4a7bfe; or overwrite the string bytes in place ("magneto\0" 8 bytes at 0x682504,
     "cyclops\0" 8 at 0x682548, "wolverine\0" 10 at 0x6824a8, "storm\0" 6 at 0x6824c4). Existing exe strings usable
     as replacements: "iceman" 0x682520, "gambit" 0x682534, "rogue" 0x6824dc, "phoenix" 0x6824ec, "nightcrawler"
     0x6824f4, "colossus" 0x682550, "beast" 0x696424 (not "jubilee", "magma", "psylocke", "frost").
- Which script runs: `menus/new_game.py` (difficulty < 2) or `menus/new_game_hard.py`; the exe does not read the
  roster from the script, only the script's own calls (unlockCharacter, loadMap*) matter.

### 2.2 Console `newgame` / `resetgame` (`FUN_005f3610` -> `FUN_005f2e70(0)` + `FUN_005f2090`; decomp_heroes1.c:177-445)
`FUN_005f2e70` (resetgame handler body) is the New Game reset:
- clears zone/game-var stores (`FUN_004a1670` vt+4), "clearsidemissions", missions (`FUN_0048a0e0`), registry vt+8
  (`FUN_00448960`: talent mgr vt+0xc(7),(8),(9),(10) = unload party talents; vt+0xac(0)/vt+0xa8(0) records), vt+0x34,
  vt+0xc, vt+0x30 (all unlocks cleared), game vt+0x280(0);
- for slots 0..3 with a name: registry vt+0x40(name) -> `FUN_004bc2c0(1)` (unload that hero's character package)
  then game vt+0xf0(i, "") (slot cleared); game vt+0xe8 (`FUN_00468aa0` marks the 4 package-name slots "dirty");
- unlocks by name (vt+0x3c then vt+0x2c): magneto, bishop, juggernaut, wolverine, cyclops, storm; and if
  `DAT_006f3c2d == 0`: colossus, sunfire, nightcrawler, gambit, rogue, phoenix, iceman, toad (0x6824b4), scarletwitch,
  pyro_hero, sabretooth_hero (retail value of `DAT_006f3c2d` UNVERIFIED; retail starts with 6 unlocked, so it is
  presumably non-zero);
- `runscript unlockCharacter('','astonishing')` (costume 1 for all heroes).
Unknown names here are harmless no-ops.

### 2.3 Console `builddefaultteam` (`FUN_005f3be0` -> `FUN_005f3330`; decomp_heroes1.c:448-577)
Reads ini section `[HERO]` (0x6900dc) keys `Name1..Name4` (`"Name%d"` 0x6a37e4) with defaults magneto, cyclops,
wolverine, bishop, or `RandomHeroes` (random unlocked heroes via hero list vt+0x48/0x4c and unlock mgr vt+0x38);
fills only slots whose name is not already in the party (game vt+0x114 = `FUN_0046b010` returns -1). Sent from menu
code at 0x5e374c (registration 0x5f4c0f). It is not on the New Game path (startFirstMission overwrites the slots),
but the `[HERO]` ini keys are a data-only knob for whatever menu path uses it (UNVERIFIED which screen).

### 2.4 Script functions that touch the party (from research/scripts/xml2_api.json, handlers decompiled)
| function (args) | handler | what it really does |
|---|---|---|
| startFirstMission () | 0x4a7b10 | 2.1 |
| unlockCharacter (s,n) | 0x49f520 | name -> vt+0x3c -> vt+0x2c unlock; 2nd arg costume name -> index via table 0x6d8aa0 (`FUN_005602f0`); costume > 0 -> `FUN_004b7ce0(idx)` on that hero's CStats (vt+0x40); **empty name + costume** -> for every hero (vt+0x7c) `FUN_004b7ce0` via vt+0x74 |
| isCharacterUnlocked (a) | 0x49f610 | vt+0x3c -> unlock mgr vt+0x38 |
| loadMapChooseTeam (s) | 0x4a0d30 | queues `"loadmap %s 0 1"`; `FUN_005f4770` (0x5f4770) with arg3=1 stores the zone in `DAT_008b12cc`, sets `DAT_008b134c` flags and opens the team menu (`FUN_005d8920` vt+0x68 = the `opencharactersmenu` handler 0x5f1cd0); the menu's confirm (`FUN_005f464b`) writes the 4 chosen names with game vt+0xf0 and sends `"loadmap %s 1"` |
| loadMapKeepTeam (s) | 0x4a0cc0 | `"loadmap %s 0 0"` -> game vt+0x150 (`FUN_004698f0`) directly, party unchanged |
| loadMapAddTeam (s) | 0x4a0bd0 | queues **`"resetgame"`** then `"loadmapaddteam %s"` (unregistered) -> resets the game and loads nothing. Never emit it. |
| extractionPointLite (a,s,s,s) / extractionPoint / extractionPointChange | 0x4a6d80 / 0x4a6b50 / 0x4a7020 | X-traction dialog -> team menu (`FUN_005eb300`, `extractionPointChange(%d,%i)` 0x68d4f8); needs the X-traction network flag (`FUN_004a1670` vt+0x54 of 0x68d540) |
| setteam (s,a) | 0x4a3a00 | entity AI team (BEHAVED_TEAM_* table 0x68a864), not the party |
| swapInStump (a) | 0x4a8e70 | swaps party actors for their cutscene stand-ins |
| awardXPToPlayable (i) / setXP (a,i) | 0x49d9d0 / 0x4a8660 | XP |
| moveHeroesToEnt, setFollowingHero, controlPlayerHeroWithAI, heroNoTarget, isActorOnTeam, setTeamInvisible, beATeamPlayer | | party-entity helpers, no composition change |

**Missing XML1 functions** (confirmed absent from the 289-entry table at 0x68a908): addHero, removeFromGroup,
setGroupLeader, setPowerStatus, enterSoloMode/exitSoloMode/soloModeCheck, levelUp, setInCampaign (-> unlockCharacter),
loadMapAddTeam (present but broken). Nearest XML2 equivalents: `unlockCharacter` + `loadMapChooseTeam` /
`extractionPointLite` (player picks), `swapInStump`, `setFollowingHero`, `controlPlayerHeroWithAI`.

### 2.5 `_HERO<n>_MC_` placeholders and `_HERO1_.._HERO4_` tokens
- Registry vt+0x38 = `FUN_00449430` (0x449430): a stats name containing `_HERO` followed by a digit 1..5 (strstr at
  0x449459) is replaced by party slot n-1's name (game vt+0xe0). This is how the front-end zones spawn the current
  party through npcstat's `_HERO1_MC_.._HERO4_MC_` entries (the pipeline keeps them: SPEC 5.1 KEEP_X2).
- Script entity arguments `_ALL_HEROES_`, `_ACTIVE_HERO_`, `_HERO1_`..`_HERO4_` are resolved by `FUN_004a1700` (0x4a1736)
  and `FUN_004a7e30` (0x4a7f78) from game vt+0x120 (party entity list).

---

## 3. Hero selection / team menu: what each hero needs

### 3.1 Team menu (ui/menus/team.xmlb, type TEAM_MENU, igb x2m_team)
- Opened by `FUN_005d8920` vt+0x68 (console `opencharactersmenu` 0x5f1cd0; `loadmap zone 0 1`; X-traction).
- Roster screen init `FUN_005e1ec0` (0x5e1ec0): loads packages `generated/maps/package/menus/characters_heads` and
  `.._pc` (0x5e1f06/0x5e1f19, type 0xb), opens `roster_screen` with `ui/models/m_team_roster_screen` (pointers
  0x6e766c/0x6e758c), then `FUN_005db810` -> `FUN_005db590` builds the roster: for each hero ordinal (vt+0x48/vt+0x4c):
  must be loaded (vt+0x78), CStats team == 0x1d (+0x2a0), **name length < 19**, **at most 21 entries**; then
  `qsort(list, 0x15, 0x14, FUN_005db320)` (sort key UNVERIFIED). `FUN_005db810` then shows each roster hero that is not
  in the party (game vt+0x114 == -1) and has CStats flag +0x2ae bit 0x40 (meaning UNVERIFIED; cleared by
  `FUN_004bbff0` at 0x4bc00c), with its unlocked state from unlock mgr vt+0x38(index).
- The head models: `characters_heads.pkgb` lists `ui/models/characters/<prefix>01` for each hero + `9999` +
  `m_team_roster_screen`; `_pc` adds the two PC heroes. A converted roster needs a rebuilt pair with the XML1 skins
  (+14000, variant 01) and should keep `ui/models/characters/9999` (generic head; its string lives in the CMenuTeam
  pointer table at 0x6e5fa8; the earlier "code xref at 0x5f7501" is a false positive: bytes `58 0C 6A 00` of
  `mov ebx,[eax+0xc]; push 0`). Whether the menu substitutes 9999 automatically for a missing head is UNVERIFIED.

### 3.2 Head / HUD / UI model lookup (`FUN_005f4ec0`, decomp1.c:374-475; caller 0x5d5a02)
Given a stats name and a mode: index = vt+0x3c(name). If not loaded (vt+0x78 == 0) the skin string is the entry's
skin (vt+0x68). If loaded: CStats = vt+0x40(name) and `FUN_004b8090(buf, 0x40, -1, 0)` = current costume skin. Then
up to three candidates: [0] as computed, [1] `FUN_004b8090(..., -1, 1)` = default costume (byte +0x255),
[2] `FUN_004b8090(..., 1, 0)` = variant `01`. Path by mode: `hud/hud_head_%s` (0x6a39a4), `ui/models/characters/%s`
(0x6a39b4), `ui/hud/characters/%s` (0x6a39cc); each candidate is checked against the loaded packages
(`FUN_0056f9f0` vt+0xc) and loaded on first hit; **no hit -> returns 0, nothing shown, no crash.**
Character packages therefore list `model HUD/hud_head_<skin>` and `model ui/HUD/characters/<skin>` (XML2
cyclops_0103.pkgb: hud_head_0101 + ui/HUD/characters/0103), and the menus package lists the ui/models head.

### 3.3 Packages a hero needs (package name format `FUN_004b8330`, 0x4b8384: `generated/characters/%s_%s%s`)
- `<name>_<skin>.pkgb` and `<name>_<skin>_nc.pkgb` for every costume the player can select (`_nc` when the zone has
  `combat_is off`, chosen by `FUN_00484990` vt+0x3c). XML2 cyclops_0103: actorskin, actoranimdb, texture
  `textures/ui/cyclops_icons1`, **`xml_talents data/talents/cyclops`**, model HUD/hud_head_0101, model
  ui/HUD/characters/0103, effects, power models, `xml data/entities/ents_cyclops`, `fightstyle data/powerstyles/ps_cyclops`.
- `<name>_xml.pkgb` (`FUN_004bc100`, 0x4bc1f6 `generated/characters/%s_xml`): xml_talents + entities + powerstyle only;
  loaded when a party slot's package name has not changed since the last zone (game vt+0xe4 dirty check
  `FUN_0046a3e0` on the 4 x 0x40 names at game+0x3c).
- Party heroes load their package at zone load (`FUN_004bc100`, callers 0x4bca37/0x5bd60a, slot 7..10 = party slot+7
  from game vt+0x118 = `FUN_0046b070`); non-party heroes (slot 0xb) load a package only in danger-room context
  (`FUN_004c87a0` = `DAT_00782728 != -1`). Browsing the roster does not load packages or talents.

### 3.4 Icons (`textureicon`)
- Stored in the entry (+0x16, vt+0x90 = `FUN_0044b840`). Read by exactly two menu routines: `FUN_005b3bb0`
  (0x5b3eb0; a "characters" list: for each stats index 1..count with the playable bit (vt+0x80): if not unlocked
  (unlock mgr vt+0x38) -> string id 0x2cd placeholder and icon 0x3f; else charactername (vt+0x64, `"%s"`) with
  item->vt+0xa4(icon = textureicon)) and `FUN_005c3c40` (0x5c3cc6, single character item). The index selects a cell
  of the list item's icon grid (menu item attributes `icons`, `icons_cols`, `icons_rows`, e.g. codex uses
  `textures/ui/mini_convo_icons.png` 8x8). Which texture/grid holds the hero portraits for the hero list is
  UNVERIFIED (team.xmlb's MENU_ITEM_LISTCHARS items carry no `icons` attribute; the atlas is presumably inside
  x2m_team.igb). XML2 values: cyclops 0, phoenix 1, wolverine 2, storm 3, nightcrawler 4, rogue 5, iceman 6, colossus
  7, professorx 9, sunfire 10, gambit 11, ironman 13, bishop 17, pyro 21, scarletwitch 22, magneto 23, sabretooth 24,
  toad 31, juggernaut 32, deadpool 40. A menu item XML attribute `playable="true"` (`FUN_005c3b40`, 0x5c3b40) makes
  the item filter by the stats playable bit (`FUN_005c3ba0`, 0x5c3ba0: also requires team 0x1d unless the menu is in
  enemy mode).
- Talent icons: per hero a 4x4 sheet `textures/ui/<hero>_icons1.png` (talent attributes `icon_texture` 0x68eb94,
  `icon`, read at 0x4be4c0/0x4be480; back plate `textures/ui/talent_icon_back.png` 0x6a1008 at 0x5c5905).

### 3.5 Loading screens (`FUN_00487000` 0x487000, `FUN_004871d0` 0x4871d0, `FUN_00486ec0` 0x486ec0)
`FUN_00487000` collects every stats index 1..count for which `FUN_004871d0(idx, variant, 0, 0)` succeeds for some
variant 1..3: the index must be a hero (vt+0x7c) **and unlocked** (vt+0x84, or unlock mgr vt+0x38 depending on
`FUN_00610d20`), CStats = vt+0x74(idx), path `"textures/loading/%02d%02d.igb"` (0x688f7c at 0x487268) formatted from the
**prefix byte** (CStats+0x254) and the **variant argument 1..3** (not the costume); existence via file mgr
(`FUN_005642d0` vt+0x38); on success the `.png` name (0x688f5c) is returned. A random unlocked hero and variant is
picked; if none matches, `FUN_00486ec0` falls back to a fixed list (`textures/loading/x_jet` 0x688f44 etc.) -> silent.
XML2 ships e.g. 0103, 0202, 0203, 0302, 0303, 10503 (prefix 105 -> 5 digits). For XML1 heroes with prefixes 140..239 the
names are `textures/loading/1400x`..`2390x`; the pipeline already copies XML1's 23 numeric loading screens with +14000
(characters.py:430-439).

### 3.6 What fails silently vs. what is dangerous
Silent: missing HUD/UI head (3.2), missing loading texture (3.5), unknown attribute (1.4), unknown `skin_<x>` suffix
(1.4), unknown name in unlockCharacter (2.2), unknown talent name on a `<Talent>` (4.5, queued), unknown `ch_*`
handler (4.6), talent file entries beyond the pools (4.3, **the dangerous silent one**), unknown `resurrect`/`aiclasstype`
values (default 0).
Dangerous: party slot name not in the stats table (2.1), > 296 names (1.2), hero name >= 19 chars (dropped from the
roster list), heroes at stats index >= 22 (no records), > 31 CStats loaded (pool full -> `LAB_0044c3c9` skips the load,
`FUN_004498d0` hands out the fallback object), `loadMapAddTeam` (resets the game).

---

## 4. Talents and powers

### 4.1 Talent manager pools (object 0x3228 bytes, ctor `FUN_004c0370`; decomp_heroes3.c:1-36)
| pool | allocator | capacity | evidence |
|---|---|---|---|
| talent files | `FUN_004bea20` | 9 | `0x4bea54 cmp ecx,9`; `FUN_004c0460` `+0x358 != 9` |
| name -> id nodes (0x2c stride, region +0x364) | `FUN_004bdfb0` | 100 | `0x4bdfe4 cmp ecx,0x64` |
| talent objects (0x24 stride, +0x1724) | `FUN_004be7b0` | 100 | `0x4be7e4 cmp ecx,0x64` |
| id -> handle nodes (0x10 stride, +0x2890) | `FUN_004be010` | 100 | `0x4be044 cmp ecx,0x64` |
Registration `FUN_004c0080` (0x4c0080; decomp_heroes1.c:2388-2487): name lookup (`FUN_00501410`, red-black tree at
+0x368); a **new** name is dropped (`return 0`) when `param_1[0x595] == 100 || param_1[0x9bd] == 100 || param_1[0xc24]
== 100` (the three counts), when `id > FUN_004bde80(2,0x10)` = 65536, or when the id is already used (`FUN_004d4e80`).
The file loader `FUN_004c0460` still returns 1, so **overflow is silent**. Each object records its owner slot (+4)
and file node (+8) via `FUN_004be1f0`.
Unload: talent mgr vt+0xc = `FUN_004bfe60(slot)` (0x4bfe60) frees every object/name/id node and file record with that
owner. Callers: `FUN_00448960` (registry reset; slots 7,8,9,10), `FUN_004bc100`/`FUN_004c06a0` (party slot whose package
changed at zone load), `FUN_004bc2c0` (hero unload, only if slot != 0xb), `FUN_004b7b90` (wrapper). Shared talents are
owner slot 2 and are never unloaded.
**Budget: shared_talents count + sum(talents in the 4 party heroes' files) [+ danger-room loads] <= 100.** XML2
retail: 34 + 4*15 = 94 worst case (files: bishop 15, colossus 13, cyclops 13, deadpool 10, gambit 14, iceman 15,
ironman 14, juggernaut 14, magneto 14, nightcrawler 14, phoenix 15, professorx 7, pyro 15, rogue 12, sabretooth 14,
scarletwitch 15, storm 15, sunfire 15, toad 12, wolverine 14). **build/xml1_tour ships 88 shared talents** -> the
XML2 stand-in heroes currently get at most 12 talents in total; the 52 empty NPC definitions (characters.py
`ensure_talent`) must be cut back (see 4.5 for why most are unnecessary).

### 4.2 Shared talents
`FUN_004c05d0` (talent mgr vt+0, 0x4c05d0) -> `FUN_004c0460("data/shared_talents.xmlb", 0, 99, 0, 2)`: ids 0..98 in
file order, the 100th and later `<talent>` elements are skipped (`param_3 < param_4`, decomp13.c:38).

### 4.3 Per-hero talent files
- Trigger: package entry `<xml_talents filename="data/talents/<name>"/>` -> handler `FUN_00561510` (type registered
  by `FUN_00562800`, vtable 0x69b000): `FUN_00560550` (basename: strrchr of '.', '\\', '/') + `FUN_00560000` -> 0x40-char
  name -> talent mgr vt+8 = `FUN_004c05f0(name, DAT_006e087c)` where `DAT_006e087c` is the package context slot set in
  `FUN_00561d40` (party slot + 7, or 0xb).
- `FUN_004c05f0` (0x4c05f0; decomp13.c:58-81): only for slot 7..10 or 0xb; `base = vt+0x30(name)` = `FUN_004bdc00` =
  `(registry vt+0x3c(name) + 1) * 100`; path `"data/talents/%s.xmlb"` (0x68ea28); `FUN_004c0460(path, base, base+100,
  name, slot)`; then registry vt+0x40(name) and `FUN_004bbff0` (recompute the hero's talents). Because the file cache
  compares by name (`_stricmp(file+0xc, name)`, decomp13.c:21) and `vt+0x40(name)` must find the hero, **the file
  basename must equal the stats name** (`data/talents/cyclops.xmlb` for stats `Cyclops`; case-insensitive).
- Per file at most 100 talents (base..base+99); id = base + position. Each `<talent>` may also carry
  `<talentvalues><talentvalue name level value/>` (read by `FUN_004bdc20` 0x4bdc20 and 0x4bf640..0x4bf6b1 into the
  talent-value manager `FUN_004c1dd0`; optional, XML1 trees do not need them).

### 4.4 Talent definition attributes (`FUN_004be1f0`, 0x4be1f0; decomp12.c:13-75)
`fightstyle="true"` (flag 0x40 at +0x21), `power` (FightMove name, 0x14 chars at +0xc), `hidden`, `value_priority`
(0..15), `type` (table 0x6d9910: `xtreme`=0, `attack`=1, `boost`=2; bits 0x30 at +0x21; XML2 files also use
`type="scale"` which is not in the table -> index unchanged/UNVERIFIED), `skirmish_locked`, and the level count =
sum over `<level>` of `count` (default 1, evaluated through `FUN_004c4bb0` vt+8 so `%value` expressions work). Display
attributes `descname`, `description`, `descshort`, `icon`, `icon_texture` are read by 0x4be480/0x4be4c0 and friends.
`<require>` (`FUN_004ac470`, 0x4ac470): `cat` = trait(1: item strength/speed/body/mind), level(2), counter(3),
xtreme(4), race(5: table 0x6d9710), character(6), anything else (skill/talent) = 0 -> `item` is a talent name resolved
through talent mgr vt+0x2c/vt+0x1c (must be registered when evaluated); `level`, `degree="see"`, `only_non_looped`,
`only_looped`. XML1's per-rank `<level description=...><require cat="level" level="N"/></level>` trees are
structurally valid XML2 talents. Special talent names cached by `FUN_004be130` (0x4be130): `ice_skating`, `flight`,
`night_faith` -> keep these names for flying heroes.

### 4.5 Talents on a stats entry (`FUN_00448ba0` -> `FUN_0043bb80`, 0x43bb80)
`<Talent name level limit>`: talent mgr vt+0x2c(name) (`FUN_004bf5e0`, known?) -> known: added to the CStats talent
heap (`FUN_0043a930`/`FUN_0043a990`); **a CStats holds at most 19 talents** (`if (*(param_1+0xb8) == 0x13) return 0;`
decomp_heroes3.c:2320). Unknown name: `FUN_0043ba60` (0x43ba60) queues it in a global 64-entry pending table
(`DAT_00712968 != 0x40`) keyed by the stats name -> **not an error**. So NPC talents that XML2 never defines (jug_punch,
marrow_shards, ... 40-odd of the 52 added empties) do not need shared definitions; only talents whose *registration*
matters (fightstyle_* for the fightstyle flag, anything a `<require>` names) do. Hero passive talents (might,
grappling, acrobatics, critical, toughness, mutantmastery, flight, leadership...) are shared talents in both games
(XML1 shared_talents.eng has 27 definitions).

### 4.6 Powers: binding and activation
- The 4 assigned power slots (CStats+0xc4 .. +0x117, 0x15 bytes each) are initialised from herostat `power1..power4`
  (1.4) and changed by the skills menu (`FUN_004b84b0`). Boss AI uses the same API (`FUN_00528020`: power1/power2/power9).
- A talent's `power="powerN"` and the slot strings are FightMove names in the hero's powerstyle (`FUN_004b8450` compares
  the slot strings; XML2 ps_cyclops FightMoves: `popupattack`, `power1`..`power11`). XML1 powerstyles name moves per
  rank (`optic_beam1`..`optic_beam10`, `cyc_xtreme1`) and XML1 talents use `power="0".."5"` (indices) - the
  conversion must produce XML2-style `powerN` FightMoves and `power="powerN"` talents plus `power1..power4` in herostat.
- Combat handler lookup `FUN_004fd860` (0x4fd860; decomp_npcai2.c:244): interned `ch_*` name -> map `DAT_00789e5c`;
  a miss (0x3fffffff) returns the handler registered under **`%default%`** (pointer 0x6dc3b8 -> string 0x691a7c,
  registered last in `FUN_004fd970` with vtable 0x692f4c). Called from the powerstyle FightMove parser
  (`FUN_004f6b80`, sites 0x4f68fa/0x4f6bf6). So an unregistered handler name loads and runs the default handler - the
  "tolerated" claim in characters.md is verified. The move still lacks the intended logic.
- Level/XP: level byte CStats+0x1c, max 99 (`FUN_004b7d10` 0x4b7d10; thresholds `FUN_00448a90` levels 1..100;
  vt+0xc4 max XP). `FUN_004b7d10` notifies unlock mgr vt+0x2c(level) for team-0x1d heroes (level-based unlocks).
  `FUN_004bbff0` (0x4bbff0) recomputes talents after a file load: for every talent handle of the CStats ->
  talent mgr vt+0x14 -> `FUN_0043b180` -> object vt+0x4c apply.

---

## 5. Saves

### 5.1 Format (`FUN_00449a60` save, registry vt+0xa0; `FUN_0044b970` load, vt+0xa4; decomp10.c:30, decomp_heroes1.c:5828)
1. For stats index 1..count with bit0 (hero) and loaded: `FUN_004b7e50` -> `FUN_0043a520` writes CStats+4 (0x18 bytes)
   and CStats+0x1c (0xa0 bytes: level/XP/attribute block), then CStatsHero vt+0 (hero data), then +0xc4 0x55 bytes
   (assigned powers), +0x120 1 byte (current costume), +0x11c 4 bytes (unlocked costume mask). No name is written.
2. `"[CHARACTERSUNLOCKED]"` + 600 bytes at +0x11e84 (unlocked list = raw stats indices, shorts; count +0x120d8).
3. `"[CHARACTERSRESTORE]"` + 1 byte (+0x11215).
4. 22 records x 0x160 from +0xf488 (`FUN_0043a520` + record vt+0): per-stats-index hero persistence
   (`FUN_004bcb00`: assigned powers at +0x100, costume +0x15c, mask +0x158, CStatsHero fields +0xc0..).
Load mirrors it in the same order (`vt+0x74(idx)` -> `FUN_004b7eb0`), re-sets bit1 for each listed index.
Consequences: the hero section is **positional**; if the roster (order, count, or identity at an index) differs
between the build that wrote the save and the one reading it, hero data lands on the wrong hero and, if the count
differs, the rest of the stream desyncs (UNVERIFIED how the loader fails: no length checks were seen). Unlock indices
also shift if npcstat entries are unlocked (only heroes normally are). Save folder is XML2's:
`%s\Activision\X-Men Legends 2\Save\saveslot%d%s` (0x69ab14, 0x69ab64) unless the launcher/proxy redirects it.
Not a blocker; state it in release notes and bump nothing else.

---

## 6. Costumes

- `skin="PPVV"` / `"PPPVV"` (`FUN_004b9c40` 0x4b9dbc-0x4b9de3): prefix -> byte +0x254 (must be <= 255), variant -> +0x255
  (= costume slot 0 "default"). `skin_<costume>="VV"` -> +0x255+idx for idx in table 0x6d8aa0 (1.4). Current costume
  index byte at CStats+0x120 (< 10), unlocked-costume bitmask at +0x11c (`FUN_004b7ce0(idx)` sets bit idx, 1..9;
  0x4b7ce0). Costume cycling `FUN_004b7fc0`/`FUN_004b7f50` (0x4b7fc0) walks slots 0..8 with a non-zero variant byte
  that are unlocked (mask) or force-unlocked by unlock mgr vt+0xa8 (cheat).
- Skin string `FUN_004b8090(this, buf, size, variant, flag)` (0x4b8090): `"%02d"` (0x68e4ec) or `"%03d"` (0x68e4e4,
  prefix >= 100) + `"%02d"`; variant = explicit, or flag 0 -> current costume's byte (1 if +0x120 >= 10), flag 1 ->
  default (+0x255). Package names (3.3), heads (3.2) and the actor skin all derive from it.
- Boot/newgame `unlockCharacter('','astonishing')` unlocks costume slot 1 for every hero; a hero without `skin_astonishing`
  just has variant byte 0 in slot 1 (never offered).
- XML1 costume attributes: `skin_60s`, `skin_70s`, `skin_future`, `skin_weaponx`, `skin_civilian` are in the table;
  `skin_magmacivilian` is not (dropped silently) - map it to a free slot name (e.g. `skin_winter`) if the costume is
  wanted. Values are 2-digit variants and survive the +14000 prefix move unchanged; only `skin` changes
  (e.g. Cyclops `0101` -> `14101`, prefix byte 141).
- Validation rule for a converted costume k of hero H: `actors/<prefix><VV>.igb` exists (in-IGB names renamed),
  packages `H_<prefix><VV>.pkgb` + `_nc`, `hud/hud_head_<prefix><VV>.igb` (or a fallback candidate), optional
  `ui/hud/characters/<prefix><VV>.igb`, `ui/models/characters/<prefix>01.igb` in characters_heads, loading screens
  `textures/loading/<prefix>01..03.igb` (optional, silent).

---

## 7. All exe-imposed requirements for a converted herostat

| # | requirement | address / evidence |
|---|---|---|
| R1 | herostat + npcstat unique names <= 296; herostat parsed first | 0x44c1a7 `cmp eax,0x129`; 0x44bab4/0x44bac7 order |
| R2 | herostat entries <= 21 (records for stats index < 22; roster list 21; ordinal map 21) | 0x449b40 `< 0x16`; 0x5db590 `< 0x15`; 0x44bb13 |
| R3 | every hero `team="hero"` (0x1d) | 0x45fbd0; roster 0x5db590 `+0x2a0 == 0x1d`; XP 0x449fe0; level notify 0x4b7d10 |
| R4 | `playable="true"` for heroes that must appear in menu lists (ProfXAstral-style heroes may be false) | 0x44c30c; 0x5b3bb0 vt+0x80; 0x4cb2f0 |
| R5 | stats name <= 31 chars, < 19 chars for the roster screen; case-insensitive uniqueness | 0x4b9c40 strncpy 0x20; 0x5db590 `< 0x13`; 0x44acc0 |
| R6 | the four New Game names exist in herostat, or the first load is `loadMapChooseTeam`, or the exe strings are patched | 0x4a7b41..0x4a7bfe; 0x486dd0 -> 0x46a6c0 -> 0x4498d0 fallback |
| R7 | skin 4-5 digits, prefix <= 255; `skin_<costume>` only for the 9 table names; variants 2 digits | 0x4b9dbc-0x4b9de3; 0x6d8aa0; 0x4b9e8d |
| R8 | packages `generated/characters/<name>_<skin>.pkgb`, `_nc`, and `<name>_xml.pkgb` for each selectable costume | 0x4b8384 (0x68e508), 0x4bc1f6 (0x68e930), 0x5b1578 (0x69e6ac) |
| R9 | the character package carries `xml_talents data/talents/<statsname>` and the file `data/talents/<statsname>.xmlb` exists (basename == stats name) | 0x561510 -> 0x560550 -> 0x4c05f0 (0x68ea28) |
| R10 | per-hero talent file <= 100 talents; **shared + party files <= 100 registered talents** | 0x4c0460 (`base+100`); 0x4bdfb0/0x4be7b0/0x4be010 `cmp 0x64`; 0x4c0080 drop |
| R11 | shared_talents <= 99 entries (ids 0..98) - and far fewer in practice because of R10 | 0x4c05d0 (0, 99) |
| R12 | a stats entry lists <= 19 `<Talent>` children | 0x43bb80 `== 0x13` |
| R13 | `power1..power4` name FightMoves of the hero's powerstyle; talent `power="powerN"` likewise | 0x4ba0c7.. (slots), 0x4b8450, 0x4be1f0 `power` |
| R14 | `autospend` names a class in `data/autospend.xmlb` (bruiser, bruiser_light, support, support_heavy or a new class) | 0x4bb2xx vt+0x90; 0x43d0c0 |
| R15 | `level="1"` and stats within 1..99 levels (cap 99) | 0x4b7d10, 0x448a90 (`< 0x65`) |
| R16 | heroes that fly keep the `flight` talent name (and `ice_skating`, `night_faith` if used) | 0x4be130 |
| R17 | XML1's Wolverine keeps the stats name `wolverine` | 0x41c7ea, 0x422e93, 0x430219, 0x43153c, 0x4ee345 |
| R18 | `_HERO1_MC_.._HERO4_MC_` npcstat placeholders stay | 0x449430 (`_HERO`) |
| R19 | HUD/UI heads: `hud/hud_head_<skin>`, `ui/hud/characters/<skin>`, `ui/models/characters/<prefix>01` in a rebuilt `menus/characters_heads(_pc).pkgb`; missing = silent | 0x5f4ec0; 0x5e1f06/0x5e1f19 |
| R20 | loading screens `textures/loading/<prefix><01..03>.igb` (optional, silent) | 0x487268 (0x688f7c), 0x487000 |
| R21 | `textureicon` indices must match whatever portrait grid the rebuilt hero-list/team menu uses (XML2 uses 0..40) | 0x44c32a; 0x5b3eb0; 0x5c3cc6 |
| R22 | never emit `loadMapAddTeam` in scripts | 0x4a0bd0 ("resetgame" + unregistered "loadmapaddteam") |
| R23 | XMLB attributes lowercase and sorted; `name` attribute must be present | (established; 1.2 `FUN_005649c0` lookups) |
| R24 | the CStats pool holds 31 objects; 21 resident heroes leave 10 for NPC types per zone (XML2 retail situation) | 0x44c3fb `cmp [ebp+0x9aa0],0x1f`; 0x4496d0 |
| R25 | saves are positional by stats index: freeze herostat order once players have saves | 0x449a60 / 0x44b970 |

## 8. Remaining UNVERIFIED items
1. Exact behaviour when a party-slot name has no stats entry at zone load (fallback CStats of handle 0; crash vs broken
   actor). Avoid by R6 rather than test.
2. Whether the team menu automatically shows `ui/models/characters/9999` for a hero without a head model.
3. Which texture/grid the hero list portraits (`textureicon`) index in x2m_team.igb / the hero-list menu, and the
   sort key of the roster (`FUN_005db320`).
4. Meaning of CStats flag +0x2ae bit 0x40 used by `FUN_005db810` to show a roster entry (set/cleared around
   `FUN_004bbff0`); XML2 heroes evidently have it set.
5. Retail value of `DAT_006f3c2d` (extra default unlocks in resetgame) - from retail behaviour presumably non-zero.
6. Behaviour of `autospend` with a class name absent from autospend.xmlb.
7. Talent `type="scale"` (used by XML2 files, absent from the 3-entry table 0x6d9910).
8. What the wolverine-only branches (vt+0x1f8/vt+0x1f4 (3, ...)) do in gameplay.
9. How `FUN_0044b970` fails on a save whose hero section length differs (no bounds checks seen).
10. Whether `builddefaultteam` / the `[HERO] Name1..4` ini keys are reachable in the port's menu flow.
11. Runtime effect of the 64-entry pending-talent table (`FUN_0043ba60`) beyond "no error": whether pending talents are
    resolved when a matching definition loads later (`FUN_0043bd30` region not fully traced).
12. In-game confirmation that a herostat with fewer than 21 entries boots (code paths are count-driven, never run).

## 9. Decompilation index (research/heroes/)
- decomp_heroes1.c: 0x4a7b10 startFirstMission, 0x46c810 set party slot, 0x469d30/0x469d60, 0x5f3610/0x5f3be0/
  0x5f2e70 (newgame/resetgame), 0x5f3330 builddefaultteam, 0x49f520 unlockCharacter, 0x49f610, 0x4a0d30/0x4a0bd0/
  0x4a3a00/0x4a8e70/0x4a6d80 script handlers, 0x5f4770 loadmap, registry slot functions 0x4498d0..0x44b860, 0x4b7f30,
  0x43d0c0 autospend, 0x4b9c40 (attribute parser), 0x4c1320, 0x4c0080 talent registration, 0x4871d0 loading texture,
  0x5b8290 menu, 0x527f20/0x533bc0/0x52d5d0 (power slot users), 0x4d1d80 danger room, 0x4e1080, 0x4c2130, 0x4d0e10,
  0x4d3ea0, 0x4b7e50 save, 0x44b520 ctor, wolverine special cases, 0x4fd8d0/0x4fd860 handler map, 0x528020,
  0x529090, 0x449430, 0x44b970 load, 0x44be40, 0x448dc0, 0x448b10, 0x449f50, 0x44a9f0, 0x448a90, 0x449fe0, 0x44a0a0,
  0x44b320, 0x44b440.
- decomp_heroes2.c: party slot getters/setters (0x46c510, 0x46b010, 0x46c590, 0x46b070, 0x46c620), 0x4698f0,
  0x46a3e0/0x46a420, 0x46a6c0 hero spawn, 0x4bc2c0 unload, registry small slots, 0x4b84b0/0x4b8450 power slots,
  0x4b7ce0 costume unlock, 0x43a520/0x43a550, 0x449b40/0x44b1d0 records, 0x4b7eb0, 0x4b7d10 level-up, 0x4b79b0 XP,
  0x4b87c0, 0x4bb960, 0x43b180, 0x501410, 0x4bde80, 0x4c1dd0, 0x4c0580, 0x48fed0, 0x4bdb30, 0x4b8090 skin string,
  0x4b7fc0/0x4b7f50 costume cycling, 0x4694d0, 0x469130, 0x44bcf0, 0x448ba0 Talent children, 0x4489c0, 0x4495e0,
  0x449dc0, 0x448a40, 0x4c1bf0, 0x43d370/0x43d3e0.
- decomp_heroes3.c: 0x4c0370 talent mgr ctor and pool helpers, 0x4bdc00 id base, 0x5c3ba0/0x5c3b40 playable items,
  0x5b3bb0 character list, 0x4cb2f0, 0x486ec0 loading screen, 0x4bcb00 record copy, 0x44ac50, 0x5db590 roster,
  0x5dc620, 0x5a9840, 0x4c8f50, 0x4a7e30/0x4a1700 hero tokens, 0x5e0950, 0x5efd10, 0x4b82a0 Race, 0x4bbae0, 0x4b7ad0,
  0x4bc8e0, 0x4612e0, 0x4b8850, 0x5e1ec0 roster init, 0x5db810, 0x4bb340, 0x43bb80, 0x4bdc20 talentvalues, 0x5c58b0.
- decomp_heroes4.c: 0x43ba60 pending talents, 0x43ad70/0x43a930/0x43a990 talent heap, 0x486dd0 zone-load party spawn,
  0x562800 xml_talents type, 0x4c0e40 description formatter, 0x4c0da0, 0x4bc990, 0x4be580, 0x4d4e80, 0x4bd810,
  0x4b7b00, 0x4bb3c0, 0x4b8ed0, 0x4c06db, 0x5e2420/0x5e3660 team menu, 0x5f464b confirm, 0x484c87, 0x4d1910.
- decomp_heroes5.c: 0x4bfe60 talent unload, 0x4beaf0, 0x4bf5e0, 0x4bf460, 0x4bf4c0, 0x4bf530, 0x4bf570, 0x4bfde0,
  0x4c06a0, 0x43bb80, 0x487000 loading-screen chooser, 0x4bd550, 0x4ac470 require parser, 0x4b7fc0.
- decomp_heroes6.c: 0x56157a, 0x5f9eb0 (0xa6a800 reader), 0x561850, 0x561f10, 0x4c0d60/0x4c0d80, 0x5b3bb0, 0x5c3c40,
  0x43ac40, 0x43b880.
- decomp_heroes7.c: 0x561510/0x561040/0x5612a0/0x5614a0 package entry handlers (xml_talents basename path).
