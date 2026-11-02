# Original Xbox campaign import preview core

This is an offline developer core with synthetic acceptance tests. It is **not
enabled for player installation**. No real Xbox campaign was available for this
round. No stock talent-byte ledger, source mission-byte ledger or tested retail
checkpoint recipe is invented to fill that gap. A separate decoder supports
the surveyed XML1-recomp sections; unsupported versions retain explicit refusals.

The owner-approved behavior is checkpoint continuation with an explicit list
of changes, W2 saves plus the XML1 economy and XP curve, an unchanged source,
and an unchanged global profile unless the player selects **Also merge unlocks**.

## Command

From `tools/`, or through the packaged `xml1-builder` entry point:

```text
python -m xml1builder import-xml1-save <extracted Xbox folder or HDD image>
    --build <installed LC build> --save-dir <actual SaveLC folder>
    --slot 0..9 [--merge-unlocks] [--dry-run] [--events jsonl]
    [--allow-inferred] [--import-table <local table>]
    [--campaign <exact E:/UDATA/4156001e/campaign path from discovery>]
    [--source-kind auto|xemu|recomp]
```

`--dry-run` performs bounded parsing, mapping, encoding and the existing Python
LC/W2 native-loader check without writing files. A preview needing inferred
interpretations refuses with `E_XML1_INFERRED` until `--allow-inferred` is
selected. Its error detail contains the proposed changes. Unknown purchased
talents, active upgrade transactions, unsupported identities, overflowing
counters/ranks or ambiguous checkpoint contexts still refuse.

Apply additionally needs `--preview-token <token from dry-run>`. The token binds
the source bytes, build/table hashes, existing profile bytes, slot, checkpoint
and both opt-ins. A mismatched token refuses with `E_XML1_CHANGED`. Round 1
then refuses with `E_XML1_UNVALIDATED`: the code-level admission gate cannot be
overridden by editing a local table. Enabling player writes needs real-save
checkpoint evidence, shipping C++ loader/economy parity, live acceptance of the
cooperating game save lease and a recoverable campaign/profile transaction.

There is no network input, upload, signature repair or original-save write.
Inputs may be extracted local folders or standalone raw/QCOW2 Xbox HDD images.
Archives, save states, URLs, links and reparse points are refused. Multiple `save.dat` files produce a
picker refusal, never a latest-file guess. Xbox signature verification is
reported as unavailable unless an independent verifier is supplied to the
reader API. A source SHA-256 records bytes; it does not authenticate them.

## Launcher events and button flow

This extends the existing builder JSONL schema. Each event retains `ev` and
`t`, and existing readers can show the English fallback messages:

| Event | Import fields / meaning |
| --- | --- |
| `hello` | Existing builder identity; always first. |
| `log`, `stage="import"` | Plain-language source discovery and decode summary. `detail` includes source SHA-256, signature status, decoder and bounded counts. |
| `warning`, `code="W_XML1_SIGNATURE"` | “Xbox signature not checked.” |
| `warning`, `code="W_XML1_APPROXIMATED"` | One exact change: `detail.code`, `field`, `source`, `target`, `reason`, `confidence`. |
| `error` | Stable `E_XML1_*` code, complete English `msg`, diagnostic `detail`, then a failed result. Parser offsets belong in details, not the primary dialog. |
| `result`, `ok=true`, `exit=0` | Successful preview only: `dry_run=true`, `imported=false`, `import_report`. Never display “Import complete” for this. |
| `result`, `ok=false`, `exit=2` | Input, unsupported-layout, inference, context or acceptance refusal. |

Cancellation keeps the existing builder exit 5. Internal bugs remain distinct
from input refusals. Stdout is JSONL in JSONL mode; human diagnostics use stderr.

