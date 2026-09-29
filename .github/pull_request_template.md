## What and why

<!-- What does this change, and why? For pipeline changes: what changes in a build, and was CONTENT_VERSION bumped? -->

## Checklist

- [ ] `python tests/unit/run.py` passes
- [ ] `python tools/check_no_game_content.py --all` passes (the pre-commit hook runs it on what you stage)
- [ ] no game files, decoded game data, game text beyond a few words, disassembly, screenshots or personal data
      (see CONTRIBUTING.md)
- [ ] for pipeline changes: built on my own PC with my own copies; what changed in the build is described above
