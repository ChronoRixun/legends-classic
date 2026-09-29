# XML1 hero roster on XMen2.exe: data inventory and contract diff (Topic A)

Written 2026-09-27. Companion data: `research/heroes/inventory.json` (per-hero records, engine facts, vocabularies).
Scope: READ-ONLY survey of what XML1's 16 herostat entries contain, what XMen2.exe's hero contract requires, what the
pipeline (`tools/xml1build`) already emits for them, and what is missing. No files outside `research/heroes/` were touched.

Evidence conventions: `verified` = read in the disassembly (`tools/disasm.py`), the Ghidra decompiles under
`research/characters/ghidra/`, an exe string scan, or the data itself. `UNVERIFIED` = plausible but not traced.
`characters.md` = `research/_summaries/characters.md` (its VERIFICATION section wins).

---------------------------------------------------------------------------------------------------------------

## 0. Headline numbers

| item | value | source |
|---|---|---|
| XML1 herostat entries | 16 = `default` + 15 heroes (Beast, Colossus, Cyclops, Frost, Gambit, Iceman, Jubilee, Magma, Nightcrawler, Phoenix, ProfXAstral, Psylocke, Rogue, Storm, Wolverine) | `xml1_loose/data/herostat.eng` |
| XML2 herostat entries | exactly 21 (default, Bishop, Colossus, Cyclops, Deadpool, Gambit, Iceman, Ironman, Juggernaut, Magneto, Nightcrawler, Phoenix, Professorx, Rogue, ScarletWitch, Storm, Sunfire, Toad, Wolverine, Pyro_hero, sabretooth_hero); mapping loop `cmp esi,0x15` at 0x44bb13 | decoded `Data/herostat.engb`; disasm |
| Name overlap XML1 herostat vs XML2 herostat (case-insensitive) | 10: default, Colossus, Cyclops, Gambit, Iceman, Nightcrawler, Phoenix, Rogue, Storm, Wolverine | data |
| XML1 heroes with no XML2 hero of the same name | 6: Beast, Frost, Jubilee, Magma, ProfXAstral, Psylocke (all six are today emitted into npcstat as "heroes used as NPCs", SPEC 5.1/12.2) | `build/xml1_tour/Data/npcstat.engb` |
| Talent children in XML1 herostat | 170 total; 85 inline definitions (power trees + passives, 568 `<level>`), 85 plain references | data |
| `activepowerup` elements in XML1 herostat | 94, **all** nested under `Talent/level` (never a direct child of `<stats>`) | data |
| XML1 hero powerstyles | 15 files, 37-52 FightMoves each (ProfXAstral 15) vs XML2 8-33 per hero | data |
| Stats-name budget after conversion | tour build today: 234/296 (21 XML2 heroes + 213 npcstat). With 16 XML1 heroes and the 6 hero-as-NPC entries removed from npcstat: 16 + 207 = 223 (228 if herostat is padded to 21) | `characters.py` counts, `build/xml1_tour` |
| Shared talents | XML2 34; tour build 88/99; hero conversion needs +5 more names if kept shared (accuracy, grappling, healing_factor, knockback, pointblank) = 93/99, or 0 if they go into per-hero files | section 2.5 |

---------------------------------------------------------------------------------------------------------------

## 1. herostat attribute and child contract

### 1.1 What XMen2.exe reads from a `<stats>` entry (herostat parser FUN_004b9c40, `ghidra/decomp3.c`; loader FUN_0044c030, `decomp1.c`)

Verified attribute handling relevant to heroes:

- `power1`..`power4`: each accepted by `_stricmp` at 0x4ba0ad/0x4ba0d9/0x4ba105/0x4ba131 and stored by `FUN_004b7f30`
  (`strncpy(dst, value, 0x14); dst[0x13]=0`) into four 0x15-byte slots at obj+0xc4, +0xd9, +0xee, +0x103. They are
  **FightMove names** (every XML2 hero: `power1="power1" ... power4="power9"`). The same slots are also written by UI code
  with literal names: 0x533bee-0x533c3d pushes `"power8","power2","power1","power9"` for slots 0..3 through
  `FUN_004b84b0(slot, name)` (slot < 4 -> obj+0xc4+0x15*slot). **Consequence: the engine addresses powers by FightMove
  name and its own code paths assume the names `powerN`.** (Which menu the 0x533bee case belongs to: UNVERIFIED.)
- `autospend`: accepted (decomp3.c line 910, vt+0x90 call); classes come from `Data/autospend.XMLB`: `bruiser`,
  `bruiser_light`, `support`, `support_heavy` (start stats + per-level bonus rates). XML1 has no equivalent; XML1's
  `RatingMelee/Ranged/Support/Durability` (16 heroes) are **not handled** (`schema_stats.txt handled=NO`) and are the only
  hint for choosing a class.
- `textureicon`: accepted by the parser (line 885) and, separately, read by the stats **loader** at 0x44c329-0x44c347:
  `atoi(value)` -> `word [entry+0x16]` of the 0x1c-byte name-table record; `playable` -> bit 2 of `[entry+0x18]`
  (0x44c2f6-0x44c326). XML2 uses indices 0..40 (sparse). Which atlas the index addresses is UNVERIFIED (no
  `textures/ui/%s` format string exists; the team menu has `roster_portrait01..03` items, string 0x6a2f?? region).
- `skin`: 4-5 digits, prefix byte at +0x254, variant at +0x255 (0x4b9dbc); `skin_<costume>` only for the 8 names in the
  table at 0x6d8aa0 (astonishing, aoa, 60s, 70s, weaponx, future, winter, civilian) -> XML1's `skin_magmacivilian`
  (Magma) has no slot (characters.md, confirmed).
- `leaderskin`/`mutantskin`/`mutatechance`/`leadername`/`leaderpowerup`/`specific_*`/`skirmish_boost`/`deathnode`/
  `xpaward`/`xpexempt`/`willflee`/`teleportpathfail`/`attackrange`/`counter`: all parsed (decomp3.c). None of the
  `specific_*`/`leader*`/`mutant*` attributes appear in XML2's **herostat** (they are npcstat-only); a hero entry does not
  need them.
- Not handled at all (schema_stats.txt): `leader`, `rating*`, `throwally`. `weapon` is parsed and ignored.

### 1.2 Per-attribute diff, XML1 herostat -> XML2 herostat

Attributes used by the 16 XML1 hero entries (count of entries): name 16, charactername 16, skin 16, level 16,
strength/speed/body/mind 16, ratingmelee/ranged/support/durability 16, characteranims 16, sounddir 15, powerstyle 15,
team 15, playable 15, scriptlevel 14, ailevel 11, skin_future 10, moveset1 6, skin_60s 5, skin_70s 5, canseestealthed 4,
canthrowally 3, skin_civilian 2, heaviness 1 (Colossus), scale_factor 1, ignoreboundsscaling 1 (Colossus),
skin_magmacivilian 1 (Magma), xpexempt 1 (ProfXAstral), canfly 1 (Storm), skin_weaponx 1, canbeallythrown 1 (Wolverine).

