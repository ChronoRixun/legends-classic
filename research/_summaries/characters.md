# characters

## SUMMARY
I have a working, offline-validated prototype for grso_riot, plus a naming scheme that avoids every XML1/XML2 filename clash. It is built on what the XMen2.exe code actually does (decompiled in Ghidra), and it has not been tested in-game yet.

The biggest blocker: XML2 keeps every herostat and npcstat name in one fixed table of 296 slots (check at 0x44c1a7, `cmp count,0x129`), and retail XML2 already fills all 296 (21 heroes + 275 NPCs). Any new name is silently skipped, which is why grso_riot never spawned. Heroes have a separate cap of 21 entries (loop at 0x44bb13), and shared talents are capped at 99.

This means XML1 characters cannot simply be added next to XML2's. The recommended approach is an "XML1 mode" install: npcstat holds the 190 XML1 NPCs plus about 20 XML2 entries the exe needs, and herostat is replaced with XML1's 16 heroes. The additive approach only works for small tests: the prototype removes one XML2 NPC nothing refers to ('Varese') and puts grso_riot in its slot.

Skins must be 4–5 digits, and all but the last two digits (the "prefix") must be 255 or less, because the exe stores it in a single byte. XML2 uses prefixes 0–135 and 200; XML1 uses 0–99 and never 60. So the rule "new skin = old skin + 14000" moves every XML1 skin to prefixes 140–239 with no clashes. That covers actor files, HUD heads, UI models, package names and the skin name stored inside each IGB. The exe looks the skin up by that internal name, with a "<skin>_outline" variant for the cel outline, so I patch those names in place without changing file sizes; they fit in all 341 XML1 skin files.

Character animation files that clash get an "x1_" prefix. The shared 'common' animation file and the fightstyle ones stay as XML2's, and powerstyles that clash also get "x1_". The whole scheme checks out with zero collisions. The same builder converts all 190 XML1 NPCs in XML1 mode, and that output also passes validation (229/296 names, 86/99 talents).

Deferred to other workstreams:
- **Sound:** XML1 sound banks are Xbox-format, so the sound reference is dropped until PC banks exist.
- **Weapon system:** XML2 removed it. It ignores the `weapon` attribute, so I turn weapons into bolt-on models. But 14 XML1 combat handlers, including gunfire and grenades, don't exist in XMen2.exe, so GRSO/HAARP gunmen need powers rework.
- **Heroes:** their talent trees and power setup need a separate conversion.

## FINDINGS
- [high] The stats-name table (herostat and npcstat together) has 296 usable slots and XML2 retail uses all 296. New names are silently skipped once the table is full, so any additive XML1 NPC needs an XML2 entry removed or an exe patch.
    EVIDENCE: XMen2.exe 0x44c1a7 `cmp eax,0x129; je 0x44c481` in FUN_0044c030 (the stats file loader; count at [this+0xbba8], entries 0x1c bytes at +0x9b28, index 0 unused). Constructor FUN_0044b520 loops 0x129 times. Hash-node pool wraps at 0x128 (FUN_00449850). The 0x129 constant appears at 11 sites (0x449884, 0x44a38e, 0x44a3b7, 0x44a3d6, 0x44b036, 0x44b558, 0x44c1a7, 0x48f74a, 0x48f77b, 0x48fadf, 0x4d0f40). count_stats.py: XML2 has 21 herostat + 275 npcstat = 296 unique names. Displacement refs listed in research/characters/stats_table_refs.txt (219 lines).
- [high] Name lookup is case-insensitive (lowercased, then hashed). All herostat and npcstat names are registered at boot, whether or not the character is loaded. The table is only reset by vtable+0x20 (FUN_0044b1f0).
    EVIDENCE: FUN_0044acc0 (vtable 0x68544c+0x3c) calls strncpy, then FUN_00602080 (lowercase), then hash lookup at +0xbbac. FUN_0044bab0 (vtable+0) loads data/herostat.xmlb and data/npcstat.xmlb through vtable+0x10 = FUN_0044c030. The only writes of [+0xbba8] are at 0x44b2c1 (reset), 0x44b571 (ctor) and 0x44c06a/0x44c1c9 (loader).
- [high] The hero roster is capped at 21 herostat entries, and at most 31 character stats can be loaded at once.
    EVIDENCE: 0x44bb13 `cmp esi,0x15` in FUN_0044bab0 maps hero indices 0..20. FUN_00449a60 saves 0x16 hero records. FUN_004496d0 pool wraps at 0x1e, and FUN_0044c030 checks param_1[0x26a8] != 0x1f.
- [high] Skin strings must be 4 or 5 digits. Everything but the last 2 digits (the prefix) is stored in one byte, so it must be 255 or less; the last 2 digits are the variant. The engine rebuilds the skin as %02d/%03d(prefix)+%02d(variant). Costume attributes skin_<name> only work for astonishing, aoa, 60s, 70s, weaponx, future, winter and civilian.
    EVIDENCE: FUN_004b9c40 at 0x4b9dbc-0x4b9de3: length check 3<len<6, atoi(len-2 chars), `mov byte ptr [ebp+0x254], al`. FUN_004b8090 formats 0x68e4ec '%02d' / 0x68e4e4 '%03d' then '%s%02d'. Costume table at 0x6d8aa0: default=0, astonishing=1, aoa=2, 60s=3, 70s=4, weaponx=5, future=6, winter=7, civilian=8. XML1's skin_magmacivilian is not in it.
