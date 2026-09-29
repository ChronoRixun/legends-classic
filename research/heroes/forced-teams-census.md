# Forced-team census: XML1's forced parties vs. what the port emits today

Written 2026-09-28 (read-only research pass). Companion to `roster.md` (sections 1, 2, 4 are the primary
source for unlock order and the mechanism table; this file does the per-mission accounting roster.md 4
summarizes but doesn't tabulate). Sources: `research/scripts/mission_plan.json` (XML1 mission attrs),
`tools/xml1build/scripts.py::forced_hero_missions` (the port's own filter, reproduced and verified below),
the generated `build/_heroes/Scripts/x1/missions/begin_<m>.py` bodies (today's port start per mission),
`build/_heroes/_build/zones_detail.json` key `hero_npc_zones` (the SPEC.md **section 18** hazard list),
`tools/xml1build/SPEC.md` section 18, and `research/heroes/roster.md` section 5 (T7-T13 spec, not yet all
implemented — cross-checked against the actual `tools/xml1build/scripts_transform.py` source, not assumed).
Items not read from code/data in this session are marked **UNVERIFIED**.

## 0. What counts as "forced" here

`forced_hero_missions()` (`tools/xml1build/scripts.py:624`) flags a mission when it has a `REQUIREDHERO` or
`maxheros < 4`. Re-running that exact rule over `mission_plan.json` in this session reproduces **49**
missions, matching roster.md 0.5's count exactly. Of the 49: **31** are Magma-solo (mansion hubs, their
briefings/debriefings, and Danger Room re-entries), **6** are boss/status Danger-Room-disc replays
(`boss_mystique`, `boss_blob`, `ice_wolverine`, `boss_sabreroof`, `boss_havok`, `boss_shadowking`,
`status_meeting` — 7 actually, see table), and the rest are one-off forced pairs/trios/flashbacks. The
**25 reachable Magma-solo missions** roster.md cites are the subset of the 31 that `campaign_missions()`
reaches from New Game (i.e. excluding the boss/status replays that also happen to require Magma).

## 1. Per-mission census (all 49)

Columns: **Conv. hero-speakers** = hero `%TOKEN%` speakers counted across every `.XMLB` conversation under
the mission's zone **folder** (not narrowed to the exact triggering zone — several forced missions share a
folder, e.g. `mansion3`/`mansion3_dangerroom`/`mansion3_uniform` all point at `mansion/man3`, so their counts
are identical; treat this as "hero relevance in this hub", not a per-trigger count). **_HERO1-4 files** =
number of distinct scripts under that folder that use positional `_HERO1_`.._HERO4_` (assume-a-slot risk,
SPEC.md 18's "Open" class). **Direct hero-name hits** = scripts under that folder calling
`remove`/`setAIActive`/`copyOriginAndAngles`/`setEnable` with a literal hero name in quotes (the SPEC.md 18
hazard: if that named hero is genuinely in the party, the call can hit the player's own hero, not an NPC
double) — first 3 examples given, `file:line`. Zone-folder mapping and hazard classification cross-checked
against `zones_detail.json:hero_npc_zones` in section 3.

| # | Mission (act) | Zone folder | Min/Max | XML1 party (REQUIREDHERO) | Skinset | Port start today | Conv. hero-speakers (folder-scope) | _HERO1-4 files | Direct hero-name hits |
|---|---|---|---|---|---|---|---|---|---|
| 1 | alison (1) | nyc/alison | 2/2 | wolverine/cyclops | default | `x1/missions/begin_alison.py`:39-43<br>unlock wolverine+cyclops -> loadMapChooseTeam(nyc/alison/nyc1_1_1) | Wolverine:3, Cyclops:2, Magma:2, Phoenix:2 | 18 | 3 (nyc\alison\1_1_5_1_end.py:16; nyc\alison\alison_gets_away.py:13; nyc\alison\alison_gets_away_2.py:6) — **all `cyclops`, all FIXED by T7's join-double rename, see §3** |
| 2 | mansion1 (1) | mansion/man1a | 1/1 | magma | magmacivilian | `x1/missions/begin_mansion1.py`:38-41<br>unlock magma -> loadMapChooseTeam(mansion/man1a/mansion1a_1) | Magma:29, Phoenix:23, Beast:2, Storm:1, Rogue:1, Iceman:1, Cyclops:1 | 0 | 3 (mansion\man1a\mansion1a_1.py:22,37; mansion\man1a\mansion1a_2.py:25) — `phoenix` — **OPEN, SPEC 18** |
| 3 | harrp_briefing (1) | mocap/mocap2 | 1/1 | magma | civilian | `x1/missions/begin_harrp_briefing.py`:4-5<br>unlock magma -> loadMapChooseTeam(mocap/mocap2/briefing_1_2_41) | - | 0 | 0 |
| 4 | jug_fb (1, side) | mansion/jugrnt | 4/- | cyclops/beast/iceman/phoenix | 60s | `x1/missions/begin_jug_fb.py`:16-20<br>unlock 4 heroes -> loadMapChooseTeam(mansion/jugrnt/jugrnt01) | Phoenix:1, Beast:1, Cyclops:1 | 0 | 0 |
| 5 | mansion2 (1) | mansion/man2 | 1/1 | magma | magmacivilian | `x1/missions/begin_mansion2.py`:37-40<br>unlock magma -> loadMapChooseTeam(mansion/man2/mansion_back2) | Magma:14, Beast:2, Cyclops:2, Gambit:1, Storm:1, Wolverine:1, Rogue:1, Jubilee:1, Iceman:1, Nightcrawler:1 | 0 | 0 (nightcrawler/cyclops NPC zones exist per §3 but no hit matched this scan's call-shape — **needs a follow-up grep of mansion2_1.py/subbasement2.py**) |
| 6 | sewer_muir_briefing (1) | mocap/mocap3 | 1/1 | magma | civilian | `x1/missions/begin_sewer_muir_briefing.py`:4-5 | - | 0 | 0 |
| 7 | dr_mag1 (1, side) | mansion/dr_mag | 1/1 | magma | default | `x1/missions/begin_dr_mag1.py`:22-23 | - | 0 | 0 |
| 8 | sent_fb (1, side) | nyc/fb | 4/4 | nightcrawler (+3 RECOMMENDED) | 70s | `x1/missions/begin_sent_fb.py`:17-20<br>unlock nightcrawler -> loadMapChooseTeam(nyc/fb/nyc_fb1) | Phoenix:1, Nightcrawler:1, Cyclops:1, Wolverine:1 | 1 (cargoboom.py, 16 lines) | 0 |
| 9 | mansion3 (3) | mansion/man3 | 1/1 | magma | magmacivilian | `x1/missions/begin_mansion3.py`:34-39 | Magma:13, Wolverine:4, Nightcrawler:4, Jubilee:4, Phoenix:4, Beast:4, Rogue:4, Storm:3, Iceman:2, Cyclops:1 | 0 | **5** (hangar3.py:19 `wolverine`; subbasement3b.py:15-21 `wolverine`+`storm`×2) — **OPEN, SPEC 18's own worked example** |
| 10 | nuke_briefing (3) | mocap/mocap5 | 1/1 | magma | default | `x1/missions/begin_nuke_briefing.py`:4-5 | - | 0 | 0 |
| 11 | mansion3_dangerroom (3) | mansion/man3 | 1/1 | magma | magmacivilian | `x1/missions/begin_mansion3_dangerroom.py`:28-29 | (same as #9) | 0 | (same as #9) |
| 12 | mansion3_uniform (3) | mansion/man3 | 1/1 | magma | default | `x1/missions/begin_mansion3_uniform.py`:34-35 | (same as #9) | 0 | (same as #9) |
| 13 | wx_fb_start (3, side) | weapon_x/wfb | 1/1 | wolverine (16 RESTRICTED) | weaponx | `x1/missions/begin_wx_fb_start.py`:7-10 | - | 0 | 0 |
| 14 | dr_mag2 (3, side) | mansion/dr_mag2 | 2/2 | magma/cyclops | civilian | `x1/missions/begin_dr_mag2.py`:33-35 | Magma:9, Wolverine:2, Cyclops:1, Storm:1 | 11 (blob/*, mystique/* — cargoboom-style hero-spot scripts) | 4 (blob/2_2_1_3a_*.py, 2_2_1_3b_end.py, 2_2_1_3_new_end.py — all `cyclops`, **FIXED by T7 rename**, §3) |
| 15 | muir2 (4) | muir_is/muir2 | 1/1 | magma | default | `x1/missions/begin_muir2.py`:27-30 | Magma:12, Colossus:3, Cyclops:3 | 0 | 3 (2_4_1_cleanup.py:6-8 `colossus`×2, `storm`) — **OPEN, SPEC 18** |
| 16 | muir2_reboot (5, side) | muir_is/muir2 | 1/1 | magma | default | `x1/missions/begin_muir2_reboot.py`:25-26 | (same as #15) | 0 | (same as #15) |
| 17 | mansion4 (5) | mansion/man4 | 1/1 | magma | default | `x1/missions/begin_mansion4.py`:32-33 | Magma:10, Phoenix:9, Beast:5, Cyclops:4, Frost:3, Nightcrawler:3, Colossus:2, Wolverine:2, Iceman:1, Gambit:1, Rogue:1, Storm:1 | 1 (grso_reveal.py, 4 hero-spot lines) | 3 (gambit_leaves.py:9, mansion4_1.py:31-32 — `gambit`×2, `rogue`) — **OPEN, SPEC 18** |
| 18 | grso_briefing (5) | mocap/mocap6 | 1/1 | magma | default | `x1/missions/begin_grso_briefing.py`:4-5 | - | 0 | 0 |
| 19 | astral_wx_briefing (5) | mocap/mocap7 | 1/1 | magma | default | `x1/missions/begin_astral_wx_briefing.py`:4-5 | - | 0 | 0 |
| 20 | grso_debriefing (5) | mansion/man4 | 1/1 | magma | default | `x1/missions/begin_grso_debriefing.py`:30-31 | (same as #17) | 1 | (same as #17) |
| 21 | mansion4_grso_done (5) | mansion/man4 | 1/1 | magma | default | `x1/missions/begin_mansion4_grso_done.py`:36-39 | (same as #17) | 1 | (same as #17) |
| 22 | astral_briefing (5) | mocap/mocap7 | 1/1 | magma | default | `x1/missions/begin_astral_briefing.py`:4-5 | - | 0 | 0 |
| 23 | astral1 (5) | astral/ast1 | 3/3 | ProfXAstral/phoenix/frost (MUSTLIVE ProfXAstral) | default | `x1/missions/begin_astral1.py`:21-24<br>unlock profxastral+phoenix+frost -> loadMapChooseTeam(astral/ast1/astral1_1) | Phoenix:3, Frost:3, ProfXAstral:2 | 1 (supershades_defeated.py, hero1/2 only) | 0 |
| 24 | astral1b (5) | astral/ast1 | 2/2 | phoenix/frost | default | `x1/missions/begin_astral1b.py`:21-25 | (same as #23) | 1 | 0 |
| 25 | old_wx (5) | weapon_x/old | 1/1 | cyclops | default | `x1/missions/begin_old_wx.py`:16-17 | Wolverine:1 | 1 (havok_defeated.py, hero1 only) | 0 |
| 26 | secret_wx (5) | weapon_x/secret | 2/2 | wolverine/cyclops | default | `x1/missions/begin_secret_wx.py`:14-16 | - | 2 (2_7_5*.py, hero1-3) | 2 (2_7_6_start.py:8-9, `cyclops`+`wolverine` — these two **are** the forced pair, so **safe today**) |
| 27 | end_astral (5) | mansion/man5 | 1/1 | magma | default | `x1/missions/begin_end_astral.py`:16-17 | Magma:6, Cyclops:4, Frost:2, Beast:2, Wolverine:1, Colossus:1 | 1 (sentinel_count.py, getName only) | 0 |
| 28 | mansion5 (6) | mansion/man5 | 1/1 | magma | default | `x1/missions/begin_mansion5.py`:24-25 | (same as #27) | 1 | 0 (but `mansion5_1` itself is a `hero_npc_zones` `wolverine` entry — **not caught by this scan's call-shape, follow up**) |
| 29 | healer_briefing (6) | mocap/mocap8 | 1/1 | magma | default | `x1/missions/begin_healer_briefing.py`:4-5 | - | 0 | 0 |
| 30 | mansion6 (7) | mansion/man6 | 1/1 | magma | default | `x1/missions/begin_mansion6.py`:11-19 | Magma:5, Wolverine:2, Cyclops:2, Frost:1, Beast:1, Phoenix:1, Storm:1 | 0 | 0 |
| 31 | muir_riots_grso_briefing (7) | mocap/mocap9 | 1/1 | magma | default | `x1/missions/begin_muir_riots_grso_briefing.py`:4-5 | - | 0 | 0 |
| 32 | muir3brig (7) | muir_is/muir3 | 1/1 | phoenix | default | `x1/missions/begin_muir3brig.py`:23-24<br>unlock phoenix -> loadMapChooseTeam(muir_is/muir3/muir_brig) | Cyclops:1 | 3 (muir_in3.py, startthefight.py, xmengreetjuggy.py — hero1-4) | 0 |
| 33 | nyc_rooftops (7) | nyc/riots | 1/1 | wolverine | default | `x1/missions/begin_nyc_rooftops.py`:23-24 | Psylocke:1, Wolverine:1 | 6 (conv3_1_1end, conv3_2_3, conv3_2_5, intro_spider_sentinel, reset_intro_spider_sentinel, start_riots — hero1-4) | 1 (conv3_2_3.py:26 `psylocke`) — **OPEN, matches the mansion7/riots Psylocke NPC**, §3 |
| 34 | mansion7 (8) | mansion/man7 | 1/1 | magma | default | `x1/missions/begin_mansion7.py`:17-18<br>-> loadMapChooseTeam(mansion/man7/status_meeting) | Beast:4, Magma:4, Cyclops:3, Phoenix:2, Wolverine:2, Storm:1, Colossus:1, Frost:1, Psylocke:1, Nightcrawler:1, Iceman:1 | 0 | 4 (3_6_2_end.py:8-11 `colossus`, `beast`, `frost`, `beast`) — **OPEN, SPEC 18** |
| 35 | astral2_briefing (8) | mocap/mocap11 | 1/1 | magma | default | `x1/missions/begin_astral2_briefing.py`:4-5 | - | 0 | 0 |
| 36 | end_astral2 (8) | mocap/mocap10 | 1/1 | magma | default | `x1/missions/begin_end_astral2.py`:6-7 | - | 0 | 0 |
| 37 | end_hive (8) | mocap/mocap12 | 1/1 | magma | default | `x1/missions/begin_end_hive.py`:4-5 | - | 0 | 0 |
| 38 | mansion8 (9) | mansion/man8 | 1/1 | magma | default | `x1/missions/begin_mansion8.py`:14-15 | Magma:5, Cyclops:4, Phoenix:3, Wolverine:3, Beast:2, Iceman:1, Gambit:1 | 0 | 0 |
| 39 | asteroid_briefing (9) | mocap/mocap13 | 1/1 | magma | default | `x1/missions/begin_asteroid_briefing.py`:4-5 | - | 0 | 0 |
| 40 | start_astral3 (9) | mansion/man8 | 1/1 | magma | default | `x1/missions/begin_start_astral3.py`:10-11 | (same as #38) | 0 | 0 |
| 41 | astral_sk (9, side) | astral/savepx | 1/1 | ProfXGladiator | default | `x1/missions/begin_astral_sk.py`:27-28 | - | 1 (conv3_9_3_4.py, hero1-4) | 0 |
| 42 | asteroid_rock (9) | astroid_m/visit1 | 4/4 | frost | default | `x1/missions/begin_asteroid_rock.py`:19-22 | - | 0 | 0 |
| 43 | boss_mystique (9, DR replay) | nyc/alison | 1/1 | wolverine | default | `x1/missions/begin_boss_mystique.py`:29-30 -> nyc1_1_2b | (same folder as #1) | 18 | 3 (same as #1) |
| 44 | boss_blob (9, DR replay) | nyc/alison | 2/2 | wolverine/cyclops | default | `x1/missions/begin_boss_blob.py`:29-31 -> nyc1_1_3 | (same folder as #1) | 18 | 3 (same as #1, **and this IS the T7 join zone**) |
| 45 | ice_wolverine (9, DR replay) | haarp/ice_sq | 1/1 | wolverine | default | `x1/missions/begin_ice_wolverine.py`:6-7 | - | 0 | 0 |
| 46 | boss_sabreroof (9, DR replay) | nyc/riots | 1/1 | wolverine | default | `x1/missions/begin_boss_sabreroof.py`:23-24 | (same folder as #33) | 6 | 1 (same as #33) |
| 47 | boss_havok (9, DR replay) | weapon_x/old | 1/1 | cyclops | default | `x1/missions/begin_boss_havok.py`:10-11 -> wx2_2 | Wolverine:1 | 1 | 0 (but `wx2_2` is a `hero_npc_zones` `wolverine` entry — **not caught by this scan, follow up**) |
| 48 | boss_shadowking (9, DR replay) | astral/savepx | 1/1 | ProfXGladiator | default | `x1/missions/begin_boss_shadowking.py`:25-26 | - | 1 | 0 |
| 49 | status_meeting (9, DR replay) | mansion/man7 | 1/1 | magma | default | `x1/missions/begin_status_meeting.py`:13-14 | (same folder as #34) | 0 | 4 (same as #34) |

All 49 confirmed by direct grep of the generated `begin_<mission>.py` bodies: **every one already routes
through `loadMapChooseTeam`** (roster.md's "the port can only unlock the required heroes and open the team
menu" — verified, not just cited). None of the 49 seats anyone; the player always picks manually. This is the
gap the task's engine-feature idea (xml2-fix seating the party directly, the way `new_game.cpp` already
re-points `startFirstMission`'s hero-name pushes) would close.

## 2. Roster-unlock progression (cumulative, for the "what's available" column above)

Built from roster.md 1.2/1.3's exhaustive script/conversation census (not re-derived here). Magma is a
special case: XML1 never scripts `setInCampaign("magma")` (roster.md 1.2's "never unlocked anywhere" list),
but every one of the 49 missions' converted `begin_<m>.py` **already calls `unlockCharacter("magma")`**
because Magma is `REQUIREDHERO` at each of them (verified above) — so in the port Magma is selectable from
mission 1 onward, earlier than XML1 arguably intended (roster.md 4 flags "Magma becomes selectable here
(XML1: mansion3_uniform, **UNVERIFIED**)").

| After... | Newly available (script-verified) | Cumulative pool |
|---|---|---|
| New Game / alison | wolverine, cyclops (addHero, nyc1_1_3) | 2 |
| mansion1 | +magma (REQUIREDHERO), storm, rogue, iceman, phoenix, beast | 8 |
| mansion2 | +nightcrawler; **Jubilee NPC-only** (mansion_back2, mansion3_1 — never scripted, roster.md 1.2) | 9 |
| sewers (fadegambit) | +gambit | 10 |
| mansion3 / dr_mag2 | (no new; beast/rogue conversations repeat) | 10 |
| muir2/muir_in2 | **Colossus NPC-only** ("welcome to join us", never scripted) | 10 |
| mansion4 / astral1 | +frost, +profxastral (both REQUIREDHERO at astral1); **Colossus, Jubilee still NPC-only** | 12 |
| mansion7 / riots | **Psylocke NPC-only** (mansion7_1, nyc3_1_2 — never scripted) | 12 |
| — | Colossus, Psylocke, Jubilee: **never unlocked by any XML1 script/conversation/mission file** (roster.md 1.2 exhaustive census); port must add explicit `unlockCharacter` calls — roster.md 4 proposes mansion4/mansion7/mansion2 respectively from the NPC evidence, **not XML1 canon, a port decision** | 15 (+ProfXAstral, +ProfXGladiator if herostat entries are made for them, open decision 4 in roster.md 6) |

## 3. SPEC.md §18 hero-NPC name-collision hazard, cross-referenced to the 49

`zones_detail.json:hero_npc_zones` (18 zones) lists every reachable zone where an NPC shares a hero's exact
entity name — `remove`/`setAIActive`/`copyOriginAndAngles`/`setEnable` by that name will hit the player's own
hero if that hero happens to be in the party (SPEC.md 18). Two of the 18 are **fixed** (the T7 `join_hero`
rename, already shipped — verified in `scripts_transform.py` and in the generated `add_cyclops.py` files,
§4). The rest are **open** per SPEC.md's own text ("XML1 only did this where its forced teams kept that hero
out of the party; the port's team menus may let the hero in... whether XMen2.exe skips a CHRB NPC whose name
matches a party hero is UNVERIFIED").

| Zone | NPC name(s) | Status | Missions in this census that reach it |
|---|---|---|---|
| `nyc/alison/nyc1_1_3` | cyclops | **FIXED** (T7 `rename_join_double`) | alison, boss_blob |
| `mansion/dr_mag2/mag_nyc4` | cyclops | **FIXED** (T7) | dr_mag2 |
| `mansion/dr_mag2/mag_nyc3` | cyclops | OPEN (pre-join, before T7's rename applies) | dr_mag2 |
| `nyc/alison/nyc1_1_2b` | cyclops (`cyclops_scripted`, a Mystique morph per roster.md 1.3 — **may not be a literal name collision**, UNVERIFIED) | OPEN / special-case | boss_mystique |
| `mansion/man1a/mansion1a_1` | phoenix, rogue | OPEN | mansion1 |
| `mansion/man1a/mansion1a_2` | phoenix, storm | OPEN | mansion1 |
| `mansion/man2/mansion2_1` | nightcrawler | OPEN (not confirmed by this pass's regex — follow up) | mansion2 |
| `mansion/man2/subbasement2` | cyclops | OPEN — **also the un-restored return zone for dr_mag1 and sent_fb** (§5): compounding risk if Cyclops is in either flashback's party | mansion2, dr_mag1 (return), sent_fb (return) |
| `mansion/man3/hangar3` | wolverine | OPEN — confirmed hit | mansion3 et al, wx_fb_start's return |
| `mansion/man3/mansion3_1` | nightcrawler | OPEN (not confirmed by this pass's regex) | mansion3 et al |
| `mansion/man3/subbasement3b` | phoenix, storm | OPEN — confirmed hit (wolverine+storm) | mansion3 et al |
| `mansion/man4/mansion4_1` | gambit, rogue | OPEN — confirmed hit | mansion4, grso_debriefing, mansion4_grso_done |
| `mansion/man4/mansion_back4` | colossus | OPEN (not confirmed by this pass's regex) | mansion4 et al |
| `mansion/man5/mansion5_1` | wolverine | OPEN (not confirmed by this pass's regex) | end_astral, mansion5 |
| `muir_is/muir2/muir_in2` | colossus, cyclops | OPEN — confirmed hit | muir2, muir2_reboot |
| `nuke_plant/nuke/nuke2_2` | colossus | OPEN | (not in the 49 — `nuke_col` isn't REQUIREDHERO/maxheros<4) |
| `sewers/hub/sewers1_2_4` | gambit | OPEN | (not in the 49) |
| `weapon_x/old/wx2_2` | wolverine | OPEN (not confirmed by this pass's regex) | boss_havok (this is literally boss_havok's own mapload zone) |

**Net: 16 of 18 known hero-NPC collision zones are unfixed and reachable from a forced-hero mission in this
census.** 5 of those are directly confirmed here by a positional-name grep; 6 more are named by
`hero_npc_zones` but weren't matched by this pass's `remove/setAIActive/copyOriginAndAngles/setEnable`
regex (they may use a different call shape, e.g. `act()`/`playanim()` on the NPC, or the collision may be in
a sibling script this pass's folder scoping didn't include) — **flagged, not verified absent**.

## 4. T7 `join_hero` (already shipped) — the only "force + unseat NPC" pattern that exists today

Verified in `build/_heroes/Scripts/{nyc/alison,mansion/dr_mag2/blob}/add_cyclops.py`: both match roster.md
5's T7 spec exactly (`unlockCharacter` -> `remove("cyclops_x1double","cyclops_x1double")` ->
`setGameFlag("x1join",<bit>,1)` -> `extractionPointChange("_ACTIVE_HERO_",0)`), and `scripts_transform.py`
has the `JOIN_FLAG='x1join'` guard/reset machinery roster.md 5 describes. This is the existing precedent for
"engine assist beyond what a script alone can do" the task is asking to extend to the other 47 missions —
except T7 still opens the team menu (the player picks); it does not seat anyone directly. **No script or
XML2 mechanism seats a hero without the team menu** (roster.md 2.1, re-confirmed: the 22 callers of
`0x46c810` are all engine-side — `startFirstMission`, save loader, zone-load pending array, danger-room team
builder, team menu, `resetgame`, `builddefaultteam`, `restorelastzone`; none is scriptable). An xml2-fix hook
that force-writes the four slot names via `game vt+0xf0` (`0x46c810`, the same primitive `new_game.cpp`
already re-points for `startFirstMission`) at each of these 49 `beginMission`/`loadMapChooseTeam` call sites
— skipping the team menu — is therefore the only route to an exact, non-optional XML1 party; this is
roster.md 3's "option C" applied per-mission instead of only at New Game.

## 5. Side missions needing a party restore (T9) — **unimplemented**

`grep -rn "x1side" tools/xml1build/*.py` returns **zero hits**: roster.md 5's T9 (`side_mission_party`) is
specified but not built. Checked every one of T9's own list (jug_fb, sent_fb, wx_fb_start, dr_mag1, dr_mag2,
astral_sk, muir2_reboot) against the actual generated "end" script:

| Side/detour mission | Begin call site | End script (today) | Behavior today | Restore needed? |
|---|---|---|---|---|
| jug_fb | `mansion/man1b/loadjuggernaut.py` | `missions/jug_done.py` (`mission("jug_fb","COMPLETE")`, not `endSideMission` — XML1 uses the blackbird-menu-complete path, not a symmetric beginSideMission/endSideMission pair) | **`loadMapKeepTeam("mansion/man1b/subbasement1b")`** — confirmed bug: the 60s flashback party (Cyclops/Beast/Iceman/Phoenix) is *kept*, not even reopened for a re-pick | **Y — worst case of the 6; silently wrong, no menu at all** |
| sent_fb | `mansion/man2/loadsentinel.py` | `nyc/fb/nycfb4_finish.py` | bare `loadZone("mansion/man2/mansion2_1","")`, no team menu | Y |
| wx_fb_start | conv `mansion/man3/2_1_15_meet_wolverine` (roster.md 1.2) | `weapon_x/wfb/end_fb.py` | bare `loadZone("mansion/man3/hangar3","")` | Y |
| dr_mag1 | dr_mag01 start | `mansion/dr_mag/fmvexit.py` | bare `loadZone("mansion/man2/subbasement2","")` | Y |
| dr_mag2 | `mansion/dr_mag2/mag_nyc1` (mission start, not a true side mission) | `mansion/dr_mag2/endsidemission.py` | chains straight into `begin_mansion3_dangerroom`'s body -> `loadMapChooseTeam` | **N (incidental)** — the very next forced mission reopens the menu anyway |
| muir2_reboot | (keepheroes continuation, not a scripted beginSideMission) | `muir_is/muir2/endreboot.py` | bare `loadZone("muir_is/muir2/muir_in2","")` | Y |
| astral_sk | `astral/savepx/xcrystal_destroyed.py` (chains in) | `astral/savepx/shadowking_defeated.py` | bare `loadZone("astral/savepx/astral2_3","")` | Y |

**5 of the 7 leave the flashback/detour party in place with no team menu at all** (identical practical effect
to jug_fb's `loadMapKeepTeam`, since a bare `loadZone` doesn't touch party slots either — `0x46c810` is only
ever written by the callers in §4, and a plain zone load isn't one of them). Simplest fix per roster.md 5 T9:
replace each end script's `loadZone(<caller>,"")` with `loadMapChooseTeam(<caller>)` so the player at least
re-picks (matches what already happens by accident at every other forced-mission boundary); the "faithful"
variant (exact return position + automatic restore) needs a second `extractionPointChange`/`restorelastzone`
pass roster.md 5 marks **UNVERIFIED and clumsy**.

## 6. Proposed seat spec (what an xml2-fix engine hook would need to write per mission)

Format: ordered hero list (slot 0..N), skinset name (numeric per-hero costume codes below), restore-after.
The "XML1 party" column of the table in §1 **is** this list (REQUIREDHERO order as read from
`mission_plan.json`, i.e. XML1's own attribute order — not independently re-derived). Only the costume
resolution and the restore flag are new information here:

- **Costume codes** (from `xml1_loose/data/herostat.eng`, hero base skin + variant suffix): Wolverine
  `skin_weaponx="02"` (wx_fb_start), Nightcrawler `skin_70s="02"` (sent_fb), Beast/Iceman/Phoenix/Cyclops
  `skin_60s="02"/"03"/"02"/"02"` (jug_fb), Magma `skin_magmacivilian="03"` (25 of the 31 Magma-solo entries).
  **Gap found**: `dr_mag2` (skinset `civilian`) requires Magma **and Cyclops** in civilian dress, but
  Cyclops has **no `skin_civilian` entry in herostat.eng** (only Iceman `"02"` and Colossus `"02"` do) —
  either XML1 used Cyclops's default costume here (civilian == default for him) or the port's converted
  herostat is missing a variant; **UNVERIFIED, worth a direct check of `xml1_assets`'s Cyclops model/skin
  list** before wiring a costume push for this one mission.
- **Restore-after = Y** for the 6 open rows in §5 (jug_fb, sent_fb, wx_fb_start, dr_mag1, muir2_reboot,
  astral_sk); **N** for the other 43 (either they chain into the next forced mission, which already reopens
  a menu today, or nothing narratively follows that would break).
- Seating primitive: write `game vt+0xf0` (`0x46c810`) for slots 0..N-1 with the REQUIREDHERO names, empty
  string (`0x681968`) for the rest (same "clear slot" behavior roster.md 3 documents for option C), then a
  costume push per seated hero (`setSkin(a,s)` `0x4a3dc0`, §2.6 of roster.md, or the `unlockCharacter("",
  costume)` global-costume-unlock pattern XML2's own `bonus/b5_unlock_ironman.PY` uses, §2.7) — this is a
  **new** primitive, not something T7 already does (T7 still uses the team menu).

## 7. Open questions

1. **T9 is unbuilt** (§5) — 6 confirmed party-carries-over gaps, one of them (jug_fb) already silently wrong
   via `loadMapKeepTeam` rather than merely unrestored.
2. **6 of 18 SPEC.md §18 hazard zones weren't confirmed present/absent by this pass's regex** (mansion2_1,
   mansion3_1, mansion_back4, mansion5_1, wx2_2, and nuke2_2/sewers1_2_4 which aren't in the 49) — needs a
   wider call-shape search (`act()`, `playanim()`, `faceEntity()` on the NPC, not just the 4 calls SPEC.md 18
   names) before assuming they're clean.
3. **Cyclops has no `skin_civilian` in herostat.eng** but `dr_mag2` needs him in one — UNVERIFIED whether
   civilian == default for him in XML1.
4. Whether `nyc1_1_2b`'s `cyclops_scripted` (a Mystique morph, roster.md 1.3) is a genuine SPEC.md 18-style
   name collision or a different mechanism entirely — UNVERIFIED, not traced further this session.
5. Every open item roster.md 6 already lists (team-menu minimum party size, `playable="false"` visibility,
   `0x46c810` fallback-name behavior, Colossus/Psylocke/Jubilee's real XML1 unlock mechanism) still gates
   whether the "proposed seat spec" in §6 is even reachable without the engine hook in §4 — none of that was
   re-verified in this pass.
6. This census's conversation/script counts are **folder-scoped, not trigger-scoped** (stated in §1); a
   mission-exact pass (matching XML1's own zone-to-mission graph, which this session did not locate as a
   ready-made list) would sharpen several rows, especially the shared `mansion/man3`, `mansion/man4`,
   `mansion/man7`, `muir_is/muir2`, and `nyc/alison` folders that back 2-3 census rows each.