| class | attributes | action |
|---|---|---|
| 1:1 with XML2 herostat (same name, same meaning) | name, charactername, skin, skin_60s/70s/future/weaponx/civilian, level, strength, speed, body, mind, characteranims, sounddir, powerstyle, moveset1, team, playable, scriptlevel, ailevel, canseestealthed, canthrowally, canbeallythrown, scale_factor, ignoreboundsscaling | copy (lowercase, sorted) |
| parsed by the exe, present in XML2 npcstat only | heaviness (Colossus), canfly (Storm), xpexempt (ProfXAstral) | copy; harmless |
| XML1-only, ignored by the exe | ratingmelee, ratingranged, ratingsupport, ratingdurability (all 16) | drop (use to pick `autospend`) |
| costume without an XML2 slot | skin_magmacivilian="03" (Magma, actor 1803 exists) | remap to `skin_civilian` (slot 8, unused by Magma) or drop |
| XML2 herostat attributes XML1 lacks (**every** XML1 hero) | `autospend`, `power1..power4`, `textureicon` | generate: power1-3 = the three power FightMoves, power4 = the xtreme (`power9`), textureicon = new index, autospend from stats |
| also missing on specific entries | `default`: playable, scriptlevel, team (XML2's default lacks them too - keep XML2's `default`); ProfXAstral: scriptlevel (and `playable="false"`) | see readiness |

Children: XML1 uses `Race` (16, always `Mutant` only), `Talent` (170), `FlyEffect` (8: Phoenix 3, Rogue 2, Storm 3),
`BoltOn` (6: Nightcrawler tail 1, Psylocke blades 3, Wolverine claws 2). XML2 herostat children: Race (always 2:
Mutant + XMen|Brotherhood; team_bonus.engb keys bonuses by `<hero name>` not race, so the second Race is optional),
talent, BoltOn (+`menuonly` attr), Multipart (+`nonmenuonly`), FlyEffect. XML1-only children that XML2's herostat never
has: inline talent bodies (`Talent/level/require`, `Talent/level/activepowerup`), and `<scope>` (5, all inside
activepowerups: Gambit `gambit_staff` x5). Psylocke's 2nd/3rd BoltOn carry `<require cat="skill" item="blademaster">`;
whether XMen2.exe's BoltOn parser (0x44a868) honours a `<require>` child is UNVERIFIED (no XML2 data does it); the
pipeline currently drops such BoltOns ("talent-gated upgrade").

Tag/attribute case: XML1 uses `Talent`, `RatingMelee`, `canSeeStealthed`, `Race`, `BoltOn`; XMLB attribute keys must be
lowercase and sorted (HANDOFF), tags keep XML2 spelling (`talent` lowercase in XML2 herostat, `Race`/`BoltOn`/`FlyEffect`
capitalised as in XML2).

---------------------------------------------------------------------------------------------------------------

## 2. Talent trees -> `data/talents/<hero>.xmlb`

### 2.1 How XML2 loads talents (verified)

- `data/shared_talents.xmlb`: ids 0..98 (`0x4c05d0` pushes 0x63 to FUN_004c0460; talents past the cap are dropped).
- `data/talents/%s.xmlb` (pointer 0x6d990c -> string 0x68ea28): FUN_004c05f0 loads it with ids `base..base+100`
  (`decomp13.c`), i.e. **100 talents per hero file**; the file registry refuses a 10th file (`+0x358 != 9`,
  FUN_004c0460) - a "loaded at once" limit, not a shipping limit (XML2 ships 21 files). The file is pulled in through the
  character package entry `<xml_talents filename="data/talents/cyclops"/>` (retail `cyclops_0103.PKGB` and
  `cyclops_xml.PKGB`; string `xml_talents` in the exe; 0x4c05f0 has no direct caller so it is reached virtually -
  package path inferred, not traced).
- Talent parser FUN_004be1f0 (`decomp12.c`): reads `fightstyle`, `power` (string, 0x14 chars, at talent+0xc), `hidden`,
  `value_priority`, `type` (via table at 0x6d9910: `xtreme`, ...; XML2 uses `boost`/`xtreme`), `skirmish_locked`, and
  sums `<level count=N>` (a level without `count` counts 1). Strings `descname`, `description`, `descshort`, `icon`,
  `icon_texture`, `talentvalues`, `talentvalue`, `cost`, `degree`, `count` all exist in the exe (parser use of `cost`/
  `degree` on `<level>`/`<require>`: UNVERIFIED but they are XML1-era names still present).
- Requirement categories (characters.md, FUN_004ac470): trait/level/counter/xtreme/race/character are built-ins;
  anything else - including XML1's `cat="talent"` and XML2's `cat="skill"` (the literal string `skill` does not exist in
  the exe) - means "look the named talent up". So XML1 `<require cat="talent" item="X" level="N"/>` works unchanged.

### 2.2 Exact XML2 schema (from `talents/cyclops.engb`, `professorx.engb`, `wolverine.engb`, `storm.engb`, all 21 read)

```
<talents>
  <talent descname="<power name>" description="..." descshort="Beam" icon="0"
          icon_texture="textures/ui/cyclops_icons1.png" name="cyclops_beam" power="power1" [type="boost|xtreme"]
          [hidden="true"] [value_priority="1"] [skirmish_locked="true"]>
    <talentvalues>
      <talentvalue level="1"  name="cyc_beam_dmg" value="11 15"/>     <!-- "min max" pairs allowed -->
      <talentvalue level="20" name="cyc_beam_dmg" value="195 217"/>   <!-- interpolated between listed levels -->
      <talentvalue level="1"  name="cyc_beam_req" value="1"/> ...
    </talentvalues>
    <level count="20" description="%cyc_beam_dmg $DMG_ENERGY\n%cyc_beam_pwr $EP">
      <require cat="level" level="%cyc_beam_req"/>
      [<require cat="skill" item="cyclops_radiation" level="1"/>]
      [<powerup life="-1"><affecter affect_type="scale" attribute="damage" level="%cyc_visor_dmg" scope_damage="dmg_energy"/></powerup>]
    </level>
  </talent>
</talents>
```

Attribute vocabulary actually used in the 21 XML2 files: talent.{name, descname, description, descshort, icon,
icon_texture, power, type, hidden, value_priority, skirmish_locked}; level.{count, description}; require.{cat|category,
item, level}; talentvalue.{level, name, value, interpolate}; powerup.{life, class, chance, percent, damagepercent,
damagetype, energy, inflicted}; affecter.{attribute, affect_type, level, damagetype, scope_attack, scope_damage,
scope_node}; special_fx.{effect, how_used}; scope.{scope_attack, scope_damage, scope_node, scope_non_powers}.
`power` values seen: power1..power11 (power9 = the xtreme in all 21 heroes, power11 = second xtreme, power10 optional)
and `blocking` (shared `block`). Explicit per-level `<level>` elements without `count` also occur (`might`, `psionic_fury`).

### 2.3 XML1 form and the mapping

XML1 (`herostat.eng`, inline under `<stats>`):

