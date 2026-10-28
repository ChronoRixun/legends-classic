# Equipment bonuses of the first game's item economy

`--loot xml1` (Legends Classic 0.4.2, default off) converts all 116 equipment definitions of the player's copy of
X-Men Legends with every bonus they carry: 97 new definitions named `lc_x1_<name>`, and the 19 Danger Room rewards
converted again in place under their old names. The table, the references, the economy sidecar
`Data/x1economy.txt`, the generated `approximations.json` / `APPROXIMATIONS.md` and the INI key `[Game]
Xml1Economy=1` are produced by `xml1build.loot`; the bonuses by `xml1build.item_bonuses` (this note). The engine half
(roller, prices, Forge, construction) is XML2 Fix's. Without the option nothing here runs and the build is
byte-identical to one made without it. The option needs `--save-layout w2` (185 definitions, more than 512 records)
and the XML1 front end, and it refuses an XML2 Fix DLL that does not carry the `Xml1Economy` key.

## Conversion contract

All equipment is derived from the player's source table in source order. Numeric classes 0/1/2 map to
gloves/belt/armor (backpack equipment sits in the PC gloves slot); the class is the source class, never a name
heuristic. Cost and unique flag are copied verbatim, including the absence of a cost (the 21 group -1 definitions carry
none and sell for nothing). Character and level requirements are preserved; character identifiers are lowercased.
Pickup art is the PC class pickup model. The display name carries XML1's quality prefix (the source strings 1006 -
1009 plus one ASCII space; none for quality 0 and for uniques), the description is the source text, `enemy_level` is
-1 and the PC `quality` attribute is not written (it only feeds the generator the economy never calls).

One source powerup occupies one enhancement record, in source order. Multiple affecters (for example regeneration rate
plus cap) share that record. Direct scope attributes and child scopes stay together on the affecter: alternatives within
a category combine, separate categories constrain the same bonus (the PC affecter loader reads child scopes at 0x535336,
so splitting is unnecessary and could duplicate a bonus on overlapping predicates).

**Every record is single-valued.** The engine draws between a record's `min max`; the zero-draw construction of the
economy fixes that draw, so a range would silently become its minimum. A source range collapses to its mean (an
`atk_damage` modifier keeps its minimum, which is what XML1 reads), and the row says so.

**Nothing is pending.** All 168 source powerups convert: 28 exact, 134 approximate, 6 original no-ops (no record is
written: XML1 does nothing for them either). Each non-exact conversion is a row of the generated
`approximations.json`, with the XML1 value, the port value, why, its family and its record number.

| Source family | Generated contribution | Known limit |
| --- | --- | --- |
| strength, body, mind; speed, traits | Port stat scale 4; scale 2 | Port stat conversion, including signed penalties |
| damage | Damage affecter, range collapsed to its mean | Integer rounding differs |
| atk_damage, atk_damage_scale | Damage additive or scale; source minimum | PC merges stages; combined terms need not commute |
| def_damage | HP subtraction; scoped form uses def_damage_scope | Scale/fractional rounding differs |
| critical | 0.02 probability per source rank | Target structure eligibility differs |
| accuracy | 0.02 non-melee critical probability per rank | This is not attack rating; structure eligibility differs |
| deflect_damage | Percent divided by 100 | Context scopes retained |
| health_regen | Rate plus maximum-health cap | Delay, tick scheduling and cap stacking differ |
| energy_regen | Source multiplier | Mind factor and integer rate differ |
| move | Source movement multiplier | PC total cap is 2.5 |
| def_knockback, def_pain | Source multiplier | Corresponding incoming/animation factors |
| atk_knockback_scale | Source minimum multiplier | Name selects multiplication |
| drain_time | Duration multiplier | Requires an attached drain-victim powerup |
| power_cost | Source multiplier with scope | Corresponding cost-query contribution |
| xp | Kill-XP multiplier | PC direct XP awards bypass the multiplier |
| reflect_damage (chance 100) | Fixed additive return plus zero scale | Reflection stage, flags, rounding and stacking differ |
| reflect_damage (chance below 100) | The same record at the expected value (chance x amount) | XML1 rolls per hit; the record always returns the mean, with no gate (a gate would be a lockstep draw) |
| special / damageaddattack | `class="add_attack" damagetype` with a flat `special` affecter (the shipped XML2 gear's form) | PC merging with same-type damage and its damage mods; the source damage mod is not carried |
| none / DamageAddBleed | `class="add_harming" radiation="false" damage time` (the shipped bleed gear's form) | XML1 tick, stacking and lifetime are code and are not reproduced |
| def_damage_scale (unregistered), additive def_stun 0 | No record | The original does nothing either |

Relevant consumers: original bonus parser/table 0x946f0/0x44e8c8; PC affecter parser 0x534d90 and cache 0x53a1a0;
original/PC flat-defense paths 0x45260/0x437490; original critical branches 0x5c020 and PC roll 0x452f20; original
deflection 0x43fa0 and PC query 0x435762; original reflection 0x44168 and PC path 0x436ae0; original regeneration
0x3a950 and PC rate/cap calculation 0x42cc60. The two secondary-damage forms are the ones the shipped XML2 item table
already uses; whether the PC consumers honour the scopes the converter puts on them is a live check of the bonus step,
not something the builder can prove. No bonus of this table has live acceptance evidence yet.

## Budgets and validation

The legacy table has 88 definitions and 410 records; the economy appends 97 definitions with 130 records and
rebuilds the 19 rewards (36 records before, 32 now), so a build has 185 definitions and 536 records (`V-LOOT` prints
the numbers), far under W2's 1024 / 4096. Own slots per definition stay within eight and no own
record is the 0xffff sentinel. `V-LOOT` re-derives the accounting from the source: all 132 definitions, the sidecar
field for field, the Forge catalog per tier (18 / 37 / 52 / 69 / 85), the drop pools per tier and bucket, the Grab Bag
pools, the 168 powerups, single-valued records, capacities, references, text, the approximations file both ways and the
number of PC treasure entities in the converted maps. The generated files are private output: do not add them, the
sidecar or a build to Git.

Developer build (owned inputs only):

```text
python tools/build_xml1.py --sources prepared --cache <cache> --base <install> --out <out> --no-movies --jobs 2 --save-layout w2 --loot xml1
python tests/unit/run.py
python tools/check_no_game_content.py --all
```

Off equivalence: a build without `--loot xml1` must equal a fresh build of the base commit, file for file, including the
save catalogue and binds. The catalogue is the reason the master `tools/lcsave/data/catalogue.json` is not edited: its
entries are all written to `catalogue.lcc`, so a build with the option numbers its keys on a copy
(`loot.derived_catalogue`: the master plus the build's new keys in table order, the rebuilt rewards marked
`own_rebuilt`). A release that ships the economy commits the same ids with `python -m lcsave catalogue --build <out>
--previous <master> --append-only --own-rebuilt-ledger <out>/_build/loot.json`.
