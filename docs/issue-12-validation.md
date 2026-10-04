# Issue #12 validation

Fresh-process before/after comparison in haarp/ext/haarp_ext01 used the same vulnerable
Wolverine, DLL, settings and native fire_wall01. The wall waypoint was moved to the
unobstructed landing area so trees could not conceal the result. No invulnerability
or damage command was used. The original act/move block was compared with the same
block wrapped in hide/show and the corrected loop-start setting.

- Before: the hazard was invisible while damaging the hero.
- After: the flame was visible at the contact location, with floating damage values.
- Both matching contact/exit sequences ended at 57 HP from 90; this is not a precise
  damage-rate benchmark. The final code preserves the non-smart damage path.
- The smartfire candidate was rejected after its reduced damage was measured.

Evidence is kept locally under the isolated clone's ignored build/proof-12-evidence:
before-v2-contact.png and before-v2-damage.json; after-v3-contact.png and after-v3-damage.json.
Game-derived screenshots are not committed or attached to the public PR.

Scope: controlled hazard activation/placement. A natural flamer encounter, extinguish
interaction and save/reload are not claimed by this check.
