# Remaining weapon-brain NPCs: static campaign priority

Revision numbers below are the unreleased candidates' (8, 9). The officer's
brain ships as gameplay rule 16 **revision 10** (XML2 Fix 1.8.0-beta.6,
Legends Classic 0.4.0-beta.6; research/npc-semi-auto.md).

The officer's revision 8 rerun is recorded in XML2 Fix commit `1401b3f`:
original and candidate each fired 49 shots in 45 game seconds, with median gaps
0.912/0.910 seconds. That result covers one discrete projectile family only.
This follow-up is static analysis; no additional NPC restoration or game launch
was performed.

## Ranking method

Rank by **placed spawner instances in campaign-reachable maps**, then by map
coverage for equal counts. Equal placement counts are tied. This is a reproducible
exposure proxy, not an assertion about the number of enemies in a playthrough.

The census resolves each `entinst`/`inst` against its local entity definition
and the global entity tables, applies instance attributes, and matches `character`
case-insensitively to the owned source NPC weapon declarations. It uses
`research/sweep/graph.json`'s 162 New Game reachable maps; all 210 packaged maps
were also checked. Story training maps remain included when campaign reachable;
standalone arenas, demos and unreachable maps do not contribute. Language copies,
character precaches and unused entity definitions are not counted as placements.

The nineteen remaining declarations account for 476 placements in 41 maps. All
campaign source maps were present; no spawner-like instance was unresolved.
The one conflicting entity definition concerned an inventory item, not an NPC.
No literal script/inline `spawn` or entity spawn edge targeting these holder
templates added further cases. The two zero rows have no map definitions or
placements even outside the campaign graph. This is not a general proof about
computed script names, arbitrary revisits or dynamic activation counts.

`Budget` below sums positive authored `actcountremove` limits. `+ ? (N)` means
N placements lack a positive explicit limit. These limits do not prove that all
activations occur or spawn successfully. For example, the base flamethrower has
only 2 placements but limits totaling 18 activations; the MP5 soldier has 155
placements and 332 activations. A literal enemy-count ranking would require
tracing encounter scripts and player routes. Placement rank is kept explicit
rather than silently treating those limits as observed encounters.

## Ranked handoff

All rows need the shared restoration below plus their listed family work.

| Rank | NPC | Placements | Maps | Budget | Campaign areas | Family / special handling |
|---:|---|---:|---:|---|---|---|
| 1 | GRSO_mp5 | 155 | 13 | 332 | Arbiter 85, sewers 70 | MP5; repeat-spawn/actor-incarnation coverage |
| 2 | HAARPSoldier | 78 | 9 | 102 + ? (1) | HAARP | MP5; retain scripted visibility/activation |
| 3 | grso_laserb | 46 | 3 | 46 | Hive 31, Weapon X 15 | Laser |
| 4 | NukeGuard | 34 | 4 | 34 | Nuclear plant | MP5; preserve spawner grenade override/moveset |
| 5 | grso_officer | 26 | 11 | 26 | Arbiter 18, sewers 5, Weapon X 3 | Nullifier; leader, incendiary grenade |
| 6 | grso_captain_b | 23 | 5 | 23 | Hive | Knockback; leader, flashbang |
| 7 | grso_stealth | 22 | 2 | 10 + ? (12) | Mansion invasion | Laser; preserve stealth/reveal moveset |
| 8 | Police | 19 | 2 | 19 | NYC flashback | Pistol; hero team, different primary handler |
| 9 | grso_flamethrowerb | 12 | 4 | 12 | Hive | Flame; preserve encounter spawn scripts |
| 10 | grso_captain | 11 | 3 | 11 | Hive 7, sewers 4 | Knockback; leader, flashbang |
| 11 | GRSO_commander | 10 | 4 | 10 | Sewers 6, Weapon X 4 | Lightning; leader, grenade |
| 12= | HAARPFlamethrower | 9 | 5 | 10 | HAARP | Flame; scripted activation/release |
| 12= | WeapXGuardLeader | 9 | 2 | 9 | Weapon X | Lightning; leader, grenade |
| 14= | grso_officerb | 7 | 3 | 7 | Weapon X | Nullifier; leader, incendiary grenade |
| 14= | WeapXGuard | 7 | 1 | 7 | Weapon X | MP5; scripted visibility |
| 16 | grso_superlaserb | 6 | 1 | 6 | Weapon X | Super laser |
| 17 | grso_flamethrower | 2 | 2 | 18 | Sewers | Flame; repeated teleport spawners |
| 18= | grso_laser | 0 | 0 | 0 | None found | Laser; synthetic/owned-source fixture before opt-in |
| 18= | grso_superlaser | 0 | 0 | 0 | None found | Super laser; synthetic/owned-source fixture before opt-in |

## What each family still needs

