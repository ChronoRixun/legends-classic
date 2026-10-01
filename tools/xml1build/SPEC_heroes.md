# xml1build.heroes: the XML1 playable roster on XMen2.exe (SPEC)

Status: implemented 2026-09-27 from `research/heroes/DESIGN.md` (v1), offline-verified only (section 9 lists the
in-game checks that are still open). This file is the normative text for the module; where it and DESIGN.md
disagree, section 8 (deviations) says why. Engine facts are cited as in DESIGN.md section 2 (E1..E20) and
`research/heroes/engine.md`; every address was read there, none here is new.

---------------------------------------------------------------------------------------------------------------

## 1. Scope and place in the pipeline

`tools/xml1build/heroes.py` is a content module (owner name `heroes`) that runs after `characters` and before
`scripts`, `zones`, `media` (`common.MODULE_ORDER = characters, heroes, scripts, zones, media`). It replaces XML2's
21 stand-in heroes with the XML1 roster and patches the characters outputs the roster invalidates. Because of that
patching `--only characters` implies `heroes` (`build_xml1.parse_args`), and `build_xml1.py` runs
`heroes.validate_out` (V-H1..V-H12) right after `validate.run`.

**Owns** (writes, all through the ctx writers; `replace=True` where characters wrote the path first):

- `Data/herostat.{XMLB,engb}` (each from its own XML2 base for `default` / the XML2 pads);
- `Data/talents/<hero>.{XMLB,engb}` for the 15 XML1 heroes + ProfXGladiator (section 3.1) (identical trees;
  English text in both, like the pipeline's npcstat entries) - 9 replace XML2's same-name files;
- `Data/powerstyles/<mapped>.{XMLB,engb}` for the 16 hero styles (over the names characters wrote:
  `x1_ps_beast`, `x1_ps_colossus`, `x1_ps_cyclops`, `x1_ps_frost`, `x1_ps_gambit`, `x1_ps_iceman`,
  `x1_ps_nightcrawler`, `x1_ps_phoenix`, `x1_ps_rogue`, `x1_ps_storm`, `x1_ps_wolverine`, `ps_jubilee`, `ps_magma`,
  `ps_profxastral`, `ps_psylocke`, `ps_profxgladiator`);
- `Packages/generated/characters/<hero>_<skin>[_nc].PKGB` for every costume (39 skins x 2), `<hero>_xml.PKGB` (16),
  the placeholder packages `magneto_0002[_nc]`, `x1pad1..3_0002[_nc]` (8) = 102;
- `Packages/generated/maps/package/menus/characters_heads.PKGB` and `characters_heads_pc.PKGB`;
- patches of `Data/npcstat.{XMLB,engb}` and `Data/shared_talents.{XMLB,engb}` (ownership passes to heroes;
  validate V2 counts these as `heroes_overrides`).

Generic XML1 assets a hero bundle names (effects, textures, `data/entities/*`, bolt-on models) go through
`ctx.import_x1_asset` under SPEC 4.4 exactly as characters does (`HeroBuilder._asset`: an asset another module
already wrote from the same source is reused, never re-imported).

**Provider**: `heroes.hero_plan(ctx)` is pure (cached in `ctx.shared['heroes_plan']`): `mode`, `order` (the herostat
names in order), `index` (stats index per name), `talent_base` ((idx+1)*100), the XML1 `<stats>` per hero,
`costumes` (attr, XML1 skin, mapped skin), `style` (mapped powerstyle), `placeholders`, `xml2_pads`, `heroes`
(the playable names: the 15 + the promoted npcstat heroes of this mode) and `npc_heroes`.

**ctx.shared** after `run`: `stats` gains the herostat entries (`file: 'herostat'`, `origin: 'xml1_hero'` for the
16, `'x1_placeholder'` for Magneto / the pads, `'xml2'` for `default` and the 21xml2 pads), loses the 7 removed
npcstat names (the 6 heroes used as NPCs + ProfXGladiator) and XML2's replaced heroes; `stats_names` refreshed;
`char_packages` gains the 102 packages;
`heroes_plan`. `characters.planned_stats` is untouched (its `heroes_as_npc` still names the 6; zones' CHRB checks
resolve them through `stats_names`).

**Counts** (report.json): `heroes_converted`, `hero_talent_files`, `hero_talents_total`, `talentvalues`,
`styles_collapsed`, `moves_collapsed`, `moves_kept`, `moves_dropped`, `enum_top_rung`, `added_triggers`,
`shared_talents_after`, `shared_talents_dropped`, `npc_talent_refs_dropped`, `npcstat_heroes_removed`,
`hero_packages`, `stats_names`, `herostat_entries`, `talent_pool_worst_party`, `assets_*`. Detail file
`_build/heroes_detail.json` (per hero: chain map, collapsed chains and their rank->rung tables, kept / dropped /
renamed moves, enum-top-rung and non-vocabulary attributes, added triggers, losses, talentvalues, packages; the
shared keep / drop lists with reasons; npcstat removals; heads). `_build/heroes_validate.json` holds V-H1..V-H12.

---------------------------------------------------------------------------------------------------------------

## 2. Options

| option | values | effect |
|---|---|---|
| `--hero-roster` | `21` (default), `17`, `21xml2` | `21`: default + 15 XML1 heroes + hidden `Magneto` + `x1pad1..3` + ProfXGladiator (3.1); `17`: no pads, 18 entries (memory-safe by analysis, engine.md 1.5, never exercised - validate V5 then accepts 1..21 heroes); `21xml2`: XML2's Deadpool, Ironman, Professorx, Sunfire as pads, copied verbatim from the base files (their XML2 talent files / packages stay; `resetgame` unlocks Sunfire), no ProfXGladiator (astral_sk / boss_shadowking then keep the team menu) |
| `--hero-icons` | `xml1` (default), `generic` | talent `icon_texture`: XML1's 2x2 `textures/ui/<hero>_all.png` atlases (icons 0..3) or XML2's `textures/ui/talent_icons.png` (power1..3/9 -> cells 0..3, passives cell 4; the style `iconfile` and the four `powerN` icons follow) - the fallback if the 2x2 grid renders wrong (7.2 #4) |
| `--hero-bleed` | `on` (default), `off` | Wolverine's `wolv_sharpness` bleed (XML1 `powerup="none" func_damage="damageaddbleed"`) as an XML2 `add_harming` powerup (UNVERIFIED) or dropped |
| `--newgame` | `chooseteam` (default), `keepteam` | recorded for `scripts`; `keepteam` needs the xml2-fix proxy pointer patch (roster.md option C) and is refused by V-H10 until it exists |

All four are `CONTENT_OPTS` (a carried-over output built with another value re-runs its module) and are written to
`report.json build`. Environment fallbacks `XML1BUILD_HERO_ROSTER / _HERO_ICONS / _HERO_BLEED`.

---------------------------------------------------------------------------------------------------------------

## 3. herostat (DESIGN D1-D7, D12-D14; rules 4.1)

Exactly `HERO_COUNT` = 21 entries in this order (stats index in parentheses): (1) `default` verbatim from each XML2
file, (2..16) Beast, Colossus, Cyclops, Frost, Gambit, Iceman, Jubilee, Magma, Nightcrawler, Phoenix, ProfXAstral,
Psylocke, Rogue, Storm, Wolverine (XML1 `herostat.eng` order; per-hero talent ids 300..1700), (17) `Magneto`
placeholder (1800), (18..20) `x1pad1..3` (1900..2100), (21) `ProfXGladiator` (2200, section 3.1; this slot was
`x1pad4` before 2026-09-28). Placeholders are XML2's `default` element with the name
changed and no `team` / `playable` / `powerstyle` / `power1..4` (hidden from the roster: 0x5db590 / 0x5db810 need
CStats team 0x1d, E4); packages `<name>_0002[_nc]` = `[actorskin 0002, actoranimdb 00_testguy]`. `Magneto` exists
because `startFirstMission` seats that name by string (0x4a7b41) and the `--start-zone` / `--tour` hooks load with
`loadMapKeepTeam` (a party name that is no stats name reaches the fallback CStats of handle 0, E7 / engine.md 2.1).

Per XML1 hero (`HeroBuilder.hero_entry`): every attribute copied except `ratingmelee/ranged/support/durability`
(ignored by the exe) and empty values; `skin_magmacivilian` -> `skin_civilian` (slot 8 is free for Magma; other
unknown `skin_*` suffixes would be dropped with a warning); `skin` -> `map_skin` (+14000), `characteranims` ->
`map_animdb`, `powerstyle` -> `map_powerstyle` (must equal the name characters wrote), `moveset1` ->
`map_fightstyle`; added `autospend` (D13 table), `power1="power1" power2="power2" power3="power3" power4="power9"`,
`textureicon` (D14; 63 = the engine's "no portrait" cell for Beast, Frost, Jubilee, Magma, Psylocke, placeholders),
`playable="true"` (also ProfXAstral, D12), `scriptlevel="3"` where missing, `team="hero"`. Children: `Race Mutant`
+ `Race XMen`, `FlyEffect` copied (their effects imported), `BoltOn` copied with numeric `model` -> `map_skin`,
`anim` -> `map_animdb`, slot checked against `characters.BOLTON_SLOTS`; a BoltOn with a `<require>` child
(Psylocke blades 2/3) is dropped and noted (D15). `<talent>` children: every inline power/passive talent whose XML1
`level` >= 1 (the starting power; ProfXAstral's six + `astralknockback`; Iceman's hidden `ice_special`) as
`<talent level="N" name=.../>`, every plain reference as-is with the 5 hero-only passives renamed
`x1_<hero>_<name>` (`accuracy`, `pointblank`, `grappling`, `healing_factor`, `knockback`). <= 19 children (E11;
the maximum is ProfXAstral's 12).

### 3.1 Promoted npcstat hero: ProfXGladiator (FORCED_TEAMS_DESIGN 7.3)

XML1 seated `profxgladiator` (astral_sk and boss_shadowking: REQUIREDHERO, maxheros 1) straight from its npcstat;
XMen2.exe seats herostat names only, so `ROSTER_NPC = ('ProfXGladiator',)` promotes him the D12 way (ProfXAstral):
`hero_plan` reads his XML1 npcstat entry (`promote_npc_stats`) and he is built by the same `convert_hero` path.
- **Slot**: the last pad's, stats index 21 (talent base 2200), so every other stats index, talent base and save
  record stays (R25). Saves written before this change carry `x1pad4`'s record in slot 21 (positional, engine.md
  5.1): loading one gives the gladiator the pad's level / attribute block (level 1) - UNVERIFIED, new games are
  unaffected.
- **Entry**: as 3 (`playable="true"`, `team="hero"`, `power1..4`, autospend `support`, `textureicon` 9 = XML2's
  Professor X cell, `scriptlevel` 3); XML1's `scale_factor` 1.5 kept, the NPC-only `npchealthscale` dropped
  (`NPC_ONLY_ATTRS`; XML2 never has it in herostat); level 40 and XML1's stats unscaled (all > 10, `STAT_X1_MAX`).
- **Talents**: his five inline talents share ProfXAstral's names (`profx_*`), which V-H3 forbids (one definition per
  talent name), so they become `pxg_psychicsmash`, `pxg_psychicburst`, `pxg_psychicdefense` (boost), `pxg_xtreme`,
  `pxg_fighting` (`NPC_TALENT_RENAME`). XML1's `BADREF:@DATA@<KEY>` descriptions (unresolved string refs in his
  npcstat) become the key's text with its value codes resolved (`badref_text`: `H1_DAMAGE_K6_KNOCKBACK` ->
  `200-250 damage 370 knockback`). 5 talents; `talentvalue` code `xpg` (none needed: single-level).
