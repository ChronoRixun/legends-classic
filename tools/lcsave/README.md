# lcsave: the LC save format and the old-save converter (reference implementation)

Append-only resident compatibility uses `Data/lcsave/zone-prefix.lcm`, an optional
builder attestation sidecar. Generate it against legally owned previous release
output with `python -m lcsave.zonecompat PREVIOUS_BUILD CURRENT_BUILD
--ledger-out tools/lcsave/data/zone_prefixes.json` after content conversion. The
release ledger contains hashes and placement indices only; savefiles emits it in
fresh builds and retains earlier sidecar entries. Regenerate against each supported
old build after another map edit; compatibility is never inferred transitively.

An attestation requires the new numbered list to be strictly longer and its old
prefix to match complete entity definitions, placement-group attributes and instance
attributes/children, in ordinal order. Attribute ordering is irrelevant; authored
values, positions and child order are exact. The old whole-map SHA1, current
whole-map SHA1, zone key hash, old placement indices and prefix digest bind the
comparison. Saved numbered identities must also match their original ordinal and
placement before they map to the current placement. Saves alone lack original
definitions, so matching saved names cannot prove compatibility.

The native reader retains old state and fog/heard provenance, starts new residents
fresh, and omits former smart/dynamic state matching the new resident tail. Missing
or stale attestations retain exact-hash rejection; malformed sidecars refuse.
Incomplete captures still reject. Cached unvisited records retain their old hash
and old placement indices until a real current-map capture replaces them. Runtime
metadata uses the current hash/indices and identifies fresh tail factories, avoiding
both a second provenance rejection and accidental tail tombstones. These are
ephemeral API fields; no container field, section version or feature bit changes.

Sidecar framing: `LCZPFX1` plus NUL, little-endian u32 version 1, row count,
total length and CRC32 of the body. Each row contains zone-key SHA256[32], old
map SHA1[20], current map SHA1[20], canonical-prefix SHA256[32], u32 prefix count,
then that many original u32 placement indices. Duplicate hash triples/placement
indices, invalid framing and counts over 4096 refuse. A compatibility sidecar is
trusted builder output, like existing bind metadata; its CRC detects damage and is
not an authenticity signature. Full current-map hashing prevents stale claims
from applying to edited installed maps.

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


## Native layouts, the Phase A marker and the typed entity-id registry (entity capacity, Phase A)

`layout.NativeLayout` describes the engine's save manager layout: `RETAIL` (the retail executable: 768 states,
256 ordinals, 300 dynamic, 768 smart, zone record 0x55e0, manager 0x1afdc, payload 0x2fc00, wrapper 0x2fc78) and
`E10A2` (the entity-capacity build: 4096 states including the sentinel, 1024 ordinals / dynamic / smart, record
0x19b88, five records, manager 0x80c24, payload 0x200000, usable end 0x200000, wrapper 0x200078, no origin
trailer; `transfer_chunk` 200 and `chunk_bounds(i)` for the 47/48 campaign transfer). Every reader and writer of the
native stream takes the layout explicitly (`oldsave.read_slot(buf, native)`, `oldsave.write_slot(m, native)`,
`convert.reverse_slot(..., native=, registry=, report=)`, `convert.old_stream_to_new(..., native=)`,
`convert.native_zone_metadata(..., native=)`, `convert.loaded_zone_metadata(..., native=, registry=)`); the default
is `RETAIL`, and a stream of the other layout's size is refused, never re-interpreted. The one-time importer
(`convert_slot`) reads retail saves only. The C++ `lcsave` mirrors this (`lcsave::retail_layout`, `e10a2_layout`).

