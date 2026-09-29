# CIGBInfoCache2: the 200-record IGB info cache (XMen2.exe) and how to raise it in memory

Written 2026-09-27 (workflow wf_ba3bb69a-9ac, research only). Target: an "engine limit adjuster" in xml2-fix
(dinput.dll proxy) that raises the cap at startup without shipping a modified exe.

Binary: `XMen2.exe` retail, PE base 0x400000, no relocations/ASLR (DllCharacteristics 0), NOT /LARGEADDRESSAWARE,
sha1 `7d95cdb4a9a599b982147a3389ea7aff211cb82b` (<XML2 folder>\XMen2.exe == the copy in
xml2-fix\docs\research\XMen2.exe). All addresses are VAs. Every address in this file was read from the
capstone disassembly of that exe (tools/disasm.py, research/scripts/xml2_text.asm) unless marked **UNVERIFIED**.
Sections 2-7 are the IGB cache proper; section 8 covers the two other structures the raise depends on.

**Verdict: raise-with-care.** The cache itself relocates cleanly (static object, everything reached through one
getter, all size-dependent fields are 32-bit immediates/displacements, 88 fields in 16 functions plus one shared
helper to clone). But raising it alone is nearly useless: every record also occupies one entry of a *global*
450-entry name table (`ratl::map_os<string_vs<68>, SCacheHandle, 450>`) shared with textures (192), actors (40),
playfields and motion paths, whose "full" check makes the same `precache` return NULL (0x56edfc). That table must
be raised in the same patch (section 8.1, 71 fields - corrected 2026-09-28, was 67), and the 692-slot `CSafeResMgrI<IModel,692,44>` handle pool
should be watched (8.2). Suggested new caps: **512 IGB records, 1024 names**.

---------------------------------------------------------------------------------------------------------------

## 1. Identity and where the object lives

| item | value | evidence |
|---|---|---|
| class | `CIGBInfoCache2` : `IIGBInfoCache2` : `ICacheBase` | RTTI `.?AVCIGBInfoCache2@@` 0x6e235c, `.?AVIIGBInfoCache2@@` 0x6e233c, vtable 0x69befc = `.?AVICacheBase@@` (dtor 0x56f9b7 resets to it) |
| vtable | 0x69c034, 8 slots (see section 3) | RTTI locator 0x69c030 -> 0x6b6378 |
| singleton | **static object at 0x7b7fb0**, size 0x7718 (0x7b7fb0..0x7bf6c8) | getter 0x56f9f0: `mov [0x7b7fb0],0x69c034` (0x56fa12), `mov ecx,0x7b7fb4; call 0x56e9c0` (0x56fa07/0x56fa1c), `mov eax,0x7b7fb0; ret` (0x56fa2e) |
| init guard | bit 0 of dword 0x7bf6c8 (`mov cl,[0x7bf6c8]; test al,cl` 0x56f9f0-0x56f9fd) - this dword sits *immediately after* the object (0x7b7fb4 + sizeof(pool) 0x7714 = 0x7bf6c8), which pins the object size | 0x56f9f0-0x56fa0c |
| atexit dtor | 0x67e190: `mov ecx,0x7b7fb0; jmp 0x56f980` registered by `push 0x67e190; call 0x67211e` at 0x56fa21 | read |
| getter callers | 12 sites, all use the returned pointer through the vtable only (section 6) | grep `call 0x56f9f0` |
| absolute references into the object | exactly 4: 0x56fa07 (`0x7b7fb4`), 0x56fa12 (`[0x7b7fb0]`), 0x56fa2e (`0x7b7fb0`), 0x67e190 (`0x7b7fb0`); nothing else in .text names an address in 0x7b7fb0..0x7bf6c7 | grep of the whole listing for `0x7b7fb?`/`0x7b8xxx`..`0x7bf6xx` |
| section | .data (VA 0x6d4000-0xa6cc10, raw size 0x20000 -> the object is in the zero-filled tail, i.e. bss) | pefile |

The object is a thin wrapper: `+0` vtable, `+4` an embedded fixed-capacity pool (called **S** below, `S = this+4`,
0x7b7fb4) that has no vtable of its own. All pool methods take `ecx = S`; the cache methods take `ecx = this` and
form `S = this+4` (`lea edx,[ebx+4]` 0x56edd3, `lea esi,[ecx+4]` 0x56eb4b, `lea edi,[ecx+4]` 0x56f85c).

## 2. Layout (verified field by field)

Record stride is **0x90 = 144 bytes** (`lea eax,[ecx+ecx*8]; shl eax,4` at 0x56edd8/0x56ecb4/0x56f662/0x56f83e/
0x56f948/0x56eb7f; the inverse `imul 0x38e38e39; sar edx,5` = /144 at 0x56f196 and 0x56f4b9).

