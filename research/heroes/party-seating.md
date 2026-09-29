# Party seating: forcing an exact XML1 party from script (XML2 engine + xml2-fix)

Written 2026-09-28 (Opus research subagent, read-only). Companion to `roster.md` (sections 1, 2, 4), `engine.md`
(2, 5, 6) and `DESIGN.md` D6. All XMen2.exe addresses were read in this session: disassembly from the retail image
(`docs/research/XMen2.exe`, base 0x400000), `research/scripts/xml2_text.asm`, and new Ghidra decompiles
`research/heroes/decomp_ft_seat1.c` / `decomp_ft_seat2.c`. XML1 addresses are default.xbe (`xml1_text.asm`,
`xml1_xbox/default.xbe`). **UNVERIFIED** = not established from code or data (needs an in-game run or more reading).
Nothing was launched, nothing but this file and the two decompile outputs was written.

Conventions: `game` = singleton at `0x729960` (accessor `0x46dce0`, vtable `0x686e1c`); `registry` = stats registry
(`0x44b8f0`, vtable `0x68544c`); `CMap` = map manager (`0x484990` -> `0x72a578`, vtable `0x68878c`); `console` =
`0x55c890` -> `0x7ac290` (vtable `0x69a81c`); "slot n" = party slot 0..3 = interned string handle at `game+0x14+4n`
(handle 0 = empty); `CStats` = per-character stats object (`registry vt+0x40(name)`).

---

## 0. Answers in one table

| question | answer (evidence) |
|---|---|
| Can a script-called engine routine seat an exact 1-4 hero party mid-game? | **Yes.** Every retail party change is "write the 4 slots with `game vt+0xf0` (empty name = handle 0 clears the slot), then load a zone": `restorelastzone` `0x5f4612-0x5f46a6`, Danger Room course start `0x4d1a23-0x4d1a6d`, save loader `0x484c70-0x484ca6`, team menu `0x5e2539` + confirm `0x5e0800`. A new xml2-fix script function doing the same is on a retail-proven path. |
| Must it be followed by a zone (re)load? | **Yes** for any change of composition. Slots are names only; heroes are spawned from them only at zone load (`0x486dd0`, called from the precache step `0x486d48`). No retail code despawns a hero mid-zone. The one exception is **adding** a hero: see next row. |
| Is there a no-reload "add hero"? | **Yes, dormant:** `game vt+0x170` = `0x46c9f0` is a complete runtime addHero(name) (seat in slot = party count, replace an NPC of the same character in place, load its package, assign controller, spawn, refresh HUD). No XML2 caller exists. It is the same routine XML1's `addHero` calls (xbe handler `0x99a00` -> XML1 `game vt+0x110` = `0x71cf0`, near-identical code). Never executed by retail XML2 -> test first. |
| What does the slot setter `0x46c810` touch? | Only the slot handle, plus - when a slot's previous non-empty name changes - `0x7733a8 vt+0x10(oldCStats)` (`0x4c1d00`: deletes that hero's entries from a map keyed by stats index `+0x28e`; engine.md calls it the talent-values table). **No** spawn/despawn, no package load, no stats/XP/level/power change. |
| XP / levels per hero? | Kept per hero: level/XP/powers/costume live in the hero's own CStats (saved per stats index, engine.md 5.1), not in the slot. Seating never touches them. |
| Does anything auto-fill empty slots? | **No, not on the load path.** `builddefaultteam` (`0x5f3330`) is sent only by (a) the team menu *open* when slot 0 is empty (`0x5e374b`) and (b) the console command. It **overwrites** slot i with ini `[HERO] Name<i+1>` (defaults magneto/cyclops/wolverine/bishop) or a random unlocked hero when that name is not already seated - so never let a team menu open with slot 0 empty. |
| Is a 1-hero party kept? | Yes as far as code goes: `0x486dd0` spawns only non-empty slots, nothing refills. Retail precedent: Danger Room character challenges (`dangerroom.engb` COURSE `hero="cyclops"` "Challenge - Cyclops", etc.) seat the course heroes and clear the rest (`0x4d1a23-0x4d1a65`) then `loadmap` (`0x4c9d5c`). That these produce N=1 is inferred from the course data (single `hero=`); HUD appearance in a story zone **UNVERIFIED**. |
| `_HERO1_.._HERO4_` / `_ACTIVE_HERO_` when the party is 1? | Resolved from the live party-entity list `game vt+0x120` (`0x46d460`), not from slots (`0x4a7e30`): `_HERO2_` needs list count > 1 (`0x4a8052`...), else no entity -> the script call gets nothing (as in XML1). `_ACTIVE_HERO_` = first listed entity without flag `+0x3d8` bit 0. |
| How does the save store the party? | 4 names x 0x20 at `+0xa4` of the 0x26c-byte **MISSION STATE** record (`zonestore+0x1ad68`), captured from the slots at save time (`0x484aa3` -> `0x4657b0` -> `0x48a170`), written under `[MAP: MISSION STATE]` (`0x484b35`), restored by `0x484c70-0x484ca6` (empty names clear slots). Costume byte `+0x120` per hero in the registry save. The side-mission stack (2 records) is saved too (`0x46bcd4-0x46bd01`, loaded `0x46e3ec-0x46e428`). A seated 1-hero party therefore survives save/load exactly. |
| Skins? | Costume = hero `CStats+0x120` (index into table `0x6d8aa0`: default 0, astonishing 1, aoa 2, **60s 3, 70s 4, weaponx 5**, future 6, winter 7, **civilian 8**; 9 = override slot). The package/skin is chosen from it when the hero's character loads at zone load (`0x4bc100` -> `0x4b8090`, **no unlock-mask check**). Writing `+0x120` before the load forces the skin; it persists (saved) until written again. |

