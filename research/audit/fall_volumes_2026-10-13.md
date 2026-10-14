# Fall volumes: original AI eligibility and remaining runtime work

This is a static comparison of the Xbox executable, the PC executable and released builder 0.2.2. It does not
claim a live reproduction of the HAARP double-jump escape, a follower crossing, a knocked-in enemy or recovery
after death. No gameplay policy changes accompany it.

## Inventory and geometry

Enumerating both English and XML-only original maps and the built output finds 32 lethal-touch definitions and
41 placements in 30 maps. The released `FALL_KILL_DEFERRED` table contains 17 definitions, covering 25 placements
in 15 maps. Three definitions belong to demo maps outside the packaged campaign reachability graph. The earlier
report's count of 18 deferred definitions is stale. English/localized twins agree in all 28 applicable maps.

Every source placement is present with its original position/orientation and the section 17 world-to-local
extent conversion; reconstructed world bounds agree within conversion precision. Source damage, activation
scripts and targeting flags are retained. These comparisons establish data preservation, not safe party movement.

HAARP's exterior contains three authored lethal placements: one in `haarp_ext01`, two in `haarp_ext03`. All are
enabled in the released output. The first has the already approved player-only exception. The raw collision
triangle blocks and canonical navigation of all five exterior rooms match the source. There is no evidence here
for an omitted authored fall volume or a removed map hull. A hero can still reach a surface above/beside a lethal
volume, and identical hull bytes do not imply identical engine traversal. The reported route needs a real-input
negative control with two heroes before adding a boundary or changing the engine.

## Original touch and harm dispatch

The common movement contact dispatcher at Xbox 0x42a7b-0x42b7f sends touch events to both contact participants
through virtual slot 0x9c. For the harm entity, that slot leads to 0x91160, then 0x27310. If touch activation is
enabled, it invokes virtual slot 0xc0 at 0x27a60. Readiness at 0x27410 checks enabled state and activation timing,
then the immediate action invokes slot 0xcc at 0x46cc0.

That action first passes 0x78d40 and the generic entity activation gate at 0x28420. The gate has optional
team/player/leader restrictions, as well as count and timing conditions. The deferred source definitions do not
request those targeting restrictions. For a non-radial harm action, the actor cast at 0x275e0 and team tests at
0x46d6b-0x46da6 select the toucher. A neutral hazard (team 0x1a in this executable) can damage actors of either
side; otherwise the same-team case is skipped. The action invokes the target's damage virtual at 0x46db9,
slot 0xa8. There is no unconditional controlled-hero requirement in this route.

The PC equivalents include touch activation at 0x41a7a0, activation scheduling at 0x41a890 and the harm action
at 0x439a90. Its non-radial branch at 0x439bb6-0x439c00 similarly casts the toucher to an actor, allows neutral
team 0x1c, skips a non-neutral same-team pair, and invokes damage slot 0xb0. The previously approved `actleader`
exception on HAARP's first exterior volume intentionally changes who can activate that one volume.

This establishes that AI control does not by itself exempt a toucher from authored lethal damage. It does not
establish that every AI can reach every instance, nor whether each original room revives, hides or returns a
fallen party member. Those are separate runtime questions; damage eligibility must not be reported as recovery proof.

## Danger-notification difference

Xbox harm tick 0x46ba0 requires health at least one. Both its radial/box branch and its ordinary notification
branch require the signed 16-bit damage field at entity offset 0x2d4 to be strictly below 32000. The first
comparison is at 0x46bc9; its rejection branch is at 0x46bd2. A lethal fall volume with damage 32000 fails this
test regardless of whether `informai` is enabled. Its parser at 0x46f10 stores that 16-bit damage field, and
constructor 0x470c0 initializes the harm flags with ordinary AI notification enabled.

PC tick 0x439350 instead checks positive health and float damage at offset 0x32c below 1000000. Other flags,
health and entity activity still matter before it advertises anything. The threshold difference alone therefore
does not prove that an enabled PC fall volume changes an AI's route. It does rule out treating the two ordinary
notification paths as equivalent, or assuming the Xbox used this notice to steer actors around lethal volumes.
Other avoidance/pathfinding mechanisms remain possible.

## Next controls

Keep the 17 deferred definitions off until each affected room passes the required live movement checks. In water
rooms, verify the original's solo-mode/bridge/follower behavior as well as damage. In rooms with multiple placements,
cover every placement, including the four in the deferred nuclear corridor and both placements in each two-pit
sewer room. Combat beside a pit does not prove a real fall into it.

A future enable must add its exact pair to `FALL_KILL_ENABLED_LATE`, append it after the settled props, audit
every built placement, pass V26/V31/V41 and preserve existing save ordinals. Do not copy HAARP's player-only
exception to another room without checking recovery and inherited control of a follower already inside the volume.