- **Style**: `ps_profxgladiator`'s four top moves carry no talent require (the NPC AI picks them); `gate_npc_style`
  adds `<require cat="talent" item=<the talent with that XML1 power index> level="1"/>` (ProfXAstral's own form), so
  the collapse makes them `power1/2/3/9` gated by the pxg talents (15 -> 15 moves).
- **Packages** from his XML1 bundles (`profxgladiator_1105[_nc]`, skin 15105, `11_profxgladiator`); the talent atlas is
  ProfXAstral's (`ICON_ATLAS`: `textures/ui/profxastral_all`, no gladiator atlas on the disc); HUD head
  `hud_head_15101` (his bundle's), menu head `ui/models/characters/15101` already listed for ProfXAstral (heads
  are de-duplicated, still 15 listed).
- **Scripts**: `scripts.forced_party_plan` now seats astral_sk (side mission of astral3: push in
  `xcrystal_destroyed`, pop in `shadowking_defeated`) and boss_shadowking (SPEC 19). His REQUIRED
  `unlockCharacter("profxgladiator", "" )` stays (decision 7.4), so after astral_sk he is an unlocked playable hero
  in later team menus (XML1 never listed him); XMen2.exe has no script call that locks a hero again.

---------------------------------------------------------------------------------------------------------------

## 4. Talent files (DESIGN 4.2, 4.6)

`Data/talents/<hero>` root `<talents>`; one `<talent>` per XML1 inline `<Talent>` of the hero (power index or
levels or descname) plus the hero-prefixed passives converted from `xml1_loose/data/shared_talents.eng`. Talent
attributes: `name`, `descname`, `description` (resolved), `icon` / `icon_texture` (XML1's, or
`talent_icons.png` cell 4 for passives without one), `power` (`power1|power2|power3|power9` for XML1 power index
0..3; none for 4/5), `type="boost"` (index 2) / `"xtreme"` (index 3), `hidden`. Levels are XML1's explicit
`<level>` elements: `description` resolved (`^L2` -> `9-11`, `^P1+` -> `15`, `^N` -> `N`, `^` removed, a bare `%`
-> `%%`; E19), `cost` / `descname` kept, `<require cat="level" level="N"/>` numeric (`degree="see"` kept), a rung
without one gets level 1, `cat="talent"` -> `cat="skill"`. `<talentvalues>` come from the style collapse (section
5). `activepowerup` children -> one `<powerup life="-1">` holding the affecters, with the class forms of DESIGN 4.6:
elemental melee `special` -> `class="add_attack" damagepercent=P(rank) damagetype` (+ `special_fx custom`,
`powerup_scope punch/kick`; P = min(2.6, 0.5 + 0.35*(rank-1)), Q6), `reflect_damage user1=C` -> `powerup
chance=C/100`, bleed `none/damageaddbleed` -> `class="add_harming" damagepercent=0.2 life=user1`,
`might_mode_mod` -> `might_heaviness` + `might_structure`, `<scope>` children folded into the affecter or a
`powerup_scope` affecter. Affecter `level`s are XML1's numbers (a damage range's mean for a single-number
attribute). Attributes in XMen2.exe's affecter table that no XML2 retail style uses (`damageLevel`, `atk_knockback`)
are emitted as DESIGN says and warned as UNVERIFIED; `atk_damage_scale` is not in the table (it would parse as `none`)
and is rewritten to scale `atk_damage` before conversion (SPEC 22). <= 8 talents per file (cap 100).