**Recommendation (details in 11):** add four script functions to xml2-fix - `setParty(ssss)` (seat exactly; caller then loads),
`setSkinset(s)` (XML1 mission skinset on the seated heroes), `pushParty()` / `popParty(ss)` (flashback save/restore on the
retail side-mission stack, with guards), and `addHero(s)` (binds the dormant `0x46c9f0`, experimental). The pipeline replaces
`loadMapChooseTeam` in the 49 forced missions by `setParty(...)` + `setSkinset(...)` + `loadMapKeepTeam(...)`.

---

## 1. The engine state that makes up "the party"

| state | where | written by | read by |
|---|---|---|---|
| 4 party slots (interned name handles, 0 = empty) | `game+0x14..+0x20` | `vt+0xf0` `0x46c810` (22 call sites, 2) | `vt+0xe0` `0x46c510` (&slot, index 0..4 accepted), `vt+0x10c` `0x46af90` (slot -> CStats), `vt+0x114` `0x46b010` (name -> slot or -1), `vt+0x118` `0x46b070` (name -> package slot 7+i, else 0xb) |
| pending-name array | `game+0x28..+0x34` | `vt+0xfc` `0x46c940` - **only caller clears it** (`0x486eae`, stores "") | `vt+0xf8` `0x46a410` (only caller `0x486e6f`) - applied at zone load `0x486e60` (3). **Dead in retail**: nothing ever writes a name into it. |
| party package-name slots (64 bytes each) | `game+0x3c+0x40*i` | `vt+0xf4` `0x46a420` (only `0x4bc1e3`) | `vt+0xe4` `0x46a3e0`; marked dirty by `vt+0xe8` `0x468aa0` |
| controller per slot / "has controller" / requested controller | `game+0x514` (4 dw), `+0x524` (4 b), `+0x528` (4 dw) | `vt+0x188` `0x46b1f0` (assignment, zone load `0x486d3b` and `0x46cd03`); `vt+0xec` swaps `+0x528` while compacting; `vt+0x178` `0x469770` resets `+0x528..+0x534` = -1, `+0x538` = 0 | spawn (`vt+0x184` `0x469ea0` -> entity `+0x3d4`) |
| live party entities | per-player cache `0x7298e0` (0x18 per player) | rebuilt by `vt+0x120` `0x46d460`: team 0x1d, flag bit 0x14, not dead (`vt+0xc0`), `+0x3d4 != -1` | `_HEROn_`/`_ACTIVE_HERO_`/`_ALL_HEROES_` (`0x4a7e30`), `vt+0x170`, HUD, side-mission capture `0x48a1d0` |
| per-hero data (level, XP, powers, costume) | hero CStats (persistent registry object for herostat entries; non-heroes are freed per zone by `0x44b090`) | gameplay, team menu, `unlockCharacter` | save (registry vt+0xa0 `0x449a60`) |
| MISSION STATE record (current zone, party names, positions) | `zonestore+0x1ad68` (zonestore = `CMap+0x3b0`), 0x26c bytes | `0x48a170` at zone leave (`0x466a60`) and save (`0x4657b9`) | save writer `0x484b35`, save loader `0x484c20`, zone load `0x4851b8`/`0x4862e5` |
| side-mission stack | `0x72b5b0`: 2 records x 0x26c, count `0x72ba8c` (= `+0x4dc`) | `pushsidemission` `0x5f3630`; pop `0x5f44a0`; reset `0x489c20` (mission mgr vt+0x3c, called at `0x5f2f16` in resetgame) | `restorelastzone` `0x5f4580`, `loadmap a=1` `0x5f46f0`; saved `0x46bcd4`, loaded `0x46e3ec` |
| game-state block (0xdc bytes, contents not traced) | `game+0x53c` / backup `+0x618` | `vt+0x200` `0x46d420` (backup; in pushsidemission `0x5f370d`) | `vt+0x204` `0x46d440` (restore; in restorelastzone `0x5f4672`) |

---

## 2. The slot setter `game vt+0xf0` = `0x46c810` (thiscall `(int slot, uint* handle)`, `ret 8`)

| step | address | effect |
|---|---|---|
| 1 | `0x46c82f-0x46c838` | slot outside 0..3 -> return |
| 2 | `0x46c846-0x46c87e` | new name = `*handle` resolved (0 -> `""` `0x681968`), copied to a 256-byte buffer, lowercased `0x5602b0` |
| 3 | `0x46c883-0x46c8bf` | `_stricmp(current slot name, new)`; equal -> return (no side effects) |
| 4 | `0x46c8c1-0x46c90c` | if the old slot name is non-empty: `0x4c1dd0()` (object `0x7733a8`, vtable `0x68ed18`) `vt+0x10(registry vt+0x40(old))` = `0x4c1d00`: erase the entries of map `+0x2cdc` whose key's stats index equals old hero `+0x28e` |
| 5 | `0x46c90d-0x46c914` | `0x425bf0(&slot, buffer)`: intern (empty -> handle 0) and store |

