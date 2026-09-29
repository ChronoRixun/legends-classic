# Forced parties: design (xml2-fix script functions + xml1build pipeline)

Written 2026-09-28 (Opus synthesis step, read-only). Inputs: `script-functions.md`, `party-seating.md`,
`conversation-speakers.md`, `forced-teams-census.md` (all four present), `roster.md` sections 1, 2, 4, 5,
xml2-fix `src/new_game.cpp`, `exports.cpp`, `limits.cpp`, `test_input_rules.hpp`, and xml1build `scripts.py`,
`scripts_transform.py`, `validate_script.py`, `testhooks.py`, `tools/harness.py`.

For this doc, I re-read the retail exe (`xml2-fix/docs/research/XMen2.exe`, capstone) at every
address marked **[v]**. XML1 addresses are default.xbe (`research/scripts/xml1_text.asm`, `research/scripts/binimg.py`)
and are marked **[v1]**. I re-checked the generated port output in `build/_heroes`. Anything not read from code or data is
marked **UNVERIFIED**. Nothing was launched, built or committed. The only file I wrote is this one.

Conventions follow party-seating.md:
- `game` = `0x46dce0()`, vtable `0x686e1c`.
- `registry` = `0x44b8f0()`, vtable `0x68544c`.
- `console` = `0x55c890()`, vtable `0x69a81c`.
- `CStats` = `registry vt+0x40(name)`.
- `stack` = side-mission stack, `0x48a0e0()->vt+0x44()`.

---

## 1. Verdict and mechanism

### 1.1 Verdict

| question | answer |
|---|---|
| Can xml2-fix give the port XML1's exact forced parties? | **Yes, for 44 of the 49 missions.** 2 cannot be seated until `profxgladiator` becomes a herostat hero (`astral_sk`, `boss_shadowking`). 3 are cut content: their zones do not exist in XML1's data (`nyc_rooftops`, `boss_sabreroof`, `ice_wolverine`, section 3.3). The Danger Room course hero (`hero=`) is already honoured by the exe (roster 1.5). |
| By which mechanism? | New **script functions** registered by xml2-fix, in the same way `new_game.cpp` changes push operands: two imm32s at `0x49fe31`/`0x49fe36` point registration at a DLL-owned copy of the table (option A1 of script-functions.md 5). `seatParty` writes the 4 party slots through the retail slot setter `game vt+0xf0`. The script's existing `loadMapKeepTeam` then spawns the party at zone load. This is the same "write 4 slots, then load" pattern every retail party change uses (`restorelastzone`, Danger Room course start, save loader, team menu; party-seating 5). |
| Is an engine hook or code patch needed beyond the two operands? | **No.** The handlers only call retail functions and write the party slots, costume bytes and console commands the game itself writes. No retail code bytes change except the two push operands. |
| Does anything need XML1 data the port lacks? | ProfXGladiator needs a herostat entry for `astral_sk` and `boss_shadowking` (SPEC 12.6 hero-conversion list). Nothing else. |
| Is it faithful to XML1's rule, not just to the census? | Yes. XML1's `beginmission` (xbe `0x18da90` -> `0x18d6d0(1)`) was read for this doc **[v1]** (section 1.4). It seats REQUIRED, then RECOMMENDED, drops RESTRICTED, and pads to `maxheros`. That makes `sent_fb` and `asteroid_rock` **fully determined** (they are not "partially forced", as party-seating 13.3 and the census assumed). |

### 1.2 Script functions (8 of the 12 free tree slots; `joinHero` added 2026-09-28 night, 1.3.6)

| name | sig (ret, args) | what it does | engine sequence (every address **[v]**) |
|---|---|---|---|
| `xml2fixFeature(s)` | `i`, `s` | 1 if the named feature is on, else 0. Names: `forcedteams` = ini `[Game] ForcedTeams`, `addhero` = `[Game] AddHero`. Scripts use it to choose the seat branch or the team-menu branch. | `return 0x4d6570(ecx=0x4d8770(), v)` (int value, thiscall `ret 4`) |
| `seatParty(h1,h2,h3,h4)` | `n`, `ssss` | Seats exactly these heroes. Empty strings = empty slots. Does not load: the script's next statement must be the load. | See 1.3.1 |
| `setSkinset(costume, heroes)` | `n`, `ss` | XML1 mission skinset. Every herostat hero whose costume is default or a skinset costume (0, 3, 4, 5, 8) gets `costume` if the hero is listed in `heroes` and has that variant. Everyone else in those costumes goes back to default. Player-picked costumes 1, 2, 6, 7 are kept. | See 1.3.2 |
| `pushParty(a)` | `n`, `a` | XML1 `beginSideMission` half 1: saves zone, 4 party names and the spot of entity `a` on the retail side-mission stack, **immediately** (before `seatParty` changes the party). | See 1.3.3 |
| `popParty(fallbackZone)` | `n`, `s` | XML1 `endSideMission`: if a record is on the stack, queues `restorelastzone 0`, which seats the saved names, restores the game-state block and loads the saved zone at the saved spot. Otherwise it queues `loadmap <fallbackZone> 0 1` (the team menu, = `loadMapChooseTeam`), where retail would drop to the main menu. | See 1.3.4 |
| `addHero(h)` | `i`, `s` | XML1 `addHero`: seats `h` mid-zone with no reload, through the game's own dormant routine `game vt+0x170` = `0x46c9f0`. Returns 1 on success. Only active when `[Game] AddHero=1`; otherwise returns 0 and the script runs the T7 fallback. | See 1.3.5 |
| `getPartyMember(i)` | `s`, `i` | Slot `i`'s hero name (`""` when empty). Not needed by the pipeline; for tests and future party-aware scripts. | `h = [game+0x14+4i]` (i in 0..3); text = `0x425bc0(ecx=&h)` (handle -> text, `""` for 0); `return 0x4d9430(ecx=0x4d8770(), text)` |
| `joinHero(h)` | `i`, `s` | XML1 `addHero` as a reload, no team menu: the active hero's spot and the party saved on the side-mission stack with `h` added to the saved party, then the zone reloaded there. 1 = the reload is queued, 2 = `h` is in the party already, 0 = refused (the script's T7 fallback runs). `[Game] JoinHero`, on with `ForcedTeams=1` unless 0; `xml2fixFeature("joinhero")`. | See 1.3.6 |

None of the seven names occurs in the exe's bytes (case-insensitive search). Registration is exact-case and keyed by
the full name, so a retail name that merely starts the same way (`setPartyLightRadiusScale`) cannot collide.
Reconciling the source docs' names: script-functions' `seatParty` / `pushSideMission` / `xml2fixVersion` and
party-seating's `setParty` / `pushParty` / `popParty` become the names above.
- `xml2fixFeature(s)` replaces `xml2fixVersion()`. A version number cannot tell a registered-but-off switch from an on one, and scripts have no bitwise AND.
- `setSkinset` takes a second argument (the heroes that own the variant), for the reason in 3.5.

### 1.3 Exact engine sequences

Handler ABI (script-functions 4, re-read **[v]**):
- Signature: `void* __cdecl h(void* args)`.
- Argument `i`: `v = 0x4d5830(ecx=args, i)` (`8b 51 1c 33 c0 85 d2 74`, `ret 4`, NULL past the count).
- Value accessors: string `v->vt[0x14/4]()`, int `v->vt[0x10/4]()`.
- Return 0 for an `n` function.

#### 1.3.1 `seatParty`

