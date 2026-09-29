# Elite Acolyte spikes (late-game test B3): XML1 skins against their anim DBs (2026-09-29)

Bug B3 of research/campaign/late_game_test.md: in Asteroid M's Magneto room (astroid_m/visit1/asteroid2_1) the elite
Acolytes AcolyteEnergy_B and AcolyteLeader_B (XML1 skins 4805 / 4808 -> 18805 / 18808, anim DB `48_acolyteenergy`)
drew huge flat black spikes, in the meeting's conversation camera and in the fight (late shots 23 / 24 / 25).

**Result.** The two skins are sound, the pipeline does not alter them beyond the in-IGB rename, and the spikes did
**not** come back: the byte-identical 18805 drew correctly in seven in-game sessions of build/_skins, next to an
A/B copy (18808 with its outline widened to 3 blend weights). B3 was a runtime state of the late test's session,
not a property of the files; it stays open until it recurs with a way to reproduce it. The branch adds what the
investigation built: validator V20 (skin / skeleton / blend checks against the anim DB), a scanner, IGB tooling
that can resize memory blocks, and an exact blend-weight padder kept as a tool (SPEC.md section 25).

## 1. The Acolyte variants

| stats entry | name | skin | anim DB | powerstyle | vertex arrays (format) |
|---|---|---|---|---|---|
| AcolyteEnergy | Acolyte | 4801 -> 18801 | 48_acolyteenergy | ps_acolyte_energy | '4801' 0x10223 (no outline) |
| AcolyteLeader | Acolyte Master | 4804 -> 18804 | 48_acolyteenergy | ps_acolyte_energy | '4804' 0x10333, '4804_outline' 0x331 |
| **AcolyteEnergy_B** | Acolyte Elite | **4805 -> 18805** | 48_acolyteenergy | ps_acolyte_energy_b | '4801' **0x10223**, '4802_outline' **0x221** |
| **AcolyteLeader_B** | Acolyte Master Elite | **4808 -> 18808** | 48_acolyteenergy | ps_acolyte_energy_b | '4801' **0x10223**, '4802_outline' **0x221** |
| AcolyteSmash | Acolyte Warrior | 4802 -> 18802 | 48_acolytesmash | ps_acolyte_smash | '4802' 0x10333 |
| AcolyteSmash_B | Acolyte Warrior Elite | 4806 -> 18806 | 48_acolytesmash | ps_acolyte_smash_b | '4802' 0x10333, '4802_outline' 0x331 |
| AcolyteMental | Acolyte Adept | 4803 -> 18803 | 48_acolytemental | ps_acolyte_mental | '4803' 0x10333, '4802_outline' 0x331 |
| AcolyteMental_B | Acolyte Adept Elite | 4807 -> 18807 | 48_acolytemental | ps_acolyte_mental_b | '4803' 0x10333, '4802_outline' 0x331 |