```
<Talent name="cyclops_beam" level="1" descname="<power name>" description="..." icon_texture="textures/ui/cyclops_all.png"
        icon="0" power="0">
  <level description="^L2 Damage. ^P1 Energy."/>
  <level description="^L3 Damage. ^P1+ Energy."><require cat="level" level="3"/></level>
  ... 11 levels; rung 6 and 11 have descname="..." cost="2"; rung 11 has <require cat="level" level="25" degree="see"/>
      plus <require cat="level" level="30"/> (visible at 25, buyable at 30)
</Talent>
```

Mapping rules (data-derived, all 15 heroes checked):

1. `Talent` -> `talent`; keep `name`, `descname`, `description`, `icon`, `icon_texture` (re-pointed, see 5.4);
   drop the herostat-side `level` attr (XML2 herostat lists `<talent level="1" name=...>` separately - keep that
   reference in the new herostat entry, exactly as XML2 does for `cyclops_beam level=1`).
2. `power="k"` in XML1 is the **power-slot index** (0..3 = the four powers; 4/5 = passive columns), not a FightMove
   name (Beast: `beast_pinball power=0 icon=1`, `beast_propeller power=1 icon=0`, and the FightMoves carry the matching
   `icon`). XML2 wants the FightMove name -> `power="power{k+1}"` for k=0..2 and `power="power9"` for the xtreme
   (k=3), consistent with all 21 XML2 heroes; passives (k=4,5, or no power) get no `power` attribute.
   `type="boost"` for the k=2 self-buff talents (beast_boost, colossus_steelskin, cyclops_tactics, frost_shield,
   kinetic_boost, iceman_armor, taunt, magma_form, night_shadow, phoenix_shield, profx_psychicdefense, psylocke_armor,
   rogue_shield, storm_shield, wolv_berserk) and `type="xtreme"` for `*_xtreme`.
3. Levels: XML1's explicit 11/9/5/6 `<level>` elements can be kept as explicit levels (XML2 accepts that form) with
   their numeric `<require cat="level" level="N"/>`, or collapsed into `<level count="N">` + `<talentvalues>` (the XML2
   way). Because the **powerstyle** side must collapse (section 4.2), `talentvalues` are needed anyway: one value per
   rung for damage (L2..H3 codes -> numbers from `xml1_loose/data/values.xml`), knockback (K codes), energy (P codes;
   use XML1's numbers, not XML2's differing P table), boost duration (BST1..9), etc. Name them with an `x1_` or
   hero prefix to avoid clashing with XML2 value names (`cyc_beam_dmg` etc. are taken).
4. `descname`/`cost` on rungs 6 and 11 (rank-up names "Cannon Ball"/"Legend Ball", cost 2): the exe has the strings
   `descname`, `cost`, `degree`; per-level descname support UNVERIFIED (XML2 data never uses it). Fold the rank names into
   the description text if it turns out unsupported.
5. Passive inline talents with `activepowerup` children (section 3) become `<level><powerup life="-1"><affecter .../>`.

### 2.4 Per-hero talent counts

| hero | talents | inline (power+passive) | plain refs | XML1 `<level>`s | inline names |
|---|---|---|---|---|---|
| default | 1 | 0 | 1 (fightstyle_hero) | 0 | - |
| Beast | 11 | 4 | 7 | 32 | beast_pinball, beast_propeller, beast_boost, beast_xtreme |
| Colossus | 11 | 5 | 6 | 37 | colossus_titanicsmash, colossus_concslam, colossus_steelskin, colossus_xtreme, colossus_charge |
| Cyclops | 11 | 4 | 7 | 32 | cyclops_beam, cyclops_sweep, cyclops_tactics, cyclops_xtreme |
| Frost | 12 | 7 | 5 | 46 | frost_confuse, frost_fear, frost_shield, frost_xtreme, frost_hardness, frost_might, psi_fight_frost |
| Gambit | 11 | 7 | 4 | 48 | charged_card, staff_slam, kinetic_boost, gambit_xtreme, overload, kinetic_strike, staff_master |
| Iceman | 12 | 7 | 5 | 44 | iceman_freeze, iceman_spikes, iceman_armor, iceman_xtreme, iceman_elemental, ice_skating, ice_special |
| Jubilee | 11 | 5 | 6 | 37 | energy_burst, photo_flash, taunt, jubilee_xtreme, detonate |
| Magma | 11 | 7 | 4 | 46 | magma_blast, lava_fissure, magma_form, magma_xtreme, magma_elemental, magma_skating, magma_might |
| Nightcrawler | 11 | 6 | 5 | 42 | night_strike, night_frenzy, night_shadow, night_xtreme, night_faith, sucker_punch |
| Phoenix | 12 | 6 | 6 | 43 | phoenix_telekinesis, phoenix_shout, phoenix_shield, phoenix_xtreme, phoenix_combat, psi_fight_phoenix |
| ProfXAstral | 12 | 6 | 6 | 6 | profx_psychicsmash, profx_psychicburst, profx_psychicdefense, profx_xtreme, profx_fighting, astralknockback (all single-level, all level=1) |
| Psylocke | 11 | 6 | 5 | 43 | psylocke_slash, psylocke_bolts, psylocke_armor, psylocke_xtreme, blademaster, psi_fight_psylocke |
| Rogue | 11 | 4 | 7 | 32 | rogue_strike, rogue_ability, rogue_shield, rogue_xtreme |
| Storm | 11 | 5 | 6 | 38 | storm_lnstrike, storm_whirlwind, storm_shield, storm_xtreme, storm_elemental |
| Wolverine | 11 | 6 | 5 | 42 | wolv_slash, wolv_frenzy, wolv_berserk, wolv_xtreme, wolv_sharpness, expertise |

Totals: 85 inline talents / 568 levels -> at most 7 talents per hero file (cap 100 per file). XML2's own files hold 7-15.

### 2.5 Name collisions and the shared-talent budget

- Collisions with XML2 **per-hero** talent files (same name, different meaning): Cyclops `cyclops_beam`,
  `cyclops_tactics`, `cyclops_xtreme`; Nightcrawler `night_faith`; Rogue `rogue_ability`, `rogue_xtreme`; Storm
  `storm_whirlwind`, `storm_shield`, `storm_xtreme`; Wolverine `wolv_slash`, `wolv_frenzy`, `wolv_berserk`, `wolv_xtreme`.
  Harmless **only** because the XML1 hero replaces the XML2 hero of the same stats name and its `data/talents/<name>`
  file is replaced wholesale (a name is registered once per talent id space). If an XML2 hero is kept as a padding entry,
  it must not be one of these five.
- Collisions with XML2 **shared** talents: the plain references `fightstyle_hero/wrestling/finesse1/psionic`, `might`,
  `critical`, `flight`, `leadership` - these intentionally resolve to XML2's definitions (XML2 `might` has 2 levels vs
  XML1 3; XML2 `critical` 15 levels with %values vs XML1's 8 - accepted).
