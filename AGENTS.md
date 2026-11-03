# Agent guidance for Legends Classic

These instructions apply throughout this repository, including automated pull-request reviews.

## Project and sources of truth

Legends Classic rebuilds X-Men Legends (Xbox) for the X-Men Legends II PC engine using the player's own copies. Faithful XML1 behavior is the priority; do not silently substitute XML2 behavior or rebalance gameplay to make a test pass.

Read `CONTRIBUTING.md` and `LEGAL.md` first. Consult `docs/BUILDING.md`, `tools/xml1build/SPEC.md` and `tools/xml1build/SPEC_heroes.md` for the affected subsystem. Use `docs/CLI.md`, `docs/SAVES.md`, `docs/ONLINE.md`, `docs/COMPATIBILITY.md` and `docs/KNOWN-ISSUES.md` for player-facing contracts. `docs/ROADMAP.md` describes plans; research notes describe historical experiments. Verify both against current code.

The 0.6 line adds in-game online screens and joining a running campaign. XML2 Fix owns the engine hooks, GameNetworkingSockets transport and broker client; Ultimate Legends installs and updates the builder and companion fix, runs builds and manages mods. Both live in separate repositories. Save import from xemu and XML1-recomp is planned for a later 0.6 beta; do not describe it as shipped without checking the implementation and release evidence.

## Content and privacy boundaries

- Ship our code, original documentation, interoperability facts and synthetic fixtures only. Never add game assets, converted output, decoded game data, dialogue, disassembly/decompiler listings, game screenshots, official logos, modified game executables, ownership bypasses or Steam emulators.
- Never add links to game downloads, disc images or ROMs. Never expose tokens, personal paths, email addresses or IP addresses in source, logs, reviews or artifacts; use placeholders and documentation addresses.
- Review each `.content-guard-allow` change and its specific reason. Passing the guard does not prove content is appropriate.
- Keep the builder offline. Read source installations and disc images without changing them; constrain writes to the output, cache and documented logs/metadata. The launcher's downloads and the game's online transport are separate from the builder.

## Pull-request review

Review the final diff, surrounding code, callers and consumers. Prioritize correctness, data loss, malformed inputs, compatibility, content/privacy violations and regressions. Give each actionable finding a file, the smallest useful line range, trigger, consequence and explanation. Distinguish defects from hypotheses; avoid duplicates and unrelated rewrites. If there are no actionable findings, say so and state material validation gaps.

Pay particular attention to:

- Package load order, talent/style registration, resource budgets, hero/NPC namespaces, forced parties and save/load behavior. A fresh start does not prove an existing save loads.
- Save ordering, talent and item identifiers, catalogue/binding compatibility, unlocks and saved-zone records. Preserve player progress and backups; consult `tools/lcsave/README.md` and the release checklist for save gates.
- Binary parser bounds, lengths, offsets, case normalization and deterministic output; cancellation/resume, cache identity, locks, atomic writes and safe cleanup. Preserve unrelated files and mods, including player-selected INI values.
- CLI exit codes, JSON-line events, error details, manifests and companion-version requirements. Identify required changes in the launcher or XML2 Fix explicitly.
- Online identity and agreement, menu/DLL capabilities, transport selection, late join, disconnect/rejoin and mixed-version refusal. Test two through four players where relevant; distinguish same-PC, LAN, internet and relayed coverage.
- Output identity: `VERSION` and `CONTENT_VERSION` live in `tools/xml1builder/__init__.py`; official content/catalogue tokens live in `tools/xml1build/release_identity.py`. Flag output changes requiring coordinated identity updates. Let the maintainer assign them; do not bump versions or append reservations merely to fix a review comment.

## Validation

From the repository root, use the relevant existing checks:

```
python tests/unit/run.py
python tools/check_no_game_content.py --self-test
python tools/check_no_game_content.py --all
```

CI uses Python 3.14 and `requirements.txt`, on Windows and Linux. The unit runner imports `test_*.py` modules and calls their module-level `test_*` functions without pytest; it injects only `tmp_path`. Use standard-library assertions/unittest helpers and `unittest.SkipTest`; do not require pytest imports, marks or other fixtures, or assume TestCase methods alone are collected. Focus with `python tests/unit/run.py -k substring`.

Windows checkout can use `core.autocrlf=true`. Keep hash-pinned or byte-sensitive fixtures exact with scoped `.gitattributes` `-text` rules (as for `tools/xml1build/fonts/**`); a passing LF-only checkout is insufficient evidence.

`--all` checks the Git index, so also pass new paths to the guard or check `--staged` after staging is authorized. CI additionally guards changed/history blobs, builds and self-checks the sound kernel, and runs release-policy/frozen-package checks; read `.github/workflows/` when changing those areas.

Use meaningful synthetic regressions. Pipeline-output changes also need owned-input regeneration and relevant self-tests from `docs/BUILDING.md`; save changes need the gates in `docs/RELEASE_CHECKLIST.md`. Game-dependent checks stay off public CI. Report checks that are unavailable; never claim automated checks prove a human playthrough or internet co-op.

Do not launch games or launcher windows without authorization for that testing. Keep runtime checks in disposable copies, preserve saves and the owner's desktop, and keep generated output, caches and captures out of commits and PR attachments.

## Making changes and managing PRs

Keep changes scoped and preserve unrelated work. Explain the user-visible problem, resulting behavior, validation, limits and companion-repository requirements; update specifications or the changelog when warranted.

A review does not authorize committing, pushing, editing a contributor's branch, merging, changing visibility, tagging, publishing, deploying or sending announcements. Obtain explicit authorization for those actions.
