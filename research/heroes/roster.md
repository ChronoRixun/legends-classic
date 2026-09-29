# Topic C - XML1 campaign roster flow on the XML2 engine

Written 2026-09-27 (Fable 5.1 engineer, read-only research). Companion to `research/heroes/engine.md`
(Topic A: exe contract for herostat / team slots / unlocks) and `research/heroes/inventory.md`.
Everything below that names an XMen2.exe address was read in this session with `tools/disasm.py` on
`research/characters/ghidra/XMen2.exe` (SHA-1 identical to the retail exe) or in
`research/scripts/xml2_text.asm`; xbe addresses come from `research/scripts/xml1_text.asm` /
`xml1_api.json`. Items marked **UNVERIFIED** were not confirmed and must be tested in game before
anything is built on them.

Conventions: "slot n" = party slot 0..3 (`game+0x14+4n`); "registry" = the stats registry returned by
`0x44b8f0` (vtable `0x68544c`); "profile" = the unlock store returned by `0x48fed0`; "team menu" = XML2's
TEAM_MENU (opened by `FUN_005d8920` vt+0x68).

---

## 0. Summary and decisions

1. **XML1 seats the party from data + script; XML2 has no script function that seats or unseats a hero.**
   In XML2 the only writers of the four party slots (`game vt+0xf0` = `0x46c810`, 22 call sites) are
   `startFirstMission` (hardcoded magneto/cyclops/wolverine/storm), the team menu, the save loader,
   `restorelastzone` (from a pushed side-mission record) and the debug/ini `builddefaultteam` path.
   Scripts can only **unlock** heroes (`unlockCharacter` -> registry vt+0x2c `0x449c00`), never lock them,
   and can **open the team menu** (`loadMapChooseTeam`, `blackbirdMenu`, `extractionPointLite/Change`).
2. **XML1's New Game is Wolverine alone; Cyclops joins by script in nyc1_1_3** (`addHero`, section 1.3).
   XML2's New Game is `resetgame` -> unlock 6 (or 17) heroes by name -> `startFirstMission` seats
   magneto/cyclops/wolverine/storm -> `menus/new_game[_hard].py`. Data alone cannot give a 1-hero start.
   Options are laid out in section 3: **B (team menu at New Game, what the pipeline does today)** works and
   is proven by XML2's own `new_game_hard.py`; **C (a 25-dword pointer patch applied by the xml2-fix proxy)**
   is the only route to XML1's exact opening and to "nothing unlocked until the story unlocks it".
   This is Owen's call; both are specified.
3. **The current `addHero` emulation is broken on first use**: `extractionPointLite` shows only the hint
   dialog `dialogs/xpoint_lite_hint` and returns when game flag `danv` bit 1 is clear (`0x4a6e35-0x4a6e82`).
   In a fresh game that is always the case at nyc1_1_3, so Cyclops never joins. Fix in section 5 (T7).
4. **XML2's side-mission stack can save and restore the party** (`pushsidemission` handler `0x5f3630`
   stores zone + 4 team names + position in a 0x26c-byte record; `restorelastzone` handler `0x5f4580`
   restores the names when its argument is 0). Combined with `extractionPointChange` (the only script
   function that pushes a record) this gives an XML1-faithful flashback flow: choose the 60s/70s/Weapon X
   party, play the flashback, return to the same spot with the previous party (section 5, T9).
5. **Forced parties (Magma-solo hubs, Wolverine-solo Weapon X, astral trio, ...) cannot be enforced.**
   49 of XML1's 101 missions force heroes (`scripts.forced_hero_missions`; 25 reachable ones are
   Magma-solo). The port can only unlock the required heroes and open the team menu (already done,
   SPEC 12.6). Whether the XML2 team menu accepts a 1-hero party is **UNVERIFIED** (its confirm path only
   demands slot 0 non-empty: `0x5e36ff-0x5e3752`, else it sends `builddefaultteam`).
6. Three XML1 heroes (Colossus, Psylocke, Jubilee) are **never unlocked by any XML1 script, conversation or
   mission file** (census in 1.2); their XML1 unlock lives in the xbe (**UNVERIFIED**, candidates 1.1.3). The
   port must add explicit `unlockCharacter` calls; proposed points in section 4.

---

## 1. How XML1 controls the party

### 1.1 Data

#### 1.1.1 herostat (`xml1_loose/data/herostat.eng`)
15 heroes + `default`. Attributes that matter for the roster: `team="hero"`, `playable="true"` on all but
ProfXAstral (`playable="false"`, level 40, `xpexempt="true"`), costume slots `skin_60s/70s/future/weaponx/
civilian/magmacivilian`. Nothing in herostat says when a hero becomes available.

| name | skin | costumes | notes |
|---|---|---|---|
| Wolverine | 0301 | 60s 03, 70s 03, future 05, weaponx 02 | New Game hero |
| Cyclops | 0101 | 60s 02, 70s 03, future 05 | joins nyc1_1_3 (addHero) |
| Storm | 0401 | future 02 | conversation 1_2_36 |
| Rogue | 0701 | - | 1_2_37, 2_1_5main |
| Iceman | 0801 | 60s 03, civilian 02 | 1_2_38, 1_4_3_cam_end |
| Phoenix (Jean Grey) | 0201 | 60s 02, 70s 03 | 1_2_1_1, 1_2_35 |
| Beast | 0501 | 60s 02, future 03 | 1_2_32, 1_4_12, 2_1_4main, offerjuggernautflashback |
| Nightcrawler | 0601 | 70s 02, future 03 | 1_4_4 |
| Gambit | 1301 | future 02 | sewers/quest/fadegambit |
| Magma | 1801 | future 04, magmacivilian 03 | REQUIREDHERO of every mansion hub; never setInCampaign |
| Colossus | 0901 | 70s 03, civilian 02, future 06 | never unlocked by script (see 1.1.3) |
| Psylocke | 1201 | future 02 | never unlocked by script |
| Jubilee | 1601 | - | never unlocked by script |
| Frost (Emma) | 1501 | future 02 | REQUIREDHERO astral1 / astral1b / asteroid_rock; never setInCampaign |
| ProfXAstral | 1104 | - | `playable="false"`; REQUIREDHERO + MUSTLIVEHERO astral1 |

XML2's herostat (decoded `Data/herostat.engb`) has 20 heroes + default, every hero `playable="true"`.
The XML2 loader (`FUN_0044c030`, decomp1.c:700-736) appends **every** herostat entry to the hero list
(`+0x120dc`) regardless of `playable`; `playable` only sets bit 2 of the entry flag byte (`+0x9b40`).
Whether the XML2 team menu hides `playable="false"` heroes is **UNVERIFIED** (the roster builder
`FUN_005db590` checks loaded / team 0x1d / name length per engine.md 3.1, not bit 2 as far as read).

#### 1.1.2 Mission files (`xml1_assets/data/missions/<m>.eng`, 101 used missions)
Parsed by default.xbe at `0x84a64-0x84c86` (`scriptstart`, `mapload`, `location`, `maxheros`, `minheros`,
`maxvillains`, `minvillains`, `remote`, `teamselect`, `keepheroes`, `skinset`) and `0x8613f-0x861f5`
(`REQUIREDHERO`, `RESTRICTEDHERO`, `RECOMMENDEDHERO`, `MUSTLIVEHERO`, `*VILLAIN`). XMen2.exe contains none
of these attribute names (sweep VERIFICATION), so all of this is compiled into scripts by the pipeline.

Full table (from `research/scripts/mission_plan.json`; min/max = minheros/maxheros; R:n = number of
RESTRICTEDHERO entries). Campaign order = `missions.xml` order.