- Plain references that XML2 does not define: `toughness` (15 heroes), `mutantmastery` (15; XML2's is `mutantmaster`,
  a *different* effect - energy regen vs XML1 max-energy), `acrobatics` (Beast, Nightcrawler), `grappling` (Beast, Rogue),
  `knockback` (Colossus), `accuracy` (Cyclops, Jubilee), `pointblank` (Cyclops, Iceman, Jubilee), `healing_factor`
  (Wolverine). The tour build already carries toughness, mutantmastery, acrobatics in shared_talents (**as empty
  definitions**, added for NPCs; 88/99 used). The other 5 are new. XML1's real definitions live in
  `xml1_loose/data/shared_talents.eng` (e.g. `toughness` = `activepowerup powerup="maxhealth" affect_type="scale"
  level="1.1"`, `mutantmastery` = `maxenergy` scale, `acrobatics` = `speed` +2/+4 + double jump, `grappling` = `strength`
  + `reflect_damage` L1 user1=100 scoped to punch/kick, `leadership` = combo_damage/combo_xp scale) and convert to
  `<powerup life="-1"><affecter attribute="maxhealth" affect_type="scale" level="1.1"/>` etc. (`maxhealth`,
  `maxenergy`, `speed`, `strength`, `reflect_damage`, `jump` are XML2 affecter attributes). Recommendation: put the
  hero-only passives (accuracy, pointblank, healing_factor, knockback, grappling) in the per-hero files, keep the shared
  budget at 88 (+0..5).
- No XML1 hero talent name exceeds the 31/0x40 name limits (longest: `colossus_titanicsmash`, 21).

---------------------------------------------------------------------------------------------------------------

## 3. `activepowerup` -> XML2 `<powerup><affecter>`

94 elements, all inside talent levels (Frost 14, Gambit 11, Iceman 7, Magma 9, Phoenix 11, ProfXAstral 2, Psylocke 11,
Storm 6, Wolverine 23; none in Beast, Colossus, Cyclops, Jubilee, Nightcrawler, Rogue, default). Attribute union:
powerup 94, level 94, life 94 (always -1), scope_damage 54, user1 51, damagetype 43, user2 43, effect_cust1 43,
func_trail 43, func_attempt_hit 43, scope_attack 13, scope_node 5 (+ `<scope scope_node="gambit_staff">` children x5),
func_damage 3, affect_type 1. XML1 `powerup=` values: special 43, damage 15, might_mode_mod 6, reflect_damage 5,
atk_damage 5, damageLevel 5, speed 5, strength 5, none 3, no_iceshell 1, atk_knockback 1.

XML2 equivalent forms (all from retail talent/powerstyle data; affecter vocabulary in `inventory.json`):

| XML1 pattern | heroes | XML2 form |
|---|---|---|
| `powerup="special" func_attempt_hit="DamageAddAttack" func_trail="elemtrail" damagetype=dmg_X level=L1..M1 user1 user2 effect_cust1="powerups/<hero>_elemental" scope_damage=dmg_physical` (elemental melee) | Frost, Gambit, Iceman, Magma, Phoenix, ProfXAstral, Psylocke, Storm (43) | `<powerup class="add_attack" damagepercent="%v" damagetype="dmg_X" life="-1"><special_fx effect="..." how_used="custom"/><affecter attribute="powerup_scope"/></powerup>` (retail `iceman_ice_combat`, `bishop_combat`). `DamageAddAttack`/`elemtrail` do not exist in XMen2.exe. XML1 adds a flat L-code amount; XML2 adds a percentage - value re-derivation needed. |
| `powerup="damage" level=L1.. scope_damage=dmg_mental` / `scope_node=psylocke_power` | Phoenix combat, Psylocke blademaster | `<affecter attribute="damage" level="%v" scope_damage="dmg_mental"/>` or `scope_node=` (retail bishop `damage` + `scope_node`) |
| `powerup="atk_damage" level=L3.. <scope scope_node="gambit_staff"/>` | Gambit staff_master | `<affecter attribute="atk_damage" level="%v" scope_node="gambit_staff"/>` (scope_node is an affecter attribute in XML2; requires the FightMoves to carry a matching node/tag - UNVERIFIED that XML1 style nodes survive as scope names) |
| `powerup="damageLevel" level=3..8 scope_attack=punch` | Wolverine sharpness | `damageLevel` string exists in exe; XML2 data never uses it as an affecter attribute -> UNVERIFIED; fall back to `attribute="damage"` |
| `powerup="none" func_damage="damageaddbleed" user1=5..9` (bleed on claws) | Wolverine sharpness (3) | `<powerup class="add_harming" damagepercent=..>` or victim tag `shared_bleed` (retail wolverine p4 uses `shared_tag`); `damageaddbleed` absent from exe |
| `powerup="reflect_damage" level=L3..M2 user1=10..50 (chance %)` | Frost hardness (5), grappling (shared) | `<affecter attribute="reflect_damage" level="%v"/>` (retail ps_juggernaut) + `powerup chance="0.1"` (powerup.chance exists) |
| `powerup="might_mode_mod" level=1..3` | Frost, Magma (6) | `might_heaviness`/`might_structure` affecters as in XML2 `might`; `might_mode_mod` absent from exe |
| `powerup="speed"/"strength" level=1..5` (additive) | Wolverine expertise (10) | `<affecter attribute="speed" level="N"/>` (no affect_type = additive, as XML2 `critical`) |
| `powerup="atk_knockback" level=K3 scope_damage=dmg_mental` | ProfXAstral astralknockback | `atk_knockback_scale` exists as XML2 affecter; plain `atk_knockback` string exists - UNVERIFIED |
| `powerup="no_iceshell" affect_type=scale level=0` | Iceman ice_special (hidden) | identical: `<affecter affect_type="scale" attribute="no_iceshell" level="0"/>` (retail `sentinel_special`) |

Also 66 `<trigger name="powerup" ...>` inside the 15 hero powerstyles (boost powers) use the same XML1 vocabulary
(`powerup=def_damage/strength/speed/might_mode/confused/fear/deflect_damage/drain_victim/nullify/stun_lock/invisible/
traits/...`, `func_deactivate`, `level`, `affect_type`, `scope_*`); XML2's form is the nested `<affecter>` inside the
trigger (section 2.2 powerup_trigger). `trigger.powerup`, `trigger.level`, `trigger.affect_type`, `trigger.func_*` occur
in **no** XML2 style.

---------------------------------------------------------------------------------------------------------------

## 4. Powerstyles: XML1 `ps_<hero>` vs XML2 `ps_<hero>`

### 4.1 Inventory

