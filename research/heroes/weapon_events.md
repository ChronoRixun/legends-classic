# XMen2.exe combat events for XML1's weapons (2026-09-30)

What the retail XML2 PC exe (`XMen2.exe`, PE base 0x400000, RTTI present) does with the combat-event types the XML1
weapon port needs. Every address was read in `research/scripts/xml2_text.asm` and checked in Ghidra decompiles of
the retail exe (`research/characters/ghidra/proj`, `run_decomp.sh`). "Verified" = read in the code; "inferred" =
a conclusion from it; "unverified" = not traced in this pass. Companion of `tools/xml1build/weapons.py` (SPEC 29)
and of the engine facts in `combat_events.py` / `npc_values.py` (SPEC 22, 24).

## 0. Mechanics shared by every event type

- The factory 0x4faea0 picks the constructor by type name; each constructor stores the class vtable (verified in
  the ctor bodies). The vtable layout of `CCombatNodeEvent` (slots used below): +0x04 fire on an actor, +0x0c parse
  the XML node (0x4f83f0: walks the node's attribute pairs and calls +0x10 for each), +0x10 parse one attribute
  (`_stricmp`, case-insensitive), +0x14 prepare (mode 0 at load: resolves effect / sound names to handles), +0x1c
  copy from the parent event, +0x2c (attack events) perform the attack. Attack events (`CCEAtk` and subclasses)
  override +0x0c with 0x4dbb90, which also hands the node to 0x44ff00 for the `<damageMod name=...>` children.
- Attribute chains. An unknown name falls through to the parent class's parser; the last fallback 0x4f8240 reads
  `time` (0..1 of the animation, else 0xff = never; `-1` is what a tag-only trigger carries), `type`, `animbased`,
  `timebased`, `only_non_looped`, `only_looped`, `tag`. 0x4dadb0 adds `powerusage` (talent value `%name`, else a
  number) and `poweraifree`. Unknown attributes are ignored without a message.
- Numbers: `damage` / `knockback` / `life` / `count` go through the talent-value manager 0x4c1dd0 vt+0x18
  (`%name` -> talent id | 0x8000, else the value table 0x4c4870: a number, "min max", or one of DMG2 DMG3 DMG4 K2 K3;
  anything else is 0 - SPEC 24). `damagelevel`, `arc`, `angle`, `pitch`, `timeinterval` go straight to 0x4c4bb0
  vt+8 (the same 0x4c4870). So XML1's `L1`..`L5`, `K10` must be numbers before the style (or the entity file,
  section 4) reaches the exe.
- Names: `effect`, `beameffect`, `hiteffect`, `spawneffect`, `entity`, `filename`, `sound` are stored as string ids
  (0x41b120 / 0x41a500) and resolved at prepare time.

## 1. ce_atk_weap (shared event `weapon_fire`)

