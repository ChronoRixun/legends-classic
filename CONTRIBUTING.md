# Contributing

Thanks for helping. This project rebuilds a game from copies its players own, so it lives or dies by one rule:
**the repository holds our code and our words, never anything from the games.**

## What may go in

| OK | Examples |
|---|---|
| Our code | the builder, the pipeline, the prepare stages, format readers and writers, the test harness |
| Our documentation of formats and engine behaviour | addresses, offsets, struct layouts, what a function does - in our own words |
| Facts and interoperability tables | script-function names and signatures, console command names, zone ids, file names, stat names, hashes of known-good inputs |
| Short byte signatures used as guards | the few-byte "is this the retail code" checks |
| Synthetic test fixtures | images, bundles, sound banks and XML made up by the tests themselves |

## What never goes in

| Never | Examples |
|---|---|
| Game files or pieces of them, from either game | `.igb .xmlb .engb .chrb .navb .boyb .pkgb .zsm .zss .sfd .fb .xbe .exe .dll` of the games, decoded dumps of them as text |
| Anything derived that still carries game content | converted sound banks, rewritten scripts, generated dialogs or missions, a build folder or any part of it |
| Game text | dialogue, objectives, character bios, item text, UI strings, subtitles - beyond a few words quoted in a design note (paraphrase instead: "the game-over dialog", "the line that starts the cut mission") |
| Disassembly or decompiler output | `.asm` listings, decompiled C, pasted instruction listings - describe the code in prose with addresses instead |
| A modified exe or DLL of the games | the project never patches game files; [xml2-fix](https://github.com/ChronoRixun/xml2-fix) patches in memory |
| Game art, logos, box art, screenshots | also not in the README or issues; the names only, as plain text |
| Links to disc images, ROMs or download sites | anywhere: code, docs, issues, discussions |
| Personal data | your user-profile paths, IP addresses, e-mail addresses, tokens |

## The content guard

`tools/check_no_game_content.py` enforces the list above on every commit and in CI (standard library only):

```
python -m pip install pre-commit
pre-commit install                                   # runs the guard on what you stage
python tools/check_no_game_content.py --all          # every tracked file
python tools/check_no_game_content.py --self-test
```

Without pre-commit, a plain hook does the same: put `exec python tools/check_no_game_content.py --staged` in
`.git/hooks/pre-commit`.

Your own patterns (your name, your PC's name, your LAN prefix, your drive layout) go in
`.git/info/content-guard-deny`, one regular expression per line: the guard reads that file, git never commits it.

If the guard flags something that really is ours and fine, add an entry with a reason to `.content-guard-allow`;
reviewers look at every new entry.

## Code

- Python 3.14, the standard library + numpy in the builder and the pipeline (see `requirements.txt`); anything else
  only in developer tools.
- Run `python tests/unit/run.py` before a pull request (no game data needed). Changes to the pipeline's output also
  need a build on your own PC and a note of what changed; bump `CONTENT_VERSION` in `tools/xml1builder/__init__.py`
  when a build's output changes.
- The builder makes no network connections and writes only to `--out`, its cache and its log. Keep it that way.
- Tests that need the games (the `*_selftest.py` modules, the harness) run only on your own PC, never in CI.

## Bug reports

Use the bug report form. It asks for:

- the builder version (`xml1-builder --version`) and how you ran it (launcher, release zip, source);
- the error code and stage, or what went wrong in game;
- `_build\verify-report.json` (file names, sizes, hashes, versions and codes - no content) and the last lines of
  `_build\builder.log`.

Never attach the disc image, the build folder, the cache, save files or any game file.
