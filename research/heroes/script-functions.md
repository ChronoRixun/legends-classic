# Script functions in XMen2.exe: registration, dispatch, and adding new ones from xml2-fix

Written 2026-09-28 (Opus subagent, read-only research). Goal: let the port force XML1's exact party at the
49 forced-hero missions (roster.md 0.5 and 4) by giving XML2's script language new engine functions
(`seatParty`, ...) through the xml2-fix `dinput.dll` proxy.

Sources read in this session: `research/scripts/xml2_text.asm` (capstone listing), raw bytes of
`xml2-fix/docs/research/XMen2.exe` (retail, base 0x400000, no relocations, file offset = VA - 0x400000
for every section), Ghidra decompiles written for this topic: `research/heroes/decomp_ft_scriptfuncs.c`
(0x49fe30, 0x4d75a0, 0x4d6910, 0x4d8970, 0x4d8b30, 0x4d5830, 0x4d6510, 0x4d6570, 0x4d51c0, handlers 0x4a9300,
0x4a5db0, 0x4a1fb0, 0x4a36f0, 0x49f520, 0x4a7b10, 0x4a3dc0, ctor 0x4d8350, game init 0x46b750, node alloc 0x4d7e60)
and `research/heroes/decomp_ft_scriptparse.c` (parser 0x4d9740, splitter 0x4da450, loader 0x4a11c0, 0x4d86c0,
0x4d6980, 0x4d78a0). Earlier work this builds on: `research/_summaries/scripts.md` (table layout, 320 cap,
case-sensitive lookup), `tools/xml1build/validate_script.py` (offline parser model), `roster.md`, `engine.md`.
Anything not read from code or data is marked **UNVERIFIED**. Nothing here was run in game.

---

## 0. Answers in one table

| question | answer | evidence |
|---|---|---|
| table layout | 16-byte entries `{void* func, char* name, char* ret_sig, char* arg_sig}`, count passed separately (no terminator) | `0x49fe30: push 0x68a908; push 0x121; ... call 0x4d75a0`; entry after the last (0x68bb18) is float data |
| tables | main `0x68a908`, 0x121 = 289 entries; builtins/operators `0x6903d8`, 0x13 = 19 entries; 308 unique names, no duplicates | walk of both tables (this session and `_summaries/scripts.md`) |
| who reads the table | **once, at startup**: `0x4d75a0` copies every entry *pointer* into a red-black tree keyed by the interned name; nothing else references `0x68a908` (single xref at `0x49fe31`) | section 2 |
| lookup structure | RB-tree in a fixed pool of **0x140 = 320 nodes** inside the script-system object; key = string-table handle of the name (case-sensitive: raw-byte hash + `repe cmpsb`) | `0x4d7310`, `0x4d5f70`, `0x5ab7d0`, `0x41a320`, `0x419d0b` |
| free capacity | 320 - 308 = **12 free slots**; a registration beyond 320 is silently skipped (`0x4d7637 cmp [edi+0x1948],0x140; je skip`) | section 2.3 |
| when names are resolved | **at script compile time** (per statement, once per script, then cached); the handler pointer is copied into the statement node (`node+0x28`); execution never looks names up | `0x4d8970` writes `[node+0x28] = entry->func` (0x4d8a9a) |
| signature validated? | yes, at compile only: `argc == strlen(arg_sig)`; per argument `s` needs a string-typed value, `i`/`f` need int or float, every other letter (`a`, `n`, `d`, `w`, ...) accepts anything. Failure = statement freed and **silently dropped** | jump table `0x4d8ad4`/`0x4d8ac4`, `0x4da37a` |
| return signature | used by the parser only: `f`/`i`/`s` type the assigned variable; `w` marks a yielding call (`node+0x34 = 1`); anything else clears the assignment target | parser 0x4d9d42 case 1, `decomp_ft_scriptparse.c:559` |
| handler ABI | `ScriptValue* __cdecl handler(ScriptArgs* args)`; `args->get(i)` = `0x4d5830` (thiscall); value vt+0x14 = as string, vt+0x10 = as int, vt+0xc = as float; return 0 for `n`, else a pool value from `0x4d6570` (int) / `0x4d6510` (float) / `0x4d9430` (string) on `0x4d8770()` | section 4 |
| best way to add functions | **A1: point the two push operands of `0x49fe30` at a DLL-owned copy of the table with up to 12 entries appended** (2 dwords, retail code path, applied in DllMain like `new_game.cpp`). Alternatives: vtable slot, lookup hook (unlimited), repurpose dead entries | section 5 |
| without xml2-fix | an unknown function makes its statement vanish at compile, the rest of the script runs; use a feature-detect variable (section 7.3) | `0x4da511..0x4da536` ignores the parse result |