Not touched: entities, packages (`vt+0xf4`), controllers, CStats contents, unlocks. Unknown names are accepted
unchecked; the damage happens later at spawn (`0x46a6c0` -> registry fallback object, engine.md 2.1) - validate in the caller.
Interning helper for a caller: `0x425bf0` is `thiscall(uint* dst, const char* s)` (writes 0 for NULL/"").

---

## 3. Zone load: where slots become heroes

`loadmap` (console `0x5f4770`) -> `game vt+0x150` `0x4698f0` -> `vt+0x14c` `0x469fd0` then `CMap vt+0x38` = `CMap::LoadMap`
`0x4840b0` -> `CMap vt+0x50` `0x484ce0` (the load itself; also driven per frame by flag `CMap+0x220` bit 1).

| order | address | what happens to the party |
|---|---|---|
| 1 | `0x484e48` -> `CMap vt+0x30` `0x4844a0` | old world shut down: "Unloading existing character assets..." registry `vt+0xb8` `0x449f00` -> `0x4bc2c0(1)` for every loaded character (heroes too); non-heroes freed `vt+0x1c` `0x44b090`; talent pool 0xb cleared |
| 2 | `0x484f59` -> `0x486e60` | **pending apply**: for i 0..3, if `game+0x28+4i` != 0 -> `vt+0xf0(i, pending)`, then pending = "". A pending empty name means "no change" (cannot clear a slot). Never fires in retail (1). |
| 3 | `0x485e2c` -> `0x486d00` "Pre-caching entity assets..." | `0x486d3b` `game vt+0x188(arg, CMap vt+0x28())` - controller assignment per seated slot: the hero's remembered controller (`CStats+0xc0 vt+0x38`) if valid, else a free one (`decomp_ft_seat1.c` 101-268) |
| 4 | `0x486d48` -> `0x486dd0` | talent mgr `0x4c05b0 vt+0x10`, `0x4c2370 vt+8`; for each **non-empty** slot i: `game vt+0x18c(name, i)` = `0x46a6c0` |
| 5 | `0x46a6c0` | `"Hero_%s"` actor from entity class `actor` (`0x46a7xx`), team 0x1d (`0x41d3e0`), `vt+0x184` register (controller -> `+0x3d4`), `0x4bc8e0` stats -> actor |
| 6 | class attr `character` `0x41c869-0x41c88f` | registry `vt+0xb0(name, -1)` = `0x449e60` -> `0x4bc990(-1)`: first reference loads the character: `0x4bc100(vt+0x118(name) = 7+i, -1)` -> package `generated/characters/<name>_<skin>` for the **current costume** `+0x120` (`0x4b8090`), replacing whatever package was in party package slot i (`vt+0xe4`/`vt+0xf4`, `0x4bc182-0x4bc1e3`) |
| 7 | `0x486884` | `game vt+0x190` `0x46a880` post-spawn party placement (not traced further) |

No step refills an empty slot. The slot must be a herostat name before step 4 (engine.md R6).

---

## 4. `startFirstMission` `0x4a7b10` end to end

| address | action |
|---|---|
| `0x4a7b16-0x4a7b1d` | `0x4b2880()` (object `0x75cbc0`) `vt+0x44()` - not traced |
| `0x4a7b22-0x4a7b2e` | `game vt+0x280(1)` `0x469d60`: `game+0x616` bit 2 ("new game") |
| `0x4a7b33-0x4a7b3f` | registry `vt+0xc0(1)` `0x44b680`: `byte [0x6d970c] = 1` |
| `0x4a7b41-0x4a7c21` | 4 x (intern name `0x602120`/`0x602140`/`0x41a320`; `game vt+0xf0(i, &h)`) magneto/cyclops/wolverine/storm (xml2-fix `new_game.cpp` re-points these operands) |
| `0x4a7c2a-0x4a7c57` | `"runscript menus/new_game"` (difficulty `vt+0x268` < 2) or `menus/new_game_hard` via console `vt+0x18` |

It seats and returns; the **script** does the load (`loadMapKeepTeam`/`loadMapChooseTeam` in `menus/new_game*.py`). This is
exactly the "seat now, let the script's load call spawn it" contract a new function should follow.

---

## 5. Every retail mid-game seat (the reference paths)

