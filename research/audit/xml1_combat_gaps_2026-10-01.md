# XML1 combat and character data on XMen2.exe: forward compatibility audit (2026-10-01)

Half of a two-agent audit; this half covers stats (herostat / npcstat), talents, power styles and fightstyles,
combat events and their attributes, affecters / powerups, entities named by styles, effects, AI attributes on
stats and spawners, races / teams, XP and stat formulas. The other half (scripts, zones / entities / triggers,
conversations / menus / HUD, items, danger room, saves) is a separate report.

Question: what else in XML1's data does the XML2 PC engine not implement, or implement differently, so that
the port (build/_w4, content version 6) silently loses behaviour? Same class as SPEC 29 (weapons), 29.1
(package styles) and 29.2 (entity value codes), which this audit takes as already fixed.

Method. (1) Re-read SPEC 12, 22, 24, 29, 29.1, 29.2, SPEC_heroes, research/heroes/{DESIGN,weapon_events,
engine}.md, research/media/effect_format.md, combat_events.py, npc_values.py, research/characters/
{combat_compat,schema_stats}.txt. (2) Censused every tag.attr pair and every enum-like value in: XML1's
herostat / npcstat / powerstyles / fightstyles / shared_nodes / shared_talents / entities / aipatterns /
shared_combat_events / stat_rules, and in the build's final files of the same kinds (only files that differ
from the XML2 install), against XMen2.exe's string table (a NUL-terminated token test: a name absent from the
binary is never parsed; a present one may still be parsed-and-dropped) and against XML2 retail data (a name
XML2's own styles use is parsed). (3) For the names that matter, the parser / consumer was read in Ghidra
decompiles of XMen2.exe (research/characters/ghidra, run_decomp.sh) or research/scripts/xml2_text.asm, and
XML1's side in default.xbe's strings / xml1_text.asm. Scratch census scripts: the session scratchpad
(census.py, xstr.py, decomp_audit1-3.c); nothing of that is in the repo.

Act order used for "how early": NYC (Alison) -> mansion -> HAARP (Magma) -> sewers / GRSO -> Weapon X ->
Nuke plant -> Muir Island -> Asteroid M -> astral / arbiter.

---------------------------------------------------------------------------------------------------------------

## 1. Ranked table

| # | impact | finding | who / where (first met) | player-visible symptom | evidence (short) | fix sketch | effort |
|---|---|---|---|---|---|---|---|
| G1 | HIGH | XML1's inline NPC "special" talents (boss immunities) are dropped: 48 npcstat entries, 26 talent names, none in the build | every XML1 boss and elite from act 1 on: PyroAct1 (NYC park), BlobAct1a (nyc1_1_3), MystiqueAct1, SabretoothAct1, JuggernautFlashback (mansion), ToadAct1 (HAARP), AvalancheAct2, MarrowAct1 (sewers), MultipleMan (Muir), HavokBoss, MagnetoBoss, mastermoldone, shadowking(two), the bots, SpiderPod, Forge | bosses can be stunned, knocked back / popped up, grabbed and thrown, finished, mind-controlled (Frost / Jubilee confuse, team_switch), frozen in Iceman's ice shell, criticalled, hurt-flinched; Morlock bruisers B/C lose their 50 % physical resistance | section 2.1 | characters: emit each distinct inline body as a shared talent in XML2 `<powerup life="-1"><affecter>` form (XML2's own `boss_resistances` is the engine form), keep the npcstat references; heroes' shared keep rule like `x1_npc_energy`; pool stays <= 100 | 0.5-1 day |
| G2 | HIGH (shared with the scripts / zones audit) | XML1's hardcoded boss AI states are not in XMen2.exe: the converted aipatterns parse, but `setstate` names `blobnyc`, `blobastral`, `avalanche`, `avalanche_astral`, `mystique`, `myst1..3`, `mag2..5`, `magshield`, `mold1..3`, `moldblowcore`, `sk2..4`, `dop_col/cyc/jean/wol`, `pyroastral`, `setpyroastral` are unknown to its 60-name table | Blob (nyc1_1_3, mag_nyc4), Mystique (nyc1_1_2b, mag_nyc3, asteroid2_1), Avalanche (mount2, astral3_4), Magneto (asteroid2_1), Master Mold (mastermold2), Shadow King (final_astral), the dopples (colosseum), Pyro / Blob astral (astral3) | whatever XML1's engine did in those states (boss phases the scripts switch with `setPatternSequence`: Magneto stage2-5 / shield, Master Mold mold2/mold3/blowcore, Mystique myst1-3, Shadow King sk2-4) does not happen; the sequences themselves switch (the function exists). Juggernaut, Toad (HAARP), Marrow and the "boss master" patterns use only states XMen2.exe has | section 2.2 | nothing in data: needs the xbe behaviour per state traced, then either script re-implementation or xml2-fix hooks | large, unknown |
| G3 | MED | the build ships XML2's `shared_combat_events` verbatim; 15 of the 29 shared events XML1 styles inherit from have different numbers in XML2: `punch`/`kick` L1 (4-5) K1 (40) -> "2 3" / 40 with `damagescale="normal"`, `punch_heavy`/`kick_heavy` L2 (9-11) K2 -> "3 5" / 120, `punch_veryheavy` L3 (15-18) -> "6 9", `grab` dmg_grab -> dmg_physical, `throw` 0 + auto_knockback -> impactdamage "3 5" throwspeed 400, `pickup_throw` none -> "21 26", `beam`/`fry`/`suspend` L4 (25-31) -> "3 5" / "6 9" | 29 XML1-origin triggers inherit the shared punch damage (moveset_shadowdemon, ps_avalanche, ps_clwmorlock a/b/c, ps_firedemon, ps_lrgmorlock, ps_magneto_boss, ps_shadowking_two, shared_nodes, x1_ps_beast/blob/gambit/juggernaut/magneto/sabretooth/toad), 54 inherit the shared knockback, 183 inherit `damagescale` | basic punches of those enemies (and of Beast / Gambit / Toad kept attack moves) do XML2's 2-3 instead of XML1's 4-5, heavy 3-5 instead of 9-11; Juggernaut's grab-throw gets XML2's impact damage; XML1 attacks silently get XML2's `damagescale="normal"` (consumer not traced) | section 2.3 | x1schema: on every trigger / event of an XML1 style that resolves to one of the 15 events and lacks the attribute, write XML1's resolved value (SPEC 24 then turns codes into numbers); or add `x1_punch`... events to the shipped shared_combat_events and re-point | 0.5 day |
| G4 | MED | XMen2.exe's `Multipart` is cosmetic only: the parser 0x48cec0 reads `NonMenuOnly`, `hideSkin`/`showSkin`, `hideSkin2`/`showSkin2` (at most 5 parts); XML1's `health`, `bone`, `effectBone`, `effectOnDeath`, `loopEffect`, `linkToPower`, `healthMul`, `startHide` are not read | JuggernautScripted / Flashback / Act3 (mansion jugrnt01 on; helmet), Sentinel / B / Leader / leaderb / Flashback (HAARP flashback, Nuke plant, Muir, Asteroid M, arbiter; both arms) | Juggernaut's helmet can never be knocked off (no explosion, no `helmet_penalty` phase), his head skin is not hidden at start (`startHide`, SPEC 10.5); Sentinel arms are indestructible and never disable `powerSmash` / `meleeAttack` | section 2.4 | not expressible in data; a script-side emulation is possible (`monster_painscript` + `skinsegment` / `ce_remove` triggers at health thresholds) or an xml2-fix hook | medium |
| G5 | LOW-MED | XML1 cloak tint triggers (`type="ce_renderfx" tint="true" solid="true" alpha="true" rgba=...` / `remove="true"`) do nothing: XMen2.exe's ce_renderfx parser 0x4e94e0 reads only `add` / `remove` with a renderfx name (XML2: `cloaked`) | ps_grsoelite (GRSO elite, sewers / GRSO), ps_acolyte_mental(_b), ps_bh_mental, ps_mp_mental, x1_ps_mystique (12 triggers in 6 styles) | the cloak / mental-shock translucency never appears or disappears (what the `invisible` powerup alone draws is unverified) | section 2.5 | x1schema: `tint/solid/alpha/rgba` -> `add="cloaked"`, `remove="true"` -> `remove="cloaked"` | tiny |
| G6 | LOW-MED | the hero passives shared with XML2 keep XML2's definitions: `critical` (XML1 5 ranks 2-10 % -> XML2 15 ranks 5-33 %), `might` (3 ranks: +5/10/15 % damage, +3/6/8 destruction -> 2 ranks heaviness/structure), `leadership` (combo damage x1.25..2.5 / combo XP -> leadership_critical / leadership_xp), `flight` (energy per second 40..5 -> flight_pwr 10..3); NPC `might level="3|4"` (Sentinels, Blob, Magneto, Master Mold) exceeds XML2's 2 ranks | every XML1 hero (critical, might, leadership on most) from the first level-up | the skill screen shows XML2's talents and rank counts; XML1's leadership combo bonus and might damage/destruction bonus are not what the player buys | section 2.6 | convert XML1's four definitions like `toughness` (SHARED_REAL_DEFS): `critical` -> affecter `critical`, `leadership` -> affecters `combo_damage` / `combo_xp` (ids 76 / 77 exist), `might` -> three ranks of `might_heaviness` / `might_structure`, `flight` -> XML2's talentvalue form with XML1's numbers | small |
| G7 | LOW | talent `cost` (119 `<level cost="2">` rungs in the hero talent files: xtremes, Legend ranks) is not read by the talent parser (the only "cost" xrefs 0x47b221 / 0x480d34 / 0x4811b6 are item code) | every hero's xtreme and Legend rung | those rungs cost 1 skill point instead of XML1's 2 | section 2.7 | none in data (the engine has one price); note it | - |
| G8 | LOW / unknown | stats `leader="true"` (21 XML1 leader NPCs) is dropped: XML1 parsed it (xbe 0xb03f5 -> CStats+0x3a1 bit 3, read at 0x323d7, 0x344c2, 0x44509, 0x7100f); XMen2.exe has only the spawner-level `leader` + `leaderpowerup` (0x422ee6 in 0x422b40) | AcolyteLeader(_B), BrotherHoodLeader, GRSO officers / commander / captains, HAARPLeader, MorlockLeader, MarrowsLieutenant, SentinelLeader(b), Shades leaders, WeapXGuardLeader | unknown (what the bit did in XML1 was not traced: candidates are a HUD/leader marker or an AI role) | section 2.8 | trace the four xbe readers first | small to find out |
| G9 | LOW | trigger attributes XMen2.exe has no string for: `maxtargets` + `doattack` + `dashbolt` (Wolverine / Rogue frenzy dash: target cap, Rogue's no-damage relocate dash), `noflying` (Rogue), `cleardata` (Nightcrawler), `removecurrent` (Shadow King), `zverticalrange` (Master Mold), `offsetend` / `offsetstart` (trails; XML2 retail carries them too), `rgba` / `solid` (G5), `user1` on `powerup` triggers is read only by the chill / freeze class (CPUChill setter 0x546620; XML2's own freeze uses `user1="2"`, XML1 varied it 1..8 per rank - dropped by heroes) | heroes mostly | Rogue's xtreme relocate dash may deal the dash damage; Wolverine's frenzy dash is uncapped; otherwise cosmetic | section 2.9 | per attribute, where a counterpart exists (none found) | - |
| G10 | LOW | entity / style typos XML1 carried that neither exe knows (behaviour as in XML1): `damagetype="dmg_electric"` (danger room robots, shockerbot, xmansion robot, Master Mold), `dmg_lightning` (shadow demon leaders, shade_ents), `explodradius` (mastermold / missilelauncher / sentin_grenade ents), `aitype="simon"`, damageMod `ame` | - | none (inherited) | 2.10 | none | - |
| G11 | LOW (zones overlap) | spawner AI attributes the registry 0x463850 does not know: `monster_grenade` (6 NukeGuard spawners: flashbang), `monster_smartqnt` (1); known and read: `monster_aggression` (714), `monster_aiforceranged`, `monster_willflee` / `fleedistance`, `monster_aipattern`, `monster_undying` | nuke1_1 | NukeGuards throw the style's default grenade entity, not the flashbang | 2.11 | zones: if the grenade entity matters, a style variant like SPEC 29 | small |

---------------------------------------------------------------------------------------------------------------

## 2. Details

### 2.1 G1: the inline NPC talents are the boss immunities, and they are gone

XML1 defines most NPC-only talents inline on the npcstat entry (`<Talent name="blob_special" level="1"><level>
<activepowerup .../>...</level></Talent>`), not in shared_talents. 48 entries carry 26 such names
(xml1_loose/data/npcstat.eng). Their bodies are immunities and resistances, the XML1 affecters being
`def_stun` / `def_knockback` / `def_pain` / `def_critical` / `def_damage` with `affect_type="scale" level="0"`
(immune), `def_grab` / `def_finisher` / `def_reflect_pain` (flags), `def_mind_control` scale 0.1 / 0.01 and
`no_iceshell` scale 0. 20 distinct bodies:

| body (XML1 activepowerups) | talent names | entries |
|---|---|---|
| def_finisher, def_grab, def_knockback 0, def_mind_control 0.1, def_pain 0, def_stun 0 | avalanche_special, marrow_special, mystique_special, pyro_special | AvalancheScripted / lite / Act2 / Act4, MarrowAct1 / Act3, MystiqueAct1 / Act2sim / Act3, PyroAct1, Vulcan |
| + no_iceshell 0 | toad_special | ToadAct1 |
| + no_iceshell 0, def_mind_control 0.01 | magnetoboss_special | MagnetoBoss |
| def_knockback 0, def_mind_control 0.1, def_stun 0 | blob_special | BlobScripted, BlobAct1a / Act2 / Act4 |
| def_critical 0, def_knockback 0, def_mind_control 0.1, def_stun 0 | juggernaut_special | JuggernautScripted / Flashback / Act3 |
| def_finisher, def_grab, def_knockback 0, def_mind_control 0.1, def_pain 0 | sabretooth_special | SabretoothAct1 / Act2 / Act3 (+ sabre_special: mind control only) |
| def_finisher, def_mind_control 0.01, def_pain 0, def_stun 0 | mastermold_special | mastermoldone |
| def_damage dmg_energy 0, def_mind_control 0.1, def_stun 0 | havok_special | HavokBoss |
| def_finisher, def_grab, def_pain 0, def_stun 0 | shadow_special, shadow_special2 | shadowking, shadowkingtwo |
| def_finisher, def_grab, def_knockback 0, def_pain 0, def_stun 0, no_iceshell 0 | as_special, pod_special, shocker_special, spidermine_special, stealth_special, suicide_special | suicideastral_s, SpiderPod, ShockerBot, suicidespider, StealthBot, SuicideBot |
| def_damage dmg_physical scale 0.5 | physical_res | MorlockBruiserB, MorlockBruiserC |
| def_mind_control 0.1 + `none` with `func_hurt="MultipleMan_Hurt"` | multipleman_special | MultipleManDividing (the hurt callback = the dividing; an XML1 code callback, no XML2 form) |
| def_grab | forge_special | Forge |
| def_finisher | sentspider_special | SentinelSpider(_b) |
| def_stun 0 (+ def_reflect_pain at level 2) | dr_stun, sentinel_special | kept: XML2's shared_talents define both (XML2's sentinel_special adds no_iceshell) |

What the build does (build/_w4/_build/characters_detail.json `dropped_children`: "talent blob_special <level>
tree: inline XML1 definition; kept as a reference", 111 rows; characters.py:943): the `<level>` trees are
dropped and only the `<talent name=... level="1"/>` reference survives characters; heroes then prunes
shared_talents to its keep list (SPEC_heroes 6, DESIGN 4.7: "the 26 empty `*_special`-style NPC definitions
and their `<talent>` children ... are dropped" - the definitions are empty in XML2's shared_talents, which is
where DESIGN looked; the real bodies were inline in XML1's npcstat) and removes the references (94). Result
in build/_w4: `Data/npcstat.XMLB` has no `*_special` / `physical_res` talent on any XML1 entry (BlobAct1a:
blob_butt, blob_belly, might, physical_resistant, x1_npc_energy; PyroAct1: might, energy_resistant, pyro_*,
fightstyle_villain, x1_npc_energy; JuggernautAct3, ToadAct1, MystiqueAct1, AvalancheAct2, MagnetoBoss,
MarrowAct1, mastermoldone, HavokBoss, SabretoothAct1, shadowking likewise) and `Data/shared_talents.XMLB`
(47 names) has none of the 26. The 11 `boss_resistances` references in the build's npcstat are all XML2's
own entries (Abyss, Bastion, Stryfe ...).

Engine: every affecter name above is in XMen2.exe's affecter table 0x6ddb18 (combat_events.AFFECTERS:
def_damage 39, def_knockback 40, def_stun 41, def_pain 42, def_critical 43, def_grab 45, def_reflect_pain 46,
def_finisher 47, def_mind_control 50, no_iceshell 81) and XML2 ships the identical idea as a shared talent:
`boss_resistances` = def_mind_control 0.1, def_pain 0, def_grab, def_pickup, def_finisher, def_stun 0,
no_iceshell 0, def_knockback 0, slow_immune 1 (`<talent name="boss_resistances"><level><powerup life="-1">
<affecter affect_type="scale" attribute="def_stun" level="0"/>...`), referenced as `<talent level="1"
name="boss_resistances"/>` by XML2's bosses. So the XML2 form of every XML1 body exists.

Symptom: in the port the XML1 bosses behave like mooks under crowd control: Blob and Juggernaut are knocked
down by heavy attacks and popped up, Pyro / Toad / Mystique / Sabretooth / Marrow / Avalanche can be grabbed
and thrown, finishers trigger on them, Frost's / Jubilee's confusion turns them, Iceman's freeze encases
Magneto / Toad / Master Mold and the bots, Wolverine's criticals land on Juggernaut, and Morlock bruisers
B / C take full physical damage. (Not yet reproduced in game - section 4.)

Fix sketch (characters, in the style of SPEC 24.3's `x1_npc_energy`): when converting an npcstat entry,
collect every inline `<Talent>` with `<level>` children; emit one shared talent per distinct body
(`x1_imm_<n>`, or keep the XML1 names - either is fine, names <= 31 chars) as `<talent name=X><level>
<powerup life="-1"><affecter attribute=A [affect_type="scale"] [level=L] [scope_damage=D]/>...</powerup>
</level></talent>` (the `none` + `func_hurt` row and `user1` are reported losses); keep the entry's
`<talent name=X level="1"/>`; add a heroes `shared_keep` rule ("XML1 NPC immunity talent while a stats entry
names it"). Budget: 47 + 14 bodies (the 20 above minus the kept dr_stun / sentinel_special, the profx rows
and the empty ones) = 61 shared, worst party 29 -> 90 of 100, +8 danger room = 98: tight but under; merging
the four bodies that are subsets of `boss_resistances` into a reference to it would save 4. Validator: a
V19-style check that every XML1 entry whose source carried an inline immunity names a shared talent with the
same affecters. Test: Blob (nyc1_1_3) does not fall to Wolverine's smash; Iceman's freeze does not shell
Toad.

### 2.2 G2: boss AI states

XML1's 17 aipatterns (data/aipatterns/*.xml) are in the build (Data/aipatterns, 35 = XML2's 18 + XML1's 17),
and XMen2.exe's pattern parser (FUN_00520a30, decomp_audit1.c) is XML1's grammar: node types `moveto`
(`basewaypoint`), `attack` (`button1` / `button2`, `attack="player|anyhero"`, `maxrange`, `refiretime`),
`condition` (`repeat` / `time` / `heightlessthan`, `test`, `jumpto`), `interrupt` (`failconfine` /
`beingattacked`, `jumpto`), `setstate` (name / value), `sound` (special-cases `jugmansiontaunt`, as XML1),
`message`, `fire="once"`. XMen2.exe's `setPatternSequence` script function exists (string 0x68c4cc).
Juggernaut (attackobjects / attackplayer / ignoreattacks), Toad HAARP (podiums / attacking / evade),
Marrow (backboss / chargeboss) and bossmaster (bossfull / bosspartial) use only states XMen2.exe knows.

Not known to XMen2.exe's `setstate` table (60 names: attackphysents, ignoreattacks, backboss, chargeboss,
bastion, deadpool, stryfe, archangel*, endbattle, holocaust, suck_life, aoeattack, findnearestwaypoint,
bossfull, bosspartial, freeze, apocalypse*, generator, middle, huge, cutscene, addtime, shrink, livmon*,
sinister*, abyss*, omegared, sauron, mikhail*, garokk*, lds*, pause) but present in default.xbe:
`blobnyc`, `blobastral`, `avalanche`, `avalanche_astral`, `mystique`, `myst1`, `myst2`, `myst3`, `mag2`,
`mag3`, `mag4`, `mag5`, `magshield`, `mold1`, `mold2`, `mold3`, `moldblowcore`, `sk2`, `sk3`, `sk4`,
`dop_col`, `dop_cyc`, `dop_jean`, `dop_wol`, `pyroastral`, `setpyroastral` (`magneto` and `sk` are XMen2.exe
strings but not setstate names). An unknown name falls through the compare chain and sets nothing.

The XML1 scripts switch these phases: asteroid_m stage scripts `setPatternSequence("magneto", "mag2".."mag5")`,
mastermold `("mastermold", "mold2" | "mold3" | "moldblowcore")`, nyc/alison and mansion `("mystique",
"myst1".."myst3")`, astral `("shadowking", "sk3" | "sk4")`, `("shadowking2", "sk2")`, `("evilcolossus" ...,
"start")`, mount `("avalanche", "endbattle")` (that one exists). What each state made the xbe's AI do
(Magneto's shield phases, Master Mold's core, Mystique's escape / morph phases, the dopples copying the
heroes) is engine code, not data; research/campaign/late_game_test.md lists the Magneto and Master Mold
fights as "still needs a human playthrough" (their boss deaths were scripted). Expect those fights to run on
the generic AI only. Fix: trace the xbe handlers per state (xml1_text.asm, the parser's name table is at
the `blobnyc`.. strings), then re-implement as scripts where possible (phase switches already come from
scripts) or as xml2-fix hooks. The scripts agent should own the per-fight assessment.

### 2.3 G3: XML2's shared_combat_events replaces XML1's

The build's `Data/shared_combat_events.XMLB` is byte-identical to XML2's (SPEC 4.4 "other global tables:
XML2's kept; deferred"). XML1's styles inherit from these events by name (SPEC 22.1), and 15 of the shared
names differ between the two tables (xml1_loose/data/shared_combat_events.xml vs XML2; XML1 codes resolved
with XML1's values.xml L1 = 4-5, L2 = 9-11, L3 = 15-18, L4 = 25-31, K1 = 40, K2 = 120):

| event | XML1 | XML2 (shipped) |
|---|---|---|
| punch / kick | damage L1 (4-5), knockback K1 (40), no damagescale | "2 3", 40, `damagescale="normal"` |
| punch_heavy / kick_heavy | L2 (9-11), K2 (120) | "3 5", 120 |
| punch_veryheavy / kick_veryheavy | L3 (15-18), K2 | "6 9", 120 |
| move_damage | L2 | "3 5", normal |
| grab | damagetype dmg_grab | dmg_physical |
| throw | damage 0 + dmgmod_auto_knockback | impactdamage "3 5", throwspeed 400, damagescale %grab_scale_dmg, no damageMod |
| pickup_throw | (none) | "21 26" |
| beam / fry / suspend | L4 (25-31) | "3 5" / "6 9" / "6 9", none |
| teleport_punch | L1 | "3 5" |
| weapon_fire | L0 | "2 3" (dead on this exe anyway, SPEC 29) |
| trail | color / width | effect base/misc/trail_default |

Reliance in the build's XML1-origin styles (trigger chains followed through the style's own events to the
shared root; an attribute set anywhere on the chain counts as overridden): punch damage 29 triggers
(moveset_shadowdemon attacklight1/2, ps_avalanche attacklight1/2 attackheavy1, ps_clwmorlock a/b/c,
ps_firedemon, ps_lrgmorlock, ps_magneto_boss, ps_shadowking_two, shared_nodes, x1_ps_beast, x1_ps_blob,
x1_ps_gambit attacklight3 / attackstun1, x1_ps_juggernaut, x1_ps_magneto, x1_ps_sabretooth, x1_ps_toad),
punch knockback 54, punch_heavy damage 9 / knockback 6, kick damage 8 (x1_ps_toad getup attacks,
shared_nodes getuponfrontattack), kick_heavy 3, punch_veryheavy 2 (x1_ps_beast attackheavy1/2), throw 4
(x1_ps_juggernaut grabthrowleft/right/grabattack, shared_nodes grabthrowbase), pickup_throw 3 (Gambit /
Jubilee charged_throw, pickupobjectthrow), grab damagetype 3; `damagescale` inherited by 183 punch and 18 kick
triggers. `beam` / `fry` / `suspend`: every XML1 user sets its own damage (0 reliant).

XML1 had no `damagescale` attribute at all (not a default.xbe string; 0 uses), so on this exe XML1's basic
attacks run with XML2's "normal" scaling while XML1's own attack events run with "none"; what the hit code
does with the enum (attack data +0xa, parsed by 0x44ec00) was not traced.

Fix: in x1schema (every XML1 style import, like the SPEC 22 rebase) resolve each trigger / event chain; when
the root is one of the 15 events and the chain does not set the differing attribute, write XML1's value on
the trigger (`damage="L1"` -> SPEC 24 resolves it; `knockback`, `damagetype`, `impactdamage` left absent
where XML1 had none). Alternatively append XML1-named copies (`x1_punch` ...) to the shipped
shared_combat_events and re-point `name` / `inherit`; the loader reads every `<event>` (0x50114d) and the
19-trigger / 31-char limits are unaffected. V18 can then assert no XML1-origin trigger relies on a changed
default.

### 2.4 G4: multipart

XML1 npcstat (13 `<Multipart>` rows): Juggernaut x3 `bone="Bip01 Head" health="400|9999" effectBone
effectOnDeath="explode/JuggernautHelmet" startHide="3401_head" hideSkin="3401_helmet" showSkin="3401_head"`;
Sentinel / B / Leader / leaderb / Flashback x2 each `bone="Bip01 R|L UpperArm" health="275|1000" healthMul="2"
effectOnDeath="explode/smexp1" loopEffect="explode/SentinelArmLoop" linkToPower="powerSmash powerAction" |
"meleeAttack powerAction" hideSkin="5501_r_forearm" hideSkin2="5501_r_upperarm"`. The build keeps the rows
verbatim (build npcstat census: `multipart.effectbone/effectondeath/healthmul/hideskin2/linktopower/loopeffect/
starthide` present, none an XMen2.exe string).

XMen2.exe (FUN_0048cec0, decomp_audit1.c; the stats loader FUN_004495e0 finds the `Multipart` children):
per part it reads `NonMenuOnly`, the string at 0x689858, `hideSkin` / `showSkin` and, through
`sprintf("hideSkin%d")`, `hideSkin2` / `showSkin2`, interns the names into a 0x20-byte record and refuses a
sixth part (`4 < +0xac`). No health, bone, effect or power link is parsed and the record has no room for them.
XML2's own rows are `health="0" hideskin="gun_left"` (menu-only bolton hiding), which is all the engine does.

Symptom: Juggernaut's helmet never breaks (XML1: 400 damage to the head blows the helmet off with
explode/JuggernautHelmet and the fight's `helmet_penalty` phase in x1_ps_juggernaut, SPEC 22.7); `startHide`
is ignored (SPEC 10.5 already lists it - whether the head mesh shows through the helmet needs the screenshot
in section 4); Sentinel arms cannot be destroyed and losing one never disables the smash / melee attacks.

Fix: no data form. Emulation: the engine has `monster_painscript` (XML1 already uses `jugpain`) and the
combat events `ce_skinsegment` (shared `skinsegment`) and `ce_effect`; a pain script can read the actor's
health (`getHealth`-style function availability is the scripts agent's call) and, below a threshold, act a
hidden FightMove that hides the helmet segment, plays the effect and switches the style's phase. An xml2-fix
hook that re-implements part health is the faithful route.

### 2.5 G5: ce_renderfx attributes

XML1: `<trigger name="tintout" type="ce_renderfx" tint="true" solid="true" alpha="true" rgba="0 0 0 0.5"/>`
and `<trigger name="tintin" type="ce_renderfx" remove="true" tint="true" solid="true"/>` (ps_grsoelite
power_boost cloak; the mental styles' `systemshock`; x1_ps_mystique). XMen2.exe's CCERenderFx parser
(vtable 0x692770 slot 4 = FUN_004e94e0) reads `add` and `remove`, each a name from the renderfx table
0x6d7bd8 OR-ed into a bit mask (+0x10 / +0x12), then the base `time` / `tag`; `tint`, `solid`, `alpha`,
`rgba` fall through, and `remove="true"` names no renderfx. XML2 retail: `<trigger name="tintout"
type="ce_renderfx" add="cloaked" time="0.35"/>` / `remove="cloaked"` (ps_deadpool and others). Fix in
x1schema: `tint|solid|alpha|rgba` present -> `add="cloaked"` (drop the four); `remove="true"` ->
`remove="cloaked"`. 12 triggers in 6 styles.

### 2.6 G6: shared hero passives

heroes keeps XML2's definitions for the names both games define (SPEC_heroes 6: `critical`, `might`,
`flight`, `leadership` and the resistances), converting XML1's only for `toughness`, `mutantmastery`,
`acrobatics`. Diff of the same-named definitions (xml1_loose/data/shared_talents.eng vs XML2):
`critical` XML1 5 levels (+2/4/6/8/10 %, unlocked at character levels 1/7/12/17/22, no activepowerup: the
xbe hardcoded it) vs XML2 15 ranks (`critical_add` 0.05..0.33 as an affecter); `might` XML1 3 levels
(+5/10/15 % melee damage, heavy / massive / gigantic objects, +3/6/8 destruction) vs XML2 2 ranks
(might_heaviness 1..2, might_structure 1); `leadership` XML1 5 levels of `combo_damage` x1.25..2.5 and
`combo_xp` x1.05..1.25 (affecters XMen2.exe has: ids 76 / 77) vs XML2 15 ranks of leadership_critical /
leadership_xp (talentvalues the exe reads by name, 0x4c135d / 0x4c1370); `flight` XML1 5 levels (40/30/20/
10/5 energy per second, flight pickup from level 3) vs XML2 5 ranks `flight_pwr` 10..3. The resistances
(`def_damage` scale 0.2 vs `resist_*` 0.8) are equivalent. XML1 NPCs reference `might` at levels 3 (Blob,
Sentinels, Juggernaut, Avalanche, Master Mold) and 4 (MagnetoBoss) - beyond XML2's 2 ranks (the engine's
clamping was not traced). Fix: convert XML1's definitions as SHARED_REAL_DEFS does for toughness
(critical -> `critical` affecter per rank; leadership -> `combo_damage` / `combo_xp` scale affecters; might
-> 3 ranks with might_heaviness 1/2/3 and might_structure; flight -> XML2's talentvalue form with XML1's
numbers if `flight_pwr` is the energy drain), and give NPC `might` a third rank. The description text
changes with it (XML1's, resolved like the hero files).

### 2.7 G7: talent `cost`

XML1 marks the xtreme and the Legend rungs `cost="2"` (119 `<level cost>` in the build's 14 hero talent
files, kept by heroes "harmless if ignored"). The string "cost" (0x687f9c) is referenced only at 0x47b221,
0x480d34, 0x4811b6 - none inside the talent file parser (0x4bd000-0x4c1000); XML2 retail talents never carry
it. Every rank therefore costs one skill point. Not fixable in data; the skill screen simply charges 1.
`require degree="see"` (28 rungs) is read (0x4ac68a in the require evaluator).

### 2.8 G8: stats `leader`

XML1's stats parser accepts `leader` (xbe 0xb03f5: `_stricmp("true")` -> CStats+0x3a1 bit 3) and four
places test that bit (0x323d7 and 0x344c2 both call 0x72cf0 when it is set, 0x44509 in a condition chain,
0x7100f sets a local flag); what they do was not traced. XMen2.exe's stats parser has no `leader` case
(engine.md 1.4; characters_detail `dropped_attrs`: 21 entries), its `leader` string belongs to the spawner
instance (FUN_00422b40: `leader` -> apply `leaderpowerup` from the spawner or the stats, XML2's danger-room
leader mechanic). If the XML1 bit drove a HUD marker or the AI "squad leader" role, 21 leader variants lost it.
Cheap next step: decompile the four xbe readers.

### 2.9 G9: minor trigger attributes

Absent from XMen2.exe (lenient token test) and present in XML1 styles: `maxtargets` (Wolverine frenzy
dash prep 7, Rogue 10), `doattack="false"` + `dashhome` (Rogue xtreme relocate / return dashes: `dashhome`
exists, `doattack` does not - the relocate dash may hit), `dashbolt` (Wolverine power2 trail bolt),
`noflying` (3 Rogue moves), `cleardata` (Nightcrawler teleport data), `removecurrent` (Shadow King),
`zverticalrange` (Master Mold), `offsetend` / `offsetstart` (trail triggers; XML2 retail has them too, so
dead in XML2 as well), `life_max` / `level_max` (converted by heroes), `enemynumber` is parsed
(`EnemyNumber` 0x4dd673), `closerange` (taunt, 0x4dee47) parsed, `ignoreanimmap` (0x4e6aa5) parsed,
`volume` on sound triggers parsed by ce_sound (0x4e9007). `user1`: of the 18 powerup classes only the
chill / freeze class setter (FUN_00546620, vtable `.?AVCPUChill@@` 0x6979b4) reads `user1` (and `sound1`);
XML2's own freeze triggers carry `user1="2"`; XML1's Iceman varied `user1` 1..8 per rank on the freeze /
chill triggers and heroes dropped it (SPEC_heroes 8 "user1/user2 of powerups dropped") - the build's freeze
has `user1="2"` on tags 20 / 100, none on the chill tags. Meaning of the number not traced.

### 2.10 G10: inherited typos

`dmg_electric` (ps_dangerroom_robot(_ldr), ps_shockerbot, ps_xmansion_robot, ps_mastermold_one),
`dmg_lightning` (ps_shadowdemon_ldr(_b), shade_ents), `explodradius` (mastermold_ents, missilelauncher_ents,
sentin_grenade_ents; XML2 retail has the same typo), `aitype="simon"` (ps_avalanche), damageMod `ame`
(fightstyle_psionic, XML2's version used anyway), `throwally` (colossusdopple): none is a string of either
exe; both games fall back the same way.

### 2.11 G11: spawner AI attributes (overlap with the zones audit)

Registered by XMen2.exe (0x463850, 61 `monster_<name>` pairs) and used by XML1 spawners: aggression (714),
spawnexactlocation, skin, actdelay, actonuse, deathtargets, guarddistance, actinactivedelay, nopickup,
hinttype, willflee (31), fleedistance (23), noaidisable, aiforceranged (10), startenabled, removeondeath,
acttargets, actcountdisable, description, actondeath, deathspawn. `monster_aipattern` is read by the spawner
(0x48a467). Not registered: `monster_grenade` (6 NukeGuard spawners, `flashbang`), `monster_smartqnt` (1).
The AI init (FUN_005034a0) copies CStats willflee (bit 0 of +0x2ad) and fleedistance (+0x4dc) and lets the
spawner override them, and clamps `aggression` to 1..8 for the enemy teams.

---------------------------------------------------------------------------------------------------------------

## 3. Checked and fine (do not re-check)

- **aipattern grammar**: node types, conditions, interrupts, attack buttons, `fire="once"`, `basewaypoint`,
  `refiretime`, `jugmansiontaunt` - all in FUN_00520a30; only the state names of 2.2 are missing.
- **stats attributes XMen2.exe parses and uses**: `xpaward` (kill XP override at 0x43712d, levels.md),
  `counter` (+0x2bc, `require cat="counter"` evaluator FUN_004ac470), `attackrange` (+0x4ce, read at
  0x511edf), `willflee` / `fleedistance` (2.11), `canSeeStealthed` (+0x2ad bit 2), `teleportpathfail` (bit 4),
  `meleetimeroffset` / `meleetimerrandomadd` (+0x4e0 / +0x4e4, stored; readers not isolated),
  `deathnode` (CStats vt+200), `xpexempt`, `dangerRating`, `ailevel`, `aipower`, `pickupthrowchance`,
  `heaviness`, `material`, `aiclasstype` (`sentinel`, `rangedenemy` are table names), `resurrect`
  (`minion` / `master`), `team` (`enemy` / `none` / `hero`), races (Mutant, Human, Robot, Astral, Morlock,
  Shadow, Sentinel, XMen: all strings), `scale_factor`, `large`, `size`, `scriptlevel`.
- **stats attributes known-dropped and already handled**: `weapon` (SPEC 29), `rating*` (XML1 menu bars ->
  autospend D13), `skin_magmacivilian` (-> skin_civilian), `throwally` (typo).
- **bolt names**: every `Bip01 ...` XML1 uses is in the 13-name table (the census flagged "Bip01 L Hand" /
  "Pelvis" / "R Forearm" only because the exe stores them with a leading byte; `Bip01 R ForeArm` matches
  case-insensitively). `ebolton_autoanim2` (Abyss, an XML2 entry) is XML2's own.
- **enum values**: damagetype flags (table 0x6d61c8), attacktype (0x6d6dc8), damagescale (0x6d6dec),
  affect_type (scale / max / min; XML1's `sum` on ps_havok is unknown to both), scope_attack / scope_damage /
  scope_node / scope_race (affecter parser 0x534d90), `how_used` (primary / activation / deactivation /
  custom), powerup `class` names (SPEC 22.7), `apply_ally` / `apply_enemy` (all / near / medium / none),
  `chain action` (`powers`, `spinleft`, `popup`, `power_smash` exist), `require cat` (XML2 parses
  `skill` / `level` / `xtreme` / `counter` / `talent`), `aitype` (20-name table; only `simon` unknown),
  `animenum` (validator: the 12 flying-carry / Juggernaut-grab enums are XML1-only and known),
  FightMove handlers (SPEC 22 UNREGISTERED_HANDLER_NOTES; nothing new), damageMod names (SPEC 22).
- **combat event / trigger attributes XML1 uses that XMen2.exe parses**: `enemynumber`, `closerange`,
  `ignoreanimmap`, `volume`, `hitenemyeffect`, `usedamageasexplodeonly`, `onlynoenemypitch`, `setbeam` /
  `timeinterval` / `intervalrandom` (SPEC 29), `angoffset`, `spawneffect`, `character` / `startnode` /
  `limit` / `team` (spawn events), `matchorigin`, `facespawner`, `copy_counter`, `bolton` / `fx_bolt` /
  `effect_cust1/2` (SPEC 22.7), `skin_swap` (string present; behaviour unverified, SPEC_heroes), `motor` /
  `timebased` / `vibrate` (parsed names; Magma), `powerup_tag`, `weapon` on events (dead, SPEC 29).
- **value codes**: SPEC 24 / 29.2 (styles and entity files resolved; none left in build/_w4).
- **entity attributes**: `deatheffect`, `deathsound`, `spawnsound(loop)`, `acteffect`, `actsound`,
  `paineffect`, `xdeatheffect`, `maxtargetingangle`, `launchedfromscript`, `explodedamagemods`, `trailfx`,
  `avgfxspacing`, `homing`, `deathspawncount` - XML2 retail entities use the same names (ents_merc, ents_gambit:
  `deatheffect="char/merc/p2_impact"`), so they are parsed although the composite ones are not single
  strings in the binary (the entity class registers `<event><suffix>` names; `death`, `spawn`, `act`,
  `pain`, `xdeath` are the event tokens at 0x4633ad..). `explodeknockback` (grenade_ents) is absent.
- **effects**: research/media/effect_format.md (parser verified; colours converted by x1schema).
- **shared tables**: `stat_rules` (per-hero `template="bruiser|support"` rows; XML1 has Beast / Frost /
  Jubilee / Magma / ProfXAstral / Psylocke, XML2 its own heroes) is read by neither exe (no `stat_rules`
  string in XMen2.exe or default.xbe); `autospend.xmlb` is XML2's mechanism and the 15 heroes have a class
  (D13). `team_bonus`, `shared_powerups`, `colors`, `styles` are XML2-only mechanisms XML1 never had.
  `values.xmlb` carries XML1's 16 extra codes (SPEC 11.2) but only DMG2-4 / K2 / K3 are read (SPEC 24).
- **XP**: xml2-fix `XPCurve=xml1` (SPEC 23) covers the level table, kill XP, the split and `xpaward`.
- **NPC energy**: SPEC 24.3.
- **fightstyles**: the 16 same-name fightstyles are XML2's by decision (SPEC 4.4); the XML1-only ones
  (moveset_sent_adv, moveset_shadowdemon, moveset_shadowking, moveset_acrobat's XML1 wall-cling, ...) carry
  nothing new beyond the handlers SPEC 22 lists (`chargespeed` / `chargetime` on moveset_sent_adv:
  `chargetime` parsed, `chargespeed` not).
- **talent file attributes**: `descname`, `description`, `icon`, `icon_texture`, `hidden`, `power`, `type`,
  `count`, `degree` parsed; `cost` not (2.7).
- **BoltOn**: slots (`characters.BOLTON_SLOTS`), `onlyprecache` parsed; the `<require>` blades are SPEC_heroes D15.

---------------------------------------------------------------------------------------------------------------

## 4. In-game checks (build/_w4 content, mirrored into a scratch folder with its own pipe `w4audit`; the
caller's `w4` game was busy)

- Setup: the designated `w4` game (build/_w4, pid 28868 then 23144) was being driven by another session
  (pipe busy, error 231; the process was restarted while this audit ran), so the build was mirrored by
  directory junctions into the session scratchpad (`w4m/`, its own `xml2-fix.ini`: pipe `w4audit`, save
  folder "X-Men Legends (w4 audit)") and run windowed from there; build/_w4 itself was not modified
  (an earlier `harness.py install build/_w4` attempt failed on the in-use dinput.dll before writing anything).
  Driver: scratchpad `audit_driver.py` (new game, `seatParty("wolverine","iceman","colossus","cyclops")`,
  `loadMapKeepTeam`, `copyOriginAndAngles("_HERO1_", <monster>)`, smash = NUMPAD6 x6 with a screenshot
  after each). The game was closed afterwards (`current_zone.kill_build(<mirror>)`).
- **G1 / G4, Juggernaut (mansion/jugrnt/jugrnt01, spawner `jugs` acted)**: JuggernautFlashback spawns with
  the "Juggernaut (5) / Mental Resistant" bar (so the XML2-form resistances it still has are applied and
  shown). Six Wolverine smashes at point-blank all land (hit flashes, Juggernaut bends into the pain /
  stagger reaction in frames 5-6; `def_pain` was never in his XML1 body, so flinching is correct). He was
  not launched or floored within the six smashes, so **knockback / stun immunity loss is NOT confirmed by
  this run** - the smash may simply not knock back a `large` actor, and the sample is small. Sheets:
  scratchpad `shots/sheet_jugsmash.png`, `zoom_jug_sheet.png`. The helmet: he draws with the helmet on; whether
  the head mesh shows through (`startHide`) is not resolvable at this zoom. Both remain open.
- **G1, Blob (nyc/alison/nyc1_1_3)**: Blob spawns ("Blob (4) / Physical Resistant"), the party reaches him,
  but the six smashes were swallowed by the zone's tutorial / co-op popups (`sheet_blob.png`), and the Iceman
  freeze attempt never switched the active hero (RIGHT did not change the portrait), so **no result**. A
  retry needs the popups dismissed per shot and the hero switch verified; both are in the driver's next
  revision, not run for lack of time.
- Not attempted in game: G2 (boss phases - needs full fights), G3 (2-3 vs 4-5 punches: 1-2 px on the bar),
  G5, G6.

---------------------------------------------------------------------------------------------------------------

## 5. Not established

- What each lost AI state (2.2) made XML1's engine do, per boss.
- What XML1's stats `leader` bit controlled (2.8).
- The consumer of `damagescale` (attack data +0xa) and therefore the size of the "normal" vs "none"
  difference in 2.3.
- The meaning of `user1` for the chill / freeze class (2.9) and how XMen2.exe treats a `<talent level>` above
  the definition's rank count (2.6 `might` 3 / 4).
- Whether the GRSO elite / mental acolytes are drawn at all while their `invisible` class powerup runs without
  the `cloaked` renderfx (2.5).