The container header's `required_features` bit 0 is `FEATURE_ENTITY_LAYOUT_CONTIGUOUS10`: the file's typed entity
ids are ten-bit tokens. The E10A2 saver writes it, the offline converters and the retail engine keep 0; a rewrite
passes the read header through (`container.write_file(kind, sections, header)` takes `header['required_features']`).
`optional_features` (ignored when unknown): bit 0 `OPTIONAL_KEYS_PRESENT`; bits 1 / 2 `OPTIONAL_LEVEL_SKILL_POINTS` /
`OPTIONAL_LEVEL_STAT_POINTS`, set by XML2 Fix 1.5 when the campaign's heroes carry the fifth-level points of
`[Game] LevelSkillPoints` / `LevelStatPoints=xml1` (a file without them gets the fix's one-time catch-up on load;
SPEC 88.1); bit 3 `OPTIONAL_CLASS_GROWTH`, the heroes' class bonus is the build's current autospend classes'
(SPEC 94: XML2 Fix re-bases a file without it once). The importer never sets them.
`container.feature_decision(required_features, native)` is the reader's rule: an unknown bit is refused ("needs a
newer version"), a feature-1 file on a retail layout is refused ("needs the entity-capacity build"; the marker is
never stripped), a feature-0 file on E10A2 has its registered typed fields migrated, a feature-1 file on E10A2 has
them validated.

`typed_registry` is the registry of script variables that hold World tokens (PHASE-A-PLAN section 4): the round6
scan over a prepared scripts tree (`v = fn(` assignments, getID/getIDString taint, literal `set(Zone|Game)Var`
keys, the float-operator taint check; `scan_scripts`), bound to the tree by a fingerprint (SHA-256 over
`relative-posix-path\0sha256\n` for every `*.py`, in lower-cased-component path order; `scripts_fingerprint`).
`tools/xml1build/typed_entity_ids.py SCRIPTS_ROOT OUT [--expect-fingerprint HEX --expect-keys N]` writes the file
and exits 1 without writing when a key has mixed writers or a token local enters a float operator;
`--check REGISTRY SCRIPTS_ROOT` is the engine's verification. The file (text, LF, ASCII; `load_registry`,
`verify_registry(file, scripts_root) -> (ok, reason)`; the C++ reads exactly the same):

    lcsave-typed-entity-ids 1
    fingerprint <64 hex digits>
    files <count of *.py files hashed>
    key<TAB><Zone|Game><TAB><key>        one per typed field, sorted by (scope, key)

At the LC -> native boundary (`reverse_slot`) and nowhere else, a registered (scope, exact key) value of a
feature-0 file is translated with `layout.migrate_typed_field` (retail `(g << 8) | i` -> `(g << 10) | i`, or null
when the value is not a positive retail token, `g == 0` or `g > 0x3fff`); a feature-1 file's registered values are
only validated (`layout.validate_typed_field`). Every other integer is preserved. The counts (mode, typed_fields,
translated, normalized_to_null, validated) are returned through `report=` and logged as one note.
`tests/unit/export_lcsave_typed_vectors.py DEST` exports the parity vectors xml2-fix's `lcsave_durable_parity`
checks byte for byte.


## Revision 2.4 Core change list

Field widths stay unchanged. Writers record/retain per-zone placement/hash/conversation provenance and capture
status: mask 1 incomplete, mask 2 historical/inferred. Observed removed numbered entities have explicit STATE
tombstones. Cached records retain their own provenance. Changed conversation digests use the historical identity
mapping; unknown nonzero marks drop with a ledger note. Unsupported semantic/native ranges refuse before narrowing. Non-converter
translation never borrows the importer's drop policy.

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
their world-item slot is absent, matching the native loader's absent-instance case. Live numbered identity loss and
other unhandled drops still refuse. Valid world items and carried/key-item counts are preserved. Legacy imports
keep the historical recorded-drop/LGCY policy; field widths and section versions are unchanged.

Native-transfer follow-up: `native_zone_metadata` validates current-table names/ordinals, marks inferred flag2
provenance with zero conversation digest, and retains object/fog data without relabeling it as observed. Its helper
path bypasses conversation hashing; ordinary save/import/bind generation still hashes by default. No wire layout,
section version or content identity changes.

