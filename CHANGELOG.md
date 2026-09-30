# Changelog

The builder's releases, newest first. The version is `xml1-builder --version`; the content version is what a
build carries (`_build\stamp.json`) - when it rises, the launcher offers a rebuild.

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
