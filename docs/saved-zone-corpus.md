# Offline G3 corpus expectations

Run `tools/check_saved_zone_corpus.py` against the native `lcsave_real_saves`
host and a finished W2, XML1-economy build. This wrapper keeps the host's raw
verdicts and exit code, checks every input, and reports loads separately from
expected refusals. Use a new output directory for each run. If `--out` already
exists the gate refuses before the host starts, naming the flag; pass
`--replace-existing` to move the old directory aside to
`<out>.superseded-<UTC stamp>` (never deleted) and run into a fresh, empty one:

```
python -B tools/check_saved_zone_corpus.py --host <lcsave_real_saves.exe> --list <unique-list.txt> --data <finished-build> --out <new-results-directory>
```

The original collection has 148 unique saves, including one experimental
save that does not belong to the successful-load set. Its SHA-1 is
`d1e97a5e373e0cb1064d40ba46743af1db0070bb`. It is byte-identical to the
loot-cap experiment's `raised-224-player-save.lcsave`, produced by a private
224-definition table containing 134 invented equipment definitions and two
plain-item probes. It was collected under the id `d1e97a5e373e`.

The file's KEYS section records `capacity_probe_160`, `capacity_probe_222`,
and `capacity_probe_223` as ITEM ids `0x020000a4`, `0x020000e2`, and
`0x020000e3`. Its last two definition counters are 1 and 23. The experiment's
`prepare_synthetic.py`, `synthetic-catalogue.json`, `synthetic-audit.json`,
and `cold-definition-state.json` independently establish these names,
identities and staged values. The original G3 report already described the
deleted synthetic build; treating its refusal as a player capacity failure
lost that provenance.

Normal builds lack those invented definitions. Their refusal prevents losing
the saved state or mapping it onto unrelated items. The wrapper accepts only
the exact input digest, campaign kind, successful dump, failed W2 load, and
the single current missing-item diagnostic for `0x020000e2`. Any other error,
additional failure, changed input, successful load, missing verdict, duplicate
id, wrong native exit, or wrong corpus count fails the gate. No wildcard or
path-based exclusion is used, and the fixture remains in the corpus.

The corrected result is **148/148 expectations: 147 successful loads and one
expected refusal**, not 148 successful loads. Raw native results remain
147/148 loads and exit 1. No builder data, runtime limit, save format or player
save migration changes are needed. Existing released saves retain the same
load behavior. A future legitimate definition with these identities would
require reviewing this negative fixture rather than silently accepting it.