| # | step | address / precedent |
|---|---|---|
| 1 | Read 4 strings, lowercase and trim. Drop duplicates, then compact so the non-empty names come first. | Keeps slot 0 filled (the team menu's `builddefaultteam` fallback `0x5e374b` fires only on an empty slot 0). Keeps "slot = party count" for `vt+0x170`. |
| 2 | For every non-empty name: `idx = registry vt+0x3c(name)` (`0x44acc0`, returns a short, 0 = unknown), then require `registry vt+0x7c(idx)` (`0x44b7c0`: byte `[reg+idx*0x1c+0x9b40] & 1`, herostat entry) **[v]**. Any failure: log, **change nothing**, return. | The slot setter accepts any name. A non-herostat name spawns through the registry fallback entry (engine.md R6). |
| 3 | If all four names are empty: log and return. | An empty party would trigger `builddefaultteam` at the next team menu. |
| 4 | For slot 0..3: `uint h = 0; 0x425bf0(ecx=&h, name_or_"")` (interns, 0 for `""`) **[v]**; `game vt+0xf0(slot, &h)` = `0x46c810` (thiscall, `ret 8`) **[v]**. | The same writes as `restorelastzone` `0x5f4612-0x5f4667` **[v]**. |
| 5 | Log `seatParty: magma / - / - / -` and return 0. No unlock, no `vt+0x178`, no load. | The setter only swaps names and clears the old hero's talent map (party-seating 2). Heroes spawn from the slots at the next zone load, `0x486dd0`. |

#### 1.3.2 `setSkinset(costume, heroes)`

| # | step |
|---|---|
| 1 | Find `k` = index of `costume` in the costume table at `0x6d8aa0` **[v]**. The table is 8-byte `{char* name, int index}` entries: default 0, astonishing 1, aoa 2, 60s 3, 70s 4, weaponx 5, future 6, winter 7, civilian 8. Match with `_stricmp`. Unknown name: log and return. |
| 2 | `dress` = the set of `registry vt+0x3c(h)` for each comma-separated name in `heroes`. |
| 3 | For each herostat hero, walking the list the way `0x4499e0` does **[v]**: count `[reg+0x12330]`, `short idx[]` at `reg+0x120dc`, `cs = reg + 4 + (([reg + idx*0x1c + 0x9b38] & [reg+0x9b20]) * 0x4f8)` (the same address `registry vt+0x40` returns, `0x44990a-0x44994f` **[v]**). Let `cur = cs[0x120]`. If `cur` is in {0, 3, 4, 5, 8}: `cs[0x120] = (idx in dress && k != 0 && cs[0x255+k] != 0) ? k : 0`. |
| 4 | No load. The skin is chosen from `+0x120` when the character loads, at the next zone load (`0x4b8090` reads `+0x120` at `0x4b80e7` **[v]**; there is no unlock-mask check, party-seating 8). |

#### 1.3.3 `pushParty(a)` (the first half of `extractionPointChange` `0x4a7020`, **[v]**)

| # | step |
|---|---|
| 1 | Resolve the entity: `hp = 0x4a1700(&tmp, name)` (cdecl, 2 args), then `ent = 0x4654b0(ecx=hp)`. NULL: log and return. |
| 2 | Check it is a character: `info = ent->vt[0]()`; bit `b = [0x718448] + 0x24`; require `[info + 0x14 + (b>>5)*4] & (1 << (b&31))`. This is the same test as `0x4a7085-0x4a70a1`. |
| 3 | `n = [stack + 0x4dc]`. If `n >= 2`: log "side-mission stack full" and return. The retail handler would silently skip the push (`0x5f3684`). |
| 4 | `console vt+0x18("pushsidemission <ent+0x1c>")` (`0x55beb0`, runs **now**, like `0x4a70df`). The record captures the current party. |
| 5 | Re-read `[stack+0x4dc]` and log whether the push happened. |

The record's names are at **+0xa4**, not +0x134 **[v]**: `0x5f4614 lea esi,[esp+0x134]`, and the record copy is at `esp+0x90`. That +0x134 is a stack offset. This is party-seating's correction, confirmed.

#### 1.3.4 `popParty(fallbackZone)`

| # | step |
|---|---|
| 1 | `n = [stack+0x4dc]`. |
| 2 | `n == 0`: log, then `console vt+0x1c("loadmap <fallbackZone> 0 1")` (`0x55c410`, queued). This is the team-menu load `loadMapChooseTeam` sends (`0x68d31c`) **[v]**. Return. |
| 3 | The current menu is `"loading"` (`0x5d8920()->vt+0x214()` vs `0x688874`, as the retail `restorelastzone` wrapper checks at `0x4a0791-0x4a07a9`) **[v]**: log and return. |
| 4 | `console vt+0x1c("restorelastzone 0")`, queued like the retail script wrapper (`0x4a07d1`) **[v]**. The handler `0x5f4580` then does the rest **[v]**:<br>- seats the 4 names at record `+0xa4` (`""` clears a slot) - only for argument 0 (`atoi` `0x67233c`; any other value keeps the party, which is what the team menu's accept wants, 1.3.6);<br>- restores the game-state block with `game vt+0x204`;<br>- runs `"loadmap <zone> 1"` now - always 1 (`push 1` at `0x5f4678`);<br>- the loadmap handler `0x5f4770` loads (`game vt+0x150`) and pops the record (`0x5f48d3`), because its second word `a` is 1 (the "only when a != 0" is loadmap's `a`, not restorelastzone's argument). So every `restorelastzone` with a record pops it: `0` and `1` alike. |
| 5 | The queue refuses when 2 commands are pending (`0x55c426` **[v]**): log an ERROR. The pipeline guarantees that `popParty` is the only console command in its script run (V14e). |

This is XML1's `endsidemission` exactly. xbe `0x18df20` **[v1]** reads the argument with `0x341986` (the function the mission loader uses for `maxheros`, `0x84b11`, so presumably `atoi`). If the result is 0 it re-seats the saved names, then runs `"loadmap %s %d"` with 1. XML1 scripts pass `"TRUE"` or `"FALSE"`, and both parse to 0. So **XML1 flashbacks always return with the pre-flashback party and spot**. That settles party-seating's UNVERIFIED "endSideMission argument semantics" (the `atoi` identity is inferred from that call site).

#### 1.3.5 `addHero(h)` (experimental; `[Game] AddHero=1`)

| # | step |
|---|---|
| 1 | Feature off: return 0. |
| 2 | Validate as in 1.3.1 step 2. The party must be compacted, which it always is after `seatParty` or a menu confirm (`vt+0xec`). |
| 3 | `ok = game vt+0x170(name)` = `0x46c9f0` (thiscall, 1 arg, returns bool) **[v]** (prologue `6a ff 68 c6 37 67 00 64`; `registry vt+0x40(name)` at `0x46ca2e`; party list `vt+0x120` at `0x46ca59`; `cmp eax,4 / jge` at `0x46caab`). Its steps (party-seating 6): find an NPC with the same CStats and **remove it, spawning the hero on its spot**, load the package, assign a controller, spawn, refresh the HUD. |
| 4 | Return `ok`. |

Nothing in XMen2.exe calls `game vt+0x170`. Of the 10 raw `call [reg+0x170]` sites **[v]**:
- 3 go through the `0x4457e0` getter (`0x511433`, `0x517f41`, `0x51800c`);
- 6 are UI objects (`0x5d8920`-family, `push 0xd; push ""`);
- 1 at `0x5acd5a` takes 2 args.

So the routine is dormant. It matches XML1's `addHero` engine routine (xbe `0x71cf0`, party-seating 6).

#### 1.3.6 `joinHero(h)` (added 2026-09-28 night; xml2-fix 0c82a6e; every address **[v]**)

What the team menu's ACCEPT does after `extractionPointChange` (the T7 path, verified in game):

| step | address | effect |
|---|---|---|
| open | `0x4a7020` | `0x5d8920()->vt+8(0)` closes the open menus; `"pushsidemission %d"` run now (`vt+0x18`, `0x4a70df`); `"setblackbirdparms FALSE restorelastzone('1') TRUE TRUE %d"` run now (`0x4a7108`); the team menu opens (`vt+0x68`) |
| `setblackbirdparms` | `0x5f23e0` | word 2 (`restorelastzone('1')`) -> the blackbird code `0x8b12cc` (0x80 bytes); word 3 `TRUE`/`script` -> `[0x8b134c]` bit 0 (run it as a script); words 4 / 5 -> bits 3 / 4; bit 2 always |
| picks | `0x5e2420` (`0x5e2539`) | each pick writes its slot live through `game vt+0xf0` |
| accept | `0x5e0800` | `0x5de970` (re-apply changed stats to live actors), `0x5de4d0`, `[0x8b11c0] = 0`, `game vt+0xec` (compact), then with bit 0 `"runscript <code>"` (`0x6a2d64`), else `"loadmap <code>"`, queued (`vt+0x1c`, `0x5e090e`); the code cleared; `menus vt+0x78` |
| `runscript` | `0x5f2350` | compiles and runs `restorelastzone('1')` (script manager `0x4a1670` vt+0xc / +0x3c / +0x10) |
| `restorelastzone('1')` | `0x4a0760` | queues `"restorelastzone 1"` (not while the menu is `loading`) + HUD `vt+0x80`. The frame's drain (`0x55c230`) unlinks each command before it runs it (`0x55bc50` decrements `+0x630`) and loops while any wait (`0x55c2f9`), so this one runs in the same drain |
| `restorelastzone 1` | `0x5f4580` | keeps the live party (argument != 0), `game vt+0x204`, `"loadmap <zone> 1"` now -> `0x5f46f0` (the record's mission-state block `+0x125`, 0x12d bytes, back to `0x72b118` via `missions vt+0x28` `0x4892e0`), `game vt+0x150(zone, 1)`, pop `0x5f44a0` (dec the count, then `0x489300` puts the party's existing bodies on the pushed spot `+0x254`, a 40-unit formation), `menus vt+0x78` (closes the menus: `0x5d4d20` -> `vt+8(0)`) |
| back out | | the zone reloads with the old party, the join lost (HANDOFF night notes) |

`cancelsidemission` (`0x5f2ce0`, registered at `0x5f4a0f`) only decrements the count: the game's own way to take a
record off without loading.

`joinHero(h)` = the accept path with the party change made in the record instead of the live slots:

| # | step |
|---|---|
| 1 | Refuse (0, logged) when off, `h` not a herostat hero, the party full, the menu `loading` or a zone load pending, **any** console command waiting (it would run first, in the same drain, and a load there would race the reload), the stack full (2), no `_ACTIVE_HERO_` character. `h` in the party already: 2, nothing done. A repeat while its own reload waits or loads: 1, nothing done (`queued_pop`, as popParty's). |
| 2 | `pushsidemission <_ACTIVE_HERO_ id>` run now (as `0x4a70df`); require count + 1. |
| 3 | `h` into the pushed record's first empty name (`+0xa4 + 0x20 slot`: 0x20 bytes cleared, the name, a 0 at `+0x1f`, as the fill `0x48a2a3-0x48a320` writes it). A party member whose body was dead at the push is recorded the same way (name set, spot `ZeroVector`, `0x48a278`), so the record is one the game itself can make. Read back. |
| 4 | `restorelastzone 0` queued + HUD `vt+0x80`: next frame the game seats the record's names (the old party + `h`), restores the state block, reloads the zone at the saved spot and pops the record. |
| 5 | Any failure after step 2: `cancelsidemission` run now, the count checked back (nothing stays on the stack). |

Why the record rather than mirroring the accept exactly (seat the live slot now, then `restorelastzone 1`): the accept
seats while the menu is up; outside a menu the live-slot write would leave the world running (the rest of the
frame, and the script) with a hero in a slot and no body; with the record, the slot setter runs inside the command
that loads, as with popParty (`restorelastzone 0`, verified in game: jug_fb, sent_fb, astral_sk back to the exact
spot), and a refusal never touches the party. The load, the spot and the pop are the accept's own.

Where the new hero appears: the pop places the bodies that exist (the old party) on the saved spot before the load;
the new hero spawns at the zone load from its slot's player start. In nyc1_1_3 / mag_nyc4 that is `player_start01`
(slot 2, `startenabled=false`, enabled by the join trigger's `acttargets enable_target01` - T7 showed Cyclops spawns
only with it enabled), at (-481, 946, -231), about 200 units from the NPC's spot. The trigger's enable lasts for
that load only, so the port's zone files enable the join zones' slot-2 starts (zones section 18) and the joined hero
spawns at every later load too. SPEC 19.7.

### 1.4 What XML1 actually did at mission start (read for this doc, **[v1]**)

| step | xbe address | effect |
|---|---|---|
| mission attrs | `0x84afa-0x84c83` | `maxheros-1` in `+0x12e` bits 0-1, `minheros-1` in bits 2-3, `teamselect` = `+0x12f` bit 0, `keepheroes` = `+0x12f` bit 1 |
| hero lists | `0x8612c-0x86180` | `REQUIREDHERO` list at `+0x130` (count `+0x1b4`), `RECOMMENDEDHERO` at `+0x1b8` (count `+0x23c`), `RESTRICTEDHERO` set at `+0x240` |
| `beginmission` | `0x18da90` | if keepheroes and slot 0 is set: keep the party; otherwise `0x18d6d0(1)`; then the scriptstart (`+0x61`) runs, or, when there is none, the mapload (`+0xc1`) with the Blackbird menu if teamselect (`0x18dc3a`) |
| team builder | `0x18d6d0` | 1. slots 0.. = REQUIRED in file order.<br>2. then RECOMMENDED into the free slots.<br>3. any slot whose hero is RESTRICTED (`0x85230` -> set `+0x240`) is cleared.<br>4. pad up to `maxheros` from ini `[HERO] Name<i>`, defaults `cyclops`, `iceman`, `storm`, `wolverine` (XML1's `build.ini` has no `[HERO]` section).<br>5. clear the remaining slots (setter `game vt+0xc8` = `0x71b90`, no campaign check). |
| free missions after forced ones | scripts `missions/nuke.py`, `icetunnels.py`, `sewers_hub2.py`, `astral2.py` | all call `blackbirdMenu(...)`. XML1 had **no party memory**: the player re-picked in the Blackbird menu, seeded by step 4 |

Consequences:
- The seat list per mission is REQUIRED + RECOMMENDED - RESTRICTED, capped at `maxheros`. None of the 49 needs step-4 padding.
- The "remember the player's party" problem (party-seating 13.2) does not exist in XML1. The port keeps XML1's `blackbirdMenu` starts (checked: `begin_nuke`, `begin_sewers_hub2`, `begin_astral2`, `begin_haarp`, `begin_icetunnels` all end in `blackbirdMenu`).
- Content contradiction, **UNVERIFIED**: step 1 would seat Cyclops at `alison` and `dr_mag2` (both list him as REQUIRED), yet both zones spawn an NPC Cyclops and join him later with `addHero`. Something not traced (a spawn-time campaign check?) keeps him out in XML1. The design follows the content: Wolverine alone and Magma alone, with Cyclops joining at the trigger.

### 1.5 Registration patch (A1) and init timing

| site | VA / file off | retail bytes **[v]** | write | why |
|---|---|---|---|---|
| table pointer | `0x49fe31` / 0x9fe31 (.text) | `08 a9 68 00` (in `68 08 a9 68 00`) | `&table` (DLL static, 0x121+7 entries) | the only reference to `0x68a908` |
| table count | `0x49fe36` / 0x9fe36 (.text) | `21 01 00 00` (in `68 21 01 00 00`) | `0x128` | |
| guard: whole function | `0x49fe30` | `68 08 a9 68 00 68 21 01 00 00 e8` then `31 89 03 00 8b c8 e8 5a 77 03 00 c3` | read only | `push; push; call 0x4d8770; mov ecx,eax; call 0x4d75a0; ret` |
| guard: tree cap | `0x4d7637` | `81 bf 48 19 00 00 40 01 00 00` | read only | 320 names; 19 + 289 + 7 = 315 |
| guard: builtins | `0x4d8694` | `6a 13` | read only | 19 builtins |
| guard: caller | `0x68d36c` (.rdata) | `30 fe 49 00` | read only | script interface vt+0 = `0x49fe30` |
| guard: last retail entry | `0x68bb08` | `10 fe 49 00 28 bb 68 00 18 9c 68 00 68 19 68 00` | read only | the copy is exactly 0x121 entries (`SetDontShowWarningOff`) |

The tree stores a **pointer to each entry**, not a copy: `lea eax,[ebp-4]` -> `0x4d7310`, at `0x4d7648-0x4d768a` **[v]**. So the table must be a static that lives as long as the process.

Timing, all on retail paths **[v]**:
1. xml2-fix `DllMain` runs before the exe entry point `0x6725f4` (exports.cpp).
2. Game init: `0x40197b` -> `game vt+0x13c` (`0x46b750`) -> script interface vt+0 (`0x49fe30`) registers the DLL table once.
3. Scripts compile later, from the first menu onward. Function names are resolved at **compile** time (`0x4d8970` -> `0x4d6910`, the only caller at `0x4d8981` **[v]**).

An unregistered or mis-typed call **drops only that statement** (script-functions 3). That is what makes the feature-detect in 3.2 safe without the DLL.

### 1.6 Where the four source docs disagree, resolved from code

| topic | claims | resolution **[v]** |
|---|---|---|
| side record names offset | roster 2.4: +0x134; party-seating 7: +0xa4 | **+0xa4** (1.3.3) |
| `extractionPointChange` console use | roster 2.4 / T7: uses "exactly the 2" queued commands; party-seating: immediate | **Immediate**: `call [edx+0x18]` at `0x4a70df` and `0x4a7108` = `0x55beb0`, which runs the handler. The queue is `vt+0x1c` = `0x55c410`, cap 2 at `0x55c426`. script-functions 7.1 also mislabels `vt+0x18` as "console queue". |
| side stack saved? | script-functions Q2: UNVERIFIED; party-seating 7: saved | **Saved and loaded**: 0x4e0 bytes of `stack` are copied into the save at `0x46bcd4-0x46bd01` and back at `0x46e3ec-0x46e428`. A save made inside a flashback keeps its return record. |
| pending-name array as a seat path | script-functions 7.1: an alternative; party-seating: dead | Irrelevant: the design uses `vt+0xf0` directly. The apply loop `0x486e60` skips empty entries (`0x486e7b`) and clears after applying (`0x486eae`) **[v]**. |
| costume forcing | census 6: `setSkin(a,s)` or `unlockCharacter("",costume)`; party-seating: write `CStats+0x120` | **`+0x120`**. It is read at character load with no mask check. `unlockCharacter` only sets a mask bit (party-seating 8), and `setSkin` works on one entity for one zone. |
| dr_mag2 "gap" (census 6: Cyclops lacks civilian) | | **Not a port gap.** In XML1's `herostat.eng`, only Iceman and Colossus have `skin_civilian`; Magma has only `skin_magmacivilian` and Cyclops has no civilian slot. So XML1's `civilian` skinset (dr_mag2 and 2 briefings) left both Magma and Cyclops in default. That assumes XML1 falls back to default for a missing variant, which is inferred from party-seating 8's `+1` arithmetic and **UNVERIFIED**. |
| census 6: "Magma magmacivilian at 25 of the 31 Magma-solo entries" | | **4 missions** have `skinset=magmacivilian` (`mansion1`, `mansion2`, `mansion3`, `mansion3_dangerroom`, from mission_plan.json). 5 have `civilian`. The rest are default. |
| "partially forced" `sent_fb`, `asteroid_rock` (party-seating 13.3, census) | | **Fully forced** by XML1's builder (1.4): Nightcrawler + Cyclops, Phoenix, Wolverine (RECOMMENDED; `sent_fb` restricts every other hero); Frost + Iceman, Storm, Wolverine (RECOMMENDED). |
| side-mission list (census 5: 7) | | 8 `beginSideMission` sites (roster 1.2). The 8th is **`nyc_rooftops`**, started by conversation `nyc/riots/3_2_6`, whose zone `nyc/riots/nyc_roof1` exists in neither XML1 tree. The port still ships that response (`chosenscriptfile x1/missions/begin_nyc_rooftops`, checked in `build/_heroes/Conversations/nyc/riots/3_2_6.XMLB`). **Side finding: a live load of a missing zone.** |
| free party after a forced stretch (party-seating 13.2) | | XML1 has no memory (1.4). No DLL state is needed. |

---

## 2. xml2-fix module design (`src/forced_teams.cpp/.hpp`, `src/forced_teams_rules.hpp`)

Style matches `new_game.cpp` and `limits.cpp`:
- A `_rules.hpp` holds everything xml2_test can check against a copy of the exe: guard table, name parsing, costume lookup.
- The `.cpp` holds `install` and the handlers.
- `install(game)` is called from `exports.cpp install()` right after `new_game::install(game)`, in `DllMain`, before `0x40197b`.

xml2-fix is on branch `display`, with uncommitted `test_input` changes (a pipe `script`/`console` command). Do not disturb those.

### 2.1 ini

```
[Game]
ForcedTeams = 1   ; the mod forces its campaign's parties (X-Men Legends 1: Magma alone in the mansion,
                  ; flashbacks with fixed heroes and costumes). 0 = the functions exist but report "off":
                  ; the mod's scripts open the team menu instead. Absent = nothing patched.
AddHero = 1       ; with ForcedTeams: addHero(hero) seats a hero mid-zone through the game's own unused
                  ; routine (0x46c9f0) - experimental; 0/absent = the mod's own fallback (team menu)
```

| ini | registration patched? | `xml2fixFeature("forcedteams")` | `xml2fixFeature("addhero")` |
|---|---|---|---|
| no `ForcedTeams` key | no | statement dropped, so the script's variable stays 0 | same |
| `ForcedTeams=0` | yes | 0 | 0 |
| `ForcedTeams=1` | yes | 1 | `AddHero` (0/1) |

The feature is read from a DLL variable when the call happens, not when the script compiles. So a later Options-menu toggle (`options_menu.cpp`) could flip it without a restart.

### 2.2 install

| step | action | log |
|---|---|---|
| 1 | Image base must be `0x400000` (as in `new_game::install`). Read `[Game] ForcedTeams`; absent means return. | - |
| 2 | Every guard in `forced_teams_rules::guards` (table below) goes through `bytes_match` (`__try` read, as in `limits.cpp`). On the first mismatch: **patch nothing**. | `forced teams: 0x%08X isn't the retail code (%s) - no script functions added; the mod's scripts open the team menu` |
| 3 | `static_assert(19 + 0x121 + std::size(extra) <= 0x140)`. `memcpy(table, (void*)0x68a908, 0x121*16)`, then append `extra[]`. | - |
| 4 | Write `0x49fe31 = &table` and `0x49fe36 = 0x121 + N` with the `limits.cpp` `patch()` helper: all pages made writable first, then the writes, then protection restored in reverse. The two sites share a page. | `forced teams: %u script functions added (seatParty, setSkinset, pushParty, popParty, addHero, getPartyMember, xml2fixFeature); ForcedTeams=%d AddHero=%d` |
| 5 | Handlers log each call at the moment it happens (they are rare: mission starts and joins), e.g. `seatParty(magma,,,) -> magma / - / - / -` or `seatParty: 'profxgladiator' isn't a herostat hero - party left as it is`. | - |

Guard table (all **[v]**; `forced_teams_rules.hpp`, checked by `xml2_test` against `docs/research/XMen2.exe`):

| va | bytes | what |
|---|---|---|
| `0x49fe30` | `6808a968006821010000e8` | registration pushes |
| `0x4d7637` | `81bf4819000040010000` | tree cap 320 |
| `0x4d8694` | `6a13` | 19 builtins |
| `0x68d36c` | `30fe4900` | script interface vt+0 |
| `0x68bb08` | `10fe490028bb6800189c680068196800` | last retail entry |
| `0x686f0c` / `0x686f3c` / `0x686f8c` | `10c84600` / `60d44600` / `f0c94600` | game vt+0xf0 / +0x120 / +0x170 |
| `0x685488` / `0x68548c` / `0x6854c8` | `c0ac4400` / `d0984400` / `c0b74400` | registry vt+0x3c / +0x40 / +0x7c |
| `0x69a834` / `0x69a838` | `b0be5500` / `10c45500` | console run now / queue |
| `0x4d5830` | `8b511c33c085d274` | args get |
| `0x4d6570` | `8b9190c0000033c0` | make int |
| `0x425bf0` / `0x425bc0` | `568b74240885f657` / `568b3185f67507b8` | intern into handle / handle to text |
| `0x4a1700` | `83ec1c568b742428` | entity handle by name |
| `0x4a7085` | `8b1548847100` | character class bit (`[0x718448]`) |
| `0x48a0e0` | `a108b17200` | mission manager (side stack via vt+0x44, count +0x4dc) |
| `0x4499e0` | `515356 8bf1 8b8e30230100` (hero list count `+0x12330`) | herostat hero walk |
| `0x6d8aa0` | `902f680000000000 2092680001000000` | costume table (`default`/0, `astonishing`/1) |
| `0x68d284` / `0x68d31c` / `0x68d584` | `"restorelastzone %s"` / `"loadmap %s 0 1"` / `"pushsidemission %d"` | the commands the handlers send, same text as retail |

### 2.3 Handler skeleton (thiscall through `__fastcall` + unused edx, as `limits.cpp` / `options_menu.cpp` do)

```cpp
struct func_entry { void* func; const char* name; const char* ret; const char* args; };
using get_arg_t   = void*(__fastcall*)(void* args, void*, int i);                 // 0x4d5830
using sys_t       = void*(__cdecl*)();                                            // 0x4d8770
using make_int_t  = void*(__fastcall*)(void* sys, void*, int v);                  // 0x4d6570
using make_str_t  = void*(__fastcall*)(void* sys, void*, const char* s);          // 0x4d9430
using intern_t    = void (__fastcall*)(std::uint32_t* dst, void*, const char* s); // 0x425bf0
using seat_t      = void (__fastcall*)(void* game, void*, int slot, std::uint32_t* h); // game vt+0xf0
using add_hero_t  = bool (__fastcall*)(void* game, void*, const char* name);      // game vt+0x170
using console_t   = bool (__fastcall*)(void* console, void*, const char* line);   // vt+0x18 / vt+0x1c
const char* arg_string(void* args, int i);  // get(i)->vt[5]()
int         arg_int(void* args, int i);     // get(i)->vt[4]()
void* __cdecl seat_party(void* args);       // returns nullptr ('n')
// ... one per function; each wraps its engine calls in __try and logs instead of crashing
constexpr func_entry extra[] = {
    {&xml2fix_feature, "xml2fixFeature", "i", "s"},   {&seat_party, "seatParty", "n", "ssss"},
    {&set_skinset, "setSkinset", "n", "ss"},          {&push_party, "pushParty", "n", "a"},
    {&pop_party, "popParty", "n", "s"},               {&add_hero, "addHero", "i", "s"},
    {&get_party_member, "getPartyMember", "s", "i"}};
func_entry table[0x121 + std::size(extra)];           // static: the tree keeps pointers into it
```

Signature strings: the exe has no `"ssss"`, so the DLL owns all its signature literals (script-functions 1).

### 2.4 xml2_test additions

| test | against |
|---|---|
| every `guards` row | the exe copy (as `limits_rules`) |
| `split_heroes("magma,,x")` -> trimmed, lowercased, deduplicated, compacted | pure |
| costume lookup: `magmacivilian` is refused (the pipeline maps it, 3.5); `CIVILIAN` = 8 | pure, table copy |
| table build: 0x128 entries; the first 0x121 are byte-identical to the exe's; no extra name collides with a retail name (walk the exe table plus the 19 builtins at `0x6903d8`) | exe copy |

---

## 3. Pipeline changes (`tools/xml1build`)

### 3.1 Build option and plan

- `build_xml1.py --forced-teams menu|seat`.
  - `menu` = today's output, unchanged.
  - `seat` = emit the blocks below.
  - Default is `menu` until in-game checks 1-6 (section 6) pass, then `seat`.
- `harness.py install --forced-teams [--add-hero]` writes `[Game] ForcedTeams=1` (`AddHero=1`).
- New `scripts.forced_party_plan(ctx)` computes, per mission, from `mission_plan.json`:
  - the seat list (XML1 rule 1.4: REQUIRED + RECOMMENDED - RESTRICTED, capped at maxheros, lowercase, file order), minus `JOIN_LATER = {'alison': {'cyclops'}, 'dr_mag2': {'cyclops'}}`;
  - the skinset args (3.5);
  - a status: `seat`, `menu` (a name is not in the port herostat), or `cut` (the load zone has no `Maps/<zone>.XMLB`).
- Problem counts `forced_party_unseatable` and `forced_party_cut_zone`.

### 3.2 The generated block (begin bodies of the forced missions)

`scripts_transform.forced_party_in_bodies(lines, plan)` runs in `scripts._script_text` **after** `choose_team_in_bodies`. It matches the same marker and exact-body occurrences (`BEGIN_MARKER`) and replaces the body's final `loadMapChooseTeam("<z>" )` with:

```
# ( "x1: XML1 forces this party (xml2-fix [Game] ForcedTeams); without it the team menu opens" )
x1ft = iadd(0, 0 )
x1ft = xml2fixFeature("forcedteams" )
if x1ft == 1
     seatParty("magma", "", "", "" )
     setSkinset("civilian", "magma" )
     loadMapKeepTeam("mansion/man1a/mansion1a_1" )
else
     loadMapChooseTeam("mansion/man1a/mansion1a_1" )
endif
```

- `x1ft = iadd(0, 0 )` declares an int. Without the DLL the `xml2fixFeature` line is dropped and `x1ft` stays 0. An *undeclared* variable would drop the `if` line itself (script-functions 7.3), so this line is required.
- The `unlockCharacter` lines, the movie and the `setGameFlag` resets stay above the block, unchanged. Keeping the REQUIRED unlocks makes a seated Magma a normal unlocked hero in later team menus (decision 7.4).
- `choose_team_in_bodies` stays and still produces the `else` branch, which is the no-DLL behaviour. Its docstring and SPEC 12.6 ("XML2 has no script function...") gain "without xml2-fix [Game] ForcedTeams".
- The New Game hook (`menus/new_game*.py`, alison) is **not** touched: `[Game] NewGameTeam=wolverine` plus `loadMapKeepTeam` already gives XML1's opening (T8, harness default).

### 3.3 Per-mission emission (all 49; seat rule 1.4; copies = the begin script plus the scripts that inline the body)

| mission | act | `seatParty` args | `setSkinset` args | load zone | copies | status | notes |
|---|---|---|---|---|---|---|---|
| alison | 1 | wolverine | default, "" | nyc/alison/nyc1_1_1 | 3 | seat (begin_alison only) | Cyclops joins at nyc1_1_3 (3.6); New Game hook unchanged |
| mansion1 | 1 | magma | civilian, magma | mansion/man1a/mansion1a_1 | 4 | seat | |
| harrp_briefing | 1 | magma | civilian, iceman,colossus | mocap/mocap2/briefing_1_2_41 | 1 | seat | Magma in default (literal XML1, decision 7.5) |
| jug_fb | 1 | cyclops, beast, iceman, phoenix | 60s, beast,cyclops,iceman,phoenix,wolverine | mansion/jugrnt/jugrnt01 | 2 | seat | side mission of mansion2 (3.4) |
| mansion2 | 1 | magma | civilian, magma | mansion/man2/mansion_back2 | 2 | seat | |
| sewer_muir_briefing | 1 | magma | civilian, iceman,colossus | mocap/mocap3/briefing_1_4_13 | 1 | seat | as harrp_briefing |
| dr_mag1 | 1 | magma | default, "" | mansion/dr_mag/dr_mag01 | 1 | seat | side mission of mansion2 |
| sent_fb | 1 | nightcrawler, cyclops, phoenix, wolverine | 70s, colossus,cyclops,nightcrawler,phoenix,wolverine | nyc/fb/nyc_fb1 | 2 | seat | RECOMMENDED seated; side mission of mansion2 |
| mansion3 | 3 | magma | civilian, magma | mansion/man3/mansion3_2 | 2 | seat | |
| nuke_briefing | 3 | magma | default, "" | mocap/mocap5/briefing_2_1_16 | 1 | seat | |
| mansion3_dangerroom | 3 | magma | civilian, magma | mansion/man3/danger_room | 2 | seat | |
| mansion3_uniform | 3 | magma | default, "" | mansion/man3/mansion3_2 | 2 | seat | Magma back in uniform |
| wx_fb_start | 3 | wolverine | weaponx, wolverine | weapon_x/wfb/wx1_1 | 1 | seat | side mission of mansion3 |
| dr_mag2 | 3 | magma | civilian, iceman,colossus | mansion/dr_mag2/mag_nyc1 | 1 | seat | Cyclops joins at mag_nyc4 (3.6); not a side mission (ends by chaining into mansion3_dangerroom's forced body) |
| muir2 | 4 | magma | default, "" | muir_is/muir2/muir_in2 | 2 | seat | |
| muir2_reboot | 5 | magma | default, "" | muir_is/muir2/mui_comcore | 1 | seat | keepheroes: XML1 keeps Magma (same result); side mission of muir2 |
| mansion4 | 5 | magma | default, "" | mansion/man4/mansion_back4 | 2 | seat | |
| grso_briefing | 5 | magma | default, "" | mocap/mocap6/briefing_2_5_5 | 1 | seat | |
| astral_wx_briefing | 5 | magma | default, "" | mocap/mocap7/briefing_2_5_14_7 | 1 | seat | |
| grso_debriefing | 5 | magma | default, "" | mansion/man4/grso_debriefing | 1 | seat | |
| mansion4_grso_done | 5 | magma | default, "" | mansion/man4/grso_debriefing | 1 | seat | |
| astral_briefing | 5 | magma | default, "" | mocap/mocap7/briefing_2_5_14_7 | 1 | seat | |
| astral1 | 5 | profxastral, phoenix, frost | default, "" | astral/ast1/astral1_1 | 3 | seat | ProfXAstral is a port herostat entry (SPEC 12.2) |
| astral1b | 5 | phoenix, frost | default, "" | astral/ast1/astral4_3 | 2 | seat | |
| old_wx | 5 | cyclops | default, "" | weapon_x/old/wx2_1 | 1 | seat | |
| secret_wx | 5 | wolverine, cyclops | default, "" | weapon_x/secret/wx3_1 | 2 | seat | |
| end_astral | 5 | magma | default, "" | mansion/man5/subbasement5b | 1 | seat | |
| mansion5 | 6 | magma | default, "" | mansion/man5/mansion5_1 | 2 | seat | |
| healer_briefing | 6 | magma | default, "" | mocap/mocap8/briefing_2_5_22 | 1 | seat | |
| mansion6 | 7 | magma | default, "" | mansion/man6/mansion6_2 | 1 | seat | |
| muir_riots_grso_briefing | 7 | magma | default, "" | mocap/mocap9/briefing_3_1_8 | 1 | seat | |
| muir3brig | 7 | phoenix | default, "" | muir_is/muir3/muir_brig | 2 | seat | `removeFromGroup("phoenix")` stays dropped (T11); the next mission start reseats |
| nyc_rooftops | 7 | wolverine | default, "" | nyc/riots/nyc_roof1 | 1 | **cut** | zone missing; conversation 3_2_6 still offers it (1.6) |
| mansion7 | 8 | magma | default, "" | mansion/man7/status_meeting | 2 | seat | |
| astral2_briefing | 8 | magma | default, "" | mocap/mocap11/briefing_3_6_7 | 1 | seat | |
| end_astral2 | 8 | magma | default, "" | mocap/mocap10/briefing_3_6_6 | 1 | seat | |
| end_hive | 8 | magma | default, "" | mocap/mocap12/briefing_3_9_0 | 2 | seat | |
| mansion8 | 9 | magma | default, "" | mansion/man8/subbasement8 | 2 | seat | |
| asteroid_briefing | 9 | magma | default, "" | mocap/mocap13/briefing_3_9_8 | 2 | seat | |
| start_astral3 | 9 | magma | default, "" | mansion/man8/subbasement8b | 1 | seat | |
| astral_sk | 9 | profxgladiator | default, "" | astral/savepx/final_astral | 2 | **menu** | not a herostat hero; side mission of astral3; stays loadMapChooseTeam, no push/pop until converted |
| asteroid_rock | 9 | frost, iceman, storm, wolverine | default, "" | astroid_m/visit1/asteroid1_1 | 3 | seat | RECOMMENDED seated (XML1 builder) |
| boss_mystique | 9 | wolverine | default, "" | nyc/alison/nyc1_1_2b | 1 | seat | Danger Room disc replay (not reachable from New Game) |
| boss_blob | 9 | wolverine, cyclops | default, "" | nyc/alison/nyc1_1_3 | 1 | seat | replay; the join trigger then finds Cyclops already seated (`vt+0x170` returns true; the NPC double stays, cosmetic) |
| ice_wolverine | 9 | wolverine | default, "" | haarp/ice_sq/ice_sq1 | 1 | **cut** | zone missing |
| boss_sabreroof | 9 | wolverine | default, "" | nyc/riots/nyc_roof1 | 1 | **cut** | zone missing |
| boss_havok | 9 | cyclops | default, "" | weapon_x/old/wx2_2 | 1 | seat | replay |
| boss_shadowking | 9 | profxgladiator | default, "" | astral/savepx/final_astral | 1 | **menu** | not a herostat hero |
| status_meeting | 9 | magma | default, "" | mansion/man7/status_meeting | 1 | seat | replay |

`seatParty` args are listed without the padding `""`; the emitted call always has four strings.

### 3.4 Side missions (XML1 `beginSideMission` / `endSideMission`): push at the begin site, pop at the end site

The callers come from `rewrite_scripts.SIDE_CALLS` and `SIDE_PARENT`, evaluated for this doc.

| side mission | begin site (what to change) | caller zone, mission (skinset) | end site | end block |
|---|---|---|---|---|
| jug_fb | `mansion/man1b/loadjuggernaut.py`, after the `beginSideMission(jug_fb)` marker | subbasement2, mansion2 (magmacivilian) | `missions/jug_done.py` | XML1 has **no `endSideMission`** here: its `jug_done.py` does `mission COMPLETE` + `loadMap("mansion/man1b/subbasement1b")`. The port emits `loadMapKeepTeam(subbasement1b)`, the census's confirmed bug. New: `setSkinset("civilian","magma")` + `popParty("mansion/man1b/subbasement1b")`. This returns to the **push** zone and spot (subbasement2), not subbasement1b (decision 7.6). |
| sent_fb | `mansion/man2/loadsentinel.py` | mansion2_1, mansion2 | `nyc/fb/nycfb4_finish.py` | `setSkinset("civilian","magma")` + `popParty("mansion/man2/mansion2_1")` |
| dr_mag1 | inline, conversation `mansion/man2/1_4_9` -> `x1/missions/begin_dr_mag1` | subbasement2, mansion2 | `mansion/dr_mag/fmvexit.py` | `setSkinset("civilian","magma")` (Magma is in both parties) + `popParty("mansion/man2/subbasement2")` |
| wx_fb_start | inline, conversation `mansion/man3/2_1_15_meet_wolverine` | hangar3, mansion3 (magmacivilian; **UNVERIFIED** that it cannot be offered during mansion3_uniform (default)) | `weapon_x/wfb/end_fb.py` | `setSkinset("civilian","magma")` + `popParty("mansion/man3/hangar3")` |
| muir2_reboot | inline, conversation `muir_is/muir2/2_4_7` | muir_in2, muir2 (default) | `muir_is/muir2/endreboot.py` | `setSkinset("default","")` + `popParty("muir_is/muir2/muir_in2")` |
| astral_sk | `astral/savepx/xcrystal_destroyed.py` | astral2_3, astral3 (default) | `astral/savepx/shadowking_defeated.py` | only once ProfXGladiator is seatable (3.3); until then T9-simple |
| nyc_rooftops | inline, conversation `nyc/riots/3_2_6` | nyc3_1_3, riots | none found | cut (3.3). Recommend dropping the response in a later pass (out of scope). |

Begin sites:
- **Script sites**: insert after the side-mission marker, before the inlined begin body:
  ```
  x1ft = iadd(0, 0 )
  x1ft = xml2fixFeature("forcedteams" )
  if x1ft == 1
       pushParty("_ACTIVE_HERO_" )
  endif
  ```
- **Inline sites**: the conversation's `chosenscriptfile` currently names `x1/missions/begin_<s>`, which only the side-mission call uses. Generate `x1/missions/side_<s>.py` = the push block + the begin body, and re-point the inline rewrite (`scripts.rewrite_data_tree`) to it.

End sites: the pass replaces the generated `loadZone("<caller>", "" )` after the `# ( "XML1 endSideMission from side mission s" )` marker (keeping `setCurrentAct`) with:

```
if x1ft == 1
     setSkinset("civilian", "magma" )
     popParty("mansion/man2/subbasement2" )
else
     loadMapChooseTeam("mansion/man2/subbasement2" )
endif
```

The `x1ft` declaration and assignment go above this block.
- The `else` branch is **roster T9's "simplest variant"**, now also the no-DLL fix: the player at least re-picks instead of keeping the flashback party.
- `popParty` falls back to the same team-menu load when no record is on the stack. That covers an old save, a flashback begun with `ForcedTeams=0`, or a debug start.
- Nesting depth is 1: no XML1 flashback starts inside another (roster), which fits the 2-record stack.

`dr_mag2` needs no push or pop. Its `endsidemission.py` chains into `begin_mansion3_dangerroom`, whose forced block reseats Magma.

### 3.5 Costumes (all 101 begin bodies)

`setSkinset` is global (1.3.2) and stateless. Every begin body therefore gets it inside the feature branch; for `blackbirdMenu` and `loadMapKeepTeam` bodies this is a 5-line `if` with no seat. The result: every hero loaded during mission X wears X's skinset variant if it has one, otherwise default. That is exactly XML1's per-mission derivation (party-seating 8), and free missions work because costumes are set before the menu.

Argument mapping, from XML1 `herostat.eng` (read for this doc; the port's herostat has every variant listed here):

| XML1 skinset | missions | `setSkinset(costume, heroes)` |
|---|---|---|
| default / none | 89 | `("default", "")` |
| magmacivilian | mansion1, mansion2, mansion3, mansion3_dangerroom | `("civilian", "magma")`: the port renames Magma's `skin_magmacivilian` to slot 8 (`heroes.py COSTUME_RENAME`) |
| civilian | harrp_briefing, sewer_muir_briefing, muir_int, dr_mag2, sewers_hub2 | `("civilian", "iceman,colossus")`: only they had `skin_civilian` in XML1 |
| 60s | jug_fb | `("60s", "beast,cyclops,iceman,phoenix,wolverine")` |
| 70s | sent_fb | `("70s", "colossus,cyclops,nightcrawler,phoenix,wolverine")` |
| weaponx | wx_fb_start | `("weaponx", "wolverine")` |

The hero list is needed because the DLL cannot tell Magma's slot 8 (from `magmacivilian`) from Iceman's slot 8 (from `civilian`).

Deviation: a player who picks a 60s/70s/weaponx/civilian costume in XML2's team menu loses it at the next mission start. Costumes 1, 2, 6 and 7 are kept, as XML1 kept player costumes.

### 3.6 Joins: T7, `addHero` and `joinHero`

`join_hero` (scripts_transform) keeps T7 as the fallback and gains an `addHero` branch.
- The `x1join` bit is now set **before** the branch. After `addHero` there is no reload, but a later save/load or re-entry re-arms the trigger and re-spawns the double, and the existing `join_hero_zone_guard` still clears them.
- The `waittimed`/popup tail stays before the block, as in T7.

```
createPopupDialogXml("dialogs/tut15" )   # nyc: XML1's join popup first ...
waittimed ( 0.500 )                      # ... the wait runs out only once it is closed (SPEC 19.7)
unlockCharacter("cyclops", "" )
setGameFlag("x1join", 1, 1 )
x1ah = iadd(0, 0 )
x1ah = xml2fixFeature("addhero" )
if x1ah == 1
     x1ah = addHero("cyclops" )
     remove ( "cyclops_x1double", "cyclops_x1double" )
endif
x1jh = iadd(0, 0 )
if x1ah == 0
     debug("x1: xml2-fix forced teams" )
     x1jh = xml2fixFeature("joinhero" )
endif
if x1jh == 1
     remove ( "cyclops_x1double", "cyclops_x1double" )
     x1ah = joinHero("cyclops" )
endif
if x1ah == 0
     # ( "x1 addHero(cyclops): T7 - save the spot and open the team menu" )
     remove ( "cyclops_x1double", "cyclops_x1double" )
     extractionPointChange("_ACTIVE_HERO_", 0 )
endif
```

`joinHero` (1.3.6) comes after the dormant `addHero` and before T7; its double is removed first (the reload respawns
the zone and the zone guard removes the new double, again at the end of the zone script: the spawner's instant
spawn comes after the guard's removes). The source's `createPopupDialogXml("dialogs/tut15")` comes before the join
with a `waittimed` after it: pending under the team menu it broke the menu in game (2026-09-28 night), shown from the
reloaded zone's script it was lost under the loading screen, and a wait after it runs out only once the player has
closed it (verified). joinHero verified in game the same night (SPEC 19.7).

The `remove` after a successful `addHero` is a safety net. If `vt+0x170`'s NPC match (step 4) misses the spawner-made double (**UNVERIFIED**), the double would otherwise stand next to the joined hero. It must come *after* `addHero`: removing first loses the spot the hero takes over.

Mission-start resets (`join_hero_mission_reset`) are unchanged.

### 3.7 What stays, what goes

| existing piece | fate |
|---|---|
| `choose_team_in_bodies` / SPEC 12.6 | stays; produces the `else` branch; text updated |
| T7 (`join_hero`, zone guard, mission reset, `JOIN_DOUBLE_SPAWNERS` rename) | stays; becomes the `addHero` fallback |
| T8 (New Game keepteam + NewGameTeam) | unchanged; already XML1-exact |
| T9 (unbuilt) | built by 3.4: faithful with the DLL, "simplest variant" without it |
| T11 `removeFromGroup` dropped | stays dropped (the next begin reseats) |
| roster 4 "Magma-solo cannot be enforced" | obsolete under `--forced-teams seat` |

### 3.8 Test hooks

`testhooks.py` gains `--start-party h1,h2 [--start-skinset costume:heroes]`. With `--start-zone`, it emits the 3.2 block in `menus/new_game*.py` in place of the plain `loadMapKeepTeam`. This allows a forced-team start in any zone without playing up to it.

---

## 4. Validator additions (V14 "forced teams", `validate.py` + `validate_script.py`)

| id | check | severity |
|---|---|---|
| V14a | `research/scripts/xml2fix_api.json` (the 7 entries of 1.2, versioned with the xml2-fix commit) is merged into `ScriptChecker`'s API **only** for `--forced-teams seat` builds. In a `menu` build, any of the 7 names is an error. | error |
| V14b | Every xml2-fix call sits inside an `if <v> == 1` whose `<v>` was declared with `iadd(0, 0 )` and then assigned from `xml2fixFeature("forcedteams"\|"addhero")` earlier in the same script. The only exception is `addHero`'s own assignment inside the `addhero` branch. Without this, a no-DLL install drops the `if` and runs the body unconditionally. | error |
| V14c | Every forced-body occurrence: the seat branch's `seatParty` args equal `forced_party_plan[m]` (4 literals, herostat names of *this* build, compact, no duplicates, at least 1 non-empty). The next statement in the branch is `loadMapKeepTeam(z)`, and the `else` branch is `loadMapChooseTeam(z)` with the same `z`, which must have `Maps/<z>.XMLB`. | error |
| V14d | `setSkinset` costume is one of the table 0x6d8aa0 names; heroes are herostat names that have that variant in the port herostat; every begin body (101) has exactly one `setSkinset`. | error |
| V14e | Each side mission with a `pushParty` begin site has a `popParty` at **every** end site (and vice versa). `popParty` is the last statement of its branch and the only console-sending call of that script run (`popParty`, `loadMap*`, `extractionPoint*`, `blackbirdMenu`, `restorelastzone` count toward the 2-command queue). The fallback zone exists. | error |
| V14f | `addHero` / `joinHero` only in `JOIN_HERO_SCRIPTS`, preceded by `setGameFlag("x1join", bit, 1 )`, followed by the `if x1ah == 0` T7 block; `joinHero` right after the double's `remove`, last in its branch, the only console command of its run. | error |
| V14h | No popup in a join script; the zone script's popup block exactly when the join script sets the popup bit. V7: no menu / reload call after a `createPopupDialogXml` in any XML1 script. | error |
| V14g | Report the `forced_party_unseatable` (astral_sk, boss_shadowking) and `forced_party_cut_zone` (nyc_rooftops, boss_sabreroof, ice_wolverine) counts. Also report any conversation or script that can start a cut mission (today: `nyc/riots/3_2_6`). | warn |
| V10 | unchanged; New Game hooks keep `loadMapKeepTeam` + NewGameTeam | - |
| selftests | `scripts_selftest`: 3.2 on begin_mansion1 (+ an inlined copy), 3.4 on loadjuggernaut / jug_done / an inline side script, 3.6 on both add_cyclops; `validate_selftest`: V14b negative case (undeclared variable) | - |

---

## 5. The conversation-speaker risk and what forced parties change

Code facts (conversation-speakers.md, spot-checked: `runwithoutuser` does not appear in the exe; the `"default"` participant string is at `0x682f90` **[v]**):
- An absent `%NAME%` speaker costs only the talk animation. Line advance never reads the speaker.

| risk | without forced parties | with `ForcedTeams=1` |
|---|---|---|
| 490 party-dependent hero lines (161 conversations); Magma has 321 lines in 107 conversations, including all 61 reply menus | cosmetic: no talk animation when the speaker is not in the zone | Magma is present in every Magma-solo hub and briefing, so her lines animate as in XML1. Other heroes' party-dependent lines (Phoenix 24 conversations, Wolverine 21, ...) are mostly in free missions and remain cosmetic. |
| Same-name clash (a hero in the party **and** a CHRB NPC with that name, e.g. Phoenix at mansion1a_1 in Owen's run): the talk animation goes to either entity, and **`remove("phoenix")` hits the party hero** (SPEC 18) | open in 16 of the 18 `hero_npc_zones` | Of the 16 open zones, 13 belong to forced missions (world `mission=`: mansion1..5 hubs, dr_mag2 `mag_nyc3`, alison `nyc1_1_2b`, old_wx `wx2_2`). There the forced party excludes the NPC's hero, which is exactly the case XML1 relied on (SPEC 18 "XML1 only did this where its forced teams kept that hero out"). **Closed 2026-09-28 (SPEC 18.1)**: the NPCs are spawners (`monster_name`; the CHRB only lists what to load), renamed `<hero>_x1double` with their scripts, inline code and conversations: `muir_is/muir2/muir_in2` Colossus, Cyclops, Storm (ForcedTeams=0 opens muir2's team menu; the free `muir_in2` / `nuke_col` missions are only in XML1's debug level list `ui/menus/map_list.xml`), `nuke_plant/nuke/nuke2_2` Colossus, `nyc/riots/nyc3_1_2` Psylocke, `sewers/hub/sewers1_2_4` and mocap4 Gambit: XMen2.exe keeps unlocks in the profile (team-menu pick checks `0x48f770`; `resetgame` clears only the registry bits), so from the second New Game on the hero can be in those free parties. The doubles keep their talk animation (`%HERO_X1DOUBLE%` tokens + npcstat speaker entries). Still open with ForcedTeams=0 only: the forced hubs and mocap1 (SPEC 18.1). |
| The 1_2_1_2 line-0084 stall | not caused by the speaker. The leading candidate is the accept input never registering; conversation-speakers 6 gives a memory probe | Not fixed by forced parties. But a repro with Magma solo (test 1) reproduces XML1's exact setup, separating "party mix" from "input". |
| `runwithoutuser` ignored (307 lines need a key press), voiced responses cut after one frame, cursor clamp `0x45b5fc` | unchanged | Unchanged. These are separate xml2-fix features (conversation-speakers 9); they need no script functions. |
| XML1's own party checks (`getName("_HERO1_".."_HERO4_")`, e.g. `asteroid_m/alisoncheck.py`) | answer for whatever party the player picked | answer as in XML1 |

---

## 6. In-game test plan (ordered; each run is short)

Use the background harness (`harness.py install <out> --mode windowed`, `RunInBackground=1`; the test save folder is the harness default).
- Tests 2 onward use `--forced-teams`.
- If the pipe `script`/`console` commands land (uncommitted in xml2-fix's `test_input_rules.hpp`), the calls can be typed through `fixinput.py`. Otherwise use the 3.8 hooks.
- Read `xml2-fix.log` after every run.

| # | setup | pass when |
|---|---|---|
| 1 | **No new code.** Today's build, `[Game] NewGameTeam=magma`, `--start-zone mansion/man1a/mansion1a_1` | Magma alone spawns and is controlled by player 1. HUD shows 1 portrait. No crash on `_HERO2_` calls. The tour conversations run with Magma present (talk animation). Does 1_2_1_2 line 0084 advance? If not, run the conversation-speakers 6 probe. Save, load: Magma still alone. This settles the 1-hero-party UNVERIFIEDs before any DLL work. |
| 2 | DLL with the module, `ForcedTeams=1`, hook `--start-party magma --start-skinset civilian:magma` into mansion1a_1 (NewGameTeam=wolverine) | Log: "7 script functions added". Wolverine is replaced by Magma alone, in skin 15803 (civilian). Log shows `seatParty(magma,,,)`. |
| 3 | Same build, `ForcedTeams=0`, then with no `[Game]` key at all | Both open the **team menu** (the `else` branch). The no-key log has no "added" line. Proves the `iadd` feature-detect. |
| 4 | `--start-zone mocap/mocap1/briefing_1_1_6_5` (its inline `beginMission(mansion1)` copy) | Magma solo, civilian, in mansion1a_1. Walk mansion1a_1: the end-of-tour `remove("phoenix")` branch removes only the NPC. |
| 5 | From mansion1 to `harrp_briefing` (Magma, default) to `haarp` (blackbirdMenu) | Magma is shown in uniform in the briefing (literal XML1, decision 7.5). The team menu opens with Magma seated: can she be removed or kept, and does the confirm load haarp? (party-seating check 6) |
| 6 | mansion2: `loadjuggernaut` -> jug_fb | 60s Cyclops/Beast/Iceman/Phoenix in jugrnt01. Log shows `pushParty` (count 1). Save, load inside jugrnt01, finish: back at the push spot (subbasement2) with Magma in civilian and the 60s costumes reset. Log: `popParty -> restorelastzone 0`. |
| 7 | sent_fb (multi-zone flashback, nyc_fb1 to nyc_fb4) | Zone links work while a record is on the stack (every `loadmap` then passes flag 1 to `CMap::LoadMap`, `0x5f47e0` **[v]**; meaning **UNVERIFIED**), and the return is correct. **Highest-risk check.** |
| 8 | `AddHero=1`: nyc1_1_3 trigger, then save/load; later dr_mag2 mag_nyc4 | Cyclops appears on the NPC's spot with no reload, as slot 1, and the HUD updates. The double is gone. After save/load the trigger and double are cleared by the guard. With `AddHero=0` the T7 menu path still works. (In game: `0x46c9f0` returns true and seats nobody; AddHero stays 0.) |
| 8b | Default (`JoinHero` on): nyc1_1_3 trigger (walk in), then mag_nyc4 | The tut15 popup (nyc); closed: no team menu, the log shows `joinHero("cyclops") -> 1: pushsidemission ...`; the zone reloads, Wolverine (Magma) on the saved spot, Cyclops from `player_start01`, the HUD shows 2 heads, the double and trigger gone (**passed 2026-09-28 night** for nyc1_1_3, build/_jh). Later loads of the zone: Cyclops spawns, the double is removed late. `JoinHero=0`: the T7 menu after the popup is closed. |
| 9 | astral1 (3 heroes incl. ProfXAstral, MUSTLIVE), asteroid_rock (4), muir3brig (Phoenix) | Parties exact. The astral MUSTLIVE logic is unaffected. |
| 10 | Optional: 2 local players in a Magma hub | Record what player 2 gets (**UNVERIFIED**, out of scope). |

---

## 7. Decisions for Owen, and every UNVERIFIED item

### Decisions

| # | decision | options / recommendation |
|---|---|---|
| 7.1 | Faithful XML1 parties vs player choice | The ini switch is the answer: `[Game] ForcedTeams=1` (faithful) / `0` (team menu, today's port). The build emits both branches. Recommend `1` as the port's harness and release default once tests 1-7 pass. An Options-menu toggle is possible later (2.1). |
| 7.2 | `addHero` via the dormant `0x46c9f0` vs T7 | Ship `AddHero=0` (T7, verified in game 2026-09-28) until test 8 passes, then `1`. `0x46c9f0` seats nobody in game; `joinHero` (1.3.6, on by default) replaces the menu, T7 stays the fallback. |
| 7.3 | ProfXGladiator herostat entry | Needed to seat `astral_sk` and `boss_shadowking`; until then they keep the team menu. |
| 7.4 | Keep the REQUIRED `unlockCharacter` lines in seat mode? | Recommend **keep**: a seated but locked Magma in later team menus is untested (test 5). Dropping them gives XML1's "locked until met" roster (roster decision 2) but risks the menu. |
| 7.5 | `civilian`-skinset briefings and dr_mag2: literal XML1 (Magma in uniform) or intent (Magma civilian) | Literal is the default (3.5). The alternative is one table edit: `civilian -> "iceman,colossus,magma"`. |
| 7.6 | jug_fb return | `popParty` returns to the push zone and spot (subbasement2, XML1's `endSideMission` semantics). XML1's `jug_done.py` instead loaded `man1b/subbasement1b` with no pop (what XML1's `mission COMPLETE` does with the pushed record is not traced). Alternative: `seatParty` from the record's names + `loadMapKeepTeam(subbasement1b)` + a DLL pop (needs a 3rd side-stack call). |
| 7.7 | Cut missions (`nyc_rooftops`, `boss_sabreroof`, `ice_wolverine`) | Drop the `3_2_6` response that starts `nyc_rooftops` (a live load of a missing zone), in a separate pass. |
| 7.8 | Remaining SPEC 18 zones (`muir_in2`, `nuke2_2`) | Done 2026-09-28 (SPEC 18.1): renamed like T7 (spawner `monster_name`), with `nyc3_1_2` Psylocke, `sewers1_2_4` and mocap4 Gambit; their conversations and a speaker stats entry per double keep the talk animation. |

### UNVERIFIED (none of these block writing the code; tests in section 6 settle most)

- A 1-3 hero party in story zones: HUD portraits, player-1 controller, co-op players beyond the party size (test 1, 10).
- The team menu with a seated Magma (locked or unlocked): list, keep, confirm (test 5).
- `game vt+0x170` in practice. It has never run in retail. Does its NPC match (`0x46cacc`, filter `0x68202c`) find a spawner-made double? (test 8)
- The meaning of `CMap::LoadMap`'s flag 1 while a side record is on the stack (`0x484e00-0x484e48`), across multi-zone flashbacks (test 7).
- The contents of the game-state block `game+0x53c` saved by `pushsidemission` (`vt+0x200`) and restored by `restorelastzone` (`vt+0x204`). The design keeps them paired as retail does.
- XML1: why `alison` and `dr_mag2` don't start with REQUIRED Cyclops although `0x18d6d0` seats REQUIRED heroes (1.4). Also what `mission("jug_fb","COMPLETE")` did with the pushed record.
- XML1's fallback to default when a hero lacks the mission's skinset variant (3.5 and 1.6), and that `0x341986` is `atoi` (1.3.4).
- Whether `wx_fb_start` can be offered during `mansion3_uniform` (its caller skinset would then be default, 3.4).
- Script pools: whether the 620 statement nodes are per compile or global. The blocks add about 10-15 statements per script; the largest port script today has 159.
- Headroom in the global string table (0x14400 bytes) for the new names and literals (script-functions Q5).
- The meaning of `CStats+0xc0 vt+0x28` (team-menu open clears such slots, `0x5e3868`).
- The hazard zones the census's regex did not confirm. Section 5 classifies them by world `mission=` instead: `mansion2_1`, `mansion3_1`, `mansion_back4`, `mansion5_1` and `wx2_2` are forced-mission zones; `nuke2_2` and `sewers1_2_4` are not. Settled by validate V6 `_v6_hero_npcs` (every entity call of the zone's scripts, inline code and conversations; SPEC 18.1).
- Whether the xml2-fix pipe `script` command lands (test convenience only).
