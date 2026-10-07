# Issue #10 validation

STAT pickups call the XML2 Fix 1.3.2 companion's `addStatPoints` with the actual
collector. The original fixed-body activation is removed; item identity and placement
are retained. Version 1.3.1 remains reserved for FightStyles and geometry sharing.

## Controlled native pickup comparison

Two fresh processes used the same isolated Sewers build and original `item_stat`
placement. The baseline replaced only the STAT item's activation with the previous
fixed-body call; the candidate restored the generated activation. Wolverine and
Cyclops were protected, the companion's AI was disabled, and Wolverine was positioned
near the pickup. Ordinary movement input then triggered native touch collection.
The test did not call `addStatPoints` directly or edit any character counters.

- Baseline: Wolverine's Body changed from 20 to 34 in this run; remaining stat points
  stayed zero. The native stats screen showed the resulting Body value.
- Candidate: Wolverine's remaining points changed from zero to one, with Body still
  20. Cyclops and every other registered hero remained unchanged. Both heroes' XP,
  levels and skill-point counters were unchanged. A read-only comparison of the saved
  stat block found only the collector's unspent-point word changed.
- A normal save in the isolated save folder was loaded through the game's UI in a
  fresh process. The collector still had one point and the compared blocks/counters
  matched the post-pickup snapshot. No save was synthesized or rewritten by the test.
- Spending that point through the native stats screen raised Focus from 12 to 13,
  left Body at 20 and reduced remaining points to zero. Cyclops remained unchanged.

Screenshots, read-only stat samples, game logs and the test save remain local and are
not committed or attached to the PR. This is a controlled pickup test, not a campaign
playthrough; multiplayer and automatic stat spending were not exercised.

## Automated checks

209 synthetic builder tests pass; the full owned-input build reports zero errors.
Scripts self-tests T1-T7 and the zones self-test pass. Native stat-point rules and the
existing script-registration suite report zero failures. Content checks and independent
review found no remaining actionable issue. Both builder and engine PRs are drafts.