**In XMen2.exe `ce_atk_weap` is not an attack: it is constructed as a `CCESound`.** The factory branch 0x4fb550
jumps to 0x4fb01e, the `ce_sound` branch's constructor call (0x4f9540, vtable 0x692404 = `CCESound`; the same
0x4f9540 is the fallback at 0x4fbced). No `*Weap*` class exists among the 643 RTTI names of the exe, and no
`CWeapon` either. The event therefore parses exactly `ce_sound`'s attributes (section 5): `sound`, `loop_type`,
`loop_timeout`, `debounce`, `powerusage`, `poweraifree`, `time`, `tag`. `attacktype`, `damage`, `damagescale`,
`maxrange` on the shared `weapon_fire` (XML2's own shared_combat_events.xmlb still carries them) are ignored.
Firing it (0x4e8a70) spends `powerusage` and plays `sound` if set - the shared event sets none, so a `weapon_fire`
trigger does nothing at all: no hit-scan, no projectile, no damage, no effect.

The per-actor weapon record does not exist on this exe:
- stats `weapon="..."` (0x4ba373 `_stricmp`) branches straight to 0x4bb2e7 `return true`: accepted, nothing stored
  (the "flag" is only the parser's success value). `weapon` also appears at 0x4633ad in a list of entity-instance
  attribute names registered by 0x463850 (purpose not traced; no reader of a weapon table follows from it).
- `data/weapons/weapons.xmlb` is the 37-byte empty `<weapons_list/>`; the exe holds none of XML1's weapon strings
  (`weapons_list`, `muzzlefx`, `muzzleaccfx`, `firesound`, `recoiltime`, `continuousbeam`, `wp_*` names: all absent
  from the binary; the only `wp_*` strings are waypoint names).

So a weapon's muzzle flash, tracer, impact and sounds must be separate `effect` / `sound` / `effect_sound` triggers,
and its hit must be a `beam` or `projectile` event. `ch_weapon_semi_auto` is not a registered handler (runs as
`%default%`, SPEC 22).

## 2. ce_atk_beam (shared event `beam`)

Class `CCEAtkBeam`, ctor 0x4fab80 (vtable 0x692a50), attribute parser 0x4dd250 -> 0x44f9f0 -> 0x4dc810 (ce_atk) ->
0x4dbf70 (attack data) -> 0x4dadb0 -> 0x4f8240. Defaults from the ctors 0x4fab80 / 0x4dc5d0.

| attribute | type / units | default | parsed at |
|---|---|---|---|
| `damage` | number or "min max" or `%talent` | 0 | 0x4dbf70 -> 0x4dbea0 |
| `mindamage`, `maxdamage` | number | 0 | 0x4dbf70 |
| `knockback` | number / `%talent` | 0 | 0x4dbf70 -> 0x4dad70 |
| `damagelevel` | number (byte) | 1 | 0x4dbf70 |
| `attacktype` | direct punch kick throw blast projectile beam crush psionic (table 0x6d6dc8); unknown -> punch | punch | 0x4dbf70 -> 0x44ebc0 |
| `damagetype` | flag names, space-separated (table 0x6d61c8: dmg_physical dmg_energy dmg_fire dmg_electricity dmg_cold ...) | dmg_physical | 0x4dbf70 -> 0x43bd70 |
| `damagescale` | none / normal / difficulty (table 0x6d6dec) | none | 0x4dbf70 -> 0x44ec00 |
| `selfeventtag[1,2]`, `victimeventtag[1,2]` | tag number | 0 | 0x4dbf70 |
| `piercechance` | number | 0 | 0x4dbf70 |
| `maxrange` | number / `%talent`; the beam length (inferred) | 0 | 0x4dc810 |
| `angle`, `arc` | degrees (arc stored as cos) | 0 | 0x4dc810 |
| `height`, `verticalrange`, `index` | number | 0 | 0x4dc810 |
| `hiteffect`, `hitenemyeffect` | effect path (section 5); enemy one defaults to `hiteffect` at prepare 0x4dc640 | none | 0x4dc810 |
| `fxlevel` | number | 0 | 0x4dc810 |
| `forceretargeting`, `tiles` | bool | false | 0x4dc810 |
| `attack_bone_pos` | "x y z" from the actor; `attack_bone_angles` "x y z" degrees: the beam origin / direction | actor | 0x44f9f0 |
| `beambolt` | one of the 13 bone names (table 0x6e25f0: Bip01 Pelvis, Spine1, Spine2, Neck, Head, L/R Hand, L/R Toe0, L/R UpperArm, L/R Forearm) or `none`; the bolt record at +0x18 also receives `attack_bone_pos/angles` | Bip01 Head (ctor 0x4fabc1 initialises the record with index 4) | 0x4dd250 -> 0x575da0 |
| `beameffect` | effect path drawn along the beam | none | 0x4dd250 |
| `spawneffect` | effect path at the origin | none | 0x4dd250 |
| `pierce` | bool: hit every entity on the ray, else the first | false | 0x4dd250 |
| `radius` | number (byte): beam thickness for the trace | 12 | 0x4dd250 |
| `pitch` | degrees | 0 | 0x4dd250 |
| `noaimfx` | bool: `beameffect` is not aimed along the ray; it is played on the actor at `beambolt` instead (0x4dcfe0 tail) | false | 0x4dd250 |
| `useboltinfo`, `onlynoenemypitch`, `fxrequireshit` | bool | false | 0x4dd250 |
| `split_count`, `split_damage` | number: extra beams fanned to other targets with their own damage | 0 | 0x4dd250 |
| `powerusage`, `poweraifree`, `time`, `tag`, ... | section 0 | | 0x4dadb0, 0x4f8240 |
| `<damageMod name="dmgmod_*"/>` children | bits of the attack data (+0x10) | inherited from the parent | 0x4dbb90 -> 0x44ff00 |

How it fires (verified): one trigger = one call. 0x4dcbd0 spends `powerusage`, builds the attack context
(0x4dc3e0) and calls 0x4dcfe0, which hands the attack system singleton (0x7179a8, vtable 0x685a64) +0x2c = 0x451cc0
the bolt record, radius, effects, pitch, pierce and split data. 0x451cc0 traces one ray from the bolt / attack_bone
position, loops over the entities it crosses, applies each hit through 0x453160 (stopping at the first unless
`pierce`), spawns `beameffect` once through the effect manager (0x6f3c50, vt+0x34) at the origin oriented along the
ray, `hiteffect` at the hit point, and recurses for `split_count`. The trace and the damage are instantaneous;
there is no duration attribute - how long the beam stays visible is the effect file's own lifetime. Repeated beams
(XML2's ps_pyro flame: 7 `flame_dmg` triggers 0.08 s apart, `noaimfx` + `useboltinfo` + `pierce`) are the retail
way to show a sustained stream.

`damagescale` / `damagelevel` consumers were not traced (unverified). Retail NPC beams use
`damagescale="difficulty"` (ps_shocktrooper), hero ones `"none"`; keep the retail NPC form.

## 3. ch_constantbeam + ce_set_constantbeamdata

- Handler `ch_constantbeam` (registered 0x4fe603, class `CCHConstantBeam`, vtable 0x6938c4). Its per-frame update
  0x4eee00: while actor flag [+0x748] bit 0 is set and the clock has passed [+0x5e8], it sets the next tick to now +
  random([+0x74c], [+0x74c] + [+0x750]) and fires the current move's triggers with **tags 150, 151 and 152** (0x96,
  0x97, 0x98 at 0x4eee5c / 0x4eee81 / 0x4eee9e), each through its normal fire (vt+4). +0x04 (0x4eede0) zeroes the
  clock when the move starts; +0x08 (0x4eedd0 -> 0x4eed00) stops the loop sound.
- Event `ce_set_constantbeamdata` (class `CCESetConstantBeamData`, ctor 0x4f9a90, vtable 0x692560). Attribute
  parser 0x4e8960 reads only: `setbeam` (bool), `timeinterval` (seconds, float, default 0), `intervalrandom`
  (seconds added at random, default 0), then 0x4f8240 (`time`, `tag`, ...). **Not** `powerusage`, not any damage,
  effect or range attribute: the attributes `weapons.py` currently puts on the setbeam trigger (`damage`,
  `damagetype`, `maxrange`, `beameffect`, `hiteffect`) are silently ignored (verified: 0x4e8960 falls to 0x4f8240,
  not to 0x4dadb0 / 0x4dc810).
- Fire 0x4e8a20 copies `setbeam` into actor [+0x748] bit 0, `timeinterval` into [+0x74c], `intervalrandom` into
  [+0x750]; `setbeam="true"` also calls 0x4eec70(actor, 0), which looks up the move's trigger with **tag 100** and,
  if it is a `CCESound`, starts its sound as a 3D loop at the actor (sound manager 0x592480 vt+0x4c; handle kept at
  [+0x6d8]); `setbeam="false"` stops that loop (0x4eed00).
- With `timeinterval` absent the next tick is now + random(0, 0): the tagged triggers fire **every frame**.

So the constant beam draws and damages with nothing of its own: it is a timer that re-fires whatever triggers carry
tags 150-152 (and loops the tag-100 sound). XML2 retail uses neither the handler nor the event (0 of 173 style
files). XML1's flame_sweep put `weapon_fire` on tag 150 - on XMen2.exe that is a silent `CCESound` (section 1), so
the flame_sweep move cannot deal damage as shipped. The report that the ported flamethrower "burned invisibly" is
not explained by this code (unverified; if it reproduces, the damage comes from something else - worth one HP watch
on a build without `weapons.py`'s replacement).

## 4. ce_atk_spawn_proj (shared event `projectile`)

Class `CCEAtkSpawnProjectile`, ctor 0x4f87b0 (vtable 0x6920a0) over `CCEAtkSpawn` 0x4e3800. Node parser 0x4df620
(attack data + damageMods, plus `Explode`-prefixed damageMods). Attribute parser 0x4e2cb0 -> 0x44f9f0 -> 0x4dc810
-> 0x4dbf70 -> 0x4dadb0 -> 0x4f8240; all of section 2's attack-data rows apply (`damage`, `damagetype`,
`damagescale`, `damagelevel`, `knockback`, `maxrange`, `attack_bone_pos/angles`, damageMods).

| attribute | type / units | default | parsed at |
|---|---|---|---|
| `filename` | entities file: `data/entities/<filename>` (prefix string at 0x4e0870, loaded at prepare) | none | 0x4e2cb0 |
| `entity` | the `<entity name=...>` of that file to spawn | none | 0x4e2cb0 |
| `count` | number / `%talent`: projectiles per fire (spread fan computed in 0x4510a0) | not established (unverified); retail always sets it | 0x4e2cb0 -> 0x4abfd0 |
| `speed` | integer, units/s (short) | 0 | 0x4e2cb0 |
| `spread` | integer degrees (short), the fan for `count` > 1 | 0 | 0x4e2cb0 |
| `life` | number / `%talent`: projectile lifetime override | entity's | 0x4e2cb0 -> 0x4df700 |
| `maxinstances`, `numbounces` | integer | none | 0x4e2cb0 -> 0x4df670 |
| `actorbolt` | bone name (table 0x6e25f0) / `none`: spawn point | actor position | 0x4e2cb0 -> 0x575da0 |
| `offset` | "x y z" integers, local to the facing | 0 0 0 | 0x4e2cb0 |
| `angoffset` | "x y z" degrees added to the direction | 0 | 0x4e2cb0 |
| `nudgeforward`, `randomvelocity`, `fxlevel`, `fire_event` | integer | 0 | 0x4e2cb0 |
| `targetable` | bool: aim at the current target (ps_mercenary) | false | 0x4e2cb0 |
| `lobattarget`, `fulltargeting`, `center`, `aimatorigin`, `usedamageasexplodeonly`, `useboltangles`, `pierce`, `tracecheck` | bool | false (tracecheck true: ctor +0x49 = 0x80) | 0x4e2cb0 |
| `explodedamage`, `explodedamagetype`, ... | the attack-data names with the `Explode` prefix | | 0x4e2cb0 -> 0x4dbf70 |

Fire 0x4e24b0 (verified): position from `actorbolt` / attack_bone / actor + `offset`, direction from the facing or
the bone + `angoffset` (towards the target when `targetable`), then the attack system +0x28 = 0x4510a0 spawns
`count` entities with `speed` and `spread`, each carrying the event's attack record (0x4dc230). The projectile
entity class (`CProjectileEntity`, attribute parser 0x49b900) reads its own `damage` (0x4c4bb0 -> rolled once
between min and max at spawn, 0x49bf35..0x49bf57), `damagetype`, `damagelevel`, `damagemods`, `knockback`,
`speed`, `pierce`, `dieoncontact`, `explodeoncontact`, `exploderadius`, `explodedamage`, `loopfx`, `deatheffect`,
`deathsound`, `homing` and more; which of the two damage records (event or entity) wins on contact was not traced
(unverified). XML2 retail puts the damage on the event and leaves it off the entity (ents_merc, ents_toad); XML1's
`ice_bullet` / `bullet_time` carry `damage="L3"`/`"L4"` and `knockback="60"`/`"K10"` on the entity, which read as 0
on this exe unless resolved to numbers (section 0).

`ProjectileEnt`, `Health`, `FiringRate` (parser 0x4e3476) belong to another spawn subclass (the sentry; which one is
unverified), not to `projectile`.

## 5. ce_effect / ce_sound / ce_effect_sound

| event | class / parser | attributes |
|---|---|---|
| `effect` | `CCEEffectFile` 0x4e7150 -> `CCEEffectBase` 0x4e6c00 -> 0x4f8240 | `effect` (path), `ground` (bool: at ground level), `bolton_slot` (name from table 0x6d6530), `bolton_point`, `teleport_visible`; base: `bolt` (bone name, table 0x6e25f0; absent = actor position), `life` (number), `fxlevel` (0..8, else 0); plus `time`, `tag`, ... No `powerusage`. |
| `sound` | `CCESound` 0x4e8ed0 -> 0x4dadb0 -> 0x4f8240 | `sound` (name), `loop_type` start / stop, `loop_timeout` (number / `%talent`), `debounce` (seconds: 0x4e8a70 skips a replay inside it), `powerusage`, `poweraifree`. No `bolt`. |
| `effect_sound` | `CCEEffectSound` 0x4e72b0 -> 0x4e7150 | `sound`, `loop_type`, `loop_timeout` plus everything of `effect`. Fire 0x4e6fc0 = effect fire 0x4e6d30 + the sound. |

Effect paths are relative to `effects/`: the loader 0x418f80 prepends `effects/` (0x592520 with the string at
0x681ec8) and the files are `Effects/<path>.xmlb` on disk (e.g. retail `char/merc/p2_shot` = Effects/char/merc/
p2_shot.XMLB). The handle is resolved at prepare (0x4e6cb0, effect manager vt+0x1c) and played on the actor at the
bolt by the node system (vt+0x120 in 0x4e6d30). Sound names are resolved at prepare by the sound manager 0x592480
vt+0x38 (0x4e8e00); the retail form is `char/<dir>_m/<event>` (where the exe's sound banks put them is sound.md's
business, not traced here).

## 6. Damage values

- `damage="2 3"` is min 2, max 3; `damage="6"` is 6..6; `damage="%cyc_beam_dmg"` a talent value (section 0).
  `mindamage` / `maxdamage` set the halves. XML1's `L1`..`L5` read as 0 on this exe; `npc_values.resolve_style`
  already turns them into XML1's numbers in styles (SPEC 24) - the same must happen to the projectile entity files
  (section 4) if the entity's own `damage` / `knockback` are kept.
- `damagelevel` is a plain number (byte, default 1), `damagescale` an enum (none 0 / normal 1 / difficulty 2, ctor
  default none); what the hit code multiplies by them was not traced (unverified). XML2's retail NPC gun / beam
  events use `damagescale="difficulty"`, `damagelevel="1"`.
- `damagetype` names and `<damageMod>` names are the same table 0x6d61c8 (`dmgmod_no_pain` 0x80000,
  `dmgmod_auto_knockback` 8, `dmgmod_drain` 4, `dmgmod_popup` 0x10 ... all of XML1's weapon damagemods exist).

## 7. Expressing XML1 weapons (recommendation per weapon type)

Every variant style keeps XML1's moves and animations; only the triggers change (`weapons.py apply`). Value codes
are resolved afterwards (SPEC 24). Effects named below are XML1's own files (`weapons/mp5/mp5_tracer`, ...) and
must exist under the build's `Effects/` for anything to show - that is the media pipeline's check, not the exe's.

- **bullet (mp5, pistol, myst_pistol, laser, superlaser)** - per `weapon_fire`: a `beam` trigger (shared
  `beam`, ce_atk_beam) with `attacktype="beam"`, `damage` = the weapon's code, `damagetype` (laser: dmg_energy),
  `maxrange` = `range` (550), `beambolt` = `actorbolt`, `beameffect` = `muzzleaccfx` (the tracer), `hiteffect` =
  `impactfx`, `damagescale="difficulty"`, `arc="0"`, `pierce="false"`, and a `<damageMod name="dmgmod_no_pain"/>`
  child for the weapon's `damagemod`; plus one `effect_sound` (`effect` = `muzzlefx`, `sound` = `firesound`,
  `bolt` = `actorbolt`) at the same time. This is exactly what `shot_triggers` emits today, minus the damageMod child
  and `damagescale`: add both. `accuracy` has no counterpart (the ray follows the facing / aim). The 19-trigger
  cap (0x4f6aa7) rule for bursts stands.
- **beam (lightning gun, m_nullifier)** - the same `beam` form: lightning `damagetype="dmg_electricity"`,
  `beameffect` = `muzzleaccfx` (`lightning_shot`), `hiteffect` = `impactfx`; nullifier `damage="10000"`,
  `dmg_energy`, `<damageMod name="dmgmod_drain"/>` (XML1's meaning of drain on a hero is unverified on this exe -
  in-game check), `chargefx` / `chargesound` as the existing `charge_triggers`. XML1's `continuousbeam` on the
  lightning gun has no XML2 attribute; a visible sustained bolt is several `beam` triggers over the move, as
  ps_pyro does, or one with a longer-lived effect.
- **flame (flamethrower, continuous)** - keep `flame_sweep`'s handler and its two `beamdata` triggers, but: (1)
  add `timeinterval="0.1"` (and nothing else) to the `setbeam="true"` trigger - without it the tick is every frame;
  (2) replace the tag-150 `weapon_fire` by a tag-150 `beam` trigger (`time="-1"`): `attacktype="beam"`,
  `damage="L3"` (XML1's flame code; XML2's Pyro uses 15..18 per 0.08 s tick), `damagetype="dmg_fire"`,
  `maxrange="275"`, `beambolt="Bip01 R Hand"`, `beameffect="weapons/flamethrower/flame_shot"`, `noaimfx="true"`,
  `useboltinfo="true"`, `pierce="true"`, `radius="12"`, `damagescale="difficulty"` (the ps_pyro `flame_dmg` form);
  (3) a `sound` trigger with `tag="100" time="-1" sound="<firesound>"` - the engine loops it from
  `setbeam="true"` to `setbeam="false"` (0x4eec70 / 0x4eed00) - and the warm-up `chargefx` / `chargesound` as
  today. Drop the attributes `apply` now writes on the beamdata trigger (ignored). Tags 151 / 152 are free for a
  per-tick `effect` if the flame needs a second emitter. `power_attack` (handler `ch_weapon_semi_auto`,
  `%default%`) gets the bullet-style replacement with the flame's attributes.
- **projectile (freeze gun -> `ice_bullet` of freezegun_ents, knockback gun -> `bullet_time` of
  knockbackgun_ents)** - per `weapon_fire`: a `projectile` trigger (ce_atk_spawn_proj) `entity` = `projectileent`,
  `filename` = `entfile`, `speed` = `projectilespeed`, `count="1"`, `actorbolt`, `targetable="true"` (retail
  ps_mercenary), plus the attack data on the trigger: `attacktype="projectile"`, `damage` = the weapon code (L5 /
  L4), `damagetype` (dmg_cold / dmg_energy), `maxrange="550"`, `damagescale="difficulty"`, and
  `<damageMod name="dmgmod_auto_knockback"/>` for the knockback gun; the muzzle `effect_sound` as for bullets.
  Convert the two XML1 entity files to the build's entities tree with their codes resolved (`damage`, `knockback`)
  and their `model` / `loopfx` / `deatheffect` assets present. Which damage record applies on contact is
  unverified: set both to XML1's numbers so either answer is right.

Not verified in game (all of it): a GRSO mp5 soldier's tracer, impact and sound; the lightning / nullifier beams;
the flamer's visible flame, its tick rate and loop sound; a freeze / knockback bullet flying, hitting and
knocking back; whether the nullifier's `dmgmod_drain` does anything to a hero on this exe.
