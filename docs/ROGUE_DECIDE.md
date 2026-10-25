# Rogue decide candidate

Use `tools/build_xml1.py --rogue-decide xml1` with the companion XML2 Fix
implementation of gameplay rule **43**, `[Game] Xml1RogueDecide=xml1`. The
recorded content option controls both the style conversion and emitted key.
Rebuilding with the default `--rogue-decide xml2` restores the old collapse and
removes a stale key. Setting the INI alone cannot recreate a dropped node.

The two eleven-rank source chains become public `power2` (`ch_roguedecide`) and
internal `ability_drain`; Special selects drain and Special2 selects
`drain_notarget`. Rank-dependent energy remains on power2 tag 1, with no
time-zero transplant onto drain. Other chains and talent identifiers retain
their existing conversion. The option participates in the profile, build
record, carried-module invalidation and standalone hero checks.

The shipped builder profile stays OFF. CONTENT_VERSION and release identity
are unchanged because its default game output is unchanged. The integrator
must advance the content version and assign the new identity before shipping
enabled output. This experimental developer flag requires the locally built
companion DLL; existing release-version checks alone cannot identify it.

Verify with `python tests/unit/run.py -k rogue_decide`, the full unit suite,
and both content-guard modes from AGENTS.md. The synthetic fixture uses eleven
invented rungs and an OFF serialization hash measured against the source
builder commit. Run the heroes pipeline/self-test on owned inputs before
packaging. No game assets or decoded source data belong in this repository.

For the game agent: compare PC and owned XML1 in xemu, same room/rank/energy.
Check a victim drains, no victim uses `drain_notarget`, a rejected first hit
does not choose a second victim, and every entry charges energy once. Include
no-target mayStart refusal, allies/neutral targets, EntityCapacity and cling
together. Co-op on/on must join; on/off must refuse on both peers naming
`43 Xml1RogueDecide`. The DLL retains XML2's extra validTarget stats-high-bit
lock restriction and native targeting-history writes; those two cases need
explicit live comparison. No live game or co-op validation is claimed.
