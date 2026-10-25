# Local release validation

Run these gates for every release candidate, after its final content build and before publishing.
For tag naming, beta flags, notes and exact publishing commands, see [RELEASING.md](RELEASING.md).
Use legally owned inputs and a separate output/cache folder. Keep game files and logs containing
game content out of Git and public CI artifacts.

- [ ] Assign the release identity first (a new `CONTENT_VERSION` in `tools/xml1builder/__init__.py`, its lobby token
  row and recorded fingerprint in `tools/xml1build/release_identity.py`) whenever generated game output changed. A
  release branch keeps the previous release's identity until this step (0.4.0-beta.7's branch carried beta 6's
  content 26 / LC35 until this step assigned content 27 / LC36: the old identity reproduces beta 6's issued
  fingerprint, so the content rebuild would not trigger); a private candidate identity commit (e.g. candidate/070a,
  candidate/070b) is never merged.
- [ ] Run `python tests/unit/run.py` and both content guard modes (`--all` and `--self-test`).
- [ ] Build the candidate from prepared sources and require zero build/validator errors.
- [ ] From `tools/`, run `python -m xml1build.zones_selftest "<candidate output>" --base "<XML2 install>"`.
  Require exit code 0 and `RESULT: PASS`; preserve the command, output and candidate revision in
  local release evidence. Run this again after any change to the candidate's zone output or the test.
- [ ] If a zones self-test expectation changes, trace it to the behavior-changing commit, audit the
  built files against that contract and run synthetic tests that reject unrelated changes. A known
  failure is a blocked gate until investigated; do not waive it by broadly allowing replacements.
- [ ] Run the other affected pipeline self-tests and the runtime checks required by the change.

The full zones self-test reads the player's game data and runs locally, never in public CI.
Its synthetic expectation tests (`tests/unit/test_zones_selftest.py`) run in the existing unit-test
CI job on Windows and Linux. This checklist does not authorize publication.