---

## 1. The tables

| table | VA (file off) | entries | registered by | notes |
|---|---|---|---|---|
| main | `0x68a908` (0x28a908) .. `0x68bb18`, `.rdata` | 0x121 = 289 | `0x49fe30` (push `0x68a908` at 0x49fe30, push `0x121` at 0x49fe35, call `0x4d75a0` at 0x49fe41) | first `setRotZ` (0x4a1cc0 "n" "ai"), last `SetDontShowWarningOff` (0x49fe10 "n" "") |
| builtins | `0x6903d8` (0x2903d8), `.rdata` | 0x13 = 19 | script-system ctor `0x4d8350` (push `0x6903d8` at 0x4d868f, push `0x13` at 0x4d8694, call at 0x4d869e) | `== != < > <= >=` i(aa), `waittimed` w(f), `waitsignal` w(s), `fadd fsub fmul fdiv` f(ff), `iadd isub imul idiv` i(ii), `strcatstr` s(ss), `strcatint` s(si), `strveci` s(iii) |

Entry `{+0 func, +4 name, +8 ret_sig, +0xc arg_sig}`; `arg_sig` may be NULL or `""` (0x681968) for no arguments
(`saveloadOvrWriteOptsAsk` has NULL). Shared signature strings in `.rdata`: `"n"` 0x689c18, `"i"` 0x68ce30,
`"s"` 0x68cde4, `"ss"` 0x68cc38, `"sss"` 0x68c524, `"si"` 0x68c864, `"is"` 0x68bce8, `"ii"` 0x68c468,
`"a"` 0x68ce2c, `"f"` 0x68cc9c. There is **no `"ssss"`** in the exe (a DLL supplies its own).

Signature letters, as the compiler treats them (argument type check at 0x4d8a56-0x4d8a86, value types from vt+0x08:
1 float, 2 int, 3 string):

| letter | as argument | as return |
|---|---|---|
| `s` | value type must be 3 (string literal or string variable) | assigned variable typed string |
| `i`, `f` | value type must be 1 or 2 (int and float are interchangeable) | variable typed int / float |
| `a` (entity), `n`, `d`, `w`, anything else | accepted unchecked (entity names travel as strings and are resolved by the handler, `0x4a1700` + `0x4654b0`) | `n`: no value (assignment dropped); `w`: the statement yields after the call (`node+0x34`) |

Node limits (same for new functions): 7 argument slots (`node+0x8..+0x20`, count `+0x24`; runtime arg array
`args[7]` + count at `+0x1c`). **The parser does not cap the count**: an 8th argument would overwrite `node+0x24`
(no XML2 function takes more than 5). Pools: 620 statement nodes of 0x38 bytes (`0x4d7e60`, cap 0x26c at
`+0x15914`), 1556 values of 12 bytes (`cmp [sys+0xc090],0x614`), 120 compiled scripts (`0x4d86c0`, cap 0x78).

---

## 2. Registration: who reads the table, when

### 2.1 Call chain (all read in this session)

| step | address | what |
|---|---|---|
| 0 | xml2-fix `DllMain` | runs while Windows loads the process, before the exe entry `0x6725f4` (xml2-fix `exports.cpp` comment: static import of libIGDisplay.dll; no TLS callbacks) |
| 1 | `0x4016f0` | app init, slot 0 of vtable `0x67fff4` (object stored at `0x6f3ac4` by `0x401b36` / static init `0x67d980`) |
| 2 | `0x40197b` | `0x46dce0()` (game singleton) -> **game vt+0x13c** = `0x46b750` (game init; vtable `0x686e1c`) |
| 3 | `0x46b7d9..0x46b7e2` | `0x4a1670()` (script interface singleton `0x756a78`, vtable `0x68d36c`) -> **vt+0 = `0x49fe30`** |
| 4 | `0x49fe30` | `push 0x68a908; push 0x121; call 0x4d8770; mov ecx,eax; call 0x4d75a0; ret` (0x17 bytes) |
| 5 | `0x4d8770` | script-system singleton `[0x787740]`; first call allocates 0x3a284 bytes (`0x5605e0`) and runs ctor `0x4d8350`, which inits the tree (`[sys+4] = 0x3fffffff`, pool `0x4d6390`) and registers the 19 builtins |
| 6 | `0x4d75a0(count, table)` | thiscall on the script system; for each entry: intern `name` (`0x602120` strlen, `0x602140` = string table `0xa0a820`, `0x41a320` intern -> handle), search the tree (`0x5ab7d0`); if absent and `[sys+0x1948] != 0x140`, insert (`0x4d7310`) with **value = pointer to the entry** |