The report contains `schema`, source/profile/decoder identifiers, signature
status and message, target and table hashes, slot and checkpoint, `imported`,
`approximated`, `skipped`, `output_sha256`, output size, campaign serial,
`player_use_validated=false`, validation limits and `preview_token`.
`imported` within the report lists proposed preserved facts; the enclosing
result's `imported` boolean states whether installation happened.

1. **Import an X-Men Legends save** opens the local extracted-folder selector.
2. If `E_XML1_MULTIPLE` is returned, show `detail.candidates` and let the player
   select a campaign folder, then analyze again.
3. Select the installed build and an empty target slot. **Also merge unlocks**
   defaults off. Run a dry preview. Existing slots and pending/backups refuse.
4. If inference is needed, display every listed change and offer an explicit
   experimental opt-in, then rerun with `--allow-inferred`. No implicit consent.
5. Display **Continue from &lt;checkpoint&gt;**, the preserved facts, and every
   reset/approximation/skip. State that enemies/props, fog, heard lines and world
   drops reset. Show signature status. An unvalidated checkpoint keeps **Import**
   disabled in this round; **Cancel** closes the preview with no writes.
6. In a future admitted release, **Import** applies the same options and preview
   token under the cooperating save lock, rechecks source/build/profile hashes
   and installs only into the selected empty slot. Changed inputs return to
   preview. A final successful apply result, not progress or a preview, enables
   **View imported slot**.

The launcher and companion DLL are separate repositories. This change defines
their contract and implements the builder side; it does not modify their UI.

## Import table and identities

`Data/lcsave/xml1-import.json` is a proposed local JSON sidecar, schema 1.
`--import-table` selects an explicit test table. No real table is shipped.
`xml1build.save_import.tables.bind_table()` is a read-only constructor: it pins
the final build's Data/Scripts files, active INI and recorded build settings.
It returns data for integration to write through the builder's owned writers;
it does not run a full build or change the build pipeline/content identity.

The table has these fields:

| Field | Required meaning |
| --- | --- |
| `source` | Profile `id`, `title_id`, original `xbe_sha256`, exactly 16 unique `hero_names`; any proven normalization assertions. It identifies a decoder profile, not source signature authenticity. |
| `target_files` | Exact relative-path -> SHA-256 map for the read build data/scripts, INI and report. No paths outside the build. |
| `heroes` | Source name -> target name, physical-skin-byte -> named costume attribute, validated default power slots; optionally sample-proven source/target authored traits and cumulative growth per level. |
| `talents` | Source hero name -> native source byte ID -> `[target owner, target talent name]`. Unknown purchased/active talents refuse. A shared source passive can map to distinct per-hero target aliases. |
| `xp_thresholds` | Absolute XML1 XP threshold at each level, starting at level 1; source saved level and XP must agree. |
| `items` | Source definition index, target name, route (`equipment`, `health`, `energy`, `key`, `effect`), source maximum and target pack maximum where relevant. No direct target numeric IDs. |
| `quantity_policy` | Explicit `includes_equipped` or `excludes_equipped`. Its inference and per-definition carried/equipped totals appear in the preview. Snapshot quantities are never added as stash. |
| `variables` | Source family/name/mission scope -> final narrowed target name, kind, first bit, width, signedness. Entity/timer values use `transient` reset rows. |
| `checkpoints` | Source mission ID and zone, required named variable predicates, party constraints, target act/zone/name, four spawn poses, anchor pose, source objective-slot -> named target objective mapping, required-objective constraints and proven travel anchors. Exactly one must match. |
| `target_defaults` | Complete validated HREC defaults for any target-only heroes; those heroes remain locked. |
| `profile_unlock_bits` | Optional confirmed source profile offset/mask -> named character/review identity or target completion flag. No codex-position guess. |
| `release_ready`, `acceptance` | Reserved admission metadata. Neither can bypass the round-1 code-level gate. |

The reader verifies installed catalogue/bind identities, bind data SHA-1,
economy-sidecar framing/digest and active W2/economy/XP/point-award settings.
It resolves names through the installed catalogue, not source positions or the
repository's current master serial order. Equipment uses the current definition
own-record lists and the existing LC loader's rebuilt-own policy.

