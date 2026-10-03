# Player-like autopilot (experimental)

The driver exercises a separately copied Legends Classic build using the engine's
AI and calibrated movement input. It observes failures; it does not establish campaign coverage
just because a run produced no findings. The known HAARP and mansion regression
sequences must actually be reached before claiming they pass.

Requires the companion XML2 Fix schema-1 state API (including `script_controls_locked`) in
[xml2-fix PR #1](https://github.com/ChronoRixun/xml2-fix/pull/1), a Windows interactive
session, and a completed build made from the user's own inputs. The normal
builder and player-facing output are unchanged.

## Run

Use a new directory **outside every Git checkout**. `prepare` copies the source
build without changing it. Each run installs the harness only into that owned
copy, creates a unique save/profile folder and pipe, and launches a background
1280x720 window under `gamedbg.py`. Each window has a unique title and background
virtual-pad isolation so physical controller input cannot steer another test. It refuses to attach to an already running game.

```text
python tools/autopilot.py prepare --source-build <completed-build> --workspace <new-external-workspace>
python tools/autopilot.py plan <workspace>
python tools/autopilot.py run <workspace> --dll <schema-1-dinput.dll> --seconds 300
python tools/autopilot.py run <workspace> --dll <schema-1-dinput.dll> --mode assisted --seconds 300
python tools/autopilot.py run <workspace> --dll <schema-1-dinput.dll> --mode fast --seconds 120
```

`--expect-zone <zone-id>` may be repeated. This records coverage requirements; it
never changes the route or jumps to those zones. Missing coverage is reported.
`--use-key E` selects the normal Use binding; override it for custom bindings.
The driver starts New Game through the menu. It uses `setAutoSpend(1,1)` for all
heroes, enables party AI and hands control to it. For navigation it briefly takes
manual control, measures W/S/A/D displacement, and follows generated route points
with bounded key holds and position feedback. Turns, stairs and explicit links
remain in the route. Blocked steps try a measured sidestep and recalibration;
combat or script displacement causes replanning. Close combat is left to party AI.
Script-owned subway transitions are approached normally and their destination is
observed; a missing transition becomes a finding. The driver does not assume that
a distant `moveToEntity` call will find a route.

`assisted` adds a limited backstop after ordinary movement stalls: teleport the
controlled hero to the next local route point, count the attempt, and verify its
position. `--max-assists` limits attempts per zone (default 8). Assists are refused
across potential doors, elevators, bridges, activation volumes, script-owned
transitions, final goal activations, or unknown/active script control locks.
Steps longer than 240 units and repeated attempts at a point are also refused.
These conservative checks can stop at a harmless volume; refusal means a harness
boundary requiring review, not proof that the game is softlocked. Assists never
clear a script stall, kill actors, or grant invulnerability.

Use actions briefly return control to the player, press the use key, then return
to AI. Objective-bearing breakables use ordinary attack input at their use point.
Conversations select the first visible response unless a hint requests another;
popups try Enter, then Escape if they remain open. The driver never calls a
model API. `fast` substitutes `copyOriginAndAngles` for movement between goals;
every log record and summary carries the mode. Fast results are not acceptance
results for player-like mode. No mode grants invulnerability or script kills.

For an explicitly seeded test, `--entry-mission x1/missions/begin_<name>` invokes
one existing generated mission-start script after New Game. The script must exist
in the owned build. The report records the exact request and confirms the loaded
zone; a queued request alone does not establish arrival. This is a disclosed test
starting point, not an unaided campaign run. It neither solves puzzles nor seats a
side-mission party on the driver's behalf.

## Offline goals, routes and hints

The planner decodes the build's Maps XMLB files with `tools/xmlb.py`, combines
entity definitions with instances, and follows literal script references and
relay targets. Candidates include touch and use triggers, zone links,
objective-completing entities, and triggers connected to spawners. Script calls
that identify boss targets help select health watches. Objective and fight triggers come first, then zone links, then other touch/use
entities, then entities whose scripts only display informational popups. Each
group is ordered by distance from the preceding goal. This is a heuristic, not a puzzle
solver or proof that a target is enabled or reachable. Script conditions and
runtime entity motion are not fully modeled.

Nonempty NAVB grids supply cell centres, bounded-height cardinal neighbors and
explicit directed links. XY cell indices become `(index + 0.5) * cellsize`; Z
retains source height. Literal unconditional party-transport scripts can connect
otherwise separate components, but the engine must actually execute them. When
navigation is absent, nearby entity anchors provide a labeled inferred fallback.
Routes are cached from authored starts and replanned from the live hero position.
This graph is not a collision mesh; connectivity and obstacle clearance remain
inferences checked by movement feedback. Door/trigger extents conservatively
bound assist eligibility. The parser does not solve conditional scripts.

The generated cache contains identifiers and coordinates but is still derived
game data: it stays under the external workspace's `cache/`. Its identity hashes
the maps, NAVB files, scripts, hints, and planner implementation. No cache belongs in Git.
Map decoding failures appear explicitly in the cache and run log.

Optional `--hints <directory>` reads `<zone-id>.json`. Files may contain only an
`order` list of existing entity names and a `responses` map from such names to
zero-based response indices. They contain no dialogue, game text or script code.
An invented example:

```json
{"order": ["switch_test", "exit_test"], "responses": {"switch_test": 1}}
```

No campaign hints are shipped. The acceptance runs must use no hints naming or
routing directly to the known bugs. A driver that cannot reach a test is a
harness limitation, not a passed regression test.

## Findings and evidence

Each run writes `runs/<run-id>/run.jsonl`, `summary.json`, `summary.md`, the
debugger log, assists per zone (including zero counts), screenshots when capture
succeeds, and one exception JSON per
finding. Records include the zone, complete observed state, last goal, and the
last 30 seconds of events. Screenshot failures are explicit; a nonexistent file
is not reported as captured. The exception record contains candidate actions and
`model_called=false` for a future decision service.

Default observation limits are configurable: no meaningful progress for 90 s,
conversation open for 60 s, nearby boss health unchanged for 90 s, a goal not
reached/activated for 120 s, downward speed below -40 for 3 s, and a stale
engine sample for 8 s. The pipe may answer while the game thread is hung; sample
timestamps detect that. Pipe requests use bounded helper processes so a blocked
Win32 read cannot freeze the controller. The driver stops its own launched PID
when the run ends, and reports a disconnected Windows session as an environment
failure.

Progress means closer approach to a goal, zone/objective/conversation changes,
or nearby combat health changes. Animation or movement away from the target does
not reset the stall timer. Ground contact is unavailable; downward motion can
also be flight or a lift. The zone-floor lower bound comes from navigation,
start and trigger origins minus a conservative margin, not collision geometry.
Falling/OOB findings therefore retain the state and screenshot for review.

A visited goal is labeled `visited_not_proven_complete`. When a goal has known
objective effects, the driver waits for those objectives. Follow-up detection is
limited to unconditional script chains with one conversation and one destination.
Boss identification uses spawner/script metadata and stats identifiers; it does
not fully resolve every dynamically spawned boss instance or shield phase.

Deaths and game-overs are findings. Recovery opens the game's load UI only when
this run's save folder has one unambiguous save. No save, multiple saves with
unverified UI ordering, or an unsuccessful load become explicit recovery
findings. Exact newest-slot selection for multiple saves is not implemented;
`loadgame <slot>` cannot supply it (the engine ignores arguments and opens the UI).
No other build's saves are read or loaded.

## Validation and current limits

Synthetic tests run with `python tests/unit/run.py -k autopilot`; the normal full
suite and content guard still apply. Tests cover cache invalidation, generated
goals and relay/script rules, unsafe identifiers and hints, repository isolation,
UI dismissal/response choice, grid coordinates/links and disconnected routes,
calibration, assist barriers and script locks, retry deadlines, stale samples,
deaths, falls, missing follow-ups,
objective/boss stalls, event history and mode restrictions.

Live results and the requested historical acceptance matrix are in the draft PR
and the external progress/run records. A controlled stock-zone experiment found
that the builder's empty BOYB networks remove native long-range navigation:
the original populated network completed a multi-segment move, while replacing
only that network with an empty one produced no movement. Port NAVB cells loaded
successfully; the observed failure was the navigator's far-path lookup with no
usable buoy nodes. A separate builder proposal records the evidence and required
coverage/connectivity checks. This PR does not change generated game output or
claim every navigation failure has that cause.

The fallback still stops at route/collision and activation boundaries. Seeded
Astral runs have not reached the crystal puzzle or side mission. It cannot claim an
unaided campaign pass. Hero-specific powers, complex puzzle conditions, exact
multi-save selection, collision-ground truth, and engine script-error hooks
remain limitations. Debugger-reported script errors supplement the sampled pipe.

Read-only observations are also available through `fixinput.state()`,
`fixinput.objectives()` and `fixinput.events()` after `fixinput.use_build(...)`,
or `python tools/fixinput.py state --build <owned-build>`. The autopilot runs these
in bounded helper processes; direct fixinput calls retain the existing blocking
pipe behavior. Workspace runs hold an OS lock to prevent concurrent writers.

Exit code 0 means the requested run budget ended with no findings; it is not a
campaign acceptance pass. Findings/harness errors return nonzero. Coverage and
all material limitations remain in the summary regardless of exit code.