Registration is idempotent (a name already present is skipped, first registration wins). `0x4d75a0` has exactly
two callers (0x49fe41, 0x4d869e). No other code reads `0x68a908`, and nothing iterates the table later.

### 2.2 Tree layout (script system `sys` = `[0x787740]`, map at `sys+0`)

| field | offset | from |
|---|---|---|
| root node index (`0x3fffffff` = none) | `sys+0x04` | 0x4d75ea, 0x4d6946 |
| last inserted index | `sys+0x08` | 0x4d732d |
| node i (16 bytes): `+0` parent/colour bits, `+4` left, `+8` right, `+0xc` key (name handle) | `sys+0x0c + 16*i`, i < 0x140 | 0x4d7329-0x4d7340, 0x5ab7e8 |
| free-index ring / cursor / free count / used bitmap (10 dwords) | `sys+0x1410` / `+0x1918` / `+0x191c` / `+0x1920` | allocator `0x4d5f70` (`cmp ecx,0x140`) |
| **used count** (cap 0x140) | `sys+0x1948` | 0x4d5fca, 0x4d7637 |
| value i = `FuncEntry*` | `sys+0x194c + 4*i` | 0x4d738d (write), 0x4d695d (read) |

Keys are string-table handles (`table_id << 24 | bucket`, 8192 buckets, 0x14400 bytes of text, byte-exact
compare at `0x419d0b`), so function names are **case-sensitive**. The table copies each name's text; the entry
itself (and its `func`/`ret`/`args`) is read through the stored pointer at every compile, so **a DLL table must
stay alive for the whole process**.

### 2.3 Capacity

| item | value |
|---|---|
| tree capacity | 0x140 = 320 (`0x4d5fa4`, `0x4d7637`) |
| retail registrations | 19 builtins + 289 main = 308 (all unique) |
| **free** | **12** |
| over capacity | silently skipped, loop continues (`0x4d7641 je 0x4d768f`); the script statements using the lost names are then dropped at compile |

---

## 3. Name resolution: compile time, once per script

| step | address | what |
|---|---|---|
| load | `0x4a11c0(name)` | if the text contains `(` (0x682074) it is inline code (dialog `runscript`, data `actscript`), split on the literal 4 chars `\n\r` (0x68d348); else `"scripts/" + name + ".py"` is read and split on CRLF (0x68d350). Compiled scripts are cached by name (`0x4d6980` lookup, `0x4d71f0` insert) |
| split | `0x4da450` | calls the line parser for each line and **ignores its result** (0x4da517, 0x4da536) |
| parse line | `0x4d9740` | tokenizer: `#` comments; `"`/`'` strings (-> `0x4d9430` string value; `_owner_`/`_activator_` special); numbers (`.` -> float `0x4d6510`, else int `0x4d6570`); bare identifiers -> variables (`0x4d6770`); keywords `if/elif/elseif/else/endif/def/__name__` (`_stricmp`); `=` makes an assignment; `main` is skipped |
| resolve | `0x4d8970(name, node)` at 0x4d9d14 | `0x4d6910(name)` (**only caller 0x4d8981**): intern + tree find -> `FuncEntry*` or 0. Then argc check (`[node+0x24] == strlen(args)`, 0x4d89c3), per-argument type check (section 1), then `[node+0x28] = entry->func`, return `entry->ret` |
| failure | `0x4da37a` | node freed (`0x4d78a0`), line dropped, no message |

Consequences for a DLL:
- Every new name must be in the tree **before the first compile of any script that calls it**. Scripts can compile
  from the first menu onward, so register during startup (section 5: all options act before `0x40197b`).
- Changing an entry's `func` after a script was compiled does not affect that compiled script (the pointer was
  copied into its nodes). When the script cache is flushed is **UNVERIFIED** (zone change is likely).
- A mis-typed call (wrong argc, a number where `s` is required) is dropped exactly like an unknown name.

---

## 4. Runtime dispatch and the handler ABI

### 4.1 The executor (`0x4d8b30`, `decomp_ft_scriptfuncs.c:195`)
For each node from the resume point: if `node+0x28` (handler) is non-null, build an argument list on the stack
(`0x4d6490`), resolving variable arguments to their current value (per-script variable map), then
`result = handler(&args)` (**cdecl, one argument**, `call [ebx+0x28]; add esp,4` at 0x4d8c3f); if the node has an
assignment target, `var->vt+0x18(result)`; if `node+0x34` (ret `w`) the script yields; if `node+0x35` (an `if`)
the branch is taken when `result->vt+0x10() != 1`; finally the result is returned to the value pool if it came
from it (range + bitmap check at `sys+0x5db8` / `sys+0xbfcc`, so a non-pool pointer is simply not freed).

