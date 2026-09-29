# CAnimMotionCache: the 40-slot actor table (XMen2.exe) and how to raise it in memory

Written 2026-09-28 (research only; sibling of igb-cache.md, same method). Target: the "engine limit adjuster" in
xml2-fix (dinput.dll proxy) that raises the cap at startup without shipping a modified exe.

Binary: `XMen2.exe` retail, PE base 0x400000, no relocations/ASLR, NOT /LARGEADDRESSAWARE, sha1
`7d95cdb4a9a599b982147a3389ea7aff211cb82b` (xml2-fix\docs\research\XMen2.exe). All addresses are VAs.
Every address below was read from the capstone listing (research/scripts/xml2_text.asm, tools/disasm.py) or the
Ghidra decompiles in this folder (decomp_actor1.c, decomp_actor2.c, decomp_actor3.c) unless marked **UNVERIFIED**.
Section 8.1 of igb-cache.md (the global 450-entry name table) is reused, not repeated.

**Verdict: A (raise to N = 127) + B2 (a diagnostic hook), with B3 (release group 1 at zone change) only after an
in-game test, and the content rule B1 as the long-term fix.**

**Implemented 2026-09-28 (A only):** xml2-fix `src/limits.cpp` + `src/limits_rules.hpp`, `[Limits] ActorSlots` /
`ResourceNames` in xml2-fix.ini. Every row of section 5 and 5.1 was re-derived from the exe with capstone and matches
byte for byte (74 in place + 5 in the clone + 3 references + 2 calls; no discrepancy in this file). xml2_test maps the
exe, applies the tables for N = 127 / M = 1024, checks nothing else changes, and runs the patched pool constructor
0x56ac10, alloc 0x56b5f0 and the findNext clone on blocks of its own. The name table (8.1) had four missing fields
and a wrong count offset in igb-cache.md 8.1; both are corrected there. Live counts: the test pipe's `status`
(`actors n/127; names n/1024; motions n/500; igb n/200`) and tools/actor_slots.py (address from xml2-fix.log).

- The table relocates as cleanly as the IGB cache: static object reached through one getter, three absolute
  references, 79 N-dependent fields (78 instructions) in 14 functions plus one shared helper to clone, no
  data-section pointer into the object. One difference: 16 of the fields are **imm8** compares (`cmp r/m32, 0x28`),
  so the largest cap expressible without re-encoding is **127** (0x7f). 127 and 128 give the same id mask/shift
  (0x7f / 7), so nothing is lost; a 128 variant is documented (section 5.2) but needs a jcc-opcode change at 13
  sites. The retail name table (450) must be raised in the same pass (section 8.1); the IModel pool is not involved;
  the 500-entry motion pool (section 8.3) is a soft limit to watch.
- The slots are **not leaking**: at zone change the game releases group 0xb and its anim-DB twin 0x14 exactly
  (section 9). What carries over is (a) the permanent group and the four hero-package groups, by design (about 14
  records), and (b) every on-demand load (`get` miss -> `precache(name, 1)`) that a spawned character makes for a
  skin or anim DB no package listed: those go to **group 1**, which only `return to menu` (0x401ba0) releases. So
  the 15-27 carry-over grows with every zone that spawns an unlisted actor, and after ~60 zone changes a 34-38 zone
  crosses 40. Raising the cap absorbs that for hundreds of zones; the hook in B2 tells the content pipeline which
  names leak; B3 would stop the growth but is only safe if no persistent CModelActor holds a group-1 record
  (UNVERIFIED for the party, section 9.4).

---------------------------------------------------------------------------------------------------------------

## 1. Identity and where the object lives

| item | value | evidence |
|---|---|---|
| class | `CAnimMotionCache` : `ICacheBase`; records are `CAnimMotion` | RTTI type descriptors `.?AVCAnimMotionCache@@` 0x6e218c, `.?AVICacheBase@@` 0x6e2150, `.?AVCAnimMotion@@` 0x6e2134 (locators 0x6b6100 / 0x6b609c / 0x6b6058) |
| vtable | 0x69bf0c, **7 slots** (0x69bf0c..0x69bf28; the string "actors/" follows at 0x69bf28) | section 3; the ICacheBase vtable 0x69befc has 3 slots (purecall 0x6720f2, 0x56aa90, purecall) and the dtor 0x56b870 resets to it |
| record vtable | 0x69bed4, 7 slots: 0x56aa00, 0x56aa30, 0x56aa50, 0x56a9e0, 0x569870, 0x569ac0, 0x4692d0 (+0x18 returns `[rec+8]`, the `igAnimationDatabase*`) | read from .rdata |
| singleton | **static object at 0x7b05e8**, size 0x7470 (0x7b05e8..0x7b7a58) | getter 0x56b8e0: `mov ecx,0x7b05e8; call 0x56acd0` (0x56b90a/0x56b917), `push 0x67e160; call 0x67211e` (0x56b91c/0x56b921), `mov eax,0x7b05e8` (0x56b92c) |
| init guard | bit 0 of dword **0x7b7a58** (`mov cl,[0x7b7a58]` 0x56b8e6, `or [0x7b7a58],eax` 0x56b904); the SEH unwind funclet 0x6763d0-0x6763dd clears the bit again if the ctor throws (scope table 0x6bf978 via 0x6763de) | 0x7b7a58 = 0x7b05e8 + 0x7470 sits *immediately after* the object and pins its size |
| atexit dtor | 0x67e160: `mov ecx,0x7b05e8; jmp 0x56b870` | read |
| getter callers | 11 sites, all through the vtable (section 6) | grep `call 0x56b8e0` |
| absolute references into the object | **exactly 3**: 0x56b90a (`B9 E8 05 7B 00`), 0x56b92c (`B8 E8 05 7B 00`), 0x67e160 (`B9 E8 05 7B 00`). Whole-listing grep for operands in 0x7b05e8..0x7b7a57 finds nothing else (two hits `mov eax,0x7b4dc993` at 0x584b30/0x5855c4 are hash constants). A scan of the whole image for aligned-or-not dword values in that range finds only the three sites plus eight unaligned code-byte coincidences (0x51d78b, 0x5ef340, 0x60767c, 0x607697, 0x6095fd, 0x63a5ba, 0x643627, 0x65f052), so no data-section pointer exists | scratchpad/actor_table_gen.py |
| section | .data bss tail (raw .data ends at VA 0x6f4000) | pefile |
| live count | this+0x73c4 = **0x7b79ac** (the value tools/actor_slots.py reads) | 0x56b2c3, 0x56b66e, 0x56b80b |

The object is the same shape as the IGB cache: `+0` vtable, `+4` an embedded fixed-capacity pool (**S** = this+4 =
0x7b05ec) with no vtable of its own. Pool methods take `ecx = S`; cache methods take `ecx = this` and form S with
`lea ecx,[ebp+4]` (ctor 0x56acf0), `lea ecx,[esi+4]` (dtor 0x56b893, slot 6 0x56b01a), `lea edx,[ebx+4]`
(precache 0x56b2b1), `lea edi,[ebx+4]` (0x56b3c8).

## 2. Layout (verified field by field)

Record stride is **0x2e0 = 736 bytes** (`imul eax,eax,0x2e0` 0x56b2b6 and 0x56b044; `imul ecx,ecx,0x2e0` in
0x56b5f0; `get` scales by 0xb8 dwords; the inverse `imul 0xb21642c9; sar edx,9` = /0x2e0 at 0x56b41b-0x56b424).

