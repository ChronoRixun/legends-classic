# Saved-campaign entry paths

The reported Maintenance Garage (`haarp/int/haarp2_1`) failure was reproduced by
opening `console loadgame` from a freshly launched main menu. Loading the same
unchanged saves through the normal Load Game menu succeeds. This is an invalid
cold-load test entry path, not evidence that those saves or the zone need repair.

## Controlled comparison

Checked on candidate 0.2.3b with an unmodified XML2 Fix 1.6 source rebuild:

| Input | Fresh main-menu console load | Normal main-menu load |
| --- | --- | --- |
| Imported garage save, origin 1 / capture flags 2 | Previously reported failure | Four heroes alive at saved positions; movement works |
| Native garage save, origin 0 / capture flags 0 | Reproduced: unresolved party, bodies near origin subsequently die | Four heroes alive at saved positions; movement works |
| Native save in a different zone | Reproduced: unresolved party | Alive at saved position; movement works |
| Fresh garage save | Not needed for the positive control | Cold reload alive at saved position; movement works |

The fresh save came from normal New Game, a staged `loadMapKeepTeam` zone jump,
movement, and the engine's save menu. It is a save/load check, not a campaign
playthrough. All tests used isolated copies and save folders, path-checked pipe
input, per-run registry restoration, and observation-only Frida. No hero health,
saved coordinates, save bytes, engine behavior or zone data were edited. Python
and C++ canonical decoders agree on the two old saves, the control and the fresh
save. Both older garage saves carry usable vitals and nonzero seat positions.

## Mechanism

The console handler at `0x5f2b70` opens the save/load UI without the normal
main-menu controller handoff. A successful LC read and native load at `0x46e2b0`
therefore do not establish a playable session.

Zone-load spawning at `0x486dd0` calls the hero factory at `0x46a6c0`. The factory
creates bodies and applies hero stats, but registration at `0x469ea0` leaves
their controller field (`actor + 0x3d4`) at `-1` on the direct-console path.
The party collector at `0x46d460` requires both membership flag bit 20 and a
controller assignment. Saved-formation placement at `0x489300` uses that
collector. The bodies are consequently omitted from saved-position placement;
later damage is downstream of the missing session setup. Observation of the
character damage entry at `0x438a10` records a 1,000,000-point hit from return
address `0x476b08` (call site `0x476b02`). Its containing height-boundary routine
starts at `0x4769c0`. This is distinct from the placement-crush touch call site
`0x49908d`; it does not implicate the garage's Xtraction entity or saved vitals.

With normal menu input, registration assigns the leader and followers valid
controllers, the collector includes them, and saved-formation placement restores
the saved positions. Frida observations of the same file distinguish these paths.
The requested-controller array is temporary: it can return to `-1` after a
successful handoff, so inspect the bodies' controller assignments as well.

The garage's default and return starts each have four instances, and its
Xtraction point is present. This failure also reproduces outside the garage and
does not depend on historical/inferred versus observed capture provenance.
An audit of all 198 converted maps found no one-position, unslotted hero start
missing `allinone`. Six inherited retail maps match that static pattern; they
were not modified or live-tested and are not evidence of this load-entry defect.
The spawn/collector/restore sequence is shared across zones; it contains no
garage-specific branch. A static audit of the built scripts found no `loadgame`
console invocation. No production fix or durable save-format change is indicated
by this experiment. Earlier-build reports using the console shortcut do not
establish a player-facing regression in those builds.

## Regression procedure

1. Stage a copy of one save in an isolated save folder and launch an owned build.
2. Use the main menu's Load Game action and its confirmations. Do not substitute
   `console loadgame` for that action. Wait for each UI transition before input.
3. Require the intended zone, completed loading, fresh sample timestamps, and
   a live body bound to every expected party name. Compare positions to the
   decoded save before movement.
4. Apply real movement through the owned input pipe. Require displacement and
   positive health afterward, then save and cold-load the new copy.
5. If studying the console failure, run it separately as an explicitly invalid
   entry-path control. Keep the normal-menu positive control on the same build.

The state API deliberately reports null body fields for an unresolved party
slot. Inspect the case-insensitive matching entries in `actors` to distinguish
an absent body, an unassigned body, a living body and an actual death. `on_floor`
is always null in schema 1; use positions over time, movement and appropriate
collision observations instead of asserting it is true.