### 4.2 Statement node (0x38 bytes, pool at `sys+0xc714`)
`+0x00` assignment target (8-byte name pair), `+0x08..+0x20` argument values[7], `+0x24` argc, `+0x28` handler,
`+0x2c` next, `+0x30` else-branch, `+0x34` yields (ret `w`), `+0x35` is a condition.

### 4.3 Arguments and return values

| need | how (retail pattern) | address / convention |
|---|---|---|
| argument i | `ScriptValue* v = args->get(i)` | `0x4d5830`, thiscall `ecx = args`, `ret 4`; returns NULL if `i >= count` (`args[7]` at +0, count at +0x1c) |
| as string | `v->vt[5]()` (vt+0x14) | string value: returns the interned `char*` (never NULL for `""`, `unlockCharacter` dereferences it); int/float: formatted and interned (`0x4d8850` / `0x4d87f0`) |
| as int | `v->vt[4]()` (vt+0x10) | int: value; float: ftol; string: `atoi` |
| as float | `v->vt[3]()` (vt+0x0c), result in st0 | int: fild; string: `atof` |
| type | `v->vt[2]()` (vt+0x08) | 1 float (vtable `0x6905d0`), 2 int (`0x6905fc`), 3 string (`0x69078c`) |
| entity argument (`a`) | `h = 0x4a1700(&tmp, v->asString())` (cdecl, 2 args); `ent = 0x4654b0(ecx = h)`; character test = class bit `[0x718448]+0x24` | as in `extractionPointChange` 0x4a7060-0x4a70a1 |
| return nothing (`n`) | `return 0` | `remove` 0x4a9300 |
| return int (`i`) | `return 0x4d6570(ecx = 0x4d8770(), int)` | thiscall, `ret 4`; e.g. `getGameFlag` 0x4a5df6 |
| return float (`f`) | `return 0x4d6510(ecx = 0x4d8770(), float)` | thiscall, `ret 4`; e.g. `getHealth` 0x4a36f0 |
| return string (`s`) | `return 0x4d9430(ecx = 0x4d8770(), const char*)` | thiscall, `ret 4`; copies/interns the text; e.g. `getName` 0x4a1fb0 |

Worked handler (getGameFlag `0x4a5db0`, `i(si)`): `get(0)->vt+0x14` (name), `get(1)->vt+0x10` (bit), script
interface `0x4a1670()->vt+0x54(name, bit)`, `return 0x4d6570(0x4d8770(), result)`.

---

## 5. Adding functions from xml2-fix: options ranked by safety

All four are applied in `DllMain` (before the exe entry point, therefore before step 3 of 2.1), each with a
retail-byte guard in the style of `new_game.cpp` (`readable_and_expected` + `VirtualProtect` write).

| rank | option | patch sites (VA / file offset, section: retail bytes -> new) | limit | risk / notes |
|---|---|---|---|---|
| **1 (recommended)** | **A1. Extended copy of the main table.** DLL keeps `static FuncEntry table[0x121 + N]`, fills it in DllMain with a `memcpy` of the 0x121 retail entries from `0x68a908` followed by its own N entries, and re-points the registration | `0x49fe31` / 0x9fe31, `.text`: `08 a9 68 00` (imm32 of `68` push at 0x49fe30) -> `&table`; `0x49fe36` / 0x9fe36, `.text`: `21 01 00 00` (imm32 of `68` push at 0x49fe35) -> `0x121 + N`. Guards (read only): `0x49fe30` `68 08 a9 68 00 68 21 01 00 00 e8`; cap `0x4d7637` `81 bf 48 19 00 00 40 01 00 00`; builtin count `0x4d8694` `6a 13` | N <= 12 (`static_assert(19 + 0x121 + N <= 0x140)`) | Retail registration code path, retail data untouched, purely additive; new names cannot collide with retail ones (would be skipped). Bonus: the DLL owns the copy, so overriding a retail handler (e.g. make the PC no-op `debug(s)` log to xml2-fix.log) is a plain write to its own memory |
| 2 | A2. Wrap the registration virtual | `0x68d36c` / 0x28d36c, `.rdata`: `30 fe 49 00` (script interface vt+0 = 0x49fe30) -> DLL `void __fastcall reg(void* self, void*)` that calls `0x49fe30(self)` then `0x4d75a0(ecx = 0x4d8770(), N, dll_table)` and logs success by looking each name up with `0x4d6910` | N <= 12 | Same safety as A1, one `.rdata` dword; gives a post-registration hook for logging/verification. Slightly more code in the init path |
| 3 | B. Hook the name lookup | `0x4d8981` / 0xd8981, `.text`: `e8 8a df ff ff` (`call 0x4d6910`) -> `call dll_find`, where `FuncEntry* __fastcall dll_find(void* map, void*, const char* name)` (callee-clean 4 bytes = the original `ret 4`) returns `0x4d6910(map, name)` or, if 0, a match from the DLL table | unlimited | Only call site of `0x4d6910`, so one rel32 covers every compile (files, inline data, `runscript`). Needs its own name matching (exact case, like the engine). More moving parts than A1 but lifts the 12-name cap |
| 4 | C. Repurpose dead entries in place | For an entry at `E` (section 6 table): `E+0` func -> DLL handler, `E+0xc` args -> DLL sig string, optionally `E+4` name -> DLL name (a rename must happen before step 3 of 2.1; func/args can change any time before the first compile) | 25 no-op stubs | Data-only, no code bytes touched, no capacity used. Keeping the retail name makes scripts unreadable (`ToggleMute("magma",...)`); renaming is equivalent to A1 but edits `.rdata`. If the DLL is missing, the retail stub (`0x5aaff0` = `xor eax,eax; ret`) runs: a safe no-op |

