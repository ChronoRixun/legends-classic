# Issue #12: delayed harm loops

Implemented and tested. Baseline: main `a5769737f1d0586d0d0cbadf4d3a71bef6b7eaae`.
CONTENT_VERSION remains 11, as requested for the unreleased content revision.

## Theory ledger

| Theory | Test / evidence | Result |
| --- | --- | --- |
| The HAARP-only workaround misses the same parser problem elsewhere. | Source scan and current dispatcher. | Confirmed: 97 baseline defects; invisible damaging NYC and Arbiter walls; zero defects in the fixed build. |
| XML1 firstact only delays the visual effect. | Read original Xbox parser and scheduled callback. | Falsified: it delays the first activation; the loop flag is parsed independently. |
| All fires that appear after circling have the same cause. | Movement / residency observations. | Not reproduced as an exact circling sequence. A separate stale-position loop failure was reproduced and corrected. |
| Setting firstact to zero preserves all timing. | Original scheduler. | Falsified: first activation advances; damage amounts and repeat intervals can remain unchanged. |
| Enabling smartfire is a faithful substitute. | SPEC 45 prior controlled test; separate XML2 code branch. | Rejected: changes damage scheduling. |

## Original timing and candidate choice

Read-only inspection of the legally owned executables, with no binary changes:

- XML1 `default.xbe`: the action parser reads loopfxstarton at `0x28c66`
  into bit 0x04 of the action flags at +0xc9. It reads firstact at `0x28d32`,
  clamps the initial activation delay to at least 0.001 seconds and schedules
  an event through `0x277e0`. The first-act event handler at `0x27550` dispatches
  the activation, using the remaining delay. The harm parser at `0x7c440`
  does not clear the loop flag. Thus the loop and first activation are independent.
- XML2 `XMen2.exe`: the action parser reads loopfxstarton at `0x41be1a`
  into bit 0x04 at +0xc5. The harm parser beginning at `0x4396a0` separately
  reads positive firstact, disables the harm entity through a virtual call at
  `0x4399c9`, clears the loop bit at `0x4399d9`, and schedules the delayed event
  through `0x439a2a`.

Implemented builder choice: set firstact to zero only on delayed, start-on, non-smart
affectableharment loops, after XML1 class remapping. Match semantics, not an
entity name, effect name, or map path. Preserve the damage, repeated activation,
collision, reaction and death fields. Preserve the HAARP placement script wrappers and extend their restart approach to source-identified relocated loops.
This loses the authored initial activation delay (one second in the scanned
matching source definitions), so the first possible damage/activation can happen
earlier. It does not claim to preserve the exact damage tick phase.

Possible companion engine fix, described only: guard the harm parser change so
the authored loop-on bit survives the positive-firstact branch for ordinary
non-smart harm entities, while retaining delayed activation. An implementation
must also test the preceding disable call, on/off timers, smartfire, extinction,
save/load, and XML2 retail hazards. Merely changing the clear instruction globally
would affect XML2 content too. No xml2-fix or executable modification is part of
this work.

## Runtime evidence and staging

Both builds use XML2 Fix 1.3.1, the shipped limits, windowed 1280x720,
pipe `impl12b` and SaveFolder `impl12b`. The DLL was not modified. Both owned
game processes are closed. Other running games were left alone.

All zone jumps, party choices, placements and enemy isolation below are **staged**.
Contact damage was produced by normal keyboard movement, never `damage()` or
health writes. No invulnerability was added for contact testing. The shipped
NYC cinematic temporarily protects the hero, then releases that protection before
the measured contact. Iceman's power was normal keyboard input, not a scripted
extinguish or entity removal. Scripts removing enemies were setup, not proof of
combat progression. These are controlled checks, not a campaign playthrough.

