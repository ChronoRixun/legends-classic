# Opening fire damage: amounts, scheduling and impact attribution

## Follow-up: startup delay and repeated contacts

The 0.2.3d follow-up trace identifies additional repeat requests from repeated
contact by the same hero with one hazard. Several party members or overlapping
fire placements are not required. Each native touch can add a chain because the
harm handler clears pending after the base action schedules its repeat.

The XBE has the same relevant sequence: touch 0x27310, request 0x27a60, callback
0x27510, repeat scheduling 0x28420 and final pending clear 0x46dbf. This does not
establish identical console damage rates, which remain unmeasured, but it
contradicts an assumed code-level single-chain guarantee.

Likewise, original `firstact=1` is creation-relative. The parser posts the first
activation independently of contact. The optional startup adapter in SPEC 51
preserves that delay without clearing the visible loop; it does not impose an
entry grace period or remove touch-created chains. A separate gameplay rule is
needed for that adapter. A one-chain/per-entry-delay policy needs an explicit
behavioral decision and must not be called proven original behavior.

The companion now provides an opt-in `HarmSingleChain=single` candidate. It keeps
the native pending bit after harm completion and immediate-request completion,
while the delayed callback still clears it before scheduling the next repeat.
One live walking/re-entry run retained exactly one pending repeat despite 528
contacts, with native three-point fire hits and no damage in either outside
tail. Candidate 0.2.3e registers it as rule 23 and turns the builder default on; a per-entry grace period is not implemented.

Investigation against the original Xbox executable and the PC executable used by
the port. The raw damage and repeat delays are preserved, but the PC box
dispatcher supplies a different impact origin. An opt-in companion-engine
candidate restores that original argument without changing builder data. The
original-console damage rate has not been measured.

## Confirmed box-origin difference

Original box service 0x5a8f0 passes zero to the dispatcher at 0x5a9b9-0x5a9d5;
PC 0x451ba0 passes the box centre at 0x451c6e-0x451c79. A zero origin skips
direction generation in the dispatcher. The original actor hit context at
0x44fb0 then reconstructs direction from victim/attacker entity origins. PC's
equivalent fallback at 0x436870 is bypassed by its explicit centre-based vector.

At the tested fire centre these yield opposite vertical signs: the native party
knockback call receives +0.55 on PC and -0.45 on the original-compatible path,
both at strength 100 from authored knockback 200. PC repeatedly lifts the idle
hero and adds touch activations; the correction keeps the hero on the floor.

Standalone, level-five survival diagnostics measured approximately 68-72 HP/s
before and 15-20 HP/s after during five-second no-input windows. Maximum/current
health was staged high to survive; native damage remained 3 per hit. These are
measured PC contact histories, not original-console DPS or a universal cap.
Short fixed-input edge contacts lost 33 HP before and 36 HP after; the correction
does not reduce every walking contact. Verified outside-fire tails showed no
damage over five seconds on either path.

With native health instead of survival health, the level-five hero started at
100 current HP and died on the 34th three-point hit: 0.752 game-seconds from first
hit to fatal hit before, 6.484 seconds after. Position setup was floor-verified
and disclosed; no input was sent during that exposure. This still does not
measure original-console DPS.

The companion `BoxHarmOrigin=xml1` hook changes only the box dispatch origin,
retaining the spatial query, radius path, damage, authored repeat settings and restored bounds.
The zero origin also selects the native default 0.01 dispatch delay. Candidate
0.2.3d registers requested-only rule 21 and enables the builder default; versions
and saved-content identity remain unchanged. The scope census is 137 definitions / 419 placements / 66 zones, with
all 348 map files unchanged; runtime coverage is the opening fire only.

## Authored damage and bounds

The small opening-room fire is authored with damage 3, fire damage type,
knockback 200, no-pain damage modifier, touch activation, and a fixed 0.4-second
repeat delay. Its original first activation delay is one second. There are seven
placements. The room also contains two separate, underground 32000-damage volumes.

The converted output preserves those amounts, repeat delays, targeting fields and
placement geometry. The start-on loop conversion advances the small fire's first
activation to zero (SPEC 51); the bounds correction adds residency and its marker
(SPEC 97). The nine source world boxes and converted local boxes agree after
translation. None of the nine boxes overlap; only one intersects the western
small-fire contact position, including the sampled hero's footprint.