| S-relative | this-relative | field | size | set / used at |
|---|---|---|---|---|
| 0x0000 | 0x0004 | `rec[200]` records, 0x90 each | 0x7080 | 0x56f640/0x56f7e0 return `S + idx*0x90`; 0x56e8b0, 0x56f948 |
| 0x7080 | 0x7084 | bitmap A "allocated" (7 dwords = 200 bits) | 0x1c | zeroed 0x56e965-0x56e97c; set 0x56f668/0x56f837; cleared 0x56f979; scanned by dtor 0x56e844-0x56e8c3 |
| 0x709c | 0x70a0 | free-index ring `ring[201]` (N+1 dwords) | 0x324 | filled 0x56e93f (ring[i]=i, i<200); pop 0x56f7e9/0x56f691; push 0x56f926 |
| 0x73c0 | 0x73c4 | ring write position | 4 | 0x56e8f4/0x56e910/0x56e923/0x56e931, 0x56f8f3-0x56f914 |
| 0x73c4 | 0x73c8 | ring read position | 4 | 0x56f684, 0x56f7e2, 0x56f80c-0x56f821; 0x491180 as ring+0x328 |
| 0x73c8 | 0x73cc | ring count (free records) | 4 | 0x56e900/0x56e916/0x56e929, 0x56f82b, 0x56f8f9/0x56f90c; 0x491180 as ring+0x32c |
| 0x73cc | 0x73d0 | bitmap B "live" (7 dwords) | 0x1c | zeroed 0x56e993-0x56e9aa; set 0x56f6a5/0x56f805; cleared 0x56f8df; scanned 0x56eb52/0x56ebc0 |
| 0x73e8 | **0x73ec** | **live count** (the value compared with 200) | 4 | zero 0x56e9af; ++ 0x56f6be/0x56f831; -- 0x56f92d; **cap check 0x56ede5** |
| 0x73ec | 0x73f0 | `id[200]`, id = (generation << shift) \| index, generation starts at 1 | 0x320 | init 0x56ea00-0x56ea1d; read 0x56f1a7/0x56f4d1; bumped 0x56f894-0x56f8b3 |
| 0x770c | **0x7710** | **index mask** = 0xff (bits(N-1)) | 4 | computed 0x56e9d9-0x56e9ec; used 0x56edcd, 0x56eca8, 0x56f855 (`id & mask` -> index) |
| 0x7710 | 0x7714 | shift = 8 (= number of mask bits) | 4 | 0x56e9f2; used 0x56ea02, 0x56f886, 0x56f8a4 (`1 << shift`) |
| 0x7714 | 0x7718 | end of object | | 0x7b7fb4+0x7714 = 0x7bf6c8 = guard dword |

Note that the two this-relative displacements the cache methods use (0x73ec = live, 0x7710 = mask) happen to equal
the S-relative displacements of the *following* fields (id table, shift). A patcher can therefore remap the two
numbers uniformly (0x73ec -> new, 0x7710 -> new) without caring which base the instruction uses, as long as the new
layout keeps `live` directly before `id[]` and `mask` directly before `shift` (section 7 does).

Record contents (0x56e570 ctor, 0x56dad0 dtor; only partially read, field meanings **UNVERIFIED**): +0/+4/+8 three
refcounted Alchemy handles (addref [0x67f65c], release [0x67f660]), **+0xc the record's id** (written by the pool at
0x56f1a7 through 0x55adf0 and stored in the name table; zeroed by the dtor 0x56daf8), +0x14 group, +0x2c and +0x38
strings ([0x67fa60] ctor), +0x44 a sub-object (0x56c6f0 ctor / 0x56c770 dtor), +0x8c a flag byte. Nothing in the
record depends on N; relocation never touches record contents.

### 2.1 The constructor chain (only reachable from the getter)

- 0x56f9f0 getter -> 0x56e9c0 `pool::pool()` (sole call site 0x56fa1c)
  - 0x56e960 (sole call site 0x56e9c4): zero bitmap A (7 dwords, unrolled), ring pos/count, bitmap B (7 dwords),
    live; then 0x56e8f0 (sole call site 0x56e9b5): `for i in 0..199: ring.push(i)` with the wrap test
    `cmp eax,0xc8` 0x56e91e / `mov eax,0xc7` 0x56e937 / loop bound `cmp edx,0xc8` 0x56e947.
  - back in 0x56e9c0: mask/shift derived from **N-1 = 0xc7** (`mov edx,0xc7` 0x56e9d9; loop shifts edx right and
    grows the mask until edx==0: 199 -> 8 iterations -> mask 0xff, shift 8), then `id[i] = (1<<shift)|i` for
    `i < 0xc8` (0x56ea18).
- The unrolled zeroing covers only 7 dwords per bitmap: a bigger pool must be handed *pre-zeroed* memory.

## 3. Methods

CIGBInfoCache2 vtable 0x69c034 (this-relative):

| slot | address | what it does | N-dependent fields |
|---|---|---|---|
| 0 (+0x00) | 0x56f850 | `release(id, group)`: `idx = id & [this+0x7710]`; 0x56f8c0(S, idx) then 0x56f880(S, idx) | mask read 0x56f855 |
| 1 (+0x04) | 0x56f9d0 | scalar deleting dtor -> 0x56f980 (sets vtable, 0x56e840 on S, vtable = 0x69befc) | via 0x56e840 |
| 2 (+0x08) | 0x56ea30 | `releaseGroup(group)`: name table 0x55af80 -> 0x55ab60(group, this) which calls slot 0 for every entry of that group owned by this cache | none |
| 3 (+0x0c) | 0x56ea50 | `isCached(name)`: looks up `name`, then `"2:%s"` (permanent group) in the name table | none |
| 4 (+0x10) | 0x56ebe0 | `get(name)`: lookup `name` then `"2:%s"`; hit -> `S + (id & mask)*0x90`; miss -> slot 5 `precache(name, 1)` | mask 0x56eca8 |
| 5 (+0x14) | 0x56ed00 | `precache(name, group)`: see section 4 | 0x56edcd, **0x56ede5**, 0x56f1a7, 0x56f4d1 |
| 6 (+0x18) | 0x56eb40 | for every live record (bitmap B scan via 0x490d70) call playfield mgr 0x585e70 vt+0x18(record); end sentinel `mov esi,0xc8` 0x56eb61; iterator step 0x56ebb0 | 0x56eb52, 0x56eb61, 0x56ebc0 |
| 7 (+0x1c) | 0x48ef90 | `ret` (empty) | none |

