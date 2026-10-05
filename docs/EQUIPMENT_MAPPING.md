# Equipment mapping audit (issue #6)

This is an opt-in translator and a read-only coverage report. **No item is added to
builds yet.** Drops, item definition order, enhancement record order and saves stay
on the existing build path. `frontend.translate_equipment(ctx, item)` retains its
previous output; `expanded=True` selects the new mapper. The full table belongs to
the later save-format release. There is no builder CLI switch enabling it and no
content-version bump.

Run against your own decoded inputs:

```
python tools/equipment_report.py --items <items.eng> --values <values.xml>
python tools/equipment_report.py --items <items.eng> --values <values.xml> --json
python tests/unit/run.py -k test_equipment
```

The report writes only to stdout. `full` means every listed bonus has an emitted
mapping; it does **not** mean exact fidelity. `partial` means at least one bonus
was emitted and at least one was rejected; `none` means no bonus was emitted.
Every bonus also has an independent `exact`, `approximate` or `unsupported`
classification and explanation. There is no built-in item table or game text.

## Evidence and scope

Addresses below are virtual addresses in retail `default.xbe` (base `0x10000`) and
the unpacked PC `XMen2.exe` (base `0x400000`). They identify applying code, not just
matching strings. The verification column distinguishes controlled runtime measurements from static-only
traces. Runtime measurements use an isolated build, an unmodified executable and
xml2-fix 1.3.1. They do not establish full campaign or save compatibility.

XML1 resolves bonus names at `0x946f0` over 59 entries at `0x44e8c8`; unknown names
become `none`. XML2 resolves 95 names at `0x534d90` over `0x6ddb18` (94 distinct IDs:
`damage` and `atk_damage` alias ID 57; ID 54 has no name). `combat_events.AFFECTERS`
is the complete registry, checked against the executable by `verify_exe`.
Registration alone does not prove a useful item effect.

XML1's `0x955c0` reads the level minimum and maximum through `0xb7e60`; a symbolic
value must be resolved from the player's values file. `0x2a220` combines matching
levels by addition, multiplication, maximum or minimum, and `0x2a400` samples the
combined range. `user1` is a separate integer: `0x2a4b0` combines it independently.
XML2's corresponding reader is `0x534ff0`, range aggregator `0x54ff80`, sampler
`0x550410`, and actor cache dispatcher `0x53a1a0`, rebuilt by `0x53bf20`.
Cached attributes have their own aggregation rules and often consume one endpoint.

Both scope parsers combine multiple attack/damage categories as a union and
different categories as an intersection (XML1 `0x955c0` / `0x94f00`; XML2
`0x5352f0` / `0x544230`). XML2 accepts `<scope>` children on the affecter itself;
`0x535337` folds them through the same parser. The mapper therefore keeps one
enhancement for a bonus with multiple scopes, avoiding duplicate bonuses on an
overlapping match. Race names are validated against XML2's enum at `0x6d9710`.
Unknown damage names silently default to physical (`0x43bd70`), so the mapper
rejects them. Other unhandled attributes, callbacks, nonpermanent life and invalid
numeric inputs are explicit losses, rather than silently discarded constraints.

## Implemented mappings

“Exact” describes the named bonus contribution and its aggregation for the
accepted input form. It does not claim identical baseline hero statistics, AI,
damage scaling or the entire combat pipeline. Rows not explicitly measured remain static-only.