| path | slot writes | then | notes |
|---|---|---|---|
| **restorelastzone** handler `0x5f4580` (script `restorelastzone(s)` `0x4a0760` queues `"restorelastzone %s"` unless the menu is `loading`) | `atoi(arg)==0`: all 4 names from the top side record `+0xa4`, `""` -> handle 0 clears (`0x5f4612-0x5f4667`) | `game vt+0x204` (restore game-state block) `0x5f4672`; `"loadmap <zone> 1"` executed immediately (`0x5f4686-0x5f46a6`, console `vt+0x18`); stack empty -> **`"mainmenuexit 1"`** (`0x5f46bf`) | the cleanest mid-game "exact party + reload" in retail |
| **Danger Room course start** `0x4d1910` | `game vt+0x178` (`0x4d191c`) then slots 0..3 = course heroes, remaining slots handle 0 (`0x4d1a23-0x4d1a65`) | `0x4d0c80`, `0x4c9c90(0)` -> `"loadmap %s"` queued (`0x4c9d5c`, console `vt+0x1c`) | 1-hero challenge courses exist (`CHCYC`, `CHGAM`, `CHICE`, `CHTOA`, `CHPHO`, `CHSCA` ...) |
| **team menu** pick `0x5e2420` (write `0x5e2539`) | one slot per pick, live, while the world exists | confirm `0x5e0800`: `0x5de970` (re-apply changed stats to live actors with `0x4bd3a0` when no load pending), `game vt+0xec` `0x46c620` **compacts** (non-empty slots to the front, `+0x528` swapped), then `"loadmap %s"` or `"runscript %s"` (blackbird code) queued `0x5e08e3-0x5e090e` | menu open `0x5e3660`: slot 0 empty -> `builddefaultteam` (`0x5e3744`, immediate); on a `loadmap z 0 1` open it also clears slots whose hero `CStats+0xc0 vt+0x28` is true (`0x5e3868`; meaning **UNVERIFIED**) |
| **save loader** `CMap vt+0xb8` `0x484b70` | 4 names from the loaded MISSION STATE record `+0xa4` (`0x484c70-0x484ca6`), empty clears | `game vt+0x14c`; `CMap vt+0x4c` `0x484010` (LoadZone at the saved spot) | |
| `builddefaultteam` `0x5f3be0` -> `0x5f3330` | slot i = ini `[HERO] Name<i+1>` (defaults `magneto/cyclops/wolverine/bishop`) if not already seated (`vt+0x114 == -1`), or random unlocked + `0x4b7fc0` | nothing (the menu's later confirm loads) | only from the menu fallback and console (strings `0x6a2f68` used at `0x5e374b`, `0x5f4c0e` only) |
| `startFirstMission` | 4 hardcoded names | runscript (4) | |
| resetgame `0x5f2e70` | clears all 4 (`0x5f3091`) after `0x4bc2c0(1)` on each | - | also `clearsidemissions` |

**Pattern:** write all 4 slots (empties as handle 0), then load a zone. No retail path changes composition without a load
(except the dormant `vt+0x170`, 6). Slots are written while the old party's actors still exist (team menu, restorelastzone)
- that window is retail-normal; package/talent bookkeeping is reconciled by index at the next load (3, steps 1 and 6).

---

## 6. The dormant runtime addHero: `game vt+0x170` = `0x46c9f0` (thiscall `(const char* name)`, returns bool, `ret 4`)

| step | address | effect |
|---|---|---|
| 1 | `0x46ca1d-0x46ca2e` | `stats = registry vt+0x40(name)` |
| 2 | `0x46ca31-0x46caa1` | party entities `vt+0x120(&list,-1,0)`; if any entity `+0x35c == stats` -> **return true** (already in party) |
| 3 | `0x46caa3-0x46cab8` | `stats == 0` or party count >= 4 -> return false; **slot = party entity count** (`[esp+0x18]`) |
| 4 | `0x46cacc-0x46cbba` | enumerate world entities using this CStats (`0x4ab6d0`/`0x4ab770`, filter `0x68202c`); for a match (an NPC of the same character): remember its package slot (`vt+0x90`), origin and angles (`vt+0x30`), **remove it** (`0x45fef0(id)`) |
| 5 | `0x46cbbc-0x46cc6f` | HUD mgr `0x59ee20 vt+8`; if the slot's previous occupant differs: `0x4bc2c0(1)` on it, package manager `0x563070 vt+8(vt+0x118(old,0))` |
| 6 | `0x46cc72-0x46cc93` | if an NPC was replaced and its package slot != 7+slot: drop that reference (`0x4bc2c0(1)`) |
| 7 | `0x46ccc5-0x46ccee` | `vt+0xf0(slot, name)`; `0x4bc990(-1)` -> character package into party package slot 7+slot |
| 8 | `0x46ccfb-0x46cd03` | `vt+0x188(1,0)` controller assignment |
| 9 | `0x46cd2d-0x46cdb4` | `vt+0x18c(name, slot)` spawn; `vt+0x190`; NPC replaced -> hero `vt+0x34`(origin) / `vt+0x158`(angles) at the NPC's spot, `0x48de40 vt+0x5c`; else `0x5252e0 vt+0x1c8(entity+0x7dc, 0)` |
| 10 | `0x46cdba-0x46cdd8` | `vt+0x120(&list,-1,1)` (refresh cache), HUD mgr `vt+0(0)`; return true |

- **No caller in XMen2.exe** (census of `call [reg+0x170]` after `0x46dce0`: 0; the 10 raw `+0x170` calls are other classes).
- XML1 correspondence: `addHero` handler xbe `0x99a00` = `game(0x72cf0)->vt+0x110(arg0)`; XML1 vtable `0x3ccd14` +0x110 =
  `0x71cf0`, whose prologue is the same algorithm (`vt+0xe0` party list, `cmp [eax+0x2d8],ebx` "already in party",
  `cmp eax,4; jge`, `mov [esp+0x18],eax` slot = count, entity query `0xa2a70`, `vt+0x30` origin copy, spawn). The XML2 routine
  is XML1's addHero engine code carried over with the vtable renumbered.
- In nyc1_1_3 the port's NPC is `sp_cyclops01` `character="cyclops"` `monster_name="cyclops_x1double"` (built zone), i.e. it
  uses the `cyclops` CStats -> step 4 should find it and put the joining hero on its spot, exactly as XML1. Whether the entity
  filter at `0x46cacc-0x46cb16` (args `(2, 0x1d)`, filter `0x68202c`) matches a spawner-made NPC: **UNVERIFIED**.
- Slot = count assumes a compacted party (slots 0..count-1 filled). `setParty` (11.2) always compacts.

---

## 7. Side missions: record, push, restore

Record (0x26c bytes, ctor `0x4874b0`, fill `0x48a170`, copy `0x5f4400`):

| offset | size | content | filled at |
|---|---|---|---|
| +0x000 | 0x40 | zone name | `0x48a3b7-0x48a3cb` (`CMap vt+0x5c`) |
| +0x040 | 4 x 0x18 | party entity origin+angles (alive, health > 0) | `0x48a1e0-0x48a29d` |
| +0x0a4 | 4 x 0x20 | **party slot names** (empty = "") | `0x48a2a3-0x48a320` |
| +0x125 | 0x12c | zeroed by ctor, copied by `0x5f3fb0`; **no reader or writer found** (pattern search of `+0x125` on every record base) | - |
| +0x254 / +0x260 | vec3 / vec3 | origin / angles of the entity passed to the push | `0x48a322-0x48a3a5` (entity 0/invalid -> zero vectors) |

Correction to roster.md 2.4: the names are at record **+0xa4**; "+0x134" there is the handler's stack offset
(`esp+0x134` = record at `esp+0x90` + 0xa4, `0x5f4614`).

| command | handler | behaviour | hazards |
|---|---|---|---|
| `pushsidemission <entityId>` | `0x5f3630` | `atoi` -> entity handle check `0x4654d0`; if count `< 2` and a zone is loaded: fill (`0x48a170`) and append; then `0x422520(0,0)` (store controller bindings) and `game vt+0x200` | count >= 2 -> **silently not pushed** (`0x5f3684`); bad entity -> return spot = origin |
| `restorelastzone <n>` | `0x5f4580` | top record; `n==0` -> slots = record names (5); `vt+0x204`; `"loadmap <zone> 1"` | count 0 -> `"mainmenuexit 1"` |
| `loadmap <zone> 1 0` | `0x5f4770` -> `0x5f46f0` | position restore from the top record (`mission mgr vt+0x28`), load (`vt+0x150(zone, count>0)`), pop `0x5f44a0` | - |
| script `extractionPointChange(a,i)` | `0x4a7020` | entity must be a character (`[0x718448]+0x24`); `"pushsidemission %d"` and `"setblackbirdparms FALSE restorelastzone('1') TRUE TRUE %d"` both via console **`vt+0x18` (immediate)**, then team menu `0x5d8920 vt+0x68`; the menu's confirm runs `restorelastzone('1')` -> same zone, same spot, new team, record popped | the record never outlives the menu in retail |

Console: `vt+0x18` `0x55beb0` executes the handler synchronously (`call [esi+eax*4+0x428]`, `0x55bf2d`); `vt+0x1c` `0x55c410`
queues (max 2: refused when `[+0x630] == 2`, `0x55c426`). `loadMapKeepTeam`/`loadMapChooseTeam` queue (`0x4a0d03`). Correction
to roster.md 2.4 / T7: `extractionPointChange` does not use the 2-command queue.

The stack is saved with the game (`game vt+0x208` = `0x46baf0` writes 0x4e0 bytes at `0x46bcd4-0x46bd01`) and restored
(`vt+0x20c` = `0x46e2b0`, `0x46e3ec-0x46e428`), so a save made inside a flashback keeps its return record.
While a record is on the stack every `loadmap` passes flag 1 to `CMap::LoadMap` (`0x5f47e0-0x5f48c9`), which makes
`0x484ce0` take the other unload branch (`0x484e00-0x484e48` -> `0x4844a0` param 0 -> `0x484900` instead of `vt+0x34`);
retail uses that branch for `restorelastzone`'s own load. Meaning (keep the caller zone's state?) **UNVERIFIED**.