Why A1: it changes two immediates in a function that runs once, keeps every retail byte of the table, needs no
new code on the init path, and the failure mode (DLL absent or stale) is "statement dropped". Twelve names are
plenty for the forced-party feature (section 7). If more are ever needed, B lifts the cap without touching A1.

C++ shape of A1 (for xml2-fix; `__thiscall` via `__fastcall` + unused edx, as `limits.cpp` / `options_menu.cpp` do):
```cpp
struct FuncEntry { void* func; const char* name; const char* ret; const char* args; };
constexpr std::uintptr_t retail_table = 0x68a908; constexpr std::uint32_t retail_count = 0x121;
constexpr FuncEntry extra[] = {
    { &seat_party,       "seatParty",       "n", "ssss" },
    { &get_party_member, "getPartyMember",  "s", "i"    },
    { &push_side_mission,"pushSideMission", "n", "a"    },
    { &xml2fix_version,  "xml2fixVersion",  "i", ""     },
};
static_assert(19 + retail_count + std::size(extra) <= 0x140, "script function tree holds 320 names");
FuncEntry table[retail_count + std::size(extra)];           // static: the tree keeps pointers into it
// DllMain: guard bytes at 0x49fe30 / 0x4d7637 / 0x4d8694, memcpy(table, (void*)retail_table, 0x121 * 16),
// copy `extra` after it, write(0x49fe31, (uint32)table), write(0x49fe36, 0x121 + size(extra)).

using get_arg_t   = void*(__fastcall*)(void* args, void*, int i);            // 0x4d5830
using sys_t       = void*(__cdecl*)();                                       // 0x4d8770
using make_int_t  = void*(__fastcall*)(void* sys, void*, int v);             // 0x4d6570
using make_str_t  = void*(__fastcall*)(void* sys, void*, const char* s);     // 0x4d9430
using as_str_t    = const char*(__fastcall*)(void* value, void*);            // value vtable +0x14
using as_int_t    = int(__fastcall*)(void* value, void*);                    // value vtable +0x10
void* __cdecl seat_party(void* args);                                        // handler: returns 0 ('n')
```

---

## 6. Registered functions that no script uses (repurpose candidates / proof of spare names)

Census (this session): exact-case regex `\bname\s*\(` for all 289 main-table names over the XML2 retail tree
(`<XML2 folder>`: Scripts, Conversations, Data, Dialogs, UI, HUD, Maps, Packages, Effects, Automaps,
MotionPaths, Subtitles, Actors; 8023 non-IGB/media files), the port build (`build/_heroes`, same folders,
13238 files) and the raw bytes of XMen2.exe (its own `runscript ...` strings and printf formats). 191 names are
used by XML2 data, 206 by the port tree. **44 names are used nowhere**; 25 of them are PC no-op stubs.

No-op stubs (handler `0x5aaff0` = `33 c0 c3`, i.e. `return 0`): every field below is the retail dword at that address.