**Xtreme ranks (deviation, section 8):** an XML1 xtreme talent has 1 level, but its FightMove chain has 6 rungs
gated on the character level (`XTL2..6` = 20/25/30/35/40 or the `XLT` typos). The talent gets ranks 2..6 whose
`<level>` requires that character level (XML2's own xtremes have 7 ranks in the same form), so the XML1 scaling
survives as talent ranks; rank 1 keeps XML1's `cost="2"` / level 15 unlock. This also covers the XTL sub-chains
(Rogue `xtreme_contact`, Wolverine `xtreme_frenzy_dash`).

Per-hero file sizes (talents): Beast 5, Colossus 6, Cyclops 6, Frost 7, Gambit 7, Iceman 8, Jubilee 7, Magma 7,
Nightcrawler 6, Phoenix 6, ProfXAstral 6, Psylocke 6, Rogue 5, Storm 5, Wolverine 7 (= DESIGN 6.2).

---------------------------------------------------------------------------------------------------------------

## 5. Powerstyle collapse (DESIGN 4.3-4.5; `StyleCollapse`)

Input: the XML1 style read again from `xml1_loose` (`ctx.x1_schema` applied), not characters' output. x1schema's
combat rewrite (SPEC 22) runs before the collapse: the style events built on XML1's `blast_ranged` point at XML2's
`blast` (+ `dmgmod_popup`; Magma's Lava Fissure `lava_rift` and the blast events of the Beast, Gambit, Jubilee, Magma,
Psylocke and Storm Xtremes, which XMen2.exe dropped before), `charged_throw`'s `ch_throw` is XML2's `ch_pickup_throw`,
Jubilee's taunt `atk_damage_scale` is scale `atk_damage`. Counts `combat_*`, per hero `combat_rewrites`.

Classification: a **rung** has `inherit` naming another move of the style and either a skill/talent `<require>`
with level > 1, a `cat="level" level="XTLk|XLTk"` require, or one of the names `power_attack/power_smash/
power_boost/power_xtreme`. Following `inherit` gives the **root**; a rung's rank is its require level (XTLk -> k),
the root is rank 1 (Colossus rungs inherit the root directly, so rank values are resolved through the inherit
chain, not carried from the previous rung). The chain's **gate** is the root's skill require, else the rungs',
else (XTL chains) the hero's xtreme talent. Output names: a **power root** (gate is a talent with XML1 power index
0..3 and the root itself carries the gate at level 1, or - Gambit `card_throw1` / Phoenix `telekinesis_start1` -
no gate but the power's `icon`) -> `power1/2/3/9`; any other chain -> the **top rung's name** (`skating`,
`chargeforward`, `time_bomb`, `xtreme_contact`, `xtreme_frenzy_dash`; the root name only when the top is one of the
four XML1 top names); a move named `power_attack` that inherits nothing (Gambit / Jubilee / Nightcrawler decide
moves, handlers registered) -> `<hero>_decide` (XML2's own `gambit_decide` form). Two chains on one power slot
(Rogue: `ability_drain_decide1..10+power_smash` with the unregistered `ch_roguedecide` vs `ability_drain1..10+
ability_drain`) keep the registered one; the dropped chain's `powerusage` trigger is transplanted per rank (tag
90). Every `inherit=` / `<chain result>` naming a rung is remapped; a dangling reference is an error.

Folding (`_collapse`): output = root effective move renamed; for each trigger tag and attribute the per-rank
values are compared: constant -> literal; numeric (after value-code resolution) -> `%<code>_<talent>_<short>`
(`<code>` = `x` + two hero letters, e.g. `xcy_beam_dmg`, `xwo_frenzy_dmg_t1`; the talent part drops a leading token
the hero name starts with; `_t<tag>` when several triggers of the move vary in that attribute; **<= 19 chars**, talent
part truncated: XMen2.exe refuses 20+ char names at 0x4c188c and a '%name' it cannot resolve parses as 0 -
research/heroes/powers_debug.md) with one
`talentvalue` per rank (gaps carried forward); `pierce="true"` from rank k -> `piercechance` 0/1; a trigger added by
a rung -> added, `life` 0 below its first rank (an attack trigger without `life` is active from rank 1 and reported
`UNGATED`); a `powerup` trigger whose kind changes with the rank (Frost / Jubilee `confused` -> `team_switch` at
rank 6) -> one life-gated trigger per kind; a `victimeventtag` that changes (Iceman chill 10 -> frozen 20) ->
`victimeventtag1..n`; any other non-numeric change (`apply_ally near/all`, `aitype`, projectile `entity`) -> the
top rung's value (`enum_top_rung`). A `%` reference on an attribute outside XML2's vocabulary (`VALUE_REF_ATTRS`:
every (tag, attribute) XML2 retail references through talentvalues - e.g. not `damagelevel`, `fxlevel`, `radius`,
`arc`) falls back to the top rung's literal (`nonref_top_rung`). FightMove attributes follow the same rule
(`playspeed` may be a reference). Chains = the top rung's set; requires = the root's (a gate is inserted when the
root had none). `<damageMod>` children a rung adds are active from rank 1 (reported). Xtreme talents: see 4.

Fixups on every output move (`fixup_move`): value codes anywhere (L/M/H damage ranges as `"min max"`, K/P/BST/A/
XTL numbers, `XLT` typos -> XTL) resolved from `xml1_loose/data/values.xml`; `<require cat="talent">` -> `skill`;
`func_*`, `fallback`, `life_max`, `level_max` dropped; root attributes `iconcolumns/iconrows/exclusive` dropped;
`icon` kept only on `power1/2/3/9`; `C.map_tree_refs` (skins 1805 -> 15805, `skin_swap` kept). Powerup triggers
(`convert_powerup_trigger`): `<trigger name="powerup" ...><special_fx/><affecter/></trigger>` with XML2's retail
forms where XML2 has one: elemental `special`/`damage+damageaddattack` -> `class="add_attack" damagepercent=0.5`,
Gambit/Jubilee `time_bomb` -> `class="time_bomb" explosion_damage/knockback/radius`, `charged_throw` ->
`class="charged" life=99`, `drain_victim` -> `class="rogue_drained"`, `stun_lock` -> `shared_tag="shared_stunned"`,
bleed -> `shared_tag="shared_bleed"`, frozen `move` -> `class="freeze" renderfx="chilled"` + `affecter frozen`,
chilled `move` -> `class="chill"` + `affecter move`, `might_mode` -> `might_heaviness`+`might_structure`,
`def_damage` with `damagetype` -> `scope_damage`, everything else -> `<affecter attribute=X [affect_type] level
[scope_*]>` (unknown attributes warned). `effect` -> `special_fx primary`, `effect_cust1` -> `deactivate` (with
`customeffect1deactivate`) / `custom`.

Results per hero (moves in -> out): Beast 41 -> 8, Colossus 45 -> 8, Cyclops 37 -> 4, Frost 37 -> 4, Gambit 51 -> 14,
Iceman 45 -> 8, Jubilee 46 -> 9, Magma 44 -> 7, Nightcrawler 51 -> 18, Phoenix 39 -> 6, ProfXAstral 15 -> 15,
Psylocke 37 -> 4, Rogue 52 -> 8 (decide chain dropped), Storm 37 -> 4, Wolverine 43 -> 10; 67 chains collapsed,
549 XML1 moves mapped, 60 kept, 11 dropped, 274 talentvalues (default build).

---------------------------------------------------------------------------------------------------------------

## 6. Packages, heads, npcstat, shared_talents (DESIGN 4.7-4.10)

**Packages** (`_packages`): for every costume skin the XML1 bundle `<hero>_<skin4>[_nc].fb` through
`C.map_package_entry` + existence (missing entries dropped with a warning), plus `actorskin`/`actoranimdb` of the
entry, `texture textures/ui/<hero>_all`, `xml_talents data/talents/<hero>` (both packages, R9), BoltOn models /
anims, and in the combat package the FlyEffect effects, every effect the collapsed style names that the bundle
lacked (imported), and `fightstyle data/powerstyles/<mapped>`; `_nc` packages carry no styles / effects (XML2
form). Every `fightstyle` entry is moved to the end of the package (`_styles_last`, XML2 retail order): the exe loads
entries in document order and resolves a FightMove's skill `<require>` and `%talentvalue` references while parsing
the style, so `xml_talents` must come first (the XML1 bundles list the style first; research/heroes/powers_debug.md).
A costume without a bundle (none today) is synthesized from the default costume's. `<hero>_xml` =
`[xml_talents, xml data/entities/* of the bundle, fightstyle]`. Character package names are 5-digit and never
collide with XML2's (error otherwise); `<hero>_xml` replaces XML2's same-name package where one exists.

**Heads**: `characters_heads.PKGB` = `ui/models/characters/<prefix>01` for every hero whose head exists in
`<out>` (15: ProfXAstral resolves to 15101, see 8), then `ui/models/characters/9999`, `ui/models/m_team_roster_
screen`; `_pc` = `[ui/models/characters/9999]`.

**npcstat**: the entries whose lowercase name is in the new herostat are removed (Beast, Frost, Jubilee, Magma,
ProfXAstral, Psylocke - a name registers once, 0x44c3c9 - and ProfXGladiator, section 3.1); `<talent>` children
naming a dropped shared talent are removed (94 references; the `profx_*` live only in ProfXAstral's file - an NPC
cannot reach a per-hero file).

**shared_talents** (`shared_keep`, rule-based): a current shared talent is kept when it is a `fightstyle_*` named
by a stats entry or a style `<require>`; named by a `<require cat="skill|talent">` of a powerstyle / fightstyle the
final stats use and not defined in a hero file; an XML2 definition referenced by a stats entry; a plain reference
of an XML1 hero (incl. the engine special names `flight`, `ice_skating`, `night_faith`, E13); one of
`toughness`, `mutantmastery`, `acrobatics`, which get XML1's real definitions; characters' NPC energy talent
`x1_npc_energy` while a stats entry names it (SPEC 24.3); or one of characters' XML1 NPC immunity talents (SPEC 30:
a non-XML2 definition in the immunity form, `npc_values.is_immunity_talent`) while a stats entry names it.
Everything else is dropped: XML2's unreferenced `fightstyle_staff`, `mutantmaster`, `block`, `grab`,
`psionic_fury`, `knock_resist`, `corrupt_vampire`, `deadpool_regen`, `blimpyboy`, `monst_dmg_low`, the 5 `profx_*`,
and the remaining empty NPC definitions (`jug_xtreme`, `pyro_shield`, `shade_spawn`, the `profx_*`). Result 88 ->
**46** (DESIGN listed 47 with `grab`; a delta is a warning naming it), 89 -> **47** with `x1_npc_energy` (SPEC 24),
**61** with the 14 immunity talents (SPEC 30; DESIGN D8 / 4.7 dropped them as "empty `*_special` definitions" -
the emptiness was characters' own `ensure_talent` stub, the real bodies were inline in XML1's npcstat).
Registered talents worst party = 61 + 8 + 7 + 7 + 7 = **90** of 100 (+8 danger room margin = 98 <= 100; the
validator's limit is 92 before the margin).

---------------------------------------------------------------------------------------------------------------

## 7. Scripts (T7, T13) and validators

`scripts_transform.join_hero(lines, bit)`: the research's `addHero` emulation (`unlockCharacter("h","") x2 +
extractionPointLite("_ACTIVE_HERO_", ...)`) becomes `unlockCharacter` once, the join comment, `remove("h","h")`
(the NPC double), `setGameFlag("x1join", bit, 1)`, `extractionPointChange("_ACTIVE_HERO_", 0)`; following
`waittimed` / `createPopupDialogXml` lines move before the block, each popup followed by `waittimed ( 0.500 )` (SPEC
19.7: the wait runs out only once the player has closed the popup, so the team menu / reload never has it pending; a
popup pending under the team menu broke the menu in game). `join_hero_zone_guard(lines, bit)`: after the leading
`setCurrentAct`, `x1j = getGameFlag("x1join", bit)` / `if x1j == 1` / `remove(trigger_touch03)` /
`remove(sp_cyclops01)` / `remove(cyclops_x1double)` / `endif`, and at the end of the zone script the late removes of
the double (`if x1j == 1` / `waittimed` / `remove(cyclops_x1double)` x 10 / `endif`: the spawner's instant spawn comes
after the guard's removes). `join_hero_mission_reset(lines, bits)`: `setGameFlag("x1join", bit, 0)` after
every `# ( "XML1 beginMission(m)" )` marker of `alison` (1) / `dr_mag2` (2). `scripts._script_text` applies them
(`JOIN_HERO_SCRIPTS`: `nyc/alison/add_cyclops` 1, `mansion/dr_mag2/blob/add_cyclops` 2; `JOIN_HERO_ZONE_SCRIPTS`:
`nyc/alison/nyc1_1_3`, `x1/zones/mansion/dr_mag2/mag_nyc4`; every script gets the marker reset), so the New Game
hook (a copy of begin_alison) clears bit 1 too. `x1join` counts toward the 96 free game-flag names (`_global_checks`).
`scripts_lint.roster_problems` (T13, run per installed script): error on `loadMapAddTeam`; error on an
`extractionPointLite("_ACTIVE_HERO_", ...)` not preceded by `setGameFlag("danv", 1, 1)`. `scripts_transform.selftest`
covers the three transforms.

In `--forced-teams seat` builds (the default, SPEC 19) `join_hero(lines, bit, add_hero=True)` emits `unlockCharacter`,
then the join bit (set before the branch, so a later reload still re-arms the zone guard), then
xml2-fix `x1ah = addHero("cyclops" )` and `remove(join_double)` inside `if x1ah == 1` (`x1ah` from
`xml2fixFeature("addhero")`: `[Game] AddHero=1`, experimental, default off), then - when that left `x1ah` 0 and
`xml2fixFeature("joinhero")` is on (`[Game] JoinHero`, on with ForcedTeams=1) - `remove(join_double)` and
`x1ah = joinHero("cyclops" )` (xml2-fix 0c82a6e: the spot saved, the hero added to the saved party, the zone reloaded
there, no team menu; SPEC 19.7), then the T7 block (comment, remove, `extractionPointChange`) inside `if x1ah == 0` -
the path with both off, without the DLL, or when both return 0. `--forced-teams menu` builds keep the T7 block alone
(with the popup and its wait before it too).

`heroes.validate_out` (`_build/heroes_validate.json`; `python -m xml1build.heroes check <out>` runs the same
without ctx.shared):

| id | check | severity |
|---|---|---|
| V-H1 | herostat: entry count and order == `hero_plan`, unique names <= 18 chars, skin 4-5 digits prefix <= 255 with its actor, characteranims actor, autospend class exists, the 15 heroes have `team="hero"`, `playable="true"`, `power1..4`, `textureicon`, an existing powerstyle, <= 19 talents; placeholders have no `team` / `playable` | error |
| V-H2 | no herostat name in npcstat; herostat + npcstat unique names <= 296 | error |
| V-H3 | per hero both talent files exist and agree, <= 8 talents, every `power=` names a FightMove of the style, every skill `<require>` resolves (file or shared), every `%name` in the file or style has a talentvalue with contiguous ranks from 1, talentvalue names <= 19 and defined by one file only (shared + hero files; <= 300 names in total), no talent name registered twice across shared + files | error |
| V-H4 | shared_talents XMLB == engb, <= 99, == DESIGN 4.7 (delta = warning), special names defined where a hero references them, shared + worst 4 files <= 92 | error / warn |
| V-H5 | per style: `power1/2/3/9` exist and require their talent, no XML1 top name / `fallback`, every `inherit` resolves, no chain to a dropped rung, no value code left, `%` only on `VALUE_REF_ATTRS`; every `<event>` / `<trigger>` resolves to a registered `ce_*` type, <= 19 triggers per move, names <= 31 (`combat_events.style_findings`, SPEC 22); every affecter in XMen2.exe's affecter table (error); handlers not in `FM_HANDLERS` and affecters no XML2 retail style uses are warnings | error / warn |
| V-H6 | per costume: `<hero>_<skin>` and `_nc` exist with `actorskin`, `actoranimdb`, `xml_talents data/talents/<hero>`, the combat one with the mapped `fightstyle`; no `xml_talents` / `xml` entry after the first `fightstyle`; every entry resolves; `<hero>_xml` and the placeholder packages exist | error |
| V-H7 | `characters_heads` lists every existing hero head + 9999 + `m_team_roster_screen`, every listed model exists; `_pc` lists exactly 9999 | error |
| V-H8 | per costume a HUD head (costume / default / variant 01 fallback) exists (error); `UI/HUD/characters/<skin>` missing -> note when a fallback exists, warning otherwise; loading textures noted | error / warn / note |
| V-H9 | actor slots per converted zone with the party Iceman, Nightcrawler, Magma, Gambit (`actor_budget.zone_report` with a `Budget` whose `party()` is that roster): > 37 error, > 35 warning | error / warn |
| V-H10 | `--newgame keepteam` refused; a `loadMapKeepTeam` New Game hook (start-zone / tour) needs `magneto`, `cyclops`, `wolverine`, `storm` in herostat; the default hook must load with `loadMapChooseTeam` | error |
| V-H11 | `ctx.shared['stats']` agrees with `<out>` herostat (names, file, origin) | warn |
| V-H12 | T7: both add_cyclops scripts carry the join pattern and no `extractionPointLite`; both zone guards exist | error |
| V-H13 | unlock points (`scripts.MISSION_START_UNLOCKS`: Jubilee at mansion2, Colossus at mansion4, Psylocke at mansion7): each hero is a playable herostat hero; every copy of those begin bodies in `<out>` (`x1/missions/begin_<m>` + the inlined copies: haarp `nextmission`, muir2 `endmuir2`, `beginmansion7mission`) unlocks it exactly once in its header (`scripts_transform.unlock_problems`) | error |

`tools/xml1build/heroes_selftest.py <out>` (HA-HK, DESIGN 5.3): XMLB round trip of every heroes-owned file; V-H1..
V-H13 recomputed; every talentvalue at rank r equals the XML1 rung r's resolved value (an independent walk of the
XML1 inherit chains: 2329 values); every XML1 move collapsed / kept / dropped; descriptions clean; `hero_plan` on a
fresh context predicts order and bases; npcstat removals (7) and dropped references; 102 packages; shared keep list
(delta `grab` documented); budgets; the base files heroes replaced.