| S-relative | this-relative | field | size | set / used at |
|---|---|---|---|---|
| 0x0000 | 0x0004 | `rec[40]` CAnimMotion, 0x2e0 each | 0x7300 | 0x56b5f0 returns `S + idx*0x2e0`; 0x56b2b6; 0x56b044 |
| 0x7300 | 0x7304 | bitmap A "allocated" (2 dwords = 64 bits) | 8 | zeroed 0x56ac15 (`lea ecx,[esi+0x7300]` then `[ecx]`, `[ecx+4]`); set 0x56b5fe; cleared 0x56b848/0x56b84f; scanned by the dtor 0x56aab3/0x56aaba; zeroed again 0x56aba5 |
| 0x7308 | 0x730c | free-index ring `ring[41]` | 0xa4 | filled 0x56abfd (ring[i]=i, i<40); pop base 0x56b63a (`lea eax,[esi+0x7308]` -> 0x455a50); push 0x56b804 |
| 0x73ac | 0x73b0 | ring write position | 4 | 0x56abb4/0x56abd0/0x56abe1/0x56abef, 0x56ac23, 0x56b7d3/0x56b7e4/0x56b7f2 |
| 0x73b0 | 0x73b4 | ring read position | 4 | 0x56abba, 0x56ac29, 0x56b634; 0x455a50 as ring+0xa8 |
| 0x73b4 | 0x73b8 | ring count (free records) | 4 | 0x56abc0/0x56abd6/0x56abe7, 0x56ac2f, 0x56b7d9/0x56b7ea; 0x455a50 as ring+0xac |
| 0x73b8 | 0x73bc | bitmap B "live" (2 dwords) | 8 | zeroed 0x56ac37 (`lea` then `[eax]`, `[eax+4]`); set 0x56b655/0x56b65c; cleared 0x56b7bf/0x56b7c6; scanned 0x56b021/0x56b080 (via 0x4554e0) |
| 0x73c0 | **0x73c4** | **live count** (compared with 40) | 4 | zero 0x56ac44; ++ 0x56b66e; -- 0x56b80b/0x56b813; **cap check 0x56b2c3** |
| 0x73c4 | 0x73c8 | `id[40]`, id = (generation << 6) \| index, generation starts at 1 | 0xa0 | init 0x56ac7e-0x56aca8; read 0x56b42e; bumped 0x56b774/0x56b77d/0x56b793 |
| 0x7464 | **0x7468** | **index mask** = 0x3f (bits(N-1)) | 4 | computed 0x56ac51-0x56ac70; read 0x56b16b (get), 0x56b2a8 (precache), 0x56b735 (release) |
| 0x7468 | 0x746c | shift = 6 | 4 | 0x56ac57/0x56ac76/0x56ac92; 0x56b766/0x56b784 (`1 << shift`) |
| 0x746c | 0x7470 | end of object | | 0x7b05ec + 0x746c = 0x7b7a58 = guard dword |

As in the IGB cache, the two this-relative displacements the cache methods use (0x73c4 = live, 0x7468 = mask)
equal the S-relative displacements of the *following* fields (id table, shift). A patcher can remap the two numbers
uniformly (0x73c4 -> new, 0x7468 -> new) regardless of base, as long as the new layout keeps `live` directly before
`id[]` and `mask` directly before `shift` (section 7 does). The two bitmaps are zeroed as `[base]`/`[base+4]` after
one `lea`, so only 2 dwords are cleared: **a bigger pool must be handed pre-zeroed memory**.