| # | entry VA (`+0` func, `+4` name, `+0xc` args) | name | sig | name ptr | args ptr |
|---|---|---|---|---|---|
| 113 | 0x68b018 | wanderNextZoneLink | n() | 0x68c75c | 0x681968 |
| 114 | 0x68b028 | causeTroubleForAutotest | n() | 0x68c744 | 0x681968 |
| 179 | 0x68b438 | saveloadDefaultCheck | n() | 0x68c2e0 | 0x681968 |
| 180 | 0x68b448 | saveloadDefaultCheck2 | n() | 0x68c2c8 | 0x681968 |
| 181 | 0x68b458 | saveloadBootDeleteCorrupt | n() | 0x68c2ac | 0x681968 |
| 231 | 0x68b778 | loadNetworkConfig | n(i) | 0x68bf1c | 0x68ce30 |
| 250 | 0x68b8a8 | bootToDash | n(i) | 0x68bdec | 0x68ce30 |
| 251 | 0x68b8b8 | titleUpdate | n() | 0x68bde0 | 0x681968 |
| 252 | 0x68b8c8 | ToggleMute | n(ii) | 0x68bdd4 | 0x68c468 |
| 253 | 0x68b8d8 | SendFriendRequest | n(si) | 0x68bdc0 | 0x68c864 |
| 254 | 0x68b8e8 | AnswerFriendRequest | n(ii) | 0x68bdac | 0x68c468 |
| 255 | 0x68b8f8 | RemoveFriend | n(i) | 0x68bd9c | 0x68ce30 |
| 256 | 0x68b908 | SendGameInvite | n(ii) | 0x68bd8c | 0x68c468 |
| 257 | 0x68b918 | AnswerGameInvite | n(ii) | 0x68bd78 | 0x68c468 |
| 258 | 0x68b928 | CancelGameInvite | n(i) | 0x68bd64 | 0x68ce30 |
| 259 | 0x68b938 | SendFeedback | n(iis) | 0x68bd54 | 0x68bd50 |
| 260 | 0x68b948 | LaunchFriendReqVoiceMenu | n(s) | 0x68bd34 | 0x68cde4 |
| 261 | 0x68b958 | LaunchGameInviteVoiceMenu | n(i) | 0x68bd18 | 0x68ce30 |
| 262 | 0x68b968 | LaunchReceiveVoiceMenu | n(i) | 0x68bd00 | 0x68ce30 |
| 263 | 0x68b978 | LaunchFeedbackMenu | n(is) | 0x68bcec | 0x68bce8 |
| 264 | 0x68b988 | JoinFriendsGame | n(i) | 0x68bcd8 | 0x68ce30 |
| 267 | 0x68b9b8 | SetNumInvites | n(i) | 0x68bcb0 | 0x68ce30 |
| 270 | 0x68b9e8 | SendFriendVoiceAttachmentPrompt | n(s) | 0x68bc6c | 0x68cde4 |
| 271 | 0x68b9f8 | SendVoiceAttachmentPrompt | n(ss) | 0x68bc50 | 0x68cc38 |
| 272 | 0x68ba08 | InviteConfirmation | n(s) | 0x68bc3c | 0x68cde4 |

All 25 share ret `"n"` (0x689c18). `debug` and `display` also point at `0x5aaff0` but are used everywhere (the
port emits `debug("x1: removed statement")`), so they are not candidates for reuse, only for an optional
"log to xml2-fix.log" override.

Unused but with real handlers (do not repurpose without reading the handler): `setTeamInvisible` n(ss) 0x4a04d0,
`allowResponseOnGameVarCount` n(si) 0x4a5d50, `setGoal` n(a) 0x4a63f0, `initHud` n() 0x49e6b0, `hudMessage`
n(ifs) 0x49eb60, `setDangerRoomFailed` n() 0x49eca0, `controllersContinue` n() 0x49ef00,
`saveloadOvrWriteOptsAsk` n() 0x49f0e0, `saveloadNoSpaceWarning` n(i) 0x49f040, `saveloadSaveConfirmed` n(i)
0x49f170, `beginMissionHack` n(s) 0x4a0b60, `startMoviePreview` i(ss) 0x49f730, `loadMapAddTeam` n(s) 0x4a0bd0
(sends `resetgame`!), `setPartyLightRadiusScale` n(f) 0x49e950, `LogoutNoExit` n() 0x49f990, `AreYouSure`
n(isss) 0x4a0f90, `closemenu` n(s) 0x4a0f20, `setupHost` n() 0x49faa0, `cancelWaitingDialog` n() 0x49fc10.

Used only by the exe itself (its own `runscript` strings; **never touch**): `KickPlayer`, `Logout`,
`ReNegotiate`, `SetDontShowWarningOff`, `SetGameType`, `SetMaxPlayers`, `SetPrefDifficulty`, `SetPrefGameType`,
`closeDangerRoom`, `confirmKickPlayerDialog`, `dangerRoomEndMission`, `kickPlayerDialog`, `mainMenuExitDialog`,
`openWaitingDialog`, `restartZone`, `restorelastzone`, 15 `saveload*`, `setAutoEquip`, `setAutoSpend`,
`setDifficultyLevel`, `startFirstMission`, `startGameDiffDialog`, `useDefaultStats`, `useSavedStats`,
`viewSparringHighScores`.