| mission | act | min/max | teamselect | keepheroes | skinset | REQUIREDHERO | notes |
|---|---|---|---|---|---|---|---|
| alison | 1 | 2/2 | false | false | default | wolverine, cyclops | New Game; Cyclops joins mid-mission |
| mansion1 | 1 | 1/1 | false | false | magmacivilian | MAGMA | first hub |
| harrp_briefing | 1 | 1/1 | false | - | civilian | MAGMA | mocap2 |
| dr_team1 | 1 | -/- | - | - | - | - | danger room team course |
| jug_fb | 1 | 4/- | false | - | 60s | Cyclops, Beast, Iceman, Phoenix | side mission (flashback) |
| haarp | 1 | 4/4 | **true** | false | default | - | first free team choice (Blackbird) |
| haarp_int | 1 | 4/4 | false | true | default | - | |
| icetunnels | 1 | 4/4 | false | false | default | - | |
| mansion2 | 1 | 1/1 | false | false | magmacivilian | MAGMA | |
| sewer_muir_briefing | 1 | 1/1 | false | - | civilian | MAGMA | mocap3 |
| dr_mag1 | 1 | 1/1 | false | - | default | Magma | side mission (Danger Room) |
| sent_fb | 1 | 4/4 | false | false | 70s | nightcrawler (+3 RECOMMENDED, R:14) | side mission (flashback) |
| sewers1 | 1 | 4/4 | **true** | false | default | - (R:1) | |
| sewers_hub | 1 | 4/4 | false | true | default | - (R:1) | |
| sewers_gambit | 1 | 4/4 | true | - | default | - (R:1) | not started from New Game |
| muir | 1 | 4/4 | false | - | default | - | |
| muir_int | 1 | 4/4 | false | - | civilian | - | |
| arbiter | 1 | -/- | false | false | default | - (R:2) | |
| arbiter_int | 2 | -/- | false | true | default | - (R:2) | |
| arbiter_flood | 3 | -/- | false | false | default | - (R:2) | |
| mansion3 | 3 | 1/1 | false | - | magmacivilian | MAGMA | |
| nuke_briefing | 3 | 1/1 | false | - | default | MAGMA | mocap5 |
| mansion3_dangerroom | 3 | 1/1 | false | false | magmacivilian | MAGMA | |
| mansion3_uniform | 3 | 1/1 | false | false | **default** | MAGMA | Magma in uniform from here |
| wx_fb_start | 3 | 1/1 | false | false | weaponx | WOLVERINE (R:16) | side mission (flashback) |
| dr_mag2 | 3 | 2/2 | false | false | civilian | MAGMA, CYCLOPS | Cyclops joins by addHero again |
| nuke | 3 | 4/4 | false | false | default | - (R:1) | |
| nuke_col | 4 | 4/4 | true | false | default | - (R:1) | |
| muir2 | 4 | 1/1 | false | false | default | magma | Magma alone on Muir |
| muir_in2 | 4 | 4/4 | **true** | false | default | - | |
| muir2_reboot | 5 | 1/1 | false | true | default | Magma | |
| mansion4 | 5 | 1/1 | false | false | default | magma | |
| grso_briefing / astral_wx_briefing / astral_briefing | 5 | 1/1 | false | - | default | MAGMA | mocap6/7 |
| mansion4_grso | 5 | 4/4 | **true** | false | default | - (R:1) | |
| grso_debriefing / mansion4_grso_done | 5 | 1/1 | false | - | default | MAGMA/magma | |
| astral1 | 5 | 3/3 | false | false | default | ProfXAstral, phoenix, frost (MUSTLIVE ProfXAstral, R:15) | |
| astral1b | 5 | 2/2 | false | false | default | phoenix, frost (R:16) | |
| old_wx | 5 | 1/1 | false | false | default | CYCLOPS | |
| secret_wx | 5 | 2/2 | false | false | default | WOLVERINE, CYCLOPS | |
| end_astral | 5 | 1/1 | false | - | default | MAGMA | |
| sentinels_mansion | 5 | 4/4 | **true** | false | default | - | |
| sentinel_mansion | 6 | 4/4 | false | - | default | - | |
| mansion5 / healer_briefing | 6 | 1/1 | false | - | default | magma/MAGMA | |
| sewers_hub2 | 6 | 4/4 | false | - | civilian | - | |
| rescue_healer | 7 | 4/4 | **true** | false | default | - | |
| mount | 7 | 4/4 | false | true | default | - | |
| mansion6 / muir_riots_grso_briefing | 7 | 1/1 | false | - | default | MAGMA | |
| muir3 | 7 | 4/4 | **true** | - | default | - | |
| muir3brig | 7 | 1/1 | false | false | default | PHOENIX | |
| riots | 7 | 4/4 | **true** | false | default | - | |
| nyc_rooftops | 7 | 1/1 | false | - | default | WOLVERINE | |
| sewers_grso | 7 | 4/4 | **true** | false | default | - | |
| sewers_marrow | 7 | 4/4 | true | - | default | - | |
| mansion7 / astral2_briefing | 8 | 1/1 | false | - | default | MAGMA | |
| astral2 | 8 | 4/4 | false | false | default | - (R:2) | |
| astral2_col | 8 | 4/4 | **true** | - | default | - (R:2) | |
| end_astral2 | 8 | 1/1 | false | - | default | MAGMA | |
| hive_ext | 8 | 4/4 | **true** | - | default | - | |
| hive1 | 8 | 4/4 | false | false | default | - | |
| hive2 | 8 | 4/4 | false | true | default | - | |
| end_hive | 8 | 1/1 | false | false | default | MAGMA | |
| mansion8 / asteroid_briefing / start_astral3 | 9 | 1/1 | false | - | default | MAGMA | |
| astral3 | 9 | 4/4 | **true** | - | default | - (R:2) | |
| astral_sk | 9 | 1/1 | false | - | default | PROFXGLADIATOR | side mission (final astral) |
| asteroid_rock | 9 | 4/4 | false | false | default | FROST | |
| asteroid_int / asteroid_mm | 9 | 4/4 | false | true | default | - | |
| asteroid_int2 / asteroid_mm2 | 9 | 4/4 | false | true | default | - | finale |
| boss_* (22), demo, nyctest2, status_meeting | 9 | various | | | | | Danger Room replays / dev |

#### 1.1.3 `data/missions/missions.xml` - `charunlock` and `defaultUnlock`
Every `<MISSION>` carries `charunlock="<mission>"` (start / mansion1 / mansion2 / sewers_gambit / dr_mag2 /
nuke / mansion4 / riots). The xbe parses `MISSIONS/MISSION name, charunlock, defaultUnlock` at `0x857cf-0x859ab`
(`defaultUnlock` compared with "true"). The value pattern (boss replays carry the mission they belong to,
e.g. `boss_mystique charunlock="start"`, `boss_toad1 charunlock="mansion1"`) suggests **UNVERIFIED**: the
roster snapshot to apply when a mission is started out of order (Danger Room disc replays / debug list).
It may also be how XML1 unlocks Colossus, Psylocke and Jubilee, which no script or conversation unlocks
(census 1.2). Not traced further; not needed by the port if unlocks are made explicit (section 4).

### 1.2 XML1 script API for the party (default.xbe) and every campaign call site

| function | xbe handler | what it does (as far as read) | XML2 equivalent |
|---|---|---|---|
| `setInCampaign(hero, "TRUE")` | `0x99460` | `_stricmp(arg2,"TRUE")` then registry vt+0x2c(vt+0x3c(name)) = unlock (scripts VERIFICATION) | `unlockCharacter(hero, "")` (`0x49f520`, same registry calls) |
| `addHero(hero)` | `0x99a00` | `game(0x72cf0)->vt+0x110(name)`: seats the hero in the party | **none** (see 2.1) |
| `removeFromGroup(hero)` | `0x9fbd0` | entity lookup (`0x9ae60`/`0x6bf80`) then game call: unseats | **none** |
| `setGroupLeader(hero)` | `0x9fcd0` | `game->vt+0xd4(0, &name)` | none (only in a commented line) |
| `enterSoloMode(ent)` / `exitSoloMode(ent)` / `soloModeCheck(ent)` | `0x9eef0` / `0x9ef70` / `0x9eff0` | entity must be a character (class bit `[0x485878]+0x21`); `0x33a70(1/0)` toggles solo | **none** |
| `setPowerStatus(ent, power, "TRUE")` | `0x9db60` | enables/disables one power on an entity | **none** |
| `blackbirdMenu(a, code, b)` | `0x9a370` | `"setblackbirdparms %s %s %s FALSE FALSE"` then menu | `blackbirdMenu` `0x4a0640`, same command (`0x68d25c`) + `FUN_005d8920` vt+0x68 |
| `extractionPointLite(ent, s,s,s,s,s)` | `0x9f4a0` | X-traction lite (6 args) | `extractionPointLite(ent,s,s,s)` `0x4a6d80` (4 args) |
| `loadMap(zone)` | `0x9a850` | `"loadmap %s"` | `loadMapKeepTeam` (`"loadmap %s 0 0"`) |
| `beginSideMission(m)` / `endSideMission(s)` | `0x18dd70` / `0x18df20` (console) | push record + beginmission / pop + restore (== XML2 `restorelastzone` handler `0x5f4580`) | `extractionPointChange` + `restorelastzone` (2.4) |

**Census of every party call in XML1 (loose + assets trees, all quoting styles, case-insensitive):**