Record contents (`CAnimMotion`, ctor 0x56b680, dtor 0x56a4d0; field meanings from decomp_actor1/2.c): +0 vtable
0x69bed4; +4 dword written 0 by `precache` at 0x56b412 (never read in the functions decompiled, meaning
**UNVERIFIED**); **+8 `igAnimationDatabase*`** (addref'd in the ctor, released in the dtor; slot +0x18 returns it);
+0xc..+0x2cc up to 176 ids from the global *motion pool* (section 8.3), one per animation of the DB, filled by
0x56a800 -> 0x56a620 at construction; +0x2cc their count; +0x2d0 index of bone `bip01` (-1 if none) and +0x2d4 its
name handle; +0x2d8 index of bone `motion` and +0x2dc its name handle. 176 = 0x2c0/4 matches the 0xaf per-DB id
stride the CModelActor uses (0x5743a0, 0x577330). Nothing in the record depends on N; relocation never touches
record contents.

### 2.1 The constructor chain (only reachable from the getter)

- 0x56b8e0 getter -> 0x56acd0 `CAnimMotionCache::CAnimMotionCache()` (sole call site 0x56b917): `[this] = 0x69bf0c`,
  then 0x56ac10 `pool::pool()` on S (0x56acf0 `lea ecx,[ebp+4]`), then a warm-up of the Alchemy
  `igAnimationCombinerBoneInfo` pool (0x640 allocate/deallocate pairs through a 0x1900-byte scratch buffer,
  0x56acfd-0x56ad6b; nothing to do with N).
  - 0x56ac10 (sole call site 0x56acf3): zero bitmap A (2 dwords), ring positions/count, bitmap B (2 dwords), live;
    0x56abb0 (sole call site 0x56ac4a): `for i in 0..39: ring.push(i)` with the wrap test `cmp eax,0x28` 0x56abde /
    `mov eax,0x27` 0x56abf5 / loop bound `cmp edx,0x28` 0x56ac05; back in 0x56ac10: mask/shift derived from
    **N-1 = 0x27** (`mov ecx,0x27` 0x56ac5d; 39 -> 6 iterations -> mask 0x3f, shift 6), then `id[i] = (1<<shift)|i`
    for `i < 0x28` (0x56aca8).
- The getter registers the atexit thunk 0x67e160 and returns 0x7b05e8 (0x56b92c).

## 3. Methods

CAnimMotionCache vtable 0x69bf0c (this-relative):

| slot | address | what it does | N-dependent fields |
|---|---|---|---|
| 0 (+0x00) | 0x56b730 | `release(id, group)`: `idx = id & [this+0x7468]`; 0x56b7a0(S, idx) then 0x56b760(S, idx) | mask read 0x56b735 |
| 1 (+0x04) | 0x56b8c0 | scalar deleting dtor -> 0x56b870 (sets vtable, 0x56aab0 on S, vtable = 0x69befc) | via 0x56aab0 |
| 2 (+0x08) | 0x56ea30 | `releaseGroup(group)`: **the same function the IGB cache uses** - name table 0x55af80 -> 0x55ab60(group, this), which calls slot 0 for every entry of that group owned by this cache | none |
| 3 (+0x0c) | 0x56ad80 | `isCached(name)`: key via 0x56af70 (section 9.1), lookup 0x55ab00; miss -> retry with the mapped group 2 key | none |
| 4 (+0x10) | 0x56b0a0 | `get(name)`: same two lookups; hit -> `S + (id & mask)*0x2e0`; miss -> slot 5 `precache(name, 1)` | mask 0x56b16b |
| 5 (+0x14) | 0x56b1c0 | `precache(name, group)`: section 4 | 0x56b2a8, **0x56b2c3**, 0x56b42e |
| 6 (+0x18) | 0x56b010 | `unbindAll()`: for every live record (bitmap B scan via 0x4554e0) 0x56a020 = for each animation of the DB `igAnimation::getBindingList()->setCount(0)`; iterator step 0x56b070. Called by CPrecacheMgr::releaseGroup after *every* group release (0x5618a0) | 0x56b021, 0x56b02c, 0x56b065, 0x56b080 |

Pool methods (ecx = S): 0x56aab0 dtor (inline bitmap-A `findNext`, destroys each allocated record with 0x56a4d0,
then zeroes the two bitmap dwords; five `cmp ..,0x28` at 0x56aacc, 0x56ab0d, 0x56ab32, 0x56ab56, 0x56ab98),
0x56abb0 ring fill, 0x56ac10 ctor, 0x56b5f0 `alloc()` (= 0x56b630 + set bitmap A + return record), 0x56b630
`takeFreeIndex()` (idx = ring[readpos]; set bitmap B; ring pop via **0x455a50**; live++), 0x56b760
`bumpGeneration(idx)` (`id[idx] += 1<<shift`; on sign overflow (`jns` 0x56b77b) reset to `(1<<shift)|idx`),
0x56b7a0 `free(idx)` (0x56b820 = record dtor 0x56a4d0 + clear bitmap A; clear bitmap B; ring push with wrap
`cmp eax,0x28` 0x56b7e1 / `mov eax,0x27` 0x56b7fc; live--), 0x56b070 iterator step (findNext from idx+1).

Shared helpers:

- **0x4554e0** `bitset<40>::findNext(from, wantSet)` - the N = 40 instantiation of the template behind 0x490d70.
  Capacity 40 hard-coded five times (0x4554e4, 0x4554ec, 0x455519, 0x455560, 0x455565). Called by the cache
  (0x56b027, 0x56b086) **and by 0x45ced8** (FUN_0045cde0, an unrelated 40-bit set at object+0x154). It must be
  **cloned**, not patched in place; it is position-independent (0x8f bytes 0x4554e0-0x45556e, only short
  intra-function jumps, no calls, no globals).
- **0x455a50** `ring<40>::pop()` on the ring base (`[ecx+0xa8]` = readpos, `[ecx+0xac]` = count, wrap
  `cmp eax,0x28` 0x455a5d). **Sole caller 0x56b669** -> patch in place.

## 4. The cap check and the silent failure

`precache(name, group)` 0x56b1c0:

1. 0x56b1eb-0x56b29d: strip `actors/` and `.igb` (0x592520), map the group for the name type (0x56ae90, section
   9.1), format the key `"%i:%s"` (0x5647f0 / 0x69b634) and look it up (0x55af80 getter, 0x55ab00); then the same
   with group 2 (permanent, mapped). A hit returns the existing record: `S + ([entry+0xc] & mask) * 0x2e0`
   (0x56b2a8-0x56b2be).
2. **0x56b2c3 `cmp dword ptr [ebx+0x73c4], 0x28; jge 0x56b2dc`** -> `xor eax,eax` (0x56b2dc): with 40 live records
   the function returns NULL. No log, no assert.
3. 0x56b2cc-0x56b2da: `if (nameTable->isFull()) return NULL` (0x55a6a0: `[map+0x9404] >= 0x1c2`). Second silent NULL.
4. Otherwise: file system 0x5642d0 vt+0x24 opens the IGB (0x56b300), 0x5695e0 loads it through `igResource::load`
   with the memory pools swapped to the group's pools, 0x56b590(dir, 0) picks the first `igAnimationDatabase` in the
   directory, 0x585230 holds it, vt+0x28 closes the file, 0x5694b0 restores the pools; 0x56b375-0x56b3c6 registers
   the loaded objects with SIGBMemoryStats (0x56e520 / 0x56e320, statistics only); 0x56b3cd `alloc()` takes a
   record, 0x56b680 constructs it (addref DB, bone lookup, one motion-pool id per animation), `[rec+4] = 0`
   (0x56b412), `idx = (rec - S) / 0x2e0`, `id = id[idx]` (0x56b42e) and the name table gets
   `add(key, group, this, id)` at 0x56b453 (0x55adf0).

Who swallows the NULL:

- Package entries: `CAnimDBPrecacher` (vtable 0x69af78: slot 0 0x560ec0 = `precache(name, [0x6e087c])`, slot 2
  0x560e50 = `releaseGroup`) is registered twice by the CPrecacheMgr ctor, for `actorskin` (0x562ef8) and
  `actoranimdb` (0x562f0e); 0x560ec0 ignores the return value.
- On-demand: `get` (0x56b0a0) returns the NULL to 0x577a30 (returns false, stores nothing), **0x577a60 (stores the
  NULL into `CModelActor+0x30[slot]` and returns false)**, 0x576cc0 and 0x5775b0 (return 0). 0x41fdf0 fills slots
  0..3 through the actor's vt+0x34 with keys `"%i:%s"` (section 9.2); 0x577330 then resolves an animation name by
  scanning the slots, **skipping a NULL slot without advancing the 0xaf base** (`local_8 += 0xaf` only inside the
  non-NULL branch, decomp_actor3.c:1770-1793); playback 0x5743a0 indexes `[this+0x30 + (id/0xaf)*4]`, gets the NULL,
  and `call [NULL+0xc]` faults at **0x5743bb** (= XMen2.exe+0x1743bb, the SPEC-14 crash).

## 5. Every N-dependent field (patch table)

**79 fields in 78 instructions** (0x56b2c3 carries both a disp32 and an imm8). 58 displacements (all disp32) and
21 immediates, of which **16 are imm8** (`83 /7 ib`, sign-extended: values up to 0x7f only) and 5 are imm32. 5 fields
live in the shared helper 0x4554e0 (clone only), 6 in 0x455a50 (sole caller, patch in place), 68 in the cache's own
14 functions. `@+k` is the byte offset of the field inside the instruction; file offset = VA - 0x400000. The `new`
column is the N = 127 layout of section 7.1 (S-relative; the this-relative 0x73c4/0x7468 sites remap uniformly, see
section 2). The `retail bytes` column is the expected-bytes guard for the whole instruction.

Functions containing patched fields: 0x56aab0 (pool dtor), 0x56abb0 (ring fill), 0x56ac10 (pool ctor), 0x56b010
(slot 6), 0x56b070 (iterator step), 0x56b0a0 (get), 0x56b1c0 (precache), 0x56b5f0 (alloc), 0x56b630
(takeFreeIndex), 0x56b730 (release), 0x56b760 (bumpGeneration), 0x56b7a0 (free), 0x56b820 (destroy+clear),
0x455a50 (ring pop); plus the clone of 0x4554e0, the getter 0x56b8e0 and the atexit thunk 0x67e160 (section 7.2).

| VA | retail bytes | instruction | kind | @+k | size | old | new (N=127) | field |
|---|---|---|---|---|---|---|---|---|
| 0x4554e4 | `83f828` | `cmp eax, 0x28` | imm8 | +2 | 1 | 0x28 | 0x7f | N (clone only) |
| 0x4554ec | `b828000000` | `mov eax, 0x28` | imm32 | +1 | 4 | 0x28 | 0x7f | N (clone only) |
| 0x455519 | `83f828` | `cmp eax, 0x28` | imm8 | +2 | 1 | 0x28 | 0x7f | N (clone only) |
| 0x455560 | `83f828` | `cmp eax, 0x28` | imm8 | +2 | 1 | 0x28 | 0x7f | N (clone only) |
| 0x455565 | `b828000000` | `mov eax, 0x28` | imm32 | +1 | 4 | 0x28 | 0x7f | N (clone only) |
| 0x455a50 | `8b81a8000000` | `mov eax, [ecx + 0xa8]` | disp | +2 | 4 | 0xa8 | 0x204 | ring-relative read pos |
| 0x455a57 | `8981a8000000` | `mov [ecx + 0xa8], eax` | disp | +2 | 4 | 0xa8 | 0x204 | ring-relative read pos |
| 0x455a5d | `83f828` | `cmp eax, 0x28` | imm8 | +2 | 1 | 0x28 | 0x7f | N |
| 0x455a60 | `8b81ac000000` | `mov eax, [ecx + 0xac]` | disp | +2 | 4 | 0xac | 0x208 | ring-relative count |
| 0x455a68 | `c781a800000000000000` | `mov dword ptr [ecx + 0xa8], 0` | disp | +2 | 4 | 0xa8 | 0x204 | ring-relative read pos |
| 0x455a73 | `8981ac000000` | `mov [ecx + 0xac], eax` | disp | +2 | 4 | 0xac | 0x208 | ring-relative count |
| 0x56aab3 | `8b8300730000` | `mov eax, [ebx + 0x7300]` | disp | +2 | 4 | 0x7300 | 0x16d20 | bitmap A |
| 0x56aaba | `8dbb00730000` | `lea edi, [ebx + 0x7300]` | disp | +2 | 4 | 0x7300 | 0x16d20 | bitmap A |
| 0x56aacc | `83f928` | `cmp ecx, 0x28` | imm8 | +2 | 1 | 0x28 | 0x7f | N |
| 0x56ab0d | `83f928` | `cmp ecx, 0x28` | imm8 | +2 | 1 | 0x28 | 0x7f | N |
| 0x56ab32 | `83f828` | `cmp eax, 0x28` | imm8 | +2 | 1 | 0x28 | 0x7f | N |
| 0x56ab56 | `83f828` | `cmp eax, 0x28` | imm8 | +2 | 1 | 0x28 | 0x7f | N |
| 0x56ab98 | `83f828` | `cmp eax, 0x28` | imm8 | +2 | 1 | 0x28 | 0x7f | N |
| 0x56abb4 | `89b1ac730000` | `mov [ecx + 0x73ac], esi` | disp | +2 | 4 | 0x73ac | 0x16f30 | ring write pos |
| 0x56abba | `89b1b0730000` | `mov [ecx + 0x73b0], esi` | disp | +2 | 4 | 0x73b0 | 0x16f34 | ring read pos |
| 0x56abc0 | `89b1b4730000` | `mov [ecx + 0x73b4], esi` | disp | +2 | 4 | 0x73b4 | 0x16f38 | ring count |
| 0x56abd0 | `8b81ac730000` | `mov eax, [ecx + 0x73ac]` | disp | +2 | 4 | 0x73ac | 0x16f30 | ring write pos |
| 0x56abd6 | `8bb9b4730000` | `mov edi, [ecx + 0x73b4]` | disp | +2 | 4 | 0x73b4 | 0x16f38 | ring count |
| 0x56abde | `83f828` | `cmp eax, 0x28` | imm8 | +2 | 1 | 0x28 | 0x7f | N |
| 0x56abe1 | `8981ac730000` | `mov [ecx + 0x73ac], eax` | disp | +2 | 4 | 0x73ac | 0x16f30 | ring write pos |
| 0x56abe7 | `89b9b4730000` | `mov [ecx + 0x73b4], edi` | disp | +2 | 4 | 0x73b4 | 0x16f38 | ring count |
| 0x56abef | `89b1ac730000` | `mov [ecx + 0x73ac], esi` | disp | +2 | 4 | 0x73ac | 0x16f30 | ring write pos |
| 0x56abf5 | `b827000000` | `mov eax, 0x27` | imm32 | +1 | 4 | 0x27 | 0x7e | N-1 |
| 0x56abfd | `89948108730000` | `mov [ecx + eax*4 + 0x7308], edx` | disp | +3 | 4 | 0x7308 | 0x16d30 | ring |
| 0x56ac05 | `83fa28` | `cmp edx, 0x28` | imm8 | +2 | 1 | 0x28 | 0x7f | N |
| 0x56ac15 | `8d8e00730000` | `lea ecx, [esi + 0x7300]` | disp | +2 | 4 | 0x7300 | 0x16d20 | bitmap A |
| 0x56ac23 | `89beac730000` | `mov [esi + 0x73ac], edi` | disp | +2 | 4 | 0x73ac | 0x16f30 | ring write pos |
| 0x56ac29 | `89beb0730000` | `mov [esi + 0x73b0], edi` | disp | +2 | 4 | 0x73b0 | 0x16f34 | ring read pos |
| 0x56ac2f | `89beb4730000` | `mov [esi + 0x73b4], edi` | disp | +2 | 4 | 0x73b4 | 0x16f38 | ring count |
| 0x56ac37 | `8d86b8730000` | `lea eax, [esi + 0x73b8]` | disp | +2 | 4 | 0x73b8 | 0x16f3c | bitmap B |
| 0x56ac44 | `89bec0730000` | `mov [esi + 0x73c0], edi` | disp | +2 | 4 | 0x73c0 | 0x16f4c | live |
| 0x56ac51 | `89be64740000` | `mov [esi + 0x7464], edi` | disp | +2 | 4 | 0x7464 | 0x1714c | mask |
| 0x56ac57 | `89be68740000` | `mov [esi + 0x7468], edi` | disp | +2 | 4 | 0x7468 | 0x17150 | shift |
| 0x56ac5d | `b927000000` | `mov ecx, 0x27` (mask/shift seed) | imm32 | +1 | 4 | 0x27 | 0x7e | N-1 |
| 0x56ac70 | `898664740000` | `mov [esi + 0x7464], eax` | disp | +2 | 4 | 0x7464 | 0x1714c | mask |
| 0x56ac76 | `899668740000` | `mov [esi + 0x7468], edx` | disp | +2 | 4 | 0x7468 | 0x17150 | shift |
| 0x56ac7e | `8d96c4730000` | `lea edx, [esi + 0x73c4]` | disp | +2 | 4 | 0x73c4 | 0x16f50 | id table |
| 0x56ac92 | `8b8e68740000` | `mov ecx, [esi + 0x7468]` | disp | +2 | 4 | 0x7468 | 0x17150 | shift |
| 0x56aca8 | `83f828` | `cmp eax, 0x28` | imm8 | +2 | 1 | 0x28 | 0x7f | N |
| 0x56b021 | `8d8eb8730000` | `lea ecx, [esi + 0x73b8]` | disp | +2 | 4 | 0x73b8 | 0x16f3c | bitmap B |
| 0x56b02c | `83f828` | `cmp eax, 0x28` (end sentinel) | imm8 | +2 | 1 | 0x28 | 0x7f | N |
| 0x56b065 | `83f928` | `cmp ecx, 0x28` (end sentinel) | imm8 | +2 | 1 | 0x28 | 0x7f | N |
| 0x56b080 | `8d8bb8730000` | `lea ecx, [ebx + 0x73b8]` | disp | +2 | 4 | 0x73b8 | 0x16f3c | bitmap B |
| 0x56b16b | `8b8668740000` | `mov eax, [esi + 0x7468]` (get: mask, T) | disp | +2 | 4 | 0x7468 | 0x17150 | mask (T) |
| 0x56b2a8 | `8b8368740000` | `mov eax, [ebx + 0x7468]` (precache: mask, T) | disp | +2 | 4 | 0x7468 | 0x17150 | mask (T) |
| 0x56b2c3 | `83bbc473000028` | `cmp dword ptr [ebx + 0x73c4], 0x28` **the cap** (live, T) | disp | +2 | 4 | 0x73c4 | 0x16f50 | live (T) |
| 0x56b2c3 | `83bbc473000028` | (same instruction) | imm8 | +6 | 1 | 0x28 | 0x7f | N |
| 0x56b42e | `8b8487c4730000` | `mov eax, [edi + eax*4 + 0x73c4]` | disp | +3 | 4 | 0x73c4 | 0x16f50 | id table |
| 0x56b5fe | `8d948e00730000` | `lea edx, [esi + ecx*4 + 0x7300]` | disp | +3 | 4 | 0x7300 | 0x16d20 | bitmap A |
| 0x56b634 | `8b8eb0730000` | `mov ecx, [esi + 0x73b0]` | disp | +2 | 4 | 0x73b0 | 0x16f34 | ring read pos |
| 0x56b63a | `8d8608730000` | `lea eax, [esi + 0x7308]` | disp | +2 | 4 | 0x7308 | 0x16d30 | ring |
| 0x56b655 | `8b8c96b8730000` | `mov ecx, [esi + edx*4 + 0x73b8]` | disp | +3 | 4 | 0x73b8 | 0x16f3c | bitmap B |
| 0x56b65c | `8d9496b8730000` | `lea edx, [esi + edx*4 + 0x73b8]` | disp | +3 | 4 | 0x73b8 | 0x16f3c | bitmap B |
| 0x56b66e | `ff86c0730000` | `inc dword ptr [esi + 0x73c0]` | disp | +2 | 4 | 0x73c0 | 0x16f4c | live |
| 0x56b735 | `8bb168740000` | `mov esi, [ecx + 0x7468]` (release: mask, T) | disp | +2 | 4 | 0x7468 | 0x17150 | mask (T) |
| 0x56b766 | `8b8868740000` | `mov ecx, [eax + 0x7468]` | disp | +2 | 4 | 0x7468 | 0x17150 | shift |
| 0x56b774 | `01b490c4730000` | `add [eax + edx*4 + 0x73c4], esi` | disp | +3 | 4 | 0x73c4 | 0x16f50 | id table |
| 0x56b77d | `899490c4730000` | `mov [eax + edx*4 + 0x73c4], edx` | disp | +3 | 4 | 0x73c4 | 0x16f50 | id table |
| 0x56b784 | `8b8868740000` | `mov ecx, [eax + 0x7468]` | disp | +2 | 4 | 0x7468 | 0x17150 | shift |
| 0x56b793 | `89b490c4730000` | `mov [eax + edx*4 + 0x73c4], esi` | disp | +3 | 4 | 0x73c4 | 0x16f50 | id table |
| 0x56b7bf | `8b8c86b8730000` | `mov ecx, [esi + eax*4 + 0x73b8]` | disp | +3 | 4 | 0x73b8 | 0x16f3c | bitmap B |
| 0x56b7c6 | `8d8486b8730000` | `lea eax, [esi + eax*4 + 0x73b8]` | disp | +3 | 4 | 0x73b8 | 0x16f3c | bitmap B |
| 0x56b7d3 | `8b86ac730000` | `mov eax, [esi + 0x73ac]` | disp | +2 | 4 | 0x73ac | 0x16f30 | ring write pos |
| 0x56b7d9 | `8b96b4730000` | `mov edx, [esi + 0x73b4]` | disp | +2 | 4 | 0x73b4 | 0x16f38 | ring count |
| 0x56b7e1 | `83f828` | `cmp eax, 0x28` | imm8 | +2 | 1 | 0x28 | 0x7f | N |
| 0x56b7e4 | `8986ac730000` | `mov [esi + 0x73ac], eax` | disp | +2 | 4 | 0x73ac | 0x16f30 | ring write pos |
| 0x56b7ea | `8996b4730000` | `mov [esi + 0x73b4], edx` | disp | +2 | 4 | 0x73b4 | 0x16f38 | ring count |
| 0x56b7f2 | `c786ac73000000000000` | `mov dword ptr [esi + 0x73ac], 0` | disp | +2 | 4 | 0x73ac | 0x16f30 | ring write pos |
| 0x56b7fc | `b827000000` | `mov eax, 0x27` | imm32 | +1 | 4 | 0x27 | 0x7e | N-1 |
| 0x56b804 | `89bc8608730000` | `mov [esi + eax*4 + 0x7308], edi` | disp | +3 | 4 | 0x7308 | 0x16d30 | ring |
| 0x56b80b | `8b86c0730000` | `mov eax, [esi + 0x73c0]` | disp | +2 | 4 | 0x73c0 | 0x16f4c | live |
| 0x56b813 | `8986c0730000` | `mov [esi + 0x73c0], eax` | disp | +2 | 4 | 0x73c0 | 0x16f4c | live |
| 0x56b848 | `8b8c8600730000` | `mov ecx, [esi + eax*4 + 0x7300]` | disp | +3 | 4 | 0x7300 | 0x16d20 | bitmap A |
| 0x56b84f | `8d848600730000` | `lea eax, [esi + eax*4 + 0x7300]` | disp | +3 | 4 | 0x7300 | 0x16d20 | bitmap A |

Sites that are *not* N-dependent although they look it: 0x56b563 `add esp,0x28` (stack clean-up in the
SExtraInfoPrinter helper 0x56b500); the `[ecx+4]` / `[eax+4]` second-dword stores of the bitmap zeroing (0x56ac1b,
0x56ac3d, 0x56aba8 - offsets from the `lea`, unchanged); the 0x2e0 stride, the 0xb21642c9 reciprocal, the
`sar 5`/`and 0x1f` bit arithmetic.

Coverage check: a capstone sweep of 0x56a4d0-0x56b940, 0x4554e0-0x455570 and 0x455a50-0x455a80 for any disp32 in
0x7000..0x7800 or immediate 0x27/0x28 found nothing outside this table; the whole-listing grep for the eleven
displacements found no other function using them with this object (the hits at 0x56e8f4-0x56f914 are the IGB cache's
own ring fields, S-relative 0x73c0/0x73c4 of a different object).

### 5.1 Absolute references and call sites to redirect (retail bytes)

| VA | retail bytes | instruction | field | new |
|---|---|---|---|---|
| 0x56b90a | `b9e8057b00` | `mov ecx, 0x7b05e8` (getter -> ctor `this`) | imm32 @+1 | new_obj |
| 0x56b92c | `b8e8057b00` | `mov eax, 0x7b05e8` (getter return) | imm32 @+1 | new_obj |
| 0x67e160 | `b9e8057b00` | `mov ecx, 0x7b05e8` (atexit thunk) | imm32 @+1 | new_obj |
| 0x56b027 | `e8b4a4eeff` | `call 0x4554e0` (slot 6) | rel32 @+1 | clone - (0x56b027+5) |
| 0x56b086 | `e855a4eeff` | `call 0x4554e0` (iterator step) | rel32 @+1 | clone - (0x56b086+5) |
| 0x56b669 | `e8e2a3eeff` | `call 0x455a50` (takeFreeIndex) | - | unchanged (0x455a50 patched in place) |
| 0x56b8e6 / 0x56b904 / 0x6763d0 / 0x6763d8 | `8a0d587a7b00` / `0905587a7b00` / `a1587a7b00` / `a3587a7b00` | guard dword 0x7b7a58 | - | unchanged (outside the new block) |

### 5.2 Why 127 and what 128 would cost

Every `cmp reg, 0x28` in the pool is the 3-byte `83 /7 ib` form; the imm8 is sign-extended, so 0x80 (128) becomes
-128 and every bound check inverts. Re-encoding as `81 /7 id` adds 3 bytes per site (13 in-place sites: 12 in the
cache, 1 in 0x455a50), which is not possible in place. N = 127 fits (0x7f), the ctor then derives mask 0x7f / shift 7
- identical to N = 128 - and the ring is 128 dwords. If 128 is ever wanted, each imm8 site can keep `0x7f` with the
adjacent jcc changed (values compared are bounded by N): `jge` (7D / 0F 8D) -> `jg` (7F / 0F 8F) at 0x455519(clone),
0x56aacf, 0x56ab10, 0x56ab35, 0x56ab59, 0x56ab9b, 0x56b2ca; `jl` (7C) -> `jle` (7E) at 0x4554ea(clone),
0x455563(clone), 0x455a66, 0x56abed, 0x56ac08, 0x56acab, 0x56b7f0; `je` (74) -> `jg` at 0x56b039; `jne` (75) ->
`jle` at 0x56b068; the sentinel `mov eax,0x28` sites take 0x80. Those jcc addresses are given for planning and are
**UNVERIFIED** individually except 0x455519/0x455563/0x56aacf/0x56ab10/0x56ab35/0x56ab59/0x56ab9b/0x56ac08/
0x56acab/0x56b068/0x56b2ca, which were read; the rest follow a `mov` that does not touch flags. Not recommended:
127 gives the same headroom.

## 6. The 11 getter callers (all vtable-relative, nothing to patch)

| caller | function | uses |
|---|---|---|
| 0x48679e | 0x486710 (CMap): key `"%i:%s"` with **0xb** and `zone_<lastPathComponent>` | `[vt+0xc]` isCached; on a miss logs through 0x40bdd0 (level 0x40) |
| 0x560e50 | CAnimDBPrecacher slot 2 | `jmp [vt+8]` releaseGroup |
| 0x560ec0 | CAnimDBPrecacher slot 0 (the `actorskin` / `actoranimdb` package entry) | `[vt+0x14]` precache(name, [0x6e087c] = current package group) |
| 0x561897 | CPrecacheMgr::releaseGroup 0x561850 | `[vt+0x18]` unbindAll after every group release |
| 0x562357 | CPrecacheMgr::registerPrecacher 0x5622d0 (after `mov [edi],0x69af78`) | result unused (forces construction) |
| 0x562eee, 0x562f04 | CPrecacheMgr ctor 0x562bc0, `actorskin` and `actoranimdb` registrations | result unused (forces construction; **the first call of the getter in the process**) |
| 0x576cec | 0x576cc0 CModelActor attach skin | `[vt+0x10]` get -> record `[vt+0x18]` -> `igAnimationDatabase::getSkin` (transient) |
| 0x5775db | 0x5775b0 CModelActor set skin / configure skeleton | `[vt+0x10]` get -> record `[vt+0x18]` (transient) |
| 0x577a33 | 0x577a30 CModelActor add anim DB | `[vt+0x10]` get -> **stores the record pointer** at `+0x30[+0x44++]` |
| 0x577a63 | 0x577a60 CModelActor set anim DB slot i | `[vt+0x10]` get -> **stores the record pointer (even NULL)** at `+0x30[i]` |

No caller dereferences a field of the cache object. Record pointers escape only into `CModelActor+0x30[0..4]`
(0x577a30/0x577a60); ids escape only into the name table (`SCacheHandle+0xc`, igb-cache.md 8.1), and 0x55ab60 hands
them straight back to slot 0. The three id -> index decodes (0x56b16b, 0x56b2a8, 0x56b735) all read the mask from
the object; no literal `& 0x3f` exists in the cache code (a hard-coded decode elsewhere is **UNVERIFIED** as absent,
but no other code reads `SCacheHandle+0xc` for this owner: the readers of entry+0xc are 0x56b2ae (precache),
0x56b174 (get: `and eax,[edx+0xc]` right after the mask load), 0x55abba, 0x55ace9 and the IGB cache's own two).

## 7. Relocation design (N = 127)

### 7.1 New layout (S-relative; object = 4 + sizeof(S))

| field | old | new | size |
|---|---|---|---|
| rec[N] | 0x0000 | 0x00000 | 127 * 0x2e0 = 0x16d20 |
| bitmap A | 0x7300 | 0x16d20 | ceil(127/32) = 4 dwords = 0x10 |
| ring[N+1] | 0x7308 | 0x16d30 | 128 * 4 = 0x200 |
| ring write pos | 0x73ac | 0x16f30 | 4 |
| ring read pos | 0x73b0 | 0x16f34 | 4 (ring + 0x204) |
| ring count | 0x73b4 | 0x16f38 | 4 (ring + 0x208) |
| bitmap B | 0x73b8 | 0x16f3c | 0x10 |
| live | 0x73c0 | 0x16f4c | 4 |
| id[N] | 0x73c4 | 0x16f50 | 0x1fc |
| mask | 0x7464 | 0x1714c | 4 (becomes 0x7f) |
| shift | 0x7468 | 0x17150 | 4 (becomes 7) |
| sizeof(S) | 0x746c | 0x17154 | object **0x17158** = 94,552 bytes (was 29,808) |

The ctor derives mask = bits(N-1) and shift = bit count, so any N <= 127 works with the same recipe (N = 127: 126 ->
mask 0x7f, shift 7; ids stay positive for 2^24 generations per slot before the 0x56b77b reset). For N = 128 the
layout would be bitmap A 0x17000, ring 0x17010, positions 0x17214/0x17218/0x1721c, bitmap B 0x17220, live 0x17230,
ids 0x17234, mask 0x17434, shift 0x17438, size 0x1743c (object 0x17440) - plus the jcc work of section 5.2.

### 7.2 Steps (DllMain / early proxy init, before the exe's CRT runs any static initialiser; the first getter call
is the CPrecacheMgr ctor at 0x562eee during game start-up, long after DllMain)

1. `new_obj = VirtualAlloc(NULL, 0x17158, MEM_COMMIT|MEM_RESERVE, PAGE_READWRITE)` (zero-filled - required, the ctor
   clears only 2 dwords per bitmap).
2. Apply the 74 in-place fields of section 5 (all rows except the five 0x4554e0 rows), each guarded by the retail
   bytes of its instruction exactly like `frame_rate_rules::code_patch` does today (expected bytes, offset,
   replacement; VirtualProtect PAGE_EXECUTE_READWRITE, memcpy, restore, FlushInstructionCache). imm8 fields are one
   byte (0x28 -> 0x7f), everything else 4 bytes.
3. Clone 0x4554e0: copy 0x8f bytes to an executable buffer, replace the five immediates (three imm8 0x28 -> 0x7f at
   clone+0x6/+0x3b/+0x82, two imm32 at clone+0xd/+0x86 - instruction offsets 0x4/0x39/0x80 plus the field's @+2,
   0xc/0x85 plus @+1), and patch the two `call rel32` operands at 0x56b027 and
   0x56b086 (@+1) to reach the clone. Leave 0x4554e0 itself alone (0x45ced8 keeps its 40-bit set).
4. Redirect the three absolute references (5.1) so the game constructs and destructs *our* block with its own, now
   patched, code: 0x56b90a, 0x56b92c, 0x67e160 imm32 `0x7b05e8` -> new_obj. The guard dword 0x7b7a58 stays where it
   is (outside the object), so the once-only logic and the SEH funclet still work; the old static becomes dead space.
   Alternative (bypassing the ctor): overwrite 0x56b8e0 with `B8 <new_obj> C3` and initialise the block in C (vtable
   0x69bf0c at +0; ring[i] = i for i < 127; write/read pos 0; count 127; id[i] = (1<<7)|i; mask 0x7f; shift 7). This
   skips the ctor's Alchemy bone-info pool warm-up (0x56acfd-0x56ad6b; effect of skipping it **UNVERIFIED**) and
   registers no atexit dtor, so prefer the redirect. Do NOT leave the getter unpatched with a patched ctor: the ctor
   would run with the new displacements on the 0x7470-byte static and overwrite 0x7b7a58 and 65 KB after it.
5. Raise the name table in the same pass (8.1); without it the new records cannot be registered.
6. Log the counters at zone changes (section 11).

### 7.3 What does NOT need patching

- Record stride math (0x2e0, the 0xb21642c9 reciprocal, the 0xb8 dword scale in `get`): unchanged.
- Bit-index arithmetic (`sar 5`, `and 0x1f`), the `[base+4]` second-dword bitmap stores.
- The `%i:%s` key format, the group mapping (9.1), CMap, CPrecacheMgr, CAnimDBPrecacher, the record class, the
  motion pool, the shared `releaseGroup` 0x56ea30 (it belongs to no object).
- The IGB cache's copies of the pool template (different functions, N = 200).

## 8. Structures the raise depends on

### 8.1 The global resource name table `ratl::map_os<string_vs<68>, SCacheHandle, 450>` (binding) - see igb-cache.md 8.1

Every actor record registers one name (`add` at 0x56b453, key `"<mapped group>:<name>"`) and `precache` refuses at
0x56b2d3 when the table is full (0x55a6a0). Retail worst case already sits near 450 (IGB 200 + textures 192 +
actors 40 + playfields + motion paths); with N = 127 the actor share alone grows by 87, so **the map must be raised
even if the IGB cache is left at 200**. Use the 1024-entry relocation of igb-cache.md 8.1 (71 fields - the 67 listed
there first plus 0x55a6c0, 0x55a6c7, 0x55ae88, 0x55af40, corrected 2026-09-28; size 0xb064 -> 0x19128; the count moves
to map+0x150a0, not 0x150a4). xml2-fix builds the table itself in DLL memory with the game's own constructor and
stores it at 0x7ac244, so the game never allocates it from its pool 0xe. Nothing in the actor cache depends on the map's layout: it only
calls 0x55af80 (getter), 0x55ab00 (lookup, reads entry+0xc), 0x55a6a0 (isFull), 0x55adf0 (add) and, through the
shared slot 2, 0x55ab60.

### 8.2 `CSafeResMgrI<IModel, 692, 44>` - not involved

`precache` 0x56b1c0 never calls 0x56f6d0 / 0x57eb90: actor IGBs are loaded as `igAnimationDatabase` objects
(skins inside them), no `CModel` handle is drawn. The 692 pool matters only for the IGB raise (igb-cache.md 8.2).

### 8.3 The motion pool at `[0x7b05bc]` (500 entries) - soft limit, watch

Every `CAnimMotion` record takes one entry of a global pool for **each animation of its DB** (0x56a800 loops the
animation list, 0x56a620 allocates at `[rec+0xc + count*4]`). The pool is the same template again: heap block of
0x4ebc bytes from game pool 0xe (0x5605e0 at 0x56a4xx/0x56a6xx, lazily, atexit 0x56a450), constructed by 0x56a330:
32-byte entries x 500 (0x0..0x3e80), bitmap A 0x3e80 (16 dwords), ring[501] 0x3ec0, positions 0x4694/0x4698/0x469c,
bitmap B 0x46a0, **live 0x46e0**, ids 0x46e4, mask 0x4eb4 (0x1ff), shift 0x4eb8 (9). Alloc 0x56a3e0 checks
`cmp [edi+0x46e0],0x1f4; jne` and **returns id 0 when full**; 0x56a1a0(0) then returns a static default entry
(guarded by 0x7b05e0) - the animation silently loses its root-motion data, no crash. Raising N to 127 makes
"sum of animation counts over all live anim DBs > 500" reachable sooner; the counter to log is
`*(int*)(*(int*)0x7b05bc + 0x46e0)`. Raising it is a separate job (same template, 500 hard-coded in
0x56a330/0x56a3e0/0x56a2a0/0x56a130/0x56a230 etc., **not swept here**).

### 8.4 Memory

The object grows from 29 KB to 92 KB: negligible. The payload is the `igAnimationDatabase` content of the extra
resident records, allocated in the CMemory pools (singleton 0x7ad2f0, vtable 0x69aa38) of the record's group; group
1 content is only freed at the menu (9.3), so a long session with many leaks costs memory before it costs slots.
XMen2.exe is a non-LAA 2 GB process; log private bytes with the counters.

## 9. Why slots carry over (approach B)

### 9.1 Group namespaces: skins and anim DBs are keyed differently

0x56ae90(name, group) decides the group a name is filed under. A 4- or 5-digit file name (`NNNN[.igb]`, a skin)
goes through CMemory vt+0x2c = 0x55d670, everything else (anim DBs) through vt+0x30 = 0x55d5e0 (jump tables at
0x55d634 / 0x55d6c4, decoded):

| requested group | skin key group (0x55d670) | anim-DB key group (0x55d5e0) |
|---|---|---|
| 0, 1, 4, 5, 6, 0xc, >= 0x16 | unchanged | unchanged |
| 2 (permanent) | 2 | **0xe** |
| 3 | 3 | 0xf |
| 7, 8, 9, 0xa (hero 0-3) | 7, 8, 9, 0xa | 0x10, 0x11, 0x12, 0x13 |
| 0xb (zone) | 0xb | **0x14** |
| 0xd (menu) | 0xd | 0x15 |
| 0xe..0x15 | mapped back to 2, 3, 7, 8, 9, 0xa, 0xb, 0xd | unchanged |

So a zone package's skins are `"11:<n>"`, its anim DBs `"20:<n>"`; the permanent ones `"2:"` / `"14:"`.
`isCached`/`get` (0x56af70) also accept a `"%i:"` prefix on the name (0x5648f0 parses it; `[ebp] = 0` when absent,
0x564978) and map that group the same way.

### 9.2 What the game releases, and when

- **Zone change** (CMap 0x484ce0): `Clearing zone memory pool...` (0x484817) -> CFxManager vt+0x24(0xb) (0x48482f) ->
  **CPrecacheMgr::releaseGroup(0xb, 0)** (tail jump 0x48484e -> 0x561850 via vtable 0x7ae9c8+8). Earlier in the same
  function releaseGroup(3, 0) at 0x484ec5 (plus CMemory pool releases 3, 0xf, 6 at 0x484edf-0x484efb).
- **0x561850 `releaseGroup(g, flag)`**: SIGBMemoryStats bookkeeping (0x56e520/0x56e260); every registered precacher's
  slot 2 with `g` (CAnimDBPrecacher -> 0x56ea30 -> **0x55ab60(g, cache)**: for each name-table entry whose group == g
  and owner == this cache, `owner->release(id, g)` (slot 0 -> record destroyed, slot freed) and the entry removed);
  then cache slot 6 `unbindAll` (every surviving record drops its animation bindings - so the engine already expects
  live CModelActors to survive the release of *other* groups); CMemory vt+0x28(g); then **recursion with
  CMemory vt+0x30(g)** when it differs (0x5618ba-0x5618c5): releaseGroup(0xb) also releases 0x14, the zone's
  anim DBs. Group 0xb/0x14 records are therefore freed completely at every zone change - **the table does not leak**.
- **Return to menu** 0x401ba0: releaseGroup(1,1), (2,1), (3,1), (7,1), (8,1), (9,1), (10,1) at 0x401c95-0x401cf5.
  This is the **only** release of group 1 in the exe (all 16 `call 0x563070 ... call [edx+8]` sites read:
  0x401c88-0x401ce8, 0x484eb8 (3), 0x48630b (3), 0x4b7ba2 and 0x4bc1a6 (hero group in a register, 7..0xa),
  0x5d429d (0xc), 0x5da765 (0xd)).
- Hero packages (groups 7-0xa, released at 0x4b7b90/0x4bc100 when a party slot changes) and the permanent group
  hold their records for the whole session by design: about 6 permanent + 2 per hero = 14 of the observed 15-27.

### 9.3 Where the rest comes from: on-demand loads into group 1

`get` (0x56b0a0) on a miss calls `precache(name, 1)`; group 1 maps to itself for both name types, so the record is
keyed `"1:<name>"` and lives until the menu. The CModelActor asks with explicit prefixes (decomp_actor3.c):
0x41fdf0 slot 0 = `"%i:%s"` with the character's precache group from 0x46dce0 vt+0x118(character+0x150) and
`characteranims`; slot 1 = the fightstyle's DB with its group (0x16 -> 2); slot 2 = `"2:common"`; slot 3 =
`"11:<zone anim DB>"` when the zone names one; the skin: 0x4202c0 -> vt+0x178(name, 0xb or **0x16**). A group of
**0x16** means "in no package": `"22:<name>"` misses, `"2:"`/`"14:"` miss, and the file is loaded into group 1.
The same happens when the character's group is 7-0xa or 0xb but its file is not in that package (content bug), and
0x4c29b0/0x4c5660/0x486440 (`"11:"` probes) show the engine expects zone content to be listed. Consequences:

- Every character a zone spawns whose skin/anim DB is not in the zone package (or its CHRB package) costs 1-2
  group-1 records that persist for the session. Re-entering the same zones does not grow the count (name hit);
  new names do. This matches "15-27 carried over after ~60 zone changes" and the late-session crash at a 34-38 zone.
- The same file can occupy two or three records at once (`"11:"` from the package, `"1:"` on demand, `"7:"` from a
  hero package); the lookup never crosses groups except to 2.
- The CModelActor keeps the **raw record pointer** (+0x30[]). A freed slot keeps stale bytes until reused (the record
  dtor releases the DB but does not null +8), so releasing a group under a live actor that uses it is a dangling
  pointer, not a clean NULL.

### 9.4 Options and verdict

| option | what | safety | value |
|---|---|---|---|
| **B1** content rule | list every skin/anim DB a zone can spawn in its package (V13 already counts; add a check that every CHRB/`monster_skin`/fightstyle name resolves to a package entry) | none needed | stops the growth at the source; does not help retail content that spawns unlisted actors |
| **B2** diagnostic hook | replace vtable slot 5 (0x69bf20, .rdata) with a thunk that logs `(name, group, live count)` when `group == 1` (or when `precache` returns NULL) and chains to 0x56b1c0; or hook the `get` miss branch | no layout change, no timing change; safe | gives the leak list per zone; needed to validate B1 and to size N |
| **B3** release group 1 at zone change | after the game's `releaseGroup(0xb)` (detour the tail jump at 0x48484e, or a post-hook on 0x561850 when g == 0xb) call `CPrecacheMgr->releaseGroup(1, 0)` through the vtable (also releases the IGB cache's group-1 records, textures, etc. - every precacher) | **conditional**: safe only if no CModelActor that survives the zone change holds a group-1 record. Zone NPCs are gone by then (their CActors are destroyed before the pool clear, evidenced by the ordering in 0x484ce0 - **UNVERIFIED** in detail); the party's CModelActors hold groups 7-0xa unless a hero file was missing from its hero package, and whether the party is re-spawned per zone (0x4202c0 has one caller, 0x422e06 in the spawn path 0x422b40 <- 0x42390e) is **UNVERIFIED** | removes the growth entirely; a wrong guess crashes with the SPEC-14 signature on the hero's next animation |
| **A** raise to 127 | sections 5-7 | verified mechanics; needs the name-table raise | absorbs the growth for hundreds of zones and also covers heavy zones that legitimately need > 40 |