| Check | Setup and observed result | Local evidence in `build/evidence/` |
| --- | --- | --- |
| Negative NYC | `nyc/alison/nyc1_1_2b`, native `fire_wall01`; staged the authored move to `firewall_benches02`, positioned Wolverine outside the hazard, walked in. Health 90 -> 75 -> 51 -> 24 -> 0; flame absent. | `baseline-wall-near.*`, `baseline-wall-contact.*`, `baseline-wall-contact-movement.json` |
| Negative Arbiter | `arbiter/a_int/arb3_4`, native `fire_wall` in its authored location; zone/hero position staged. Walked toward it: 90 -> 87, then 30 during attempted retreat; floating 3 damage, flame absent. | `baseline-arb3-near.*`, `baseline-arb3-contact-damage.*`, `baseline-arb3-contact-movement.json` |
| Separate relocation control | Current-main NYC `smallfire02` has empty firstact. Staged relocation from underground to the bench waypoint left it invisible. A hide/show restart, without changing firstact or the asset, produced a visible flame. | `baseline-relocated-small-off.*`, `baseline-relocated-small-restart.*` |
| Fixed first NYC map | `nyc/alison/nyc1_1_1` street fires visible before contact. Normal movement recorded; live harm flag +0xc5 has bit 0x04 set. | `fixed-nyc1-near.*`, `fixed-nyc1-move-*`, `fixed-nyc1-live.json` |
| Fixed NYC bench | Staged invocation of the generated `meet_pyro` script, with enemies removed for isolation. After it finished, moved hero near the bench and walked in/out: 90 -> 84 -> 72. Flame and floating damage visible together. | `fixed-bench-before.*`, `fixed-bench-contact-damage.*`, `fixed-bench-contact-movement.json` |
| Fixed NYC third map | `nyc/alison/nyc1_1_3`: visible fires on both sides of the tipped police car while moving. | `fixed-nyc3-near.*`, `fixed-nyc3-movement-*` |
| Fixed Arbiter | Same native interior wall: visible before and during contact, health 72 -> 63 -> 36. | `fixed-arb3-near.*`, `fixed-arb3-contact-damage.*`, `fixed-arb3-contact-movement.json` |
| Iceman extinguish | Staged single-Iceman party, approach position and facing in `arb3_4`. Real movement closer, then NUMPAD5 followed by NUMPAD4: beam visible; fire stopped and its live entity disappeared. Walked through former hazard area at 78 HP throughout. No fire-target mutation was used. | `fixed-iceman-face-*`, `fixed-iceman-close-beam.*`, `fixed-iceman-close-end.*`, `fixed-iceman-extinguished-live.json`, `fixed-iceman-passage-movement.json` |
| Sewer fire | `sewers/hub/sewers1_1_1`, native `fire01`: visible during recorded movement near the fire pit. Party/position and AI-off isolation staged. No isolated damage-rate claim for this small fire. | `fixed-sewer-movement-*`, `fixed-sewer-around-*` |
| HAARP SPEC 45 | `haarp/ext/haarp_ext01`, native `fire_wall01`. Moved its waypoint to a clear landing-area spot and staged the unchanged hide/act/move/show block. First approach was blocked by the landing platform; moved the test waypoint sideways and restarted the loop. Real contact: visible wall, floating damage, 72 -> 48 -> 30 after retreat. Natural flamer encounter not claimed. | `fixed-haarp-active.*`, `fixed-haarp-clear-near.*`, `fixed-haarp-clear-contact-damage.*`, `fixed-haarp-clear-contact-movement.json` |
| Save/reload | Opened extraction menu by script beside burning NYC bench (staged menu invocation); used normal Save Game UI, then normal pause-menu Load Game UI. Reload returned to the same position and 72 HP, with fire still burning. Subsequent normal movement succeeded. Own `saveslot0.save` verified on disk (195716 bytes). | `fixed-save-confirm.*`, `fixed-load-confirm.*`, `fixed-reload-settled.*`, `fixed-reload-movement-*` |

