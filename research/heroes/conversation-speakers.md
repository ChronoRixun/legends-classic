# Conversation speakers on the XML2 engine: what happens when the speaker is absent

Written 2026-09-28 by an Opus research subagent. This was read-only static work: nothing was launched and nothing was
built. All XMen2.exe addresses come from `research/scripts/xml2_text.asm`, `tools/disasm.py` (argument = RVA) and
headless Ghidra decompiles written next to this file: `decomp_ft_conv1.c` … `decomp_ft_conv6.c`, each with a
`.log`. Data comes from `build/_heroes` (decoded with `tools/xmlb.py`) and from XML2 retail `<XML2 folder>`.
The survey scripts are in the session scratchpad and are not part of the project. Anything that was not read from code
or data is marked **UNVERIFIED**.

Conventions:
- **CS** = the conversation system singleton `[0x717aac]` (getter `0x4583f0`, vtable `0x685e04`, size `0x239dc`).
- **node** = a parsed `<line>` or `<response>`. Lines use vtable `0x685d74` and are drawn by `0x45beb0`. Responses use
  vtable `0x685d6c` and are drawn by `0x45b7b0`.
- **activator** = the hero entity that starts the conversation. Its id is stored at `CS+0x21b34`.

---

## 0. Answers

| question | answer (from code) | where |
|---|---|---|
| What does `%NAME%` resolve to? | A **stats-table name** (herostat/npcstat). At parse time the token at the start of `text`/`textb` becomes the node's *speaker key* (node+0x64). If the stats entry exists, the token (with or without `: `) is replaced by the entry's display name plus `\n`. At display time the key drives two things: (1) the name/portrait head model, built from the stats entry and loaded whether or not the character is in the zone, and (2) a **talk animation** on whichever zone entity has that name. The token has nothing to do with the party, the participant or the activator. | parse `0x456d00` (from `0x458820`); display `0x45b920` → `0x5d59d0`/`0x5f4ec0` (portrait), `0x45bd1e` (entity lookup) |
| What does `participant name="default"` mean? | Each `<startCondition>` maps participant names to root lines. At start the key is the **activator's character name**. If no participant has that name, `"default"` is used; if neither exists, the conversation does not start. XML1 (523) and XML2 (768) only ever use `default`, so a per-hero tree (`<participant name="magma">`) is supported but unused. | `0x45c460` (`"default"` fallback: `push 0x682f90` at `0x45c749`), key from `0x45cbae` (`0x4b7ca0` on the activator) |
| How do `runwithoutuser` lines advance? | **They don't auto-advance.** XMen2.exe has no `runWithoutUser` string. The only time-related attribute, `timeDelay`, is copied to `CS+0x239a8` (`0x4587ee`, `0x45a282`, `0x45a316`) and never read. Every line waits for the accept action (controller "pressed" bit 4, `0x5d4970`, called via UI vt+0x138(4) at `0x45d33e`). Accept is ignored during the first **1.0 s** after the conversation starts (`CS+0x21b5c` = start + `[0x685c28]`=1.0). Voice end never advances a line. | update `0x45d1a0` |
| Why would a line never advance when the next speaker is absent? | **It wouldn't.** No path from accept to the next line reads the speaker. An absent speaker only loses the talk animation; the name label and portrait still show, and the voice plays by `soundtoplay` name. | section 4 and table 5 |
| What stalled 1_2_1_2 then? | **Not established by static code.** Ruled out: the absent speaker, a missing voice (all 21 voices of 1_2_1_2 resolve, including `voice/alison/1_2_0085b` in `manint_v.zss`), the camera script (it runs once, as the startCondition condition), pool limits, and tagjump. Three code paths produce "accept does nothing". None of them fits Jean's line 0084 cleanly, so the remaining candidate is input or game state. A memory probe for the next repro is in section 6. | section 6 |
| Soft-lock survey | 161 XML1 conversations contain 490 lines spoken by a hero who is **not an NPC in any zone that uses the conversation** (so the speaker exists only if that hero is in the party). Of these, **Magma accounts for 107 conversations and 321 lines**, including all 61 Magma "reply menu" lines. By the code above none of them can block the conversation; the loss is cosmetic (no talk animation). | section 7 |

