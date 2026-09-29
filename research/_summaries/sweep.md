# sweep

## SUMMARY
Sweep finished. All 210 XML1 zone bundles convert with tools/convert_zone.py and no errors. I converted them into a writable XML2 copy at research/sweep/xml2_copy. The other 46 map bundles are maps/package/* (menus and permanent packs), not zones. The harness blocked writing report.md, so the report is in this output. The machine-readable result, including a record for every zone, is research/sweep/inventory.json.

**New Game.** In XML1 the newgame command (default.xbe handler 0x18d0b0) runs "beginmission alison". That mission plays movie r102, then loads nyc/alison/nyc1_1_1. I built a graph of zones, scripts, conversations, dialogs and missions (2,191 nodes). From New Game it reaches 162 zones and 63 missions, ending at mastermold/mastermold2.

**Script gap is much bigger than the old report says.** I pulled the actual script-function tables out of both binaries. The record layout is {handler, name, ret_sig, arg_sig}, confirmed by disassembly. XML2 is missing 22 XML1 engine functions, used by 1,602 calls. The old script_func_diff.txt said 9. The good news: the largest ones are renames.
- screenFade is literally cameraFade in XML1 (both names point to handler 0x98ec0).
- Get/SetMissionVar and Get/SetMissionFlag map to XML2's Get/SetZoneVar and Get/SetZoneFlag: same signatures, same position in source order.
- The popup-dialog trio has to become generated dialog XML.

**XML2 doesn't support XML1's mission system.** XMen2.exe contains none of the MISSION attribute names XML1 relies on: scriptstart, mapload, teamselect, minheros, keepheroes, requiredhero. It also registers no beginmission console command. So XML1's mission-to-mission progression has to be compiled into scripts.

**Characters and skins are the biggest data blocker.**
- Zones need 166 characters. 152 are missing from XML2's stat tables; all 166 exist in XML1's.
- 140 XML1 actor files have the same names as XML2's. The converter currently loads XML2's actor for 647 zone references instead of XML1's.
- Evidence (Pyro_hero skin 11401/11402) shows XML2 accepts 5-digit skins, which gives a safe renumbering (CCVV → 3CCVV).
- Character packages (484 bundles) aren't converted yet.

**Text XML.** Only 5 of 3,989 files fail the stock parser, all from '<' inside attribute values. A fix covering those plus 3 latent issues is in sweeplib.py and passes on every file. A separate problem: 71 text files are 0 bytes, 30 of them in reachable zones. The converter turns these into invalid 8-byte XMLB files. Shipping XML2 zones list nav/boy/zam files that don't exist, so the fix is to not write the file.

**Movies, UI, automaps.**
- Movies: both games use the same CRI Sofdec format (MPEG-1 640x480, identical ADX stereo header). XML1 adds a second audio stream.
- UI: 11 XML1 menu types don't exist in XMen2.exe, so keep XML2's UI and port only the data.
- Automaps: XMen2.exe still reads XML1's automap_texture and automap_offset attributes (read at 0x4c7fa2, which appends ".png"), so the texture automaps might work as-is. Needs an in-game test.

## FINDINGS
- [high] All 210 XML1 zone bundles convert with stock tools/convert_zone.py and zero exceptions. Categories: 173 campaign, 13 mocap briefings, 15 Danger Room arenas, 7 demo copies, 1 cinematic, 1 main-menu backdrop. The other 46 map bundles are maps/package/* menu and permanent packages.
    EVIDENCE: research/sweep/sweep.py run into research/sweep/xml2_copy (copy of <XML2 folder> without *.sfd and Sounds); zones.json convert=='ok' for all 210; inventory.json summary.zones_convert_errors=0
- [high] XML1 New Game runs console command 'beginmission alison' (or 'beginmissionhack demo' when the demo flag is set). Mission alison has scriptstart missions/alison, which runs startMovie('r102') then loadMap('nyc/alison/nyc1_1_1'). So the true first zone is nyc/alison/nyc1_1_1.
    EVIDENCE: default.xbe: 'newgame' registered at 0x18e217 with handler 0x18d0b0; handler pushes 0x3e05d0 'beginmission alison' at 0x18d118 and 'beginmissionhack demo' at 0x18d12a when [0x498db0] != 0 (xbedis.py 18d119). Then xml1_assets/data/missions/alison.eng and xml1_assets/scripts/missions/alison.py.
- [medium] XML2 New Game path: newgame (handler 0x5f3610) -> difficulty dialog -> 'runscript startFirstMission()' -> startFirstMission handler 0x4a7b10. The first zone is act0/tutorial/tutorial1, which is the only zoneinfo entry with state='2'.
    EVIDENCE: XMen2.exe: push 0x6a397c 'newgame'/0x5f3610 at 0x5f491d; push 0x6872a0 'runscript startFirstMission()' at 0x5f3d19; Data/zoneinfo.engb has 34 entries with state=1 and 1 with state=2 (tutorial1)
- [high] 162 zones and 63 missions are reachable from New Game. Act order: nyc/alison -> briefing -> mansion1a -> HAARP -> mansion2 -> Sentinel flashback, Juggernaut, sewers -> arbiter -> mansion3 ... -> asteroid -> mastermold2. 24 'campaign' zones are unreachable: man5 test/junk, duplicate arb_fd copies, 0-byte savepx astral1_1/1_3, blackbird backdrops, plus 4 to check manually. All 15 arenas are referenced only from data/dangerroom.eng <ARENA zone=...>.
    EVIDENCE: research/sweep/graph.py -> graph.json reachable_from_new_game / reachable_missions / unreachable_by_category; inventory.json.graph
- [high] XML1 zonelink nextzone values are short names; XML2 uses full paths. Of 157 non-empty nextzones, 150 resolve by same directory, 5 are cross-directory and 2 are already full paths. The converter must rewrite nextzone/prevzone to full lowercase paths. 20 prevzone values point to zones that don't exist (hangar2-7, mansion_back3-8, etc.).
    EVIDENCE: zones.json links[].how counts: zonelink same_dir 150, unique_campaign 5, full 2; prevzone unresolved 20. XML2 Maps/Act0/tutorial/tutorial1.engb nextzone='act1/sanctuary/sanctuary1'.
- [high] The script-function tables use 16-byte records {handler, name, ret_sig, arg_sig}. XML2 has 302 functions, XML1 has 207. Every XML1 script call is in XML1's table except user-defined def names, which validates the extraction.
    EVIDENCE: script_table.py -> script_functions.json. Layout proofs: xbe dword before 'blackbirdMenu'(sss) = 0x9a370, which pushes 'setblackbirdparms %s %s %s FALSE FALSE' at 0x9a3c7; exe beginMission handler 0x4a0af0 pushes 'beginmission %s', beginMissionHack handler 0x4a0b60 pushes 'beginmissionhack %s' at 0x4a0b84. XML2 table ends with float pi after SetDontShowWarningOff.
- [high] 22 XML1 engine functions (1,602 calls) are missing from XML2, not 9 as script_func_diff.txt says. Biggest: screenFade 396, addPopupDialogOption 254, setMissionVar 252, getMissionVar 178, setMissionFlag 118, getMissionFlag 103, create/showPopupDialog 103 each, get/setGameVar 28 each. 132 of the 162 reachable zones use at least one.
    EVIDENCE: script_calls.py -> script_calls.json xml1_missing_in_xml2; aggregate.json scripts.missing_functions_zone_count; the strings setMissionVar and screenFade do not occur in XMen2.exe at all (grep -c = 0)
- [high] screenFade(ff) is an exact alias of cameraFade(ff) in XML1, so rewriting it to cameraFade (which XML2 has) is lossless.
    EVIDENCE: script_functions.json xml1: screenFade.handler == cameraFade.handler == 0x98ec0
- [medium] XML1 get/setMissionVar and get/setMissionFlag match XML2 get/setZoneVar and get/setZoneFlag: identical signatures, and the same source order between allowConversation and timerAdd. XML2 dropped XML1's get/setGameVar(si); it only has get/setGameFlag bitflags. Whether zone vars persist across zone loads, as XML1 mission vars must, is unverified.
    EVIDENCE: handlers sorted by address: XML1 0x98bb0 getGameVar, 0x98bf0 setGameVar, 0x98c30 getMissionVar, 0x98c70 setMissionVar, 0x98cb0 getMissionFlag, 0x98d20 setMissionFlag; XML2 0x49db80 getZoneVar, 0x49dbc0 setZoneVar, 0x49dc00 getZoneFlag, 0x49dc70 setZoneFlag; matching prologues and call shapes (xbedis.py / strpush.py)
- [high] Two functions changed signature: sound sass->ssas (75 zones) and extractionPointLite asssss->asss (20 zones). displayEx and magnetoBall are no-op stubs in XML1 itself and can be deleted.
    EVIDENCE: script_functions.json args; stubs.py: XML1 handler 0x2123a0 = 'xor eax,eax; ret' shared by debug/display/displayEx/magnetoBall/saveloadFormat
- [high] XML2 doesn't support XML1's mission system. XMen2.exe has none of the MISSION attribute names (scriptstart, mapload, teamselect, minheros, keepheroes, requiredhero), and registers no 'beginmission', 'beginsidemission' or 'changethememusic' console commands (XML1 registers beginmission at 0x18e2b6 with handler 0x18da90). XML2 beginMission only loads data/missions/%s.xmlb objectives. So the 65 beginMission calls and 63 reachable missions need a mission-to-script compiler.
    EVIDENCE: grep -c -a -i on XMen2.exe: scriptstart 0, mapload 0, teamselect 0, minheros 0, keepheroes 0, requiredhero 0 (XML1 xbe: 1 each); '\0beginmission\0' exists only in the xbe; XML2 Data/missions/act1_insect.engb holds only MISSION act + OBJECTIVE
- [medium] blackbirdMenu(sss) (49 XML1 calls) exists in XML2 and issues 'setblackbirdparms', which XML2 registers. But XML2 has no BLACKBIRD_MENU type or CMenuBlackbird class; its own flows use 'setblackbirdparms ...; opencharactersmenu'. Whether XML1-style calls work is unknown.
    EVIDENCE: XML2 handler 0x4a0640 pushes 0x68d25c 'setblackbirdparms %s %s %s FALSE FALSE'; grep: CMenuBlackbird x2:0 x1:1, BLACKBIRD x2:0 x1:1; strings 0x28fc30 and 0x28d548 in XMen2.exe
- [high] Zones need 166 characters; 152 are missing from XML2 npcstat/herostat. All 166 are in XML1's tables. 157 of 162 reachable zones need at least one missing character.
    EVIDENCE: aggregate.py -> aggregate.json.characters (summary 'x1:True x2:False': 152, 'x1:True x2:True': 14)
- [high] 140 XML1 actor files share names with different XML2 files, including 30 animation databases (e.g. 05_beast, common, fightstyle_*). The converter keeps XML2's version, so 647 zone references currently load XML2 actors. XML1 uses 60 two-digit character codes; 56 are taken in XML2 and only 4 are free. XML2 already supports 5-digit skins with variant = code+VV, so remapping XML1 CCVV -> 3CCVV and anim DBs CC_name -> 3CC_name is safe (XML2's highest skin is 20026).
    EVIDENCE: collisions.json summary actors different=140; Herostat Pyro_hero skin='11401' skin_astonishing='02' characteranims='114_pyro_hero' and Actors/11402.IGB exists; aggregate.json.actors; inventory.json zones[*].xml2_version_kept_but_different (actors 647)
- [high] Both engines load character packages as generated/characters/%s_%s (plus _nc and %s_xml). All 484 XML1 character bundles (plus 93 powerstyle, 20 fightstyle, 18 weapon bundles) therefore need PKGB conversion; convert_zone.py only handles map bundles.
    EVIDENCE: XMen2.exe strings 0x28e914 'generated/characters/%s_%s', 0x29e6ac '%s_%s_nc', 0x28e930 '%s_xml'; default.xbe 0x3c524c, 0x3cfb9c, 0x3c5230; _fb_manifest.json counts
- [high] 5 of 3,989 text-XML files fail the stock parser, all because of '<' inside attribute values: ui/menus/characters.{eng,fre,ger} line 107 ('At < 20% Health') and dialogs/mansion1a_2_hint.{fre,ger} ('<arrow>'). credits.* and personal/magma04.* only need the '&' escape, which parse_text_xml already does. Latent issues: stray '/>' tails (shared_combat_events.xml:40, fightstyle_gun_rifle.*:7) and a PowerAttack/powerattack case collision (ps_sentinel_spider.*). sweeplib.normalise_text_xml fixes all of these and round-trips 3,918/3,918 non-empty files.
    EVIDENCE: parse_all.py -> parse_results.json; parse_extra.py -> parse_extra.json; verify_parse.py output
- [high] 71 text files are 0 bytes (48 .nav, 12 .xml, 11 .chr; 85 empty bundle entries in total). 30 of them are in reachable zones: all 13 briefings plus the mansion hub zones of man2/4/5/6/7/8. convert_zone writes 8-byte header-only XMLB for these, which is invalid (xmlb.decode crashes on them). Shipping XML2 zones reference missing nav/boy/zam files (21/22/23 zones), so the fix is to skip writing the file.
    EVIDENCE: fb_conflicts.json empty_entries; xml2_copy/maps/mansion/man6/mansion6_1.NAVB is 8 bytes; nav_absent.py: nav {True:99, False:21} e.g. briefing/briefing1_10.PKGB, act4/tower/tower2_new.PKGB
- [high] Collisions after extension mapping (fre/ger excluded): 5,985 new, 763 different, 32 identical. All 21 top-level data tables collide and differ, and must be merged, not replaced: herostat, npcstat, items, item_ents, common_ents, shared_talents, shared_nodes, shared_anims, shared_sounds, shared_combat_events, stat_rules, values, colors, strings, codex, trivia, dangerroom, credits, review_paths, boltonactoranims, zoneinfo. 21 powerstyles and 16 fightstyles collide with different content and should be namespaced.
    EVIDENCE: collisions.py -> collisions.json summary_by_category / data_collisions
- [high] The XML1 zoneinfo needs converting too: 162 entries, all names use backslashes and 9 are mixed-case, and it only has loading/savename. XML2 has act, build, state, description, extraction, mapx, mapy, towncenter.
    EVIDENCE: ui_inventory.json.zoneinfo
- [high] Sound: zones use 35 world soundfile banks. 30 exist in XML1's sounds/zsds; the other 5 are only used by demo/junk zones. Only 'menu' exists in XML2 (a name collision). 18 bank names collide overall: beast, bishop, blob, coloss, cyclop, danger, iceman, magnet, menu, morl_c, morl_p, mystiq, night, pyro, storm, toad, x_common, x_voice.
    EVIDENCE: aggregate.json.sound_banks
- [high] Movies are the same CRI Sofdec format in both games: MPEG-1 program stream, 640x480, 'SofdecStream' plus version bytes 02 15, and ADX stereo header 80 00 01 1c 03 12 04 02 on stream C0. Every XML1 NTSC file also has a C1 stream (AIX in 26, a second ADX in 8). XML2 has only C0. XML1 path layout movies/ntsc/<c1>/<c2>/ must become Movies/ntsc/eng/<c1>/<c2>/. i101-i107 collide by name. Movie subtitle XML uses the same schema in both games.
    EVIDENCE: movies.py -> movies.json (PES walk); xml1_assets/movies/int101.eng vs Movies/cine01.engb
- [medium] XMen2.exe still reads XML1's world-entity automap_texture (appending '.png') and automap_offset ('%f %f'). XML1 texture automaps might work without generating XML2 .zam files, and 23 shipping XML2 zones lack a .zam anyway.
    EVIDENCE: strpush.py 4c7f40: push 0x68f898 'automap_texture' at 0x4c7fa2, '.png' at 0x4c7fce, 'automap_offset' at 0x4c8002, '%f %f' at 0x4c801e
- [high] UI: 11 XML1 menu types don't exist in XMen2.exe (BLACKBIRD, PAUSE, OBJECTIVES, PLAYERS, EQUIP_SHOP, ITEM_SHOP, LOAD, MMLOST, OPTIONS_STATS, OPTIONS_DEBUG, DEBUG). Neither do item types MENU_ITEM_CHARACTERS/SLIDER or commands beginmissionhack/loadmapaddteam/optionscontroller. Keep XML2's UI and fonts and port data only. Conversation tag schemas are identical, but speaker markup differs (XML1 '%X-TEAM%text' vs XML2 '%Name%: text').
    EVIDENCE: ui_inventory.py -> ui_inventory.json
- [high] The xml1_loose unpack is sound. Only 8 file names differ between .fb bundles, all automap textures of identical size; one demo variant was kept (textures/automap/mansion/jugrnt/jugrnt01.igb).
    EVIDENCE: fb_conflicts.py -> fb_conflicts.json
- [high] Resolved file references across all zones: 9,608 converted, 481 XML2 originals, 261 present in XML1 but outside the zone bundle (pickup/levelup effects from package/permanent, impacts/energy, models/tiles/<area>/ for tileent), and 29 missing even on the XML1 disc (dead references in the original).
    EVIDENCE: aggregate.json refs.status_totals and refs.missing; zones.json refs

## PLAN
1. Harden the converter: Fork tools/convert_zone.py:
- Use sweeplib.normalise_text_xml.
- Skip 0-byte source files; don't write NAVB/CHRB/XMLB for them.
- Rewrite nextzone/prevzone to full lowercase paths (same directory first).
- Normalise loadMap/mapload paths (lowercase, '/').
- Also convert maps/package/permanent*.fb and the models/tiles/* folders.
- Convert non-map bundles (484 characters, 93 powerstyles, 20 fightstyles, 18 weapons, items/item_ents/common_ents/shared_nodes) into Packages/generated/**.PKGB.
2. Namespacing pass: - Skins: XML1 CCVV -> 3CCVV, anim DBs CC_name -> 3CC_name, shared anim DBs common/fightstyle_* -> x1_*.
- Rewrite every reference: skin, skin_*, characteranims, monster_skin, hud/hud_head_*, ui/hud/characters/*, bolt-on models, character package names.
- Rename colliding XML1 powerstyles/fightstyles and the 18 colliding sound banks, and update all references.
3. Merge the global data tables: Merge npcstat/herostat first: it unblocks enemies in nyc1_1_1 (grso_riot). Then items, item_ents, common_ents, shared_* tables, stat_rules, values, colors, strings, codex, trivia, dangerroom, review_paths, boltonactoranims. For zoneinfo: full-path lowercase names plus act/build/state.
4. Script translator: - Renames: screenFade->cameraFade; get/setMissionVar->get/setZoneVar; get/setMissionFlag->get/setZoneFlag.
- Fix extractionPointLite arity.
- Turn createPopupDialog/addPopupDialogOption/showPopupDialog/canCancelDialog sequences into generated dialog XML plus createPopupDialogXml.
- Delete the no-op displayEx/magnetoBall calls.
- Hand-port enterSoloMode/exitSoloMode, side-mission calls, setInCampaign, addHero, removeFromGroup, setPowerStatus, destroyMultipartPiece.
- Map get/setGameVar per the result of the scope test.
5. Mission compiler: - For each of the 136 data/missions/*.eng|xml: emit an XML2 objectives file (MISSION act plus OBJECTIVE) and a generated scripts/xml1/missions/begin_<m>.py (beginMission -> movies -> loadMapChooseTeam/loadMap(mapload) -> scriptstart body).
- Rewrite every beginMission/blackbirdMenu call to use those scripts.
- Hook XML2's New Game (the tutorial1 script or startFirstMission) to begin_alison.
6. In-game validation along the graph: Walk graph.json reachable_from_new_game in order: nyc/alison (6 zones) -> briefing_1_1_6_5 -> mansion1a -> HAARP ... The orchestrator runs the scope and blackbird tests first.
7. Media and polish: Sound banks (with the sound workstream), movies (NTSC into ntsc/eng/<c1>/<c2>, rename i101-i107), movie subtitles, automap_texture test, conversation speaker markup, then review/codex/danger-room/credits data.

## ARTIFACTS
- research/sweep/inventory.json
- research/sweep/zones.json
- research/sweep/graph.json
- research/sweep/aggregate.json
- research/sweep/collisions.json
- research/sweep/parse_results.json
- research/sweep/parse_extra.json
- research/sweep/script_functions.json
- research/sweep/script_calls.json
- research/sweep/script_syntax.json
- research/sweep/movies.json
- research/sweep/ui_inventory.json
- research/sweep/fb_conflicts.json
- research/sweep/sweeplib.py
- research/sweep/sweep.py
- research/sweep/graph.py
- research/sweep/collisions.py
- research/sweep/aggregate.py
- research/sweep/build_inventory.py
- research/sweep/script_table.py
- research/sweep/stubs.py
- research/sweep/script_calls.py
- research/sweep/verify_parse.py
- research/sweep/nav_absent.py
- research/sweep/movies.py
- research/sweep/ui_inventory.py
- research/sweep/fb_conflicts.py
- research/sweep/xref.py
- research/sweep/strpush.py
- research/sweep/xbedis.py
- research/sweep/make_copy.py
- research/sweep/xml2_copy

## RISKS
- Scope of XML2 zone vars and flags: if setZoneVar/setZoneFlag are cleared on every zone load, the Mission->Zone rename breaks multi-zone XML1 missions. The workaround would be game flags or a script-side store.
- The skin remap to 3CCVV relies on the engine deriving variants as skin[:-2]+VV for 5-digit skins. Supported by Pyro_hero 11401/11402, but not tested with 3xx codes.
- Current conversions silently use XML2's colliding models, textures, actors and powerstyles (199 zones affected). Visual or behaviour bugs are likely until the namespacing pass lands.
- The graph only follows static string arguments. Progression built dynamically or through menus (setblackbirdparms, missions picked from dialogs) may hide more zones; 4 unreachable zones need a manual check.
- XML1 conversations put inline code in chosenScriptFile ('game.cameraReset()\n\r'), and 56 scripts use def/import game. If XML2's interpreter differs, a large set of conversation and script edges will fail silently.
- The XML2 first-zone evidence (zoneinfo state='2' and the startFirstMission path) is circumstantial. I didn't trace 0x4a7b10 through to the zone load.
- xml2_copy is 2.0 GB in research/sweep. Delete it when it's no longer needed.

## OPEN QUESTIONS
- In-game: do setZoneVar/getZoneVar/setZoneFlag values persist across loadZone within one session?
- In-game: does XML2 blackbirdMenu('FALSE',"game.loadMap('x')",'TRUE') open a team-select menu and then run the stored script, or do all 49 calls need rewriting to loadMapChooseTeam?
- In-game: does XML2 accept inline code in conversation chosenScriptFile, def/import game style scripts, and the 7 scripts that start with indented code (e.g. nyc/alison/nyc1_1_1.py)?
- In-game: does XML2's Sofdec player play XML1 .sfd files that carry the extra C1 AIX/ADX stream (e.g. r102)?
- In-game: does a converted zone with automap_texture/automap_offset show XML1's texture automap (XMen2.exe appends '.png' to the path)?
- Decision: namespace colliding generic props (140 models, 189 textures) or accept XML2's versions? Actors and power/fight styles must be namespaced regardless.
- Decision: are the Danger Room arenas (15 zones) and XML1 review/trivia content in scope for 'full campaign playable'?
- Manual check: are nyc/alison/blackbird, xjet/blackbird_arbiter, muir_is/muir2/muir_brig, muir_comcore, nyc/riots/nyc3_2_2 and mansion/man8/subbasement8b reached through menu flows, or are they cut content?

## VERIFICATION
verdicts: Counter({'confirmed': 15, 'partly-wrong': 7, 'unverifiable': 1})
- CONFIRMED: Script-function tables are 16-byte {handler,name,ret_sig,arg_sig} records; XML2 has 302, XML1 207
    NOTE: Wrote my own walker (verify/v_table.py): it starts from the only data ref to 'screenFade' (xbe) and 'cameraFade' (exe) and walks while records stay valid. Main tables: XML1 197 records (0x3d0b88..0x3d17c8), XML2 289 (0x68a908..0x68bb08, last is SetDontShowWarningOff, followed by 0x40490fdb = pi). The researcher's extra 10 and 13 entries come from a second built-in table (waittimed, waitsignal, fadd..idiv, and XML2's strcat*/strveci). Every one of my records matches script_functions.json field for field. The handler-first layout is proven: the dword before 'blackbirdMenu' is 0x9a370, and that function pushes 'setblackbirdparms %s %s %s FALSE FALSE' at 0x9a3c7.