Earlier baseline probes of small NYC/Arbiter fires did **not** isolate hazard damage;
nearby enemies confounded some HP changes, and a bad staging position caused a
fall/death. Those attempts are not counted as proof. The later wall tests above
provide the damaging negative controls. There is no precise damage-rate benchmark:
contact durations and tick phase differ, and damage schedules were not rewritten.

The exact “appears only after circling” symptom remains unconfirmed. Walking around
the initially tested fires did not establish spontaneous recovery. The stale-world-
position failure is independently confirmed, but attributing every intermittent
visibility report to it or to smart-entity streaming would exceed the evidence.

## Automated validation

- Baseline suite: 234 passed, 0 failed. Final suite: 241 passed, 0 failed.
- Full baseline and fixed builds from the owned disc and PC install: exit 0;
  each verified 21343 files and reported 269 warnings. Fixed validation: zero errors.
- Direct V-TBD run on the baseline decoded output: **97 errors** (identical
  localized twins counted once). Full fixed-build V-TBD: **0 errors**.
- Independent output audit: **97 definitions in 55 files (53 map zones/aliases,
  two entity libraries)** changed only firstact 1 -> 0. No remaining dead forms.
- Output script comparison: exactly four changed scripts, eleven placements;
  existing six HAARP exterior placement scripts byte-identical.
- Zones pipeline self-test: PASS. Scripts pipeline self-test: T1-T7 PASS.
- Content guard and its 31-case self-test passed; staged/public-file check is
  repeated before commit/push. Game-derived evidence is ignored and never attached.

Local logs: `build-baseline-native.log`, `build-fixed.log`,
`build/unit-final.log`, `build/zones-selftest.log`, `build/scripts-selftest.log`.
Detailed local inventories: `build/evidence/baseline-audit.json`, `final-audit.json`,
`changes.json`, `changed-scripts.json`, `validator-negative.json` and the fixed
build's `_build/validate.json`.

## Script relocation changes

The plan derives named instances from source maps in the script's directory;
no new zone-name or fire-name allowlist is added. Authored-off loops, smartfire,
explicitly invisible definitions and unrelated entities are left alone. Conflicting
instance names in the same namespace fail the build. This does not infer dynamic
script targets or cross-directory contexts. The full build's existing script-pool
checks passed with the added statements.

| Source zone | Generated script | Relocated instances |
| --- | --- | --- |
| `nyc/alison/nyc1_1_2b` | `nyc/alison/meet_pyro.py` | `smallfire01`, `smallfire02`, `smallfire03`, `fire_wall01`, `fire_wall02`, `fire_wall03` |
| `hive/h_int/hive1_2_1` | `hive/h_int/barrel_kicker.py` | `the_fire` |
| `hive/h_int/hive1_2_3` | `hive/h_int/spawn_n_shoot.py` | `fire_wall` |
| `haarp/int/haarp2_6` | `haarp/int/burndoor.py` | `fire_wall01`, `fire_wall02` (the latter moves twice) |

Hive and HAARP interior script changes were validated structurally and by the
pipeline; those encounters were not played. The six existing HAARP exterior
placements keep SPEC 45's stricter shape validation and unchanged output.

## Verification commands

From the repository root:

```text
python tests/unit/run.py
python tools/check_no_game_content.py --all
python tools/check_no_game_content.py --self-test
```

From `tools/`, build with owned inputs into a new output folder, then run:

```text
python -m xml1build.zones_selftest <out> --base <XML2-install>
python -m xml1build.scripts_selftest --out <out> --base <XML2-install>
```

Check `_build/validate.json` for V-TBD = zero. For runtime verification, install
the harness with an isolated pipe/save folder and XML2 Fix 1.3.1; repeat the staged
setups above, using normal movement for damage and the actual Iceman power for
extinguishing. Keep all game-derived output local.

## Files changed