Source-only raw spans stay in the private in-memory IR. The report lists
unresolved subsystem resets, not a fake translation of Xbox CGame, profile,
resident entity or inventory rollback bytes into similarly sized PC records.

## Wire and loader evidence

The reader implements the documented retail layout: Xbox envelope length at
file `0x00`, 20 signature bytes at `0x04`, payload at `0x18`; payload capacity
`0x2fc00`; course marker at `0x458`, course bytes `0x48c`, grade marker `0x554`,
grade bytes `0x588`, credit marker `0x590`, credits `0x5c4`, characters `0x5c6`.
Markers are consumed at the cursor, including newline boundaries; bytes after
their NUL need not be zero. Variable character records contain 44 scalar bytes,
one talent-count byte, four bytes per talent, one equipped-count byte, and byte
item IDs. Seventeen restore records follow the unlock bank.

The objective getter at original XBE `0x84927` sign-extends the word, shifts
only AX left four, then arithmetically shifts EAX right four. Its result is
`(word & 0xfff) - (0x1000 if word & 0x8000 else 0)`. Treating bit 11 as a generic
12-bit sign bit would decode values differently. Source complete maps to LC
objective flags bit 0; source hidden/disabled maps to LC hidden bit 1, with the
visibility approximation reported. Persistent script values are big-endian.

Synthetic tests encode LC sections directly with `lcsave.container.write_file`,
decode them with the real reader, validate domains and native budgets, reverse
through `convert.reverse_slot(..., native=W2)`, serialize/read the native stream,
then save LC again and require identical second-cycle native bytes. They also
check copy conservation and source/unrelated-profile/slot preservation. This is
the builder's real Python loader, not execution of the C++ game loader.

## Real-save sample plan and admission checklist

Keep originals private and byte-identical. For every sample record the disc/XBE
hash, region/language, source game/recomp version and config, exact checkpoint,
party, displayed levels/XP/points, equipment/quantities, currency and any cheats.
Export the whole title folder including metadata and optional settings; hash
every file before and after import.

| Sample | Capture and comparisons |
| --- | --- |
| A, early | First practical NYC Xtraction/first mansion boundary. Verify actual envelope/payload length and tail, markers, sixteen hero order, seventeen snapshots, mission byte/name, initial party/unlocks, XP units, traits and skin. |
| B, early-mid | HAARP exit/mansion. Paired saves around levels 4/5 and 9/10, one rank allocation, stat allocation, equip/unequip, purchase/sale and sold last copy. Prove native talent byte registration, point awards/ack level, bonuses/baseline/limit, carried versus equipped conservation, unique flag meaning and no repeated reward. |
| C, mid | Mansion after ship/Muir/sewer plus a completed side mission. Separate active flashback save must refuse. Verify shared-zone mission disambiguation, scoped flags, final narrowed counters, forced party/skinset, return route and travel unlocks. |
| D, late | Late Astral/Asteroid M/Master Mold stable checkpoints before/after saving. Verify late mission/act IDs, high XP/traits/ranks, forced Professor forms, unique equipment, cosmetics/codex/comics and every required door/conversation/boss/reward gate. |
| R, optional recomp | One exact build/version at A-D. Determine envelope/signature behavior, XML1CHR version/bitmap/lengths/value widths/named IDs and PRG/DIF/STSH presence. Add a separate decoder only after its sample identifies the needed family. |

Within A-D, make pairs changing only one costume, one Danger Room course with
and without extra credit, one trivia answer, and one acquired/viewed review or
codex entry. Include an original-game load/resave pair to distinguish padding
from live state. Bind discovered byte/bit meanings to names and source hashes.

Before enabling player installation:

- Prove complete native talent and mission ordinal ledgers; validate missing
  hero defaults, named power bindings, physical skins and progression formulas.