Other validate.py changes (the two DESIGN 5.4 relaxations plus two the build needed): V2 no longer warns about a
heroes-owned herostat and counts characters -> heroes ownership changes as `heroes_overrides`; V5 accepts 1..21
heroes for `--hero-roster 17`; V5 notes (instead of erroring) XML2 hero names the exe references only in its
unlock / default-team lists (bishop, deadpool, ... - no-ops for an unknown name, engine.md 2.2) when heroes owns
the herostat. `characters_selftest` K compares the npcstat part of the plan when heroes owns the herostat and
accepts heroes-owned `<hero>_xml` packages.

---------------------------------------------------------------------------------------------------------------

## 8. Deviations from DESIGN.md (each with the reason)

1. **Xtreme talents get 6 ranks** (DESIGN 4.4 rule 6 called a rung/level mismatch "an error to be resolved by
   hand"): XML1 gates the xtreme rungs on the character level (XTL2..6), which talentvalues cannot express; ranks
   2..6 requiring character levels 20/25/30/35/40 keep the XML1 numbers and follow XML2's own multi-rank xtremes.
2. **Collapsed non-power chains keep the top rung's name** (DESIGN 4.3: "keeps the root's name"): other moves chain
   to the top name (`jump -> skating` / `chargeforward`, `gambit_decide -> time_bomb`, `power9 -> xtreme_frenzy_dash`).
   Every reference is remapped either way; keeping the referenced name is the safer choice against any engine-side
   name use. Decide moves become `<hero>_decide` (XML2's `gambit_decide`), not a kept `power_attack`.
3. **Retail powerup forms instead of plain affecters** for `drain_victim` (`class="rogue_drained"`), `stun_lock`
   (`shared_tag="shared_stunned"`), the chill / freeze / time_bomb / charged classes and the bleed `shared_tag`: XML2
   ships exactly these forms for the same powers (ps_rogue power2, ps_iceman power1/2, ps_gambit power6_atk /
   charged_throw); an affecter named `drain_victim` is UNVERIFIED. `nullify` is an affecter as XML2 does it.
4. **Rank-dependent powerup kinds are split into life-gated triggers** and **rank-dependent `victimeventtag`s
   become `victimeventtag1..n`** (both XML2 forms) instead of the top-rung enum; DESIGN's top-rung rule would have
   made Frost / Jubilee convert enemies at rank 1 and Iceman's beam freeze at rank 1.
5. **Rogue's power2 gets the decide chain's `powerusage`** (transplanted per rank, tag 90): the drain move itself
   carried no energy cost in XML1 (the decide did).
6. **shared_talents keep list is 46, not 47**: `grab` is referenced by nothing in the built data once XML2's heroes
   are gone (XML2's fightstyle grab moves are not talent-gated); the rule drops it, the DESIGN comparison warns.
7. **characters_heads lists 15 heads** (16 heroes: ProfXGladiator shares 15101), including
   `ui/models/characters/15101` for ProfXAstral (skin 15104):
   FUN_005f4ec0's third candidate is variant 01 of the prefix, and XML1's own `characters_heads.fb` listed 1101.
8. **validate.py got two more edits than DESIGN 5.4 listed** (V2 `heroes_overrides`, V5 exe-referenced XML2 hero
   names) - without them every build has 64 V2 warnings and 10 V5 errors.
9. **`--only characters` implies heroes** (heroes patches characters' outputs; SPEC 2 `--only` semantics extended).
10. `UI/HUD/characters/<costume>` missing on the XML1 disc is a note when the engine's fallback candidates exist
    (DESIGN: warning) - 10 costumes are affected in every build.
11. Affecter attribute values keep XML1's spelling (`damageLevel`): the exe has that string.
12. **ProfXGladiator is a herostat hero** (DESIGN D12 kept him npcstat, astral_sk deferred): section 3.1, in the last
    pad slot; his talents are renamed `pxg_*` and his style's power moves gated (an npcstat style has no gates).

Fidelity losses recorded per hero in `heroes_detail.json` (`enum_top_rung`, `nonref_top_rung`, `added_triggers`,
`losses`): destruction `damagelevel` and effect `fxlevel` at the top rung from rank 1 (not %-referenceable);
`apply_ally near -> all`, `aitype buffself -> buff`, projectile `entity` (ice_shard -> ice_spike, lava_ball1 -> 3,
storm_lightning1 -> 10, psybolt -> psyspikelegend) at the top rung; `damageMod`s a rung adds active from rank 1;
Frost fear's `fry` damage event active from rank 1 (no life to gate it); elemental melee as XML2's percentage
curve; `user1/user2` of powerups dropped; `add_attack` boosts at a fixed 0.5.

---------------------------------------------------------------------------------------------------------------

## 9. Deferred (DESIGN D15) and in-game checklist

Deferred to v2: Rogue's decide step (`ch_roguedecide` is not registered, E14; the decide chain is dropped; Gambit /
Jubilee `charged_throw` got XML2's `ch_pickup_throw`, SPEC 22); astral solo mode (T10) (flashback
party save / restore, T9, is built by SPEC 19: xml2-fix `pushParty` / `popParty`, and without the DLL the return
opens the team menu at the caller zone, T9's simplest variant); XML1 Danger Room courses; XML1 team
bonuses; talent icon re-atlassing (`--hero-icons generic` is the fallback); Psylocke blades 2/3 (BoltOn `<require>`
UNVERIFIED); NPC damage vs XML1 hero stats; `--newgame keepteam` (option C proxy patch).

In-game checks, in order (DESIGN 7.2, trimmed to what the build needs; `build/_heroes` = `--no-movies` full build):

1. Launch to the main menu (boot crash = a herostat attribute problem, > 19 talents, or a missing autospend class).
2. New Game -> Normal: the team menu opens before nyc1_1_1; it lists XML1 heads for the 15 heroes only (no
   Defaultman / x1pad entry); note which are unlocked (Wolverine, Cyclops, Storm + up to 6 more settles byte
   [0x6f3c2d]). A placeholder listed -> E4's "no team hides the entry" is wrong: fall back to `build/_heroes17`.
3. Confirm with Wolverine alone: nyc1_1_1 loads with XML1 Wolverine (claw bolt-ons, XML1 idle), HUD head 14301.
4. Fight, open the skills screen: 4 powers + passives listed, `wolv_slash` rank 1 buyable, the 2x2 icons whole
   (quartered / wrong -> `build/_heroes_generic`).
5. Use power1..3 and the xtreme (cheat levels): XML1 animations / effects, numbers change with rank.
6. Cyclops beam at rank 6+: piercing (piercechance UNVERIFIED -> literal `pierce="true"` fallback).
7. Level up 3-4 times: autospend, no crash on the level-up notify.
8. nyc1_1_3: touch the trigger -> the tut15 popup; close it -> (seat build, JoinHero on) no team menu: the zone
   reloads at the same spot with Wolverine + Cyclops, NPC Cyclops and trigger gone (joinHero verified 2026-09-28
   night). With `JoinHero=0` the T7 team menu opens after the popup is closed (no popup under it). Every later load
   of the zone: Cyclops spawns (slot-2 start enabled), the double is removed within about a second (SPEC 19.7).
9. Rogue power2 on a target: the drain plays (no per-victim decision); energy is spent.
10. Blackbird / X-traction at haarp: pick Iceman, Nightcrawler, Magma, Gambit; all four idle-animate (36 slots at
    haarp2_6 is the heaviest zone).
11. Magma power3 (skin swap 15805, `skin_swap` UNVERIFIED), Iceman armor bolt-ons, Frost confuse at rank 1 (no
    conversion) and rank 6 (conversion).
12. Costume: `unlockCharacter('', '60s')` then the costume option: Cyclops 14102 + hud_head_14102.
13. Save, quit, load: party / levels / talents restored (saves are positional by stats index, R25).
14. astral1 team menu offers ProfXAstral (D12).
14a. Unlock points (V-H13): after the mansion2 start Jubilee is in the next team menu, after mansion4 Colossus, after
    mansion7 Psylocke (heads, XML1 skins).
14b. ProfXGladiator (3.1): boot (21 entries, index 21 is a hero now); `runscript x1/missions/begin_astral_sk` with
    ForcedTeams=1 -> final_astral with the Astral Gladiator alone (skin 15105, HUD head 15101), four powers in the
    wheel (pxg talents), fight Shadow King; the real flow (xcrystal_destroyed push -> shadowking_defeated pop)
    returns to the crystal spot with the astral3 party. A save from before this change: his level after loading.
15. `build/_heroes17`: steps 1-3 (fewer than 21 heroes, UNVERIFIED #12).
16. `--tour 12` regression on a rebuilt tour build (party = testguy placeholder + XML1 Cyclops/Wolverine/Storm).

Known pre-existing failure, not from this module: `regress_nyc1.py` check "zone package covers all 88 proven
entries" fails since SPEC section 16 renamed `mission_alison` to `zone_nyc1_1_1` (also on `build/xml1_full`).