---

## 1. Parse: what XMen2.exe reads from a conversation file

The attribute and child lookups `0x5649c0`/`0x564cb0` use `_stricmp` (`0x672562` → IAT `0x67f180`). XML1's lowercase
names therefore match, and so do XML2 retail's, which are lowercase too.

| element | attributes read (node offset) | ignored in XML1 data |
|---|---|---|
| `startCondition` (`0x459860`) | `conditionScriptFile` (+0xe0), `runOnce`, `enableAI`, `noReturnToGameCamAtEnd`, `noAutoFaceActivator`, `noAnimResetActivator`, `noAnimResetUsed`, `warpCharacter` | - |
| `participant` | `name` → root line (5 slots per startCondition) | - |
| `line` / `response` (`0x458820` / `0x458d10`) | `text` (+4), `textb` (+0xc), `scriptFile` (+0x14), `chosenScriptFile` (+0x1c), `scriptCommand` (+0x24), `conditionScript` (+0x2c), `tagIndex` (+0x34), `tagJump` (+0x3c), `includeCharacter` (+0x44), `excludeCharacter` (+0x4c), `soundToPlay` (+0x54), `soundToPlayB` (+0x5c), `actorAnimation` (+0x74), flags +0x7c (bit0 = talk anim unless `noTalkAnim`, bit1 `conversationEnd`, bit2 `onlyif_brotherhood`, bit3 `onlyif_xman`), `timeDelay` (+0x80, default 0.5) | **`runwithoutuser`** (XMen2.exe has no such string). The port carries it on 307 lines and 223 responses, and XML2 retail on 7 lines and 4 responses. |

Derived fields: speaker key at node+0x64; id at +0x88; child ids at +0x8c..+0xa8 (count +0xac, max 8); remembered
menu cursor at +0x84.

Pools per conversation file: **40 lines** (`0x457b00`, `cmp [+0x4f8],0x28`), **50 responses** (`0x4579d0`,
`cmp [+0x2c8],0x32`), **7 visible responses** per menu (bits 0..6, `0x4559a0`), **6 child lines** per response
(bits 0..5, `0x4559e0`), and **32 loaded files** (`0x459860`, `cmp [+0x328],0x20`). The largest XML1 conversation
(`mansion/man2/1_4_2_5`) has 27 lines and 31 responses, and the largest menu has 6 responses (`2_1_5main`), so no
XML1 conversation exceeds these limits. Ids carry a generation counter and are never 0 (`0x4575d0`, `0x457700`).

**%BLANK% collapse (parse, `0x458e2a`-`0x458e7b`)**: a line's single `%BLANK%` response takes its text from its child
line when that child contains `%PLAYER%` and the parent line has no sibling lines. This is
XML2's "NPC line, then the player's reply" authoring shortcut. XML1 files mostly don't trigger it: their child lines
start with `%MAGMA%`, not `%PLAYER%`.

---

## 2. `%NAME%` resolution in detail

**Parse time**, `0x456d00(textcopy, out, node, text, isResponse)`:

| step | code |
|---|---|
| Built-ins first. `%CONTINUE%`/`%MORE%`/`%END%`/`%NULL%` → speaker "" (none). `%X-TEAM%` → speaker "X-Team". `%PLAYER%: ` / `%PLAYER%` → speaker "X-Team" on normal nodes; on a collapsed `%BLANK%` response (see below) the token is stripped and no speaker is set. At display, speaker "X-Team" becomes the activator's name. | `0x456d41`-`0x456fea`; display `0x45b920` |
| Otherwise the token must start at offset 0 (or offset 4). Up to 27 characters before the closing `%` become the speaker key, stored at node+0x64. | `0x456d00` body |
| The stats registry `0x44b8f0` is queried: vt+0x3c(name) gives an index, vt+0x64(index) gives the entry. If the entry exists, game `0x46dce0` vt+0x118(name) is called (a precache, **UNVERIFIED**). Every `%NAME%: ` or `%NAME%` in the text is then replaced by the entry's localized name (`0x425bc0`) plus `\n`. XML1's `%MAGMA%text` and XML2's `%Magma%: text` therefore render identically, so SPEC's deferred "speaker markup" item needs no conversion. | same |
| On a name miss, the registry returns index 0 (SPEC 12.2). The token then stays in the text verbatim and the key is still set. | same |