Pool methods (ecx = S): 0x56e840 dtor (destroys every allocated record, scans bitmap A with three `cmp esi,0xc8`),
0x56e8f0 ring fill, 0x56e960/0x56e9c0 ctor, 0x56f640 `allocAt(idx)` (sets bitmap A, returns record), 0x56f680
`takeFreeIndex()` (idx = ring[readpos]; set bitmap B; ring pop via **0x491180**; live++), 0x56f7e0 `alloc()` (same
inline, plus bitmap A; wrap `cmp ecx,0xc8` 0x56f813), 0x56f880 `bumpGeneration(idx)` (`id[idx] += 1<<shift`, on
sign overflow reset to `(1<<shift)|idx`, 0x56f89b `jns`), 0x56f8c0 `free(idx)` (0x56f940 record dtor + clear bitmap
A; clear bitmap B; ring push with wrap `cmp eax,0xc8` 0x56f901 / `mov eax,0xc7` 0x56f91e; live--).

Shared helpers:

- **0x490d70** `bitset<200>::findNext(from, wantSet)` - capacity 200 hard-coded five times (0x490d74, 0x490d7e,
  0x490dab, 0x490df8, 0x490dff). Called by the cache (0x56e8c3, 0x56eb58, 0x56ebc6) **and by two unrelated owners
  of 200-bit sets: 0x4916b9 and 0x57d8d0** (both clear a 7-dword bitmap after iterating it). It must therefore be
  **cloned**, not patched in place; it is position-independent (only short intra-function jumps, no calls, no
  globals; 0x99 bytes 0x490d70-0x490e09).
- **0x491180** `ring<200>::pop()` on the ring base (`[ecx+0x328]` = readpos, `[ecx+0x32c]` = count, wrap
  `cmp eax,0xc8` 0x49118d). **Sole caller 0x56f6b9** -> patch in place.

## 4. The cap check and the silent failure

`precache(name, group)` 0x56ed00:

1. 0x56ed4b-0x56edc8: normalise the name (0x58e970), format the key `"%i:%s"` (0x69b634) for the requested group
   and look it up in the global name table (0x55af80 getter, 0x55ab00 lookup); then the same for group 2
   (permanent). A hit returns the existing record: `edi = [entry+0xc]` (id), `S + (id & mask)*0x90` (0x56edca-0x56ede0).
2. **0x56ede5 `cmp dword ptr [ebx+0x73ec], 0xc8; jge 0x56f280`** -> `xor eax,eax` (0x56f280): with 200 live
   records the function returns NULL. No log, no assert.
3. 0x56edf5-0x56ee03: `if (nameTable->isFull()) return NULL` (0x55a6a0: `[map+0x9404] >= 0x1c2`). Second silent
   NULL (section 8.1).
4. Otherwise the IGB is loaded (0x5642d0 file system, vt+0x24), its objects are classified (three igObject metas
   [0x67fdf4], [0xa6ca90], [0x67ff50]); model nodes get a `CModel` handle from the IModel pool (0x56f6d0 ->
   0x57eb90, section 8.2); a record is taken (0x56f680 + 0x56f640, or 0x56f7e0 for the no-model path 0x56f3fd),
   constructed (0x56e570) and registered in the name table with its id (0x55adf0 at 0x56f1d4 / 0x56f4ea:
   `add(key, group, this, id[idx])`).

Why the game bounces back to the previous zone (verified in the SPEC-13 investigation and re-read here): the zone
package's own map IGB is its last `model` entry; `Loading Zone igb...` (0x485458) asks the playfield manager for
it (0x48548b -> playfield `get`, which ends in cache slot 4/5 -> NULL); the result bit 0x40 stays clear
(0x48548d-0x4854a6) and 0x4854ac-0x4854c7 calls CMap vt+0xbc with `CMap+0x60`, the previous zone name, and sets
the load-pending bit again. There is no exception for a debugger to see.

## 5. Every N-dependent field in the cache code (patch table)

88 fields, all 32-bit (no imm8/disp8 forms exist because 199/200 and the displacements exceed 127). `@+k` is the
byte offset of the field inside the instruction; file offset = VA - 0x400000 (the .text section is mapped 1:1 at
raw 0x1000 = VA 0x401000, so file = VA - 0x400000 for all of these). Values for the suggested N = 512 layout of
section 7 are given in the last column (S-relative unless the row says T).

Immediates (N = 0xc8 -> 0x200, N-1 = 0xc7 -> 0x1ff):