| Source bonus | XML1 applying code and units | XML2 applying code and emitted form | Fidelity / numerical difference | Verification |
|---|---|---|---|---|
| `health_regen`, additive integer | `0x3a950`: integer nominal HP/s coefficient; delay `5 / regen_scale` seconds after damage; maximum `user1` cap as percent of maximum HP (`0x3aa66`, `0x2a4b0`) | `health_regen` additive; optional second `health_regen max` with `user1/100`. Cache `0x53a1a0` cases 22/23; rate/cap `0x42cc60` | Approximate. Same nominal rate coefficient and cap, but starts immediately. Both engines apply fixed 0.1-times-rate ticks; late scheduling lowers healing per elapsed second. The earlier 20-HP/five-second example assumed ideal tick timing and is not a measured guarantee. XML1 selects the highest cap; XML2 takes the lowest cap, initialized to 1.0 (`0x539df0`, helper `0x419e60`). | Runtime: level 4, user1=100; 30-second A/B. Other caps/stacking static |
| `energy_regen scale S` | `0x3a950`, `0xaf860`: hero rate `truncate((maxEP/60 + add) * S * (1+mind/100))` | `energy_regen scale S`; cache case 24, rate `0x42cc60` | Approximate. Preserves S, but XML2 lacks the mind factor and keeps fractional rates. At maxEP 120, mind 20, S=1.5: XML1 3 EP/s, XML2 3 EP/s; at mind 50: XML1 4, XML2 3. Baseline pools can also differ. | Static only |
| `def_damage` additive | `0x45260`, arithmetic `0x45518`: subtract HP, floor at zero, then apply defense scale | Unscoped `def_damage`; scoped `def_damage_scope`. Cache case 39, combat `0x437490` / `0x4379e6` queries ID 56 then combines cached ID 39 | Exact for integer flat reductions. A 20 HP hit with +7 armor becomes 13, not 18.6. Fractional reductions are approximate because XML1 truncates integer damage. | Runtime: unscoped +7 only; 26 control hits at 20 HP, 26 item hits at 13 HP |
| `def_damage scale S` | Same consumer: `truncate(max(0,D-A) * S)` | Same attributes with `affect_type=scale`, `0x437490` | Approximate: same multiplication, XML2 keeps fractional HP. Difference less than 1 HP at this stage before later modifiers. Scoped resistance must use the contextual ID 56, not a cached global value. | Static only |
| `critical` additive L | `0x5c020`, `0x5c12c..0x5c1da`: `0.02*L` probability on punch/kick/throw | `critical level=0.02*L`, cache case 70, roll `0x452f20` | Approximate. Same additional probability on eligible targets: L=3 gives +6 percentage points. XML1 rejects structure >=10; XML2 >=2 (`0x41d550` is the structure setter). The measured fixture supports the incremental chance; other structure classes and attack types remain unverified. | Runtime: punch, source level 3, structure 0; 11/1,000 vs 67/1,000 criticals |
| `accuracy` additive L | Other branch of `0x5c020`, `0x5c0d2..0x5c127`: non-melee critical probability, **not hit rating** | `atk_critical level=0.02*L`, scoped to direct/blast/projectile/beam/crush/psionic; `0x452f20` queries ID 63 before its melee branch | Approximate for the same structure-eligibility reason. L=2 adds 4 percentage points; it adds zero attack-rating points. Both attack enums are identical (`0x59740`, `0x44ebc0`). | Static only |
| `deflect_damage` additive L | `0x43fa0`, `0x44250`: roll against L/100; return copied incoming attack and cancel original damage | `deflect_damage level=L/100`; `0x435440`, queries `0x435762` / `0x435773` | Exact chance and return/cancel operation for the accepted additive form. L=35 becomes 0.35. Scoped rolls remain scoped. | Static only |
| `reflect_damage` with `user1` 0 or 100 | `0x44168..0x4422f`: fixed returned `truncate(sum(level)*product(scale))`, with integer percentage gate (`user1=0` means no gate) | Additive `reflect_damage` plus a **zero scale** affecter, `0x436ae0..0x436c38` | Approximate. XML2 otherwise returns `incoming*scale + add`, so copying L alone would add the entire incoming hit. Zero scale preserves fixed amount, but XML1 reflection runs before final damage resolution; XML2 runs later and changes reflected flags. | Static only |
| `move scale S` | `0x38270`: multiplicative movement factor | `move scale S`, cache case 9, `0x428980`: clamp `(1+add)*scale` to `[0,max]`, default max 2.5 | Approximate. Same factor below the cap; combined factor 3.0 becomes 2.5. | Static only |
| `def_knockback scale S` | `0x45634..0x45676`: scale incoming knockback and convert to integer | Same name and scale; cache case 40, `0x437490` uses cached factor | Exact multiplier/product for unscoped scalar inputs. S=0.6 turns 200 into 120. | Static only |
| `def_pain scale S` | `0x394e0`, `0x395c3`: pain animation rate `clamp(1/S,0,10)`; `0x44410` suppresses pain when zero | Same name and scale, cache case 42; `0x428af0`, `0x435850` | Exact corresponding animation-rate factor, not flat damage resistance. S=0.4 means playback rate 2.5. | Static only |
| `drain_time scale S` | `0xd75a0`: modify life of a `drain_victim` attachment, `(life+add)*S` | Same name and scale; cache case 72, `0x5370b0` / `0x5372e0` | Exact duration multiplier when a `drain_victim` powerup is actually attached. S=1.2 maps 10 seconds to 12. Registration does not prove the converted hero currently uses that powerup. | Static only |
| `xp scale S` | `0x33170`: apply `(award+add)*S` before adding XP | `xp scale S`, cache case 73; kill-award path `0x436c50`, add `0x437408` / multiply `0x437437` | Approximate. XML2 direct award `0x422350` -> `0x4b79b0` bypasses this cache. At S=1.1, a direct award of 100 stays 100 instead of 110. | Static only |
| `damage` | `0x5cca0`: resolve range, apply source damage contribution, integer conversion | `damage`; `0x453a60` / `0x453bb6`: sample range and add `ceil(base*(scale-1)+add)` | Approximate integer rounding; up to 1 HP difference at the contribution stage before later multipliers. Ranges and scopes are preserved. | Static only |
| `atk_damage`, `atk_damage_scale` | `0x29fd0`, switch at `0x2a114`: separate final `(damage+add)*scale` stage; reads **minimum only**, regardless of `affect_type` | `damage` additive/scale at `0x453a60` | Approximate stage change. Base 100, earlier damage +10, final attack x1.2 yields 132 in XML1 versus 130 with XML2's merged terms, before rounding. | Static only |
| `atk_knockback_scale` | `0x29fd0`: minimum-only product in attack-modifier pass | Same name, `0x54f900` (ID 61); name selects multiplication | Exact corresponding multiplier with the shared knockback threshold rules. No additional `affect_type=scale` is needed. | Static only |
| `power_cost scale S` | `0x3f410`: additive then multiplicative energy cost | Same name/form, `0x4318d0`; SPEC 24 | Exact cost multiplier. | Static only |
| Stat bonuses | XML1 trait values, existing port conversion described in SPEC 21 / SPEC_heroes | Existing `stat_scale`: 4 for strength/body/mind; 2 for speed/traits; XML2 cache cases 2..6 | Approximate port stat conversion; explicitly reported, not called exact. | Static only |