- CONFIRMED: 22 XML1 engine functions (1,602 calls) are missing from XML2, not 9
    NOTE: Independent recount (verify/v_calls.py), deduplicated by relative path; only menus/main_back_main.py exists in both trees and it is identical. Result: 22 functions, 1,602 calls. screenFade 396, addPopupDialogOption 254, setMissionVar 252, getMissionVar 178, setMissionFlag 118, getMissionFlag/createPopupDialog/showPopupDialog 103 each, get/setGameVar 28 each, canCancelDialog 9, and the rest. case-insensitive grep of XMen2.exe and every exe/dll in the XML2 install: screenFade, setMissionVar, addPopupDialogOption, showPopupDialog, canCancelDialog and setGameVar all 0. The list includes mission(ss) with 5 calls, which the plan's translator omits.
- CONFIRMED: screenFade is an exact alias of cameraFade in XML1 (handler 0x98ec0)
    NOTE: Records at xbe 0x3d12f8 (screenFade) and 0x3d1198 (cameraFade) both hold handler 0x98ec0, ret 'n', args 'ff'. XML2 cameraFade is n:ff at handler 0x49df70.
- PARTLY-WRONG: get/setMissionVar and get/setMissionFlag correspond to XML2 get/setZoneVar and get/setZoneFlag (persistence unverified)
    NOTE: The code does line up. XML1 getMissionVar calls lookup 0xcac70 (store at this+0x1e614, 12-byte name); XML2 getZoneVar calls lookup 0x4d6840 (store at this+0x261ac), and the two are instruction-for-instruction twins. Signatures match: i:s, n:si, i:si, n:sii. But the scope differs, which undermines calling the rename lossless. XML2 CPythonGameInterface vtable slot 2 (0x49fe70, vtable 0x68d36c) always calls the zone-var clear 0x4d67f0 unless CMap flag [+0x220] bit 2 is set, and ignores its second argument. The XML1 twin (0x99b90, vtable 0x3d2824) clears mission vars only when its bool argument is true, and XML1 also clears them in the beginmission path (0x9a734, right after formatting 'beginmission %s'). So XML1 mission vars live for a mission, while XML2 zone vars are very likely wiped on each zone load. The save routine 0x49feb0 serialises only 32 zone-var slots. Separately, XML2 getGameFlag (0x4a5db0) uses lookup 0x4d68a0, the twin of XML1's getGameVar lookup 0xcacd0. The persistent game-var store therefore still exists in XML2.