`CHANGELOG.md`, `REPORT.md`, `tests/unit/test_fire_walls.py`,
`tests/unit/test_harm_loops.py`, `tools/xml1build/SPEC.md`,
`tools/xml1build/fire_wall_scripts.py`, `tools/xml1build/scripts.py`,
`tools/xml1build/validate.py`, `tools/xml1build/x1schema.py`.
No CONTENT_VERSION bump, xml2-fix change, source-install change or game asset is
included. The remaining uncertainty is exact intermittent circling/streaming
behavior and natural end-to-end encounters, not the reproduced startup and
relocation failures.

## Changed definitions

Every listed definition changes only `firstact` from 1 to 0. Localized XMLB/engb pairs are counted once; both halves are written. Zone aliases are listed separately.

| Output file | Entities |
| --- | --- |
| `Data/entities/grenade_ents.XMLB` | `fire_glob` |
| `Data/entities/sentin_grenade_ents.XMLB` | `gas_cloud` |
| `Maps/arbiter/a_int/arb2_1.engb` | `fire`, `fire_big02` |
| `Maps/arbiter/a_int/arb2_2.engb` | `fire` |
| `Maps/arbiter/a_int/arb2_3.engb` | `fire` |
| `Maps/arbiter/a_int/arb3_1.engb` | `fire_deck_lrg01`, `fire_wall01` |
| `Maps/arbiter/a_int/arb3_2.engb` | `fire02` |
| `Maps/arbiter/a_int/arb3_3.engb` | `fire02`, `fire03`, `fire_big01` |
| `Maps/arbiter/a_int/arb3_4.engb` | `fire_wall`, `fire_wall02` |
| `Maps/arbiter/arb_fd1.engb` | `fire_deck_lrg`, `fire_deck_sm` |
| `Maps/arbiter/arb_fd2.engb` | `fire_deck_huge`, `fire_deck_lrg`, `fire_deck_sm` |
| `Maps/arbiter/deck/arb_fd1.engb` | `fire_deck_lrg`, `fire_deck_sm` |
| `Maps/arbiter/deck/arb_fd2.engb` | `fire_deck_huge`, `fire_deck_lrg`, `fire_deck_sm` |
| `Maps/astroid_m/visit1/arb_fd1.engb` | `fire_deck_lrg`, `fire_deck_sm` |
| `Maps/astroid_m/visit1/arb_fd2.engb` | `fire_deck_huge`, `fire_deck_lrg`, `fire_deck_sm` |
| `Maps/astroid_m/visit1/asteroid2_2.engb` | `fire_deck_sm` |
| `Maps/astroid_m/visit1/asteroid2_3.engb` | `fire_deck_sm` |
| `Maps/demo/a_int/arb3_1.engb` | `fire_wall01` |
| `Maps/demo/deck/arb_fd1.engb` | `fire_deck_lrg`, `fire_deck_sm` |
| `Maps/demo/hub/sewers1_1_1.engb` | `fire02`, `fire_barrel15` |
| `Maps/demo/hub/sewers1_1_2.engb` | `fire02`, `fire01`, `fire_barrel03`, `fire_barrel05` |
| `Maps/haarp/ext/haarp_ext01.engb` | `fire` |
| `Maps/haarp/ext/haarp_ext02.engb` | `fire` |
| `Maps/haarp/ext/haarp_ext03.engb` | `fire` |
| `Maps/haarp/int/haarp2_6.engb` | `fire_blob`, `fire_wall01` |
| `Maps/hive/h_int/hive1_2_1.engb` | `fire_wall` |
| `Maps/hive/h_int/hive1_2_3.engb` | `fire_wall` |
| `Maps/mansion/dr_mag2/mag_nyc1.engb` | `fire_deck_sm19` |
| `Maps/mansion/dr_mag2/mag_nyc2.engb` | `fire_deck_lrg04`, `fire_deck_sm08` |
| `Maps/mansion/dr_mag2/mag_nyc3.engb` | `fire_wall01` |
| `Maps/mansion/dr_mag2/mag_nyc4.engb` | `fire_deck_sm` |
| `Maps/nuke_plant/nuke/nuke1_4.engb` | `fire01`, `fire_deck_lrg01` |
| `Maps/nuke_plant/nuke/nuke2_3.engb` | `fire_wall` |
| `Maps/nyc/alison/nyc1_1_1.engb` | `fire_deck_sm19` |
| `Maps/nyc/alison/nyc1_1_2.engb` | `fire_deck_lrg03`, `fire_deck_sm09` |
| `Maps/nyc/alison/nyc1_1_2b.engb` | `fire_wall01` |
| `Maps/nyc/alison/nyc1_1_3.engb` | `fire_deck_sm` |
| `Maps/nyc/riots/nyc3_1_1.engb` | `fire_barrel`, `fire_deck_sm` |
| `Maps/nyc/riots/nyc3_1_2.engb` | `fire_barrel`, `fire_deck_lrg`, `fire_deck_sm` |
| `Maps/nyc/riots/nyc3_1_3.engb` | `fire_barrel`, `fire_deck_sm` |
| `Maps/nyc/riots/nyc3_2_1.XMLB` | `fire_barrel`, `fire_deck_lrg`, `fire_deck_sm` |
| `Maps/nyc/riots/nyc3_2_2.engb` | `fire`, `fire_big`, `fire_big03`, `fire_big04` |
| `Maps/sewers/grso/sewers3_1_1.engb` | `fire_barrel`, `fire_barrel04` |
| `Maps/sewers/healer/sewers2_1_1.engb` | `fire_barrel` |
| `Maps/sewers/healer/sewers2_1_2.engb` | `fire01`, `fire_barrel02` |
| `Maps/sewers/healer/sewers2_1_3.engb` | `fire_barrel` |
| `Maps/sewers/healer/sewers2_1_4.engb` | `fire_barrel` |
| `Maps/sewers/healer/sewers_hub2.engb` | `fire` |
| `Maps/sewers/hub/sewers1_1_1.engb` | `fire01`, `fire_barrel10` |
| `Maps/sewers/hub/sewers1_1_2.engb` | `fire01`, `fire_barrel03`, `fire_barrel04` |
| `Maps/sewers/hub/sewers1_1_3.engb` | `fire`, `fire_barrel07` |
| `Maps/sewers/hub/sewers1_1_4.engb` | `fire`, `fire_barrel` |
| `Maps/sewers/hub/sewers1_2_1.engb` | `fire`, `fire_barrel` |
| `Maps/sewers/hub/sewers1_2_3.engb` | `fire`, `fire_barrel` |
| `Maps/sewers/hub/sewers_hub.engb` | `fire`, `fire_barrel` |