---

## 7. Proposed functions for the forced-party feature

### 7.1 Definitions

| name / sig | handler recipe (every call below was read in this session) | retail precedent | open points |
|---|---|---|---|
| `seatParty(h1,h2,h3,h4)` n(ssss) | 1) validate: for each non-empty name `idx = registry->vt+0x3c(name)` (`0x44b8f0()`, `0x44acc0`, lowercases, 0 = unknown) and `registry->vt+0x7c(idx)` (`0x44b7c0`, flag bit0 = herostat entry); if any fails, log and change nothing (a non-herostat name spawns with fallback stats, engine.md 2.1). 2) for slot 0..3: `h = name[0] ? 0x41a320(ecx = 0x602140(), name, strlen+1, 0) : 0` (thiscall, `ret 0xc`); `game = 0x46dce0()`; `game->vt+0xf0(slot, &h)` (`0x46c810`, thiscall, `ret 8`; lowercases, handle 0 = empty slot). The script then loads the zone with `loadMapKeepTeam(zone)` so `0x486dd0` spawns the new party | `startFirstMission` `0x4a7b10` (4x vt+0xf0 then `runscript menus/new_game` -> `loadMapKeepTeam`); `restorelastzone` `0x5f4612-0x5f46a6` (4x vt+0xf0 with handle 0 for empty, then `loadmap %s 1`) | in-game behaviour of a 1-hero party (HUD, co-op player count) **UNVERIFIED**; `restorelastzone` also calls game vt+0x204 (`0x46d440`, copies a 0xdc-byte state block `game+0x618 -> game+0x53c`, purpose **UNVERIFIED**) and `startFirstMission` does not |
| `getPartyMember(i)` s(i) | `p = game->vt+0xe0(i)` (`0x46c510`, returns `&game+0x14+4i`); `*p == 0` -> `""`, else text = `[0x602140() + 4 + (h & 0xffffff)*4] + 0x8008 + table` (as `0x46c810` resolves it); `return 0x4d9430(0x4d8770(), text)` | slot read in `0x46c810` | lets scripts test/save the party (`isActorOnTeam` only answers yes/no) |
| `pushSideMission(a)` n(a) | resolve `a` to a character entity (as `0x4a7060-0x4a70a1`), `snprintf(buf, 0x100, "pushsidemission %d", ent+0x1c)` (`0x5604f0`, fmt `0x68d584`), `0x55c890()->vt+0x18(buf)` (console queue) | first half of `extractionPointChange` `0x4a7020` (without the blackbird parms and team menu) | Saves zone + 4 team names + position (roster 2.4); `restorelastzone("0")` (registered, `0x4a0760`) restores all three = XML1 `endSideMission`. Max 2 records; console queue holds 2 pending commands, 127 chars. Whether the record survives save/load **UNVERIFIED** |
| `xml2fixVersion()` i() | `return 0x4d6570(0x4d8770(), FIX_SCRIPT_API)` | - | feature detect (7.3) |
| `setPartySkin(slot, costume)` (not specified) | needs the "current costume" setter; engine.md 3.x only identified the reader (`0x4b8090`, "current costume skin") and the costume-name table `0x6d8aa0` | - | **open**; interim: per-zone `setSkin(ent, skin)` (`0x4a3dc0`) after spawn, persistence across zone loads **UNVERIFIED** |

The party slots can also be set through the pending array (game vt+0xf8 = `&game+0x28+4i` at `0x46a410`,
vt+0xfc = set pending at `0x46c940`), which `0x486e60` (called from `0x484f59`) copies into the slots at the next
zone load when non-zero. That would defer the write to load time, but who else sets pending names is not traced
(**UNVERIFIED**); the direct vt+0xf0 write has two retail precedents and is the recommended path.

### 7.2 Mission patterns (port output)