| VA | instruction | field | new |
|---|---|---|---|
| 0x490d74 | `cmp eax,0xc8` | @+1 | clone only |
| 0x490d7e | `mov eax,0xc8` | @+1 | clone only |
| 0x490dab | `cmp eax,0xc8` | @+1 | clone only |
| 0x490df8 | `cmp eax,0xc8` | @+1 | clone only |
| 0x490dff | `mov eax,0xc8` | @+1 | clone only |
| 0x49118d | `cmp eax,0xc8` | @+1 | 0x200 |
| 0x56e866 | `cmp esi,0xc8` | @+2 | 0x200 |
| 0x56e8a7 | `cmp esi,0xc8` | @+2 | 0x200 |
| 0x56e8ca | `cmp esi,0xc8` | @+2 | 0x200 |
| 0x56e91e | `cmp eax,0xc8` | @+1 | 0x200 |
| 0x56e937 | `mov eax,0xc7` | @+1 | 0x1ff |
| 0x56e947 | `cmp edx,0xc8` | @+2 | 0x200 |
| 0x56e9d9 | `mov edx,0xc7` (mask/shift seed) | @+1 | 0x1ff |
| 0x56ea18 | `cmp eax,0xc8` | @+1 | 0x200 |
| 0x56eb61 | `mov esi,0xc8` (iteration end sentinel) | @+1 | 0x200 |
| 0x56ede5 | `cmp dword ptr [ebx+0x73ec],0xc8` **the cap** | imm @+6 | 0x200 |
| 0x56f813 | `cmp ecx,0xc8` | @+2 | 0x200 |
| 0x56f901 | `cmp eax,0xc8` | @+1 | 0x200 |
| 0x56f91e | `mov eax,0xc7` | @+1 | 0x1ff |

Displacements (old -> new for N = 512, section 7):

| old | field | new | sites (VA, field offset) |
|---|---|---|---|
| 0x7080 | bitmap A | 0x12000 | 0x56e844@+2, 0x56e84b@+2, 0x56e965@+2, 0x56f64c@+3, 0x56f837@+3, 0x56f966@+3, 0x56f96d@+3 |
| 0x709c | ring | 0x12040 | 0x56e93f@+3, 0x56f68a@+2, 0x56f7e9@+3, 0x56f926@+3 |
| 0x73c0 | ring write pos | 0x12844 | 0x56e8f4@+2, 0x56e910@+2, 0x56e923@+2, 0x56e931@+2, 0x56e97f@+2, 0x56f8f3@+2, 0x56f906@+2, 0x56f914@+2 |
| 0x73c4 | ring read pos | 0x12848 | 0x56e8fa@+2, 0x56e985@+2, 0x56f684@+2, 0x56f7e2@+2, 0x56f80c@+2, 0x56f819@+2, 0x56f821@+2 |
| 0x73c8 | ring count | 0x1284c | 0x56e900@+2, 0x56e916@+2, 0x56e929@+2, 0x56e98b@+2, 0x56f82b@+2, 0x56f8f9@+2, 0x56f90c@+2 |
| 0x73cc | bitmap B | 0x12850 | 0x56e993@+2, 0x56eb52@+2, 0x56ebc0@+2, 0x56f6a5@+3, 0x56f6ac@+3, 0x56f805@+3, 0x56f8df@+3, 0x56f8e6@+3 |
| 0x73e8 | live (S) | 0x12890 | 0x56e9af@+2, 0x56f6be@+2, 0x56f831@+2, 0x56f92d@+2, 0x56f935@+2 |
| 0x73ec | id table (S) / live (T) | 0x12894 | S: 0x56e9f8@+2, 0x56f1a7@+3, 0x56f4d1@+3, 0x56f894@+3, 0x56f89d@+3, 0x56f8b3@+3; T: 0x56ede5@+2 |
| 0x770c | mask (S) | 0x13094 | 0x56e9cd@+2, 0x56e9ec@+2 |
| 0x7710 | shift (S) / mask (T) | 0x13098 | S: 0x56e9d3@+2, 0x56e9f2@+2, 0x56ea02@+2, 0x56f886@+2, 0x56f8a4@+2; T: 0x56eca8@+2, 0x56edcd@+2, 0x56f855@+2 |
| 0x328 | ring-relative read pos (0x491180) | 0x808 | 0x491180@+2, 0x491187@+2, 0x49119a@+2 |
| 0x32c | ring-relative count (0x491180) | 0x80c | 0x491192@+2, 0x4911a5@+2 |

Coverage check: a scan of 0x56e570-0x56fa34, 0x490d70-0x490e09 and 0x491180-0x4911ac for *any* disp32 in
0x7000..0x7800 found nothing outside this set; the whole-listing grep for the ten displacements found no other
function using them with this object (the hits at 0x56aab3-0x56b766 are the actor manager, the N=40 instantiation
of the same pool template with its own copies of every method: ring 0x7308, positions 0x73ac/0x73b0/0x73b4,
bitmap 0x73b8, live 0x73c4 - the `cmp [obj+0x73c4],0x28` of SPEC 14). The other displacement hits (0x415ce0..,
0x47c76a.., 0x4c6810..) are unrelated classes.

## 6. The 12 getter callers (all vtable-relative, nothing to patch)

| caller | uses |
|---|---|
| 0x560e90 (CIGBPrecacher vt 0x69b070 slot 2) | `jmp [vt+8]` releaseGroup |
| 0x560ea0 (CIGBPrecacher slot 0, the `model` package entry) | `[vt+0x14]` precache(name, group) |
| 0x562437 (CPrecacheMgr ctor 0x5622d0 path, after `mov [edi],0x69b070`) | result unused (forces construction) |
| 0x562f1a (CPrecacheMgr::CPrecacheMgr 0x562bc0 registration list) | result unused (forces construction) |
| 0x577ce1 | `[vt+0x10]` get |
| 0x57ae8d (motion paths) | `[vt+0x14]` precache |
| 0x58511d (playfield manager) | `[vt+0x1c]` slot 7 (empty) |
| 0x588979 (playfield `get` 0x588950) | `[vt+0x10]` get |
| 0x58dbd2 | `[vt+0x10]` get |
| 0x5f50aa (HUD heads `hud/hud_head_%s`) | `[vt+0xc]` isCached |
| 0x560e80 is the *actor* precacher's twin (calls 0x58a3a0, not this getter) | - |