Dead numbered missing-item follow-up: native factory 0x465c35 checks `flags_b & 8` before restoring an item.
With that bit clear, native recording keeps the removed placement/name identity as a tombstone and clears its
unreachable item flag/payload, with an explicit ledger note. It preserves position and other `flags_b` bits.
Alive numbered dangling references still refuse. Historical imports and the revision 2.4 wire layout are unchanged.

Legacy Forge contact recovery (maintainer import policy): only pre-LC campaign imports receive the one-based
`x1v03` bit 31 (`0x40000000`) when a catalogue-known current zone, used side-mission return frame, or retained
zone record proves the campaign reached HAARP or a later main-campaign directory. Later mansion hubs count;
NYC's opening mission, the first mansion, training/flashbacks and unknown zones alone do not. The source
first-mansion briefing starts HAARP; subsequent missions preserve the contact flag. Zone names are stored
literally in every supported legacy era, so the gate does not depend on era-specific objective numbering.
An already-set flag is unchanged. A missing word is appended if the native 100-variable store has room;
otherwise import refuses rather than losing an unrelated variable. Only the flag changes, and the import's
LGCY/external ledger records once: "Forge contact unlock granted (0.1.x builds did not record it)".
Native saving, new games and LC resaves never run this repair. Previously imported LC files are not repaired
retroactively. The Python verifier lists this deliberate change in `legacy_repairs` while checking all other
semantics. No wire layout, section version, catalogue or content-version change is needed.

## Conversation heard marks across builder eras

The engine ranks loaded conversation files by case-insensitive name, then indexes four consumption lanes per
file (0x45cb5a, 0x45c56e, 0x45c679). A lane counts consumed run-once starts, not line ids or startCondition
ordinals. Historical tables contain hashes of file name plus decimal lane; identical eras share a reference.

New native `ZREC.conversation_digest` is package-aware: SHA-256 of `LCCONV2` plus NUL, the canonical zone key
hash[32], little-endian u32 lane count, and every ordered file/lane identity hash[32]. Dialogue edits do not
renumber these identities. Only an exact current package-ranking digest permits positional reuse. Bare global
conversation-tree digests are legacy provenance keys, never evidence that current ranks match. The pinned
release snapshot for the previously shipped global digest also protects earlier native LC resaves.

Metadata regeneration reads and validates the previous `conversation.lcm`, retaining every recorded
layout before appending historical and current layouts. Recorded keys are immutable: a conflicting mapping
or damaged prior sidecar stops regeneration without overwriting history. Releases must carry this sidecar
forward with their metadata; deleting it loses snapshots absent from the historical model.

`conversation.lcm` emits both historical global keys and qualified package keys, plus the writing build's
current package snapshots. A different package ranking maps surviving identities into their current positions;
removed or unassigned identities get individual ledger notes. Unknown/zero provenance drops heard words with
a note and continues loading. This keeps successful native/online-transfer saves loadable even when their
capture metadata has no authenticated conversation provenance. Other state remains intact. Unknown marks
are not asserted to be retained by this fallback.

Loaded metadata rebases to the reconstructed package digest and retains inferred capture status. Cached-zone
resaves therefore do not remap translated words a second time. Capture hooks and fresh native recording also
write package-aware provenance. Legacy import bytes, LC field widths/layout, and catalogue identities are unchanged.

Sidecar framing remains `LCCONV1` plus NUL, u32 version=1, u32 table count, u32 file length, and u32 body CRC-32.
Each table has provenance[32], zone-key-hash[32], u32 bit count, then identity hashes[32]. Counts are multiples of
four, at most 128. Duplicate keys/identities, bad framing/version/CRC refuse malformed table files. V39 checks
the generated set. Rebuild savefiles after the era ledger changes; game asset preparation caches remain valid.