**Display time**, `0x45b920` (run for each new line) and `0x45a340` (text):

| effect | uses | absent speaker |
|---|---|---|
| Text rows | node text; `%BLANK%`/`%CONTINUE%` → string 502, `%MORE%` 501, `%END%` 500, `%YES%`/`%NO%` 2026/2027; `%PLAYER%`/`%ACTIVE_HERO%`/`X-Team` → the activator's name | unaffected |
| Name label / portrait head (`CS+0x21b1c`) | `0x5d59d0` → `0x5f4ec0(name)`: stats entry → skin → first file that exists among `ui/hud/characters/%s`, `ui/models/characters/%s`, `hud/hud_head_%s`, loaded into the UI | **still shown**. The port has Magma's heads (`UI/hud/characters/1801, 15801`) |
| Voice | `0x45a170`: `soundToPlayB` if the activator has flag bit 9 in +0x4c8 (the Brotherhood variant, **UNVERIFIED** naming), else `soundToPlay`. Played via audio `0x592480` vt+0x38/+0x48, handle in `CS+0x21b80` | **still plays** |
| Talk animation | `0x45bd1e`: `0x4c7f20` vt+8(key) = zone entity by name. If found, the previous talker gets anim 2 and the speaker gets anim `0xb6+rand(0..2)` (`0x430cd0`). If not found, nothing happens | **skipped silently** |
| Camera | not touched per line. Only the scripts (`*_cam_start` conditionscriptfile, camera calls in line scripts) and the startCondition flags move it | unaffected |

---

## 3. Start: startCondition, participant, activator

| step | code |
|---|---|
| `startConversation(s)` (`0x4a5660`) calls CS vt+0x14 = `0x45c950(name, hero, owner)`. `hero` is the script's entity #1 if it is a character, otherwise the hero of the active controller (`[0x70b814+i*4]`). `owner` is script entity #0 if it is a character (the NPC whose actscript ran), else none. | `0x4a5660` |
| The call is refused inside the cooldown (`CS+0x21b2c`) or while a conversation is active (vt+0x20 = bit 1 of `CS+0x21b24`). | `0x45c950` |
| Participant key = the hero's character name (`0x4b7ca0` on hero+0x35c, `0x45cbae`), falling back to `"default"`. | `0x45c460`, `0x45cbc3` |
| The first startCondition that is not a used runOnce and whose `conditionScriptFile` leaves the condition bit set (preset to 1 by vt+0x34(1), read by vt+0x38) is chosen. **XML1's `*_cam_start` files run here**: they are the camera setup and never clear the bit. | `0x45c460` |
| Unless `enableAI` is set, party AI stops for the conversation (`0x455eb0`) and is restored at the end (`0x455ff0`). | `0x45c8a4`; `0x45cf28`/`0x45cf5b`, `0x4585f0` |
| `startCharConversation(convA, hero, convB)` (`0x4a57b0`) plays `convB` if an entity named `hero` exists **and** a living party member (game vt+0x120 list) has the same name (`_stricmp`), otherwise `convA`. XML2 uses this 23 times for hero-specific banter, e.g. `("…/1_deadzone2_0020","phoenix","…/1_deadzone2_0021")`. | `0x4a57b0` |

---

## 4. Advance: the complete loop (update = CS vt+0xc `0x45d1a0`, called every frame from `0x46f16f`)