- Establish source bonus/flag/profile/review/trivia/Danger Room semantics or
  enumerate the owner's explicitly accepted approximations per sample.
- Produce final script storage metadata after narrowing; verify signed ranges,
  scope aliases, transient resets, typed registry and table/script hashes.
- For each admitted checkpoint, test load, target save/reload, zone exit/return,
  side-mission return behavior and a migrated door/conversation/boss/reward gate.
  Confirm completed unique rewards are not awarded again.
- Run the shipping C++ W2 reconstruction/save cycle with its verified economy;
  compare canonical heroes/XP/ranks/points, every gear copy/effect, Tech Bits,
  party, objectives and flags through two cycles. A slot listing is insufficient.
- Run at least one late-game host/client campaign transfer, join/leave/rejoin,
  both sides save/reload, plus a mismatched-build refusal control.
- Accept the cooperating game-writer lease live and add recoverable optional global-profile
  merge. Exercise cancel/disk-full/report failure, occupied final slot, changed
  source/build/profile, concurrent import and crash-recovery cases. Verify all
  original, unrelated slot and existing profile hashes; profile changes only
  in explicitly opted-in monotonic merge tests.

No game/emulator, desktop, network, full owned-input build or actual co-op test
is part of this round's automated validation.


## Launcher discovery, slot history and retained campaign copy

The launcher integration adds two read-only operations to the same command. All
JSONL clients keep stdin open until the process finishes; `cancel` or EOF retain
exit 5. The launcher uses individual argv values and no shell. Both source and
slot discovery emit `hello` followed by a terminal `result`.

```text
xml1-builder import-xml1-save --events jsonl <folder> --inspect-source
xml1-builder import-xml1-save --events jsonl --save-dir <SaveLC> --list-slots
```

`--inspect-source` enumerates bounded campaign folders. A successful result has
`imported=false`, `candidates=[{folder,label}]`, `source_report` and `capabilities`.
Multiple campaigns return all candidates and `source_report=null`; no latest-save
selection is made. One campaign is decoded without an installed mapping table.
Its source report includes source SHA-256, decoder, description, signature status,
provisional stock heroes with level/XP/unlocked state, mission ID/zone/party and
side-mission depth. These are source facts, not approved destination mappings.
Unsupported recomp versions and damaged envelopes retain their specific `E_XML1_*` refusal.
HDD images follow the read-only path below; no extracted host files are created.

`--list-slots` returns exactly ten `slots=[{slot,occupied}]` and an `imports` array.
Any primary, backup or pending filename with a slot's prefix reserves that slot.
Each recognized ledger row reports transaction ID, slot, checkpoint, report path,
retained campaign path and `undo_available`. That last field means that the current
slot and retained copy match the ledger hash; it does not override the release gate.
Malformed/incomplete ledgers are never advertised as undoable. Paths are local;
link/reparse ancestors are rejected before reads. No directories are created.

`capabilities` schema 1 is additive. Its flags are `extracted_folders`, `hdd_images`,
`recomp_extensions`, `player_install`, `merge_unlocks`, `undo`, plus a description
of `backup_policy`. Extracted-folder and HDD analysis are enabled. `writer_lock`
additionally names the lease protocol (`lc-save-writer/1`); it does not admit player writes.
Successful dry previews now include these capabilities, per-hero level/XP/unlock
rows and source progress in the existing `import_report`. A successful preview
still has `dry_run=true` and `imported=false`.

The existing builder exits are unchanged: 0 successful read/preview, 2 explicit
usage/import refusal, 5 cancellation, 6 operating-system I/O failure and 70 an
internal bug (1 remains general validation/pipeline failure). Machine JSON stays
on stdout. Import-specific refusal details stay in `error.detail`, with complete
English fallback text in `error.msg`; the launcher escapes that text.

