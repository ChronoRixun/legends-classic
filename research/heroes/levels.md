# Hero levels and XP: why the roster jumped to level 40 (XMen2.exe vs XML1)

Question (2026-09-28): after ProfXGladiator (herostat `level="40" xpexempt="true"`) played astral_sk, every hero
seated afterwards showed level 40 in the HUD (Wolverine, Magma, Rogue). Is there an XMen2.exe "catch-up" rule that
raises benched / newly seated heroes to a reference level and counts the fixed-level guests?

Sources: `docs/research/XMen2.exe` (xml2-fix) via `tools/disasm.py`, `research/scripts/xml2_text.asm`, a raw byte scan
of every `E8`/`E9` call and every `FF 9x disp32` virtual call in `.text`, Ghidra decompiles
`research/heroes/decomp_lvl1.c` .. `decomp_lvl5.c` (not committed, regenerate with DecompAt.java), XML1's
`xml1_xbox/default.xbe` (`research/scripts/xml1_text.asm`, `binimg.py`) and XML1's `data/missions/*.eng`
(`xml1_xbox/z/assetsfb.zip`). Walk evidence: `build/walk1/shots/` + `build/walk1.log` (2026-09-28 13:35-14:38).

## 1. Answer

**There is no catch-up rule in XMen2.exe, and the guests are not the cause.** The 40 is XP:

1. `astral/savepx/xcrystal_destroyed.py` (the astral_sk side mission's entry; the walk ran it at 14:29:48) completes two
   act-9 objectives: `objective("release","EOBJCMD_COMPLETE")` (`xp="500000"`) and `objective("rescue",...)`
   (`xp="1500000"`) - XML1's own values (`data/missions/astral3.eng`, `astral_sk.eng` in assetsfb.zip; the port copies
   them into `Data/missions/x1_act09`).
2. XMen2.exe gives an objective's XP to **the whole roster**: objective state change `0x488720` -> on a fresh
   COMPLETE with `xp > 0` -> registry `vt+0xd4` = `0x449fe0(xp * (difficulty>=2 ? 2.5 : 1), 1)` (`0x48882e-0x48884c`)
   -> every loaded herostat hero with `team="hero"`, in the party or not, gets `+xp` (`0x4b79b0`), then its level is
   recomputed (`0x4b7d10`, or `0x421610` for a spawned actor). XML1 does the same (`xbe 0x55180`).
3. `0x4b79b0` returns without adding anything when CStats+0x2ad bit 0x20 (herostat `xpexempt`, parsed at
   `0x4bad04`) is set, so ProfXAstral / ProfXGladiator never gain XP.
4. On XMen2.exe's XP curve (below) 2,000,000 XP is **exactly level 40**: T2(40) = 1,988,935 <= 2,000,000 < T2(41) =
   2,124,300. Heroes at level 1 (XP < 2,960) all land on 40. That this equals the guests' fixed level is a coincidence.
   On XML1's curve the same 2,000,000 XP is level 26.

Walk evidence (HUD crops, bottom-left number): 071 astral3 Magma **1** -> 072 astral_sk ProfXGladiator 40 -> 073
asteroid_rock Wolverine **40** (health bar short: max health rose, current did not), 076 asteroid_mm 40. astral1 had
ProfXAstral (40) in the party but its only objective (`illyana`) has `xp="0"`: 040 astral1b Phoenix **1**, and the
active heroes of 041..071 all show **1**. So a level-40 guest in the party raises nobody; the act-9 objectives do.

The real problem is bigger than astral_sk: **the port runs XML1's XP amounts on XML2's XP curve.** Objective XP
alone (no kills) takes heroes to XML2 level 57 after act 8 and 92 after act 9 (XML1: 29 and 34, section 5).

## 2. Every way XMen2.exe changes a hero's level (exhaustive)

The level is the byte CStats+0x1c (HUD: active entity `+0x35c` -> `0x4b87c0` at `0x5a4024`). Writers of that byte:
`0x4b7d10` (recompute from XP, clamps 99), `0x4ba1f9` (herostat/npcstat parse, non-heroes only; heroes get
XP = T(level) at `0x4ba1c7-0x4ba1ed`), and the save/load block copy (`0x4b7e50`/`0x4b7eb0`, `0x43a520`/`0x43a550`).
XP (CStatsHero+0x38, object CStats+0xc0, vtable `0x685294`, get vt+0xc / set vt+0x10) is only changed by
`0x4b79b0` (add) and `0x4b7a60` (subtract). Their callers (byte scan, all of `.text`):

