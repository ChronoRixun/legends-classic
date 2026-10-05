# Issue #12 validation

## Original HAARP fix (SPEC 45)

The original fresh-process before/after comparison in `haarp/ext/haarp_ext01`
used the same vulnerable Wolverine, DLL, settings and native `fire_wall01`.
Its waypoint was staged in an unobstructed landing area. Before the fix the
wall was invisible while damaging the hero; after the loop-start correction
and hide/act/move/show wrapper, the flame and floating damage were visible.
Both matching contact/exit sequences ended at 57 HP from 90. This was not a
precise damage-rate benchmark. A smartfire candidate was rejected after its
reduced damage was measured. That original check did not cover a natural
flamer encounter, extinguishing or save/reload.

## General fix (PR #56)

Baseline behavior was built from main `a5769737f1d0586d0d0cbadf4d3a71bef6b7eaae`.
The scan found 97 remaining ordinary harm definitions with a nonempty loopfx,
loopfxstarton=true and positive firstact: 55 output files, comprising 53 map
zones/aliases and two entity libraries. Identical localized pairs count once.
XML2's harm parser clears the loop-on bit at `0x4399d9` for positive firstact;
XML1's first-act scheduling does not clear that bit.

The builder now sets firstact=0 after class remapping for that form, without
matching zone, entity or effect names. Enabled smartfire, authored-off loops,
other entity classes and definitions without a positive delay stay unchanged.
The output comparison found only firstact 1 -> 0 in those 97 definitions.
Damage values, repeat intervals, collision fields and extinguish reactions
remain authored. CONTENT_VERSION stays 11 for this unreleased revision.

**Timing tradeoff:** this removes the first game's one-second start delay on
these 97 hazards. A player already touching a newly created hazard may take
damage up to one second sooner, and the phase of repeated activations may shift.
A player reaching it after that initial second may notice only the restored
flame. The size of the timing difference was not measured as a gameplay benchmark.

An alternative XML2 Fix change could preserve the authored loop-on bit in the
positive-firstact branch for ordinary non-smart harm entities while retaining
the delayed activation. It would need guarded engine code and separate tests
of the preceding disable call, smartfire/on-off timers, extinguishing, save/load
and XML2 retail hazards. No such engine change is implemented or required here.

A second mechanism was reproduced independently: a NYC fire with empty firstact
remained invisible after being moved from underground, then appeared after a
hide/show restart. A source-derived script pass now restarts known start-on harm
loops after literal copyOriginAndAngles calls. It adds eleven placements across
four scripts: six in NYC's `meet_pyro`, two in the Hive and three in HAARP's
interior. The six existing HAARP exterior scripts retain their original wrappers.

## Controlled runtime checks

Both builds used XML2 Fix 1.3.1, shipped limits and isolated windowed harnesses.
Zone jumps, party selection, placement, facing and enemy isolation were staged.
Contact damage came from normal keyboard movement, without damage commands or
health writes. Iceman's power used normal keyboard input. These checks do not
constitute a natural campaign playthrough.

| Check | Observation |
| --- | --- |
| Negative NYC | Native `fire_wall01` in `nyc/alison/nyc1_1_2b`, with its authored placement staged: walking into the invisible wall reduced HP 90 -> 75 -> 51 -> 24 -> 0. |
| Negative Arbiter | Native `fire_wall` in `arbiter/a_int/arb3_4`, at its authored location: walking contact reduced HP 90 -> 87 -> 30, with floating damage but no flame. |
| Fixed NYC | Street fires in `nyc1_1_1` and `nyc1_1_3` were visible during movement. After staged invocation of the generated Pyro placement script, the bench wall was visible and contact/retreat reduced HP 90 -> 84 -> 72. |
| Fixed Arbiter and sewer | The same Arbiter wall was visible and damaging (72 -> 63 -> 36). The native sewer fire pit was visible during movement; no isolated damage-rate claim is made for that small fire. |
| HAARP regression | The native exterior wall was staged in a clear landing-area spot with the unchanged hide/act/move/show sequence. It remained visible and damaging during movement (72 -> 48 -> 30). |
| Iceman | Staged party, approach and facing in the Arbiter; actual power input extinguished the wall, stopped the effect and removed the live hazard. Iceman then walked through its former area at 78 HP throughout. |
| Save/reload | The extraction menu was opened by script beside the burning NYC bench. Normal Save Game and Load Game UI returned the hero to the same position and 72 HP with the flame still visible; subsequent movement worked. |

Earlier small-fire probes with enemy interference and a bad staging position
were discarded as damage evidence. Contact durations differ between runs, so
these HP observations do not establish equal damage rates. Hive and HAARP
interior placements have structural and pipeline validation only.

The report that a fire appears only after walking around it was **not reproduced**.
It may have a separate visibility or smart-entity streaming cause. The proven
relocation failure does not establish the cause of that intermittent symptom.

## Offline checks and reproducibility

- 241 synthetic tests passed; baseline and fixed builds each verified 21343 files
  with zero errors and 269 warnings. Zones and scripts pipeline self-tests passed.
- `test_harm_loops.test_validator_rejects_dead_loop_and_accepts_converted_tree`
  asserts one validator error for an invented definition left in the dead form
  (localized twins reported once), then no error after conversion. Repeat with
  `python tests/unit/run.py -k validator_rejects_dead_loop`.
- V25 found 97 errors in decoded baseline output and zero in the fixed build.
- A binary comparison against the retained main-build output confirmed all six
  `Scripts/haarp/ext/create_firewall{1,1b,2,3,4,6}.py` files are byte-identical.
  Exactly four other generated scripts changed, for the eleven placements above.
- Run `python tests/unit/run.py`, `python tools/check_no_game_content.py --all`
  and `python tools/check_no_game_content.py --self-test` from the repository root.
  From `tools/`, run `python -m xml1build.zones_selftest <out> --base <XML2-install>`
  and `python -m xml1build.scripts_selftest --out <out> --base <XML2-install>` on a
  build made from owned inputs. Check `_build/validate.json` for V25 = zero.

The full working report, captures, saves and detailed inventories remain local
and untracked. No game text, screenshots, decoded data or personal paths are
included in this public summary. The documentation follow-up launched no game.