The tested empty-slot installation primitive now flushes and reads back an
independent `campaign.lcsave` beside `report.json` under
`SaveLC/.xml1-imports/<transaction-id>/` before publishing the slot. Failure to
retain that copy prevents installation. Source folders, unrelated slots and the
PC profile are preserved. Existing slots are never overwritten, even after a
race; there is no overwrite option.

`undo_campaign()` is a separately tested future-CLI primitive. It holds the
cooperating game-writer lease itself, validates the
ledger, checks both slot and retained-copy hashes, refuses additional slot backup
or pending files, creates an exclusive archive link and removes only the unchanged
imported slot. Both the archive and independent copy remain with the report. A
changed slot, missing copy, foreign lock or cancellation leaves the slot intact.
The archive operation never replaces a prior archive. It does not restore or
modify a global profile.

`--undo-import <transaction-id>` is reserved at the CLI but currently returns
`E_XML1_UNVALIDATED` (exit 2) without writes, just as player apply remains gated.
Neither a user-edited table nor a frontend capability flag can enable installation.

### What still needs implementation or acceptance

- Real-source/native-loader/checkpoint acceptance, build-bound shipping import
  tables and live acceptance with the cooperating DLL before enabling apply or undo.
- Wire admitted apply to the transaction primitive and produce a final result only
  after slot, retained copy and report are committed. Required fields for the
  launcher are `ok=true`, `exit=0`, `imported=true`, `dry_run=false`, `slot`,
  `checkpoint`, `preview_token`, `output_sha256`, `transaction_id`, `backup` and
  `report` (paths as strings). The process exit must also be 0.
- Wire admitted undo to the primitive and return `ok=true`, `exit=0`, `undone=true`,
  the matching `transaction_id` and `slot`, and `retained`/`backup` paths only after
  success. A changed campaign must continue to refuse. Fresh slot scanning follows
  undo before another destination is selected.
- Real-save acceptance of the XML1-recomp decoder and real-image acceptance of
  the bounded raw/QCOW2 reader below. Synthetic coverage is not real-save acceptance.
- Recoverable multi-file global profile merging before advertising that capability.
  The launcher leaves the merge option off and disabled for this core.

No new public exit-code family or progress-event protocol is needed. Existing
JSONL result/error/warning events suffice for bounded discovery and previews.

## Read-only HDD sources (round 2)

The CLI identifies an image by bytes, not its suffix. It opens a regular local
file for reading only; Windows sharing denies a live writer and prevents writes
and deletion until inspection closes. It never opens backing files, mounts a
volume, opens a device, follows links, exports a save, or repairs disk structures.
The Xbox envelope and retail decoder receive the selected `save.dat` bytes in RAM.

```text
xml1-builder import-xml1-save <image.qcow2> --inspect-source --events jsonl
xml1-builder import-xml1-save <image.raw> --campaign E:/UDATA/4156001e/<campaign>
    --build <build> --save-dir <SaveLC> --slot 0 --dry-run --events jsonl
```

Standalone QCOW2 v2/v3 supports standard L1/L2 mappings, sparse/zero clusters,
and bounded raw-DEFLATE compressed clusters. Encryption, backing chains, internal
snapshots, dirty/corrupt flags, external data files, extended L2 tables and other
incompatible features refuse with `E_XML1_DISK_VERSION`. Unsupported input is
never flattened or rewritten. Invalid bounds, alignment, metadata overlaps,
reserved mapping bits, truncation and invalid compression produce
`E_XML1_DISK_DAMAGED`. These use the existing refusal exit 2.

The reader parses the 512-byte Xbox `****PARTINFO****` sector: fourteen 32-byte
entries at byte 48, with 16-byte names and little-endian flags/start/count/reserved
dwords. Only active flag `0x80000000` is supported. All active ranges must fit
and not overlap. Entry zero must be the E data partition (`XBOX DATA`, `E`, or
`E:`). Without PARTINFO it tries only the retail E offset `0xabe80000`, length
`0x9896b0 * 512`, and requires a FATX superblock there. It does not scan a disk
for plausible saves or infer partitions from the image's unused end.

