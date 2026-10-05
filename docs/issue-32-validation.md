# Issue #32 validation

The builder derives two relative paths from the player's original animation tracks.
The XML2 Fix companion for planned 1.3.2 enables their native evaluation on characters.
Both parts are required; 1.3.1 remains the FightStyles and geometry-sharing release.

## Controlled in-game comparison

Each case entered the relevant zone in an isolated build and activated its original
ladder spawner through the developer script queue. The observer was protected and
placed for the camera. No soldier position, velocity, health or completion signal was
written by the test. Native actor coordinates and flags were read alongside backbuffer
captures. Original and converted descent scripts were compared in fresh processes.

- Sewers: the original soldier settled near z=157 and remained above the floor; the
  converted soldier followed the source's 1.6-second descent to approximately z=0.04,
  then resumed ordinary movement on the floor.
- Arbiter: the original soldier remained near z=157; the converted soldier reached
  approximately z=0.04 and resumed movement on the floor.
- Two overlapping repeat spawns in Sewers both landed. Their world/entity collision
  flags were restored and their native movement timers were cleared.

The converted runs used source-derived keys, the original pose animation and its
original completion signal. Entity collision suppression alone was insufficient:
world clipping also has to be disabled for the duration of the authored descent.
The engine's native final callback ends scheduling; it is not a timed teleport.

Raw screenshots, coordinate samples and debugger logs remain in the developer's
ignored build directories. They are not distributed with the repository or PR.

## Automated checks and limits

Synthetic tests cover malformed motion data, supported script shapes, idempotence,
package limits and the generated engine option. The owned-input self-test compares
all generated keys and timings with the source, checks six zone packages and retains
the unrelated exceptional spawnscript. Native policy tests cover ordinary actors,
completion, repeated identities and final callback behavior.

This is a controlled authored-spawner reproduction, not natural trigger traversal or
a campaign playthrough. Mid-descent saves, fresh-process reload, multiplayer and
other frame rates remain unverified. The change stays a draft for review.