XML1 reference: `beginSideMission`/`endSideMission` are console commands (xbe `0x18dd70`/`0x18df20`) on the same design
(push, then `beginmission`; pop + restore). `endSideMission("TRUE"/"FALSE")` argument semantics **UNVERIFIED**.

---

## 8. Costumes / skins

| item | fact | address |
|---|---|---|
| current costume | `CStats+0x120` (byte, 0..9); variants `+0x255+idx` (0 = hero has no such costume); unlocked mask `+0x11c` (bits 1..9) | engine.md 6 |
| names | table `0x6d8aa0`, 8-byte `{name, index}`: default 0, astonishing 1, aoa 2, 60s 3, 70s 4, weaponx 5, future 6, winter 7, civilian 8; lookup `0x5602f0` | read this session |
| override slot 9 | `0x4bc100(slot, v)` with `v > -1` sets `+0x120 = 9`, `+0x25e = v` (arbitrary variant); used by spawners' `skinindex` (`0x48a42d` -> registry `vt+0xb0(name, skinindex)`) | `0x4bc145-0x4bc158` |
| skin string | `0x4b8090`: prefix `+0x254` + variant of `+0x120` (>= 10 -> 01); **no mask check** | `decomp_heroes2.c` 1224 |
| when it matters | at character load in zone load (3, step 6) and for HUD/head lookups (`0x5f4ec0`) | |
| team menu costume | `0x5e5149` `0x4b7fc0` (next unlocked costume with a variant, slots 0..8) then preview `0x5e3e90` | |
| `unlockCharacter(h, costume)` | unlocks the hero; costume > 0 -> `0x4b7ce0` sets the mask bit only (does **not** select it); empty hero -> every hero | `0x49f520` |
| persistence | `+0x120` saved per hero (engine.md 5.1) - a forced costume stays until written back | |
| port mapping | XML1 `skin_60s/70s/weaponx/civilian/future` -> slots 3/4/5/8/6; Magma `skin_magmacivilian` -> `skin_civilian` (8) | `tools/xml1build/heroes.py` `COSTUME_RENAME`, DESIGN D6 |
| **XML1 semantics** | the skinset is a **mission** property (xbe parse `0x84c86-0x84cb4`: mission `+0x12e` bits 4-6) and is applied at character-load time: if the hero's own costume byte `+0x1e` is 0xff or 1 (default) the variant is `CStats+0x372[missionSkinset]+1`, otherwise the hero's own costume wins (`0xb1076-0xb10ad`, `0xb0e63-0xb0e96`, package `"generated/characters/%s_%s"` `0xb10be`). Nothing is stored in the hero, so leaving the mission reverts automatically. | xml1_text.asm |