FATX16/32 reads the 4096-byte superblock, aligned FAT and root cluster; sectors
are 512 bytes and cluster sizes are 1..128 power-of-two sectors. FAT width uses
partition cluster capacity (<65525: 16-bit, otherwise 32-bit); accessible cluster
bounds additionally subtract the header and FAT. It traverses E:/UDATA, selects
only title `4156001e`, and enumerates bounded campaign subdirectories. FATX names
retain their byte spelling via Latin-1, up to the native 42 bytes, including long
names and fragmented directory/file chains. No host path is derived from a name.
Unsafe names, duplicate folded names, free/reserved/bad/out-of-range clusters,
cycles, touched-chain cross-links and file/chain length disagreements refuse.
The reader validates structures it uses; it is not a full-volume filesystem or
QCOW2 refcount consistency checker. Unrelated title contents are not scanned.

Budgets per inspection are 2 TiB guest size, 16 MiB per read, 64 MiB physical
I/O and 64 MiB decompression, 8 MiB L1/refcount tables, 4096 metadata extents,
eight L2 cache entries, 8 MiB compressed-cluster cache, 1024 clusters per directory,
8192 root/UDATA/title entries total, and the existing 256 title entries/four nested
levels. Campaign bytes remain capped at `0x2fc00 + 24`. Excessive but potentially
valid inputs refuse explicitly. No whole multi-gigabyte image hash is required.

Discovery candidates for images are `{folder: <image path>, label: <in-image
campaign path>, campaign: <same exact path>}`. Multiple candidates return
`source_report=null`; a client must retain the image as the source and pass the
selected `campaign` as `--campaign` in both inspection and preview. A unique
campaign needs no selector. Extracted-folder candidates retain their previous
shape. The launcher from the earlier UI round still has a hard-coded HDD guidance
branch; its next integration must enable this CLI path and carry the selector.
No launcher source is changed in this round.

Source facts and preview reports include `source_container`: kind, image format,
campaign, image file identity and a SHA-256 of the bounded physical read set.
The preview token binds this context as well as the extracted envelope hash.
Rechecking reopens the same image, repeats mapping and traversal, and compares
file identity, read-set hash and envelope hash; drift refuses. SHA-256 remains
provenance rather than Xbox signature authentication. No real HDD/save sample
has been inspected in this implementation round; synthetic fixtures prove the
code paths, not compatibility with all real images.

## Cooperating game writer lease (round 2)

Protocol `lc-save-writer/1` uses `SaveLC/.lc-save-writer.lock`. Both Python and
the companion DLL open that same file with Win32 `GENERIC_READ | GENERIC_WRITE`,
share mode zero, `OPEN_ALWAYS`, no handle inheritance and reparse-point refusal.
Neither truncates, writes contents, deletes, replaces or ages the lock file.
Its existence is normal; the live handle is the lease. Normal close or process
death releases it immediately, so an unlocked file left by a crash is reusable.
No PID, timeout, boot identifier or stale-file deletion is involved. The Python
fallback uses a nonblocking exclusive `flock` on other hosts; the game is Windows.

The DLL acquires its lease during `save_format::ensure_ready()`, after resolving
and creating SaveLC but before reading save data, loading tables or migrating
legacy files. It keeps the handle through its entire LC save lifetime, including
menus, campaign/profile writes and slot deletion. Acquisition failure uses the
existing fail-closed LC state; restarting after the other owner exits is required.
Holding through gameplay also prevents an importer installing over a slot that
an already loaded campaign might later overwrite. `save status` reports the
protocol and whether the lease is held. `[Save] Format=off` does not participate.