- CONFIRMED: XML1 New Game runs 'beginmission alison' (demo: 'beginmissionhack demo'); mission alison plays r102 then loads nyc/alison/nyc1_1_1
    NOTE: xbe 0x18e217: push 0x18d0b0 / push 'newgame' / call [edx+0xc]. In handler 0x18d0b0, if [0x498db0]==0 it pushes 'beginmission alison' (0x18d118), otherwise 'beginmissionhack demo' (0x18d12a). data/missions/alison.eng has scriptstart='missions/alison', and scripts/missions/alison.py is startMovie('r102'), waitsignal, loadMap('nyc/alison/nyc1_1_1').
- CONFIRMED: XML2 New Game: newgame -> 'runscript startFirstMission()' -> 0x4a7b10; first zone act0/tutorial/tutorial1 (only zoneinfo state='2'); marked circumstantial/untraced
    NOTE: I traced the step the researcher left out. At 0x4a7c42 startFirstMission pushes 'runscript menus/new_game' (and 'runscript menus/new_game_hard' at 0x4a7c57). Scripts/menus/new_game.py is startMovie('cine01'), waitsignal, loadMapKeepTeam('act0/tutorial/tutorial1'). Before that, it sets up the heroes magneto, cyclops, wolverine and storm (0x4a7b41-0x4a7bef). zoneinfo.engb has 34 entries with state=1 and 1 with state=2 (tutorial1). The clean hook is to replace Scripts/menus/new_game.py and new_game_hard.py, with no exe patch.