No caller dereferences a field of the object; the only other consumers of a record pointer are the record's own
methods, and the only consumers of an *id* outside the cache are the name table (`SCacheHandle+0xc`, section 8.1)
and 0x55ab60, which hands the id straight back to slot 0. All three id->index decodes in the exe (0x56eca8,
0x56edcd, 0x56f855) read the mask from the object; no hard-coded `& 0xff` was found in the cache code (a
hard-coded decode elsewhere is **UNVERIFIED** as absent, but no other code reads `SCacheHandle+0xc` for this
cache: the readers of entry+0xc are 0x56edca, 0x56eca5, 0x55abba, 0x55ace9).

## 7. Relocation design (N = 512)

### 7.1 New layout (S-relative; object = 4 + sizeof(S))

| field | old | new | size |
|---|---|---|---|
| rec[N] | 0x0000 | 0x00000 | 512 * 0x90 = 0x12000 |
| bitmap A | 0x7080 | 0x12000 | ceil(512/32) = 16 dwords = 0x40 |
| ring[N+1] | 0x709c | 0x12040 | 513 * 4 = 0x804 |
| ring write pos | 0x73c0 | 0x12844 | 4 |
| ring read pos | 0x73c4 | 0x12848 | 4 (ring + 0x808) |
| ring count | 0x73c8 | 0x1284c | 4 (ring + 0x80c) |
| bitmap B | 0x73cc | 0x12850 | 0x40 |
| live | 0x73e8 | 0x12890 | 4 |
| id[N] | 0x73ec | 0x12894 | 0x800 |
| mask | 0x770c | 0x13094 | 4 (becomes 0x1ff) |
| shift | 0x7710 | 0x13098 | 4 (becomes 9) |
| sizeof(S) | 0x7714 | 0x1309c | object 0x130a0 = 78 KB |

Any N works as long as the same recipe is followed; the ctor derives mask = bits(N-1), shift = bit count, so N need
not be a power of two (N = 512 gives mask 0x1ff, shift 9; ids stay positive for 2^22 generations per slot before the
0x56f89b reset).

### 7.2 Steps (all in DllMain / the proxy's early init, before the exe's CRT runs any static initialiser;
xml2-fix already patches code there)

1. `new_obj = VirtualAlloc(NULL, 0x130a0, MEM_COMMIT|MEM_RESERVE, PAGE_READWRITE)` (zero-filled - required,
   because the ctor only zeroes 7 dwords per bitmap).
2. Apply the 19 immediate patches and the 76 displacement patches of section 5 (skip the five 0x490d70 rows), each
   guarded by the retail bytes exactly like `frame_rate_rules::code_patch` does today (`expected` bytes, offset,
   4-byte replacement; VirtualProtect PAGE_EXECUTE_READWRITE, memcpy, restore, FlushInstructionCache).
3. Clone 0x490d70: copy 0x99 bytes to an executable buffer, replace the five imm32 0xc8 with N, and patch the
   three `call rel32` operands at 0x56e8c3, 0x56eb58, 0x56ebc6 (E8 xx xx xx xx, field @+1) to point at the clone.
   Leave 0x490d70 itself alone (0x4916b9 and 0x57d8d0 keep their 200-bit sets).
4. Redirect the four absolute references so the game constructs and destructs *our* block with its own (now
   patched) code: 0x56fa07 imm32 `0x7b7fb4` -> new_obj+4; 0x56fa12 disp32 `[0x7b7fb0]` -> new_obj; 0x56fa2e imm32
   `0x7b7fb0` -> new_obj; 0x67e190 imm32 `0x7b7fb0` -> new_obj. The guard dword 0x7bf6c8 stays where it is (it
   lies outside the object), so the game's once-only logic still works.
   Alternative (if the ctor is to be bypassed): overwrite 0x56f9f0 with `B8 <new_obj> C3` and initialise the block
   in C (vtable 0x69c034 at +0, ring[i]=i, write pos 0, read pos 0, count N, id[i] = (1<<9)|i, mask 0x1ff,
   shift 9). This registers no atexit dtor, which is harmless. Do NOT leave the getter unpatched with a patched
   ctor: the ctor would then run with the new displacements on the 0x7718-byte static and overwrite 0x7bf6c8 and
   everything after it.
5. Raise the name table in the same pass (8.1); without it the new records cannot be registered.
6. Log the two counters at zone changes (section 10).

Ordering matters only in one place: the patches (2, 3) must be in before the first call of 0x56f9f0, which happens
from the CPrecacheMgr constructor (0x562437 / 0x562f1a) during game start-up, long after DllMain. Nothing in the
process touches the cache before that.

### 7.3 What does NOT need patching

- Record stride math (0x90, the 0x38e38e39 reciprocal): unchanged.
- The bit-index arithmetic (`sar 5`, `and 0x1f`): unchanged.
- The `%i:%s` key format, the group numbers, CMap, CPrecacheMgr, the precachers.
- The actor manager's copies of the pool template (different functions, N = 40).

## 8. Structures the raise depends on

### 8.1 The global resource name table: `ratl::map_os<ratl::string_vs<68>, SCacheHandle, 450>` (binding)