`install_campaign()` and `undo_campaign()` acquire the same lease themselves,
before any transaction mutation and through every source/table/slot/hash recheck,
publication/archive and cleanup. Concurrent cooperating games/importers refuse
`E_XML1_BUSY`; a pre-protocol `.xml1-import.lock` also refuses and is preserved for
manual review with all old writers closed. Preview/discovery never create or
acquire a writer lock, so they remain read-only. Slot occupancy and hashes must
still be rechecked on admitted apply. The lease excludes cooperating versions;
it cannot prove an older DLL or another tool obeys it. Apply/undo admission gates
remain false, including when a table advertises release readiness.

The DLL's evidence anchors are CMemoryCardWin32 vtable `0x69aa8c`, object
`0x6e03d8`, folder buffer `0x7ad6a0`, init `0x55e760`; slot writer `0x55fe70`
(vt+0x64), profile writer `0x55f9a0` (vt+0x54), slot delete `0x55e930` (vt+0x70),
delete-all `0x55f6f0` (vt+0x28), serializer `0x46baf0` (CGame vt+0x208).
`save_format_rules.hpp` retains the guarded addresses/signatures; no new binary
hook or unverified save-writer address is introduced by the lease.

## XML1-recomp source decoding and preview

This implementation follows the locally surveyed upstream revision `a30ec29`.
Newer upstream may differ. The evidence is the source's `character_save.h`,
`character_talent_record.h`, `talent_identity_save.c`, `raven_power_bindings.cpp`,
`raven_progress_stream.h`, `raven_campaign_state_guest.c` and `raven_stash_owner.cpp`.
It has been checked with invented saves, through the Python LC/W2 loader and
two native-stream serialization cycles. No player recomp save or shipping
C++ game load has been tested here. Import and Undo remain disabled.

The surveyed Windows player build resolves its data root beside the executable
when `default.xbe` is present, and keeps saves under
`<recomp installation>/UDATA/4156001e/<campaign>/save.dat`. Its README documents
installation-local `UDATA`/`TDATA`; `TDATA` and `pc-settings.ini` are not campaign
inputs. Developer builds use their configured game-data root (and diagnostic
builds may explicitly override it). No user-profile or AppData save location is
assumed, and no disks or user directories are searched automatically.

```text
xml1-builder import-xml1-save <recomp installation> --source-kind recomp
    --inspect-source --events jsonl
xml1-builder import-xml1-save <campaign folder or save.dat> --source-kind recomp
    --build <build> --save-dir <SaveLC> --slot 0 --dry-run --allow-inferred
```

The explicit `recomp` kind selects only installation-local `UDATA`, avoiding
asset subtrees. A UDATA, title or individual campaign folder also works. Multiple
campaigns are returned for selection; no latest-save choice is made. `auto`
recognizes XML1CHR only at payload `0x5c6`, including saves extracted into memory
from HDD images. `xemu` explicitly selects the retail decoder. Both retain the
existing raw/QCOW2 readers. The outer envelope remains a little-endian u32 length,
20 opaque signature bytes and exactly that many payload bytes, capped at
`0x2fc00`. Signatures remain unauthenticated. Inspection and previews write no
source, destination, profile, lock or metadata files.

| Section | Supported wire contract |
| --- | --- |
| XML1CHR v1 | Minimum 48-byte header: magic, u16 version/header length/snapshot count/reserved, 32-byte positional definition bitmap. Records follow ascending set IDs; IDs 0/255, empty/over-48 live rosters and snapshots other than 48 refuse. Native unlock bank and 48 restore records follow. |
| XML1CHR v2 | Each talent value expands from three bytes of four-bit fields to four bytes of five six-bit fields. The top two bits must be zero. |
| XML1CHR v3 | Header adds a u16 selection count and 100 bytes per named owner: five zero-padded 20-byte strings (owner plus four moves). |
| XML1CHR v4 | Header adds separate u16 selection/identity lengths. TLID v1 records bind each nonzero native talent byte ID to exact name, source filename and selector. A saved talent without an identity refuses. |
| XML1CHR v5/v6 | Every live and restore record inserts two permanent health/energy bonus bytes after its 44-byte prefix; v6 adds a boolean auto-equip byte. |
| XML1PRG v1 | Optional 16-byte hard-difficulty unlock section after the native embedded profile. |
| XML1DIF v1–5 | Optional 20/22/112/120/124-byte records: live/retained difficulty, acts, two recall records, cooldown floats, then pickup-allowance bonuses. |
| XML1STSH v1 | Optional declared-size section after PRG/DIF, with snapshot-valid flag and two named item/quantity lists. Each list has at most 60 copies total; names, quantities, framing and native inventory validity are checked. |

