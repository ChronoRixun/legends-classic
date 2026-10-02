# XML1 boss fights on XMen2.exe: what the missing AI states (issue #2 / audit G2) cost (2026-10-01)

Question: is #2 cosmetic, or does it break the climax fights? Short answer from all ten fights played through the harness (two sessions): **nothing blocks progression** - every scripted phase, pain-script threshold,
death script and follow-on (conversation, objective, next zone, credits) fired - but the bosses run on
XMen2.exe's generic monster AI, so the designed phases that XML1's engine owned (Magneto's shield,
Master Mold's shield-until-the-cores, Shadow King's perched / shielded phases) are gone or inert, and the
fights are **easier and flatter** than XML1's. Shadow King phase 1 is the one fight that is wrong: on his
floating pillar he is inert and hero attacks never register (not an immunity - moved to the floor he fights and
takes damage), so the side mission needs script damage or a fix to get past him.

Build: `build/_t16` (content 8 candidate), harness `python tools/harness.py install build/_t16 --pipe-name boss
--save-folder "X-Men Legends (boss tests)"`, xml2-fix 1.3.0 (log line 1), windowed 1280x720, launched with
`tools/gamedbg.py`. Party `seatParty("wolverine","cyclops","storm","iceman")` at 2,000,000 XP (level 26),
heroes invulnerable; bosses damaged with `setHealth` (`fraction()` in `boss_common.py`) followed by smash
hits so the pain scripts run, and killed with `damage(<boss>,<boss>,N)`. Frames and per-run logs are in the
session scratchpad `boss/shots` (contact sheets `sheet_*.png`); the drivers are
`research/regression/boss_fights/*.py` (`boss_common.py` reads the boss bar - row 72, x 449..851 full,
colour (127,25,25) - and matches the bar's title text; `run_fresh.py` / `cycle.sh` were abandoned, see 5).

## 1. Results

| fight (zone) | verdict | evidence |
|---|---|---|
| Juggernaut flashback, control (mansion/jugrnt/jugrnt01, states attackphysents / ignoreattacks only) | works | spawns, bar "Juggernaut (5)", smashes furniture then fights, bar 100 -> 93 % under the party, leaves the dining room on stage2's `ignoreattacks` + path after 30 s (`sheet_10_jug`, `sheet_12_jug`) |
| Magneto (astroid_m/visit1/asteroid2_1; magneto, mag2-5, magshield) | **degraded**, completes | trigger_touch06 spawns him + 3 elite acolytes, conversation 3_10_2, bar "Magneto (40)"; magneto_pain caps at 75 / 50 / 25 % exactly (bars 75.4, 49.9, 24.1) and acts shieldup/stage2-4; acting the acolyte deathtargets spawned Sabretooth, his death + pain spawned Mystique (both found by teleport); `damage()` killed him -> defeat_magneto's conversation 3_10_2_5 (`sheet_21..34_mag`). Missing: `magshield` never makes him invulnerable - his bar kept dropping (75 -> 72.5 -> 65 -> 58) while the acolytes / Sabretooth / Mystique were alive, so the whole fight can be brute-forced in one go; mag2-5 (his attack-set / cooldown phases) do nothing. Elite acolytes still draw the black spike polygons (B3) |
| Master Mold (mastermold/mastermold2; mold1-3, moldblowcore) | **degraded**, completes | spawns at zone start, bar 99.5 %, fires eye beams and melee swings; **damage lands from the first hit (99.5 -> 99.0) without touching a warp core** - `mold1` = the shielded phase (shockshield_on: def_damage 0 + touch damage) never comes up; mmpain's thirds cap at 66.5 / 33.0 % and the stage-2 spawnsentinels cinematic plays (camera tour, three leaders drop in); `damage()` -> stage3death: HUD off, he breaks apart, R501 call, credits (`sheet_40..44_mm`; the build has no movie files, so R501 is skipped) |
| Shadow King (astral/savepx/final_astral; sk, sk2-4) | **phase 1 broken (unreachable), completes** | SK1 spawns perched on the floating pillar and never attacks or moves; with a VULNERABLE party (second session, `sheet_130_skv`): Cyclops's and Storm's powers from the floor, 8 smashes + scripted heavy melee + Cyclops's power from ON the pillar, and the same after `setInvulnerable("shadowking","FALSE")` all left his bar at 100 %, while `damage()` took it to 83.6 % - and once moved to the floor (`copyOriginAndAngles("shadowking","_HERO1_")`, `sheet_150_skf`) he took hero damage at once (100 -> 93 %) and fought back (spear beams). So: **not immune - hits never register on the pillar and he cannot path from it**; sk1pain never ran there (no 84 % cap). Script `damage()` killed him -> spawnsk2 swap worked (bar back to 100, EA_POWER7 anim); SK2 fights normally (melee, beam, sk2pain cap 49.9 %, power_boost shades, power_xtreme clones); killing the three SK2s (two are style-spawned clones, `damage("shadowkingtwo",..)`) ran shadowking_defeated: Professor X conversation, "mission accomplished", popParty to subbasement8 (`sheet_51..59_sk`) |
| Mystique NYC (nyc/alison/nyc1_1_2b; mystique, myst1-3) | degraded at most, completes | spawner acted; she walks in from the bridge, trades ranged hits (aiforceranged), bar shows 39.7 % once (she is `monster_undying`, the bar mostly stays off); stage 2 ran away + round1grunts, grunt deaths, stage 4 disguised grunt; killing the grunt + her ran grunt2death's conversation and the 1_1_5 ending (`sheet_61b..67b_my`). myst1-3 (approach / flee / fight behaviour toggles) not visible |
| Blob NYC (nyc/alison/nyc1_1_3; blobnyc) | works (generic AI) | bar "Blob (4)" 100 %, his first pain opens the designed resistance popup (pain_blob_popup), `damage()` -> the 1_1_5_2 conversation and the defeat_blob objective (`sheet_71_blob`); the charge / belly-flop brain (0x36) is replaced by the style's generic attacks |
| Avalanche, mountain (mount/mount/mount2; avalanche, endbattle) | works | bar "Avalanche (27)", every 10 % step of avalanchepain caps and fires (79.9 / 69 / 60 / 35 / 4.7 %), QUAKE power_xtreme + rock drops play, `monster_undying` holds him at 0.5 % and mountoutro runs (his line, camcut teleporter scene, Cyclops's closing line) (`sheet_81_av`, `sheet_85_av`) |
| Pyro astral (astral/ast3/astral3_3; pyroastral, setpyroastral) | degraded at most | bar "Dark Pyro (29)" blue while shielded (shield_on + setInvulnerable), he flames the party meanwhile; four demon deaths -> red bar, vulnerable window, then the shield returns after 10 s as scripted (`sheet_91_py`); the only loss is the brain's stand-at-the-brazier placement |
| Avalanche astral (astral3_4; avalanche_astral = same brain id 0x24 as mount) | works | bar "Dark Avalanche (29)", stage 2 at 74.9 % with the invulnerable cage phase, `damage()` -> death script (bar empties, gate relays) (`sheet_101_aa`) |
| Blob astral (astral3_5; blobastral) | works | bar "Dark Blob (29)" drops under hits (100 -> 89.8), stage 2 armor_on (blue bar, Energy Resistant, vortex), pillar death -> armor_off + growth, `damage()` -> death (`sheet_111_ab`) |
| Dopplegangers (astral/ast3/colosseum; dop_col/cyc/jean/wol) | works | the four spawn and fight with the heroes' moves (Chaos Lord / Ultimate Predator / Sun Goddess bars, grabs, beams, an Xtreme flash), bars drop under hits, four deaths -> relay_end -> conv3_7_6, shadowking_escapes and the closing line (`sheet_141_col`); the mimic brain's loss is invisible |

Hangs seen during the first session are the harness environment, not the port (section 5). Second session (Owen's console session active): six fresh-process runs, one fight each, closed with kill_build; no stall.

## 2. What the states did in XML1 (default.xbe)

`xml1_text.asm` 0xf5834-0xf5ea8: the aipattern `setstate` parser maps the name to a small id (attackphysents 0,
ignoreattacks 1, backboss 2, chargeboss 3, sabretooth 4, mystique 5, myst1-3 6-8, avalanche = avalanche_astral 9,
aoeattack 0xa, freeze 0xd, pause 0xe, pyroastral 0xf, setpyroastral 0x10, magneto 0x11, mag2-5 0x12-0x15,
magshield 0x16, mold1-3 0x17-0x19, moldblowcore 0x1a, moldendgame 0x1b, sk 0x1c, sk2-4 0x1d-0x1f, blobnyc 0x20,
blobastral 0x21, dop_wol/col/jean/cyc 0x22-0x25, findnearestwaypoint 0x26, initmystique 0x27, bossfull 0x28,
bosspartial 0x29, endbattle 0x2a). The node runs through the jump table at 0xf43ac (`scratchpad/boss/setstate_cases.py`
dumps every case):

- The boss "start" states select a hardcoded AI state of the monster's state machine via `0xfe330(monster, N)`:
  avalanche 0x24, mystique 0x22 (myst2 0x23 + a timer), pyroastral 0x2a, magneto 0x2c, mold1 0x2e, sk / sk2 0x34,
  blobnyc / blobastral 0x36 (global 0x4fedb4 = 0 / 1), dop_* 0x38 (+ the dopple's mirror hero in 0x4feda0..ac and
  the bossfull bit in monster+0x28c); backboss 0x1d / chargeboss 0x1f / sabretooth 0x20 use the same call. The
  behaviour of each state (Magneto's shield and flight, Master Mold's shield until the cores, Shadow King's pillar
  and shield, the dopples copying their hero) is C++ in those state handlers - not data, not script.
- The phase states only set globals the brain reads: mag2-5 set six attack-enable bytes 0x4fedc0-c5/d0 and two
  floats 0x4fedcc / 0x4fedd8 (5/6, 4/6, 3/6, 2/3 - cooldowns); magshield doubles both floats and sets 0x4fedc0;
  mold2 sets 0x4feda0, mold3 sets 0x4fedc9 and clears it, moldblowcore sets 0x4fede0; sk3 sets 0x4fedb4 (shield),
  sk4 clears it via 0x4fedb5 and writes 350.0 to monster+0x254; setpyroastral writes its bool to 0x4feda0; myst1
  clears monster+0x408, myst3 writes 0x204 there and 0 to monster+8 (= what endbattle does: leave the state).
- XMen2.exe's parser (0x5210a0..0x5217f4) has the same shape with XML2's bosses (bastion 0xb, deadpool 0xc,
  stryfe 0xd, archangel 0xe ...); its state machine has no XML1 boss brains, so adding the names would still have
  nothing to run.

## 3. Fix sketches

| fight | fix | effort |
|---|---|---|
| Magneto | script: at each `shieldup` act `setInvulnerable("magneto","TRUE")` + the existing shield combat node, and `FALSE` in stage2/3/4/5 (the counters that end each sub-fight already exist); mag2-5 attack sets via `setCombatNode` on existing moves; the `flight` part stays XML2 AI | 0.5 day, data + scripts |
| Master Mold | script: `setCombatNode("mastermold","shockshield_on")` in mmspawn (the node already carries def_damage 0 + touch damage) - checkcore already turns it off; mold2/mold3 = pattern sequences with `attack` nodes picking his heavy moves; moldblowcore = a scripted `playanim` + the existing core relays | 0.5 day |
| Shadow King phase 1 | he is unreachable on the pillar, not immune: bring him to the floor at zone start (a floor spot via `copyOriginAndAngles` in final_astral.py, or a waypoint path down) and he fights and takes damage as is; then sk3 = `setInvulnerable` (+ the `power_boost` vortex, def_damage 0) and sk4 = `setInvulnerable FALSE` on the 30 s shieldtimer | 0.25 day |
| Blob (both) | pattern with `attack` nodes for the charge move; the astral armor / pillar logic is already script | 0.25 day |
| Pyro astral | pattern `attack` nodes for fireball / flame moves; keep him near the brazier with `setRadiusConfinement` | 0.25 day |
| Avalanche (both) | nothing needed beyond a pattern; the phases are combat nodes | 0.1 day |
| Dopples | the mimic brain cannot be scripted; accept four ordinary enemies (their styles are the heroes' moves) | none |
| xml2-fix hook alternative | implement boss brains in the DLL on top of the monster AI (0xfe330's XMen2.exe counterpart, the 0x5217f4 id store) | weeks, not recommended |

## 4. Not tested / uncertain

- Vulnerable runs: only the two Shadow King probes (`sk1_vuln_driver.py`, the floor probe inline in the second
  session) ran without setInvulnerable; whether Magneto / Master Mold / SK2 can kill a party and how hard they hit
  is untested.
- Shadow King 1: why hits do not register on the pillar (mover collision, height, or the hit test) was not traced;
  the floor result makes the fix independent of the cause.
- Pyro astral was not killed (the shield had returned by the kill step, as designed); Blob NYC's hits were
  swallowed by the pain popup, so his attacks were not watched.
- `killEntity`/`damage` on unnamed spawns do nothing (the elite acolytes stayed alive; their deathtargets were
  acted by hand), so the acolyte sub-fight's timing was not played.
- Mystique NYC's myst1/myst2/myst3 approach / flee toggles: the frames show her fighting at range; not compared
  with XML1.
- Magneto's `stage4.py` waits for signal `readytogo` that nothing sends (XML1's script is the same) - harmless.

## 5. Harness notes (environment, not the port)

- Three "no frame within 3000 ms" stalls (15:26 asteroid2_1, 15:38 mastermold2, 15:56 nyc1_1_3) and the final
  start failure at 16:02 ("Hardware acceleration not supported", no Direct3D device, `xml2-fix_run6_nodevice.log`)
  line up with the desktop session: `query session` shows Owen's session 1 **Disc** and
  `SystemInformation.TerminalServerSession = True` - the runs were in a disconnected RDP session, where D3D8 loses
  the device (the game then stops presenting and later stops pumping messages). Loads from a fresh game after a
  reconnect worked every time. Not a loadMapKeepTeam bug as first suspected.
- `run_fresh.py`'s detached launch left the game suspended under its debugger; launch `gamedbg.py` from the
  Bash tool's background instead (`cycle.sh` kept for the kill / wait part).
- The game's console queue holds 2 lines: one `fraction()` (3 statements on one line) after two teleport lines was
  dropped once (Magneto at 24.1 % did not go to 2 %); resend when the bar does not move.
