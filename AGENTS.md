# Agent guidance for Legends Classic

These instructions apply throughout this repository, including automated pull-request reviews.

## Project and sources of truth

Legends Classic rebuilds X-Men Legends (Xbox) for the X-Men Legends II PC engine using the player's own copies. Faithful XML1 behavior is the priority; do not silently substitute XML2 behavior or rebalance gameplay to make a test pass.

Read `CONTRIBUTING.md` and `LEGAL.md` first. Consult `docs/BUILDING.md`, `tools/xml1build/SPEC.md`, `tools/xml1build/SPEC_heroes.md`, and relevant `research/` notes for the affected subsystem. Research notes record historical experiments: verify their claims against current code and evidence rather than treating every old proposal as current policy.

## Content and privacy boundaries

- Ship our code, original documentation, interoperability facts and synthetic fixtures only.
- Never add game assets, converted output, decoded game data, game dialogue, disassembly/decompiler listings, game screenshots, official logos, modified game executables, ownership bypasses or Steam emulators.
- Never add links to game downloads, disc images or ROMs.
- Never expose tokens, personal paths, email addresses or IP addresses in code, logs, review comments or artifacts. Use placeholders and documentation addresses.
- Inspect content-guard allowlist changes individually. An allowlist entry needs a specific reason and must not excuse prohibited content. Passing the guard is evidence, not proof that every file is appropriate.
- Never modify source game installations or disc images. The builder must remain offline and constrain writes to its output, cache and documented logs/metadata.

## Pull-request review

Review the final diff and enough surrounding code to understand the behavior. Follow callers and consumers across modules when contracts change. Prioritize concrete correctness, data loss, input validation, compatibility, content/privacy violations and regressions over stylistic preferences.

For each actionable finding, give the affected file and smallest useful line range, the triggering conditions, the consequence, and a concise explanation. Distinguish confirmed defects from hypotheses. Avoid speculative findings, duplicate comments, or requesting unrelated rewrites. If no actionable defects are found, say so and state material validation gaps.

Pay particular attention to:

- Package load order, talent/style registration, resource budgets, hero/NPC namespaces, forced parties and save/load behavior. A successful fresh start does not prove a saved-game load works.
- Save compatibility: hero record ordering, talent identifiers, unlock state and existing saves. Do not assume rebuilds may reset player progress.
- Disc and binary parsers: bounds, offsets, lengths, malformed inputs, case normalization and deterministic output.
- Build lifecycle: cancellation/resume, cache identity and invalidation, locking, atomic writes, verification, and safe cleanup. Preserve unrelated files and player saves.
- Launcher-facing contracts: CLI exit codes, JSON-line events, error details, release manifest fields and supported versions. The launcher and xml2-fix live in separate repositories; identify cross-repository dependencies explicitly.
- Versioning: changes to generated game output require `CONTENT_VERSION` in `tools/xml1builder/__init__.py` to advance. Release version changes are separate; do not bump versions or publish releases merely to resolve a review comment.
- Documentation claims: distinguish automated campaign checks, scripted boss defeats, human playthroughs, and actual internet co-op testing.

## Validation

From the repository root, use the relevant existing checks:

```
python tests/unit/run.py
python tools/check_no_game_content.py --all
python tools/check_no_game_content.py --self-test
```

The `--all` guard checks tracked files; also check newly added/staged files before committing. Use focused synthetic regression tests for behavioral changes. Do not create tests that merely restate the implementation.

Pipeline-output changes also need a build from legally owned inputs and relevant pipeline self-tests, as described in `docs/BUILDING.md`. Game-dependent tests never run in public CI. When those inputs or a Windows game runtime are unavailable, perform the available checks and clearly report the missing validation; never claim it passed. Runtime fixes should reproduce the reported sequence and, where practical, compare against a negative control.

Do not launch focus-grabbing game or launcher windows without knowing the maintainer is available for testing. Keep generated game files, caches, screenshots and saves out of commits and PR attachments.

## Making changes and managing PRs

Keep changes scoped to the reported problem and preserve unrelated work. PR descriptions should explain the user-visible problem, resulting behavior, validation performed, limitations and any companion-repository requirement. Update specifications or the changelog when the change warrants it.

Reviewing a PR does not authorize merging it, changing repository visibility, publishing a release, creating release tags, deploying, or sending community announcements. Carry out those actions only when explicitly authorized by the maintainer. Do not commit, push, or edit a contributor's branch as part of a review unless requested.
