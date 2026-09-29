# M3 "shippable": the XML1 builder (design)

Status: design, 2026-09-28. No code changed. Written from the code as it is at xml1-port `f8dc2e2`,
ultimate-legends `main 970024e` / `display-settings 2680372`, xml2-fix `display 1c750e3` (v1.2.0 in CMake, unreleased).

Owen's decisions this design follows:

- (a) a **standalone builder executable** that the Ultimate Legends launcher calls; no builder logic in the launcher;
- (b) the XML1 input is the user's **Xbox disc image only**;
- (c) the tools repo goes **public** when done: bring-your-own-copy, never distribute game files, a modified exe, or
  anything derived that contains game content; in-memory engine fixes ship as the xml2-fix `dinput.dll` proxy.

---------------------------------------------------------------------------------------------------------------

## 0. Findings that shape the plan (read these first)

| # | Finding | Where | Consequence |
|---|---|---|---|
| F1 | **A clean checkout cannot build today.** The pipeline reads gitignored, game-derived *research outputs* (rewritten scripts, converted sound banks, fixed music banks) and three hand-made source trees (`xml1_xbox/`, `xml1_assets/`, `xml1_loose/`). They were produced once, by hand, by research prototypes with hard-coded absolute paths and module-level code. | `common.py:36-52`, `scripts.py:54,199-239`, `media.py:74-77`, `research/scripts/rewrite_scripts.py:40-46` | The builder needs a **prepare** phase that regenerates all of them from the ISO + XML2 install on the user's PC (section 1.5). This is the biggest M3 work item. |
| F2 | **Sound preparation dominated the first build** (phase 1p + 1b: a first build from the ISO now takes 5.5 min on Owen's PC, 1.5 status). The 216-bank Xbox→PC IMA conversion logged 4,002 CPU-s (`research/sound/out/all_ima_log.jsonl`; 1,194 s of it on music banks that the fixed banks replace anyway), the 61 fixed music banks 8,853 s (`music0x20/banks/eng/_fix_music_report.json` `seconds_taken`, beam encoder, numpy). The content modules + validator take ~230-290 s (`build/_heroes/_build/report.json`: media 118, validate 55, zones 35, characters 15, scripts 11). | | First build today ≈ 15 min on 16 threads, ~25 on 8, ~50 on 4 (estimate: ~11,700 CPU-s / cores, one bank per core, + ~6 min). Rebuilds with a warm cache ≈ 5 min. Progress UI, cancellation, caching and a perf pass (Phase 1p) are required, not optional. |
| F3 | **A rebuild deletes the launcher's files.** `sweep_stale` deletes every file that is neither a base file nor registered; the base index *excludes* `dinput.dll`, `mods/`, `xml2-fix.*` (`PROXY_PATTERNS`), so a rebuild into an installed port removes the DLL, the ini, the log **and the user's mods**. Validator V1 also errors on proxy files in `<out>`. | `common.py:88,743,1281-1316`; harness.py docstring | Builder mode must keep `PROXY_PATTERNS` in `<out>` (never sweep, never V1-error them) and merge its ini keys instead of rewriting the file. |
| F4 | **The XML1-specific xml2-fix is unreleased.** Everything the port needs (`NewGameTeam`, `ResetUnlocks`, `SaveFolder`, `ForcedTeams`/`JoinHero`, `PostgameScript`, `MainMenuItems`, `XPCurve`, `[Limits]`, menus at 60, pad prompts, `LocalIP`) is on the local `display` branch (38 commits ahead of `main`). The latest release is v1.1.1, and `ChronoRixun/xml2-fix` is private (the launcher's xml2 setup 404s for anyone else). The launcher always takes `releases/latest`. | xml2-fix `CMakeLists.txt:2` (1.2.0), launcher `game_config.cpp:15` | Release xml2-fix **v1.2.0 publicly** before M3 ships; the build stamp records the minimum DLL version (section 2.8). |
| F5 | **XML1 and XML2 both run `XMen2.exe`.** The launcher's "is running" / `stop-game` match the exe *name* (`Process32` `szExeFile`), so the two library entries would see each other as running and Stop would kill the wrong game. | launcher `game_commands.cpp:145-187` | Match running processes by full image path (`QueryFullProcessImageNameW`) before adding the xml1 entry. |
| F6 | **Hard-coded paths and repo-relative data.** `ROOT = parents[2]`, `DEFAULT_BASE = <XML2 folder>`, `_check_out_safe` protects repo trees, `harness.DEFAULT_DLL/REAL_INSTALL`, `regress_nyc1.ROOT`, and the research generators' `LOOSE/ASSETS` constants. | `common.py:36-42,1228-1241`, `harness.py:26-27` | Replace with a `Sources` object (disc cache, prepared-output cache, packaged read-only data) passed through `BuildContext`; repo-relative paths only in developer mode. |
| F7 | The shared XML2 **registry settings** (`HKCU\Software\Activision\X-Men Legends 2\Settings\Display`, `...\Controls\Player1..4`) are read by the port too: key bindings and resolution are shared between XML2 and the port (saves are not: `SaveFolder`). | registry on Owen's PC | Known limitation for M3; candidate xml2-fix key `[Game] RegistryKey=` later (open question Q9). |

---------------------------------------------------------------------------------------------------------------

## 1. Inputs and validation

### 1.1 The XML1 Xbox disc image

**Owen's dump (reference):** `X-Men Legends (World).iso`, 7,825,162,240 bytes = a Redump **XGD1** full-disc image
(video partition + game partition); the XDVDFS game partition starts at `0x18300000` (`MICROSOFT*XBOX*MEDIA` at
`+0x10000`, root directory sector 303734). `tools/xdvdfs_extract.py` already probes the offsets
`0x18300000, 0x0FD90000, 0x02080000, 0`.

`default.xbe` (4,698,112 bytes, md5 `1e1a766ae4dc9f5f0151aa4ce029f362`, built 2004-08-15): certificate title
**`X-Men Legends`**, title ID **`0x4156001E`** (publisher `AV` = Activision, game 30), version `0x1`, game region
`0x7` (North America + Japan + rest of world), no alternate title IDs. The disc carries both `movies/ntsc` and
`movies/pal`, which fits one worldwide master ("World" in the Redump name).

**Formats the builder accepts** (detected by content, never by extension):

| Format | Detection | Notes |
|---|---|---|
| Redump full image (XGD1), `.iso` | XDVDFS magic at `0x18300000 + 0x10000` (and the same magic at `+0x7EC` of that sector) | Owen's dump. |
| XISO (extract-xiso / xdvdfs "rewritten" or trimmed game partition), `.iso` / `.xiso` | magic at `0x10000` | Common in the Xbox scene; same filesystem, offset 0. |
| XGD2/XGD3 offsets | magic at `0x0FD90000` / `0x02080000` | Harmless to keep; XML1 is XGD1. |

**Rejected with a specific message** (`E_ISO_NOT_XBOX` + `detected`): a PS2 image (ISO9660 PVD `CD001` at `0x8000`
with `BOOT2 = cdrom0:\SLUS_...` in `SYSTEM.CNF`), a GameCube image (magic `0xC2339F3D` at `0x1C`), a PC/other
ISO9660 image, a compressed CCI/CSO image (`E_ISO_COMPRESSED`: "decompress it with ... first"; supporting CCI is open
question Q3), a folder (decision b).

**Identification (after the filesystem opens):**

1. `default.xbe` exists, starts with `XBEH`, and its certificate title ID is `0x4156001E` -> else
   `E_ISO_WRONG_GAME` (message names the title it found).
2. The required files exist with plausible sizes: `z/assetsfb.zip` (656,461,422 bytes in Owen's dump), 34 movies
   under `movies/ntsc/<c1>/<c2>/*.sfd` (only needed with movies on), `sounds/zsds/**` (XML1's ZSND banks, read by the
   sound preparation and by `media`'s music check). Missing -> `E_ISO_INCOMPLETE` (a demo disc or a bad rip).
3. `known_dumps.json` (shipped; hashes only) lists recognised dumps: xbe md5, `assetsfb.zip` size + CRC-32 of its
   central directory, Redump ISO sha1 (for `verify --deep`). A dump that passes 1-2 but is not in the list builds
   with warning `W_ISO_UNKNOWN_DUMP` (the validator still gates the output); the result stamp records
   `"known": false`, so bug reports show it.
4. Integrity: `zipfile.ZipFile.testzip()` over `assetsfb.zip` read in place (627 MB, every entry's CRC) catches a
   damaged dump in ~10 s without hashing 7.8 GB. `verify --deep` hashes the whole image.

**Regional variants.** Owen's disc is region-free and single-master; I know of no other XML1 Xbox master, but I did
not check Redump's list. Reprints (Platinum Hits) normally keep the title ID and content. Open question Q2: collect
the Redump entries (and any community dumps) into `known_dumps.json` before release. The GameCube and PS2 versions
are out of scope (decision b); they are detected so the error is helpful.

**Reading strategy.** XDVDFS stores every file as one contiguous extent, so the builder reads files straight out of
the image through a small `SubFile` (seek/read/tell window) - no 7.8 GB copy:

- `z/assetsfb.zip` is opened with `zipfile` *on the window* and its members are streamed; the `.fb` bundles under
  `packages/` (1.7 GB of the 1.83 GB unzipped, 875 bundles) are read member by member into memory and parsed with
  `fb_unpack.entries`' record layout (name[0x80], type[0x40], u32 size, data; adapted to take bytes) and written
  straight into the loose tree - they never hit the disk as `.fb` files. `xml1_assets/` today keeps them (1.7 GB);
  the builder does not.
- `sounds/zsds/**` (595 MB) and `default.xbe` (4.7 MB; validator V7 reads its `ea_*` enum strings,
  `validate.py:2317-2319`) are copied to the disc cache.
- `movies/ntsc/**` (648 MB) is copied only with movies on. Even a `--no-movies` build reads the movies today: their
  names (`scripts.py:2037`, `validate.py:2983`) and ADX durations for the Review screen (`media.movie_duration`,
  called from `frontend.py:816`). P1 therefore always writes `disc/movies.json` (name, path, size, ADX rate and
  sample count, parsed while streaming from the image) and those providers read the index when the files are
  absent. (Done in phase 1b: SPEC.md 27.3.)
- `movies/pal`, `media/*.bin`, `OptionsImage.xpr`, `sounds/badaudio.wav` are never read.

### 1.2 The XML2 PC install

**Detection.** The launcher passes the path of its set-up xml2 entry (`xml2-install` property); the builder never
searches the disk. Standalone users pass `--xml2`. (Owen's install has no HKLM uninstall key - it is a copied
folder - so registry detection would not help.)

**Checks** (`info` and `build`):

| Check | Reference (Owen's install) | Failure |
|---|---|---|
| `XMen2.exe` exists, PE32, image base `0x400000` | | `E_XML2_NOT_FOUND` |
| `XMen2.exe` md5 in `known_xml2.json` | 3,129,344 bytes, md5 `b34f0baf1058d518f55b3cefb3fccc5f`, PE timestamp 2005-09-08 13:25:03 UTC, sections `.text .rdata .data .tls .data1 .rsrc` (no SecuROM/SafeDisc section) | `E_XML2_UNKNOWN_EXE` (hard error, `--allow-unknown-exe` for testers) |
| English data present | `Data/herostat.engb`, `Sounds/eng/`, `Movies/*.engb`, `build.ini` `Language = ENG` | `E_XML2_LANGUAGE` |
| Base files unmodified (the pipeline *merges* herostat, npcstat, zoneinfo, shared_talents, items, sound banks ... from the base) | `known_xml2.json` carries (rel, size, sha1) for the 13,382 base files (the index `common.FileIndex` builds, proxy excluded). `info` compares names + sizes only (seconds); `build` and `verify --deep` hash (2.3 GB, ~10-30 s on an SSD) | files the pipeline reads: `E_XML2_MODIFIED` listing them; others: `W_XML2_MODIFIED` |
| Not running from the install and not the output | `_check_out_safe` | `E_OUT_UNSAFE` |

Why the exe check is a hard error: xml2-fix guards every patch site byte-for-byte against the retail build and, on
another build, logs and *leaves the game alone* (`forced_teams.cpp:828`, `limits.cpp:210`, `new_game.cpp:124`,
...). The port would then start, but New Game, forced parties, the XP curve and the limits would silently be XML2's -
a broken campaign that looks like a port bug. `build.ini`'s comments mention Beenox-built Polish and Russian
versions, so other exes exist (open question Q1: which retail builds exist, and are any byte-identical at every
xml2-fix guard?).

A mod the user installed *into* XML2's folder (loose files over base files) shows up as `E/W_XML2_MODIFIED`. The
xml2-fix `mods/` folder is already excluded (`PROXY_PATTERNS`) and never copied.

### 1.3 Disk space

Measured on Owen's PC:

| What | Size |
|---|---|
| XML2 install (the base the output copies) | 2.3 GB (1.9 GB without `.sfd`) |
| Output, movies on (`build/_heroes`) | 4.2 GB + 372 MB `_build/media_cache` (a snapshot of the fixed music banks) |
| Output, movies off (`build/_nb3`) | 3.1 GB + cache |
| Disc cache: loose tree 867 MB, assets outside `packages/` 45 MB, `movies/ntsc` 648 MB, `sounds/zsds` 595 MB | ~2.1 GB (measured P1: 2.16 GB, 1.5 GB without the movies) |
| Prepared outputs (measured, phase 1b): P4 676 MB = all_ima 523 MB (the 61 music banks stay, SPEC 27.6) + merged 153 MB; P5 372 MB; P3 4 MB; P2 1 MB | ~1.05 GB |
| **Peak with movies, cache kept** | output 4.6 GB + cache 3.2 GB ≈ **7.8 GB** (measured; 6.1 GB without movies) |

The builder checks `shutil.disk_usage` on the output volume (output estimate - bytes already present in a previous
build of the same `<out>` + 10 %) and on the cache volume (cache estimate - cache present), per volume when they
share one. `E_SPACE` names the volume and the shortfall. `info` returns the estimates so the launcher can show them
before the build starts.

Two savings, both measured by the design, not implemented:

- **Do not snapshot fixed music into `<out>/_build/media_cache`** in builder mode (the prepared cache is the source;
  saves 372 MB per output).
- **`--link-base`** hard-links unchanged base files instead of copying them (same NTFS volume only; saves ~2 GB).
  The pipeline already writes with temp file + `os.replace` (`common._atomic_write`), which never writes through a
  link. The risk is outside the pipeline: anything that edits a linked file *in place* edits the real XML2 install
  too (and a read-only attribute is shared by both names). Default **off**; a launcher option "Save disk space".

### 1.4 What the build reads today

| Input | Path today | Role | Builder source |
|---|---|---|---|
| XML2 install | `--base` (`DEFAULT_BASE`) | synced into `<out>`, base index, merged tables | `--xml2` |
| XML1 loose files | `xml1_loose/` (+ `_fb_manifest.json`) | zones, characters, scripts sources | disc cache (unpacked `.fb`) |
| XML1 assets | `xml1_assets/` | data tables, subtitles, UI, textures (loose wins on overlap, `ctx.x1_path`) | disc cache (unzipped, minus `packages/`) |
| XML1 disc files | `xml1_xbox/movies/ntsc`, `xml1_xbox/sounds/zsds`, `xml1_xbox/default.xbe` | movies + durations (`media.py:66,680-697,756`), music originals (`media.py:520`, `validate.py:1291`, `characters.py:863`), `ea_*` strings (`validate.py:2319`) | disc cache |
| Research outputs (gitignored) | `research/scripts/out`, `research/sound/out/{all_ima,merged}/eng`, `research/sound/music0x20/banks*/eng` | installed scripts / dialogs / missions, inline rewrites, zone acts; sound banks; fixed music | **prepared on the user's PC** (1.5) |
| Research tables (tracked) | `research/sweep/*.json`, `research/characters/*.json`, `research/scripts/*api*.json`, `mission_plan.json` | indexes and API tables | packaged data or regenerated (1.5) |
| Research modules | `sweeplib`, `x1names`, `zsnd`, `ztrk`, `zhash`, `adpcm`, `bescript` via `sys.path` | parsers / codecs | move into the builder package |

### 1.5 Provenance of the research inputs, and the prepare phase

How every research input the build reads was made, and what the builder does with it. "trk" = tracked in git,
"ign" = gitignored. Generator paths are under `research/` unless they start with `tools/`.

**Game content: must be produced on the user's PC (the prepare phase).**

| Input (build reader) | Size | Generator | Generator inputs | Cost (logged) |
|---|---|---|---|---|
| `scripts/out/scripts/**.py` (1,536), `dialogs/x1/*` (276), `data/missions/*` (29), `zone_acts.json`, `inline_rewrites.json`, `helper_refs.json`, `zone_extra_files.json`, `var_storage.json` (ign; `scripts.py:199-239,291,553,1975`, `characters.py:271,279,1534`, `zones.py:928,1643,1942`, `zones_providers.py`, `frontend.py:912`, `testhooks.py:67`) | 3.5 MB | `scripts/rewrite_scripts.py` (analysis runs at import, lines 47-423; hard-coded `LOOSE`/`ASSETS`, line 41-42) + `scripts/mission_plan.py` (runs at import; writes `out/data/missions/*.xml` and `mission_plan.json`) | `xml1_loose` + manifest, `xml1_assets` (scripts, `data/strings.eng`, `data/missions`), `xml1_api.json`, `xml2_api.json`, `bescript.py`, `tools/xmlb.py` | ~8 s (`_summaries/scripts.md:167`) |
| `scripts/mission_plan.json` (trk; `scripts.py:737,752,1611`, `zones.py:1950`) | 100 KB | `scripts/mission_plan.py:129` | `xml1_assets/data/missions/*` | seconds; **holds ~280 objective names/descriptions (game text)** |
| `sound/out/all_ima/eng/**` (ign; `common.py:1162`, `media.py:404`) | 523 MB, 216 banks | `sound/convert_zsnd.py --batch xml1_xbox/sounds/zsds <out>/eng --rekey character/=char/` (encoder `auto`) | `sounds/zsds`, `sound/names_xml1.json` (the `char/` aliases; missing file = aliases silently skipped) | 4,002 CPU-s logged (1,194 of it on the 61 music banks the fixed banks replace); worst bank 645 s |
| `sound/out/merged/eng/**` (ign; `common.py:1163`, `media.py:403`, `validate.py:675`) | 153 MB, 18 banks | `sound/merge_all.py` (runs at import) + `merge_zsnd.py` | `all_ima/eng` + XML2 `Sounds/eng` | not logged (small) |
| `sound/music0x20/banks/eng/**` (ign; `media.py:74,156`) | 372 MB, 61 banks | `tools/fix_music.py fix` | `sounds/zsds` `*_a`/`*_c` originals; `convert_zsnd`, `adpcm`, `zsnd`; **numpy** | 8,853 s logged (`seconds_taken`); worst bank 511 s |
| fallback music dirs `banks_22k`, `_previous_attempt` (ign; `media.py:74-75`) | 192 MB | older `fix_music` runs | | drop in the builder (`FIXED_MUSIC_DIRS` = the prepared dir only) |

**Facts about the binaries: ship as packaged data** (pinned to the exe/xbe hashes in `known_*.json`; regenerated
only by developers):

| Input | Generator (dev only) | Note |
|---|---|---|
| `scripts/xml2_api.json`, `scripts/xml1_api.json` (trk) | `scan_functable.py` -> `*_api_raw.json` -> `api_diff.py` | names, signatures, addresses; needs `pefile` |
| `scripts/xml2fix_api.json` (trk) | hand-written, mirrors `scripts_transform.XML2FIX_API` | keep in sync with the xml2-fix release |
| `scripts/xml2_console_cmds.txt` (trk; `validate_frontend.py:44`) | `console_cmds.py` over `xml2_text.asm` (`capstone`) | only the command names are used: ship a name list |
| `characters/combat_compat.json` (trk) | `combat_compat.py` (exe + xbe strings + styles) | only `unknown_handlers` is read |
| `scripts/verify/console_senders.json` (trk) | none | identical to `scripts_lint.CONSOLE_SENDERS_DEFAULT`: drop the file |

**Name/graph indexes derived from the data: regenerate the cheap ones, strip and ship the expensive one.**

| Input | Build reader | Generator + inputs | Builder |
|---|---|---|---|
| `characters/collisions.json` (trk, 265 KB, names + status) | `x1names.py:31` (every `map_*` rename), `characters.py:361` | `characters/collisions.py` (all of `xml1_loose` vs the XML2 install; hard-coded paths via `characters/common.py`) | **regenerate** in prepare (it decides every `x1_` rename; a shipped copy would be silently wrong for a different install) |
| `characters/x2_stats_refs.json` (trk) | `characters.py:236`, `validate.py:965` | `characters/x2_unref.py` (XML2 install + exe strings; runs at import) | regenerate (cheap) |
| `sweep/graph.json` (trk, 91 KB; **~120 mission titles/descriptions**) | `common.py:810`, `scripts.py:1025,1107,1151,1464`, `zones.py:1987,2368`, `validate.py:1777` | `sweep/sweep.py` (needs a 2 GB `xml2_copy` from `make_copy.py`, `convert_zone` of every zone, `script_table.py` + `pefile`) then `graph.py` | **strip** `descname`/`description` and ship as data (the build uses `reachable_from_new_game`, `reachable_missions`, `missions`, `mission_start_zones`, `zone_edges`); regenerating it needs the whole sweep - not worth it for M3 |
| `sweep/zones.json` (trk, 1.2 MB) | only `media.py:1071` (one sound-bank-slot warning) | `sweep/sweep.py` | compute that warning from the zone `.chr` files in the build; drop the file from the build path |
| `sound/names_xml1.json` (trk, 214 KB) | not the build: `convert_zsnd.load_names` | `sound/resolve.py` + `soundrefs.py` | regenerate in prepare (cheap; it feeds the `char/` aliases) |
| `sweep/collisions.json` (trk, 618 KB) | `ctx.collisions` exists (`common.py:804`) but **nothing reads it** | `sweep/collisions.py` | remove the property; not shipped |

**Research modules imported by the build** (`common.py:46-52`, `media.py:61-63`, `media_music.py:39-44`,
`validate_sound.py:32`): `sweeplib` (line 5 prepends a hard-coded absolute `.../tools` to `sys.path` at
import), `x1names` (opens `collisions.json` relative to itself), `zsnd`, `ztrk`, `zhash`, `adpcm`, `simlookup`,
plus the generators' `bescript`, `convert_zsnd`, `merge_zsnd`. They move into the builder package
(`tools/xml1build/lib/`) with the `sys.path` tricks and hard-coded paths removed; `research/` keeps the history.
(Done in phase 3, 3.6.)

**The prepare phase** (new `tools/xml1build/prepare/`, each stage a pure function `run(sources, out_dir,
progress, cancel)` with a cache key = stage version + digests of its inputs):

| Stage | Replaces | Output (cache) | Cost estimate |
|---|---|---|---|
| P1 `disc` | `xdvdfs_extract.py` + an unzip nobody scripted + `fb_unpack.py` | `disc/loose` (+ `_fb_manifest.json`, first bundle in sorted order wins, as `fb_unpack` does), `disc/assets` (without `packages/`), `disc/default.xbe`, `disc/sounds/zsds`, `disc/movies.json`, `disc/movies/ntsc` (movies on) | I/O bound: read ~1.9 GB, write ~2.2 GB; measured 17 s (13 s without movies) |
| P2 `tables` | `mission_plan.py`, `characters/collisions.py`, `x2_unref.py`, `resolve.py` | `tables/*.json` | measured 25-46 s |
| P3 `scripts` | `rewrite_scripts.py` | `scripts/out/**` (same layout) | measured 8 s |
| P4 `sound` | `convert_zsnd --batch` (the 61 music banks stay - the planner and media's structure check use them, SPEC 27.6), `merge_all.py` | `sound/all_ima/eng`, `sound/merged/eng` | ~2,800 CPU-s before 1p; measured with the kernel 18 s on 8 jobs, 26 s on 4 (78-98 CPU-s) |
| P5 `music` | `fix_music.py fix` + `media_music.check_bank` per bank | `music/banks/eng` | ~8,850 CPU-s before 1p; measured with the kernel 93 s on 8 jobs, 100 s on 4 (memory-bound, SPEC 27.9) |

P4 + P5 are ~11,700 CPU-s with single-threaded work per bank (critical path >= the largest bank, ~10 min).
Estimated wall time today: ~15 min on Owen's 16 threads, ~25 min on 8, ~50 min on 4 - on top of ~6 min for P1-P3
and the pipeline. Phase 1p (section 6) targets a first build <= 15 min on 4 cores (vectorised or compiled IMA
encoders; the 1,194 s of duplicated music conversion is free to drop).

**Phase 1a status (2026-09-29): Sources, P1 `disc`, P2 `tables` done** (SPEC.md section 27 has the details).
- `tools/xml1build/sources.py`: `Sources` (developer mode = the repo's folders; prepared mode = the cache, with
  research-relative overrides) in `BuildContext` (`ctx.sources`, `ctx.research_path`); x1names reads the Sources'
  collisions.json; `build_xml1.py --sources prepared --cache DIR [--iso IMAGE]` (exit 3 = input not usable) writes
  `_build/sources.json`. Developer mode is byte-for-byte the old behaviour (`tools/build_equiv.py`: 21,379 files +
  12 `_build` JSON files identical).
- P1 (`prepare/image.py`, `xbe.py`, `fb.py`, `disc.py`): Redump / XGD2 / XGD3 / XISO by content, the rejections of
  1.1 (`E_ISO_COMPRESSED`, `E_ISO_NOT_XBOX` + detected, `E_ISO_WRONG_GAME`, `E_ISO_INCOMPLETE`, `E_ISO_READ`,
  `E_ISO_FOLDER`), SubFile + zip streaming, fb_unpack's rules (its glob ran on Windows: bundles sorted with `\`
  separators). **17 s** on Owen's dump; 8,787 files byte-identical to `xml1_loose` / `xml1_assets` / `xml1_xbox`, the
  918 files only in the hand-made trees all explained (`tools/prepare_equiv.py`). (1a deviation from 1.1 - P1
  always copied `movies/ntsc` - resolved in 1b.)
- P2 (`prepare/tables.py`): mission_plan (+ the 10 mission texts), collisions, x2_stats_refs byte-identical to the
  research copies; names_xml1 identical except 11 of its 22 ELF-hash-ambiguous keys (the generator's choice depended
  on PYTHONHASHSEED; P2 takes sorted order; no `character/` name among them, so P4's aliases cannot change).
  **25-46 s**.
- A prepared `--no-movies` build is file for file identical to the developer build (roots mapped).
- `tests/unit` (19 synthetic tests, `python tests/unit/run.py`), `tools/prepare_xml1.py`, `tools/prepare_equiv.py`.

**Phase 1b status (2026-09-29): P3 `scripts`, P4 `sound`, P5 `music` done - phase 1 is done** (SPEC.md 27.5-27.12).
- P3 (`prepare/scripts.py`): rewrite_scripts ported as a `Rewriter` (NTFS walk order on any file system, no D:/ paths,
  no import-time work); research/scripts/out (1,846 files) and both reports byte-identical; 8 s.
- P4 (`prepare/sound.py`): convert_zsnd `--batch --encoder auto --rekey character/=char/` with P2's names passed
  explicitly + merge_all; P5 (`prepare/music.py`): fix_music with parameterised roots, every bank accepted by
  `media_music.check_bank` (not by hashes: fact 2 below). All 295 banks + the three reports identical to
  `build/_snd_final` at 16, 8 and 4 jobs. **The 61 music banks stay in P4** (the planner and media's structure
  check use the 1:1 banks as the reference; ~35 CPU-s and 371 MB). Worker pools are **memory-budgeted**: a P5
  worker peaks at up to 2.7 GB and 16 of them exhausted a 32 GB PC.
- Prepared mode: every research output comes from the cache (overrides `scripts/out`, `sound/out`,
  `sound/music0x20`); a missing or failing music bank is an error, never a research/ fallback; `StageFailed` = exit 1.
- **Movies follow the build's option**: a `--no-movies` P1 leaves `movies/ntsc` out and the movie providers read
  `movies.json` (1.1); a later movies build adds the files to the cached disc.
- **Full equivalence** (`build_equiv.py`, roots mapped): first prepared build from the ISO vs developer build,
  movies on: 21,427 files (4.82 GB) + 13 `_build` JSON identical; `--no-movies` (P1 without the movie files):
  21,379 + 12 identical; developer mode unchanged by the 1b code (21,379 + 12).
- Self-tests read their inputs through `Sources.for_out`; characters_selftest K follows SPEC 18.1; all eleven pass
  on a developer and a prepared build. The research generators the stages replaced are wrappers or carry a
  `SUPERSEDED` note (SPEC 27.7). `tests/unit`: 24 tests.
- **Timings (Owen's PC, 8 jobs)**: first build from the ISO with an empty cache **5 min 32 s** (prepare 3.0 min,
  of which P5 93 s; 5 min 24 s with `--no-movies`); warm rebuild 83-107 s; developer build 2.6 min.
- Left for later (phase 2+): the cache lock, `known_*.json`, no `media_cache` snapshot in builder mode, moving the
  sound research modules and `fix_music.py` into `xml1build/lib/`, the graph.json strip / zones.json warning /
  console_senders / `ctx.collisions` items of the phase-1 row (SPEC 27.12).

**Equivalence is the acceptance test.** Owen's PC has both worlds: the prepared outputs from the ISO must be
byte-identical to today's `research/**/out` and `music0x20/banks` (24 `all_ima` banks came from an earlier run and
may need regenerating once to become the reference), and a builder build must register the same files with the
same sha1 as `build_xml1.py` from the research outputs.

**Phase 1p status (2026-09-29): done.** Two steps, both byte-identical for the whole disc: numpy codecs
(`research/sound/adpcm_np.py`, merged f5b52c2), then an optional compiled kernel (`research/sound/ima_kernel.c`,
Owen approved) that the sound stages use when it is built. The sound stages now take under 2 minutes on 4 jobs.

| Sound stages, whole disc (convert `--encoder auto` + merge + fix_music), Owen's PC (Ryzen 7 5700X, 8 cores / 16 threads) | 16 jobs wall | 16 jobs CPU | 4 jobs wall | 4 jobs CPU |
|---|---|---|---|---|
| pure Python (before 1p) | 3,002 s | 15,980 s | 3,512 s | 10,654 s |
| numpy (f5b52c2), at merge | 663 s | 6,585 s | 818 s | 3,206 s |
| numpy, re-measured with the kernel runs (quiet PC) | 651 s | 6,798 s | 689 s | 2,681 s |
| **compiled kernel** | **85.5 s** | **821 s** | **108.5 s** | **407 s** |

Kernel per stage, 4 jobs: convert 22.0 s, merge 1.5 s, fix_music 85.0 s (16 jobs: 18.8 / 1.6 / 65.1 s; there
fix_music is throughput-bound on the 16 hyperthreads: the sum of the bank times / 16 is the wall time). With P1-P3 and the pipeline
(~6 min) the first build is ~8 min on 4 cores: the 15-min target is met.

How it works (`research/sound/adpcm.py` docstring, `adpcm_c.py`, `ima_kernel.c`):
- `ima_kernel.c` is plain C99 (no Python C-API): the greedy encoder, the 4x3 beam encoder (`encode_beam`), fix_music's
  64-wide weighted beam (`beam_window`) and the Xbox / PC decoders (with the encoders native, the numpy PC decoder
  that verifies every converted bank was 28% of a convert). `research/sound/adpcm_c.py` calls it with ctypes and
  offers `adpcm_np`'s entry points (`encode_streams`, `solve_chains`, `run_lanes`, `xbox_decode_np`, `pc_decode_np`).
- `adpcm.codec()` is the backend of `convert_zsnd`, `fix_music` and `adpcm`'s public codecs: `adpcm_c` when the
  library loads, was built from the current `ima_kernel.c` (its source sha1 is compiled in) and passes a self-check
  on synthetic audio against `adpcm_np` and the pure-Python references (0.4 s per process); else `adpcm_np`,
  unchanged. The stages log `sound codec: ...` (which backend, and why not the kernel), every bank report carries
  `"codec": "kernel"|"numpy"` (`sound_equiv` ignores it), `XML1_SOUND_KERNEL=off` forces numpy and a path in it
  names the library.
- The C boundary: whole streams per call - a convert job is one call per file channel, fix_music runs each channel's
  chain sequentially (one call per body stretch, one per seam window) - so the numpy path's speculative lanes are
  not needed. What stays in numpy is `np.argpartition` in the wide beam: its order of tied elements is numpy's (see
  (2) below), so `ima_wide` calls back into Python for it, but only when that order can change the result - a tie
  at the 64/65 boundary (the survivor set), or a tie that the survivors' order decides at the next sample or at the
  end (then that sample's full candidate list is rebuilt, sorted into key order, handed to `np.argpartition`, and
  the next sample recomputed): ~6% of the wide-beam samples. The rest skip the numpy call and most candidates (a
  slot's errors fall and rise with the rank, so only candidates under a bound on the 65th smallest error are
  expanded). Speeds: wide beam 8 us/sample (numpy lanes 69, pure Python ~105), beam4 0.13, greedy 0.02.
- So fact (2) below holds unchanged: the kernel reproduces the numpy path on the same numpy build + CPU class.

Equivalence evidence: `tools/sound_equiv.py build/_snd_final <run>` = 295 banks + 3 reports identical for the kernel
at 16 and at 4 jobs and on the final source, and for the numpy path through the rewired callers at 16 and 4 jobs.
`tools/xml1build/sound_selftest.py` passes with the kernel (`--require-kernel`) and with `XML1_SOUND_KERNEL=off`:
S1-S6 numpy vs pure Python, K0-K6 kernel vs pure Python and numpy (decoders; greedy / beam4 on real and edge-case
streams; the wide beam, lazy and eager, on 160 seam windows; `solve_chains`' unit merging; `fix_music.encode` /
`auto_holds`; whole `convert_zsnd` banks kernel vs numpy).

Building it: `python tools/build_sound_kernel.py` - MSVC (vswhere + vcvarsall, or `cl` already on PATH) for the
running Python's platform: `build/native/ima_kernel-win_amd64.dll` (a 32-bit Python gets `-win32`; the source also
compiles for x86, /W4-clean), `cc` elsewhere (`.so`). `build/` is gitignored: never commit the binary. No FMA
contraction (`/fp:precise` without `/arch:AVX2`, `-ffp-contract=off`): the wide beam's double arithmetic must match
numpy's operation for operation. The script ends with the loader's self-check (exit 1 if it fails).

CI (the builder's release workflow, a `windows-latest` job - it has Visual Studio with the C++ tools):
```yaml
      - uses: actions/setup-python@v5
        with: { python-version: '3.13', architecture: x64 }   # the Python the builder is frozen with
      - run: python -m pip install numpy==<the pinned version>
      - run: python tools/build_sound_kernel.py               # build/native/ima_kernel-win_amd64.dll + self-check
      # freeze: pyinstaller ... --add-binary "build/native/ima_kernel-win_amd64.dll;."   (adpcm_c also looks next to itself)
```
The self-check needs no game data, so it is the kernel's CI test too (6.1). Without the DLL a build still works
(numpy path, 6-8x slower sound stages).
Two facts for this acceptance test: (1) 21 of the 216 `all_ima` banks in `research/sound/out` (music `_a`/`_c`)
are the earlier run and differ from what the current code makes - the fixed music banks replace them in builds;
(2) `fix_music.beam_window` keeps its beam in `np.argpartition` order and ties decide which paths survive (in
almost every seam window); numpy leaves the order of tied elements undefined and picks its partition kernel by
CPU (X86_V3 here, AVX-512 elsewhere), so the fixed music banks are only reproducible byte for byte with the same
numpy build on the same class of CPU. On users' PCs accept the music banks with `media_music.check_bank`, not with
hashes.

---------------------------------------------------------------------------------------------------------------

## 2. The builder CLI contract

Name: **`xml1-builder`** (`xml1-builder.exe` frozen; `python -m xml1builder` from source). It wraps the existing
pipeline (`build_xml1.main` and the modules); `tools/build_xml1.py` stays the developer entry point with every
test/A-B flag. The builder exposes one **profile**, the play build Owen verified (`build/_heroes`): every
`CONTENT_OPTS` default (`--frontend xml1 --forced-teams seat --newgame keepteam --xp-curve xml1 --tiles used
--hero-roster 21 ...`), no test hooks, no `--test-ini`. Movies are the only content switch.

### 2.1 Commands

```
xml1-builder info    --iso PATH [--xml2 DIR] [--out DIR] [--cache DIR]
xml1-builder build   --iso PATH --xml2 DIR --out DIR [--movies | --no-movies] [--cache DIR]
                     [--keep-cache | --drop-cache] [--link-base] [--jobs N] [--no-ini] [--allow-unknown-exe]
xml1-builder verify  --out DIR [--iso PATH] [--xml2 DIR] [--deep]
xml1-builder clean   --out DIR [--mods] [--cache DIR] [--dry-run]
xml1-builder --version
global: [--events jsonl] [--log FILE] [--quiet]
```

| Command | Does | Writes |
|---|---|---|
| `info` | Identifies the ISO (format, title, known dump), the XML2 install (exe known, language, base files by name + size), space estimates, the cache state, and - with `--out` - the state of an existing build (2.7). Fast (a few seconds: no hashing beyond `XMen2.exe` and `default.xbe`; `testzip` and base hashing only with `--deep`). | nothing |
| `build` | Probe -> prepare (cached) -> sync -> content modules -> sweep -> validate -> ini -> stamp. Idempotent: re-running into the same `<out>` is the rebuild and the resume. | `<out>`, the cache |
| `verify` | Reads the stamp; re-hashes every registered file against `_build/registry.json` (the builder adds `sha1` to each registry entry) and the base files against the base manifest; with `--iso/--xml2` also compares input fingerprints; `--deep` re-runs the validator and hashes the ISO. Reports `current / stale / damaged / incomplete / foreign / absent` + reasons. | nothing |
| `clean` | Uninstall helper: deletes exactly what the builder made in `<out>` (registry entries + synced base files + `_build/`), leaves `dinput.dll`/`xml2-fix.*` to the launcher, `mods/` unless `--mods`, never saves; removes empty dirs; refuses a folder the builder didn't make (no `_build/` with a builder `stamp.json` or `building.json`). `--cache` deletes the cache for this disc. | deletes |

### 2.2 Exit codes

Compatible with `build_xml1.py` (0 / 1 / 2) and extended:

| Code | Meaning | Launcher reaction |
|---|---|---|
| 0 | success (warnings allowed) | continue (install the DLL, Play) |
| 1 | build failed: a module failed or the validator found errors (our bug) | "Build failed - please report" + log |
| 2 | usage error or refused (`E_OUT_UNSAFE`, `E_OUT_FOREIGN`: non-empty folder the builder didn't make) | show message, let the user pick another folder |
| 3 | input not usable (`E_ISO_*`, `E_XML2_*`) | show message + hint, back to the input step |
| 4 | not enough disk space (`E_SPACE`) | show sizes |
| 5 | cancelled | back to the game page; "Resume build" |
| 6 | I/O error (read error on the image, write/permission error, file locked - e.g. the port is running) | show message + retry |
| 70 | internal error (unexpected exception; traceback in the log) | "Build failed - please report" |

### 2.3 Events: JSON lines on stdout (`--events jsonl`)

With `--events jsonl`, stdout carries **only** events, one JSON object per line, UTF-8, flushed per line; human
text goes to stderr and the log. Without it the builder prints the human text (today's `[module] ...` lines) to
stdout. Every event has `ev` and `t` (ms since start). Schema version 1:

```json
{"ev":"hello","v":1,"t":0,"builder":"1.0.0","content_version":3,"commit":"abc1234","pid":4242}
{"ev":"plan","t":40,"stages":[{"id":"probe","title":"Checking your files","weight":1,"cached":false},
                              {"id":"extract","title":"Reading the disc","weight":6,"cached":true}, "..."]}
{"ev":"stage","t":52,"id":"extract","state":"start"}
{"ev":"progress","t":900,"stage":"extract","done":512,"total":1888,"unit":"files","pct":27.1,"overall":8.4,"eta_s":1310}
{"ev":"log","t":950,"level":"info","stage":"zones","msg":"198 zones converted"}
{"ev":"warning","t":960,"stage":"content","code":"W_PIPELINE","msg":"142 warnings (...)","detail":{"count":142},"count":142}
{"ev":"stage","t":1200,"id":"extract","state":"done","seconds":1.1}
{"ev":"error","t":5000,"stage":"probe","code":"E_ISO_WRONG_GAME","msg":"...","hint":"...","detail":{"title_id":"0x...","title":"..."}}
{"ev":"result","t":1400000,"ok":true,"exit":0,"out":"C:/Games/X-Men Legends (Port)",
 "report":".../_build/report.json","log":".../_build/builder.log","errors":0,"warnings":204,
 "stamp":{"...": "section 2.8"},"seconds":1400}
```

- `plan` is emitted once the probe knows which stages are cached, so `overall` is honest on a warm rebuild.
  Weights come from measured seconds (1.5) and are recalibrated per release from CI timing logs.
- `progress` is rate-limited to ~4 per second per stage. Sources: files done / total for extract, sync and
  sweep; banks done / total for the sound stages; the ctx write count against the previous build's registry count
  for the content modules (the registry of the last good build, else a shipped estimate: 8,065 files).
- Pipeline warnings (130 in zones, 73 in validate on the play build) are **not** streamed one by one; the builder
  emits a count per stage at stage end and the full text stays in `report.json`/the log. Errors are streamed.
- `code` strings are stable (the launcher translates them); `msg` is English fallback text. Every warning carries
  its count as data in `detail.count` (files, pipeline warnings; 1 for a single fact), not only in `msg`.
- Every string of every event, and every human / log line, has the user profile folder masked as `%USERPROFILE%`
  (`events.mask`, one helper: any case, either separator, doubled backslashes).
- The launcher treats a non-JSON stdout line as a `log` line (robustness against a stray `print`); the builder
  redirects `sys.stdout` to stderr for the pipeline's own prints while in `jsonl` mode, so this should not happen.

### 2.4 Logs

- `<out>/_build/builder.log` - everything (the human stream, timings, full warnings, tracebacks), rotated per run
  (`builder.log`, `builder.1.log`, 3 kept). Until `<out>` exists (probe errors), the log is `--log` or
  `<cache>/logs/builder-<timestamp>.log`.
- The existing `_build/report.json`, `registry.json`, `validate.json`, `*_detail.json` stay.
- The log header records builder version, commit, Python version, OS build, CPU count, free space, the input
  fingerprints and the command line with the user profile path masked as `%USERPROFILE%`.

### 2.5 Cancellation

- In `jsonl` mode a thread reads stdin: a line `cancel` (or EOF: the launcher went away) sets a cancel flag; from a
  console, Ctrl+C takes the same path (`KeyboardInterrupt` -> cancel). The launcher also creates the
  process in a **job object** with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so a crashed or closed launcher never leaves
  a builder or its worker processes behind.
- Checkpoints: every `ctx.write_*` / `ctx.copy_file` / sync file / extract member / sound bank checks the flag
  (these run thousands of times per stage, so latency is well under a second); process pools (`media` uses
  `ProcessPoolExecutor`; the sound stages will) are shut down with `cancel_futures=True` and their workers
  terminated.
- On cancel the builder writes no stamp, leaves `_build/building.json` (so the state reads `incomplete`), emits
  `result` with `exit 5`. The launcher kills the job object if the builder has not exited 15 s after `cancel`.
- Cancel is safe at any point: every file write is atomic (temp + `os.replace`), cache stages publish their output
  by renaming a `.partial` directory, and a re-run sweeps leftover `*.tmp<pid>_<tid>` files (they are unregistered).

### 2.6 Idempotent re-runs, locking, the cache

- **Re-runs.** `build_xml1` is already built for rebuilding into the same `<out>`: `sync_base` copies only files
  whose size or mtime differ and restores base files a previous build replaced; the content modules rewrite their
  outputs; `sweep_stale` removes what is no longer registered. The builder keeps that and adds: F3 (keep
  `PROXY_PATTERNS`), a `_build/lock` (exclusive create, holds the pid; a stale lock whose pid is gone is taken
  over), and `building.json` -> `stamp.json` at the end.
- **Foreign folders.** `check_out_dir`'s rule stays: an empty folder or one with `_build/` is accepted; anything
  else is `E_OUT_FOREIGN` (`--adopt` is not offered in the builder: its sweep deletes non-base files).
- **Cache location.** `--cache DIR`; the launcher passes `%LOCALAPPDATA%\ultimate-legends\cache\xml1`; standalone
  default `%LOCALAPPDATA%\xml1-builder\cache`. Layout:
  `cache/<disc_id>/disc/` (loose tree, assets, movies, zsds; disc_id = first 12 hex of the xbe md5 + assets CRC
  digest), `cache/<disc_id>/prepared/<stage>-<stage_version>-<inputs_digest>/` (scripts out, sound out, music),
  `cache/logs/`, `cache/lock`. Each stage directory has `stage.json` (inputs digest, stage version, seconds,
  counts). A stage is reused only when its key matches; stale stage directories are deleted when a new one
  completes.
- **Keep or drop.** Default **keep** (the launcher shows "Build cache: 2.8 GB [Free up]"): it turns a builder update
  into a ~5-minute rebuild instead of a full first build, and lets the user delete or unmount the ISO after the first
  build. `--drop-cache` deletes the disc and prepared directories after a successful build. (Q5.)

### 2.7 Rebuild detection

`info --out` / `verify --out` compute a state from `_build/stamp.json`, `_build/building.json` and the inputs:

| State | Condition | Launcher shows |
|---|---|---|
| `absent` | the folder is missing, empty, or holds only the launcher's / player's files (`dinput.dll`, `xml2-fix.*`, `mods/`) | Set up |
| `foreign` | files but no `_build/` from the builder | Choose another folder |
| `incomplete` | `building.json` present, or no stamp | Resume build |
| `stale` | stamp `content_version` < builder's, or the profile differs, or `--iso`/`--xml2` fingerprints differ | Update available (rebuild) |
| `damaged` | (`verify` only) a registered or base file is missing or its sha1 differs | Repair (rebuild) |
| `current` | none of the above | Play |

`content_version` is an integer the release bumps **only when the output would change** (a pipeline change), not
for CLI-only releases, so a builder update does not always cost a rebuild.

### 2.8 The stamp (`<out>/_build/stamp.json`, written last, atomically)

```json
{"format": 1,
 "builder": {"version": "1.0.0", "commit": "abc1234", "content_version": 3},
 "profile": {"movies": true, "frontend": "xml1", "forced_teams": "seat", "newgame": "keepteam",
             "xp_curve": "xml1", "tiles": "used", "hero_roster": "21", "hero_icons": "xml1", "hero_bleed": "on",
             "blackbird": "menu", "npc_scaling": "off"},
 "inputs": {"disc": {"format": "redump-xgd1", "title_id": "0x4156001E", "xbe_md5": "1e1a766a...",
                     "assets_zip_digest": "...", "known": "xml1-world-v1"},
            "xml2": {"exe_md5": "b34f0baf...", "base_digest": "...", "base_files": 13382, "modified": []}},
 "requires": {"xml2fix": ">=1.2.0",
              "ini": {"Game": {"NewGameTeam": "wolverine", "...": "..."}, "Limits": {"ActorSlots": "127", "ResourceNames": "1024"}}},
 "outputs": {"files": 8065, "bytes": 4512345678, "registry_sha1": "..."},
 "result": {"errors": 0, "warnings": 204, "seconds": 1400},
 "finished": "2026-10-10T20:15:00Z"}
```

The launcher reads `requires.xml2fix` and compares it with the installed `dinput.dll`'s file version
(`GetFileVersionInfoW`; xml2-fix has a `VERSIONINFO` from CMake, `src/version.rc`).

### 2.9 Phase 2 status (2026-09-29): the builder CLI is done (branch `builder-cli`)

`tools/xml1builder/` (`python -m xml1builder` from `tools/`, or `python tools/xml1builder`; module map in its
`__init__.py`). The protocol is the launcher's fake builder's (ultimate-legends `xml1-entry`,
`tools/dev/fake_xml1_builder.py`), which follows 2.1-2.8; where the design and the fake disagreed the fake won (below).

- **Pipeline side** (`builder_mode` in `xml1build.common`, off for `build_xml1.py`, which is unchanged): the proxy
  files stay (out index, sweep, V1 - F3); `write_bytes` records the sha1 of what it wrote in the registry; media
  installs P5's banks straight from the cache (no 372 MB `media_cache/music_fixed` snapshot); `common.set_checkpoint`
  is the builder's hook on every `ctx.log` line and every registered write (cancel, progress, the write journal).
  `xml1build/fix_ini.py` holds the port's ini keys; `harness.py` takes its `[Game]`/`[Limits]`/`[Online]` lines from it
  (294,912 argument combinations byte-identical before/after).
- **Integrity** (beyond 2.1): the sync reads every copied base file back against its source's sha1; the last stage
  (`finish`) reads every file of the build back against its expected sha1 (the XML2 source, the recorded sha1, or the
  source of a module's copy) on 8 threads - a copy that differs is copied again, a written file that differs or is gone
  is `E_IO` naming it - and writes `_build/manifest.json` (every file: size, sha1, kind base/built). Reading each file
  back right after writing it instead made the content modules 2-4x slower (an antivirus scan per reopen).
  `verify` re-hashes everything and reports groups (`missing`, `changed` with expected vs found size + sha1,
  `unreadable`, `extra`, `xml2_changed` with `--xml2`, `xml2_not_retail` from the stamp, `disc_unknown` /
  `disc_damaged` / `disc_changed` with `--iso [--deep]`), each with a `cause_hint`; `_build/verify-report.json` (relative
  paths, sizes, hashes, versions, codes - no content) is written by every build and every verify.
- **Repair = rebuild**: `build` over a damaged or interrupted folder reuses the cache and re-runs every content module;
  the sync re-copies what differs by size / time, the final read-back what differs by content (measured: a deleted
  XMLB + a flipped IGB byte + a stray file, 90 s, then `verify` current).
- **Cancel**: stdin is polled (`PeekNamedPipe`), never read with a blocking `ReadFile`: a pending read on the stdin pipe
  made `GetFileType` block, and numpy's OpenBLAS DLL calls it at load under the loader lock - the first builder hung
  there. Measured: exit 0.7 s after `cancel` in P5 (the pool terminated, no worker left), 4.8 s in the content modules;
  a 10 s watchdog hard-stops anything slower (result `exit 5`, locks released, `building.json` kept).
- **Measured on Owen's PC** (Ryzen 7 5700X, 32 GB): first build from the ISO, movies on, empty cache **6.1 min**
  (P1 17 s, P2 40 s, P3 8 s, P4 24 s, P5 133 s under a 6 GB memory budget, sync 28 s, content 70 s, validate 35 s,
  finish 10 s); rebuild with a warm cache, no movies, 90-103 s; `verify` 8-10 s (21,318 files); `info` 1.5-5 s.
- **Equivalence**: builder output (no movies) vs `build_xml1.py --sources prepared --no-movies` from the same cache
  (`tools/build_equiv.py`): all 21,318 files outside `_build` (3.29 GB) byte-identical; `_build` differs only where
  builder mode means to (no `media_cache/music_fixed`, music sources = P5's directory, registry `sha1`, V1 allowlists
  the ini, the builder's `manifest.json` / `stamp.json` / `verify-report.json` / `report.json` block; the known
  rebuild difference of `scripts_detail.json` `popup_dialog_sources`, SPEC 27.8).
- **Launcher**: its `xml1_cdp.py` ran against the real builder (the builder package the test publishes carried an
  adapter that runs the real builder and swaps the test's stand-in XML2 / X-Men Legends images for the real ones,
  read only; timeouts raised for real builds; Play / Stop / launch-refusal skipped because the build holds the real
  game): tool install, disc check (PS2 / CSO / missing), estimate and space, plan / progress / hide / cancel ->
  incomplete -> resume (all prepare stages cached), XML2 Fix + stamp + ini (builder keys next to the launcher's
  Display / Discord), update 1.0.0 -> 1.1.0 (content 3 -> 4) and pruning, Verify -> damaged -> Repair, Free up, and
  uninstall (game gone, mods kept) all pass. What differs is the fake's own test fixtures: its "other title" image is
  not a real XDVDFS (the real builder says `E_ISO_NOT_XBOX`, not `E_ISO_WRONG_GAME`), and its `fail_stage` /
  `ignore_cancel` knobs have no real equivalent (the real build succeeds; the real cancel exits in ~1 s instead of
  being killed after 15 s).
- **Held files and I/O errors** (fixes after that run; the launcher's `xml1_cdp.py --real` found them). One rule:
  - *A file the build did not make* (a stray, an old output) that the sweep can't delete because another program
    has it open **stays, and the build succeeds** (exit 0) with `W_EXTRA_FILES` naming it: `msg` "1 file(s) in the
    game folders that the build did not make (first: Data/x.txt): the rebuild could not remove it because another
    program has it open", `detail {files, count, not_removed, cause}`. This is what the fake does and what the
    launcher's text says ("They were left as they are"): the game does not need the file gone, and failing would
    leave the player unable to finish a repair over a file that is not part of the game. The validator's V2 allows
    exactly those files in builder mode (`ctx.shared['sweep_kept']`, from `sweep_stale(failed=)`; before, V2 failed
    the build as `E_VALIDATE` "a bug in the builder"); `verify` then lists them as `extra` (state stays `current`);
    the next rebuild after the program lets go removes them.
  - *A file the build must write, replace, read or restore* that another program holds open, or a full / failing /
    write-protected / removed drive, is **`E_IO` (exit 6)** wherever it happens (probe, prepare, sync, a content
    module, the validator, finish; also when a stage or module wrapped the `OSError`): `msg` "A file could not be
    read or written: Actors/14001.IGB (another program has it open).", `detail {path, where, cause, errno,
    winerror}` - `path` relative to the game folder (`where: out`; `cache` / `xml2` files say "(in the build cache)" /
    "(in X-Men Legends II's folder)"), `cause` one of `held`, `read_only`, `denied`, `disk_full`, `drive_read_only`,
    `disk_error`, `drive_gone`, `too_long` (`other` for an OSError reaching the builder directly without a known
    cause), a hint per cause. A content module that hits one stops the build at once (before: every later module
    ran, then `E_PIPELINE` "step characters"). A module's other exceptions stay `E_PIPELINE` (our bug).
  - Measured on the real `--no-movies` build (warm `build/_p1_cache`, a scratch folder, the file held with a Python
    file handle in a child process): a held stray -> exit 0 in 112 s, `W_EXTRA_FILES` `cause: held`, V2 ok with the
    file allowlisted; a held `Actors/14001.IGB` (the first registered written file, the launcher test's victim) ->
    exit 6 after 11 s, `E_IO` `stage: content`, `cause: held` (WinError 5 from the replace).
  - Also fixed: `info --out` / `verify --out` call a folder holding only the launcher's / the player's files
    (`dinput.dll`, `xml2-fix.*`, `mods/`, and a `_build/` without a builder marker) `absent`, the rule `build` uses to
    accept it (`stamp.out_state`, one rule for all three; before, info said `foreign`); every event string and
    human / log line is masked (`E_ISO_NOT_FOUND`'s text carried the unmasked profile path); every warning has
    `detail.count`.
  - **For the launcher** (branch `xml1-entry`): the fake's docstring and destination rule ("which `info` still calls
    foreign, as the real one does") should now say `absent`; `xml1_cdp.py --real` can run the W_EXTRA_FILES-after-
    repair check instead of skipping it, and its failed-build check gets `E_IO` (exit 6) for a held written file;
    `xml1-port.js noticesOf` can take the count from `detail.count` instead of `parseInt(msg)`; `E_IO`'s
    `detail.path` / `detail.cause` can name the file in the error panel.
- **Deviations** (design -> builder, and builder vs the fake): `E_ISO_FOLDER` is reported as the fake's
  `E_ISO_NOT_XBOX` + `detected: folder`; new codes
  `E_CACHE_LOCKED` (2), `E_ISO_READ` / `E_CACHE_*` (3, from prepare), warnings `W_XML2_UNKNOWN_EXE`, `W_XML2_MODIFIED`,
  `W_EXTRA_FILES`, `W_LINK_BASE`; a failed prepare stage is `E_PIPELINE` with `detail.code` = `E_PREPARE_*`;
  `stamp.outputs.files/bytes` count the whole build (the fake: registered files only); `build` without `--iso` works
  when the cache holds the disc; a folder holding only the launcher's files (`dinput.dll`, `xml2-fix.*`, `mods/`) is
  accepted as a destination (and `info` / `verify` call it `absent`); `--link-base` is accepted but copies
  (`W_LINK_BASE`); `E_XML2_MODIFIED` is a warning; `E_IO` carries `detail.cause` (above).

---------------------------------------------------------------------------------------------------------------

## 3. Packaging

### 3.1 Runtime dependencies

- **Build (pipeline + prepare): the standard library + numpy.** numpy is imported by `media_music.py:37` (every
  build that runs `media`) and `tools/fix_music.py:54` (P5). Optional: the compiled sound kernel
  `ima_kernel-win_amd64.dll` (plain C, loaded with ctypes; built in CI, 1p status in 1.5) - without it the sound
  stages run the numpy path. No `audioop` anywhere (removed in 3.13), no scipy,
  soundfile or Pillow (Pillow is used only by the game-driving harness tools: `tour_runner`, `power_sweep`,
  `campaign_walk`, ...). No external programs (`ffmpeg` appears only in `research/sound/ffcheck.py`).
- Process/thread pools: `media.py:383` (`ProcessPoolExecutor`, worker `media_music.py:236` must stay picklable),
  `convert_zsnd.py:267` and `fix_music.py:821` (`multiprocessing`), thread pools in `characters.py:460`,
  `validate.py:1110,2689`.
- **Developer-only** (regenerating the shipped API tables, never in the builder): `pefile` (`binimg.py:37`,
  `sweep/script_table.py:30`), `capstone` (`dump_text.py:5`, the `.asm` listings).
- Harness / in-game test tools (not shipped in the builder): Pillow, the xml2-fix pipe.

### 3.2 Freezing: PyInstaller **onedir**, zipped

Recommendation: **PyInstaller, one-folder mode**, shipped as `xml1-builder-<ver>-win64.zip`
(`xml1-builder.exe` + `_internal/`), installed by the launcher into
`%LOCALAPPDATA%\ultimate-legends\tools\xml1-builder\<ver>\`.

| Option | For | Against |
|---|---|---|
| **PyInstaller onedir** (recommended) | Standard; fast start (the launcher calls `info` often); nothing unpacked to `%TEMP%` per run; `ProcessPoolExecutor` workers start quickly; fewer AV heuristics than onefile | Many files -> must ship as a zip (GitHub release assets are flat), so the launcher needs a zip install path (it already extracts zips with System32 `tar.exe` in `game_mods.cpp:204-233`) |
| PyInstaller onefile | One asset: fits `client_updater`'s flat `[name, size, sha1]` manifest with no launcher change except the target dir | Self-extracts ~50 MB into `%TEMP%` on every call (2-4 s per `info`); "unpacks and runs code" is the classic AV false-positive pattern |
| Nuitka | Native code, smaller | Long CI builds, C toolchain, numpy plugin quirks; no clear AV win |
| Embeddable CPython + zipapp | `python.exe` is the PSF's Authenticode-signed binary (best AV standing, no bootloader) | Not "an exe of ours"; numpy's extension modules must sit unzipped; more moving parts in the launcher |

Size estimate: CPython 3.12/3.13 runtime ~12 MB + numpy ~25-35 MB (OpenBLAS is most of it; exclude
`numpy.tests`, `f2py`) + our code and data ~5 MB -> **~45-55 MB unpacked, ~20 MB zipped**. `multiprocessing.freeze_support()`
must be the first call in `main` (frozen Windows + process pools).

Python version: the dev box runs **3.14.7** with numpy 2.5.3. Freeze with the newest CPython that the pinned
PyInstaller release officially supports (at worst 3.12/3.13), pinned in `requirements-freeze.txt`, and run the
unit tests on that exact version in CI.

### 3.3 Antivirus false positives and signing

Nothing is signed today (launcher CI: no signing step; xml2-fix releases unsigned). Plan:

1. No UPX; `--noupx`. Build the **PyInstaller bootloader from source** in CI (the prebuilt bootloader's hash is on
   many AV lists because malware ships it). Add a `VSVersionInfo` resource (product, company "Ultimate Legends
   community", file description, version) and an application manifest (`asInvoker`, long paths aware).
2. The builder makes **no network calls** (the launcher downloads; the builder only reads and writes local files).
3. Every release: submit `xml1-builder.exe` to the Microsoft Defender submission portal as "incorrectly detected"
   *before* announcing; publish SHA-256 sums in the release notes and in `xml1-builder.json`.
4. Signing: apply to **SignPath Foundation**'s free code signing for open-source projects once the repo is public
   (it signs CI-built artifacts from a public repo); the paid alternative is Azure Trusted Signing (identity
   validation required). Sign the launcher and xml2-fix's DLL through the same program. Open question Q6.

### 3.4 Windows only?

The release artifact is **Windows x64 only** (the launcher is Windows-only). The pipeline itself is pure Python +
numpy and path-portable, so keep it runnable from source on Linux (`python -m xml1builder`) - it costs nothing,
lets Steam Deck / Wine users build, and lets CI run the unit tests on Linux too. Rules: no `os.startfile`, no
drive-letter assumptions, case-insensitive lookups stay in `FileIndex` (already the case), `shutil.disk_usage`
for space.

### 3.5 xml2-fix's DLL: the launcher installs it; the builder owns the port's ini keys

**DLL: obtained by the launcher**, not bundled in the builder:

- The xml1 library entry reuses xml2's patch mechanism unchanged: `update_manifest_url = XML2_FIX_RELEASE
  "ultimate-legends.json"`, destination = the port folder. `verify-game` installs `dinput.dll`, and every Play
  re-checks it (`game_commands.cpp:279-290`).
- One copy of the DLL logic, updated independently of the builder (an xml2-fix fix does not need a rebuild), and
  the launcher's uninstall already knows how to remove exactly its files.
- Compatibility: the stamp's `requires.xml2fix` (>= 1.2.0) is checked against the installed DLL's file version;
  scripts already degrade safely without the DLL (every xml2-fix call is behind `xml2fixFeature`, SPEC 19.1).
- The builder never downloads it (no network calls, 3.3). Standalone users copy `dinput.dll` from the xml2-fix release
  into the port folder; the builder's final message says so.

**The ini: written by the builder** (move harness.py's play-build logic into the pipeline):

- New module `tools/xml1build/fix_ini.py`:
  - `port_keys(out) -> {'Game': {...}, 'Limits': {...}}` - the content requirements of *this build*:
    `NewGameTeam=wolverine`, `ResetUnlocks=0`, `SaveFolder=X-Men Legends` (`PLAY_SAVE_FOLDER`),
    `ForcedTeams=1` (only for a `--forced-teams seat` build), `PostgameScript=x1/menus/postgame` (only when the
    script exists), `MainMenuItems=button1..button7` (from `harness.build_menu_items`, i.e. the XML1 menu is in the
    build), `XPCurve=xml1` (from `harness.build_xp_curve`), `[Limits] ActorSlots=127 ResourceNames=1024`.
  - `merge_ini(path, sections, drop=())` - line-based merge with `WritePrivateProfileString` semantics: replaces or
    adds only these keys, keeps every other section, key, comment and the file's line endings; creates the file if
    missing. (Python's `configparser` would lower-case keys and drop comments; the launcher's display code already
    merges key by key with `WritePrivateProfileStringW`, `xml2_display.cpp:159-201`, so both writers coexist.)
- `harness.ini_text` / `install` keep their test options (`[Test]`, `[Online]`, `[Debug]`, modes) but take the
  port keys from `fix_ini.port_keys` so the harness and the shipped build cannot drift.
- The launcher owns only user preferences: `[Display]` (its Display section; for xml1 it writes Owen's play-build
  defaults `Mode=borderless`, `Width=0`, `Height=0`, `RunInBackground=1` at first setup), `[Discord] Enabled`
  (HANDOFF 21:00 decision), later `[Online]`, `[Input]`. Neither writer removes the other's keys. `[Test]` and
  `[Debug]` are never written for players (the play build's `InputPipe=0`/`LogFiles=0` are the defaults anyway).
- The same keys go into the stamp (`requires.ini`), so the launcher's `verify-game` can check them and restore a
  deleted or hand-edited ini without re-deriving anything. HANDOFF (f8dc2e2) records "launcher does ... xml2-fix
  install/ini": if Owen wants the launcher to be the only writer, it merges `requires.ini` from the stamp and the
  builder runs with `--no-ini` - the builder side is the same code either way (Q8).
- Why the builder: the keys are functions of the build's content (`build_menu_items` decodes `UI/menus/main.XMLB`,
  `build_xp_curve` reads `report.json`, PostgameScript checks a script file) - the builder knows them for free,
  the C++ launcher would have to re-derive them; standalone users get a correct ini; and a builder update that
  changes a requirement (a new key) ships with the content that needs it.

### 3.6 Phase 3 status (2026-09-29): the frozen builder, its release files and CI

Details and measurements: SPEC.md 27.13. In short:

- **Lib move** (1.5 "research modules"): done - `tools/xml1build/lib/` holds every research module the build imports
  (plus `fix_music`), no `sys.path` tricks, no machine paths; shims at the old places. Developer and prepared builds
  identical to before (21,379 files + 12 `_build` JSON each), eleven self-tests pass.
- **Freeze** (3.2): `tools/xml1builder/xml1-builder.spec` + `tools/freeze_builder.py` (+ `tools/freeze_smoke.py`),
  CPython **3.14.7** (PyInstaller 6.22.3 supports it; the "3.13" of the 1p CI snippet is superseded), numpy 2.5.3,
  `requirements-freeze.txt`. 0.1.0: **23.7 MB zip**, 55.7 MB unpacked (the 3.2 estimate held), 120 files; `--version`
  0.12-0.14 s warm, 0.3-0.6 s on the first start after unpacking; `info` 4 s.
- **Release files** (4.5): `xml1-builder-<ver>-win64.zip` + `xml1-builder.json` exactly as the launcher's
  `tool_install::parse_manifest` reads them (`min_launcher` 0.0.0 until a launcher release carries the xml1 entry) +
  `SHA256SUMS.txt`. The parser also takes an optional `url`; not written (the zip sits next to the manifest).
- **Frozen end to end** on Owen's PC, from outside the repo with no Python on PATH: build from the cache 127-140 s,
  first build from the ISO with an empty cache **7.2 min** (`--no-movies`, 16 jobs; P5 157 s); both byte-identical to
  a python-run builder build (21,319 files); the kernel loads from the bundle; the worker pools (P4, P5, media) run
  frozen; the XML2 install and the disc image folder unchanged.
- **Game text** (5.2): the release carries graph.json and zones.json packaged without their text fields (the Find-Gambit
  derivation takes mission texts from the disc's mission plan instead); the freeze stops if the content guard finds
  anything in the bundled data.
- **CI** (6, 6.1): `.github/workflows/{content-guard,tests,release}.yml` (actionlint clean), written here, running
  once exported. The bootloader-from-source step exists behind the release workflow's `bootloader` input (default:
  the wheel's) - switch it on for releases once it has been tried on a runner.
- **Handover to phase 5 (public repo)**: export `.github/`, `tools/check_no_game_content.py`, `.content-guard-allow`,
  `requirements*.txt`, the spec and freeze scripts with the curated tree; the guard over this private repo
  (`--all`, 577 tracked files) reports 1,099 errors + 1 warning in 104 files (`build/_p3_content_guard.txt`) -
  none in phase-3 files. Most are 5.3's SCRUB / REVIEW list (decoded dumps and `verify/` text files,
  `mission_plan.json` + its `rerun` copy, `graph.json` / `zones.json` / `inventory.json` text, the screenshots,
  HANDOFF / notes / `newgame_test.sh` personal data); new since 5.3: the WSL IP in `research/online/*.md` (3 files),
  user paths in `research/characters/skins.md`, `research/campaign/late_game_test.md` and 5.3's own lines, six more
  research `.txt` logs (`sound/music0x20/batch*_log.txt`, `sound/verify/*result*.txt`, two zone_coverage files,
  `characters/combat_compat.txt`), and in the unit tests a LAN-style IP (`test_builder_parts.py:205,218`, use
  192.0.2.x) and one XML attribute (`test_sources_tables.py:119`);
  the public copies of graph.json / zones.json need the same packaging the release got (or regeneration), and
  `mission_plan.json` must not ship (P2 makes it; developer mode would then need `research/` regenerated locally).
  Set `MIN_LAUNCHER` when the launcher release is known; submit the first zip to Defender before announcing (3.3).
- **Handover to phase 6 (clean machine)**: install the zip through the released launcher on a fresh Windows account
  with no Python; first build from the ISO (movies on and off), `verify`, play; check the `sound codec:` log line says
  the kernel (else the numpy path: 6-8x slower sound stages) and the stage times against 27.13; watch memory on an
  8-16 GB PC (P5's budget); Defender / SmartScreen reaction to the unsigned exe and the prebuilt bootloader.

---------------------------------------------------------------------------------------------------------------

## 4. Launcher integration

### 4.1 What exists (ultimate-legends)

- JS -> C++: `window.executeCommand(cmd, data)` -> `POST http://ultimate-legends/command`, handlers run
  synchronously on the CEF IO thread (`cef_ui_scheme_handler.cpp:405-475`); long work goes to detached threads.
- Progress is **polled** (`get-update-progress` every 100 ms; mod import: a per-game job struct polled by
  `get-mod-import` every 300 ms, `mod_commands.cpp:18-27`, `mods-view.js:261-267`). No C++ -> JS event bus.
- No code reads a child's stdout today (no `CreatePipe`); precedents: `tar.exe` with exit code only, and the
  redist worker's JSON lines over a named pipe.
- `client_updater` writes only into a game's install path, keeps whole files in memory, checks size + SHA-1,
  always takes `releases/latest`.
- The JS registry already has `xml1` (`utils.js:113-129`, `comingSoon: true`, accent `#FF4D63`, art in
  `assets/img/games/xml1/`); there is **no C++ `xml1` entry**.
- Optional game-page sections use `XView.supports(id)/render(id)` (`views.js:1032-1060`): `DisplayView` (xml2,
  branch `display-settings` only), `ModsView` (mua, mua2, xml2).

### 4.2 New launcher pieces

| Piece | Where | What |
|---|---|---|
| Running check by path | `game_commands.cpp` | F5: compare `QueryFullProcessImageNameW` with `<install>\XMen2.exe` for xml1 and xml2. **Prerequisite.** |
| `xml1` C++ entry | `game_config.cpp` | `exe_name XMen2.exe`, `update_manifest_url XML2_FIX_RELEASE "ultimate-legends.json"`, `valid_game_files {"XMen2.exe", "_build/stamp.json"}`, `check_running_exes {"XMen2.exe"}`, new field `built = true` (setup = build flow, not "point at a folder"). |
| Tool installer | `src/launcher/tools/tool_install.{hpp,cpp}` | Fetch `https://github.com/<owner>/<repo>/releases/latest/download/xml1-builder.json`; download the zip **streamed to disk** into `tools\.staging-*`; check SHA-256; extract with `tar.exe`; rename to `tools\xml1-builder\<ver>\`; keep the previous version until a build with the new one succeeds. |
| Builder job | `src/launcher/xml1/builder_job.{hpp,cpp}` | `CreateProcessW` (`CREATE_NO_WINDOW`, `STARTF_USESTDHANDLES`, stdin/stdout/stderr pipes, job object with kill-on-close); a reader thread parses JSON lines into a job struct `{active, stage, stages[], overall, eta, message, warnings, error_code, error_msg, result}` guarded by a mutex; stderr -> the launcher log. |
| Commands | `commands/xml1_commands.cpp` | `xml1-probe` (runs `info`, async + poll), `xml1-build-start {iso, out, movies, keep_cache}`, `get-xml1-build` (poll), `xml1-build-cancel` (writes `cancel`), `xml1-state` (`info --out`), `xml1-clean {mods, cache}`, `get-xml1-builder` (installed/latest version). |
| Properties | `property_keys.hpp` | `xml1-install`, `xml1-iso`, `xml1-movies`, `xml1-keep-cache`, `xml1-builder-version`. |
| UI | `app/xml1-setup.js` (wizard popup), `app/xml1-view.js` (`XView` section on the game page), `DisplayView`/`ModsView` `supports` += `xml1`, i18n `en` keys for every `E_*` code | Sonnet-scale pattern work. |

Everything polls, like mod import; no new push channel is needed. One build at a time (the job struct is
per-launcher); Play for xml1 is disabled while a build runs, and the build refuses to start while the port runs.

### 4.3 UX flow

1. **Library card** "X-Men Legends - Community port" (no longer `comingSoon`) -> **Set up**.
2. **Requirements** (one screen, live checks): *X-Men Legends II set up in the launcher* (tick / "Set up XML2
   first"), *Your X-Men Legends Xbox disc image* (`browse-file` with `*.iso;*.xiso`, plus a "How to make a disc
   image" link to the public docs), *Destination* (default `<parent of the XML2 folder>\X-Men Legends (Port)`,
   same volume as XML2), free space tick. A short bring-your-own-copy note.
3. **Disc check** (runs `info`): "X-Men Legends (Xbox) - recognised dump" or the error (`E_ISO_*` text + hint).
   Shows the time estimate ("first build: about N minutes on this PC", from CPU count and the stage weights).
4. **Options** (collapsed "Advanced"): Movies (on, +1.1 GB), Keep build cache (on, ~3 GB, "makes updates fast and
   lets you remove the disc image"), Save disk space with hard links (off).
5. **Building**: stage checklist from the `plan` event, overall bar + ETA, current message; [Cancel]; [Hide]
   (continues; the global progress bar shows it like a download).
6. **Finishing**: the existing `verify-game` installs `dinput.dll` (xml2-fix), the launcher writes the
   `[Display]` defaults, checks the DLL version against the stamp -> **Ready: [Play] [Open folder]**.
7. **Failure**: the translated `E_*` message; [Copy details] (builder version, stage, code, last 40 log lines,
   paths masked), [Open log], [Report on GitHub] (a prefilled issue URL; the user pastes the details).

**Game page** (`Xml1View`): state line from `xml1-state` (Up to date / Update available: rebuild ~5 min / Resume
build / Needs your disc image again - cache was removed), [Rebuild], [Open build log], cache size + [Free up].
Display and Mods sections as for XML2 (same DLL, same `<game>\mods` loader).

### 4.4 Where the game lives

A normal folder the user picks (default beside XML2, see 4.3). Never inside the XML2 install, the cache, or the
launcher's appdata (the builder refuses; `_check_out_safe` plus the cache root). Saves go to
`Documents\Activision\X-Men Legends` (`SaveFolder`), key bindings and display settings to XML2's registry key (F7).

### 4.5 Updates

- **Builder:** the tools repo's CI publishes `xml1-builder-<ver>-win64.zip` and `xml1-builder.json`
  (`{"version", "content_version", "zip", "size", "sha256", "min_launcher", "requires_xml2fix"}`) on a `v*` tag,
  the same shape of pipeline as xml2-fix's `build.yml` (`ultimate-legends.json`). The launcher checks it at start
  and on the game page. A new version installs silently; if its `content_version` is higher than the stamp's, the
  game page offers a rebuild (never automatic: it takes minutes and may need the ISO).
- **xml2-fix:** unchanged per-Play check through `client_updater`; if a new stamp needs a newer DLL than the
  latest release (should not happen if releases are ordered), the page says so.

### 4.6 Uninstall

Manage install -> Uninstall -> dialog with [x] Delete the built game (4.2 GB), [ ] Also delete mods in it,
[x] Delete the build cache (2.8 GB), and a note that saves in `Documents\Activision\X-Men Legends` are kept. The
launcher runs `xml1-builder clean --out <dir> [--mods] [--cache <dir>]` (deletes only what the registry, the base
manifest and `_build/` account for), then its existing `delete_client` removes `dinput.dll`, then `config.reset()`.
The launcher's rule "never deletes the game" holds for xml1 too: the builder is the only code that deletes build
output, and only its own files.

### 4.7 Error reporting

- Every `E_*` code has English text + hint in the builder (`msg`, `hint`) and an i18n key in the launcher.
- The launcher logs the builder's stderr and the event stream into `ultimate-legends.log`.
- GitHub issue template in the tools repo: builder version, content version, stage, code, OS, the log tail;
  never the ISO, never game files.

---------------------------------------------------------------------------------------------------------------

## 5. Legal / distribution checklist

Not legal advice; this is the project's own bring-your-own-copy rule turned into a checklist.

### 5.1 What the public repo and the releases may contain

| OK | Examples |
|---|---|
| Our code | the pipeline, the builder, the prepare stages, the format readers/writers (XDVDFS, `.fb`, XMLB, ZSND, IGB patching), the harness tools |
| Our documentation of formats and engine behaviour | SPEC.md, SPEC_heroes.md, `research/**/*.md`: addresses, offsets, struct layouts, what a function does, in our words |
| Facts / interoperability tables | script-function names + signatures + addresses (`xml1_api.json`, `xml2_api.json`), console command names, zone ids, file names, stat names, hashes of known-good inputs (`known_dumps.json`, `known_xml2.json`) |
| Short byte signatures used as guards | the 4-16-byte "is this the retail code" checks (`npc_values.py:289`; xml2-fix's `*_rules.hpp` tables are the same kind of thing and go public under MIT with v1.2.0) |
| Synthetic test fixtures | generated XDVDFS images, fake bundles, generated sine-wave ZSND banks, made-up XMLB trees (the current selftest fixtures are already synthetic: `ok_ev`, `ch_bogus`, ...) |
| Original art | the launcher's own capsules / logos (already original, per the launcher plan) |

### 5.2 What they may not contain

| Never | Why / examples |
|---|---|
| Game files or pieces of them, from either game | `.igb .xmlb .engb .chrb .navb .boyb .pkgb .zsm .zss .sfd .fb .xbe .exe .dll` of the games, decoded dumps of them as text (`zone.txt`-style) |
| Anything derived that still carries game content | converted sound banks, rewritten scripts, generated dialogs/missions, re-framed IGBs, `mission_plan.json` / `graph.json` *with* their text fields, the output folder or any part of it |
| Game text | dialogue, objective/mission text, character bios, item text, UI strings, subtitles - beyond a few words quoted in a design note |
| Disassembly or decompiled code | `.asm` listings, `decomp*.c`, pasted instruction listings (`stats_table_refs.txt`-style); addresses and our prose are fine |
| A modified exe or DLL of the games | the project never patches files; xml2-fix patches in memory |
| Game art, logos, box art, trademarks as branding | descriptive use of the names only ("for X-Men Legends"), with a non-affiliation notice (xml2-fix's `INSTALL.txt` wording) |
| Screenshots in the repo | copyrighted imagery and 41.6 MB of history; if the README needs pictures, a few small ones, Owen's call (Q7) |

### 5.3 Audit of the private working repo

The private working repo (tools, notes and research scratch since the first experiments) was audited file by file
before the first public commit (2026-09-28/29). Decoded game files, game text, disassembly listings, screenshots,
personal notes and duplicate copies stayed private; this public repository is a curated export of the rest with
fresh history (5.4), and the content guard (5.4 step 5) keeps it that way.

### 5.4 Publishing plan

1. **A new public repo with fresh history** (`ChronoRixun/legends-classic`: this repository), made from a curated
   export - not the private working repo flipped public and not a `filter-repo` of it. The working repo stays
   private for its handoff log and working notes.
2. Contents: `tools/` (pipeline, builder, prepare, harness tools; `newgame_test.sh` on env vars),
   `research/**/*.md` after the paraphrase fixes, `research/**/*.py` (the research code is OK), the stripped/fact
   JSONs the build or tools need (section 1.5), `docs/` (README, DUMPING.md - how to make an ISO from your own
   disc, BUILDING.md, LEGAL.md with the non-affiliation notice), `LICENSE`, issue templates.
3. Left out: everything in 5.3 SCRUB, `verify/rerun/`, `inventory.json`, `parse_results.json`, screenshots (unless
   Q7), `notes/`, `HANDOFF.md`, `.codegpt-game.json`, the top-level scratch files.
4. `.gitignore`: add `research/**/tmp/`, `research/**/verify/*.txt`, `*.asm`, `decomp*`, `*.iso`, `*.xiso`, and
   every game extension at every level.
5. **Content guard in CI** (and as a pre-commit hook): fail on any game-file extension, any file > 1 MB, any `.txt`
   under `research/` outside an allowlist, decoded-game-XML signatures (e.g. a line starting `<world`, `<zone`,
   `<SubTitles`, `<conversation`), `C:\Users\` / private IP patterns, and on JSON keys known to carry text
   (`descname`, `description`, `text`, `bio`) in shipped data.
6. License: the tools repo is independent of the launcher's GPL-3.0 (separate process); MIT matches xml2-fix
   (Q6).

### 5.5 Rules for the builder's own output

- The output folder and the cache are the user's own data on the user's PC; nothing is uploaded.
- Logs and `report.json` quote file names and short attribute values; the issue template asks for the error lines
  and the log tail, **never** attachments of the build, the cache or the disc.
- The builder makes no network calls.

---------------------------------------------------------------------------------------------------------------

## 6. Phased implementation plan

Effort in agent-days (one focused agent session ≈ 1 day of work); model per `fable-budget` (no Fable needed: this is
refactoring, systems code and UI, not new reverse engineering).

| Phase | Work | Effort | Model | Verified automatically by |
|---|---|---|---|---|
| **0 Prerequisites** | Merge xml2-fix `display` -> `main`, tag **v1.2.0** (its CI publishes `ultimate-legends.json`), make xml2-fix public; Owen answers section 7 | 0.5 | Opus | launcher `tools/dev/launcher_cdp.py` on a clean profile downloads v1.2.0 for xml2 |
| **1 Sources + prepare** (done: 1a Sources, P1, P2; 1b P3-P5, movies optional, full equivalence - see 1.5; left: the lib move of the sound modules, graph.json strip, zones.json warning, console_senders, `ctx.collisions`) | `xml1build/sources.py` (a `Sources` object in `BuildContext` replacing `ROOT/X1_*/RESEARCH/DEFAULT_BASE`; developer mode maps to today's folders so `build_xml1.py` keeps working); move the research modules into `xml1build/lib/`; `prepare/disc.py` (XDVDFS + `SubFile` + zip/`.fb` streaming + XBE certificate + `movies.json`), `prepare/tables.py`, `prepare/scripts.py` (rewrite_scripts + mission_plan as functions), `prepare/sound.py`, `prepare/music.py`, stage cache; strip `graph.json`, compute the zones.json warning in-build, drop `console_senders.json`, remove `ctx.collisions` | 4-6 | Opus | on Owen's PC: prepared outputs byte-identical to `research/**/out` + `music0x20/banks`; builder output = `build_xml1.py` output (same registry, same sha1); all selftests pass on it |
| **1p Sound performance** (done: numpy f5b52c2 + compiled kernel, see 1.5) | Profile `adpcm` beam/greedy encoders; skip `all_ima` for the 61 fixed music banks; vectorise with numpy or compile the encoder (a small C extension built in CI); keep bank order deterministic | 2-4 | Opus | banks byte-identical (or, if the encoder changes, `media_music.check_bank` + the fix_music SNR figures within tolerance); timing log: first build <= 15 min on 4 cores |
| **2 Builder CLI** | `tools/xml1builder/` (`info/build/verify/clean`, events, exit codes, cancel, lock, stamp, state machine); `xml1build/fix_ini.py` + harness refactor; builder mode: keep `PROXY_PATTERNS` in the sweep and V1 (F3), registry `sha1`, no `media_cache` snapshot, `--link-base`; input identification (`known_dumps.json`, `known_xml2.json` with the base manifest) | 2-3 | Opus | unit tests with a stub pipeline (events schema, exit codes, cancel at every stage, resume, lock, stamp states, ini merge preserving foreign keys/comments); on Owen's PC: cancel + resume, no-op rebuild, `verify` catches a deleted file, `clean` removes exactly the build |
| **3 Packaging + CI + release** (done except CI's first run and the Defender scan, which need the public repo: 3.6) | PyInstaller onedir spec (`freeze_support`, bootloader from source, no UPX, version resource, manifest); GitHub Actions: content guard, unit tests (Windows + Ubuntu), synthetic end-to-end, freeze, smoke, release zip + `xml1-builder.json` + SHA-256 on `v*` tags | 1.5-2 | Opus / Sonnet | CI green on a tag; the frozen exe passes the smoke tests; Defender scan of the artifact |
| **4 Launcher** | Merge `display-settings` first (the xml1 Display section reuses it); F5 (running check by path); `xml1` C++ entry; tool installer (zip, SHA-256, `tar.exe`, staging + rename); builder job runner (pipes, job object, JSON-lines parser, cancel); `xml1-*` commands; setup wizard, game-page section, Display/Mods `supports` += xml1; English strings for every `E_*` | 4-6 | Opus (C++ runner), Sonnet (UI) | `tools/dev/xml1_cdp.py` (like `launcher_cdp.py` / `mods_cdp.py`) against a **fake builder** (a tiny exe/script that replays recorded event streams and exit codes) - runs in CI without game data; then once with the real builder on Owen's PC |
| **5 Public repo** | Curated export into the new repo (5.4), scrub list, paraphrases, docs (README, DUMPING, BUILDING, LEGAL), license, issue templates, `.gitignore`, content guard | 1-2 | Opus | content guard passes; Owen reads the file list before the flip |
| **6 Release validation** | Fresh Windows user account (no Python) + the released launcher: set up XML2, build XML1 from the ISO, play; `campaign_walk.py` and `power_sweep.py` on the built folder (the harness works on any build folder); a second PC / tester if possible | 1-2 + beta | Opus + Owen | the harness runs; Owen plays |

Total ≈ **16-26 agent-days**; phases 1/1p/2 are sequential in the port repo, phase 4 can run in parallel once the
event schema (2.3) is frozen (the fake builder only needs the schema), phase 5 in parallel with anything.

### 6.1 What CI can verify without game data

Nothing in today's test suite runs without game files: every selftest reads `<out>`, the XML1 sources, the XML2
install, `XMen2.exe`/`default.xbe`, or the `.asm` listings. CI gets new synthetic tests (`tests/unit`, pytest):

| Area | Synthetic check |
|---|---|
| Disc reading | generate tiny XDVDFS images in the test (XISO at offset 0, and a sparse file with the partition at `0x18300000`); read directory trees, contiguous files, the `SubFile` window; a synthetic XBE header + certificate (title ID, version); PS2 / GameCube / ISO9660 / CCI magic detection |
| Bundles and zips | a generated `.fb` bundle through `fb_unpack.entries`; zip streaming through a `SubFile`; first-bundle-wins manifest rule |
| Formats | XMLB encode/decode round trips on made-up trees (attribute sort, `MULTI_ROOT`, header-only refusal); ZSND/ADPCM encode-decode of generated tones with pinned output hashes (determinism of the encoders across Python/numpy versions), with and without the compiled kernel; `tools/build_sound_kernel.py` ends with the kernel's self-check (synthetic audio: kernel vs numpy vs pure Python) |
| Pure pipeline helpers | `norm`, `FileIndex`, `map_skin`/`map_animdb`/`map_package_entry`, `map_review_texture`, `scripts_lint` on synthetic scripts, `x1schema` conversions and `combat_events` T7 (already synthetic) |
| Build orchestration | the builder with a stub pipeline: events schema, plan/progress math, cancel, resume, lock, stamp/state machine, keep-proxy sweep on a synthetic base/out, ini merge |
| Packaging | the frozen exe: `--version`, `info` on a synthetic image (exit 3 `E_ISO_WRONG_GAME` with a fake title ID), `--events jsonl` output validates against the schema |
| Launcher | `xml1_cdp.py` with the fake builder |
| Repo hygiene | the content guard (5.4) |

### 6.2 What needs game data (Owen's PC, a local script - never a CI runner)

A `tools/ci_local.py` runs, in order: prepare + build from the ISO; the equivalence checks (Phase 1); the existing
selftests on the result; `validate` standalone; timing log. Not a self-hosted GitHub runner: on a public repo,
workflows from forks could reach it and the game files.

| Test | Needs |
|---|---|
| `characters_selftest`, `heroes_selftest`, `scripts_selftest`, `zones_selftest` | a build + the XML1 sources (+ `xml2_test` for zones; replace that reference with a stored registry-hash baseline) |
| `combat_events_selftest` T1-T6, T8-T9 | `XMen2.exe`, XML2/XML1 styles, `xml2_text.asm` (T2 skips without it); T7 is synthetic |
| `npc_values_selftest` | `XMen2.exe`, `default.xbe`, both `.asm` listings, a build |
| `frontend_selftest` (unit U1-U14 too) | XML1's menu IGB and XML2's camera IGB |
| `validate_selftest` | runs full builds |
| `regress_nyc1.py` | a build, `xml2_test`, `research/characters/out/grso_riot_scheme` |
| harness tools (`campaign_walk`, `power_sweep`, `conv_probe`, ...) | a build, xml2-fix, the game running (Owen's etiquette rules) |

---------------------------------------------------------------------------------------------------------------

## 7. Open questions for Owen

| # | Question | Recommendation |
|---|---|---|
| Q1 | **Other XML2 exes.** Which retail XMen2.exe builds should the builder accept (non-English retail, the Beenox Polish/Russian builds `build.ini` mentions, no-CD exes)? An unknown exe silently loses every xml2-fix port feature. | Hard error on unknown exe hashes (`--allow-unknown-exe` for testers); collect hashes from the community; accept only exes whose bytes match at every xml2-fix guard. |
| Q2 | **Other XML1 dumps.** Accept a dump with the right title ID and files but an unknown hash? | Yes, with `W_ISO_UNKNOWN_DUMP` and `"known": false` in the stamp; fill `known_dumps.json` from Redump before release. |
| Q3 | **Compressed images** (CCI/CSO, common with modded consoles and xemu) and extracted folders: support them, or ISO/XISO only (decision b)? | ISO + XISO for M3; a clear error for CCI with a pointer to a decompressor; CCI later if people ask. |
| Q4 | **Where the game goes and hard links.** Default `<parent of XML2>\X-Men Legends (Port)`; hard links opt-in? | Yes and yes (links save ~2 GB but can write through to the real XML2 install if anything edits a file in place). |
| Q5 | **Keep the ~2.8 GB build cache by default?** | Keep: updates become ~5-minute rebuilds and the ISO can be deleted after the first build; a visible "Free up" button. |
| Q6 | **License and signing.** MIT for the tools repo (like xml2-fix)? Apply to SignPath Foundation's free OSS signing once public (check its current terms: it signs CI builds of public, OSI-licensed projects)? | **Decided: MIT** (2026-09-29); SignPath: yes, once public. |
| Q7 | **Public repo shape.** A new clean repo (not the private working repo flipped or filter-repo'd); name? Research notes with addresses public (yes?); screenshots in the repo (none? a few small ones?). | **Decided:** a new repo, **Legends Classic** (`ChronoRixun/legends-classic`); research notes public after the paraphrase fixes; no screenshots in git (release page / Discord). |
| Q8 | **Who writes xml2-fix.ini's port keys.** HANDOFF records "launcher does ... xml2-fix install/ini". This design: the builder writes the content keys (`[Game]`, `[Limits]`) and records them in the stamp; the launcher installs the DLL and writes the preference keys (`[Display]`, `[Discord]`, `[Online]`). OK, or launcher-only (it merges `requires.ini`, builder `--no-ini`)? | Builder writes content keys (standalone users get a working ini; no XMLB logic in C++). Both options cost the same. |
| Q9 | **Shared registry settings.** The port reads XML2's key bindings and display settings (`HKCU\...\X-Men Legends 2`). Acceptable for M3, or an xml2-fix `[Game] RegistryKey=` redirect like `SaveFolder`? | Accept for M3; the redirect is a small xml2-fix feature for later. |
| Q10 | **Online for the port.** A port host registers as `xmenlegpc` on OpenSpy, so XML2 players would see port games (and vice versa) with different content. Out of M3 scope, or must M3 separate them (a game-name/version filter in xml2-fix)? | Out of M3 scope, but don't advertise port online until they are separated. |
| Q11 | **Movies default.** On (+1.1 GB, the intro and all cinematics)? `--no-movies` also drops XML2's base movies, as today. | On. |
| Q12 | **First-build time.** Ship with ~15-50 min first builds, or land Phase 1p first? | Land 1p first; a 50-minute first run on a 4-core laptop will read as a hang. |
| Q13 | **Beta testers.** Is there anyone with a different PC (and ideally their own dump + XML2 install) for Phase 6? | Ask in the community Discord once the repo is public. |
