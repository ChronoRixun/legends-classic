# Changelog

The builder's releases, newest first. The version is `xml1-builder --version`; the content version is what a
build carries (`_build\stamp.json`) - when it rises, the launcher offers a rebuild.

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

New build checks: V33 (every object carries the first game's strength next to the
engine's), V34 (no soldier placed on the floor gets the ladder slide) and V35 (the pause menu has no portal).

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
