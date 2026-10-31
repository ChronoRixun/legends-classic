# Known issues and limitations

Open bugs and play-test notes: [issues](https://github.com/ChronoRixun/legends-classic/issues) and
`research/campaign/late_game_test.md`. Each release's own known issues are in the [CHANGELOG](../CHANGELOG.md).
Report with a screenshot where it helps.

## Additions, not fidelity

Legends Classic aims to play like the first game, and the rest of this page says where it does not. The items below
are the opposite case: things the first game never had. They are modernisation, they are not part of what is being
matched to the original, and none of them counts as a fidelity claim.

- **Online co-op** for up to four players (see [the online guide](ONLINE.md)): codes, public games, drop-in at the
  next level change, Connect by IP and LAN search. The first game was local-only. Joiners must run matching builds.
- **Solo-segment watchers**: players without a hero watch a solo story segment and regain control afterwards. This
  exists because of online play.
- **A 60 frames-per-second online rate** (`[Online] TickRate`) and the larger engine limits the port needs (model
  pools, object capacity). They change how much the engine can hold, not what the first game's rules do.
- **Display options**: borderless, windowed or exclusive fullscreen at your desktop's resolution and refresh rate, with
  anti-aliasing.
- **Saves of their own** (`Documents\Activision\X-Men Legends`, the port's save format), so the first game never
  touches X-Men Legends II's saves.

## Not yet recreated

Some of the first game's features rely on engine code X-Men Legends II doesn't have. Until they are recreated (most
need new engine hooks in xml2-fix), the port plays without them:

- **The first game's loot and shops** ([#6](https://github.com/ChronoRixun/legends-classic/issues/6)). In the stable
  0.4.0, random drops are X-Men Legends II's, not the first game's equipment, and the shops (the Healer's, and the one
  at Xtraction points once you have met Forge) are X-Men Legends II's: generated stock, its prices and its training
  services. The 0.5 beta brings the first game's items, drop tables, Forge, Healer prices, Grab Bag, selling and
  Danger Room rewards; where a bonus has no exact PC form it is converted as closely as the PC game allows (the build's
  `Docs\APPROXIMATIONS.md` lists every one). #6 stays open until players have checked it.
- **15 of the first game's fall kill zones** ([#22](https://github.com/ChronoRixun/legends-classic/issues/22)): 20
  placements in 14 maps (three of the zones in demo maps outside the campaign) stay off: several sit in water or in
  rooms followers can stray into, and need their own checks. The East Rooftops and a sewer walkway have theirs back
  since 0.2.2, and two more since 0.2.3.

Recreated in 0.2.2: the scan turrets ([#4](https://github.com/ChronoRixun/legends-classic/issues/4)), breakable
enemy parts ([#3](https://github.com/ChronoRixun/legends-classic/issues/3)), solo mode
([#5](https://github.com/ChronoRixun/legends-classic/issues/5)), the Xtraction services and the Danger Room's story
lock ([#63](https://github.com/ChronoRixun/legends-classic/issues/63)) and the two-point ranks
([#35](https://github.com/ChronoRixun/legends-classic/issues/35)).

## Gameplay

- **Settings are shared** with X-Men Legends II: key bindings and display settings read the same Windows registry
  key. Saves are separate.
- **Enemy attack rate** ([#101](https://github.com/ChronoRixun/legends-classic/issues/101)): unarmed enemies (the
  Brotherhood in the HAARP tunnels) still attack about 1.5 times as often per minute as in the first game (measured:
  about 19 against 28 attacks per enemy per minute with a moving hero, 20 against 32 with a still one); the cause is
  not found. Whether heroes are now stunned as long as in the first game has not been measured again since 0.2.5
  re-stuns them on every stun hit.
- **Gun soldiers** (#101, #54): since 0.4.0-beta.6 the HAARP officer has the first game's weapon brain: single aimed
  shots about every 0.9 s, no bursts or punches from range, he backs off, and he holds his grenade at full energy.
  Since 0.4.0-beta.7 all 20 gun NPCs have it (MP5 and laser soldiers, nullifier / knockback officers with their
  charge-up, lightning and flamethrower commanders, police pistols), and bullets hit only on the weapon's XML1 trace
  timer (the MP5's half second). Measured against the original on one PC: the MP5 soldier's shot rate matches and its
  hits never outnumber the trace timer, but at mid range it still does about 1.6-2.2 times the original's damage (the
  original misses the first trace or two after each pause; planned for a later release); the engaged officer's shots
  and damage are within 10 %. The warm-up, continuous-beam (lightning commander), flame, pistol and line-of-sight paths
  still need their live comparison with the original. Before beta 6 the port officer, in a matched 45 s window, fired
  none of the original's 49 shots and punched 24 times, and when he did shoot he fired bursts of seven whose sound
  stacked (the louder gun).
- **Hazards** ([#104](https://github.com/ChronoRixun/legends-classic/issues/104)): the earlier 57-level audit had live
  checks in only three rooms; report remaining misses.
- **A keycard behind a door in HAARP:** since 0.2.2 the HAARP officers are no longer launched onto the key door, the
  way their keycards ended up behind it. The first game can itself push an officer through that door when the two
  overlap; if a keycard is ever out of reach, load your last save.
- **Button prompts** after rebinding or with Steam Input (XML2 Fix #8).
- **Cosmetic reports** (#54): the HAARP officer's gun being louder than on the Xbox, and others.

## In the 0.5 and 0.6 betas

- **Phoenix's telekinesis** lifts the enemy she faces; when she faces away or stands in a crowd the game can pick a
  crate next to him, or nobody.
- **The flying carry** ends when the carried one bumps a prop or a wall, or when the carrier lands (fly higher over
  crates). At the pickup the carried hero can be invisible for a moment (visual only; 0.6 attaches him from the first
  frame, still to be checked on a real controller).
- **Throws**: a thrown enemy is hurt only by what he hits, not by landing on the floor; whether throw damage against
  resistant soldiers is enough is still being judged.
- **The first game's Guard** (picking up a stunned enemy, Beast's rank 3 wall lunge) is optional and off by default
  (`--guard-decide xml1` to try it) until it passes real-controller checks; Guard is beta 8's Block / Grab.
- **The first Grab Bag course** can be "Challenge - Rogue" rather than the first game's first one (being checked
  against the original).
- **The 96-live-actor limit** (`[Limits] Actors=96`, with `[Limits] ActorPools=124`) is off by default; a save written
  with it on needs it on to load ([SAVES.md](SAVES.md)).
- **Blob** fights with the first game's brain since beta 8, but in rare runs he can still stand still.

## The classic look (new in 0.4.0)

It was checked on one PC at 4:3 and 16:9 with keyboard and a virtual pad, not yet on physical controllers or many
screens. Once, at 4:3, the first frame of Gear clipped the bottom help labels; it did not happen again in any later
try. If a screen's text or labels are cut off, or something looks off, please report it with a screenshot.

## Online

<!-- release round: update -->
- **Certified on two PCs on a LAN** (the 0.6.0-beta.1 co-op round). Internet play through the relay is not verified
  yet, and four-player games are not certified yet. Earlier releases were tested on one PC with two instances of the
  game, plus local three-player drop tests (0.4.0).
- **Host loss ends the session** until co-op recovery (0.8): no host migration or automatic reconnection yet. A guest
  can join again by code.
- **Drop-in joins at the host's next area**, not mid-level: everyone reloads that area together, so the load takes a
  little longer.
- A failed shared-campaign restore can require rehosting.
- LAG warnings may remain, but the slow-player drop is disabled.
- Solo story segments online are watched now, but #106 stays open until played through in more sessions.
- Public games connect directly, so players can see each other's internet address. The broker caps each internet
  address at two public rooms and two seats in other people's rooms.
- Local co-op on controllers should work (it is X-Men Legends II's) but has had little testing.

Full online guide: [ONLINE.md](ONLINE.md).