| # | step | code |
|---|---|---|
| 1 | Skip unless the system is initialised (bit 0x10) and active (bit 1 of `CS+0x21b24`). End the conversation if its file is no longer loaded (`0x456440`, then `0x4585f0`). | `0x45d1a6`-`0x45d22c` |
| 2 | **Pending response** (`CS+0x239a0` ≠ 0): if its voice is still active (audio vt+0x60 `0x5909a0`), stop it (vt+0x74 `0x590780`), then advance (`0x45cde0`). | `0x45d23a`-`0x45d295` |
| 3 | If the ending flag (bit 3) is set, end via `0x4585f0`. | `0x45d2aa` |
| 4 | Draw the current line (`CS+0x4bc`) through vt[0] `0x45beb0`. This rebuilds the response menu every frame (`0x45b0a0`). | `0x45d2c3`-`0x45d2ec` |
| 5 | Menu filter per response: its `scriptFile`/`scriptCommand` run once as a visibility condition (cached in +0xb6). `includeCharacter`/`excludeCharacter` are compared with the activator's name. `onlyif_brotherhood`/`onlyif_xman` test activator flag bits 8/9. If no response is visible, `0x457550(1)` sets the ending flag. | `0x45b0a0` |
| 6 | **Accept**: UI vt+0x138(4) (bit 4 of the pressed mask of an active player's controller, `0x5d4970`) **and** `now > CS+0x21b5c`. Then play a UI sound, stop the line voice, and call vt+0x18 = `0x45d5d0(sel)`. | `0x45d333`-`0x45d3bc` |
| 7 | Up/down move `sel` (`CS+0x21b26`), wrapping over the visible count `CS+0x21b28`. | `0x45d3bf`-`0x45d493` |
| 8 | `0x45d5d0(sel)` picks the sel-th **visible** response. If it has `soundToPlay` and no voice is playing, `0x458700` plays the voice, sets it as pending and returns (step 2 advances it next frame). Otherwise it advances immediately. | `0x45d5d0`, `0x458700` |
| 9 | Advance `0x45cde0(resp)`: `tagJump` → the line in the same file whose `tagIndex` matches (case-sensitive). Otherwise the next line is the first child whose bit is set in `CS+0x239c0` (`0x45b6d0`: bits 0..5 preset, the response's `conditionScript` may clear them, the response's scriptFile/scriptCommand then run). No child → ending flag. `chosenScriptFile` runs. The next line is looked up with `0x4573f0`: **if the lookup is NULL, the function returns and nothing changes**. Otherwise the line is displayed (`0x45b920`, which also runs the line's scriptFile/scriptCommand and starts its voice). | `0x45cde0`, `0x45d0b1`-`0x45d199` |

Timers: none. The only "wait" in the whole loop is step 2, and that step **stops** a response voice that is still
playing rather than waiting for it. Read literally, a voiced response (XML1 has **240**; XML2 retail 6, all Storm and
Frost) is cut one frame after it starts. **UNVERIFIED in game**: pick the reply that asks what the place is in the
tour and listen.

---

## 5. What an absent speaker changes

| aspect | present (NPC or party member with that name) | absent |
|---|---|---|
| line text and name label | "Magma" plus the text | same |
| portrait head | loaded by stats skin | same (the model is loaded even if the character isn't in the zone) |
| voice (`soundtoplay`) | plays | plays |
| talk animation on the speaker | yes | none; the previous talker is returned to anim 2 |
| which line comes next | child/tagjump rules (step 9) | same |
| accepting input | step 6 | same |
| menu lines (`%MAGMA%` + responses) | the responses are the player's choices | same; the choices still work |

Name clash, which is the case in Owen's run: with Phoenix in the party *and* NPC Jean (`sp_phoenix01`,
`monster_name=phoenix`) in `mansion1a_1`, the talk-animation lookup for `PHOENIX` can hit either entity
(**UNVERIFIED** which one). This is cosmetic in conversations. The same clash matters in zone scripts, for example
`remove("phoenix","phoenix")` in `mansion1a_1.py` (end-of-tour branch) and SPEC 18's open risk.

---

## 6. The 1_2_1_2 stall (Wolverine/Phoenix/Rogue party, Jean's line 0084)

The conversation is 16 lines and 21 responses (`Conversations/mansion/man1a/1_2_1_2.engb`, one `default` participant).
It is precached by `mansion1a_1` (soundfile `manint`) and started by `trigger_touch07` → `mansion/man1a/conv_1_2_1_2.py`.
The chain in question is Jean 0084 → `%BLANK%` → Magma 0085b → `%BLANK%` tagjump `startTour` → the menu line
`text="%MAGMA%"` with 6 responses.

| candidate | check | verdict |
|---|---|---|
| Magma absent blocks the next line | no speaker read on the accept → advance path (section 4). Magma's line 0083, one step earlier, *did* advance with Magma equally absent | ruled out |
| Missing voice 1_2_0085b | `research/sound/simlookup.py` (a simulation of the `0x590bd0` lookup) against `manint_{m,a,c,d,v}` + `x_common` + `x_voice` in the build: **all 21 voices resolve** in `Sounds/eng/m/a/manint_v.zss`. A missing voice would not block anyway (step 9 doesn't read it) | ruled out |
| Waiting for `runwithoutuser` / voice end | not implemented (section 0); every line needs accept | not a stall, but explains the behaviour difference from XML1: the tour no longer plays itself |
| Camera script | `1_2_1_2_cam_start` = `cameraMove` + `cameraPan` 0.5 s, run once at start as the startCondition condition | ruled out |
| tagjump / pools | `startTour` exists (same case); the file is well under 40/50 | ruled out |
| (a) **cursor clamp**: the menu builder sets `sel = visibleCount` when `sel ≥ visibleCount` (`0x45b5f1`-`0x45b5fc`: `cmp ecx,edi / jl / mov [+0x21b26],di`), leaving nothing highlighted. Accept then selects nothing until Up/Down is pressed | for 0084 (one always-visible response, cursor 0 on first visit) this cannot happen. It **can** happen on menus that come back via tagjump with hidden responses (`disallowResponseOnVar`), such as `startTour` | not this line, but a real "Enter does nothing" trap (see 8) |
| (b) next-line lookup NULL (`0x45d106`) | needs the child id to be missing or the file key `CS+0x4b0` to change. The key is overwritten with a **stack address** whenever a conversation file loads (`0x4598f1`), and files load only through precache (`0x561353`). No evidence of a mid-conversation load | unlikely |
| (c) accept never registered | bit 4 of the controller pressed mask for an active player (`0x5d4970`). Depends on key binding, window focus, the test InputPipe, or another UI layer / popup taking input (**UNVERIFIED**) | **leading candidate**, and not speaker-related |

**Next repro, read-only memory probe**: read these fields with a ReadProcessMemory script like `tools/current_zone.py`
from `base = [0x717aac]`. Pressing Up then Enter separates (a) from (c).

| field | meaning |
|---|---|
| `+0x21b24` (byte) | bit1 active, bit3 ending, bit4 initialised |
| `+0x4bc` | current line id (compare with the ids at line+0x88) |
| `+0x21b26` / `+0x21b28` (short) | selected index / visible response count. **If sel == count, it is (a)** |
| `+0x4e0`, `+0x4c0..` | response slots (-1 = hidden) |
| `+0x239a0` | pending response id (should be 0 within a frame) |
| `+0x21b80` | voice handle (`[0x69d05c]` = none) |
| `+0x21b5c` (float) | accept-enable time |
| `+0x4b0` | pointer to the current file key; a stack address means (b) |

---

## 7. Survey: hero-speaker lines that depend on the party

Method: all 379 XML1 conversations in `build/_heroes/Conversations`. A `<line>` whose text starts with a hero token is
counted. The hero counts as **party-dependent** if it is in no `CHRB` and no spawner `character`/`monster_name` of
any zone that precaches the conversation. Zone → mission comes from the world entity's `mission=`; a zone without it
gets its folder's mission, marked `*`. Built-in tokens are excluded. Heroes: wolverine, cyclops, storm, rogue, iceman,
phoenix, beast, nightcrawler, gambit, magma, colossus, psylocke, jubilee, frost, profxastral.

Totals: 341 (conversation, hero) pairs, **205 party-dependent**, in **161 conversations**, with **490 lines** (408
voiced, 65 `runwithoutuser`, 63 reply-menu lines). By hero: magma 107 conversations, phoenix 24, wolverine 21, cyclops 19,
frost 6, storm 6, rogue 5, profxastral 4, iceman 4, beast 3, gambit 2, colossus 2, nightcrawler 2. Magma is an NPC in
only 5 conversations (dr_mag2 `mag_nyc4` ×4, alison `nyc1_1_3`).

Legend: `Nc/Ml/Km` = N conversations / M lines / K of those lines are reply menus. Forced = XML1 REQUIREDHERO / maxheros
(`mission_plan.json`).

| mission | act | XML1 forced | max | convs | party-dependent speakers |
|---|---|---|---|---|---|
| alison | 1 | wolverine, cyclops | 2 | 4 | wolverine 3c/7l/1m; phoenix 1c/2l |
| haarp | 1 | - | 4 | 1 | cyclops 1c/1l |
| jug_fb | 1 | cyclops, beast, iceman, phoenix | - | 1 | beast, phoenix, cyclops 1c/1l each |
| **mansion1** | 1 | **magma** | 1 | 30 | **magma 29c/77l/11m**; cyclops 1c/1l |
| **mansion2** (+`mansion_back2`, `mansion2_1`*) | 1 | **magma** | 1 | 15 | **magma 14c/68l/11m**; wolverine 2c/3l; gambit, rogue, storm 1c/1l |
| sent_fb | 1 | nightcrawler | 4 | 1 | wolverine 1c/2l; phoenix, nightcrawler, cyclops 1c/1l |
| arbiter_int* | 2 | - | - | 5 | phoenix 5c/7l |
| arbiter_flood* | 3 | - | - | 4 | phoenix 4c/7l |
| dr_mag2 | 3 | magma, cyclops | 2 | 5 | magma 5c/9l; wolverine 2c/3l; storm 1c/1l |
| **mansion3** | 3 | **magma** | 1 | 16 | **magma 13c/44l/10m**; rogue 4c/16l |
| mansion3_dangerroom | 3 | magma | 1 | 1 | magma 1c/4l |
| wx_fb_start* | 3 | wolverine | 1 | 1 | wolverine 1c/2l |
| **muir2** | 4 | **magma** | 1 | 6 | **magma 6c/22l/4m** |
| astral1 | 5 | profxastral, phoenix, frost | 3 | 2 | profxastral 2c/3l; phoenix 2c/2l; frost 2c/2l |
| astral1b | 5 | phoenix, frost | 2 | 2 | phoenix 1c/2l; frost 1c/2l |
| **mansion4** (+`subbasement4`*) | 5 | **magma** | 1 | 12 | **magma 10c/25l/7m**; wolverine 2c/2l; colossus, frost, iceman, storm 1c each |
| mansion4_grso | 5 | - | 4 | 6 | phoenix 6c/6l; beast 1c/1l |
| muir2_reboot | 5 | magma | 1 | 6 | magma 6c/10l |
| secret_wx | 5 | wolverine, cyclops | 2 | 2 | cyclops 2c/5l; wolverine 2c/3l |
| mansion5 (+`subbasement5`*) | 6 | magma | 1 | 6 | magma 6c/10l/5m; wolverine, gambit 1c/2l; iceman 1c/1l |
| mansion6 (+`subbasement6`*) | 7 | magma | 1 | 7 | magma 5c/16l/4m; cyclops 2c/7l; storm 1c/1l |
| muir3 | 7 | - | 4 | 1 | cyclops 1c/1l |
| riots | 7 | - | 4 | 1 | wolverine 1c/2l/1m |
| mansion7 | 8 | magma | 1 | 7 | magma 4c/13l/4m; cyclops 3c/8l; wolverine 2c/2l; iceman 1c/2l; colossus, storm, nightcrawler 1c/1l |
| asteroid_int2 | 9 | - | 4 | 3 | magma 3c/9l (XML1 checks Magma itself, see below) |
| asteroid_rock | 9 | frost | 4 | 1 | frost 1c/2l |
| old_wx (`wx2_2`, mapload of boss_havok) | 5 | cyclops | 1 | 4 | cyclops 4c/12l |
| mansion8 (+`hangar8`*) | 9 | magma | 1 | 6 | magma 5c/14l/5m; beast, wolverine 1c/1l |
| demo (`demo/a_int`) | - | - | - | 4 | phoenix 4c/5l |
| not precached by any zone | - | - | - | 6 | `astral/ast3/3_7_5`, `3_7_6` (profxastral); `mansion/man5/2_5_15` (phoenix, frost, cyclops, wolverine; started by `subbasement5b.py`); `mansion/man8/3_9_0`; `nyc/alison/1_1_6_5` (magma, phoenix); `xjet/1_7_1` (cyclops, wolverine, storm; `blackbird_arbiter.py`) |

Magma conversations by mission, for the forced-party work: mansion1 29 (`1_2_1_1`, `1_2_1_2`, `1_2_3`, `1_2_24_1b`,
`1_2_26_5`, `1_2_31_5`, `1_2_32`, `1_2_35`..`1_2_38` hold reply menus), mansion2 14, mansion3 13, mansion4 10,
muir2 6, muir2_reboot 6, mansion5 6, mansion6 5, dr_mag2 5, mansion8 5, mansion7 4, asteroid_int2 3,
mansion3_dangerroom 1, and `nyc/alison/1_1_6_5` (not precached).

Existing party-aware mechanisms:

| mechanism | who | status in the port |
|---|---|---|
| `getName("_HERO1_".."_HERO4_")` loop → `startConversation(A or B)` | XML1 `asteroid_m/alisoncheck.py`, `start2_3.py` (with Magma `3_10_3_1`, without Magma `3_10_3_2`) | XMen2.exe knows `_HERO1_`..`_HERO4_` (`0x68d410`.., used by the actor lookup `0x4a1789`). Expected to work, **UNVERIFIED** |
| `startCharConversation(convA, hero, convB)` | XML2 (23 scripts) | available; unused by the XML1 content |
| `isActorOnTeam(a)`, `includeCharacter`/`excludeCharacter`, `<participant name="hero">` | XML2 | available; `includeCharacter`/`excludeCharacter` and participant trees are unused by both games |

---

## 8. Side findings (engine behaviour that affects XML1 content)

| # | finding | evidence | consequence for the port |
|---|---|---|---|
| 1 | `runwithoutuser` is ignored and `timeDelay` is never read | section 0 | The XML1 tour and cutscene chains (307 lines) need the player to press accept after every line. XML1 parses `runWithoutUser` into node flag +0x68 bit 2 (default.xbe `0x619a6`); its runtime use was not traced (**UNVERIFIED**: presumably auto-advance) |
| 2 | Voiced responses are stopped one frame after they start | `0x458700` + `0x45d242`-`0x45d27d` | 240 XML1 responses (mostly Magma's spoken choices) may be inaudible (**UNVERIFIED**, listen) |
| 3 | Cursor clamp `sel = count` | `0x45b5fc` | On re-entered menus with hidden responses nothing is highlighted and Enter does nothing until Up/Down. It hits XML1's hub menus (tagjump back, `disallowResponseOnVar`) |
| 4 | Unresolved cross-file tagjump | `mansion/man4/2_5_10b` → `2_5_10loop` (the tagIndex is not in that file; the other 364 XML1 tagjumps resolve) | In XML2 the lookup fails, and a `%BLANK%` response with no child then ends the conversation |
| 5 | The file key `CS+0x4b0` points at a stack local after any conversation file load | `0x4598f1` | Harmless while conversations load only at zone precache. Don't add runtime conversation precache without saving and restoring the key |

## 9. Implications for "force XML1's party"

- Enforcing the forced parties is **not needed for conversations to work**, and the absent speaker did not cause the
  1_2_1_2 stall. With Magma seated, the 321 Magma lines gain a talk animation and nothing else changes functionally.
- If the goal is XML1 fidelity for conversations, three xml2-fix candidates (each a guarded patch like `new_game.cpp`):
  1. **auto-advance**: at parse `0x458820`, read `runwithoutuser` into spare flag bit 0x10 of node+0x7c. In update
     `0x45d1a0`, auto-select when the current line has the bit and exactly one visible `%BLANK%` response, once the
     line voice has ended (audio vt+0x60 false) or `timeDelay` (`CS+0x239a8`) has elapsed.
  2. **let response voices finish**: in the pending branch `0x45d242`, return while vt+0x60 is true instead of
     stopping the voice.
  3. **clamp fix** at `0x45b5fc`: store `count-1` (or 0) instead of `count`.
- For non-forced play, the data-only options are the participant tree keyed by the activator's name
  (`<participant name="magma">` plus a `default` tree with `%PLAYER%`) and `startCharConversation`/the `_HEROn_` check.

## 9a. XML1's own speaker resolution (default.xbe, read 2026-09-29)

Read from `research/scripts/xml1_text.asm` for the Alison / Emma speaker fix (SPEC 18.1).

| step | default.xbe | XMen2.exe |
|---|---|---|
| built-in tokens | `%BLANK%` `%CONTINUE%` `%MORE%` `%END%` `%NULL%` `%PLAYER%` (skip), `%X-TEAM%` -> key "X-Team" (`0x61ad8`-`0x61bc1`) | the same set (section 2) |
| `%ALISON%` | `0x61bc6`: `_stricmp` with "%ALISON%" (0x3cc014). Key = the name of the stats entry "Magma" (`0x61bde`-`0x61c24`: registry vt+0x3c("Magma") -> vt+0x68 -> `0x13dc0`); precache vt+0xdc("Magma"). Every `%ALISON%` in the text becomes **string 503** (`0x61c81` string table vt+8(0x1f7); `data/strings.eng` id 503 = "Alison", the same in .fre/.ger) + the separator | no such alias |
| other `%NAME%` | `0x61d54`: key = the token's name (<= 27 chars), stats lookup; the label is the entry's name (`0x13dc0`) | `0x456d00`, label = the entry's localized name |
| talk animation | `0x6443e` (line flag +0x6c bit 0): previous talker (handle at `CS+0x3e18`) gets anim 2; `0xbef20` vt+8(key) finds the new talker, which plays anim `0xba+rand` and is stored at `CS+0x3e18` | `0x45bd1e`: `0x4c7f20` vt+8(key), anim `0xb6+rand`, handle at `CS+0x2399c` |

So XML1 showed every `%ALISON%` line (213 in 72 English conversations) as **"Alison"** with Magma's portrait, and
keyed the talk animation to Magma - the party Magma where one was there. XMen2.exe takes the label and the entity
from one key, so the port's party-Magma lines (`%MAGMA%`) say "Magma"; only an engine alias could show "Alison" there.
`0xbef20` vt+8 has XMen2.exe's lookup shape (by entity name, not traced further): if it matches entity names only, as
XMen2.exe's does (verified: `%MAGMA%` found no talker in nyc1_1_3, where the NPC is `alison` with character magma),
XML1 animated neither the NPC Alison (`alison`, key Magma) nor the NPC Emma (`emma`, key FROST), and the party Magma
mouthed the simulated Alison's line in mag_nyc4. The port gives those lines to the NPCs (SPEC 18.1).

## 10. Open questions / UNVERIFIED

1. Which input stopped 0084 from advancing: the probe in section 6 on the next repro (read-only; no launch was done here).
2. Whether the response voice is audibly cut (finding 2).
3. XML1's runtime meaning of `runWithoutUser`/`timeDelay` (auto-advance timing), needed to reproduce it exactly.
4. Whether `0x4c7f20` vt+8 matches entity names only or also character names (it decides which Phoenix gets the talk
   animation in a name clash).
5. Game vt+0x118(name) called for speakers (a precache?) and the meaning of activator flag bits 8/9 (the
   Brotherhood/X-Men variants).