| XML1 case | proposed script |
|---|---|
| Magma solo hub (mansion1..8), Phoenix brig, Wolverine rooftops, Cyclops old_wx, 1/1 and 2/2 missions | `seatParty("magma", "", "", "" )` then `loadMapKeepTeam("<zone>" )` in the begin body (replaces today's `loadMapChooseTeam`) |
| flashback / side mission (jug_fb, sent_fb, wx_fb_start, dr_mag1/2, astral_sk) | `pushSideMission("_ACTIVE_HERO_" )`, `seatParty(...)`, `loadMapKeepTeam(<flashback zone>)`; XML1 `endSideMission` -> `restorelastzone("0" )` (back to the saved zone, position and party) |
| astral trio (ProfXAstral + Phoenix + Frost) | `seatParty("profxastral", "phoenix", "frost", "" )`; ProfXAstral must be a herostat entry (flag bit0) or the validation refuses the call |
| `addHero("cyclops")` mid-zone (nyc1_1_3, mag_nyc4) | `p0 = getPartyMember(0 )` (string variable, typed by ret `s`) then `seatParty(p0, "cyclops", "", "" )` + `loadMapKeepTeam(<current zone>)` (reloads the zone; spawn point/position handling **UNVERIFIED**) |
| `removeFromGroup("phoenix")` (reallyendmuir3) | `seatParty` with the remaining names before the next `loadMapKeepTeam` |

### 7.3 Feature detection (script works with or without the DLL)
Retail idiom for declaring a typed variable (`act1/codes_convo_1.py`: `codes = iadd(0, 0 )`) plus the fact that a
call to an unregistered name is dropped at compile:
```
x1fx = iadd(0, 0 )
x1fx = xml2fixVersion( )
if x1fx >= 1
     seatParty("magma", "", "", "" )
     loadMapKeepTeam("mansion/man1a/mansion1a_1" )
else
     loadMapChooseTeam("mansion/man1a/mansion1a_1" )
endif
```
Without the DLL the second line disappears and `x1fx` stays 0 (declared by `iadd`), so the `if` still compiles.
Do **not** rely on an undeclared variable: an unknown identifier drops the argument, `>=` then fails its argc
check and the `if` line itself is dropped. The zero-argument assignment form is retail
(`reset = getZoneReset( )`, `conv = getConversationActive( )` in XML2's own scripts).

### 7.4 Pipeline follow-ups (not done here)
- `validate_script.ScriptChecker` takes `ctx.xml2_api` (`research/scripts/xml2_api.json`); the new names need an
  extension API file (e.g. `research/scripts/xml2fix_api.json`, versioned with `xml2fixVersion`) merged in, or
  every `seatParty` line is reported as "unknown function".
- `scripts_transform.choose_team_in_bodies` is the place that today turns the 49 forced bodies into
  `loadMapChooseTeam`; it would emit the 7.3 block instead, using `required`/`maxheros` from `mission_plan.json`.

---

## 8. Patch-site summary (for xml2-fix)

| site | VA | file off | section | retail bytes | write | when |
|---|---|---|---|---|---|---|
| A1 table pointer | 0x49fe31 | 0x9fe31 | .text | `08 a9 68 00` (after opcode `68` at 0x49fe30) | DLL table address | DllMain (before 0x40197b) |
| A1 count | 0x49fe36 | 0x9fe36 | .text | `21 01 00 00` (after opcode `68` at 0x49fe35) | `0x121 + N`, N <= 12 | DllMain |
| guard: tree cap | 0x4d7637 | 0xd7637 | .text | `81 bf 48 19 00 00 40 01 00 00` | read only | DllMain |
| guard: builtin count | 0x4d8694 | 0xd8694 | .text | `6a 13` | read only | DllMain |
| A2 alternative | 0x68d36c | 0x28d36c | .rdata | `30 fe 49 00` | DLL wrapper | DllMain |
| B alternative | 0x4d8981 | 0xd8981 | .text | `e8 8a df ff ff` | `e8 <rel32 to DLL find>` | DllMain (before the first script compile) |
| C alternative | entry+0 / +4 / +0xc (section 6) | VA - 0x400000 | .rdata | as tabled | DLL func / name / sig | DllMain (a rename before 0x40197b) |

---

## 9. Open questions

1. Does the retail game behave with a 1- or 2-hero party set by `seatParty` + `loadMapKeepTeam` (HUD portraits,
   hero-switch, extraction menu, co-op players beyond the party size)? Code precedent exists (team menu confirm only
   requires slot 0), in-game **UNVERIFIED** (same open item as roster.md 2.3).
2. Is the side-mission record stack (`pushsidemission`) and the pending-name array saved in savegames? Decides
   whether a flashback can be saved mid-way.
3. Which engine call sets a hero's *current* costume (needed for `setPartySkin`: 60s / 70s / weaponx / civilian /
   magmacivilian skinsets)? Only the reader (`0x4b8090`) and the costume table (`0x6d8aa0`) are known (engine.md).
4. When is the compiled-script cache (`0x4d6980` / `0x4d71f0`, 120 objects) flushed? Only matters for option C
   changes after startup.
5. Headroom of the global string table (0x14400 bytes at `0xa0a820`) was not measured; new names add a few bytes.