| hero | XML1 file | mapped name (pipeline) | moves | XML2 same-name file | XML2 moves | value codes used | attrs not in any XML2 style |
|---|---|---|---|---|---|---|---|
| Beast | ps_beast.eng | x1_ps_beast | 41 | yes (NPC style) | 8 | 62 | 8 |
| Colossus | ps_colossus.eng | x1_ps_colossus | 45 | yes | 13 | 68 | 9 |
| Cyclops | ps_cyclops.eng | x1_ps_cyclops | 37 | yes | 12 | 62 | 6 |
| Frost | ps_frost.eng | x1_ps_frost | 37 | yes (NPC, 2 moves) | 2 | 52 | 10 |
| Gambit | ps_gambit.eng | x1_ps_gambit | 51 | yes | 21 | 61 | 14 |
| Iceman | ps_iceman.eng | x1_ps_iceman | 45 | yes | 15 | 64 | 18 |
| Jubilee | ps_jubilee.eng | ps_jubilee | 46 | no | - | 55 | 13 |
| Magma | ps_magma.eng | ps_magma | 44 | no | - | 62 | 15 |
| Nightcrawler | ps_nightcrawler.eng | x1_ps_nightcrawler | 51 | yes | 33 | 60 | 8 |
| Phoenix | ps_phoenix.eng | x1_ps_phoenix | 39 | yes | 15 | 66 | 7 |
| ProfXAstral | ps_profxastral.eng | ps_profxastral | 15 | no | - | 15 | 11 |
| Psylocke | ps_psylocke.eng | ps_psylocke | 37 | no | - | 66 | 9 |
| Rogue | ps_rogue.eng | x1_ps_rogue | 52 | yes | 14 | 68 | 13 |
| Storm | ps_storm.eng | x1_ps_storm | 37 | yes | 13 | 60 | 8 |
| Wolverine | ps_wolverine.eng | x1_ps_wolverine | 43 | yes | 17 | 53 | 15 |

All 15 are already converted and emitted by the tour build (`build/xml1_tour/Data/powerstyles/<mapped>.XMLB`), with
XML1 semantics untouched ("power-system review pending"). All effects they reference exist on the XML1 disc and in the
tour build (`Effects/powers/cyc_*.XMLB` etc.; 0 dead references).

### 4.2 FightMove naming: `optic_beam1..10` + `power_attack` vs `power1..N` - the structural problem

XML1 encodes each power as a chain of 11 FightMoves: `optic_beam1` (root: `animenum`, `icon="0"`, `require cat=talent
item=cyclops_beam level=1`) then `optic_beam2 inherit="optic_beam1" fallback="optic_beam1"` with `require level=2` and one
overriding `<trigger tag=1 Damage=.. powerusage=..>`, ... up to `power_attack inherit=optic_beam10` (level 11). Every
hero follows it: 4 chains per hero (icon groups 0..3), plus `power_smash`/`power_attack`/`power_xtreme` top rungs.
XML2 encodes each power as **one** FightMove named `powerN` whose attributes reference `%talentvalues`
(`damage="%cyc_beam_dmg" powerusage="%cyc_beam_pwr" playspeed="%cyc_beam_speed"`), gated by
`<require cat="skill" item="cyclops_beam" level="1"/>`.

Engine facts that force the collapse:

- `fallback` is **not** a string in XMen2.exe (only `ea_grab_fallback`, `random_fallback_loc`), so the rung-selection
  attribute XML1 relies on is ignored; `inherit` is read. Retail XML2 still writes `fallback="attackheavy1"` on
  `popupattack` - dead data.
- Powers are addressed by FightMove name from the herostat `power1..4` slots and from UI code that hardcodes
  `power1/2/8/9` (section 1.1), and a talent names exactly one FightMove (`power=` string, 0x14 chars).
- `IconColumns`/`IconRows`/`exclusive` on `<PowerStyle>` are not exe strings (ignored); `iconfile` and `cansteal` are.
- XML2 retail styles contain **zero** value codes; XML1 hero styles use 52-68 distinct codes each. 16 codes are absent
  from XML2's values.XMLB (A1-A10, XTL1-6; the pipeline already appends them) and 34 differ (BST1, BST9, P0+..P16+) -
  irrelevant once numbers come from talentvalues, but every non-power move that keeps codes (basic attacks do not; power
  triggers do) must be checked. Whether code lookup still works at runtime is UNVERIFIED (data/values.xmlb is still
  loaded: string at file 0x28f2fc). Note 4 XML1 typos `XLT2..6` (Frost, Nightcrawler, Rogue, Storm) resolve to nothing in
  either game.

Proposed mapping per hero (data in `inventory.json` -> `talents.inline[].proposed_x2_power`): power index 0 -> `power1`,
1 -> `power2`, 2 -> `power3` (boost), 3 (xtreme) -> `power9`; herostat `power1="power1" power2="power2" power3="power3"
power4="power9"`. Collapse each 11-rung chain into one FightMove that copies the root's static attributes and turns the
per-rung `Damage/Knockback/powerusage/damageLevel/fxLevel/radius` overrides into `%x1_<hero>_<power>_<field>` talentvalues
(level 1..11). Rungs that add whole triggers (e.g. `optic_beam6` adds `pierce="true"`, cyc_tactics adds a second
powerup at rank 6) need a per-level `<require>`d duplicate trigger or acceptance of the top-rung behaviour.
`power_attack`/`power_smash`/`power_xtreme` exist as strings in XMen2.exe (XML1-era defaults) - meaning UNVERIFIED; do
not rely on them.

### 4.3 Combat handlers

Handlers used by the 15 hero styles and their status in XMen2.exe's registration table (0x4fd975-0x4fe88a, characters.md):
ch_fastball, ch_bounce_move (Beast); ch_move_jump, ch_jump, ch_charge_move (Colossus); ch_gambitboltons x6,
ch_pickup_idle, ch_pickup_walk, ch_gambitdecide, **ch_throw** (Gambit); ch_move_jump, ch_jump x2, ch_skating (Iceman);
ch_pickup_idle, ch_pickup_walk, ch_gambitdecide, **ch_throw** (Jubilee); ch_move_jump, ch_jump, ch_skating (Magma);
ch_nightcrawlerdecide, ch_tele_jump x6, ch_move_tele_land x7, ch_teleport_stomp, ch_grab_victim (Nightcrawler);
ch_telekinesis x2 (Phoenix); ch_popup_attack (ProfXAstral); **ch_roguedecide**, ch_teleport_dash_start,
ch_move_jump_land (Rogue); ch_fastball, ch_teleport_dash_start, ch_teleport_frenzy_dash, ch_move_jump_land (Wolverine);
none in Cyclops, Frost, Psylocke, Storm. Registered in XMen2.exe: all except the three in bold.

Moves that lose their handler logic (the move still loads and plays; the handler's behaviour is gone - retail XML2 itself
ships unregistered `ch_sab_*`/`ch_grenade`, characters.md):

| hero | FightMove | handler | what is lost |
|---|---|---|---|
| Gambit | `charged_throw` (the thrown-object rung of power 1 `charged_card`, `icon 0` group has 3 moves: power_attack, card_throw1, charged_throw) | ch_throw | throwing a picked-up object charged with kinetic energy |
| Jubilee | `charged_throw` (same pattern, `energy_burst` power) | ch_throw | throwing a charged picked-up object |
| Rogue | `ability_drain_decide1` (root of power 2 `rogue_ability`, 22 `require` rungs) | ch_roguedecide | the decide step that picks a drain/steal variant per victim: Rogue's signature power |