Recommendation: ship **A + B2** first (B2 costs nothing and produces the data), fix content per **B1** from B2's
logs, and test **B3** in isolation (test D in section 11) before enabling it - it is the only option that also
bounds memory, but it is the only one that can introduce a crash.

## 10. Risks and unknowns

1. Shared helper 0x4554e0 has a second user (0x45ced8): patching in place would corrupt it -> clone (7.2 step 3).
2. imm8 encodings: N > 127 is impossible without the jcc rewrite of 5.2; the DLL must reject N > 127.
3. Name table 450 binds immediately (8.1) - the raise is a two-structure job even without the IGB raise.
4. Motion pool 500 (8.3) can now be exhausted by a legitimately large actor set; failure is silent (root motion
   zero), so log its counter.
5. **UNVERIFIED**: meaning of `[rec+4]`; whether the party's CModelActors are re-created per zone (B3 safety);
   the exact effect of skipping the ctor warm-up if the C-init alternative is used; any code outside the cache
   decoding an actor id with a literal mask (none found); the jcc addresses listed in 5.2 that follow a `mov`.
6. Ids are `int`; `bumpGeneration` uses `jns` (0x56b77b), so 32-7 = 25 generation bits are fine.
7. The 11 callers never store the object pointer (section 6); any new xml2-fix hook must go through 0x56b8e0.
8. Group 1 also collects IGB-cache and texture records (same `get`-miss pattern); A raises the actor table only.
9. If the exe is not the retail build the expected-bytes guards refuse every patch; the DLL must then leave the
   getter and the atexit thunk untouched as well (all-or-nothing).

