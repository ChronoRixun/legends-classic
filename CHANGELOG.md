# Changelog

The builder's releases, newest first. The version is `xml1-builder --version`; the content version is what a
build carries (`_build\stamp.json`) - when it rises, the launcher offers a rebuild.

## v0.4.0 - content version 25 (needs XML2 Fix 1.8.0)

Renumbered from 0.3.0 while in beta (the betas 0.3.0-beta.1..3 are this release's history);
no stable 0.3.0 was published. Betas 1-4 were content 24 / `LC33`; beta 5 (the classic look) is content 25 / `LC34`.

Legends Classic 0.4.0 brings online play from Ultimate Legends **0.4.0**. Update the launcher to 0.4.0 first,
then **Rebuild**, then **Play**. Everyone needs the same 0.4.0 build and XML2 Fix 1.8.0 or later;
0.2.x and 0.4.0 never join each other. Test mode must be off.


- **Beta 5: the classic look.** The port's screens now wear the first game's own art, converted from your disc when
  you build: the HUD (hero heads and bars, the power wheel, the target frame and a bigger small-map frame that keeps
  fog and markers inside it), the pause menu, Objectives, Options and Controls, the Save/Load lists and the dialogs,
  the character room (the Blackbird backdrop and classic frames around Stats, Skills, Gear and AI), Review, the Codex,
  the Danger Room, the Forge, the healer, trivia, loading screens and credits. In the character room the pulsing white
  cones and gold rings are gone; the selected hero stands on a bright blue podium and a selection mark follows the
  keyboard and controller. In the Codex, Details opens the entry you are on, and Back from a biography returns to the
  list with that entry still selected. Only the look changes: the port's controls, tabs, numbers, shops, gameplay and
  saves stay the same (your saves carry over). Builds write XML2 Fix's `[Game] ClassicHud = xml1` and
  `ClassicCodex = 1`, so beta and rc builders now require `>=1.8.0-beta.5` and the builder refuses an older DLL by
  name. Because the build's output changes, the content version rises to 25 and the lobby token to `LC34`: the
  launcher offers a Rebuild, and a beta 5 game and a beta 4 or older game never join each other - everyone updates
  and rebuilds.

- **Beta 3: online at 60 fps.** Builds now write XML2 Fix's `[Online] TickRate = 60`: online sessions run at 60
  frames a second like single-player instead of the game's own 30 (the game keeps its speed; about 11 KB/s upload
  per player instead of ~6). `TickRate = 30` in `xml2-fix.ini` is the fallback for a slow PC - then every player in
  that session sets 30. The rate is gameplay-agreement rule 29, so a 60 and a 30 game refuse each other at join
  naming `29 TickRate`, and a beta 2 game and a beta 3 game never join. Beta and rc builders now require
  `>=1.8.0-beta.3`; the builder refuses an older DLL that does not know the key. Content and the lobby token (`LC33`)
  are unchanged. XML2 Fix beta 3 also fixes an occasional crash on quit and the cleanup of beta 2's bigger model
  pools on level changes and quits.
- **Beta 2: no more team-combo crash, bigger model pools.** Builds now write XML2 Fix's `[Engine] ModelPools = x4`
  (4096 models, 2048 IGB, 128 actors, 128 particle clouds ...) and `[Game] ComboPopupGuard = 1`: with the game's own
  pools a heavy fight could fill one, effects and props went missing and a team-combo popup without a hero's head
  crashed the game (beta 1, hosting alone in the Maintenance Garage). The pools are gameplay-agreement rule 28, so a
  beta 1 game and a beta 2 game refuse each other at join, naming `28 ModelPools` on the beta 2 PC: everyone
  rebuilds with builder 0.3.0-beta.2 and XML2 Fix 1.8.0-beta.2. Beta and rc builders now require
  `>=1.8.0-beta.2`; the builder refuses an older DLL that does not know the two keys. Content and the lobby token
  (`LC33`) are unchanged.
- **Four-player start is fixed:** participants keep distinct peers when the game starts.
- **Hero swaps survive level changes.** Solo-segment hand-back runs only during the segment and where it ends,
  using the heroes held when the segment began (rule 26 revision 6).
- **Slow players stay connected.** LAG warnings may still show, but the slow-player drop is disabled.
- **Frozen guests:** a joiner frozen for 30 seconds is removed through the agreed cut frame; survivors keep playing.
  A host drop or freeze still ends the joiners' session with "lost connection to the host".

- **Host or join by code**, without port forwarding or ini editing. The code appears in the game's online menus
  and host lobby; the launcher copies it when it first appears.
- **Browse public games:** opt in to a public listing with a room name, or keep the room private and share its code.
  The list shows the host, level, mode and player count. A matching build's row can join: room tokens are exactly
  `GameVersion` (`LC33`), with no content fingerprint appended. The normal gameplay agreement still checks content
  and rules when joining.
- **Drop-in co-op is on by default.** Start alone, let friends join mid-campaign, then bring them into play at the
  next level change. When the last guest leaves, the host keeps playing and can accept another.
