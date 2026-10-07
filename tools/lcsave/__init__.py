"""lcsave - the Legends Classic save format ("LC save", format 1) and the one-time converter from XMen2.exe's
own save format (the reference implementation; XML2 Fix carries the C++ translation, CONVERTER-PORT.md).

Modules (all standard library; no game data in this package - names come from the player's build at run time):

  keys       domains, canonical key bytes, the SHA-256 key hash, the 32-bit id grammar, CRC-32
  layout     table-driven byte layouts: the old save (every fixed record as a field table) and the new container
  oldsave    bounds-checked reader of an old slot file / profile -> model; writer model -> bytes (reverse check)
  binds      the engine's numbering of a build's data (position -> key per domain; placed-entity ordinals)
  catalogue  the master catalogue (data/catalogue.json: serial per key hash), the tag ledger, id lookups
  legacy     the era model (data/legacy_eras.json): what each builder release numbered how, era detection
  container  the new format: sections, records, validation, reader and writer
  convert    old model + era + catalogue -> new model; the reverse reader new -> old stream; LGCY record
  dump       canonical JSON of either format for semantic comparison
  __main__   command line: convert, dump, verify, eras (developer), catalogue (developer)

Specification: agent-work/save-step1/SPEC-new-save.md revision 2.2 (the converter's change list is in its
section 15); the old format: agent-work/save-step0/SPEC-old-save.md revision 2.
"""
FORMAT_MAJOR = 1
FORMAT_MINOR = 0
CONVERTER_VERSION = (0, 1, 0)        # writer version bytes: major, minor, patch (kind byte = 1, Python converter)