| call | count | files (zone -> trigger) |
|---|---|---|
| `setInCampaign('beast','TRUE')` | 4 | conv `mansion/man1a/1_2_32` (subbasement1a), conv `mansion/man2/1_4_12` (subbasement2 and jugrnt01 via `jugpain.py`), conv `mansion/man3/2_1_4main` (subbasement3b), script `mansion/man1b/offerjuggernautflashback.py` (run by conv 1_4_12 `%END%` response) |
| `setInCampaign('rogue','TRUE')` | 2 | conv `mansion/man1a/1_2_37` (mansion1a_1), conv `mansion/man3/2_1_5main` (mansion3_1) |
| `setInCampaign('phoenix','TRUE')` | 2 | conv `mansion/man1a/1_2_1_1` (mansion1a_1), conv `mansion/man1a/1_2_35` (subbasement1a) |
| `setInCampaign('iceman','TRUE')` | 2 | conv `mansion/man1a/1_2_38` (mansion1a_1), script `mansion/man2/1_4_3_cam_end.py` (conv 1_4_3, mansion2) |
| `setInCampaign('cyclops','TRUE')` | 2 | scripts `nyc/alison/add_cyclops.py`, `mansion/dr_mag2/blob/add_cyclops.py` |
| `setInCampaign('angel','TRUE')` | 2 | conv `mansion/man2/1_4_2`, `1_4_2_5` (mansion_back2) - Angel is not an XML1 hero: no-op for the roster |
| `setInCampaign('storm','TRUE')` | 1 | conv `mansion/man1a/1_2_36` (mansion1a_2) |
| `setInCampaign('profx','TRUE')` | 1 | conv `mansion/man1a/1_2_1_1` - not a hero (ProfXAstral is), no-op |
| `setInCampaign('nightcrawler','TRUE')` | 1 | conv `mansion/man2/1_4_4` (mansion2_1, `1_4_4_conversation_start.py`) |
| `setInCampaign('gambit','TRUE')` | 1 | script `sewers/quest/fadegambit.py` (conv `sewers/quest/1_5_5` -> `missionComplete('sewers/quest/fadeGambit')`, zone sewers1_2_4) |
| `addHero("cyclops")` | 2 | `nyc/alison/add_cyclops.py` (nyc1_1_3 `trigger_touch03`, actontouch, actcountremove=1, acttargets=enable_target01), `mansion/dr_mag2/blob/add_cyclops.py` (mag_nyc4, same trigger) |
| `removeFromGroup("phoenix")` | 1 | `muir_is/muir3/reallyendmuir3.py` (muir_brig `trigger_use01`); XML1 comment: workaround for "next zone forces Jean into slot 1" |
| `removeFromGroup("cyclops")`, `setGroupLeader("alison")` | 1 each | `muir_is/muir2/control_alsion.py`, **commented out** |
| `exitSoloMode("_ACTIVE_HERO_")` | 4 | `astral/astralbridge_1inmap.py`, `_1inmap_camera.py`, `_2inmap_a.py`, `_2inmap_b.py` |
| `enterSoloMode('_ACTIVATOR_')` (inline `actscript` on `trigger_solo`, `actleader="true"`) | 18 zones | astral1_2, astral1_3, astral2_2, astral2_3, astral3_4, arb3_2, arb3_3, arb3_4, icetunnel1, icetunnel2, hive2_2_4, nuke1_2, nuke1_3, nuke1_4, nuke2_2a, nyc3_2_2, sewers1_1_4, sewers3_1_3 |
| `setPowerStatus("_ACTIVE_HERO_","power_smash","TRUE")` | 1 | `mansion/dr_mag/dr_mag01.py` (Magma Danger Room tutorial) |
| `blackbirdMenu(...)` | 50 files | all in `xml1_assets/scripts/missions/*.py` (the XML1 mission `scriptstart` bodies) |
| `beginSideMission` | 8 sites | `mansion/man1b/loadjuggernaut.py` (jug_fb), `mansion/man2/loadsentinel.py` (sent_fb), conv `mansion/man3/2_1_15_meet_wolverine` (`wx_fb_start`), dr_mag1 start, ... |
| `endSideMission` | 8 sites | `weapon_x/wfb/end_fb.py`, `nyc/fb/nycfb4_finish.py`, `mansion/dr_mag/fmvexit.py`, `muir_is/muir2/endreboot.py`, `astral/savepx/shadowking_defeated.py`, `astral/savepx/xcrystal_destroyed.py`, ... |

Never unlocked anywhere: **Colossus, Psylocke, Jubilee, Magma, Frost, Wolverine**. Wolverine/Magma/Frost are
REQUIREDHERO of missions (alison; every hub; astral1/asteroid_rock) and XML1's `beginmission` evidently
seats required heroes that are in the campaign; for Colossus/Psylocke/Jubilee no XML1 mechanism was found
in data (**UNVERIFIED**, see 1.1.3). Observable evidence of when they arrive: Colossus is an NPC in
`muir_is/muir2/muir_in2` (conv `2_4_11b`: the line inviting Colossus to join) and `mansion/man4/mansion_back4`;
Jubilee in `mansion/man2/mansion_back2` and `mansion/man3/mansion3_1`; Psylocke in `mansion/man7/mansion7_1` and
`nyc/riots/nyc3_1_2` (conversations `mansion/man3/2_1_12_5*` and `mansion/man7/3_6_4` speak as `%PSYLOCKE%`).

### 1.3 The XML1 opening and where the roster opens up (script/data evidence)

1. **New Game** (xbe `newgame` console handler `0x18d0b0`): `resetgame`, then `"beginmission alison"` (`0x18d118`).
   `alison.eng`: `minheros="2" maxheros="2"`, REQUIREDHERO wolverine + cyclops, `teamselect="false"`.
   The party at start is **Wolverine alone**: Cyclops is an NPC (`nyc1_1_2b` `cyclops_scripted` = Mystique
   morph; `nyc1_1_3` spawner `sp_cyclops01` character="cyclops", `instantspawn`) until `trigger_touch03`
   in nyc1_1_3 runs `nyc/alison/add_cyclops.py`: voice line, `setInCampaign("cyclops","TRUE")`,
   `addHero("cyclops")`, popup `dialogs/tut15`. So XML1's beginmission seats only required heroes already
   "in campaign" (inference; consistent with `charunlock="start"`).
2. `nyc/alison/blackbird_brief1.py` -> `mission("alison","COMPLETE")`, `loadZone("mocap/mocap1/briefing_1_1_6_5")`;
   the briefing ends with `beginMission("mansion1")`.
3. **mansion1** (Magma solo, civilian skin). Unlocks by talking to X-Men: Rogue (1_2_37), Iceman (1_2_38),
   Phoenix (1_2_1_1) in mansion1a_1; Storm (1_2_36) in mansion1a_2; Beast (1_2_32) and Phoenix (1_2_35) in
   subbasement1a. `mansion/man1a/begin_haarp.py` -> `beginMission("haarp")` (via `harrp_briefing`, mocap2).
4. **haarp** is the first `teamselect="true"` mission: XML1 opens the Blackbird team select
   (`missions/haarp.py` in xml1_assets calls `blackbirdMenu(...)`). From here the player chooses 4 of the
   unlocked heroes (Wolverine, Cyclops, Storm, Rogue, Iceman, Phoenix, Beast if all conversations were had).
5. **mansion2** (Magma solo): Nightcrawler (1_4_4), Iceman again (1_4_3_cam_end), Beast (1_4_12); side
   missions: **sent_fb** (Nightcrawler required, 70s skins, `mansion/man2/loadsentinel.py`), **jug_fb**
   (Cyclops/Beast/Iceman/Phoenix, 60s skins, `mansion/man1b/loadjuggernaut.py` offered by
   `offerjuggernautflashback.py`), **dr_mag1** (Magma solo Danger Room, `setPowerStatus` tutorial,
   `fmvexit.py` -> `endSideMission("TRUE")`). `mansion/man2/chose_mission.py` offers sewers or Muir.
6. **sewers**: Gambit freed -> `sewers/quest/fadegambit.py`: `setInCampaign("gambit")`, `loadMap(briefing_1_7_1)`.
7. **mansion3**: Beast (2_1_4main), Rogue (2_1_5main) again; **wx_fb_start** (Wolverine solo, weaponx skin;
   `end_fb.py` -> `endSideMission("FALSE")`); **mansion3_uniform** (Magma in default skin from here);
   **dr_mag2** (Magma + Cyclops civilian; `mag_nyc4` `trigger_touch03` -> `mansion/dr_mag2/blob/add_cyclops.py`).
8. **muir2** (Magma alone; `control_alsion.py` "set Alison as the playable character again"), **muir2_reboot**.
9. **mansion4** (Colossus and Frost present as NPCs) -> **astral1** (ProfXAstral + Phoenix + Frost, 3/3),
   **astral1b** (Phoenix + Frost), **old_wx** (Cyclops solo), **secret_wx** (Wolverine + Cyclops).
10. Later solo/forced: **muir3brig** (Phoenix; `reallyendmuir3.py` removes her afterwards), **nyc_rooftops**
    (Wolverine), **astral_sk** (ProfXGladiator - an npcstat character seated as a hero), **asteroid_rock**
    (Frost required, 4/4).

