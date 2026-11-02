# Rogue decide candidate

Since 0.4.1-beta.1 (the port's beta 8) `--rogue-decide xml1` is the default,
with the companion XML2 Fix 1.9.0-beta.1 implementation of gameplay rule **43**,
`[Game] Xml1RogueDecide=xml1`. The recorded content option controls both the
style conversion and emitted key. Rebuilding with `--rogue-decide xml2` restores
the old collapse and removes a stale key (A/B builds). Setting the INI alone cannot recreate a dropped node.

The two eleven-rank source chains become public `power2` (`ch_roguedecide`) and
internal `ability_drain`; Special selects drain and Special2 selects
`drain_notarget`. Rank-dependent energy remains on power2 tag 1, with no
time-zero transplant onto drain. Other chains and talent identifiers retain
their existing conversion. The option participates in the profile, build
record, carried-module invalidation and standalone hero checks.

The beta 8 integration turned the option on by default, which changes the
default game output: the 0.4.1 release must advance the content version and
assign its new identity (the private candidate 0.8.0a used content 37 / C08A).
The builder's DLL gate refuses a companion that does not know the key.

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
