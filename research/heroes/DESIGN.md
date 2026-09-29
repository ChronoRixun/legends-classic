# XML1 playable roster on XMen2.exe: design and implementation plan (v1)

Written 2026-09-27 by the design task of workflow `wf_c521e91b-62e`. Inputs, in order of authority:
`research/_summaries/characters.md` (VERIFICATION section), `research/heroes/engine.md` (Topic B, exe contract),
`research/heroes/inventory.md` + `inventory.json` (Topic A, data), `research/heroes/roster.md` (Topic C, campaign
flow), `HANDOFF.md`, `tools/xml1build/SPEC.md`, the pipeline sources under `tools/xml1build/`, and the XML1/XML2
data itself (`xml1_loose/`, `<XML2 folder>`, `build/xml1_tour`). Every XMen2.exe address below was
read this session with `tools/disasm.py` (RVA = VA - 0x400000) or in the Ghidra decompiles under
`research/heroes/decomp_heroes*.c` / `research/characters/ghidra/decomp*.c`; anything not read is marked
**UNVERIFIED** and has a fallback. Nothing outside `research/heroes/` was written.

This document is written for an implementation agent that must not do further research. Section 3 is the
per-hero table, section 4 the exact conversion rules, section 5 the module plan, section 6 the budgets, section 7
the verification plan, section 8 the short list of owner decisions (each with a default so work can start).

---------------------------------------------------------------------------------------------------------------

## 0. Summary of the design

* A new pipeline module `tools/xml1build/heroes.py` runs after `characters` and before `scripts`/`zones`
  (`MODULE_ORDER = characters, heroes, scripts, zones, media`). It replaces XML2's 21 stand-in heroes with a
  **21-entry herostat**: XML2's `default`, the 15 XML1 heroes in XML1 file order, one hidden `Magneto` placeholder
  (a clone of `default`, needed because `startFirstMission` seats the name `magneto` at 0x4a7b41) and 4 hidden
  pad entries `x1pad1..x1pad4` (clones of `default`) that keep the count at XML2's proven 21. Hidden = no `team`
  and no `playable` attribute, exactly like XML2's own `default` entry, which the team menu never lists
  (roster builder 0x5db590 / 0x5db810 require CStats team == 0x1d, decomp_heroes3.c:2205).
* Per hero it writes `Data/talents/<name>.{XMLB,engb}` (the XML1 inline trees in XML2 talent-file form with
  `talentvalues`), a **collapsed powerstyle** (one `powerN` FightMove per power instead of XML1's 11-rung
  inherit/fallback chains, written over the mapped style name `characters.py` already emits), character packages
  for every costume plus `<name>_xml`, and a rebuilt `menus/characters_heads(.PKGB|_pc.PKGB)`.
* It rewrites two `characters.py` outputs: `Data/npcstat` (removes the 6 hero-as-NPC entries and dead talent refs)
  and `Data/shared_talents` (88 -> 47 talents, so shared + the 4 party files stay under the engine's 100
  registered-talent pool: 0x4bdfe4 / 0x4be7e4 / 0x4be044 `cmp ecx,0x64`, drop path 0x4c0080).
* New Game keeps option B (team menu before the first zone, `loadMapChooseTeam`, as today). The proxy patch
  (option C) is offered to Owen as the fidelity upgrade; nothing in v1 depends on it.
* Budgets after conversion (section 6): stats names 228/296; registered talents worst case 76/100 (+8 danger
  room); actor slots max 35/37 per zone with the heaviest 4-hero XML1 party; IGB cache resident 58 -> zone
  budget 142 against the largest zone package 119.

---------------------------------------------------------------------------------------------------------------

## 1. Decisions