Also from `moveset_flying` (Phoenix, Rogue, Storm via `moveset1`): ch_air_grab_pickup(_idle/_throw), ch_fly_guard_decide
are XML1-only (combat_compat.txt) - but the pipeline shares XML2's `moveset_flying`, so those moves are XML2's already.
`moveset_acrobat` (Beast, Psylocke): ch_clingwall* likewise replaced by XML2's file.

### 4.4 Trigger names and attributes

Re-scanned against every XML2 style/fightstyle/shared_combat_events name, the style's own `<event name=>` definitions
and the exe strings: only **one** hero trigger name is truly unknown to XMen2.exe: Jubilee `bait` (1 use). The names
combat_compat.txt flagged for heroes (`optic_blast`, `phoenixforce`, `freeze_fx`, `icextreme_*`, `telekinesis_dmg`) are
either local `<event>` definitions or (optic_blast, freeze_fx) used by XML2's own styles with `inherit="beam"`.
Attributes with no occurrence in any XML2 style (per hero 6-18; union): `powerstyle.exclusive/iconcolumns/iconrows`,
`trigger.powerup/level/affect_type/scope_attack/scope_damage/life_max/level_max/func_activate/func_deactivate/func_damage/
func_death/func_hurt/func_think/func_touch/func_trail/func_attempt_hit`, `trigger.fx_bolt`, `trigger.effect_cust2`,
`trigger.bolton`, `trigger.skin_swap` (string exists), `trigger.motor/timebased/vibrate` (Magma), `trigger.dasheffect/
dashbolt/closerange/hitenemyeffect/nopushback/targetdot/scale`, `event.powerup_tag`, `require.only_looped`,
`require.entity`, `fightmove.noflying`. The `func_*` family is the XML1 script-callback mechanism and is absent from
the exe as strings -> those triggers run without their callbacks.

---------------------------------------------------------------------------------------------------------------

## 5. Assets per hero

### 5.1 Skins, costumes, HUD/UI models, loading screens (XML1 id -> +14000; `x1names.igb_rename` of `<id>`, `<id>_outline`, `<id>_skel`)

| hero | costume ids (XML1 -> XML2) | actors on disc | hud_head on disc | ui/hud/characters | ui/models/characters | textures/loading | in tour build |
|---|---|---|---|---|---|---|---|
| default | 0002->14002 | yes | no | no | no | no | actor only |
| Beast | 0501->14501, 60s 0502->14502, future 0503->14503 | 3/3 | 0501,0502 | 0501,0502 | 0501 | 0501 | all + packages (hero-as-NPC) |
| Colossus | 0901->14901, 70s 0903->14903, civilian 0902->14902, future 0906->14906 | 4/4 | 0901 | 0901,0902,0903 | 0901 | 0901 | all files, **no packages** |
| Cyclops | 0101->14101, 60s 0102->14102, 70s 0103->14103, future 0105->14105 | 4/4 | 0101,0102,0103 | 0101,0102,0103 | 0101 | 0101 | files, no packages |
| Frost | 1501->15501, future 1502->15502 | 2/2 | 1501 | 1501 | 1501 | 1501 | all + packages |
| Gambit | 1301->15301, future 1302->15302 | 2/2 | 1301 | 1301 | 1301 | 1301 | files, no packages |
| Iceman | 0801->14801, 60s 0803->14803, civilian 0802->14802 | 3/3 | 0801,0803 | 0801,0802,0803 | 0801 | 0801 | files, no packages |
| Jubilee | 1601->15601 | 1/1 | 1601 | 1601 | 1601 | 1601 | all + packages |
| Magma | 1801->15801, future 1804->15804, magmacivilian 1803->15803 | 3/3 | 1801 | 1801,1803 | 1801 | 1801 | all + packages |
| Nightcrawler | 0601->14601, 70s 0602->14602, future 0603->14603 (+ tail bolt-on 0610? XML2 uses 0610; XML1 BoltOn model see json) | 3/3 | 0601,0602 | 0601,0602 | 0601 | 0601 | files, no packages |
| Phoenix | 0201->14201, 60s 0202->14202, 70s 0203->14203 | 3/3 | 0201,0202,0203 | 0201,0202,0203(,0204) | 0201 | 0201 | files, no packages |
| ProfXAstral | 1104->15104 | 1/1 | 1104 | 1104 | no (1101 = ProfX npc) | 1101/1102 only | all + packages |
| Psylocke | 1201->15201, future 1202->15202 | 2/2 | 1201 | 1201 | 1201 | 1201 | all + packages |
| Rogue | 0701->14701 | 1/1 | 0701 | 0701 | 0701 | 0701 | files, no packages |
| Storm | 0401->14401, future 0402->14402 | 2/2 | 0401 | 0401 | 0401 | 0401 | files, no packages |
| Wolverine | 0301->14301, 60s=70s 0303->14303, future 0305->14305, weaponx 0302->14302 | 4/4 | 0301,0302,0303 | 0301,0302,0303 | 0301 | 0301 | files, no packages |

Facts: every XML1 hero skin id collides with an XML2 actor of the same 4-digit id (different content) - the +14000 rule is
mandatory; the pipeline already writes all 182 actors, 68 HUD heads, 74 ui/hud/characters, 16 ui/models/characters and
23 loading screens under mapped ids (`characters.py` docstring; counts in `build/xml1_tour`: Actors 968, HUD 184,
UI/HUD/characters 261, UI/models/characters 58, Textures/loading 135). Missing per-costume HUD heads are tolerated: the
engine tries up to three rebuilt skin strings (FUN_005f4ec0, `decomp1.c` 370-475) and retail relies on it (XML2 Cyclops
skin 0103, only `hud_head_0101` ships). Loading screens are found by `textures/loading/%02d%02d.igb` from the prefix
byte (0x487258), so `Textures/loading/14101.IGB` is reached for prefix 141 (`%02d` of 141 = "141"); missing variants are
skipped after an existence check (0x487291). `ui/models/characters/9999.igb` is the engine fallback head model
(string xref 0x5f7501 in FUN_005f7480).

**Not yet done for heroes:** character packages `Packages/generated/characters/<name>_<skin>[_nc].PKGB` for the 10
stand-in-covered heroes (Colossus, Cyclops, Gambit, Iceman, Nightcrawler, Phoenix, Rogue, Storm, Wolverine + default) -
today XML2's own packages (`cyclops_0103.PKGB`...) serve the stand-ins. XML1 bundles exist for every costume
(`packages/generated/characters/<name>_<skin>.fb` + `_nc` + `<name>_xml.fb`, e.g. cyclops 0101/0102/0103/0105) and list
actorskin, actoranimdb, hud/hud_head, ui/hud/characters, effects, textures, `models/bolton/*`, and the powerstyle
(`data/powerstyles/ps_cyclops.eng` as `fightstyle`). The XML2 hero package additionally needs
`<xml_talents filename="data/talents/<hero>"/>`, `<texture filename="textures/ui/<icons>"/>` and (XML2 does) the
`<name>_xml.PKGB` with xml_talents + powerstyle. `characters.py build_packages` already produces this shape for NPCs and
heroes-as-NPC and can be reused with the two extra entries.

### 5.2 Animation DBs and fightstyles