## 11. Test plan

Offline (no game):
- Unit test in xml2-fix: map XMen2.exe, apply the 74 in-place fields + 3 absolute refs + 2 call redirections to a
  copy, re-disassemble the 14 functions and 0x455a50: every N-dependent operand equals the new value, every other
  byte unchanged; the cloned 0x4554e0 contains exactly three 0x7f imm8, two 0x7f imm32 and no rel32.
- Recompute the section-5 table from the exe with `scratchpad/actor_table_gen.py` and diff against the table in
  the DLL.

In game (short launches, per the display/harness rules in HANDOFF.md):
- Counters: actor live = dword **0x7b79ac** (retail) / `new_obj + 0x16f50` after relocation; name table count
  `*(int*)(*(int*)0x7ac244 + 0x9404)` (+0x150a0 with 1024 names); motion pool live `*(int*)(*(int*)0x7b05bc + 0x46e0)`; IGB live 0x7bf39c.
  Read them the way tools/actor_slots.py reads 0x7b79ac and add them to build/tour_slots.
- A (regression): patched DLL, unmodified `build/xml1_tour`: 12-zone and full tours behave exactly as today;
  the actor counter never exceeds 40 with budgeted content, and the mask at `new_obj + 0x17150` reads 0x7f / shift 7.
- B (force the old failure): rebuild `mansion/man4/mansion4_1` without `actor_budget.prune_package_root` (38+
  estimate) and enter it after a 60-zone sequence: retail crashes at 0x5743bb; patched must load with the actor
  counter > 40 and every character animating (SPEC 14.1 checklist 11).