(vertex format: igVertexFormat bits 0 position, 1 normal, 4-7 blend weights, 8-11 blend indices, 16-19 texcoord
sets - libIGGfx.dll getBlendWeightCount 0x10001d30 `>>4 &0xf`, getBlendIndexCount 0x10001d60 `>>8 &0xf`.)
4805 and 4808 are the same model (the Leader's 875 / 543 vertices, texture 4805_4808) with 2-weight skinning; the
geometry names are the artists' leftovers ('4801', '4802_outline').

## 2. Static comparison (scratchpad skins/dump.py, va.py, bonecheck.py, geomcheck.py; skins.check_skin)

- **Skeletons.** Every skin has its own 35-bone `<id>_skel` (32 with blend matrices); every anim DB skeleton has the
  same 35 names with no blend matrices. 4801 / 4802 / 4804 list the bones in the anim DB's order; 4803 / 4805-4808
  put 'Motion' second instead of last (130 of the 200 XML1 skin / anim DB pairs differ in order). The bodies of
  4803 / 4806 / 4807 and of the elites animate correctly, so XMen2.exe matches skin bones to anim DB bones by name.
  All 32 blend bones of 4805 / 4808 exist in 48_acolyteenergy.
- **Blend palette.** 32 entries (a permutation of the 32 blend matrices); every vertex index < 32; every weight set
  sums to 1.0 exactly; resolving index -> palette -> bone, 541 of the 543 outline vertices land on the same bone as
  the nearest body vertex (the other two: neighbouring finger bones) - the outline is bound correctly.
- **Geometry.** Index buffers (1717 / 1508 strip indices) stay inside their vertex arrays; one strip each.
- **What only these two have** among the Acolytes: 2 blend weights per vertex in both arrays. Across the XML1 stats
  skins 20 blend 1 or 2 weights somewhere (the plain 4801 too, which draws fine); every XML2 skin in use blends 3-4
  (XML2's own 0x221 / 0x10223 arrays are in unused costumes 0105 / 0906 and the default-man skins).
- **libIGGfx.dll (Ghidra, scratchpad skins/gproj):** at load every blended igDxVertexArray1_1 gets 4 internal
  weights when vertex-shader skinning is on (makeConcrete 0x10047040 / configure 0x10045c40: `this[0x4c] = 4`), the
  unused slots zeroed from the index count up (initUnusedBlendWeights 0x10047ff0), vertex declaration FLOAT4 weights +
  D3DCOLOR indices (0x10048980); the shader is looked up per pipeline state (findShaderHandle 0x10039e40,
  pickVertexShader 0x10049ee0) and an array without a shader drops to CPU skinning for good
  (setVertexShaderBlendingState_Dx 0x10047f80: makeAbstract 0x10047560 + makeConcrete); the CPU blend
  (blendVertices 0x10047940 -> igVectorBlending, SSE 0x10022df0 in libIGMath) handles any weight count. No path
  treats 2 weights differently from 3 in a way that would place a vertex elsewhere. (XMen2.exe's own '%s_outline'
  uses, 0x4a5bd0 / 0x4ea590 / 0x48c700, are the segment show / hide functions, not the outline's rendering.)

## 3. In game: seven sessions, no spikes

build/_skins = this branch, `--no-movies`; harness `install build/_skins --limits --pipe-name skins --save-folder
"X-Men Legends (skins tests)"`, pipe `skins` only (three other agents' games were running and never touched).
Actors swapped for the A/B test (restored afterwards): **18805 = the original file** (identical to build/_heroes',
the late test's), **18808 = outline padded to 3 weights** (body still 2), 18806 original, 18807 outline reduced
from 3 to 2 weights. Scripts: research/characters/skins_test/ (drive.py, magneto.py, longrun.py, variants.py).
Screenshots: the session's scratch folder `skins\shots\` (not kept).

| # | conditions | Magneto room reached by | spikes | shots |
|---|---|---|---|---|
| 1 | Begin Story, begin_asteroid_rock (4-hero party, level 1); a fight with elite Acolytes in asteroid1_1 | loadMapKeepTeam | none | s1_07/08 sheets, s1_12_crop5, s1_13_crop3 |
| 2 | alchemy.ini [GFX] disableVertexShaderBlending = true (CPU skinning for everything), Wolverine alone | loadMapKeepTeam | none | s2_02 / s2_03 sheets |
| 3 | the late test's path: begin_asteroid_rock, begin_asteroid_int, awardXPToPlayable(8411600) -> 31, zone_link02 + E; 9-13 fps (3 other games) | zone link | none | s3_03_sheet |
| 4 | 17 zones first (mansion8, astral2_x, asteroid1_x / 2_x, mastermold1/2, nyc, arbiter), then the late path | zone link | none | s4_meet / s4_fight sheets |
| 5 | the r302 movie played (and skipped) before the late path | zone link | none | s5_overview, s5 sheets |
| 6 | 17 zones, mainMenuExit(), Begin Story again, the late path (the late test had a game over -> main menu -> Begin Story) | zone link | none | s6 sheets |
| 7 | the late test's xml2-fix DLL (scratchpad/dll/dinput_1c750e3.dll), the late path | zone link | none | s7 sheets |

`compare_late_vs_skins.png`: late test 23 / 24 (spikes) against sessions 4 / 1 (same cameras, same 18805 file).
Differences from the late session that were not reproduced: ~1 h of play incl. a campaign_walk run, 6-20 fps for
most of it, an XInput pad connected (xinput: pad 1 connected), the movies build (all movies, not only r302).

## 4. The scanner and V20 (skins.py)

`python -m xml1build.skins scan xml1_loose` (206 stats skins of the disc) and `check build/_skins` (160 XML1 skins
incl. costumes via V20):

- **0 structural errors** (count mismatch, index outside palette, palette without bone, weights off 1).
- **Skin / skeleton mismatch** (vertices weighted to bones the anim DB skeleton lacks; all as shipped on the XML1
  disc -> V20 warnings marked inherited): Colossus 0901/0902/0904 (+ costumes 0903/0906), Gambit 1301, ProfX
  Gladiator 1105, Moira 2101 - ponytail bones, 1-18 vertices; the four wingless Shades 3502/3504/3512/3514 (3
  vertices); AstralGhost 3705 (80 vertices); SentinelSpider 5504 (both toes, 173 vertices); Master Mold 5901 (Wing_L /
  Wing_R 580 vertices each, eight finger bones 144 vertices). Master Mold looked right in the late test (shots 46-47);
  none of these has been reported misdrawn.
- **1-2 blend weights** (V20 note): 0101 Cyclops (visor), 0802 icemanflesh, 1101 ProfX (chair), 1601 Jubilee, 2301
  IllyanaComa, 3401 Juggernaut (helmet, head), 3705 AstralGhost, 4801 / 4805 / 4808 Acolytes, 5401 / 5404 / 5405 bots,
  5501 / 5504 / 5505 Sentinels, 5901 Master Mold, 8001 / 8002 spider mines, 8100 SpiderPod, 0002 default. (An
  earlier reading of a Jubilee power-sweep frame as a black bar was the park fence; powers_redo shows her clean.)

## 5. If B3 comes back

1. Note the session: fps, other windows, pad, how long it ran, which zones, whether movies played.
2. `python tools/current_zone.py` / harness `status` (actors, names, motions, igb counters).
3. Pad the two skins in that build and relaunch the same save: `python -m xml1build.skins pad Actors/18805.IGB
   <tmp>` (exact: weight 0.0 on the vertex's own bone; the padded outline drew correctly in sessions 1-7), then
   compare. If the padded pair stays clean while the originals spike, wire `pad_blend_weights` into
   characters.emit_namespace for the 32 numeric actors it changes (T2 of skins_selftest lists them).

## 6. Also found

- `igb_file` refused 27 XML1 and 23 XML2 actor IGBs whose last memory block ends 2 bytes short of a 4-byte boundary
  (the file is padded); fixed. `IgbFile.rebuilt(blocks)` rewrites the memory section with blocks of any size (a
  resized block gets its own directory entry; 977 actor IGBs round-trip; only padding bytes differ in 2).
- Pre-existing, not from this branch: V7 error on Conversations/mansion/man1a/1_2_37 (`disallowResponse()` with an
  argument; flagged by the validator at bdb81c5 and by main's, not by the older _heroes validation); frontend_selftest
  U2 (harness MAIN_MENU_ITEMS button8 vs button7) fails at bdb81c5.