`characteranims` -> mapped (x1names): 00_testguy->x1_00_testguy, 01_cyclops->x1_01_cyclops, 03_wolverine->x1_03_wolverine,
04_storm->x1_04_storm, 05_beast->x1_05_beast, 06_nightcrawler->x1_06_nightcrawler, 07_rogue->x1_07_rogue,
08_iceman->x1_08_iceman, 09_colossus->x1_09_colossus, 13_gambit->x1_13_gambit (all clash with XML2 files of the same
name); 02_phoenix, 11_profxastral, 12_psylocke, 15_emmafrost, 16_jubilee, 18_magma keep their names. All 16 are on the
disc and in the tour build. Fightstyles/movesets: `fightstyle_hero/wrestling/finesse1/psionic`, `moveset_flying`
(Phoenix, Rogue, Storm), `moveset_acrobat` (Beast, Psylocke) are shared with XML2 by name (XML2's files are used;
namespace policy in x1_namespace_map "STYLES"). Each party hero costs 2 actor slots (skin + anim DB) exactly as the
stand-ins do; `actor_budget.PARTY` and `prune_package_root` (which today treats XML1 hero actors as dead weight) must be
switched to the XML1 hero skins when the roster changes (SPEC 14).

### 5.3 Voice/sound banks

XML1 `sounddir` per hero: beast_m, coloss_m, cyclop_m, emmaf_m, gambit_m, iceman_m, jubile_m, magma_m, night_m,
phoen_m, profxa_m, psyloc_m, rogue_m, storm_m, wolver_m. All 15 exist on the Xbox disc, all 15 are converted
(`research/sound/out/all_ima/eng/<c1>/<c2>/<sd>.zsm`), and all 15 are already installed by the tour build's media step
(`build/xml1_tour/Sounds/eng/...`). Six names collide with XML2 banks (beast_m, coloss_m, cyclop_m, iceman_m, night_m,
storm_m): merged banks (XML2 keys kept, XML1 appended) exist in `research/sound/out/merged/` and are what the build
uses. XML1 keys are `character/<dir>/...` with `char/` aliases for the 71% of recovered names (sound.md); the power
triggers reference the XML1 `character/...` names, which still hash-resolve. XML2 uses different names for four heroes
(wolv_m, phoenx_m, vogue_m, igam_m) - no collision, but the XML2 stand-in's engine-event sounds (pain/death/jump) will
come from the XML1 bank's aliases only where the name was recovered.

### 5.4 Icons / textureicon / menus

