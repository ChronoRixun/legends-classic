# Original Xbox campaign import core (round 1)

This is an offline developer core with synthetic acceptance tests. It is **not
enabled for player installation**. No real Xbox campaign was available for this
round. No stock talent-byte ledger, source mission-byte ledger or tested retail
checkpoint recipe is invented to fill that gap. XML1-recomp extensions produce
specific version refusals; they are not decoded as retail padding.

The owner-approved behavior is checkpoint continuation with an explicit list
of changes, W2 saves plus the XML1 economy and XP curve, an unchanged source,
and an unchanged global profile unless the player selects **Also merge unlocks**.

## Command

From `tools/`, or through the packaged `xml1-builder` entry point:

```text
python -m xml1builder import-xml1-save <extracted Xbox save folder>
    --build <installed LC build> --save-dir <actual SaveLC folder>
    --slot 0..9 [--merge-unlocks] [--dry-run] [--events jsonl]
    [--allow-inferred] [--import-table <local table>]
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
checkpoint evidence, shipping C++ loader/economy parity, cooperating game save
locking and a recoverable campaign/profile transaction.

There is no network input, upload, signature repair or original-save write.
Inputs must be extracted local folders, not archives, disk images, save states,
URLs, links or reparse points. Selecting multiple `save.dat` files produces a
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
- Add cooperating game-writer locking and recoverable optional global-profile
  merge. Exercise cancel/disk-full/report failure, occupied final slot, changed
  source/build/profile, concurrent import and crash-recovery cases. Verify all
  original, unrelated slot and existing profile hashes; profile changes only
  in explicitly opted-in monotonic merge tests.

No game/emulator, desktop, network, full owned-input build or actual co-op test
is part of this round's automated validation.