- [high] Character package names are generated/characters/<stats name>_<skin string><'' or '_nc'>. '_nc' is the no-combat package, used when the zone package has <combat_is filename="off"/>; powerstyles are not loaded in those zones. There is also a <name>_xml package.
    EVIDENCE: String 0x68e508 'generated/characters/%s_%s%s' is used at 0x4b8384 (FUN_004b8330, name at +0x150, skin from FUN_004b8090, '_nc' at 0x68e528 chosen by FUN_00484990 vtable+0x3c). 'generated/characters/%s_xml' at 0x4bc1f6; '%s_%s_nc' at 0x5b1578 (menu). FUN_00501bd0 skips data/powerstyles/%s when the same flag is set. 414 XML2 map packages have combat_is on, 53 off. Decoded abyss_0101_nc has no powerstyle or effects.
- [high] A file in actors/ is treated as a skin only if its name is exactly 4 or 5 digits; anything else is loaded as an animation database. 'actors/' and '.igb' are added when missing, so package entries work with or without the prefix.
    EVIDENCE: FUN_0056ae90 checks isdigit on 4 or 5 characters followed by '\0' or '.', then calls FUN_0055e6f0 vtable+0x2c (FUN_0055d670, skin pools) or +0x30 (FUN_0055d5e0, animation pools). FUN_0056af70 calls FUN_00592520(name,'actors/','.igb'), which only prepends/appends when strstr fails.
- [high] The skin model is taken from the character's own skin IGB by internal object name (the skin string), with a fallback to the first skin in the file. The skeleton comes from the skin file. The cel outline is looked up as '<skin>_outline'. So renaming a skin file should also rename those internal names.
    EVIDENCE: FUN_005775b0: igAnimationDatabase::getSkin(db, basename) (import 0x67fd20, call 0x57773e) with fallback getSkinList()->get(0), and getSkeletonList(db)->get(0). FUN_004ea590 and FUN_004a5bd0 format '%s_outline' (0x68d484).
- [high] IGB string fields are stored as a u32 padded length followed by NUL-padded bytes. Renaming '<id>', '<id>_outline' and '<id>_skel' from 4 to 5 digits fits inside the existing padding in every XML1 skin-named IGB, with no size change. Longer sub-part names (e.g. '3401_helmet') don't always fit; they are looked up per file, so they are left unchanged.
    EVIDENCE: xml1_loose/actors/5810.igb: '5810' at 0x20c5 preceded by u32 8; '5810_skel' at 0x1ea1 preceded by 0x0c; '5810_outline' at 0x209d preceded by 0x10. test_igb_rename.py: 341 skin-named IGBs, 240 contain the names, 0 don't fit. Renaming every sub-part name would fail on 14 files. cmp of 5810.igb against out/grso_riot_scheme/Actors/19810.IGB: only 64 string bytes differ.
- [high] HUD and UI character models are loaded as hud/hud_head_<skin>, ui/models/characters/<skin> and ui/hud/characters/<skin>, so they follow the skin renumbering.
    EVIDENCE: FUN_005f4ec0 uses the strings at 0x6a39a4, 0x6a39b4 and 0x6a39cc (refs 0x5f507f, 0x5f506e, 0x5f505d).
- [high] XML2's stats parser accepts the XML1 'weapon' attribute but does nothing with it, and XML2's weapons.XMLB is empty. The XML1 combat handlers ch_weapon_semi_auto, ch_grenade, ch_throw, ch_grab_attack, ch_roguedecide, the ch_air_grab_* and ch_clingwall* handlers, ch_fly_guard_decide and ch_stun don't exist in XMen2.exe. XML1 gun/grenade NPCs therefore need their powers reworked; for melee weapons, turning the weapon into a bolt-on model plus the fightstyle talent is enough.
    EVIDENCE: 0x4ba373-0x4ba383: `_stricmp(attr,'weapon')` jumps to 0x4bb2e7 (`mov al,1`). XML2 Data/weapons/weapons.XMLB decodes to an empty <weapons_list/>. combat_compat.py compares ch_* strings: XMen2.exe has 75, XML1 default.xbe has 71, 14 are XML1-only. Affected XML1 characters are listed in research/characters/combat_compat.txt (e.g. GRSO_mp5, HAARPSoldier, NukeGuard, WeapXGuard, Gambit, Jubilee, Rogue).
- [high] Talent requirements in XML2 treat cat='talent' like cat='skill', but the named talent must be registered. Shared talents get IDs 0..98 (99 max); per-hero talents load from data/talents/<name>.xmlb (up to 9 files). 52 talents used by XML1 NPCs are missing from XML2's shared_talents (including fightstyle_villain, used by 37 NPCs) and must be added. XML2 has 34 shared talents, so the result is 86/99.
    EVIDENCE: FUN_004ac470 maps trait/level/counter/xtreme/race/character to 1..6; anything else is 0 = talent lookup via FUN_004c05b0. FUN_004c05d0 calls FUN_004c0460('data/shared_talents.xmlb',0,99); FUN_004c05f0 uses 'data/talents/%s.xmlb' at base..base+100; the 0x358 != 9 check limits files. build_chars --all-npcs reports 52 talents added.