Consequence: XML2 stores costume per hero, XML1 derives it per mission. A stateless emulation that matches XML1: at every
mission start apply the mission's skinset to the seated heroes that are in default or in another *skinset* costume
(0, 3, 4, 5, 8), leaving player-choice costumes (1, 2, 6, 7) alone; "default" puts skinset costumes back to 0 (11.3).

---

## 9. Party of 1..3 mid-game: what the engine does

| aspect | behaviour | evidence / status |
|---|---|---|
| spawn | only non-empty slots | `0x486e14-0x486e22` |
| auto-fill | none on load; only team-menu open with slot 0 empty | 5 |
| controller | seated heroes without a valid remembered controller get a free one -> player 1 controls the solo hero | `0x46b1f0` (decomp_ft_seat1.c 216-268); in game **UNVERIFIED** |
| `_HERO1_`.. | index into the live entity list; missing -> 0 entities | `0x4a8010-0x4a80d7` |
| `_HERO<n>_MC_` npcstat placeholders | slot n-1 name (`0x449430`); empty -> "" -> fallback stats | only XML2 `Maps/Briefing/*` use them; none of the port's XML1 zone dirs do (grep of `build/_heroes/Maps/{arbiter..xjet}`: 0 files) |
| XML1 scripts on `_HERO2_.._HERO4_` | `copyOriginAndAngles`, `setAIActive`, `setReactToEnemies`, `alive`, `setOrigin` (dozens, cutscene staging) - no-ops when absent, as in XML1 | build/_heroes/Scripts grep |
| HUD | rebuilt at zone load (HUD manager `0x59ee20`, object `0x81d7e0`, hidden in `0x4844a0`); refreshed by `vt+0x170` | number of portraits for N<4 in a story zone **UNVERIFIED** |
| co-op | a second local player gets no hero if the party is smaller than the player count; `vt+0x178` resets requested controllers (Danger Room does this) | out of scope, **UNVERIFIED** |
| team menu later | opens with the seated party; locked seated heroes (e.g. Magma, never `setInCampaign` in XML1) are not validated by confirm | whether the menu lets a locked seated hero stay **UNVERIFIED** - see 11.6 |

---

## 10. Save game (party-related)

| section | what | write / read |
|---|---|---|
| registry heroes | per stats index 1..: level/XP block, powers, **costume `+0x120`**, mask `+0x11c` | `0x449a60` / `0x44b970` |
| game-state block | 0xdc bytes of `game+0x53c` | `0x46bcc2` / `0x46e3b8` |
| side-mission stack | 0x4e0 bytes (2 records + count) | `0x46bcd4` / `0x46e3ec` |
| `[MAP: MISSION STATE]` | current record incl. **4 party names** (captured `0x484aa3`) | `0x484b35` / `0x484c20`, slots `0x484c70-0x484ca6` |

---

## 11. Recommendation: new script functions in xml2-fix

### 11.1 Registration and ABI (all read this session)
- Table `0x68a908`, 289 (`0x121`) entries of 16 bytes `{handler, name, retSig, argSig}` (e.g. `{0x4a1cc0,"setRotZ","n","ai"}`),
  registered once by `0x49fe30`: `push 0x68a908` / `push 0x121` / `call 0x4d8770` / `call 0x4d75a0` (inserts by name into a map).
  Patch the two imm32 at **`0x49fe31`** and **`0x49fe36`** (retail bytes `68 08 a9 68 00 68 21 01 00 00`) to a DLL copy of the table
  + the new entries, count + N - same guarded-operand style as `new_game.cpp`. The proxy loads before the game registers scripts.
- Handler: `int __cdecl h(Args* a)`, returns 0. Argument i: `Arg* p = thiscall 0x4d5830(a, i)`; string = `p->vt[0x14/4]()`,
  int = `p->vt[0x10/4]()` (as `0x4a7020`). Entity from a name: `0x4a1700(buf, name)` then `0x4654b0` (as `0x4a7066-0x4a7070`).
