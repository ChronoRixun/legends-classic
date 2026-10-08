# lcsave: the LC save format and the old-save converter (reference implementation)

What it is: the builder's reference implementation of the new save container ("LC save", format 1) and of the
one-time converter from XMen2.exe's own save format, plus the era model that tells which builder release numbered
an old save's positional data. XML2 Fix carries the C++ translation; this package is the oracle it is checked
against (decision D1 of the save-format pass).

Nothing in this package or its data carries game content: `data/catalogue.json` and `data/legacy_eras.json` hold
SHA-256 hashes of canonical keys and position numbers only. Names come from the player's own build at run time.

    python -m lcsave convert  OLD.save OUT.lcsave --build BUILD_DIR [--slot N] [--report out.json]
    python -m lcsave dump     FILE [--build BUILD_DIR] [--out dump.json]      # old or new save -> canonical JSON
    python -m lcsave verify   OLD.save --build BUILD_DIR [--out DIR]           # convert, dump both, reverse, compare
    python -m lcsave corpus   FOLDER --build BUILD_DIR --out DIR               # every saveslot*.save under FOLDER
    python -m lcsave eras     --reference BUILD --era CV=BUILD ...             # developer: regenerate the era model
    python -m lcsave catalogue --build BUILD [--eras data/legacy_eras.json]   # developer: regenerate the catalogue

Modules: `keys` (domains, canonical key hash, id grammar, CRC-32), `layout` (table-driven byte layouts of the old
save and the new container), `oldsave` (bounds-checked reader / writer), `binds` (the engine's numbering of a
build's data, the placed-entity ordinal rule), `catalogue`, `legacy` (era model and detection), `container`
(sections, records, validation), `convert` (old -> new, the reverse reader, the verification commands), `dump`.

Tests: `python tests/unit/run.py -k test_lcsave` (invented build and saves). Specification: the save-format pass
documents (SPEC-new-save revision 2.3, SPEC-old-save revision 2.1) in the coordinator's notes; the port design for
XML2 Fix is CONVERTER-PORT.md beside them.


## Revision 2.4 Core change list

Field widths stay unchanged. Writers record/retain per-zone placement/hash/conversation provenance and capture
status: mask 1 incomplete, mask 2 historical/inferred. Observed removed numbered entities have explicit STATE
tombstones. Cached records retain their own provenance. Zero/different conversation digests reset conversation
bits, and unsupported semantic/native ranges refuse before narrowing. Non-converter translation never borrows the
importer's drop policy.

Campaign/profile resaves retain LGCY and unknown KEEP payloads with the original KEYS index prefix. Profile imports
now emit LGCY. Python writes canonical KEYS text, matching the native codec. Full parking remains deferred while
unresolved identities refuse intact; it must precede content retirement. Opaque extensions use stable IDs/pinned
KEYS or self-contained data, not undocumented mutable-list references.

Synthetic byte-parity acceptance covers two campaign KEEP resaves, per-capture metadata/tombstones, identical-name
twins with a skipped factory, profile import and two profile resaves. W11 and actual engine acceptance remain
separate release gates. Native demand estimates include restore equipment conservatively.

Revision 2.4 review follow-up: reverse translation removes only world-item handles exclusively owned by discarded
zone records; shared and unowned handles remain. Native preflight rejects duplicate numbered placement destinations.
Unsupported capture bits refuse even when the placement hash differs. Conversation/zone reset explanations remain
in the reverse reader's notes for callers to surface. No wire layout or section version changes.

Native save follow-up: dangling unnumbered dynamic/smart item states are omitted with an explicit result note when
their world-item slot is absent, matching the native loader's absent-instance case. Numbered identity loss and
other unhandled drops still refuse. Valid world items and carried/key-item counts are preserved. Legacy imports
keep the historical recorded-drop/LGCY policy; field widths and section versions are unchanged.

Native-transfer follow-up: `native_zone_metadata` validates current-table names/ordinals, marks inferred flag2
provenance with zero conversation digest, and retains object/fog data without relabeling it as observed. Its helper
path bypasses conversation hashing; ordinary save/import/bind generation still hashes by default. No wire layout,
section version or content identity changes.
