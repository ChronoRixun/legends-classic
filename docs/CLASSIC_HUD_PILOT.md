# Classic HUD conversion

Every normal port build generates and registers the classic HUD assets in its
frontend stage, including builds using `--frontend xml2`. The builder writes
`[Game] ClassicHud=xml1` and rejects an installed DLL that only knows the retired
`ClassicHudPilot` key. This requires XML2 Fix 1.8.0-beta.5 or later (first shipped
in Legends Classic 0.4.0-beta.5); earlier fixes do not implement it.

Set `ClassicHud=off` (or `0`, or remove the key) after building to retain today's
native HUD byte-for-byte: the adapter makes no writes and native HUD resources
are not replaced. Rebuilding restores the builder-owned setting. The old pilot
key is removed during INI merge and is no longer read by the DLL.

The converter reads the player's Xbox scene and separate Xbox atlas plus the
owned PC atlas. All outputs use the normal build registry, output hashing and
sweep lifecycle. Validator `V-TBD-hud` regenerates their expected bytes from the
owned inputs and rejects missing, stale or corrupt outputs. No palette/style or
font slots are allocated. Numbers, controls and gameplay stay with the port.

For private developer experiments the same converter remains available from
`tools/` as `python -B -m xml1build.classic_hud --disc <extracted-disc-root>
--base <owned-PC-install> --out <private-port>`. This standalone command does not
update the normal build manifest; use a complete build for acceptance.

The conversion emits `Textures/ui/lch.IGB`, `UI/hud/lc_healthpanel.IGB`,
`UI/hud/lc_healthpanel_pc.IGB`, `UI/hud/lc_partycross.IGB`,
`UI/hud/lc_partycross_pc.IGB`, and `lc-hud.txt`. Both platform aliases have the
same intended geometry. The party-selector resource uses a bounded centred quad
with the original silver/blue emblem, explicit round coverage and corrected row
orientation. The pilot's whole HUD scene in this role left an opaque central disc.
The primary portrait sprite still uses the original ring from the private atlas.
Existing namespaced character head art remains the ordinary builder's output.

The 256x512 sprite atlas keeps the complete decoded PC atlas in its own region.
Original artwork and explicitly rotated health/energy strips occupy separate
regions. All three native HUD sprite batches need the new UV scale, including
the potion and additive-effect batches. Other sprite objects retain their native
UVs. This consumes no menu palette, style or font slots.

HUD format 15 uses explicit DXT3 alpha; the hero-icon DXT5 decoder's alpha is not
appropriate here. Mesh vertex-array slot 2 is a table of 20 stream references,
not interleaved vertex bytes. Positions and UVs are separate streams 0 and 11.
The converter checks their lengths, finite values and index bounds before
producing its new panel quad. The original executable's bar surround is a thin
procedural bevel, rather than the atlas's small-map corner graphic.

Panel depth is part of the geometry contract. The PC parent adds 10 to local Y;
its controller-colour rectangles sit at parent depth minus 5. The imported face
uses local Y=-6 (world depth 4), in front of those rectangles, while preserving
the native colour tags and both mirrored layouts. Merely copying the original
PC face's depth leaves the colour rectangles covering the new black face.

Synthetic regression checks run with:

```text
python -B tests/unit/run.py -k classic_hud
```

The release integrator must advance content identity and the companion version
before release. The private gate report records runtime evidence and remaining
acceptance gaps. Do not infer complete party-wheel, 1-4-player, power-wheel,
font or aspect-ratio parity from one successful primary HUD frame.


The small map is XMen2.exe's own and is drawn without a frame, as in the original
game's reference captures. Beta 5 composited a transparent-interior 128x128 bevel for it
at atlas rows 384..511; that region is now left transparent, and the companion
(the next XML2 Fix beta) neither draws it nor moves the map's safe-area inset. The atlas
size and sprite numbering are unchanged. The final private asset contract is LC-HUD-4; older markers are refused.


The XP meter uses the original silver atlas strip: XBE draw0x15b85d selects
sprite8, whose UV getter0x187d90 addresses x27..30/y0..64. Conversion rotates
the interior silver texels into a dedicated strip, avoiding the adjacent energy
colour. The companion keeps the native XP fraction and level digits, aligns
the fill with health/energy and uses the original three-pixel height. No XP
thresholds, level rules, font slots or text are changed.

The matching companion now fits long primary target titles using the native
font measurements, with ellipsis and the numeric level suffix retained. Its
transaction has nine destinations (eight pointers plus the target-title call).
The builder's assets and `LC-HUD-4` contract are unchanged. Short titles,
resistance subtitles, target selection and combat values retain native behavior.
