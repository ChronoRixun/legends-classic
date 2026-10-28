# Scoped online typography

The online fixture menus use four private Barlow Condensed bitmap fonts, selected
through the companion XML2 Fix `[Game] LegendsClassicFonts=1` capability. Other
menus and classic font resources retain their previous bytes. Removing the key,
using an older DLL, or refusing a runtime guard leaves readable classic text.

The builder is offline. It reads the official Google Fonts OFL TTFs in
`tools/xml1build/fonts/barlowcondensed`, verifies `manifest.json` SHA256 hashes,
and rasterizes native metrics and atlas pixels with Pillow. It reuses the owned
PC atlas container topology, replacing every pixel, name and mip level. The
output includes `licenses/BarlowCondensed-OFL.txt` and its provenance record.
The four metric/atlas pairs are `UI/fonts/lc_online_{title,row,body,label}.XMLB`
and `Textures/fonts/lc_online_{title,row,body,label}.IGB`. Separate
`UI/fonts/lc_fonts_{pc,hd}.XMLB` maps append the private indices to copies of the
existing mappings. Original map files are not changed by this feature.

The four primary sizes on the 640x480 design grid are title 37 (800 italic), row
15 (700), body 12.5 (500), and label 11 (700). Native style scale accounts for
the 512x384 engine canvas. The screen-name inset retains the existing reference
preview's compact 22-unit title through a style sharing the title slot. Code
cells use another alias of the upright row slot at title size.
The family therefore uses six of 32 native style records, leaving two free
after the existing 24; 71 of 75 palette entries are occupied. Titles are sampled
from a 96-pixel face and other roles from 64-pixel faces for sharper output.

Round colored face buttons and outlined keyboard keycaps are private glyphs.
Text items draw glyphs in back-buffer pixels (the classic fonts are the same
pixel size at 720p and 1080p) and are never stretched at 16:9. The face
button cells keep their 3:4 width (they were sized for a stretch that does not
happen; a square cell overflows the label atlas - open item). The style `textscale` is authored in 512 x 384 view
units; XML2 Fix (`lc-fonts-screen/1`) multiplies it by the screen height / 384
at draw time, so the family keeps its design size at every resolution (live
060p: without that factor 15-unit rows were 8.6 px tall at 720p and 1080p). The DLL's existing actual-binding/device selection chooses
glyphs during private text rendering; stored `$MENU_*` tokens remain unchanged.
The view itself is the engine's: 384 units tall and aspect x 384 wide, centred
on the 512-wide composition, so 16:9 shows the composition at its true shape
with the backdrop field filling the sides.

Frontend validation checks private maps, all 256 ordered metric records, paired
resources, style scales, and the shipped OFL license. The generated metric table
is compiled XMLB, not a raw memory dump: the loader fills the 24-byte prefix
relative to the manager plus 256 28-byte records (`<hhhhi4f>`), with the texture
handle at the next stride boundary. Offline previews must sample these emitted
metrics and atlas pixels and include the real style scale; a TTF-only reference
does not validate native output. Real D3D sampling/input remains a live gate.