- Engine calls: game = `0x46dce0()`; registry = `0x44b8f0()`; console = `0x55c890()` (`vt+0x18` run now, `vt+0x1c` queue).
  Registry: `vt+0x3c(name)` -> index (0 = unknown), `vt+0x7c(i)` = herostat hero (bit0), `vt+0x84(i)` = unlocked, `vt+0x78(i)` =
  has CStats, `vt+0x40(name)` -> CStats.

### 11.2 `setParty(h1, h2, h3, h4)` - `n(ssss)` - seat exactly, no load
| # | action | address / precedent |
|---|---|---|
| 1 | each non-empty arg: lowercase; `idx = registry vt+0x3c(name)`; require `idx != 0` and `vt+0x7c(idx)` (herostat hero). Any failure -> log, change nothing, return | avoids the `0x46a6c0` fallback-stats spawn (engine.md R6) |
| 2 | drop duplicates; **compact** (non-empty first) so slot 0 is filled | keeps team-menu (`0x5e36ff`) and `vt+0x170` (slot = count) invariants |
| 3 | for i 0..3: `h = 0; 0x425bf0(&h, name_i)` (empty -> 0); `game vt+0xf0(i, &h)` | `restorelastzone` `0x5f4612-0x5f4667`, Danger Room `0x4d1a23-0x4d1a65` |
| 4 | do **not** unlock, do **not** touch `+0x528`/`vt+0x178` (single player: restorelastzone parity), do **not** load | |
| 5 | return; the script's next statement must be the load: `loadMapKeepTeam(zone)` (queued `"loadmap %s 0 0"`), `loadZone(zone, start)` or `popParty` | nothing spawns until 3 step 4 |

Optional XML1 niceties: `"hero:skin"` per arg handled as `setSkinset` for that hero only. Not needed if 11.3 is emitted.

### 11.3 `setSkinset(s)` - `n(s)` - XML1 mission skinset on the seated party
| # | action |
|---|---|
| 1 | `k = index of s` in `0x6d8aa0` (`"magmacivilian"` -> 8); unknown -> return |
| 2 | for each seated slot: `c = registry vt+0x40(name)`; `cur = c[+0x120]`; if `cur` in {0, 3, 4, 5, 8} (default or a skinset costume): `c[+0x120] = (k != 0 && c[+0x255+k] != 0) ? k : 0` |
| 3 | no load; takes effect at the next character load (3, step 6) - so call it before the zone load, like `setParty` |

This is XML1's rule (8, last row) made explicit; `"default"` reverts. Emit it at **every** generated mission start (XML1 has
a `skinset` on every mission; all `teamselect="true"` missions are `default`); `popParty` applies it itself (11.4).
Side note: XML2 spawners with `skinindex` write the override slot 9 into the **shared** CStats (`0x48a42d` -> `0x4bc151`); no
converted XML1 zone uses `skinindex` (0 hits in the built XML1 zone dirs), so 9 is not in the reset set.