| item | value | evidence |
|---|---|---|
| class | `.?AV?$map_os@V?$string_vs@$0EE@@ratl@@USCacheHandle@@$0BMC@@ratl@@` (key 0x44 chars, value SCacheHandle, capacity 0x1c2 = **450**), node pool `tree_base<value_semantics_node<string_vs<68>,450,tree_node>>` | RTTI of vtables 0x69a708 / 0x69a6f0 |
| object | heap, pointer at **0x7ac244**; allocated lazily by the getter 0x55af80 through the game allocator `0x5605e0(size 0xb064, pool 0xe, 0xf)` (zero-fills, 0x560627), constructed by 0x55af00, freed at exit by 0x55af50 | read; decomp_limits1.c:53 agrees |
| entries | `SCacheHandle[450]` at +0x9408, 16 bytes: +0 name string ptr, +4 group, +8 owner `ICacheBase*`, **+0xc id**; entry bitmap 15 dwords at +0xb028; count at +0x9404 | 0x55adf0 (add), 0x55ab00 (lookup returns `map + idx*16 + 0x9408`), 0x55ab60 |
| node pool | embedded pool **P at map+0xc**; its offsets below are **P-relative** (0x55aa00, 0x55a810, 0x55a8d0, 0x55adb0 get ecx/esi = P: 0x55af04 `lea ecx,[esi+0xc]`, 0x55aaa4, 0x55ada0 `add ecx,0xc`). 450 tree nodes of 0x50 (flags/parent +0, left +4, right +8, key 0x44 at +0xc) at P+0 (= map+0xc; 0x55ad20 returns map+0xc+i*0x50); 4 unused bytes at P+0x8ca0; node ring `[451]` at P+0x8ca4 with write/read/count at P+0x93b0/+0x93b4/+0x93b8 (ring-relative +0x70c/+0x710/+0x714); node bitmap 15 dwords at P+0x93bc; node count at P+0x93f8 = **map+0x9404, the same dword as the "entry count"** (the map's size is its node count) | 0x55aa00, 0x55a810, 0x55a880, 0x55a8d0, 0x55a760 |
| full checks | `isFull` 0x55a6a0 (`[map+0x9404] >= 0x1c2`) called by the IGB cache 0x56edfc, the actor manager 0x56b2d3, motion paths 0x57a5dc, textures 0x5867df, playfields 0x58a0a2; `add` 0x55adf0 refuses at 0x55ae07 | grep `call 0x55a6a0` / `call 0x55adf0` |
| who registers names | IGB cache (`%i:%s` per record), actor manager 0x56b453, motion paths 0x57a6c3, texture manager 0x58699c, playfield manager 0x58a16b: roughly the sum of the CSafeResMgr capacities 200 + 192 + 40 + 6 + ... | 41 call sites of the getter 0x55af80 |

Consequence: with IGB raised to 512 but the map left at 450, `precache` fails at 0x56edfc as soon as
IGB + textures + actors + others reach 450, i.e. at roughly 210-310 IGB records depending on the zone. The map has
to grow to at least 450 + (N-200); **1024** leaves room for a later texture-cache raise.

All N-dependent fields of the map - **71**, not 67: the list below (67) plus the four marked **[added]**, found by a
capstone sweep of every function 0x55a600-0x55afc0 on 2026-09-28 (the xml2-fix limits module, `limits_rules.hpp`
`name_sites`, carries all 71 with their retail bytes; xml2_test checks them against the exe). The helpers 0x55a600-0x55aa45
have no other callers, verified by grep, and the only pointers to any of the map's functions in the image are its
own two vtables (0x69a6f0/0x69a708, slots 0x55ad20/0x55ad40/0x55ad70/0x55ada0) and the push of 0x55af50, so all of
them can be patched in place. The generic tree routines 0x601a40/0x601e50 and the bit-clear 0x570130 are shared by
dozens of maps and go through the vtable; nothing in them depends on M. Nothing outside 0x55a600-0x55afc0 uses any
of the map's displacements.

Immediates: `0x1c2` at 0x55a604@+1, 0x55a60e@+1, 0x55a63b@+1, 0x55a688@+1, 0x55a68f@+1 (bitset<450>::findNext,
exclusive to this map), 0x55a6a8@+2 (isFull), 0x55a6d9@+2, 0x55a719@+2, 0x55a72e@+1 (clearAll), 0x55a844@+2 (node
alloc wrap), 0x55a88e@+1 (node push wrap), 0x55a8fe@+1, 0x55a927@+2 (node ring fill), 0x55aa07@+1 (node zero loop
count), 0x55ae07@+6 (add: full check); `0x1c1` at 0x55a8b1@+1, 0x55a917@+1; `mov ecx,0xf` bitmap dword counts at
0x55a735@+1, 0x55aa26@+1, 0x55af28@+1 (-> ceil(M/32)); allocation size `push 0xb064` 0x55af8d@+1; the shifted
entry index `0x941` (= (0x9408+8)>>4, i.e. the 16-byte entries base+8 divided by 16) at 0x55aba8 `lea
edx,[ebp+0x941]` disp32@+2 and 0x55acd5 `add eax,0x941` imm32@+1 - **the new entries base must stay congruent to 8
mod 16** for these two to be expressible. **[added]** the entries base as an immediate: 0x55af40 `add ecx,0x9408`
imm32@+2 (the clear called by the atexit free 0x55af50, which then jumps to 0x55a6c0 with ecx = the entries).

Displacements: node ring 0x8ca4 (0x55a818@+3, 0x55a91f@+3, 0x55aa19@+2, 0x55adcc@+2); node ring pos/count
0x93b0 (0x55a8d4, 0x55a8f0, 0x55a903, 0x55a911 @+2), 0x93b4 (0x55a812, 0x55a83b, 0x55a84a, 0x55a852, 0x55a8da
@+2), 0x93b8 (0x55a85c, 0x55a8e0, 0x55a8f6, 0x55a909 @+2); ring-relative 0x70c/0x710/0x714 (0x55a744, 0x55a74a,
0x55a750, 0x55a880, 0x55a886, 0x55a893, 0x55a899, 0x55a8a5 @+2); node bitmap 0x93bc (0x55a825@+3, 0x55aa2b@+2,
0x55adb8@+2); node live 0x93f8 (0x55a862, 0x55a86a, 0x55aa35, 0x55add7 @+2); entry count 0x9404 (0x55a6a0@+2,
0x55ae07@+2); entries 0x9408 (0x55ab3d@+3, 0x55abc8@+2, 0x55ae82@+2), entry+4 0x940c (0x55ab92@+3,
0x55accd@+2), entry+0xc 0x9414 (0x55abba@+2, 0x55ace9@+2); entry bitmap 0xb028 (0x55aa7b@+3, 0x55ac18@+3,
0x55af22@+2). **[added]** the entry bitmap **entries-relative**, 0x1c20 = M*16: 0x55a6c0 `mov eax,[ecx+0x1c20]` @+2 and
0x55a6c7 `lea edi,[ecx+0x1c20]` @+2 (clearAll, ecx = map+0x9408), and 0x55ae88 `lea esi,[edx+ecx*4+0x1c20]` @+3 in
`add` (edx = map+0x9408; sets the new entry's bit). Missing 0x55ae88 alone would make every `add` set its bitmap bit
inside the entries array of a bigger table.

Bases: the node-pool displacements (0x8ca4, 0x93b0-0x93b8, 0x93bc, 0x93f8) are P-relative, P = map+0xc; 0x9404,
0x9408, 0x940c, 0x9414, 0xb028 and 0x941 are map-relative; 0x1c20 is entries-relative; 0x70c/0x710/0x714 ring-relative.
0x93f8 (P) and 0x9404 (map) are the **same field**, the node count, so a layout must keep map-count = P-live + 0xc.

Relocation for M (corrected 2026-09-28; the recipe as `limits_rules::name_layout_for`, which reproduces the retail
layout for M = 450 field for field). P-relative: nodes 0..M*0x50; the 4 unused bytes at M*0x50 (kept); ring
M*0x50+4, (M+1) dwords; write/read/count right after it; node bitmap ceil(M/32) dwords; node count. Map-relative:
count = P-count + 0xc; entries = the first offset >= count+4 that is 8 mod 16; entry bitmap = entries + M*16;
size = entry bitmap + ceil(M/32)*4.

M = 1024: ring 0x14004; write/read/count 0x15008/0x1500c/0x15010 (ring-relative 0x1004/0x1008/0x100c); node bitmap
0x15014; node count P 0x15094 = **map 0x150a0**; 4 bytes of padding; entries 0x150a8 (+4 = 0x150ac, +0xc = 0x150b4,
shifted index 0x150b); entry bitmap 0x190a8 (entries-relative 0x4000); size 0x19128 (~100 KB); 0x1c2 -> 0x400,
0x1c1 -> 0x3ff, 0xf -> 0x20. **Correction:** the earlier version of this paragraph put the entry count at 0x150a4,
shifting the P-relative node count (0x93f8) and the map-relative count (0x9404) as if they were different fields;
isFull/add would then read a dword nothing ever increments and the table could never report full (xml2_test runs
the patched node allocator 1024 times and checks isFull turns true at the 1024th, which that layout would fail).
The "8-byte offset" worry was the two bases: nodes start at map+0xc = P+0, and the ring at P+0x8ca4 = map+0x8cb0.

Allocation (read 2026-09-28): 0x5605e0 takes the pool's allocate (vt+0xcc) and zero-fills the result with `rep stosd`
before returning, so a NULL from pool 0xe would fault inside 0x5605e0 (or in Alchemy's allocation-failure callback)
rather than reach the getter's NULL test; pool 0xe's headroom for the larger block is still **UNVERIFIED**. The
fallback avoids the question and is what xml2-fix implements: allocate the block in the DLL (VirtualAlloc,
zero-filled), patch the fields (and the getter's `push 0xb064`, so a table the game might build itself would be the
right size), construct it by calling the patched 0x55af00 on it (pure code: vtables, the node pool constructor
0x55aa00, the ring 0x55a940/0x55a740/0x55a8d0, the entry bitmap), and store it at 0x7ac244 in DllMain. The getter
0x55af80 then returns it at once: its allocation branch is the only place that registers the free 0x55af50 (push
0x55af50; call 0x401d50, a 32-entry shutdown list at 0x6f3a38), so nothing needs neutralising. 0x55af50 itself:
if [0x7ac244], call 0x55af40 (clearAll on the entries), free through 0x5606a0(ptr, 0xe), zero the pointer. The five
references to 0x7ac244 are 0x55af51, 0x55af6d, 0x55af80, 0x55afae, 0x55afb8 - all in the getter and the free.

### 8.2 `CSafeResMgrI<IModel, 692, 44>` - the CModel handle pool (watch)

RTTI `.?AV?$CSafeResMgrI@VIModel@@$0CLE@$0CM@@@` (vtable 0x69c320; 0x2b4 = 692 handles of 0x2c bytes) is the pool
`precache` draws a `CModel` from for every model node it finds in an IGB (0x56f6d0 -> 0x57eb90). Its ctor 0x5752c0
/ 0x5753c0 loops `cmp esi,0x2b4` (0x5753d9); the same pool template (bitmap A 0x76f0, ring 0x7748, bitmap B
0x8228, live 0x8280, ids 0x8284, shift 0x8d58 - seen in 0x5753f6 and 0x5700f0). It is embedded at +0x12938 of a
static aggregate at **0x7bf6d0** (`mov [edi+0x12938],0x69c320` 0x575549; aggregate ctor 0x5754c0 from 0x575642 /
0x575ce3 / 0x575d59 with `mov ecx,0x7bf6d0`; atexit 0x67e1a0 -> 0x575560). Retail sizing suggests ~3.5 CModels per
IGB record on average, so 512 records could exhaust 692 handles if many multi-model IGBs are resident. Raising it
means relocating the whole aggregate (bigger job; same recipe). First measure: live count at
0x7bf6d0 + 0x12938 + 4 + 0x8280 = **0x7da28c** (**UNVERIFIED** - derived from the offsets, not read at runtime).

### 8.3 Memory

The cache itself grows from 30 KB to 78 KB, the map from 44 KB to 100 KB: negligible. The real cost is the IGB
payloads that a bigger cache keeps resident (zone group 0xb is freed per zone, but group 1 on-demand loads live
until the menu, SPEC 13). XMen2.exe is a 32-bit non-LAA process (2 GB) with Alchemy memory pools of fixed size
(pool ids passed to 0x5605e0); a zone that lists 400 models will stress those pools before the record cap. Measure
private bytes and pool failures during the tour; the SPEC-13 tile fix (`--tiles used`) should stay in place, the
raise is headroom for NPC packages and long sessions, not a licence to list whole tile folders.

## 9. Risks and unknowns

1. Shared helper 0x490d70: patching in place would corrupt the two other 200-bit users -> clone (7.2 step 3).
2. Name table cap 450 binds immediately (8.1) - the raise is a two-structure job.
3. IModel pool 692 may bind next (8.2) - measure before raising further.
4. **UNVERIFIED**: memory pool 0xe headroom for the bigger name table (sidestepped: xml2-fix builds the table in DLL
   memory, 8.1); any code outside the cache decoding an IGB id with a literal mask (none found); record field
   semantics. (The node/ring "8-byte" detail is resolved in 8.1: two bases, and a 4-byte gap kept as is.)
5. Ids are `int`; `bumpGeneration` uses `jns` (0x56f89b) so a generation field of 32-9 = 23 bits is fine.
6. The getter's `mov eax,0x7b7fb0` (0x56fa2e) is not the only place the game could cache the pointer - the 12
   callers do not store it (section 6), but a caller added by another patch (xml2-fix hooks) must go through the
   getter.
7. If the exe is not the retail build the expected-bytes guards will refuse every patch; the DLL must then leave
   the getter untouched as well (all-or-nothing, like the frame cap patch).

## 10. Test plan

Offline (no game):
- A unit test in xml2-fix that maps XMen2.exe with pefile/capstone (or C++), applies the patch table to a copy of
  the image in memory and re-disassembles the 16 functions: every N-dependent operand must equal the new value,
  every other byte unchanged; the cloned 0x490d70 must contain exactly five 0x200 immediates and no rel32.
- Recompute the section-5 table from the exe with `scratchpad/igb_sites.py` (the capstone script used here) and
  diff against the table checked into the DLL.

In game (short launches, per the display/harness rules in HANDOFF.md):
- Counters: IGB live = dword at **0x7bf39c** (0x7b7fb0 + 0x73ec) in the retail layout, `new_obj + 0x12894` after
  relocation; name table count = `*(int*)(*(int*)0x7ac244 + 0x9404)` (+0x150a0 with 1024 names); IModel live 0x7da28c (UNVERIFIED). Read them
  the way tools/actor_slots.py reads 0x7b79ac and add them to build/tour_slots.
- A: patched DLL, unmodified `build/xml1_tour`: the 12-zone tour and the full 162-zone tour must behave exactly as
  today (regression; counters never exceed 200 / 450 because the content was budgeted for them).
- B: force the old failure: rebuild one zone with `--tiles folder` (hive2_2_4 -> 179 records + resident 51 > 200)
  and enter it from its neighbour; retail bounces back (SPEC 13), the patched game must load it and the IGB
  counter must read > 200 while the name-table count stays < 1024.
- C: long session: the 60-zone sequence of tour v2 followed by mansion/man4/mansion4_1; watch the three counters
  drift (group 1 accumulation) and the private bytes.
- D: exit the game normally after B and C (the patched dtor 0x56e840 runs on the relocated block at exit; a crash
  on exit would point at a missed displacement).

## 11. Commands used

```
python tools/disasm.py xml2-fix/docs/research/XMen2.exe <rva> 0 <len>   # every function above
grep -n -E "0x73ec\]|0x73f0\]|0x7710\]|..." research/scripts/xml2_text.asm         # displacement sweep
grep -n -E "^00(56[ef]|490[de])[0-9a-f]+ .*(0xc8|0xc7)\b" research/scripts/xml2_text.asm
grep -n "call 0x56f9f0" / "call 0x490d70" / "call 0x55af80" / "call 0x55a6a0" ...
python scratchpad/igb_sites.py                                                       # capstone field offsets
RTTI/vtable map: pefile scan for .?AV type descriptors -> complete object locators -> vtables (section 1, 8)
```