- C (long session): tour v2's 60-zone sequence then mansion4_1; log the four counters and private bytes per zone;
  the actor counter's floor after each zone change is the carry-over - with B2 enabled the log names the
  group-1 entries that make it grow.
- D (B3 only): enable the group-1 release; run C again - the floor must return to ~14 after every zone change; then
  deliberately remove a hero's `characteranims` from its hero package so it loads on demand and change zone: if the
  hero animates afterwards the party is re-resolved per zone and B3 is safe, if the game faults at 0x5743bb it is not.
- E: exit the game normally after B and C (the patched dtor 0x56aab0 runs on the relocated block; a crash at exit
  points at a missed displacement).

## 12. Commands used

```
python tools/disasm.py xml2-fix/docs/research/XMen2.exe <rva> 0 <len>        # functions above
python scratchpad/asmrange.py <lo> <hi>                                                  # slices of xml2_text.asm
grep -n -E "call 0x56b8e0|call 0x4554e0|call 0x455a50|call 0x55ab60|call 0x563070" research/scripts/xml2_text.asm
grep -n -E "0x7b(05e[89a-f]|05f|0[6-9a-f]|[1-6]|7[0-9]|7a[0-5])[0-9a-f]*" research/scripts/xml2_text.asm  # abs refs
grep -n -E "\+ 0x(7300|7304|7308|73ac|73b0|73b4|73b8|73bc|73c0|73c4|7464|7468|746c)\]" research/scripts/xml2_text.asm
python scratchpad/actor_sites.py ; python scratchpad/actor_table_gen.py                  # capstone sweeps, section 5
analyzeHeadless ... DecompAt.java decomp_actor2.c / decomp_actor3.c <addrs>              # see decomp_actor2.log
pefile: RTTI locators -> type descriptors for 0x69bf0c / 0x69bed4 / 0x69befc / 0x69af78 / 0x69aa38 / 0x68190c
```
