"""xml1build.lib - the format, codec and parser modules the build needs that used to live in research/ (BUILDER_DESIGN.md
1.5: "they move into the builder package with the sys.path tricks and hard-coded paths removed; research/ keeps the
history"; SPEC.md 27.13). The pipeline, the prepare stages and the builder import them from here (`from .lib import
zsnd`); nothing here touches sys.path or holds a machine path (developer defaults come from xml1build.sources:
REPO_ROOT, DEFAULT_XML2). Each old file is now a thin shim that hands out this very module, so the research tools
and `python research/sound/<name>.py ...` / `python tools/fix_music.py ...` keep working.

  bescript      the BehavEd script parser (was research/scripts; P3 rewrites the XML1 scripts with it)
  sweeplib      the robust XML1 text-XML parser (was research/sweep; its shim keeps the sweep's X1/X1A/X2 folders)
  x1names       the collision-free XML1 namespace, every x1_ rename (was research/characters); the collision table
                comes from the build's Sources (use_collisions), else research/characters/collisions.json of REPO_ROOT
  zsnd, ztrk    ZSND sound banks and their ZTRK track bytecode (was research/sound)
  zhash         the engine's ELF name hash (was research/sound)
  simlookup     XMen2.exe's sound-name resolution, offline (was research/sound; validate_sound)
  adpcm         Xbox / PC IMA ADPCM codecs: pure-Python references + codec() = the kernel or numpy (was research/sound)
  adpcm_np      the numpy codecs, bit-identical to the references (was research/sound)
  adpcm_c       the optional compiled kernel (ima_kernel.c here, built by tools/build_sound_kernel.py; the frozen
                builder ships the library next to this module)
  convert_zsnd  Xbox -> PC bank conversion (was research/sound; P4)
  merge_zsnd    XML1 banks merged into XML2's of the same name (was research/sound; P4)
  fix_music     XML1's layered / stereo music banks re-laid for XMen2.exe (was tools/fix_music.py; P5)"""