- [high] Every Race used by XML1 is supported by XML2: none, human, mutant, robot, sentinel, morlock, shadow, astral, xmen, brotherhood.
    EVIDENCE: Race table at 0x6d9710 in XMen2.exe.
- [high] Schema differences in stats: XML1-only attributes are leader, rating* and throwally (not handled by XML2) and weapon (ignored). XML1-only children are activepowerup and scope (heroes) and inline talent definitions (level/require/descname/power index). XML2 moved hero talents into data/talents/<hero>.xmlb (talentvalues, power='powerN'), added power1-4, leadername/leaderskin/mutantskin, specific_* and textureicon, and uses FightMove names power1..N instead of XML1's per-level optic_beam1..10.
    EVIDENCE: research/characters/schema.py compared all 206 XML1 and 296 XML2 stats entries against the attribute list decompiled from FUN_004b9c40 (ghidra/decomp3.c); output in schema_stats.txt and schema_stats.json. Also ps_cyclops: 74 FightMoves in XML1 vs 24 in XML2.
- [high] The damage/knockback value codes (L0..H6, K0..) mean the same numbers in both games' values tables. A1-A10 and XTL1-6 are missing from XML2, and P0+..P10 have different values, so converted XML1 powerstyles that use those codes need their numbers substituted.
    EVIDENCE: schema.py values comparison: 112 XML1 entries; 16 missing and 20 different in XML2 Data/values.XMLB.
- [high] Almost no XML1 file with the same path as an XML2 file is identical: 28 identical and 711 differing (by bytes, or tree comparison for XML). Character-related clashes: skins 110 of 183, animation files 21 of 69, fightstyle animation files 8 of 8, common.igb, HUD heads 40 of 68, ui/hud/characters 65 of 74, ui/models/characters 16 of 16, powerstyles 21 of 93 (1 identical: ps_def), fightstyles 16 of 20. The IGB object types used by XML1 character files all also appear in XML2 IGBs.
    EVIDENCE: research/characters/collisions.py writes collisions.json (all 6268 XML1 loose files checked). igb_meta.py: 151 XML1 actor/hud/ui IGB types; none are absent from the 170 types in XML2 IGBs.
- [high] The skin +14000 rule and the x1_ prefixes produce no clashes with any XML2 file for any of XML1's 185 skins, 121 animation files (21 renamed), 93 powerstyles (21 renamed) and 20 fightstyles (shared).
    EVIDENCE: mapping.py writes x1_namespace_map.json with check_errors = [] (prefix check at 255, file-existence checks against the XML2 index).
- [high] XML1 zone files carry skin numbers that the zone converter must rewrite with the same map: entity monster_skin (305 uses), precache 'Hud/hud_head_<id>' (40), and package actorskin/actoranimdb/UI entries. XML2 map packages also list NPC actor files, so the zone package for nyc1_1_1 in xml2_test preloads actors/5810 and 53_grso.
    EVIDENCE: skinrefs.py scans every XML1 text XML and .py file. Decoded xml2_test/Packages/generated/maps/nyc/alison/nyc1_1_1.PKGB (read only). XML2 map packages contain actorskin entries (e.g. 51× actorskin 1101).
- [medium] 44 XML2 stats names have no exact-string reference anywhere else in XML2 (data, maps, scripts, packages or the exe). These are the candidates to remove in additive mode; the prototype removes 'Varese' and puts grso_riot at its position (index 39).
    EVIDENCE: x2_unref.py writes x2_stats_refs.json. Comparing the output npcstat.engb with the original shows the only difference is index 39 (Varese replaced by grso_riot).
- [high] XML1 sound banks are Xbox format and XML2 has no grso_m bank. The prototype omits sounddir rather than point it at a missing bank; 95 XML1 NPC sounddirs are deferred.
    EVIDENCE: Header of xml1_xbox/sounds/zsds/c/y/cyclop_m.zsm is 'ZSNDXBOX'; XML2 Sounds/eng/c/y/cyclop_m.zsm is 'ZSNDPC  '. Banks sit at Sounds/eng/<c1>/<c2>/<name>.zsm (all 104 XML2 banks). build report: 'sounddir grso_m has no PC bank'.