Adjuncts are consumed only at their documented boundary, in PRG/DIF/STSH order;
duplicates or reordered known sections refuse. No magic scanning or resynchronization
is used. Bounds, versions, reserved fields, finite floats, duplicate identities,
name termination/padding and aggregate counts are checked before mapping.

A schema-1 import table can describe a recomp source with `source.kind="recomp"`,
the existing source `id`, `title_id`, `xbe_sha256`, plus `herostat_sha256` and
`definitions`, an explicit object of decimal definition IDs to exact source names.
The hash identifies the **effective** source herostat, including loose/modded
overlays. The ledger must be captured from that exact configuration; it must not
be filled from the stock roster, a sorted list, or the first 21 save records.
Optional `hero_names`, if supplied, must agree with those names. The envelope
does not authenticate the ledger or identify which herostat produced it: choosing
and proving the right source profile remains part of real-save acceptance.
Without a table, inspection reports `definition_<id>` placeholders and explicitly
unresolved identity status. It does not label these as identified heroes.

Recomp `heroes` mappings may cover a subset of the source definitions. Supported
heroes are written in the installed LC roster order (21 slots in LC), with pinned
`target_defaults` for absent heroes. Unlocks use exact definition IDs, including
sparse/high IDs. Unsupported nonparty heroes are individually listed in `skipped`,
including progression, talents, selected skin, equipment and unlock status.
Representable equipment from those heroes moves to carried inventory, with an
explicit approximation and copy conservation under either quantity policy. Any
unsupported party member or controlled character refuses with `E_XML1_IDENTITY`.
There is no record-count truncation. Unknown saved/unlocked IDs refuse.

For v1–3, proven native byte-to-talent tables are still needed. For v4–6,
`named_talents[hero]` lists `{name,source,selector,target:[owner,talent]}` rows.
All three source strings must match; a reused runtime byte or matching name alone
cannot choose a target talent. Purchased ranks through 63 are representable;
limits/baselines over 3 and pending upgrades refuse rather than clip. Source
equipment bonuses are explicitly recalculated. Optional per-hero `power_selections`
maps source move names (including the empty string) to supported target chains;
unmapped saved selections are individually reported as defaults or omissions.
Permanent vitality bytes are preserved as target health/energy boosts. Enabled
auto-equip currently resets to manual equipment with a preview approximation.

An explicit decoded difficulty is preserved in both META and GAME, including
Easy `0`; absent DIF means Normal by the recomp reader's documented default.
The shared mapper honors explicit difficulty from either decoder family. No
retail difficulty byte has been established in the native XML1 record, so retail
keeps a disclosed Normal fallback instead of interpreting an unrelated byte.
The saved current act must agree with the checkpoint. Retained act/difficulty,
recall departure/cooldowns, pickup allowances and unproven Hard-unlock profile
state are disclosed as reset/skipped. They are not copied into arbitrary flags.

Named live stash gear needs an exact `source_name` on one equipment item mapping.
Every mapped copy becomes carried target equipment, with the location change
reported; unknown gear refuses. Stash snapshots are rollback state and are listed
as invalidated, separately from live inventory. Native equipment and enhancement
budgets remain enforced by the LC/W2 loader. These previews do not prove gameplay
effects, source signature validity, actual checkpoint safety, save/reload behavior
or co-op compatibility. Those require private real recomp saves and runtime tests.
