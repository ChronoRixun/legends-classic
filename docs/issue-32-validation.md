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

## Spawners that place soldiers on the floor

One Sewers spawner and both Arbiter spawners of the second ladder room have no exact-location
flag. Both games place those soldiers on the ground (SPEC 46), so the converted script carried
them through the floor: in an integration run all five Sewers soldiers ended about 500 units
below it and died. Those spawners now run a generated copy of the original descent script.

Each case entered the room with real movement after a developer zone load; the party was made
invulnerable and, where the room is not reachable on foot, the leader was placed nearby first.

- Sewers floor spawner, converted script restored as a negative control: 8 of 8 soldiers sank to
  about 515-545 units below the floor and died.
- Same spawner with the floor copy: 8 of 8 stayed on the floor, alive. After the door was
  opened they came from about 550-760 units to within 40-170 units of the hero and fought.
- Sewers ladder-top spawner: the soldier still went from 166 to the floor in about 0.7 s.
- Arbiter floor spawners: two soldiers on the floor, no path, closed to 30-70 units and fought.
- CharacterLadderPaths=0: floor soldiers unchanged; ladder-top soldiers stay near 157 as before.

## Automated checks and limits

Synthetic tests cover malformed motion data, supported script shapes, idempotence,
package limits and the generated engine option. The owned-input self-test compares
all generated keys and timings with the source, checks six zone packages and retains
the unrelated exceptional spawnscript. Native policy tests cover ordinary actors,
completion, repeated identities and final callback behavior.

This is a controlled authored-spawner reproduction, not natural trigger traversal or
a campaign playthrough. Mid-descent saves, fresh-process reload, multiplayer and
other frame rates remain unverified. The change stays a draft for review.