### 11.4 Flashbacks: `pushParty()` `n()` and `popParty(skinset, fallbackZone)` `n(ss)`
| call | exact sequence |
|---|---|
| `pushParty()` (at the XML1 `beginSideMission` site, before `setParty`) | count = `*(int*)0x72ba8c`; if `>= 2` -> log and return (retail would silently not push). Resolve `_ACTIVE_HERO_` (11.1), require the character class bit (`[0x718448]+0x24`, as `0x4a7085-0x4a70a1`); `console vt+0x18("pushsidemission <entity+0x1c>")` - immediate, so the record captures the **current** party before `setParty` changes it |
| then | `setParty(<flashback heroes>)`, `setSkinset(<60s/70s/weaponx/...>)`, `loadMapKeepTeam(<flashback zone>)` (existing begin body) |
| `popParty(callerSkinset, fallbackZone)` (at the XML1 `endSideMission` site) | 1 `setSkinset("default")` on the flashback party (still seated). 2 count `== 0` (should not happen) -> `setSkinset(callerSkinset)`, `loadMapKeepTeam(fallbackZone)` instead of the retail `mainmenuexit 1`; return. 3 top record = `0x72b5b0 + (count-1)*0x26c`; seat its 4 names at `+0xa4` with the 11.2 step 3 loop (empties clear) - the same writes `restorelastzone 0` would do (`0x5f4612-0x5f4667`). 4 `setSkinset(callerSkinset)` on the restored party (XML1 re-derives the caller mission's skinset; e.g. Magma back to civilian after the uniformed `dr_mag1`). 5 `console vt+0x1c("restorelastzone 1")`: keeps the party just seated, `vt+0x204`, `loadmap <zone> 1` -> same spot, pop |

Doing the seat in the DLL (step 3) instead of passing `0` lets step 4 run on the right heroes: `restorelastzone` runs from the
console queue after the script returns, so a script-level `setSkinset` after it would hit the flashback party. Both records
survive save/load (7). Nesting depth needed by XML1: 1 (no flashback starts inside a flashback) - fits the 2-record limit.

### 11.5 `addHero(h)` - `n(s)` - XML1 addHero, no reload (experimental)
| # | action |
|---|---|
| 1 | validate as 11.2 step 1; ensure the party is compacted (it is if every seat came from `setParty`/menu confirm) |
| 2 | `bool ok = game vt+0x170(name)` (`0x46c9f0`, thiscall, 1 arg) |
| 3 | `!ok` (party full / unknown) -> log; the pipeline's current T7 fallback (`extractionPointChange`) stays available |

For nyc1_1_3 / mag_nyc4: `unlockCharacter("cyclops","")` + `addHero("cyclops")`, **without** the preceding `remove("cyclops_x1double")`
(step 4 of 6 removes the NPC itself and uses its spot; removing it first only loses the spot). No zone reload, so the zone-script
guard of T7 is not needed. Must be tested in game first (6: never executed by retail XML2).

### 11.6 Pipeline emission (what the port would generate)
| XML1 case (roster.md 4) | emitted |
|---|---|
| fully forced mission (Magma hubs, briefings, `muir2`, `muir3brig`, `nyc_rooftops`, `old_wx`, `secret_wx`, `astral1/1b`, `end_*`) | `setParty(<REQUIREDHERO list>)` + `setSkinset(<skinset>)` + `loadMapKeepTeam(<mapload>)` in place of `loadMapChooseTeam` |
| side mission / flashback (`jug_fb`, `sent_fb`, `wx_fb_start`, `dr_mag1`, `dr_mag2`, `astral_sk`) | begin: `pushParty()` + the forced-mission lines; end: `popParty("<caller mission skinset>", "<caller zone>")` replacing the generated `loadZone(...)` after the `endSideMission` marker (keep `setCurrentAct`); caller zones = `SIDE_CALLS` in `rewrite_scripts.py` |
| `addHero` sites | 11.5 |
| partially forced (`sent_fb` NC + 3 RECOMMENDED, `asteroid_rock` FROST + 3, `alison` W+C with C joining later) | open decision (13.3) |
| `teamselect="true"` | `setSkinset("default")` + existing blackbird / `loadMapChooseTeam` |
| any mission whose XML1 party is free but `teamselect="false"` directly after a forced one (e.g. `nuke` after `dr_mag2`, `sewers_hub2` after `healer_briefing`, `astral2` after `astral2_briefing`) | must reach a team menu or a restored party, else it inherits the forced 1-2 heroes (13.2) |
| New Game (option C of roster.md 3) | unchanged (`new_game.cpp` already seats `[Game] NewGameTeam`) |

Lint additions: `setParty` names must be herostat names (V10-style); every `pushParty` has a `popParty` on each exit path;
`setParty` (and `pushParty` + `setParty`) is followed by a load in the same script (`popParty` loads by itself); no `setParty`
with all four empty.

---

## 12. In-game checks (ordered, short runs)

1. Registration: a test script calling `setParty("magma","","","")` + `loadMapKeepTeam("mansion/man1a/mansion1a_1")` logs the call;
   Magma alone spawns, player controls him, HUD shows one portrait, no crash on `_HERO2_` script calls.
2. Save inside that zone, load: party still Magma alone (MISSION STATE path).
3. `setSkinset("civilian")` before the load: Magma in 15803 skin; next mission `setSkinset("default")` -> 15801.
4. Flashback: `pushParty()` in subbasement2 -> jug_fb with Cyclops/Beast/Iceman/Phoenix in 60s -> `popParty` returns to the same
   spot with the old party and default costumes. Repeat with a save/load inside jugrnt01.
5. `addHero("cyclops")` in nyc1_1_3: Cyclops takes the NPC's spot, joins as slot 1, HUD updates, no hitch-crash; save/load keeps him.
6. Team menu after a hub (Blackbird to haarp): what the menu does with a seated but locked Magma.

---

## 13. Open questions and UNVERIFIED items

Decisions:
1. Adopt the seating route at all (it overrides DESIGN/SPEC 12.6 "team menu at forced missions") - and whether `addHero` (11.5)
   replaces T7.
2. **Party memory across a forced segment.** After a Magma hub the next `teamselect` menu opens with Magma seated; free-party
   missions after forced ones inherit the small party. Options: (a) pipeline always routes such exits through a team menu
   (menu shows the forced party; player re-picks); (b) `saveParty()/restoreParty()` in xml2-fix storing the 4 names in the
   MISSION STATE record's unused `+0x125` bytes (saved with the game, 7; "unused" is **UNVERIFIED**); (c) a side record for the
   whole hub (not recommended: every hub load would run with the side-record flag, 7). XML1's own rule for this is not traced.
3. Partially forced missions: seat the required heroes then open the team menu (player can remove them), or seat required +
   fill from unlocked heroes in xml2-fix (`builddefaultteam`-like, without its magneto/bishop defaults).
4. Whether `setParty` should also unlock the seated heroes (not needed for spawning: `vt+0x118` checks unlock only in the
   Danger Room, `0x46b070` + `0x4c87a0` = `byte [0x782728] != 0xff`).

UNVERIFIED:
- HUD layout and any UI assumption of 4 heroes in story zones; `vt+0x188` controller result for a solo hero in game.
- `game vt+0x170` behaviour in practice (dormant code); its entity filter matching spawner-made NPCs.
- Meaning of `CStats+0xc0 vt+0x28` (slot cleared at team-menu open `0x5e3868`), of the game-state block `game+0x53c`, of
  `0x4b2880 vt+0x44` in startFirstMission, and of the side-record load flag branch (`0x484900`).
- Record `+0x125` being unused (only pattern-searched).
- XML1 `endSideMission` argument semantics; how XML1 re-filled parties after forced missions; XML1 `+0x1e` costume byte values.
- Whether the team menu lists or keeps a seated hero that is not unlocked.