## PLAN
1. In-game test of grso_riot (orchestrator): Copy the contents of research/characters/out/grso_riot_scheme/ (except _build_report.json) into xml2_test/, keeping the folder structure. Files: Actors/19810.IGB, Actors/53_grso.IGB (same bytes as the existing xml2_test actors/53_grso.igb), UI/HUD/characters/19810.IGB, Packages/generated/characters/grso_riot_19810.PKGB, Packages/generated/characters/grso_riot_19810_nc.PKGB, and Data/npcstat.XMLB + Data/npcstat.engb (these overwrite: XML2's npcstat with Varese replaced in place by grso_riot, skin 19810, animation 53_grso, powerstyle ps_def, talents might + fightstyle_baton, Race Human, baton bolt-on in the weapon slot, no sounddir). Load nyc/alison/nyc1_1_1: spawners ss_grso_riot03 and ss_grso_riot11 should produce 'Anti-Mutant Troop' holding a baton.
2. Bisect if it fails: out/grso_riot_orig keeps skin 5810 and no IGB rename; it tests only the stats + package path. out/grso_riot_animprefix also renames the animation file to x1_53_grso, which confirms animation-file renaming for the 21 clashing ones. All three pass validate.py. Rebuild with: python build_chars.py --variant scheme|orig|animprefix --out out/<dir> grso_riot && python validate.py out/<dir>.
3. Use x1names.py / x1_namespace_map.json in the zone converter: Rewrite actorskin/actoranimdb/model(hud_head, ui/*/characters) entries in converted zone packages, entity monster_skin, precache filenames and BoltOn/trigger actorskin values with map_skin / map_animdb / map_ui_path. Leave '<id>_<part>' names alone. Copy skin IGBs through x1names.igb_rename.
4. Choose XML1 mode for the real port: Run build_chars.py --all-npcs --mode xml1 (validated: 190 NPCs, 229/296 names, 380 packages, shared_talents 86/99). It keeps the 4 _HEROn_MC_ placeholders plus 16 npcstat names that appear as strings in XMen2.exe; same-named XML1 entries win. Additive mode only fits up to about 44 XML1 NPCs, and only by dropping unreferenced XML2 entries.
5. Sound workstream hand-off: Produce PC ZSND banks for the 50 XML1 sounddirs (95 NPC uses; 32 bank names also exist in XML2 with different content, so rename those, e.g. with an x1 prefix) at Sounds/eng/<c1>/<c2>/<name>.zsm, then remove the sounddir omission in build_chars.convert_stats.
6. Powers workstream hand-off: Converted XML1 powerstyles are marked 'power-system review pending' (72 in the XML1-mode run). Replace FightMoves that use missing handlers (ch_weapon_semi_auto, ch_grenade, ch_throw, ch_grab_attack, ch_roguedecide, ch_air_grab_*, ch_clingwall*, ch_fly_guard_decide, ch_stun) with XML2-style event projectiles (see ps_mercenary). Substitute numbers for A1-A10, XTL1-6 and the P codes. Resolve the unknown triggers listed in combat_compat.txt (systemshock, tintin/tintout, beamdata, ...).
7. Hero conversion (follow-up): Replace herostat with XML1's 16 entries (21 max) and map the clashing XML1 hero names on top of XML2's. Per hero: move the inline Talent trees into data/talents/<name>.xmlb in XML2 format (talentvalues, power='powerN'); convert activepowerup (289 elements) into powerstyle powerups; add power1-4 and autospend; generate HUD heads and ui/models/characters for every costume (+14000); rebuild the menus/characters_heads(_pc) package and the textureicon atlas. Magma's skin_magmacivilian costume has no XML2 slot.
8. Optional exe patch (only if an additive install is wanted): Raise the 296-name limit by relocating the 0x1c-stride array at [this+0x9b28], the hash map at +0xbbac/+0xd32c and the hero list at +0x120dc, growing the 0x12334-byte allocation in FUN_0044b8f0, and patching the 11 immediate 0x129 sites plus the displacement refs in stats_table_refs.txt. Not attempted.

## ARTIFACTS
- research/characters/out/grso_riot_scheme/Actors/19810.IGB
- research/characters/out/grso_riot_scheme/Actors/53_grso.IGB
- research/characters/out/grso_riot_scheme/UI/HUD/characters/19810.IGB
- research/characters/out/grso_riot_scheme/Packages/generated/characters/grso_riot_19810.PKGB
- research/characters/out/grso_riot_scheme/Packages/generated/characters/grso_riot_19810_nc.PKGB
- research/characters/out/grso_riot_scheme/Data/npcstat.XMLB
- research/characters/out/grso_riot_scheme/Data/npcstat.engb
- research/characters/out/grso_riot_scheme/_build_report.json
- research/characters/out/grso_riot_orig/
- research/characters/out/grso_riot_animprefix/
- research/characters/out/all_npcs_xml1/
- research/characters/build_chars.py
- research/characters/validate.py
- research/characters/x1names.py
- research/characters/x1_namespace_map.json
- research/characters/mapping.py
- research/characters/collisions.py
- research/characters/collisions.json
- research/characters/inventory.py
- research/characters/inventory_characters.json
- research/characters/inventory_characters.tsv
- research/characters/schema.py
- research/characters/schema_stats.txt
- research/characters/schema_stats.json
- research/characters/combat_compat.py
- research/characters/combat_compat.txt
- research/characters/combat_compat.json
- research/characters/x2_unref.py
- research/characters/x2_stats_refs.json
- research/characters/prefixes.py
- research/characters/skinrefs.py
- research/characters/test_igb_rename.py
- research/characters/igb_meta.py
- research/characters/igbstr.py
- research/characters/animcmp.py
- research/characters/count_stats.py
- research/characters/common.py
- research/characters/dump_x2.py
- research/characters/x2text/
- research/characters/dx.py
- research/characters/exestr.py
- research/characters/peek.py
- research/characters/finddisp.py
- research/characters/stats_table_refs.txt
- research/characters/ghidra/DecompAt.java
- research/characters/ghidra/run_decomp.sh
- research/characters/ghidra/proj/
- research/characters/ghidra/decomp1.c
- research/characters/ghidra/decomp2.c
- research/characters/ghidra/decomp3.c
- research/characters/ghidra/decomp4.c
- research/characters/ghidra/decomp8.c
- research/characters/ghidra/decomp9.c
- research/characters/ghidra/decomp11.c
- research/characters/ghidra/decomp12.c
- research/characters/ghidra/decomp13.c

## RISKS
- Additive mode relies on dropping XML2's 'Varese'. The 44 'unreferenced' names were found by exact-string match only, so a script that builds names at runtime could still ask for a dropped entry.
- The in-IGB rename of '<id>', '<id>_outline' and '<id>_skel' is byte-safe (sizes unchanged, validated), but I can't check offline whether the Alchemy loader also caches names elsewhere. The orig variant isolates this.
- Renamed animation files (x1_ prefix, used for the 21 clashing ones) keep their original internal names. The code I traced binds the skeleton from the skin file, but this is not proven for animation lookup; the animprefix variant tests it.
- The in-game appearance of XML1 Xbox-exported textures in character IGBs is unverified. All IGB object types exist in XML2, and the converted zone already renders.
- Converted XML1 powerstyles/fightstyles keep XML1 combat semantics: missing handlers, unknown triggers, and differing or missing value codes (P*, A*, XTL*). Affected NPCs may spawn but fight wrongly or not at all. grso_riot uses ps_def (identical in both games) and XML2's fightstyle_baton, so it avoids this.
- The 52 XML1 NPC talents are added as empty definitions. Passive XML1 talents such as acrobatics, toughness and mutantmastery would do nothing unless XML2 implements them by name.
- XML1-mode shared_talents reaches 86 of the 99-slot limit; hero talent conversion must stay within that or use per-hero files.
- XML1 stat levels (grso_riot is level 1, stats 1-4) under XML2's stat rules will make enemies very weak; balance is out of scope.
- Some XML1 powerstyles referenced by weapon definitions (ps_grso, ps_pistol, ...) don't exist in XML2 at all and were converted from XML1 text, so their content is untested.

## OPEN QUESTIONS
- In-game: do both grso_riot spawners in nyc1_1_1 appear, render with the XML1 riot-trooper model, animate, hold the baton and fight with the scheme variant? If not, which of orig / scheme / animprefix works?
- Does the English game read Data/npcstat.engb or npcstat.XMLB? Both are written with identical content, but knowing which avoids double maintenance. The language fallback code is at 0x5898f7 (not fully traced).
- Is a sounddir that points at a missing bank tolerated? XML2 ships one (svsdab_m on svs_DazzlerBaddy), but that NPC may never be spawned. Test once the sound workstream has a grso_m PC bank.
- Decision: XML1-only install (npcstat replaced; recommended given the 296/21 caps) or an additive install that needs an exe patch to raise the 0x129 limit?
- Decision: fidelity for fightstyles (x1_fightstyle_* plus new shared talents and packages) versus sharing XML2's same-named fightstyles (current default; XML1 fightstyle_gun_rifle has 9 animation names that XML2's lacks).
- Does the outline (cel shading) show on renamed skins? This checks the '<skin>_outline' rename.
- Hero plan: which XML2-only heroes, if any, to keep in the 21-entry roster alongside XML1's 15 heroes + default?

## VERIFICATION
verdicts: Counter({'confirmed': 13, 'partly-wrong': 5})
- CONFIRMED: The stats name table has 296 usable slots, XML2 retail fills all 296, and new names are silently skipped
    NOTE: 0x44c1a7 is `cmp eax,0x129 / je 0x44c481`. The count starts at 1 because 0x44c05a-0x44c06a sets it to 1 when it is 0, so indices run 1..0x128, which is 296 slots. The ctor loop at 0x44b558 runs 0x129 times. The only caller of the hash insert FUN_0044b120 is 0x44c3b7, inside the loader. There are 4 vt+0x10 loader calls, and every one passes data/herostat.xmlb or data/npcstat.xmlb (0x44bab4, 0x44bac7, 0x44bc97, 0x4d0d67). My own recount gives herostat 21 + npcstat 275 = 296 unique names in both XMLB and engb. The only platform tags are 2 entries with platform=PC, so they count on PC. All 11 0x129 immediate sites were reproduced. Caveat: the summary says this is 'why grso_riot never spawned', but the milestone notes say grso_riot was simply missing from npcstat. That part is unverified and misleading.
- CONFIRMED: Name lookup is case-insensitive, all names are registered at boot, and only 0x44b1f0 resets the table
    NOTE: 0x44acc0 (vt+0x3c) does strncpy 0xff, then 0x602080 (a per-char CRT case map at 0x6723d4), then the hash lookup. The loader lowercases the key the same way (decomp1.c:733-747). A byte scan finds exactly 4 writes to [+0xbba8]: 0x44b2c1, 0x44b571, 0x44c06a and 0x44c1c9.
- PARTLY-WRONG: The hero roster is capped at 21 herostat entries and at most 31 character stats can be loaded at once
    NOTE: The 0x44bb13 loop (`cmp esi,0x15`) maps exactly 21 hero indices into 0xa6a800. However, the loader appends heroes to the short array at +0x120dc with no bound (decomp1.c:690-693), and that array holds 298 entries. So more than 21 heroes is a mapping/UI limit, not a hard cap. FUN_00449a60 loops 0x16 = 22 records of stride 0x160 (0x449b05), not 21. The pool in FUN_004496d0 wraps at `cmp ecx,0x1f; jl`, not 0x1e (31 is still right). With fewer than 21 heroes, the allocator zeroes memory (0x560627 rep stosd), so the extra iterations write to index 0 of 0xa6a800. That is memory-safe but has never been exercised.
- CONFIRMED: Skins must be 4 or 5 digits with a byte-sized prefix; the engine rebuilds them with %02d/%03d + %02d; skin_<costume> only works for 8 names
    NOTE: 0x4b9dbc: `cmp esi,3; jle` and `cmp esi,6; jge`, then atoi(len-2) goes into the byte at +0x254 and the last 2 digits into +0x255. 0x4b8090: `cmp al,0x64` selects '%02d' (0x68e4ec) or '%03d' (0x68e4e4). The costume table at 0x6d8aa0 is default=0 … civilian=8, and skin_magmacivilian is absent. Something the research misses: the prefix byte also builds 'textures/loading/%02d%02d.igb|png' (0x688f7c and 0x688f5c, used at 0x487258 and 0x4872af). XML2 ships 74 of these files, and the rename scheme does not cover them. The engine checks they exist before loading.
- CONFIRMED: Character packages are generated/characters/<stats name>_<skin>[_nc], and _nc packages have no powerstyles
    NOTE: 'generated/characters/%s_%s%s' is at 0x68e508 (xref 0x4b8383), with name at +0x150, skin from 0x4b8090 and '_nc' at 0x68e528 chosen by FUN_00484990 vt+0x3c. Empirically, all 292 XML2 stats entries that have a skin have both packages, and the 4 _HEROn_MC_ entries have no skin. None of the 742 XML2 _nc packages contain powerstyles. I could not trace that the flag is literally combat_is, but 414 map packages have it on and 53 off.
- CONFIRMED: An actors/ file whose name is exactly 4-5 digits is a skin; anything else is an animation DB; 'actors/' and '.igb' are added only when missing
    NOTE: 0x56ae90 isdigit-checks 4 characters, then a 5th, and requires '\0' or '.' after them; it then calls vt+0x2c (skin) or vt+0x30 (anim). 0x592520 uses strstr before sprintf-prefixing. Because strstr is case-sensitive, package entries must use the lowercase 'actors/'.
- CONFIRMED: The skin model is looked up by internal name via getSkin, falls back to the first skin, and the outline uses '<skin>_outline'
    NOTE: 0x57773e calls the import at 0x67fd20 = ?getSkin@igAnimationDatabase@Sg@Gap@@QBEPAVigSkin@23@PBD@Z. When it returns null, 0x57776d calls getSkinList (0x67fe88) and 0x67fd24. '%s_outline' (0x68d484) is used at 0x4a5c8f and 0x4ea5b6. Because of the fallback, the in-IGB rename is not required for the model itself, only for the outline. Animation DBs carry their own '<file>_skel' (53_grso.igb contains '53_grso_skel', and every XML2 anim DB follows <file>_skel), so renaming the skin's '_skel' does not touch animation binding.
- CONFIRMED: Renaming '<id>', '<id>_outline' and '<id>_skel' from 4 to 5 digits fits in the existing IGB padding in every XML1 file
    NOTE: My independent scanner covered 341 XML1 skin-named IGBs (actors, hud, ui). 240 contain the names, 1241 length-prefixed strings in total, and none fail to fit. Diffing 5810.igb against 19810.IGB shows exactly 64 differing bytes in 7 strings (0x1ea1, 0x209d, 0x20c5, 0x27cd, 0x283d, 0x2a19, 0x2a35). The HUD IGB has 20 bytes in 4 strings. The format matches native XML2 5-digit skins: 10901.IGB stores '10901' with padded length 8 and '10901_skel' with 12. All 416 XML2 numeric actors contain '<id>' and '<id>_skel'; 135 contain '<id>_outline'.
- CONFIRMED: HUD and UI models load from hud/hud_head_<skin>, ui/models/characters/<skin> and ui/hud/characters/<skin>
    NOTE: The strings at 0x6a39a4, 0x6a39b4 and 0x6a39cc have xrefs exactly at 0x5f507f, 0x5f506e and 0x5f505d. I did not trace which string feeds %s.
- PARTLY-WRONG: XML2's stats parser ignores 'weapon', XML2's weapons file is empty, and 14 XML1 combat handlers are missing, so gun and grenade NPCs need their powers reworked
    NOTE: Confirmed parts: 0x4ba373-0x4ba383 `_stricmp(attr,'weapon'); je 0x4bb2e7` (`mov al,1`), and Data/weapons/weapons.XMLB decodes to <weapons_list />. My own ch_* extraction (registration table 0x4fd975-0x4fe88a) gives exactly the same 14 XML1-only names. The consequence is overstated. XML2's own retail data uses 4 handlers the exe never registers: ch_sab_frenzy, ch_sab_lunge and ch_sab_lunge_attack in ps_sabertooth_hero, which belongs to Sabretooth, a PC-exclusive playable hero, and ch_grenade in moveset_grenade and moveset_stealth. Unknown handler names are therefore evidently tolerated, and the move just runs without the handler logic. XML2 still parses monster_weapon and monster_grenade on spawners (0x4633ad and 0x4633bf; XML1 uses monster_grenade="flashbang" 6 times) and has the trigger type ce_atk_spawn_grenade (0x692da8, xref 0x4fb3f3). So 'removed the weapon system' is not absolute.
- CONFIRMED: Shared talents get IDs 0..98 (99 max); 52 talents are added, giving 86/99
    NOTE: At 0x4c05d0, FUN_004c0460 is called with (path, 0, 0x63, 0, 2), and it loads talents only while param_3 < param_4, so IDs 0..98 and any extra are silently dropped. Per-hero files use base..base+100. The file limit is 0x358 != 9. XML2 shared_talents has 34 talents in both XMLB and engb; the rebuilt XML1-mode output has 86 in both, with 52 added.
- CONFIRMED: Every Race used by XML1 is supported by XML2
    NOTE: The table at 0x6d9710 is none/human/mutant/robot/sentinel/morlock/shadow/astral/xmen/brotherhood (0..9). XML1 stats use mutant 111, human 40, robot 15, astral 13, morlock 13, shadow 11 and sentinel 5, all present.
- PARTLY-WRONG: L/K value codes match between the games; A1-A10 and XTL1-6 are missing; P codes differ (16 missing, 20 different)
    NOTE: The 16 missing codes are confirmed: A1-A10 and XTL1-6. There are 34 differing codes, not 20: BST1, BST9 and P0+ through P16. schema.py line 114 prints `diff[:20]`, so the count of 20 is an artifact of print truncation. The powers hand-off must substitute BST1/BST9 as well as the P codes, all the way to P16.
- CONFIRMED: Same-path collision counts (skins 110/183, anim 21, fightstyle anim 8/8, common, HUD heads 40/68, ui/hud 65/74, ui/models 16/16, powerstyles 21 differ + 1 identical of 93, fightstyles 16/20)
    NOTE: My independent v_collide.py reproduces every count. One exception: I count 112 non-skin, non-fightstyle anim IGBs in XML1 actors/ rather than 69. The 21 differing ones match. ps_def is the identical powerstyle.
- CONFIRMED: The +14000 skin rule and x1_ prefixes produce no clashes with XML2
    NOTE: XML1 has 183 numeric actor files, all 4-digit, with prefixes 0-99 and never 60. XML2 numeric actors use prefixes 0-135 plus 200; HUD/UI max out at 130. No mapped id collides with any XML2 actors, HUD or UI file, and no mapped prefix collides. x1_namespace_map.json has check_errors = [].
- CONFIRMED: XML1 zones carry skin numbers that the converter must rewrite: monster_skin 305 uses, hud_head precache 40, and package entries
    NOTE: grep over .eng/.xml finds 305 monster_skin values and 40 hud/hud_head_ references. XML2's monster_skin takes a full skin (monster_skin="20021" appears 10 times), so mapping to 5 digits is valid. Test zone nyc1_1_1.PKGB lists actoranimdb actors/53_grso and actorskin actors/5810. Its spawners use character="grso_riot" with no monster_skin, so the stats skin applies. skinrefs also shows XML1 entity 'loading' attributes such as 'textures/loading/3001', which follow the skin-keyed loading-texture convention and are not in the map.
- PARTLY-WRONG: 44 XML2 stats names are unreferenced; the prototype replaces Varese at index 39
    NOTE: The prototype diff is confirmed: in all three variants, both npcstat.XMLB and npcstat.engb differ from retail only at index 39 (Varese to grso_riot). Varese appears elsewhere only in voice/varese/ paths. The list of 44 is not clean. A case-insensitive token search finds %NAME% speaker tokens in conversation text for nickfury (12 files), squawkbox (8) and caleb_bann (1). 79 of the 91 distinct %TOKEN%s in XML2 conversations are stats names, so these are systematic runtime references, and those 3 are not safe to drop. The psychicdemon_c hit is only a comment.
- PARTLY-WRONG: XML1 sound banks are Xbox format, XML2 has no grso_m bank, and banks sit at Sounds/eng/<c1>/<c2>/<name>.zsm (all 104 XML2 banks)
    NOTE: The headers are confirmed: 'ZSNDXBOX' in XML1 and 'ZSNDPC  ' in XML2. XML2 has no grso bank. The layout rule holds, but XML2 has 202 .zsm files under Sounds/eng (154 of them *_m), not 104. The XML1-mode build reports 96 sounddir deferrals, not 95.

### artifact check
I ran every prototype tool, and all of them do what the researcher said. My scratch scripts are in research/characters/verify/.

- **Three grso_riot variants:** `build_chars.py --variant scheme|orig|animprefix grso_riot` rebuilt into verify/rb_*. Each output is byte-identical to the shipped out/grso_riot_* tree, with the same file lists. The scheme variant has 7 files, orig 6 and animprefix 7.
- **Validation of the variants:** `validate.py` printed RESULT: PASS for all three. The scheme notes read '7 names renamed, 64 bytes changed' for actors/19810 and '4 names renamed, 20 bytes' for ui/hud/characters/19810.
- **Build report:** the grso_riot entry reads skin 19810, characteranims 53_grso, ps_def, talents might(2) and fightstyle_baton(1), Race Human, BoltOn models/bolton/baton in slot ebolton_weapon, no sounddir. The stats name count stays 296/296.
- **All NPCs, XML1 mode:** `build_chars.py --all-npcs --mode xml1` gives 190 entries, 1230 files, 229/296 names, 52 talents added (86 total), 380 packages and 96 deferrals (all sounddir). validate.py passes, and the shipped out/all_npcs_xml1 also passes. 72 styles are marked review-pending (68 powerstyles and 4 fightstyles).
- **Other tools:** count_stats.py, prefixes.py, skinrefs.py and test_igb_rename.py ran and matched the claimed numbers. test_igb_rename.py reported 341/240/0 unfit.
- **Packages:** the decoded grso_riot_19810.PKGB has the same shape as XML2's native mercenary_a_5810.pkgb: actorskin, actoranimdb, ui model, powerstyle, bolton model, fightstyle anim DB and fightstyle.
- **Test copy (read only):** Actors/53_grso.IGB is byte-identical to xml2_test/Actors/53_grso.igb, as claimed. xml2_test's npcstat, herostat and shared_talents are currently identical to retail.
- **Exe copy:** ghidra/XMen2.exe has the same SHA-1 (7d95cdb4…) as the real exe.

I did not re-run collisions.py, mapping.py, schema.py, x2_unref.py or combat_compat.py, because they overwrite the researcher's JSON. I reproduced their key numbers with independent scripts instead: v_collide.py, v_values.py, v_unref.py and v_handlers.py.

### plan problems
- The plan treats missing combat handlers as meaning the NPC 'may spawn but fight wrongly or not at all', and routes 14 handlers to a powers rework. XML2 retail itself ships unregistered handlers: Sabretooth (PC-exclusive, playable) uses ch_sab_frenzy, ch_sab_lunge and ch_sab_lunge_attack, and moveset_grenade/moveset_stealth use ch_grenade. So unknown handlers load and are presumably ignored. A cheaper first test is to run XML1 styles as they are. XML2 also keeps ce_atk_spawn_grenade and the monster_weapon/monster_grenade spawner attributes (0x4633ad, 0x4633bf), which could carry XML1 grenades without a full rework.
- The powers hand-off lists only 'the P codes'. In fact 34 value codes differ, including BST1, BST9 and P0+ through P16. The number 20 came from schema.py printing diff[:20].
- The additive-mode list of 44 'unreferenced' names is unsafe as a drop list. At least nickfury, squawkbox and caleb_bann are referenced through %NAME% speaker tokens in XML2 conversation text; 79 of the 91 distinct tokens are stats names. The reference check should include %token% scanning and case-insensitive substring search, not just exact attribute values. Varese itself is safe.
- The skin renumbering misses one engine-derived path. Loading-screen textures are built from the skin prefix byte as textures/loading/%02d%02d.igb|png (0x487258, 0x4872af; XML2 ships 74). XML1 zone 'loading' entity attributes also reference textures/loading/<id>. The hero plan and zone converter need these mapped (+14000) or supplied; the engine checks they exist, so they fail silently.
- XML1-mode keeps XML2 npcstat entries named beast, profx, forge, archangel and others, and the hero plan then puts XML1 heroes such as Beast into herostat. The name table registers a name only once, and the second file's entry takes the 'already registered' path (LAB_0044c3c9). The plan needs to drop kept npcstat names that collide with the new herostat.
- The hero plan says 'XML1's 16 entries (21 max)', but XML2 retail always has exactly 21. With fewer, the 0x44bb13 loop still runs 21 iterations and maps unused slots to stats index 0. This is memory-safe (the allocator zero-fills) but untested; padding to 21 would be safer. More than 21 is not a memory cap (the hero list holds 298) but a mapping/UI limit.
- Bisect variants are not clean. 'orig' silently uses XML2's different UI/HUD/characters/5810.IGB, and XML2 also ships a leftover package mercenary_a_5810 that references actorskin 5810 + 53_grso. 'animprefix' produces x1_53_grso.IGB whose internal skeleton is still '53_grso_skel', while every XML2 anim DB names its skeleton <file>_skel. A failure there could come from that convention break rather than from the rename, confounding the bisect.
- Because getSkin falls back to getSkinList()->get(0) (0x57776d), the in-IGB rename cannot be confirmed by the model rendering. Only the cel outline ('<skin>_outline') tests it. The in-game test should check the outline specifically.
- The open question says npcstat.XMLB and npcstat.engb are 'written with identical content'. They are not identical files. Retail XMLB uses @DATA@ localisation keys for charactername and engb uses English text, and 271 of 275 entries differ. The builder correctly patches each file from its own base; only the new entry is identical. If the game reads XMLB, 'Anti-Mutant Troop' shows as a literal string, which is harmless.
- Converted NPCs lack the specific_attack, specific_defense and specific_health attributes and the monst_dmg_* talents that every XML2 enemy carries (for example Mercenary_a). Combined with XML1 level 1 and stats 1-4, grso_riot may be close to harmless in-game, which could be mistaken for broken AI during the test.
- The summary says grso_riot 'never spawned' because the 296-slot table is full. The stated milestone says grso_riot was simply absent from XML2's npcstat. The table limit is real, but no evidence was shown that an added grso_riot was ever loaded and skipped.