## Unchanged fire definitions

These fire/flame effect definitions do not have the dead startup form. This is a definition inventory; source-derived relocation wrappers can still change a named instance's placement script. Enabled smartfire would also be left to its own scheduler; no matching source defect used it.

| Output file | Entity | Reason |
| --- | --- | --- |
| `Data/entities/pyro_ents.XMLB` | `fire_bat` | not an ordinary harm entity |
| `Data/entities/sentin_grenade_ents.XMLB` | `fire_bomb` | not an ordinary harm entity |
| `Maps/arbiter/a_int/arb2_2.engb` | `loop_effect06` | not an ordinary harm entity |
| `Maps/arbiter/a_int/arb3_1.engb` | `loop_effect26` | not an ordinary harm entity |
| `Maps/arbiter/a_int/arb3_1.engb` | `firejet_fx` | not an ordinary harm entity |
| `Maps/arbiter/a_int/arb3_2.engb` | `loop_effect55` | not an ordinary harm entity |
| `Maps/arbiter/a_int/arb3_2.engb` | `fire_jet` | not an ordinary harm entity |
| `Maps/arbiter/a_int/arb3_2.engb` | `loop_effect62` | not an ordinary harm entity |
| `Maps/arbiter/a_int/arb3_2.engb` | `firejet_fx01` | not an ordinary harm entity |
| `Maps/arbiter/a_int/arb3_3.engb` | `firejet_fx2` | not an ordinary harm entity |
| `Maps/arbiter/arb_fd1.engb` | `fire_deck_huge01` | loop authored off or no start-on flag |
| `Maps/arbiter/arb_fd1.engb` | `fire_deck_lrg02` | loop authored off or no start-on flag |
| `Maps/arbiter/arb_fd2.engb` | `loop_effect01` | not an ordinary harm entity |
| `Maps/arbiter/arb_fd2.engb` | `loop_effect02` | not an ordinary harm entity |
| `Maps/arbiter/arb_fd2.engb` | `loop_effect06` | not an ordinary harm entity |
| `Maps/arbiter/deck/arb_fd1.engb` | `fire_deck_huge01` | loop authored off or no start-on flag |
| `Maps/arbiter/deck/arb_fd1.engb` | `fire_deck_lrg02` | loop authored off or no start-on flag |
| `Maps/arbiter/deck/arb_fd2.engb` | `loop_effect01` | not an ordinary harm entity |
| `Maps/arbiter/deck/arb_fd2.engb` | `loop_effect02` | not an ordinary harm entity |
| `Maps/arbiter/deck/arb_fd2.engb` | `loop_effect06` | not an ordinary harm entity |
| `Maps/astral/ast3/astral3_3.engb` | `firedemon03` | not an ordinary harm entity |
| `Maps/astral/ast3/astral3_3.engb` | `pyro_bigfire` | not an ordinary harm entity |
| `Maps/astral/ast3/astral3_3.engb` | `pyro_fire04` | not an ordinary harm entity |
| `Maps/astroid_m/visit1/arb_fd1.engb` | `fire_deck_huge01` | loop authored off or no start-on flag |
| `Maps/astroid_m/visit1/arb_fd1.engb` | `fire_deck_lrg02` | loop authored off or no start-on flag |
| `Maps/astroid_m/visit1/arb_fd2.engb` | `loop_effect01` | not an ordinary harm entity |
| `Maps/astroid_m/visit1/arb_fd2.engb` | `loop_effect02` | not an ordinary harm entity |
| `Maps/astroid_m/visit1/arb_fd2.engb` | `loop_effect06` | not an ordinary harm entity |
| `Maps/astroid_m/visit1/asteroid2_2.engb` | `firejet2_fx` | not an ordinary harm entity |
| `Maps/astroid_m/visit1/asteroid2_2.engb` | `firejet_fx` | not an ordinary harm entity |
| `Maps/astroid_m/visit1/asteroid2_2.engb` | `loop_effect08` | not an ordinary harm entity |
| `Maps/demo/a_int/arb3_1.engb` | `loop_effect26` | not an ordinary harm entity |
| `Maps/demo/a_int/arb3_1.engb` | `firejet_fx` | not an ordinary harm entity |
| `Maps/demo/a_int/arb3_1.engb` | `loop_effect18` | not an ordinary harm entity |
| `Maps/demo/a_int/arb3_1.engb` | `fire_sailor_fx01` | not an ordinary harm entity |
| `Maps/demo/a_int/arb3_2.engb` | `loop_effect42` | not an ordinary harm entity |
| `Maps/demo/a_int/arb3_2.engb` | `loop_effect62` | not an ordinary harm entity |
| `Maps/demo/a_int/arb3_2.engb` | `loop_effect52` | not an ordinary harm entity |
| `Maps/demo/a_int/arb3_2.engb` | `firejet_fx02` | not an ordinary harm entity |
| `Maps/demo/a_int/arb3_2.engb` | `loop_effect26` | not an ordinary harm entity |
| `Maps/demo/a_int/arb3_2.engb` | `fire_jet` | not an ordinary harm entity |
| `Maps/demo/deck/arb_fd1.engb` | `fire_deck_huge01` | loop authored off or no start-on flag |
| `Maps/demo/deck/arb_fd1.engb` | `fire_deck_lrg02` | loop authored off or no start-on flag |
| `Maps/demo/hub/sewers1_1_1.engb` | `loop_effect04` | not an ordinary harm entity |
| `Maps/demo/hub/sewers1_1_2.engb` | `loop_effect04` | not an ordinary harm entity |
| `Maps/haarp/ext/haarp_ext01.engb` | `fire_wall` | no positive firstact (including prior HAARP fix) |
| `Maps/haarp/ext/haarp_ext02.engb` | `fire_wall02` | no positive firstact (including prior HAARP fix) |
| `Maps/haarp/ext/haarp_ext03.engb` | `fire_wall` | no positive firstact (including prior HAARP fix) |
| `Maps/haarp/ext/haarp_ext04.engb` | `fire_wall` | no positive firstact (including prior HAARP fix) |
| `Maps/haarp/int/haarp2_6.engb` | `fire_spot1` | not an ordinary harm entity |
| `Maps/mansion/dr_mag2/mag_nyc3.engb` | `water_jet` | not an ordinary harm entity |
| `Maps/mansion/dr_mag2/mag_nyc3.engb` | `smallfire02` | no positive firstact (including prior HAARP fix) |
| `Maps/mansion/dr_mag2/mag_nyc3.engb` | `fire_wall02` | no positive firstact (including prior HAARP fix) |
| `Maps/mansion/man3/mansion3_1.engb` | `loop_effect01` | not an ordinary harm entity |
| `Maps/mansion/man5/mansion5_1.engb` | `loop_effect02` | not an ordinary harm entity |
| `Maps/mansion/man5/mansion5_1.engb` | `loop_effect01` | not an ordinary harm entity |
| `Maps/mansion/man6/mansion6_1.engb` | `loop_effect01` | not an ordinary harm entity |
| `Maps/mansion/man7/mansion7_1.engb` | `loop_effect01` | not an ordinary harm entity |
| `Maps/mansion/man8/mansion8_1.engb` | `loop_effect01` | not an ordinary harm entity |
| `Maps/mount/mount/mount.engb` | `loop_effect01` | not an ordinary harm entity |
| `Maps/mount/mount/mount.engb` | `loop_effect07` | not an ordinary harm entity |
| `Maps/mount/mount/mount2.XMLB` | `loop_effect06` | not an ordinary harm entity |
| `Maps/nuke_plant/nuke/nuke1_2.engb` | `loop_effect01` | not an ordinary harm entity |
| `Maps/nuke_plant/nuke/nuke2_2.engb` | `firejet` | not an ordinary harm entity |
| `Maps/nyc/alison/nyc1_1_2b.engb` | `water_jet` | not an ordinary harm entity |
| `Maps/nyc/alison/nyc1_1_2b.engb` | `smallfire02` | no positive firstact (including prior HAARP fix) |
| `Maps/nyc/alison/nyc1_1_2b.engb` | `fire_wall03` | no positive firstact (including prior HAARP fix) |
| `Maps/nyc/riots/nyc3_2_2.engb` | `loop_effect08` | not an ordinary harm entity |
| `Maps/nyc/riots/nyc3_2_2.engb` | `firejet_fx03` | not an ordinary harm entity |
| `Maps/sewers/hub/sewers1_1_1.engb` | `torch_loop_effect18` | not an ordinary harm entity |
| `Maps/sewers/hub/sewers1_1_2.engb` | `torch_loop_effect21` | not an ordinary harm entity |
| `Maps/weapon_x/secret/wx3_1.engb` | `flame2` | not an ordinary harm entity |
| `Maps/weapon_x/secret/wx3_2.engb` | `flame2` | not an ordinary harm entity |
| `Maps/weapon_x/secret/wx3_3.engb` | `flame2` | not an ordinary harm entity |
| `Maps/weapon_x/wfb/wx1_3.engb` | `firejet_fx02` | not an ordinary harm entity |
| `Maps/weapon_x/wfb/wx1_3.engb` | `firejet_fx01` | not an ordinary harm entity |