The original affectable-harm parser is **0x46f10**, not 0x7c440. The latter parses
the separate harm-target class. Original 0x46f79-0x46f99 resolves the damage with
the values getter and a null maximum, then stores a signed short at entity+0x2d4.
PC 0x4396fe-0x439737 follows the same single-value conversion, sign-extends it and
stores a float at entity+0x32c. Literal 3 therefore remains 3. Neither parser
multiplies this literal by hero level, map level or difficulty.

Actor attack-stat scaling is conditional on the source being an actor in the
receive paths (original 0x45260, PC 0x437490). An ordinary environmental harm
entity does not pass that class test. Recipient resistance, immunity and other
combat state still matter; unchanged raw damage alone does not establish all
effective damage outcomes.

## A repeat delay is not a contact cooldown

Both engines distinguish `actrescheduledelay` from `actinactivedelay`. The latter
is the minimum activation gap, and defaults to zero in the action constructor.
The former schedules another activation after a successful one.

| Operation | Original Xbox | PC |
|---|---:|---:|
| Action activation and repeat scheduling | 0x28420 | 0x41b5b0 |
| Enabled/pending/inactive-delay gate | 0x27410 | 0x41a820 |
| Immediate or delayed activation request | 0x27a60 | 0x41a890 |
| Delayed activation callback | 0x27510 | 0x41a5b0 |
| Ordinary affectable-harm activation | 0x46cc0 | 0x439a90 |
| Box damage dispatch | 0x5a8f0 | 0x451ba0 |
| Queue one pending area hit per target | 0x93be0 | 0x499b10 |

The delayed callback clears the pending-action bit before dispatch. The action
handler can schedule its next repeat; the enclosing harm handler clears the bit
again at its end. A subsequent touch can therefore start another repeat chain.
The reviewed original and PC paths both have this behavior. Both damage queues
reject a second hit while the target already has one queued; this is not a
0.4-second damage cooldown.

Consequently, 3 / 0.4 = **7.5 HP per second is only the nominal rate of one repeat
chain**, before resistances and scheduling quantization. It is not a proven
ceiling for contact damage. Adding an inactive delay equal to the repeat delay
would change original behavior, rather than merely preserve an authored field.

Historical PC observations of the bounds candidate show one western hazard with
multiple activations in the same game frame and 3-HP actor losses separated by
as little as 0.2 game-seconds. They were collected under heavy instrumentation:
approximately 180 wall-seconds elapsed over 23.6 game-seconds. They are unsuitable
for a wall-clock damage-rate claim and are not a level-five test.

## Fire effects are not proof of damage over time

The original fire-hit effect helper is 0x5d5c0, selected by original damage type 4.
Its PC counterpart is 0x454290, selected by fire mask 0x10000. Both request the
fire effect/sound and an additional ordinary impact effect for appropriate
attack categories. Neither helper creates a damaging burn powerup or schedules
a health subtraction. The PC render-effect name `burning` is a separate visual
flag (0x200); its existence does not establish a damage-over-time mechanic.

The original and PC effect files selected for a fire hit both specify a
0.1-second effect loop time, 0.4-second flame-particle lives and 0.15-second flash
lives. These are visual component timings, not health-damage ticks. Repeated hit
effects can overlap without a stacking damaging burn status.

In the historical bounds trace, the later 10.416667-HP losses have **direct
damage type 0x80** and originate in physical impact handler 0x499100, at return
sites 0x4994cc and 0x499724. They must not be described as burning ticks. An
attacker handle retained from an earlier fire hit also does not turn impact
damage into fire damage.

## Acceptance boundary

Do not lower the source damage, remove touch activation, add a cooldown, reduce
bounds or revert hazard residency based solely on the nominal-rate calculation.
The box-origin candidate has the demonstrated native difference, negative
control and predicted direction change. It uses requested-only gameplay rule 21; wider room/difficulty/co-op acceptance remains. Original-console contact
cadence, frame-rate sensitivity, four-hero exposure and full normal-health
traversal remain separate questions from the successful controlled diagnostics.