- PARTLY-WRONG: XML2 has none of XML1's MISSION attribute names and registers no beginmission/beginsidemission/changethememusic console command; XML2 beginMission only loads data/missions/%s.xmlb objectives
    NOTE: Confirmed: grep -c -a -i on XMen2.exe gives 0 for scriptstart, mapload, teamselect, minheros, keepheroes, requiredhero and remote (1 each in the xbe). Two independent registration scans (v_cmds.py byte pattern: 44 names; v_cmds2.py, all 191 console-singleton call sites) find no beginmission, beginsidemission or changethememusic in XML2; XML1 registers beginmission at 0x18e2b1 with handler 0x18da90. Wrong part: XML2 beginMission (0x4a0af0) does not load objectives. It formats 'beginmission %s', sends it to the console (vtable+0x1c), where no such command exists, then calls CHud vfunc+0x80. data/missions/%s.xmlb is loaded only by CMissionMgr vtable slots 5 and 8 (0x489190 and 0x489b30, both calling 0x488520). In practice XML2 beginMission does nothing.
- CONFIRMED: Signature changes: sound sass->ssas, extractionPointLite asssss->asss; displayEx/magnetoBall are XML1 no-op stubs
    NOTE: Diffing my table walk gives exactly these two signature changes. XML1 handler 0x2123a0 is 'xor eax,eax; ret'. magnetoBall has 0 XML1 calls, and enterSoloMode is also XML1-only with 0 calls.
