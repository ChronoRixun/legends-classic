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
matching strings. These mappings have **static analysis only** validation. The
attempted isolated runtime test could not access its named pipe (Windows error 5);
regeneration, damage and a statistically meaningful critical-rate comparison remain
required before enabling the mappings in builds.

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
damage scaling or the entire combat pipeline. All rows are static-only.

| Source bonus | XML1 applying code and units | XML2 applying code and emitted form | Fidelity / numerical difference |
|---|---|---|---|
| `health_regen`, additive integer | `0x3a950`: integer HP/s; delay `5 / regen_scale` seconds after damage; maximum `user1` cap as percent of maximum HP (`0x3aa66`, `0x2a4b0`) | `health_regen` additive; optional second `health_regen max` with `user1/100`. Cache `0x53a1a0` cases 22/23; rate/cap `0x42cc60` | Approximate. Same standalone HP/s and cap, but starts immediately. A 4 HP/s bonus can supply 20 additional HP during the first five seconds. XML1 selects the highest cap; XML2 takes the lowest cap, initialized to 1.0 (`0x539df0`, helper `0x419e60`). |
| `energy_regen scale S` | `0x3a950`, `0xaf860`: hero rate `truncate((maxEP/60 + add) * S * (1+mind/100))` | `energy_regen scale S`; cache case 24, rate `0x42cc60` | Approximate. Preserves S, but XML2 lacks the mind factor and keeps fractional rates. At maxEP 120, mind 20, S=1.5: XML1 3 EP/s, XML2 3 EP/s; at mind 50: XML1 4, XML2 3. Baseline pools can also differ. |
| `def_damage` additive | `0x45260`, arithmetic `0x45518`: subtract HP, floor at zero, then apply defense scale | Unscoped `def_damage`; scoped `def_damage_scope`. Cache case 39, combat `0x437490` / `0x4379e6` queries ID 56 then combines cached ID 39 | Exact for integer flat reductions. A 20 HP hit with +7 armor becomes 13, not 18.6. Fractional reductions are approximate because XML1 truncates integer damage. |
| `def_damage scale S` | Same consumer: `truncate(max(0,D-A) * S)` | Same attributes with `affect_type=scale`, `0x437490` | Approximate: same multiplication, XML2 keeps fractional HP. Difference less than 1 HP at this stage before later modifiers. Scoped resistance must use the contextual ID 56, not a cached global value. |
| `critical` additive L | `0x5c020`, `0x5c12c..0x5c1da`: `0.02*L` probability on punch/kick/throw | `critical level=0.02*L`, cache case 70, roll `0x452f20` | Approximate. Same additional probability on eligible targets: L=3 gives +6 percentage points. XML1 rejects structure >=10; XML2 >=2 (`0x41d550` is the structure setter). Structure conversion/eligibility and baseline critical chances need runtime comparison. |
| `accuracy` additive L | Other branch of `0x5c020`, `0x5c0d2..0x5c127`: non-melee critical probability, **not hit rating** | `atk_critical level=0.02*L`, scoped to direct/blast/projectile/beam/crush/psionic; `0x452f20` queries ID 63 before its melee branch | Approximate for the same structure-eligibility reason. L=2 adds 4 percentage points; it adds zero attack-rating points. Both attack enums are identical (`0x59740`, `0x44ebc0`). |
| `deflect_damage` additive L | `0x43fa0`, `0x44250`: roll against L/100; return copied incoming attack and cancel original damage | `deflect_damage level=L/100`; `0x435440`, queries `0x435762` / `0x435773` | Exact chance and return/cancel operation for the accepted additive form. L=35 becomes 0.35. Scoped rolls remain scoped. |
| `reflect_damage` with `user1` 0 or 100 | `0x44168..0x4422f`: fixed returned `truncate(sum(level)*product(scale))`, with integer percentage gate (`user1=0` means no gate) | Additive `reflect_damage` plus a **zero scale** affecter, `0x436ae0..0x436c38` | Approximate. XML2 otherwise returns `incoming*scale + add`, so copying L alone would add the entire incoming hit. Zero scale preserves fixed amount, but XML1 reflection runs before final damage resolution; XML2 runs later and changes reflected flags. |
| `move scale S` | `0x38270`: multiplicative movement factor | `move scale S`, cache case 9, `0x428980`: clamp `(1+add)*scale` to `[0,max]`, default max 2.5 | Approximate. Same factor below the cap; combined factor 3.0 becomes 2.5. |
| `def_knockback scale S` | `0x45634..0x45676`: scale incoming knockback and convert to integer | Same name and scale; cache case 40, `0x437490` uses cached factor | Exact multiplier/product for unscoped scalar inputs. S=0.6 turns 200 into 120. |
| `def_pain scale S` | `0x394e0`, `0x395c3`: pain animation rate `clamp(1/S,0,10)`; `0x44410` suppresses pain when zero | Same name and scale, cache case 42; `0x428af0`, `0x435850` | Exact corresponding animation-rate factor, not flat damage resistance. S=0.4 means playback rate 2.5. |
| `drain_time scale S` | `0xd75a0`: modify life of a `drain_victim` attachment, `(life+add)*S` | Same name and scale; cache case 72, `0x5370b0` / `0x5372e0` | Exact duration multiplier when a `drain_victim` powerup is actually attached. S=1.2 maps 10 seconds to 12. Registration does not prove the converted hero currently uses that powerup. |
| `xp scale S` | `0x33170`: apply `(award+add)*S` before adding XP | `xp scale S`, cache case 73; kill-award path `0x436c50`, add `0x437408` / multiply `0x437437` | Approximate. XML2 direct award `0x422350` -> `0x4b79b0` bypasses this cache. At S=1.1, a direct award of 100 stays 100 instead of 110. |
| `damage` | `0x5cca0`: resolve range, apply source damage contribution, integer conversion | `damage`; `0x453a60` / `0x453bb6`: sample range and add `ceil(base*(scale-1)+add)` | Approximate integer rounding; up to 1 HP difference at the contribution stage before later multipliers. Ranges and scopes are preserved. |
| `atk_damage`, `atk_damage_scale` | `0x29fd0`, switch at `0x2a114`: separate final `(damage+add)*scale` stage; reads **minimum only**, regardless of `affect_type` | `damage` additive/scale at `0x453a60` | Approximate stage change. Base 100, earlier damage +10, final attack x1.2 yields 132 in XML1 versus 130 with XML2's merged terms, before rounding. |
| `atk_knockback_scale` | `0x29fd0`: minimum-only product in attack-modifier pass | Same name, `0x54f900` (ID 61); name selects multiplication | Exact corresponding multiplier with the shared knockback threshold rules. No additional `affect_type=scale` is needed. |
| `power_cost scale S` | `0x3f410`: additive then multiplicative energy cost | Same name/form, `0x4318d0`; SPEC 24 | Exact cost multiplier. |
| Stat bonuses | XML1 trait values, existing port conversion described in SPEC 21 / SPEC_heroes | Existing `stat_scale`: 4 for strength/body/mind; 2 for speed/traits; XML2 cache cases 2..6 | Approximate port stat conversion; explicitly reported, not called exact. |

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