## Deliberately unsupported

- Probabilistic `reflect_damage`: XML1 uses an independent `user1` roll, XML2's
  affecter always fires. A smaller every-hit amount is not an equivalent proc.
  For fixed returned damage R and probability p, pR every hit matches one item's
  mean but removes variance `p*(1-p)*R^2`, changes lethal-hit timing, and fails to
  reproduce XML1's combined `user1` stacking. Engine support needs the probability
  gate in the reflect path. XML2 `hurt_attacker` is also not a substitute: its
  consumer `0x547fb0` imposes a one-second per-attacker cooldown.
- `func_damage=damageaddattack`: XML1 dispatch `0x2dee0` selects `0x2cca0`, with
  attack construction `0x2c970`. It copies damage type/mods, samples the integer
  level range, and adjusts damage level; same-type/same-mod attacks are treated
  specially. XML2 `class=add_attack` (`0x545670` parser, `0x545740` consumer) has
  `damageSum`, `damagePercent`, `damageType`, `mirror`, but merges matching types
  into original damage and uses different flags/level rules. A faithful mapping
  needs that secondary-attack behavior, including `damageMod`, established first.
- `func_damage=damageaddbleed`: XML1 `0x2dd90` attaches a victim effect, excludes
  robots, uses integer `user1` seconds and level damage, and ticks through
  `0x2ce70`. XML2 `add_harming` (`0x545250` parser, `0x545370` consumer) attaches
  shared bleed/radiation and accepts **time**, **damage**, **damagePercent**.
  Its tick/refresh/stack equivalence is not established. Merely putting the source
  duration in `life` limits the equipment buff rather than the victim bleed.
- Additive `def_stun level=0`: XML1 `0x38230` queries **scale** entries. Zero in
  an additive entry is not stun immunity. Do not turn it into an XML2 zero factor.