- CONFIRMED: Zones need 166 characters; 152 missing from XML2 npcstat/herostat; all 166 in XML1 tables
    NOTE: verify/v_chars.py parses all 210 zone .chr files: 166 distinct names. All 166 are in XML1 npcstat.eng + herostat.eng (206 names). Checked against the union of XML2 npcstat/herostat .XMLB and .engb (296 names), 152 are missing. The 14 present are beast, colossus, cyclops, default, forge, frost, gambit, moira, nightcrawler, phoenix, profx, rogue, storm and wolverine. grso_riot is in XML1 only.
- PARTLY-WRONG: 140 XML1 actor files collide with different XML2 files (30 anim DBs); 647 zone refs load XML2 actors; 5-digit skins supported (Pyro_hero 11401/11402); XML2 max skin 20026; 60 XML1 codes, 4 free
    NOTE: Confirmed: 140 same-name files, 0 identical, 30 non-numeric (the anim DBs, common, fightstyle_*). Re-running the converter over all zones gives 647 kept-XML2 actor references (108 distinct). Herostat Pyro_hero skin=11401 with skin_astonishing='02', and 11402.igb exists. XML2 max skin is 20026 and there are no 3xxxx skins. XML1 does use 60 codes, but only 3 are free in XML2 (35, 36, 45), not 4. That does not affect the 3CCVV plan.
