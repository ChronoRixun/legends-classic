# Changelog

The builder's releases, newest first. The version is `xml1-builder --version`; the content version is what a
build carries (`_build\stamp.json`) - when it rises, the launcher offers a rebuild.

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