| path | callers | what it is |
|---|---|---|
| `0x4b79b0` add XP | `0x422377` (`0x422350` actor add XP: kill share, `setXP` script `0x4a8660`, reward menu `0x5d2e2e`), `0x44a05a` (`0x449fe0` roster award), `0x44bd84` (`0x44bcf0` NPC level +50 at difficulty >= 2), `0x44bfb9` (`0x44be40` level-up-by-N), `0x4ba1ed`/`0x4ba239` (herostat `level`/`experience` at boot), `0x5d2e1c` (reward menu "level up") | |
| `0x449fe0` roster award (registry vt+0xd4) | `0x48884c` objective COMPLETE (flag 1), `0x49d9f1` `awardXPToPlayable` (flag 1), `0x4a799c` `dataDiscReward` 2500, `0x4c8fc7` Danger Room course reward (`rewardxp` of the REWARD tier; skipped when 0), `0x5d0bd8`/`0x5e7b71` menu rewards, `0x4371bc` kill share to the bench (flag 0, **at most 1 XP**: `0x437199-0x4371ab` = min(xp*0.4, 1)) | the "benched heroes aren't punished" design is here: story XP goes to everyone |
| `0x44be40` level-up-by-N (vt+0xdc) | `0x448b88` (`0x448b10` set-level, vt+0xe4), `0x46a16a` (game vt+0x270 `0x46a100`: difficulty 2 -> every hero to 45), `0x4c913a`/`0x4c91ab` (Danger Room reward `rewardlevel`, +1), `0x5db47e` (cheat: all to 99) | |
| `0x448b10` set level (vt+0xe4) | `0x41c91f` (class attr `character`: level = CMap vt+0x2c `0x483ec0` = 30/1 in Danger Room modes 0xfe/0xfd, else -1 = no change), `0x4d09e2`/`0x4d0aa0`/`0x4d0b11` (Danger Room), `0x449fbb` (inside `0x449f50` = vt+0xe8 "all non-exempt heroes to L": **no caller**) | |

Registry `vt+0xa8`/`vt+0xac` (hero record snapshot/restore, `0x449b40`/`0x449ba0`): snapshot only at boot
(`0x44baf1`), restore never called. Nothing reads one hero's level and writes it into another.

## 3. xpexempt and the "reference levels" XMen2.exe keeps

xpexempt = CStats+0x2ad bit 0x20. Readers: `0x4b79b0`/`0x4b7a60` (no XP gain/loss), `0x4b7e0e` (no "highest level"
notify), `0x4b7b00`/`0x4bbae0` (no skill points / autospend), `0x449960` (max level), `0x449f50`, `0x46d098`
(HUD "points to spend" flag), `0x59bebb`/`0x5a3fe1`/`0x5db979`/`0x5e5772`/`0x5e5c3e` (skill UI).

| reference | where | counts guests? | used for |
|---|---|---|---|
| highest hero level | registry vt+0x50 `0x449960` | **no** (skips bit 0x20) | shop/loot tiers (`0x46a340`, `0x47b35a`, `0x480d10`, `0x481b80`, `0x5a9b00`, `0x5d3720`), `<require>` (`0x4ad034`) |
| highest level reached (stored) | unlock mgr (`0x48fed0`, vtable `0x689994`) +0x228; set vt+0x2c `0x48f280` from `0x4b7e38`, read vt+0x3c | **no** (`0x4b7e0e`) | Danger Room menu gate (>= 6, `0x5c98ec`), a menu value (`0x5b6c7a`); never raises a hero |
| party average level | kill XP `0x44a9f0` (registry vt+0xcc) | yes | kill XP multiplier max(30, 100 - 10*|avg - enemy|)%. A level-40 guest lowers kill XP for a low party - minor, and XML1 did the same |

So no data or exe change is needed for the guests: they neither gain XP nor feed any value that raises other heroes.
A `[Game] GuestLevels` switch would have nothing to change.

## 4. The XP curves

**XMen2.exe** (`0x448a90`, table `0x717720`, built once, flag byte `0x7178b4`): T2(1) = 0,
T2(n) = T2(n-1) + (730 + 65*(n-2))*n + 1500 for n = 2..99, T2(100) = 0x7fffffff; max level 99 (`0x44b690`), max XP
T2(99)+1 (`0x44b6d0`). Kill XP for an enemy of level L: (20L + 80) * party multiplier (`0x44a9f0`); npcstat `xpaward`
overrides it (`0x43712d`); the bench gets at most 1 XP per kill.