| # | decision | rationale |
|---|---|---|
| D1 | **herostat = exactly 21 entries**, in this order (stats index in parentheses; index 0 is unused, 0x44c05a-0x44c06a): (1) `default` [XML2's entry verbatim], (2) Beast, (3) Colossus, (4) Cyclops, (5) Frost, (6) Gambit, (7) Iceman, (8) Jubilee, (9) Magma, (10) Nightcrawler, (11) Phoenix, (12) ProfXAstral, (13) Psylocke, (14) Rogue, (15) Storm, (16) Wolverine [XML1 `herostat.eng` order], (17) `Magneto` placeholder, (18..21) `x1pad1..x1pad4`. Build option `--hero-roster 21|17|21xml2` (default 21; `17` drops the pads; `21xml2` replaces the pads by XML2's Deadpool, Ironman, Professorx, Sunfire for an A/B). | 21 is the only count XML2 ever exercised (0x44bb13 `cmp esi,0x15` maps 21 ordinals; records for index < 22 at 0x449b40; roster list `cmp ebx,0x15` at 0x5db5fd). Fewer is memory-safe by analysis (engine.md 1.5) but untested (engine.md UNVERIFIED #12) - the `17` option is the test, not the default. XML1 file order keeps the per-hero talent-id bases and save layout stable (saves are positional, R25). |
| D2 | **Hidden placeholder `Magneto` = clone of `default`** (`skin="0002"`, `characteranims="00_testguy"`, `charactername="Defaultman"`, `autospend="support_heavy"`, `<Race Mutant/>`, `<talent level="1" name="fightstyle_hero"/>`, no `team`, no `playable`, no powerstyle, no talent file) with packages `magneto_0002.PKGB`/`_nc` (2 entries: actorskin 0002, actoranimdb 00_testguy). Same shape for `x1pad1..4`. | `startFirstMission` (0x4a7b10) stores the *name* `magneto` in party slot 0 (push 0x682504 at 0x4a7b41/0x4a7b50 -> game vt+0xf0 = 0x46c810, no validation) before `menus/new_game.py` runs; `resetgame` (0x5f2e70) unlocks it by name; `builddefaultteam` (0x5f3330) defaults to it. A name absent from the stats table reaches the fallback CStats of handle 0 at zone load (0x486dd0 -> 0x46a6c0 -> 0x4498d0/0x448c60; behaviour UNVERIFIED, assumed crash). The New Game hook uses `loadMapChooseTeam`, which rewrites all four slots on confirm (0x5f464b), but the `--start-zone`/`--tour` hooks use `loadMapKeepTeam` and DO spawn slot 0. A `default`-shaped entry is XML2's own proven form of a herostat entry that spawns (actors/0002 + 00_testguy exist in the base install) yet never appears in the team menu (no team). It never pollutes the roster and costs one CStats slot at boot, as in retail. |
| D3 | **XML2 heroes kept: none** (only `default`). All 10 same-name XML2 heroes (Colossus, Cyclops, Gambit, Iceman, Nightcrawler, Phoenix, Rogue, Storm, Wolverine, default) are replaced; the 11 XML2-only heroes are dropped. | A stats name registers once (herostat first, 0x44bab4 before 0x44bac7; second registration ignored at LAB_0044c3c9) and `data/talents/<name>` is keyed by the stats name (0x4c05f0, "data/talents/%s.xmlb" 0x68ea28), so XML1 and XML2 versions of one name cannot coexist. XML2-only heroes would be unlocked by `resetgame` (magneto, bishop, juggernaut always; 11 more if byte [0x6f3c2d] == 0) and appear in the XML1 campaign's team menus. |
| D4 | **Name clashes with npcstat**: heroes.py removes from `Data/npcstat.{XMLB,engb}` every entry whose lowercase name is in the new herostat (today: Beast, Frost, Jubilee, Magma, ProfXAstral, Psylocke - the `heroes_as_npc` of `characters.planned_stats`), and updates `ctx.shared['stats']`/`['stats_names']`. `ProfXGladiator`, `ProfX`, `ProfXComa`, the `<Hero>NoAnims` doubles and the Danger-Room villains stay npcstat. | 0x44c3c9: an npcstat duplicate of a loaded hero is dead data; `characters._check_caps` and validate V5 treat a name in both files as an error. |
| D5 | **Skin numbering**: unchanged from the pipeline: XML1 `CCVV` -> `CCVV+14000` (`common.map_skin`, prefixes 140..239 <= 255 per 0x4b9dbc-0x4b9de3), costume variants stay 2-digit, anim DBs through `common.map_animdb`, HUD/UI heads through `map_ui_path`. Every hero actor/HUD/UI/loading file is already written by `characters.emit_namespace`. | characters.md CONFIRMED items; `x1_namespace_map.json` check_errors = []. |
| D6 | **Costume slots**: XML1 `skin_60s/70s/future/weaponx/civilian` copied (table 0x6d8aa0 indices 3,4,6,5,8); Magma's `skin_magmacivilian="03"` -> `skin_civilian="03"` (slot 8 is free for Magma). Costumes start locked (XML2 unlocks slot 1 `astonishing` for everyone at 0x685538; XML1 heroes have no slot-1 variant so nothing is offered) and become selectable through `unlockCharacter("", "<costume>")` in the flashback begin bodies (roster.md T9 step 3, v2). | 0x4b9e8d/0x488400: unknown suffixes are dropped silently; the civilian actor 1803 -> 15803 exists (inventory 5.1). |
| D7 | **Talent id ranges**: shared `data/shared_talents` ids 0..98 (0x4c05d0 pushes 0x63); per-hero file ids `(statsIdx+1)*100 .. +99` (0x4bdc00): default 200 (no file), Beast 300, Colossus 400, Cyclops 500, Frost 600, Gambit 700, Iceman 800, Jubilee 900, Magma 1000, Nightcrawler 1100, Phoenix 1200, ProfXAstral 1300, Psylocke 1400, Rogue 1500, Storm 1600, Wolverine 1700, Magneto 1800, pads 1900..2200 (no files). Per file <= 8 talents (cap 100). | engine.md 4.3; ids are derived by the exe from the herostat position, nothing to write. |
| D8 | **Registered-talent pool**: shared_talents is pruned to the 47 names in section 4.7 (rule-based: fightstyle flags, style `<require>` targets, XML1 hero plain refs, engine special names 0x4be130, XML2 real definitions still referenced). The 26 empty `*_special`-style NPC definitions and their `<talent>` children in XML1 NPC entries are dropped. `toughness`, `mutantmastery`, `acrobatics` get real definitions from `xml1_loose/data/shared_talents.eng`. Hero-only passives (`accuracy`, `pointblank`, `grappling`, `healing_factor`, `knockback`) move into the per-hero files under hero-prefixed names (`x1_<hero>_<name>`) so two party members never register the same name. | 100 simultaneously registered talents (0x4bdfe4/0x4be7e4/0x4be044 `cmp ecx,0x64`; 0x4c0080 drops silently when any pool == 100, decomp_heroes1.c:2428). Today's 88 shared leave 12 for the party. Unknown `<Talent>` names on a stats entry are queued in a 64-entry pending table (FUN_0043ba60, decomp_heroes4.c: `DAT_00712968 != 0x40`), not errors, and an empty definition has no effect either, so dropping both the definition and the reference is behaviour-neutral. Registration of an already-registered name (0x4c00f6 -> 0x4c0228) is UNVERIFIED, hence the per-hero prefixes. |
| D9 | **Powers**: each XML1 power chain collapses to ONE FightMove named `power1`/`power2`/`power3`/`power9` (XML1 power index 0/1/2/3), gated by `<require cat="skill" item="<talent>" level="1"/>`, with per-rank numbers moved into `<talentvalues>` referenced as `%x1_<hero>_<talent>_<field>`. herostat gets `power1="power1" power2="power2" power3="power3" power4="power9"`. Non-power moves are kept. Value codes are resolved to XML1's numbers at build time. | The engine addresses powers by FightMove name (herostat power1..4 -> CStats+0xc4.. via 0x4b7f30 at 0x4ba0c7/0x4ba0f3/0x4ba11f; UI code hardcodes `power8/power2/power1/power9` at 0x533bee); talent `power=` is a 0x14-char FightMove name (0x4be1f0); `fallback` is not an exe string; XML2 retail styles carry zero value codes and 34 codes differ between the games (characters.md VERIFICATION). |
| D10 | **Collapsed styles overwrite the mapped style names** `characters.py` already writes (`x1_ps_beast`, `x1_ps_colossus`, `x1_ps_cyclops`, `x1_ps_frost`, `x1_ps_gambit`, `x1_ps_iceman`, `x1_ps_nightcrawler`, `x1_ps_phoenix`, `x1_ps_rogue`, `x1_ps_storm`, `x1_ps_wolverine`, `ps_jubilee`, `ps_magma`, `ps_profxastral`, `ps_psylocke`), `replace=True`. | No XML1 npcstat entry uses a hero powerstyle (checked: 0 references; dopples use `ps_<hero>_dopple`), the 6 hero-as-NPC users leave npcstat, and `Packages/generated/powerstyles/<mapped>.PKGB` written by characters stays valid. |
| D11 | **New Game = option B** (unchanged hook: begin_alison body ending in `loadMapChooseTeam("nyc/alison/nyc1_1_1")`). Option C (xml2-fix proxy patch of 8 + 17 pointers, roster.md 3) is an owner decision (section 8) and changes only `scripts.py`'s hook when accepted. The T7 `join_hero` fix (roster.md 5) ships with this milestone because the first mission's Cyclops join is broken today. | XML2 retail `new_game_hard.py` proves the menu-before-first-zone path; the menu confirm rewrites all 4 slots (0x5f464b) so the hardcoded names never spawn in New Game. |
| D12 | **ProfXAstral** gets a full herostat entry with `playable="true"` (XML1: false), `level="40"`, `xpexempt="true"`, `scriptlevel="3"`; `ProfXGladiator` stays npcstat (astral_sk side mission deferred). | The roster builder does not read the playable bit (0x5db590 checks loaded/team/name length; 0x5db810 checks team and CStats+0x2ae bit 0x40) but two other menu lists do (0x5b3bb0 vt+0x80, 0x5c3ba0); since XML2 has no forced seating, he must be pickable in the astral1 team menu. `true` is the only value XML2 ever shipped. |
| D13 | **autospend classes** (XML2 `data/autospend.xmlb` has exactly bruiser, bruiser_light, support, support_heavy; unknown class UNVERIFIED): Wolverine, Rogue, Colossus = `bruiser`; Beast, Nightcrawler, Psylocke = `bruiser_light`; Frost, Phoenix, Storm, ProfXAstral = `support`; Cyclops, Gambit, Iceman, Jubilee, Magma, placeholders = `support_heavy`. | Rule from XML1's RatingMelee/Ranged/Support/Durability (ignored by XMen2.exe, decomp3.c:911): Melee >= 0.6 -> bruiser (bruiser_light when speed >= 5 and Durability <= 0.7); Support >= 0.4 -> support; else support_heavy. Matches XML2's own choice for all 9 shared heroes. |
| D14 | **textureicon**: Cyclops 0, Phoenix 1, Wolverine 2, Storm 3, Nightcrawler 4, Rogue 5, Iceman 6, Colossus 7, ProfXAstral 9, Gambit 11 (XML2's portrait cells for the same characters); Beast, Frost, Jubilee, Magma, Psylocke, placeholders = 63. | The index is read at 0x44c329-0x44c347 into entry+0x16 and consumed by two menu list routines (0x5b3eb0, 0x5c3cc6); 0x5b3bb0 uses icon 0x3f = 63 for locked entries, so 63 is the engine's own "no portrait" cell. The atlas itself is UNVERIFIED (engine.md #3). |
| D15 | **Out of scope for v1** (deferred, with reasons): Gambit/Jubilee `charged_throw` and Rogue's decide step (`ch_throw`, `ch_roguedecide` are not registered, 0x4fd975-0x4fe88a; the moves fall back to `%default%` at 0x4fd860) - Rogue's power2 binds the drain move directly (4.5); flashback party save/restore T9 and the astral solo-mode T10 (roster.md) - both are script work independent of the roster; Colossus/Psylocke/Jubilee unlock points (owner decision, section 8); XML1 Danger Room courses; XML1 team bonuses (XML2's `team_bonus` stays and fires for matching names such as storm+phoenix+rogue); talent icon re-atlassing (UNVERIFIED grid, section 7 A/B); the 2 talent-gated Psylocke blades (BoltOn `<require>` UNVERIFIED -> first blade only, as today); balance of NPC damage vs XML1 hero stats. | Each item is either UNVERIFIED engine behaviour that needs an in-game answer first, or a script/fidelity feature that does not block playing with the XML1 roster. |

---------------------------------------------------------------------------------------------------------------

## 2. Engine contract the implementation must satisfy (addresses read this session)

| # | fact | address |
|---|---|---|
| E1 | herostat loaded before npcstat; heroes get stats indices 1..N | 0x44bab4 / 0x44bac7 (FUN_0044bab0) |
| E2 | 296 usable stats names; extra names silently skipped | 0x44c1a6 `cmp eax,0x129` / `je 0x44c481` |
| E3 | 21 hero ordinals mapped; roster screen lists <= 21; persistence records for index < 22 | 0x44bb13 `cmp esi,0x15`; 0x5db5fd `cmp ebx,0x15`; 0x449b40 (loop `< 0x16`) |
| E4 | roster shows an entry only if loaded, CStats team == 0x1d (+0x2a0) and CStats+0x2ae bit 0x40; name < 19 chars | 0x5db5e9 (vt+0x78 loaded), decomp_heroes3.c:2205; 0x5db590 `< 0x13` |
| E5 | `textureicon` atoi -> word entry+0x16; `playable` first char t/T -> flag bit 2 | 0x44c329-0x44c347; 0x44c30c |
| E6 | `power1..power4` -> four 0x15-byte FightMove-name slots at CStats+0xc4/+0xd9/+0xee/+0x103 | 0x4ba0c7 `lea ecx,[ebp+0xc4]; call 0x4b7f30`, 0x4ba0f3, 0x4ba11f |
| E7 | startFirstMission seats magneto/cyclops/wolverine/storm by name, then runs menus/new_game(_hard) | 0x4a7b41 `push 0x682504` ... 0x4a7bfe; 0x4a7c42 / 0x4a7c57 |
| E8 | shared talents ids 0..98 | 0x4c05d0 `push 0x63; call 0x4c0460` |
| E9 | 100-entry talent pools; overflow silently dropped | 0x4bdfe4 `cmp ecx,0x64` (name nodes), 0x4be7e4, 0x4be044; 0x4c0080 (decomp_heroes1.c:2428) |
| E10 | per-hero file `data/talents/%s.xmlb`, ids (idx+1)*100.., pulled by package entry `xml_talents`, basename == stats name | 0x4c05f0 (0x68ea28); 0x561510 -> 0x560550 (decomp_heroes7.c) |
| E11 | a stats entry holds <= 19 `<Talent>` children | decomp_heroes3.c:2320 `*(param_1+0xb8) == 0x13` (FUN_0043bb80) |
| E12 | unknown `<Talent>` name -> 64-entry pending table, no error | FUN_0043ba60 `DAT_00712968 != 0x40` (decomp_heroes4.c) |
| E13 | special talent names cached by name: `flight`, `ice_skating`, `night_faith` | 0x4be130 (FUN_004be130, engine.md 4.4) |
| E14 | unknown `ch_*` handler -> `%default%` handler | 0x4fd860 (decomp_npcai2.c:244), registration table 0x4fd975-0x4fe88a |
| E15 | `extractionPointLite` hint gate on game flag `danv` bit 1 | 0x4a6e3e `push 0x68d540` ... 0x4a6e5e / 0x4a6e63 |
| E16 | skin prefix byte <= 255, 2-digit variant; `skin_<costume>` only for table 0x6d8aa0 | 0x4b9dbc-0x4b9de3; 0x4b9e8d |
| E17 | 40 actor slots (skins + anim DBs) per zone, silent NULL on overflow | 0x56b2c3 (actor_budget.py docstring, SPEC 14) |
| E18 | 200 IGB-cache records, zone refused silently on overflow | 0x56ede5 (igb_budget.py docstring, SPEC 13) |
| E19 | talent description formatter handles `%name` tokens only (no `^` handling seen) | FUN_004c0e40 (decomp_heroes4.c:263, `*param_2 == 0x25`) |
| E20 | XMLB attribute names must be lowercase and sorted | HANDOFF (in-game); `common.encode_xmlb` does it |

---------------------------------------------------------------------------------------------------------------

## 3. Per-hero conversion table

Columns: XML1 sources -> outputs (all under `<out>`), transformations beyond the common rules of section 4,
known losses, risks. Common to every hero: herostat entry (4.1), `Data/talents/<name>.{XMLB,engb}` (4.2),
collapsed powerstyle over the mapped name (4.3-4.5), packages for every costume + `<name>_xml` (4.8),
head in `characters_heads` (4.9). Skins: XML1 -> +14000. "file talents" = number of `<talent>` elements in the
per-hero file (inline XML1 talents + hero-prefixed passives).

| hero (idx, ids) | XML1 sources | outputs | hero-specific transformations | known losses | risks |
|---|---|---|---|---|---|
| **default** (1, 200) | XML2 `Data/herostat` entry | herostat entry verbatim (skin 0002, 00_testguy, autospend support_heavy, Race Mutant+XMen, fightstyle_hero) | none | - | none (retail) |
| **Beast** (2, 300) | herostat `Beast`; `ps_beast.eng`; bundles beast_0501/0502/0503 (+_nc); `beast_all.igb`; sounddir beast_m (merged bank) | entry skin 14501, skin_60s 02, skin_future 03, `moveset1="moveset_acrobat"`, autospend bruiser_light, textureicon 63; talents file 5 (beast_pinball->power1, beast_propeller->power2, beast_boost->power3 type=boost, beast_xtreme->power9 type=xtreme, x1_beast_grappling); style `x1_ps_beast` (41 moves -> 4 collapsed + ~14 kept: bowl/prop/boost/xtreme chains); packages beast_14501/14502/14503 (+_nc), beast_xml; head 14501 | grappling -> per-hero (strength add + reflect_damage punch/kick, 4.6); `acrobatics` stays shared with a real definition; talent `might level=1` | A-codes (A1-A6) resolved to XML1 numbers | `ch_fastball`/`ch_bounce_move` registered; moveset_acrobat is XML2's file (XML1 ch_clingwall* lost, already the case) |
| **Colossus** (3, 400) | herostat `Colossus` (heaviness); `ps_colossus.eng`; bundles 0901/0902/0903/0906; `colossus_all.igb`; coloss_m (merged) | entry skin 14901, skin_70s 03, skin_civilian 02, skin_future 06, `heaviness` kept (parsed, decomp3.c), autospend bruiser, textureicon 7; talents 6 (colossus_titanicsmash p1, colossus_concslam p2, colossus_steelskin p3 boost, colossus_xtreme p9, colossus_charge passive, x1_colossus_knockback); style `x1_ps_colossus` (45 -> ~18); packages x4 (+_nc), colossus_xml; head 14901 | knockback passive -> `<affecter attribute="atk_knockback" level="<K number>" scope_damage="dmg_physical"/>` (string exists; affecter use UNVERIFIED) | `deflect_damage`/`def_knockback` triggers with life 0.01 kept as XML2 affecters | `ch_charge_move` registered; XML2 Colossus talents file (13) and `col_smash` disappear with the entry |
| **Cyclops** (4, 500) | herostat `Cyclops`; `ps_cyclops.eng`; bundles 0101/0102/0103/0105; `cyclops_all.igb`; cyclop_m (merged) | entry skin 14101, skin_60s 02, skin_70s 03, skin_future 05, autospend support_heavy, textureicon 0; talents 6 (cyclops_beam p1, cyclops_sweep p2, cyclops_tactics p3 boost, cyclops_xtreme p9, x1_cyclops_accuracy, x1_cyclops_pointblank); style `x1_ps_cyclops` (37 -> 5: power1 [optic_beam1..10+power_attack], power2 [optic_sweep1..10+power_smash], power3 [cyc_tactics1..8+power_boost], power9 [cyc_xtreme1..5+power_xtreme] + no other moves); packages x4 (+_nc), cyclops_xml; head 14101 | `optic_beam6` adds `pierce="true"` at rank 6 -> `piercechance="%x1_cyclops_cyclops_beam_pierce"` (0 below rank 6, 1 from rank 6; UNVERIFIED on beams, fallback literal `pierce="true"`); cyc_tactics `apply_ally` near (rank 4) / all (rank 7) is an enum -> top rung `all` kept from rank 1 (loss) | accuracy/pointblank are display-only in XML1 too (no activepowerup) | XML2 cyclops talent names `cyclops_beam/tactics/xtreme` clash only with the replaced XML2 file (harmless, D3) |
| **Frost** (5, 600) | herostat `Frost` (charactername Emma Frost); `ps_frost.eng`; bundles 1501/1502; `frost_all.igb`; emmaf_m | entry skin 15501, skin_future 02, `moveset1` none, `fightstyle_finesse1` + `fightstyle_psionic`, autospend support, textureicon 63; talents 7 (frost_confuse p1, frost_fear p2, frost_shield p3 boost, frost_xtreme p9, frost_hardness, frost_might, psi_fight_frost); style `x1_ps_frost` (37 -> ~6); packages x2 (+_nc), frost_xml; head 15501 | 14 activepowerups: `reflect_damage` x5 with user1 chance -> `<powerup life="-1" chance="0.NN"><affecter attribute="reflect_damage" .../>`; `might_mode_mod` x3 -> might_heaviness/might_structure affecters; elemental melee x6 -> class add_attack (4.6) | confused/fear triggers use `life_max`/`apply_enemy` (XML1-only attrs, kept, ignored) | removed from npcstat (hero-as-NPC today); `%FROST%` speaker token resolves via herostat |
| **Gambit** (6, 700) | herostat `Gambit`; `ps_gambit.eng`; bundles 1301/1302; `gambit_all.igb`; gambit_m; `data/entities/card_ents` (bundle xml) | entry skin 15301, skin_future 02, autospend support_heavy, textureicon 11; talents 7 (charged_card p1, staff_slam p2, kinetic_boost p3 boost, gambit_xtreme p9, overload, kinetic_strike, staff_master); style `x1_ps_gambit` (51 -> ~14: power1 [card_throw1..11+power_attack], power2 [StaffSlam1..10+power_smash], power3 [kinetic_boost1..8+power_boost], power9 [pick_up_1..5+power_xtreme], `time_bomb` [time_bomb1..4 collapsed, gated on `overload`], kept: charged_throw, pickupobjectidle/walk, attack*); packages x2 (+_nc), gambit_xml; head 15301 | `staff_master` atk_damage with `<scope scope_node="gambit_staff"/>` -> `<affecter attribute="atk_damage" level=.. scope_node="gambit_staff"/>` (scope name survives only if the collapsed moves keep their `node` tags - UNVERIFIED); `kinetic_strike` elemental melee -> add_attack | **`charged_throw` (ch_throw) runs without handler logic** (kept, `icon` removed); the charged-object `powerup="special"` trigger keeps its attrs minus func_* | 6x `ch_gambitboltons` registered; `ch_gambitdecide` registered |
| **Iceman** (7, 800) | herostat `Iceman`; `ps_iceman.eng`; bundles 0801/0802/0803 (0801 lists actors 0001, 0805 too); `iceman_all.igb`; iceman_m (merged) | entry skin 14801, skin_60s 03, skin_civilian 02, autospend support_heavy, textureicon 6; talents 8 (iceman_freeze p1, iceman_spikes p2, iceman_armor p3 boost, iceman_xtreme p9, iceman_elemental, `ice_skating` [name kept, E13], ice_special hidden, x1_iceman_pointblank); style `x1_ps_iceman` (45 -> ~12: 4 collapsed + jumps/skating/pickups kept); packages x3 (+_nc), iceman_xml; head 14801 | `ice_special`: `<affecter affect_type="scale" attribute="no_iceshell" level="0"/>` + `hidden="true"` (retail sentinel_special form); the ice-blade bolton trigger (`bolton=`, `fx_bolt=`) kept verbatim | 18 XML1-only trigger attrs (mostly func_*) ignored | **heaviest party member: 4 actor slots** (14801, x1_08_iceman, 14001, 14805) - counted in section 6 |
| **Jubilee** (8, 900) | herostat `Jubilee`; `ps_jubilee.eng`; bundle 1601; `jubilee_all.igb`; jubile_m | entry skin 15601 (no costumes), autospend support_heavy, textureicon 63; talents 7 (energy_burst p1, photo_flash p2, taunt p3 boost, jubilee_xtreme p9, detonate, x1_jubilee_accuracy, x1_jubilee_pointblank); style `ps_jubilee` (46 -> ~10: power1 [firework_throw1..+power_attack], flash, taunt, independence + kept charged_throw/pickups/attacks); packages x1 (+_nc), jubilee_xml; head 15601 | `atk_damage_scale` boost affecter emitted verbatim (UNVERIFIED name) | `charged_throw` (ch_throw) without handler; trigger `bait` unknown to the exe (1 use, kept, expected no-op) | removed from npcstat; never unlocked by any XML1 script (section 8 Q2) |
| **Magma** (9, 1000) | herostat `Magma`; `ps_magma.eng`; bundles 1801/1803/1804 (1802 unused: no costume slot); `magma_all.igb`; magma_m; `data/entities/magma_ents` | entry skin 15801, skin_future 04, **skin_civilian 03** (from skin_magmacivilian), autospend support_heavy, textureicon 63; talents 7 (magma_blast p1, lava_fissure p2, magma_form p3 boost, magma_xtreme p9, magma_elemental, magma_skating, magma_might); style `ps_magma` (44 -> ~11: 4 collapsed + jump/jumploop/skate1-4/skating kept); packages magma_15801/15803/15804 (+_nc), magma_xml; head 15801 | fire_armor powerup trigger carries `skin="1805" skin_swap="true"` -> `skin="15805"` (map_skin) + `skin_swap` kept (exe string exists; semantics UNVERIFIED); `might_mode` -> might_heaviness/might_structure | `motor/timebased/vibrate` trigger attrs ignored | required by mansion hubs (25 Magma-solo missions) and nyc1_1_3; removed from npcstat; the extra actor 15805 makes Magma a 3-slot party member |
| **Nightcrawler** (10, 1100) | herostat `Nightcrawler` (BoltOn tail 9801/98_tail); `ps_nightcrawler.eng`; bundles 0601/0602/0603; `nightcrawler_all.igb`; night_m (merged) | entry skin 14601, skin_70s 02, skin_future 03, `moveset1="moveset_acrobat"`, BoltOn `slot=ebolton_tail bolt="Bip01 Pelvis" model=23801 anim=<map_animdb(98_tail)>`, autospend bruiser_light, textureicon 4; talents 6 (night_strike p1, night_frenzy p2, night_shadow p3 boost, night_xtreme p9, `night_faith` [name kept, E13], sucker_punch); style `x1_ps_nightcrawler` (51 -> ~20: the tele/decide moves kept); packages x3 (+_nc), nightcrawler_xml; head 14601 | `invisible` boost with `func_think/func_deactivate` -> `<affecter attribute="invisible" level="1"/>` (func_* dropped) | A1-A9 codes resolved | 4 actor slots (tail bolt-on model + anim); all handlers registered |
| **Phoenix** (11, 1200) | herostat `Phoenix` (charactername Jean Grey, 3 FlyEffect); `ps_phoenix.eng`; bundles 0201/0202/0203; `phoenix_all.igb`; phoen_m | entry skin 14201, skin_60s 02, skin_70s 03, `moveset1="moveset_flying"`, FlyEffects copied, autospend support, textureicon 1; talents 6 (phoenix_telekinesis p1, phoenix_shout p2, phoenix_shield p3 boost, phoenix_xtreme p9, phoenix_combat, psi_fight_phoenix); style `x1_ps_phoenix` (39 -> ~6); packages x3 (+_nc), phoenix_xml; head 14201 | `phoenix_combat` damage scope_damage=dmg_mental -> `<affecter attribute="damage" level=.. scope_damage="dmg_mental"/>`; `flight` shared (E13) | - | `ch_telekinesis` registered; XML2 bank phoenx_m untouched (no collision) |
| **ProfXAstral** (12, 1300) | herostat `ProfXAstral` (level 40, xpexempt, playable false); `ps_profxastral.eng` (15 moves, own basic attacks); bundle 1104; `profxastral_all.igb`; profxa_m | entry skin 15104, **playable="true"** (D12), `scriptlevel="3"` added, `xpexempt` kept, level 40 / 35 40 40 80, autospend support, textureicon 9; talents 6 (profx_psychicsmash p1, profx_psychicburst p2, profx_psychicdefense p3 boost, profx_xtreme p9, profx_fighting, astralknockback) - all single-level, so no talentvalues except req; style `ps_profxastral` (15 -> 15: power_attack/power_smash/power_boost/power_xtreme renamed power1/2/3/9, attacks kept with their icons removed); packages x1 (+_nc), profxastral_xml; head: none on disc (ui/models 1101 is ProfX) -> characters_heads lists nothing for him (engine fallback 9999 UNVERIFIED, silent) | `astralknockback` -> atk_knockback affecter (UNVERIFIED) | - | removed from npcstat; the 5 profx_* talents leave shared_talents (they were empties added for the hero-as-NPC entry) |
| **Psylocke** (13, 1400) | herostat `Psylocke` (3 BoltOn blades, 2 talent-gated); `ps_psylocke.eng`; bundles 1201/1202; `psylocke_all.igb`; psyloc_m | entry skin 15201, skin_future 02, `moveset1="moveset_acrobat"`, BoltOn blade_01 only, autospend bruiser_light, textureicon 63; talents 6 (psylocke_slash p1, psylocke_bolts p2, psylocke_armor p3 boost, psylocke_xtreme p9, blademaster, psi_fight_psylocke); style `ps_psylocke` (37 -> ~6); packages x2 (+_nc) (blade_02/03 models stay precached from the bundle), psylocke_xml; head 15201 | `blademaster` damage `scope_node="psylocke_power"` -> affecter with scope_node (node tags on the collapsed moves must survive - the collapse keeps the root move's `powerup_tag`/node attributes) | blades 2/3 never appear (BoltOn `<require>` UNVERIFIED) | removed from npcstat |
| **Rogue** (14, 1500) | herostat `Rogue` (2 FlyEffect, canthrowally); `ps_rogue.eng`; bundle 0701; `rogue_all.igb`; rogue_m | entry skin 14701 (no costumes), `moveset1="moveset_flying"`, autospend bruiser, textureicon 5; talents 5 (rogue_strike p1, rogue_ability p2, rogue_shield p3 boost, rogue_xtreme p9, x1_rogue_grappling); style `x1_ps_rogue` (52 -> ~10: power1 [sstrike1..10+power_attack], **power2 = ability_drain1..10+ability_drain collapsed** (the decide chain ability_drain_decide1..10+power_smash is dropped), power3 [rogue_shield1..8+power_boost], power9 [power_xtreme], kept: drain_notarget, xtreme_relocate/contact1..5/contact/return); packages x1 (+_nc), rogue_xml; head 14701 | drain powerups `drain_victim`, `stun_lock`, `nullify` emitted as affecters (strings exist; effects UNVERIFIED), func_activate/deactivate dropped | **`ch_roguedecide` unregistered -> the per-victim variant decision is gone; power2 always plays the drain move** | signature power fidelity; in-game check 7.2 #9 |
| **Storm** (15, 1600) | herostat `Storm` (canfly, 3 FlyEffect); `ps_storm.eng`; bundles 0401/0402; `storm_all.igb`; storm_m (merged) | entry skin 14401, skin_future 02, `canfly="true"` kept, `moveset1="moveset_flying"`, autospend support, textureicon 3; talents 5 (storm_lnstrike p1, storm_whirlwind p2, storm_shield p3 boost, storm_xtreme p9, storm_elemental); style `x1_ps_storm` (37 -> ~6); packages x2 (+_nc), storm_xml; head 14401 | elemental melee x6 -> add_attack | - | XML2 storm talent names clash only with the replaced file |
| **Wolverine** (16, 1700) | herostat `Wolverine` (2 claw BoltOns, canbeallythrown, canSeeStealthed); `ps_wolverine.eng`; bundles 0301/0302/0303/0305; `wolverine_all.igb`; wolver_m | entry skin 14301, skin_60s 03, skin_70s 03, skin_future 05, skin_weaponx 02, BoltOns claw_left/claw_right (XML2 models, `_model_ok`), autospend bruiser, textureicon 2; talents 7 (wolv_slash p1, wolv_frenzy p2, wolv_berserk p3 boost, wolv_xtreme p9, wolv_sharpness, expertise, x1_wolverine_healing_factor); style `x1_ps_wolverine` (43 -> ~10); packages x4 (+_nc), wolverine_xml; head 14301 | 23 activepowerups: `damageLevel` (5) -> affecter `damagelevel` scope_attack punch (UNVERIFIED), `damage` (5) -> affecter damage scope_attack punch, bleed (3, func_damage=damageaddbleed) -> `<powerup class="add_harming" damagepercent="0.2" damagetype="dmg_physical" life="<user1>">` (UNVERIFIED; fallback drop), speed/strength (10) -> additive affecters; healing_factor -> `health_regen` + `def_pain affect_type=scale` affecters | - | name must stay `Wolverine` (six exe special cases on "wolverine", 0x41c7ea etc.) |
| **Magneto placeholder** (17, 1800) | XML2 `default` entry | `<stats autospend="support_heavy" body="1" characteranims="00_testguy" charactername="Defaultman" level="1" mind="1" name="Magneto" skin="0002" speed="1" strength="1"><Race name="Mutant"/><talent level="1" name="fightstyle_hero"/></stats>`; packages magneto_0002.PKGB/_nc = `[actorskin 0002, actoranimdb 00_testguy]` | none | hidden (no team) | see D2; in-game check 7.2 #2 confirms it is not listed |
| **x1pad1..x1pad4** (18-21, 1900-2200) | XML2 `default` entry | same as the placeholder with names x1pad1..4 and packages x1padN_0002(_nc) | none | hidden | `--hero-roster 17` removes them |

Costume packages total: 38 costumes x 2 + 15 `_xml` + 5 placeholders x 2 = 101 PKGB files.

---------------------------------------------------------------------------------------------------------------

## 4. Conversion rules

### 4.1 herostat entry (per XML1 hero)

Read the XML1 `<stats>` with `ctx.read_x1_xml('data/herostat.eng')` (attributes come back lowercase). Emit, in
this order of operations:

1. Copy every attribute except `ratingmelee/ratingranged/ratingsupport/ratingdurability` (ignored by the exe,
   decomp3.c:911) and `skin_magmacivilian` (-> `skin_civilian`). `skin` -> `C.map_skin`, `characteranims` ->
   `C.map_animdb`, `powerstyle` -> `C.map_powerstyle` (must equal the mapped name characters wrote),
   `moveset1` -> `C.map_fightstyle` (XML2's `moveset_flying`/`moveset_acrobat` are shared by name).
2. Add: `autospend` (D13), `power1="power1" power2="power2" power3="power3" power4="power9"`, `textureicon`
   (D14), `playable="true"` (all 15), `scriptlevel="3"` where missing (ProfXAstral), `team="hero"` (all 15).
3. Children: `<Race name="Mutant"/>` + `<Race name="XMen"/>` (XML2 form; race table 0x6d9710); `FlyEffect`
   copied; `BoltOn` copied with `model` 4-digit -> `map_skin`, `anim` -> `map_animdb`, XML2 slot names checked
   against `characters.BOLTON_SLOTS`, BoltOns with `<require>` children dropped (Psylocke blades 2/3, reported).
4. `<talent>` children (lowercase tag as XML2): (a) inline power/passive talents of the hero whose XML1 `level`
   >= 1 (the starting power, e.g. `cyclops_beam level=1`; ProfXAstral's six) as `<talent level="N" name=.../>`
   - the other inline talents are NOT listed (XML2 lists 1 of 13 for Cyclops; the file defines the rest);
   (b) every XML1 plain reference as-is (`critical level=0`, `might level=1`, `fightstyle_* level=1`,
   `flight level=0`, ...), renaming the 5 hero-only passives to their `x1_<hero>_<name>` file names. Count must
   stay <= 19 (E11; max is 12).
5. `C.normalize_attrs(entry)`; XMLB and engb get the same tree (`charactername` in English in both, as
   characters.py does for new NPC entries).

`default` is copied from XML2's `Data/herostat.XMLB` / `.engb` (each from its own file). Placeholders per D2.

### 4.2 `Data/talents/<name>.XMLB` + `.engb`

Both files identical (XML2's XMLB uses `@HERO_CYC@...` string keys, engb English; English text in both is the
safe choice, exactly like the pipeline's npcstat entries). Root `<talents>`. One `<talent>` per XML1 inline
`<Talent>` of the hero (those with children, `power=`, or `descname=`) plus the hero-prefixed passives:

```
<talent descname="<power name>" description="<text>" icon="0"
        icon_texture="textures/ui/cyclops_all.png" name="cyclops_beam" power="power1" [type="boost"|"xtreme"]>
  <talentvalues>
    <talentvalue level="1"  name="x1_cyclops_cyclops_beam_req" value="1"/>   ... one per rank 1..N
    <talentvalue level="1"  name="x1_cyclops_cyclops_beam_dmg" value="9 11"/>
    <talentvalue level="1"  name="x1_cyclops_cyclops_beam_pwr" value="10"/>
    <talentvalue level="1"  name="x1_cyclops_cyclops_beam_dlv" value="2"/>
    ...
  </talentvalues>
  <level description="<level text>"><require cat="level" level="1"/></level>
  <level description="<level text>"><require cat="level" level="3"/></level>
  ...
  <level cost="2" descname="<power name>" description="...">
    <require cat="level" degree="see" level="25"/><require cat="level" level="30"/>
  </level>
</talent>
```

Rules:
* `power`: XML1 `power="0|1|2|3"` -> `power1|power2|power3|power9`; index 4/5 or absent -> no `power` attribute
  (passive). `type="boost"` for index 2, `type="xtreme"` for index 3 (table 0x6d9910).
* `icon`/`icon_texture`: keep XML1's (`textures/ui/<hero>_all.png`, icons 0..3; the atlas is on disc and in the
  build). Inline passives without icon_texture: `icon_texture="textures/ui/talent_icons.png" icon="4"` (XML2's
  generic "Passive" cell). Build option `--hero-icons xml1|generic` (default xml1) switches every hero talent to
  `talent_icons.png` cells (0..7) if the 2x2 atlas renders wrong (7.2 #5).
* Levels: keep XML1's explicit `<level>` elements (XML2 accepts explicit levels: `might`, `psionic_fury`) with
  their `<require cat="level" level="N"/>` (numeric), `degree="see"`, `cost`, `descname` kept verbatim
  (harmless if ignored, correct if honoured; per-level descname/cost support UNVERIFIED). A rung without a level
  requirement gets `<require cat="level" level="1"/>`.
* Description text: XML1 `^CODE` tokens are resolved at build time from `xml1_loose/data/values.xml`
  (`^L2` -> `9-11`, `^P1+` -> `15`, `^BST1` -> `15`, `^A8` -> its number) and `^N` -> `N`; `^` is removed
  (E19: the XML2 formatter substitutes `%name` tokens only). `%` characters in XML1 text (`-^100% Knockback`)
  are escaped as `%%` (XML2 team_bonus uses `%%`).
* `<require cat="talent" ...>` -> `cat="skill"` (both resolve as talent lookups, FUN_004ac470; XML2 spelling).
* `activepowerup` children -> section 4.6.
* Hero-prefixed passives (`x1_cyclops_accuracy` ...) are built from `xml1_loose/data/shared_talents.eng`
  definitions with the same rules (descname/description/levels; activepowerups per 4.6).
* File size check: <= 8 talents per hero (cap 100 per file); total registered = shared + party files (6.2).

### 4.3 Powerstyle collapse - which moves

Parse the XML1 style (`ctx.read_x1_xml('data/powerstyles/ps_<hero>.eng')`, then `ctx.x1_schema` as every
import does). Classify FightMoves:

* **Chain rung**: has `inherit="<other move of this style>"` and a `<require>` on a talent with `level > 1`, or
  is one of the top names `power_attack`, `power_smash`, `power_boost`, `power_xtreme` inheriting from a rung.
  Following `inherit` reaches the **chain root**: the move with `<require ... level="1"/>` (or no level) and the
  static attributes (`animenum`, `icon`, ...).
* **Power root**: a chain root whose gating talent has XML1 `power="0..3"` -> output name `power1/2/3/9`.
  Per hero the four roots are the `icon_groups` roots of inventory.json (e.g. Cyclops optic_beam1,
  optic_sweep1, cyc_tactics1, cyc_xtreme1; Gambit card_throw1, StaffSlam1, kinetic_boost1, pick_up_1; Rogue
  sstrike1, **ability_drain1** (not ability_drain_decide1, D15), rogue_shield1, power_xtreme; ProfXAstral
  power_attack, power_smash, power_boost, power_xtreme; see section 3).
* **Other chain** (gated on a passive talent, e.g. Gambit `time_bomb1..4` on `overload`): collapses the same
  way, keeps the root's name.
* **Kept move**: everything else (basic attacks, pickups, jumps, skating, teleports, xtreme sub-moves such as
  Rogue's `xtreme_relocate/contact/return`, Gambit's `charged_throw`), copied with the trigger fixups of 4.5 and
  the `icon` attribute removed (only the four `powerN` moves keep an `icon`).
* Dropped: every non-root rung, the Rogue decide chain, the root attribute `fallback`, root-element attributes
  `iconcolumns`/`iconrows`/`exclusive` (not exe strings); `iconfile` and `cansteal` kept.
* Every `<chain result="X">` / attribute value naming a dropped rung is remapped to its collapsed move
  (e.g. Rogue `Special -> ability_drain` -> `power2`); the selftest fails on any dangling move name.

### 4.4 Powerstyle collapse - folding the rungs into talentvalues

For a chain with root R (rank 1) and rungs r2..rN (rank = the rung's `<require level>`):

1. Output move = R's element: `name` = powerN (or R's name), `<require cat="skill" item="<talent>" level="1"/>`,
   all R children (events, triggers, chains) kept.
2. Each rung contributes override triggers `<trigger tag="t" a1="v1" .../>` (no `name`): the root trigger with
   the same `tag` is the target. For every `(tag, attribute)` overridden anywhere in the chain:
   * numeric (after value-code resolution) or `"min max"` -> the root trigger's attribute becomes
     `%x1_<hero>_<talent>_<short>` and a `talentvalue` per rank is emitted (rank without an override inherits
     the previous rank's value; rank 1 = root value). `<short>`: `dmg` (damage), `pwr` (powerusage), `kb`
     (knockback), `dlv` (damagelevel), `fxl` (fxlevel), `rad` (radius), `lif` (life), `lvl` (level),
     `rng` (maxrange), else the attribute name; with a `_t<tag>` suffix when two triggers of the move override
     the same attribute. Talentvalue names <= 31 characters (truncate the talent part, keep uniqueness).
   * `pierce="true"` appearing at rank k -> attribute `piercechance="%..._pierce"` with values 0 (ranks < k)
     and 1 (ranks >= k) (XML2 uses `piercechance` %values on ice beams; on `beam` attack types UNVERIFIED ->
     fallback literal `pierce="true"` if the in-game check 7.2 #6 shows no piercing at all).
   * any other non-numeric override (enum/boolean, e.g. `apply_ally="near"|"all"`, `aitype="buff"`): the value
     of the **highest** rung is written on the root trigger; recorded in `heroes_detail.json` as `enum_top_rung`
     (fidelity loss, section 3).
3. A rung trigger whose `tag` does not exist on the root (a trigger added at a higher rank): added to the output
   move with its numeric attributes as talentvalues that are `0` below its first rank (`life="0"` / `damage="0"`
   = no effect) - recorded as `added_trigger`.
4. Root-level `<require>` of rungs on other talents (rare) are kept only if present on the root.
5. Every attribute listed in section 2's %-vocabulary of XML2 retail (trigger damage/powerusage/life/knockback/
   maxrange/count/damagepercent/chance/piercechance/radius..., event damage/knockback/powerusage/life,
   FightMove playspeed/energypersecond, affecter level, require level) may carry a `%` reference; the selftest
   rejects a `%` reference on any other attribute (fallback: top-rung literal).
6. talentvalue `level` = talent rank (the talent's explicit `<level>` count must equal N; if a chain has more
   rungs than the talent has levels - e.g. XML1 `cyclops_tactics` 9 levels vs 8 rungs + power_boost = 9 - the
   selftest asserts equality per (hero, talent); mismatches are an error to be resolved by hand).

### 4.5 Trigger and attribute fixups applied to every output move (collapsed or kept)

| XML1 form | XML2 form written | status |
|---|---|---|
| value codes `L0..H6`, `L1+`, `K1..K10`, `P0..P16`, `P1+..`, `BST1..9`, `A1..A10`, `XTL1..6` anywhere in trigger/event/require attributes | resolved to XML1's numbers from `xml1_loose/data/values.xml` (`min` or `"min max"`); typos `XLT2..6` -> the XTL value; unknown code -> error | deterministic; removes the dependence on the 34 differing codes (values.xmlb is still shipped with the 16 appended codes) |
| `<trigger name="powerup" powerup="X" level="L" [affect_type="scale"] [scope_damage/scope_attack] life= powerusage= effect= effect_cust1= func_*= no_shadow= apply_*= ...>` | `<trigger name="powerup" life=.. powerusage=.. [no_shadow] [apply_ally/apply_enemy/apply_self]><special_fx effect="<effect>" how_used="primary"/>[<special_fx effect="<effect_cust1>" how_used="deactivate"/> when func_deactivate="customeffect1deactivate"]<affecter attribute="<X>" [affect_type="scale"] level="L" [scope_damage=..] [scope_attack=..]/></trigger>` | XML2 retail form (ps_beast p3, ps_bishop p2); `func_*`, `life_max`, `level_max`, `fx_bolt`, `center_bolt`, `allow_actors`, `allow_non_actors`, `apply_held`, `user1/user2` kept only where listed below |
| `powerup="might_mode"` | two affecters `might_heaviness` + `might_structure` with the same level | XML2 `might` talent form |
| `powerup="special"` on a boost/charged-object trigger (Gambit time bomb, elemental boosts) | trigger kept with `class="add_attack" damagepercent="0.5" damagetype="<damagetype>"` when it carries `damagetype` + `scope_damage`; otherwise kept verbatim minus `func_*` | UNVERIFIED semantics; reported |
| `powerup="def_damage/speed/strength/body/mind/move/jump/def_knockback/def_pain/deflect_damage/confused/fear/traits/invisible/nullify/drain_victim/stun_lock/damage/atk_damage_scale/none"` | affecter of the same attribute name | all but `atk_damage_scale` and `none` are in XML2's affecter vocabulary (inventory.json); the two are UNVERIFIED (kept, warned) |
| `skin="1805" skin_swap="true"` (Magma form) | `skin="15805"` (map_skin) + `skin_swap="true"` kept | `skin_swap` is an exe string; behaviour UNVERIFIED (7.2 #11) |
| `bolton=` / `boltslot=` / `model=` on triggers (visor, ice blades) | kept; `model` 4-digit -> map_skin | XML2 uses `bolton` triggers too |
| `Sound="character/<dir>/..."` | kept (XML1 keys hash-resolve through the installed banks, sound.md) | - |
| `require cat="talent"` | `cat="skill"` | E: FUN_004ac470 treats both as talent lookups |
| root attrs `IconColumns/IconRows/exclusive` | dropped | not exe strings |
| `handler="ch_*"` | kept; the selftest lists unregistered ones (`ch_throw`, `ch_roguedecide`) as warnings | E14 |
| `<event>` definitions | kept (names checked against the move's triggers) | - |
| attribute names | lowercased + sorted by `C.encode_xmlb`; element tags keep case (`FightMove`, `damageMod`) | E20 |

### 4.6 `activepowerup` -> XML2 `<powerup>`/`<affecter>` (talent levels and the 3 shared passives)

Inside the owning `<level>`: one `<powerup life="-1">` per XML1 level holding one `<affecter>` per XML1
`activepowerup` (grouped), except the class-based forms:

| XML1 | XML2 written | status |
|---|---|---|
| `powerup="special" func_attempt_hit="DamageAddAttack" damagetype=dmg_X level=Lcode user1 user2 effect_cust1="powerups/<hero>_elemental" scope_damage=dmg_physical` (43: Frost, Gambit, Iceman, Magma, Phoenix, ProfXAstral, Psylocke, Storm) | `<powerup class="add_attack" damagepercent="P" damagetype="dmg_X" life="-1"><special_fx effect="powerups/<hero>_elemental" how_used="custom"/><affecter attribute="powerup_scope"><scope scope_attack="punch"/><scope scope_attack="kick"/></affecter></powerup>` with `P = min(2.6, 0.5 + 0.35*(rank-1))` (XML2 iceman/bishop curve 0.5..2.6; XML1 added a flat L-code amount instead) | retail form; the percentage curve is a balance heuristic (section 8 Q6) |
| `powerup="damage" level=L scope_damage=dmg_mental` / `scope_node=psylocke_power` / `scope_attack=punch` | `<affecter attribute="damage" level="<L number>" scope_damage=.. / scope_node=.. / scope_attack=..>` | XML2 bishop `damage` + scope_node |
| `powerup="atk_damage" ... <scope scope_node="gambit_staff"/>` | `<affecter attribute="atk_damage" level=.. scope_node="gambit_staff"/>` | scope_node is an XML2 affecter attribute |
| `powerup="damageLevel" level=N scope_attack=punch` | `<affecter attribute="damageLevel" level="N" scope_attack="punch"/>` | string exists; as affecter UNVERIFIED (warned) |
| `powerup="none" func_damage="damageaddbleed" level=L user1=S` | `<powerup class="add_harming" damagepercent="0.2" damagetype="dmg_physical" life="S"><affecter attribute="powerup_scope"><scope scope_attack="punch"/></affecter></powerup>` | UNVERIFIED (XML2 `add_harming` class exists); option `--hero-bleed off` drops it |
| `powerup="reflect_damage" level=L user1=C` | `<powerup life="-1" chance="C/100"><affecter attribute="reflect_damage" level="<L number>"/>[<affecter attribute="powerup_scope"><scope scope_attack="punch"/><scope scope_attack="kick"/></affecter> for grappling]</powerup>` | `powerup.chance` and `reflect_damage` exist in XML2 data |
| `powerup="might_mode_mod" level=N` | `<affecter attribute="might_heaviness" level="N"/><affecter attribute="might_structure" level="1"/>` | XML2 might form; `might_mode_mod` is not an exe string |
| `powerup="speed"/"strength" level=N` (additive) | `<affecter attribute="speed"/"strength" level="N"/>` | XML2 additive form (critical) |
| `powerup="atk_knockback" level=K scope_damage=..` | `<affecter attribute="atk_knockback" level="<K number>" scope_damage=..>` | string exists; UNVERIFIED |
| `powerup="no_iceshell" affect_type=scale level=0` | identical affecter | retail `sentinel_special` form |
| `powerup="maxhealth"/"maxenergy" affect_type=scale level=1.1` (toughness, mutantmastery) | identical affecter | XML2 vocabulary |
| `powerup="health_regen" level=N user1=100` + `def_pain affect_type=scale` (healing_factor) | `<affecter attribute="health_regen" level="N"/>` + `<affecter affect_type="scale" attribute="def_pain" level=..>` | XML2 vocabulary (`user1` dropped) |
| `<scope scope_attack/scope_node>` children | folded into the affecter's `scope_*` attribute, or a `powerup_scope` affecter when several | XML2 forms |

### 4.7 shared_talents rewrite (heroes.py patches both files written by characters)

Keep exactly these 47 (rule: fightstyle_* named by a stats entry or XML1 hero; named by a style `<require>`
in the build; XML1 hero plain reference; engine special name; XML2 real definition still referenced by npcstat):
`fightstyle_finesse1, fightstyle_hero, fightstyle_wrestling, fightstyle_psionic, fightstyle_gun_rifle,
fightstyle_gun_hip, fightstyle_baton, fightstyle_huge, fightstyle_nonhuman, fightstyle_villain, leadership, grab,
critical, might, flight, energy_resistant, mental_resistant, physical_resistant, energy_resistant_share,
mental_resistant_share, physical_resistant_share, spawn_invis, dr_stun, sentinel_special, boss_resistances,
monst_dmg_high, aval_crack, aval_quake, blob_butt, blob_belly, havok_beam, havok_nova, jug_punch, jug_slam,
jug_armor, marrow_shards, marrow_armor, marrow_xtreme, steal_form, pyro_flame, pyro_firering, pyro_firebat,
sabre_spin, sabre_claw, acrobatics, toughness, mutantmastery`.

Drop 41: XML2's unreferenced `fightstyle_staff, mutantmaster, block, psionic_fury, knock_resist,
corrupt_vampire, deadpool_regen, blimpyboy, monst_dmg_low`; the 5 `profx_*` (move to ProfXAstral's file); the
empties referenced only as NPC `<talent>` children: `avalanche_special, blob_special, forge_special,
havok_special, juggernaut_special, jug_xtreme, magnetoboss_special, marrow_special, mastermold_special,
physical_res, multipleman_special, mystique_special, pyro_shield, pyro_special, sabretooth_special,
sabre_special, sentspider_special, shade_spawn, shadow_special, shadow_special2, pod_special, as_special,
shocker_special, stealth_special, suicide_special, spidermine_special, toad_special` (their `<talent>` children
are removed from the XML1 npcstat entries at the same time, so validate V5's "talent defined" check holds).
`toughness`, `mutantmastery`, `acrobatics` are replaced by real definitions converted from
`xml1_loose/data/shared_talents.eng` (4.6). The keep list is computed, not hardcoded: heroes.py re-derives it
from the build and asserts it equals this list (a difference is a warning naming the delta).

### 4.8 Character packages

For every herostat costume skin S (stats `skin` + each `skin_<costume>` variant) of hero H:
`Packages/generated/characters/<h>_<S+14000>.PKGB` and `_nc.PKGB` from the XML1 bundle
`packages/generated/characters/<h>_<S>.fb` / `_nc.fb` (manifest), entries through `C.map_package_entry` (as
`characters._Builder.map_entry` does; skins/anim DBs/HUD/UI/effects/models/textures/entities), plus:
* `<texture filename="textures/ui/<h>_all"/>` (already in every XML1 bundle),
* `<xml_talents filename="data/talents/<h>"/>` (R9; both packages, as XML2 cyclops_0103 and _nc do),
* `<fightstyle filename="data/powerstyles/<mapped>"/>` in the combat package only (XML2 `_nc` has none),
* BoltOn models (`characters._Builder.add_boltons` logic: models/bolton/* entries),
* the `data/entities/*` file the XML1 bundle lists (magma_ents, card_ents ...) imported with the XML1-wins
  policy exactly as characters does (`_asset`).
`<h>_xml.PKGB` = `[xml_talents data/talents/<h>, xml data/entities/<...> (if any), fightstyle data/powerstyles/<mapped>]`
(XML2 cyclops_xml form; the XML1 `<h>_xml.fb` lists only the style). Packages the tour build already wrote for
the 6 hero-as-NPC heroes are overwritten (`replace=True`). Placeholder packages per D2.

Implementation note: reuse `characters._Builder` for `build_pkg`/`add_boltons`/`write_pkg`/`map_entry` by
constructing `_Builder(ctx)` and calling `emit_namespace`-independent pieces is NOT possible today (`map_entry`
needs `actor_new`/`ui_new` filled by `emit_namespace`). heroes.py therefore builds packages with the pure
`C.map_package_entry` + `C.package_entry_files` existence checks (same result for hero bundles, whose entries
are all in the character namespace or generic assets characters already imported) and imports missing generic
assets through `ctx.import_x1_asset` under the same policy (`characters.FORCE_PREFIXES`).

### 4.9 `menus/characters_heads` and `_pc`

`Packages/generated/maps/package/menus/characters_heads.PKGB` = `[model ui/models/characters/<prefix>01 for
each of the 15 heroes that has one on disc (all but ProfXAstral: 14101, 14201, 14301, 14401, 14501, 14601,
14701, 14801, 14901, 15201, 15301, 15501, 15601, 15801), model ui/models/characters/9999, model
ui/models/m_team_roster_screen]`; `characters_heads_pc.PKGB` = `[model ui/models/characters/9999]` (the engine
loads both, 0x5e1f06/0x5e1f19; an empty packagedef is avoided). Both base files are overwritten
(`overwrote_base`, like npcstat). The 16 XML1 head models are already written by characters
(`UI/models/characters/<+14000>.IGB`).

### 4.10 npcstat rewrite and ctx.shared

heroes.py patches `Data/npcstat.XMLB` and `.engb` (`ctx.patch_out_xmlb`): remove entries named in the new
herostat; remove `<talent>` children naming a dropped shared talent (4.7) from XML1-origin entries. It then sets
`ctx.shared['stats'][lname] = {name, file:'herostat', skin, characteranims, powerstyle, sounddir,
origin:'xml1_hero'}` for the 15 heroes (`origin:'xml2'` for default, `'x1_placeholder'` for the 5 clones),
deletes the 6 removed npcstat keys, refreshes `ctx.shared['stats_names']`, and adds its packages to
`ctx.shared['char_packages']`. `characters.planned_stats` stays untouched (its `names` set still contains the 6
names, now as heroes, so zones' CHRB checks pass).

### 4.11 Scripts (minimal, this milestone)

* `scripts_transform.join_hero(lines, bit)` (roster.md T7): in the installed `nyc/alison/add_cyclops.py` and
  `mansion/dr_mag2/blob/add_cyclops.py`, replace the 3-line pattern `unlockCharacter("cyclops", "" )` x2 +
  `extractionPointLite("_ACTIVE_HERO_", "true", "false", "false" )` with `unlockCharacter("cyclops", "" )`,
  `# ( "x1 addHero(cyclops): XML2 has no seat-a-hero call (0x46c810 is not scriptable); save the spot and open the team menu" )`,
  the `waittimed`/`createPopupDialogXml("dialogs/tut15")` lines moved before, `remove ( "cyclops", "cyclops" )`,
  `setGameFlag("x1join", <1|2>, 1 )`, `extractionPointChange("_ACTIVE_HERO_", 0 )`; zone-script guards in
  `nyc/alison/nyc1_1_3` and `mansion/dr_mag2/mag_nyc4` removing `trigger_touch03` + `sp_cyclops01` when the bit
  is set; bit cleared after the `# ( "XML1 beginMission(alison)" )` / `(dr_mag2)` markers. Called from
  `scripts._script_text` after `choose_team_in_bodies`. `x1join` counts toward `MAX_GAME_FLAG_NAMES`.
* New Game hook unchanged (option B). `--start-zone`/`--tour` hooks unchanged (slot 0 = the hidden placeholder).
* Lint (scripts_lint): error on `loadMapAddTeam`; error on an `extractionPointLite("_ACTIVE_HERO_", ...)` not
  preceded by `setGameFlag("danv", 1, 1 )` (T13).
* T8/T9/T10 (roster.md) are v2.

---------------------------------------------------------------------------------------------------------------

## 5. Module plan

### 5.1 `tools/xml1build/heroes.py` (new; owner name `heroes`)

```
"""xml1build.heroes - XML1's playable roster on XMen2.exe (tools/xml1build/SPEC_heroes.md)."""
ROSTER_X1 = ('Beast','Colossus','Cyclops','Frost','Gambit','Iceman','Jubilee','Magma','Nightcrawler','Phoenix',
             'ProfXAstral','Psylocke','Rogue','Storm','Wolverine')          # XML1 herostat.eng order
PLACEHOLDER = 'Magneto'; PADS = ('x1pad1','x1pad2','x1pad3','x1pad4')
HERO_COUNT = 21; TALENT_POOL = 100; SHARED_CAP = 99; FILE_CAP = 100; STATS_TALENT_MAX = 19
POWER_SLOT = {'0':'power1','1':'power2','2':'power3','3':'power9'}
AUTOSPEND = {...D13...}; TEXTUREICON = {...D14...}; HERO_ONLY_PASSIVES = ('accuracy','pointblank','grappling','healing_factor','knockback')
SPECIAL_TALENT_NAMES = ('flight','ice_skating','night_faith')            # 0x4be130
VALUE_REF_ATTRS = {('trigger','damage'), ('trigger','powerusage'), ...}   # section 2 %-vocabulary
AFFECTER_VOCAB = frozenset({...inventory.json xml2_contract...})

def hero_plan(ctx) -> dict          # pure provider, cached in ctx.shared['_heroes_plan']:
    # {'order': [21 names], 'index': {lname: statsIdx}, 'talent_base': {lname: (idx+1)*100}, 'x1': {lname: Element},
    #  'costumes': {lname: [(slot, xml1 skin4, mapped skin)]}, 'style': {lname: mapped style name},
    #  'placeholders': [...], 'roster_mode': ctx.opt('hero_roster','21')}

class _Values:    # xml1 values.xml codes -> number strings; resolve_text(desc) for ^tokens; resolve(attr value)
class _TalentFile: # per hero: talents (Element list), talentvalues registry (name -> {rank: value}), counts
class _StyleCollapse: # classify(), collapse_chain(), fixup_trigger(), remap_names(); returns root + report
class _HeroBuilder:
    load()                 # XML1 herostat/shared_talents/values/styles; XML2 herostat/shared_talents/autospend/team files
    convert_hero(name)     # -> (herostat Element, _TalentFile, style root, package plan, report)
    default_entry(), placeholder_entry(name)
    write_all()            # talents files, styles (replace=True), herostat pair, npcstat patch, shared_talents pair,
                           # packages, characters_heads pair, heroes_detail.json
def run(ctx)               # the module step
def validate_out(ctx)      # V-H1..V-H12 over <out> (called by build_xml1.py after validate.run); pure reads
def check(out)             # CLI: python -m xml1build.heroes check <out>  (same checks, no ctx.shared)
```

Reporting (SPEC 4.6 discipline): counts `heroes_converted`, `hero_talent_files`, `hero_talents_total`,
`talentvalues`, `styles_collapsed`, `moves_collapsed`, `moves_kept`, `moves_dropped`, `enum_top_rung`,
`added_triggers`, `shared_talents_after`, `shared_talents_dropped`, `npc_talent_refs_dropped`,
`hero_packages`, `stats_names`; notes per hero; `defer` for every D15 item; errors for any hard rule.
Detail file `_build/heroes_detail.json`: per hero the chain map (rung -> collapsed name), talentvalue table,
losses, per-file talent counts, the shared keep/drop lists with reasons, package lists.

### 5.2 Validator checks inside heroes.py (`validate_out`, run from build_xml1.py; never in validate.py)

| id | check | severity |
|---|---|---|
| V-H1 | `Data/herostat.{XMLB,engb}`: exactly `HERO_COUNT` entries (17 with `--hero-roster 17`), order == plan, names unique case-insensitively, <= 18 chars, every entry has `skin` (4-5 digits, prefix <= 255), `characteranims` actor exists, `autospend` in `Data/autospend.XMLB`, the 15 XML1 heroes have `team="hero"`, `playable="true"`, `power1..power4`, `textureicon`, `powerstyle` file exists; placeholders have no `team`/`playable` | error |
| V-H2 | no herostat name in `Data/npcstat`; herostat + npcstat unique names <= 296 | error |
| V-H3 | `Data/talents/<name>.XMLB` and `.engb` exist for the 15 heroes, decode, <= 8 talents, every `talent power=` names a FightMove of the hero's style, every `<require cat="skill" item>` resolves (file or shared), every `%name` in the file and the style has a talentvalue in that file with ranks 1..N contiguous, talentvalue names <= 31 chars, no talent name registered twice across shared + any two hero files | error |
| V-H4 | shared_talents.{XMLB,engb}: same name set, <= 99, == the derived keep list (delta = warning), `SPECIAL_TALENT_NAMES` present where a hero references them; `shared + max over any 4 hero files <= 100 - 8` | error / warn |
| V-H5 | each hero style: exactly the moves `power1`, `power2`, `power3`, `power9` exist with `<require cat="skill" item=<the talent whose power= names it>>`; no move named `power_attack/power_smash/power_boost/power_xtreme` or with `fallback=`; every `inherit=` and `<chain result>` names an existing move; no value code left (regex `^(L\d\+?|M\d|H\d|K\d+|P\d+\+?|BST\d|A\d+|XTL\d|XLT\d)$` on trigger/event attributes); `%` references only on `VALUE_REF_ATTRS`; unknown `ch_*` handlers and non-vocabulary affecter attributes are warnings | error / warn |
| V-H6 | packages: for every herostat costume, `<name>_<skin>.PKGB` and `_nc.PKGB` exist, list `actorskin <skin>` and `actoranimdb <anims>`, `xml_talents data/talents/<name>` (basename == stats name), the combat one lists `fightstyle data/powerstyles/<mapped>`; every entry resolves (`C.package_entry_files`); `<name>_xml.PKGB` exists; placeholders' packages exist | error |
| V-H7 | `menus/characters_heads.PKGB` lists exactly the 14 XML1 heads + 9999 + m_team_roster_screen; `_pc` lists 9999; every listed model exists | error |
| V-H8 | HUD/UI assets per costume: `HUD/hud_head_<skin>.IGB` or a fallback candidate (default costume / variant 01) exists; `UI/HUD/characters/<skin>.IGB` (warn if missing); `Textures/loading/<prefix>01.IGB` (note) | error / warn / note |
| V-H9 | actor budget re-check with the heaviest XML1 party (Iceman, Nightcrawler, Magma, Gambit) using `actor_budget.zone_estimate` machinery (party slots from the hero packages): every converted zone <= 37 (error), <= 35 (warn) | error / warn |
| V-H10 | scripts: `Scripts/menus/new_game(_hard).py` load with `loadMapChooseTeam` unless `--newgame keepteam` is set; every `loadMapKeepTeam` first-load hook (`--start-zone`/`--tour`) requires the stats names `magneto`, `cyclops`, `wolverine`, `storm` to exist in herostat (they do: placeholder + 3 XML1 heroes) | error |
| V-H11 | `ctx.shared['stats']` (when present) agrees with `<out>` herostat (names, file, origin) | warn |
| V-H12 | T7 pattern present in the two add_cyclops scripts and their zone guards; no `extractionPointLite` addHero emulation left | error |

### 5.3 `tools/xml1build/heroes_selftest.py` (new, standalone like characters_selftest.py)

`python tools/xml1build/heroes_selftest.py <out>` after `build_xml1.py --out <out> --no-movies --only
characters,heroes --no-validate`. Re-derives from `<out>` + registry + XML1 sources (no ctx.shared):
HA every XMLB owned by heroes decodes/re-encodes byte-identically with lowercase+sorted attrs; HB = V-H1..V-H8
recomputed independently; HC round trip: for each hero and each power talent, the collapsed move's talentvalue at
rank r equals the XML1 rung r's resolved value for every overridden attribute (reads the XML1 style again and
walks the inherit chain itself); HD every XML1 FightMove of the hero style is either collapsed into a named
output move or kept by name (the report's chain map is complete); HE description text has no `^` and no unresolved
code; HF `hero_plan(ctx)` on a fresh context predicts the herostat order and talent bases in `<out>`; HG the
6 removed npcstat names are absent and no XML1 NPC entry still names a dropped shared talent; HH package
count == 38*2 + 15 + 10; HI shared keep list == section 4.7 (delta printed); HJ budgets: shared + worst 4 files
<= 92, stats names <= 296, per-file <= 8, herostat talent children <= 19; HK the base files heroes overwrote are
only herostat, npcstat, shared_talents, characters_heads(_pc), the 6 hero-as-NPC packages and the 15 styles.
Exit 1 on any error; prints counts.

### 5.4 Touch points in existing modules (minimal; the act-crash agent owns zones.py, validate.py, SPEC.md)

| file | change |
|---|---|
| `tools/xml1build/common.py` | `MODULE_ORDER = ('characters', 'heroes', 'scripts', 'zones', 'media')` (line 54). Nothing else: `map_*`, `write_xmlb_pair`, `patch_out_xmlb`, `import_x1_asset`, `read_x1_xml`, `x1_schema` already provide what heroes needs. |
| `tools/build_xml1.py` | argparse: `--hero-roster {21,17,21xml2}` (default 21), `--hero-icons {xml1,generic}` (default xml1), `--hero-bleed {on,off}` (default on), `--newgame {chooseteam,keepteam}` (default chooseteam; keepteam only with the proxy patch, refused by V-H10 otherwise). `CONTENT_OPTS` += `'hero_roster': ('heroes','21'), 'hero_icons': ('heroes','xml1'), 'hero_bleed': ('heroes','on'), 'newgame': ('scripts','chooseteam')`. After the `validate` step: `from xml1build import heroes; ok &= C.run_step(ctx, 'heroes_validate', heroes.validate_out)` (guarded like validate). Report `build` dict += the new options. Docstring step list mentions heroes. |
| `tools/xml1build/characters.py` | none required. Optional cosmetics later: the `ctx.defer('XML1 hero conversion ...')` at line 1438 becomes a note when `'heroes' in ctx.shared['selected_modules']`; `_hero_refs_report`'s defers likewise. Do not change `planned_stats`, `convert_stats`, `_check_caps` (it compares the BASE herostat, which still has 21 names, and passes). |
| `tools/xml1build/actor_budget.py` | no code change: `Budget.party()` already takes skins/anim DBs from the build's herostat and the `<name>_<skin>[_nc]` packages, so the XML1 party is measured automatically once heroes runs before zones; `character_namespace()` keeps working (hero actors are now needed and survive the prune). Update the `PARTY` comment and the docstring sentence "hero as NPC ... dead weight" in the same commit as SPEC_heroes.md. |
| `tools/xml1build/zones.py`, `igb_budget.py` | no change (`NEW_GAME_PARTY` names remain valid stats names). |
| `tools/xml1build/scripts_transform.py` | add `join_hero(lines, bit)` + `join_hero_zone_guard(lines, bit)` (4.11) and their selftest cases; `scripts.py._script_text` calls them after `choose_team_in_bodies` for the two scripts / two zone scripts; `scripts_lint.py` T13 rules. |
| `tools/xml1build/testhooks.py` | no change. |
| `tools/xml1build/validate.py` | **no change for the default roster.** Known consequences to record in SPEC_heroes.md: (a) V2 line 692-693 warns "herostat rewritten in phase 1" (owner heroes) - harmless; when the act-crash agent has landed, change that warning to fire only when the owner is not `heroes`; (b) V5 line 896-897 `len(hero) != HERO_COUNT` errors for `--hero-roster 17` - relax to `1 <= len(hero) <= 21` in the same later edit; (c) V5's per-entry checks classify the 15 heroes as `xml1` through `ctx.shared['stats'].origin` (`'xml1_hero'.startswith('xml1')`) and verify their talents against `Data/talents/<name>` - satisfied by 4.2. |
| `tools/xml1build/SPEC_heroes.md` (new) | the normative text: sections 1, 2, 4, 5.2 of this document in SPEC style (owns, must, counts, deviations), the module contract (`hero_plan` provider, `ctx.shared` keys `heroes_plan`, `stats` origin `xml1_hero`/`x1_placeholder`), the validator ids V-H1..V-H12, the in-game checklist of section 7.2, and the D15 deferral list. SPEC.md gets one line at the end of section 5.0's module list pointing to it (only if the act-crash agent has finished; otherwise the pointer waits). |
| `tools/xml1build/regress_nyc1.py` | re-run; if a check compares herostat with the proven test copy, allowlist `Data/herostat.*` (heroes owner). |

### 5.5 Implementation order (each step leaves the build green)

1. `heroes.py` skeleton + `hero_plan` + herostat/placeholders/npcstat/characters_heads/packages, talents files
   with **XML1 raw levels and no styles change** (styles still XML1 chains): validator green, boot test possible
   (7.2 #1-#3) - powers will not fire yet (no `powerN` moves).
2. `_StyleCollapse` + talentvalues + trigger fixups; `heroes_selftest.py` HC/HD; shared_talents prune.
3. T7 scripts pass + lint.
4. SPEC_heroes.md, HANDOFF note, commit.

---------------------------------------------------------------------------------------------------------------

## 6. Resource budget

### 6.1 Stats names (cap 296, E2)

| | today (build/xml1_tour) | after |
|---|---|---|
| herostat | 21 (XML2) | 21 (default + 15 XML1 + 5 hidden) |
| npcstat | 213 (190 XML1 NPC + 6 hero-as-NPC + 17 kept XML2) | 207 |
| total | 234 | **228** (`--hero-roster 17`: 224; `21xml2`: 228) |

### 6.2 Registered talents (pool 100, E9; shared cap 99, E8; file cap 100)

| | today | after |
|---|---|---|
| shared_talents | 88 | **47** (4.7) |
| per-hero files (talents) | XML2: 12-15 each | Beast 5, Colossus 6, Cyclops 6, Frost 7, Gambit 7, Iceman 8, Jubilee 7, Magma 7, Nightcrawler 6, Phoenix 6, ProfXAstral 6, Psylocke 6, Rogue 5, Storm 5, Wolverine 7 |
| worst party (4 largest files) | 88 + 4x15 = 148 -> truncated at 100 today | 47 + (8 + 7 + 7 + 7) = **76**; + one danger-room file (8) = 84 <= 100 |
| herostat `<talent>` children per entry (cap 19, E11) | 4-7 | 7-12 (ProfXAstral 12 incl. six level-1 inline refs) |

### 6.3 Actor slots per zone (40, error > 37, warn > 35; E17, SPEC 14)

Party cost in slots (actorskin + actoranimdb entries of the combat package): most heroes 2; Magma 3 (extra skin
15805); Iceman 4 (14001 and 14805); Nightcrawler 4 (tail 23801 + its anim DB). Recomputed over all 197 converted
zone packages of `build/xml1_tour` with `actor_budget.zone_estimate`'s formula (permanent 6 + party + zone
package + CHRB/spawner characters, sets deduplicated; XML1 hub NPC heroes such as `nightcrawler` in mansion3_1
resolve to the same XML1 actors as the party member and are counted once):

| party | party slots | max zone | zones > 35 | zones > 37 |
|---|---|---|---|---|
| XML2 stand-ins today (magneto/cyclops/wolverine/storm) | 8 | 34 (mansion3_1, mansion4_1) | 0 | 0 |
| opening XML1 party wolverine/cyclops/storm/rogue | 8 | 32 (mansion3_1) | 0 | 0 |
| heaviest XML1 party iceman/nightcrawler/magma/gambit | 13 | **35** (haarp/int/haarp2_6), 34 (mansion4_1, astral/ast3/colosseum) | 0 | 0 |

V-H9 keeps this under watch per build; the placeholder party of the test hooks (testguy + 3 XML1 heroes) is
lighter than either row.

### 6.4 IGB cache (200 records, E18, SPEC 13)

Resident outside the zone group today: 36 (permanent 16 + items 20) + XML2 party packages 15 = 51. XML1 hero
packages (records = models + effect models + HUD/UI heads, `igb_budget.package_igbs`): Magma 8, Psylocke 5,
Jubilee 3, Frost/Beast/ProfXAstral 2 (measured on the tour packages); the others estimated 3-6 from their bundles
(Gambit 4 models, Iceman 6, Wolverine 4 incl. claws). Worst 4 = about 22 -> resident 58 -> zone budget 142.
Largest converted zone package: 119 records (mansion/jugrnt/jugrnt01); V12 unchanged.

### 6.5 CStats pool (31, 0x44c3fb) and sound banks (64, media.py)

21 herostat entries resident at boot leave 10 CStats for on-demand NPC types per zone, exactly retail XML2's
situation and what the 162-zone tour ran with. Sound: `media._zone_bank_load` already counts a 4-bank party; the
15 XML1 hero banks are installed (6 merged with XML2's), unchanged.

---------------------------------------------------------------------------------------------------------------

## 7. Verification plan

### 7.1 Offline (must be green before the main session launches anything)

1. `python tools/build_xml1.py --out build/_heroes --no-movies --only characters,heroes --no-validate` then
   `python tools/xml1build/heroes_selftest.py build/_heroes` (HA-HK) - proves: schema/encoding, roster
   composition and order, talent files and their talentvalue tables equal the XML1 rungs, every `%` reference
   resolves, no dangling move name, packages and heads complete, shared keep list, budgets 6.1-6.2.
2. Full build `python tools/build_xml1.py --out build/_heroes --no-movies` (validator 0 errors expected; the one
   known V2 warning about herostat ownership); `heroes.validate_out` V-H1..V-H12 green;
   `python -m xml1build.actor_budget check build/_heroes` and `python tools/xml1build/igb_budget.py check
   build/_heroes` (6.3/6.4); `python tools/xml1build/regress_nyc1.py build/_heroes`.
3. Same with `--hero-roster 17` and `--hero-icons generic` to have the A/B builds ready.

### 7.2 In-game, in order (main session owns the game; one build/_heroes with movies off, then the full build)

| # | step | expected | if it fails -> most likely cause |
|---|---|---|---|
| 1 | launch to the main menu | menu, no crash | boot crash while loading herostat: an XMLB attribute not lowercase/sorted (null strcmp) or a malformed `skin` (0x4b9dbc); >296 names; a `<talent>` child count > 19; `data/autospend` class missing (UNVERIFIED but would not crash at boot) |
| 2 | New Game -> Normal | the team menu opens before nyc1_1_1 (option B); it lists XML1 heads for the 15 heroes only (no Defaultman/x1pad entries); unlocked = Wolverine, Cyclops, Storm (+ Colossus, Nightcrawler, Gambit, Rogue, Phoenix, Iceman if byte [0x6f3c2d] == 0 - note which, it settles that UNVERIFIED) | a placeholder listed -> the "no team hides the entry" reading (E4) is wrong: rename placeholders' `charactername` to blank and set `playable="false"`, or fall back to `--hero-roster 17` plus `21xml2`; menu crash -> characters_heads package (V-H7) or the roster's head lookup |
| 3 | confirm with Wolverine alone (remove the pre-filled slots) | nyc1_1_1 loads with XML1 Wolverine (claw bolt-ons, XML1 idle); HUD head 14301 | crash spawning `Hero_wolverine`: package `wolverine_14301.PKGB` entries (V-H6), NULL anim DB (actor slots, section 6.3), or the placeholder still in slot 0 spawning `Hero_magneto` (only with a confirm on an unchanged team - expected to spawn a testguy, not crash) |
| 4 | fight (basic attacks, block, jump); open the powers/skills screen | 4 power talents + passives listed; buying `wolv_slash` rank 1 possible; the 2x2 XML1 icons appear whole (else quartered/wrong = icon grid UNVERIFIED -> rebuild with `--hero-icons generic`) | screen crash -> talent file (ids beyond the pool, a `%name` without talentvalue, or a `<level>` count mismatch) |
| 5 | assign and use power1..power3 and the xtreme (after `awardXPToPlayable` / level-ups) | each fires with its XML1 animation and effects; damage/energy numbers on the screen come from the talentvalues; rank-up changes numbers | power does nothing: FightMove name vs talent `power=` mismatch (V-H5), `<require cat="skill">` unmet, or the talent not in the file; effects missing -> package effect entries |
| 6 | Cyclops beam at rank 6+ (cheat levels) | piercing (piercechance UNVERIFIED) | no piercing -> switch the rule to a literal `pierce="true"` from rank 1 |
| 7 | level up 3-4 times | autospend distributes stats per class; no crash on level-up notify (0x4b7d10) | crash -> `autospend` class name (UNVERIFIED for unknown names) |
| 8 | nyc1_1_3: touch the trigger (T7) | team menu opens, Cyclops (XML1) can be added, the zone reloads at the same spot, NPC Cyclops and trigger gone (guard) | hint dialog instead of the menu -> T7 not applied (V-H12); double Cyclops -> guard missing |
| 9 | Rogue power2 (after unlock, e.g. from a `--start-zone mansion/man1a/mansion1a_1` build + team menu) | drain move plays on a target (no per-victim decision) | move plays in place / no grab: accept or revisit D15 (decide handler) |
| 10 | X-traction / Blackbird at haarp: pick Iceman, Nightcrawler, Magma, Gambit | zone loads; all four idle-animate (no T-pose) | T-pose or crash at +0x1743bb = actor slots over 37 in that zone (6.3; V-H9) |
| 11 | Magma power3 (fire form) and Iceman armor | skin swap to 15805 (UNVERIFIED `skin_swap`), armor bolt-ons | no swap: drop `skin_swap` from the deferral list to "not supported" |
| 12 | costume change: console `unlockCharacter('', '60s')` (or the flashback begin body in v2) then the costume option in the team menu | Cyclops 14102 skin + hud_head_14102 | wrong head -> fallback chain (FUN_005f4ec0) shows 14101, acceptable |
| 13 | save, quit, load | party, levels, talents restored | desync -> herostat order/count differs from the saving build (R25; wipe saves between roster changes) |
| 14 | astral1 team menu | ProfXAstral offered (D12) | not offered -> `playable` did hide him after all: report; no crash |
| 15 | `--hero-roster 17` build: steps 1-3 | identical behaviour | crash/oddity -> keep 21 (default) and record UNVERIFIED #12 as "fails" |
| 16 | `--tour 12` regression on `build/xml1_tour` rebuilt with heroes (party = testguy + XML1 cyclops/wolverine/storm) | 162/162 zones load | a zone bouncing back = IGB budget (V12), a crash at spawn = actor slots (V13/V-H9) |

---------------------------------------------------------------------------------------------------------------

## 8. Open questions for Owen (implementation proceeds with the defaults)

| # | question | recommended default | why it is his call |
|---|---|---|---|
| Q1 | New Game opening: keep option B (team menu first; Wolverine must be picked by hand, Cyclops/Storm pre-unlocked by the exe) or accept option C (xml2-fix proxy patches 8 + 17 pointers in memory when the XML1 mod is active: exact XML1 opening, nothing unlocked until the story unlocks it) | **B now**; build C as a `--newgame keepteam` option only when the proxy patch exists (V-H10 refuses it otherwise) | Owen has ruled out exe patches so far; C is a code patch, even if reversible and mod-conditional |
| Q2 | Where Colossus, Psylocke and Jubilee join (XML1's mechanism was not found in data, roster.md 1.1.3) | unlock at the start of mansion4 / mansion7 / mansion2 (NPC evidence), plus Magma from mansion1 (already) | story pacing |
| Q3 | If the 2x2 icon atlas renders wrong (7.2 #4): re-atlas the 4 XML1 icons into a 4x4 IGB (new tooling) or use XML2's generic talent icons (`--hero-icons generic`) | generic until re-atlassing is worth it | art fidelity vs effort |
| Q4 | Keep XML2's `team_bonus` (fires for XML1 heroes with matching names, e.g. storm+phoenix+rogue "Femme Fatale") or convert XML1's bonuses | keep XML2's for v1 | fidelity |
| Q5 | Rogue without the per-victim decide step (power2 = drain move directly) vs waiting for a handler re-implementation | ship the direct drain; revisit if it plays badly | signature power |
| Q6 | Elemental-melee percentage curve (0.5 -> 2.6 over the ranks, XML2's shape) vs a flat XML1-like bonus | XML2 curve | balance |
| Q7 | Saves: freeze the herostat order now (any later change breaks saves) | freeze after the first playthrough passes step 13 | release policy |

---------------------------------------------------------------------------------------------------------------

## 9. UNVERIFIED items this design depends on, with the fallback each has

| item | where it matters | fallback |
|---|---|---|
| herostat entries without `team`/`playable` are hidden from the team menu (XML2's own `default` is the precedent; E4 read) | D1/D2 placeholders | 7.2 #2; `--hero-roster 17` + `21xml2` |
| fewer than 21 heroes boots | only `--hero-roster 17` | default is 21 |
| talent icon grid for 2x2 atlases | 4.2 icons | `--hero-icons generic` |
| per-level `descname`/`cost`, `degree="see"` honoured by the talent screen | 4.2 | cosmetic |
| `piercechance` on beams; `atk_knockback`, `damageLevel`, `atk_damage_scale`, `drain_victim`, `stun_lock`, `nullify`, `skin_swap` as affecter/trigger attributes; `add_harming` bleed | 4.5/4.6 | selftest warns; `--hero-bleed off`; literal `pierce` |
| unknown `autospend` class | none (all 4 classes exist) | - |
| `textureicon` atlas | D14 | cosmetic |
| BoltOn `<require>` (Psylocke blades) | D15 | first blade only |
| pending-talent table behaviour beyond "no error" | D8 (dropped NPC talent children) | the references are removed too, so nothing is pending |
| registration of a name already registered by another file | D8 | avoided by per-hero prefixes |
| `ice_skating` special-casing for Magma's skating (ch_skating shared) | Magma | in-game |
| team menu with a pre-filled non-roster slot (placeholder in slot 0 at New Game) | 7.2 #2/#3 | the confirm rewrites all slots; testguy spawns at worst |