- `def_damage_scale`: not present in the XML1 table; `0x946f0` returns ID 0.
  The existing default translator interprets this name as resistance. The audit
  marks it unsupported rather than inventing an XML1 applying consumer. The
  legacy build output is deliberately retained pending a separate compatibility
  decision.

Unknown schemas remain unsupported, including scoped cache-only attributes,
fractional HP/s, unsupported aggregation modes and damage callbacks. A later
implementation should expand the evidence and tests before accepting those forms.

## Controlled runtime validation (2026-10-04)

The private test build replaces existing equipment slots with synthetic items from
`expanded=True`; no definitions or patches enter normal builds. Items were delivered
through inventory pickups and equipped/unequipped through the normal gear menu.
The executable was restored to its unmodified state and saves/profile data isolated
with a dedicated SaveFolder. No existing save was loaded.

The setup is staged: a hero with zero innate regeneration and critical talent rank
zero, an enemy with a large health pool, scripted health resets and AI toggles, and
local fixed-20-damage punch events with no attack-rating roll, pain or knockback.
The damaging hits themselves are actual combat events, not script `damage()` calls.
Health and game time are sampled read-only from the running game. These are isolated
bonus tests, not a campaign playthrough or a claim about every target/attack type.

- **Flat armor +7:** 26 landed enemy hits without equipment each removed 20 HP;
  26 hits from the same enemy with the item each removed 13 HP. The additive defense
  cache changed from 0 to 7. This supports the exact subtraction mapping.
- **Health regeneration coefficient 4:** control gained 0 HP in 30.0543 wall seconds
  (29.7552 game seconds). Equipped, it gained 96.3985 HP in 30.0542 wall seconds
  (29.2766 game seconds): 3.20749 HP/wall-second or 3.29268 HP/game-second. Cached
  rate was 4, scale 1, cap 1. The original literal HP-per-elapsed-second claim was
  too strong: XML2 `0x496bd0` adds `0.1*rate`, then `0x496970` schedules the next
  tick after another 0.1 seconds. XML1 `0x91190` likewise uses fixed 0.1 increments.
  Late scheduling is not compensated. The mapper keeps level 4 and now describes
  a nominal coefficient instead of promising four HP per elapsed second.

- **After-hit regeneration:** following one real calibrated enemy hit, the next
  positive healing increment was observed after 0.11621 game seconds; subsequent
  increments restored 17.60107 HP in the first five game seconds. There were no
  additional hits. A healing tick coincided with the hit, so its sampled net health
  loss was 19.59998 rather than the calibrated 20. This demonstrates immediate
  continued regeneration, not the XML1 five-second delay traced at `0x3a950`.
  XML1 was not run; that side of the comparison is applying-code evidence.
- **Critical source level 3 -> +0.06 probability:** no item gave 11 criticals in
  1,000 landed punches (1.1%; Wilson 95% interval 0.6153%–1.9589%). The item gave
  67/1,000 (6.7%; 5.3102%–8.4212%). Observed increase: 5.6 percentage points;
  approximate 95% interval for the difference: 3.9209–7.2791 points. This is
  consistent with the predicted +6 points (1% base -> 7% total). Normal hits were
  20 HP and criticals 40 HP. Both samples used the same hero and enemy entities,
  target structure 0 and critical-defense multiplier 1; the equipped cache changed
  from 0 to 0.06. One attempt that failed to land hits after a menu transition was
  excluded before the retained sample; recorded positions and facing were restored.
  Only landed hits enter the rates. Kick/throw, non-melee accuracy and other target
  structure classes were not measured. A separately equipped positive-control item
  (source level 50 -> probability 1.0) produced 100/100 criticals at 40 HP, confirming
  the damage-based critical classification in this fixture.

The previous local `198 passed / 48 failed` result was environmental. All 48 final
baseline exceptions were temporary-directory permission failures under the restricted
Windows token. Removing the sandbox but retaining TEMP inside the checkout left
five autopilot tests failing their deliberate outside-Git-output rule. With normal
system TEMP, the unchanged suite passes **246/246**, matching CI. The content-guard
self-test also passes **31/31**. No tests were weakened to obtain these results.