- **Solo story segments:** players without a hero stay connected as watchers and regain control when the party
  widens. This covers Wolverine's opening and Magma's mansion tour (issue #106).
- **An abrupt guest drop in a game of three or more no longer ends the survivors' session.** XML2 Fix's rule 25
  revision 4 agrees a cut frame before removing the lost player. That player can join again by code and return at
  the next level change. Losing the host still ends the session; there is no host migration.
- **Clearer room messages:** `room_closed` means the game cannot take new players right now; `room_full` means
  all four places are taken (launcher contract v1.5).
- Encrypted connections with relay fallback, and online hardening. Public games connect players directly, so
  players can see each other's internet address. Use a private code to play only with friends.
- The broker allows at most two public rooms and two seats in other people's rooms per internet address.
- Includes 0.2.5's bedroom picture window and per-hit hero stun fix. The save format is unchanged.

See [Play online](docs/ONLINE.md) for steps, privacy and troubleshooting.

**Known issues**

- **Enemy attack rate** (issue #101): unarmed enemies (the Brotherhood in the HAARP tunnels) still attack about 1.5
  times as often per minute as in the first game (about 19 against 28 attacks per enemy per minute with a moving
  hero, 20 against 32 with a still one); the cause is not found. The per-hit hero stun fix shipped in 0.2.5; whether
  heroes are now stunned as long as in the first game has not been measured again, so it does not close the
  remaining combat report.
- **Gun soldiers** (issues #101 and #54): the HAARP officer, and probably the other gun soldiers, still close in to
  punch where the first game's keep their distance and shoot (matched 45 s window: 49 shots and no punches in the
  first game, no shots and 24 punches in the port).
- **Falls** (issue #22): 15 of the first game's fall kill zones (20 placements in 14 maps, three of the zones in demo
  maps outside the campaign) stay switched off until proven safe for the AI followers too. The double jump out of the play area on the HAARP slopes and bridge that
  0.2.2 listed could not be reproduced from 0.2.3 on (18 jumps, all landing inside; the zone's boundary data matches
  the first game).
- **Cosmetics** (issue #54): the HAARP officer's gun is louder than on the Xbox: the port fires a seven-shot burst
  where the first game fires single spaced shots, and each shot plays its own ~1.5 s sound, so about seven stack
  (the sound's volume is the original's). The bedroom picture window is fixed.
- **Loot and the item shop** (issue #6) still use the sequel's systems.
- **Hazards** (issue #104): the earlier 57-level audit had live checks in only three rooms. Report any fire,
  spike or electricity that still does not hurt.
- **Host loss ends the session.** There is no host migration; host again and load the last save.
- **Four-player internet play is not yet verified.** Local three-player abrupt-drop checks passed; the owner's
  030e three-PC acceptance including a hotspot PC is still required before publication.
- A failed shared-campaign restore can require rehosting. Automatic reconnection is not provided.

<details><summary>Technical details</summary>

- Builder 0.4.0, content 24, catalogue 7, game version LC33; requires XML2 Fix >=1.8 (CMake/DLL 1.8.0).
- Builder defaults include `Broker`, `BrokerPin`, `JoinInProgress=1`, `FastTransfer=1` and `ReceiveValidation=1`.
  Room starts imply GNS transport (rule 25 revision 4 / framing 3); drop-in uses rule 26 revision 6.
- Conversation timing is the 0.2.4 fix (rule 27), retained here, rather than a new 0.4.0 feature.

</details>

## v0.2.5 - content version 23 (needs XML2 Fix 1.7.1)

Legends Classic 0.2.5 - content version 23, needs XML2 Fix 1.7.1. Rebuild in the
launcher, then Play. Both co-op players need the same build and fix.

- **Bedroom items show their picture in the first game's picture window** (issue #54): each item in the
  mansion bedrooms shows the first game's own picture in its picture window, with the panels, text and Back bar
  around it, instead of an enlarged picture hiding them. The builder ships the first game's pictures unchanged and
  writes `[Game] PersonalItemPicture=window`.
- **Heroes are re-stunned by every stun hit, as in the first game** (issue #101, `[Game] StunRule=xml1`, rule 18
  revision 3): a hero who is already stunned is stunned again by the next stun hit instead of ignoring it, so the
  Brotherhood in the ice tunnels and other stunning enemies keep a hero reeling the way they did in the first
  game. Stuns still end when the hero gets up. Both co-op PCs need builder 0.2.5 and XML2 Fix 1.7.1.
- The save format is unchanged.

## v0.2.4 - content version 22 (needs XML2 Fix 1.7.0)

Legends Classic 0.2.4 - content version 22, needs XML2 Fix 1.7.0. Rebuild in the
launcher, then Play. Both co-op players need the same build and fix.

- **Toad at HAARP fights through all four jets again** (issue #105): he attacks
  from each jet and stays protected until it breaks, then returns to ground
  combat. Soldiers ride the two elevators up each time Toad heads for the next jet, step into the arena and
  fight; the next wave follows once the last one is down.
- **Enemy resistance text is back:** physical, energy and mental resistance
  appears beneath the target health bar, with the first game's colors. This
  changes the display only; damage and resistance rules stay the same. The
  builder enables `[Game] ResistanceDisplay=xml1`.
- **Co-op no longer drops during conversations:** a conversation line that
  moves on by itself (the mansion tour, briefings) now does so at the same
  moment on both PCs. Before, each PC waited for its own voice clip to end,
  the games fell out of step and the session ended. Online, a reply you pick
  no longer plays its full voice line; single-player is unchanged. The builder
  enables this after a rebuild. Both PCs need builder 0.2.4 and XML2 Fix 1.7.0.
- The save format is unchanged. The HAARP boss map changed, so an older saved
  record for that encounter may reset when you enter it.

**Known issues**

- **Online co-op and the first game's solo story segments** (issue #106; Wolverine's opening, Magma's mansion tour):
  the second online player has no hero while the story seats one hero alone. A co-op *New Game* starts with Wolverine
  alone, and when a solo segment begins mid-campaign the second player is dropped at the next level load. Use *Load
  Saved Campaign* for co-op and start a new session from a save after the segment; the fix is planned with 0.3.0's
  drop-in co-op.
- **Enemy powers and stun** (issue #101): enemies still use powers and stun heroes more than in the first game
  (Brotherhood, HAARP); only parts of it are fixed here.
- **A double jump on slopes or the HAARP bridge** can land a hero outside the play area (issue #22); the remaining
  fall kill zones are still switched off until proven safe.
  *Correction, 2026-10-23: this was not reproducible on 0.2.3 or later (18 jumps, all landing inside the play area).*
- **Loot and the item shop** (issue #6) are not in this version.
- **Cosmetic reports** from the first playthrough (issue #54) are still tracked.
- **Hazards** (issue #104): 57 levels were fixed from an audit of the game's data, but only three rooms were played
  in the checks. Report any fire, spike or electricity that still doesn't hurt.
- Co-op was tested with two copies of the game on one PC; the two-PC pass, on one network and across the internet,
  is 0.3.0.

<details><summary>Technical details</summary>

- Content version 22, catalogue revision 7, lobby token LC31; requires XML2 Fix >=1.7.
- The builder writes `[Game] ResistanceDisplay=xml1` (display only) and
  `[Game] OnlineConversations=lockstep` (gameplay agreement rule 27, revision 1).
  Peers using the earlier 0.2.4a candidate are refused because their rules differ.
- The save schema is unchanged; an older HAARP boss-zone record may reset because
  the encounter map changes.

</details>

## v0.2.3 - content version 21 (needs XML2 Fix 1.6.0)

This build needs **XML2 Fix 1.6.0**: in the launcher, **Rebuild**, then **Play** (the launcher installs the fix after
the build). Your saves carry over.

**Updating**

- **Online, both players need 0.2.3 with XML2 Fix 1.6.0.** A 0.2.2 / XML2 Fix 1.5.0 player and a 0.2.3 player refuse
  each other at join, with the reason on both PCs.
- **Old saved zones keep what they had.** A zone your save already holds keeps its objects, and anything this
  version adds to that zone (a hazard, a crate) starts fresh. If a save's zone record can't be matched safely, the
  game does what it did before and rebuilds that zone from scratch (a zone with identical crates is one such case).
  The save format is unchanged.

**The big ones**

- **Co-op *Load Saved Campaign* works, in seconds.** The host's saved campaign used to stall at "Sending game
  information..." or end the session. It now reaches the joining player in a few seconds on a LAN (two real saves took
  about 15 and 5 seconds from clicking to playing, against minutes before), without stalls. Both PCs need 0.2.3 with
  XML2 Fix 1.6.0.
- **Connect by IP and the LAN search work between port builds.** Before, two port games could only find each other
  through the OpenSpy list. Builds that differ (another builder release) still don't list or admit each other.
- **Fires, spikes and electricity hurt again** (issue #104): the placed hazards that had no model, in 57 levels, keep
  their authored size and hurt heroes and enemies as in the first game. The opening fire hits about every 0.4 seconds
  (3 health a hit) with its knockback, and stops hurting when you step out of it.
- **Enemy combat closer to the first game** (issue #101, progress): the HAARP gunmen flinch when you hit them and stop
  firing, as in the first game; enemy combos follow its button timing; a hero's stun animation plays at the original
  speed and the hero recovers control as soon as in the original, and a refused or interrupted stun no longer comes
  back after recovery.
- **Danger Room:** the training robots (and other opponents that start cloaked) are visible and take damage, their
  health bars go down, and a lesson that starts without a full party gets the first game's four heroes, Phoenix among them. A robot protected by
  a lesson only goes down to the move the lesson names - other moves lower its bar but don't finish it.
- **Sentinel flashback:** the Sentinels' eye scan, the surface hits and the acquired-target effect are back, and the
  Sentinel's head aims naturally at a target.

**Fixes**

- **The HAARP ice-tunnel crates** (issue #103) settle on the floor, survive the first ordinary punch and break on
  later hits, instead of falling through the floor. Every landing with nothing to collide with now deals no damage, as
  in the first game.
- **Two more fall spots** (issue #22, partly): two fall volumes whose first-game position is proven are on, so a hero
  who falls there dies as in the first game. The rest stay off (known issues).
- **Co-op robustness:** the game checks the network messages it receives before using them and drops malformed ones
  instead of acting on them. Ordinary game messages that carry extra bytes, or that the game sends while a movie plays,
  are not dropped (a Blob-fight kill used to produce false drops on the joining player).
- **Launcher settings survive a rebuild:** the Display and Discord settings the launcher keeps in `xml2-fix.ini`
  stay as they were; the builder merges its own keys into the existing file.
- **Optional testing tools:** XML2 Fix's `[TestMode]` (off by default and not written by the builder) adds Forge access
  at Xtraction points and F8 / F9 / F10 tools for testers. Either switch blocks online play until it is off and the
  game restarted.

**Known issues**

- **Online co-op and the first game's solo story segments** (issue #106; Wolverine's opening, Magma's mansion tour):
  the second online player has no hero while the story seats one hero alone. A co-op *New Game* starts with Wolverine
  alone, and when a solo segment begins mid-campaign the second player is dropped at the next level load. Use *Load
  Saved Campaign* for co-op and start a new session from a save after the segment; the fix is planned with 0.3.0's
  drop-in co-op.
- **Toad's fight at HAARP** (issue #105) skips the jets, his armour and the soldier waves; planned for 0.2.4.
- **Enemy powers and stun** (issue #101): enemies still use powers and stun heroes more than in the first game
  (Brotherhood, HAARP); only parts of it are fixed here.
- **A double jump on slopes or the HAARP bridge** can land a hero outside the play area (issue #22); the remaining
  fall volumes are off.
  *Correction, 2026-10-23: 18 double jumps on the 0.2.3 release did not reproduce it (see issue #22).*
- **Attack and impact sounds that loop** in the Manhattan streets (issue #79) were not reproduced lately, but no fix
  is claimed.
- **Loot and the item shop** (issue #6) are not in this version.
- **Cosmetic reports** from the first playthrough (issue #54) are still tracked.
- **Hazards** (issue #104): 57 levels were fixed from an audit of the game's data, but only three rooms were played
  in the checks. Report any fire, spike or electricity that still doesn't hurt.
- Co-op was tested with two copies of the game on one PC; the two-PC pass, on one network and across the internet,
  is 0.3.0.

<details><summary>Technical details</summary>

- Content version 21, catalogue revision 7, lobby token LC30 (0.2.2 was content 19, catalogue 6, LC27). Online, both
  players need the same content version.
- New `[Game]` keys written for every XML1 build: `ObjectWorldImpact`, `StunRule`, `DangerRoomParty`,
  `Xml1LockOnEffects`, `Xml1LockOnAim`, `BoxHarmOrigin`, `DangerRoomHealthBars`, `HarmSingleChain`; new `[Online]`
  keys `FastTransfer` and `ReceiveValidation`. `[Game] NpcPowerRule` is at revision 4 (per-button combo delays).
  The builder refuses an existing fix companion that lacks a key it needs.
- Gun priority: XML2 adds priority 5 to a gun move; the build keeps the first game's priority 0, so a real hit that
  doesn't kill can interrupt a firing gunman. 18 gun-style files change.
- Hazards: model-less fire / spike / electrical volumes keep their authored bounds (output audit over 57 zones;
  live checks in three rooms, the rest need campaign testing).
- Danger Room: the validator V16 now checks the first game's lesson goals (FR101-105 count specific combat
  connections, FR112 counts seven grabs, CHMAG needs 20 kills).
- Co-op: the receiving side reserves room in all four shared network pools, defers a datagram it cannot store instead
  of acknowledging it, and ends a session that stays blocked for 30 seconds with one log line. *Fast transfer* sends
  the 2 MiB campaign image as data and zero-run records with up to 32 in flight and a 400,000 bytes/s budget, and both
  PCs must use it. XML2 Fix 1.6.0's agreement protocol is 4 (1.5 and older peers are refused).
- Cold saved-game loads must use the normal Load Game menu: the console `loadgame` command from a fresh main menu
  bypasses the controller setup.

</details>

## v0.2.2 - content version 19 (needs XML2 Fix 1.5.0)

This build needs **XML2 Fix 1.5.0**: in the launcher, **Rebuild**, then **Play** (the launcher installs the fix after
the build). Your saves carry over.

**Updating**

- **Old saves catch up once.** The first time an existing save is loaded, every hero gets the fifth-level points the
  new rules give (1 skill point and 4 stat points for each fifth level already passed), and each hero's automatic stat
  growth is recomputed with the first game's tables; comic rewards are kept. The next save records it, so it happens
  only once.
- **The fix and the build go together.** The new rules need XML2 Fix 1.5.0: an older `dinput.dll` ignores them without
  a word. A build that finds an older fix in its folder warns and names the missing settings; the launcher replaces
  the fix right after the build (standalone: copy the 1.5.0 `dinput.dll` into the folder).
- **Online, both players need 0.2.2 with XML2 Fix 1.5.0.** A 0.2.1 / XML2 Fix 1.4.0 player and a 0.2.2 player refuse
  each other at join, with the reason on both PCs.
- **Going back to 0.2.1?** Copy `Documents\Activision\X-Men Legends` somewhere before updating. XML2 Fix 1.4.0 never
  overwrites a save 1.5.0 wrote without keeping it (as `.lcsave.newer`), and after going back and forth it can refuse
  to save the profile at all; put your copy back to go back cleanly.

**The big ones**

- **Enemy AI** (issue #101): enemies pay energy for powers, decide every 2 seconds, need at least half their energy, and use the first game's melee combos. Visibility uses the first game's geometry and query scheduling. Heroes still spend more time stunned than in the original; that part of #101 remains open.

- **The scan turrets fire again** (issue #4): the HAARP exterior missile tanks scan, turn, lock on and fire their
  three-missile salvos with the first game's timing, the Arbiter and Weapon X tripod guns sweep and fire their
  bullets, and the Hive tanks' flame turrets burn whoever comes close. All of them can still be destroyed, and stay
  destroyed in your saves.
- **Xtraction points offer the first game's services** (issue #63): Load, the Danger Room, the Healer and Forge where
  the first game had them; the main menu's Danger Room is greyed until Phoenix has joined your campaign. Online,
  Load and the campaign-gated choices are greyed with other players, as XML2 does.
- **Skill ranks cost what they cost in the first game** (issue #35): the ranks that open a new form of a power cost
  2 skill points, and every fifth level gives 2 skill points and 8 stat points instead of 1 and 4.
- **Heroes grow like the first game's**: the automatic stat bonus of each level follows X-Men Legends I's bruiser /
  support tables instead of XML2's classes. Bruisers end up with more health, supports and mental attackers deal
  more damage.
- **Breakable parts** (issue #3): Juggernaut's helmet and the Sentinels' arms can be broken again, with their effects,
  and a Sentinel without an arm can't use that arm's attacks. Boss "armour off" moments now really take the armour off
  (Juggernaut's helmet, Blob's pillars, Pyro and Toad): those fights were much tougher than the first game's.
- **Resistant enemies stand their ground again**: the first game's resistance talents also stop hit reactions, so
  HAARP officers and the other resistant enemies (41 of 74 resistant entries) are no longer launched or knocked back
  by a punch-punch-slam; plain soldiers still are. A boss whose armour comes off takes full damage again but
  still isn't launched, as in the first game. XML2's "Resistant" line under enemy health bars goes with it (the
  first game had none).
  *Correction, 2026-10-23: the first game does show resistance labels (for example "Physical Resistant"); 0.2.4
  restored the text with its colors. The enemies were resistant the whole time (a Brotherhood Revolutionary takes
  0.2 of physical damage); only the label was missing in 0.2.2 and 0.2.3.*
- **Solo mode** (issue #5): the first game's solo boxes and bridges keep the rest of the party behind and regroup it
  afterwards, so followers no longer walk into the void at the gaps.

**Fixes**

- **Leaders** (issue #15): leaders drop as in the first game (no chance roll, four drops, one of them a health pack, energy pack or Xtreme pip)
- **Enemies die below 1 health**, as in the first game, so none fights on at a fraction of a point with its death
  script and drop waiting (the HAARP keycard officer).
- **A hero who takes over from a fallen one stands still** until you move them, as in the first game, instead of
  finishing the walk its AI had started (in the ice tunnel's solo crossing, off the edge).
- **Reviving a fallen hero costs the first game's price**: 200 x (your highest hero's level) squared. That is much more
  than before at high levels (level 24: 115,200).
- **Packs restore a quarter** of health or energy, as in the first game (XML2 gave a third).
- **Fall volumes work as in the first game** (issue #22): the East Rooftops and the second sewer room kill a hero who
  falls, and every fall volume keeps the first game's round shape.
- **Pads and the Codex**: *Defaults 1/2/3* in the controls menu keep your pad layout (XML2 Fix issue #9); in a
  cinematic the mouse no longer outlines or moves heroes (issue #85); the Codex list highlight covers the whole row
  (issue #97).
- **Exclusive fullscreen** asks only for a mode your screen can show, 8x anti-aliasing is really 8x, and a failed
  start no longer resets your display settings (issue #84).
- **More room for scripts**: the game's limit of 320 script functions is raised to 1024 (the first game's scripts and
  the fix's own had filled it).
- **Fixed: Professor X sat inside his desk at the first mansion visit** (issue #54). XMen2.exe seats a spawned character
  one walk cell away from where the first game does in about 91 of 233 cases; three of Xavier's spawn points now land
  on the original's seats (his desk, the first subbasement, the second visit's war room). A save that already holds a
  record of one of those rooms (a save keeps up to five zone records) restores the spawn point it saved there, so he
  keeps the old seat in that room; a new campaign, or a room the save holds no record of, gets the new one (SPEC 41.1).
- **Fixed: two hit sounds from an empty room on entering the dormitories** (issue #79). Builds ask XML2 Fix for
  `[Game] PlacementCrush=xml1`: objects being settled on the floor no longer crush each other (SPEC 63.4).
- **Fixed: the health / energy pack sound sometimes played lower** (issue #82). That was XML2's double heal and its own
  "double" sound; builds ask XML2 Fix for `[Game] DoubleHeal=0`, so packs heal as in the first game and the stats screen
  drops the double-heal lines (SPEC 63.5).

**Known issues**

- Professor X keeps his old seat in the rooms an existing save already visited (above).
- The revival price is the first game's, steep at high levels (above).
- 18 fall volumes are still off (#22): several sit in water or rooms followers can stray into, and need their own
  checks.
  *Correction, 2026-10-23: 18 was a miscount. The 0.2.2 release left 17 zones (25 placements in 15 maps) off, and
  0.2.3 switched two on, which leaves 15 (20 placements in 14 maps).*
- In co-op, *Load Saved Campaign* can stop at "Sending game information..." (0.2.1 too). Start a new campaign in co-op
  for now.
- Co-op was tested with two copies of the game on one PC; the two-PC pass, on one network and across the internet,
  is 0.3.0.

<details><summary>Technical details</summary>

- Content version 19, catalogue revision 6, lobby token LC27 (the catalogue's keys and domains are unchanged; only the
  data hashes of `shared_talents.lcbind` (resistance talents) and `herostat.lcbind` (stat growth classes) differ).
- New `[Game]` keys written for every XML1 build: `PlacementCrush`, `DoubleHeal`, `RankCosts`, `LevelSkillPoints`,
  `LevelStatPoints`, `Xml1Multipart`, `X1Leader` (with `Data\x1leader.txt`), `SoloMode`, `DeathRule`,
  `DangerRoomGate`, `RevivalCost`, `Xml1Turrets` (with `[Xml1Turrets]`), `PackAmount`, `DeathSwitchClear`; `[Limits] ScriptFunctions`.
- New build checks: V52 breakable parts, V53 removable resistances, V54 leader list, V55 fractional health, V56 scan
  turret contract, V57 script function names, V58 Codex highlight, V59 solo mode calls, V60
  resistance talents; V26 compares fall volumes with
  the source; V32 checks the Load bit of every Xtraction point.
- SPEC 41.1, 52, 63.4-63.6, 79.1, 88-94; heroes check V-H17 (autospend classes).
- `xml1-builder build` over a folder that still holds an older XML2 Fix (the launcher's Rebuild runs before it
  installs the new fix) finishes with warning `W_XML2FIX_OLD`, naming the keys that DLL doesn't know, instead of
  failing at the last step; `build_xml1.py` and the harness still refuse an older DLL.

</details>

## v0.2.1 - content version 18 (needs XML2 Fix 1.4.0)

- **Fixed: builds with the released builder failed at the last step** ("typed entity ids: the shipped scripts could
  not be classified; no registry written"). The new save step looked for its script table beside the program
  instead of in the builder's bundled data, so every build from the 0.2.0 download stopped there. Builds from source
  were not affected. Nothing else changes: the game a 0.2.1 build makes is the one 0.2.0 was meant to make, so
  just run the build again (Resume or Rebuild); your saves are untouched.

## v0.2.0 - content version 18 (needs XML2 Fix 1.4.0)

This build needs **XML2 Fix 1.4.0** (the launcher installs it). Rebuild, then start the game once: your saves are
carried over into the new format by themselves. Saves made with 0.2.0 don't load in earlier builds.

**Updating**

- **A new save format, and your old saves come with you.** The first time the rebuilt game starts, every existing
  save and the profile are converted once into a new `SaveLC` folder next to the old `Save` folder, which is never
  touched. Heroes, levels, stats, talents, inventory, mission progress, unlocks, heard conversations and trivia
  answers carry over, from every builder version. `SaveLC\legacy-import.txt` says what happened to each file.
  Future updates can change content without breaking saves.
- Rebuild **and** update the fix: the format needs both. Updating only `dinput.dll` doesn't make the save tables.
- Want to be able to go back? Copy `Documents\Activision\X-Men Legends` somewhere first. Older builds play the old
  `Save` folder as it was before the update; they can't read the new `.lcsave` files.
- Every save keeps the one before it as `.lcsave.bak`. If a save or load is ever refused, the game says why and the
  file on disk is kept as it was: report it with `xml2-fix.log` and `SaveLC\legacy-import.txt`.

**The big ones**

- **Enemy AI** (issue #101): enemies pay energy for powers, decide every 2 seconds, need at least half their energy, and use the first game's melee combos. Visibility uses the first game's geometry and query scheduling. Heroes still spend more time stunned than in the original; that part of #101 remains open.

- **The first game's combat balance** (issues #14, #94). Enemy health and damage, the heroes' strength bonus, power
  attacks, melee hit chance and the original seven basic melee attacks are back to X-Men Legends' numbers; enemy
  punches hurt again. NPC guns roll the first game's +/-30 % damage (they hit about 13-15 % too hard before), and
  hero health is scaled to match: a fresh level-1 Wolverine has 80 HP, the opening riot cops 40. Expect fights to be
  harder than in 0.1.12.
- **The classic main menu.** The bright blue Cerebro room, honeycomb panels behind every button, the original fonts,
  colours and help line, in a widescreen layout that moves everything together instead of stretching it. The mouse
  lands anywhere on a button, also in a window Windows resized for display scaling.
- **Bigger rooms stay complete.** The engine's object limits are raised (general objects 224 -> 768, world handles
  256 -> 1024), so crowded rooms no longer silently drop props and projectiles: the HAARP freeze gun fires, Magneto's
  arena keeps its props, and about 940 objects across 116 zones that went missing before are there.
- **Master Mold fights like the original** (issue #27). His warp-core shield, the cores that bring it down, his
  platform and floor attacks and their original timing, through to his defeat and the ending. Loading a save made
  mid-fight keeps your progress.

**Fixes**

- Mystique's pistol and smash bursts keep every shot's sound and muzzle flash (#83).
- Explosions count their first hit the way the first game did; Avalanche's rocks, Magneto's props and other thrown
  objects deal their original explosion damage.
- Soldiers throw the right grenades; the freeze-gun leader's flashbang drains energy with a white flash (#36).
- Pyro reaches his fight position at HAARP and can pass his own fire barrier (#93).
- Keycards lying in the world show their model instead of a yellow question mark (#96).
- The equipment shop is reachable from Xtraction points after you have met Forge (#95).
- The personal items in the mansion bedrooms show their picture framed in its window, with readable text (#47).
- Hero power icons show the first game's complete art in round frames (#53, #73).
- "Enter the HAARP facility?" no longer answers itself while the accept button is still held (#77).
- Floating props settle onto the floor on a fresh visit; positions a save already holds stay as they were (#81).
- Trivia answers are remembered in every act, including acts 8 and 9.
- Heard conversations stay heard after loading, even when content changed between versions.
- The bridge tanks drive out in older saves instead of appearing after the cutscene.
- Equipped items in older saves import correctly when the save's talent era differs.
- No crash on Quit from the classic main menu.

**Co-op**

- Saving during co-op no longer freezes the game long enough for the other player to be disconnected.
- Players whose builds or gameplay settings differ are refused when they join, with the reason on both PCs (the host
  sees it in the lobby, or as a short line in play), instead of joining and drifting out of sync.
- Co-op works in tests with two copies of the game on one PC. A dedicated co-op pass with two PCs, on one network
  and across the internet, is planned for 0.3.0: please report disconnects, and whether the game showed its lag
  warnings first.

**Known issues**

- Scan turrets in HAARP and other zones are still inert (#4; planned for 0.3.0).
- An officer killed while pinned against a door in HAARP can drop his keycard behind it, out of reach: load your last
  save if it happens (fix planned for 0.2.1).
- Exclusive fullscreen can fail on high-refresh desktops (seen at 2560x1440 and 180 Hz) and the game then resets its
  own resolution settings: use borderless, the launcher's default (fix planned for 0.2.1).
- The Danger Room is always open from the main menu; the first game opened it at a point in the story.
- An online save made after destroying objects was refused once in an earlier test build (after a connection drop).
  Two fixes since address the likely causes and destruction saves have passed online since, but that case was never
  reproduced: if a save is refused, your existing save file is kept - please report it with `xml2-fix.log`.

<details>
<summary><b>Details</b> (technical list of every change)</summary>


- Centre the classic main menu in every display mode. The game already centres the original 4:3
  composition at any aspect; the `--main-menu-layout widescreen` used for candidate 0.2.0j added a
  48-unit shift on top, so the logo and panels sat about 7 % of the width right of centre (borderless
  2560x1440 and windowed alike). Classic is the only composition now; `widescreen` is accepted as a
  retired name for it. Only `UI/menus/x1_menu_main.IGB` changes; save files and mouse rows are unaffected.

- Own `[Limits] EntityCapacity=1` for port builds (SPEC 85): the companion DLL raises the entity domain to
  32 actor / 768 generic / 1024 World handles, so the props, projectiles and triggers the stock 224-slot
  arena refused (943 refusals across 116 zones in the 0.2.0 census; the HAARP freeze gun) exist again.
  The builder writes `Data/lcsave/typed-entity-ids.txt`, the registry of the shipped scripts' typed
  entity-id zone variables (`tools/xml1build/typed_entity_ids.py`), which the DLL verifies before it
  migrates a legacy save; V50 checks it against the shipped scripts. The Python lcsave takes an explicit
  native layout (retail or the expanded E10A2) and the LC required-feature marker; retail outputs are
  byte-identical.

- The companion agreement now carries explicit effective rules and entity/token layout, with a shared
  registration API for capacity/controllers and immediate native incompatibility messages/cleanup.

- The companion explosive first-hit fix now verifies effective installed rules between peers before joining.
  Differing/failed rules are refused independently of the assigned release identity.

- Request the companion XML2 Fix first-contact explosion rule through `[Game] ExplosiveFirstHit=1`.
  This restores the original fresh blast attack ID without changing entity attributes or save records.

- Resolve XML1 numeric value codes in map-local entity declarations, restoring explosion damage on
  Avalanche rocks, Magneto props, and other inline projectiles. Explosion damage keeps the original scalar
  minimum; V19 rejects unresolved inline codes and ranges. Entity and placement order are preserved.

- Persist trivia answers in every campaign act. New builds use compact native trivia bits with the
  companion XML2 Fix hooks; LC question identities and legacy sparse-save imports remain unchanged.

- Restore classic main-menu back panels, blue colours, original English typography with PC
  glyph fallback, and the help footer. Bright Cerebro rendering needs
  the companion XML2 Fix backdrop hook. The original profile gate remains a separate question.
- Match main-menu mouse regions to the full visible panel widths with disjoint row seams
  through the companion DLL's `ClassicMainPanelBounds` setting.
- Main-menu (and every menu's) mouse needs the companion XML2 Fix with the client-area mapping
  fix: a window resized by a DPI change no longer drifts the hover downwards or leaves Quit
  unreachable, and the focus no longer flips inside a row's lower third.

- Supply the effective packed stage binding for the native Master Mold controller
  and enable it only for first-game builds with that validated contract. The companion
  DLL restores the shield/core encounter and registers it as shared gameplay rule 3, so
  co-op stays available between matching builds and refuses peers whose controller
  state differs (SPEC 86). Older DLLs ignore the keys and retain the existing fallback.
- Import equipped legacy items using the detected item era, including restore-bank equipment, when the
  campaign's talent era differs. Attribute restore-bank talent evidence to its actual stats-table owner.
  The companion XML2 Fix converter and semantic dump apply the same corrections; no save-format change.


- Preserve existing streamed cutscene entities when loading legacy saves into builds that pin them. The
  companion XML2 Fix loader associates unique saved states with their current numbered placements;
  explicit removed states remain removed. Existing LC imports benefit without reconversion.


- **Pyro reaches his intended fight position** (issue #93). The HAARP intro finishes his scripted approach at
  its existing doorway waypoint after spawning him. XML2 world collision had stopped him behind the doorway
  before the fire barriers rose. The barriers, allegiance, combat moves and death-script progression retain
  their authored settings. V47 checks the intro correction and its waypoint.

- **World-placed keycards show their model instead of the missing-model marker** (issues #96, #98). The
  HAARP train-car keycard and the dropped proximity/ID keycards are placed as world pickups whose model
  comes from the items table; XML2's same-named items table entries ship no model (XML2 never places them),
  and the xml2-wins merge kept that gap - the pickups rendered as a floating yellow question mark under a
  correct hint arrow. A same-name items-table entry with no model now takes XML1's model, the model ships
  in the items package, and a validator refuses any referenced item without a packaged pickup model.
  SPEC 77; the check V46.
- Restore equipment-shop access from Xtraction points after contacting Forge (issue #95). The companion
  XML2 Fix menu hook keeps native Save and team handling, and respects each lite point's original shop
  permission. The option uses the port's existing shop adapter. SPEC 79; V48.

- **NPC gun damage rolls the first game's minimum-based +/-30 % draw.** The first game stores only the
  weapon damage code's minimum and rolls one integer draw between trunc(min x 0.7f) and trunc(min x 1.3f) on
  every shot (all gun types); the port instead rolled the whole authored code range, inflating gun damage by
  roughly 13-15 % on average (the HAARP leader's freeze gun 34-64, mean 49, instead of 50-63, mean 56.5).
  Generated gun-shot triggers now carry the draw's bounds, and thrown explosives' `explodedamage` carries the
  code's minimum only, as XML1's entity parser reads it (flashbang 15, not 15-18). SPEC 76; the check V45.
- **Correct the Arbiter talent overflow while retaining the original shared pool.** NPC powers and immunities
  remain in the save-stable63-name shared list. Per-set/union NPC files are not shipped: engine filename
  truncation and default-ID collisions made that approach unsafe. Only reviewed noncombat Arbiter props'
  unnecessary talent precache is removed when it would exceed the registry budget. Fighting heroes keep
  their precache. V44 retains the complete roster scan and checks100names,9files,63-byte formatted paths,
  default-ID interval collisions, and records every justified prop-file removal. Save catalogue revision5
  is appended without renumbering existing identities.
- **A new save format; every old save is carried over once, automatically.** With XML2 Fix 1.4 the build starts
  in the LC save format: at the first start the fix converts the old saves it finds, once per file, into the new
  `SaveLC` folder - the old folder is never touched. Saves of every builder era load: heroes, levels, stats,
  talents, inventory, mission progress, unlocks and the profile all carry over, including the talent moves of
  0.1.8-0.1.9 (a save begun before 0.1.8 gets Grab back; the 0.1.8/0.1.9 moves are undone) and the older shift
  from before 0.1.5. The new format names everything by a permanent id from a catalogue the build ships
  (`Data\lcsave\catalogue.lcc`, `legacy.lcm` and a `.lcbind` beside every save-bound data file, checked at every
  start), so future content can retain those save ids. The build writes `[Save] Format=lc`
  and needs XML2 Fix 1.4 (SPEC 70, SPEC-new-save; the check V39).
- **The first game's combat balance, on for every build** (issue #14). Enemy health and damage and the heroes'
  strength bonus are the first game's again (enemy health per body point, the stat bonus, might, power attacks,
  the melee hit chance and rounding through xml2-fix's `[Balance]` section), and the seven basic melee attacks
  and the power-attack rule are in the build's data. Was prepared off by default; 0.2.0 turns the switch on
  (`xml1build.balance.X1_BALANCE`, the test override dropped). SPEC 69; the check V38.
- **Co-op compatibility metadata** (decision D5). `[Online] GameVersion` is the release's lobby token, `LC26`
  (content 18, catalogue 6; `tools/xml1build/release_identity.py`), separating these lobbies from earlier port
  generations and candidates. The ini also records the save-table content fingerprint, as metadata: XML2 Fix 1.4
  compares the peers' effective gameplay rules and entity layout when a player joins (the shared gameplay
  agreement), not the fingerprint.
- Continuing LC saves retain legacy/KEEP payloads and documentary keys. Core capture metadata records opened
  placements, numbered identities and completeness; Python/C++ canonical KEYS bytes match (SPEC 70.5).
- Power slots retain their usable flag through conversion, save and load (HERO 1.1).
- Melee weapons contribute their authored fixed bonus before Strength and Might; damage rolls use inclusive
  integers. The opening cop's punch is 7 or 9 damage (SPEC 69.5; V40).
- Includes every 0.1.12 content and XML2 Fix 1.3.2 change listed below.
- **Fixed: every shot of Mystique's pistol bursts keeps its fire sound and muzzle flash** (issue #83).
  Port builds request `[Limits] MoveTriggers=64` from the companion XML2 Fix patch. Her attack keeps its original
  holster/redraw events and all six sounds (23 triggers); smash keeps all ten sounds (27 triggers). The previous
  build emitted two smash sounds. Conversion and validation share the capacity written into the port ini.
- **Checked: the health / energy pack sound** (issue #82). The port plays the first game's own pack recordings
  (the merged bank's entries are the same audio the Xbox ships) at the original 22050 Hz; verified in game
  through a DirectSound trace of the engine's sound calls. No cause for the reported "sometimes lower pitched"
  was found in the port's data or playback.
- **Fixed: the mansion bedrooms' personal items filled the screen** (issue #47, follow-up). 0.1.8 gave every item
  its own picture, but the engine draws it as a background sprite stretched over the whole menu screen, so the
  painted scene covered everything. Each picture is now re-framed to show inside the same window the first game
  drew it in, with the scene's colours continuing to the edges. XML2 Fix's default-on PersonalItemText fix
  places this menu's opaque background behind its description, so the text is visible too.
- **Fixed: hero power icons show the first game's complete art inside round frames** (issues #53, #73).
  The first game's four 64px icons were read as 32px quarter-crops and drawn square over the round frames.
  The builder now resamples each complete icon into the second game's 128px 4x4 sheet layout, preserves
  bottom-up image storage, and bakes circular alpha into the icons. The intended generic passive fallback
  is included in cell 4 so the skills screen retains its passive icons. Image references stay unchanged.
  Validator V-H15 checks the converted pixel layout and references; synthetic regression tests cover the
  layout, orientation, image references and bright-colour codec interpolation.

- **Soldier grenade choices** (issue #36). Holder-specific movesets carry the grenade named by the weapon
  or unanimous spawner override; nuclear-plant guards receive their missing grenade moveset. Matched HAARP
  checks confirm the freeze-gun leader's flashbang drains energy with a white flash while soldiers retain
  ordinary damage grenades. The original explosion modifiers are preserved. Confusion behavior remains
  unverified. SPEC 72 and validator V43 cover styles, packages and modifiers.

- Resident props selected for floor placement preserve the original numbered-instance prefix (#81; SPEC 71, V31/V41).
- Port builds enable `[Game] ConfirmationRelease=1` (#77) and retain `[Limits] EffectCurves=3600`.
- Hero health uses `[Balance] HeroHealthPerBody=2.5`: scaled level-1 Wolverine has 80 HP.

</details>

## v0.1.12 - content version 15 (needs XML2 Fix 1.3.2)

This build needs XML2 Fix 1.3.2 (the launcher installs it). With an older fix the game starts, but the ladder,
objective, STAT, wall, effect and Xtraction-menu changes below do nothing. Saves of earlier builds load as before.

- **Fixed: soldiers waiting at the top of a ladder now climb down** (issue #32). In the sewers and in the Arbiter's
  levels the first game sends soldiers down a ladder into the fight; here they stayed up at the top, out of reach.
  They now slide down as in the first game. Soldiers that the first game puts straight on the floor stay there.
- **Objectives read as in the first game once they are done** (issue #8). The first game changes an objective's
  text on the Objectives page when you complete it (for example after the fight with Mystique); here the page kept
  the original instruction. It now shows the first game's completion text.
- **Fixed: STAT pickups gave no point to spend** (issue #10). They raised Body by itself. Now the hero who picks one
  up gets one attribute point to spend on the stats screen, as in the first game.
- **Sturdier objects break as in the first game: to powers and Might, not to plain punches** (follow-up to issue
  #51). The first game gives every object a strength from 0 to 10 and breaks it only with an attack at least that
  strong: a punch is 1, powers are higher, and Might adds 3, 6 or 8. The engine only knows 0 to 2, so walls such as
  the one in HAARP's barracks either could not be broken at all or, since 0.1.8, broke to any punch. That wall now
  takes Wolverine's Claw Flurry and shrugs off his punches, a desk computer needs Might or a stronger power, crates
  and lockers still break to anything. Attacks on enemies are unchanged.
- **Fixed: fires and powers without their particles in busy areas** (issue #68). With four heroes, some areas
  needed more effect animations than the engine keeps: the effects loaded last were drawn without particles - the
  burning bench in Central Park was a faint glow, and a hero's power could lose its sparks. The game now has room
  for four times as many.
- **Removed: the pause menu's Blink Portal** (issue #89). It is X-Men Legends II's: it opened a portal to that
  game's towns, with no way back to this one except an earlier save (saving there overwrote the slot with a town
  save). The first game had no portal. Its place in the pause menu is now an empty slot.
- **The water channel in one of the first sewer areas is deadly again** (issue #22). 0.1.9 switched off 17 shallow
  fall areas until each was checked in game; this one, between two walkways, was checked and kills a hero who falls
  in, as in the first game.
- **Fixed: the Xtraction menu offered X-Men Legends II's Xtract world map** (issue #46). Every Xtraction point's
  menu had an Xtract choice that opened X-Men Legends II's world map of its five town centres; the first game's
  menu has no world map. The menu now offers the title, Change Team and Save only, from the first mission on.
  With the pause menu's Blink Portal gone (#89), no route into X-Men Legends II's towns is left. XML1's Load,
  Danger Room, Healer and Forge choices are still missing at every point (as in 0.1.11).
- **The first HAARP mission starts with the first game's recommended team** (issue #76). Its team selection
  opened with Magma, carried over from the briefing; the first game seats its recommended four (Cyclops, Iceman,
  Storm and Wolverine) and lets you change them. Missions with a complete recommended team in the first game's
  data do the same. Loading a save already inside HAARP is unchanged.
- **Fixed: Rogue's Southern Strike dealt no damage at rank 1** (issue #78). Its three punches only knocked enemies
  down until a second point was spent. At rank 1 they now deal the first game's damage; Cyclops' Optic Sweep and
  X-treme power had the same fault and are fixed too. Powers that do no damage at rank 1 in the first game stay so.
- **Fixed: blue Xtraction points did not glow** (issue #74). Only the mansion sub-basements' purple point glowed;
  the blue points used X-Men Legends II's models of the same name, which lack the glow. They now use the first
  game's.

New build checks: V33 (every object carries the first game's strength next to the engine's), V34 (no soldier
placed on the floor gets the ladder slide), V35 (the pause menu has no portal), V36 (the recommended team before a
mission's team selection) and V37 (the first game's Xtraction beacons; no power left without its rank-1 damage).

## v0.1.11 - content version 14 (needs XML2 Fix 1.3.1)

- **Fixed: 20 Xtraction points could not save, including the first one in the game** (issue #63). The point in
  Central Park before the Mystique fight, the flashback and Danger Room side areas, the five Weapon X areas, all
  eight mansion sub-basements and the two Master Mold areas only offered Change Team (after an X-Men Legends II
  tip on first use). They now open the same Xtraction menu as every other point, with Save. Not yet as in the
  first game: no Load, Danger Room, Healer or Forge choices at any Xtraction point, and the menu still has the
  Xtract world-map choice (#46); both need an XML2 Fix change. A new check (V32) keeps the old menu out. The
  scripts prepare stage reruns once.
## v0.1.10 - content version 13 (needs XML2 Fix 1.3.1)

- **Fixed (0.1.8 regression): games saved before 0.1.8 lost or swapped hero skills.** The save names a hero's
  shared skills by their place in a list, and 0.1.8 inserted Grab and the rifle fighting style in the middle of it
  and dropped an unused rifle style: a saved Leadership rank came back as Grab, and Acrobatics, Toughness and
  Mutant Mastery each as their neighbour. The list keeps its 0.1.7 order again, with the skills added since at the
  end. Games saved on 0.1.5 to 0.1.7 load with the skills they had there; games saved on 0.1.8 or 0.1.9 are moved
  the other way by this fix (see SPEC 61). A new check (V31) keeps the order.
- **Fixed (0.1.8 regression): objects of an old save in the wrong places.** In zones with a restored fall volume
  (the HAARP exterior and ice tunnels, two nuclear-plant and four sewer areas) and in the mansion sub-basement of
  the last act, a game saved before 0.1.8 put saved object states on the wrong objects: at the HAARP exterior the
  Xtraction Point was missing beside the X-Jet and the finish-objectives message appeared at the start. Saved
  objects are found on their own objects again (V31 checks the order).

## v0.1.9 - content version 12 (needs XML2 Fix 1.3.1)

- **Fixed (0.1.8 regression): the East Rooftops could not be crossed** (the first level; issue #22). One of the
  fall volumes restored in 0.1.8 is a slab under the whole rooftop map, and the ramp to the billboard dips into
  it: every hero died there. That volume is off again, and so is every other restored volume that lies just
  under a floor, ramp or ledge (15 more, in the Arbiter, the mountain, the nuclear plant and the sewers), until
  each has had a crossing test in game. The fall volumes over real pits stay on (HAARP's ravine and bridges, the
  ice tunnels, two nuclear-plant and four sewer pits). Saves are not affected.

## v0.1.8 - content version 11 (needs XML2 Fix 1.3.1)

- **Changed: the HAARP exterior ravine kills only the hero you control** (issue #22). Falling or double-jumping
  into the ravine under the ice bridge still kills the hero a player controls (either player in co-op). A
  computer-controlled teammate who slips off a ledge there is no longer killed: he rejoins the party when you move
  on, as before the kill volumes were restored. If you take control of a teammate who is already down there, he
  dies at his first jump. The other pits are unchanged. The fall-volume check (V26) verifies the new marker
  (SPEC 52, "Player-only ravine").

- **Fixed: the first game's heroes and villains were silent or spoke X-Men Legends II's lines** (issue #49).
  Wolverine, Jean, Emma, Gambit, Jubilee, Magma, Professor X, Psylocke and Rogue had no taunts, team commands,
  low-health or victory lines; Cyclops, Colossus, Iceman, Nightcrawler, Storm, Beast and villains such as Blob and
  Mystique used the second game's voice actors. The first game's lines are now found under the names the engine
  asks for, and they win over the second game's in the shared voice bank. A new check (V27) verifies every voice
  line. The sound prepare stage reruns once.

- **Fixed: rifle soldiers stood unarmed with the gun stuck to a fist** (issue #52, part). The HAARP, nuclear-plant,
  Weapon X and GRSO rifle soldiers now hold their rifles level and fire from the gun, with the first game's
  idle, fire and crouch-fire animations, and their full 7-shot bursts play. Damage per shot is unchanged (4-5); at
  the HAARP exterior two soldiers now take about 6.6 HP per second from a standing hero instead of about 5.3, because
  their bursts land in full. As in the first game, an enemy's gun now replaces its own fighting style (the HAARP
  flamethrowers and leaders fight in the hip-gun style). A new check reports a gun-armed enemy without its gun's
  style.

- **Conversation lines advance by themselves only where the first game's do** (issue #54). The rule now follows
  the first game's own: a line goes on without the player only when it has a voice and is flagged itself or by
  its file's last start condition. Lines without a voice, and lines flagged only through their reply, wait for
  the button again (75 lines); 4 voiced lines that the first game advances now do too (SPEC 34.2).

- **Fixed: invisible fires beyond HAARP's exterior walls** (issue #12): restore
  delayed start-on harm loops across imported content, including NYC, the Arbiter
  and sewers, and restart source-identified loops after scripted relocation.
  This builder workaround advances the first activation by its authored delay
  (one second in affected definitions); damage values, repeat intervals and
  extinguish reactions stay unchanged. V25 rejects remaining dead startup forms.
  Controlled movement, Iceman extinguishing and save/reload evidence is in `docs/issue-12-validation.md`.

- **Fixed: Mystique's pistols fired nothing** (issue #52, part). Her two-gun attacks in the first level now show
  muzzle flashes from both hands and tracers, and each hit does the first game's pistol damage (4-5). Her grenade
  already did damage (9-11 per explosion when it lands next to the hero); that part of the report was not
  reproduced. A new check reports any enemy style that still fires the first game's weapon event (SPEC 29.3).

- **Fixed: empty tutorial tips** (issue #50). Seven tips of the first game (six in the first mission, one in the
  mansion) existed only in console versions, which the PC game skips, so their panel opened empty. Each now also
  has a PC version (the PlayStation 2 wording, as X-Men Legends II did for PC), and a new check verifies every
  dialog has one (SPEC "Popup dialog platforms").

- **Fixed: Cyclops' face on every codex entry** (issue #48). The codex list now has no icons, as in the first game,
  instead of X-Men Legends II's icon column, which drew Cyclops for every character without an icon of their own.
  A new check verifies the codex menu (SPEC 55).

- **Fixed: bedroom items showing the loading screen** (issue #47). The first game's 36 personal items in the
  mansion bedrooms and their pictures are now converted, so examining one shows its picture instead of the mansion
  loading screen (or, for Wolverine's flag, a yellow and magenta panel). Their description text is not drawn yet.
  A new check verifies every item has its data and picture (SPEC 56).

- **Fixed: arriving at HAARP without Iceman (softlock), and Magma playable from the first mansion visit** (issue
  #55). Every mission start now unlocks the heroes the first game unlocked there, read from your own copy of the game
  (its mission list and executable); a build from an unknown executable stops with a message instead of guessing.
  Magma and the two Professor X forms are only placed in the party where the first game did that, until their own
  unlock; with forced parties off the team menu still offers them. Saves made inside a mission by an earlier build
  get that mission's heroes when they are loaded. Heroes an earlier build already unlocked stay unlocked (the game
  keeps unlocks per profile).

- **The first game's shared hero passives** (issue #34): critical strike (5 ranks, +2 to +10%, unlocking at levels
  1/7/12/17/22), might (3 ranks, heavier objects each rank), leadership (5 ranks of combo damage and combo XP) and
  flight (energy drain 40 down to 5 per second) replace X-Men Legends II's versions. Might's bonus melee damage has no
  engine equivalent and is not recreated. A save that holds more ranks than a talent now has keeps the maximum; the
  extra skill points are not refunded (SPEC 50 in SPEC_heroes.md).

- **Fixed: black portraits in conversations for heroes who are not in the party or the zone** (issue #13; seen with
  forced parties switched off, for example Magma's reply menus in the mansion). Zone packages now preload the
  portrait of every named speaker of their conversations, and a new check (V24) verifies it (SPEC section 49).

- Restore HAARP fire-wall loop startup and restart the visual at its scripted destination, preserving the non-smart damage path (SPEC 45).
  Before-and-after runtime verification is tracked with this issue PR.

- **Fixed: black spikes on some enemies** (issue #11; needs XML2 Fix 1.3.1) - the HAARP officer, the GRSO
  nullifier and flamethrower. They looked like broken weapons but were the character's own outline, drawn with
  another enemy's bones because the game treated the two outlines as the same mesh. The build now asks the XML2
  Fix to compare the bones too (`[Game] GeometrySharingBlendIndices`, SPEC section 44).

- **Fixed: the fourth hero having no powers in crowded zones** (issue #31; needs XML2 Fix 1.3.1). The game keeps
  at most 19 fighting and power styles loaded at once, and several zones of the first game need up to 22 with a
  full party, so the hero seated last lost their special moves. The build now asks the XML2 Fix for a registry of
  32 (`[Limits] FightStyles`), and a new check (V23) counts every zone's styles for the worst possible party
  against it (SPEC section 43).

- Generate long-range buoy networks from XML1 navigation grids and map bounds for XML2's shared hero, ally and
  enemy navigator (SPEC section 42). XML1 has no buoy data to convert. Generation respects native coordinate and
  pool limits, conservatively excludes gates/special transitions, and reports remaining coverage gaps.
  Empty navigation stays empty; per-zone build notes and validator warnings expose the limitations.

- **Fixed: pits and chasms that a hero could land in alive and never leave** (issue #22). The first game's lethal
  fall volumes work again in 29 zones (a double jump off the HAARP bridge, the mountain ledges, the nuclear-plant
  pit); the Arbiter's flooded room is left as it was until its crossing is revalidated. A new check (V26) verifies
  them (SPEC section 52).

- **Fixed: heroes could not lift or throw objects or grab enemies, and a wall inside HAARP could not be broken**
  (issue #51). Object weight and strength are mapped onto this engine's scales, every hero can grab, and the HAARP
  barracks wall breaks, so the mission can be finished (SPEC section 59).

### Known issues

- With four heroes some zones run out of effect data: a fire shows only a glow, or a hero's power loses its
  particles (issue #68; an engine limit, to be raised by a later XML2 Fix).
- Walls that the first game reserves for power attacks also break to ordinary combos (the first game's rule comes
  with a later XML2 Fix).
- The 20 "lite" Xtraction points cannot save (issue #63), and Xtraction points open X-Men Legends II's world map
  (issue #46).
- The port is easier than the first game (issue #14).
- Bedroom personal items show their picture but not their text (issue #47); the codex highlight bar sits slightly
  off; a profile that already unlocked Magma keeps her.
- At HAARP's ice bridge, face the icon from one or two body-lengths away when using Freeze Blast.

## v0.1.7 - content version 9 (needs XML2 Fix 1.3.0)

- **Magneto's shield works again** (Asteroid M). When he raises it he cannot be hurt until his helpers are beaten -
  the acolytes, then Sabretooth, then Mystique - as in the first game; before, the whole fight could be brute-forced
  in one go (SPEC section 36).
- **Shadow King's first form can be fought** (the Astral Plane finale). He used to sit on a floating pillar where
  hits never registered; he now starts on the arena floor, away from the party, and his shield phases hold for the
  first game's 30 seconds (SPEC section 36). His Xtreme-power shield break is not recreated; wait the shield out.
  The fight ends when the real Shadow King falls - his mirror images vanish with him, in any kill order (before,
  killing an image after him left the fight unfinished; found in a hand play-through).
- **Emma Frost's introduction in the mansion reaches her questions again** (fourth mansion visit). The
  conversation ended at her last line because its jump into her question menu pointed at another file, which the
  engine cannot follow (SPEC section 39).
- **Fixed: arriving in the mansion after the Shadow King mission dropped the hero out of the level.** The
  subbasement's default arrival point sat behind the war room's console desk; it now matches the war room's other
  visits (SPEC section 41). Found in a hand play-through.
- Optional objectives are listed as secondary objectives (SPEC section 37). The first game's completion text for
  objectives is still not shown (issue #8).
- The per-zone music settings the first game's zone files carry were never used by the first game either, so
  nothing is lost there (SPEC section 38).
- The first build is more robust: when an antivirus scan briefly locks the files a prepare stage just wrote, the
  builder waits for it instead of failing with "Access is denied".
- Master Mold's fight is unchanged: his warp-core shield puzzle needs enemies that shoot the cores, which the
  engine does not have; it stays an open issue.

## v0.1.6 - content version 8 (needs XML2 Fix 1.3.0)

- **Conversations advance by themselves again.** The first game let many lines run on without a key press once
  the voice finished (the mission briefings, the mansion tours, the hub chatter); on the XML2 engine every one of
  them waited for Enter. The builder now marks those lines and XML2 Fix 1.3.0 advances them when the voice ends
  (SPEC section 34). Spoken replies also play to the end instead of being cut off.
- **A SKILL pickup gives one skill point to the hero who takes it**, exactly as in the first game, through a new
  script function in XML2 Fix 1.3.0. This replaces 0.1.5's one-level-of-XP approximation (SPEC section 32).
- **All 19 Danger Room reward items load.** The engine's item table stopped at 375 enhancements; the fix raises the
  pool to 512 and the builder asks for it (SPEC section 32.3). Existing saves keep working: nothing is renumbered.
- **Fixed: the tank cutscene on the HAARP bridge never ended** (act 1, a softlock: the camera stayed on three
  guards and the game could not continue). The engine unloads a zone's distant objects to save memory, so the tank
  and the gate had been unloaded before the cutscene tried to move them. Every object a zone's scripts refer to
  by name is now kept loaded, as X-Men Legends II does for its own scripted scenes (SPEC section 35). Both tank
  reveals now play: the gate opens, the tank drives out, the guards come through. Found in a hand play-through.
- The launcher installs XML2 Fix 1.3.0 before offering this rebuild; standalone users need it in the game folder.

## v0.1.5 - content version 7

- **Fixed: a SKILL pickup levelled the whole roster.** Every hero, in the party or not, got 5,000 XP from each
  pickup. It now gives one level's worth of XP to the hero who takes it, which is the engine's way of granting one
  skill point (SPEC section 32). Found: the engine stops reading the item table after its 375th enhancement, which
  had also hidden the XP pickups and the astral stone; those load again. Most Danger Room reward items are still
  past the cut-off (noted, not yet fixed).
- **Fixed: bosses could be stunned, knocked down, grabbed and finished like henchmen.** The first game's inline
  immunity talents (Blob, Juggernaut, Pyro, Toad, Mystique, Magneto, Mastermold, Sabretooth, Shadow King, the
  bots, the Morlock bruisers' physical resistance) were dropped; they are now shared talents in the engine's own
  boss-resistance form (SPEC section 30). Checked in game: Pyro no longer goes down to Wolverine's smashes.
- **Fixed: melee did XML2's damage, not the first game's.** Punches and kicks inheriting the shared combat events
  did 2-3 where XML1 did 4-5, heavies 3-5 instead of 9-11. The first game's values are written onto the inheriting
  moves (SPEC section 33). Measured: Morlock light punches on Cyclops 3-5 before, 6-7 after.
- Fixed: twelve cloak triggers in six enemy styles used a render form the engine ignores (SPEC section 31).

## v0.1.4 - content version 6

- **Fixed: projectile and explosion damage from the first game's data read as zero** - the freeze and knockback
  guns' shots, grenades and flashbangs, incendiaries, Sentinel grenades, missiles, Shades' and Mystique's thrown
  attacks, and Magma's and Pyro's projectiles carried XML1 value codes the PC engine does not know. The zone import
  re-wrote those entity files without resolving the codes after the character converter had. Both import paths
  now resolve them, and the validator refuses a build that leaves one behind. Those attacks now do the first
  game's damage, so expect them to hurt (SPEC section 29.2).
- Preserve XML1 projectile damage and knockback values through the zone import pass. Zone imports could
  overwrite the character converter's numeric values with XML1-only codes that the PC engine reads as zero.
- Make each per-weapon power-style package load its own variant instead of the original shared style.
- Explicitly classify spawned weapon attacks as projectiles rather than inheriting the attack parser's punch
  default. Add final-output validation for entity value codes and style-package self references.

## v0.1.3 - content version 5

- **Fixed (0.1.2 regression): in zones with gun soldiers, the third and fourth heroes of the party had no power
  wheel** (holding the power key did nothing for them; the first two heroes were fine, and the next zone restored
  everyone). 0.1.2 pointed the soldiers at their new per-weapon power styles but their packages still listed the
  old style, so the engine loaded the new one on demand - and a style loaded outside the packages breaks the
  power registration of the heroes seated after it. The character and zone packages now list the style the
  soldier actually uses (SPEC section 29.1), and the validator refuses a build where a stats entry names a style
  no package carries. Reported from the HAARP exterior with a four-hero party; reproduced and verified there.

## v0.1.2 - content version 4

- **Fixed: X-Men Legends' gun soldiers fired blanks** (the GRSO mp5, laser, lightning, nullifier, freeze and
  knockback guns, the HAARP soldiers and flamethrowers, the pistol thugs): no tracer, no sound, no damage, and the
  flamethrower's flame was invisible. XML1 arms a soldier through a weapon table the XML2 engine does not have (its
  `weapon_fire` event is a sound event there), and XML2's AI only fires moves marked for it. Each weapon's damage,
  range, tracer, impact, muzzle flash and sounds are now written into a copy of the soldier's power style, and the
  moves carry the AI marking (SPEC section 29). Reported from the HAARP exterior; verified in game with the
  health bar.

## v0.1.1 - content version 3

- **Fixed: a hero's powers vanished from the power wheel after loading a save in some zones** (nyc1_1_2b and
  nyc1_1_3 for Cyclops, the two Danger Room flashback zones with him, the sewer hub zone where Gambit is met,
  nuke2_2 for Colossus, the Blackbird arbiter zone). Those zones precache the hero's power style for an NPC copy of
  him; the engine resolves a style's talents when it registers the style, and a loaded save registers the zone's
  package before the party's, so the hero's own talents came too late and his powers bound nothing until the next
  zone. The zone packages now list the hero's talents ahead of his style (SPEC section 28). Reported by the first
  play-through; reproduced and verified with a save in nyc1_1_3, with the old package order as the control.

## v0.1.0 - content version 2

- First public release: `info` / `build` / `verify` / `clean`, the prepare stages from the disc image, the
  compiled sound encoder, the launcher's release manifest.