### 1.4 Solo mode
`trigger_solo` entities (`boxcollision`, `actontouch`, `actmatchteam`, `actleader="true"`,
`actinactivedelay="0.1"`, `actscript="enterSoloMode('_ACTIVATOR_')"`) exist in the 18 zones listed in 1.2.
Only the four astral bridge scripts call `exitSoloMode`; the sequence there (astral1_2.eng): leader touches
`trig_solo1` -> solo -> `act("bridge_anim01")`, `act("bridgespawner1")` (spawns `astralbridge2_special`),
`remove(trig_solo1)`, `remove(plat1)` (a `moverent` platform), `exitSoloMode("_ACTIVE_HERO_")`. How the other
14 zones leave solo mode is **UNVERIFIED** (no script; presumably automatic). XMen2.exe parses `actleader`
(string `0x682138`), `actinactivedelay` (`0x682268`), `actmatchteam`, `actteamplayer`, `actcountremove`, so the
trigger itself converts; only the call is lost.

### 1.5 Danger Room
`xml1_loose/data/dangerroom.eng`: 15 ARENA zones (`arena/*`), courses with `hero="..."` forcing a solo hero
(magma x10, gambit/nightcrawler/rogue x2, beast/colossus/cyclops/frost/iceman/jubilee/phoenix/psylocke/storm/
wolverine x1). XMen2.exe's dangerroom loader also reads a COURSE `hero` attribute (`0x4d460c` push "hero" ->
registry vt+0x3c) and XML2's own `Data/dangerroom.engb` uses it (CHCYC cyclops, CHGAM gambit, CHICE iceman,
CHTOA toad, CHPHO phoenix), so **forced heroes in Danger Room courses are supported by XML2 data**. The
pipeline currently keeps XML2's dangerroom table (SPEC section 5 "deferred").

### 1.6 What the pipeline does with each call today

Research output (`research/scripts/rewrite_scripts.py`, installed by `tools/xml1build/scripts.py` and
post-processed by `scripts_transform.py`):

| XML1 call | today's output | verdict |
|---|---|---|
| `setInCampaign(h,'TRUE')` | `unlockCharacter("h", "" )` (scripts and inline data, `out/inline_rewrites.json`) | correct (same registry calls) |
| `setInCampaign(h,'FALSE')` | comment | correct (no-op in XML1 too) |
| `addHero(h)` | `unlockCharacter("h","")` x2 + `extractionPointLite("_ACTIVE_HERO_", "true", "false", "false" )` | **broken on first use** (danv hint gate, 2.5); needs T7 |
| `removeFromGroup`, `setGroupLeader`, `setPowerStatus`, `enterSoloMode`, `exitSoloMode` | `# ( "x1 removed: <call>" )` + `debug("x1: removed statement" )`; inline `enterSoloMode('_ACTIVATOR_')` -> `debug('x1: removed statement')` | acceptable for removeFromGroup/setGroupLeader/setPowerStatus; solo mode: see T10 |
| `beginMission(m)` | generated body: clear packed vars, `setCurrentAct`, objective resets, `unlockCharacter` for each REQUIREDHERO, then scriptstart body or `loadMapKeepTeam(mapload)` / `loadMapChooseTeam` when `teamselect="true"`; `choose_team_in_bodies` turns the load of the 49 forced-hero missions into `loadMapChooseTeam` (73 starts) | works; REQUIRED unlocks make Magma selectable from mansion1 (XML1: from mansion3_uniform, **UNVERIFIED**) |
| `blackbirdMenu(a,"loadMap('z')",b)` | kept (`loadMapKeepTeam` inside the code) or `loadMapChooseTeam("z")` with `--blackbird chooseteam` | both open the same team menu (2.3) |
| `beginSideMission(s)` | comment + the begin body of `s` | team not saved; see T9 |
| `endSideMission(x)` | `setCurrentAct(parent)` + `loadZone(caller_zone, "")` (fallback `restorelastzone("1")`) | party stays the flashback party; position lost; see T9 |
| New Game | `Scripts/menus/new_game.py` = begin_alison body: clears, `setCurrentAct(1)`, objectives, `unlockCharacter("wolverine")`, `unlockCharacter("cyclops")`, `startMovie("r102")`, `loadMapChooseTeam("nyc/alison/nyc1_1_1")` (SPEC 12.6); `--start-zone`/`--tour` hooks use `loadMapKeepTeam` | see section 3 |
| `loadMapAddTeam` | not called by XML1 | XML2's version sends `"resetgame"` first (`0x4a0bf8`) - must never be emitted (lint) |

---

## 2. XML2: the mechanisms that exist (verified reads)