| Family | Source timing/range facts | Required restoration and acceptance |
|---|---|---|
| MP5 | Range 550; recoil 0.16; burst 1.5; rapid-fire flag | Restore original bullet aiming and rapid-fire/burst decisions, then the source input/recoil behavior. Preserve authored burst events and distinguish per-entry recoil from intra-animation shots. Test repeated spawns as well as steady fire. Four rows above share this work. |
| Laser / super laser | Range 550; recoil 0.17; burst 1.5; accuracy 5; no rapid-fire flag | Restore the bullet-specific aiming/firing branch and source accuracy semantics; do not route these through the officer's non-bullet fallback. Validate the source semi-auto entry/chain behavior alongside authored burst moves. Stealth must retain its reveal behavior. Five rows share these semantics, with separate weapon effects/damage. |
| Nullifier | Range 550; recoil 0.7; warm-up 0.5; omitted burst defaults to 1 | Restore a distinct warm-up deadline and charge lifecycle before firing, including interruption and release. Preserve the nullifier's existing effect/attack conversion and leader/grenade behavior. Two rows. |
| Knockback | Range 550; recoil 0.8; warm-up 0.5; default burst 1 | Restore charged projectile admission and cancel/restart timing, then validate projectile events independently of recoil. Preserve leader and flashbang choices. Two rows. |
| Lightning | Range 550; recoil 0; warm-up 0.6; burst 2.5; continuous beam | Add a family contract that permits genuine zero recoil, restores warm-up plus held-beam start/update/stop and firing/pause windows, and measures damage/effect cadence. Schema 2's positive-recoil restriction intentionally excludes it. Two rows. |
| Flame | Range 275; recoil 0.03; warm-up 1; burst 3.5; continuous | Restore the shorter weapon brain range, charge and continuous-fire/sweep decisions; preserve and compare `ch_constantbeam` tag execution, stop/release and damage ticks. The builder's inserted 0.1-second beam interval is not proof of source parity. Three rows. |
| Pistol | Range 550; recoil 0.2; burst 1.5; source primary has no semi-auto handler | Restore bullet brain/range and directly compare the original default-primary/input path. Do not manufacture a `ch_weapon_semi_auto` declaration merely to fit the current exporter. Retain hero-team targeting and validate against enemies. One row. |

## Shared implementation boundary

The original initializer selects a weapon brain independently of ordinary AI
class (`0xfd330`), reads range from the weapon prototype (`0xfd3ff`), and creates
the brain (`0xee060`). These declarations need that selection/range restoration,
source leader semantics, and their family-specific decision/input path. The PC
ranged constructor is `0x518090`. Preserve source-authored powers and grenades;
remove only converter-added gun lottery capabilities when the corresponding
source decision path has been restored and tested.

The builder already converts weapon hits, effects and sounds in
`tools/xml1build/weapons.py`; `combat_events.py` records the missing semi-auto
handler. `AI_TYPE`/`AI_REUSE` currently make converted shots available through
the generic PC power picker. This supplies attacks, not the original weapon
brain. `charge_triggers()` schedules charge effects at
`max(0, first_shot_time - warmup)`; it does not implement an actor-owned warm-up
gate. Continuous flame trigger conversion likewise does not establish the
original beam lifecycle or AI hold duration.

The existing schema 2 descriptor contains only actor identity, recoil, range,
burst and leader. Expanding it must explicitly represent and fingerprint the
new family semantics (bullet/rapid, warm-up, continuous, accuracy and any
additional required source fields), with strict per-family eligibility. Do not
simply relax exclusions and apply the officer implementation to all nineteen.
Use builder data where PC events express the source behavior; retain guarded
engine compatibility paths for the missing state/decision semantics.

These are further semantics of existing NPC-combat rule 16. They need a future
negotiated rule revision/fingerprint update, not an unassigned new rule ID.
OFF must continue to install no weapon patches and retain released rule values.
Each family needs original-vs-PC decision, entry, fire, interruption and
completion observations; separate melee, low/full-energy, camera eligibility,
source leader/grenade, transaction rollback, OFF-byte and peer-agreement gates.
No new revision number, normal-build enablement or gameplay implementation is
introduced by this document.

Private audit: `re/r5_campaign_weapons.py` writes
`evidence/r5-campaign-weapons.json`, including source hashes, per-map placements,
activation-limit distributions and all excluded-map counts. The table above
contains interoperability findings, not copied game definitions or assets.

## Officer revision 9 findings that apply to every family (2026-10-24)

From the owner's original S2 ring (xml2-fix `docs/npc-weapon-round6.md`): the
original officer never runs the weapon brain's burst/pause branch (`0xefc4a`);
its brain holds power+fire on every update through the held-fire branch
(`0xef8df..0xef981`) and the shot cadence is only the recoil gate. Two XML2-only
behaviours had to be undone for listed weapon NPCs: the power decision
(`0x518770`) returns false after pressing a power, so the same update adds held
fire (the original returns true, `0xef5d2`), and the attack-state update returns
before the brain while the actor is input locked in a flagged move
(`0x512f01..0x512f14`; absent from the original `0x10ad70`), which let the grenade
move finish instead of being held. Before restoring another family, check in its
original ring which brain branch it actually runs and whether its timers move:
do not assume the branch from the weapon type. The builder contract (schema 2) is
unchanged by revision 9; the burst duration stays in the fingerprint but the
officer path does not use it.