**XML1** (`xbe 0x541e0`): T1(1) = 0, T1(n) = T1(n-1) + 5*(n+8)*f(n-1) for n = 2..45, T1(46) = 0x7fffffff;
f(L) = int(2.5 * (4/3)^(L-1)) (`0x54800`, constants `0x3cb710` = 4/3, `0x3c8c98` = 2.5); max level 45 (`0x56c80`).
Kill XP = f(enemy level) or the NPC's xpaward (`0x45f63`-`0x45f8f`); the bench gets xp/2 per kill (`0x45f93`-`0x45fb0`),
each party hero 3*(xp/2+1) plus a bonus (`0x46149`-`0x4615b`). (Section 8: the xp/2 goes to the party too - XML1's
roster award adds it whatever its flag - and f(40) is 186,444, not 186,445.) XML1's `awardXPToPlayable`/`setXP` work
like XML2's (roster award / add to the named actors, `0xa0280`).

| level | XML1 T1 | XML2 T2 | XML1 kill XP f(L) | XML2 kill XP 20L+80 |
|---|---|---|---|---|
| 5 | 830 | 17,910 | 7 | 180 |
| 10 | 6,880 | 70,860 | 33 | 280 |
| 20 | 220,650 | 340,385 | 591 | 480 |
| 26 | 1,543,300 | 650,500 | 3,322 | 600 |
| 30 | 5,510,355 | 936,410 | 10,499 | 680 |
| 35 | 26,544,400 | 1,397,485 | 44,244 | 780 |
| 40 | 125,847,705 | 1,988,935 | 186,444 | 880 |

XML1's curve is exponential; XML2's is roughly cubic. The same XP means very different levels above ~20.

## 5. Objective XP per act (port = XML1 values), objectives only, no kills

| act | XML1 objective XP | cumulative | XML1 level | XML2 level |
|---|---|---|---|---|
| 1 | 1,600 | 1,600 | 6 | 1 |
| 3 | 10,000 | 11,600 | 11 | 3 |
| 5 | 145,000 | 156,600 | 18 | 14 |
| 7 | 555,000 | 711,600 | 23 | 26 |
| 8 | 4,700,000 | 5,411,600 | 29 | 57 |
| 9 | 15,000,000 | 20,411,600 | 34 | 92 |

Also XML1-scaled: `awardXPToPlayable` literals in the converted scripts (2,000..40,000), `setXP("_HERO1_"..4, 1125000)`
in `asteroid_m/end_goons_defeated.py` (XML1: ~T1(25) - a top-up; XML2: +32 levels), npcstat `xpaward` (30..500).
XML1's XP pickups carry their amount in the entity's `count` (300000 in hive2_2_4, 30000 in wx2_1) and give it to the
hero who picks them up (SPEC 23.1).

## 6. Fix

Nothing to patch for the guests (section 3). What must change is the XP economy, and that is a design choice:

**A. (recommended, faithful; BUILT - section 8) XML1's XP economy in the exe for XML1 builds** - xml2-fix `[Game] XPCurve=xml1`,
harness writes it for XML1 builds. All XML1 numbers (objectives, scripts, xpaward, NPC levels, talent `<require
cat="level">` ranks) then mean what they meant in XML1, and the bench keeps up the XML1 way. Sites, all retail-guarded:
- level table: write T1 into `0x717720` (index 0 = -1, 1..45 = T1, 46..100 = 0x7fffffff) and set `0x7178b4` = 1
  before the first call (DllMain; both are zero-initialised `.data`), so `0x448a90` never builds XML2's table;
- max level 99 (imm 0x63) -> 45, instruction addresses: `0x44b690` `mov eax,0x63` (vt+0xc8), `0x44b6d0`
  `push 0x63` (vt+0xc4 max XP), `0x4b7d69` `cmp eax,0x63` + `0x4b7d6e` `mov eax,0x63` (recompute clamp),
  `0x44bec3`/`0x44bed7`/`0x44bee7`/`0x44befc` (level-up-by-N), `0x5a9db1` `cmp ax,0x63` (menu), `0x5db45f` (cheat);