### 2.1 Party slots and who writes them
- Slot setter `game vt+0xf0` = `0x46c810` (slot 0..3, interned lowercase name; unknown names go to the
  registry's fallback entry via `0x4498d0`/`0x448c60` - **UNVERIFIED what spawns**, avoid). Getter `vt+0xe0`;
  `vt+0x114` = slot index of a name or -1 (`0x5f358e`); `vt+0xf8/vt+0xfc` = a pending-name array applied at
  zone load (`0x486e60-0x486eb8`); `0x486dd0` spawns each non-empty slot at zone load.
- The 22 callers of `vt+0xf0`: `startFirstMission` (`0x4a7b73/0x4a7bad/0x4a7be7/0x4a7c21`), save loader
  (`0x484c96`, 4 x 0x20-byte names), zone load pending array (`0x486e8b`), danger-room/course team builder
  (`0x4d1a5b`, `0x4d1b7e`, `0x4d2011-0x4d2368`: default wolverine/colossus/storm/bishop read from ini
  `[HERO] Name1..4` `0x6900dc/0x6900e4..`), team menu (`0x5e2539`, `0x5e3868`), resetgame clearing
  (`0x5f3091`), `builddefaultteam` (`0x5f35e0`), `restorelastzone` (`0x5f465a`).
  **None is a registered script function except `startFirstMission` itself** (table `0x68a908`).
- `setteam(s,a)` (`0x4a3a00`) sets an entity's combat team from `BEHAVED_TEAM_NONE/HERO/ENEMY/ALT_ENEMY`
  (table `0x68a860`), not the party. `setTeamInvisible(s,s)` (`0x4a04d0`) hides a whole combat team.

### 2.2 Unlocks
- Registry entry flag byte `+0x9b40` (stride 0x1c): bit0 = herostat entry, **bit1 = unlocked**
  (`0x449c00`: `or bl,2`, appends to list `+0x11e84`, count `+0x120d8`, then profile vt+0x28(idx)),
  bit2 = `playable` (decomp1.c:717-727), bit4 = loaded. Getters vt+0x7c/0x84/0x80 (`0x44b7c0/0x44b800/0x44b7e0`).
- Only "lock all" is `0x449540` (registry vt+0x30, clears bit1 for the whole list), called **only** from
  `resetgame` (`0x5f2f96`). No script function locks a hero.
- Script API: `unlockCharacter(s,n)` `0x49f520` (name -> vt+0x3c -> vt+0x2c; 2nd arg costume via table
  `0x6d8aa0`; empty name + costume = costume for every hero), `isCharacterUnlocked(a)` `0x49f610`
  (profile vt+0x38). The team menu queries profile vt+0x38 at `0x5e3d81`, `0x5e5319`, `0x5e55cb`.
- **New Game default unlocks** in the `resetgame` body (`0x5f2e70`, unlocks by name at `0x5f30c2-0x5f32fb`):
  magneto, bishop, juggernaut, wolverine, cyclops, storm, and if `byte [0x6f3c2d] == 0` also colossus,
  sunfire, nightcrawler, gambit, rogue, phoenix, iceman, toad, scarletwitch, pyro_hero, sabretooth_hero;
  then `"runscript unlockCharacter('','astonishing')"` (`0x685538`). Retail value of `0x6f3c2d` is
  **UNVERIFIED** (set to 1 at `0x403269`; read at 25 sites, several in UI code). In-game check: count the
  heroes offered by the first team menu. **Consequence for the port:** any XML1 hero whose stats name is in
  this list (wolverine, cyclops, storm, and probably colossus, nightcrawler, gambit, rogue, phoenix, iceman)
  is unlocked at New Game by the exe before any script runs, and cannot be re-locked from script.

### 2.3 New Game sequence and the map-load family
- Menu "New Game" -> console `newgame` (`0x5f3610`): `resetgame(0)` then `startgamedialog` (difficulty) ->
  `0x5f3c20`: `resetgame(0)` again, registry vt+0xc0(0), then `"runscript startFirstMission()"` (`0x5f3d19`,
  when `[0x612be0]+0x3e0 == 1`; `== 2` is the Danger Room start `"set drmode 1;openmenu danger_room"` `0x68d184`).
- `startFirstMission` (`0x4a7b10`): game vt+0x280(1) (bit 2 of game+0x616), registry vt+0xc0(1)
  (`byte [0x6d970c] = 1`), slots 0..3 = "magneto" `0x682504`, "cyclops" `0x682548`, "wolverine" `0x6824a8`,
  "storm" `0x6824c4` (each pushed twice: strlen `0x602120` + hash `0x602140`/`0x41a320`), then
  `"runscript menus/new_game"` (`0x68d63c`) if difficulty (`game+0x60c`, vt+0x268) < 2 else
  `"runscript menus/new_game_hard"` (`0x68d61c`).
- Console `loadmap <zone> <a> <b>` (`0x5f4770`, both ints via `atoi` `0x67233c`):
  `b != 0` -> zone name stored at `0x8b12cc`, flags `0x8b134c |= 4`, team menu opened (`FUN_005d8920` vt+0x68)
  and the load happens on confirm; `b == 0` -> if `a != 0` restore the top side-mission record's position
  (`0x5f46f0`), then game vt+0x150 (the real load), then pop the record (`0x5f44a0`).
  Script wrappers: `loadMapKeepTeam` = `"loadmap %s 0 0"` (`0x4a0ce3`), `loadMapChooseTeam` = `"loadmap %s 0 1"`
  (`0x4a0d53`), `loadMap` = `"loadmapaddteam %s"` (unregistered, no-op), **`loadMapAddTeam` = `"resetgame"` +
  `"loadmapaddteam %s"` (`0x4a0bf8/0x4a0c07`: resets the whole game)**.
- `blackbirdMenu(a, code, b)` (`0x4a0640`) = `"setblackbirdparms %s %s %s FALSE FALSE"` + the same team menu
  open (vt+0x68 at `0x4a06c4`); the stored code runs afterwards via `"runscript %s"` (`0x5e08d4`).
- Team menu confirm (`0x5e36ff-0x5e3752`): if slot 0 is empty it sends `builddefaultteam` (`0x6a2f68`), i.e.
  the menu tolerates empty slots 1..3 -> a 1-hero party is **probably** allowed (**UNVERIFIED** in game).
- `builddefaultteam` (`0x5f3be0` -> `0x5f3330`): ini `[HERO]` `RandomHeroes` or `Name1..Name4` with defaults
  magneto/cyclops/wolverine/bishop; fills empty slots with unlocked heroes not already on the team. Not on the
  New Game path; a data knob only for the menu fallback (which ini file: **UNVERIFIED**; neither `xmen.ini`
  nor `build.ini` has a `[HERO]` section).

### 2.4 Side missions: the party can be saved and restored
- `pushsidemission <entityid>` (`0x5f3630`): if fewer than 2 records (`cmp [eax+0x4dc],2`) and a zone is
  loaded, captures the current state into a 0x26c-byte record (`0x4874b0`, return entity `0x48a170`):
  zone name, **4 team names (0x20 bytes each at +0x134)**, position.
- `restorelastzone <arg>` (`0x5f4580`): with `atoi(arg) == 0` it writes the 4 saved names back with
  `vt+0xf0` (`0x5f4612-0x5f4667`), then sends `"loadmap <savedzone> 1"` (`0x6a3744`) -> position restored,
  record popped. With `arg != 0` the current party is kept.
- Script access: `restorelastzone(s)` (`0x4a0760`, `"restorelastzone %s"` `0x68d284`) and
  `extractionPointChange(a, i)` (`0x4a7020`): entity `a` must be a character (class bit `[0x718448]+0x24`);
  sends `"pushsidemission <a's id>"` (`0x68d584`) and `"setblackbirdparms FALSE restorelastzone('1') TRUE TRUE %i"`
  (`0x68d548`), then opens the team menu. Net effect: **save team + spot, let the player re-pick the team,
  reload the same zone at the same spot with the new team, record still on the stack** (its `restorelastzone('1')`
  keeps the new team and pops - so a *later* `restorelastzone("0")` needs its own record; see T9 for the
  exact sequence). Max 2 records; console queue holds at most 2 pending commands and 127-char commands
  (scripts VERIFICATION) - `extractionPointChange` uses exactly 2.

### 2.5 `extractionPointLite(ent, s1, s2, s3)` (`0x4a6d80`)
- `ent` must resolve to a character entity (else return at `0x4a7006`).
- **Hint gate**: `getGameFlag("danv",1)` (`0x4a6e3e`); when clear it sets the flag (`0x4a6e5e`), shows
  `dialogs/dialogs/xpoint_lite_hint.xml` (`0x4a6e63`) and **returns without opening any menu**.
- Otherwise builds the X-traction lite dialog (string 2000 "X-Jet Xtraction"); `s1 == "TRUE"` adds option
  2001 "Change Team" whose code is `extractionPointChange(<ent id>,<s3=="TRUE">)` (`0x68d4f8`); `s2`/`s3`
  become the other flags (save / danger room per XML2 strings 2002-2005, exact mapping **UNVERIFIED**).
- Therefore `setGameFlag("danv", 1, 1)` before the call skips the hint (registered script call `0x4a5e10`);
  `danv` is one of the four engine game-flag names the pipeline already reserves (`scripts.ENGINE_GAME_FLAGS`).

### 2.6 Helpers usable for emulation (all registered, `xml2_api.json`)
`moveHeroesToEnt(a)` `0x4a2560` (iterates the party via game vt+0x120 and places the heroes around the
entity, radii 10/40), `setallaiactive(s)` `0x49ecc0`, `setAIActive(a,s)`, `controlPlayerHeroWithAI(f)`
`0x4a4200`, `setInvisible(a,s)`, `remove(a,a)`, `killEntitySilent(a)`, `setEnable(a,s)`, `getName(a)`,
`isActorOnTeam(a)` `0x4a5a70`, `setSkin(a,s)` `0x4a3dc0`, `copyOriginAndAngles(a,a)`, `getGameFlag/setGameFlag`.

### 2.7 How XML2's own campaign handles the roster (real scripts, `<XML2 folder>/scripts`)
XML2 never seats a hero from script; it unlocks and lets the X-traction/team menu do the rest:
- `scripts/menus/new_game_hard.py`: `startMovie("cine01","waitSignal")` / `waitsignal("waitSignal")` /
  `loadMapChooseTeam("act0/tutorial/tutorial1")` - the retail proof that the team menu works before the first
  zone (normal difficulty uses `loadMapKeepTeam` with the four hardcoded heroes).
- `scripts/act5/apocalypse/apoc_death.py:121`: `unlockCharacter("deadpool", "" )`;
  `scripts/bonus/b5_unlock_ironman.PY`: `setGameFlag("bonus5", 2, 1 )`, `unlockCharacter("ironman", "" )`,
  `setSkin("tony", "1501" )`, effect + `playanim` + `startConversation("bonus/5_ironman5_0010c")` - a hero
  "joins" by being unlocked while his NPC stands there; he is only in the party after the next X-traction.
- `scripts/act1/genosha/genosha5/is_magneto_on_team.PY`: `magnetoOnTeam = isActorOnTeam("magneto" )` gating
  `allowConversation`; `scripts/act4/mansion/mansion1.py:98`: `a = isActorOnTeam("colossus" )` -> hint type.
- `scripts/act4/mansion/mansion1.py`, `act1/sanctuary/sanctuary1.py`, ...: `extractionUnlock("")` at hub entry;
  `loadpoints/*.py`: `extractionUnlock("act4/mansion/mansion1")` (world-map destinations).
- `resetgame` itself runs `runscript unlockCharacter('','astonishing')` (costume unlock for all).

### 2.8 Danger Room
XML2 COURSE `hero=` is honoured by the exe (`0x4d460c`), section 1.5.

---

## 3. The New Game start: options and evidence

Facts that constrain every option: (i) `startFirstMission` writes four names before `new_game.py` runs
(2.3); (ii) `resetgame` unlocks by name before that (2.2); (iii) a party name that is not a herostat name
reaches `0x46c810`'s fallback path - **UNVERIFIED** and to be avoided (engine.md 2.1 agrees); (iv) the
team menu rewrites all four slots on confirm, so with `loadMapChooseTeam` the hardcoded names never spawn.

| option | what | evidence it works | fidelity | cost / risk |
|---|---|---|---|---|
| **A. Name aliasing** | give the converted herostat entries whose *names* are `magneto`, `cyclops`, `wolverine`, `storm` | the exe only compares names (`0x46c810`, `0x486dd0`); XML1 has cyclops/wolverine/storm; `magneto` would be an extra entry | a 4-hero start (XML2's), not XML1's Wolverine-alone; a duplicate hero (e.g. `magneto` as a Wolverine clone) gives two Wolverines | cheap; useful only as a **safety net** so New Game never spawns an unknown name (keep a `magneto` filler among the 21 herostat entries or point the hook at the team menu) |
| **B. Team menu at New Game (current)** | `new_game.py` ends in `loadMapChooseTeam("nyc/alison/nyc1_1_1")`; the player picks Wolverine (SPEC 12.6) | XML2 retail `new_game_hard.py` does exactly this; the menu's confirm rewrites all slots then `loadmap %s 1` | player *can* start with Wolverine alone (if the menu allows 1 hero - UNVERIFIED) but can also take 4; the exe has pre-unlocked cyclops/storm (+ up to 7 more XML1 names if `0x6f3c2d == 0`) so they are offered | no engine change; `--start-zone`/`--tour` hooks still spawn the four names via `loadMapKeepTeam` (they need the A safety net or a ChooseTeam variant) |
| **C. Proxy/exe pointer patch** | in the xml2-fix `dinput.dll` proxy (already the mod loader), when the XML1 mod is active, patch 8 + 17 dwords: `startFirstMission` slot names -> slot0 "wolverine", slots 1-3 "" ; `resetgame` default-unlock names -> "" | `0x46c810` treats an empty name as "clear slot" (`0x46c8dd cmp byte [eax],0 -> je`), `0x486dd0` spawns only non-empty slots; unlock of "" -> vt+0x3c returns 0 -> vt+0x2c returns at `0x449c08`; the empty-string constant `0x681968` already serves as "no hero" (`0x486e91`, `0x46c84c`) | **exact XML1 opening**: Wolverine alone, nothing unlocked until `unlockCharacter` says so, `new_game.py` can use `loadMapKeepTeam` | it is a code patch (Owen decided "no exe patch" so far; must be conditional on the mod); 25 dwords, in-memory, reversible; the astonishing-costume unlock stays (harmless) |
| D. Rename XML1 heroes to avoid the exe's name list | e.g. `x1storm` | would dodge the default unlocks | breaks `%STORM%` speaker tokens, zone `character="storm"` spawns, `unlockCharacter("storm")` everywhere | rejected |
| E. Ship a savegame as "New Game" | `loadgame` restores the party (`0x484c96`) | data-only | save format/paths unknown; profile-bound; hacky | rejected |

**Patch table for option C** (file offsets in XMen2.exe, all inside `.text`, raw offset = VA - 0x400000):

| purpose | imm32 operand VA (file offset) | now -> | set to |
|---|---|---|---|
| startFirstMission slot 0 | `0x4a7b42` (0xa7b42), `0x4a7b51` (0xa7b51) | `0x682504` "magneto" | `0x6824a8` "wolverine" |
| slot 1 | `0x4a7b7c` (0xa7b7c), `0x4a7b8b` (0xa7b8b) | `0x682548` "cyclops" | `0x681968` "" |
| slot 2 | `0x4a7bb6` (0xa7bb6), `0x4a7bc5` (0xa7bc5) | `0x6824a8` "wolverine" | `0x681968` "" |
| slot 3 | `0x4a7bf0` (0xa7bf0), `0x4a7bff` (0xa7bff) | `0x6824c4` "storm" | `0x681968` "" |
| resetgame default unlocks (17 `push imm32`, operand = push VA + 1) | `0x5f30c3, 0x5f30e5, 0x5f3107, 0x5f3129, 0x5f314b, 0x5f316d, 0x5f319b, 0x5f31bd, 0x5f31df, 0x5f3201, 0x5f3223, 0x5f3245, 0x5f3267, 0x5f3289, 0x5f32ab, 0x5f32cd, 0x5f32ef` (file 0x1f30c3 ... 0x1f32ef) | magneto, bishop, juggernaut, wolverine, cyclops, storm, colossus, sunfire, nightcrawler, gambit, rogue, phoenix, iceman, toad, scarletwitch, pyro_hero, sabretooth_hero | `0x681968` "" (each) |

Under C, `begin_alison` must not emit `unlockCharacter("cyclops")` (T8) or Cyclops is selectable before he
joins; Wolverine's unlock stays. Under B, that line is moot (the exe unlocked him already).

**Recommendation**: keep B as the shipped default now (it works and is retail-proven), implement T7-T9 (they
are needed under both), and put C in front of Owen as the one change that restores the XML1 opening and the
"locked until met" roster. If C is accepted, the hook becomes `loadMapKeepTeam("nyc/alison/nyc1_1_1")` after
the r102 movie and the alison zones play exactly as XML1 (Wolverine alone, Cyclops joins in nyc1_1_3).

---

## 4. Mission-by-mission roster availability and the port's mechanism

"XML1 party" = what XML1 seats; "available" = heroes newly in campaign after this step; "today" = the
pipeline's current output; "proposed" = with the section 5 rewrites. Acts are the pipeline's 9 packed acts.

| # | mission (act) | zones | XML1 party rule | roster change (XML1) | today | proposed |
|---|---|---|---|---|---|---|
| 1 | New Game / alison (1) | nyc1_1_1..1_1_5 | Wolverine alone; Cyclops joins at nyc1_1_3 | +Cyclops (addHero) | hook: unlock wolverine+cyclops, r102, `loadMapChooseTeam(nyc1_1_1)`; add_cyclops = unlock + `extractionPointLite` (fails first time) | B: unchanged hook; C: `loadMapKeepTeam`, no cyclops unlock (T8). add_cyclops -> T7 (unlock, remove NPC, guard flag, `extractionPointChange`) + zone-script guard in nyc1_1_3 |
| 2 | briefing_1_1_6_5 (1) | mocap1 | cutscene | - | `loadZone` then `beginMission(mansion1)` body | unchanged |
| 3 | mansion1 (1) | mansion1a_1/1a_2, subbasement1a, hangar1a | Magma solo, civilian skin | +Storm, Rogue, Iceman, Phoenix, Beast (conversations); Magma REQUIRED | `unlockCharacter("magma")` + `loadMapChooseTeam` (forced); conversations -> `unlockCharacter` | unchanged; Magma-solo cannot be enforced (design note); Magma becomes selectable here (XML1: mansion3_uniform, UNVERIFIED) |
| 4 | harrp_briefing -> haarp (1) | mocap2; haarp_ext01.. | first Blackbird team select (teamselect) | - | `blackbirdMenu("FALSE","loadMapKeepTeam('haarp/ext/haarp_ext01')","TRUE")` (or ChooseTeam with `--blackbird chooseteam`) | unchanged (same menu either way, 2.3) |
| 5 | haarp_int, icetunnels (1) | haarp2_*, icetunnel1/2 | keepheroes; solo triggers in icetunnels | - | `loadMapKeepTeam`; solo dropped | unchanged; icetunnel solo stays dropped (no exit script, 1.4) |
| 6 | mansion2 (1) | mansion_back2, mansion2_1/2_2, subbasement2 | Magma solo | +Nightcrawler, Iceman, Beast; Angel/profx no-ops; Jubilee appears as NPC | as mansion1 | unchanged; optional `unlockCharacter("jubilee")` at mansion2 start (decision, 1.2) |
| 7 | sent_fb (1, side) | nyc_fb1..4 | Nightcrawler + 3, 70s skins | - | begin body: unlock nightcrawler, `loadMapChooseTeam`; `nycfb4_finish` -> `loadZone(subbasement2)`... | T9 flashback flow: save party (`extractionPointChange`), pick team, play, `restorelastzone("0")` back to the exact spot with the old party; costume forcing -> Topic B (`unlockCharacter("", "70s")` makes the 70s costume selectable) |
| 8 | jug_fb (1, side) | jugrnt01 | Cyclops, Beast, Iceman, Phoenix, 60s | - | begin body: 4 unlocks, `loadMapChooseTeam` (forced); end `loadZone` | T9 |
| 9 | dr_mag1 (1, side) | dr_mag01..03 | Magma solo Danger Room | - | `loadMapChooseTeam`; `setPowerStatus` dropped; `fmvexit` -> `loadZone(subbasement2)` | T9; `setPowerStatus` stays dropped (T12) |
| 10 | sewers1 / sewers_hub / sewers_gambit (1) | sewers1_*, sewers_hub | teamselect / keepheroes | +Gambit (fadegambit) | blackbirdMenu / KeepTeam; `unlockCharacter("gambit")` | unchanged |
| 11 | muir, muir_int (1) | muir_* | 4/4; muir_int civilian skinset | - | KeepTeam | unchanged |
| 12 | arbiter, arbiter_int, arbiter_flood (1-3) | arb* | R:2 restricted; solo triggers arb3_2..3_4 | - | KeepTeam; solo dropped | solo: T10 only where an exit exists (none here -> stays dropped) |
| 13 | mansion3 (3) | mansion3_1/3_2, subbasement3b, danger_room | Magma solo; mansion3_uniform switches skinset to default | +Beast, Rogue (again) | ChooseTeam (forced) | unchanged |
| 14 | wx_fb_start (3, side) | wx1_* | Wolverine solo, weaponx skin | - | unlock wolverine, ChooseTeam; `end_fb` -> `loadZone(mansion/man3/hangar3)` | T9 |
| 15 | dr_mag2 (3, side) | mag_nyc1..4 | Magma + Cyclops (civilian); Cyclops joins by addHero at mag_nyc4 | - | unlock magma+cyclops, KeepTeam (forced? maxheros 2 -> ChooseTeam); add_cyclops as #1 | T7 (guard bit 2) + T9 |
| 16 | nuke, nuke_col (3-4) | nuke1_*, nuke2_* | 4/4; solo triggers nuke1_2..2_2a | - | KeepTeam / ChooseTeam | unchanged; solo stays dropped |
| 17 | muir2, muir_in2, muir2_reboot (4-5) | muir_in2, MUI_ComCore | Magma solo (control_alsion) / teamselect / Magma keepheroes | Colossus NPC ("welcome to join us") | ChooseTeam (forced) / blackbird / KeepTeam | `unlockCharacter("colossus")` at mansion4 start (decision) |
| 18 | mansion4 + briefings (5) | mansion_back4, mansion4_1, subbasement4 | Magma solo | Frost NPC present | ChooseTeam | as above |
| 19 | mansion4_grso, grso_debriefing (5) | mansion_back4_grso | teamselect | - | blackbird | unchanged |
| 20 | astral1 / astral1b (5) | astral1_1.., astral4_3 | ProfXAstral + Phoenix + Frost (3/3) / Phoenix + Frost | +Frost, ProfXAstral (REQUIRED) | unlock profxastral/phoenix/frost, ChooseTeam | unchanged; ProfXAstral `playable="false"` may hide him in the menu (UNVERIFIED) -> set `playable="true"` in the converted entry |
| 21 | old_wx / secret_wx (5) | wx2_*, wx3_* | Cyclops solo / Wolverine + Cyclops | - | ChooseTeam (forced) | unchanged |
| 22 | sentinels_mansion, mansion5, healer_briefing, rescue_healer, mount (5-7) | man5, sewers hub2, mount | teamselect / Magma / keepheroes | - | blackbird / ChooseTeam / KeepTeam | unchanged |
| 23 | mansion6, muir3, muir3brig (7) | man6, muir_in3, muir_brig | 4/4 teamselect; Phoenix solo in the brig; `removeFromGroup("phoenix")` at exit | - | blackbird; ChooseTeam; removeFromGroup dropped | unchanged (T11: stays dropped, justification in 5) |
| 24 | riots, nyc_rooftops, sewers_grso, sewers_marrow (7) | nyc3_*, nyc_roof1, sewers3_*, sewers_marrow | teamselect; Wolverine solo rooftops; solo triggers nyc3_2_2, sewers3_1_3 | Psylocke NPC in nyc3_1_2 | blackbird / ChooseTeam | `unlockCharacter("psylocke")` at mansion7 start (decision); solo dropped |
| 25 | mansion7, astral2, astral2_col, end_astral2 (8) | man7, astral3_* | Magma / 4/4 / teamselect; solo triggers astral3_4 | Psylocke NPC mansion7_1 | as before | unchanged |
| 26 | hive_ext, hive1, hive2, end_hive (8) | hive1_*, hive2_* | teamselect / keepheroes; solo hive2_2_4 | - | blackbird / KeepTeam | unchanged |
| 27 | mansion8, start_astral3, astral3, astral_sk (9) | man8, savepx | teamselect; ProfXGladiator solo (astral_sk, side) | ProfXGladiator (npcstat) seated | ChooseTeam; end `loadZone` | astral_sk needs ProfXGladiator as a herostat entry to be seatable (hero conversion decision); T9 for the return |
| 28 | asteroid_rock ... asteroid_mm2 (9) | asteroid*, mastermold* | Frost required; keepheroes | - | unlock frost, KeepTeam | unchanged |
| - | Danger Room (arenas, 15 zones) | arena/* | COURSE hero= | - | XML2 dangerroom kept | when XML1's dangerroom.eng is converted, `hero=` is honoured by the exe (1.5) |

Design notes for the table:
- Every "Magma solo" hub becomes "team menu, player picks"; nothing in XML2 can force a 1-hero party.
- The team-select moments that XML1 had (teamselect=true) already open the same XML2 menu; the port adds
  team menus where XML1 forced a party (49 missions), which is the only way to let the player match it.
- Colossus / Psylocke / Jubilee unlock points are a **decision**: XML1's mechanism was not found in data
  (1.1.3). The NPC evidence suggests Jubilee at mansion2, Colossus at mansion4, Psylocke at mansion7.

---

## 5. Implementation spec (no pipeline edits made here)

Pass placement: `scripts.py::_base_text` runs `narrow_packed`, `blackbird_to_choose_team`,
`normalise_zone_literals`, `rename_mission_anims`, `bound_unwakeable_loops`; `scripts.py::_script_text` then
runs `choose_team_in_bodies` and `inject_act`. The new passes below are text transforms over the installed
research output (markers are stable: `# ( "XML1 beginMission(m)" )`, `# ( "x1 removed: <call>" )` +
`debug("x1: removed statement" )`, `# ( "XML1 endSideMission from side mission s" )`), so they belong in
`tools/xml1build/scripts_transform.py` and are called from `_script_text` after `choose_team_in_bodies`.
Inline data rewrites (`enterSoloMode`) go through `scripts.rewrite_data_tree` like `rename_mission_anims`.

### T7 `join_hero` - real `addHero` emulation (nyc/alison/add_cyclops, mansion/dr_mag2/blob/add_cyclops)
Match (installed text):
```
unlockCharacter("cyclops", "" )
unlockCharacter("cyclops", "" )
extractionPointLite("_ACTIVE_HERO_", "true", "false", "false" )
```
Replace with (bit = 1 for nyc/alison, 2 for mansion/dr_mag2; `x1join` is a new game-flag name, 6 chars,
counts toward `MAX_GAME_FLAG_NAMES`):
```
unlockCharacter("cyclops", "" )
# ( "x1 addHero(cyclops): XML2 has no seat-a-hero call (0x46c810 is not scriptable); save the spot and open the team menu" )
remove ( "cyclops", "cyclops" )
setGameFlag("x1join", <bit>, 1 )
extractionPointChange("_ACTIVE_HERO_", 0 )
```
Why: `extractionPointLite` is gated by the `danv` hint (2.5) and would need a second player step ("Change
Team"); `extractionPointChange` opens the team menu directly, saves the position and returns to the same
spot with the new party. `remove("cyclops")` deletes the NPC Cyclops spawned by `sp_cyclops01`
(`monster_name="cyclops"`) so the joined hero is not doubled (XML1 `fadegambit.py` uses the same
`remove("gambit","gambit")` idiom). The following `waittimed(1.000)` + `createPopupDialogXml("dialogs/tut15")`
(nyc only) must move **before** the `remove` (the reload kills the script); whether a popup and the team menu
can be opened back to back is an in-game A/B (alternative: show tut15 from the zone-script guard below on the
first guarded re-entry).
Zone-script guard (generated wrapper `x1/zones/<zone>` as in SPEC 12.7, or injected first statements) for
`nyc/alison/nyc1_1_3` (bit 1) and `mansion/dr_mag2/mag_nyc4` (bit 2), because the reload re-arms the
`actcountremove="1"` trigger and re-spawns the `instantspawn` NPC:
```
x1j = getGameFlag("x1join", <bit> )
if x1j == 1
     remove ( "trigger_touch03", "trigger_touch03" )
     remove ( "sp_cyclops01", "sp_cyclops01" )
endif
```
(XML2 zone scripts remove entities at load the same way: `act5/apocalypse/zone_script.py`.) Clear the bit at
the owning mission start: insert `setGameFlag("x1join", 1, 0 )` after the `# ( "XML1 beginMission(alison)" )`
marker and bit 2 after `beginMission(dr_mag2)`, in `inject_act`'s style. Entity names verified in both
`nyc1_1_3.eng` and `mag_nyc4.eng` (`sp_cyclops01`, `trigger_touch03`, `enable_target01`).
Console budget: `extractionPointChange` sends exactly the 2 allowed pending commands; nothing else may be
queued in the same frame (lint: no other console-sending call within the same statement run).

### T8 `new_game_roster` - REQUIRED-hero unlock exceptions and hook variants
- Static exception table in `scripts.py`: `{'alison': {'cyclops'}}` - drop `unlockCharacter("cyclops", "" )`
  from the begin_alison body (the New Game hook and every inlined copy). Rationale: Cyclops joins by script;
  under option C this line would make him selectable before nyc1_1_3. Under B it is harmless but misleading.
- Hook body by option: B (default) unchanged (`loadMapChooseTeam("nyc/alison/nyc1_1_1")`); C:
  `loadMapKeepTeam("nyc/alison/nyc1_1_1")` guarded by a build option `--newgame keepteam`, with the proxy
  patch documented as a prerequisite (validator V10 should refuse `keepteam` unless the herostat has
  `wolverine` and the option is explicitly set).
- `--start-zone` / `--tour` hooks: keep `loadMapKeepTeam` only while the herostat still contains the four
  hardcoded names (XML2 stand-ins). Once XML1 heroes replace them, these hooks must either use
  `loadMapChooseTeam` or the herostat must keep aliases (option A safety net); V10 should check this.

### T9 `side_mission_party` - flashbacks with party save/restore
For the forced-party side missions (jug_fb, sent_fb, wx_fb_start, dr_mag1, dr_mag2, astral_sk; also
muir2_reboot if its party differs):
1. At the `beginSideMission(s)` site (marker `# ( "XML1 beginSideMission(s) - return handled by endSideMission rewrite" )`):
   emit `setGameFlag("x1side", <bit_s>, 1 )` then `extractionPointChange("_ACTIVE_HERO_", 0 )` and **stop**
   (the rest of the generated begin body is not run here). The player picks the flashback party (the
   REQUIRED heroes were unlocked by the begin body; move those `unlockCharacter` lines before the call).
   The menu confirm reloads the caller zone at the same spot with the chosen party and pops the record.
2. Caller zone script guard (subbasement2 for jug_fb/sent_fb/dr_mag1, hangar? for wx_fb_start - the exact
   caller zones are `SIDE_CALLS` in rewrite_scripts.py): if `getGameFlag("x1side", <bit_s>) == 1`:
   `setGameFlag("x1side", <bit_s>, 0 )`, `extractionPointChange("_ACTIVE_HERO_", 0 )` **must not** be used
   again; instead push a fresh record for the return trip with the *flashback* party already seated:
   this second push is the problem - the only pusher is `extractionPointChange`, which opens the menu again.
   **Simplest correct variant** (no second push): at step 1 do **not** rely on the record surviving; instead
   at the end of the flashback emit `loadMapChooseTeam(<caller zone>)` (player re-picks the normal party,
   default start position), i.e. replace the generated `loadZone("<caller>", "" )` after the
   `# ( "XML1 endSideMission from side mission s" )` marker with `loadMapChooseTeam("<caller>" )`.
   **Faithful variant** (position + party restored, one extra menu): keep step 1; in the caller zone guard
   run the flashback's begin body with `loadMapKeepTeam(<flashback zone>)` (party = chosen); at the end
   emit `restorelastzone("0")` - this needs a record on the stack, which `extractionPointChange`'s own
   `restorelastzone('1')` popped. So the faithful variant requires the caller-zone guard to call
   `extractionPointChange` a second time (menu shown twice) - **UNVERIFIED** and clumsy. Recommendation:
   ship the simplest variant; test the faithful one only if Owen wants exact return positions.
3. Skinsets (60s/70s/weaponx/civilian): make the costume selectable with `unlockCharacter("", "<costume>")`
   in the begin body (XML2 table `0x6d8aa0`: 60s=3, 70s=4, weaponx=5, civilian=8; `magmacivilian` has no
   slot - Topic B); forcing it is not possible from script.

### T10 `solo_mode` - only where an exit exists
- Inline `enterSoloMode('_ACTIVATOR_')` (data rewrite value `debug('x1: removed statement')`) **stays
  dropped** in the 14 zones without an `exitSoloMode` (1.4): emitting `setallaiactive('FALSE')` with no
  matching TRUE would freeze the AI for the rest of the zone.
- In the 4 astral bridge zones (scripts `astral/astralbridge_1inmap.py`, `_1inmap_camera.py`,
  `_2inmap_a.py`, `_2inmap_b.py`): replace the marker pair
  `# ( "x1 removed: exitSoloMode('_ACTIVE_HERO_')" )` / `debug("x1: removed statement" )` with
  `moveHeroesToEnt("_ACTIVE_HERO_" )` + `setallaiactive("TRUE" )`, and the zone's `trigger_solo`
  `actscript` with `setallaiactive('FALSE')` (inline, no spaces needed - not console code, so spaces are
  allowed anyway). Semantics differ from XML1 (the player may still switch to a frozen teammate);
  in-game check on astral1_2 that the bridge puzzle completes and the party regroups.
  (`_1inmap_camera.py` already calls `setallaiactive("FALSE"/"TRUE")` itself; do not double it.)

### T11 `removeFromGroup` - stays dropped
`reallyendmuir3.py`'s `removeFromGroup("phoenix")` was an XML1 workaround for the next mission forcing Jean
into slot 1 (XML1 comment). XML2 never force-seats; the next mission start opens the team menu. No action.
`control_alsion.py`'s calls are commented out in XML1.

### T12 `setPowerStatus` - stays dropped
`dr_mag01.py` enabled `power_smash` for the Magma tutorial; XML2 has no per-power toggle. Effect: the tutorial
text may reference a power the player already has. No action; note in the deferral list.

### T13 lint / validator additions
- Error on any emitted `loadMapAddTeam` (sends `resetgame`, 2.3).
- Error on `extractionPointLite("_ACTIVE_HERO_", ...)` emitted as an addHero emulation without a preceding
  `setGameFlag("danv", 1, 1 )` or T7 replacement.
- V14 roster flow: every `x1join`/`x1side` bit has (a) a clearing `setGameFlag(...,0)` in its mission start,
  (b) a zone-script guard in its zone; `x1join`, `x1side` counted in `game_flag_names`.
- V10: the New Game hook's load call is `loadMapChooseTeam` unless `--newgame keepteam`; when the herostat no
  longer contains `magneto`/`cyclops`/`wolverine`/`storm`, every `loadMapKeepTeam` first load from a hook
  (start-zone/tour) is an error (the hardcoded names would spawn through `0x46c810`'s fallback path).
- Selftests: T7 pattern on the two add_cyclops scripts; T9 marker replacement; T10 only in the 4 files.

### In-game checks (ordered)
1. New Game (option B build): the team menu opens before nyc1_1_1; note which heroes it offers (settles
   `0x6f3c2d`); confirm with Wolverine alone (settles "1-hero party allowed").
2. nyc1_1_3 with T7: touch the trigger -> team menu opens (no hint dialog), add Cyclops, confirm ->
   nyc1_1_3 reloads at the same spot, NPC Cyclops gone, trigger gone; save/load keeps the party.
3. `--start-zone` build with an XML1-only herostat: does New Game survive `startFirstMission`'s unknown
   names (fallback path) - run once to classify crash vs. defaultman before relying on option A/B choices.
4. jug_fb with T9 (simplest variant): 60s heroes selectable; return to subbasement2 reopens the team menu.
5. astral1_2 with T10: bridge puzzle completes and the party regroups.

---

## 6. Open decisions and UNVERIFIED items

Decisions for Owen:
1. Option B (team menu at New Game, works today) vs option C (proxy pointer patch: exact XML1 opening and
   story-driven unlocks). C is the only route to "Wolverine alone" and "locked until met".
2. Where to unlock Colossus, Psylocke, Jubilee (XML1 mechanism not found; proposed mansion4 / mansion7 /
   mansion2 from NPC evidence) and whether Magma may be selectable from mansion1 (REQUIRED unlock) or only
   from mansion3_uniform.
3. Flashback return: simplest (team menu at return, default start) vs faithful (double menu, exact spot).
4. Whether ProfXGladiator/ProfXAstral get herostat entries (needed to seat them at all).

UNVERIFIED (must be tested or read before relying on it):
- Retail value of `byte [0x6f3c2d]` (6 vs 17 default unlocks at New Game).
- XML2 team menu: minimum party size; whether `playable="false"` heroes are listed.
- `0x46c810` / `0x486dd0` behaviour for a party name absent from herostat (fallback entry of handle 0).
- XML1 `charunlock`/`defaultUnlock` semantics and how Colossus/Psylocke/Jubilee were unlocked in XML1.
- Whether a popup (`createPopupDialogXml`) and the team menu can be opened in one script run (T7 ordering).
- `extractionPointLite` s2/s3 flag meanings; `setblackbirdparms` 4th/5th parameters.
- How the 14 no-exit `enterSoloMode` zones leave solo mode in XML1.
- Which ini file `builddefaultteam` reads.
