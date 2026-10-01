# Changelog

The builder's releases, newest first. The version is `xml1-builder --version`; the content version is what a
build carries (`_build\stamp.json`) - when it rises, the launcher offers a rebuild.

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