- kill XP: registry vt+0xcc `0x44a9f0` -> f(L) (XML1 applies no party-average multiplier at this point; its own
  bonus is `xbe 0x4604d-0x460dd` - read it before dropping XML2's), bench share `0x437199-0x4371ab`
  (`fmul [0x684100]` = 0.4, `cmp edi,1` cap) -> xp/2, party share after `0x4371c2` (read the loop) -> 3*(xp/2+1);
- difficulty 2 start level 45 (`0x46a15f` `mov ecx,0x2d`) and the NPC +50 (`0x44bd4e` `add ebx,0x32`) only matter
  at difficulty 2.
Offline tests: table values, guards; in-game: a kill/objective/level sweep. Effort: about a day with the in-game pass.

**B. (data only, approximate) keep XML2's curve, convert XML1 amounts in the pipeline** by level equivalence
g(x) = T2(L1(x)) along the campaign (objectives only; per act the factor runs from 17.9x in act 1 to 0.025x in act 9).
Kills stay XML2's (bench 1 XP), talent ranks would unlock at XML2-paced levels, and scripts' literal awards need the
same treatment by act. Simpler, but the numbers only approximate XML1.

Until one of these lands, any act-8/9 objective (and asteroid_m's setXP) will spike the roster.

## 7. In-game tests (harness, xml2-fix test pipe)

Use a build where heroes are at level 1; read the number next to the health bar (bottom-left HUD crop).

1. Roster award, no catch-up: in any zone with Magma in the party:
   `python tools/fixinput.py script 'awardXPToPlayable(2000000)'` -> Magma shows 40 on the next frame. Then
   `script 'seatParty("rogue","","","")'` + `script 'loadMapKeepTeam("<same zone>")'` -> Rogue (never in a party)
   shows 40. Seat `profxastral` -> still 40 (xpexempt: no XP). `awardXPToPlayable(500000)` on fresh heroes -> 23.
2. A guest alone raises nobody (the case that was suspected): fresh heroes,
   `script 'seatParty("profxgladiator","","","")'`, `script 'loadMapKeepTeam("astral/savepx/final_astral")'`,
   wait for the zone, `script 'seatParty("magma","","","")'`, `script 'loadMapKeepTeam("astral/savepx/astral2_3")'`
   -> Magma shows **1** (no objective ran).
3. The walk's case: `script 'setCurrentAct(9)'`, then `python tools/fixinput.py console runscript
   astral/savepx/xcrystal_destroyed` -> "+500000"/"+1500000" XP popups, after the loads every non-exempt hero shows
   **40** (with fix A: 26).

## 8. Built: option A, xml2-fix `[Game] XPCurve=xml1` (xml2-fix 791964d, 2026-09-28)

`src/xp_curve_rules.hpp` (xml2-fix) has every address, guard and byte; `src/xp_curve.cpp` patches from DllMain (before
the herostat load's first `0x448a90` call), all or nothing after 14 retail-byte guards: 19 sites, 51 bytes. Port side
(SPEC 23): `tools/harness.py` writes the key for every build_xml1.py build, `tools/power_sweep.py` levels heroes on the
table the build's ini names, `tools/hero_xp.py` reads every hero's level and XP from the running game.

| what | sites | XML2 | with `XPCurve=xml1` |
|---|---|---|---|
| level table | `0x448afa` (bound), `0x448b00` (disp32) | `0x717720`, 0 < n < 101 | the DLL's copy of T1 (47 entries, index 0 = -1, 46 = 0x7fffffff), 0 < n < 47; XML2's builder still fills `0x717720`, which nothing reads |
| cap | `0x44b691` (vt+0xc8), `0x44b6d1` (vt+0xc4 = T(cap)+1), `0x4b7d6b`/`0x4b7d6f` (recompute clamp), `0x44bec4`/`0x44bed9`/`0x44bee8`/`0x44befd` (level-up-by-N), `0x5a9db3` (shop level-up item), `0x5db460` (cheat) | 99 | 45; most XP 589,254,821 |
| kill XP | `0x44a9f0` (vt+0xcc) | (20L + 80) x max(30, 100 - 10 abs(avg - L)) % | `jmp` to the DLL: f(L), L capped at 45 (XML1's enemies are 0..40; f overflows XML1's int from 73) |
| split | `0x437199` (23 bytes), `0x4371b8` (flag), `0x4373d1` (`fld` -> `fild`) | bench min(trunc(0.4 xp), 1); party xp x factor | every hero xp/2 (roster award flag 1: the party too); each party hero + 3 (xp/2 + 1) x factor |
| AI teammate factor | `0x43739e`, `0x4373c7`, `0x4373cd` (float operands -> the DLL's) | 0.4 + 0.6 (1 - d^2/90000); 0.4 from 300 units | 1/3 + 2/3 (1 - d^2/90000); 0 from 300 units |

Corrections to sections 4 and 6 found while building it:
- **f(40) = 186,444** (2.5 x (4/3)^39 = 186,444.998, truncated). The only value that depends on the x87 precision: at
  24 bits the multiply would round it to 186,445 and T1(41..45) would be 245 higher. XML1's code never changes the
  default 53-bit precision (the CRT pow `0x341990` forces 0x27f itself; ftol `0x3439c4` only sets truncation), so the
  DLL has 186,444 and T1(45) = 589,254,820. Every other f(L) is at least 0.047 from a whole number.
- **XML1's kill half goes to every hero, the party included**: XML1's roster award (`0x55180`) adds the XP whatever
  its flag (the flag only picks the actor's level-up path); XML2's (`0x449fe0`) skips the heroes in the zone at flag 0.
  So an XML1 party hero gets xp/2 + 3 (xp/2 + 1) (about twice the kill) plus the victim bonus, the bench xp/2.
- XML1's AI teammate that didn't kill: (1 - d^2/90000)(bonus + 2 (half + 1)) + (half + 1), nothing from 300 units;
  the patched XML2 gives 3 (half + 1) x (1/3 + 2/3 (1 - d^2/90000)) = the same without the bonus (within a unit, the
  floats), and adds the victim bonus unscaled.

Decided, left as XMen2.exe has it (why):
- Danger Room: the fixed level 30 (1 in one versus mode; `0x483ec0`, `0x4d0a9b`, `0x4d0b0c`) is within the cap and,
  like XML2's 30 of 99, a late-campaign level on XML1's curve (objectives alone end XML1's campaign at 34). XML1's
  registry has no set-level slot (its vtable ends at `0x55bc0`), so XML1's Danger Room played the heroes' own levels;
  the port uses XML2's Danger Room machinery (SPEC 21.3) and keeps its balancing.
- Hard (difficulty 2; unlocked only by XML2's `apoc_death.py`, and the port's profile is its own): heroes start at 45 =
  XML1's cap; the NPCs' +50 levels (clamp 99, `0x44bd4e`) stay, as the NPC stat formulas at Hard use level - 50
  (`0x4b88e6`); the kill XP caps L at 45. The cheat: every hero to the cap, 45.
- A downed party hero still gets nothing for a kill (XML1 gave it the full share); the victim bonus (`+0x6b0`), the XP
  boosts, the victim flags' x2 / x3 (`+0x3db`; XML1's npcstat has no leaderskin / mutantskin) and the Danger Room's
  halving stay XML2's. The loot level range max + 20 (`0x5d3800`) becomes 65; the talent data's 0..99 range
  (`0x4c05d9`, `0x5efdb2`) is not the hero cap.
- Saves keep the level byte; the recompute (`0x4b7d10`) walks it up or down to the new table at the hero's next XP
  gain, so a save made on the other curve re-syncs then.
- Pipeline follow-ups, done (SPEC 23.1, `build_xml1.py --xp-curve`, default xml1): Danger Room completion gives XML1's
  0 XP (XML1 gave points only), each XML1 XP pickup its own XML1 count to the hero who takes it.

Tests: xml2_test (xml2-fix) checks the value rules, both tables against default.xbe's formulas worked out again (and
the margins above), the lookups at the table edges (level for 0, 99, 100, T1(45), max XP, 0xffffffff; 2,000,000 -> 26,
XML2 40), the kill XP edges (below 0, 45, 46, 255) and the split, every guard against the retail exe, exactly the bytes
written, and runs the patched lookup, cap and kill XP jump on the mapped exe. In game (xml2-fix test pipe; the HUD and
the stats screen show a level and an XP bar, never the XP: `tools/hero_xp.py` prints every hero's level and XP):
1. Fresh heroes, Magma in the party: `python tools/fixinput.py script 'awardXPToPlayable(2000000)'` -> the HUD shows
   **26** (XML2: 40); `python tools/hero_xp.py`: every non-exempt hero xp 2000000, level 26.
2. A kill with a 2-hero party (a third hero unlocked and benched): `hero_xp.py` before and after one kill (no other XP
   between): the benched hero's XP rises by K/2 (XML2: 1), each party hero's by K/2 + 3 (K/2 + 1) (+ the victim bonus;
   an AI teammate less by distance), K = f(enemy level) (level 20: 591 -> bench +295, party +295 + 888) or the npcstat
   xpaward.
3. `awardXPToPlayable(1119830)` on fresh heroes -> the level-up popup(s) to 25 and the skills screen's points as usual;
   `awardXPToPlayable(600000000)` -> level 45, the XP bar empty (the top), a second award changes nothing.