- CONFIRMED: All 210 XML1 zone bundles convert with stock convert_zone.py and zero exceptions; 46 map bundles are maps/package/*
    NOTE: Manifest: 256 map bundles, 46 under maps/package/, 210 zones, and every zone has a zonexml. I re-ran the stock Converter over all 210 (verify/v_convert_all.py) into a scratch target, with the existing-file set taken from the real XML2 file list: 0 errors, 6,403 files written, 4,956 kept-XML2 references, 199 zones with at least one kept file. The run also writes 81 outputs of 8 bytes or less, including 10 zero-byte .igb copies.
- CONFIRMED: 71 text files are 0 bytes (48 nav, 12 xml, 11 chr); 30 are in reachable zones; convert_zone writes invalid 8-byte XMLB; shipping XML2 zones reference missing nav/boy/zam (21/22/23)
    NOTE: find -size 0: 48 nav, 12 xml, 11 chr, plus 12 igb and on/off, 85 in total. Against graph.json's reachable set, 30 of the text files are in reachable zones (13 briefings and 17 mansion hub files). xml2_copy/maps/mansion/man6/mansion6_1.NAVB is b1110000 01000000, and xmlb.decode raises an unpack error on it. Re-running nav_absent.py reproduces nav {True:99, False:21}, boy 98/22, zam 97/23. Most of the absent ones are briefing zones, so they show missing files are tolerated in non-combat zones only. The researcher missed the 12 zero-byte .igb files, including actors/7501.igb, which is the skin of npcstat 'Computer'.
- PARTLY-WRONG: Only 5 of 3,989 text-XML files fail the stock parser; sweeplib fixes them plus 3 latent issues and round-trips all non-empty files
    NOTE: Stock parse_text_xml fails on exactly 5: ui/menus/characters.{eng,fre,ger} at line 107, and dialogs/mansion1a_2_hint.{fre,ger}. sweeplib.parse_text_xml_robust -> encode -> decode succeeds on 3,897/3,897 distinct non-empty files. Count nuance: 3,989 includes 21 relative paths present in both trees (3,968 distinct). On the other 3,892 files the robust parser's XMLB is byte-identical to the stock output, so the 3 'latent issues' do not change any output today.
- PARTLY-WRONG: nextzone values are short names while XML2 uses full paths, so the converter must rewrite nextzone/prevzone; 150 same-dir, 5 cross-dir, 2 full; 20 unresolved prevzone
    NOTE: XML1 counts confirmed (verify/v_links.py): nextzone 150 same_dir, 5 unique elsewhere, 2 full, 7 empty; prevzone 20 unresolved. But XML2's own shipping zones use short same-directory names in 63 of 144 nextzone values (e.g. act1/genosha/genosha1 -> 'genosha5', act1/deadzone/deadzone2 -> 'deadzone3'), and 1 cross-directory short name (dr/dr_boss4 -> 'perimeter4'). So XML2 resolves short same-directory names, and only the 5 cross-directory XML1 links need full paths.
- PARTLY-WRONG: XMen2.exe still reads automap_texture (appends .png) and automap_offset, so XML1 texture automaps might work without .zam
    NOTE: The read code is confirmed. CWorldEntity (RTTI via vtable 0x68f8ac) slot 0x4c7f90 pushes 'automap_texture' at 0x4c7fa2, appends '.png' at 0x4c7fce when it is absent, and parses 'automap_offset' with '%f %f'. XML1 has identical code at 0xbefb2. But XML1's consumer builds the path 'textures/automap/%s' (xbe 0x1526d6-0x152700), and XMen2.exe contains no 'textures/automap' string at all. No shipping XML2 zone uses automap_texture (grep of Maps/ returns nothing). The attribute is most likely a dead read in XML2, so texture automaps working as-is is unlikely.
- CONFIRMED: Movies: same Sofdec format (SofdecStream + 02 15, 640x480 MPEG-1, ADX 80 00 on C0); every XML1 NTSC file has a C1 stream (AIX 26, ADX 8); XML2 C0 only; path ntsc/eng/<c1>/<c2>; i101-i107 collide
    NOTE: PES walk over all files (verify/v_movies.py): NTSC 26 have C1 AIX ('AIXF') and 8 have a second ADX on C1; PAL 27, 7, and 1 with no C1; all 14 XML2 files are C0+E0 only. r102: 'SofdecStream' followed by spaces then 02 15; sequence header 640x480. XML2 layout is Movies/ntsc/eng/c/i and ntsc/eng/i/1. Nuance: XML1 NTSC has no i106, so 6 files collide, not 7.
- CONFIRMED: Sound: 35 world soundfile banks, 30 in XML1 zsds, only 'menu' in XML2; 18 bank-name collisions
    NOTE: verify/v_sounds.py over zone .xml and .eng world entities: 35 banks, 30 present. The 5 absent are a_int, deck, hub, man1b (demo zones) and main (mansion/man5/subbasement4, which is unreachable). Only 'menu' exists in XML2. My regex found 16 collisions; x_common.zsm and x_voice.zss exist in both games without the _x suffix, which gives 18.
- CONFIRMED: Both engines load character packages as generated/characters/%s_%s (+_nc, %s_xml); 484 character bundles need PKGB conversion
    NOTE: Both binaries contain generated/characters/%s_%s, %s_%s_nc and %s_xml; XMen2.exe also has %s_%s%s. The manifest has 484 characters/*.fb bundles, named <name>_<skin>, e.g. acolyteenergy_4801, so the skin remap must also rename packages. XML2 has 1,535 character PKGBs.
- CONFIRMED: 162 zones and 63 missions reachable from New Game; 24 campaign zones unreachable
    NOTE: I re-ran a copy of graph.py with SWEEP pointed at verify/graphrun. It reproduces 2,191 nodes, 162 reachable zones (identical list) and 63 missions. The static-only caveat stands. Example: mansion/man8/subbasement8b is the mapload of mission start_astral3 ('mansion/Man8/subbasement8b'); that mission's only reference is the data/missions/missions.xml charunlock list, and the xbe has no 'start_astral' string, so it is plausibly cut.
- CONFIRMED: XML1 zoneinfo: 162 entries, all backslashed, 9 mixed-case, only loading/savename
    NOTE: Python parse of xml1_loose/data/zoneinfo.eng: 162 names, 162 with backslashes, 9 with uppercase (the nyc\Alison\* set, mansion\Jugrnt\jugrnt01, arbiter\Deck\arb_fd1/2). Attributes present: name, loading, savename.
- PARTLY-WRONG: 11 XML1 menu types don't exist in XMen2.exe
    NOTE: All 11 are absent from XMen2.exe, but LOAD_MENU, OPTIONS_STATS_MENU, OPTIONS_DEBUG_MENU and DEBUG_MENU are also absent from XML1's own default.xbe (its *_MENU strings are BLACKBIRD, CODEX, CREDITS, DANGER_ROOM, EQUIP_SHOP, IMAGE_VIEWER, ITEM_SHOP, MAIN, MMLOST, MOVIE, OBJECTIVES, OPTIONS_CONTROLLER, OPTIONS, PAUSE, PERSONAL, PLAYERS, REVIEW_PATHS, STYLE, TRIVIA). Only 7 retail-used types are really lost. MENU_ITEM_CHARACTERS and MENU_ITEM_SLIDER are confirmed missing. The 'keep XML2 UI' conclusion still holds.
- CONFIRMED: blackbirdMenu(sss) exists in XML2 and issues setblackbirdparms, which XML2 registers; no BLACKBIRD_MENU
    NOTE: XML2 record at 0x68b228 points to handler 0x4a0640, which pushes 0x68d25c 'setblackbirdparms %s %s %s FALSE FALSE', runs it through console vtable+0x18, then calls vfunc+0x68 on the object from 0x5d8920. setblackbirdparms is registered at 0x5f4a7d with handler 0x5f23e0. BLACKBIRD_MENU: XML2 0, XML1 1. Runtime behaviour is still untested.
- UNVERIFIABLE: Collisions: 5,985 new / 763 different / 32 identical; all 21 data tables must be merged; 132 of 162 reachable zones use a missing function; sound 'sass' change affects 75 zones
    NOTE: I did not recompute these derived counts. I only confirmed the 21 shared data-table names (ui_inventory data_tables.both) and that the XML2 .XMLB and .engb variants of npcstat, herostat, zoneinfo, strings and items differ in size and content.

### artifact check
I ran or re-derived the main prototype tools; the reproducible headline numbers held.
(1) tools/convert_zone.Converter over all 210 zones, into a scratch target (verify/x2stub) with the existing set taken from the real XML2 file list. Result: 0 exceptions, 6,403 written, 4,956 kept-XML2 references, 647 kept actor references (108 distinct), 199 zones affected. That matches the claims and the risk text. It also emitted 81 outputs of 8 bytes or less, including 10 zero-byte .igb copies.
(2) research/sweep/nav_absent.py, run as-is: nav {True:99, False:21}, boy 98/22, zam 97/23, identical to the claim.
(3) graph.py, run as a copy pointed at verify/graphrun so their graph.json was not overwritten. It reproduces 2,191 nodes, 162 reachable zones (list identical to theirs), 63 missions and the same 24 unreachable campaign zones.
(4) sweeplib.parse_text_xml_robust: 3,897/3,897 distinct non-empty files parse, encode and decode. Stock parse_text_xml fails on exactly the 5 named files. On every other file the robust output is byte-identical to the stock output.
(5) script_functions.json: matches my independent table walk (verify/v_table.py) field for field for all 197 XML1 and 289 XML2 main-table records, plus the 10/13 built-in arithmetic/wait records. I did not re-run script_table.py itself, to avoid overwriting their output.
(6) script_calls.json: my independent recount (verify/v_calls.py) gives the same 22 functions and 1,602 calls.
(7) xml2_copy/maps/mansion/man6/mansion6_1.NAVB is 8 bytes and xmlb.decode raises an unpack error on it.
(8) Their xbedis.py and strpush.py reproduce every cited disassembly address: 0x18d118, 0x18e217, 0x18e2b6, 0x9a3c7, 0x4a0af0, 0x4a0b84, 0x5f491d, 0x5f3d19, 0x4c7fa2, 0x4a0697.
I did not reproduce collisions.json, aggregate.json's per-zone usage counts, or movies.py itself; I wrote my own PES walker instead.
All verifier scripts and outputs are in research/sweep/verify/.

### plan problems
- Zone vars probably reset on every zone load. XML2 CPythonGameInterface slot 2 (0x49fe70) always calls the zone-var clear 0x4d67f0 unless CMap[+0x220] bit 2 is set, and ignores its bool argument. XML1's twin (0x99b90) clears mission vars only when that argument is true, and XML1 also clears them at mission start (0x9a734). The 'setMissionVar -> setZoneVar' rename will therefore likely lose state across zones in multi-zone missions. Plan for a persistent store from the start rather than waiting on the scope test. XML2 getGameFlag/setGameFlag use lookup 0x4d68a0, the structural twin of XML1's game-var store lookup 0xcacd0, so namespaced game flags or generated script state are the candidates. The zone-var save routine 0x49feb0 serialises only 32 slots with 12-byte names; all 111 XML1 MissionVar names are 11 characters or less.
- The mission compiler relies on a mechanism XML2 doesn't have. XML2 beginMission (0x4a0af0) sends 'beginmission %s' to a console where that command is not registered, then only calls CHud vfunc+0x80. Objective files (data/missions/%s.xmlb) are loaded by CMissionMgr slots 0x489190 and 0x489b30. The plan must say how the emitted objective XMLB gets activated. That likely means XML2's own API (objective, getObjective, immediateObjective, missionComplete, missionComplete2, newMissionBriefing, setCurrentAct, unlockCharacter), not beginMission.
- The script translator list is incomplete. XML1-only mission(name,'COMPLETE') (5 calls, e.g. missions/jug_done.py and nyc/alison/blackbird_brief1.py) and xtremeConversationLight (1 call) are not covered. mission() is part of the mission system; missionComplete(s) is a likely XML2 target.
- The New Game hook should be data-only. Replace Scripts/menus/new_game.py and new_game_hard.py, which startFirstMission runs at 0x4a7c42/0x4a7c57. No exe or tutorial change is needed. But startFirstMission first sets up the XML2 roster (magneto, cyclops, wolverine, storm at 0x4a7b41-0x4a7bef), while XML1's alison mission requires exactly wolverine and cyclops (min/max heroes 2). The plan does not handle this roster/team mismatch.
- The nextzone rewrite is only needed for the 5 cross-directory links. XML2's own zones use short same-directory nextzone names in 63 of 144 cases, so the 150 same-directory XML1 links should work unchanged. Rewriting is harmless but should not be treated as a blocker.
- The automap test is probably moot. XML1 builds 'textures/automap/%s' (xbe 0x1526d6-0x152700) and XMen2.exe has no such string; no XML2 zone uses automap_texture. Budget for .zam generation or accept having no automap.
- The data-table merge must handle XML2's paired variants. XML2 ships separate, differing .XMLB and .engb files for npcstat, herostat, zoneinfo, strings and items, and it is unverified which one the engine loads for English. convert_zone.add_zoneinfo only edits data/zoneinfo.xmlb. The merge should write both, or first establish the load rule.
- The 0-byte handling covers text files only. xml1_loose also has 12 zero-byte .igb files: actors/7501.igb (the skin of npcstat 'Computer'), models/ui/models/x_slider.igb and 10 junk-zone maps. The converter copies them as empty files. Character-package conversion will do the same for 7501 unless it is skipped or substituted.
- Evidence for skipping empty NAVB files is weak. The 21 shipping XML2 zones without a nav file are almost all briefings. The 17 reachable XML1 mansion hub zones with empty .nav contain NPCs, so a missing NAVB there needs its own in-game check.
- Minor count corrections. Free two-digit codes are 3 (35, 36, 45), not 4. The i1xx movie collisions are 6 files (XML1 NTSC has no i106). 4 of the '11 missing menu types' are not in XML1's retail xbe either. 3,989 text files includes 21 duplicate paths (3,968 distinct). The '3 latent parse issues' change no output. XML2 beginMission does not load objectives.