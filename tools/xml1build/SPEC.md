# xml1build: XML1 to XML2 PC build pipeline (SPEC)

Status: architecture v1, 2026-09-27; **integrated** the same day (section 10); **review fix rounds 1 and 2**
applied (sections 11 and 12); **engine limit fix** (the 200-record IGB info cache, section 13). All modules
(`characters.py`, `scripts.py`, `zones.py`, `media.py`, `validate.py`) are implemented; a full build and a tour build
run end to end with exit 0 and 0 validator errors. Sections 10-13 record the integration results and the deviations
from this text (with evidence); where they disagree with an earlier section, a later section wins (13 over 12 over
11 over 10), and all of them win over sections 0-9.

Sources of truth: `research/_summaries/{characters,scripts,sound,sweep}.md`. Their VERIFICATION sections override
the researchers' text. Every hard constraint in section 4 cites the summary it comes from.

---------------------------------------------------------------------------------------------------------------

## 0. Scope

**Goal (phase 1, "XML1 mode").** Convert the user's own XML1 Xbox data into an XML2 PC install that plays the
XML1 campaign from New Game:

- all 210 XML1 zones;
- the 190 XML1 NPCs, plus the XML1 heroes that zones use as NPCs;
- XML1 scripts, missions and dialogs (already rewritten by the scripts research);
- XML1 sound banks (already converted by the sound research);
- XML1 movies and their subtitles.

XML2's 21 herostat heroes stand in for the player party. There is no exe patch. It is bring-your-own-copy: the
tool only reads the user's discs and install, and writes a separate output directory.

**Out of scope for phase 1.** Each item is reported with `ctx.defer`:

- XML1 hero conversion (talent trees, `activepowerup`, menus, `textureicon`);
- the powers rework: XML1-only combat handlers without an XML2 counterpart (the triggers, handlers and affecters
  that have one are rewritten: section 22) and value codes P0+..P16 / BST1 / BST9;
- the XML1 UI and menus (XML2's UI is kept);
- codex, trivia, danger room menu, review, credits and personal data;
- ~~`.zam` automap generation~~ (done: section 26);
- conversation speaker markup (`%X-TEAM%text` versus `%Name%: text`);
- fre/ger languages;
- exe patches (the 296-name table, zone-var clearing at 0x49fe70).

**Confirmed in-game so far:**

- converted zone `nyc/alison/nyc1_1_1`;
- XML1 NPC `grso_riot` via the skin+14000 scheme, including the in-IGB rename and the cel outline;
- converted ZSND IMA banks.

**Not yet confirmed:** music, ZTRK death-style tracks, movies, popups, missions and zone-var persistence. The
build must still produce these, and `validate` checks them offline.

---------------------------------------------------------------------------------------------------------------

## 1. Code layout and who writes it

| File | Written by | Role |
|---|---|---|
| `tools/build_xml1.py` | architect (done) | CLI entry point: base sync, module runner, sweep, registry, validate, reports |
| `tools/xml1build/__init__.py` | architect (done) | empty |
| `tools/xml1build/common.py` | architect (done) | `BuildContext` (ctx), indexes, writers, registry, report, namespace helpers, sound plan |
| `tools/xml1build/testhooks.py` | architect (done) | `--start-zone` / `--tour` hooks, `_tour.json` |
| `tools/xml1build/characters.py` | characters owner | section 5.1 |
| `tools/xml1build/scripts.py` | scripts owner | section 5.2 (also provides the rewrite functions zones uses) |
| `tools/xml1build/zones.py` | zones owner | section 5.3 |
| `tools/xml1build/media.py` | media owner | section 5.4 |
| `tools/xml1build/validate.py` | validate owner | section 5.6 |
| `tools/xml1build/x1schema.py` | fix round 1 | XML1 -> XML2 schema conversions every import gets (entity classes, renamed attributes, effect colours, the combat rewrite); section 11 |
| `tools/xml1build/combat_events.py` (+ `combat_events_selftest.py`) | combat triggers | XMen2.exe's registered combat-event types, FightMove handlers and affecters (data with addresses), the XML1 -> XML2 style rewrite x1schema applies, validator V18; **section 22** |
| `tools/xml1build/npc_values.py` (+ `npc_values_selftest.py`) | NPC values | how both exes read a style value code and size / refill an NPC's energy (addresses), the resolver characters runs on every style it writes, the NPC energy talent, validator V19; **section 24** |
| `tools/xml1build/skins.py` (+ `skins_selftest.py`) | skins | XML1 skin IGBs against their anim DBs: structure, blend weights, skin / skeleton mismatches, validator V21; `pad_blend_weights` (not applied by the build); **section 25** |
| `tools/xml1build/automaps.py` (+ `automaps_selftest.py`) | automaps | how both exes load and draw a zone's automap (addresses), the `.zam` format, the XML1 automap texture -> `.zam` conversion zones runs per zone, validator V20; **section 26** |
| `tools/xml1build/scripts_transform.py` | fix round 1 | post-passes on the installed research scripts (counter narrowing, zone literals, blackbird fallback) + self-test interpreter; section 11 |
| `tools/xml1build/schema_check.py` | fix round 1 | standalone: XML1 names XMen2.exe can never read (whole-string exe match; replaces `tools/schema_diff.py`'s substring match) |
| `tools/xml1build/regress_nyc1.py` | integration | standalone regression guard for the in-game-proven `nyc/alison/nyc1_1_1` test |
| `tools/xml1build/heroes.py` (+ `heroes_selftest.py`) | heroes owner | the XML1 playable roster on XMen2.exe (herostat, per-hero talent files, collapsed powerstyles, packages, npcstat / shared_talents patches; runs between characters and scripts): **`tools/xml1build/SPEC_heroes.md`** |
| `tools/xml1build/frontend.py` (+ `frontend_selftest.py`, `validate_frontend.py`) | M2 front end | XML1's main menu (XML1's menu IGB unchanged, MAIN_MENU file, package; xml2-fix `MainMenuItems` for the mouse and Quit), Danger Room, review_paths / codex / trivia / credits tables and their textures; runs after media; nothing with `--frontend xml2`; validator V15-V17: **section 21** |

Each module exposes `run(ctx) -> None`. It raises only on bugs; data problems go to `ctx.error`, `ctx.warn` or
`ctx.defer`. Module-level *provider functions* (section 5.0) must be pure: they may read files, but they must not
write, and they must work even if that module's `run` did not execute (for example `--only zones`).

**Module rules**

- Never modify the real XML2 install, `xml1_*`, `research/*` or `xml2_test`. The ctx writers refuse any path
  outside `<out>`, and `BuildContext` refuses an `<out>` that overlaps the base or a protected tree.
- Never write with `open()` or `shutil`. Every file goes through `ctx.write_*`, `ctx.copy_file` or
  `ctx.import_x1_asset`, so that it is registered, owned and swept correctly.
- You may import or copy code from the research prototypes, but never modify them.
  - `research/characters/build_chars.py` and `research/scripts/rewrite_scripts.py` execute at import
    (argparse / analysis at module level). Copy their functions; do not import them.
  - `x1names`, `sweeplib`, `zsnd`, `zhash`, `simlookup` and `xmlb` are importable. `common.py` appends
    `tools/`, `research/sweep`, `research/characters` and `research/sound` to `sys.path`. Import our common
    module as `from . import common as C`, never as `import common` (that name is `research/characters/common.py`).
- Write Python files with the Write tool, not bash heredocs, which mangle backslashes.
- Threads are allowed (`ctx.opt('jobs')`), because all ctx writers are locked. Keep module caches thread-safe.

---------------------------------------------------------------------------------------------------------------

## 2. Entry point and build flow (implemented)

```
python tools/build_xml1.py --out <dir> [--base "<XML2 folder>"] [--start-zone <zone>]
                           [--tour <seconds>] [--no-movies] [--only <module,...>] [--no-validate]
                           [--test-ini] [--adopt] [--jobs N]
```

| Option | Meaning |
|---|---|
| `--out` | Output install. It is created if missing. It is refused if it overlaps the base, `xml1_*`, `research/` or `tools/`, or if it is non-empty without `_build/` (unless `--adopt`). |
| `--base` | XML2 PC install to copy (read-only). It must contain `XMen2.exe`. |
| `--start-zone Z` | New Game jumps straight to zone `Z` (for example `nyc/alison/nyc1_1_1`). See section 7. |
| `--tour N` | Smoke-tour: every reachable converted zone waits N seconds, then loads the next. Writes `<out>/_tour.json`. See section 7. |
| `--no-movies` | Leaves out all `*.sfd`: base movies are not copied (and are removed from an existing `<out>`), and media skips XML1 movies. Movie subtitles are still written. |
| `--only a,b` | Runs only these content modules (`characters`, `scripts`, `zones`, `media`). Outputs of the other modules from the previous build in the same `<out>` are carried over unchanged. |
| `--no-validate` | Skips the validator. |
| `--test-ini` | Sets `alchemy.ini` to `fullScreen = false` and `defaultReportLevel = kInfo`, and writes `<out>/.codegpt-game.json` with the launch command pointing at `<out>/XMen2.exe`. |
| `--adopt` | Allows taking over a non-empty directory that this tool did not create (for example an old `build_test` copy). The sweep deletes non-base files there. |
| `--jobs` | Number of worker threads a module may use (default: CPU count / 2). |
| `--blackbird menu\|chooseteam` | Mission starts (section 11.6). `menu` (default) keeps XML1's `blackbirdMenu(..., "loadMapKeepTeam('z')", ...)`; `chooseteam` rewrites those calls to `loadMapChooseTeam("z")`. Also `XML1BUILD_BLACKBIRD`. |
| `--npc-scaling off\|xml2curve` | XML1 enemies (section 11.8). `off` (default) keeps XML1's level and stats; `xml2curve` adds XML2's per-level `specific_attack/defense/health` and `monst_dmg_high`. Also `XML1BUILD_NPC_SCALING`. |
| `--forced-teams seat\|menu` | XML1's forced parties (section 19). `seat` (default) emits the xml2-fix seat / skinset / push / pop / addHero blocks with the team menu as their else branch; `menu` emits no xml2-fix call (section 12.6 only). Also `XML1BUILD_FORCED_TEAMS`. Re-runs scripts and zones when it changes. |
| `--start-party h1,h2` / `--start-skinset costume:heroes` | With `--start-zone`: the New Game hook unlocks these heroes and seats them through the section 19 seat block (section 7). |
| `--frontend xml1\|xml2` | The front end (section 21). `xml1` (default) = XML1's main menu, backdrop, intro, menu music, Danger Room and Review data; `xml2` = XML2's front end exactly as before section 21. Also `XML1BUILD_FRONTEND`. Re-runs scripts, zones, media and frontend when it changes. |

A carried-over module output that was built with a different `--blackbird` (scripts) or `--npc-scaling`
(characters) is stale, so `--only` re-runs that module (`build_xml1.plan_content_opts`, recorded as
`report.json build.forced_rerun`).

**Flow** (`build_xml1.main`):

1. **Safety checks.** Then create `<out>/_build/`.
2. **Carry-over.** Load `<out>/_build/registry.json` from the previous build. Its entries owned by content
   modules that are *not* selected this time (and whose files still exist) are carried over. Files `testhooks`
   overrode (owner `testhooks`; content owner = the last content module in their `history`) hold hooked content:
   with the same `--start-zone`/`--tour` as the previous build (`_build/report.json`) they are carried and testhooks
   re-applies its idempotent patches; otherwise their content module is added to the selection and re-run
   (printed as `[build] re-running [...]`, recorded as `report.json build.forced_rerun`). Without this, `--only
   media` after a `--tour` build restored XML2's `new_game.py` and swept every tour-stop zone file.
3. **`common.sync_base(base, out, skip_sfd, keep=carried)`.** Copies every base file except the xml2-fix proxy
   (`dinput.dll`, `mods/`, `xml2-fix.*` at the root, which are never copied), and except `*.sfd` with
   `--no-movies`. It copies only files whose size or mtime differ (`copy2`), so it restores every base file a
   previous build replaced. The first build copies about 2.37 GB (1.9 GB with `--no-movies`); later builds copy
   only what changed.
4. **Build the context.** `ctx = BuildContext(out, base, args, registry=Registry(carried))`, with
   `ctx.shared['selected_modules']`, and the `--test-ini` tweaks applied (owner `build`).
5. **Run the content modules** in the fixed order **characters → scripts → zones → media**, each via
   `common.run_step`, which records timing, status and exceptions. A module failure is recorded as an error and
   the build continues, so the validator still runs. A module that is not implemented yet is reported as
   `missing` (error).
6. **`testhooks.run`**, only if `--start-zone` or `--tour` is given. With no `--tour`, a stale `_tour.json` is
   deleted.
7. **`common.sweep_stale`.** Deletes every file in `<out>` that is neither a base file nor registered this build
   (this includes proxy files and stale outputs of earlier builds), then removes empty non-base directories. The
   build metadata (`_build/`, `_tour.json`, `.codegpt-game.json`) is kept. Then `_build/registry.json` is written.
8. **`validate.run`**, unless `--no-validate`. It runs after the sweep, so it sees the final tree.
9. **Reports.** Writes `_build/report.json` (per-module status, seconds, counts, notes, warnings, errors,
   deferred) and prints a summary.
10. **Exit code.** `0` means no errors anywhere; `1` means a module failed or there are errors (including
    validator errors); `2` means the build was refused (unsafe `--out`, bad `--base`).

**Outputs in `<out>/_build/`:**

- `registry.json`: every written file → {rel, owner, source, overwrote_base, size, mtime, shared, history};
- `report.json`;
- `validate.json` (written by validate);
- any `ctx.write_meta(name, obj)` files modules want to keep (for example `zones_detail.json`).

Recommended build directory: `build/xml1` (not `xml2_test`).

---------------------------------------------------------------------------------------------------------------

## 3. The ctx API (`tools/xml1build/common.py`, implemented)

### 3.1 Fields

| Field | Type | Content |
|---|---|---|
| `ctx.args` | Namespace | `out, base, start_zone, tour, no_movies, only, no_validate, test_ini, adopt, jobs`. Use `ctx.opt(name, default)`. |
| `ctx.out`, `ctx.base` | Path | resolved output and base install |
| `ctx.build_dir` | Path | `<out>/_build` |
| `ctx.sources` | Sources | where every input lives (section 27): developer mode (the repo's folders) or prepared mode (the prepare cache) |
| `ctx.root`, `ctx.tools`, `ctx.research`, `ctx.x1_loose`, `ctx.x1_assets`, `ctx.x1_xbox` | Path | input paths, from `ctx.sources` (never the `common.X1_*` / `RESEARCH` constants) |
| `ctx.base_index` | FileIndex | base install without the proxy (about 13,382 files). `get(rel)` gives the actual spelling, `path(rel)`, `find(rel_noext, exts)`, `find_all`, `under(prefix)`, `in` |
| `ctx.out_index` | FileIndex | `<out>` without the metadata; kept current by every ctx write |
| `ctx.x1_loose_index`, `ctx.x1_assets_index` | FileIndex | XML1 sources. `ctx.x1_path(rel)` prefers loose over assets. `herostat.eng/.fre/.ger` differ between the two, and loose (the disc bundles) wins. |
| `ctx.registry` | Registry | this build's written files (plus the carried entries) |
| `ctx.report` | Report | per-module collector |
| `ctx.shared` | dict | hand-over between modules (keys fixed in section 5.0) |
| `ctx.module` | str | current step name, set by `run_step`, used as the owner of writes |

### 3.2 Reporting

`ctx.log(msg)` prints progress. The rest go to `report.json`:

- `ctx.note(msg)`
- `ctx.warn(msg)`
- `ctx.error(msg)`: makes the build fail.
- `ctx.defer(msg)`: intentionally left for a later phase.
- `ctx.count(key, n=1)`
- `ctx.set_count(key, value)`

### 3.3 Read-only research and source data (cached)

- `ctx.research_json('sweep/graph.json')`: any research JSON, read from `ctx.research_path(rel)`.
- `ctx.research_path(rel)`: where a research input lives (`'scripts/out/scripts'`, `'sound/out/all_ima/eng'`, ...):
  `research/<rel>`, or a prepared stage's output when the Sources override it (section 27). Never
  `ctx.research / rel`.
- `ctx.manifest`: `xml1_loose/_fb_manifest.json`, bundle → `[[path, kind]]`.
- `ctx.nsmap`: `x1_namespace_map.json`.
- `ctx.collisions`: sweep `collisions.json['files']`, XML1 rel → {status: new|different|identical}.
- `ctx.graph`, `ctx.zones_info` (sweep `zones.json`), `ctx.xml2_api` (scripts `xml2_api.json`: exact-case name →
  {args, ret}).
- `ctx.x1_zones()`: the 210 zone ids, lowercase (for example `nyc/alison/nyc1_1_1`).
- `ctx.zone_bundle(zone)`: its `[[path, kind]]`.
- `ctx.tour_order()`: graph `reachable_from_new_game`, 162 zones in BFS order.
- `ctx.x1_path(rel)`, `ctx.x1_origin(rel)`, `ctx.x1_rels(prefix)`, `ctx.x1_is_empty(rel)`.
- `ctx.read_x1_xml(rel)`: an Element via the robust sweeplib parser (attribute names lowercased and sorted), or
  **None for a 0-byte / whitespace file**.
- `ctx.read_base_xmlb(rel)` and `ctx.read_out_xmlb(rel)` (the current `<out>` state).
- `ctx.out_exists(rel)`, `ctx.base_exists(rel)`.

### 3.4 Writing (the only allowed way to create files in `<out>`)

| Call | Semantics |
|---|---|
| `write_bytes(rel, data, *, source=None, replace=False, shared=False) -> actual_rel` | Atomic (temp file plus `os.replace`, so it can never write through a hard link). Reuses the existing directory and file spelling; new top-level directories get XML2's spelling (`Maps`, `Actors`, ...). Writing a file another module wrote this build raises `OwnershipError` unless `replace=True`. Overwriting a base file needs no flag and is recorded as `overwrote_base`. |
| `copy_file(src, rel, *, replace=False, shared=False)` | `copy2`. Skipped when the destination already has the same size and mtime (fast rebuilds); it is registered either way. |
| `write_xmlb(rel_noext, root, exts=('.XMLB',), ...)` | Encodes once with `encode_xmlb`, which lowercases and sorts attribute names, preserves tag case, supports `MULTI_ROOT`, refuses header-only 8-byte output (raises `EmptySource`) and re-decodes to check. Writes each extension. Pass `('.XMLB', '.engb')` for localized files. |
| `write_xmlb_pair(rel_noext, root_xmlb, root_engb)` | For tables XML2 ships as **two different files**: npcstat, herostat, zoneinfo, strings, items, shared_talents, and so on. XMLB uses `@DATA@` keys and engb uses English text. Patch each file from its own base. |
| `write_script(rel_or_ref, text_or_lines, *, replace=False)` | Forces CRLF, latin-1. Accepts `'Scripts/a/b.py'` or the ref `'a/b'`. |
| `write_json(rel, obj)` | A registered game-tree JSON file (used for `_tour.json`). |
| `write_meta(name, obj)` | `<out>/_build/<name>`, not registered (reports and intermediate data). |
| `patch_out_xmlb(rel_noext, fn, exts=(...), replace=True)` | Decodes each existing extension in `<out>`, calls `fn(root) -> changed`, and rewrites the changed files. |
| `remove_out(rel)` | Deletes a file the current module wrote (never a base file). |
| `import_x1_asset(x1_rel, *, force=False, patch=None, patch_key=None, out_rel_noext=None, out_ext=None) -> ImportResult` | **The shared XML1 asset importer** (section 4.4). Text (`.eng`/`.xml`/`.chr`/`.nav`) goes to the XMLB family per `TEXT_OUT`, with `patch(root)` applied first. Binary files are copied, with `.igb` written as `.IGB`. `.fre`/`.ger` are `skipped`. 0-byte sources are `empty` and nothing is written. If the base has the destination path and `force` is False, the result is `kept_xml2`. The importer is idempotent across modules: the same source with no patch, or the same `patch_key`, returns the cached result, and the file is owned by the first importer and marked shared. The same module may re-import with a patch, which rewrites the file. A different module with a different patch gets `conflict` plus an error. `.py` raises: scripts belong to the scripts module. |

`ImportResult` fields:

- `x1_rel`
- `status`: one of `written`, `kept_xml2`, `missing`, `empty`, `skipped`, `conflict`
- `pkg_name`: the lowercase, extensionless destination, which is what goes into a packagedef
- `out_rels`
- `.ok`: true when the status is `written` or `kept_xml2`

### 3.5 Namespace helpers

These are available as module functions `C.x` and as `ctx.x`.

| Helper | Rule |
|---|---|
| `map_skin(s)` | A 4-digit XML1 skin maps to `+14000` (for example `5810`→`19810`, prefixes 140..239 ≤ 255). Anything else, including 2-digit costume variants and 5-digit XML2 skins, is unchanged. |
| `map_animdb(name)` | Numeric → `map_skin`. A clashing XML1 character anim DB gets `x1_`+name (21 of them). `common`, `fightstyle_*` and `moveset_*` stay XML2's. |
| `map_powerstyle(n)` | A clashing XML1 powerstyle gets `x1_`+n (21). `ps_def` is identical and is shared. |
| `map_fightstyle(n)` | Unchanged: shared with XML2 by name. |
| `map_ui_path(p)` | `hud/hud_head_<id>`, `ui/hud/characters/<id>` and `ui/models/characters/<id>` get `+14000`. |
| `map_actor_path(p)` | `actors/<id or name>[.igb]` is mapped. |
| `map_loading_texture(p)` | `textures/loading/<4 digits>` gets `+14000`. The engine builds `textures/loading/%02d%02d` from the prefix byte (0x487258). Named loading textures are unchanged. |
| `map_attr(attr, value)` | Skin attributes (`skin`, `skin_*`, `monster_skin`, `actorskin`, `leaderskin`, `mutantskin`, and a numeric `model`), `characteranims`, `powerstyle`, `moveset1`/`fightstyle`, `loading`, and any value that is a HUD/UI character path, an `actors/` path or a numeric loading texture. |
| `map_tree_refs(root) -> n` | Applies `map_attr` to every attribute in a tree. |
| `map_package_entry(kind, x1_path) -> (kind, filename)` | Converts an XML1 bundle entry to the XML2 packagedef form: actorskin/actoranimdb become a bare mapped stem (`19810`, `x1_01_cyclops`); HUD/UI models are mapped; `fightstyle` `data/powerstyles/<x>` is mapped; `effect` loses its `effects/` prefix (the form all 10,796 XML2 effect entries use); numeric loading textures are mapped; everything else becomes lowercase, extensionless and `/`-separated. |
| `char_package_rel(name, skin, nc=False)` | `Packages/generated/characters/<name>_<skin>[_nc].PKGB` (0x68e508). |
| `package_entry_files(kind, filename)` | The candidate `norm()` files a packagedef entry must resolve to, or None for `combat_is`, `bigconvmap`, `sound` and `xml_talents`. Checked against all of XML2's own packages; XML2's own misses are all leftover or test packages. |

### 3.6 Sound plan (pure; usable before media runs)

- `ctx.planned_sound_banks()` returns `norm(rel)` → `{bank, kind: base|x1|merged, src}`:
  - **328 base banks** are kept;
  - **197 XML1 banks** come from `research/sound/out/all_ima/eng`;
  - **18 merged banks** come from `research/sound/out/merged/eng` and replace XML2's `x_common`, `x_voice`,
    `menu_a/c`, and the hero and colliding NPC banks.
  - `bishop_m` (empty in XML1) stays XML2's.
- `ctx.sound_bank_rel('grso_m')` returns `'sounds/eng/g/r/grso_m.zsm'`. It prefers `.zsm`, the way the loader
  does (0x591380), and returns None if the bank will not exist. **characters uses this to decide `sounddir`, and
  media installs exactly this plan.**

### 3.7 Misc

- `C.norm(rel)`: lowercase, `/`-separated key.
- `C.split_ext`, `C.to_crlf`, `C.script_ref`, `C.script_rel`.
- `C.parse_x1_text`, `C.normalize_attrs`, `C.encode_xmlb`, `C.decode_xmlb`, `C.xmlb_attr_problems(root)`,
  `C.iter_roots`, `C.find_world(root)`.
- `C.TEXT_OUT`, `C.MODULE_ORDER`, `C.PROXY_PATTERNS`.
- `C.sync_base`, `C.sweep_stale`, `C.run_step`: build internals.

---------------------------------------------------------------------------------------------------------------

## 4. Global conventions and hard constraints

### 4.1 Paths and names

- **Zone ids** are lowercase with `/`, relative to `maps/`, with no extension: `nyc/alison/nyc1_1_1`.
  Normalise XML1 backslashes and mixed case (zoneinfo, `nextzone`, `loadMap` arguments) with `C.norm`.
- **Packagedef filenames** are lowercase, extensionless and relative to the game root (`maps/<zone>`,
  `scripts/<ref>`, `conversations/...`, `dialogs/...`, `textures/...`, `models/...`). Two exceptions:
  - actors use a bare stem;
  - effects drop the `effects/` prefix.
- **Output spelling** follows XML2: `Maps/...XMLB`, `.engb`, `.CHRB`, `.NAVB`, `.BOYB`, `.PKGB`, `.IGB`. `out_path`
  handles this; do not hand-build paths.

### 4.2 XMLB (sweep and characters summaries)

- Attribute names must be lowercase and **sorted**, because lookup is a binary search. Tag case is preserved.
  `encode_xmlb` enforces this for every write.
- Some files have several top-level elements: keep `xmlb.MULTI_ROOT`.
- Localized XML1 `.eng` becomes `.XMLB` plus `.engb`. Non-localized `.xml` becomes `.XMLB` only (XML2 ships 86
  XMLB-only maps). `.chr` becomes `.CHRB` and `.nav` becomes `.NAVB` (`C.TEXT_OUT`).
- Where XML2 ships both files with different content (npcstat, herostat, zoneinfo, strings, items,
  shared_talents, ...), patch each from its own base with `write_xmlb_pair`.
- Never emit a header-only 8-byte XMLB (`encode_xmlb` raises).

### 4.3 Scripts (scripts summary)

- Scripts use CRLF.
- Every call must be a function registered in XMen2.exe, **with exact case**: `ctx.xml2_api` has 308 names. Name
  lookup is case-sensitive (0x4d6910 plus `repe cmpsb`); keywords are compared with `_stricmp`.
- argc must equal `len(argsig)`, and literal types must match (`i`/`f` need a number, `s` a string, `a` accepts
  anything). Otherwise the line is **silently dropped**.
- Inline data scripts (an attribute value containing `(`) are limited to 255 bytes and split on the literal
  `\n\r`.
- Console `runscript <code>` (dialog options, blackbird) must contain no whitespace or `;`, at most 127 characters,
  and at most 2 pending console commands.
- XML2 `beginMission`, `beginMissionHack` and `loadMap` are no-ops: XML1 code must not call them. XML1 `loadMap`
  equals XML2 `loadMapKeepTeam`.
- Zone vars are cleared on every zone load. XML1 mission vars and flags are packed into game flags (`x1v##`,
  `x1g##`, `research/scripts/out/var_storage.json`: 41 game vars, within the 96 free).
- Script-engine pools: 620 statement nodes (0x4d7e6e) and 1,556 values. `mastermold2` grew to 906 statements; the
  packed counters `corecount` and `stage` are narrowed to their real width (section 11.5), which brings it to 613.
- Zone literals in load calls are normalised to lowercase `/` ids (section 11.4).

### 4.4 Collision policy (XML1 path == XML2 path)

| Category | Policy | Who |
|---|---|---|
| numeric actors, HUD heads, UI character models, numeric loading textures | never collide: renamed +14000 | characters |
| character anim DBs (21 differ), powerstyles (21 differ) | `x1_` prefix; `ps_def` (identical) shared | characters |
| `common.igb`, `fightstyle_*`/`moveset_*` anim DBs, 16 colliding fightstyles | XML2's version used (shared by name; XML1 `fightstyle_gun_rifle` has 9 extra anim names, which are reported) | characters |
| zone files `maps/<zone>.*` (2 differ, 1 identical) | XML1 wins (`force=True`), **except the XML2 front end `menu/main_back`** (`C.FRONTEND_ZONES`: `Maps/menu/main_back.*`, `MotionPaths/menus/main_back.*`, its PKGB), which stays XML2's (section 11.1) | zones |
| `conversations/`, `dialogs/`, `subtitles/`, `data/entities/`, `motionpaths/` text or IGB referenced by XML1 zones | XML1 wins (`force=True`): XML1-mode build, and XML2's zones are not played | zones |
| generic `models/`, `textures/`, `effects/`, `skybox/` (140 / 189 / 7 / 1 differ) | **XML2 wins** (`kept_xml2`, the proven default). Kept counts are reported. Namespacing props is a later decision. XML1-only effects are written with their colours converted (section 11.2). | zones / characters via `import_x1_asset` |
| global data tables (`herostat`, `npcstat`, `shared_talents`, `values`, `zoneinfo`, `common_ents`, `item_ents`, `items`, `shared_nodes`) | merged by their owner (section 5), never replaced wholesale | characters / zones |
| other global tables (`strings`, `codex`, `trivia`, `dangerroom`, `credits`, `review_paths`, `colors`, `stat_rules`, `shared_anims`, `shared_sounds`, `shared_combat_events`, `boltonactoranims`, `personal/*`) | XML2's kept; deferred (`shared_combat_events`: XML1's differing values are written onto the XML1 styles instead, section 30) | (report only) |
| `Scripts/**` (25 rewritten paths collide: `common/*`, `menus/*`) | XML1's rewritten versions overwrite `common/*`. XML2's front-end `menus/intro_normal.py`, `menus/main_back_main.py` and `menus/main_back_debug.py` are kept. `menus/new_game*.py` are replaced by the hook. | scripts |
| sound banks (19 names) | merged banks (XML2 entries win) replace XML2's. Never install `all_ima` `x_common`/`x_voice`/`menu_*`/hero banks. | media |
| movies `i101`-`i105`, `i107` | XML1 files renamed with an `x` prefix (`xi101`, ...) | media |

### 4.5 Empty (0-byte) XML1 files (sweep verification)

There are 71 empty text files (48 `.nav`, 12 `.xml`, 11 `.chr`) and 12 empty `.igb` files.

- `import_x1_asset` returns `empty` and writes nothing.
- An empty `.chr` becomes a valid `<characters/>` CHRB.
- An empty `.nav` means no NAVB and no `nav` package entry. This applies to 17 reachable mansion hub zones, and
  there is an in-game risk there.
- A zone whose zonexml or map IGB is empty is skipped. There are 12 such zones: 9 junk `mansion/man5` maps,
  `astral/savepx/astral1_1`, `astral/savepx/astral1_3` and `muir_is/muir2/muir_comcore`.
- `actors/7501.igb` (npcstat `Computer`'s skin) is not copied. See section 5.1.

### 4.6 Report discipline

- **error:** the result will not load or will silently misbehave (missing file, bad XMLB, unregistered call, cap
  exceeded).
- **warn:** degraded but loadable.
- **defer:** out of phase-1 scope.
- **count:** the key numbers listed per module below, which the orchestrator compares between builds.

---------------------------------------------------------------------------------------------------------------

## 5. Modules

### 5.0 Order, data flow and hand-over

```
characters ──(stats names, char files; sounddir via ctx.sound_bank_rel)──────────┐
heroes ──────(XML1 roster: herostat, talents, styles, packages; patches npcstat / shared_talents) SPEC_heroes.md
scripts ─────(Scripts/**, missions, Dialogs/x1; provider fns)────────┐           │
zones ───────(uses scripts.* providers + ctx.map_*; zone files, zoneinfo, world tables)
media ───────(sound plan from common; Sounds/**, Movies/**)                        │
testhooks ───(zones_converted, zone XMLB/PKGB, new_game)                           │
validate ────(reads <out> only + registry + research; cross-checks ctx.shared) ◄───┘
```

The characters, scripts and zones steps depend only on deterministic functions (`common` mappings and the
scripts providers), so any one of them can be re-run alone with `--only`. `validate` never trusts `ctx.shared`
alone: it re-derives facts from the `<out>` files.

**ctx.shared keys** (producer → type; every key is optional for consumers):

| Key | Producer | Value |
|---|---|---|
| `selected_modules` | build | list of module names |
| `stats` | characters | lowercase name → `{name, file: 'herostat'\|'npcstat', skin, characteranims, powerstyle, sounddir, origin: 'xml2'\|'xml1'\|'xml1_hero_as_npc'}` |
| `stats_names` | characters | set of lowercase names (herostat ∪ npcstat) |
| `char_packages` | characters | set of lowercase `Packages/generated/characters/*.pkgb` written |
| `scripts_installed` | scripts | set of lowercase script refs installed (`nyc/alison/tut1`) |
| `zones_converted` | zones | list of zone ids converted (manifest order) |
| `zones_skipped` | zones | zone id → reason |
| `zone_info` | zones | zone id → `{soundfile, zonescript, pkg, chr_names, nextzones, has_nav}` |
| `sound_banks_installed` | media | set of lowercase rels |
| `movie_renames` | media | `{'i101': 'xi101', ...}` |
| `tour` | testhooks | the `_tour.json` dict |

**Provider functions** (pure, cached through `ctx.research_json` / `ctx.shared`, no writes):

| Function | Defined in | Used by |
|---|---|---|
| `rewrite_data_tree(ctx, root, rel) -> int` | scripts | zones (zone XML, conversations, dialogs, `data/entities`, world tables) |
| `zone_script_ref(ctx, zone) -> str \| None` | scripts | zones (world `zonescript`) |
| `zone_package_extras(ctx, zone) -> list[(kind, filename)]` | scripts | zones |
| `zone_act(ctx, zone) -> int \| None` | scripts | zones (zoneinfo `act`). testhooks reads `zone_acts.json` itself. |
| `script_exists(ctx, ref) -> bool` | scripts | zones, validate |
| `movie_name(ctx, x1_name) -> str` | media | validate |

### 5.1 characters.py

**Owns:**

- `Data/npcstat.{XMLB,engb}` and `Data/shared_talents.{XMLB,engb}`;
- `Data/values.XMLB` (append only);
- `Actors/<mapped>.IGB` for XML1 actors;
- `HUD/hud_head_<mapped>.IGB`, `UI/HUD/characters/<mapped>.IGB` and `UI/models/characters/<mapped>.IGB`;
- `Textures/loading/<mapped 5-digit>.IGB`;
- `Data/powerstyles/<mapped>.{XMLB[,engb]}` and `Data/fightstyles/<xml1-only>.{XMLB[,engb]}`;
- `Packages/generated/characters/<name>_<skin>[_nc].PKGB`;
- `Packages/generated/powerstyles/<mapped>.PKGB` and `Packages/generated/fightstyles/<xml1-only>.PKGB`.

Generic assets referenced by character bundles (effects, models, `data/entities`) go through `import_x1_asset`,
where the first importer owns them.

**Reuse and regenerate.** Regenerate everything. Port `research/characters/build_chars.py` (`convert_stats`,
`ensure_talent`, `pkg_entry`, `build_packages`, `fix_package_for_boltons`, `copy_actor`, `copy_ui`) into
functions that take `ctx`. Keep the logic of `x1names.igb_rename`. Do **not** copy
`research/characters/out/all_npcs_xml1`: it omits `sounddir`, the heroes used as NPCs and the loading textures.
The build also reads `research/characters/x2_stats_refs.json` (keep-list evidence) and `combat_compat.json`
(report).

**Must:**

1. **Emit every XML1 character-namespace file, not only the ones NPCs use**, so that zones can reference any of
   them:
   - 183 numeric actors (+14000), with `igb_rename(data, old, new)` for `<id>`, `<id>_outline` and `<id>_skel`.
     Assert there are no problems; the research found 0 unfit names. Skip the empty `7501`.
   - 121 anim DBs. The 21 clashing ones get `x1_` (the file is renamed, internal names are kept). XML1-only
     names are copied. `common`, `fightstyle_*` and `moveset_*` are not copied (XML2's are used).
   - 68 HUD heads, 74 `ui/hud/characters` and 16 `ui/models/characters`, all +14000 with the in-IGB rename.
   - 23 numeric loading textures from `xml1_assets/textures/loading/NNNN.igb`, +14000.
   - 93 powerstyles through `map_powerstyle` (skip identical `ps_def`) and the 4 XML1-only fightstyles.
   - Convert text through `ctx.import_x1_asset(..., out_rel_noext=mapped)` or `write_xmlb`, with `.eng` becoming
     `.XMLB` plus `.engb`.
   - Never overwrite an XML2 file in these categories. If a mapped name exists in the base: identical means skip
     and share; different is an error. The namespace map's `check_errors` is empty, so this should never
     happen.
2. **npcstat in XML1 mode.** Build each of XMLB and engb from its own XML2 base:
   - **Remove** every XML2 npcstat entry except `KEEP_X2`, the `build_chars --keep-x2` default: `_hero1_mc_` to
     `_hero4_mc_`, `abyss`, `apocdummy`, `archangel`, `bastion`, `beast`, `forge`, `garokk`, `holocaust`, `menu`,
     `mikhail`, `omegared`, `profx`, `sauron`, `scarabapoc`, `stryfe` and `sugarman`. Add every name the kept XML2
     content needs: scan the CHRB files of XML2 zones that are still reachable in XML1 mode (`Maps/menu/*`, the
     front end), and names that XML2 herostat heroes' powerstyles or entities spawn by name. Report the
     additions and the dropped count (257 in the prototype).
   - **Add** all 190 XML1 npcstat entries through the ported `convert_stats`. **Keep `sounddir`** when
     `ctx.sound_bank_rel(sounddir)` is not None; otherwise drop it and defer. Weapons become BoltOns as in the
     prototype. XML1-only attributes (`leader`, `rating*`, `throwally`) are dropped, as are non-XML2 `skin_*`
     costumes.
   - **Add the XML1 heroes that zones use as NPCs.** These are the XML1 herostat names referenced by an XML1 zone
     `.chr` (also check scripts and conversations) that are *not* XML2 herostat names. Offline this gives
     **beast, frost, jubilee, magma and psylocke**. Magma is needed by the first mission, `nyc1_1_3`. Convert each
     like an NPC and drop hero-only children (inline talent trees, `activepowerup`, `scope`). Mark them
     `origin: xml1_hero_as_npc`.
   - **XML1 wins on the same name.** It replaces the kept XML2 entry of that name (`beast`, `profx`, `forge`, ...).
   - **Never add a name that exists in XML2 herostat.** Ten names are covered by XML2 stand-ins: `default`,
     `colossus`, `cyclops`, `gambit`, `iceman`, `nightcrawler`, `phoenix`, `rogue`, `storm` and `wolverine`.
     Report them.
3. **herostat is untouched** (XML2's 21). This is hero stand-in mode; `defer` the hero conversion.
4. **Caps** (errors):
   - unique names across herostat and npcstat ≤ 296 (expected about 233 = 229 + 4);
   - herostat = 21;
   - shared_talents ≤ 99 (expected 86 plus any talents added for heroes used as NPCs);
   - name length ≤ 31;
   - skins 4-5 digits with prefix ≤ 255.
5. **shared_talents.** Run `ensure_talent` for the talents missing from XML2 (52 in the prototype, including
   `fightstyle_villain`) in both the XMLB and engb files.
6. **values.** Append only the XML1 value codes absent from XML2 (A1-A10, XTL1-6) to `Data/values.XMLB`. Leave
   the 34 differing codes (P0+..P16, BST1, BST9) to the powers phase and defer them.
7. **Character packages** for every written stats entry, built from the XML1 bundle of the entry's own skin
   (`generated/characters/<name>_<skin>` plus `_nc`). Entries go through `ctx.map_package_entry`, and the
   BoltOn models are added. `Computer`: keep the stats entry (skin 21501), write no `Actors/21501.IGB`, and leave
   `actorskin` out of its packages. It is referenced by no zone `.chr`; validate allowlists it.
8. **Powerstyle and fightstyle bundles** (`packages/generated/powerstyles/*.fb`, 93; `fightstyles`, 20) become
   `Packages/generated/{powerstyles,fightstyles}/<mapped>.PKGB` for every style this module wrote. Skip weapon
   bundles and defer them (XML2 ignores `weapon`).
9. **shared:** `stats`, `stats_names`, `char_packages`.
10. **counts:** `npc_entries`, `hero_as_npc`, `stats_names`, `shared_talents`, `actors_written`,
    `igb_names_renamed`, `powerstyles_written`, `packages_written`, `sounddir_kept`, `sounddir_dropped`.
11. **Report or defer:** 72 review-pending styles (combat handlers XMen2.exe lacks: section 22),
    weapon bundles, the hero conversion, and value codes.

### 5.2 scripts.py

**Owns:**

- `Scripts/**`, except `Scripts/x1/tour/**` (testhooks);
- `Scripts/menus/new_game.py` and `new_game_hard.py` (testhooks may override them);
- `Dialogs/x1/*.{XMLB,engb}`;
- `Data/missions/*.{XMLB,engb}`.

**Reuse directly** (deterministic; `verify/rerun` diffed clean). Do **not** re-run `rewrite_scripts.py` during a
build.

- `research/scripts/out/scripts/**` (1,536 `.py`, already CRLF, with `setCurrentAct` injected into 73 zone
  scripts, 101 `x1/missions/begin_*.py` and 27 `x1/zones/*.py`);
- `out/dialogs/x1/p001..p092.{XMLB,engb}` (not the `.xml`);
- `out/data/missions/{missions.XMLB, x1_act01..09.{XMLB,engb}}`;
- `out/inline_rewrites.json` (129), `out/zone_extra_files.json` (67 zones), `out/zone_acts.json` (150 zones) and
  `out/helper_refs.json` (report).

**Must:**

1. Install every `out/scripts/**` file with `ctx.write_script` (re-normalise CRLF). The 22 XML2 `common/*`
   collisions are overwritten; report them. Do **not** install the front end: keep XML2's
   `menus/intro_normal.py`, `menus/main_back_main.py` and `menus/main_back_debug.py`, and leave out XML1's dead
   `menus/intro_demo.py` and `menus/intro_e3.py`.
2. **New Game hook** (no exe patch). `Scripts/menus/new_game.py` and `new_game_hard.py` are the body of
   `out/scripts/x1/missions/begin_alison.py`: flag clears, `setCurrentAct(1)`, objectives,
   `unlockCharacter wolverine/cyclops`, `startMovie("r102","afterMovie")`, `waitsignal`, and
   `loadMapKeepTeam("nyc/alison/nyc1_1_1")`. XMen2.exe `startFirstMission` runs these scripts after setting up its
   own roster of magneto, cyclops, wolverine and storm (0x4a7c42/0x4a7c57). The roster mismatch with XML1's
   alison (wolverine and cyclops) is accepted and deferred.
3. Install `Dialogs/x1` and `Data/missions`. This replaces XML2's `missions.XMLB`; report it. XML2's act mission
   files stay on disk but are unlisted.
4. **Dead-end dialogs.** `x1/p091` and `x1/p092` (Forge on Muir Island, run by
   `conversations/muir_is/muir1/1_6_4_meet_forge.eng`) have the options `muir_is/muir1/loadSewers` and
   `loadBlackbird`, which exist nowhere. Point them at the real next step (derive it from the XML1 mission data or
   `graph.json`: the begin script of the mission that follows Muir Island). If it cannot be determined, keep the
   dialogs and raise an error naming them.
5. **Providers** (section 5.0):
   - `rewrite_data_tree(ctx, root, rel)`:
     - exact-value replacement from `inline_rewrites.json` (all 129 keys occur verbatim in data);
     - for script-reference attributes (`actscript`, `deathscript`, `chosenscriptfile`, `scriptfile`, `script`,
       `zonescript`, and any attribute name ending in `script` or `scriptfile`) whose value contains no `(`:
       backslash → `/`, lowercase, strip `.py`;
     - an inline value containing `(` that is longer than 255 bytes gives a warning;
     - returns the number of changes.
   - `zone_script_ref(ctx, zone)`, in this order:
     - `zone_acts[zone]['zonescript']`, if that script is in `out/scripts`;
     - else `x1/zones/<zone>`, if generated (27);
     - else the XML1 world `zonescript` normalised, if the script exists;
     - else None.
   - `zone_package_extras(ctx, zone)`: `dialogs/x1/pNNN` → `('xml_resident', ...)` and `scripts/x1/...` →
     `('script', ...)`.
   - `zone_act(ctx, zone)`: `inject_act`, else the first of `acts`, else None.
   - `script_exists(ctx, ref)`: the ref is in the installed or planned set.
6. **shared:** `scripts_installed`. **counts:** `scripts_installed`, `common_overwritten`, `dialogs_x1`,
   `mission_files`, `inline_rewrites_available`.
7. **Defer:** forced per-mission heroes (REQUIREDHERO / maxheros), `addHero`, solo mode (18 inline
   `enterSoloMode` removed), the exact side-mission return point, conversation speaker markup, 44 zones that set
   no act on entry, and the 22 multi-act zones.

### 5.3 zones.py

**Owns:**

- `Maps/<zone>.{XMLB,engb,CHRB,NAVB,BOYB,IGB}` and `Packages/generated/maps/<zone>.PKGB` for the 210 zones;
- `Data/zoneinfo.{XMLB,engb}`;
- the world tables `Data/{common_ents,item_ents,shared_nodes}.*` and `Data/items.*`, with their
  `Packages/generated/{common_ents,item_ents,items,shared_nodes}.PKGB`;
- `Packages/generated/maps/package/permanent.PKGB` (append only);
- the first imports of `Conversations/**`, `Dialogs/**` (non-x1), `Subtitles/**`, `Data/entities/**`,
  `MotionPaths/**` and XML1-only `Models/`/`Textures/`/`Effects/`/`Skybox/`;
- `Automaps/<zone>.zam` (section 26; XML1's `textures/automap` textures are no longer imported or packaged).

**Reuse and regenerate.** Regenerate: a hardened port of `tools/convert_zone.py` `Converter.zone`, which is
proven in-game for `nyc1_1_1`. Use `sweeplib` through `ctx.read_x1_xml` / `import_x1_asset`, and scripts come
from the scripts module, never raw from `xml1_loose`. Reuse `research/sweep/zones.json` (links, categories,
`chr_characters`) as the expected-values baseline, and `graph.json`.

**Per zone** (threads allowed):

1. **Skip** if the zonexml (`maps/<zone>.eng` or `.xml`) or `maps/<zone>.igb` is missing or empty. This applies to
   12 zones; record them in `zones_skipped`.
2. **Zone XML.** Parse it, then:
   - (a) `ctx.map_tree_refs` (305 `monster_skin`, 40 `Hud/hud_head` precaches, `loading` attributes);
   - (b) `scripts.rewrite_data_tree`;
   - (c) world entity:
     - set `zonescript` from `scripts.zone_script_ref`;
     - keep `soundfile` and check it is under 10 characters (error);
     - note `ambientmusic`/`combatmusic` (5 zones), which XML2 drops silently;
     - `automap_texture` / `automap_offset` are dead reads in XML2 (0x4c7f90), so leave them; zones converts the
       texture they name into `Automaps/<zone>.zam` instead (section 26);
   - (d) `nextzone`/`prevzone`: backslash → `/` and lowercase. Only a target that is **not** in the zone's own
     directory is rewritten to the full lowercase path. The known case is `nyc/riots/nyc3_2_2` →
     `astroid_m/visit1/asteroid2_1` (plus the demo copies). XML2 resolves short same-directory names (63 of 144
     retail links). Warn about the 20 known unresolved `prevzone` values.
   - Collect `motionpath="dir/file/object"` values for step 5.
   - Write with `import_x1_asset(maps/<zone>.<ext>, force=True, patch=..., patch_key='zones.zone')`.
3. **CHR** → CHRB. An empty file gives `<characters/>` (via `write_xmlb`). Names that are not in
   `ctx.shared['stats_names']` (if present) are errors.
4. **NAV** → NAVB if non-empty; otherwise omit the file and the entry, and warn (the 17 mansion hubs are an
   in-game check). **BOYB:** generated from the native walk grid and map bounds (section 42); empty NAV retains an empty network. **Map IGB:** copied with `force`.
5. **Package** `Packages/generated/maps/<zone>.PKGB`, built from the bundle entries in order and de-duplicated:
   - `combat_is on/off` are kept as flags;
   - `zonexml`/`characters`/`nav`/`boy`/`model maps/<zone>`;
   - `actorskin`/`actoranimdb`, HUD/UI character models, `fightstyle`, and numeric loading textures →
     `ctx.map_package_entry` only. The files belong to characters; do not import them.
   - `script` entries → `scripts/<ref>`, only if `scripts.script_exists`; otherwise warn and drop.
   - `effect`/`model`/`texture`/`xml`/`xml_resident`/`motionpath` files → `ctx.import_x1_asset`:
     - use `force=True` for `conversations/`, `dialogs/`, `subtitles/`, `data/entities/` and `motionpaths/`, with
       text patched by `map_tree_refs` plus `rewrite_data_tree` under a fixed `patch_key`;
     - `missing` or `empty` → warn and drop the entry; `kept_xml2` → keep the entry and count it;
   - `motionpath` entries in XML2 form: `dir/file/object` from the zone XML, with the file at
     `MotionPaths/dir/file.IGB`;
   - `.fre`/`.ger` are skipped;
   - plus `scripts.zone_package_extras(zone)`;
   - plus `('script', 'scripts/<zonescript>')`;
   - plus any XML1-only file the zone XML references by attribute (`model`, `*effect`, `*spawn` entities, tile
     models) that the bundle lacks. The sweep counted 261 such refs (for example in `package/permanent`,
     `impacts/energy` and `models/tiles/<area>/`). The 29 references that are dead on the disc give warnings.
6. **zoneinfo** (after all zones). Start from the base `Data/zoneinfo.XMLB` and `.engb` (via `write_xmlb_pair`,
   each from its own base). Add or replace one `<zone>` per converted zone:
   - `name` = zone id;
   - `loading` = `map_loading_texture(XML1 loading)`;
   - `savename` = XML1 `savename`;
   - `act` = `scripts.zone_act`, or 1;
   - `build="normal"`, `state="1"`.

   The XML1 names are backslashed and 9 are mixed-case, so join by `C.norm`. `tutorial1` keeps its `state="2"`.
7. **World tables.** Merge XML1 `data/common_ents.xml`, `item_ents.xml`, `items.eng` and `shared_nodes.eng` into
   XML2's. Add the XML1 entries whose `name` is absent, apply `map_tree_refs` and `rewrite_data_tree`, and let
   XML2 win on the same name. Merge the matching XML1 bundles (`packages/generated/{common_ents,item_ents,items,
   shared_nodes}.fb`) into XML2's PKGBs by appending missing entries (with imports).
8. **Permanent package.** Import the XML1-only model, texture and effect entries of
   `maps/package/permanent.fb` and append them to XML2's `permanent.PKGB`. Report the count.
9. **shared:** `zones_converted`, `zones_skipped`, `zone_info`. **counts:** `zones_converted` (expected 198),
   `zones_skipped` (12), `files_written`, `kept_xml2`, `missing_refs`, `empty_nav`, `crossdir_links_fixed`,
   `pkg_entries`.

### 5.4 media.py

**Owns** `Sounds/eng/**` (the XML1 and merged banks) and `Movies/**` (XML1 `.sfd` files and subtitles).

**Reuse directly:**

- `research/sound/out/all_ima/eng` and `out/merged/eng`, through `ctx.planned_sound_banks()`. Do not re-encode;
  the verified SNR figures apply to these outputs.
- `xml1_xbox/movies/ntsc/<c1>/<c2>/*.sfd` (34 files, 648 MB), copied byte for byte. The extra C1 AIX/ADX stream
  stays.
- `xml1_assets/movies/*.eng` (27 subtitle files).

**Must:**

1. **Sounds.** For every plan entry of kind `x1` (197) or `merged` (18), `ctx.copy_file(src, rel)`. Merged banks
   replace base files (recorded as `overwrote_base`). Use a strict `zsnd.load` on each copied bank. **A stereo
   sample (flag 0x02) in any `.zsm` is an error** (the loader forces `nBlockAlign=2`). No XML1 bank has one
   today.
2. **Movies** (skip with `--no-movies`):
   - `new = movie_name(ctx, name)`: `'x' + name` if any base `Movies/ntsc/eng/**/<name>.sfd` exists. That covers
     `i101`-`i105` and `i107`; XML1 NTSC has no `i106`.
   - Copy to `Movies/ntsc/eng/<new[0]>/<new[1]>/<new>.sfd`.
   - The renamed XML1 `i1xx` are referenced only by XML1's front-end `intro_*.py` (not installed) and
     `data/review_paths.eng` (not ported). Note this.
3. **Subtitles.** `xml1_assets/movies/<name>.eng` → `Movies/<movie_name(name)>.{XMLB,engb}` (same schema as XML2
   `cine01`). This is done even with `--no-movies`.
4. **shared:** `sound_banks_installed`, `movie_renames`. **counts:** `banks_x1`, `banks_merged`,
   `movies_copied`, `subtitles`, `movie_bytes`.
5. **Defer or note:** the per-zone `ambientmusic`/`combatmusic` overrides (lost in XML2); the optional 44.1 kHz
   → 22.05 kHz downsample (only if the in-game music test stutters); the lossless `pcm_zsm` alternative
   (orchestrator decision).

### 5.5 testhooks.py (implemented)

See section 7. It runs after media and before the sweep, only with `--start-zone` or `--tour`. It may override
files owned by scripts and zones (`replace=True`).

### 5.6 validate.py

The validator reads the `<out>` tree, `ctx.registry`, the research files and `ctx.args`. It writes
`<out>/_build/validate.json`:

```
{checks: {id: {status, errors, warnings, counts}}, summary}
```

It also calls `ctx.error`/`ctx.warn`, capped at the first 50 findings per check (all of them are in the JSON).
Allowlists are named constants with a reason. Checks:

| id | Check | Severity |
|---|---|---|
| V1 proxy | No `dinput.dll`, `mods/` or `xml2-fix.*` in `<out>` | error |
| V2 registry | Every registered file exists with the recorded size. Report ownership overrides (`history`). The installed `x_common`/`x_voice`/`menu_*`/hero banks have a `research/sound/out/merged` source. | error |
| V3 xmlb | Every registered XMLB-family file decodes, re-encodes byte-identically, has lowercase + sorted attribute names on every element (`C.xmlb_attr_problems`), and is longer than 8 bytes. Every `classname` is one of XMen2.exe's 27 entity classes (`x1schema.REGISTERED_ENTITY_CLASSES`); no XML1-sourced effect keeps `red`/`green`/`blue` (section 11) | error |
| V4 packages | Every entry of every registered PKGB resolves (`C.package_entry_files`) in `<out>`. Allowlist: the 29 references dead on the XML1 disc, and `Computer`'s skin. Zone packages have `zonexml`, `characters` and `boy`. | error |
| V5 stats | Parse `<out>` herostat and npcstat (both XMLB and engb). Unique names ≤ 296; herostat == 21; no npcstat name in herostat; names ≤ 31 characters; skins 4-5 digits with prefix ≤ 255. Per XML1-origin entry: the skin actor, `characteranims`, powerstyle, `moveset1`, talents (in shared_talents or `talents/<name>`), `sounddir` bank, both character packages, BoltOn models and `skin_<costume>` variants exist. shared_talents ≤ 99. The same checks for XML2-origin entries are warnings. | error / warn |
| V6 zones | Per converted zone: CHRB names ⊆ stats names; world entity present; `zonescript` resolves to an installed script; `soundfile` < 10 characters and its `_m` bank exists; `nextzone`/`prevzone` resolve (same directory or full path) to a zone in `<out>` (20 known unresolved `prevzone` are warnings); the zoneinfo entry exists; the zone file is owned by zones. The XML2 front end (`C.FRONTEND_ZONES`) is not rewritten. `Data/items`: XML1 items only in XML2 schema (type item/potion/equipment/money, no `activepowerup`), every `inventoryitem` names an item (section 11) | error / warn |
| V7 scripts | For every registered `.py` and every script a registered package lists: CRLF only; each statement's function registered **exact-case** in `ctx.xml2_api`, argc == `len(argsig)`, literal types match; no `beginMission`/`beginMissionHack`/`loadMap`/`setMissionVar`/`getMissionVar`/`screenFade` in XML1 output. Inline data scripts (attribute values with `(` in registered XMLB) ≤ 255 bytes and valid. Dialog `runscript` code has no whitespace/`;` and ≤ 127 characters. Per-zone statement total (zone script plus the scripts its package lists) > 620 gives a warning. Distinct game-flag names ≤ 96 free. XML1 zone literals of load calls (and `cinematicStart` paths) lowercase with `/` (warning, section 11.4). Allowlist: the 14 known droppable lines in dead developer scripts (`missions/*_start.py`). Port the statement parser from `research/scripts/verify/v_output.py` / `rewrite_scripts.validate_lines`, but with exact-case matching. | error / warn |
| V8 sounds | Every installed bank parses strictly (except XML2's own `boss4_m`); no stereo sample in any `.zsm`. Per converted zone, resolve with `research/sound/simlookup.load_banks(paths)` plus `simlookup.resolve(name, soundfile, banks)`: banks = `<soundfile>_{m,a,c,v,d}` + `x_common` + `x_voice` + the `sounddir` banks of its CHRB characters; names = registered zone XMLB attributes containing "sound" plus `sound("PLAY_SOUND","<name>",...)` literals in its package scripts. Report per-zone and total coverage. Warn on misses, and on a total below 94% (research baseline 94.8%, whose misses are absent from XML1 too). | error / warn |
| V9 movies | Every `startMovie("<name>",...)` literal in installed scripts has `Movies/ntsc/eng/<c1>/<c2>/<name>.sfd` (only a warning with `--no-movies`; allowlist `test1`, `test3` and `blackbird_leave_mansion` in dead `missions/*_start.py`). The subtitle XMLB/engb pairs are complete. | error / warn |
| V10 new game | `Scripts/menus/new_game.py` and `new_game_hard.py` exist, pass V7, and their `loadMapKeepTeam`/`loadZone` target has `Maps/<zone>.XMLB` | error |
| V11 tour | If `_tour.json` exists: each stop's script exists, its zone's world `zonescript` equals the stop's script, and the zone PKGB lists it | error |
| V14 forced teams | Section 19.4: xml2-fix calls only in seat builds and only behind their `xml2fixFeature` guard; seat blocks = `scripts.forced_party_plan`; `setSkinset` valid, one per begin body; `pushParty`/`popParty` paired; `addHero` only in the join scripts; unseatable / cut missions (warn) | error / warn |
| V18 combat events | Section 22.4: the combat tables equal the install's XMen2.exe; in every style the build wrote each `<event>` / `<trigger>` resolves to a registered `ce_*` type, no orphan tag-only trigger, <= 19 triggers per move, names <= 31, affecters registered; unassessed unregistered handler (error), assessed ones (warn) | error / warn |
| V19 npc values | Section 24.5: the value name table / energy constants equal the install's XMen2.exe; no style the build wrote holds a value code XMen2.exe reads as 0; the NPC energy talent and every XML1-origin npcstat entry's rank | error |
| V20 automaps | Section 26.4: a `.zam` and exactly one last `<zam>` entry for every converted zone whose XML1 world names an automap texture (none elsewhere, no `textures/automap` entry); every `.zam` the build wrote parses as the loader reads it, keeps its vertices in their cells and fits the automap's 0x2000-vertex builder in every draw window | error / warn |

**counts:** `files_checked`, `pkg_entries_checked`, `script_statements`, `sound_names`, `sound_resolved`,
`movies_missing`.

---------------------------------------------------------------------------------------------------------------

## 6. Reuse and regenerate summary

| Research output | Build use |
|---|---|
| `research/characters/x1names.py`, `x1_namespace_map.json`, `collisions.json` | imported through `common.map_*` (the single source of naming truth) |
| `research/characters/build_chars.py` | code ported into characters.py; not executed |
| `research/characters/out/*` | not used (prototype and bisect outputs only) |
| `research/scripts/out/{scripts,dialogs/x1,data/missions}` | installed as-is by scripts.py |
| `research/scripts/out/{inline_rewrites,zone_extra_files,zone_acts}.json` | read by the scripts providers |
| `research/scripts/xml2_api.json` | `ctx.xml2_api` (V7) |
| `research/sound/out/all_ima/eng`, `out/merged/eng` | installed as-is by media through `ctx.planned_sound_banks()` |
| `research/sound/{zsnd,simlookup,zhash}.py` | imported by media and validate |
| `research/sweep/sweeplib.py` | the text-XML parser behind `ctx.read_x1_xml` and `import_x1_asset` |
| `research/sweep/{graph,zones,collisions}.json` | tour order, zone baseline, collision status |
| `tools/convert_zone.py` | ported into zones.py (hardened); the old tool stays for `build_test.py` |
| `research/sweep/xml2_copy` (2 GB) | not used (can be deleted) |

---------------------------------------------------------------------------------------------------------------

## 7. Test options (implemented in testhooks.py)

- **`--start-zone Z`.** `Scripts/menus/new_game.py` and `new_game_hard.py` become:

  ```
  # xml1-port test hook: --start-zone Z
  setCurrentAct(<act> )
  loadMapKeepTeam("Z" )
  ```

  `<act>` is `zone_acts.json[Z].inject_act`, else the first of its `acts`, else 1. `Z` must be a converted zone
  or an existing `Maps/Z.XMLB`. XML2's `startFirstMission` runs `new_game.py` after setting up its own hero
  roster.
- **`--start-party h1,h2 [--start-skinset costume:heroes]`** (with `--start-zone`, seat builds; section 19.5).
  `unlockCharacter("h", "" )` for each hero (the begin bodies unlock their REQUIRED heroes before their seat block,
  decision 7.4), then the load becomes the section 19 seat block: with xml2-fix `[Game] ForcedTeams=1`,
  `seatParty(h1, h2, "", "")` + `setSkinset(costume, heroes)` (default `("default", "")`) +
  `loadMapKeepTeam("Z")`; otherwise `loadMapChooseTeam("Z")`. The names must be heroes of the build's herostat.
- **`--tour N`.** The order is `graph.json['reachable_from_new_game']` restricted to converted zones that have a
  world entity. It starts at `--start-zone` if given (rotated, or prepended if unreachable). For stop *i*:
  - `Scripts/x1/tour/<zone>.py` contains:

    ```
    # xml1-port tour stop i/n: <zone>
    waittimed(N.000 )
    loadZone("<next>", "" )
    ```

    The last stop has no `loadZone`.
  - The world entity `zonescript` in `Maps/<zone>.XMLB` and `.engb` is set to `x1/tour/<zone>`.
  - `<script filename="scripts/x1/tour/<zone>"/>` is added to its PKGB.
  - New Game loads stop 1.
  - `<out>/_tour.json` is `{dwell_seconds, count, start, order[], stops[{i, zone, next, script}], skipped{zone:
    reason}, note}`.

  The zones' own scripts do **not** run in tour mode. It is a load, render and spawn smoke test, and an original
  zone script could queue its own `loadmap` or movie (at most 2 pending console commands) and break the chain.
  Game-side timing per stop is dwell plus load time.

---------------------------------------------------------------------------------------------------------------

## 8. Acceptance and first builds (the orchestrator runs the game)

1. `python tools/build_xml1.py --out build/xml1 --no-movies --test-ini --start-zone
   nyc/alison/nyc1_1_1`. Expect exit 0 and validator errors = 0. In-game:
   - `nyc1_1_1` loads;
   - `grso_riot` spawns with its outline and pain/death sounds (`char/grso_m` aliases);
   - `music/nyc1_a` and `music/nyc1_c` play;
   - breaking props plays ZTRK death styles;
   - Magma appears in `nyc1_1_3`.
2. The same with `--tour 20`. The orchestrator walks `_tour.json` (about 150 stops) and records crashes or hangs
   per zone.
3. A full build (no `--no-movies`, no `--start-zone`): New Game → `r102` (Sofdec with the C1 stream) →
   `nyc1_1_1` with the `x1_act01` objectives. Then check a popup (`mansion/man2/chose_mission` → `x1/p018`), a
   packed var across a zone change and a save/load, and `endSideMission` from `jug_fb`.
4. `--only zones` after a full build must leave the characters, scripts and media outputs intact (carried over).

---------------------------------------------------------------------------------------------------------------

## 9. Known risks and open items

**Unverified in-game (offline evidence only):**

- ZTRK playback on PC (XML2 never shipped a working track);
- 44.1 kHz stereo music streams;
- Sofdec with the extra C1 stream;
- runscript popups;
- mission objectives via `setCurrentAct` 1..9 (XML2 uses 1..5; changing act purges item categories 3 and 4);
- persistence of the game-flag packing;
- `loadMap` versus `loadMapKeepTeam`;
- empty-NAV hub zones with NPCs;
- `x1_` anim-DB renames (internal `<file>_skel` names are unchanged);
- IMA re-encode quality (median about 31 dB, worst 17 dB).

**Stats capacity.** XML1 mode leaves about 60 of 296 name slots. The later hero conversion must fit in them and
stay within 99 shared talents.

**Keep-list completeness.** The 20 XML2 npcstat entries kept were found by exe-string search. Names built at
runtime by XML2 heroes, menus or scripts that remain active may be missing. The characters owner must scan for
them, and V5/V6 only catch static references.

**Collision policy.** XML2 wins for 140 models and 189 textures, so some XML1 props render as XML2's same-named
assets. Namespacing props is a later decision.

**Script-engine pools.** 620 statement nodes per load are unconfirmed as a per-zone limit. `mastermold2` (906
statements) is the first thing to watch.

**Not handled in phase 1:**

- forced per-mission heroes;
- `addHero`;
- solo mode;
- XML1 per-zone music overrides;
- ~~automaps~~ (section 26);
- danger-room and review data;
- the 34 differing value codes;
- XML1-only combat handlers with no XML2 counterpart (section 22: they run as `%default%`, the moves without their
  logic; the triggers, `ch_throw` and `atk_damage_scale` are rewritten).

---------------------------------------------------------------------------------------------------------------

## 10. Integration (2026-09-27)

### 10.1 Commands and results

| Build | Command | Result |
|---|---|---|
| full install (movies) | `python tools/build_xml1.py --out build/xml1_full` | exit 0; 211 s from an empty `<out>` (2.37 GB base copy), about 70 s on a rebuild; 8,070 files registered; module errors 0; validator PASS, 0 errors, 54 warnings (10.3) |
| start-zone test | `python tools/build_xml1.py --out build/xml1 --no-movies --test-ini --start-zone nyc/alison/nyc1_1_1` | exit 0; 164 s from an empty `<out>`; 8,038 files; validator PASS, 0 errors, 81 warnings; `new_game.py` = `setCurrentAct(1)` + `loadMapKeepTeam("nyc/alison/nyc1_1_1")`; windowed `alchemy.ini` and `.codegpt-game.json`; regression guard 70/70 |
| tour | `python tools/build_xml1.py --out build/xml1_tour --no-movies --tour 12` | exit 0; 162 stops, 0 skipped, `<out>/_tour.json` written, V11 ok; validator PASS, 0 errors, 81 warnings (the 54 below plus 27 V9 "movie missing (--no-movies)"; tour mode does not run zone scripts) |

Also checked: `--only zones` on the full build leaves all 21,366 files byte-identical (section 8.4);
`python -m xml1build.validate_selftest --movies` passes (rc 0: positive, about 45 injected defects all reported,
restored == positive, tour, movies). The module self-tests pass on the full build: `characters_selftest` (0
errors), `zones_selftest` and `scripts_selftest` (T1-T7).

**Regression guard (the in-game-proven `nyc/alison/nyc1_1_1` test).** Run `python
tools/xml1build/regress_nyc1.py <out>` (read-only; 70 checks, exit 1 on any failure). All 70 pass on `xml1_full`
and `xml1`. It checks:
- `Maps/nyc/alison/nyc1_1_1.{XMLB,engb,CHRB,NAVB,BOYB,IGB}` are byte-identical to the proven `xml2_test` copies;
  the world has `soundfile="nyc1"` and `zonescript="nyc/alison/nyc1_1_1"`.
- The zone package covers all 88 proven entries (in the SPEC entry forms) and all of its entries resolve.
- `grso_riot` appears once in npcstat `.XMLB` and `.engb`, with skin 19810, characteranims 53_grso, the proven
  attributes and children, and `sounddir="grso_m"`. `grso_riot_19810(_nc).PKGB` contain every proven entry.
- `Actors/19810.IGB`, `Actors/53_grso.IGB` and `UI/HUD/characters/19810.IGB` are byte-identical to the proven
  `grso_riot_scheme` files. The IGB contains `19810`, `19810_outline` and `19810_skel`, and no old node name.
- `nyc1_m`, `nyc1_d`, `nyc1_v` and `grso_m` are byte-identical to `research/sound/out/all_ima` and to the proven
  `xml2_test` banks. `nyc1_a` and `nyc1_c` are the fixed-layout 44.1 kHz music banks (10.2).

### 10.2 Integration fixes

- **Carry-over of hooked files** (`build_xml1.plan_carry`, section 2 step 2). This was a confirmed bug: a
  `--tour` build followed by `--only media` restored XML2's `new_game.py` and swept 302 tour-stop Maps files and
  162 PKGBs (validate: 402 errors). Now:
  - With the same hook options, the hooked files are carried and re-hooked.
  - With different options, their content module is re-run.
  - A lost `history` is inferred from the path.

  Tested by unit cases, by `--only media --tour 12` on a tour build (tree byte-identical, V11 ok), by `--only
  media` without hooks on a tour build (scripts and zones re-run, the 162 tour scripts swept, V6 and V10 ok), and
  by `validate_selftest` (a start-zone build carried under `--only media --start-zone`).
- **Music fallback.** `media.FIXED_MUSIC_DIRS` gained `sound/music0x20/_previous_attempt/banks/eng` as a last
  resort, so a default build stays green while `fix_music.py` regenerates `banks/eng`. Every candidate is still
  checked against the Xbox original. With the finished batch, all 59 music banks come from `banks/eng` at 44.1 kHz,
  and all pass.

### 10.3 Remaining validator warnings (full build: 54, none from a pipeline bug)

| Check | Count | Classification |
|---|---|---|
| V5 | 3 | XML2 retail's own undefined talents (Gambit `dodge`, sabretooth_hero `wolv_slice`, ScarabApoc `elemental_resistant`) |
| V6 | 9 | Inherited from XML1: 4 zones without a soundfile, menu/main_back without `menu_m`, 20 prevzone names XML1 never shipped, 1 ambiguous demo-copy prevzone. Deferred: 47 zones without a zonescript (no `setCurrentAct` on entry). Engine risk: 37 zones whose XML1 .nav is empty (34 with characters) |
| V7 | 41 | Inherited XML1 dead references: missing conversations, dialogs, zones, data scripts and objectives, `gambit_free.py`'s nested `startConversation`, and `disallowResponse` with an argument. XML2 base content: `common/conversationlighton.py`. Engine risk: the mastermold2 620-node pool warning (907 statements) |
| V8 | 1 | 188 sound names in 77 zones that do not resolve against XML1's own banks either (inherited) |
| V9 | 27 | Tour and `--no-movies` builds only: startMovie targets are not installed, by design |

### 10.4 Owner deviations from sections 4-5 (recorded; each backed by exe or data evidence)

- **characters**
  - Weapon accessory BoltOns use `ebolton_altweapon` (`ebolton_weapon2` is not in the slot table at 0x6d6530).
  - BoltOn `onlyprecache` is kept (0x44a868).
  - `Data/boltonactoranims.XMLB` gets an append-only merge (`MERGE_BOLTON_ANIMS`).
  - Extra packages: 46 zone monster_skin variants, 14 `<name>_xml` packages (replacing XML2's beast_xml and
    frost_xml), and 11 replaced XML2 leftover style packages.
  - 258 XML2 npcstat entries are dropped.
- **zones**
  - It also owns `Packages/generated/maps/package/permanent_fightstyles.PKGB` (append-only: fightstyle_villain).
  - It adds a bare world entity to `cinematics/beastlab2_cine` and `muir_is/muir2/muir_brig`.
  - A soundfile with no bank on either disc takes its campaign twin's soundfile (6 zones).
  - Precache paths are normalised; `bolton/x` becomes `models/bolton/x`.
  - Zone packages also list the conversations and popups their scripts start.
- **scripts**
  - `zone_script_ref` falls back to the zone's own-name script (17 zones).
  - `zone_act` falls back to the mission's mapload.
  - Console code in dialogs and UI files is compacted.
  - p091 and p092 are retargeted to `x1/missions/begin_sewers1` and `loadMapKeepTeam('mocap/mocap4/briefing_1_7_1')`.
- **media**
  - XML1 music comes from `tools/fix_music.py` fixed-layout banks, not `all_ima`. The all_ima layered banks play
    both layers interleaved through 0x595d60.
  - Controls: `XML1BUILD_MUSIC=fixed|ima`, `XML1BUILD_MUSIC_DIR`, `XML1BUILD_MEDIA_DEEP`.
  - Subtitle lives are clamped to the next item.
  - New shared key `sound_bank_sources`.
  - New engine limit: at most 64 simultaneously loaded ZSND banks (0x594e50); the worst case is 16.

### 10.5 Not verified in game (the orchestrator's checklist)

- Movies with the C1 stream.
- 44.1 kHz stereo music and ZTRK death styles.
- runscript popups (p001-p092) and `setCurrentAct` 6-9.
- Persistence of the packed game flags across zone changes and saves.
- The 37 empty-NAV zones.
- mastermold2's statement count.
- The New Game roster mismatch (XML2 gives magneto/cyclops/wolverine/storm).
- The 6 fixed accessory BoltOns and the onlyprecache psi whip.
- Juggernaut's helmet (starthide is ignored).
- In `--no-movies` builds, about 30 mission scripts keep a `startMovie`+`waitsignal` pair. Whether XMen2.exe
  fires the signal for a missing .sfd is unknown, so use full builds for campaign play-through tests.

Section 11.9 extends this checklist.

---------------------------------------------------------------------------------------------------------------

## 11. Review fix round 1 (2026-09-27)

Ten review findings, eight distinct problems (two pairs were duplicates). Each was checked against the exe and
data before it was fixed; none was rejected.

### 11.1 XML2 front end kept (`menu/main_back`)

XMen2.exe loads the main-menu backdrop itself at boot (`loadmap menu/main_back`, string 0x6a3774), before New
Game can run; `xml2_test` ran with XML2's files. `C.FRONTEND_ZONES` lists the zone and its XML2 files
(`Maps/menu/main_back.*`, `MotionPaths/menus/main_back.*`, `Packages/generated/maps/menu/main_back.PKGB`).
zones does not convert it (`zones_detail.json frontend_kept_xml2`, count `frontend_zones_kept_xml2`), its forced
imports never touch those paths, and zoneinfo keeps XML2's entry. `zones_converted` is now 197 (12 skipped + 1
front end). V6 errors if any of those files is registered this build or missing. The XML1 backdrop is not offered
behind a flag: it carries no campaign content.

### 11.2 XML1 -> XML2 schema conversions (`x1schema.py`, applied to every XML1 text import)

`ctx.import_x1_asset` (all modules) and zones' world-table merge run `ctx.x1_schema(root, rel)` before the
module's own patch; changes are logged in `ctx.schema_log` and reported by zones (counts `x1schema_*`).

- **Entity classes.** XMen2.exe registers 27 classes through 0x461080 (`x1schema.REGISTERED_ENTITY_CLASSES`;
  XML2 retail data uses 26 of them). An unknown class silently becomes the bare 0x70-byte `ent` (0x4611a0 falls
  back to 0x718444). Remapped: `harmtargetent` -> `affectableharment` (104 entities in 65 files, including the
  fire kill zone `harm_target01` of the proven `nyc1_1_1`), `lightningentity` -> `affectableharment` (7, XML2's
  own `ents_storm storm_p1_lightning` has the same attributes and that class), `scanturretent` -> `physent` (9 in
  8 files). A scan turret keeps health, structure, deathscript, spawnscript, deathspawn, deathsound and
  targetlockable, so the HAARP (`haarp_ext02`, `haarp_ext04`) and Hive (`hive1_1_1`) progression deathscripts can
  fire; it gets its `turretweapon`'s model (XML1 draws the turret with it; entity form without `models/`). Turret
  aiming and firing are lost (deferred). V3 errors on any unregistered classname in a registered XMLB.
- **Renamed attribute.** `persistant` (default.xbe string; not in XMen2.exe) -> `persistent` (XMen2.exe 0x68683c).
- **Effect colours.** XML1 `red`/`green`/`blue` quadratic curves (`a1 b1 c1 a2 b2 c2 [max min]`) become XML2's
  packed `startColor1/2`, `midColor1/2`, `endColor1/2` (the only colour names XMen2.exe reads, 0x681ca4-0x681cbc):
  each channel is sampled at t = 0 / 0.5 / 1, clamped, truncated to a byte and packed A<<24|B<<16|G<<8|R (unsigned
  decimal). A constant `alpha` is folded into A and dropped; a varying `alpha` stays (XML2 retail keeps 3,728 alpha
  curves) with A = 0xFF. `x1schema.selftest` reproduces XML2's own conversion of the six XML1 test effects exactly
  (red/green/yellow/bluesquare, grnspot, testpuff; `test/axis` was re-authored for XML2). 2,309 primitives in 709
  effect files are converted; V3 errors on an XML1-sourced effect that keeps `red`/`green`/`blue`. Varying colour
  curves are approximated by three keys (in-game check).
- **Combat styles** (`data/powerstyles/*`, `data/fightstyles/*`, `data/shared_nodes`): `combat_events.rewrite_style`
  re-points events built on XML1's `blast_ranged` at XML2's `blast` (+ `dmgmod_popup`), renames `ch_throw` ->
  `ch_pickup_throw` and the affecter `atk_damage_scale` -> scale `atk_damage` (section 22).
- `tools/xml1build/schema_check.py` replaces `tools/schema_diff.py`'s substring test with whole-string matching
  (NUL-terminated, NUL-preceded or 4-aligned). On the full build it finds no further confirmed renames: the other
  XML1-only entity names are XML1's own typos (`actound`, `qacttargets`, `healh`), turret attributes, the music
  overrides (deferred) and powers-rework attributes (`func_*`, `iconrows`, ...).

### 11.3 Items: only referenced XML1 items, in XML2 schema

XMen2.exe's item parser (0x47aeff) knows the types item(0), potion(1), equipment(2) and money(3); `frequency`,
`group`, numeric `class`/`quality`, `unique` and `<activepowerup>` are never read. zones now appends only the XML1
items that converted content names in `inventoryitem` (zones, entity files, `common_ents`/`item_ents`), translated
(`zones.ITEM_TYPE_MAP`, `translate_item`): `XP` -> one `XP_<count>` item per XML1 pickup amount with
`setXP('_ACTIVATOR_',<count>)` (`--xp-curve xml1`, section 23.1) or `awardXPToPlayable(5000)` (`xml2`), `SKILL` ->
one `SKILL_<xp>` item per pickup with `setXP('_ACTIVATOR_',<one level step at the zone's level>)` (XML2 has no
skill-point call; section 32), `STAT` -> `permanentStatBoost('_ACTIVATOR_','body')` (XML2's stat-booster call), all
`type="item" activateonpickup="true"`; `ASTRAL_STONE` becomes a plain item (its bonus is deferred). The other 114
XML1 items are not added, so XML2's random-drop pool is unchanged. The items package gets only those items'
pickup models. V6 errors on an XML1 item with a type XMen2.exe does not parse or with `activepowerup`; an
`inventoryitem` naming no item is an error unless XML1's table lacks it too (`money` in `item_ents`: inherited).

### 11.4 Zone literals normalised

`scripts_transform.normalise_zone_literals` lowercases and `/`-normalises the zone literal of `loadZone`,
`loadMapKeepTeam`, `loadMapChooseTeam`, `loadMapAddTeam`, `loadMap` and `restorelastzone` (also inside
`blackbirdMenu`'s stored code) and both paths of `cinematicStart`, in every installed script (86 literals) and in
inline data code (`rewrite_data_tree`). V7 warns on any XML1 zone literal that is not normalised (0 in the build).

### 11.5 Statement pool: packed counters narrowed

`scripts_transform.narrow_packed` rewrites the research's 8-bit packed counters to their real width in place
(read terms, write groups, literal writes and mission-start clears of the high bits are deleted; sign-extension
constants rescaled; the game-var layout is unchanged; any other reference to a narrowed bit makes it refuse).
`scripts.NARROW_PACKED`: `m:corecount` 8 -> 3 bits (0..7; +1/-1 only in core_on/off, 3 switches per mastermold
zone, the mission var carries 1 -> 2, so at most 6) and `m:stage` 8 -> 5 signed bits (-16..15; literals -1..8,
every increment guarded by the boss health thresholds). `scripts_transform.selftest` runs the narrowed blocks
through a small interpreter and checks every value of the range round-trips (including values stored by the old
full-width code). 132 installed scripts change (104 blocks). Per-zone estimate: `mastermold2` 907 -> **613**
(pool 620), `mastermold1` 613 -> 365, `nyc1_1_2b` 556 -> 520, `mag_nyc3` 549 -> 513; `muir_in3` 540 and
`nyc3_2_1` 532 are unchanged (their load is `act3mssn`/`temp` bit-field code). `zones_over_statement_pool` = 0.

### 11.6 blackbirdMenu fallback

The 76 `blackbirdMenu` calls stay by default. `--blackbird chooseteam` (or `XML1BUILD_BLACKBIRD=chooseteam`)
rewrites the 64 of the form `blackbirdMenu(a, "loadMapKeepTeam('z')", b)` to `loadMapChooseTeam("z")` (what XML2
retail's `new_game_hard.py` uses); both variants lint clean. Tested with `--only media --tour 12 --blackbird
chooseteam` on the tour build (scripts re-run automatically, V11 ok) and back.

### 11.7 Regression guard

`regress_nyc1.py` accepts exactly two kinds of difference from `xml2_test`'s zone file: the x1schema fixes (here
one: `harm_target01` harmtargetent -> affectableharment) and test-only spawn instances the orchestrator added to
the live `xml2_test` copy after the proven run (`tools/add_spawn_inst.py`; an `<inst>` in neither our file nor the
XML1 source). An `<inst>` the XML1 source has but ours lacks still fails. It also checks the zone's packaged
effects carry XML2 colours only, and accepts the tour hook's zonescript. 71/71 on `xml1_full`, `xml1` and
`xml1_tour`.

### 11.8 NPC combat scaling (deferred by default, opt-in fallback)

The finding's premise is only partly right: XML1 NPCs are not all level 1-4. 121 XML1 npcstat entries carry
XML1's own level (1..40) and strength/body/mind/speed; `grso_riot` is level 1 because it is the first-zone riot
cop. What they lack is XML2's `specific_attack/defense/health` (read at 0x4ba450..0x4ba4fd via atoi) and the
`monst_dmg_*` talents. Default: kept as XML1 authored them, deferred with the reason (in-game check). `--npc-scaling
xml2curve` gives the 112 XML1 enemies with a level XML2 retail's per-level curve (median per level,
interpolated; e.g. L1 157/3/19, L15 568/31/152, L40 2494/189/612) and `monst_dmg_high` at their level; XML1's
`npchealthscale` still multiplies boss health.

### 11.9 In-game checklist additions (order: first the boot path)

1. Boot to the main menu (XML2's backdrop) and start New Game.
2. `nyc1_1_1`: the fire kill zone (`harm_target01`, now affectableharment) hurts; effect colours look right (fire,
   sparks, break effects); pick up a health/energy pack.
3. Right after `mansion1a`: HAARP briefing -> team menu -> `haarp/ext/haarp_ext01` loads. If the menu never runs
   the stored code, rebuild with `--blackbird chooseteam`.
4. `haarp_ext02`: destroy the HAARP tank turret (now a physent), then leave to `haarp_ext03`; `haarp_ext04`: the
   turret again opens the HAARP interior; `hive1_1_1`: destroying the turrets completes the objective.
5. Early: `mastermold2` (613 statements) and `nyc1_1_2b` (520): all scripts run (no dropped lines); the mastermold
   core counter reaches 3.
6. Pick up the XP / SKILL / STAT pickups (`hive2_2_4`, `haarp_ext03`, `arb2_1`) and a keycard.
7. XML1 enemies vs the XML2 stand-ins; if trivial, rebuild with `--npc-scaling xml2curve`.

### 11.10 Results (validator 0 errors on every build)

| Build | Command | Result |
|---|---|---|
| full install | `python tools/build_xml1.py --out build/xml1_full` | exit 0, 50-65 s rebuild, 8,064 files; validator PASS 0 errors / 53 warnings; regress 71/71 |
| start-zone test | `python tools/build_xml1.py --out build/xml1 --no-movies --test-ini --start-zone nyc/alison/nyc1_1_1` | exit 0, 8,032 files; PASS 0 / 80; regress 71/71 |
| tour | `python tools/build_xml1.py --out build/xml1_tour --no-movies --tour 12` | exit 0, 162 stops, `_tour.json` written, V11 ok; PASS 0 / 80; regress 71/71 |

Full-build warnings (53, none from a pipeline bug): V5 3 (XML2 retail's own undefined talents); V6 9 (4 zones
without a soundfile as in XML1, 1 ambiguous demo prevzone, 20 prevzone names XML1 never shipped, 36 empty-NAV
zones, 47 zones without a zonescript (deferred), `inventoryitem="MONEY"` that XML1's items table lacks too); V7 40
(XML1 dead references to conversations, dialogs, zones and scripts that are absent on the disc too, XML1's
`disallowResponse` with an argument, XML2's `common/conversationlighton.py`); V8 1 (188 sound names that resolve
against XML1's own banks neither). Tour and `--no-movies` builds add 27 V9 warnings (movies not installed, by
design). Module self-tests pass: `zones_selftest`, `scripts_selftest` (T1 compares against research output + the
transforms), `characters_selftest`, `validate_selftest --movies` (with negative cases for every new check).

---------------------------------------------------------------------------------------------------------------

## 12. Review fix round 2 (2026-09-27)

Seven findings. Each was checked against XMen2.exe, default.xbe and the data before it was fixed; none was rejected.
Two premises were corrected on the way: act 9 is not only boss/demo/test missions (12.7), and the sewers hub and
the arbiter interior are single-act in the campaign (12.7).

### 12.1 Conversation speaker alias `%ALISON%` -> `%MAGMA%`

default.xbe resolves `%ALISON%` itself (0x61bc6 `_stricmp` against "%ALISON%" 0x3cc014, then the stats entry "Magma"
0x3cc00c); XMen2.exe has no such string, and its built-in tokens are `%PLAYER%` `%X-TEAM%` `%NULL%` `%END%` `%MORE%`
`%CONTINUE%` `%BLANK%` (0x685d18..0x685d5c). `scripts.rewrite_data_tree` rewrites the token (case-insensitive,
`scripts.SPEAKER_TOKEN_ALIASES`) in the `text`/`textb` attributes of every conversation it patches (zones' forced
imports, both `.XMLB` and `.engb`). Result: 213 lines x 2 files rewritten, no `%ALISON%` left.
**Label (2026-09-29, section 18.1):** default.xbe keys the speaker to Magma but labels the line with its string 503
"Alison" (`0x61c88`; `data/strings.eng`), so XML1 showed "Alison" where the port shows "Magma" on the party-Magma
lines (XMen2.exe takes label and talk-animation entity from one key: an engine alias would be needed). The NPC
Alison's own two lines are renamed to her speaker entries, labelled "Alison" (18.1); V6 accepts `%ALISON%` only there.
**V6** checks every `%TOKEN%` of every registered conversation: a built-in or a stats name passes; the alias or an
XML1 stats name the build lacks is an error; a token XML1 could not resolve either is an inherited warning. Full
build: 3,601 tokens, all resolve.

### 12.2 ProfXAstral added as a hero used as an NPC

`characters.planned_stats` now also counts XML1 herostat names (not XML2 heroes) that live content looks up by name:
conversation speakers `%NAME%` and `unlockCharacter` / `setInCampaign` literals (research scripts and inline rewrite
values; `_x1_hero_name_refs`). This adds `ProfXAstral` (skin 15104, `11_profxastral`, `ps_profxastral`, `profxa_m`,
packages `profxastral_15104(_nc)`); heroes as NPCs are now beast, frost, jubilee, magma, **profxastral**, psylocke;
234 stats names (cap 296). A name miss resolves to index 0 (0x44acc0 -> 0x44ad7e `xor ax,ax`), which is why the
speaker lines had no name. `unlockCharacter` of npcstat heroes (magma x45, frost, beast, profxgladiator,
profxastral) still unlocks nothing playable until the hero conversion (12.6).

### 12.3 Remapped scan turrets keep XML1's fixed mount

`x1schema.convert_entities` gives every `scanturretent` -> `physent` the flags `nogravity`, `nopickup` and `nopush`
= true unless the entity sets them (`x1schema.TURRET_MOUNT_FLAGS`; `CLASS_REMAP_LOSSES` updated). Evidence: every
XML1-authored physent of the same tanks has them (haarp_ext02/04 tank_base, tank, tank_turret_haarp_sp_d; hive1_1_1
tank_vehicle_hex01-04, tank_turret_sp_d); `haarp/ext/tank_ready` runs `setNoClip('tank_turret','FALSE')`, and the
turret deathscripts gate progression (`tank_destroyed`, `setGameFlag('haarp3',1,1)`, `turret_death`). Applied to the
3 turrets that lacked them (haarp_ext02, haarp_ext04, hive1_1_1; the gun_tripod remaps already had them).
**V3** errors on any physent with a `turretweapon` without the flags; `zones_selftest` I asserts the three.

### 12.4 XML2's Xtraction network switched off (zoneinfo)

XMen2.exe registers every zoneinfo entry with `extraction="true"` (0x468130, `_stricmp` 0x468155, at most 31 at
0x46817d) and parses `towncenter`/`act`/`savename`/`description`/`mapx`/`mapy` (0x467f60). XML2's `extractionPoint`
menu (0x4a6b50) offers `openmenu('worldmap')` over that list, `extractionPointChange(%d,0)` (0x4a7020: pushsidemission
+ team menu with `restorelastzone('1')`) and `saveloadProcess(4)`. XML1's menu (default.xbe 0x9f110) had no world map
(team change, save, load, danger room, item shop), and no XML1 zoneinfo entry has extraction/towncenter/mapx. So
`zones.build_zoneinfo` strips `extraction`, `towncenter`, `mapx` and `mapy` from every XML2 entry (30 entries, 5 town
centres) and registers no XML1 zone: an XML1 Xtraction beacon keeps team change and save, and its world map lists no
destination. **V6** errors on any zoneinfo entry with those attributes that names a non-XML1 zone. The XML1 menu
extras (load, danger room, shop) are deferred. The SPEC/scripts-research claim that zoneinfo `act` is unused is
superseded: it is read for extraction entries (none remain).

**Superseded by section 15 (same day):** stripping every town centre crashes XMen2.exe at boot, and acts 6-9 need
town centres of their own. `zones.STRIP_XTRACTION` is False; XML2's 5 town centres stay, its 25 other destinations
are stripped, and each act 6-9 gets an XML1 hub as town centre. **V6** warns (not errors) on XML2 zones that keep the
attributes and errors on a selectable act without a registered town centre.

### 12.5 XML1 mission animations: `EA_MISSIONn` -> `EA_ZONEn`

XMen2.exe has no `ea_mission*` enum (no 'ea_mission1' string); its equivalent is `ea_zone1..20` (0x683170; XML2
`Data/shared_anims.XMLB` ea_zoneN = 'zoneN', played from XML2's per-zone `zone_*` anim DBs). XML1 used
`ea_missionN` = 'missionN' from its per-zone `mission_*` anim DBs. Now:
- `scripts_transform.rename_mission_anims` rewrites `EA_MISSIONn` -> `EA_ZONEn` (case kept, n = 1..20) and the
  `(set|loop)CombatNode(..., "missionN")` literal -> `"zoneN"` in every installed script (263 literals in 84 scripts)
  and, through `scripts.rewrite_data_tree`, in every data tree (zone `monster_spawnscript` idles, powerstyle
  `animenum` of ps_dangerroom_robot and ps_marrow, inline code);
- `characters` renames the length-prefixed IGB strings 'missionN' -> 'zoneN' in place (shorter, fits the padding;
  `rename_mission_anims_igb`) in the 43 XML1 `mission_*` anim DBs: 296 anims ('mission9_extra' is not an enum
  anim and stays).
**V7** checks every animation enum literal (EA_* string arguments in scripts, `animenum`, EA_* in inline data code,
1,040 literals / 182 distinct) is a whole ea_* string of XMen2.exe: `ea_mission*` is an error, the 12 XML1-only
flying-carry / Juggernaut-grab enums of the added shared nodes are deferred warnings (powers rework), `EA_NULL`
(sewers/hub/mor_stealing2.py, in neither exe) is inherited.

### 12.5a Non-combatant NPCs: `LOOP_WAKE` spawn animations never end in XMen2.exe (npc-loop fix)

In-game report: "some NPCs never stop attacking" (enemies behave). Engine facts (XMen2.exe, base 0x400000):

- A stats entry without `team` is team **none**: the stats object defaults it to 0x1c (`mov dword [esi+0x2a0],0x1c`
  at 0x4bce9b) and 0x45fbd0 maps only `hero` (0x1d), `enemy` (0x1e) and `altenemy` (0x1f); anything else, e.g.
  XML1's `neutral`, is none. So XML1's team-less civilians equal XML2's `team="none"` NPCs.
- The AI never attacks with team none: the default brain 0x51dfe0 returns before its targeting block when
  0x41a220 == 0x1c, the attack decision 0x514080 needs team != none **and** `willflee` clear (`cmp byte
  [ai+0x46d],1` at 0x51410c), and the alert helper 0x5078b0 has the same gate. `FightMove aitype`/`aireusetime`
  (parser 0x4f6b80: byte +0x13d from the 20-name table at 0x6db940, float +0x140) only feed the power table
  0x50fb70, which reads the stats `power1..4` slots (XML1 NPCs have none -> "no powers" flag 0x40 at
  +0x2b9). `noncombat` (bit 1 of +0x144) is the combat-off gate 0x4f575c. None of these makes an NPC loop.
- XMen2.exe has **no flee behaviour**: the AI's `fleedistance` (+0x470, filled from the spawner/stats at 0x5034d2,
  default 100 at 0x51658a) is never read by any code (the only `fcomp [+0x470]`, 0x43fa10, is another class);
  `willflee` (+0x46d) is only tested at 0x507925 / 0x50e5ef / 0x51240a / 0x51410c, all gates that suppress
  attacking. XML2 retail ships no `willflee` stats and one spawner with `monster_willflee="false"`.
- `playanim(<EA_*>, ent, "LOOP_WAKE", ..)` (handler 0x4a8a20; modes STOP=1 LOOP=2 LOOP_WAKE=3 from 0x68a880;
  the play routine 0x430d40 restarts the node while the mode is 2 or 3) is ended in exactly two places, both
  in the combat AI: 0x5100d0 (after target acquisition in 0x514080) and 0x513ff3 (alert scan 0x513c50). default.xbe
  has the same two sites (`cmp [ent+0x304],3` at 0x1085b7 / 0x10b964), so XML1 woke its looters through the
  civilian AI (flee) that XML2 dropped [inferred, not decompiled].

Consequence in XML1 data: the riot looters (`nyc/riots/prep_smash_down`, `prep_jump_smash`, `prep_smash_side`,
`prep_smash_side_pipe`: 23 spawners in nyc3_1_1/2/3 and nyc3_2_1 - 16 + 5 + 1 + 1; nyc3_2_1 is an `.xml`-only
zone, so the owner index reads `.eng` zones and `.xml` zones without an `.eng` twin -, team none,
`monster_willflee="true"`, fleedistance 160-250)
swing their bat forever; the Weapon X lab techs (inline `playanim ('EA_MISSION3|4', '_OWNER_', 'LOOP_WAKE', '')`,
8 spawners in wx1_1..3) work forever. `prep_mutant` (Simon) is ended by its act script `mutant_rescue`
(`loopCombatNode(.., "stop")`) and is left alone; enemies' LOOP_WAKE (astral `scarymonster`) is woken by the AI.

Fix (scripts module, XML2's own spawn-script idiom - 12 XML2 spawnscripts play an anim, `waittimed`, then act;
55 XML2 inline attributes contain `waittimed(..)\n\r..`):

- `scripts_transform.bound_unwakeable_loops`: the **last** statement `playanim(<anim>, "_OWNER_", "LOOP_WAKE", x)`
  becomes `LOOP` + `waittimed ( 15.000 )` + the same call with `STOP` (node `gen_anim_stop` 0x693de4;
  `UNWAKEABLE_LOOP_SECONDS`). A non-final statement is left and reported (the wait would delay what follows).
- `scripts.spawner_unwakeable(ctx, attrs)`: a monsterspawnerent whose effective team (`monster_team`, else the
  XML1 stats team, else none) is none/neutral and that has no `monster_actscript`. `unwakeable_owner(ctx, ref)`:
  every XML1 spawner running the script file is such a spawner (index `_spawn_script_owners`, English zone
  files). Applied in `_base_text` (script files) and in `rewrite_data_tree` for inline `monster_spawnscript`
  code (`INLINE_SEP`-separated, as XML2 writes it). Counts `unwakeable_loops_bounded`,
  `loop_wake_spawn_scripts_kept`.
- **V7** `_v7_unwakeable_loops`: from the built zones and stats, a LOOP_WAKE `_OWNER_` animation in a spawn
  script or inline spawn code whose spawners are all non-combatants without an act script is an error (XML1
  output) / note (XML2's); mixed owners warn. Notes list the XML1 npcstat entries keeping willflee/fleedistance
  (`x1_npcs_willflee`, no flee AI) and the team-none XML1 NPCs with a fightstyle talent the AI can never use
  (`x1_noncombat_npcs_with_fightstyle`). Counts `loop_wake_spawn_scripts`, `loop_wake_inline`,
  `loop_wake_unwakeable`.

Not changed (no engine reason): stats `team` (default is none), fightstyle talents, `ps_civilian`
(`civ_carry_tv` is noncombat, aitype null; `civ_cower`/`civ_spray` that XML1 scripts name never existed in
XML1's ps_civilian either - inherited), converted FightMoves without aitype (the AI only uses `power1..4`).

### 12.6 Forced heroes (mitigation; the hero conversion is the next phase)

(Since section 19 this is the `--forced-teams menu` build and the else branch of every seat block: what the port
does without xml2-fix `[Game] ForcedTeams=1`.) Retail XML2 has no script function that adds or removes a party member (the only related entries are loadMapChooseTeam,
isActorOnTeam, setTeamInvisible, swapInStump, extractionPointLite). `scripts.forced_hero_missions` lists the 49 XML1
missions with REQUIREDHERO entries or maxheros < 4; `scripts_transform.choose_team_in_bodies` turns the
`loadMapKeepTeam` of every copy of their start body (x1/missions/begin_<m> and the copies inlined in briefings and
zone scripts, matched by the `# ( "XML1 beginMission(m)" )` marker and the exact body) into `loadMapChooseTeam`:
73 starts in 73 scripts. blackbirdMenu starts already open the team menu and are unchanged. This includes New Game
(alison: wolverine+cyclops, maxheros 2): `Scripts/menus/new_game(_hard).py` now end with
`loadMapChooseTeam("nyc/alison/nyc1_1_1")`, as XML2 retail's own `new_game_hard.py` does; the `--start-zone` and
`--tour` hooks still use loadMapKeepTeam.
**Next phase: the hero conversion**, in this order: magma (every mansion hub mission and briefing is Magma-solo:
25 of the 63 reachable missions), frost, profxastral, profxgladiator, beast, jubilee. It gates hub, astral and
briefing fidelity; until then the unlocks of these names unlock nothing playable.

### 12.7 Act on zone entry (scripts plan step 6, completed)

`scripts.act_on_entry_plan` (pure provider; `zone_script_ref` and `zone_act` use it). A zone's campaign acts are
the acts of its zone_acts.json missions minus the non-campaign ones, plus the campaign missions that start in it
(graph.json `mission_start_zones`), else the union of its predecessors' acts (graph.json `zone_edges`, fixed point).
Non-campaign: the 22 boss_*/demo/*test* missions, and 17 missions graph.json proves are not started from New Game
(only the XML1 debug level list `ui/menus/map_list`, `missions.xml` or their own files name them: arbiter_flood,
nuke_col, sewers_gambit, sewers_hub2, icetunnels, status_meeting, ...). This corrects two premises: act 9 also holds
real campaign missions (asteroid_*, astral3, astral_sk, mansion8), so "ignore act 9" would be wrong; and the sewers
hub [1,6] and arbiter interior [2,3] are single-act in the campaign (sewers_hub2 is begun only by the dead
missions/sewers_hub2 and sewers_hub5, arbiter_flood only by the debug list). For every zone reachable from New Game
whose zone script sets no act and that has exactly one campaign act:
- no zone script: generated `Scripts/x1/zones/<zone>.py` = `setCurrentAct(n)` (22 zones);
- a zone script used only by zones of that act and run by nothing else (no script-attribute value, script literal,
  dialog option or inline-rewrite target names it): `setCurrentAct(n)` injected as its first statement, in
  rewrite_scripts' format (17 zones);
- otherwise a generated wrapper `x1/zones/<zone>` = `setCurrentAct(n)` + a copy of the zone script (6 zones: the
  arb3_x check_timer / arb3_1 / arb3_2 scripts shared with demo copies or other users, haarp_ext_boss,
  sewers1_1_2); the original stays installed for its other users.
45 more zones now set their act on entry. Still deferred (warned by V6): `astroid_m/visit1/asteroid2_1`, `2_2`
[1, 9] and `mansion/man5/mansion5_2`, `subbasement5` [5, 6], which are visited in two campaign acts; 29 zones not
reachable from New Game are left as they were. zoneinfo `act` = the entry act. Statement pool unchanged
(`mastermold2` 613, `nyc3_2_1` 533). **V6** errors on a reachable zone the plan gives an entry act whose zone script
sets none; `scripts_selftest` T1 checks the generated scripts, T7 `zone_act` against the entry act.

### 12.8 Also reported

- `zones` notes the 18 reachable zones that spawn XML2 stand-in heroes as NPCs (cyclops 6, phoenix 3, wolverine 3,
  colossus 3, storm/rogue/nightcrawler/gambit 2) and the 11 of them with a hero of XML2's New Game party
  (`zones_detail.json hero_npc_zones`).
- New counts: characters `mission_anim_dbs_renamed` 43, `mission_anims_renamed` 296, `hero_as_npc` 6; scripts
  `mission_anim_enums_renamed` 263, `forced_hero_missions` 49, `forced_hero_starts_choose_team` 73,
  `act_entry_x1_act_entry` 22 / `_inject` 17 / `_x1_act_wrapper` 6, `zones_no_act_on_entry_reachable` 4; zones
  `x1schema_turret_mount_*` 3, `zoneinfo_xtraction_entries_stripped` 30, `zones_spawning_xml2_hero_npcs` 18.

### 12.9 In-game checklist additions (after 11.9)

1. New Game: the team menu opens before `nyc1_1_1` (alison is a forced-hero start); pick wolverine + cyclops.
2. `nyc/alison/nyc1_1_2b`: use the Xtraction point: team change and save work; the world map option shows no
   destination (and does not hang).
3. `mocap/mocap1/briefing_1_1_6_5` (New Game stop 7): the briefing characters play their `EA_ZONEn` mocap anims
   (renamed 'zoneN' in `mission_mocap1`); mansion hub NPC idles loop (e.g. `mansion2_1` sp_civiliankid_a01
   `EA_ZONE17`); Magma's speaker name and portrait show in `nyc/alison` and `man1a` conversations.
4. `haarp_ext02`: after `tank_ready` the turret stays on the tank, cannot be picked up; destroying it opens
   `zone_link02` (and `haarp_ext04` sets `haarp3`, `hive1_1_1` runs `turret_death`).
5. Save and reload inside `sewers/hub/sewers1_1_3` (generated act-entry script), `nyc/riots/nyc3_2_1` (injected)
   and `arbiter/a_int/arb3_3` (wrapper): the act objectives come back.
6. Duplicate heroes: in the hub zones that spawn a hero of the New Game party (`mansion/man2/subbasement2`,
   `mansion/dr_mag2/mag_nyc3` and `mag_nyc4`, `mansion/man1a/mansion1a_2`, `mansion/man3/hangar3` and
   `subbasement3b`, `mansion/man5/mansion5_1`, `muir_is/muir2/muir_in2`, `nyc/alison/nyc1_1_2b` and `nyc1_1_3`,
   `weapon_x/old/wx2_2`) watch for scripts addressing the NPC (cyclops / storm / wolverine) hitting the player's
   hero instead.
7. `astral/ast1` conversations `2_8_1`/`2_8_2`: ProfXAstral's speaker name shows.
8. npc-loop fix (12.5a), `--start-zone nyc/riots/nyc3_1_1`: the bat-swinging looters near the spawn stop after
   about 15 s and stand idle (before: forever); `weapon_x/wfb/wx1_1..3` lab techs stop typing after 15 s. The
   mansion students / Morlocks still sit and talk (LOOP by design); riot NPC Simon keeps cowering until used.

### 12.10 Results (validator 0 errors on every build)

| Build | Command | Result |
|---|---|---|
| full install | `python tools/build_xml1.py --out build/xml1_full` | exit 0, 78 s rebuild, 8,095 files; validator PASS 0 errors / 55 warnings; regress 71/71 |
| start-zone test | `python tools/build_xml1.py --out build/xml1 --no-movies --test-ini --start-zone nyc/alison/nyc1_1_1` | exit 0, 8,063 files; PASS 0 / 82; regress 71/71 |
| tour | `python tools/build_xml1.py --out build/xml1_tour --no-movies --tour 12` | exit 0, 162 stops, `_tour.json` written, V11 ok; PASS 0 / 81; regress 71/71 |

Full-build warnings (55, none from a pipeline bug): V5 3 (XML2 retail's own undefined talents); V6 9 (4 zones without
a soundfile as in XML1, 1 ambiguous demo prevzone, 20 prevzone names XML1 never shipped, 36 empty-NAV zones, the 4
multi-act zones without an entry act (deferred, 12.7), `inventoryitem="MONEY"` XML1 lacks too); V7 42 (the 40 XML1
dead references / XML1 defects / XML2 base content of 11.10, plus 12 deferred flying-carry / Juggernaut-grab enums
and the inherited `EA_NULL`, 12.5); V8 1 (188 sound names XML1's own banks do not resolve either). The start-zone
build adds 27 V9 warnings (no movies, by design); the tour build adds the same 27 and has no act-on-entry warning
(tour stops run no zone script).

Also checked: `--only zones` on the full build (exit 0, validator unchanged, regress 71/71); `python -m
xml1build.validate_selftest --movies` rc 0 (positive, negative with new cases for every round-2 check: `%ALISON%`
left in a conversation, an unknown `%TOKEN%` as inherited, a turret without `nogravity`, an XML2 zone back in the
Xtraction network, `EA_MISSION3` in a script, a generated act-entry script without its `setCurrentAct`; restored ==
positive, tour, movies); `scripts_selftest` T1-T7, `zones_selftest` (C: XML2 zoneinfo entries unchanged except the
Xtraction attributes; I: the three turrets) and `characters_selftest` (K: heroes as NPCs incl. profxastral) pass.

---------------------------------------------------------------------------------------------------------------

## 13. Engine limit: the IGB info cache (2026-09-27)

Found from the tour: `haarp/int/haarp2_3` (from `haarp2_2`) and `mansion/jugrnt/jugrnt01` (from `nyc/fb/nyc_fb1`)
never load. The zone-name buffer (CMap+0x1e0 = 0x72a758) switches to the target and about a second later back to the
previous zone, which reloads; no exception. Everything in both packages resolves. The one thing that separates them
from the zones that load is the number of `model` entries (178 / 153 versus 145 and below).

### 13.1 Mechanism (XMen2.exe, all addresses verified in the disassembly / Ghidra decompile)

- **Package loading.** `CPrecacheMgr` (singleton 0x7ae9c8, getter 0x563070, RTTI `.?AVCPrecacheMgr@@`) parses a
  `packagedef` (0x561d40, path `packages/<name>.pkgb`) and hands every entry to the precacher registered for its
  tag (constructor 0x562bc0 registers `combat_is`, `bigconvmap`, `actorskin`, `actoranimdb`, `model`, `texture`,
  `effect`, `motionpath`, `xml`, `nav`, `boy`, `zonexml`, `xml_talents`, `fightstyle`, `xml_resident`,
  `characters`, `zam`, `script`; packages load into numbered groups: 0 system, 2 permanent, 7-10 hero0-3, 0xb zone,
  0xc/0xd menus). A zone load (`CMap` vtable 0x68878c slot 0x50 = 0x484ce0) prints `Loading Zone Package...`
  (0x4851c0), then 0x486560 loads `generated/common_ents` and `generated/maps/<zone>` into group 0xb.
- **`model` entries go to one global cache.** The `model` precacher (`CIGBPrecacher`, vtable 0x69b070) reads
  `filename` (0x561040) and calls `CIGBInfoCache2::precache(name, group)` (singleton 0x7b7fb0, getter 0x56f9f0,
  vtable 0x69c034 slot 5 = 0x56ed00). The same cache serves motion-path files (0x57ae00), HUD heads (0x5f4ec0,
  `hud/hud_head_%s`), the playfield loader (0x588950) and every on-demand model load (`get` 0x56ebe0: a miss
  calls `precache(name, 1)` into group 1, which is only released on return to the menu, 0x401ba0).
- **The limit.** `CIGBInfoCache2` is a fixed pool of **200 records** of 0x90 bytes: constructor 0x56e9c0
  (`mov edx,0xc7` at 0x56e9d9, `cmp eax,0xc8` at 0x56ea18; live count at object+0x73ec, id table +0x73f0, mask
  +0x7710 = 0xff / 8 bits), free-slot scan 0x490d70 (`199 < i -> 200`), `precache` at **0x56ede5 `cmp
  [this+0x73ec],0xc8; jge 0x56f280`** (`xor eax,eax; ret`): with 200 live records a precache returns NULL and
  nothing is logged. Records are keyed `"%i:%s"` (0x69b634: group and normalised name; a lookup also tries the
  permanent group 2), so a name already cached in the same group or in `permanent` costs nothing, one cached by
  a hero package (group 7-10) is cached again for the zone.
- **Why the zone bounces.** The zone's own map IGB is the last `model` entry of its package (`model
  maps/<zone>`, entry 199 of 211 in haarp2_3); when the cache is full at that point it is the entry that fails.
  `Loading Zone igb...` (0x485458) then asks the playfield manager for it (0x48548b -> 0x588950 `get`, another
  NULL), the result bit 0x40 stays clear and 0x4854ac-0x4854c7 calls CMap slot 0xbc (0x4841b0: copy the name
  into CMap+0x1e0 and set the load-pending bit) **with CMap+0x60, the previously loaded zone**: the previous zone
  reloads (group 0xb was already released by `Clearing zone memory pool...`, 0x484832), and the tour script
  sends the game back to the failing zone forever. The debugger sees no exception because there is none.
- **Budget.** Resident outside the zone group with XML2's New Game party (magneto/cyclops/wolverine/storm,
  `tools/xml1build/igb_budget.py check`): `maps/package/permanent` 16 + `items` 20 + the 4 hero packages 15 =
  **51** (69 with the largest possible party; the team menu adds `menus/characters_heads` 22 while open).
  Budget 149 matches the tour exactly: `haarp2_1` with 145 records loaded, `haarp2_3` with 153 did not. NPC
  character packages load into group 0xb while the zone package is parsed (`CXmlCharacterPrecacher` 0x5613a0 at
  the `characters` entry -> 0x44b8f0 slot 0x28 -> 0x4bc100 `generated/characters/<name>_<skin>`), one entry
  before the map model, so their models (1-8 beyond the zone's own; `igb_budget.py check` column `+npc`) count
  before the map as well; the observed budget is 146-153 including them. XML2 retail never exceeds 106 model entries
  per zone package; 13 converted XML1 zones had 153-179 (`hive/h_int/*`, `mansion/jugrnt/jugrnt01` and its demo
  copy, `haarp2_3`). The related texture cache (`CSafeResMgrI<ITexture,192,8>`, 0x69ca84) is not near its limit
  (at most 21 `texture` entries per zone package). The XML1 Xbox executable's own cache size was not found
  (no matching constructor signature in `default.xbe`); XML1 evidently allowed at least 179 + resident.

### 13.2 What filled the packages: tile models

Every over-budget package is dominated by `models/tiles/<folder>/*` entries (64-98 of them). `CTileEntity` draws
an instance `T_<folder>_<S><H><T>_<F|W>_<V><d>` (zone XML `entinst type=<tileent>` / `inst name=`) with the model
`models/tiles/<folder>/<folder>_<sht>_<fw>_<v><d>`, built by 0x4c2460 with `"%s_%c%c%c_%c_%c%d"` (0x68ee70); a
breakable tile also names the other variant letters of its shape (damage stages, 0x4c2b52-0x4c2ba4) and, for
size letters C-E, the `<S>A<T>` shape (0x4c2400 / 0x4c2bc1). Nothing else ever names a tile model. XML1's own
bundles list whole letter sets per tileent (33 of the 64 `haarpint` files for `haarp2_1`, all 98 `hive` files
for `hive2_2_x`), and the pipeline's `tilemodelfolder` rule (section 5.3 step 5) added the **whole folder** on top,
which is XML2's own rule (retail packages list every file of `models/tiles/tutorial` etc.), harmless there
because XML2's folders have 23-30 files and fatal here (XML1: `sewers` 49, `haarpint` 64, `mansion` 71, `hive`
98). A zone actually names 3-17 tiles.

### 13.3 Fix (data side; no exe patch)

- **zones** lists exactly the tiles a zone can name (`zones.tile_models_used`, pure; `analyse_zone` computes
  them from the zone XML, `build_package` drops the bundle's other tile entries, `resolve_refs` adds the used set
  for `tilemodelfolder` instead of the folder). A tileent whose instances do not parse falls back to the whole
  folder with a `tilefolder_no_instances` warning (none today); an instance naming a tile that exists on neither
  disc is warned `tile_inst_unresolved` (5 zones: XML1 names such as `T_sewers_BAC_W_A01` with only `a0` files,
  which the code maps to the `a0` file, and `nyc3_2_2`'s `boc_w_a0` that XML1 never shipped). `--tiles
  used|folder` / `XML1BUILD_TILES` selects the old behaviour (`folder`); it is a CONTENT_OPT, so a carried-over
  zones output built with the other value is re-run.
- Per zone the package's IGB-cache records (`zones.igb_records`: distinct `model` names + motion-path files) are
  counted (`zones_detail.json zones[z].igb_records`, count `igb_records_max`): > 149 is an error, > 128 a warning
  (`IGB_ZONE_ERROR` / `IGB_ZONE_WARN`, `IGB_CACHE_RECORDS` = 200).
- **V12 igb cache** (validate) re-derives the same counts from `<out>` and checks every zone package's tile entries
  against the engine's used set (missing = error: on-demand load into the never-freed group 1; extra = warning).
- **`tools/xml1build/igb_budget.py`** (standalone, read-only unless `--apply`): `check <out>` prints every zone's
  records, its NPC packages' extra records, the resident estimate and the budget; `fix <out> --dest DIR` rewrites
  the packages whose tile entries differ from the used set into DIR (manifest `igb_budget_fix.json`, originals
  untouched; `--apply` copies them over `<out>` after backing the originals up). This is the post-process for a
  build made before section 13.

Result on the tour build: 13 zones over 149 -> 0; the largest packages are now `mansion/jugrnt/jugrnt01` 119,
`demo/jugrnt/jugrnt01` 118, `mansion/man4/mansion4_2` 115 (no tiles; XML1's own list), `haarp2_3` 106,
`hive2_2_4` 98; 67 zone packages lose 14-87 tile entries each and nothing else changes.

### 13.4 In-game checklist additions (after 12.9)

8. `haarp/int/haarp2_2` -> `haarp2_3` and `nyc/fb/nyc_fb1` -> `mansion/jugrnt/jugrnt01` load (the two tour
   failures), and `hive/h_int/hive2_2_3` / `hive2_2_4` (179 records before the fix).
9. Tiles: in `haarp2_1` (4 tiles named) and `hive2_2_4` (17) every wall/floor tile is drawn, breaking one shows
   its damage stages and debris; no tile is missing or replaced by nothing.
10. After a long session (20+ zones) `haarp2_3` still loads: on-demand loads into group 1 accumulate until the
    menu, so a zone that is missing precaches would be the first to fail late.

---------------------------------------------------------------------------------------------------------------

## 14. Engine limit: the actor table (2026-09-27, mansion/man4/mansion4_1 crash)

**Crash.** Tour stop 77 (`mansion/man4/mansion4_1`, `build/tour_results/gamedbg_029.log`): access violation at
`XMen2.exe+0x1743bb` reading address 0, Edi = Edx = 0xe, Ebx = 0x69c264. Call chain (return addresses on the
stack, all verified against the disassembly): `0x422b40` CActor spawn-from-XML (reads `character`, `skinindex`,
`skin`, ...) -> `0x4202c0` set skin -> `0x430cd0` play ea slot 0 (`ea_idle1`, 0x426a50) -> `0x42f0f0` play anim
id 14 -> `CModelActor` vtable 0x69c264 +0x58 = `0x5743a0`, which indexes the actor's animation databases by
`id / 175` and dereferences slot 0 = NULL.

**Mechanism (evidence in `actor_budget.py`'s docstring).**

- A `CModelActor` holds up to 5 animation databases (+0x30.., count +0x44); `0x577330` resolves an animation name
  by scanning them in order and returns `index + 175 * (databases scanned so far)`, but it skips a NULL slot
  *without* advancing that base. `0x41fdf0` fills slot 0 with the character's `characteranims`, slot 1 with the
  fightstyle's anim DB, slot 2 with `common` (`0x577a60` stores the lookup result even when it is NULL).
- The lookup (`0x56b0a0` -> `0x56b1c0`) goes to the actor manager (singleton 0x7b05e8), which keeps every loaded
  skin *and* anim DB in **one table of 0x28 = 40 slots** (`0x56ac10`; used count obj+0x73c4). When the table is
  full (`cmp [obj+0x73c4], 0x28 / jge` at 0x56b2c3) or the global 449-name resource table is full (`0x55a6a0`),
  the load **returns NULL silently**, both for package entries (`actorskin`/`actoranimdb` share the handler
  registered at 0x5622d0) and for on-demand loads at spawn time.
- So when a zone's actor files exceed the table, the last-loaded characters (the CHRB packages, loaded after the
  zone package's own actor entries) spawn with a NULL slot 0: `idle` resolves inside the fightstyle DB with an id
  below 175 (14 = `fightstyle_hero`'s idle under the sorted list order; `fightstyle_wrestling` 15,
  `fightstyle_finesse1` 17), playback indexes slot 0 and crashes on the character's first frame.

**Why mansion4_1.** The estimator (`actor_budget.zone_estimate`: permanent 6 + party 8 + zone package + CHRB
packages + fightstyle DBs) gives 38 for the converted zone, the highest of the tour, against at most 37 for XML2's
own 142 zones (`act2/mikhail/mikhail`; `egypt6` and `savage1` 36); the engine keeps about 3 actors the estimate
cannot see. The 4 slots that push it over are the XML1 hero actors the XML1 bundle precaches for `gambit` and
`rogue` (`x1_13_gambit`/`15301`, `x1_07_rogue`/`14701`) while both names resolve to XML2 herostat stand-ins that
load their own `13_gambit`/`1301` and `07_rogue`/`0703`. The same dead weight sits in 20 other converted zones
(`python -m xml1build.actor_budget check <out>` lists them; `mansion3_1` 36, `mansion1a_1` 36 were the next
candidates).

**Fix.**

- `tools/xml1build/actor_budget.py` (new): `prune_package_root` drops from a zone package the `actorskin` /
  `actoranimdb` entries that are XML1 herostat actors (mapped names: `map_skin` / `map_animdb`) which no character
  the zone can spawn needs (CHRB names -> the build's stats `skin`/`characteranims`/fightstyle DBs, spawner
  `monster_skin` values). Nothing outside that namespace is touched: XML2's own zones precache actors for
  script-spawned characters that are in no CHRB, and `mission_*`, `fightstyle_*`, `moveset_*`, `common` and
  bolt-on DBs are never candidates. zones calls it right after `build_package` (one delimited block; detail
  `zones_detail.json zones[z].actors_pruned`, count `actor_entries_pruned`). mansion4_1: 38 -> 34.
- **V13 actor slots** (validate, `actor_budget.validate`): re-derives the estimate per converted zone from `<out>`:
  > 37 (`ACTOR_ERROR` = XML2's own maximum) is an error, > 35 a warning; any remaining unused XML1 hero actor in a
  zone package is an error. `_build/validate.json checks.V13.details.zones` has the per-zone breakdown.
- Constants: `ACTOR_SLOTS` 40, `RETAIL_MAX` 37, `PARTY` = XMen2.exe's startFirstMission roster with the build's
  herostat skins (`_nc` packages when the zone is combat-off, as `0x4b8330` does).

**Not changed (options if a zone still exceeds the budget).** `fightstyle_villain` in `permanent_fightstyles`
costs one slot in every zone but XML1 kept it permanent too; civilian `monster_skin` variants (up to 8 skins in the
mansion hubs) are XML1 content; XML2's own actors for stand-in heroes cannot be dropped. The next lever would be
listing `fightstyle_villain` per zone instead of permanently.

### 14.1 In-game checklist additions (after 13.4)

11. `mansion/man4/mansion4_1` loads from a `--start-zone` build and Gambit, Rogue, Emma Frost, Professor X, the
    civilians and the scripted Cyclops all animate (idle) - none is frozen in a T-pose or missing.
12. The zones that lost XML1 hero actors (`zones_detail.json actors_pruned`, e.g. `mansion1a_1`, `mansion3_1`,
    `nyc1_1_3`, `sewers1_2_4`) still show their heroes as XML2's models.

---------------------------------------------------------------------------------------------------------------

## 15. Engine requirement: a town centre for every act (2026-09-27, acts 6-9 / stripped-zoneinfo crash)

**Crashes (same signature).** `EXCEPTION 0xc0000005 at msvcr71.dll+0x3300` (inside `_stricmp`), Ecx = Edx = Esi = 0,
Edi = 0x72a758 (the zone name buffer, "nyc/riots/nyc3_1_1"), innermost return address `XMen2.exe+0x86849`
(`0x486849`, after `call 0x672562` = `jmp [0x67f180]` = MSVCR71 `_stricmp`), outer `+0x862c8` (`0x4862c8`, after
`call 0x4867e0` in the zone-load path). The stack words `+0x286dac`, `+0x286da0`, `+0x288cd4` are not return addresses:
`0x686dac` is the Xtraction table's vtable, `0x686da0` the string "zone", `0x688cd4` the string "zoneinfo".
(A) boot into `menu/main_back` with every zoneinfo `extraction`/`towncenter`/`mapx`/`mapy` stripped (this morning);
(B) `build/_npcloop` with `new_game.py` = `setCurrentAct(7)` + `loadMapKeepTeam("nyc/riots/nyc3_1_1")`
(`build/_npcloop/dbg.log`).

**Mechanism (all addresses verified in `research/scripts/xml2_text.asm` and the exe's .rdata).**

- `0x468530` returns the Xtraction table (`[0x7298a0]`, 0x198 bytes, ctor `0x4684a0`, vtable `0x686dac`): count at
  +4 and 32 entries of 12 bytes from +0x14 (entry vtable `0x686d68`: +4 zoneinfo node, +8 act byte, +9 bit 0 =
  visited, bit 1 = towncenter). `0x468300` (vtbl+0) walks `Data/zoneinfo` and calls `0x468130` per `<zone>`: it
  registers only entries with `extraction` = "true" (`_stricmp` 0x468155) and only while the count is <= 0x1e
  (`cmp eax,0x20 / jl` 0x468164, `cmp eax,0x1f / jge` 0x46817d): **at most 31 entries, the rest are dropped
  silently**. `0x467f60` then parses `towncenter` ("true" -> bit 1) and `act` (atoi -> byte, default 1 from the ctor
  `0x4680a0`); `savename` (`0x467fe0`, NULL when absent), `description` (`0x468000`, "" when absent), `mapx`/`mapy`
  (`0x468040`/`0x468070`, 0.0 when absent) are read lazily.
- `0x4682b0` (vtbl+0x14) = town centre of an act: the first registered entry whose act byte equals the argument and
  whose towncenter bit is set, returning its `name`; **NULL when none matches**.
- `0x4867e0` (a method of the world object 0x72a578, called at 0x4862c3 while a zone loads, before "Placing players at
  start points...") does `_stricmp(world+0x1e0 /* zone name */, table->townCentre(game->currentAct()))` at
  0x486844 with no NULL test, and on a match calls `[0x815e98]->vtbl+0x20` (`0x596830`, zeroes that object's 0x34c
  bytes of state). `game->currentAct()` is vtable `0x686e1c`+0x274 = `0x469c30` = byte game+0x5e0, the byte
  `setCurrentAct` (`0x49f440` -> +0x278 = `0x469c40`) stores. So: **any act with no registered town centre crashes
  the first time any zone loads under it** - act 1 when every town centre is stripped (case A), acts 6-9 always
  (case B), because XML2's zoneinfo has exactly 5 town centres (`act1/sanctuary/sanctuary1`, `act2/savage/savage1`,
  `act3/military/military1`, `act4/mansion/mansion1`, `act5/teleport/teleport1`, acts 1-5) among its 30
  `extraction="true"` entries.
- The same compare without a NULL test is `0x5cc0f0` (called from the pause/PDA menu code at 0x5cc884 and 0x5cd1ae
  when game flag +0x616 bit 1 is set): a second crash site for the same acts. The other users are NULL-safe:
  `0x46e160` (game vtbl+0x158, the Xtraction "go to town / recall" toggle: `loadextraction %s recall`), `0x49f220`
  (a script binding), and the 0x5cc918, 0x5f40c0 and 0x60ba00 menu paths all test the pointer first.
- Acts above 5 elsewhere: the mission manager compares act bytes (`0x489130`, `0x72b570+i`), the save game copies the
  game block including +0x5e0 and re-applies it through `setCurrentAct` on load (`0x46e3b3`-`0x46e3e6`), the item
  purge on act change (`0x469c40` -> vtbl+0x24 = `0x46a1a0`) drops item categories 4 and, when the act changed, 3,
  independent of the number. Act-indexed **resources** exist for acts 0/1-5 only: `Packages/generated/maps/package/
  menus/pda_act%d` (0x5ccc93, the PDA loads it for the current act; act 0 when `[0x782728]` != 0xff), `act_team_%d`,
  `actcommon%d`, `UI/models/m_map_act1..5`, `Textures/ui/quest_icons_act0..5`, and `UI/menus/worldmap.XMLB` has act
  tabs 1-5 (`m_wm_map1..5`). XML2 also scales NPC stats by act (`0x4a21c0`: striking x2*act, `0x4a22f0`: maxhealth
  x10*act) - the `--npc-scaling` option's domain. None of these is a known crash; they are in-game checks (15.1).

**Options weighed.** (b) repacking the 101 XML1 missions into 5 acts is impossible without renaming objectives: the 75
cap alone would allow 3 groups, but every consecutive pair of the 9 groups shares an objective name with different
text (`marines`, `plugholes`/`brotherhood`, `find_scientist`, `reboot`, `sentinels`, `rescue_healer`,
`explore_mansion` x2; 19 of the 36 group pairs conflict), and 139 installed scripts plus `zone_acts.json` carry acts
6-9. (c) an exe patch (NULL test at 0x486844) is not needed. **(a) data-side** is implemented.

**Fix (zones.py, one delimited block; constants `XTRACTION_CAP` 31, `XTRACTION_STRIP_XML2_DESTINATIONS`,
`TOWNCENTER_HUB_RE`, `TOWNCENTER_MAP_XY`, `TOWNCENTER_SAVENAME`).** `Zones.act_towncenters` runs on both zoneinfo
trees after the converted entries are added:
- `Zones.selectable_acts`: the entry act of every converted zone (`prov.zone_act`), every act in research
  `zone_acts.json` (the `--start-zone`/`--tour` hooks pick from it), the mission plan's groups
  (`research/scripts/mission_plan.json`, = `Data/missions/x1_act01..09`) and act 1 -> {1..9} today.
- XML2's 25 `extraction="true"` entries that are not town centres lose `extraction`/`towncenter`/`mapx`/`mapy`
  (room under the 31 cap; XML1 mode has no XML2 destinations). XML2's 5 town centres stay untouched (boot proven).
- Every selectable act without a registered town centre gets one on a converted zone of that act: the zone matching
  `TOWNCENTER_HUB_RE` (`mansion/man*/mansion*_1`, the X-Mansion ground floor of that visit), else a `mansion/*` zone,
  else the act's first zone in New Game reach order (a zone of another act only if the act has none: warning). It gets
  `extraction="true" towncenter="true" act="<n>"`, `mapx`/`mapy` = XML2's X-Mansion position (0.12/0.11) and, when
  XML1's zoneinfo gave it no `savename`, "X-Mansion" (mansion zones) or its directory name - `0x467fe0` returns NULL
  without one and the world map list reads it. Today: act 6 `mansion/man5/mansion5_1`, act 7
  `mansion/man6/mansion6_1`, act 8 `mansion/man7/mansion7_1`, act 9 `mansion/man8/mansion8_1`; 9 extraction entries.
- More than 31 extraction entries or an act with no converted zone at all is a build error. Counts
  `zoneinfo_towncenters_added`, `zoneinfo_xml2_destinations_stripped`, `zoneinfo_xtraction_entries`;
  `zones_detail.json towncenters` = {stripped, added, towncenters, entries}.
- **V6** `_v6_act_towncenters`: re-derives the selectable acts from `<out>` (every `setCurrentAct` literal in every
  installed script + the `act` of every listed mission file) and errors on an act with no `towncenter="true"` entry
  among the first 31 `extraction="true"` entries of either zoneinfo file, on more than 31 such entries, and on a town
  centre whose `Maps/<zone>.XMLB` is missing. `validate_selftest` removes act 7's town centre and expects the error;
  `zones_selftest` C checks XML2 town centres unchanged, the other XML2 destinations stripped, the added hubs'
  attributes and the cap.

Unverified (offline build only): that the world map / PDA / recall toggle behave in acts 6-9 with their per-act
resources missing (15.1), and that a plain-text `savename` renders in the world map list as XML1's plain-text
savenames do in the save menu.

### 15.1 In-game checklist additions (after 14.1)

13. `build/_acts` (`--start-zone nyc/riots/nyc3_1_1`, `new_game.py` = `setCurrentAct(7)`): New Game loads the riots
    zone with no crash (previously `_stricmp` at msvcr71+0x3300 from `XMen2.exe+0x86849` while loading it), the act
    7 objectives (`x1_act07`) appear in the PDA, and the PDA opens (it asks for the missing package
    `menus/pda_act7`; expected: quest icons missing, no crash - if it crashes, ship `pda_act6..9` as copies of
    `pda_act5`).
14. In an act 6-9 zone with an Xtraction point (e.g. `mansion/man6/mansion6_1` itself, or a riots zone beacon), open
    the Xtraction menu: team change and save work; the world map opens without crashing and lists the act's
    X-Mansion (plain-text "X-Mansion"); choosing it loads `mansion/man6/mansion6_1`. `worldmap.XMLB` only has act
    tabs 1-5, so the map background may be blank for acts 6-9.
15. Regression: New Game (act 1, alison) and `menu/main_back` boot still work with the 25 XML2 destinations stripped
    (the 5 XML2 town centres are unchanged).

## 16. Engine convention: the per-zone animation DB is `zone_<leaf>` (2026-09-27, the "punching bystanders")

**Symptom.** Bystander NPCs whose spawn script plays a zone animation (`playanim("EA_ZONEn", "_OWNER_", "LOOP")`:
mansion civilians sitting / talking, riot looters smashing, briefing poses) crouch, lunge and swing at the party
instead. Section 12's `bound_unwakeable_loops` (LOOP + 15 s + STOP) only limited how long it lasted.

**Mechanism (XMen2.exe, verified in the disassembly and by an in-game A/B).**

- `0x486710` (world object, called while a zone loads) takes the zone name at world+0x1e0, skips to the text after
  the last `/` (`strchr` loop on `0x68417c` "/"), formats `"zone_%s"` (`0x688d78`) into a 0x40 buffer at world+0x160,
  builds the resource key with `0x5647f0` (pool 0xb, `"%i:%s"`) and asks the actor manager (`0x56b8e0`, vfunc +0xc)
  whether a resource of exactly that name is resident. When it is not, it copies `"zone_shared"` (`0x681968`) over
  the name instead. Every actor of the zone then gets that DB as its extra animation database, which is where the
  `ea_zoneN` -> `zoneN` clips (`Data/shared_anims`) come from.
- XML2 therefore ships `Actors/zone_<leaf>.igb` per zone (75 files, e.g. `zone_briefing1_10` for
  `briefing/briefing1_10`, clips `zone3 zone6 zone7 zone9 zone15 zone16`). XML1 shipped one `mission_<area>.igb` per
  area (43 files, clips `mission1..20`), listed as `actoranimdb` by all zones of the area (168 bundles).
  `characters.rename_mission_anims_igb` already renamed the clips to `zoneN` and the scripts' `EA_MISSIONn` to
  `EA_ZONEn` (section 12), but the DB was still named `mission_<area>`, so XMen2.exe never attached it, `zoneN` was
  found in no DB of the actor, and the play call fell through to a wrong clip.
- The name must be the bare stem. In-game A/B on `mansion/man4/mansion4_1` with two `sp_civilianKid_a` instances
  (`EA_ZONE17` LOOP) planted at the player start: package entry `zone_mansion4_1` (a copy of `mission_man4`) = both
  civilians sit still; `mission_man4` = they crouch and lunge at the party; `actors/zone_x/zone_mansion4_1` (file
  present under `Actors/zone_x/`) = crouch again, so the resource key is the entry string, not the basename.

**Fix (zones.py, section 16 markers).** `Zones.zone_animdb_plan()` reads every XML1 zone bundle once: the zone's
`mission_<area>` DB and how many `EA_ZONE/EA_MISSION/EA_TALKING` literals its bundle scripts use. `build_package`
replaces the `actoranimdb mission_<area>` entry with `actoranimdb zone_<leaf>` (`zone_animdb_entry`) and writes
`Actors/zone_<leaf>.IGB` once per name from the XML1 file with `rename_mission_anims_igb` applied (the
`mission_<area>` copy the characters module still writes is now unreferenced). Zones sharing a leaf and an area
(the `demo/` copies) share the file. Four leaves are wanted by two areas with different DBs (`astral1_1` and
`astral1_3`: ast1 vs savepx; `muir_brig`: muir2 vs muir3; `subbasement4`: man4 vs man5): the area whose zones use
more zone animations owns the file, the other zone's entry is dropped (status `lost`, warned, `zones_detail.json
zone_animdbs`) and it keeps XMen2.exe's `zone_shared`. Only a zone rename can serve both; not done. `dr_mag03`
is the one XML1 leaf equal to an XML2 zone DB name; XML1's copy overwrites XML2's (that zone is unreachable here).
Actor-slot accounting is unchanged (one `actoranimdb` entry replaces one).

**Validator.** **V6** `_v6_zone_animdbs`: a converted zone package listing any `mission_*` anim DB, a `zone_*` DB
other than its own `zone_<leaf>` (or `zone_shared`), or a path-form zone DB is an error; a listed `zone_<leaf>`
must exist in `<out>` and hold `zoneN` (no `missionN`) clips; a zone whose XML1 bundle had a mission DB but whose
package has no `zone_<leaf>` entry is a warning when zones marked it `lost`, otherwise an error.

### 16.1 In-game checklist additions (after 15.1)

16. `mansion/man4/mansion4_1`: the civilians in the side rooms sit / talk (EA_ZONE11..20) instead of crouching at the
    party; `nyc/riots/nyc3_1_1`: the looters swing baseball bats at shop fronts (EA_ZONE3/5, bolt-on bat) and the TV
    thief walks off with a TV, then stop after 15 s (section 12 bound).
17. One `lost` zone (e.g. `mansion/man5/subbasement4`): its zone-anim NPCs still misbehave (known; zone rename).

## 17. Engine convention: `<inst extents>` are entity-local (2026-09-27, dead triggers and zone links)

XML1 writes an `<inst>`'s `extents` as the WORLD-space axis-aligned box of the rotated entity; XMen2.exe reads the
box in the entity's own frame, relative to `pos` and rotated with `orient` (inst parser 0x461e3e). Unconverted,
every XML1 trigger box (subway stairs, zone links, touch triggers) sat far outside the map. Evidence, method and
the per-inst conversion (`x1_extents_to_local`: offset / rot90 / solved / fallback45 / fallback_xy) are in the
section 17 comment of zones.py; `convert_inst_extents(root)` runs first in `mutate_zone` (counts
`inst_extents_<how>`). Verified in game: nyc1_1_1's subway stairs and every zone exit ("[E] West Manhattan").
Test touch triggers by walking in from outside: a hero teleported into one (copyOriginAndAngles) does not fire it.

**Validator.** **V6** `_v6_inst_extents`: a box that contains the entity's world `pos` but not its own origin is
an error (unconverted); boxes containing neither are XML1's offset boxes (kill volumes above a marker), counted.

## 18. Engine behaviour: `remove(name)` removes every entity of that name, the party's heroes included (2026-09-28)

`remove(a, b)` (0x4a9300) collects EVERY entity named `a` (0x4a7e30) and removes them. XML2 names the party's heroes
after their herostat entry, so a script removing an NPC that shares a hero's name also removes that hero from the
party. In game (build/_cyc, nyc1_1_3): the join (section 12 T7, SPEC_heroes 7) reloads the zone with Cyclops in the
party; the zone's spawner `sp_cyclops01` instant-spawns the NPC double `cyclops` again before the zone script runs,
so the guard's `remove(sp_cyclops01)` left the double standing next to the hero, and a guard `remove("cyclops")`
removed the party's Cyclops as well (the HUD dropped to Wolverine alone).

**Fix (zones.py section 18, scripts_transform).** `JOIN_DOUBLE_SPAWNERS` names the join zones' spawners
(`nyc/alison/nyc1_1_3`, `mansion/dr_mag2/mag_nyc4`: `sp_cyclops01`, hero `cyclops`); `rename_join_double` sets
their `monster_name` to `join_double(hero)` = `cyclops_x1double` (XML2's own pattern: tutorial1's Cyclops NPC is
`simplecyclops`). `join_hero` removes the double by that name, and `join_hero_zone_guard` removes trigger, spawner
and double on the reload. Before the join no script addresses the double by name in either zone (the later
`setAIActive("cyclops")` lines of both missions mean the party hero, as in XML1 where the NPC became the hero).
Count `join_doubles_renamed` (2); problem `join_double_missing` if a spawner is not found. Verified in game
2026-09-28: after the join Wolverine + Cyclops, no double; Cyclops switches in (Right arrow - XML2 switches by the
HUD position of the head, `switching_hint` in igct.bnx) and his optic beam fires.

**Later loads (2026-09-28 night, section 19.7).** The instant spawn turned out to come after the zone script's
removes on later loads too, so the zone script ends with repeated late removes of the double; and the join zones'
slot-2 starts (`player_start01`, `startenabled="false"`, enabled only by the join trigger for its own load) are
enabled in the zone file (`enable_join_starts`, count `join_starts_enabled` 2, problem `join_start_missing`), so the
joined hero spawns at every later load.

**Validator.** **V6** `_v6_join_doubles`: each join zone's spawner has exactly `monster_name=join_double(hero)`, no
script that uses the `x1join` flag removes the hero's own name, and each join zone has a slot-2 start that is not
`startenabled="false"`.

### 18.1 The other same-name NPCs (2026-09-28)

The NPCs are the zones' spawners (`monster_name`, else the spawner's `character`; the CHRB only lists what to load).
Every reachable converted zone whose spawner NPC carries a playable hero's name AND whose scripts (world zonescript +
the package's scripts + inline zone code) address that name in an entity call (`scripts_transform.entity_name_refs`:
any call but `unlockCharacter` / `seatParty` / `objective` / flags ...) was reviewed against the party that can be
there (SPEC 19 seat blocks, the unlock points of section 20, the load that enters the zone):

**"Not unlocked yet" is no protection (2026-09-28).** XMen2.exe keeps hero unlocks in the PROFILE
(`settings.dat`), not in the game: `unlockCharacter` sets the registry bit and the profile bit (`0x449c00` -> profile
`0x48fed0` vt+0x28 = `0x48f740`, a bitset at profile+0x1c0), New Game's `resetgame` clears only the registry bits
(`0x449540`, called from `0x5f2f96`), and the team menu's pick checks the profile bit (vt+0x38 = `0x48f770` at
`0x5e3d81` / `0x5e5319` / `0x5e55cb`) - the reason XML2's shared profile offered the port nearly every hero before
`[Game] SaveFolder`. So a hero unlocked once (Gambit at the sewers, Colossus at mansion4, Psylocke at mansion7) can be
picked in every team menu of every later New Game on that profile, before the story unlocks him again.

- **Renamed** (`NPC_DOUBLE_SPAWNERS`, `zones.rename_npc_doubles` -> `<hero>_x1double`; the zone's scripts follow via
  `scripts_transform.rename_npc_refs`, `NPC_DOUBLE_SCRIPTS`; the zone's own inline code via
  `zones.rename_npc_inline_refs`):
  - `mocap/mocap1/briefing_1_1_6_5` wolverine, cyclops (`nyc/alison/blackbird_brief1` loadZone()s it with alison's
    Wolverine + Cyclops; mansion1's seat block runs only after the cinematic) and `mocap/mocap4/briefing_1_7_1`
    wolverine, cyclops, rogue, phoenix, storm, nightcrawler, gambit (`sewers/quest/fadegambit` loadMapKeepTeam()s it
    with the free sewers party, Gambit included from the second New Game on). Their only references are the
    cinematic's `playanim("EA_ZONEn", "<name>", ...)` lines; briefings have no conversation speaker lines.
  - `muir_is/muir2/muir_in2` colossus, cyclops, storm (2026-09-28): muir2 seats Magma, but with `[Game]
    ForcedTeams=0` (or without xml2-fix) its start opens the team menu, and a picked Storm lost her party slot to
    `2_4_1_cleanup`'s `remove("storm")`; Cyclops (`cyclops_face_alison` faceEntity), Colossus (`2_4_1_cleanup`
    setEnable / copyOriginAndAngles, `sp_colossus01`'s inline spawnscript `setEnable('colossus', 'FALSE' )`) likewise.
    The free XML1 mission `muir_in2` (and `nuke_col`) is only in XML1's debug level list `ui/menus/map_list.xml`;
    nothing in the campaign starts it (graph.json `reachable_missions`).
  - `nuke_plant/nuke/nuke2_2` colossus (`colossus_holding`: `playanim("EA_ZONE1", "colossus", "LOOP", "")` would loop
    a party Colossus; the zone also has an Xtraction Point), `nyc/riots/nyc3_1_2` psylocke (`conv3_2_3`
    copyOriginAndAngles), `sewers/hub/sewers1_2_4` gambit (`gambit_spawn` setInvulnerable, `gambit_free`
    setWaypointPath, `fadegambit` fade + remove): free parties, open from the second New Game on (above).
  - **Their conversations follow** (`NPC_DOUBLE_CONVERSATIONS`: muir2 `2_4_1`, `2_4_3`, `2_4_6`, `2_4_11`, `2_4_11b`;
    nuke `2_3_3`, `2_3_4`; riots `3_2_3`; sewers `1_5_3`, `1_5_5`; each packaged by its zone only): a `%NAME%` speaker
    key is looked up twice - the stats entry of that name gives the name label and portrait (`0x456d00`,
    `0x5f4ec0`), the zone entity of that name the talk animation (`0x45bd1e` -> `0x4c6f20`, the entity name table) -
    so `scripts.rewrite_data_tree` turns the doubles' `%HERO%` tokens into `%HERO_X1DOUBLE%`
    (`scripts_transform.rename_speaker_tokens`) and their inline code follows `rename_npc_refs`, and heroes.py adds a
    **speaker stats entry** per speaking double (`NPC_DOUBLE_SPEAKERS` colossus, cyclops, gambit, psylocke ->
    npcstat `<hero>_x1double`: the hero's charactername / skin / characteranims, team none, playable false - XML2's
    own `CyclopsSimple` / `Cyclops_MC` pattern; never spawned, the spawner keeps the hero character, so no character
    package: V5 allows its absence). The NPC keeps its talk animation, the line its "Colossus" label and portrait, and
    a party Colossus no longer mouths the NPC's lines. Stats names 227 -> 231 of 296.
  - Counts: zones `npc_doubles_renamed` 15, `npc_double_inline_refs` 1; scripts `npc_double_refs` 21;
    heroes `npc_double_speakers` 4; problem `npc_double_missing`.
  - **Verified in game 2026-09-28** (build/_npc, pipe `npcdbl`; the hero seated by `seatParty` + `loadMapKeepTeam`,
    entities probed with `alive(name)` through getPartyMember's log line): muir_in2 with Storm / Cyclops / Colossus
    / Magma - 2_4_1 plays, `2_4_1_cleanup` removes only `storm_x1double`, all four stay in the party (HUD 4 heads);
    2_4_1's and 2_4_6's double lines show "Colossus" / "Cyclops" with the portrait. nuke2_2 with Colossus - both
    Colossi exist, the party one walks (no holding loop), 2_3_3 labels "Colossus". sewers1_2_4 with Gambit - 1_5_5
    -> mission complete -> `fadegambit` removes the double, the briefing loads with Gambit + Wolverine and the next
    team menu shows both. nyc3_1_2 with Psylocke - conv3_2_2 spawns `psylocke_x1double`, conv3_2_3 moves it, 3_2_3
    labels "Psylocke", the party Psylocke stays. (The talk animation itself is not checked frame by frame.)
- **The joins' Cyclops lines, line by line (2026-09-29).** The join zones have ONE Cyclops speaker line between
  them: nyc1_1_3's `1_1_5_1d` (Cyclops warns the Blob). It plays after the join only: from the entry
  start the zone's nav mesh reaches the Blob trigger (`trigger_touch01` -> `alison_gets_away` -> `1_1_5_1b` ->
  `alison_gets_away_2` -> `1_1_5_1d` -> `1_1_5_1_end`) only across the join trigger `trigger_touch03` (without its
  cells 72 of the 2072 nav cells are reachable), and XML1's own scene puts `_HERO2_` on `cyc_spot` and wakes
  `"cyclops"` - the party Cyclops speaks, so the line keeps `%CYCLOPS%` (reviewed `party`, below). mag_nyc4 has none
  (`2_2_1_3_new` is Magma quoting him). Before the join Cyclops is heard in the join zones only through
  `add_cyclops`'s `sound("PLAY_SOUND", "voice/cyclops/1_1_0045_1", ...)` - no conversation line, no speaker. The lines
  Cyclops speaks as an NPC come one zone earlier: `nyc/alison/nyc1_1_2b` `1_1_09` "Hey, Wolverine." and its Danger
  Room copy `mansion/dr_mag2/mag_nyc3` `2_2_1_0_5` "All right.", both spoken by Mystique disguised as Cyclops - the
  spawner NPC `cyclops_scripted` (XML1's own name, character cyclops; `cyc_wp1` hits Wolverine, `cyc_wp2` morphs it
  into Mystique). Their `%CYCLOPS%` talk-animated the entity named `cyclops`: nobody there before the join (alison
  seats Wolverine, dr_mag2 Magma), or the party's Cyclops where one was there (dr_mag2 through the team menu with
  ForcedTeams=0). **Fix:** `scripts_transform.NPC_SPEAKER_CONVERSATIONS` (conversation -> its zone, {hero: NPC
  name}) makes `scripts.rewrite_data_tree` write `%CYCLOPS_SCRIPTED%` (`rename_speaker_tokens` with a mapping), and
  `speaker_stats_entries()` (the x1double names + these NPC names) gives heroes.py a speaker entry `cyclops_scripted`
  (Cyclops's charactername / skin / characteranims, team none, playable false - the x1double entry's pattern; the
  NPC keeps XML1's name, nothing else changes). The entity-name lookup folds case (`0x4c6f20` -> `0x5602b0`), so the
  upper-case token finds the lower-case entity. Stats names 231 -> 232 of 296; heroes `npc_double_speakers` 5.
  Whether XML1's own talk animation found `cyclops_scripted` under `%CYCLOPS%` was not traced (default.xbe keys the
  speaker by stats name, `0x61bc6`; its entity lookup was not read).
- **Speaker review (2026-09-29, `HERO_SPEAKER_REVIEW`).** A reachable zone that spawns an NPC of a playable hero
  under another entity name, packaging a conversation with that hero's `%HERO%` line: the talk animation goes to the
  party's hero, not to the NPC. Each such (conversation, hero) is renamed (above) or reviewed: `party` - only the
  party's hero speaks it there: nyc1_1_3 `1_1_5_1d` (post-join, above) and mag_nyc4's Magma lines `2_2_1_3_new`,
  `2_2_1_3a`, `2_2_2` (Magma is dr_mag2's party hero; `alison_scripted` is the simulated Alison); `open` - the NPC
  speaks under the hero's token and gets no talk animation (label and portrait right; V6 warns): none left since the
  Alison / Emma fix below (the reason stays for new cases). `nyc/alison/blackbird` (Jean, `jeangray`, `%PHOENIX%` in
  `1_1_6_5`) is not reachable.
- **The NPC Alison and the NPC Emma (2026-09-29, the former `open` lines).** Line by line from XML1's scripts:
  nyc1_1_3 (alison; party Wolverine, + Cyclops after the join) - the NPC `alison` (`sp_magma01`, character magma, skin
  1803, team none) punches the Blob (`alison_gets_away`) and says `1_1_5_1b` (her cry for help), then runs
  to `alison_spot`; mag_nyc4 (dr_mag2's Danger Room replay, party Magma) - the simulated Alison `alison_scripted`
  says the same line, `2_2_1_3b` (`2_2_1_3a_end`: she punches the Blob, then the conversation), while the zone's other
  `%ALISON%` lines (`2_2_1_3a` "Hey, that's me!", `2_2_1_3_new`, `2_2_2`) are the party Magma's (`party` above);
  mansion4_1 (mansion4, Magma forced) - Emma Frost is the NPC `emma` (`sp_frost01`, character frost; her actscript
  starts `2_5_10`, `emma_talk` / `profx_apears` start `2_5_10b`), every `%FROST%` line of both files hers, the
  `%MAGMA%` / `%ALISON%` lines Magma's. `NPC_SPEAKER_CONVERSATIONS` now also maps `1_1_5_1b` {magma: `alison`},
  `2_2_1_3b` {magma: `alison_scripted`}, `2_5_10` and `2_5_10b` {frost: `emma`}: the alias turns XML1's `%ALISON%`
  into `%MAGMA%`, the mapping into `%ALISON%` / `%ALISON_SCRIPTED%` / `%EMMA%` (14 Emma lines), and heroes adds the
  speaker entries `alison`, `alison_scripted` (Magma's skin / characteranims) and `emma` (Frost's charactername "Emma
  Frost", skin, characteranims). **The label is XML1's own:** default.xbe resolves `%ALISON%` itself (`0x61bc6`):
  the speaker key is the stats entry Magma (`0x61bde`-`0x61c24`), the label its **string 503 "Alison"**
  (`0x61c81`-`0x61c8f` string table vt+8(0x1f7); `data/strings.eng` id 503, the same in .fre/.ger) - "Alison" with
  Magma's portrait. `scripts_transform.SPEAKER_DISPLAY_NAMES` {`alison`, `alison_scripted`: "Alison"} gives the two
  entries that charactername (XMen2.exe labels with the entry's charactername), the skin stays Magma's, so the line
  reads "Alison" with Magma's head as in XML1. The talk animation is the port's: XML1 keyed it to Magma / FROST
  (`0x6449f`: `0xbef20` vt+8(key), the shape of XMen2.exe's by-name lookup), which names neither NPC; the NPCs now
  mouth their own lines, and the party Magma no longer mouths the simulated Alison's. Details:
  `research/heroes/conversation-speakers.md` 9a. Stats names 232 -> 235 of 296; heroes `npc_double_speakers` 8; V6
  `hero_npc_speaker_tokens` 18, `hero_speakers_open` 0. **Not done (engine):** XML1 labelled all 213 `%ALISON%`
  lines "Alison"; the party-Magma ones say "Magma" in the port, because one key gives XMen2.exe both the label and
  the talk-animation entity (`magma`); showing "Alison" there needs an xml2-fix alias at `0x456d00` (section 12.1).
  - **Verified in game 2026-09-29** (build/_speak, pipe `speak`, one window; talker from `tools/conv_probe.py`):
    nyc1_1_3 with Wolverine (`loadMapKeepTeam`), the scene script `nyc/alison/alison_gets_away` run by the pipe (a
    teleport into `trigger_touch01` does not fire it): `1_1_5_1b` line 1 "Blob / Ow!" (no talker, `%BLOBACT1A%`),
    line 2 **"Alison / (her cry for help)" with Magma's portrait, talker `alison`**; then `1_1_5_1d` plays.
    `begin_mansion4` (Magma seated) -> mansion4_1, `startConversation("mansion/man4/2_5_10b")`: **"Emma Frost / Hello,
    dear..." talker `emma`**, Magma's reply talker `magma`, Emma again `emma`; `profx_apears` -> the second
    startCondition (Emma visible, her lines `emma`, Professor X's no talker) -> `profx_disapears` -> `2_5_10`: Emma
    `emma`, the reply menu (4 responses) `magma`, (the farewell line) -> end. mag_nyc4 with the party Magma
    (both `magma` and `alison_scripted` exist), `2_2_1_3a_start` by the pipe: `2_2_1_3a` "Magma / Hey, that's me!"
    (notalkanim), **`2_2_1_3b` "Alison / (her cry for help)" talker `alison_scripted`, not the party Magma**,
    `2_2_1_3_new` Magma's line talker `magma`. Screenshots in build/_speak_shots.
  - **Verified in game 2026-09-29** (build/_cyctalk, pipe `cyctalk`; New Game -> nyc1_1_1 with Wolverine, then
    `loadMapKeepTeam`; the talker read from the conversation singleton: `CS+0x2399c` holds the handle of the entity
    the new line's talk animation went to (`0x45bddd`, set only on the path that plays anim `0xb6+rand`, `0x45bdf3`),
    the handle resolved through the entity-name tree (`0x778b70+0xc44`, keys interned at `0xa2c440`)): nyc1_1_2b
    before the join (party Wolverine; no entity `cyclops`) - `1_1_09` line 1 "Cyclops / Hey, Wolverine." with
    Cyclops's portrait, talker `cyclops_scripted`; line 2 talker `wolverine`; the morph and `1_1_1a` follow. nyc1_1_3
    - walked into `trigger_touch03`, popup, `joinHero("cyclops") -> 1`, reload with Wolverine + Cyclops; the Blob
    scene: `1_1_5_1b`'s Alison line talker none (`open`), `1_1_5_1d` "Cyclops / Don't take another step closer,
    Blob!" talker `cyclops` - the party Cyclops, standing on `cyc_spot`. mag_nyc3 with the party Wolverine + Cyclops
    (both `cyclops` and `cyclops_scripted` exist): `2_2_1_0_5` "Cyclops / All right." talker `cyclops_scripted`, not
    the party's Cyclops.
- **Kept, reviewed** (`HERO_NPC_REVIEW`; only the reasons `HERO_NPC_REVIEW_REASONS` = `forced`, `party` count):
  `forced` - the mansion hubs (mansion1a_1/1a_2, mansion2_1, hangar3, mansion3_1, subbasement3b, mansion4_1,
  subbasement4, subbasement6, mansion7_1, status_meeting, subbasement7) and the briefings mocap2/3/5..13: every way in
  seats Magma (or pops back to her) whatever the profile has unlocked; `party` - mocap1's other NPCs (alison's party
  is Wolverine + Cyclops, joinHero adds Cyclops without a team menu). The former `locked` (nuke2_2, nyc3_1_2) and
  `joins` (sewers1_2_4, mocap4 Gambit) reasons are gone (profile, above). Not reached from New Game (skipped):
  `xjet/blackbird_arbiter`, `man8/subbasement8b`.
- **Open (ForcedTeams=0 only):** with `[Game] ForcedTeams=0` (or without xml2-fix) the forced starts open the team
  menu (and the joins fall back to T7's), so a player can bring e.g. Phoenix into `mansion1a_1` (`remove("phoenix")`)
  or Storm into mocap1. The hubs keep XML1's names for now; the muir_in2 treatment (rename + conversations + speaker
  entries) now keeps the talk animation, so they can follow it without a loss if ForcedTeams=0 is to be supported.

**Validator.** **V6** `_v6_hero_npcs`: each `NPC_DOUBLE_SPAWNERS` spawner has `monster_name=join_double(hero)`; no
script of the zone (world zonescript, package scripts, inline zone code) and no conversation its package lists
addresses the hero's own name in an entity call, and no such conversation has a `%HERO%` speaker token for a renamed
hero; every `NPC_DOUBLE_CONVERSATIONS` entry is packaged by its zone and by no zone that keeps those names; every
double speaker token (and every `speaker_stats_entries()` name) has a stats entry. Any other reachable zone whose
scripts address a hero-named NPC must be in `HERO_NPC_REVIEW` with a reason in `HERO_NPC_REVIEW_REASONS` (error
otherwise: rename or review a new case). `_v6_hero_speakers` (2026-09-29): every `NPC_SPEAKER_CONVERSATIONS` entry
is packaged by its zone, every zone packaging it spawns that NPC (entity name, the hero's character), its lines say
`%NPC%` (at least one; count `hero_npc_speaker_tokens` 18) and none keeps `%HERO%`, the NPC name has a stats entry;
every speaker entry (`speaker_stats_entries()`, XMLB and engb) carries the hero's skin and the hero's charactername,
or `SPEAKER_DISPLAY_NAMES`' (the NPC Alison: "Alison"); every reachable zone's (conversation, hero) of the speaker
review above is renamed or in `HERO_SPEAKER_REVIEW` with a reason in `HERO_SPEAKER_REVIEW_REASONS` (error otherwise;
`hero_speakers_reviewed` 4, `hero_speakers_open` 0 - an `open` entry warns; a review entry that matches nothing
warns). `_v6_speakers` accepts the alias spelling `%ALISON%` only in the conversations whose NPC is `alison`
(`NPC_SPEAKER_CONVERSATIONS`); anywhere else it stays the section 12.1 error. validate_selftest
`npc_double_defects` injects all these kinds (a double addressed / spoken as the hero, a speaker entry gone, `1_1_09`
back on `%CYCLOPS%`, an unreviewed `%CYCLOPS%` line in mag_nyc4, `1_1_5_1b` back on `%MAGMA%`, `alison_scripted`
labelled "Magma"; the round-2 `%ALISON%` line in another conversation is still an error).

## 19. Forced teams: XML1's parties through xml2-fix script functions (2026-09-28)

The design, with every address and the reasons, is `research/heroes/FORCED_TEAMS_DESIGN.md` (supporting research
next to it: `script-functions.md`, `party-seating.md`, `forced-teams-census.md`, `conversation-speakers.md`). This
section records what the pipeline builds. Owen's decisions: faithful parties are the ini switch `[Game]
ForcedTeams=1` over a build that carries both branches; `AddHero` defaults to 0; the REQUIRED `unlockCharacter`
lines stay; XML1's literal `civilian` skinset; `popParty` returns to the push spot; the `nyc_rooftops` response is
dropped; ProfXGladiator is a herostat hero since 2026-09-28 (SPEC_heroes 3.1), so astral_sk and boss_shadowking
are seated too.

### 19.1 The functions and the guard

xml2-fix (branch `display`, module `forced_teams` since xml2-fix 7b457dc, not part of this repo) registers eight
script functions (`research/scripts/xml2fix_api.json`, `scripts_transform.XML2FIX_API`): `xml2fixFeature(s)` i,
`seatParty(ssss)`, `setSkinset(ss)`, `pushParty(a)`, `popParty(s)`, `addHero(s)` i, `getPartyMember(i)` s,
`joinHero(s)` i (since xml2-fix 0c82a6e, section 19.7).
`ctx.xml2_api` merges them in `--forced-teams seat` builds (the default), so lint and V7 accept them;
`--forced-teams menu` builds emit none (the section 12.6 output, byte-identical to the scripts before this
section).

Every call sits in the `then` branch of a feature guard (`scripts_transform.feature_detect`):

```
x1ft = iadd(0, 0 )
x1ft = xml2fixFeature("forcedteams" )
if x1ft == 1
     ...xml2-fix calls...
else
     ...the team menu (or nothing)...
endif
```

Without the DLL (or with an xml2-fix build lacking the module, or no `ForcedTeams` key) the query statement is
dropped at compile (an unregistered name drops only its own statement, 0x4da37a), `x1ft` stays 0 (declared by
`iadd`, the retail idiom; an undeclared variable would drop the `if` line itself) and the else branch runs. With
`ForcedTeams=0` the query returns 0. What the else branches do, against the scripts before this section (the
`menu` build):

- forced mission starts (seat block): `loadMapChooseTeam(z)`, as before (section 12.6); skinset and push blocks
  have no else branch, so nothing changes; the joins run the same T7 statements as before (`remove` of the
  double now after the join bit instead of before it).
- **side-mission returns change**: the pop sites (`nycfb4_finish`, `fmvexit`, `end_fb`, `endreboot`, and the
  jugdead exit through `x1/missions/end_jug_fb`, and `shadowking_defeated`) used to `loadZone(caller, "")`, which
  kept the flashback party in the caller zone; they now open the team menu at the caller zone
  (`loadMapChooseTeam(caller)`, roster T9's "simplest variant", design 3.4: the player re-picks instead of keeping
  the flashback party). A side mission that is not seated (only in `--hero-roster 21xml2`: astral_sk, whose
  ProfXGladiator is then no herostat hero) does so in every seat build, with the DLL too (no party record).

Branches that would be empty without the DLL carry `debug("x1: xml2-fix forced teams" )` (XML2 retail never has an
empty block). `scripts_transform.selftest` runs each block through `run_pack_ops` in the three cases (DLL and
feature on, feature off, DLL absent).

### 19.2 What is emitted (`scripts._script_text`, seat builds)

| piece | where | block |
|---|---|---|
| seat block | the final load of every copy of the begin body of the 46 seated missions (`forced_party_in_bodies`; 70 starts: `x1/missions/begin_<m>` + the copies inlined in briefings / zone scripts) | `seatParty` (XML1's builder: REQUIRED, RECOMMENDED, minus RESTRICTED, cap maxheros; Cyclops left out of `alison` / `dr_mag2`, `JOIN_LATER`) + `setSkinset` + `loadMapKeepTeam(z)`; else `loadMapChooseTeam(z)` |
| skinset block | before the final load of the other 55 begin bodies (81 starts; free missions, the cut `nyc_rooftops` / `boss_sabreroof` / `ice_wolverine`) | `setSkinset` only |
| push block | after the `XML1 beginSideMission(s)` marker of `loadjuggernaut` (jug_fb) / `loadsentinel` (sent_fb) / `astral/savepx/xcrystal_destroyed` (astral_sk); before the marker of `begin_dr_mag1` / `begin_wx_fb_start` / `begin_muir2_reboot` (their conversation `chosenscriptfile` is the only thing that runs them; checked at build time) | `pushParty("_ACTIVE_HERO_" )` |
| pop block | the `loadZone(caller, "")` after every `XML1 endSideMission from side mission s` marker of a seated side mission (`nycfb4_finish`, `fmvexit`, `end_fb`, `endreboot`, `shadowking_defeated`) and the generated `x1/missions/end_jug_fb` | the parent mission's `setSkinset` + `popParty(caller)`; else `loadMapChooseTeam(caller)` (roster T9, simplest variant) |
| T9 simple | the end site of a side mission that is not seated (none in the default roster) | `loadMapChooseTeam(caller)` in place of `loadZone` |
| join | `nyc/alison/add_cyclops`, `mansion/dr_mag2/blob/add_cyclops` (`join_hero(add_hero=True)`) | XML1's popup + `waittimed` first (19.7), unlock, join bit, then `x1ah = addHero("cyclops" )` + remove the double behind `xml2fixFeature("addhero")`; if that left `x1ah` 0: remove the double + `x1ah = joinHero("cyclops" )` behind `xml2fixFeature("joinhero")`; `if x1ah == 0` the T7 block |

`setSkinset(costume, heroes)` arguments (`scripts.skinset_args`): `default` / none -> `("default", "")`; otherwise
the XML2 costume name of the XML1 variant (`magmacivilian` -> `civilian`, `heroes.COSTUME_RENAME`) and the sorted
list of the port's heroes whose XML1 herostat has `skin_<skinset>` (`civilian` -> `colossus,iceman`, so Magma
stays in uniform in the `civilian` briefings, decision 7.5). The New Game hook is built from the menu-mode text of
`begin_alison` (XML1's opening stays `[Game] NewGameTeam` + `loadMapKeepTeam`, T8).

`scripts.forced_party_plan(ctx)` (pure, cached) is the per-mission table (status `seat` / `menu` / `cut` / `free`,
seat list, skinset, zone); `scripts_detail.json forced_teams` has it with the emitted blocks. Counts:
`forced_party_seat_missions` 46, `forced_party_seat_blocks` 70, `forced_party_skinset_blocks` 81,
`forced_party_unseatable` 0, `forced_party_cut_zone` 3, `side_push_sites` 6, `side_pop_sites` 6,
`join_addhero_branches` 2. A planned block that is missing, a side mission pushed without a pop (or popped without
a push) and an xml2-fix call outside its guard are build errors.

### 19.3 Data changes (`scripts.rewrite_data_tree`)

- **jug_fb's exit is a dialog**, not `missions/jug_done.py` as the design read it (that script is the scriptstart
  of XML1's `dr_mansion1b`, which nothing starts): `dialogs/jugdead` option "Return to Beast",
  `script="endSideMission('true')"`. A dialog option runs one console token, so seat builds point it at the
  generated `x1/missions/end_jug_fb` (`INLINE_SIDE_ENDS`), which the zones closure packages with the jugrnt zones.
  It returns to the pushing spot (mansion2's `subbasement2`, where `loadjuggernaut` runs), as decision 7.6 wants.
- **Cut missions** (all builds): a conversation response that starts a forced mission whose zone XML1 never shipped
  is removed (`_drop_cut_mission_responses`): `nyc/riots/3_2_6` (the reply that starts the cut rooftop mission)
  (`nyc_rooftops`, zone `nyc/riots/nyc_roof1`). A line keeps at least one response.

### 19.4 Validator V14

| id | check | severity |
|---|---|---|
| V14a | `xml2fix_api.json` equals `scripts_transform.XML2FIX_API` and is merged into seat builds' API; any xml2-fix call in a menu build, or in inline data / dialog code, is an error | error |
| V14b | `scripts_transform.xml2fix_guard_problems` over every XML1 script with a call: declared (`iadd(0, 0 )`) then assigned from `xml2fixFeature("forcedteams"\|"addhero"\|"joinhero")`, the call in the `then` branch of `if <v> == 1` of the right feature (`addHero`: `addhero`, `joinHero`: `joinhero`) | error |
| V14c | every `seatParty`: the seat-block shape, 4 names compact without duplicates, herostat heroes of this build, `Maps/<z>.XMLB` exists, equal to the plan of the begin body it sits in (the `--start-party` hook: its option, every seated hero unlocked by an `unlockCharacter` above the block); each seated mission's `begin_<m>.py` has exactly one | error |
| V14d | `setSkinset` costume in the table at 0x6d8aa0, every hero in herostat with that `skin_<costume>`, one per `begin_<m>.py`, equal to the plan | error |
| V14e | `pushParty` / `popParty` paired per seated side mission; `popParty` last in its branch, its fallback zone exists, no other console command queued before it in its script run | error |
| V14f | `addHero` / `joinHero` only in `JOIN_HERO_SCRIPTS`, after `setGameFlag("x1join", bit, 1 )`, followed by the `if x1ah == 0` T7 block; `joinHero` assigned to `x1ah`, right after the double's `remove`, the last statement of its branch and the only console command of its run (`scripts_lint.console_overflows` limit 1: it queues the reload); every join script of a seat build has its `joinHero` | error |
| V14g | unseatable (none by default; astral_sk / boss_shadowking in `--hero-roster 21xml2`) and cut (nyc_rooftops, boss_sabreroof, ice_wolverine) missions; any conversation / script that can still start a cut mission | warn |
| V14h | (every build) a join script's popup comes before the join bit and its next statement is a `waittimed`; each join zone's script ends with the late removes of the NPC double (`if x1j == 1` / `waittimed` / `remove` ... / `endif`) | error |

V7 (`validate_script`, every XML1 script): a call that opens a menu or reloads (`validate_script.POPUP_BLOCKERS`:
`extractionPointChange`, `joinHero`, `popParty`, `blackbirdMenu`, the `loadMap*` / `loadZone` / `restorelastzone`
loads, the shop / codex / review menus ...) after a `createPopupDialogXml` with no `waittimed` between them (the wait
runs out only once the popup is closed) is an error `popup pending` (on any path: if / else branches apart; the only
case in the port was the nyc join, 19.7). V6 (zones section 18): the join zones' slot-2 starts are not
`startenabled="false"`.

### 19.5 Test hooks and harness

- `build_xml1.py --start-zone Z --start-party h1,h2 [--start-skinset costume:heroes]`: the New Game hook unlocks
  the heroes, then runs the seat block for `Z` (section 7), as a real forced start does (`begin_mansion1`:
  `unlockCharacter("magma", "" )` before its seat block). The main session's test 2 build: `build/_ft_hub`
  (`--no-movies --start-zone mansion/man1a/mansion1a_1 --start-party magma --start-skinset civilian:magma`).
- `tools/harness.py install <out>` writes `[Game] ForcedTeams=1` by default (`--forced-teams 0` writes 0,
  `--forced-teams off` no key), `--add-hero` writes `AddHero=1`, `--no-join-hero` writes `JoinHero=0` (the joins
  then open the T7 team menu; without the key xml2-fix has joinHero on). ForcedTeams defaults on because the fallback is
  safe: with ForcedTeams=0, no key, an xml2-fix build without the module (GetPrivateProfile ignores the unknown
  key) or no DLL, the same scripts open the team menu - at forced starts as before, and at side-mission returns
  where the old scripts kept the flashback party (19.1).

### 19.6 Not verified (in game, FORCED_TEAMS_DESIGN.md section 6)

The DLL module itself (another workstream), every seat / pop / addHero path, a seated party whose RECOMMENDED
heroes may still be locked (sent_fb and asteroid_rock unlock only their REQUIRED hero), whether
`wx_fb_start` can be offered during `mansion3_uniform` (the return would then put Magma in civilian), and the
UNVERIFIED items listed in the design's section 7. Side finding, not changed: the free missions `muir`,
`muir_int`, `sewers_hub2`, `boss_multipleman` and `nyctest2` also load zones XML1's data lacks (`forced_party_plan`
`cut` True, status `free`).

Script node pool (V7 `zone_pools`, 620 nodes, 0x4d7e6e; per-zone residency unverified): the blocks add statements
to every zone whose package lists scripts holding begin bodies. `build/_cyc` (before this section) -> `build/_ft`:
`nyc/riots/nyc3_2_1` 576 -> 602 (four such scripts: `beginriotsmission` 39 -> 45, `begingrsomission` 29 -> 35,
`beginmuir3mission` 23 -> 29, `beginmansion7mission` 16 -> 24), `muir_is/muir3/muir_in3` 542 -> 576,
`mansion/man2/subbasement2` 196 -> 244 (the largest growth, far from the limit). No zone passes 620, but
`mastermold/mastermold2` (613, unchanged) and `nyc3_2_1` (602, 18 nodes left) are the zones to watch in game. If
headroom is needed, the skinset block's `debug` keep-line is the cheapest statement to drop, but only once an empty
`if` block without the DLL is shown to compile (XML2 retail never has one).

### 19.7 Joins without the team menu: `joinHero` (2026-09-28 night)

XML1's `addHero("cyclops")` (nyc1_1_3, mag_nyc4) took the NPC into the party where it stood. The dormant
`0x46c9f0` returns true and seats nobody (`AddHero` stays 0), so the joins opened the T7 team menu: the player had
to place Cyclops and accept, backing out lost the join, and Owen's pad-B back-out once hung the game. xml2-fix
`joinHero(hero)` (0c82a6e; `[Game] JoinHero`, on with `ForcedTeams=1` unless 0; `xml2fixFeature("joinhero")`) does
what the menu's accept does, without the menu (design 1.3.6): `pushsidemission <_ACTIVE_HERO_>` run now, the hero
into the pushed record's first empty party name (`+0xa4 + 0x20 slot`), `restorelastzone 0` queued - next frame the
game seats the record's names, reloads the zone and puts the party back on the saved spot, and the load pops the
record (`loadmap <zone> 1`, 0x5f48d3). 1 = the reload is queued, 2 = the hero is in the party already (no reload,
no fallback), 0 = refused (logged in `xml2-fix.log`; the script's T7 block runs). **Verified in game** (main
session, build/_jh, 2026-09-28 night): walked into trigger_touch03, `joinHero("cyclops") -> 1 ... restorelastzone 0
queued`, no team menu, the zone reloaded with 2 HUD heads, Cyclops fighting.

The join script (`scripts_transform.join_hero` / `join_block`, seat builds; nyc shown):

```
sound (  "PLAY_SOUND", "voice/cyclops/1_1_0045_1", "", "" )
waittimed ( 1.000 )
waittimed ( 1.000 )
createPopupDialogXml("dialogs/tut15" )       # XML1's join popup, first
waittimed ( 0.500 )                          # runs out only once the player has closed it
unlockCharacter("cyclops", "" )
setGameFlag("x1join", 1, 1 )
x1ah = iadd(0, 0 )
x1ah = xml2fixFeature("addhero" )
if x1ah == 1
     x1ah = addHero("cyclops" )
     remove ( "cyclops_x1double", "cyclops_x1double" )
endif
x1jh = iadd(0, 0 )
if x1ah == 0
     debug("x1: xml2-fix forced teams" )    # keeps the block non-empty without the DLL
     x1jh = xml2fixFeature("joinhero" )
endif
if x1jh == 1
     remove ( "cyclops_x1double", "cyclops_x1double" )
     x1ah = joinHero("cyclops" )
endif
if x1ah == 0
     remove ( "cyclops_x1double", "cyclops_x1double" )
     extractionPointChange("_ACTIVE_HERO_", 0 )
endif
```

The double is removed before the reload (it would stand next to the party otherwise). `joinHero` is the last
statement of its branch and the only console command of the run (its reload must be the only command waiting;
xml2-fix refuses with any other command queued).

**The join popup** (nyc only: `dialogs/tut15`, "Co-op will become available when new X-Men become unlocked for
play!"). In game (main session, the same night): created 2 s after the trigger with `extractionPointChange` in the
same run, it stayed up UNDER the team menu, invisible, and broke the menu (after one Enter the hint bar dropped to
"Details / Accept", Replace/Details stopped responding) - the likeliest cause of Owen's hang. Shown instead from the
reloaded zone's script (a first fix) it fired while the restorelastzone loading screen was still up and was lost.
What works (verified): the popup, then `waittimed ( 0.500 )` - the game pauses while a popup is up, so the wait
runs out only once the player has closed it (the next statement ran 0.4 s after the close), and only then comes the
join, whose reload or team menu never has it pending. XML1 showed it at the join too. `join_hero` moves the popup
(with the waits that followed XML1's join) before the block and adds the wait; the T7 fallback and `--forced-teams
menu` builds get the same order.

**The NPC double after later loads.** The zone guard removes trigger_touch03, the spawner and the double while
x1join's bit is set, but the spawner's instant spawn comes AFTER the zone script's removes (in game: bit 1 set, the
guard ran, the double still stood there; a `remove` sent after the load cleared him). The zone script now ends
with late removes (`join_hero_zone_guard`, `JOIN_LATE_REMOVE_WAITS`): `if x1j == 1` / `waittimed` / `remove(double)`
after 0.25, 0.5, 1, 1.5, 2, 2.5, 3.5, 4.5, 6.5 and 10.5 s. The zone script's waits already run under the loading
screen and the load's length varies, so the removes are repeated (a remove of an absent entity does nothing); at the
end of the zone script they delay nothing else. The alternative (the spawner not instant, acted by the zone script
while the bit is clear) is not verified.

**Where Cyclops appears.** After the join's reload the party is put back on the saved spot at the pop (0x5f44a0 ->
0x489300, before the load: the bodies that exist then, Wolverine's), and the new hero spawns at the zone's slot-2
start `player_start01` (-481, 946, -231), about 200 units south of the NPC's spot (-430, 1150, -201) and 50 from the
entry start `player_start02` (slot 1): in view, just behind Wolverine at the trigger. XML1 put him on the NPC's spot;
accepted (a `copyOriginAndAngles("_HERO2_", ...)` in the guard is possible, not done). `player_start01` was
`startenabled="false"` and only the trigger's `acttargets enable_target01` enabled it, for that load: every later
load (save/load, re-entry, `loadMapKeepTeam`) loaded Wolverine alone with Cyclops seated in slot 1 (in game).
zones section 18 (`zones.enable_join_starts`) sets the join zones' slot-2..4 starts `startenabled="true"` (verified
in game by hand the same day); before the join the party has one hero, so the start is unused. V6 checks it.

### 19.8 Team lock at the Xtraction Points (2026-09-29; research/online/online_forced_parties.md)

XMen2.exe's Xtraction menu (`extractionPoint` 0x4a6b50) offers Change Team anywhere, and its team menu lets every
player pick any unlocked hero: in game (online) a player on standby took Gambit into alison's Wolverine-alone
stretch and the host swapped Wolverine for Iceman at nyc1_1_3's X-point (single player: the same swap). XML1's
Xtraction team change kept a mission's REQUIRED heroes and maxheros. xml2-fix f06f2e2+ (`[Game] ForcedTeams=1`)
greys Change Team out while game flag `teamlock` bit 1 is set; seat builds set it (`scripts.team_lock_plan`,
`scripts_transform.team_lock_at_markers` / `team_lock_at_side_ends`):

- after every `XML1 beginMission(m)` marker (every copy of every begin body and the New Game hook):
  `setGameFlag("teamlock", 1, 1 )` for a seated forced mission (`forced_party_plan` status `seat`), `0` for every
  other; a `--newgame chooseteam` hook gets 0 (the player picks the opening party);
- before every `XML1 endSideMission from side mission s` marker of a seated side mission: the caller mission's
  value (`SIDE_MISSIONS`), as `popParty` returns there.

The flag is saved with the game and streamed to joiners with the host's save, so every machine greys the same option.
`mission_header_end` counts the lock comment as header (V-H13). Deviation: `asteroid_rock` (maxheros 4, only Frost
REQUIRED) is locked whole at asteroid1_1's X-point, where XML1 let the player swap the other three. Saves made before
this have no flag (unlocked) until the next mission start.

## 20. Unlock points: Jubilee, Colossus, Psylocke (2026-09-28)

*Superseded by the section "XML1's per-mission hero unlocks" (issue #55): the three hand-placed unlock points were a stand-in for XML1's table and are gone.*

XML1 unlocked these three through `data/missions/missions.xml` `charunlock`, not through a script or a conversation
(research/heroes/roster.md 1.1.3 / 4). Owen's decision: at the start of the mission after which XML1 first shows them
as NPCs, in story order - `scripts.MISSION_START_UNLOCKS` = mansion2 -> jubilee, mansion4 -> colossus, mansion7 ->
psylocke. `scripts_transform.unlock_at_mission_starts` (in `scripts._base_text`, so every copy of a begin body
stays identical for the SPEC 19 body matching) puts `# ( "x1: XML1 unlocks <h> at this mission ..." )` +
`unlockCharacter("<h>", "" )` at the end of the body's header (after the REQUIRED unlocks, before the movie / load),
in all 6 copies: `x1/missions/begin_mansion2` + haarp `nextmission`, `begin_mansion4` + muir2 `endmuir2`,
`begin_mansion7` + `mansion/man7/beginmansion7mission`. Idempotent; count `mission_start_unlocks` (6); a copy without
exactly one unlock is a build error, and heroes **V-H13** checks `<out>` the same way (SPEC_heroes 7). Pools:
`nyc/riots/nyc3_2_1` 602 -> 603 statements.

## 21. M2 front end: XML1's main menu, Danger Room and Review data (2026-09-28)

The design, with every exe address and the reasons, is `research/frontend/M2_DESIGN.md` (sections A-C, D.1, F).
This section records what the pipeline builds. Owen's decisions (the design's section E defaults): 7 main-menu
buttons (XML1's 6 + Quit), pure XML1 intro logos, `x_mansion` as the main-menu loading screen, trivia split over
the mansion acts, Danger Room XP by XML2's reclevel curve and comic stat rewards scaled like the hero stats,
XML1-unobtainable extras stay locked (the Nightcrawler comic, the `marvel` concept group, r309), credits = XML1's plus
a short port block. Section 11.1 (XML2's front end kept) now applies only to `--frontend xml2`.

### 21.1 The switch

`build_xml1.py --frontend xml1|xml2` (also `$XML1BUILD_FRONTEND`; default `xml1`). `xml2` is the front end before
this section, byte for byte (21.7): nothing of 21.2-21.5 is written and every provider below returns XML2's rule.
Code reads the mode through `common.frontend_mode(ctx)`; `common.frontend_zones(ctx)` / `frontend_prefixes(ctx)`
replace the `FRONTEND_ZONES` / `FRONTEND_PREFIXES` constants everywhere (zones, validate, the V6 rule). A new
content module `frontend` runs after media (`common.MODULE_ORDER`). `CONTENT_OPTS['frontend']` re-runs scripts,
zones, media and frontend when the option changes (a build from before this section counts as `xml2`,
`LEGACY_OPT_VALUES`); `report.json build.frontend` records it, and `common.args_for_out(out)` rebuilds a build's
options for the standalone tools (validate, zones_selftest, scripts_selftest).

### 21.2 Main menu (A)

| Piece | Module | What is built |
|---|---|---|
| backdrop | zones | `menu/main_back` is converted like any zone: XML1's Cerebro room (`Maps/menu/main_back.{XMLB,CHRB,BOYB,IGB}`, `MotionPaths/menus/main_back.IGB` with `mp_camera`, the zone anim DB `zone_main_back` from `mission_menu`). The world keeps XML2's `nosave` / `startblack` (the existing replaced-zone rule of `mutate_zone`); the package keeps XML2's `bigconvmap off` and `xml data/npcstat` (`Zones.menu_zone_xml2_entries`). zoneinfo keeps XML2's entry (act 1) with `loading="textures/loading/x_mansion"` (`C.FRONTEND_MENU_LOADING`; XML1's zoneinfo has no entry). The act plan never touches a menu zone (`C.MENU_ZONES`, both modes). |
| zone script | scripts | XML1's `menus/main_back_main.py` (byte-identical to XML2's) is installed; XML2's `main_back_debug` stays. |
| intro | scripts | `Scripts/menus/intro_normal.py` (XMen2.exe runs it at boot, 0x402cd1) is generated (`scripts.frontend_scripts`): `startMovie` xi102, xi101, xi103, xi104, xi105 (Activision, Marvel, Raven, VV, Sofdec through `media.movie_name`), each with its `waitsignal`, then `mainMenuExit()` (not XML1's `openmenu("main")`: `mainmenuexit` loads the backdrop). `--no-movies` builds keep the same script (a missing movie signals at once). |
| menu IGB | frontend | `UI/menus/x1_menu_main.IGB` = XML1's `ui/menus/menu_main.igb` (3D logo, lights, button layout; nodes `button1..9` = the text anchors, `button1..9_back` = the button meshes, `button1..9_highlight` = the focus models, `desctext1`, `version`; `frontend.menu_igb` checks every node the menu names, `igb_string_fields`) **re-framed on XML2's menu camera** (21.2.1). The `x1_` name keeps XML2's own `UI/menus/menu_main.IGB` (an unused prototype) untouched; the menu file and the package name the IGB. The first cut renamed 7 back-nodes to `label_option04..08` / `label_credits` / `debug_text` and put the text on them: the game drew no text on a button mesh (seen in game 2026-09-28), so XML1's own binding (text on `buttonN`) came back with M2_DESIGN's fallback A3. |
| menu file | frontend | `UI/menus/main.{XMLB,engb}` (English in both) = XML1's `ui/menus/main.eng` in XML2's schema: `MAIN_MENU`, `igb="x1_menu_main"`, `fullscreen="false"`, `lighting="true"`, `image="textures/loading/x_mansion"`; XML1's items in XML1's order: `button1..9_back` (`MENU_ITEM_MODEL`, `enabled="false"`; 9 hidden), `button1..9_highlight` (models; 9 hidden), the 8 text items `button1..8` with XML1's texts and each action in its `usecmd`, so keys and the pad work without an exe change (Begin Story `resetgame;runscript setDifficultyLevel(1)` = XMen2.exe's `newgame` without its difficulty prompt, 21.2.2; Load Game `runscript saveloadProcess(3)`, Danger Room `set drmode 1;openmenu danger_room` = XMen2.exe's own line for its item (0x68d184; the exe's story-level-6 gate is not reproduced, XML1's menu had none), Options `options_main`, Review `set reviewmode -1;openmenu review`, Credits `openmenu credits`, Play Online `openmenu online` (21.2.4), Quit = `button8` without a usecmd), `button9` hidden, `desctext1`, `version`. Text style `STYLE_MENU_BLACK`, XML1's (default.xbe style table 0x458d80: colour 9, focus 10, disabled 5, font big; XMen2.exe's has the same indices and font, which XML2's colour table makes dim white / white; XML1's were blue), centred (both exes' default, 0x5c6eb1 / xbe 0x17d8e6); no `mode` (MAIN_MENU never toggles modes; 0x5acf30's callers are other menus). `up`/`down` one wrapping cycle, `startactive` on `button1`, focus highlight through `<onfocus item="buttonN_highlight" type="focus|nofocus" model=...>` (XMen2.exe does not read XML1's `focusitemname` / `focusmodel`). No item is named `label_option06` / `label_option09`: XMen2.exe runs its own Danger Room gate / `openmenu online` for those names whatever the usecmd. |
| mouse, Quit | harness + xml2-fix | XMen2.exe's MAIN_MENU hit-tests only the items named `label_option04..09`, `debug_text`, `debug`, `debug_focus` (0x5c933f..0x5c93bf) and quits on the item named `debug_text` (text "Quit", quit flag 0x6f3a2d; no console command or script function quits). xml2-fix `[Game] MainMenuItems=button1,button2,button3,button4,button5,button6,button8` (`frontend.MAIN_MENU_ITEMS`) points those name pushes in MAIN_MENU's code at ours, in that slot order: `button1..6` = the six mouse slots, `button8` = Quit (the exe sets its text and replaces its usecmd with a dummy); Play Online (`button7`) has no mouse slot (21.2.4). `tools/harness.py install` writes the key read off the build's `UI/menus/main.XMLB` (`harness.build_menu_items` / `menu_items_for`; `frontend_selftest` U2 keeps the two lists equal). Without it: keys and pad work, the mouse hovers nothing and Quit does nothing. |
| package | frontend | `Packages/generated/maps/package/menus/main.PKGB`: `model ui/menus/x1_menu_main`, XML2's PC `ui/models/model_button`, `model_button_highlight`, `model_hide`, `xml ui/menus/main`. |
| music | common / media | `planned_sound_banks` makes `menu_a` / `menu_c` kind `x1` (`'frontend': True`) with the all_ima plan source; media installs the fixed-layout bank (`research/sound/music0x20/banks/eng/m/e/menu_{a,c}.zss`, checked against the Xbox original like every XML1 music bank). `C.FRONTEND_MUSIC` is the only allowlist for an `x1` bank over an XML2 bank (media, V2). The credits menu plays `music/menu_a` too. |
| save / load texts | frontend | every base `igct*.bnx` (the game folder's root) that names XML2 and both halves of `Data/strings`, with XML2's name replaced by the port's (21.2.3). |

#### 21.2.1 The menu camera (the invisible New Game prompt, 2026-09-28)

Seen in game with XML1's menu IGB byte for byte: Begin Story ran `newgame`, but its difficulty prompt was not drawn
(Enter accepted the default; with the mouse the player was stuck). Cause (research/frontend/M2_DESIGN.md section G):
XMen2.exe draws a menu's IGB in menu layer 0 through the IGB's own camera, as an orthographic view the size of the
virtual screen centred on the camera and clipped by its near / far planes, and draws its own overlays in the same
layer at fixed depths - the box of every dialog (`0x5eb300`: the difficulty prompt, the save / load lists) at y -700,
the text system (dialog text, the help line) at y -800 / -850. Every x2m_* menu IGB XML2 uses has its camera at
(256, -1000, 192), near 100. XML1's `Camera01` sits at (254, -1108.19, 141) with near 897 / far 1263 (XML1's
convention; XML2's unused `menu_*` leftovers have it too): the overlays were in front of its near plane, and the view
was 51 units off the frame the mouse maps onto (virtual screen = world x / z).

`frontend.reframe_menu_igb` (an in-place edit through `igb_file`, a small reader of the IGB layout; sizes unchanged)
moves the whole scene rigidly by the camera's offset to `MENU_CAMERA_POS` = (256, -1000, 192): the 30 transforms
outside any transform (Camera01, the 27 button nodes, `desctext1`, `version`), the 5 bounds and 4 vertex blocks
(3,587 vertices) of the world-space geometry (the 3D logo, its plate) and the 5 lights; the camera's near plane
becomes XML2's 100 (far stays 1263). The picture through the camera is the same; the overlays are drawn over it;
the drawn buttons sit where the mouse hit-tests them. Anything it cannot place or move (an unknown world node type, a
turned camera, a block of another size) is refused whole (build error). Idempotent. XML1's own flow had no difficulty
choice at all (default.xbe has no difficulty string; its `newgame` is `resetgame` + `beginmission alison`): since
21.2.2 Begin Story no longer opens the prompt; the re-frame still matters for every other dialog over the menu (the
save / load lists, Load Game's message).

#### 21.2.2 Begin Story: New Game on Normal, no prompt (2026-09-28)

XML1 asked for no difficulty (default.xbe has no difficulty string; its `newgame`, xbe 0x18d0b0, is `resetgame` +
`beginmission alison`), so the port's Begin Story starts a New Game on Normal at once (Owen: faithful XML1 behaviour).
XMen2.exe's console command `newgame` (0x5f3610, registered at 0x5f4929) is `resetgame` (0x5f2e70) followed by
`startgamedialog` (0x5f2090): the prompt "Choose a difficulty level:" (strings 0x866) with Easy / Normal / Hard (0x867 /
0x868 / 0x869; Hard shown only when the profile has it unlocked), each running the script `setDifficultyLevel(n)` (0,
1, 2), the default selection the current difficulty. `setDifficultyLevel` (0x4a0930, script table entry 0x68b7a8)
writes n through the game object's setter (0x729960 vt+0x26c = 0x469d40: `[0x729960+0x60c]` = 0x729f6c; registered as
the programmer var `difficulty` at 0x4690a9, Normal at boot; `resetgame` does not touch it), then asks
the profile (0x72c530 vt+0xb0 = 0x48f730: bit 2 of `[+0x229]`) whether Hard is unlocked. No: it has the console queue
`runscript startFirstMission()` (0x4a0ab1) and hands the menu's controller on (0x4a0acf); `startFirstMission`
(0x4a7b10) seats the starting team and runs `Scripts/menus/new_game.py` (difficulty < 2, 0x4a7c42; the port's New Game
hook). Yes: it opens XML2's New Game+ prompt instead (0x86a "Choose a saved game to load character statistics from, or
use the default character statistics.", `useDefaultStats()` / `useSavedStats()`). The end credits set that bit after a
win on Normal (CREDITS_MENU state 3, 0x5b1d44), so a port player who finishes the campaign would meet it.

- **Begin Story** `usecmd` = `frontend.BEGIN_STORY_CMD` = `resetgame;runscript setDifficultyLevel(1)`: the two steps of
  `newgame` with the prompt's Normal choice in place of the prompt. The console runs a line at once (0x55beb0), `;`
  separating commands; `runscript` reads one word, and code with `(` runs as a statement (the same way XMen2.exe itself
  sends `runscript startFirstMission()`). Data only: it works with any xml2-fix (or none).
- **No New Game+**: xml2-fix `[Game] NewGamePlus=0` (branch display 723e592, `new_game_plus_rules.hpp`) turns the je at
  0x4a099e (after the profile's answer) into nop + jmp to the same target 0x4a0a9c, the not-unlocked path, after 9
  guards match; `tools/harness.py install` writes it with `MainMenuItems` (the XML1 front end, `harness.NEW_GAME_PLUS`).
  XML1 had no statistics choice either (its strings.eng has no such text). Without the key a port player who finished
  the campaign on Normal gets the statistics prompt on the next Begin Story (Enter = default statistics).
- `--frontend xml2` keeps XML2's New Game (`newgame`, the prompt, no key).

Checks: V15 (Begin Story's usecmd is `BEGIN_STORY_CMD`; no main-menu item runs `newgame` / `startgamedialog`),
frontend_selftest U2 (the usecmds, XML1's own `newgame` as the source, harness's `NewGamePlus=0`), validate_selftest
(Begin Story back on `newgame` -> 2 V15 errors), xml2_test (the guards against XMen2.exe, exactly the je's two opcode
bytes changed, the jump target kept). In game: Begin Story -> nyc1_1_1 with Wolverine, no prompt; the log shows
`new game: no New Game+ ([Game] NewGamePlus=0)`.

#### 21.2.3 The game's name in the save / load texts (2026-09-28)

The Load Game dialog's no-save-data message named XML2. XMen2.exe's PC save messages are not in
`Data/strings`: its message function (0x55e9b0, vtable 0x69ab00) maps message codes 0..0x23 to keys of `igct<lang>.bnx`
in the game folder (key=text lines, CRLF, latin-1; `igct` + "" for eng, `igctfre` / `ger` / `ita` / `pol` / `rus` /
`spa`, 0x4032b2) and looks them up (0x629bf0); the codes without a key fall back to `Data/strings` id 0xc80 + code
(0x55ea74 -> 0x55eb30), the consoles' memory-card texts. Names of XML2 the XML1 build could show:

| Where | Text | Port |
|---|---|---|
| `igct*.bnx` `EMSG_NO_DATA_DEVNUM` (code 7, 0x55ea04) | the no-save-data message, naming XML2 (Load Game without saves) | the same message with the port's name |
| `igct*.bnx` `EMSG_INSUF_SPC_DEVNUM_BLOCKS` (3), `EMSG_NO_GAME_DEVNUM_BLOCKS` (22) | disk-space / no-game-data texts | the port's name |
| `Data/strings.engb` 3328 (`@MEMCARD@XBOX_DELETE_CORRUPT_QUERY`, fallback code 43) | the damaged-save message, naming XML2 | the port's name |
| `Data/strings.engb` 3105, 3203.., 3300.., 3500.. (18 more) | PS2 / Xbox / GameCube memory-card texts (codes with an igct key never reach them) | the port's name (consistency) |
| XMen2.exe 0x6a3a70 "X-Men Legends 2" (0x5faf43, the display's create-window call) | the window title (taskbar / title bar) | exe-embedded: not changed (an xml2-fix title option would be a separate decision; xml2-fix already hooks CreateWindowExA in display.cpp) |
| XMen2.exe 0x6a3a70 at 0x5f5215, 0x6174dc, 0x618484, 0x61bbda.. | the registry key `Software\Activision\X-Men Legends 2` (settings) | not shown |
| XMen2.exe 0x69ab14 / 0x680048 | `Documents\Activision\X-Men Legends 2\Save` / `Screenshots` | xml2-fix `[Game] SaveFolder` (the port: "X-Men Legends") |
| XMen2.exe 0x688cf0: the demo's end message | demo builds only | not shown |
| `Docs/ENU/*` | XML2's readme / manual files | not in the game |

`frontend.igct_retext` replaces `X-[Mm]en Legends (2|II)` (not followed by a letter or digit) with "X-Men Legends"
(XML1's own spelling, its strings.eng 3105) in every line of every base `igct*.bnx` that has it (3 keys in each of the
7 files; the lines are otherwise byte-identical; idempotent) and writes the file at the root of `<out>`;
`frontend.strings_retext` does the same to the English texts of `Data/strings.engb` (19 ids) and writes both halves
(the `.XMLB`, keys, unchanged - V3's localized-pair rule). `--frontend xml2`: nothing written (XML2's files). Checks:
V15 (every such igct file written by frontend without the name, igct.bnx `EMSG_NO_DATA_DEVNUM` = the wanted text,
`Data/strings` without it; xml2: none registered), frontend_selftest U15 + the build checks, validate_selftest (XML2's
igct.bnx back -> 2 V15 errors).

#### 21.2.4 Play Online (2026-09-29)

The port online test (`research/online/port_online_test.md`) found no online item in the XML1 menu. XMen2.exe opens
its online screens (XML2's, still in the build and working in the port) from MAIN_MENU only for an item named
`label_option09` (0x5c9803 compares the focused item's name with the cell 0x6e662c, then the menu manager's
vt+0x6c("online"), 0x5c9857), a name XML1's menu must not use (`EXE_MENU_FORBIDDEN`). `console openmenu online` on a
fresh boot reaches them, but Host / Join then crash (`igControllerManager::getController` from 0x5517db); after the
accept of any main-menu item it works every time.

- **Item.** `button7` "Play Online" (XML2's text) with usecmd `frontend.PLAY_ONLINE_CMD` = `openmenu online` - what
  the exe runs for XML2's item; the item's own accept comes first, which is the crash fix. Last before Quit, as in
  XML2; Quit moves to `button8`, `button9` stays hidden; the up/down cycle has 8 items.
- **Layout.** XML1's IGB has 9 button slots, but only button1..7 fit the view (XML1's button8 text anchor sits on its
  bottom edge: z -51.5 with the camera at z 141; a debug slot). `frontend.space_menu_buttons` (after the re-frame, in
  place, z floats only) spreads the 8 buttons evenly over XML1's button1..button7 span, each kind (text anchor
  `buttonN`, mesh `_back`, focus model `_highlight`) from its own button1 z to its own button7 z: spacing 32.56 ->
  27.91 units (61 -> 52 px at 720 lines), top and bottom unchanged. The nodes have no bounds (item rectangles come
  from node positions, 0x5bc530). With 7 buttons it would keep XML1's own positions.
- **Mouse.** XMen2.exe's MAIN_MENU hit-tests 9 names (0x5c933f..0x5c93bf: label_option04..09, debug_text, debug,
  debug_focus) but clamps every slot >= 6 to focus index 6 (0x5c944b `cmp edi, 6` / `mov ebx, 6` / `jge`): slots 7 / 8
  are Quit's models. `MAIN_MENU_ITEMS` = button1..6 (the mouse slots) + button8 (Quit); Play Online is keys / pad only
  (`MAIN_MENU_KEYS_ONLY`). `tools/harness.py` reads the value off the build's menu (`menu_items_for`: the first 6
  shown buttons with a usecmd, then the one without), so builds from before keep `button1..7`. With today's DLL an
  item named for slot 7 would focus and accept Quit: `MAIN_MENU_ITEMS_MOUSE_ALL` is only for the change below.
- **xml2-fix (queued, not part of the port):** when MainMenuItems names an 8th item (slot 7, `debug`), patch the imm8
  of `cmp edi, 6` at 0x5c944d from 6 to 8 (guard: `83 ff 06 bb 06 00 00 00 7d 02` at 0x5c944b): slot 7 then focuses
  and accepts its own item (0x5c9587 indexes the 9-slot array with the clamped index), slot 8 (`debug_focus`) still
  maps to Quit. The harness then writes `MainMenuItems=button1,button2,button3,button4,button5,button6,button8,button7`.

Checks: V15 (one item runs `PLAY_ONLINE_CMD`, shown, in the up/down chain, not in the Quit slot; every shown button's
three nodes on screen with a `MENU_EDGE` 16 margin and `MENU_MIN_SPACING` 20 apart; `x1_menu_main.IGB` =
`frontend.menu_igb`), frontend_selftest U1 (the spacing) and U2 (8 buttons, texts, usecmds, Quit on button8, harness
reading this menu and a pre-Play Online one but not XML2's, the clamp's retail bytes), validate_selftest (Play Online
out of the chain; XML1's IGB as on the disc now also puts button8 off screen). In game (build/_fe3, xml2-fix display
c17c158, fresh boots): the 8 buttons fit under the logo with the focus bar clear of the neighbours; Play Online ->
Play Online screen -> Ready -> Select Online Mode -> Host Game -> Game Options, and in a second fresh boot with
`[Online] Server=127.0.0.1` (nothing listening) on to Post Game -> the lobby "Campaign (Normal) : Player - Game" - no
crash (the console path crashed there); back out with Esc to the menu; Quit (button8) exits the game.

### 21.3 Danger Room (B)

`frontend.dangerroom_tree` writes `Data/dangerroom.{XMLB,engb}` from XML1's `data/dangerroom.eng`: 15 arenas (zone
ids normalised), 6 grades (Freshman `unlocked="true"`), 62 courses. Per course: `requirement` / `reward` (XML1
points) and `duration` dropped (never read; counts `dr_points_dropped`); `QE200` gets `rewardexam="true"`
(`DR_EXAM_FIXES`: XMen2.exe opens a grade with the previous grade's exam, XML1 gated Junior by points); `hero`
lowercased + `singleplayer="true"`; one `<REWARD type="Titanium">`: the XML1 `rewarditem` (19 courses), else
`rewardxp` by the build's XP curve (`frontend.course_reward_xp`, section 23.1): `0` with `--xp-curve xml1` (XML1 gave
no completion XP), with `xml2` XML2's own curve (`frontend.xp_curve`: per reclevel the smallest Titanium `rewardxp` of
XML2's non-exam courses, piecewise-linear, clamped, rounded to 50: rl1 200, rl8 2500, rl15 4500, rl21 6250, rl27
10000, rl38 25000); FR106's extra-credit outro (XML1 glyphs `{ | } ~` and `~NN` colour codes) is trimmed to "Well Done!".
Adamantium / Vibranium tiers are deferred (XML1's extra credits were default.xbe logic).

The 19 reward items are added to `Data/items` by zones as XML2 equipment (`frontend.dr_reward_items` feeds zones'
referenced-item set; `frontend.translate_equipment` replaces SPEC 11.3's equipment -> item downgrade for them):
`class` gloves / armor / belt by name (`equipment_class`: 7 / 5 / 7), XML2's `pickups/equip_<class>_c` model,
`cost 10000 enemy_level -1 heft light quality legend unique true` (XML2's challenge items), `<require
cat="character|level">` kept (XMen2.exe 0x4ac470 knows both), each XML1 `<activepowerup>` one `<enhancement
description><powerup life="-1"><affecter>`, only with affecter attributes XML2's own data uses:
`atk_damage_scale L` -> `damage` scale L with the same scope (`scope_damage` / `scope_node` on the affecter,
several `scope_damage` children -> one enhancement each, `scope_attack` children -> a `powerup_scope` affecter);
`def_damage_scale L` on `dmg_mental|energy|physical` -> `resist_*` 1-L; `strength|body|mind` x4, `speed` x2,
`traits` x2 (`frontend.stat_scale`, heroes.py's STAT_SCALE and speed slope); `power_cost` scale (Mask of Xorn,
ps_bishop's form). Rogue's `drain_time` has no XML2 affecter use and is dropped (reported). Arena worlds
(`arena/*`) get `nosave="true"` like XML2's DR arenas. characters' "XML2 Danger Room spawns dropped NPCs" defer is a
note under xml1.

### 21.4 Review, codex, trivia, credits (C)

All four tables are written English in `.XMLB` and `.engb`.

- **review_paths** (`frontend.review_entries`): a Credits entry first (XML2 convention), then XML1's 149 entries in
  order: 34 `cin` (value `media.movie_name`, `duration` = C0 ADX samples / rate, `media.movie_duration`; logos and
  promo i101-i105, i107 `unlocked="true"`), 64 `load`, 13 `comic`, 38 `concept`. Texture values through
  `common.map_review_texture`: `textures/comic/x1/<x>` and `textures/concept/x1/<y>` (XML2 ships rogue_cov,
  storm_cov and 27 concept names; the paths keep "comic" / "concept", which imageViewer's category test needs),
  numeric loading +14000, a named XML1 loading screen XML2 also ships -> `textures/loading/x1_<name>` (x_jet,
  characters_menu). Comic `reward_focus` -> `reward_mind` (XMen2.exe reads four stats), amounts x4 (speed x2).
  frontend imports the textures Review needs (13 comics, 38 concepts, `acolytes`, the renamed screens).
- **imageViewer literals** (scripts, `scripts_transform.rewrite_image_viewer` in `rewrite_data_tree` and `_base_text`):
  the 32 zone pickups name the x1 paths; the Colossus pickup's `comic/0901` becomes `col_cov`
  (`C.REVIEW_TEXTURE_FIXES`, the XML1 quirk).
- **zoneinfo** (zones): the renamed loading screens are imported as `textures/loading/x1_<name>` from XML1's file
  (`C.x1_loading_source`), so the 3 XML1 zones with `x_jet` show XML1's image and it unlocks in Review.
- **codex** (`frontend.codex_tree`): XML1's 26 entries in order; `Magneto` -> `MagnetoScripted` (the herostat Magneto
  is the placeholder); `anim` = XML1's if the character's anim DB (`Actors/<characteranims>.IGB`) has it, else
  `menu_idle`, else `idle`.
- **trivia** (`frontend.trivia_tree`): XML1's 50 questions (5 answers) split in XML1 order over the acts of the
  zones with a trivia console (`frontend.trivia_acts`: 1, 3, 5, 6, 8, 9 -> 9 / 9 / 8 / 8 / 8 / 8).
- **credits**: XML1's 513 lines, then `PORT_CREDITS` (a page break, "Legends Classic", "An unofficial fan port",
  Project: ChronoRixun, Engine fixes: xml2-fix); text codes escaped (21.4.1); the credits menus over XML1's backdrops
  (21.4.2).

#### 21.4.1 Text codes in credit and trivia texts (2026-09-29)

`research/campaign/late_game_test.md` B2: XML1's 21 credit lines with `#N` ("NYC Acolyte #1, Shadow") drew over
themselves. XMen2.exe's menu / HUD text renderer (0x5ef2e0) reads codes inside the text: `#` takes the next 3
characters through atoi as code 3000+N (0x5ef5dc..0x5ef60a), which the draw (0x5ee780, 0x5ee7f2) makes "pen x = N" -
a tab, so "#1, " moves the pen back to x 1 and "Shadow" is drawn over the line's start; the width (0x596df0) and wrap
(0x597c90) measures read it the same way. `~NN` / `~~` are colour on / off, `$NAME` a controller token (0x5ef6dd), and
`|c` is the character c itself (0x5ef4fa; the measures add c's advance and skip both). XML2's own texts never show one
of these characters (no escape in its data to copy). `frontend.escape_menu_text` writes `#`, `$`, `~` and `|` as `|c`
in every credit line (21 lines) and trivia text (1: a question naming a comic issue "#1"). The credit fonts have a
`#` glyph (x2f_med_pc / x2f_big glyph 35; `|` has none). XML1's tutorial dialogs keep their `$TOKEN`s (intended).

Checks: V17 (no credit / trivia text with `frontend.unescaped_menu_codes`), frontend_selftest U8 / U9 (the lines
changed are exactly XML1's 21 with `#` -> `|#`, the escape rules on probes), validate_selftest (a bare `#` back). In game
(build/_fe3, main menu Credits): both Voice Talents pages read "Moira, Female Prisoner #3", "NYC Acolyte #1, Shadow",
"Demon #1", "Soldier #4, NYC GRSO", "Debra Owens, Computer Voice #1", "Beast, Nuclear Tech #1," ... "NYC Acolyte #2,
Apocalypse" whole, with the `#` glyph.

#### 21.4.2 The credits' backdrop (2026-09-29)

B5a: the credits rolled over XML2's hero collage. XML1's credits menus (`ui/menus/credits.xml`: `CREDITS_MENU`
`igb="menu_credits"` `lighting="true"`; `credits_end.xml`: `igb="menu_credits_end"` `endgame="true"`; no image):
`menu_credits.igb` = a black plane with, in front of it, XML1's credits page (`credits_page.png`, 512x512 DXT inside
the IGB, a dark blue collage) lit by one directional light; `menu_credits_end.igb` = the black plane alone (the end
credits roll over black); both with XML1's camera (260, -1108.19, 200), near 897. XML2's credits / credits_end draw
`x2m_credits` (a 60% black plane) with `image="textures/loading/credits01"` and switch the image with 19 `texture`
credit lines (0x5b1e80); XML1's credits have none, so the port's showed XML2's collage throughout.

The `image` is the menu manager's, not the menu's: a menu with the attribute sets the manager's current image (vt+0x1c0,
0x5bba0f), and every menu opens with the manager's current image as its background sprite when that is not empty
(0x5bbbb5..0x5bbbe8 -> menu vt+0x84 = 0x5bb7b0: loads the texture, a sprite in the menu's layer; it also unlocks the
image in Review), drawn in front of XML1's planes. A first cut without the attribute showed the last image set - the
online screens' Apocalypse art after Play Online (seen in game). `image=""` empties it: no sprite.

The port: `UI/menus/credits.XMLB` / `credits_end.XMLB` = XML2's menus (type, endgame, lighting, precache) with
`igb="x1_menu_credits"` / `"x1_menu_credits_end"` and `image=""` (`CREDITS_MENU_SET`);
`UI/menus/x1_menu_credits{,_end}.IGB` = XML1's IGBs re-framed on XML2's menu camera (`reframe_menu_igb`; the credit
text is drawn by the text system at y -800 / -850, which XML1's near plane would clip); `Packages/generated/maps/
package/menus/credits{,_end}.PKGB` = XML2's with the x1 IGB as the model. XML2's own `menu_credits*.IGB` (4 KB camera
leftovers) stay untouched; `--frontend xml2` writes none of it. In game (build/_fe3, main menu Credits right after the
online screens): XML1's blue credits page behind the whole roll, pillarboxed (XML1's plane is 4:3-ish).

Checks: V17 (the two menus over their x1 IGBs, XML2's endgame, `image=""`, the IGBs = `credits_menu_igb` with the
camera seeing the text depths, the packages), frontend_selftest U16 + the build owners, validate_selftest (XML2's image
back).

#### 21.4.3 Review without Stats (2026-09-29)

B5b. The Stats tab (REVIEW_PATHS_MENU's fifth tab; its list is built by 0x5d0c20) is XMen2.exe code with the acts
hard-coded: ebp = act, `[esp+0x14]` = 4 x act, `[esp+0x18]` = 6 x act; `cmp dword ptr [esp+0x14], 0x14` / `jg` Total
at 0x5d0cc4 (imm8 at 0x5d0cc8) and the loop end `add eax, 4` ... `cmp eax, 0x18` / `jle` at 0x5d11de (imm8 at
0x5d11e0): acts 1-5, then Total. Per act, as "~02Act %d~~" (string 1166), the rows with a total > 0 (0x5d07b0, "%d of
%d" 1228): Comic Books / Concept Art = review_paths entries of category 2 / 3 whose `act` is the act (concept group
`marvel` skipped; count function review vt+0x50 = 0x4ae130, the act byte +0xc8 is only read there), and unless
0x4ad890 says otherwise Homing Beacons (`stat` entries `homing` + game var `beaconact%d`), Data Discs (`r_d_disc` bits
4 x act - 3 .. 4 x act), Tech Stations (`r_t_station` bits 6 x act - 5 .. 6 x act), Iron Man Armor (`r_imarmor`);
Total = the per-act sums, then Load Screens / Cinematics (act 0 = every entry). XML1 had no Stats category (its
`review.eng`: Cinematics, Comics, Concept Art, Loadscreens) and its review_paths has no `act`, so the port's tab shows
5 empty act headers and Total (Load Screens, Cinematics) - seen again in build/_fe3 ("Load Screens 1 of 64,
Cinematics 7 of 35" on a fresh profile).

Owen's call (2026-09-29): hide it - XML1 had no Stats. Implemented as two halves, like MainMenuItems (21.2):

- The tabs are data: XML2's `UI/menus/review.{XMLB,engb}` (REVIEW_PATHS_MENU over `x2m_review`) has five text items
  `option01_text` .. `option05_text` (Screens, Cinematics, Comics, Concepts, Stats), each dressing a backdrop item
  `option0N_focus` (`m_invis` + `onfocus` focus / nofocus models). The exe finds them by name through the table
  0x6e6e28 and skips a name the menu lacks (0x5adc10 / 0x5ade70 / 0x5adf80 return on a failed lookup; the mouse
  handler 0x5d04d0 tests each looked-up item for null). frontend (`review_menu_trees`) writes both halves as XML2's
  minus `option05_text` and `option05_focus` (`REVIEW_STATS_ITEMS`); the package, IGB and `review_paths` stay.
- The tab change is exe code: the shown tab is the global 0x8afef0 (4 = Stats: 0x5d0c20's list), changed only by
  0x5d17d0 (tab + step, wrapped at 5 / -1; left / right, the pad, vt+0x40, and the mouse, which turns a click into
  that many presses), the open 0x5d1c60 (`reviewmode` 0..4 picks that one tab; the four review<Category>() script
  functions set 0..3, the main menu -1), the main menu (0) and resetgame (0). xml2-fix `[Game] ReviewStats=0`
  (`review_menu_rules.hpp`) writes five guarded imm8s: the wrap `cmp esi, 5` 0x5d180a -> 4 and `mov esi, 4`
  0x5d1817 -> 3, the mouse's `cmp edi, 5` 0x5d05b3 -> 4, and the two `reviewmode` range checks `cmp eax, 5` at
  0x5d1c89 / 0x5d17f8 -> 4 (so `set reviewmode 4` opens all four tabs instead of Stats alone); xml2_test checks the
  guards against the exe and that the change writes exactly those five bytes. `tools/harness.py` writes
  `ReviewStats=0` when the build's review menu is a REVIEW_PATHS_MENU without `option05_text` (`review_stats_for`);
  `--frontend xml2` builds keep XML2's menu and get no key. Without the key (an older DLL) the label is gone but
  left / right still reach an unlabelled Stats page.

Checks: V17 (both halves registered by frontend, REVIEW_PATHS_MENU, the four category tabs, no Stats item, = XML2's
minus the two items), frontend_selftest U17 (the trees against XML2's, harness `review_stats_for` / the ini line;
`--out`: the build owners; `--compare`: `ui/menus/review.` among the front-end files) and validate_selftest (XML2's
`review.engb` back). In game (build/_rev, xml2-fix f991482, pipe keys): main menu Review shows Screens / Cinematics /
Comics / Concepts and an empty end of the tab bar; right goes Concepts -> Screens -> Cinematics -> Comics -> Concepts,
left Screens -> Concepts -> Comics, each page's list as before; `set reviewmode 4` opens all four tabs (cycling),
`set reviewmode 2` Comics alone (no cycling, the other labels drawn, as in XML2); `xml2-fix.log` "review menu: no
Stats tab". The menu opened on its last tab each time (Concepts; XML2's would be Stats): the tab is 0 after the main
menu and the first update reads one step left from the input (0x5aaeb0 -> vt+0x40 0x5d1870), also when opened by the
console with no key pressed - seen with the harness's unfocused window, not investigated further.

The act-count alternative, kept for reference: `[Game] ReviewActs=9` would set the imm8 at 0x5d0cc8 to 4 x N
(0x24) and at 0x5d11e0 to 4 x (N + 1) (0x28), guarding the retail `83 7c 24 14 14` at 0x5d0cc4 and `83 f8 18` at
0x5d11de. Safe for N = 9: the bit reads beyond 32 return 0 (0x4a0190 tests bits 1..32; 0x4a16c0 counts bits 1..32 of
`beaconactN`, a missing var counts 0); the act byte is a char. With it alone the tab shows Act 1..9 headers with no
rows. For rows, the port would add `act` to comic / concept entries: 12 comics and 20 concepts come from zone pickups
(imageViewer literals in 31 XML1 zones), the rest (18 concepts, the Nightcrawler comic XML1 never gives) have none;
the pickup zones' acts (research/scripts/out/zone_acts.json) are ambiguous for 9 revisited zones (e.g. haarp2_6 1 / 9,
sewers1_1_4 1 / 6 / 9), so the rule (first visit) is an invention - XML1 never grouped Review items by act.

### 21.5 End of campaign (D.1)

### 21.5 End of campaign (D.1)

`Scripts/x1/menus/postgame.py` (scripts, both front ends): `startMovie("r505", "postgame")`, `waitsignal`,
`mainMenuExit()`. xml2-fix's `[Game] PostgameScript` makes the endgame credits run it instead of XML2's
`loadZone('act5/egypt/egypt6','')` (0x5b1cbf; the xml2-fix side is another workstream). `tools/harness.py install`
writes `PostgameScript=x1/menus/postgame` into `[Game]` for XML1 builds (not with `--stock-opening`) when the build
has the script. Playing r505 also unlocks it in Review.

### 21.6 Validator

| id | check | severity |
|---|---|---|
| V15 | xml1: `menu/main_back` converted by zones, world `zonescript` installed + `nosave`, `MotionPaths/menus/main_back.IGB` has `mp_camera`, zoneinfo entry + loading screen present (warn if not `x_mansion`); `UI/menus/main` MAIN_MENU, `fullscreen="false"`, every item a node of its IGB, every `MAIN_MENU_ITEMS` name a shown text item with a usecmd (the Quit slot's without), no `label_option06` / `label_option09`, every usecmd command an XMen2.exe console command (`research/scripts/xml2_console_cmds.txt`), `openmenu` targets exist, `runscript` code console-valid; Begin Story's usecmd = `BEGIN_STORY_CMD` and no item runs `newgame` / `startgamedialog` (21.2.2); the `igct*.bnx` files and `Data/strings` with the port's name (21.2.3); `x1_menu_main.IGB` = `reframe_menu_igb` of XML1's `menu_main.igb` with every node the menu names, its camera at `MENU_CAMERA_POS` with the overlay depths -700 / -800 / -850 inside near..far; the package resolves and lists the IGB and the menu; the intro plays XML1's 5 logos and ends in `mainMenuExit()` (movies: warn with `--no-movies`); `menu_a` / `menu_c` planned `x1` and not the merged bank. Both: the postgame script (r505, `mainMenuExit()` last). xml2: no front-end file registered (`igct*.bnx` and `Data/strings` included) | error (focus chain: warn) |
| V16 | xml1: grades <= 8, courses <= 25 per grade and <= 75; course `arena` = an ARENA title, arena zones converted; SPAWNER / MUST* characters in the stats, `hero` a herostat hero; a Titanium REWARD per course; reward items in `Data/items` as equipment (warn if downgraded); Freshman unlocked; an exam in every grade but the last; every `loadDangerRoomCourse` literal in installed data and scripts names a course; no XML1 points | error (course neither startloaded nor on a disk: warn) |
| V17 | xml1: <= 90 review entries per category; `load` / `comic` / `concept` textures installed, comic / concept values contain their category; `cin` movies present (warn with `--no-movies`); every `imageViewer` literal equals a comic / concept value; no `reward_focus`; codex names in the stats; trivia 2..5 answers with one correct; credit line types = the ones XML2's credits use; `UI/menus/review` (both halves) = XML2's without the Stats tab's two items (21.4.3) | error (comic group not a hero, codex anim not in the anim DB, zoneinfo loading screens of XML1 zones that are no Review entry, trivia act without a question: warn) |

V6: its front-end rule applies to `frontend_zones(ctx)` (xml2); with xml1 the backdrop is a converted zone and gets
every V6 zone check. V2 accepts the `FRONTEND_MUSIC` banks from XML1's music under xml1. `Data/items` accepts XML2's
equipment attributes `heft` / `unique`, and Danger Room rewards count as item references.

### 21.7 Tests

`python -m xml1build.frontend_selftest [--out <build> [--compare <reference>]]` (from `tools/`): U1-U17 unit checks (U16: the credits menus, 21.4.2; U17: the review menu without Stats, 21.4.3) of
the providers (21.2-21.5; U1 the menu IGB re-frame (only its floats change, every world position by the camera's offset, idempotent, the constants = XML2's `x2m_main` camera), U2 the menu file against XML1's `main.eng` and harness.py's `MainMenuItems` / `NewGamePlus`, Begin Story = `BEGIN_STORY_CMD`, U15 the `igct*.bnx` / `Data/strings` re-text); with `--out`, the build's front-end files and owners per mode; with `--compare`, every
file either build registered, plus the files this section touches, byte-identical except the new postgame script
(the `--frontend xml2` guarantee). `scripts_transform.selftest` covers `rewrite_image_viewer`; `scripts_selftest`
and `zones_selftest` read the build's front end from `report.json`; `validate_selftest` injects `label_option09`
and XML1's menu IGB as on the disc (V15: not re-framed, overlay depths clipped), Begin Story back on `newgame` and
XML2's `igct.bnx` (V15, 21.2.2 / 21.2.3) under xml1.

---------------------------------------------------------------------------------------------------------------

## 22. Combat events: XML1-only triggers, handlers and affecters (2026-09-28)

Found in game (`tools/power_sweep.py`): Magma's power2 Lava Fissure played its animation but dealt no damage and
spent no energy. Its trigger `lava_rift` names the style event `lava_rift`, which inherits XML1's shared event
`blast_ranged`; XML2's `data/shared_combat_events` has no `blast_ranged`, so XMen2.exe dropped the event and every
trigger naming it, with its damage and its `powerusage`. `tools/xml1build/combat_events.py` holds the engine facts,
the registered name tables, the rewrite and the checker.

### 22.1 Mechanism (XMen2.exe; every address is in the `combat_events.py` docstring)

- A style (powerstyle, fightstyle, `shared_nodes`) is loaded by 0x5010b0 into one event list:
  `data/shared_combat_events.xmlb` (0x50111e), then the style's root `<event>`s, then its FightMoves. An event or
  trigger resolves in 0x501630: a `type` attribute names the `ce_*` type; otherwise `inherit`, else `name`, is
  looked up case-insensitively in that list. Not found, or a type the factory 0x4faea0 does not know (70 `ce_*`
  names) -> the event / trigger is dropped without a message. A child event copies its parent, damageMod bits
  included (0x4dce80).
- A tag-only trigger updates the inherited trigger of that tag (0x4f6a1f) and is dropped otherwise; a move holds at
  most 19 triggers (0x4f6aa7); names are at most 31 characters (0x5016dd); only `trigger` / `event` children are
  read (XML1's `<trigger2>` leftovers were read by neither exe).
- FightMove `handler` -> 0x4fd860 over the 68 names 0x4fd8d0 registers; an unknown name runs as `%default%`
  (animation and triggers, no handler logic).
- `<affecter attribute>` -> 0x534d90 over the `{name, id}` table 0x6ddb18 (95 names); an unknown name is id 0,
  `none`.
- The tables are data (`CE_TYPES`, `FM_HANDLERS`, `AFFECTERS`) with their addresses. `verify_exe` checks them byte
  for byte against the install's XMen2.exe (V18); the self-test re-reads the first two from
  `research/scripts/xml2_text.asm`.

### 22.2 Census (every XML1 style and `shared_nodes`; build/_heroes before the fix)

| name | kind | users | XML1 behaviour | rewrite |
|---|---|---|---|---|
| `lava_rift` | root event -> `blast_ranged`; 1 trigger | Magma power2 Lava Fissure (hero) | fire blast (ce_atk_blast) at a target within 250, radius 48 (trigger 60..120), damage, popup + environment damage, spends energy | `inherit="blast"` + `dmgmod_popup` |
| `lava_impact` | root event; 4 triggers | Magma power9 Volcano (Xtreme) | 4 random fire blasts per trigger, radius 60, range 225 | same |
| `card_impact` | root event; 6 triggers | Gambit power9 (Xtreme) | 2 energy blasts per enemy (enemynumber 0..5) | same (XML2's own ps_gambit `card_impact` is exactly this) |
| `firework`, `firework_blue` | move events; 3 + 3 triggers | Jubilee power9 Independence Day | random energy blasts | same |
| `lightning_impact` | root event; 1 trigger | Storm power9 | 4 electric blasts, radius 30, range 350 | same |
| `orbital_impact` | root event; 6 triggers | Beast power9 Orbital Bombardment | 2 energy blasts per trigger | same |
| `psy_knife` | move event; 6 triggers | Psylocke power9 Psychic Onslaught | 2 mental blasts per enemy | same |
| `pickup_sound` | trigger | x1_ps_juggernaut `grabstart` (boss) | nothing: XML1 defines no such event | none; allowlisted (`UNRESOLVED_ALLOWED`) |
| `ch_throw` | FightMove handler | Gambit and Jubilee `charged_throw` (hero); XML1 shared_nodes `pickupobjectthrow` | throw of the held (charged) object | `ch_pickup_throw`: XML2's same `pickupobjectthrow` node |
| `atk_damage_scale` | powerup / affecter | Jubilee power3 taunt (hero; enemies' damage x0.75); NPC Mystique | attack-damage multiplier | `atk_damage` + `affect_type="scale"` (XML2 retail form, e.g. ps_bishop's handicap) |
| `ch_grab_attack`, `ch_weapon_semi_auto`, `ch_grenade`, `ch_clingwalldecide`, `ch_clingwallbackflip`, `ch_air_grab_*`, `ch_fly_guard_decide`, `ch_stun`, `ch_roguedecide` | FightMove handlers | Juggernaut; GRSO / flamethrower soldiers; Mystique, Shadow King; `moveset_acrobat`; XML1's flying carry; XML1 `stun`; Rogue | see `UNREGISTERED_HANDLER_NOTES` | none: no XML2 counterpart, they run as `%default%` (V18 warning). XML2's own `moveset_grenade` / `moveset_stealth` name `ch_grenade` too; `moveset_flying` and the `stun` node are XML2's in the build; heroes drops Rogue's decide chain |
| tag 3 | tag-only trigger | x1_ps_pyro `power_smash` (NPC) | XML1 data bug: nothing to update in XML1 either | none; allowlisted (`ORPHAN_TAG_ALLOWED`) |

So before the fix 8 events and 30 triggers in 6 hero styles did nothing: Magma's Lava Fissure and the blasts of the
Beast, Gambit, Jubilee, Magma, Psylocke and Storm Xtremes (their name banner still showed, which is what
power_sweep counts for an Xtreme).

Also checked against the XMen2.exe strings, with no rewrite: every `damageMod` name is registered;
`attacktype="power"` is a string of both exes; `damagetype="dmg_lightning"` (ps_shadowdemon_ldr) and
`aitype="simon"` (ps_avalanche) exist in neither exe (XML1 typos with the same default in both games);
`damagetype="dmg_mental dmg_physical"` (ps_profxgladiator) goes through the flag parser 0x43bd70;
`affect_type="sum"` (ps_havok) is known to neither exe's affect-type parser (both read scale / max / min, default.xbe
0x95851, XMen2.exe 0x535025) and parses as the default in both. XML2 retail's own dead triggers (ps_beast
`orbital_impact`, the nameless triggers of ps_sin_wolverine / ps_toad) are left alone.

### 22.3 Rewrite (`combat_events.rewrite_style`)

`x1schema.convert` runs it on every XML1 style tree (section 11.2 item 4): characters' imports, heroes before the
collapse (so talentvalues and power slots are computed on the XML2 names), zones' `shared_nodes` merge. It is
table-driven and idempotent:

- `EVENT_REBASE`: an event or trigger whose `inherit` (or bare `name`) is `blast_ranged` points at `blast` (the same
  `ce_atk_blast` type; angle 0, attacktype blast, damagelevel 1 and radius 50 as in XML1; `damagescale="none"` as
  XML2's hero blasts). XML1's `damage` L3, `damagetype` dmg_fire and `maxrange` 50 are added only where the event
  lacks them (all 7 set their own), plus `dmgmod_popup` (the parent's damageMod, inherited as a bit in XML1).
  `PowerAttack` has no XMen2.exe reader. The triggers' `%talentvalue` references are untouched.
- `HANDLER_RENAME`: `ch_throw` -> `ch_pickup_throw`. `AFFECTER_RENAME`: `atk_damage_scale` -> `atk_damage` with
  `affect_type="scale"` (in an `<affecter attribute>` and in an XML1 powerup trigger's `powerup`).
- Reported as the x1schema kinds `combat_*` (zones counts `x1schema_combat_*`); characters counts
  `combat_events_rebased`, `combat_handlers_renamed` and `combat_affecters_renamed`; heroes counts the same plus
  `combat_damagemods_added`, and `heroes_detail.json` has `combat_rewrites` per hero. A full build rewrites 8 events,
  adds 8 damageMods, renames 3 handlers and 2 affecters.

### 22.4 Validator V18 combat events (and V-H5)

| id | check | severity |
|---|---|---|
| V18 | The tables equal the install's XMen2.exe (`verify_exe`). In every style file the build wrote (`Data/powerstyles`, `Data/fightstyles`, `Data/shared_nodes`; XMLB and engb): every `<event>` / `<trigger>` resolves to a registered `ce_*` type, no orphan tag-only trigger, at most 19 triggers per move, names of at most 31 characters, every `<affecter attribute>` registered. An unregistered FightMove handler is a warning when `UNREGISTERED_HANDLER_NOTES` assesses it, else an error. `<trigger2>`: note; an XML1-form powerup trigger (`powerup=` attribute) or XML1 removal (`remove="true"` on a powerup trigger or on a tag update of an inherited one): error (22.7). XML2 retail style files are allowlisted per file; allowlists `UNRESOLVED_ALLOWED` (`pickup_sound`) and `ORPHAN_TAG_ALLOWED` (x1_ps_pyro `power_smash` tag 3). | error / warn |

A tag-only update of an inherited powerup trigger that still carries `level` / `affect_type` / `level_max` /
`scope_*` (XMen2.exe reads those only on an `<affecter>`) is an error too (`x1_powerup_update`, section 24.4).

V-H5 applies the same resolution to the 16 hero styles (error), checks handlers against `FM_HANDLERS` (warning)
and affecters against `AFFECTERS` (error; a registered one that no XML2 retail style uses keeps the UNVERIFIED
warning).

### 22.5 Tests

`python -m xml1build.combat_events_selftest [--out <build>]` (from `tools/`): T1 the tables against the exe; T2
against the disassembly; T3 the resolver on XML2's 131 retail styles (only XML2's own three dead-trigger styles);
T4/T5 the XML1 census before and after the rewrite, idempotency and the change counts; T6 Magma's `lava_rift` ->
`blast` -> `ce_atk_blast`, Gambit / Jubilee `ch_pickup_throw`, Jubilee's taunt as scale `atk_damage`; T7 one
injected defect of each kind (with the XML1 powerup forms; an XML1 `ce_renderfx remove="true"` is no removal); T8
V18 read-only over a build, printing Magma's power2; T9 22.7 over every XML1 NPC style (nothing left, the change
counts, idempotency, the Blob / shadow demon / GRSO elite / Master Mold / Juggernaut / Havok forms, the heroes'
converter's special_fx forms).

### 22.6 Not verified in game / open

- `tools/power_sweep.py <build> <results> --heroes magma,beast,gambit,jubilee,psylocke,storm`: Magma's power2 must
  drain energy and damage; the six Xtremes must damage; Jubilee's boost weakens enemies. `charged_throw` (pick up
  an object, then Power) is not part of the sweep.
- NPC powerups: 22.7.

### 22.7 NPC powerups: XML1's `powerup=` and `remove="true"` forms (2026-09-28)

**Mechanism (XMen2.exe).** `ce_powerup` (factory 0x4fb104, parse 0x4e7f00) hands the trigger to its powerup template
(class by `class`, else `default`); the template parser 0x53df10 gives every attribute to the class setter (base
0x53ea60 and 17 class overrides: none reads `powerup`, `level`, `affect_type`, `scope_*`, `remove`, `user1`, `func_*`,
`level_max`, `bolton`), then reads the `<affecter>` (0x534d90: `attribute`, `affect_type` scale / max / min, `level`,
`scope_damage|attack|node|talent|race|character|powers|non_powers`, `damageType`), `<special_fx>` and `<bolton>`
children. XML1's form (default.xbe 0x9565c: `powerup=` names one of 59 attributes, table 0x44e8c8) therefore built a
powerup with no affecter: effect, skin and life played, the buff did nothing (62 triggers in 36 NPC styles). XML1's
`remove="true"` (0x95bd3, bit 4 of +0x72) makes the trigger remove the actor's powerups of that attribute instead of
applying one (0xd7668 -> 0x2b100); XMen2.exe removes by name: `remove_tag` (0x4e7e79) -> execute 0x4e8387 -> 0x54f7b0
drops the owner's powerups whose `tag_name` (0x53ea6e) matches. A tag update re-parses the inherited trigger
(0x4f6a1f -> vt+0xc), so `<trigger tag="1" remove_tag=...>` turns an inherited powerup into its removal. Unconverted,
the removals applied their powerup (the shadow demons' `spawn_in` / `fly_out` never ended the spawn_invis cloak).

**Conversion** (`heroes.convert_npc_powerups`, run by characters' style patch on every style it writes; heroes
rewrites its own styles with its collapse; table-driven, idempotent):

| XML1 | XML2 | users |
|---|---|---|
| `powerup=X level= affect_type= scope_* effect*` | `heroes.convert_powerup_trigger` (DESIGN 4.5: `<affecter>` or the retail class forms); the trigger's value codes resolved to XML1's numbers (A6 -> 20, BST6 -> 24, K7 -> 430, `powerusage` P6 -> 60; XMen2.exe reads any code but DMG2/3/4, K2, K3 as 0: 0x4c1580 -> 0x4c4870, 0.0 at 0x680030). Until section 24 `powerusage` kept its code (`NPC_KEEP_CODE_ATTRS`, now empty): XML1 NPCs pay XML1's costs from XML1's pool | 47 triggers |
| a tag-only update of an inherited powerup that changes `level` / `affect_type` / `scope_*` | `<trigger tag=N time="-1"/>` + the updated copy under a fresh tag (section 24.4) | Juggernaut x2, Marrow, Avalanche |
| `remove="true"` (a powerup trigger, or a tag update of an inherited one) | `remove_tag="X"` (`name` / `tag` / `time` / `powerusage` kept); the style's powerups of X get `tag_name="X"`; X = `invisible` is XML2's own `spawn_invis` tag, the cloak these removals end | 23 removals (17 invisible: shadow demons, shades, astral ghost, Danger Room robots, stealthbot; 6 def_damage: Blob, Toad, Pyro, Magneto, Juggernaut x2) |
| `invisible` + `func_activate="invisible_activate"` | `class="invisible"` (vtable 0x697aec) + `no_think="true"` without an XML1 `func_think`, `no_hurt="true"` without `func_hurt` (setter 0x548340) - XML2 retail's cloak / spawn_invis form | GRSO elite |
| `special` + `func_touch="damagetouch"` | `class="touch_damage" damage="15 25"` = XML1's rand(level, level_max) (0x2c970; setter 0x54ae00 `damage` / `damageType`; XML2's ps_storm form) | Master Mold's shock shield |
| `powerup="fighting"` | no affecter: not in default.xbe's name table either (parsed as none in XML1) | Marrow |

Reported losses (`NPC_CALLBACK_LOSSES`; characters notes): Phoenix dopple's mind-fry logic, the Sentinel spider's
reversed controls, the Wolverine dopple's hit / hurt sounds, the shield-hit flash (`magnetohurt`: a custom fx tag 1),
`user1` of the robots' `health_regen max`, XML1's `bolton=` on a powerup (Marrow, mp_smash; no XMen2.exe attribute).

**The heroes' converter** (so heroes too): `how_used="deactivate"` is no XMen2.exe value (0x53c1f0 over 0x6de16c:
primary / activation / deactivation / custom, anything else = custom), so the expire effects of x1_ps_beast /
colossus / frost / phoenix, ps_magma, ps_profxastral and ps_profxgladiator never played: now `deactivation`.
`effect_cust1` / `effect_cust2` = custom fx tag 1 / 2 and `fx_bolt` = the primary fx's bolt, as XMen2.exe reads those
XML1 attributes itself (0x53f14c..0x53f24c; Iceman's freeze shatter needs tag 1, as XML2's own ps_iceman).
`scope_node` / `scope_race` (and the other affecter scopes) go onto the affecter.

V18: any XML1-form powerup trigger or removal left is an error (22.4). Tests: T7 / T9 (22.5).

In game (not verified): Blob / Toad / Pyro / Magneto shields make them immune until the `*_off` move; Juggernaut's
armor1 ends at `armor_end` / `helmet_penalty`; the shadow demons and shades become visible when they spawn in / fly
out; the GRSO elite cloaks; Master Mold's shield hurts on touch; Avalanche's quake slows the party; Magneto's and
Master Mold's stun beams hold the hero; the sentinel leader nullifies mutant powers.

## 23. XML1's XP curve: xml2-fix `[Game] XPCurve=xml1` (2026-09-28)

The port's objectives, scripts and npcstat carry XML1's XP amounts (act 9's crystal objectives 2,000,000, asteroid_m's
`setXP(..., 1125000)`, npcstat `xpaward`); on XMen2.exe's curve one act-9 objective takes a level-1 hero to 40
(`research/heroes/levels.md`, sections 1-5). xml2-fix `[Game] XPCurve=xml1` (xml2-fix 791964d,
`src/xp_curve_rules.hpp`) has the game use XML1's level table (default.xbe, cap 45: 2,000,000 XP = level 26), XML1's
kill XP f(L) = trunc(2.5 (4/3)^(L-1)) and XML1's split: half of each kill to every hero, the bench included (XML2 gives
the bench 1 XP), 3 (half + 1) more to each party hero. What is patched, what stays XML2's and why (the Danger Room's
fixed level 30, Hard's 45), the in-game checks: `levels.md` section 8.

- `tools/harness.py install` writes `XPCurve=xml1` into `[Game]` for every build_xml1.py build (the build has
  `_build/report.json`) made with `--xp-curve xml1` (the default; a build from before 23.1 counts as xml1),
  `--stock-opening` included: the XP amounts are the data's, not the opening's. The summary line prints it.
- `tools/power_sweep.py` reads the build's `xml2-fix.ini` (`campaign_walk.read_ini` now returns `xp_curve`): with
  `xml1` its level-ups are XML1's table (level 15 = 41,265 XP, the cap 45), so `--level 15` still lands on 15; the
  plan line prints the table.
- `tools/hero_xp.py` prints every hero's level and XP from the running game (read only; the HUD and the stats screen
  show a level and an XP bar, never the XP).

### 23.1 The XP amounts the pipeline chooses: `--xp-curve xml1|xml2`

`build_xml1.py --xp-curve xml1|xml2` (also `$XML1BUILD_XP_CURVE`; default `xml1`; `common.xp_curve_mode`) says which
curve the game runs; `report.json build.xp_curve` records it (a build from before counts as `xml2`,
`LEGACY_OPT_VALUES`; `CONTENT_OPTS` re-runs zones and frontend when it changes) and `harness.build_xp_curve` writes
`XPCurve=xml1` only for `xml1`. The two amounts the pipeline itself chose follow it:

| amount | XML1 (default.xbe) | `xml1` (default) | `xml2` (before 23.1) |
|---|---|---|---|
| Danger Room course completion (21.3) | none: the first completion adds the course's `reward` to the Danger Room points (word 0x4e70c4, +1 per extra credit; 0xc53ee..0xc5428, 0xc5809..0xc59c3) that `requirement` gates; no XP award is called (roster award = registry vt+0xcc 0x55180, never from the Danger Room code). The XP came from the kills. | Titanium `rewardxp="0"` (`frontend.DR_XML1_REWARD_XP`; XMen2.exe's reward code skips 0, 0x4c8fb3 / 0x5d0b7d); the 19 challenge items unchanged | `rewardxp` by XML2's reclevel curve (200..25000) |
| XP pickup (`item_xp01`: hive2_2_4 count 300000, wx2_1 count 30000) | the inventoryent's `count` (0x7d3c0 -> +0x2c8) as XP to the hero who picks it up (0x7dc41: 0x33170 = the actor's XP gain scaled by its xp affecter, then the popup 0x2fcf0) | the entity names `XP_<count>`; zones adds that item (XML1's `XP` item, `activateonpickup`) with `onactivate="setXP('_ACTIVATOR_',<count>)"` (0x4a8660: the actor's XP gain 0x422350 + popup; `_ACTIVATOR_` in an item's onactivate is XML2 retail's HEALTH_ITEM / SKIRMISH_KING_PIP form) | the one `XP` item, `awardXPToPlayable(5000)` to the roster |

Both curves: the XP pickup entity's `count` becomes `1` - XMen2.exe reads an inventoryent's count as a 16-bit item
quantity (0x47a970, default 1; 300000 wrapped to -27680, 30000 would have been 30000 units). Not reproduced: XML1
scaled a pickup by the picker's `xp` affecter. The `SKILL` pickup's `awardXPToPlayable(5000)` stand-in (the whole
roster) is replaced in both modes by one level of XP to the picker, section 32. Checks: V16 errors on a `rewardxp` other than the curve's value;
`frontend_selftest` U14 (both modes, and with `--out` the build's table); `zones_selftest` J (the pickups against
XML1's counts and the items).

## 24. XML1 value codes in the NPC styles, and the NPC energy pool (2026-09-28)

Found offline: XMen2.exe resolves a value code in a style attribute only for DMG2, DMG3, DMG4, K2 and K3; every
other code reads as 0. The NPC styles characters wrote still held XML1's codes (394 in 70 NPC styles: 213 damage,
62 knockback, 119 powerusage; plus 2 tag-update levels, 24.4), so XML1 NPC attacks (Pyro's flame, every Acolyte,
Sentinel, Master Mold ...)
did 0 base damage and 0 knockback and their powers cost nothing. `tools/xml1build/npc_values.py` holds the engine
facts (every address in its docstring), the resolver, the energy talent and V19.

### 24.1 Mechanism

- **XMen2.exe.** A numeric style attribute goes through the talent-value parser 0x4c1580 (powerusage 0x4dadb0,
  attack damage 0x4de670, powerup life 0x4e7890) or the value table 0x4c4bb0 -> vt+8 (damage / knockback 0x4e8830),
  both ending in 0x4c4870: a number ("%f %f" when it holds a blank: min and max; "%f": both), else one of the 5
  names of the table 0x6da240 {index, name} (DMG2 DMG3 DMG4 K2 K3; min / max from data/values.xmlb, 0x4c4640, which
  keeps no other row), else 0.0 (0x680030). XML2 retail styles hold no code at all.
- **XML1 (default.xbe).** The value table 0xb8550 loads data/values.xml (0xb8100); its resolver 0xb7e60 returns a
  code's min (and max) for every row, 0.0 for an unknown name. Every style reader calls it while the style is parsed
  (0xcf6b0 attack Damage min + max, 0xd7bc0 damage / knockback, 0xcdc10 powerusage) and stores the number: a code
  is a constant of the style - not scaled by the NPC's level, the spawner or the difficulty (an NPC's level acts
  through its stats, section 11.8). A reader that takes one number gets the min in both exes.
- Both games' tables give every L/M/H/K code the same numbers; XML2's P codes are XML1's / 10. XML2's own ports of
  XML1 NPCs wrote XML1's numbers as literals (ps_pyro flame_dmg L3 -> "15 18", ps_sabretooth; npc_values_selftest
  T3: 15 equal, none different).

### 24.2 Resolution (`npc_values.resolve_style`, characters `_style_patch` after `convert_npc_powerups`)

Every value code in any non-name attribute (`heroes._NAME_LIKE_ATTRS` skipped) of every style characters writes
(powerstyles and the XML1-only fightstyles) -> XML1's number(s) from XML1's data/values.xml (`heroes.Values`):
`"min max"` for an L/M/H range (range readers get XML1's range, one-number readers its min, exactly as XML1),
`"min"` for K/P/A/BST/XTL. XMen2.exe's own K2 / K3 are resolved too (the same numbers). Table-driven (the values
file is the table), idempotent; an unknown code is a build error and stays. The XML1 hero styles are rewritten by
heroes with the same numbers (SPEC_heroes 5). Pyro (x1_ps_pyro): flame 15..18 per tick, fire ring 100..125 / 370,
80..100 / 245, 50..63 / 190, the ring costs 50, the fire shield 30. characters counts `npc_codes_damage`,
`npc_codes_knockback`, `npc_codes_powerusage`, `npc_codes_other`, `npc_codes_resolved`, `npc_code_styles`.

### 24.3 The NPC energy pool: XML1's, reproduced

- **XML1 NPCs had a pool and waited for it** (both exes have the same design): every actor but a player hero spends
  a powerusage trigger's cost (XML1 0xcde90 -> 0x3f410, XMen2.exe 0x4daa30 -> 0x4318d0); FightMove canAfford
  (0xe1a20 / 0x4f5fb0) refuses a move whose summed costs exceed the energy; XML1's AI picks a power only with at
  least half its energy (0xee37a: max / energy > 2.0 -> no power).
- **Pools differ.** Maximum: XML1 30 + 4 level + 7 mind (0xafbd0); XMen2.exe 30 + 4 level + 2 mind (0x4b8c20, at
  the default difficulty). Regeneration per second: XML1 15 x (1 + mind / 100) outside the hero team (0x3a950);
  XMen2.exe 15 for the enemy team (0x42cc60, team 0x1e = "enemy", 0x45fbd0), no mind factor. The hero team
  regenerates max / 60 in both (XML1 x (1 + mind / 100)). Both then apply the maxenergy / energy_regen affecters.
- **Fix.** `powerusage` resolves to XML1's P numbers (`heroes.NPC_KEEP_CODE_ATTRS` is empty). The shared talent
  `x1_npc_energy` (`npc_values.energy_talent`, added by characters `_npc_energy`): talentvalues `x1npc_ep_max` = 5 r
  and `x1npc_ep_regen` = 1 + r / 100 listed for every rank r up to the highest used, and one `<level count=N>` whose
  permanent powerup has `<affecter attribute="maxenergy" level="%x1npc_ep_max"/>` and `<affecter affect_type="scale"
  attribute="energy_regen" level="%x1npc_ep_regen"/>` (XML2's own NPC talent form: `might`; the scale form:
  `mutantmaster`). Every stats entry characters converts that has a mind gets `<talent name="x1_npc_energy"
  level="<mind>"/>` (127 converted entries, ranks 1..80; 120 stay in npcstat once heroes removes the hero names,
  ranks 1..60; a mind above 99 would be capped). With it XMen2.exe
  computes XML1's pool and regeneration: PyroAct1 (L9 M13) 92 -> 157 (XML1 157), 15 -> 16.95 per second (XML1
  16.95), so his fire ring (50) fires as often as in XML1. heroes keeps the talent in its shared prune
  (`SHARED_KEEP_EXPECTED`, rule 'XML1 NPC energy pool'): 47 shared talents, worst party 76 of 92, talentvalue names
  287 of 300.
- **Left different.** XMen2.exe's other difficulties (below the default the enemy base is halved, above it a
  level-50 formula; XML1's NPC energy ignores the difficulty); an NPC of team "none" (XML1: 50 of 190 entries,
  civilians and scripted forms) regenerates max / 60 per second in XMen2.exe instead of XML1's 15 base; XML2's AI
  keeps its own energy tests (e.g. 0x51a9f1, 75 %) where XML1's used 50 %. The hero-team exemption (flag bit 0 of
  the actor and the player manager's answer for its slot) is the same in both exes.

### 24.4 Tag updates of a powerup's buff (section 22.7 follow-up)

XML1's tag-only update of an inherited powerup trigger re-parsed the whole XML1 trigger, `level` / `affect_type`
included; XMen2.exe re-parses the trigger's own attributes (life, time, powerusage, remove_tag) but reads `level` /
`affect_type` / `scope_*` only on an `<affecter>`, so 6 updates in 4 NPC styles were dropped: Juggernaut
power_boost (A6 20 -> A8 50) and armor_start (def_damage scale 0 for 60 s: immune at the fight's start), Marrow
power_boost (A2 8 -> A4 13), Avalanche power_smash (quake slow 0.5 -> 0.4). `heroes._npc_powerup_updates` (end of
`convert_npc_powerups`, parent-first, idempotent) turns such an update into `<trigger tag=N time="-1"/>` (the
inherited trigger never fires, XML2 retail's own form) plus a copy of the inherited powerup with the new terms on its
affecters and the update's other attributes, under a fresh tag (100, 101, ...); a later move's update of tag N
(Juggernaut armor_start, armor_end's removal) is retargeted to the copy. Mystique's two updates keep the level they
inherit (1): only their dead `level` goes, `life` stays a native update. Counts `npc_powerup_update:<attr>`,
`npc_powerup_update_same`, `npc_powerup_retag`.

### 24.5 Validator V19 (and V18)

| id | check | severity |
|---|---|---|
| V19 | `npc_values.verify_exe`: the 5-row value table 0x6da240, the resolver's 5-name loop and the energy constants equal the install's XMen2.exe. No style file the build wrote (Data/powerstyles, fightstyles, shared_nodes; XMLB and engb) holds a value code XMen2.exe reads as 0 (any L/M/H/K/P/A/BST/XTL/XLT/DMG shape but DMG2/3/4, K2, K3); XML2 retail files are allowlisted per file, XMen2.exe's own five are notes. `x1_npc_energy` is defined once per shared_talents file with the right values for every rank used, and every XML1-origin npcstat entry with a mind carries it at rank = mind (none on XML2 entries). | error |
| V18 | `x1_powerup_update`: a tag-only update of an inherited powerup trigger still carrying `level` / `affect_type` / `level_max` / `scope_*` (24.4). | error |

V-H5 now flags any code shape in a hero style (`npc_values.is_code`; it missed the `+` codes before).

### 24.6 Tests

`python -m xml1build.npc_values_selftest [--out <build>]` (from `tools/`): T1 the exe / xbe facts byte for byte;
T2 24 disassembly lines (both resolvers, the loaders, the powerusage / damage / knockback readers, both energy
formulas and regenerations, canAfford, XML1's AI half-energy test); T3 XML2 retail holds no code, both values tables
agree on L/M/H/K, XML2 P = XML1 P / 10, the XML1 NPCs XML2 re-ships carry XML1's numbers; T4 every NPC style
characters writes: no code left, idempotent, the counts, Pyro / Toad; T5 the talent reproduces XML1's pool and
regeneration for every XML1 entry, its definition, idempotent attach; T6 V19 over a build. combat_events_selftest T7
/ T9 cover 24.4 (the Juggernaut chain) and the resolved Juggernaut cost (P2 -> 20).

### 24.7 Not verified in game

- Pyro in the park (nyc1): his flame hurts the hero (15..18 per tick before XMen2.exe's stat scaling), his fire
  ring knocks the party back; Toad's tongue / Sabretooth's claws / GRSO troopers' hits damage and knock back.
- NPC energy: Pyro casts his fire ring (50) and shield (30) about as often as in XML1 (pool 157, ~17/s), not every
  AI reuse tick; `hero_xp.py`-style memory read of an NPC's energy if needed (current [+0x288], max [+0x314]).
- Juggernaut (boss) starts immune (armor_start, 60 s) and his armor absorbs 50 after the upgrade; Avalanche's
  upgraded quake slows the party more.

## 25. XML1 skins against their anim DBs: the elite Acolytes' spikes, validator V21 (2026-09-29)

Late-game test bug B3 (research/campaign/late_game_test.md): the elite Acolytes AcolyteEnergy_B / AcolyteLeader_B
(XML1 4805 / 4808 -> 18805 / 18808, anim DB `48_acolyteenergy`) drew huge black spike polygons in Asteroid M's
Magneto room (asteroid2_1). `tools/xml1build/skins.py` holds the checks; research/characters/skins.md the whole
investigation (IGB dumps, the libIGGfx.dll decompiles, the seven in-game sessions).

### 25.1 What the files are

- The pipeline changes nothing in a skin IGB but the names (`x1names.igb_rename`): 18805 = 4805 byte for byte apart
  from '4805' -> '18805' (and _skel).
- 4805 / 4808 are sound: weights sum to 1 on every vertex, every blend index is inside the 32-entry blend palette,
  every palette entry is a skeleton bone, every outline vertex resolves to the same bone as the nearest body vertex,
  the index buffers stay inside their vertex arrays, and all 32 bones the skin blends with exist by name in
  `48_acolyteenergy`'s skeleton. Their skeleton ORDER differs from the anim DB's ('Motion' second, not last - the
  same in 4803 / 4806 / 4807 and in 130 of the 200 XML1 skin / anim DB pairs); XMen2.exe matches by name.
- What they have that XML2's used characters do not: blended vertex arrays with 2 weights per vertex (body
  0x10223, cel outline 0x221; igVertexFormat bits 4-7 = weights, 8-11 = bone indices, libIGGfx.dll 0x10001d30 /
  0x10001d60). 20 of the XML1 stats skins blend 1-2 weights somewhere (plain AcolyteEnergy 4801, Sentinels, the
  bots, Master Mold, Jubilee, Cyclops' visor, ...); XML2's used skins blend 3-4. Alchemy's DX8 path pads every
  blended array to 4 internal weights with zeroes (igDxVertexArray1_1::makeConcrete 0x10047040,
  initUnusedBlendWeights 0x10047ff0, vertex declaration 0x10048980) and its CPU path blends any count
  (igVectorBlending SSE 0x10022df0; the CPU / vertex-shader choice is per array, pickVertexShader 0x10049ee0).

### 25.2 In game: not reproduced

build/_skins (this branch, --no-movies), harness pipe `skins`, 18805 the original file and 18808 with only its outline
widened to 3 weights (A/B in one scene): no spike on either in seven sessions - asteroid1_1 fights (all four elite
types), the Magneto meeting camera and fight via `loadMapKeepTeam`, via the late test's own path (begin_asteroid_rock,
begin_asteroid_int, XP to 31, zone link02 + E), after a 17-zone session, after a return to the main menu and a new
Begin Story, with Alchemy's CPU skinning forced (alchemy.ini [GFX] disableVertexShaderBlending), after the r302 movie,
and with the late test's xml2-fix DLL (1c750e3). B3 is a runtime state of that one session (6-20 fps with three other
game windows, an XInput pad connected, ~1 h of play), not a property of the files; it stays open (HANDOFF) until it
recurs with a way to reproduce it. Nothing is changed in the build's output.

`skins.pad_blend_weights` (with `igb_file.IgbFile.rebuilt`, which re-lays the memory section so blocks can change
size) widens 1-2-weight arrays to 3 weights / 3 indices with weight 0.0 on the vertex's own first bone - exact, same
deformation; the padded 18808 outline drew correctly in game. It is a tool (`python -m xml1build.skins pad in out`),
not a build step: if B3 recurs, pad 18805 / 18808 in that session's build and compare.

### 25.3 Validator V21 skins

For every XML1-origin herostat / npcstat skin (and its costume skins) against its `characteranims` anim DB:

| finding | severity |
|---|---|
| unreadable skin; a vertex array whose weight and index counts differ; a blend index outside the palette; a palette entry no skeleton bone carries; weights that do not sum to 1 | error (none on the XML1 disc) |
| skin / skeleton mismatch: vertices weighted to a bone the anim DB skeleton lacks (no animated transform for it) | error, or warning marked inherited when the XML1 disc's own skin and anim DB have the same mismatch |
| arrays blended with 1-2 weights (one note listing the skins), palette bones nobody uses that the anim DB lacks, a shared bone with a different parent | note |

The XML1 disc's inherited mismatches (15 skins with costumes, 13 stats skins): the ponytail bones of Colossus (14901
-14906), Gambit 15301, Prof X Gladiator 15105, Moira 16101, the four wingless Shades 1750x / 1751x and AstralGhost
17705 (80 vertices); the Sentinel spider's toes (19504, 173 vertices); Master Mold 19901's wing bones (2 x 580
vertices) and eight finger bones. None has been seen misdrawn in game yet (Master Mold's fight, late test shots 46-47).

`python -m xml1build.skins scan xml1_loose` / `check <out>` print the same per skin; `skins_selftest` (T1 rebuilt
round-trips all 977 actor IGBs of both discs, T2 padding is exact and idempotent over the 32 numeric actors that
need it, T3 check_skin incl. injected defects, T4 V21 over a build: 0 errors, 15 inherited warnings).

`igb_file` now also reads the 27 XML1 / 23 XML2 actor IGBs it refused before (the memory section is padded to 4
bytes after a 2-byte-aligned last block).
---------------------------------------------------------------------------------------------------------------

## 26. Automaps: XML1's automap textures as XMen2.exe `.zam` files (2026-09-29)

Before: the pause menu's Automap and the HUD's small map showed nothing for XML1 zones (hero icons on an empty map):
XMen2.exe draws a zone's automap only from a `.zam` its package lists, and no XML1 zone had one; the XML1 bundles'
`texture textures/automap/<name>` entries (XML1's HUD automap) were packaged although XMen2.exe never reads them.
Research with every address: `research/automaps/automaps.md`; code `tools/xml1build/automaps.py` (docstring).

### 26.1 Mechanism

- **XML1** (default.xbe): world `automap_texture="<name>"` + `automap_offset="<u> <v>"` (0xbefa0); CHudAutoMap loads
  `textures/automap/<name>` (0x152690) and maps world (x, y) to texture pixel (x / 12 - u, y / 12 - v) (0x1528c0:
  `* 0x3dd314` = 1/12, `- [+0x210]`, `- [+0x214]`). 125 grey-scale DXT textures (256 / 512 px): black nothing, grey
  floors / streets, white outlines. 175 of the 196 XML1 world entities name one (16 of them through a
  `textures/automap/...` path); the mocap briefings, the Danger Room, the Blackbirds, the menu backdrop and a few
  mansion / Muir variants have none (no map in XML1).
- **XMen2.exe**: the zone package's `<zam filename="automaps/<zone>"/>` (last entry; CAutomapPrecacher 0x561420 ->
  HUD vt+0x100 -> loader 0x5a02f0). Format (all 109 retail files parse, T2): `s16 9, s16 origin_x, s16 origin_y`
  (240-unit cells, 0x69ddf4), `s16 n`, n x `(s16 x, s16 y, u32 ARGB)` in world units, `u32 grid[41 * 41]` (index
  `x * 41 + y`: the ordinal of the cell's list, -1 none), then per listed cell `s16 count, s16 index[count]` = one
  triangle strip. The generator 0x59fa70 emits every frame the strips of the cells within 8 (small map) / 10
  (overlay and pause-menu automap, 0x5a0150) cells of the player - a (2r)^2 window clamped to cells 0..39 - as one
  strip (cells joined by 2 alpha-0 vertices) into the automap playfield's own builder of **0x2000** vertices
  (0x584dc3; the generator drops what does not fit), white x vertex alpha (XML2: 0xcb lines, 0x32 fill).
- **Fog of war** (CAutoMap 0x815e98): 82 x 82 bits of 120-unit cells from the zam origin; an unexplored vertex gets
  alpha 0, one 240 units from unexplored ground turns dark blue (0x77). Saved in the current-zone record (0x4664d0 /
  0x465630, 211 dwords), reset on zone change (0x484631). Generic: nothing to convert.
- `automap_texture` / `automap_offset` are still read into the world entity (0x4c7f90) and never used.

### 26.2 Conversion (`automaps.build`, run by zones per converted zone)

`zones.automap(zone, st)` (after the actor-budget prune): the XML1 world's `automap_texture` -> `automaps.texture_rel`
-> the XML1 file (loose, then assets) -> `automaps.convert(bytes, automap_offset)` -> `Automaps/<zone>.zam`
(`ctx.write_bytes`, source `zones:automap <texture> offset <u,v>`) and `<zam filename="automaps/<zone>"/>` appended
after `boy`. A (texture, offset) pair converts once per build (the mansion hubs share 5 textures). `build_package`
drops every bundle entry `texture textures/automap/*` (count `automap_textures_dropped`), so those textures are no
longer imported either. Problems `automap_texture_missing` / `_unreadable` / `_empty` and `automap_offset` (a value
that is not two whole numbers) are warnings; V20 makes a missing `.zam` for a texture that exists an error.

The algorithm (constants at the top of automaps.py): luminance = max(R, G, B) of the DXT colour blocks; grey area =
5 x 5 majority of `lum >= 48` (dither and the HAARP snow speckle go), white = `lum >= 160` exactly; per 240-unit cell
(20 x 20 px; whole-pixel offsets align cells with pixel edges) each level's pixels become vertical chains of row runs
whose edges are Douglas-Peucker polylines (white 0.75 px, grey 1.5 px; grey chains under 6 px dropped), broken at the
cell's 120-unit mid row (the fog cell) and emitted as one strip segment each (2 vertices per break row, degenerate
joins); grey first (alpha 0x50, XML1's ~90/255), white on top (0xcb, XML2's line value). Deterministic.

Result over all 175 XML1 automaps: 0 problems, 5.2 MB of `.zam` (19-58 KB each; retail 8-66 KB), worst draw window
7,646 strip vertices (astroid_m/visit1/asteroid1_2) of 8,192 (retail XML2 reaches 9,934 by the same count: egypt2);
rasterised back onto the texture the white outlines keep >= 0.946 recall / >= 0.928 precision and the grey area
>= 0.909 IoU (medians 0.994 / 0.995 / 0.965).

### 26.3 Not converted / differences

- XML1 drew the texture itself (grey dither, soft street ends, the HAARP snow speckle); the `.zam` is XMen2.exe's
  vector form of it: two intensities, smoothed grey edges. Layout, outlines and scale are XML1's.
- XML1's own map modes are not reproduced: XMen2.exe's fog of war, small map and overlay apply as for XML2 zones.
- Zones without an XML1 automap get none (faithful).

### 26.4 Validator V20

| id | check | severity |
|---|---|---|
| V20 | Every converted zone whose XML1 world names an automap texture has `Automaps/<zone>.zam` and exactly one `<zam filename="automaps/<zone>"/>`, the last package entry (not last: warn); a zone without one has no `<zam>`; no zone package lists `texture textures/automap/*`; every `.zam` the build wrote parses as 0x5a02f0 reads it (version 9, grid, list bounds), every list's vertices sit within 120 units of its cell, no list in cell 40, and its worst (2 x 10)^2-cell draw window fits the 0x2000-vertex builder (warn above 7,800). A texture missing from the disc is a warning. | error / warn |

### 26.5 Tests

`python -m xml1build.automaps_selftest [--out <build>] [--all] [--asm-dir <research/scripts>]` (from `tools/`): T1 23
disassembly lines (loader, grid, window clamp, builder size and primitive, fog grid, XML1's transform and texture
path); T2 all 109 retail `.zam` parse and re-pack byte for byte, 18,781 / 18,789 lists sit in their grid cell; T3
fidelity of 6 sample zones (`--all`: all 175) and determinism; T4 placement: the XML1 nav cells of 7 enclosed maps
fall inside the drawn outlines (1.000 each) and not with the rows flipped (mean 0.141) or the offset negated (0.490);
T5 V20 over a build.

### 26.6 In game (build/_automap, 2026-09-29, harness pipe `automap`)

Verified: New Game -> `nyc/alison/nyc1_1_1`; pause menu > Automap draws XML1's map around the hero marker, only
the explored cells near the start at first (fog; the rest appears when the fog bits are cleared); the HUD small map
(mode 1, the default) shows it too. `mansion/man1a/mansion1a_1` (Xavier's office): the office outline encloses the
hero and the desk, edges parallel to the room's walls; small map on the HUD. `astroid_m/visit1/asteroid1_2` (the
densest map, 7,646): complete around the player, the room / corridor outlines fit the rooms and the door the hero
stands between. No exception in dbg.log. Screenshots `screenshots/automap_*.png`. The fog was cleared by writing
CAutoMap's bits (0x815e9c, 211 dwords) in the test process only (scratchpad fog.py); on PC the "next to unexplored
ground" colour 0x77 shows red, not blue (D3D colour order), as for XML2's own maps.

Not seen: fog revealing while walking a long way; save / load keeping the fog; an act town centre revealing all.

## 27. Inputs: the Sources object and the prepare phase (2026-09-29, M3 phase 1a + 1b)

Before: every module read its inputs through module constants (`common.ROOT / X1_LOOSE / X1_ASSETS / X1_XBOX /
RESEARCH / DEFAULT_BASE`) that point at hand-made folders on Owen's PC (BUILDER_DESIGN.md F1, F6). Now the build reads
them through one `Sources` object, and the prepare phase regenerates every game-derived input - the XML1 trees, the
research tables, the rewritten scripts, the sound banks and the fixed music banks - from the user's Xbox disc image
and XML2 install. Design: `research/release/BUILDER_DESIGN.md` 1.1, 1.5, 6 phase 1. Phase 1a: Sources, P1, P2;
phase 1b: P3-P5, movies optional, the full equivalence, the self-tests in both modes.

### 27.1 `xml1build/sources.py`

| Field | Developer mode (default) | Prepared mode |
|---|---|---|
| `x1_loose` | `<repo>/xml1_loose` | `<cache>/<disc_id>/disc/loose` |
| `x1_assets` | `<repo>/xml1_assets` | `<cache>/<disc_id>/disc/assets` |
| `x1_xbox` | `<repo>/xml1_xbox` | `<cache>/<disc_id>/disc/xbox` (the movies only for movies builds, 27.3) |
| `xml2` | `--base` | `--base` |
| `research` | `<repo>/research` | `<repo>/research` (only the tracked tables no stage makes: API tables, `graph.json`, `x1_namespace_map.json`, `combat_compat.json`, ... - packaged data) |
| `overrides` | none | P2: `scripts/mission_plan.json`, `characters/collisions.json`, `characters/x2_stats_refs.json`, `sound/names_xml1.json`; P3: `scripts/out`; P4: `sound/out`; P5: `sound/music0x20` |
| `movies_index` | none | `<cache>/<disc_id>/disc/movies.json` (27.3) |

- `research_path(rel)`: the longest override that is `rel` or a whole-component prefix of it, else `research/<rel>`.
  `ctx.research_path` / `ctx.research_json` go through it; no module joins `ctx.research / rel` any more (SPEC 3.3).
  The P4 / P5 overrides cover whole trees (`sound/out`, `sound/music0x20`), so every path below them - including
  `validate`'s `sound/out/merged` and media's old fallback folders - resolves inside the stage directory.
- `BuildContext(..., sources=None)`: None = `Sources.for_out(out)`: `<out>/_build/sources.json` (a prepared build
  writes it) else developer mode, so the self-tests and `validate` run standalone over a build read the inputs that
  build read (27.11). `build_xml1.py` passes its Sources explicitly; a developer build deletes a stale `sources.json`.
- `protected()`: the input trees, `research/`, `tools/`, the overrides and the cache; `_check_out_safe` refuses an
  `<out>` overlapping any of them.
- `collisions`: the collisions.json x1names reads (`x1names.use_collisions`, set by BuildContext): every `x1_`
  rename follows the Sources' table, not the file next to x1names.py.
- The `common.X1_*` / `RESEARCH` / `ROOT` constants stay for standalone research tools; the pipeline modules and the
  self-tests no longer use them for inputs.

### 27.2 Command line

```
python tools/build_xml1.py --out DIR [...] --sources prepared --cache CACHE [--iso IMAGE] [--no-movies] [--jobs N]
python tools/prepare_xml1.py --cache CACHE [--iso IMAGE] [--stages disc,tables,scripts,sound,music] [--force [STAGES]]
                             [--no-movies] [--jobs N] [--base XML2]
python tools/prepare_xml1.py --identify IMAGE
python tools/prepare_equiv.py --disc CACHE/<disc_id>/disc          (P1/P2 vs xml1_* and research/)
python tools/build_equiv.py REF_OUT NEW_OUT [--map REF_ROOT=NEW_ROOT ...]   (two builds, file for file)
python tools/sound_equiv.py REF_ROOT NEW_ROOT [--map REF_INPUT=NEW_INPUT]  (P4 / P5 outputs vs a reference run)
```

Prepared mode runs the five stages in order (`prepare.run_stages`; each reused while its cache key matches) and
builds from them; `--jobs` (default: half the CPUs) is also P4's and P5's worker count. Without `--iso` the cache must
hold exactly one prepared disc (the user may delete the image after the first build) - and, for a movies build, one
prepared with its movies. Exit codes: 3 = input not usable (`PrepareError`: `E_ISO_*`, `E_CACHE_EMPTY`,
`E_CACHE_AMBIGUOUS`, `E_CACHE_NO_MOVIES`, `E_XML2_LANGUAGE`), 1 = a stage could not make a correct output
(`StageFailed`: `E_PREPARE_SOUND`, `E_PREPARE_MUSIC`) or the build failed. The `report.json` `build` block is unchanged
in both modes; the Sources (paths, overrides, stage keys) are in `_build/sources.json`.

Cache layout: `<cache>/<disc_id>/disc/` (P1) and `<cache>/<disc_id>/prepared/<stage>-v<N>-<key12>/` (P2-P5); each
stage writes `stage.json` (key, counts, timings, jobs / memory budget) into a `.partial` directory and renames it when
done (a leftover `.partial` is deleted by the stage's next run; an older key of the same stage is deleted once the new
one is published). `disc_id` = the first 12 hex of default.xbe's md5 + the first 8 of the digest of assetsfb.zip's
central directory (member names, sizes, CRC-32s): Owen's World dump is `1e1a766ae4dc78bcd91b`. Keys hash contents or
listings, never the cache path: two caches of the same disc and install get the same stage directory names.

### 27.3 P1 `disc` (`prepare/image.py`, `xbe.py`, `fb.py`, `disc.py`)

- **Formats** by content: XDVDFS magic (`MICROSOFT*XBOX*MEDIA` at partition + 0x10000 and + 0x107EC) at
  0x18300000 (Redump XGD1: Owen's dump), 0x0FD90000 (XGD2), 0x02080000 (XGD3), 0 (XISO). The XDVDFS check comes
  first: a Redump Xbox image also has an ISO 9660 PVD at 0x8000 (its video partition). Rejected: CCI (`CCIM`),
  CSO/ZSO (`CISO`/`ZISO`), zip/7z/rar -> `E_ISO_COMPRESSED` with how to decompress; GameCube (0xC2339F3D at 0x1C),
  Wii (0x5D1C9EA3 at 0x18), PS2 / PS1 (ISO 9660 + `SYSTEM.CNF` with `BOOT2` / `BOOT`), other ISO 9660, anything else
  -> `E_ISO_NOT_XBOX` + `detected`; a folder `E_ISO_FOLDER`; a file or directory past the image end `E_ISO_READ`.
- **Reading**: the directory trees are walked (left/right links in 4-byte units, 0xFFFF = sector padding); every file
  is one extent read through a `SubFile` window; `zipfile` opens `z/assetsfb.zip` on its window. Nothing is copied
  that the build does not read.
- **Identification**: `default.xbe` certificate title ID 0x4156001E (title "X-Men Legends", version 1, region 7)
  else `E_ISO_WRONG_GAME` (+ the title found); `z/assetsfb.zip`, `sounds/zsds/**`, `movies/ntsc/**.sfd` present else
  `E_ISO_INCOMPLETE` (+ `missing`). Every zip member is read, so every CRC-32 is checked (`E_ISO_READ`).
- **Outputs**: `xbox/` = `default.xbe`, `sounds/zsds/**` and - for a movies build - `movies/ntsc/**` (spelled as on
  the disc); `assets/` = every zip member except the `.fb` bundles (folder entries created); `loose/` = the bundles
  unpacked from memory with `fb_unpack.py`'s rules: bundle order = the paths sorted with `\` separators (its glob ran
  on Windows; proven by `_fb_manifest.json`'s key order: `dr_mag2/*` before `dr_mag/*`), entry names
  `lstrip('/').lower()`, the first bundle carrying a name writes it (17 conflicting and 24,021 identical duplicates on
  the disc), the manifest `json.dumps(indent=1)` with CRLF; zip member names that escape the tree are refused.
- **Movies follow the build's option** (phase 1b): `run(..., movies=False)` (a `--no-movies` build) leaves the 648 MB
  of `movies/ntsc` out; `stage.json` says `"movies": false`. `movies.json` is always written, read **from the image**
  (`media.sofdec_info_bytes` over each movie's first 2 MB: name, disc path, size, `dirs`, duration, and the same
  Sofdec facts `media._sofdec_info` gives for the file). A `--no-movies` build reads only those facts - media's
  `x1_movie_files` / `movie_facts` serve `_x1_movies`, `movie_duration` (the Review durations) and
  `_install_movies`' detail rows from `movies.json` when the files are absent, and `scripts._x1_movie_names` and
  validate V9 go through them - so it builds the same files (27.8). A later movies build with `--iso` adds the files
  to the same directory (`add_movies`: a `xbox.movies.partial` tree renamed into `xbox/`, then `stage.json`; the key
  does not change); without `--iso` it stops with `E_CACHE_NO_MOVIES`. P1 directories made before the option always
  have the movies (`has_movies`: a missing `movies` key means true).
- **Not written** (never read by the pipeline): `z/assetsfb.zip`, the 875 `.fb` files, `movies/pal/**`, `media/*.bin`,
  `OptionsImage.xpr`, `alchemy.ini`, `build.ini`, `sounds/badaudio.wav`.
- **Key**: stage version + xbe md5 + zip central-directory digest + the disc listing (path, size, is_dir) - the
  content, never the image path or layout (an XISO of the same disc has the same key; unit test).
- Owen's dump: 17 s with the movies (read ~2.2 GB, write 2.2 GB: 251 + 916 + 7,620 files), 13 s without (1.5 GB).

### 27.4 P2 `tables` (`prepare/tables.py`)

The research generators, ported as functions over P1's trees + the XML2 install (indexed like the base index, the
xml2-fix proxy excluded); files written with CRLF, as the generators wrote them on Windows:

| Output | Replaces (research/) | Generator ported |
|---|---|---|
| `mission_plan.json` | `scripts/mission_plan.json` | `scripts/mission_plan.py` |
| `missions/x1_act01..09.xml`, `missions.xml` | `scripts/out/data/missions/*.xml` (P3 compiles them) | `scripts/mission_plan.py` |
| `collisions.json` | `characters/collisions.json` | `characters/collisions.py` (its own plain parser: a file it cannot parse is `x1_parse_error`) |
| `x2_stats_refs.json` | `characters/x2_stats_refs.json` | `characters/x2_unref.py` |
| `names_xml1.json` | `sound/names_xml1.json` | `sound/resolve.py` + `soundrefs.py` (XML1 only) |

`names_xml1`: the generator iterated a Python set of candidate names, so where two candidates hash to the same bank
key (ELF hashes collide) the name it kept depended on PYTHONHASHSEED. P2 takes the candidates in sorted order (the
last assignment wins, as in the loop) and records every such key in `stage.json` `ambiguous_sound_keys`. The ELF
hashes run in numpy over columns (`_elf_np`, `_random_chain`; unit-tested equal to `zhash.elf_hash` and the loop).
Key: version + P1 key + the XML2 listing (rel, size, mtime_ns). Owen's PC: 25-46 s (the first read of freshly
written files is slower).

### 27.5 P3 `scripts` (`prepare/scripts.py`)

`research/scripts/rewrite_scripts.py` ported as a `Rewriter` object (the analysis passes in the constructor, the
outputs in `write(out)`): P1's `loose/` (+ `_fb_manifest.json`) and `assets/`, P2's `mission_plan.json`, and the
packaged API tables `research/scripts/xml{1,2}_api.json`. It writes the research layout under `<stage>/out/`
(`scripts/**.py`, `scripts/x1/**`, `dialogs/x1/*`, `data/missions/*` = P2's texts copied and compiled to XMLB/engb,
`zone_acts.json`, `inline_rewrites.json`, `helper_refs.json`, `zone_extra_files.json`, `var_storage.json`) and the
two reports next to it (`rewrite_report.txt/.json`). Sources override: `scripts/out` -> `<stage>/out`.

- Same rules, same engine facts (the module docstring now carries them). Three deliberate differences, none of which
  changes a byte on Owen's PC: the trees are walked in NTFS directory order on every file system
  (`prepare.ntfs_walk`: names sorted by their upper-case form = `FindFirstFile` on NTFS, checked equal to `os.walk`
  on the P1 and hand-made trees - the dialog / helper numbering and the key order of `inline_rewrites.json` and
  `zone_acts.json` follow the walk); the inline-code scan's "skip `/scripts`, `/packages`" test looks at the path
  below the tree root (the generator tested the whole path: a cache under `...\AppData\Local\Packages\...` would have
  skipped every file); files are written with explicit CRLF where the generator relied on Windows text mode.
- `bescript.py` (the BehavEd parser) moved to `tools/xml1build/lib/`; `research/scripts/bescript.py` is a shim.
- Key: version + P1 key + sha1 of P2's `mission_plan.json` and mission texts + sha1 of the two API tables.

### 27.6 P4 `sound`, P5 `music` (`prepare/sound.py`, `prepare/music.py`)

| Stage | Does | Output (Sources override) |
|---|---|---|
| P4 | `convert_zsnd --batch <P1 sounds/zsds> --encoder auto --rekey character/=char/` with P2's `names_xml1.json` passed explicitly (`convert_all`: the same jobs, groups and report as the CLI), then `merge_all` (every converted bank whose name XML2's `Sounds/eng` also has, merged by `merge_zsnd.merge`) | `all_ima/eng/**` + `_convert_report.json`, `merged/eng/**` + `_merge_report.json`, `convert.log`, `merge.log` (`sound/out` -> `<stage>`) |
| P5 | `tools/fix_music.py fix` with its defaults over P1's `sounds/zsds` (the 61 stereo `*_a` / `*_c` banks), its two roots now parameters (`xbox_root`, `xml2_root`); every bank then checked with `media_music.check_bank` against its Xbox original in the same worker | `banks/eng/**` + `_fix_music_report.json`, `check.json`, `music.log` (`sound/music0x20` -> `<stage>`) |

- **The 61 music banks stay in P4** (design 1.5 suggested skipping them): `common.planned_sound_banks` plans every
  XML1 bank from the `all_ima` file list, and media holds each fixed music bank to its 1:1 conversion
  (`media_music.structure_diff`: keys, entries, rates) - the 1:1 banks are the reference. With the compiled kernel
  they cost ~35 of P4's ~80 CPU-s (4 jobs; roughly 7 s of its wall time) and 371 MB of cache; skipping them needs a
  planner that plans music banks from the disc and another structure reference (not worth the risk now).
- **P5's acceptance is `check_bank`, not hashes**: nothing is published unless all 61 banks pass (`StageFailed`
  `E_PREPARE_MUSIC`, exit 1). `fix_music.beam_window` keeps its survivors in `np.argpartition` order, whose tie order
  depends on the numpy build and the CPU (BUILDER_DESIGN 1.5 fact 2), so another PC's banks may differ in bytes and
  still be right. On Owen's PC they are byte-identical to `build/_snd_final/music/eng` (27.8).
- **Prepared mode never falls back into `research/`**: the override covers all of `sound/music0x20`, so the old
  fallback folders (`banks_all`, `banks_22k`, `_previous_attempt`) would resolve inside P5's directory, where they do
  not exist; and `media.fixed_music_dirs` returns only P5's `banks/eng` in prepared mode (`$XML1BUILD_MUSIC_DIR` is
  ignored there, with a warning). A music bank P5 lacks, or whose check fails in the build, is a media **error**
  ("prepared mode: no music bank from prepare stage P5 plays correctly"), never the 1:1 bank (developer mode keeps its
  fallback). The build's own deep check (media, cached per output) runs as before, so every build re-checks the
  banks it installs.
- **Memory**: a P5 worker peaks at 0.6 GB + ~110 MB per MB of Xbox bank (nuke_c, 21 MB: 2.7 GB of commit), a P4 bank
  group at ~0.5 GB + ~15 MB per MB. Sixteen P5 workers ran this 32 GB PC out of commit (`_ArrayMemoryError`), so
  `prepare.pool_map` starts a task only while the estimated memory of the running tasks plus its own fits a budget:
  85 % of min(free physical, free commit) - 1 GB at stage start (`memory_budget_mb`; `$XML1_PREPARE_MEMORY_MB`
  overrides the available figure). Biggest first, results in input order; one task always runs.
- Keys: P4 = version + P1 key + sha1 of P2's `names_xml1.json` + the listing (rel, size, mtime) of XML2's
  `Sounds/eng`; P5 = version + P1 key + that listing (the report's `xml2_ships_same_name`). The codec (kernel or
  numpy) is not part of the key: both give the same bytes.
- Reports name the published directory (`prepare.rebase_paths`: the stages write into `<final>.partial` and rename).

### 27.7 What became of the research generators

The rule: **one implementation**. A generator a stage took over completely becomes a thin CLI over the stage's function
(same command line, same output); a generator whose tracked output is still the developer-mode input keeps its code with
a `SUPERSEDED` note; libraries the stages call stay where they are.

| Research file | Now |
|---|---|
| `scripts/rewrite_scripts.py` | wrapper over `prepare.scripts.Rewriter` (developer paths, writes `research/scripts/out` + the reports); output byte-identical |
| `sound/merge_all.py` | wrapper over `prepare.sound.merge_all` (`[converted_root] [out_root] [xml2_sounds]`); output and report identical |
| `scripts/mission_plan.py`, `characters/collisions.py`, `characters/x2_unref.py` | unchanged code + `SUPERSEDED` header: P2 regenerates their outputs; they remain the generators of the tracked research copies (developer input, P2's reference) |
| `sound/resolve.py` (+ `soundrefs.py`) | `PARTLY SUPERSEDED` header: P2 makes `names_xml1.json` (sorted candidates); the XML2 half stays research |
| `sound/convert_zsnd.py`, `merge_zsnd.py`, `zsnd.py`, `ztrk.py`, `zhash.py`, `adpcm*.py`, `simlookup.py`, `ima_kernel.c`, `sweep/sweeplib.py`, `characters/x1names.py`, `tools/fix_music.py` | moved to `tools/xml1build/lib/` (phase 3, 27.13); shims left behind (the `.c` file moved without one) |
| `scripts/bescript.py` | moved to `tools/xml1build/lib/bescript.py`; shim left behind |

### 27.8 Equivalence evidence (Owen's PC, 2026-09-29)

Phase 1a:
- Developer mode unchanged: `build/_p1_dev_a` (old code, kept as the reference) vs `_p1_dev_c` (Sources; deleted
  after the check): 21,379 files (3.68 GB) + 12 `_build` JSON files, 0 differences (`build_equiv.py`). A second build
  of the old code (`_p1_dev_b`, deleted) was identical too; the one difference seen on the way was
  `characters_detail.json`'s thread-timed skin order, now recorded in job order (49d95cf).
- P1 vs the hand-made trees: loose 7,620 / assets 916 / xbox 251 files byte-identical; only in the hand-made trees:
  875 bundles, `z/assetsfb.zip`, 35 PAL movies, 2 `media/*.bin`, 4 settings / art / wav files (27.3).
- P2 vs research: `mission_plan.json`, `collisions.json`, `x2_stats_refs.json` and the 10 mission texts
  byte-identical; `names_xml1.json` differs at 11 of 22 ambiguous keys (all pairs of equally valid names, e.g.
  `object_ambi/arbiter_fld/shipcreak/***RANDOM***/0` vs `zone_link01/***RANDOM***/0` in `arbfld_m`), nowhere else, and
  none is a `character/` name (the only names P4's `--rekey character/=char/` reads).

Phase 1b:
- **P3** vs `research/scripts/out`: 1,846 files and both rewrite reports byte-identical (the port over P1's trees;
  the `rewrite_scripts.py` wrapper over `xml1_*` reproduces them too, with the reports in git unchanged).
- **P4 / P5** vs `build/_snd_final` (`sound_equiv.py`, the zsds root mapped): 216 `all_ima` + 18 `merged` + 61
  music banks and the three reports identical - at 16, 8 and 4 jobs, with the compiled kernel. (`research/sound/
  music0x20/banks` equals `_snd_final/music` as well; `research/sound/out/all_ima` differs in the 21 music banks of an
  earlier run, BUILDER_DESIGN 1.5 fact 1.) The `merge_all.py` wrapper reproduces `_snd_final/merged` too.
- **Developer mode unchanged by phase 1b**: a `--no-movies` developer build of the 1b code vs `build/_p1_dev_a`:
  21,379 files (3.68 GB) + 12 `_build` JSON files identical.
- **Full equivalence, movies on**: the first prepared build from the ISO into an empty cache
  (`build/_p1b_prep_mov`) vs a developer build of the same code: **21,427 files (4.82 GB) + 13 `_build` JSON files
  identical** (`build_equiv.py`, the source roots, P3-P5 and P2's tables mapped). The one difference on the first
  run was `_build/media_cache/movie_verify.json`: its values are `[size, mtime_ns]` stat keys of the movie sources
  (when the developer tree or the cache was written), so `build_equiv` now compares them by size (3f5e44c). The 21
  old `all_ima` music banks leave no trace: builds install the fixed banks and media reads only the 1:1 banks'
  structure.
- **Full equivalence, `--no-movies`**: the first prepared `--no-movies` build from the ISO, with P1 **without** the
  movie files (the `movies.json` path), vs `build/_p1_dev_a`: **21,379 files + 12 `_build` JSON files identical**.
- A warm rebuild into the same `<out>` differs from a fresh build in one report field (any mode, not new):
  `scripts_detail.json` `popup_dialog_sources` counts the 23 XML1 dialogs as `out` instead of `xml1`, because
  `scripts.dialog_source` finds the ones the previous build's zones imported in `<out>` (scripts runs before zones).
  Game files identical.
- Self-tests (27.11): all eleven pass on the developer and on the prepared movies-on build.
- Kept: `build/_p1_cache` (P1-P5 of Owen's dump, 3.2 GB; the stage directories have the same names as in any cache of
  this disc + install), `build/_p1b_prep_mov` (the prepared movies-on build, 4.6 GB; rebuilt warm from `_p1_cache`,
  its `sources.json` points there), `build/_p1_dev_a` (phase 1a's developer `--no-movies` reference),
  `build/_p1b_equiv_movies.json`, `build/_p1b_equiv_nomovies.json`, the logs `build/_p1b_*.log`. Deleted after the
  comparisons: the developer movies-on and `--no-movies` builds, the prepared `--no-movies` build, both scratch caches,
  and phase 1a's `build/_p1_prep` (superseded).

### 27.9 Timings (Owen's PC: Ryzen 7 5700X, 8 cores / 16 threads, 32 GB; compiled sound kernel)

All with the compiled sound kernel; about 12 GB of the 32 GB were free during the runs (other programs running).

| Stage | 16 jobs | 8 jobs (the build's default) | 4 jobs |
|---|---|---|---|
| P1 disc | | 16.9 s (movies) / 13.4 s (no movies) | |
| P2 tables | | 46.1 s / 41.8 s (freshly written files; ~25 s warm) | |
| P3 scripts (one process) | 7.9 s | 8.7 s | 8.2 s |
| P4 sound: convert + merge | 22.3 s (20.5 + 1.3; 166 CPU-s) | 18.4 s (16.7 + 1.2; 98 CPU-s) | 25.9 s (24.2 + 1.3; 78 CPU-s) |
| P5 music: fix_music + check_bank | 105.2 s (budget 9.3 GB; 417 CPU-s) | 93.0 s (8.8 GB; 374 CPU-s) | 100.4 s (8.1 GB; 341 CPU-s) |

P5 is memory-bound here, not core-bound: the budget lets only 3-4 of the big banks run at once whatever `--jobs` says
(the 1p measurement, 65 s at 16 jobs, had no check and more free memory). P4 is fastest at 8 (hyperthreads inflate
its CPU time at 16).

| Build (Owen's PC) | Wall time |
|---|---|
| **First build from the ISO, empty cache, movies on** (`build_xml1 --sources prepared --cache --iso`, 8 jobs) | **5 min 32 s** (prepare 3.0 min: P1 17 s, P2 46 s, P3 9 s, P4 18 s, P5 93 s; sync + modules + validate 2.5 min) |
| First build from the ISO, empty cache, `--no-movies` | 5 min 24 s |
| Warm rebuild, all five stages cached, same `<out>`, no `--iso` | 83-107 s |
| Developer build of the same content (research outputs already there) | 2.6 min |

Disk: the cache is 3.2 GB with the movies (P1 2.16 GB of which movies 648 MB; P2 1 MB; P3 4 MB; P4 676 MB =
`all_ima` 523 MB incl. the 61 music banks + `merged` 153 MB; P5 372 MB), 2.6 GB without; the output 4.6 GB with the
movies (incl. the 377 MB `_build/media_cache` snapshot of the music banks) / 3.5 GB without.

### 27.10 Tests without game data (`tests/unit`, BUILDER_DESIGN 6.1)

`python tests/unit/run.py` (or pytest): 24 tests, ~2 s (+3 s when the sparse-file test runs). `synth.py` generates
XDVDFS images (chain / balanced trees, tables spanning sectors, the Redump layout as a virtual file and a sparse
file), XBE headers, bundles and zips. Covered: format detection and every rejection, SubFile + zipfile on a window,
truncated images, the XBE certificate, bundle order and first-bundle-wins, P1 end to end (trees, manifest bytes,
conflicts, reuse, the key across layouts, wrong / incomplete / damaged discs), Sources overrides / round trip /
`for_out`, `_check_out_safe`, the numpy ELF hash and random chain, the mission plan grouping, collision categories;
phase 1b (`test_prepare_stages.py`): P1 without movies (movies.json from the image, a synthetic Sofdec/ADX header ->
duration 10.0 s), the no-movies providers reading it, `E_CACHE_NO_MOVIES`, `add_movies` (same key, same facts from
the files), `Sources.movies_index` round trip, the P3 `Rewriter` on a tiny XML1 tree (storage plan, popup dialog ->
`x1/p001`, beginMission -> setCurrentAct + objective resets, act injection, inline rewrite, deterministic output),
`ntfs_walk` order (= `os.walk` on Windows), `rebase_paths`, `find_ci`, `pool_map` (order, budget, worker errors,
cancel).

### 27.11 Self-tests over a build, in both modes

Every self-test reads its XML1 / XML2 inputs through the Sources of the build it is given (`Sources.for_out(out)`:
the build's `_build/sources.json`, else developer mode): `automaps_selftest`, `combat_events_selftest`,
`npc_values_selftest`, `skins_selftest` (a `use_sources()` hook set from `--out`; without `--out` developer mode),
`regress_nyc1` (the XML1 zone and the converted banks; `xml2_test` and `grso_riot_scheme` stay developer
references), `schema_check` (`scan_out` roots), `igb_budget` (`--x1` defaults to the build's loose tree).
`characters_selftest` K now follows SPEC 18.1: with the heroes module, npcstat also holds the speaker-only entries
(`scripts_transform.speaker_stats_entries`: `<hero>_x1double`, `cyclops_scripted`, `alison`, `alison_scripted`,
`emma`); each must be there (team none, not playable) and they are neither planned XML1 names nor kept XML2
entries. Results: 27.8.

### 27.12 Not done yet (phase 2: the builder CLI)

(Phase 2 is done - `tools/xml1builder/`, BUILDER_DESIGN 2.9: the cache lock, `known_*.json`, `--drop-cache` /
`clean --cache`, builder mode without the music snapshot, the kept proxy files, registry sha1 + the manifest, the
stamp. Phase 3 (27.13) did the lib move, the frozen builder and the packaged, text-free graph.json / zones.json for
the release. Still open: the same strip for the public repo's own copies, dropping `console_senders.json` and
`ctx.collisions`, and computing the zones.json warning in the build - phase 5.)

For the builder CLI (BUILDER_DESIGN 2, phase 2):

- **Entry points**: `prepare.run_stages(cache, xml2, iso, stages, jobs, movies, log, cancel, progress, force)` ->
  `{stage: {'dir', 'stage', 'cached'}}`; `prepare.prepared_sources(...)` -> the `Sources` for
  `BuildContext`; `build_xml1.main` does both today (`make_sources`). `progress(stage, done, total, unit)` fires for
  P1 (files), P4 (bank groups) and P5 (banks); P2 and P3 are short and silent; the content modules print `[module]`
  lines. Stage weights: 27.9.
- **Cancel**: `check_cancel` takes an Event or a callable; the stages check it per file / bank / script batch;
  `pool_map` polls it every 0.5 s and terminates its workers; the next run deletes the `.partial` directories.
- **Errors**: `PrepareError` = input (exit 3), `StageFailed` = our bug (exit 1); `.code` / `.msg` / `.hint` /
  `.detail` are ready for the event stream.
- **Not done**: the cache lock (design 2.6: two builders on one cache would delete each other's `.partial`);
  `known_dumps.json` / `known_xml2.json` identification (P1's `identify()` already returns xbe md5, zip digest,
  listing digest, disc id); `--drop-cache` / `clean --cache` (= delete `<cache>/<disc_id>`; P1 directories are never
  pruned automatically); builder mode without the `_build/media_cache/music_fixed` snapshot (372 MB: P5's directory is
  the source, design 1.3), keep `PROXY_PATTERNS` in the sweep (F3), registry sha1, the stamp.
- **Idempotent rebuilds**: expect the `popup_dialog_sources` report difference of 27.8 on a rebuild (make
  `dialog_source` ask the registry instead of `<out>` if the builder compares reports).
- **Frozen builder**: P4, P5 and media use process pools (spawn): `multiprocessing.freeze_support()` first in main;
  the workers import `xml1build.prepare.sound/music`, `convert_zsnd`, `merge_zsnd`, `fix_music`, `media_music`,
  `adpcm`/`adpcm_c`/`adpcm_np`, `zsnd`, `ztrk`, `zhash` (hidden imports) and the kernel DLL. `fix_music` still puts
  `research/sound` and `tools/` at the front of `sys.path` when imported.
- **Memory**: P5 decides its concurrency from free memory at stage start (`memory_budget_mb`; override
  `$XML1_PREPARE_MEMORY_MB`); an 8 GB PC runs one or two music banks at a time (P5 ~5-6 min there, estimate).
- **Left from the phase-1 table** (BUILDER_DESIGN 6): move the remaining research modules the build imports
  (`convert_zsnd`, `merge_zsnd`, `zsnd`, `ztrk`, `zhash`, `adpcm*`, `simlookup`, `sweeplib`, `x1names`) and
  `tools/fix_music.py` into `xml1build/lib/` (only `bescript` moved); strip `graph.json`'s text fields; compute the
  `zones.json` sound-slot warning in the build; drop `console_senders.json`; remove `ctx.collisions`. The public repo
  (design 5.3) needs these.

### 27.13 Phase 3: the lib move, the frozen builder, CI (2026-09-29)

Design: BUILDER_DESIGN.md 3.2, 3.3, 4.5, 6 phase 3; status there in 3.6.

**The lib move.** `sweeplib`, `x1names`, `zsnd`, `ztrk`, `zhash`, `adpcm`, `adpcm_np`, `adpcm_c` + `ima_kernel.c`,
`simlookup`, `convert_zsnd`, `merge_zsnd` and `fix_music` live in `tools/xml1build/lib/` (with `bescript`; module map
in its `__init__.py`). Package-relative imports, no `sys.path` set-up, no machine paths: the developer defaults
(x1names' collision table, convert_zsnd's name table, fix_music's CLI roots, adpcm_c's `build/native`) come from
`xml1build.sources.REPO_ROOT` / `DEFAULT_XML2`. The old files are shims that put the lib module itself into
`sys.modules` (research code that imports `zsnd` gets the same object; `python research/sound/zsnd.py` and
`python tools/fix_music.py fix` still run; zsnd / ztrk keep their developer default folders in the shim, the sweeplib
shim keeps `X1` / `X1A` / `X2`). Also removed from the builder's reach: common's research `sys.path` loop, the tools/
inserts of media_music, fix_ini, skins and build_xml1.py, and `xml1builder/__main__.py`'s folder bootstrap when
frozen. `ima_kernel.c` is unchanged (source sha1 `e6059e7f...`), so existing kernels stay valid.
Proof: a developer and a prepared (`build/_p1_cache`) `--no-movies` build of the move vs the same builds of
`c47f81c`: 21,379 files (3.68 GB) + 12 `_build` JSON identical each (`build/_p3_equiv_{dev,prep}.json`); the eleven
self-tests pass on both builds; `sound_selftest --require-kernel` passes.

**What the frozen builder reads.** An audit hook (`sys.addaudithook`, `build/_p3_trace_builder.py`) over a full
builder build listed every file opened under the repo: the three `xml1builder/data` files and eight research tables
(`xml1builder.resources.RESEARCH_DATA`: `characters/combat_compat.json`, `scripts/verify/console_senders.json`,
`scripts/xml{1,2}_api.json`, `scripts/xml2fix_api.json`, `scripts/xml2_console_cmds.txt`, `sweep/graph.json`,
`sweep/zones.json`). Nothing else: the prepare stages read only the two API tables; `x1_namespace_map.json` and
`sweep/collisions.json` are never opened.

**No game text in a release** (BUILDER_DESIGN 5.2). `graph.json` carries ~120 mission titles / descriptions and
`zones.json` zone-link names. The frozen builder carries packaged copies (`tools/freeze_builder.py package_research`):
graph.json without any `descname` / `description` plus a `_packaged` key; zones.json reduced to zone ->
{`chr_characters`, `spawner_characters`} (all media's sound-slot warning reads; 1.26 MB -> 42 KB). The one reader of
mission texts, `scripts._derive_find_hero_branch` (the Find-Gambit branch), takes them from the mission plan when
graph.json is packaged (`scripts._mission_texts`): the same `data/missions/<m>.eng` attributes, made from the user's
disc by P2. Without the mark (developer and python-run builds) nothing changes. The freeze runs the content guard over
the bundled data and stops on a finding.

**Frozen layout** (`tools/xml1builder/xml1-builder.spec`, PyInstaller 6.22.3 one folder, CPython 3.14.7, numpy 2.5.3):
`xml1-builder.exe` + `_internal/` (`sys._MEIPASS`): `xml1builder/data/` (known_dumps, known_xml2,
xml2_retail_files.json.gz, build-info.json), `research/<rel>` (the packaged tables), `xml1build/lib/ima_kernel.c` +
`ima_kernel-win_amd64.dll` (adpcm_c looks next to itself and checks the source sha1). Frozen, `$XML1_PORT_ROOT` is
always set to `_internal` (an inherited value is overridden) and `resources.check_root()` refuses a data root outside
the bundle (`E_INTERNAL`); the log header names the data root. Hidden imports: every xml1build / xml1builder module
except the self-tests and developer tools (`igb_budget`, `schema_check`, `regress_nyc1`, `devdata`), `build_xml1`,
`xmlb`. No UPX, `optimize=0` (asserts stay), a VSVersionInfo resource from `VERSION`, an asInvoker + long-path-aware
manifest; bootloader: the wheel's (from source is a CI switch, BUILDER_DESIGN 3.3).

**Release files** (`tools/freeze_builder.py`): `dist/xml1-builder/`, `dist/xml1-builder-<VERSION>-win64.zip`
(exe and `_internal/` at the top), `dist/xml1-builder.json` = the manifest ultimate-legends' `tool_install::
parse_manifest` (branch `xml1-entry`) reads: `version`, `content_version` (int), `zip`, `size`, `sha256`,
`min_launcher` (`MIN_LAUNCHER` = 0.0.0 until the first launcher release with the xml1 entry), `requires_xml2fix`
(`>=` + `fix_ini.REQUIRED_XML2FIX`); `dist/SHA256SUMS.txt`. 0.1.0: 120 files, 55.7 MB unpacked, **23.7 MB zipped**
(23,690,535 bytes). `tools/freeze_smoke.py` (no game data): layout, `--version` text / jsonl, wrong-game /
synthetic-XML1 / XML2-stand-in / usage errors through the exe, an inherited `$XML1_PORT_ROOT` ignored.

**Frozen end to end** (Owen's PC; the zip unpacked with `tar.exe` into a folder outside the repo, PATH =
System32 + Windows only, no Python variables; `build/_p3_frozen_e2e.ps1`, results in `build/_p3_frozen_results/`):

| Run | Result | Time |
|---|---|---|
| `--version`, first start after unpacking / warm | exit 0 | 0.29-0.58 s / 0.12-0.14 s |
| `info --iso <World dump> --xml2 <install> --cache build/_p1_cache` | known dump `xml1-world-v1`, retail-en exe, all five stages cached, kernel present | 4.1-4.4 s |
| `build --no-movies` into `build/_frozen_e2e`, cache `build/_p1_cache` | exit 0, 0 errors, 268 warnings, stamp current | 127-140 s (sync 28, content 61, validate 24, finish 9) |
| `verify` | current, 21,318 files | 9.8-9.9 s |
| first build from the ISO, **empty cache**, `--no-movies` | exit 0; kernel loaded from `xml1build\lib`; P4 / P5 / media worker pools ran frozen | **432 s** (P1 16, P2 38, P3 6, P4 25, P5 157, sync 30, content 104, validate 41, finish 13) |

Equivalence: the frozen build (cached cache) vs `python -m xml1builder build` of the same commit from the same cache:
21,319 files (3.29 GB) + 15 `_build` JSON identical, 0 differences (`build/_p3_equiv_frozen.json`; manifest sha1
`a3da3371...` on both). The frozen first build from the empty cache: the same, except `report.json` `builder.stages.
*.cached` (`_p3_equiv_frozen_first.json`); its cache vs `build/_p1_cache`: 10,911 files (2.66 GB: P1 without movies,
P2, P3, all 295 banks) byte-identical, the reports equal but for time stamps. The XML2 install and `<the disc image folder>` were unchanged by all of it (14,231 files and folders, size + mtime; `build/_p3_ro_snapshot.py`).
The first comparison differed only in the builder's provenance (the commit as git's 7-digit short hash from source
vs 12 digits frozen; the manifest / stamp / verify-report time stamps): `resources.commit()` now gives 12 digits
from source too, and `build_equiv` drops the builder's `created` / `finished` / `verified`.

**CI** (`.github/workflows/`, for the public repo; actionlint 1.7.12 clean): `content-guard.yml`
(`tools/check_no_game_content.py` from the release draft: self-test, every tracked file, every blob a push / PR adds),
`tests.yml` (windows-latest + ubuntu-latest, CPython 3.14: `tests/unit/run.py` + `tools/build_sound_kernel.py`),
`release.yml` (windows-latest: requirements-freeze.txt, the tag = `v<VERSION>` check, optional bootloader from
source, unit tests, the kernel, `freeze_builder.py --smoke`, the smoke tests again on the zip unpacked with `tar.exe`,
artifact; on `v*` a separate `contents: write` job publishes the release). `tests/unit`: 52 tests.

## 28. Zone packages that carry a playable hero's power style (2026-09-29, Cyclops's empty power wheel)

**Symptom (Owen, first public play-through).** Cyclops joined at nyc1_1_3, the game was saved and loaded there, a
point went into Optic Beam - and the power wheel stayed empty for Cyclops (assigning the power changed nothing);
Wolverine's powers were fine. One zone later (nyc1_1_4) Cyclops had his power.

**Cause.** XML1's zone bundles precache a playable hero's power style for the zone's NPC copy of that hero:
`data/powerstyles/x1_ps_cyclops` in nyc1_1_2b, nyc1_1_3, mag_nyc3, mag_nyc4 and blackbird_arbiter, `x1_ps_gambit`
in sewers1_2_4, `x1_ps_colossus` in nuke2_2, `x1_ps_wolverine` in wx2_2 and blackbird_arbiter, `x1_ps_phoenix` /
`x1_ps_storm` in blackbird_arbiter. XML2 never does this (no retail zone package lists a hero's `ps_*`; its NPC
copies use NPC styles). XMen2.exe resolves a style's talent references when the style is registered (heroes.py
section: unregistered talentvalue -> literal 0, unknown `require` talent -> never satisfied), registers a style
once per zone load, and loads a *saved game's* zone package before the party's character packages. So in those
zones a load registers the hero's style with his talents unknown, his own package's `xml_talents` comes too late,
and his power slots bind nothing until the next zone. A join reload (character packages first) and a plain zone
transition don't hit it - which is why the earlier in-game join test passed.

**Fix (`zones.build_package`, `hero_of_style`).** When a zone package entry is a playable hero's style
(`data/powerstyles/x1_ps_<hero>`, hero in `heroes.hero_plan(ctx)['heroes']`), the package lists `xml_talents
data/talents/<hero>` immediately before it - the same rule heroes.py enforces inside character packages (XML2
retail: `xml_talents` before every fightstyle, 380/380). `Pkg.add` keeps one entry per file, so a hero already in
the party registers his talents once. Counts: `hero_talents_before_zone_style` (12 entries in 10 packages);
`zones_detail.json` `hero_style_zones`. CONTENT_VERSION 2 -> 3.

**Verified in game 2026-09-29 23:40 (build/_pwr, pipe pwr, scratchpad pwr_drive.py).** Cyclops seated first with
Wolverine in nyc1_1_3, a level with auto-spent points (two wheel slots filled), `savegame` through the Save menu
(saveslot0), then a FRESH XMen2.exe: main menu -> Load Game -> the slot -> nyc1_1_3: the wheel shows both powers.
Negative control on the same save: the zone's package re-encoded with the `xml_talents` line removed (the old
order) -> the same fresh load -> all four wheel slots EMPTY, Cyclops still level 5. Package restored afterwards.

**Open.** Whether the hero's talents registered by a zone package while he is *not* in the party count against
the engine's 100-talent registry (SPEC_heroes; blackbird_arbiter lists four heroes' styles) - to check in game with a
party that isn't those four. Owen also doubts Optic Beam's damage; measured separately.

## 29. XML1's weapon system as style triggers (2026-09-30, the HAARP flamers)

**Symptom (Owen, first public play-through, 0.1.1).** On Magma's rescue mission outside the X-Jet (haarp_ext01) the
HAARP flamethrower soldiers "don't say anything, I can't see the flame; they stood there then shot invisible flames
out that persisted, and I walked into them and died". In 0.1.1 every XML1 gun soldier (GRSO mp5 / laser /
lightning / nullifier / freeze / knockback / superlaser, the HAARP soldiers, the flamers, the pistol thugs) fired
blanks: no tracer, no sound, no damage.

**Cause (research/heroes/weapon_events.md, XMen2.exe addresses there).** XML1 arms an NPC through the stats
attribute `weapon="wp_..."` and `data/weapons/weapons.eng`: the record names the model, bolt, damage code, range,
muzzle / tracer / impact effects, fire / charge sounds, a continuous beam or a projectile entity, and the shared
combat event `weapon_fire` (= `ce_atk_weap`, Damage="L0" in shared_combat_events: a placeholder) takes all of it
from the weapon at fire time. XMen2.exe has none of that: its `ce_atk_weap` is the SOUND event class (factory
0x4fb550 -> the ce_sound constructor 0x4f9540), so a `weapon_fire` trigger plays nothing and hits nothing; the
stats `weapon` attribute is parsed and dropped (0x4ba373 -> 0x4bb2e7); `data/weapons/weapons.xmlb` ships empty;
none of XML1's weapon attribute names exist in the binary. Second cause, found in game: XML2's AI fires a
FightMove only when it carries `aitype` (the parser 0x4f6b80, 20-name table at 0x6db940; retail gun soldiers:
`aitype="beamanyrange" aireusetime="3" priority="5"`). XML1's NPC styles have no `aitype` - XML1's AI chose by
weapon - so even with real attack triggers the soldiers never fired: a flamer with `monster_aiforceranged` paced
around the hero for 15 s without a shot, two mp5 soldiers stood at point-blank range while the hero sat at 20 HP.

The "invisible flame that persisted" is a third thing: the zone's `fire_wall` entity (an `affectableharment`:
damage 3 dmg_fire + knockback 200 every 0.4 s, `loopfx="ambient/fire_wall"`), which the `create_firewall*`
scripts move to the spot the flamer plays `flame_sweep` at. Its harm worked in 0.1.1; its flame is the loop
effect - checked in game below.

**Fix.**

- `tools/xml1build/weapons.py` (new). Per (XML1 style, weapon) pair in use, a VARIANT style `x1_<style>_<weapon>`
  (`variant_name`): the XML1 style with every `weapon_fire` trigger of every FightMove replaced by the weapon's own
  triggers (`apply`): bullet / beam -> a `beam` trigger (ce_atk_beam, one-call hit-scan: `beambolt`=actorbolt,
  `beameffect`=muzzleaccfx (the tracer), `hiteffect`=impactfx, `damage`=the weapon's code, `damagetype`,
  `maxrange`=range, `damagescale="difficulty"`, `damagelevel="0"` (issue #51), `<damageMod name=damagemod>`) plus one
  `effect_sound` (muzzlefx + firesound on the bolt); flame -> the ps_pyro `flame_dmg` form (`noaimfx`,
  `useboltinfo`, `pierce`, `beameffect`=flame_shot) keeping the original trigger's tag (150: ch_constantbeam
  fires it every `timeinterval`, which `apply` sets to 0.1 s on the `setbeam="true"` beamdata trigger) and a
  tag-100 `sound` the engine loops while the beam is on; projectile (freeze / knockback guns) -> a `projectile`
  trigger (ce_atk_spawn_proj: `entity`=projectileent, `filename`=entfile, `speed`, `count="1"`, `targetable`)
  with the attack data; `chargefx` / `chargesound` `warmuptime` before the first shot (never before 0). A move
  keeps at most 19 triggers (0x4f6aa7): a 7-shot burst gets its muzzle `effect_sound` on every other shot. Every
  move that got weapon triggers and has no `aitype` gets XML2's retail AI marking (`AI_TYPE` / `AI_REUSE`:
  bullets and beams `beamanyrange` 3 s, projectiles `projectile` 2.5 s, the flame `projectilenear` 4 s, and
  `priority="5"` when absent). Value codes stay codes (L1..L5, K10): `npc_values.resolve_style` turns them into
  XML1's numbers (section 24; L1 -> "4 5", L3 -> "15 18"), and `_data_patch` resolves them in the two projectile
  entity files (`data/entities/freezegun_ents` ice_bullet L3, `knockbackgun_ents` bullet_time K10).
- `characters.py`: `weapon_style()` imports the XML1 style under `Data/powerstyles/<variant>` with `W.apply` as the
  patch (patch key `<style>.weapon.<weapon>`); `convert_stats` points a stats entry whose weapon is a bullet /
  beam / flame / projectile weapon at the variant (melee weapons change nothing); the character package follows
  the stats entry. Counts `weapon_styles_written`, `weapon_styles_used`.
- `validate.py` V5 (namespace): a `powerstyle` on an entry with an XML1 `weapon` must be the variant name.
- Variants built: x1_ps_grso_{mp5, laser_gun, lightning_gun, m_nullifier, freeze_gun, knockback_gun,
  superlaser_gun}, x1_ps_flamethrower_flamethrower, x1_ps_pistol_pistol. `tests/unit/test_weapons.py` (9 tests).
  CONTENT_VERSION 3 -> 4; builder 0.1.2.

**Verified in game 2026-09-30 evening (build/_wpn with the variants patched in place, a VULNERABLE Wolverine: no
`setInvulnerable` in the process; scratchpad wpn/, research/regression/weapon_damage_driver.py).** haarp_ext01: the
flamer spawned with `act("ss_haarpsoldier_flamethrower01", ..)` next to the hero fires `power_attack` every ~4 s
(aireusetime 4): the damage numbers 18 and 17 float over Wolverine (L3 = "15 18"), the health bar drops 19 px of
137 per hit, the flame_shot fireball draws at the muzzle. haarp_ext04: the instantspawn mp5 soldiers (beamanyrange)
hit for 4-5 (one measured 6-px drop) and killed the hero in under 8 s when he was teleported among them. Before the
`aitype` change, with the same triggers, neither fired (flamer pacing 15 s, mp5 soldiers idle at point-blank with
the hero at 20 HP). Not reached in game: the freeze and knockback guns (projectile; their zones' spawners are
instantspawn without monster names, so neither teleport nor act finds them), lightning / laser / nullifier (same
beam mechanism as the mp5, different effects). The `fire_wall` harm entity's loop effect is still unchecked.

### 29.1 Styles named by a stats entry must be listed by its packages (2026-10-01, the missing power wheels)

**Symptom (Owen, 0.1.2, the HAARP exterior with Magma, Jean, Iceman and Wolverine).** The bottom and left heroes'
power wheel would not open at all (holding the power key did nothing); the top and right heroes' opened. Reproduced
in build/_wpn with the same four (scratchpad wheel_seats.py: seatParty, loadMapKeepTeam haarp_ext01, UP / RIGHT /
DOWN / LEFT then the power key): seats 3 and 4 have no wheel, with a 3-hero party seat 3 has none, with 2 both
work; the same party in nyc1_1_1 has all four; haarp_ext01 on 0.1.1 content (build/_pwr) has all four; the flamer
need not spawn (the zone load alone does it).

**Cause.** 0.1.2 pointed the HAARP soldiers' stats entries at the weapon variants (x1_ps_grso_mp5,
x1_ps_flamethrower_flamethrower) but their character packages, built from XML1's bundles, still listed the base
styles (ps_grso, ps_flamethrower), as did the zone package. The engine loaded the variants on demand when the
zone's instantspawn soldiers appeared, and a power style loaded outside the packages breaks the power registration
of the heroes seated after it (the mechanism in the exe is not traced; the fix below is proven by the control).

**Fix.** `characters.swap_variant_style`: every character package (bundle, synthesized, `_xml`) of a stats entry
that uses a weapon variant lists the variant where the bundle listed the base (`variant_base` from
`weapon_style`; count `package_styles_to_variant`). `zones.weapon_variant_entries` (characters publishes
`ctx.shared['weapon_variant_base']` and `stats_powerstyle`): a zone package's `data/powerstyles/<base>` becomes the
variants the zone's .chr characters use, the base kept only when a character still uses it (counts
`zone_style_variants`, `zone_base_styles_replaced`). Validator V4: a zone package listing a weapon-variant base that
none of its characters uses, or a character package whose power styles do not include its stats entry's, is an
error (77 on the 0.1.2 play build, 0 on the fixed one). `tests/unit/test_zone_packages.py`. CONTENT_VERSION 4 -> 5,
builder 0.1.3.

**Verified in game 2026-10-01.** build/_wpn with the three HAARP packages patched by hand to the variants: all
four wheels (Magma, Jean, Wolverine, Iceman) in haarp_ext01. build/_w3 (the builder's own output, harness pipe
w3): the same four-seat check - see the sheet wheel/sheet_w3fix.png in the session scratchpad.

### 29.2 Entity value codes and generated weapon-style packages (compatibility audit)

Two cross-module defects remained after 29.1. `characters._data_patch` resolved XML1 codes in
`data/entities/*`, but `zones._data_patch` did not. The latter compares its freshly converted source
against a previous importer and takes ownership when they differ. It therefore restored `L3`, `L4`,
and `K10` in the shipped freeze/knockback entity files. XMen2.exe does not resolve those names
(section 24; the projectile parser uses the same value resolver, weapon_events.md section 4).
Both importers now call `npc_values.resolve_entity_codes`. Unknown codes report a build error.
V19 checks the final registered entity files as well as styles, including single and multiple XMLB roots.

`characters.style_packages` also used the original bundle unchanged for weapon variants. All nine
variant packages named the original style internally, even though the character and zone packages
had been corrected in 29.1. `weapons.bind_style_package` changes only the source style's self-reference;
other styles, effects and entity dependencies keep their order. It inserts the variant's XML entry if
an asset-only bundle omits the source style. V4 checks the self-reference of generated style packages.

The generated projectile trigger now explicitly sets `attacktype="projectile"`. The shared event's
`ce_atk_spawn_proj` selects the spawn implementation but does not override the attack-data parser's
`punch` default (weapon_events.md sections 2 and 4). The projectile's event/entity damage precedence
still needs an in-game comparison; resolving both records does not establish which wins on contact.

Regression tests use synthetic data: the character and zone entity patches must produce identical
bytes; generated variant packages must load their own style with dependencies preserved; validators
reject the former output. CONTENT_VERSION 5 -> 6; release version left unchanged pending review.

Validation of the review branch: 78 synthetic tests pass; a full no-movies build and a subsequent rebuild
both validate with zero errors (existing warnings retained). Compared with the 0.1.3 play build, the final
output has zero unresolved entity codes instead of 24 across nine files: freeze/knockback weapons, grenades,
Magma, missile launchers, Mystique, Pyro, Sentinel grenades, and Shades. All nine weapon-variant packages
now load their own style. Both projectile variants explicitly carry the projectile attack category.
This is final-file validation, not a claim that projectile contact behavior has been playtested.

### 29.3 Weapon events a style names itself: Mystique's pistols (issue #52)

**Symptom (tester, builder 0.1.7).** In the first level (nyc/alison/nyc1_1_2b) Mystique's pistol attacks showed no
bullets and did no damage.

**Cause.** Section 29 rewrites only triggers literally named `weapon_fire`, and only in the variant styles of stats
entries that carry a weapon. XML1's ps_mystique arms itself instead: two style events `left_gun` / `right_gun`
inherit `weapon_fire` and name `weapon="wp_myst_pistol"` (the left one also `boltselect="Bip01 L Hand"`); her stats
have no weapon. The 16 triggers of her two gun moves name those events, so in XMen2.exe every one resolved to the
sound class (`ce_atk_weap`, section 29) and did nothing. No other XML1 style does this (ps_mastermold_two's gun events
already inherit `beam`).

**Fix.** `weapons.rewrite_weapon_events`, called by `characters._style_patch` on every converted style before the
references are mapped: an `<event>` (root or move level) whose inherit chain reaches `weapon_fire` and names a
bullet / beam weapon becomes a `beam` event with that weapon's data, exactly as `shot_triggers` builds a shot
(`beambolt` = the event's `boltselect`, else the weapon's `actorbolt`; tracer, impact, damage code, range,
`damageMod`). Event names stay, so no move gains a trigger for its shots; the weapon's muzzle flash + fire sound
(`effect_sound`) go on the first shots of a move while it stays within 19 triggers (both of her gun moves have 17:
the first left and the first right shot get them). Projectile / flame weapons named this way are counted and left
(none on the disc). Count `weapon_events_to_beam` (2), report `detail['weapon_events']`.

Validator (in V5): a stats entry's power style must not fire `weapon_fire` - through an event naming a weapon,
or by name when the entry's XML1 weapon is a gun (error); a melee weapon is a warning (NukeGuardMelee: ps_grso with
wp_baton, what XML1 did is not established); no weapon is allowlisted. On the unfixed output it reports Mystique's
16 triggers (weapon_fire_left run offline on the main build's x1_ps_mystique, the style of MystiqueAct1 / Act2sim / Act3).

**Verified in game (build of this branch vs main, harness pipe, Wolverine standing still, HP read through the test
pipe every ~0.1 s, 60 s each, nyc1_1_2b: spawner acted, mystique_fight_start, myst_wp_none).** Main: 7 HP drops, all
9.3-11.0 (her grenade, below); no 4-5 hits. This branch: muzzle flashes alternate between her two hands, tracers run
to Wolverine with impact sparks and floating "5"s; 8 single hits of 4.2-4.6 (XML1's L1 = 4-5) plus 3 drops of
9.2-10.2. Fewer hits than shots (6 per power_attack burst): not every shot of a burst connects, and hits closer
together than a sample merge.

**Her grenade (the same report: "showed its area and had no effect") is not reproduced.** On main, a standing
Wolverine took 9.3-11.0 per explosion (7 in 60 s; the explosion and a floating "11" are in the frame), which is the
spawn trigger's damage (L2 = 9-11, `usedamageasexplodeonly`). Neither research hypothesis (only the death effect
plays; the attack data filters heroes) holds for a hero inside the radius (52). A hero who moves away from the
landing spot is not hurt, as in XML1. Nothing changed.

---------------------------------------------------------------------------------------------------------------

## 30. XML1's inline NPC immunity talents as shared powerup talents (2026-10-01, combat audit G1)

### 30.1 The gap

XML1 defines most of its NPC-only talents inline on the npcstat entry, not in shared_talents:
`<Talent name="blob_special" level="1"><level><activepowerup powerup="def_stun" affect_type="scale" level="0"
life="-1"/>...</level></Talent>` (xml1_loose/data/npcstat.eng: 53 inline trees on 48 entries, 31 names). Their
bodies are the boss immunities: `def_stun` / `def_knockback` / `def_pain` / `def_critical` / `def_damage` with
`affect_type="scale" level="0"` (immune), `def_grab` / `def_finisher` / `def_reflect_pain` (flags),
`def_mind_control` scale 0.1 or 0.01, `no_iceshell` scale 0, and `def_damage scope_damage="dmg_physical"` scale
0.5 (the Morlock bruisers' 50 % physical resistance). characters dropped the `<level>` trees and kept only the
reference (`convert_stats`, "inline XML1 definition; kept as a reference"), `ensure_talent` then wrote an empty
shared definition for each name, and heroes pruned those as "empty NPC definition (references removed)" with
the references (DESIGN D8 / 4.7 took the names for empty XML2 definitions; XML2's shared_talents has none of the
24 names - only `dr_stun` and `sentinel_special`). Result in content 6: every XML1 boss and elite could be
stunned, knocked down, grabbed and thrown, finished, mind-controlled, frozen in Iceman's shell and criticalled
like a common enemy (research/audit/xml1_combat_gaps_2026-10-01.md 2.1).

### 30.2 The engine form

XMen2.exe's affecter table 0x6ddb18 has every attribute the bodies use (combat_events.AFFECTERS: def_damage 39,
def_knockback 40, def_stun 41, def_pain 42, def_critical 43, def_pickup 44, def_grab 45, def_reflect_pain 46,
def_finisher 47, def_mind_control 50, no_iceshell 81, slow_immune 85), and XML2 ships the same idea as a shared
talent: `boss_resistances` = `<talent><level><powerup life="-1"><affecter affect_type="scale" attribute="def_stun"
level="0"/><affecter attribute="def_grab"/>...</powerup></level></talent>`, referenced as `<talent level="1"
name="boss_resistances"/>` by XML2's bosses. The HUD's "Physical Resistant" / "Mental Resistant" text under a
boss bar is XML2's own display of such affecters registering.

### 30.3 What the builder does (`npc_values`, `characters`, `heroes`)

- `npc_values.immunity_rows(<Talent>)` classifies one inline tree: exactly one `<level>`, every `activepowerup` a
  permanent (`life="-1"`) `IMMUNITY_AFFECTERS` affecter; a `powerup="none"` row (an XML1 code callback such as
  MultipleManDividing's `func_hurt="MultipleMan_Hurt"`) and attributes outside powerup / affect_type / level /
  scope_damage are reported losses, not disqualifications. Anything else (the five `profx_*` trees of
  profxgladiator, a timed powerup) is not an immunity and keeps today's path.
- `npc_values.immunity_plan(npcstat)` censuses the bodies (a body = its rows as a multiset; the order of the
  affecters inside one talent does not matter) and names each body after the XML1 talent name most entries used,
  ties alphabetical; names XML2's shared_talents defines (`dr_stun`, `sentinel_special`) are excluded and keep
  XML2's definition (XML2's `sentinel_special` adds `no_iceshell`). XML1's 20 inline bodies give **14 distinct
  immunity bodies** (14 names, not the audit's 26: 4 names share the standard boss body, 6 share the bot body,
  2 the Shadow King body, and `multipleman_special` minus its callback row equals `sabre_special`):

  | shared talent | XML1 names (entries) | affecters |
  |---|---|---|
  | `avalanche_special` | avalanche_special (4), mystique_special (3), marrow_special (2), pyro_special (2 incl. Vulcan) | def_knockback 0, def_pain 0, def_stun 0, def_mind_control 0.1, def_grab, def_finisher |
  | `as_special` | as_special, pod_special, shocker_special, spidermine_special, stealth_special, suicide_special (1 each) | the above minus def_mind_control, plus no_iceshell 0 |
  | `toad_special` | toad_special (ToadAct1) | avalanche_special's plus no_iceshell 0 |
  | `magnetoboss_special` | magnetoboss_special (MagnetoBoss) | toad_special's with def_mind_control 0.01 |
  | `blob_special` | blob_special (4) | def_knockback 0, def_stun 0, def_mind_control 0.1 |
  | `juggernaut_special` | juggernaut_special (3) | blob_special's plus def_critical 0 |
  | `sabretooth_special` | sabretooth_special (3) | def_knockback 0, def_pain 0, def_mind_control 0.1, def_grab, def_finisher |
  | `sabre_special` | sabre_special (SabretoothAct2 / Act3), multipleman_special (MultipleManDividing) | def_mind_control 0.1 |
  | `mastermold_special` | mastermold_special | def_pain 0, def_stun 0, def_mind_control 0.01, def_finisher |
  | `havok_special` | havok_special (HavokBoss) | def_damage dmg_energy 0, def_stun 0, def_mind_control 0.1 |
  | `shadow_special` | shadow_special (shadowking), shadow_special2 (shadowkingtwo) | def_pain 0, def_stun 0, def_grab, def_finisher |
  | `physical_res` | physical_res (MorlockBruiserB / C) | def_damage dmg_physical 0.5 |
  | `forge_special` | forge_special (Forge) | def_grab |
  | `sentspider_special` | sentspider_special (SentinelSpider, _b) | def_finisher |

- `characters.convert_stats`: an inline tree whose body is in the plan becomes `<talent name="<body talent>"
  level="1"/>` on the entry (`immunity_name`; the definition `npc_values.immunity_talent` is appended to both
  shared_talents roots on first use, replacing any empty one; a second XML1 name of the same body on one entry is
  dropped as a duplicate reference - none today). 41 references on 39 converted entries (SabretoothAct2 / Act3
  carry two; the 7 dr_stun / sentinel_special trees keep XML2's definitions); 14 of them are renamed to the
  body's talent, 10 distinct (XML1 name, talent) pairs (`characters_detail.json` `npc_immunities.renamed`; e.g.
  PyroAct1 names `avalanche_special`, MultipleManDividing `sabre_special`, the bots `as_special`). The
  definition is `<talent name=N><level><powerup life="-1"><affecter [affect_type="scale"] attribute=A [level=L]
  [scope_damage=D]/>...</powerup></level></talent>`, the rows in XML1's order; rebuilt from XML2's own
  `boss_resistances` rows the function reproduces that definition byte for byte (tests/unit/test_npc_immunities).
- `heroes.shared_keep`: a current shared talent named by a stats entry, not an XML2 definition, in the immunity
  form (`npc_values.is_immunity_talent`: one level, one permanent class-less powerup, only immunity affecters, no
  talentvalues) is kept ("XML1 NPC immunity body (npc_values, SPEC 30) named by a stats entry");
  `SHARED_KEEP_EXPECTED` gains the 14 names (`SHARED_KEEP_IMMUNITIES`).
- Validator V19 (`npc_values.v19_immunities`): for every npcstat / herostat entry whose XML1 source carried an
  inline immunity body (names XML2 defines excluded), the built entry names a shared talent whose definition has
  the same rows (any name); an immunity-form shared talent no stats entry names is a warning (a pool slot for
  nothing). Counts `npc_immunity_entries` / `npc_immunity_refs` / `npc_immunity_talents`.

### 30.4 Budget (SPEC_heroes 6, DESIGN 6.2)

shared_talents 47 -> **61**; registered talents, worst party 61 + (8 + 7 + 7 + 7) = **90** of 100, under the
heroes validator's 92 (100 minus the 8-talent Danger Room margin), so no body was merged or dropped. Merging the
four bodies that are subsets of XML2's `boss_resistances` into references to it (4 slots) stays available if a
later section needs the room; it would add `def_pickup`, `slow_immune` and, for `avalanche_special` /
`sabretooth_special`, `no_iceshell` that XML1 did not give those bosses.

### 30.5 Lost and left different

- MultipleManDividing's `func_hurt="MultipleMan_Hurt"` (the dividing-on-hit callback) has no XML2 form; the
  entry keeps its mind-control resistance only (reported as a deferred item).
- SabretoothAct2 / Act3 carry both `sabretooth_special` and `sabre_special` (def_mind_control 0.1 twice), as in
  XML1; whether XMen2.exe multiplies the two scales (0.01) or takes one is not established - XML1 had the same
  pair, so the port is faithful either way.
- `sentinel_special` keeps XML2's definition (XML1's level-1 body is def_stun 0 twice; XML2's adds no_iceshell 0).
- Validation: 83 synthetic unit tests pass; the build's validators report 0 errors; the output diff against the
  content-6 build is npcstat (48 references), shared_talents (14 definitions) and the build reports only.
  In-game evidence: section 30.6.

### 30.6 In-game check (2026-10-01, research/regression/spec30_pyro)

Subject: PyroAct1 in haarp/int/haarp2_6 (spawner `sp_pyroact01`, monster `pyro`; XML1 body `pyro_special` ->
`avalanche_special`: def_knockback 0, def_pain 0, def_stun 0, def_mind_control 0.1, def_grab, def_finisher; no
heaviness, so a normal-size knockback subject - Blob and Juggernaut carry `heaviness`, which attenuates knockback
by itself). `immunity_driver.py <build> <tag>`: new game, `seatParty("wolverine","colossus","cyclops","iceman")`,
`loadMapKeepTeam`, `act` the spawner, `setAIActive("pyro","FALSE")` (XMen2.exe 0x4a50f0, so he neither attacks
nor evades), then 10 times: `copyOriginAndAngles("pyro","_HERO1_")`, Wolverine's smash (NUMPAD6), frames at
0.15 / 0.3 / 0.5 / 0.8 s, centre crops. Same script, both builds, Wolverine active in both runs.

- **build/_w4 (content 6, no immunity talents)** `before_w4_pyro_smash.jpg`: landed smashes (red hit flash, "18",
  "3", "11", "18/14") launch Pyro into the air (smashes 2 and 3: airborne above Wolverine at 0.5 s, out of the
  crop at 0.8 s) or floor him (smashes 4, 5, 6: lying / getting up at 0.5-0.8 s): at least 6 of 10 smashes
  launched or floored him.
- **build/_t1b (with the talents)** `after_t1b_pyro_smash.jpg`: the same smashes land (hit flashes, "29", "19")
  and Pyro stays on his feet next to Wolverine in all 10 x 4 frames; never airborne, never on the floor.
- Not established by this run: the pain flinch (def_pain 0; he twists slightly on some hits, within the smash's
  push), def_stun / def_grab / def_finisher / def_mind_control, and the other 13 bodies. Iceman's AI froze Pyro
  in an ice shell in both builds (frame row 9 of each sheet): PyroAct1's XML1 body has no `no_iceshell`, so that
  is XML1-faithful; Toad / Magneto / the bots (no_iceshell 0) were not tested.
- An earlier attempt with Pyro's AI on was ambiguous (he evades and runs; the floor frames had no hit flash);
  a run where Wolverine had died earlier (Iceman active, Pyro teleported to the dead slot) was discarded.

## 31. XML1's ce_renderfx tint form -> XML2's cloak (2026-10-01, audit G5)

XMen2.exe's ce_renderfx parser (CCERenderFx vtable 0x692770 slot 4 = 0x4e94e0) reads `add` and `remove`, each a
name of the renderfx table 0x6d7bd8 (`none`, `pain1`, `pain2`, `chilled`, `metalfreeze`, `radiation`, `radiated`,
`fading`, `xtreme_fb`, `cloaked`, `bleeding`, `burning`) OR-ed into a mask, then the base `time` / `tag`. XML1 tinted
the actor instead (`tint`, `solid`, `alpha` flags and an `rgba` colour; `remove="true"` to end it). The parser
reads none of those (`solid` and `rgba` are not even XMen2.exe strings), so the 12 triggers in 6 styles did nothing: ps_grsoelite (power_boost cloak: tintout `rgba="0 0 0 0.5"` / tintin), ps_acolyte_mental,
ps_acolyte_mental_b, ps_bh_mental, ps_mp_mental (the systemshock tint), ps_mystique (steal_form / transform_end).

`x1schema.convert_renderfx` (style files, after section 33): a `ce_renderfx` trigger or event with any of `tint` /
`solid` / `alpha` / `rgba` and no `add` / `remove` name gets `add="cloaked"`; one with `remove="true"` gets
`remove="cloaked"`; the four XML1 attributes go; everything else (`time`, `tag`, `life`) stays. This is XML2's own
conversion of the same triggers: XML2 retail's `tintout` / `tintin` are `add="cloaked"` / `remove="cloaked"`
(e.g. ps_deadpool). XML1's colours are not reproduced (the renderfx table has no tint colour); Mystique's opaque
purple morph tint (`rgba="0.1 0 0.2 1"`) becomes the translucent cloak like the others. Idempotent; counts
`renderfx:add` / `renderfx:remove`; `x1schema.renderfx_x1_elements` lists what is left (nothing after a build).
Tests: `tests/unit/test_xml1_data_fixes.py` (the two forms, a mixed-case form, an XML2-form trigger untouched,
idempotent, through `convert`). In game: not checked (no cheap cloaking enemy: the GRSO elite is act 7, the mental
Acolytes later); the build output diff shows exactly these 12 triggers changed.

## 32. The SKILL pickup: one skill point to the hero who takes it, through xml2-fix (2026-10-01, audit W2; 1.3.0)

XML1's `SKILL` item (`data/items.eng` type `skill`; pickups in haarp_ext03, sewers3_1_3, hive2_2_4) gave one free
skill point to the hero who picked it up. The port's first stand-in, `awardXPToPlayable(5000)`, was the roster award
(0x49d9d0 -> 0x449fe0: every herostat hero, the bench included): seen in game, eleven heroes went from level 1 to 9
on XML1's curve from one pickup at haarp_ext03. Its second (content 7, this section's first form) gave the picker one
level step of XP (`SKILL_<xp>` items sized to the zone's world level), a level and its stat points rather than a point.

**What the engine has.** XMen2.exe's 308 script functions (`research/scripts/api_diff.txt`, table 0x68a908) have no
call that grants a skill point (`setXP`, `awardXPToPlayable`, `permanentStatBoost`; `levelUp` is XML1-only). Its
"points to spend" test 0x4b7b00 (on a hero's stats) is: nothing for an xpexempt hero (bit 0x20 of CStats+0x2ad); else
the two words of the saved block at CStats+4 - the **unspent skill points** at block+0x14 (CStats+0x18; read by
0x544a30, written by 0x43a5b0 when the stats have talents, block+0xb8 > 0) and the unspent attribute points at
block+0x16 (0x544a40 / 0x43a3f0) - summed above 0, or levels the hero hasn't been given their points for yet (the level
byte CStats+0x1c past the XP object's processed count, CStats+0xc0 vt+0x14 = 0x5f5ff0). Each level processed gives one
skill point and four attribute points (the autospend 0x4bbae0 at 0x4bbb54-0x4bbb75: +1 to the word at +0x14, +4 to the
one at +0x16); the skills screen spends from the word at +0x14 (0x5e5dff -> 0x43a5b0); the block is saved with the
hero (0x43a520), so a point granted keeps across a save.

**The fix (xml2-fix 1.3.0, `addSkillPoints(name, n)`; forced_teams_rules.hpp / forced_teams.cpp in the xml2-fix
repository).** Registered with the forced-teams functions (the ninth entry of the DLL's copy of the function table,
`n(ai)` like `setXP`; it works whatever `[Game] ForcedTeams` says, and `xml2fixFeature("skillpoints")` reports 1 when it
is there). It resolves the name as `setXP` does (0x4a8660: 0x4a7e30 lists the entities the name means - a named
entity, `_ACTIVE_HERO_`, `_HERO1_`.., `_ALL_HEROES_`; the script compiler has turned an item's `_ACTIVATOR_` into the
activator's name by then), keeps the ones with the stats class bit (bit [0x70b840]+0x24 of the class info, setXP's
test) and a stats object at entity+0x35c, and adds n (1..20) to each one's word through the game's own getter and
setter; nothing else changes (no XP, no level, no popup). Every call is logged with before / after per hero.

**The data (this builder).** The `SKILL` item keeps XML1's name, model and texts (`items_to_add` -> `translate_item`,
`ITEM_TYPE_MAP['skill']`): type `item`, `activateonpickup`, `onactivate="addSkillPoints('_ACTIVATOR_',1)"`
(`zones.SKILL_PICKUP_SCRIPT`). The pickup entities are left as XML1 wrote them (`inventoryitem="skill"`, count 1);
the `SKILL_<xp>` items, `zones.rewrite_skill_pickups` and `level_step_xp` are gone. The call is an xml2-fix name in
data: `common.XML2FIX_ALWAYS_FUNCS` merges it into the script API of every build (seat or menu), and validate V14a
lets data call the names in `scripts_transform.XML2FIX_DATA_FUNCS` (V14b's guard rule stays for the forced-teams
calls). **No fallback:** an inline `onactivate` is one statement, and a second statement would run as well as the
call, not instead of it; without the DLL, or with one before 1.3.0, the engine drops the unknown call at compile and the
pickup gives nothing (the entity still vanishes with its sound and effect). The port's manifest requires xml2-fix
`>= fix_ini.REQUIRED_XML2FIX` = 1.3.0, which the launcher enforces; the harness copies the DLL it is given.

Checks: `zones_selftest` J2 (each built SKILL pickup names XML1's `SKILL`, whose `onactivate` is the call and
`activateonpickup` true; no skill item awards the roster) and J3 (32.1, unchanged: the pickup items load before the
equipment). Tests: `tests/unit/test_xml1_data_fixes.py` (the item and its call on both curves, the API merge, the
item order of 32.1). In game: 32.2.

### 32.1 Engine limit: the item table's enhancement pool (found by this section's in-game check)

The first SKILL_<xp> build put the three items at the end of `Data/items`, and in game the haarp_ext03 pickup was
gone (not drawn; the entity removed at spawn). XMen2.exe's item loader (0x480400..0x4805c5) gives every
`<enhancement>` of the table - the prefix / suffix / tr_item affixes first, then the items in file order - a record
from a fixed pool of 375 (`0x4804a6 cmp [mgr+0x6064], 0x177; jge 0x4806cc`); the first enhancement past it aborts the
whole load, so that item and every later one are never registered (read in the running game: item manager [0x72a514]
count 65, enhancement counter 375; none of the later names reached the string pool), and an `inventoryent` naming one
of them is removed when it spawns (0x47a9b4 -> vt+0xbc). XML2 retail uses 374 (prefixes 85, suffixes 79, tr_item 95,
items 115), so the first XML1 equipment item with two enhancements overflows it.

**xml2-fix 1.3.0 (`[Limits] ItemEnhancements`, SPEC 32.3 on the items-limit branch has the save-format evidence):** the fix
grows the pool - the records and their bitmap move to the end of a bigger item manager, 41 instructions and one
cloned bit scan carry the new size, nothing already numbered moves - and the port's ini asks for 512
(`fix_ini.LIMITS['ItemEnhancements']`). `zones.ITEM_ENHANCEMENT_POOL` reads that value, so the warning below and J3
are measured against the pool the shipped ini asks the fix for: with the fix all 88 items (410 enhancements) load;
an install without the fix, or with one before 1.3.0, keeps XMen2.exe's 375 and the cut-off below. In game
(build/_fix130, the 1.3.0 DLL, `ItemEnhancements=512`): see 34.3.

**Pre-existing consequence (content 6, fixed by the fix above):** the load stops at `VISOR_OF_RETRIBUTION`, so 19 of the 20
XML1 items after it never load: 18 of the 19 Danger Room reward items (section 21.3; VISOR_OF_RETRIBUTION ..
SHIAR_ENERGY_ARMOR), `ASTRAL_STONE` and the two `XP_<count>` pickups of section 23.1 (`XP_30000` wx2_1, `XP_300000`
hive2_2_4), whose entities were therefore removed in game. **Fix for the pickups (this section):** `zones.items_to_add`
orders the XML1 items it appends without enhancements first (stable), so `SKILL`, `XP_*`, `ASTRAL_STONE` and the
other plain items load before the equipment cuts the load off. The Danger Room rewards stay cut off (a data fix needs
fewer enhancements: e.g. one enhancement per reward, or dropping XML2's unused random-affix entries; an exe fix
raises the pool); zones warns with the list (`items_beyond_enhancement_pool`, `zones.enhancement_pool_cut`), and
`zones_selftest` J3 fails if a SKILL / XP pickup item lies past the overflow. Why no data-only fix: 32.3.

### 32.2 In game

**xml2-fix 1.3.0 form (build/_fix130, harness pipe f130, save folder "X-Men Legends (f130 tests)"):** see the
in-game notes at the end of section 34 (the same run): `tools/skill_points.py` reads every hero's unspent skill and
attribute points (the words at CStats+0x18 / +0x1a) before and after.

**Content 7 form (one level step of XP; build/_t1a, harness pipe t1a):** haarp_ext03 with Wolverine and Cyclops
seated, every hero first set to XML1 level 6 (`awardXPToPlayable(1320)` = T1(6)), then Wolverine put on the pickup
(`tools/hero_xp.py` before and after): Wolverine 1,320 XP level 6 -> 2,070 XP level 7 (the HUD shows 7); Cyclops (in
the party) and the 13 benched heroes stay at 1,320 / level 6. The same steps on the build without sections 31-33:
every non-exempt hero 1,320 -> 6,320 XP, level 6 -> 9.

### 32.3 Why the rewards cannot be fitted by data alone: saves store enhancement record numbers (2026-10-01)

**What the 374 are.** XML2 retail's `Data/items`: `prefixes` 85, `suffixes` 79, `tr_item` 95, the 27 standard /
advanced / legend belts, gloves and armor (1 each; records 259-285), 15 hero uniques with `enemy_level -1`
(`ACCELERATED_VISOR` .. `WPN_X_FISTS`, item defs 40-54, records 286-339; XML2's Danger Room rewards, named only by
XML2's `Data/dangerroom`, so unwinnable with `--frontend xml1`) and 9 drop uniques with `enemy_level` 25-35
(`APOC_BANE` .. `XAVIER_DREAM`, defs 55-63, records 340-373; named by nothing but the items table, so random drops).

**The save format.** The item manager's save (0x47c4c0) writes, per item definition (up to 160, 0x480430), its count
byte (+0x39) and a flag bit (+0x3b), then every item instance (the gear bag; a hero's equipped slots go through
0x4b8570 -> the same instance save): instance save 0x481610 / load 0x482b40 = definition index (byte, manager
vt+0x7c / vt+0x18), 4 bytes (+0x2c, +0x2d, +0x2f, +0x2e), then three lists (+8, +0x10, +0x18), each a dword count
and per element the **enhancement record index** (u16) + a dword (element class vtable 0x6865ac, save 0x45e4e0,
load 0x482ad0 -> 0x481910 -> vt+0x2c 0x45e510; the record is looked up by index, manager vt+0x10 0x47bad0). List
+0x10 is the definition's own enhancements (0x481a10 copies the definition's up to 8 record indices, def+0x24),
+8 / +0x18 the random affixes (manager vt+0x108 / vt+0x10c). So a saved drop unique names its own records.

**Measured** (item manager in the running game, def+0x24 record indices): content 7 (`build/_t15`) `APOC_BANE` (def
55) = records 340-345, `XAVIER_DREAM` (def 63) = 371-373; with the 15 hero uniques' 54 enhancements stripped (branch
items-limit c81d220, reverted) `APOC_BANE` = 286-291, `XAVIER_DREAM` = 317-319, and 340-355 belong to the XML1
rewards. A content 7 save holding a drop unique would load it with an XML1 reward's bonuses (or none: records past
355 do not exist then). Stripping or removing anything before record 374 renumbers saved records; the definition
order is saved too (by index), so items cannot be reordered either.

**What fits without renumbering:** only records 286-339 (owned by whatever sits at definitions 40-54, which no save
holds) and record 374. Putting XML1 rewards at definitions 40-54, padded to exactly 54 enhancements, plus one
single-enhancement reward at the end, loads 16 of the 19 rewards; the 22 padding enhancements would show in the gear
screen (unverified) and 3 rewards still miss. **So the full fix is an xml2-fix patch of the pool** (0x4804a6
`cmp eax, 0x177`; the 375 records of 0x28 bytes at mgr+0x2594, its allocation bitmap at mgr+0x602c, the counter at
mgr+0x6064, the lookup bound in 0x47bad0, the manager allocated 0x7a00 bytes at 0x480a21) - noted for the fix
maintainer; the record numbers of saves stay valid when the pool only grows. Until then the build warns
`items_beyond_enhancement_pool` (18 rewards). Note also def+0x24's sentinel: 0x47ad10 reads a stored record 0xff as
"none", so record 255 can never be an item's own enhancement.

## 33. XML1's shared combat event values on the XML1 styles (2026-10-01, audit G3)

Found offline (`research/audit/xml1_combat_gaps_2026-10-01.md` G3): the build ships XML2's
`Data/shared_combat_events` byte for byte (section 4.4), and XML1's styles inherit from it by name (section 22.1),
so an XML1 event or trigger that leaves an attribute to its shared parent got XML2's number: an XML1 punch did
XML2's "2 3" instead of XML1's L1 = 4-5, a heavy punch "3 5" instead of L2 = 9-11.

### 33.1 Rewrite (`combat_events.apply_x1_shared_values`, run by `x1schema.convert` after `rewrite_style`)

`X1_SHARED_EVENT_VALUES` lists every XML1 shared event whose XML1 value differs from the shipped XML2 event, with
XML1's value: `damage` L1 for `punch`, `kick`, `teleport_punch`; L2 for `punch_heavy`, `kick_heavy`, `move_damage`;
L3 for `punch_veryheavy`, `kick_veryheavy`; L4 for `beam`, `fry`, `suspend`; and XML1's `dmgmod_auto_knockback` on
`throw` (XML1: `Damage="0"` plus that damageMod; a child inherits its parent's damageMods as bits, 0x4dce80).
On every XML1 style tree (characters' imports, heroes before the collapse, zones' `shared_nodes` merge: the
section 22.3 entry points), each `<event>` / `<trigger>` that names one of those events directly (`inherit`, else
`name`) and does not set the attribute itself gets XML1's value, resolved with XML1's `data/values.xml`
(`BuildContext.x1_values`, the section 24 numbers: "4 5", "9 11", "15 18", "25 31"). A style event that inherits
the shared one carries the value on to every trigger naming it, so only the direct child is written. Left alone:
an element with a `type`; a name that resolves to an event of the style itself (a style event of the shared name
shadows it); an `<event name=X>` without `inherit` (a redefinition); a tag update of an inherited trigger (0x4f6a1f
re-parses only its own attributes onto the inherited copy, which carries the value already). XML2-origin styles
(XML2's 16 same-name fightstyles, XML2's shared_nodes entries) are never XML1 trees and keep XML2's numbers.
Idempotent; counts `x1_shared_value:<event>.<attr>` in the schema log.

Over XML1's style files (xml1_loose: 12 fightstyles, 34 powerstyles, `shared_nodes`): punch 61, kick 17,
punch_heavy 20, kick_heavy 14, punch_veryheavy 8, move_damage 1, fry 2 elements, throw damageMod 7. In the build only
the XML1 styles characters and heroes write change (XML1's 10 same-name fightstyles and every shared_nodes node of
XML2's name stay XML2's; no XML1-only shared_nodes node inherits a listed event), 23 styles: Avalanche, Blob,
Juggernaut (with its three throws), Magneto and Magneto boss, Pyro, Sabretooth, Toad, the clawed (a/b/c) and bruiser Morlocks, the fire demon, Shadow King two,
`moveset_sent_adv`, `moveset_shadowdemon`, the Phoenix dopple's `phnx_fry`, and the heroes' kept XML1 moves of Beast,
Colossus (`radial_punch`), Gambit, Phoenix, ProfXAstral and ProfXGladiator.

### 33.2 Differences deliberately not written

- `knockback`: XML1 K1 = 40 and K2 = 120 equal XML2's 40 and 120 (the audit's "54 inherit knockback" inherit the
  same number).
- `damagescale`: XML1 has no such attribute (not a default.xbe string). XMen2.exe parses it with 0x44ec00 over the
  table 0x6d6dec (`none` 0, `normal` 1, `difficulty` 2; an unknown name is 1) into +0x14 of the attack (0x4dc118);
  its consumer is not traced, so whether XML1's melee is closer to `normal` or `none` is unknown. XML2's own
  re-ships of XML1 NPCs (ps_sabretooth, ps_blob, ps_juggernaut punches) keep the shared punch's `normal`; so does
  this port.
- `grab` `damagetype="dmg_grab"`: not an XMen2.exe string (the damage-type parser 0x43bd70 has no such type);
  XML2's `dmg_physical` stays.
- `pickup_throw` (XML1 sets no damage; XML2 "21 26") and the throw's `impactdamage` / `throwspeed`: XML1 has no
  number for them (neither is a default.xbe string); writing 0 would remove the damage XMen2.exe takes from them.
- `weapon_fire`: `ce_atk_weap` is XMen2.exe's sound class (section 29); weapons.py replaces every weapon_fire
  trigger of a gun style. `trail` (colour / width vs an effect): cosmetic.

### 33.3 Tests and checks

`tests/unit/test_xml1_data_fixes.py`: on a made-up style against a made-up XML2 shared table, the effective damage
of an inheriting punch / an event-chained heavy punch goes "2 3" / "3 5" -> "4 5" / "9 11"; overrides, a `type`,
a tag update, a shadowing style event and non-style files are left alone; idempotent; codes without a values
table. `combat_events_selftest` T4/T5 (the `combat_*` counts) are unchanged; V18 / V19 / V-H5 see resolved numbers.
In game: section 33.4.

### 33.4 In game (build/_t1a vs the same build without sections 31-33, build/_t1a_base; harness pipes t1a / t1abase)

A GRSO soldier's own melee is not affected: the GRSO npcstat entries name no fightstyle and their XML1 power style
(`ps_grso` -> the `x1_ps_grso_<weapon>` variants) holds only weapon_fire attacks, so their punch is XML2's default
fightstyle with XML2's numbers. The check uses the clawed Morlocks and the Morlock brute of sewers/hub/sewers1_1_1
(ps_clwmorlock / ps_lrgmorlock: `attacklight1/2` are bare `punch` triggers; the clawed Morlock's `power_attack`
projectile sets its own `15 18`, the control). Cyclops alone, level 1, `setHealthMax 7779` so he never dies; every hit
read exactly from his actor's health float (+0x27c, found by a memory scan for the two max-health markers), 60-75 s
per build, two runs each (scratchpad `t1a/melee_driver.py`):

| hits on Cyclops | before (XML2's "2 3") | after (XML1's L1 "4 5") |
|---|---|---|
| light melee (punch) | 3.01, 3.03, 3.14, 3.43, 3.50, 3.66, 3.70, 3.85, 4.68 (mean 3.6) | 5.65, 6.06, 6.33, 6.44, 6.78, 6.98 (mean 6.4) |
| the 15-18 projectile (control) | 14.26 .. 17.91 (mean 16.2, n 8) | 15.54 .. 20.44 (mean 17.3, n 6) |

The light hits scale by 1.8, XML1's 4.5 / XML2's 2.5 mean; the control does not move. (Hits of 5.8 / 6.3 before and
8.1 after are probably the brute's `punch_heavy`, "3 5" -> "9 11" at the same scale; not attributed.)

## 34. XML1's `runWithoutUser` conversation lines, the voiced replies and the reply-menu cursor through xml2-fix (2026-10-01, audit W1 / W3 / 7; 1.3.0)

Found by the world audit (`research/audit/xml1_world_gaps_2026-10-01.md`): XML1's conversations flag lines (and whole
startConditions, and single `%BLANK%` responses) `runWithoutUser="true"` - the mansion tours, the walk-and-talk
lines, the cutscene chains: 151 conversations wholly (939 lines), 51 more in part (530 lines and responses). XMen2.exe
never reads the attribute (not an exe string; the line parser 0x458820 / 0x459860 looks for it nowhere): on the XML2
engine every one of those lines sat until the player pressed accept. Two more engine behaviours the XML1 data hits far
more often than XML2's: a chosen reply's voice is stopped one frame after it starts (0x45d242-0x45d27d; XML1 has 239
voiced replies, XML2 six), and a reply menu come back to by `tagJump` with its previous pick now hidden highlights
nothing (the menu builder stores the visible count as the cursor, 0x45b5f1-0x45b5fc; XML1's hub menus).

### 34.1 The engine side (xml2-fix 1.3.0, `conversations_rules.hpp` / `conversations.cpp`; `[Game] AutoAdvance`, `ReplyVoices`, `ReplyCursor`, each on unless 0)

The conversation system's update (vt+0xc = 0x45d1a0, every frame) is described byte by byte in the rules header; the
three changes, each written only when every byte it relies on is the retail build's:

- **AutoAdvance.** The engine does parse `timeDelay` (0x458b68: atof into the line's +0x80, 0.5 when absent) and then
  never uses it (its one other use, a copy into CS+0x239a8 at display, is read by nothing). The builder writes the
  flag INTO that number: a NEGATIVE `timeDelay` marks a line that advances by itself; the magnitude is how long to
  show it when there is no voice to wait for. The call at 0x45d33e (the menu manager's vt+0x138(4), "accept pressed")
  becomes a call into the fix, which asks the game's own accept first and hands the answer back; when it isn't
  pressed and the current line's `timeDelay` is negative, exactly ONE reply is visible (CS+0x21b28), the engine's own
  first-second lock-out (CS+0x21b5c) has passed, no menu is up, and either the line's voice (CS+0x21b80) was heard
  playing and then not (plus 0.25 s), or there is no voice (or one the sound system never started) and |timeDelay| has
  passed, the fix does what accept does without the menu sound - stops the line's voice if any and picks reply 0
  (CS vt+0x18) - and answers "not pressed". A menu of two or more replies is never picked for the player.
- **ReplyVoices.** The pending-reply step (0x45d242, `call 0x592480`) becomes a jump into the fix: while the chosen
  reply's voice still plays and accept isn't pressed, the update goes on at step 3 (the line and its menu stay drawn)
  instead of stopping the voice; once it has ended, or when accept is pressed (a skip), the game's own path runs.
- **ReplyCursor.** The store at 0x45b5fc becomes a jump to a stub that stores max(count - 1, 0): the reply after the
  previous pick, which the pick's own bookkeeping meant (0x45d61d-0x45d636 remembers pick + 1, wrapping to 0).

`xml2-fix.log` gets one line per auto-advanced line (its id, timeDelay, why, how long it was shown, the voice handle)
and the start / end of every reply-voice wait (the handle, its lifetime in ms and game time, skipped or ended).

### 34.2 The data side (this builder: `conversations.mark_auto_advance`, run by `scripts.rewrite_data_tree` on every XML1 conversation)

A `<line>` is marked when it is flagged itself, or its enclosing `<startCondition>` is (every line of that tree), or its
one and only `<response>` is (XML1 flags the `%BLANK%` under a flagged line, and 11 times the response alone).
Responses are not marked. The magnitude: an existing positive `timeDelay` on the line (XML1's own 2 / 3, six lines) is
kept; otherwise a reading time from the text after its `%SPEAKER%` token, 1 s + 0.06 s a character, clamped to 2..12 s
(`reading_seconds`). The attribute is written under the engine's own name `timeDelay` (a `timedelay` of any other case
is replaced); `runWithoutUser` itself stays in the file (the engine ignores it). Idempotent (a negative value is left
alone; scripts_selftest runs `rewrite_data_tree` twice). Counts in XML1's English conversations (xml1_loose): 268 +
37 flagged lines with one reply, 745 + 99 lines under flagged startConditions, 11 single flagged responses; the 2 + 4
+ 40 menu lines inside flagged trees are marked too but never picked (they have several replies). Retail data has
no negative `timeDelay` (XML1: 6 lines / 6 responses at 2 or 3; XML2: 2 / 2), so XML2's own data is untouched by the
hook even with the keys on, and without the fix the number is as inert as it always was.

Tests: `tests/unit/test_conversations_auto_advance.py` (which lines and why, the values, the floor / ceiling / token
stripping, the engine's attribute name, responses untouched, idempotence). In game: 34.3.

### 34.3 In game (build/_fix130, harness pipe f130, save folder "X-Men Legends (f130 tests)", xml2-fix branch `conversations`, 2026-10-01)

Wolverine alone (`loadMapKeepTeam`), windowed, `tools/conv_probe.py` every 0.5 s, `xml2-fix.log` quoted; the drivers
and frames are in the session scratchpad (`f130_driver.py`, `f130/*.png`).

- **A line goes on by itself (W1).** mansion1a_2's entry conversation (Jean's second-floor line, id 64, voice handle
  0x4): no key pressed for 90 s; the probe shows the line up at 2 s and the conversation over by 8.5 s; the log:
  `line 64 advanced by itself (timeDelay -8.00, its voice played and ended, shown 6.64 s, 1 reply visible, voice
  handle 0x00000004)`. mansion1a_1's entry conversation: line 67 (voice 0xb) went on by itself into the hub menu
  (line 69, 4 replies visible) at 9 s.
- **A menu is never picked (W1).** Line 69 with 4 visible replies sat for 85 s with nothing pressed (the probe:
  the same line, `selected 0`, `pending 0`; no log line).
- **A chosen reply's voice plays out (W3).** Enter on the first (voiced) reply of that menu: the probe shows the
  menu line still up with `pending_response 69` and voice handle 0xc for the first 1.8 s, then the answer (line 70);
  the log: `a chosen reply's voice (handle 0x0000000C) is playing - the conversation waits for it` ...
  `the reply's voice (handle 0x0000000C) ended after 1719 ms (1.72 s of game time) - on to its answer`. Before the
  fix (the audit, build/_w4): the answer within the key press, the reply's handle replaced before its first sample.
- **The chain after it (W1):** lines 70, 71 and 72 went on by themselves at 6.10 s, 4.67 s and 1.35 s (each `its
  voice played and ended`), then the conversation ended; no key after the one Enter.
- **ReplyCursor:** bytes verified against the retail exe (xml2_test), not reproduced in game in this run (the hub
  re-entry with a hidden reply needs the mansion1 `disallowResponseOnVar` state; `startConversation` of 1_2_1_2
  from the pipe did not start after the entry conversation had run).
- **addSkillPoints (SPEC 32):** `tools/skill_points.py` before / after `addSkillPoints('_ACTIVE_HERO_',1)` from the
  pipe in nyc1_1_1: Wolverine's unspent skill points 0 -> 1, every other hero 0 -> 0, levels and attribute points
  unchanged; the log: `addSkillPoints("_ACTIVE_HERO_", 1) -> Wolverine: unspent skill points 0 -> 1`; the
  character screen's SKILLS tab shows `REMAINING POINTS 1` for Wolverine (frame `19_details_right.png`), its STATS
  tab `REMAINING POINTS 0`, and the HUD shows the game's own "Press [F1] to Level Up" prompt (0x46d089 -> 0x4b7b00).
  The pickup itself (haarp_ext03's `item_skill`, `SKILL` registered as definition 64 of 69, read from the item
  manager) did not fire in this session: `copyOriginAndAngles("_HERO1_","item_skill")` plus a walk never touched it,
  and the same held for the content-7 form (`SKILL_750` / `setXP`) and for haarp_ext02's health pack with the 1.2.0
  DLL - the touch method of this run, not the item; the activator resolution is `setXP`'s (0x4a7e30) and the pipe
  run above shows the call reaching the hero's counter.
- **[Limits] ItemEnhancements=512 (32.1):** the same build with the 1.3.0 DLL and the key: the log `item enhancement
  pool raised from 375 to 512 records - the item manager grows from 0x7a00 to 0xCA40 bytes ... records move from
  +0x2594 to +0x7A00`; after New Game the item manager (read from [0x72a514]) holds **88 definitions** (69 before:
  the load stopped at VISOR_OF_RETRIBUTION) and **410 enhancement records** (375 before), the 410 bits set in the
  new bitmap at +0xca00 and none in the old one; definitions 69-87 (the 19 Danger Room rewards) own records 374-409,
  every record a definition names has the record vtable; the pipe's `status` says `items 410/512`; haarp_ext03
  loads and a save completes with the pool at 410. XML2's own records 0-373 are where they were.

## 35. XMen2.exe streams zone entities by hero distance: the entities a zone's scripts name are pinned (2026-10-01, the haarp_ext02 bridge softlock)

### 35.1 The gap

haarp/ext/haarp_ext02 "The Bridge": walking onto the bridge (trigger_touch01 -> trigger_tank -> reveal_tank ->
Scripts/haarp/ext/tank_reveal.py) locks the controls, moves the heroes to hero_spot01-04, acts exit_door, spawns
the three tank guards, plays the engine loop, then `startMotionPath("tank", "haarp/ext/tank/mp_tank_base",
"FALSE", "tank_finished")` and `waitsignal ( "tank_finished" )`. On the port the door stays shut, no tank appears
and the signal never arrives: a softlock (Owen, by hand; the harness tours teleport past it). Pre-existing (0.1.5
and 0.1.6 alike). The second reveal (haarp_ext01, tank_reveal2.py, `waittimed ( 8.000 )`) showed the same
symptoms without the softlock: tank motionless, its henchmen stuck behind the never-opened exit_door.

### 35.2 The engine (breakpoint traces of build/_t16 under scratch tankdbg.py, a gamedbg.py with int3 breakpoints)

- The motion path itself is fine: the package entry `motionpath filename="haarp/ext/tank/mp_tank_base"` reaches
  the motion-path precacher (vtable 0x69c50c; `0x57ae00` strips the entry at its last `/`, prefixes
  `motionpaths/`, precaches the IGB, walks its scene graph in `0x57a6f0` - igTransform nodes by name, igGroup
  children recursively - and registers `"<group>:motionpaths/haarp/ext/tank/mp_tank_base"` in the 450-name map
  through `0x57a5c0`, 16 path records at most, `[mgr+0x15c] == 0x10` refuses). XML1's `motionpaths/haarp/ext/tank.igb`
  (byte copy of the disc file, igTransform `mp_tank_base` + igTransformSequence1_5, 257 keys, 8.53 s) registers
  exactly like XML2's `abyss/blimp_fly_in.IGB` (handles 0x11 / 0x12 for tank / tank2 in the trace).
- `startMotionPath` (`0x4a8f20`) resolves its entity with `0x4a7e30` and got **0 matches for "tank"**
  (`0x4a8f7e`); the single-entity resolver `0x4a1700` -> name registry lookup `0x4c6f20` returned 0 for every
  `setInvisible("tank")` / `setNoClip("tank")` too. The entity existed at load: its model
  `hive_ext/tank_vehicle_whole` loaded (`0x475817`), the name registry (`0x778b70`, ctor `0x4c6730`) registered
  `"tank"` (`0x4c7890`) and **unregistered it in the same frame** (`0x4c70a0`), as it did for every physent /
  doorent / spawner / affectableharment / actionent of the zone - except the three whose XML1 entity already says
  `smartent="false"` (tank_base, tank_turret x2), which stayed registered. Entities near the heroes were
  re-registered under new ids as the party moved (reveal_tank, ready_tank, play_tank_loop_sound, exit_door when
  the script enabled it); teleporting a hero to the tank's spawn point (977 -1380 305, 1,200 units from the
  bridge) re-registered `"tank"` at once while the far props (snowmobile_ha, 55galdrum_ha, fire, soldier spawns)
  were released. So XMen2.exe keeps a zone's entities dormant unless a hero is near, or the entity is marked
  `smartent="false"`; a script naming a dormant entity finds nothing and silently does nothing.
- Why the script's own door and tank looked dead: exit_door (972 -1117) and tank (977 -1380) are 900 and 1,200
  units from the hero spots at the bridge (the camera looks at 938 -220 -> 941 -316); whatever the engine
  re-created for the door was released again as soon as it was out of range, so the gate never opened and the
  guards spawned behind it could not come out (haarp_ext01, same layout).
- XML2's own data is explicit about this: every entity its scripts drive along a motion path carries
  `smartent="false"` (genosha4 shipA / shipB / bomb1-4 / firefx), and over its 170 zone files 487 physents, 82
  doorents, 489 monsterspawnerents, 249 gameents, 329 actionents, 102 affectableharments ... are pinned that way,
  up to 68 in one zone (egypt3). `smartent="true"` is rare (9 physents). XML1's own zones use the attribute too
  (tank_base, tank_turret) but not on the entities its cutscenes drive from afar: XML1's engine evidently resolved
  dormant entities differently.

### 35.3 What the builder does (`zones.pin_scripted_entities`, run by `mutate_zone` after the data rewrite)

For every converted zone, the scripts it runs are read (`Zones.zone_script_texts`: the XML1 bundle's scripts, the
world's `zonescript`, and every script an entity's `*script` attribute names; inline attribute code - a value
with `(` - is read as source). Every slash-free quoted string of those sources, lower-cased and not starting with
`_` (`_OWNER_`, `_HERO1_`, `_ACTIVE_HERO_`), is a candidate entity name (`script_name_literals`; paths and sound
names carry a slash). Each `entity` whose name is such a literal, or whose own `*script` moves `"_OWNER_"` with
`startMotionPath` / `setMotionPath`, gets `smartent="false"` - unless it is of `PIN_SKIP_CLASSES` (no classname,
playerstartent, waterent, tileent, cameramagnetent: XML2 never pins those) or XML1 already set `smartent`
(either value wins). A script may name an *instance* rather than its entity (hive1_1_1 `tank1`-`tank4` of entinst
type `tank_vehicle_whole_hex`, arb_fd2 `the_lift` of `decklift_arb`, hive1_2_1 `kick_barrel` of `barrel_hive_hv`,
haarp_ext_boss `the_jet`); `smartent` is an entity attribute (XML2's 29,063 insts carry only name / pos / orient /
extents / parent), so the instance's type is pinned and every instance of it with it (hive1_2_1: all 21 barrels for
the one the script kicks). The scripts are not changed: `waitsignal ( "tank_finished" )` stays, the signal now comes
from the path's end. Counted as `entities_pinned` (per zone in `Zones.pinned`); one build note gives the total,
the per-class split and the largest zone (XML2's own largest is 68).

Lost / different: pinned entities are alive from zone load wherever the heroes are, as in XML2's own zones; a
pinned spawner that is enabled at start spawns at load (XML2 pins 489 spawners the same way). Entities named only
through variables, `spawn()` results or `setName` are not found and stay streamed. The turret on the tank
(`tank_turret`, XML1 `scanturretent` -> physent, section 1) still does not aim or fire: XMen2.exe has no turret
class; XML2's firing "turrets" (tutorial1 `turret1`) are a physent whose actscript `spawn()`s an invisible gunner
NPC and `setParent`s it to the model - the route if the port ever wants a firing turret (an XML1 gun soldier
character, invisible / noclip, parented by the turret's spawnscript), not done here.

### 35.4 Tests and checks

`tests/unit/test_zone_entity_pins.py` (made-up zone and scripts): names by zone script / entity script / inline
attribute code, `_OWNER_` motion paths by ref and inline, document order, XML1's own `smartent` kept, the skip
classes, unnamed and classless entities left alone, a second run a no-op, unreadable scripts ignored.

### 35.5 In game

- Hand patch first (build/_t16: `smartent="false"` on `tank` and `exit_door` in Maps/haarp/ext/haarp_ext02.ENGB -
  the engine reads the .ENGB, not the .XMLB beside it - and the original waitsignal script restored with CRLF; a
  fresh process, new game, party seated, loadMapKeepTeam, `setGameFlag("x1v03",9,1)`, walk onto the bridge): the
  registry keeps `tank` and `exit_door` from load, `startMotionPath` finds 1 match, the class bit passes, the path
  handle resolves (`0x47528b` -> 0x7dc8ac), the gate is open and the tank rolls out of it with the three guards
  walking ahead (scratch shots_t16f), control returns, and 11 s after the start `tank_ready` removes `tank`
  (`UNREG tank`) and the fight begins on the bridge.
- build/_tank (this builder, `--no-movies --test-ini`, harness pipe `tank`, save folder "X-Men Legends (tank
  tests)", xml2-fix 1.3.0 DLL; 1,145 entities pinned in 162 zones - physent 280, monsterspawnerent 216, gameent
  190, actionent 127, affectableharment 67, doorent 51, ...; most in mastermold2 with 29), each scene in a fresh
  process (scratch drive3.py: new game, party magma / phoenix / iceman / wolverine, loadMapKeepTeam):
  - haarp_ext02 bridge, the builder's own tank_reveal.py (`waitsignal` intact), `setGameFlag("x1v03",9,1)` and a
    jog onto trigger_touch01: the gate is open, the tank drives out through it with the three guards walking
    ahead, the fade returns control on the bridge, the HAARP soldiers engage (shots_bridge); afterwards
    `copyOriginAndAngles("_HERO1_","base_tank_spot")` shows tank_base with its turret parked in front of the gate
    where tank_ready put it (base_spot.png).
  - haarp_ext04 second reveal, `act("reveal_tank","reveal_tank")` (tank_reveal2.py, `waittimed ( 8.000 )`): the
    gate opens, the four henchmen come out through it, the tank drives out behind them, control returns
    (shots_reveal2). Owen's earlier hand run on the 0.1.6 stopgap had both reveals with a motionless tank, a shut
    gate and the henchmen running against it: same cause, same fix.
  - The other motion-path scripts (arbiter crane_drop / crane_swingout, asteroid_m blastoff, hive tank1-4,
    barrel_kicker, haarp fly_jet) were checked by data only: their targets (the_sub, the_crane, decklift_arb for
    the_lift, shootme_floor* by `_OWNER_`, tank_vehicle_whole_hex for tank1-4, barrel_hive_hv for kick_barrel,
    the_jet in haarp_ext_boss) all carry `smartent="false"` in the build; none of them waits on a path signal
    (tank_reveal.py was the only `waitsignal` after a `startMotionPath` in XML1's scripts), so none could softlock
    even before.


## 36. Scripted boss protection on the XML2 engine (issue #2)

### 36.1 Scope and cause

XML1's boss pattern names configure engine-owned brains that XMen2.exe does not implement. This
conversion restores Magneto's protection transitions and Shadow King's reachable first form/timed
shield through scripts and data. It does not recreate the original brains. Master Mold is explicitly
excluded after review found the initially proposed spawn shield could block the final fight.

### 36.2 Conversion

`boss_phases.py` runs from `Scripts._base_text` and `rewrite_data_tree`, on exact script/zone paths only.
Generated scripts retain CRLF. Original counters, timers, health thresholds, rewards and follow-on
scripts remain in control. HAARP scripts and all Master Mold scripts/data are outside the dispatch.

- **Magneto, asteroid2_1:** append `setInvulnerable("magneto","TRUE")` to the existing `shieldup`
  inline action. Preserve its targets/counts. After the pattern call in each `asteroid_m/stage2` through
  `stage5`, wait 0.100 seconds, then clear invulnerability. When helpers die before the threshold, the
  pain script can activate both shieldup and the final stage-relay input together. The delay gives the
  shield-up action time to execute before release, avoiding a permanently protected boss.
- **Shadow King, final_astral:** place only the first-form spawner at the XY of existing named waypoint
  `wp_bossmaster3000_04`, using `player_start` solely for its known floor height. The resulting position
  is (-578.026, -300.718, 65.0815), 322.04 units from the party start. The waypoint's raw Z is 0, below
  the arena's visible floor; do not use that Z for the actor. The spawner retains its identity/facing.
  The zone-entry alive guard copies the living first-form actor to that same named waypoint, then sets
  Z from player_start. It does not move the party. `relocate_spawn` rejects missing/duplicate instances
  and malformed coordinate counts, including duplicate types across multiple entinst groups.
- After `sk3` in `sk1pain`, set Shadow King's invulnerability TRUE; after `sk4` in `dropshield`, set it
  FALSE. Original shield flag, threshold caps and 30-second timer remain. The unchanged `spawnsk2`
  script places the second form at the first form's death position; it is not moved back to the party.

Content version 8 -> 9, unreleased. Builder version stays 0.1.6 until a release is selected.

### 36.3 Master Mold correction and deferred work

The initial PR enabled shockshield_on at spawn while stage < 4. This was unsafe. `mmpain` needs damage
to cross 66.7% (mold2 plus sentinel cinematic) and 33.4% (mold3). The new spawn shield prevented both.
`checkcore` requires coresgone >= 3 AND corecount >= 3; it writes stage 4, which would also skip the
health phases if the cores were completed first. The cores are elevated team-hero physents, designed
for enemy fire under the missing XML1 moldblowcore targeting behavior. Switch activation alone does
not destroy them. The review's unstaged switch-window run left coresgone at zero and the boss blue
at 100% throughout. The former `issue2_core_control.py` bypassed this dependency by assigning the
prerequisites; its earlier result is withdrawn as progression evidence and the driver is removed.

This revision takes the review's removal route: mmspawn is untouched, no Master Mold conversion or
new release timer remains, and the original core puzzle is deferred to a separate fix. All 30 generated
Master Mold scripts were byte-compared against the pre-PR baseline with zero differences; all 12 map
files match the reviewer's build (whose Master Mold maps were already confirmed unchanged from main). Synthetic
tests explicitly require these script paths and the zone to pass through unchanged. Existing missing
core-targeting behavior is not claimed fixed. The new `issue2_review.py mastermold` uses no health or
phase assignments, core-counter assignments or direct checkcore activation; its damage calls invoke
the existing pain thresholds, and switch acts use their ordinary scripts.

### 36.4 Evidence and limits

Separate builds/save folders/pipes, 1280x720 windowed harness with xml2-fix 1.3.0, connected desktop.
Source installations and Owen's play build were not modified. Screenshots/saves stay outside Git.
Boss bars are approximate pixel measurements with title checks; minion-target frames are rejected.
These are controlled encounter probes, not complete unaided campaign playthroughs.

| Check | Baseline / earlier defect | Revised result |
|---|---|---|
| Magneto shield | Shield-up still allowed ordinary damage, 99.5% -> 98.3% | Protection blocks damage; stage relays release it. Earlier stage-3/4/5 samples held at 99.5/92.6/85.1%, then fell to 92.6/85.1/77.7% after release |
| Master Mold | Initial PR spawn shield gated damage behind a core puzzle whose targeting is missing | Spawn shield removed; original scripts preserved byte-for-byte; core puzzle deferred |
| Shadow King placement | Original pillar unreachable; first PR placed him on the party start | New waypoint XY/floor Z is 322 units away. Fresh-entry images show him separate from the heroes; normal AI/party attacks reach him, 98.5% -> 98.3%, without teleporting either side |

Revised placement's isolated solo run: blue 83.6% stayed 83.6% under ordinary hits; after 32 seconds
it was red, and ordinary hits lowered it to 76.2%. With the last damage window and one HP staged,
an ordinary hero hit triggered the unchanged second-form handover on the ring floor; the second form
was visible and its bar had already fallen to 97.3%. Normal-entry party AI was kept out of this separate
probe because it could advance the encounter between samples. Failed/reused encounter probes were
not counted as passes.

Master Mold no-core-staging run after removal: spawned red at 99.5%; damage progressed through
91.1%, 83.6%, 76.7%, 69.2%, then the 66% sentinel drop-in cinematic (captured). Subsequent damage
reached 37.7% and the next threshold at 33.0%. No health, phase or core-counter assignments were used;
no direct checkcore activation. All three switches were activated; after their 90-second windows
expired, the bar remained red at 33.0% and further damage lowered it to 26.1%. Minion-title frames between the cinematic and 37.7% were discarded.

The timer/phase-end probe stages health and the last damage window but uses ordinary hero attacks for
pain/transition triggers. The generic-AI power_boost has a separate roughly 31-second damage shield;
the isolated test idles that AI and waits out its buff. It is unchanged in normal play. Scripted
invulnerability does not recreate XML1's Xtreme-only shield bypass; timed vulnerable windows remain.
Original boss attack scheduling, flight/pillar choreography and cooldown changes remain outside scope.
Save migration and completed-fight re-entry have not been exercised end-to-end.

Build after review: 0 errors (inherited warnings remain). All affected generated scripts verified CRLF.
Unit suite: 117 passed, including 12 synthetic boss-helper tests using invented actor/entity names.
They cover scope, CRLF, delayed release ordering, idempotence, named marker selection, floor-height
substitution, duplicate rejection, unchanged party/second-form positions, and Master Mold exclusion.
Drivers and setup: `research/regression/boss_fights/ISSUE2.md`.

### 36.5 The second form's death ends the fight in any kill order (2026-10-02, Owen's hand test)

At 50% the second form (`shadowking2`, spawner `sp_shadowkingtwo`) casts `power_xtreme`: two `spawn_actor` images of
the character `shadowkingtwo`. They inherit the spawner's death script, `astral/savepx/shadowking_defeated`, which
counts deaths in the zone var `deadsks` and ends the side mission (objective, popParty back to astral2_3, Professor X's
conversation 3_9_3_4, the portal, mansion8) at exactly 3. Owen played the fight twice on the 0.1.7 candidate:
image -> real -> image never ended (an image that dies after the real one runs nothing, so the count stops at 2);
images first, real last ended normally. XML1's count assumed every death counts.

`boss_phases.end_on_real_death` rewrites the generated script: after the counter is stored it waits 0.5 s and asks
`alive("shadowking2")`; the fight ends if the count reached 3 OR the real one is gone, a zone var `sk_ending` (read
and set in the same frame) lets exactly one run end it, and the leftover images are removed (four `remove` calls).
The original ending body is unchanged; only its condition becomes the decision. Fails closed if the source shape
changes; idempotent. One deviation from XML1: the last image no longer has to be hunted down once the real one falls.

Not proven in the harness: scripted kills could not drive the first form's death reliably (his own `power_boost`
damage shield and the pain caps), so neither the broken order nor the control reproduced there; the check is Owen's
replay of the broken order on the rebuilt test build. Related, separate: issue #28 (arriving in the mansion out of
bounds after the ending, seen on a run that entered the arena by a test shortcut that skipped pushParty).

---------------------------------------------------------------------------------------------------------------

## 37. XML1's objective attributes `required` and `updatedescription` (2026-10-01, audit W10; issue #8)

XML1 objectives carry two attributes the port dropped: `required` ("false" on optional objectives - XML1 shipped
two, one of them in a mission the plan installs) and `updatedescription` (the completion text XML1 swapped in when
the objective finished - 31 installed objectives have one (unique per act group), most of them count objectives). The generator
(`prepare/tables.mission_plan`, stage P2) wrote every objective `major="true"` and neither attribute survived.

### 37.1 What the engine offers (and what it does not)

XMen2.exe's objective schema is `name descname description enabled count xp major parentname type zone`. `major`
drives the HUD's Primary list (`Primary` / `Secondary` are exe strings); XML2 retail's own minor objectives are
`major="false"` with a `parentname`. XML1's `required="false"` maps onto it directly: the optional objective moves
to the Secondary list instead of standing among the primaries.

`updatedescription` is read by XML1 (the string is in `default.xbe`: the Xbox swapped the completion text in) but
not by XMen2.exe, which contains no such string; both executables know the same objective commands -
`EOBJCMD_COMPLETE / DECREMENT / HIDE / INCOMPLETE / INCREMENT / SHOW` (plus `UNKNOWN`) - and `display` is a stub
(0x5aaff0), so there is no verb that rewrites an objective's text. The builder keeps the attribute in
`mission_plan.json` (objectives keep their source attributes there), writes nothing the engine cannot read, and
counts both attributes instead of dropping them silently. Issue #8 stays open for the completion text. Two routes
remain: a data-side swap for objectives a script completes (emit a hidden sibling objective carrying the
completion text; at `EOBJCMD_COMPLETE` HIDE the original and SHOW + COMPLETE the sibling - it cannot cover count
objectives that the engine completes on its own when DECREMENT reaches zero, which are most of the 31), or an
xml2-fix text verb (review note, 2026-10-01).

### 37.2 The data side (this builder: `prepare/tables.mission_plan`, stage P2, VERSION 2)

`required="false"` (any case) -> `major="false"`; absent or "true" stays `major="true"`. The plan JSON gains
`objectives_major_false` and `objectives_with_updatedescription`, and the stage log reports them. Cache: the stage
key does not cover the generator's code, so the VERSION bump to 2 forces the tables stage (and, through its
input-hash key, the P3 scripts stage) to re-run.

In the installed content this changes one objective today (the test mission nyctest2's `enemies` objective becomes
`major="false"`; the other `required="false"` sits in `arbiter_test`, which no script references and the plan does
not install) and records 31 `updatedescription` objectives.

Tests: `tests/unit/test_objective_attrs.py` (made-up missions: the `major` mapping for required true / false /
absent, `updatedescription` absent from the XML2 text but counted and carried in the plan).

---------------------------------------------------------------------------------------------------------------

## 38. XML1's per-zone music override attributes are dead in XML1 retail too (2026-10-01, audit W8 revisited; issue #7)

The audit read the world attributes `ambientmusic` / `combatmusic` / `intromusic` (9 campaign zones + 7 demo
copies) as per-zone music overrides the port loses: "the zone bank's default ambient / combat track plays instead
of XML1's override". Investigating the fix surfaced that the premise is wrong - **the attributes were already dead
in the shipped Xbox game**, and the port's behaviour matches the Xbox exactly.

### 38.1 The evidence

- The attribute names are not strings in `default.xbe` (`ambientmusic`, `combatmusic`, `intromusic` - absent;
  `soundfile`, `zonescript`, `skybox` present as the read-attribute control). XML1's world parser never looked at
  them, and there is no composition table that would build the names from pieces (`_ambient`, `combat`, `intro`
  exist in unrelated contexts only). XMen2.exe lacks the names as well.
- None of the override values names any audio anywhere: not a bank (216 XML1 banks: no `morlocks`, `sewers1`,
  `arbiter1`, ...), not a sound or ZTRK track (a PJW/ELF hash scan of every sound/track name table in all 216
  banks over the values and `music/...`, `music/music_amb/...`, `music/music_combat/...`,
  `music/music_cues/...` spellings: zero hits), not a file (the disc holds only `default.xbe` and `sounds/zsds`),
  and not a hardcoded xbe table (the values are not xbe strings either).
- XML1's real music system is the same one the port uses: the world `soundfile` whose `music/<name>_a` /
 `music/<name>_c` banks the engine loads (the keying is confirmed, sound summary section 2), plus a `CMusicEntity`
  class and the `changethememusic` console command that no XML1 zone data uses (no `musicent` entities anywhere).

So on the Xbox, `arb2_2` played `arbint_a`/`arbint_c`, `sewers1_1_4` played `sewer1_a`/`sewer1_c`, and so on -
exactly what the port plays. The attributes are development leftovers (the values read like internal track
working titles from Raven's music pipeline, shipped in zone files only).

### 38.2 The builder side

No behaviour change - there is nothing to restore. `zones.world_music_attrs` collects the attributes for the zone
report (`zones_detail.json music_overrides`), the converted zones keep writing only what XMen2.exe reads, and the
stage's defer message now says the attributes are dead in XML1 retail too instead of implying the port lost a live
feature. If Raven's music titles ever resurface (e.g. a future xml2-fix hook reading them), the plan is the
audit's sketch: build the zone's `_a` / `_c` banks from the named track.

Tests: `tests/unit/test_zone_music_attrs.py` (made-up world elements: collection of the three attributes, absent /
empty ignored, the attributes reported rather than written).

---------------------------------------------------------------------------------------------------------------

## 39. The one cross-file conversation tagjump: mansion4's Emma scene copies its menu into the jumping file (2026-10-01, audit W11; issue #9)

XML1 resolved a response's `tagJump` across every loaded conversation file; XMen2.exe looks only in the file the
response lives in (`0x45cde0` -> `0x4573f0`, case-sensitive match on `tagIndex`, conversation-speakers.md section 4
step 9). Of the 365 XML1 tagjumps exactly one leaves its file: `conversations/mansion/man4/2_5_10b`'s last response
(`tagJump="2_5_10loop"`) targets the reply-menu line that lives in `conversations/mansion/man4/2_5_10`. In the port
the lookup returns NULL, the childless `%BLANK%` response sets the ending flag, and Xavier's introduction of Emma
ends at Emma's last line: the seamless hand into the ask-Emma menu (and the `noReturnToGameCamAtEnd` continuity) is
lost; the player only reaches the menu through a later re-trigger of `2_5_10`.

### 39.1 The data side (this builder: `conversations.resolve_cross_file_tagjumps`, run first in the conversation branch of `scripts.rewrite_data_tree`)

For the one tabled case the tagged `<line>` and its whole subtree are deep-copied out of the owning conversation
(read from the XML1 source through `ctx.read_x1_xml`) and become the root line of a new `<participant>`
(`x1_tagjump_<tag>`) of the jumping `<startCondition>`. Every tagIndex known to work sits on a participant root
line (80 XML1 + 1 XML2 retail); placing the copy as a second root line of `default` was tried first and the engine
never registered it (35.2). Entry selection - activator name, the `"default"` fallback, then the first unspent
`runOnce` startCondition - is untouched. The copy is inserted before
`mark_auto_advance` and the attribute pass, so it is patched exactly like the rest of the file (speaker tokens,
script references, auto-advance marks; the menu's internal `tagJump="2_5_10loop"` responses now resolve to the
local copy and loop there). `chosenScriptFile` on the jumping response stays as XML1 wrote it
(`mansion/man4/profx_disapears` still fades Xavier out and marks the scene done), but its `conversationEnd` is
removed: in game (35.2) XMen2.exe ends the conversation on a response's `conversationEnd` even when its `tagJump`
resolves - the flag sets the ending flag at the advance and step 3 ends the conversation a frame later - while XML1
followed the jump. The copied menu ends at its own `%END%` response (which still runs `astral_legwork`), so the
conversation still closes properly. Idempotent: a file that already carries the `tagIndex` is left alone
(`scripts_selftest` runs `rewrite_data_tree` twice), and a tabled conversation whose jumping response was cut is
skipped without a copy. The fixed file stays well under the engine's 40-line / 50-response conversation pools
(22 lines, 25 responses). Table-driven (`CROSS_FILE_TAGJUMPS`) so a second discovered case is one row, not a new
mechanism.

Why a copy and not a retarget: the menu exists only in `2_5_10`; there is no equivalent local line to point at,
and XML1's own behaviour is "continue this conversation at that line".

Tests: `tests/unit/test_conversations_tagjump.py` (made-up conversations: the copy and its placement, idempotence,
the case-sensitive local check, missing source / missing tagIndex warnings, and the no-jumper / no-table-entry
no-ops). In game: 35.2.

### 39.2 In game (build k28, harness pipe k28, save folder "X-Men Legends (k28 tests)", windowed, 2026-10-01)

Wolverine + Cyclops (`seatParty`), `loadMapKeepTeam("mansion/man4/mansion4_1")`, `startConversation` of
`mansion/man4/2_5_10b` from the pipe, `tools/conv_probe.py` every 0.5 s; the driver and frames are in the session
scratchpad (`tagjump_driver.py`, `tagjump_game/*.png`).

- **The scene runs its two passes and lands in the menu.** Lines 64-66 (Emma meets Alison, SC1) advanced by
  themselves, the conversation ended on SC1's own `conversationEnd` (by design: `profx_apears` fades Xavier in and
  re-starts it), lines 67-72 (Xavier introduces Emma, SC2) advanced by themselves, and the jumping response then
  went **straight to line 73 - the copied menu, 4 visible responses, `ending=False`, no key pressed**. Before the
  fix the conversation ended at that point (`ending=True`, the probe sat on line 72 with one response); the menu
  was only reachable later through a fresh `2_5_10`.
- **The menu loops in-file.** Enter on the first reply ran its answer chain and the probe shows the menu again at
  line 73 (`visible_responses` 4) - the copy's `tagIndex` resolves for the jumper and for the menu's own
  `tagJump="2_5_10loop"` responses alike.
- **What did not work, and the two corrections it took.** First attempt (copy as a second root line of the
  `default` participant, jumper otherwise untouched): in game the conversation still ended at line 72 - the engine
  never registered the copy's `tagIndex` (every tagIndex that works in either game sits on a participant root
  line), and the response's `conversationEnd` was honoured even though the jump... the ending flag observed with
  the copy in place showed `conversationEnd` ends the conversation regardless of the jump. The shipped form puts
  the copy in a new `x1_tagjump_2_5_10loop` participant and removes the jumper's `conversationEnd`; the menu then
  appears with the conversation unbroken, `profx_disapears` still fades Xavier out, and the menu's own `%END%`
  still runs `astral_legwork`.


---------------------------------------------------------------------------------------------------------------

## 41. Player starts outside the walkable area (2026-10-02, issue #28)

mansion/man8/subbasement8's default start `player_start01` (732.275 1535.96 24.0228, `default="true"`, no prevzone)
is where every load without a matching prevzone arrives - in the campaign, astral/savepx/mission_end's
`loadMapKeepTeam("mansion/man8/subbasement8")` after the Shadow King side mission. On XMen2.exe it puts the hero
behind the war room's console desk, between the desk and the map wall: she can slide along the desk, and walking
towards the room drops her into the void (Owen's hand test; reproduced in the harness with a plain load and a walk).
The same war room's default start in subbasement7 (701.376 1674.6 24; the zone IGBs are the same size) is in the
room proper, and in subbasement8 a hero placed there walks to the computer and the stairs. Elevator arrivals
(player_start08/09) were also checked and are fine; subbasement7's and subbasement1a's defaults are fine.

`start_fixes.fix_player_starts` (run from `scripts.rewrite_data_tree` next to the boss-phase data rewrites) moves
tabled start instances (`START_FIXES`: zone -> start -> (expected XML1 pos, tested pos)); facing and identity kept;
an unexpected source position or a missing instance fails the build; a second run is a no-op. Tests:
tests/unit/test_start_fixes.py (invented zones).


## 42. Generated long-range buoy networks (2026-10-03, content version 10)

### 42.1 Generation, not conversion

XML1 ships no `.boy` files and no buoy section in its `.nav`. The former builder wrote an empty `<buoy/>`
for every converted zone. XML2 uses NAVB for local walk grids and separate BOYB networks for long routes;
this affects enemies and allies as well as scripted hero movement.

Unpacked retail XMen2.exe: `moveToEntity` at 0x4a4690 queues movement through 0x524ef0 / 0x50f000. Actor navigator
0x496280 calls far-path lookup 0x495790 when squared XY distance exceeds `2 * (15 * cellsize)^2` (about 848.5
units for size 40); local failures can also use it. Attachment needs a usable node strictly within 640 units.
A live port trace reached that lookup with a valid goal and loaded NAV cells/links, but only reserved buoy zero.

### 42.2 Native encoding

`buoys.py` implements the native read contract; no executable is patched.

- Zone loader 0x4857ca..0x485878 starts with the IGB scene root's aggregate AABox. Explicit extent_min/max
  replace XY; an explicit Z of zero keeps geometry Z. Re-unioning descendant boxes can double-transform
  decoration and inflate bounds, so the authored root bound is read directly.
- Spatial initialization 0x463f30 uses 120-unit cells unless `mapcellsize` overrides them, rounds bounds, and
  has additional oversized-grid rounding branches. NAV initialization 0x490e10 adds half a NAV cell to its XY
  minimum; XY bias truncates the spatial minimum divided by NAV cellsize. Z origin is effective minimum Z + 6.
  The native NAV grid limits XY dimensions to 252 cells.
- NAV loader 0x494470 packs c/p as `(x-bias_x, y-bias_y, trunc((z+12-origin_z)*0.083333f))`. It consumes only the first
  two records per XY location, including duplicates. Generation mirrors this order-dependent selection and
  reports ignored/out-of-range records, never placing buoys on floors the engine did not load. The native
  200-block limit (9x9 cells per block, 0x493210) is also enforced in source order; unmodeled nonzero c/t
  restriction bytes are excluded and reported. The converted corpus currently has no c/t attributes.
  The multiplier is the native float at 0x689b30, bits 0x3daaaa7e, not exact `1/12`. At an exact height
  boundary that difference selects the correct lower packed layer. A live NAV-cell audit and an invented
  boundary regression cover it; a BOY decode/encode round trip alone does not validate NAV height packing.

- BOY loader 0x494a30 reads a buoy root with b/n records: three unsigned packed coordinates and at most eight
  one-based neighbor indices. Minus one terminates padded lists; omitted slots have the same meaning. Zero is
  reserved and there are at most 288 real nodes. The directed link pool also has 350 slots, of which slot zero is reserved
  (0x493810), leaving 349 authored arcs (0x4936d0, graph+0x2eac); eight neighbors per node alone is not sufficient. Decode 0x490980 is `origin + (x*cellsize, y*cellsize, z*12)`.
- Coordinate range, neighbor indices and caps are checked before writing. Unreadable bounds fail closed with
  explicit coverage diagnostics rather than guessed coordinates.

Stock coordinate records were round-tripped and compared byte-for-byte with loaded records
in two stock zones, including negative bias. Predicted origins/biases matched live memory. Geometry defaults,
zero-Z overrides and the scene-root distinction were separately checked in live port zones. Exact scope and
exceptions are in the external evidence report; these controls do not establish campaign coverage. The initial
prototype passed file/stock-node round trips but a subsequent live NAV-array audit exposed its exact-division
height error. Corrected nodes were checked against loaded heights before the corrected networks were emitted;
prototype runtime attempts are not final-data validation.

### 42.3 Conservative walk graph

Zones generate BOYB after importing package model dependencies, through the normal context writer. Inputs are
the converted NAVB, final zone tree and map/model bounds. Source installations and disc images are read-only.
Cardinal walk neighbors follow native closest-layer selection and may differ by at most four height quanta
(48 units; 0x495d00 requires a delta strictly between -5 and +5). The nearest-layer choice is directed; a reverse edge is emitted only when a native walk search proves it.
Requiring each cell step to be reciprocal would invent isolated lower-floor components. Explicit NAV links are read as
restrictions, never promoted to unconditional edges: BOY cannot encode their jump/drop/team/action requirements.
No script-only teleport or puzzle transition becomes a walk edge. Potential doors, movers, elevators, gates
and bridge geometry are excluded even when scripts may open them later. Instance extents or readable model
bounds supply the volume; tilted gates use a conservative enclosing sphere rather than guessing Euler order.
Unknown gate bounds leave an empty network with diagnostics.

Gate volumes include body-height clearance below their geometry, so a hanging closed door is not treated as
a gap beneath its mesh. Nodes prefer corridor interiors over NAV boundary corners to reduce local collisions.

Each component receives a node before extra coverage is allocated. Deterministic farthest-point sampling uses
incremental distances in weak walk components, targeting 280 units to a node, stronger than native 640-unit
Euclidean attachment. Nodes favor cells with both incoming and outgoing native steps. Adjacent coverage regions
propose connections; bounded directed searches prove each direction separately. Within each strongly connected
coarse region, outgoing and incoming spanning trees precede one-way region connections and optional extra arcs.
Output never exceeds 288 nodes, eight outgoing neighbors per node, or 349 authored directed links.
Uncovered cells, exhausted budgets and fragmentation are reported, never repaired by crossing gates. Stable
ordering controls seeds, ties, numbering and serialization; source order matters only for native layer loading.

This is static navigation, not collision-mesh reconstruction or a puzzle solver. Opening a gate cannot add an
excluded static edge. Native local avoidance and interaction scripts retain responsibility for dynamic geometry.

### 42.4 Diagnostics and tests

Every converted zone emits a build note with nodes, components, coverage gaps and node/neighbor/link/grid-block
budget hits. Directed reachability lost during pruning is reported separately, never silently called covered.
`_build/zones_detail.json` contains its buoys diagnostics, including gate exclusions and rejected NAV records.
The 37 empty-NAV zones retain empty networks; their complete list is in validator V22's empty_nav_zones detail
and note in `_build/validate.json`.

V22 in developer and CI builds independently re-derives expected networks from output files, checks deterministic
structure and native bounds/caps/indices, and warns for gaps and budget hits. It does not trust cached generation
notes. Player builds (builder mode) check the structural invariants only: the full re-derivation added about 25 s
to every rebuild, and the same generation already ran in zones.

### 42.5 Fallback and the developer switch (review, 2026-10-03)

Any failure while generating one zone - one generate() handles itself (unusable bounds, an unreadable gate model)
or an unexpected exception - writes that zone's empty network, the 0.1.7 and earlier output, with a build warning
naming the reason, instead of failing the build. A standalone `xml1build.validate` reads the build's recorded
`buoys` mode from its report; a build made before SPEC 42 (no recorded mode) counts as `empty`.
`--buoys empty` writes the empty network for every zone: an A/B switch for comparing
AI movement with and without generated networks, and a quick way back. It is a content option: changing it
re-runs zones, and builds made before SPEC 42 count as `empty`. V22 then requires every network to be empty.

Behaviour note: enemies and allies now plan routes longer than about 850 units in the 161 zones with a NAV
grid. That matches XML2's own zones and XML1's allies following anywhere; encounters that relied on enemies
being unable to path around a gap may play differently, so releases carrying this need a hand check of mixed
zones. Build cost: about 30 s more in zones. Stats,
talents, hero ordering and saves are not renumbered. CONTENT_VERSION advances to 10; release VERSION is unchanged.

Invented-grid tests cover encoding round trips, negative coordinates, geometry defaults, zero Z, layer loading,
caps, connectivity, deterministic output, special-link/script-gate exclusion, tilted gates and empty grids.
Live before/after routes, ally/enemy behavior, pre-change saves, setup actions and runtime limitations are
recorded in the separate draft PR and external evidence. Autopilot campaign acceptance remains parked.

## 43. The fighting / power style registry (2026-10-04, issue #31)

### 43.1 The limit

XMen2.exe keeps every loaded style file - fighting styles, power styles, movesets and `data/shared_nodes` - in one
registry of 19 entries (manager 0x78a800; registration 0x4ffb30). A name that is already registered costs nothing;
a new one when the count is 19 is refused at 0x4ffb8a without a report. The permanent packages and the zone package
register first, then the party's packages in seat order, so the hero seated last loses the power style and has no
special moves (the fourth hero in arbiter/a_int/arb2_2 and sewers/grso/sewers3_1_2; swapping seats moves the
failure to whoever is last). XML1's zones need up to 22 with a four-hero party: 33 converted zones are over 19
for some party.

Trimming content cannot fix this: the styles are the zone's enemies' and the party's own.

### 43.2 The raise

xml2-fix 1.3.1 `[Limits] FightStyles` (20..32) rebuilds the registry with the configured size; the port's ini asks
for `fix_ini.LIMITS['FightStyles']` = 32, and `REQUIRED_XML2FIX` is 1.3.1. 32 keeps both of the registry's bitmaps
at one word, which is the most the fix supports, and leaves ten entries over the measured maximum for styles a
script loads later. An older xml2-fix ignores the key, and the registry stays at 19.

`tools/harness.py` writes the same `[Limits]` block, so test installs carry the raise too.

### 43.3 V23

`style_budget.validate` counts, per converted zone, the distinct style files of: the permanent packages, the zone
package, the packages of the zone's CHRB characters, and the worst four-hero party (every combination of the
playable herostat entries; a zone with combat off loads the heroes' `_nc` packages). More than the capacity the ini
asks for is an error; exactly the capacity is a warning (no room for a scripted load). Without the key the check
counts against the game's own 19. Scripted spawns outside the CHRB roster and temporary power styles are not
modeled.

Invented-package tests cover the capacity value, distinct-file counting, shared movesets counted once, the worst
party, NPC packages, combat-off zones and the stock registry. On a full build: 198 zones, 33 over 19, the largest
22 (astral/ast1/astral4_3).

## 44. Enemy outlines drawn with another skin's bones (2026-10-04, issue #11)

### 44.1 What was reported and what it is

Issue #11 reported black, spiky "weapons" on some enemies (the HAARP officer, the GRSO nullifier and flamethrower).
The weapons are fine. The spikes are the character's own black outline pass, deformed.

When XMen2.exe caches a model it runs a sharing pass that replaces a geometry with an identical one already loaded
in the same resource group (comparator 0x56D210, decision 0x56D700). The comparison covers format, counts,
positions and weights but not the packed blend indices. XML1's enemy skins reuse one outline shape across skins
with different skeleton indices: the officer's outline (534 vertices) equals the soldier's in every compared field,
and differs in the index field of every vertex. The engine hands the officer the soldier's outline, and the
officer's skin palette reads those indices as other bones.

Shown at runtime with a logging hook (no debugger): blocking only that one substitution gave a normal officer in
5 of 5 launches with the soldier unchanged; hiding only the gun left the spikes. The async-load theory was ruled
out (both weapons loaded synchronously and completely in every launch). Earlier package-content, package-weight,
package-identity and spawn-position theories had already been falsified over repeated launches.

### 44.2 The fix

xml2-fix 1.3.1 `[Game] GeometrySharingBlendIndices=1` adds the missing comparison inside the candidate loop: a
candidate whose packed indices differ is skipped, and the search goes on to the next one. Vertex-array layouts
the fix does not recognise keep the game's own comparison. It is off without the key (stock XML2 is not known to
need it), so `fix_ini.game_keys` writes it for every XML1 build, and harness installs carry it.

No data changes: the skins are XML1's. Measured in four zones the fix rejected 0 to 2 reuses out of 154 to 1657
comparisons, with memory within about 1.3 MiB.

Not covered: only the HAARP officer and soldier (5 launches) and the GRSO nullifier and flamethrower (1 launch
each) were checked in game. The comparator's other gaps (normals, extra UV sets, a count-reuse defect found in
static analysis) are not addressed.

## 45. HAARP fire-wall loop startup and relocation (issue #12)

The wall effect and its textures are present. Two engine behaviours hid it: the
harm parser at 0x4396a0 clears the loop-on bit for positive firstact, and a running
loop retains its old world placement after copyOriginAndAngles moves the entity.

The original fix gave the exact HAARP exterior fire_wall definition firstact=0, keeping loopfxstarton
without entering XML2's smartfire damage mode. The wall is staged underground until
its authored placement script moves it. This advances its initialization from the
original one-second delay; placement timing, damage fields and the normal non-smart
harm handler remain unchanged. An explicit smartfire configuration is not overwritten.

The six placement scripts hide the wall before the original act/move sequence and
show it after the move. Hiding/re-showing restarts the existing loop at the destination.
Scripts with an act keep it before the move; move-only scripts get no new act. The
flamer animation, waits, target names and activation count are preserved. Unexpected
source forms fail conversion rather than silently leaving the effect broken.

A smartfire=true candidate was rejected in game: although restarting its loop made
it visible, its different scheduling reduced damage. The final conversion does not
set that flag or change collision flags, damage, extent, health or extinguish reaction.

Controlled before/after proof in haarp_ext01 used fresh processes, the same vulnerable
Wolverine and the same native hazard relocated to the unobstructed landing area.
Baseline: no visible fire during damaging contact. Final candidate: visible fire and
floating damage values. Both completed the matching contact/exit sequence at 57 HP
from 90. This is an isolated hazard/placement test, not a full campaign playthrough
or a precise rate benchmark. Local captures and state records are retained outside Git;
see docs/issue-12-validation.md. Extinguishing and save/reload remain separate checks.

The general harm-loop conversion below (SPEC 51) supersedes
the name/path restriction on startup. The relocation script handling remains necessary.

## 49. Conversation speaker HUD-head residency (2026-10-04, issue #13)

Issue #13: with forced parties disabled, a named speaker can be absent from both
party and zone actors. Conversation portrait creation asks the IGB cache for
`hud/hud_head_<skin>` in the party slot group or zone group 11, with permanent
group 2 as fallback. A file on disk alone does not make that lookup succeed.

After completing each zone package's script/data reference closure, the zones
builder reads its final English conversations (XMLB fallback), including rewritten
speaker aliases and copied cross-file tagjump subtrees. Named line/response
speakers use the final herostat/npcstat baseline skin. Built-in activator and
control tokens need no additional head. An unloaded speaker uses the exact stats
skin; the builder does not manufacture an alternate-costume fallback or remap
converted skin numbers again.

Available heads absent from the permanent package are added as `model` entries
through `Pkg.add(extra=True)`: deterministic, deduplicated, before the zone core.
No actor, animation database, talent, style or conversation node is added. The
same rule applies with forced parties enabled or disabled; zone/NPC presence and
an arbitrary player's party are not assumed. Existing missing head assets are
not fabricated.

**V24 conversation portraits** independently reads final conversations, stats
and packages. An available required head without permanent/zone model coverage
is an error. A missing head whose source asset exists is an error; unavailable
source heads/stats are separately reported as inherited warnings (V5/V6 still
check stats). The check deliberately requires coverage without party packages,
which also covers forced-party configurations. V12 continues to check every
zone's direct IGB budget; passing it is not a bound on all simultaneous groups.
V4 permits an otherwise source-looking model name only when a conversation in
that package requires the head of a same-name, same-skin native XML2 stats entry.
The asset must still exist; this avoids remapping a retained XML2 speaker twice.

Cold-start runtime experiment: the unchanged build with ForcedTeams=0 and
Wolverine alone showed a black Magma portrait on `mansion/man1a/1_2_37`, line 66
(four replies); Rogue's preceding head rendered. A single zone model addition
made Magma render with no Magma actor. Direct package IGB records increased
111 to 112; live IGB records 154 to 155 and resource names 239 to 240, with
16 actor slots and 10 fight styles unchanged. This was a staged map load and
conversation invocation, not evidence of the natural campaign interaction path.

The generalized build reproduced that positive result and rendered absent
Cyclops in `mansion/man3/2_1_10` with Wolverine alone. The NYC starting zone
remained at 36 direct records and loaded/rendered. Across all 198 zones the
change adds 89 direct model entries in 48 zones (maximum seven per zone), with
V12 still passing. The largest direct counts are mansion Juggernaut 119 -> 122,
its demo counterpart 118 -> 121, and mansion4_2 unchanged at 115. V24 checks
612 speaker/zone occurrences: 579 covered, 33 inherited occurrences of three
unavailable source heads, zero available-head gaps.

A staged stress run in the largest zone, with the estimator's heaviest baseline
party (Magma, Iceman, Psylocke, Wolverine), used 184/200 IGB records and 297/1024
resource names. `extractionPointChange` released zone resources: its team menu
used 87/200 and 160/1024; returning retained the party and used 186/200 and
300/1024. This route does not keep the entire zone and team-menu head packages
resident together. These measurements are not bounds for every costume, menu
route, saved-game load or long session; those remain unverified.

Synthetic tests cover final speaker keys, the offset-four form, mixed case,
activator/control tokens, exact skins, aliases, duplicates, missing stats/assets,
existing permanent/zone coverage, closure-introduced conversations, copied
subtrees, ordering, idempotence, and a removed-head validator negative control.

Generated packages change, so CONTENT_VERSION must advance at merge. The task
coordinator owns that bump; this change intentionally leaves its value untouched.

## 51. Ordinary harm-loop startup (issue #12)

`x1schema.convert_harm_loop_start` runs after entity class remapping on every
imported XML1 tree. An entity qualifies when its class is affectableharment,
loopfx is nonempty, loopfxstarton is true, and firstact is a finite positive
number. Absent or explicitly false smartfire uses the ordinary harm path;
enabled or unrecognized explicit smartfire configurations are retained.
No entity name, map path or effect-name whitelist is used. In particular,
non-fire loops with the same engine failure qualify too.

The conversion sets only firstact to zero and records `harm_loop_start` in the
schema change log. This includes the HAARP walls previously handled by SPEC 45.
Their hide/move/show script wrappers are unchanged: starting a loop correctly
does not fix its old world position after script relocation.

The second failure is handled by a source-derived script pass: named instances
of start-on, non-smart harm loops are collected from source map definitions,
scoped to the matching maps/scripts directory. Their literal
copyOriginAndAngles calls get hide/move/show wrappers. A preceding act of the
same entity stays after hide and before move; move-only calls gain no act.
Existing SPEC 45 blocks remain byte-identical. Names that also identify an
unrelated instance in the same namespace fail conversion if moved. Authored-off
loops and explicitly invisible definitions do not qualify. This does not infer
dynamic targets or cross-directory script contexts. The current source inventory
adds wrappers for six NYC placements, two Hive placements and three HAARP
interior placements; the six existing HAARP exterior scripts remain unchanged.
The extra script statements are checked by the existing script-pool validator.

A controlled current-main NYC test confirmed this separate relocation failure
on a fire with an empty firstact: the loop was invisible after relocation from
underground and became visible after hide/show. This does not establish that
every report of a fire appearing after circling has the same cause.

XML1's action parser reads loopfxstarton at 0x28c66 independently of firstact
at 0x28d32. The latter schedules an activation via 0x277e0 and the first-act
callback at 0x27550. XML1's harm parser at 0x7c440 does not clear the loop bit.
XML2's harm parser at 0x4396a0 clears the authored loop-on bit at 0x4399d9 when
firstact is positive. Zero bypasses that branch. The builder therefore loses
the initial activation delay (one second in the matching source definitions):
damage can begin earlier, and the phase of repeated activations can shift.
Damage values, repeat delays, contact settings, reaction powers, health and
death scripts remain authored. Enabling smartfire is not a substitute: it
selects a different damage scheduler (SPEC 45).

A future, guarded XML2 Fix change could preserve the authored loop bit while
retaining the delayed activation. It needs separate evaluation of the preceding
disable call, smartfire/on-off timers, extinction and save/load, including XML2
retail content. This builder change neither implements nor requires that patch.

V25 independently scans decoded registered output for remaining ordinary harm
entities in the dead form, failing with the file, entity, effect and delay.
Identical XMLB/engb twins are reported once. Synthetic tests use invented hazard
names and effects, cover remapped classes, explicit false smartfire, unrelated
classes, authored-off loops, missing/malformed/zero/negative delays and idempotence.
Runtime evidence and its limitations are recorded in docs/issue-12-validation.md. CONTENT_VERSION
stays 11 for the unreleased content revision.

## 52. Fall kill volumes (issue #22)

Issue #22: XML1's lethal touch boxes survive conversion, but a hero can land alive
inside one and become trapped outside the playable area. Keep the designers'
boxes; do not infer a global floor height or replace the harm entity with script
triggers.

`x1schema.convert_fall_kill_volumes` applies only to map entities with the XML1
lethal-touch signature: `affectableharment`, `damage="32000"`,
`damagetype="dmg_direct"`, `actontouch="true"`, `nocollide="true"`. Matching is
independent of entity names except for the specific deferred pair below. After normal class conversion, set
`boxcollision="true"` and `smartent="false"`, the collision and residency flags
used by XML2's native fall kill volumes. Preserve every other attribute and all
instances, including bounds, positions, orientations, damage modifiers, targeting
flags, and activation scripts. Ordinary fire/damage hazards and non-map entities
are outside this rule. The conversion is idempotent and reports
`fall_kill_volumes` in the schema counters.

Source evidence: these volumes specify lethal direct damage without a hero-only
team filter; some also invoke a script that hides the activator. Retaining the
harm class, damage, and script preserves that authored behavior as far as the
source data establishes it. Original Xbox runtime behavior for AI allies and
knocked-in enemies has not been independently tested. No new hero-only targeting,
invulnerability bypass, damage multiplier, or lethal script call is introduced.

Runtime mechanism controls used the released xml2-fix 1.3.1. An unchanged native
kill definition in a staged flat-corridor box killed a walking hero without a
fall. Native `dmgmod_kill` can produce health near -1,000,000, so that number alone
cannot distinguish a volume hit from the engine's void-fall handler. A HAARP
negative control left Magma alive on the ravine floor after a real double jump
and unable to return under movement input. Adding boxcollision alone still left
a hero alive there. With both flags, a real double jump killed Wolverine with a
32,000-point health loss. Teleports were setup only, not evidence of touch entry.
Experimental XMLB writes must use `common.encode_xmlb`: unsorted attributes
invalidate the engine's binary-search lookups and any resulting mechanism claim.

V26 checks registered XML1-sourced map outputs for matching volumes missing
either flag; identical localized twins are counted once. Deferred volumes are
reported separately, and adding either enabling flag to one is an error. Its number is assigned
at merge. Synthetic tests cover preservation of multiple instance bounds and
activation scripts, class remapping, unrelated hazards, idempotence, sorted
binary output, and validator negative controls for each flag. CONTENT_VERSION
remains 11 under the maintainer's unreleased-version instruction.

The generated build was also checked with Magma and Wolverine at HAARP (real
jump input after position setup), and with Wolverine at `mount/mount/mount2`.
The mountain negative control reached the engine void limit; the converted box
instead dealt the original 32,000 damage inside its authored bounds. At HAARP,
Iceman formed the ice bridge through power input, and Wolverine walked across
with three AI teammates following; all four retained full health. Ordinary
combat with existing enemies on the bridge approach likewise left the party
alive. These are bounded harness checks, with scripted party/position setup,
not a complete campaign or saved-game playthrough. An attempted closer-edge
solo lure was navigation-limited and is not additional combat proof.

The initial PR output contained 32 matching definitions and 41 instances across 30
converted zones. Comparison of all 198 map trees found only the intended flag
changes (32 smartent attributes, 31 boxcollision attributes; one box already
had collision). V26 counted all 32 definitions once across localized twins;
full build validation and the zones self-test passed.

The reduced two-flag configuration also passed a staged flat-floor on-foot
control: Wolverine lost exactly 32,000 HP at Z=0.16, with no fall.

### Option: defer the HAARP exterior ravine volume too

`maps/haarp/ext/haarp_ext01` / `kill_target` is deferred for the same reason. In ten walks and crossings per build
with a four-hero party and real input, an AI follower cut a ledge corner and fell into the ravine about once in six
passes on both builds; nothing about the volume causes the fall. With the volume inert the engine put the fallen
follower back on the bridge about a second later; with it lethal the follower died (two deaths in the candidate's
runs). The first game's data has no solo-mode trigger at this bridge. Cost of deferring: a leader who double-jumps
into this ravine is left alive on the ravine floor again (issue #22 stays open for this zone). This leaves 30 enabled
definitions and two deferred.

### Review follow-up: deferred flooded-room volume (issue #5)

Leave only `kill_target` in `maps/arbiter/a_int/arb3_4` in its original form.
`FALL_KILL_DEFERRED` identifies an exact map stem and entity name; other lethal
entities in that map and same-name entities in other maps still receive the fix.
This leaves 31 enabled definitions in 29 converted zones, with one definition
explicitly deferred. No bounds, damage values or unrelated hazards change.

Four-hero runtime review reproduced a regression: the player crossed a
player-created ice bridge safely, while AI Wolverine took the flooded-room
route and lost 32,000 HP. Restoring the original volume left the party alive;
a separate real-input water entry left the player and an AI ally alive below
the plane. Keep this volume deferred until issue #5 party handling and the
crossing are revalidated. The bridge script itself removes the solo triggers,
so this test proves an AI-routing interaction, not that missing solo mode alone
explains all of it.

The nuclear-plant pit `nuke_plant/nuke/nuke2_2a` remains enabled: its tested bridge
crossing produced no AI kill-volume deaths. A level-1 attempt had ordinary enemy
combat deaths; a repeat staged to level 17 separated those from lethal-volume
hits. Some allies lagged on the bridge. An attempted Storm crossing did not
maintain flight and is only a player-fall control, not evidence about flight
routing. Original Xbox behavior and every possible party route remain unverified.

Synthetic tests use invented map/entity identifiers to check exact-pair scope,
source-attribute preservation, neighboring hazards, localized paths, validator
deferral reporting and rejection of accidental reactivation.

The revised generated build repeated the flooded-room bridge crossing with all
four heroes alive, and HAARP still killed on a real double jump for 32,000 damage.
A short control retained the earlier experiment's misspelled `damagemo` field:
its definition attributes and instance bounds matched the saved experiment,
but normal sorted encoding killed correctly. The saved experimental XMLB had
unsorted attribute keys; it was not a valid negative control for the native flags.

## 53. The first game's voice lines (2026-10-05, issue #49)

XMen2.exe builds each character's sound table when the character loads (0x438d20, called from 0x4239be). For
every event of the build's `shared_sounds` table it checks a name with the sound system's exists method (vtable
+0x34, 0x590120) and, when it exists, stores the handle from resolve (+0x38, 0x590bd0); a missing name stores the
"none" handle and the line is skipped. The first six events (pain .. death) use `char/<sounddir>/<event>`, every
later one (tauntkd, victory, sight, the team commands, lowhealth, epitaph, solo, xtreme, levelup, bored, the banter
events) `char/<voice folder>/<event>`, the voice folder being the sounddir with its `_m/` as `_v/`
(`simlookup.voice_dir`). The first game names the same lines `character/<voice folder>/<event>` in its global
`x_voice` bank.

Before: P2 recovered names for x_voice only as `character/x_voice/<word>` guesses, so P4 wrote no `char/` alias
for them, and the merge into X-Men Legends II's `x_voice` kept X-Men Legends II's entries on every shared key. In
game (the character sound-table builder traced at 0x438f9f / 0x438fbb): Wolverine and Jean answered none of their
24 voice names; Cyclops and Blob answered only X-Men Legends II's lines (Cyclops 20 events plus 14 banter lines,
Blob 7 events including canttalk / lowhealth / respaffirm, which the first game's Blob does not have). Offline, on
the same bank: Emma, Gambit and Rogue silent too; Colossus, Iceman, Nightcrawler and Storm X-Men Legends II's lines,
Beast 5 of them.

Rules:
- P2 `tables` (VERSION 4) tries `character/<voice folder>/<event>` for every XML1 herostat / npcstat sounddir and
  every XML1 `shared_sounds` event, in the `x_voice` bank only (no other XML1 bank names one). Where such a name
  shares a key with another guess (ELF hash collisions), the voice name wins. P4's existing rename then writes the
  `char/` aliases (645 -> 2179 aliases).
- P4 `sound` (VERSION 2) merges with a shadow list: `char/<voice folder>/<event>` for every first-game voice folder
  and every event of both games' `shared_sounds`. X-Men Legends II's entries under those names (and their random
  variants) keep their index and audio but move to a private key (`merge_zsnd.shadow_key`), so the first game's
  entries are appended and answer instead. X-Men Legends II's lines for events the first game's character never had
  (Cyclops's banter, Blob's low-health line) no longer play either: that character said nothing there. 854 keys
  are shadowed. The media check of merged banks accepts exactly those private keys.

**V27 voice lines** (validator): for every XML1 stats entry, every voice name the
first game's `x_voice` answers must answer in `<out>`'s `x_voice` (error: silent), from an entry whose audio file
index is past the retail bank's files (error: X-Men Legends II's line). On the unfixed build it reports the silent
heroes; on the fixed build 0 errors.

Bank: `x_voice.zss` 153,229,172 -> 153,278,260 bytes (key and entry tables only; the first game's audio was
already in the bank under its `character/` keys). The sound prepare stage reruns once (43 s with the compiled
kernel on an 8-thread machine, about 6 minutes with the numpy codec).

Not established: which event the hero switch itself plays, and the run-time play path for a stored handle (the
switch keys did not switch heroes in the opening NYC zones in the test harness, on either build).

## 54. Popup dialog platforms (issue #50)

Issue #50: seven of the first game's popup dialogs (six tutorial tips of the first mission and the mansion's
second-floor hint) ship only `platform="xbox"`, `"ps2"` and `"gc"` variants. XMen2.exe's popup loader (0x5ebfd0)
asks the platform test 0x4bd650 about every `<dialog>`: a missing or empty `platform` is accepted, a list (space,
comma or tab separated, 0x68d618) is accepted only with a `PC` token (`_stricmp` against 0x68e9a0), anything else is
skipped. With every variant skipped the panel opens empty, with the engine's default help line. A dialog's `filter`
(0x5ec003) selects among variants too; a variant without one matches every filter.

`x1schema.convert_dialog_platforms` (every XML1 text import under `dialogs/`) gives each filter group with no
accepted variant an untagged copy of its `ps2` variant (else `xbox`, else the first), inserted after the group's
last variant; the console variants are kept unchanged. The ps2 text is chosen because it is what X-Men Legends II
itself shipped for PC: its platform-split hints end with an untagged variant, word for word the ps2 one in 9 of the
10 that have a ps2 variant ("press" rather than the Xbox trigger "pull"). The conversion is idempotent and is
counted as `dialog_pc_variant_added`.

V28 (dialog platforms) checks every registered `Dialogs/` file (an identical `.XMLB` twin once) for a variant the
platform test accepts per filter value.

In game (xml2-fix 1.3.1, windowed harness): on the unfixed build the tips opened by tut4 and tut14 in the first zone
and the mansion hint opened empty panels; on the fixed build all seven show their text (read from the game's popup
record in memory, alongside the test pipe's popup state, not only from screenshots). The token-expanded button names
read correctly with the keyboard and with a pad. Inherited wording that does not fit PC: the world-map tip names a
PlayStation stick button and the grapple tip asks for an analog stick, which keyboard players do not have (X-Men
Legends II's own PC automap hint has the same wording). Not changed: rewording game text is out of scope.

## 55. Codex list without icons (issue #48)

Issue #48: every first-game codex entry that is not a hero showed Cyclops' face. X-Men Legends II's
`UI/menus/codex` list item (`MENU_ITEM_LISTCODEX`) has `icons="textures/ui/mini_convo_icons.png"` with an 8x8 grid,
and the list draws for each entry the cell its stats' `textureicon` names. The port's heroes carry one; the first
game's NPC stats have none (default.xbe has no such attribute), so they all drew cell 0. The first game's codex list
was text only (no `icons` on its codex menus).

`frontend.codex_menu_trees` writes `UI/menus/codex` (both halves, each from its own XML2 file) without the list's
`icons`, `icons_cols` and `icons_rows` and without the `textures/ui/mini_convo_icons` precache; the list reads
`icons` only when present (0x5c269e). `--frontend xml2` keeps XML2's menu. V29 (codex icons) checks that with
`--frontend xml1` both halves are the frontend module's and draw no icon cells.

In game (xml2-fix 1.3.1): on main, an NPC entry (Professor X, unlocked with `unlockCharacter` as staged setup) showed
Cyclops' icon; on the fixed build the list shows no icons for heroes or that entry, and the highlight follows the
keys. Without icons the entry text starts at the list's left edge while the focus bar keeps its old start, so the
first letters of the focused entry sit left of the bar (reported, not changed). On both builds the 3D preview and
the Details page stayed on the first entry after moving the selection with test-pipe keys or pad; this is not caused
by the change and is not investigated here. Enemy entries were not reached in game: `unlockCharacter` did not list
them.

## 56. Personal items (issue #47)

Issue #47: examining a bedroom item in the mansion's second-floor zones showed the zone's loading screen, and
Wolverine's item a yellow/magenta panel. The first game's map entities call `personalItem('<hero>NN')` (36 names, in
the `mansion*_2` zones). XMen2.exe's `personalItem` (0x49e570) opens the `personal` menu (PERSONAL_MENU), whose loader
(0x5cedd0) reads `data/personal/<name>`: an `ITEM` with `texture` and `text`. Section 4.4 had kept X-Men Legends II's
`Data/personal` (only a leftover `wolverine01`, naming a texture X-Men Legends II never shipped, drawn as the engine's
default texture) and no `Textures/personal` existed, so a missing item left the menu manager's last image on screen.

`frontend.write_personal_items` (both front ends; the items are in-zone data) writes every first-game
`data/personal/*.eng` as `Data/personal/<name>.{XMLB,engb}` (schema conversion, text through `escape_menu_text`) and
imports each item's texture IGB under the same name (`Textures/personal/*.IGB`, 36 files). X-Men Legends II's
`wolverine01` is replaced. The menu (`UI/menus/personal`, `menu_personal.IGB`) stays X-Men Legends II's: it is the
same PERSONAL_MENU as the first game's. This supersedes the "XML2's kept; deferred" entry for `personal/*` in 4.4,
and with `--frontend xml2` the frontend module now writes these items (and nothing else).

V30 (personal items) checks every `personalItem` literal in installed data and scripts: both halves of its data
file are the frontend module's, have text without unescaped renderer codes, and name a texture whose IGB is in
`<out>`.

In game (xml2-fix 1.3.1): on main, Cyclops' first item showed the mansion loading screen and Wolverine's the
yellow/magenta default texture; on the fixed build both show the first game's picture and close with the back key or
the pad's B. Known gap: the item's text is not drawn. It is loaded (the word-wrapped text is in the game's memory
while the menu is open), but no text box appears over the picture. Re-framing the menu IGB on X-Men Legends II's menu
camera as done for the credits menus (21.2.1) did not draw it and hid the help line too, so it is not shipped; adding
a text style to the text box or only moving the camera's near plane changed nothing. The cause is open.

## 57. Gun soldiers fight in their gun's style (issue #52)

### The gap

The HAARP, nuclear-plant and Weapon X rifle guards stood in the unarmed villain idle with the rifle bolted to a raised
fist, and the muzzle flash and shots came from above the head. The GRSO rifle soldiers held the gun up in one hand
with the other arm spread. Two things combined:

- XML1 (default.xbe) replaces the holder's selected fighting style with the weapon's while it is armed: spawn's
  weapon assignment (0x327A0) installs it in fighting-style slot 1 (0xED300 / 0xED390), and 0x30890 overwrites
  animation slot 1 with its animations. XML1's character bundles agree: the HAARP, nuclear-plant, Weapon X and police
  bundles list only `fightstyle_gun_rifle`, never the `fightstyle_villain` of their stats entries (melee holders
  likewise list only their weapon's style). The port added the weapon's style only when the entry had none, and
  XMen2.exe uses one fighting-style talent per character (the lowest talent id, 0x43B0A0). So seven entries kept
  `fightstyle_villain`: HAARPSoldier, HAARPFlamethrower, HAARPLeader, NukeGuard, WeapXGuard, WeapXGuardLeader,
  Police.
- The port shipped X-Men Legends II's `fightstyle_gun_rifle` anim DB (13 animations). The first game's has 22; idle,
  attack_light1 / heavy1 and the fire moves power_1 / 3 / 5 / 10-12 are only in the first game's. The GRSO entries,
  which did get the rifle talent, therefore had no rifle idle and no fire animation either. `fightstyle_gun_hip` has
  the same 21 animations in both games.

### What the builder does

- `weapons.gun_fightstyle`: the style a gun (bullet / beam / flame / projectile) names. `characters.convert_stats`
  drops the entry's fighting-style talents for such a gun and gives it the gun's (count
  `fightstyles_replaced_by_gun`, 7). Melee weapons are unchanged: they still add their style only when the entry
  has none (what XML1 does for them is the same replacement; not changed here).
- `x1names.X1_OWN_FIGHTSTYLES = {fightstyle_gun_rifle}`: `map_fightstyle` and `map_animdb` give it `x1_`, so the
  first game's style file, anim DB and shared talent ship as `x1_fightstyle_gun_rifle`, and every character, zone
  and style package entry that named the rifle style follows through the existing mapping. `map_attr` maps a fighting
  style's `animations=` like `characteranims`, and the style file's root `name` follows the file.
  `is_fightstyle_name` (`fightstyle_*` or `x1_fightstyle_*`) replaces the prefix tests of the shared-talent keep rule,
  the validator, the actor budget and the self-test. The keep list swaps `fightstyle_gun_rifle` (named by nothing
  now) for `x1_fightstyle_gun_rifle`: still 61 shared talents.
- 15 stats entries change (the 7 above and the 8 GRSO rifle entries, whose talent becomes the `x1_` name); 56
  packages change only by the rename, and the style's own package is new. Budgets, per zone against the build of main: IGB cache (`igb_budget.py check`),
  actor slots (V13) and the fight-style registry (V23) are unchanged in every one of the 198 zones: the packages
  already listed the rifle style, and the villain style was in none of these soldiers' packages.
- Validator V5: an XML1-origin entry whose XML1 weapon is a gun that names a style must carry exactly that
  style (mapped) as its only fighting-style talent (`weapons.fightstyle_problems`; 20 entries checked). Run
  offline against main's output it reports 15 entries; against this branch's, none.

### In game (harness, windowed, XML2 Fix 1.3.1, own pipe, 2026-10-04)

Negative control = the build of main; fix = this branch. Wolverine level 1 (90 HP), vulnerable, from a new game.
haarp_ext04: the hero is put at `generator_fence_ha03` and steps out with one real 0.6 s key press (the spot itself
is inside the generator box, where nothing could see him: 0 damage in 40 s), then stands for 40 s next to the two
mp5 soldiers; HP read through the pipe at the observer's ~0.13 s sample rate. To keep him alive he is healed when low
(staged: `restoreHealth` below 30 in the first four main and first three fix runs, `setHealth` to 90 below 45 in the rest).
Left out: one run per build with screenshots every 0.5 s (slower sampling; 4.20 and 4.81 HP/s), one fix run where the
hero died under the first heal method, one main run started while my other game still served the same pipe.

| | main | fix |
|---|---|---|
| pose | villain idle, rifle in a raised fist, flash above the head | rifle held level in both hands, flash and shells at the gun |
| damage per hit | 4.0-5.0 (mean 4.53, 248 hits) | 4.0-5.0 (mean 4.47, 283 hits) |
| HP per second, 7 runs of 40 s | 5.26 mean (2.61-6.75) | 6.62 mean (5.89-8.51) |
| bursts | 5-6 hits spread over 0.5-0.7 s; never 6+ hits within 0.5 s | 7 hits within 0.36-0.40 s (3-4 samples; once in one sample), stacked damage numbers |

The burst against the first game's data (`ps_grso` power_boost): 7 shots of L1 (4-5) at 0.30-0.74 of `ea_power1`,
whose animation is 0.20 s and plays at playspeed 0.125 (1.6 s), i.e. 0.48-1.18 s into the move, about 0.11 s apart,
about 0.5 s from first to last. The fix lands 7 hits in 0.36-0.40 s of samples, consistent with that. The playspeed
is honoured: with power_boost set to playspeed 1 in the fix build (staged edit, restored afterwards) no cluster above
4 hits appeared in 2 runs. Damage per shot is the first game's in both builds. The higher HP per second comes from
bursts that now play out in full; how often a soldier fires is still XML2's AI cadence (`aitype` / `aireusetime 3`,
section 29), not XML1's weapon timing (`bursttime`, `recoiltime`), so the absolute rate is not established as the
first game's.

Also seen: GRSO mp5 soldiers in sewers3_1_1 (main: gun up in one hand, other arm spread; fix: rifle level, firing,
stacked hits), the nuclear plant guards in nuke1_1 (main: villain stance, guns above the head; fix: rifle level,
tracers, sparks on the hero), the HAARP flamer in haarp_ext01 now in the hip style (flame hits 18 every ~4 s, as in
section 29). Police in nyc_fb2 keep their own idle (58_police's idle wins over the style's); they did not fight
there. Not reached: Weapon X guards, laser / nullifier / lightning / freeze / knockback holders, police firing.

Unchanged by construction (identical output files and stats entries against main): melee holders (HAARPSoldierMelee,
NukeGuardMelee, WeapXGuardMelee, the GRSO batons and gloves), Mystique (no weapon on her entry; her style is
unchanged), the scan-turret props (no entity file changes).

Tests: `tests/unit/test_gun_fightstyles.py` (invented weapons, styles and entries: the gun rule, melee and unarmed
entries, the `x1_` mapping of style, anim DB, `animations=` and package entries, the validator rule).

## 58. XML1's per-mission hero unlocks (2026-10-04, issue #55)

**Symptom.** A player who skipped Iceman's optional mansion conversation reached HAARP without him and could not
build the ice bridge (softlock); Magma could be picked from the first mansion visit on.

**What XML1 does** (default.xbe, image base 0x10000). Every console `beginmission` (New Game's `beginmission
alison`, script `beginMission`, `beginSideMission` = pushsidemission + beginmission) loads the mission through
0x86560, which calls 0x84fc0 unconditionally (0x866fb) before the party builder 0x18d6d0. 0x84fc0 walks the table at
0x44e2e8 (8-byte rows {milestone label, hero}, a NULL label ends it): it finds the FIRST row whose label equals the
mission's `data/missions/missions.xml` `charunlock` (case-insensitive, 0x343612) and unlocks the hero of that row
and of every row before it (registry vt+0x2c = 0x552a0). The party builder only seats REQUIRED heroes (slot setter,
no unlock), so Magma, REQUIRED in the hubs and briefings, is unlocked only by the `dr_mag2` milestone (missions
`nuke`, `nuke_col`). Loading a save never re-applies the table (the save keeps its own unlock list).

**The port** (`xml1build/unlocks.py`, `scripts.mission_start_unlocks`). The milestones come from the prepared
`missions.xml`, the table from the player's prepared `default.xbe`, after checking that the walking function
(0x84fc0, 0xb3 bytes) has the known SHA-1 and that the mission loader calls it at 0x866fb; any other executable,
an unreadable table or a mission without `charunlock` is a build error (no guessing; nothing from the table is in
the repository). Rows naming no playable hero of the build (Forge, Healer) are dropped.
- Mission starts: every copy of every begin body (`x1/missions/begin_<m>` and the inlined copies, side missions
  included) unlocks, after its REQUIRED unlocks, the heroes of its milestone's own group (the rows after the
  previous labelled row), identically in every copy. XMen2.exe keeps unlocks in the profile and nothing clears
  them, so every story path, which starts each milestone's missions in table order, ends each mission start with
  XML1's cumulative set. The full cumulative set in every copy (up to 14 lines) pushed `nyc/riots/nyc3_2_1` (four
  act-3 begin bodies) to 671 and `muir_is/muir3/muir_in3` to 658 statements, past the 620-node pool (0x4d7e6e).
- Seated-only heroes (`scripts.menu_only_unlock_map`, `scripts_transform.menu_only_unlocks`): in a forced-teams
  seat build, the REQUIRED heroes of a seated mission that are outside its cumulative set (Magma before `nuke`,
  ProfXAstral / ProfXGladiator, Cyclops at the two joins) are unlocked only in the seat block's team-menu branch
  (`else` -> `loadMapChooseTeam`, i.e. `[Game] ForcedTeams=0` or no DLL), where the player must be able to pick
  them; xml2-fix `seatParty` seats without an unlock check. V14c accepts those unlocks at the start of the branch.
- Saves in progress (`scripts.catchup_unlock_plan`, `scripts_transform.catchup_unlocks`): XMen2.exe runs a zone's
  script when a saved game is loaded into the zone (verified in game, see below), so the zone script of every zone
  whose XML1 world entity names a mission unlocks that mission's cumulative set after its act entry (a script shared
  by zones of several missions gets the heroes common to all). `CATCHUP_SKIP_ZONES` leaves out `mastermold2` (613)
  and `nyc3_2_1` (610) for the statement pool.
- The X-Men Legends II rule that the team menu reads the profile, not the save, is unchanged (scripts cannot lock a
  hero): a profile that unlocked Magma or a later hero before keeps it. Per-save unlocks need XML2 Fix (not here).

**Checks.** Build errors: the table / milestone reading; every begin-body copy unlocks its group exactly once
(`unlock_problems`, also heroes **V-H13** on `<out>`); a seated body that still unlocks a seated-only hero in its
header (`menu_only_problems`, also **V-H14** on `<out>`); a planned catch-up not written. Counts:
`mission_start_unlock_missions` (99), `menu_only_unlocks`, `catchup_unlock_scripts`. Unit tests:
`tests/unit/test_mission_unlocks.py` (invented tables and bodies).

## 59. Object physics on XMen2.exe's scales: lifting, grabbing, breakable walls (issue #51)

### TBD.1 Lifting (heaviness)

XML1 (default.xbe) clamps an entity's `heaviness` to 5 and its pickup gate (0x38400) lifts an object when
heaviness < 5 and heaviness <= might + 1, where might is the hero's `might` talent rank (0xb1ba0, talent name
string 0x3d3fb0): anyone lifts 0-1, Might rank 1/2/3 lifts 2/3/4, 5 is never lifted. XMen2.exe clamps heaviness to
3 (physent parser 0x498900) and its gate (0x427f60, run by ch_guard_decide 0x4ec090) lifts when the object has no
`nopickup` bit (+0x30d & 4), heaviness < 3 and heaviness <= the hero's lift value (0x427dc0: 0 unless the
`might_heaviness` affecter raises it). XML1's values were copied unchanged, so a heaviness-1 trash can needed Might.

`x1schema.convert_physics` maps the heaviness of every XML1 entity definition (any element with a classname;
characters' stats are a different property and untouched): 0, 1 -> 0; 2 -> 1; 3 -> 2; 4, 5 -> 3. Anyone, Might 1
and Might 2 lift exactly XML1's objects. Remaining deviation: XML1's heaviness 4 (cars, Might rank 3) stays
unliftable because XMen2.exe never lifts 3 (the `cmp ..., 3` at 0x427fa3); an XML2 Fix byte patch of that limit to 4
would remove it, and XML1's heaviness 5 would then need `nopickup` (not set now: the same bit also excludes objects
from the heaviness-limited object attacks at 0x4f2dee). Validator rule: an XML1-sourced entity definition with a
heaviness above 3 (a value the conversion did not touch) is an error.

### TBD.2 Grabbing enemies (the shared `grab` talent)

XMen2.exe's ch_guard_decide (0x4ec090) grabs a target only when the hero's `grab_scale_dmg` talentvalue (string
0x68edac) is above 0.0 (0x4ec3c6-0x4ec407; the global mode byte 0x782728 can skip it) and the target passes
0x429210; otherwise the handler takes action 0x1a. XML2 gives the value through the hidden shared talent `grab`
(talentvalue grab_scale_dmg = 2) that each XML2 hero names at level 1. XML1's handler (0xd99d0) grabs any target
passing the same target test (0x391a0) with no talent gate. The port named `grab` on no hero, so the shared_talents
rule dropped it and no hero could grab. `heroes.hero_entry` now adds `<talent name="grab" level="1"/>` to every hero
entry (GRAB_TALENT); the rule keeps XML2's definition (DESIGN 4.7's list again matches, V-H4 no longer warns).
Budgets: shared talents 61 -> 62, worst party 90 -> 91 of the 92 the danger-room margin allows. The shared `throw`
event's %grab_scale_dmg reference now resolves (2 instead of 0), so thrown enemies take XML2's throw damage scale.
Validator rule (in V-H4): a playable hero without the talent, or no positive grab_scale_dmg, is an error.

### TBD.3 Breakable walls and the ordinary-damage regression

The object structure remap remains: XML1 0-1 -> 0, 2-9 -> 1, 10 -> 2. This opens routes blocked when XML1's
structure 2-9 was copied into XMen2.exe, where structure >= 2 is unbreakable (0x498044). Lifting and the hidden
grab talent remain as described above. **Plain combos can now break the remapped walls too.** The original
punch-versus-power wall restriction is withdrawn; preserving ordinary character damage takes priority.

The initial implementation also mapped attack levels 0-1 -> 0 and >= 2 -> 1, including shared events, styles,
projectiles and gun beams. That broke normal attacks against living enemies. FUN_00429320 compares hit byte
+0x2e with character byte +0x31c at 0x4293e0-0x4293e9 and accepts only unsigned **greater than**, not equality.
A level-zero hit against a normal structure-zero character returns false at 0x42947c. The separate bypass bits
0x00200000 / 0x40000000 mean kill / no-protection; they are not suitable substitutes for normal attacks.

Attack levels are restored to main behavior in every affected path. Shared combat events remain the base
file; styles retain authored values and omitted engine defaults, shared-value rewriting retains its prior
main behavior, projectiles retain their values, and generated gun beams use level 1. Damage amounts, types,
rolls and modifiers are not changed to compensate. The validator no longer requires the rejected zero/one
attack-level mapping. Synthetic regressions exercise default and explicit ordinary attacks through conversion,
including projectiles, and preserve authored zero/power values rather than inventing attack levels.
CONTENT_VERSION stays 11 (unreleased).

Why levelling can hide this: the attack-data constructor defaults the level to 1 (0x4dc603), the hit builder
copies it from attack data +0x1c to hit +0x2e (0x4dc271-0x4dc274), and FUN_0044f770 adds the attacker's
might_structure nibble (actor+0x57b) and rounded damageLevel affecter (actor+0x530), capped at 1. The result is
stored to hit +0x2e at 0x4501fb. Wolverine's Sharpness contributes +3 at its first rank: an auto-spent higher-level
hero can turn the broken zero into one. Character level itself is not read by this attack-level calculation.

### TBD.4 Engine work required for the wall rule (not implemented here)

For unchanged character defense and attack semantics, a normal hit must exceed character structure 0. To spare
an object remapped to structure 1, the hit must be below 1. No integer can satisfy both; the effective attack
level is capped at 1. Changing damage type, adding kill/no-protection flags or weakening character defenses
would alter main combat and is not a faithful builder fix.

XML2 Fix would need a separate object-only attack-level representation/comparison. Retain XML1's original
structure and attack levels in side data, compute the XML1 attack threshold (authored DamageLevel + Might
break strength + affecters), and apply it both to object damage eligibility (0x498044) and object target
collection (0x4de501). Preserve the original/default hit level for the living-character gate at 0x4293e3 and
its damage/defense calculation. Audit the other structure-byte consumers (0x42bdf0, 0x431c57, 0x450be7) rather
than raising the byte's clamp globally. No XML2 Fix change is part of this builder correction.

Remaining approximation: all source structure 2-9 objects map to one breakable class, so normal attacks can
break more objects than in XML1. Class 10 remains immune; script flags and health still apply. Full original
Might thresholds and the punch/power wall distinction remain deferred to the separate engine work above.