- Power icons: XML1 `icon_texture="textures/ui/<hero>_all.png"` (15 atlases, 4 icons each, `icon` 0..3; PowerStyle
  `IconColumns=2 IconRows=2` ignored by XMen2.exe). XML2: `textures/ui/<hero>_icons1.png`, icons 0..12 per hero, grid
  UNVERIFIED (menu items use `icons_cols/icons_rows`; the talent screen's grid attribute was not located). The 15 XML1
  atlases are on disc and already copied by the tour build (`Textures/ui/beast_all.IGB` ...). If the XML2 talent screen
  assumes a 4x4 (or other) grid, XML1's 2x2 index 1..3 land on the wrong cell -> either re-atlas the 4 icons into XML2's
  grid or verify the grid first. Shared passives use XML2's `textures/ui/talent_icons.png` (indices 0-7).
- `textureicon`: XML2 heroes 0..40; the index feeds a portrait sheet whose file was not identified (UNVERIFIED). XML1 has
  no equivalent (its character menu uses the 3D heads `ui/models/characters/<skin>` via
  `packages/generated/maps/package/menus/characters_heads.fb` listing 16 heads: 0101..0901, 1001, 1101, 1201, 1301, 1501,
  1601, 1801).
- XML2's `generated/maps/package/menus/characters_heads(.PKGB|_pc.PKGB)` lists `ui/models/characters/<skin>` for its
  19 (+2 PC) heroes plus 9999 and `m_team_roster_screen`; the tour build ships it **unchanged** (XML2's list), so the 16
  XML1 head models (14101 ...) are on disk but not precached by the roster screen (fallback 9999 or on-demand load).
  The package must be rewritten with the XML1 ids.
- Conversations: speaker tokens `%CYCLOPS%` (94+19), `%PHOENIX%` (156), `%MAGMA%` (113), `%BEAST%` (91),
  `%WOLVERINE%` (71), `%FROST%` 41, `%NIGHTCRAWLER%` 37, `%COLOSSUS%` 36, `%ICEMAN%` 36, `%STORM%` 33, `%ROGUE%` 32,
  `%JUBILEE%` 27, `%GAMBIT%` 14, `%PSYLOCKE%` 10, `%PROFXASTRAL%` 10 resolve through the stats name table (a miss ->
  index 0, SPEC 12.2); portraits come from the speaker's `hud/hud_head_<skin>`. Nothing hero-specific to convert.

---------------------------------------------------------------------------------------------------------------

## 6. XML1 heroes that exist in XML2 too

| XML1 | XML2 entry (skin, anims, powerstyle, sounddir, talent file) | notes |
|---|---|---|
| default | default 0002 / 00_testguy / - / - (autospend support_heavy, Race Mutant+XMen) | keep XML2's |
| Colossus | 0903 / 09_colossus / ps_colossus / coloss_m / talents/colossus (13 talents) | XML2 version can stay as a padding hero only under another stats name (impossible without renaming) -> it is replaced |
| Cyclops | 0103 / 01_cyclops / ps_cyclops / cyclop_m / talents/cyclops (13) | replaced; 3 talent-name clashes vanish with the file |
| Gambit | 1301 / 13_gambit / ps_gambit / igam_m / talents/gambit (14) | replaced |
| Iceman | 0801 / 08_iceman / ps_iceman / iceman_m / talents/iceman (15) | replaced |
| Nightcrawler | 0603 / 06_nightcrawler / ps_nightcrawler / night_m / talents/nightcrawler (14) | replaced |
| Phoenix | 0203 / 02_jean_grey / ps_phoenix / phoenx_m / talents/phoenix (15) | replaced (charactername "Jean Grey" in both) |
| Rogue | 0703 / 07_rogue / ps_rogue / vogue_m / talents/rogue (12) | replaced |
| Storm | 0403 / 04_storm / ps_storm / storm_m / talents/storm (15) | replaced |
| Wolverine | 0303 / 03_wolverine / ps_wolverine / wolv_m / talents/wolverine (14) | replaced |

"Fallback" semantics: because stats names are registered once (herostat first, then npcstat; second registration ignored
at 0x44c3c9) and the per-hero talent file is keyed by the stats name, an XML2 hero and an XML1 hero of the same name
**cannot coexist**. The XML2 version can only survive under a different name (not recommended) or as the padding
entries for the 21 slots: the XML2-only heroes Bishop, Deadpool, Ironman, Juggernaut, Magneto, Professorx, ScarletWitch,
Sunfire, Toad, Pyro_hero, sabretooth_hero are candidates (XML2 Beast/Frost/Jubilee/Magma/Psylocke/ProfX do not exist as
XML2 heroes; Beast/profx are XML2 npcstat names already replaced by XML1's in XML1 mode).

Roster-size decision (open): XML1 has 16 entries; XMen2.exe maps exactly 21 (0x44bb13; fewer is memory-safe but
unexercised: unused iterations map to stats index 0). startFirstMission (0x4a7b41-0x4a7bef) pre-loads **magneto,
cyclops, wolverine, storm** by name before `menus/new_game.py` runs; with XML1's herostat `magneto` is not a stats name
(XML1 npcstat has MagnetoAct2/MagnetoBoss/... only) and resolves to index 0. Cheapest mitigation: keep XML2's `Magneto`
as one of the 5 padding heroes (names must match `magneto` case-insensitively), or verify in game that a missed name is
harmless; `new_game.py` already ends in `loadMapChooseTeam` (SPEC 12.6), which re-picks the team.

XML1 npcstat also flags 56 entries `team="hero"` or `playable="true"`: the 15 `<Hero>NoAnims` doubles, Forge (2201),
ProfX (1101), ProfXComa (1102), profxgladiator (1105, `playable="false"`, 7 talents / 5 inline - the Astral Gladiator
form), Police, and 37 Danger-Room-playable villains (AcolyteEnergy ... ToadAct1). None belongs in herostat; the
gladiator/astral forms are forced-hero cases (SPEC 12.6 order: magma, frost, profxastral, profxgladiator, beast, jubilee).

---------------------------------------------------------------------------------------------------------------

## 7. Per-hero readiness

Legend: **ready** = nothing to do; **needs conversion** = herostat attrs + talents file + powerstyle collapse + packages,
no engine gap; **needs conversion + powers rework** = as before plus a power whose handler XMen2.exe lacks. No hero is
blocked by a missing asset: every skin, anim DB, HUD/UI model, loading screen, effect, icon atlas and voice bank is on the
disc and already emitted by the pipeline.

| hero | status | specific blockers / work beyond the common conversion |
|---|---|---|
| default | ready | keep XML2's `default` (has autospend, Race XMen) |
| Beast | needs conversion | remove from npcstat (hero-as-NPC today); `grappling`, `acrobatics` need XML2 definitions; sound bank collides (merged bank in use) |
| Colossus | needs conversion | `knockback` passive needs a definition; `heaviness` kept |
| Cyclops | needs conversion | `accuracy`, `pointblank` passives; talent names clash with XML2 cyclops file (replaced) |
| Frost | needs conversion | remove from npcstat; 14 activepowerups (reflect_damage x5 with chance, might_mode_mod x3, elemental melee x6); no XML2 hero counterpart |
| Gambit | needs conversion + powers rework | `charged_throw` uses ch_throw (unregistered); 11 activepowerups incl. `scope_node="gambit_staff"` x5; ch_gambitboltons x6 registered |
| Iceman | needs conversion | 7 activepowerups (elemental melee, no_iceshell); `pointblank`; 18 XML1-only trigger attrs (most `func_*`); sound bank collides (merged) |
| Jubilee | needs conversion + powers rework | remove from npcstat; `charged_throw` uses ch_throw; trigger `bait` unknown to the exe; `accuracy`, `pointblank`; no XML2 counterpart |
| Magma | needs conversion | remove from npcstat; `skin_magmacivilian` -> `skin_civilian`; 9 activepowerups; `trigger.skin_swap/motor/vibrate/timebased`; needed by the first mission (nyc1_1_3) and 25 Magma-solo hub missions |
| Nightcrawler | needs conversion | `acrobatics`; XML2 herostat gives him a tail BoltOn (0610, anim 06_nightcrawler_tail) - XML1 has 1 BoltOn (see json); sound collides (merged) |
| Phoenix | needs conversion | 11 activepowerups; 3 FlyEffects; XML2 bank name differs (phoenx_m) so no collision |
| ProfXAstral | needs conversion (design-gated) | `playable="false"`, `level=40`, fixed stats 35/40/40/80, `xpexempt`, no scriptlevel; 15 moves incl. its own basic attacks (icon groups 0..11); single-level talents; only meaningful with the forced-hero mechanism (SPEC 12.6); remove from npcstat |
| Psylocke | needs conversion | remove from npcstat; 2 of 3 blade BoltOns are talent-gated (XML2 BoltOn `<require>` UNVERIFIED -> first blade only); 11 activepowerups incl. `scope_node="psylocke_power"` |
| Rogue | needs conversion + powers rework | `ability_drain_decide1` (power 2, 22 rungs) uses ch_roguedecide - her signature drain needs an XML2 re-expression (`drain_victim`/`nullify`/`stun_lock` powerups exist as strings); `grappling`; XML2 bank name differs (vogue_m) |
| Storm | needs conversion | `canfly` kept; 6 activepowerups; 3 FlyEffects; sound collides (merged) |
| Wolverine | needs conversion | 23 activepowerups (damageLevel x5, bleed via damageaddbleed x3 -> add_harming/shared_bleed, speed/strength x10); `healing_factor` passive; XML2 bank name differs (wolv_m) |

Common conversion for all 15 (none of it exists in the pipeline yet; `characters.py` explicitly defers it and drops the
inline trees for heroes-as-NPC - `detail.dropped_children` "hero talent tree (hero conversion)"):

1. herostat entry: lowercase/sorted attrs; drop rating*; add `autospend` (bruiser: Colossus, Rogue, Wolverine, Beast?;
   bruiser_light: Nightcrawler, Jubilee?; support: Phoenix, Storm, Frost, Psylocke?; support_heavy: Cyclops, Gambit,
   Iceman, Magma - a design choice, XML2 examples in inventory.json), `power1..4`, `textureicon`, optional
   `<Race name="XMen"/>`; keep the plain `<talent>` references (levels as XML1).
2. `data/talents/<hero>.xmlb` + `.engb` (the pipeline's `write_xmlb_pair`) from the inline trees (section 2.3) with
   talentvalues generated from `xml1_loose/data/values.xml`.
3. Powerstyle collapse: 4 chains -> `power1`, `power2`, `power3`, `power9` (+ keep the non-power moves: pickups, jumps,
   teleports, `popupattack`), `require cat="skill"`, `%talentvalue` references; rewrite `trigger name="powerup"`
   bodies into `<affecter>` children; drop `IconColumns/IconRows/exclusive`.
4. Packages per costume (+`_nc`) and `<hero>_xml` with `xml_talents`; rewrite `menus/characters_heads(.PKGB|_pc)`.
5. Remove the six hero-as-NPC entries from npcstat; recompute `actor_budget.PARTY`; re-run V13.
6. `Scripts/menus/new_game.py` already uses `loadMapChooseTeam`; decide the 21-slot padding (section 6).

Everything above that touches XMen2.exe behaviour is either verified as listed in `inventory.json -> engine_facts` or
marked UNVERIFIED there; the four items to test in game first are: (a) a herostat with fewer than 21 entries or the
padding choice, (b) `startFirstMission`'s `magneto` miss, (c) the talent-screen icon grid for a 2x2 atlas, (d) whether
`<level descname/cost>` and BoltOn `<require>` are honoured.
