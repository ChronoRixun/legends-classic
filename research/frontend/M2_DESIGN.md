# M2 design: XML1 front end, Danger Room, Review (2026-09-28)

Read-only research for the main session. Nothing here is implemented yet. Sources: the XML1 disc extraction
(`xml1_xbox`, `xml1_assets`, `xml1_loose`), the XML2 install (`<XML2 folder>`, read-only),
`research/scripts/xml2_text.asm` (XMen2.exe listing) and `research/scripts/xml1_text.asm` (default.xbe listing),
and the play build `build/_heroes` (for "what the port does today").

**Labels.** VERIFIED means checked in the data or at the cited exe address. UNVERIFIED means inferred, still
to be proven in game or by deeper RE. Exe addresses are XMen2.exe VAs unless marked `xbe`.

Probe scripts (generic, no game content) are in `research/frontend/probes/`:

| Script | Purpose |
|---|---|
| `exact.py <exe> name...` | whole-string presence of attribute names in an exe |
| `igbnames.py <igb>...` | IGB string fields and their padded sizes (for in-place renames) |
| `sfd_dur.py <glob>` | movie length from the first ADX header; matches XML2's own `duration` values within 0.3 s |

---------------------------------------------------------------------------------------------------------------

## 0. Summary

| Item | Recommendation | Owner | Main risk |
|---|---|---|---|
| A. Front end | XML1 Cerebro backdrop zone, XML1 menu music, XML1 intro logos. XML1 main-menu IGB (`menu_main.igb` with its 3D logo), with 7 button nodes renamed in place to the names XMen2.exe hard-codes (`label_option04..08`, `debug_text`), plus an XML2-schema `UI/menus/main` menu file. | new `frontend.py`; small changes in zones / scripts / media | renamed IGB nodes place text differently (fallback: A3, section A.4.6) |
| B. Danger Room | Keep XML2's `danger_room` menu UI. Replace `Data/dangerroom` with XML1's courses converted to XML2 schema (REWARD children, first grade unlocked, QE200 exam flag). Add the 19 challenge reward items. | `frontend.py`; zones (items) | XML1 extra-credit and points-gating logic has no XMen2.exe equivalent |
| C. Review | Keep XML2's review / codex / trivia / credits menus. Replace `Data/review_paths`, `codex`, `trivia` and `credits` with XML1 data. Import XML1 comic, concept and loading textures under a collision-free namespace, and rewrite the `imageViewer()` literals to match. | `frontend.py`; scripts (literal rewrite); zones (loading names) | trivia is per act in XML2; `marvel`-group concept art has an unknown unlock path |
| D. Found on the way | End of campaign: XML2's `credits_end` loads `act5/egypt/egypt6` after the credits. XML2's Danger Room today spawns 68 dropped XML2 NPCs. XML1's main menu had an idle promo (i107). | xml2-fix (later batch) | see section D |

Suggested build switch: `--frontend xml1|xml2` (env `XML1BUILD_FRONTEND`, default `xml1` once verified).
`xml2` keeps today's behaviour, as an A/B fallback. `build_xml1.plan_content_opts` re-runs zones, scripts, media
and frontend when the switch changes.

### 0.1 Where the XML1 files live

| Tree | What it is | Front-end content |
|---|---|---|
| `xml1_xbox/` | the raw disc: `default.xbe`, `movies/ntsc|pal/**.sfd`, `sounds/zsds/**`, `z/assetsfb.zip` (1,888 files, 1.83 GB) | movies, menu music banks `sounds/zsds/m/e/menu_{a,c}.zss` (1,114,376 B each) |
| `xml1_assets/` | `assetsfb.zip` extracted: loose data plus the `packages/generated/**.fb` bundles | `data/{dangerroom,review_paths,strings,...}.eng`, `scripts/menus/*.py`, `textures/{comic,concept,loading,personal}`, `movies/*.eng` subtitles, the `packages/generated/maps/package/menus/*.fb` menu bundles |
| `xml1_loose/` | the `.fb` bundles unpacked (`tools/fb_unpack.py`); `_fb_manifest.json` = bundle -> `[[path, kind]]`; `ctx.x1_path` prefers it | `ui/menus/*.eng|xml|igb`, `ui/models/*.igb`, `maps/menu/main_back.*`, `motionpaths/menus/main_back.igb`, `data/{codex,trivia,credits,dangerroom,review_paths}.eng`, `textures/legal/*` |

### 0.2 What XMen2.exe hard-codes for the front end (all VERIFIED at the address given)

| What | Where | Consequence for the port |
|---|---|---|
| boot: `openmenu legal_pc` | 0x40187e (string 0x680120) | the legal menu name is fixed; its contents are data |
| boot: `runscript menus/intro_normal` (always; the `main` compare at 0x402c8f is a dead debug switch) | 0x402cd1 | the intro is a script; replace `Scripts/menus/intro_normal.py` |
| `mainmenuexit` console handler: `resetgame`, then `loadmap menu/main_back` | 0x5f2892, 0x5f28a3 (handler 0x5f27a0) | the backdrop zone **name** is fixed; the content is data. XML1's backdrop has the same name. |
| menu files: `ui/menus/%s.xmlb`, `ui/menus/%s.igb`, package `generated/maps/package/menus/%s` | 0x69e244, 0x69e228, 0x6a1c40 | a menu = its XMLB/engb + IGB + PKGB |
| MAIN_MENU class, mouse handler: looks up items `label_option04..09`, `debug_text`, `debug`, `debug_focus` (NULL-safe loop) | 0x5c933f..0x5c93ca | mouse clicks work only on items with these names |
| MAIN_MENU update: focus on `debug_text` + accept sets the quit flag `[0x6f3a2d]=1` | 0x5c969f..0x5c96dd | **Quit on PC needs an item named `debug_text`** (there is no `quit` console command, `research/scripts/xml2_console_cmds.txt`) |
| MAIN_MENU update: `label_option09` used -> `openmenu online` | 0x5c9857..0x5c9867 (0x6e662c) | leave `label_option09` out (no Play Online) |
| MAIN_MENU update: `label_option06` used -> if the profile's story level (vt+0x3c of 0x48fed0) >= 6, `set drmode 1;openmenu danger_room`, else popup string 636 (the "unlocked at story level 6" message) | 0x5c98c9..0x5c9950 | the Danger Room item must be named `label_option06` and must have **no** `usecmd` |
| MAIN_MENU update: compares the focused item's name with **`button3`** (XML1's Danger Room item) | 0x5c97c1 (0x6a1374) | leftover XML1 logic; harmless |
| MAIN_MENU open: sets `debug_text` text to "Quit" and shows `desctext1` | 0x5c9986..0x5c99e1 | `debug_text` shows its own text |
| demo mode (`[0x7298a8]==2`) disables `label_option06/07/09` | 0x5c92a5 | not our case |
| script functions `reviewLoadScreens/Cinematics/Comics/Concept` -> `set reviewmode 0|1|2|3;openmenu review`; `dangerRoomMenu()` -> `set drmode 0;openmenu danger_room`; `codexMenu(i)` -> filter i + `openmenu codex`; `triviaMenu()` -> `openmenu trivia` | 0x49e39a/3ca/3fa/42a, 0x49e62f, 0x49e250, 0x49e2a0 | XML1's in-mansion consoles (below) already call these; they open XML2's menus |
| data tables loaded by path: `data/review_paths.xmlb` 0x68da78, `data/codex.xmlb` 0x69e67c, `data/trivia.xmlb` 0x6a30dc, `data/dangerroom.xmlb` 0x68fbe8, `data/credits.xmlb` 0x69e7a4 | - | these are data swaps; no exe change |
| window title "X-Men Legends 2" (igWindow create) | 0x5faf43 | the same string is the registry root `Activision\X-Men Legends 2` (0x5f5215, 0x6174dc); do not patch the string. Retitle through xml2-fix's existing `CreateWindowExA` hook (display.cpp) in a later batch. |
| endgame credits: after the credits, `runscript saveloadProcess(2)`, then `runscript loadZone('act5/egypt/egypt6','')` | 0x5b1df4, 0x5b1cbf | see D.1 |

XMen2.exe does **not** read these XML1 menu attributes (checked with `probes/exact.py`): `zone_background`,
`zone_script`, `focusitemname`, `focusmodel`, `animonopen`, `holdframe`, `pathstype`. It does read `usecmd`,
`startactive`, `text`, `style`, `gamevar`, `igb`, `lighting`, `enabled`, `hide`, `debug`, `neverfocus`,
`model`, `mode`, `arrowmodel`, `items`/`MENU_ITEMS`, `perspective_camera`, `background`, `no_stack`,
`up`/`down`, and `<onfocus>` children.

---------------------------------------------------------------------------------------------------------------

## A. The front end

### A.1 What XML1 has

| Part | File(s) | Size | Notes |
|---|---|---|---|
| backdrop zone `menu/main_back` | `xml1_loose/maps/menu/main_back.{igb,xml,chr,nav}` | 281,856 / 217 / 16 / 0 | the **Cerebro** room (nodes `Cerebro*`, `CerebroSphere`, `menu_back*.png`). World: `zonescript="menus/main_back_main" soundfile="menu"`, precache motionpath `menus/main_back/mp_camera`. The `.chr` is empty and the `.nav` is 0 bytes. |
| camera path | `xml1_loose/motionpaths/menus/main_back.igb` | 28,588 | object `mp_camera` (VERIFIED, `probes/igbnames.py`) |
| zone script | `xml1_loose/scripts/menus/main_back_main.py` | 133 | byte-identical to XML2's (`cameraFollowMotionPath("menus/main_back","mp_camera",...)`) |
| zone bundle | `xml1_assets/packages/generated/maps/menu/main_back.fb` | 332,615 | entries: combat_is on, script, motionpath, actoranimdb `actors/mission_menu.igb` (20,237 B, a Bip01 skeleton), characters, model, zonexml, nav |
| main menu | `xml1_loose/ui/menus/main.eng` (+ `.fre/.ger`) | 3,239 | `type="MAIN_MENU" igb="menu_main" zone_background="menu/main_back"`. Items `button1..9` (text + `usecmd`), `buttonN_back` / `buttonN_highlight` models, `desctext1`, `version` (gamevar). Visible order: **Begin Story, Load Game, Danger Room, Options, Review, Credits**; `button7..9` are `debug="true"` (Load Mission, Debug, hidden). |
| main menu scene | `xml1_loose/ui/menus/menu_main.igb` | 153,576 | nodes `button1..9`, `buttonN_back`, `buttonN_highlight`, `desctext1`, `version`, **`3d_logo`** (texture `metal_noise.png`), lights `Omni10/12/13`, `Camera01`. This is XML1's only logo on the disc; there is no 2D logo texture (checked `textures/**`, `ui/**`). |
| menu bundle | `xml1_assets/packages/generated/maps/package/menus/main.fb` | 239,480 | `ui/menus/menu_main.igb`, `ui/models/model_button`, `model_button_highlight`, `model_hide`, `ui/menus/main.eng` |
| intro | `xml1_assets/scripts/menus/intro_normal.py` | 326 | `startMovie` i102 (Activision), i101 (Marvel), i103 (Raven), i104 (Vicarious Visions), i105 (Sofdec), then `openmenu("main")`. Labels from XML1 `review_paths.eng`. |
| attract | default.xbe main-menu idle timer -> `startMovie('i107', '')` when config `MAP/showMovies` | xbe 0x17e8c7..0x17e933 | i107 = "X-men Legends Promo", 71.0 s |
| movies | `xml1_xbox/movies/ntsc/i/1/i10{1,2,3,4,5,7}.sfd` | 5.4 / 4.5 / 9.8 / 1.7 / 1.2 / 29.2 MB | XML1 NTSC has no i106. media installs them renamed `xi101..xi105, xi107`. |
| menu music | `xml1_xbox/sounds/zsds/m/e/menu_{a,c}.zss` | 1,114,376 each | one stream each, key `music/menu_a` / `music/menu_c`. The fixed-layout PC re-encode already exists: `research/sound/music0x20/banks/eng/m/e/menu_{a,c}.zss` (988,984 B, 44.1 kHz stereo). |
| legal | `xml1_loose/ui/menus/legal_xbox.eng`, `textures/legal/legal_xbox.igb` | - | the texture names Xbox; not wanted on PC |
| loading screen | `ui/menus/loading.xml` (`IMAGE_VIEWER_MENU`, `menu_loading.igb` + `loading_anim.igb`) | - | XML2 ships PC copies of both IGBs (same sizes) |
| fonts | `xml1_assets/ui/fonts/font_xmen_*.xml` + `textures/fonts/*.igb` | - | optional (A.4.7) |

### A.2 What the port does today (XML2's, kept by SPEC 11.1 / `C.FRONTEND_ZONES`)

| Part | XML2 file kept | Size | What the player sees |
|---|---|---|---|
| backdrop | `Maps/Menu/main_back.{IGB,XMLB,CHRB}`, `MotionPaths/menus/main_back.{IGB,XMLB}`, `Packages/generated/maps/menu/main_back.PKGB` | 5,550,180 / 784 / 35 / 179,108 / 282 / 608 | the Egypt tomb with fire torches. World has `nosave="true" startblack="true"`. |
| zoneinfo | `menu/main_back act=1 loading=textures/loading/main_menu` | - | XML2's loading image |
| main menu | `UI/menus/main.{XMLB,engb}` + `x2m_main.IGB` (29,218) + `main.PKGB` | 6,605 / 6,499 | PDA-style buttons, `ui/models/m_logo` (XML2 3D logo, 46,742 B), `title_text01` "r i s e   o f   a p o c a l y p s e", items New Game / Load Game / Danger Room / Review / Options / Play Online + Quit (`debug_text`), `image="textures/loading/0303"` |
| intro | `Scripts/menus/intro_normal.py` (386 B) | - | XML2's i102, i101, i103, i107 (Beenox), i104, i105, then `mainMenuExit()` |
| music | `Sounds/eng/m/e/menu_{a,c}.zss` = merged bank (XML2 entry wins, byte size = XML2's 495,864) | - | XML2 menu music |
| XML1 logos | `Movies/ntsc/eng/x/i/xi10*.sfd` installed but unused (media note "no installed script plays") | - | - |

### A.3 Gap

| XML1 look | Blocker in XMen2.exe | Resolution |
|---|---|---|
| Cerebro backdrop | none: same zone name | convert XML1's `menu/main_back` (drop the SPEC 11.1 exception) |
| per-menu `zone_background` / `zone_script` | not read (0.2) | nothing needed: the exe always loads `menu/main_back` |
| XML1 button layout and 3D logo | the MAIN_MENU class binds its behaviour to item **names** (0.2); XML1's IGB node names are `buttonN*` | rename 7 IGB nodes in place (A.4.2), or repoint the exe operands in xml2-fix (A.4.6) |
| focus highlight (`focusitemname` / `focusmodel`) | not read | `<onfocus item=... model=... type="focus|nofocus">` |
| implicit up/down order | UNVERIFIED whether XML2 derives navigation from item order | explicit `up` / `down` attributes |
| Quit | XML1 has none; PC needs `debug_text` | item `debug_text` on a renamed node |
| Play Online | exe-bound to `label_option09` | leave the item out |
| menu music | the merged bank keeps XML2's single `music/menu_a` sound | install XML1's fixed bank for `menu_a` / `menu_c` only |
| intro logos | the script is data | XML1's order with the `x` names, ending with `mainMenuExit()` (not `openmenu("main")`: mainmenuexit is what loads `main_back`) |
| idle promo (i107) | no attract call found in XMen2.exe's MAIN_MENU; the idle timer at 0x5c9754 is kept but unused | optional xml2-fix feature (D.3) |
| window title / registry | "X-Men Legends 2" string shared with the registry path | xml2-fix title override (later batch); do not patch the string |

### A.4 Conversion plan

#### A.4.1 Backdrop zone (zones.py)

| Step | Detail |
|---|---|
| gate | `C.FRONTEND_ZONES` applies only with `--frontend xml2`. With `xml1`, zones converts `menu/main_back` like any zone (`classify` already returns `menu_background`). |
| world | XML1 world plus XML2's `nosave="true" startblack="true"` (both XML2 world attrs; `startblack` UNVERIFIED as needed). Keep XML1's extents / zonescript / `soundfile="menu"`. |
| motionpath | XML1 `motionpaths/menus/main_back.igb` (the FORCE prefix `motionpaths/` already makes XML1 win). The base `MotionPaths/menus/main_back.XMLB` stays (it names the same zonescript and `mp_camera`). |
| package | from the XML1 bundle through `build_package`: script, motionpath `menus/main_back/mp_camera`, characters, model, zonexml, boy. No nav (0-byte `.nav`, SPEC 4.5; no combat here). `actoranimdb mission_menu` is optional (no characters in the zone). Keep XML2's `bigconvmap off`. Drop XML2's `zam automaps/menu/main_back` (the file does not exist in XML2 either). |
| zoneinfo | keep XML2's `menu/main_back` entry (act 1). Set `loading` to an XML1 screen (proposed `textures/loading/x_mansion`; open question E.3). |
| script | scripts installs XML1's `menus/main_back_main.py` (identical) and stops listing it in `FRONTEND_KEEP_XML2` under `--frontend xml1` |

#### A.4.2 Main menu (frontend.py)

**IGB.** Import `xml1_loose/ui/menus/menu_main.igb` as `UI/menus/x1_menu_main.IGB`. XML2 ships an unrelated
`UI/menus/menu_main.IGB`, a 27 KB prototype nothing uses; do not overwrite it. Rename these nodes in place with
`x1names.igb_rename(data, old, new, suffixes=('',))`. Each name occurs 3 times (node name, ItemName value, path).
Every rename fits the 16-byte padded field (VERIFIED, `probes/igbnames.py`).

| XML1 node (field) | Renamed to | Item role | Text | `usecmd` | Focus highlight node |
|---|---|---|---|---|---|
| `button1_back` (16) | `label_option04` | focusable, `startactive` | Begin Story | `newgame` | `button1_highlight` |
| `button2_back` (16) | `label_option05` | focusable | Load Game | `runscript saveloadProcess(3)` | `button2_highlight` |
| `button3_back` (16) | `label_option06` | focusable; the exe opens the Danger Room with the level-6 gate | Danger Room | **none** | `button3_highlight` |
| `button4_back` (16) | `label_option07` | focusable | Options | `options_main` | `button4_highlight` |
| `button5_back` (16) | `label_option08` | focusable | Review | `set reviewmode -1;openmenu review` | `button5_highlight` |
| `button6_back` (16) | `label_credits` | focusable (generic item; mouse only through the base handler, UNVERIFIED) | Credits | `openmenu credits` | `button6_highlight` |
| `button7_back` (16) | `debug_text` | Quit; the exe sets the text and handles accept | (exe: "Quit") | none | `button7_highlight` |

- XML1 order is kept. XML1 had no Quit; slot 7 (a hidden debug slot in XML1) becomes Quit.
- Fallback if 7 slots do not fit the layout: Quit takes slot 6 and Credits moves to Review > Cinematics > Credits
  (an XML2 convention; C.4.1 adds the entry anyway).
- `label_option04..08` are exactly the names the mouse handler and the Danger Room gate need. `label_option09`
  and `debug` / `debug_focus` are absent; the loops are NULL-safe (VERIFIED, 0x5c93e5 / 0x5cc496).

**Menu file** `UI/menus/main.{XMLB,engb}` (English in both, like every XML1 import; XML2's own `.XMLB` holds
`@UI_MENUS@...` keys, the `.engb` English). Shape:

```
<MENU name="main" igb="x1_menu_main" type="MAIN_MENU" fullscreen="false" gamepause="false" resetcontroller="true"
      updownonly="true" lighting="true" fadein="false" fadeout="false" desctext1="$MENU_ACCEPT Select">
  <item name="buttonN_highlight" type="MENU_ITEM_MODEL"/>                        N = 1..7
  <item name="button8_back|button8_highlight|button9_back|button9_highlight" type="MENU_ITEM_MODEL"
        enabled="false" hide="true"/>                                         hide the unused debug slots
  <item name="label_option04" startactive="true" text="Begin Story" style="STYLE_MENU_BLACK"
        textalignx="TEXT_ALIGN_CENTER_X" textaligny="TEXT_ALIGN_CENTER_Y" usecmd="newgame"
        up="debug_text" down="label_option05">
    <onfocus item="button1_highlight" type="focus"   model="ui/models/model_button_highlight"/>
    <onfocus item="button1_highlight" type="nofocus" model="ui/models/model_hide"/>
  </item>
  ... label_option05..08, label_credits, debug_text (same pattern, up/down chained, wrapping)
  <item name="desctext1" style="STYLE_DESC"/>
  <item name="version" style="STYLE_DESC" textalignx="TEXT_ALIGN_LEFT" gamevar="version"/>
</MENU>
```

- `fullscreen="false"` is required so the zone shows through. XML1's main set no `fullscreen`; XML2's sets false.
- `STYLE_MENU_BLACK` and `STYLE_DESC` exist in XML2 `Data/styles.XMLB` (VERIFIED).
- `ui/models/model_button`, `model_button_highlight` and `model_hide` ship in XML2 as PC builds (VERIFIED, same
  sizes as XML1's). Use XML2's copies.
- XML2's `image="textures/loading/0303"` (an XML2 loading screen) is dropped, or replaced with an XML1 screen.
  When the engine shows it is UNVERIFIED.

**Package** `Packages/generated/maps/package/menus/main.PKGB` (replaces XML2's, which names `x2m_main`, `m_*`
models and a dead `ui/menus/main_pc`):

```
model ui/menus/x1_menu_main
model ui/models/model_button
model ui/models/model_button_highlight
model ui/models/model_hide
xml   ui/menus/main
```

#### A.4.3 Intro (scripts.py, `Scripts/menus/intro_normal.py`)

```
startMovie("xi102", "afterMovie1")   waitsignal("afterMovie1")
startMovie("xi101", "afterMovie2")   waitsignal("afterMovie2")
startMovie("xi103", "afterMovie3")   waitsignal("afterMovie3")
startMovie("xi104", "afterMovie4")   waitsignal("afterMovie4")
startMovie("xi105", "afterMovie5")   waitsignal("afterMovie5")
mainMenuExit()
```

The names come from `media.movie_name` (pure provider). With `--no-movies` a missing movie signals at once
(HANDOFF, verified), so the script is safe either way. Keep XML2's Beenox logo (`i107`) after `xi103`? Open
question E.2.

#### A.4.4 Music (common.py / media.py)

- In `planned_sound_banks`, `sounds/eng/m/e/menu_a.zss` and `menu_c.zss` become kind `x1` music with the fixed
  bank `research/sound/music0x20/banks/eng/m/e/menu_{a,c}.zss`, instead of `merged`.
- XML2's bank holds only the one `music/menu_*` sound (VERIFIED, dumpbank), so nothing else is lost.
- media's rule "an `x1` bank never replaces an XML2 bank" needs a named allowlist: `FRONTEND_MUSIC = {menu_a,
  menu_c}`, with its reason.
- The XML2 credits menu also plays `music/menu_a` (0x5b1b84), so the credits get XML1's menu music too. XML1's
  credits used the same key (xbe string next to `data/credits.xml`).

#### A.4.5 Logo, strings and other XML2 branding

| XML2 branding | Where | Plan |
|---|---|---|
| 3D logo + "rise of apocalypse" | main menu `m_logo`, `title_text01` | gone with the XML1 menu (XML1's `3d_logo` node renders as part of `x1_menu_main`; UNVERIFIED that it animates) |
| main-menu loading image | zoneinfo `menu/main_back loading=textures/loading/main_menu` | XML1 `x_mansion` (A.4.1) |
| loading-screen emblem | `ui/models/m_loading_logo` (chrome "X", not title text) | keep (optional: XML1 `menu_loading` + `loading_anim`, but the menu type must stay `LOADING_MENU`) |
| legal screen | `legal_pc` (texture `textures/legal/legal_pc`, text names no title) | keep XML2's PC legal (XML1's texture says Xbox) |
| window title | "X-Men Legends 2" (0x5faf43) | xml2-fix: pass `[Game] WindowTitle` (for example "X-Men Legends") in the `hooked_create_window_ex_a` path when the class is `igWin32WindowClass` |
| `strings` id 3105 "X-Men Legends 2" | Data/strings | optional one-string patch; used by console save UIs only (UNVERIFIED on PC) |

#### A.4.6 Fallback A3: repoint the exe instead of renaming nodes (xml2-fix, later batch)

If the text on renamed back-nodes is misplaced, keep XML1's IGB untouched and its item names (`button1..7`), and
repoint only MAIN_MENU's name operands:

- mouse: 0x5c933f/4f/5f/6f/7f/8f, 0x5c939f/af/bf
- update: 0x5c9691, 0x5c96c2, 0x5c96f8, 0x5c95f4, 0x5c961d
- open: 0x5c9986, 0x5c9993, 0x5c99a1
- the pointers at 0x6e6628 / 0x6e662c

Point them at "button1".."button7". **Do not patch the strings themselves:** another menu class at 0x5cc3ee
shares `label_option01..09`.

**Status 2026-09-28: A3 is what the port builds** (SPEC 21.2). The renamed back-nodes of A.4.2 drew no text in game
(the text anchors are the `buttonN` nodes, the `buttonN_back` nodes are button meshes). The build now uses XML1's IGB
unchanged and XML1's item names, with every action in a `usecmd` (the Danger Room item runs the exe's own line
`set drmode 1;openmenu danger_room`, without the level-6 gate). xml2-fix `[Game] MainMenuItems` re-points only the
19 name pushes (the mouse array, the three e3 disables, the seven Quit references); the cells 0x6e6628 / 0x6e662c
stay, so the exe's Danger Room gate and Play Online never fire on renamed items. Quit has no console command or
script function (the exe writes the quit flag 0x6f3a2d itself), so Quit works only through the DLL.

#### A.4.7 Optional

XML1 fonts (`font_xmen_*`) would change every UI string. That is a separate decision; keep XML2's
`fonts_pc.xmlb` for M2.

#### A.4.8 Validator (new V15 "front end")

| Check | Severity |
|---|---|
| `--frontend xml1`: `Maps/menu/main_back.*` registered by zones; world has `zonescript` + `nosave`; `MotionPaths/menus/main_back.IGB` contains `mp_camera`; the zoneinfo entry exists; its loading texture exists | error |
| `UI/menus/main.{XMLB,engb}` decode; `type=MAIN_MENU`; the `igb` resolves; every item name except text-only items is a node name of that IGB (string scan) | error |
| exe contract: items `label_option04..08` and `debug_text` exist; `label_option06` has no `usecmd`; no `label_option09` | error |
| every `usecmd` first word is an XML2 console command (`xml2_console_cmds.txt`); every `openmenu X` target has `UI/menus/X.xmlb`; `runscript` code passes V7 | error |
| `up` / `down` targets exist; the focus chain is a cycle | warn |
| `x1_menu_main.IGB`: each renamed name present 3 times, each old name gone | error |
| `main.PKGB` entries resolve (V4 already covers this) | error |
| `Scripts/menus/intro_normal.py` passes V7; its `startMovie` targets resolve (V9); last statement `mainMenuExit()` | error |
| `menu_a` / `menu_c` = the fixed XML1 music bank (V2 / V8 allowlist) | error |

V6's current `FRONTEND_ZONES` rule inverts under `--frontend xml1`.

#### A.4.9 Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| text drawn on a back-node sits off-centre or is clipped | medium | alignment attributes; fallback: textless `label_*` focus proxies plus text items on the untouched `buttonN` nodes (`neverfocus`). Quit must stay on `debug_text`. Last resort: A3. |
| an XML1 Xbox UI IGB renders wrongly on PC | low (every converted zone, actor and HUD head is an Xbox IGB and renders) | in-game check |
| `igHashedUserInfo` hashes the ItemName **value** (a rename would break the bind) | low (the value is a plain igStringValue; x2m_main has the same layout) | in-game check; A3 |
| profile-based Danger Room entered from the menu at level >= 6 misbehaves | see B | B in-game checks |
| XML1 menu lighting / camera differ from XML2 menus | low | none needed |

#### A.4.10 In-game checks (main session)

1. Boot: legal screen, then the XML1 logos Activision, Marvel, Raven, VV, Sofdec, then the Cerebro backdrop with
   XML1 menu music and the XML1 logo and buttons.
2. Up/Down through all 7 items with keys and pad; mouse hover and click on each; Esc does nothing harmful.
3. Begin Story reaches nyc1_1_1 with Wolverine (unchanged). Load Game opens the save list.
4. Danger Room with a fresh profile shows the level-6 popup. Options opens PC options. Review opens (C).
   Credits rolls XML1's credits (C). Quit exits to the desktop.
5. Quit to main menu from a zone (pause menu): the backdrop and menu come back.

---------------------------------------------------------------------------------------------------------------

## B. Danger Room

### B.1 What XML1 has (`xml1_loose/data/dangerroom.eng`, 40,094 B; also in `xml1_assets/data`)

| Element | Count | Attributes (XML1) |
|---|---|---|
| ARENA | 15 (6 `trainingonly`) | title, zone (`arena/arena_*`), info, enttitle, destroyent / protectent / dangerent |
| GRADE | 6: Freshman, Sophomore, Junior, Senior, X-Man, Legend | name |
| COURSE | 62: 19 `startloaded`, 43 loaded by disk pickups | name, title, reclevel, arena, **reward** (points), **requirement** (points), startloaded, timelimit, timeduration, destroylimit, killlimit, paniclimit, protectlimit, combolimit, connectlimit, executelimit, combatnode, movename, **hero** (26), hint, intro, outro, **rewarditem** (19, the challenge items), rewardexam (QE100 / QE300 / QE400 / QE500; **not QE200**), destroylimittimerstart, dangerlimit, duration (CHEMM only) |
| SPAWNER / MUSTDIE / MUSTSURVIVE | 405 / 21 / 7 | character (74 distinct), count, killcount, delayMax / delaymax, destroycount, canhavemultiple, neutral |

- **Forced heroes (`hero=`):** magma x10 (all of Freshman), gambit / nightcrawler / rogue x2, and beast,
  colossus, cyclops, frost, iceman, jubilee, phoenix, psylocke, storm, wolverine x1 each.
- **Disk pickups:** 43 zone entities call `loadDangerRoomCourse('<name>')`, one course each. Examples: FR108
  `nyc1_1_5`, QE100 `icetunnel1`, CHCYC `jugrnt01`, LECHA `asteroid2_3`. The full list can be regenerated with
  grep. All 43 non-startloaded courses have a disk (VERIFIED).
- **In-mansion consoles:** `dangerRoomMenu()` in subbasement1a / 2 / 3b, `danger_room` (man3), 5 / 6 / 7 / 8.
- **XML1 menu:** `ui/menus/danger_room.eng` (`DANGER_ROOM_MENU`, models `model_dr_training / sparring /
  skirmish`). XML2 keeps the same three modes in its own UI.
- default.xbe reads `reward`, `requirement` and `rewardexam` (xbe 0xc8dc1, 0xc8dd0, 0xc8f73), not `duration`.
- **Arenas are already converted:** 15 `Maps/arena/arena_*` zones with zoneinfo entries and `player_startNN
  slot=5..8`, plus 2 duplicates under `arbiter/`. All 74 spawner characters and all 14 `hero=` names exist in the
  port's stats (VERIFIED against `build/_heroes/Data/{npcstat,herostat}.engb`).

### B.2 What the port does today

| Thing | State |
|---|---|
| `Data/dangerroom.{XMLB,engb}` | XML2's: 26 arenas (`dr/*`, `svs/*`, `act4/perimeter/perimeter5`), 7 grades, 54 courses. **Its spawners name 68 XML2 NPCs the characters module dropped** (build report defer), so XML2's courses cannot spawn their enemies (UNVERIFIED in game; likely empty or broken rooms). |
| XML1 disk pickups | converted as-is (`loadDangerRoomCourse('FR108')` in `nyc1_1_5`). 0x4a72e0 skips names the table lacks, so today they do nothing. |
| XML1 arenas | converted but unreachable (no course names them) |
| menus | XML2's `danger_room` UI (engine class `CMenuDangerRoom`) |

### B.3 XMen2.exe's dangerroom loader (VERIFIED, 0x4d4079..0x4d48cc)

| Element | Read by XMen2.exe | Limit |
|---|---|---|
| ARENA | platform, title, zone, info, trainingonly, onlineonly, maxHeros, maxVillains, dangerent, destroyent, protectent, enttitle | - |
| GRADE | name, level, unlocked | **<= 8 grades** (0x4d43a5) |
| COURSE | reclevel, title, name, bossname, arena (matched to an ARENA title), hero (roster.md 1.5, 0x4d460c), singleplayer, canthrow, boss_level_boost, boss_health_scale, boss_damage_scale, startloaded, rewardexam, and the limit attributes (timelimit, timeduration, killlimit, destroylimit, protectlimit, paniclimit, combolimit, connectlimit, executelimit, movename, combatnode..combatnode4, *timerstart, dangerlimit) | **<= 25 per grade** (0x4d4463). Total: records at 0x784e00, stride 0x78, counter at 0x78712c, so about **75** (derived from the BSS layout, UNVERIFIED). |
| REWARD | type (Titanium / Adamantium / Vibranium), requiredkills, requiredtime, requiredcombos, rewardcharacter, rewarditem, rewardxp, rewardtrait, itemSpawnType, rewardlevel, rewardtalent | XML2 gives every course exactly 3 |
| SPAWNER / MUSTDIE / MUSTSURVIVE | character, count, killcount, slot, neutral, canhavemultiple, delaymax, destroycount | - |
| **not read** | `requirement`, `reward` (as an attribute), `duration` | - |

- `loadDangerRoomCourse(s)` (0x4a72e0) splits on space, comma and tab, finds each course by name, and sets its
  loaded flag (+0x4f |= 1).
- Grade progression: XML2's 5 `rewardexam` courses are exactly its 5 grade transitions (QE100..QE500), so passing
  the exam of grade n most likely opens grade n+1. UNVERIFIED as code; strong data evidence.

### B.4 Conversion plan (frontend.py writes `Data/dangerroom.{XMLB,engb}`)

| XML1 | XML2 output | Rule / reason |
|---|---|---|
| root, ARENA (all attrs) | same | zone ids normalised with `C.norm`; every arena zone must have `Maps/<zone>.XMLB` |
| GRADE | same, plus `unlocked="true"` on Freshman | XML1 has no `unlocked`; without it nothing is available |
| COURSE shared attrs | same | all read by XMen2.exe |
| COURSE `requirement`, `reward` | dropped and reported (`count dr_points_dropped`) | XMen2.exe never reads them. Deviation: inside an open grade, the XML1 points gate is lost; `startloaded` and disks still gate. |
| COURSE `duration` (CHEMM) | dropped | XML1 ignored it too |
| QE200 | add `rewardexam="true"` | without it Junior never opens under XML2's exam rule (XML1 gated by points instead) |
| COURSE `rewarditem` (19 challenges) | `<REWARD type="Titanium" rewarditem="X"/>` | XML2 challenge pattern (for example CHCYC `ACCELERATED_VISOR`) |
| other courses | `<REWARD type="Titanium" rewardxp="N"/>`, N from XML2's reclevel -> XP curve (piecewise-linear over XML2's 34 Titanium `rewardxp` rows; for example rl1 200, rl8 2500, rl15 4500, rl21 6250, rl27 10000, rl38 25000) | XML1's XP came from kills (the FR101 outro says so); tuning question E.5 |
| Adamantium / Vibranium | optional second phase: `requiredtime` = 1/2 and 1/3 of `timelimit` / `timeduration`, or `requiredkills` for kill courses; `rewardtrait` cycling Strike / Speed / Body / Focus | XML1's extra credits (Efficiency / Demolitionist / Tactician / Untouchable) are XML1-exe logic with no data. Start with Titanium only; add these if the menu misbehaves with 1 reward (UNVERIFIED). |
| `hero=` | kept, plus `singleplayer="true"` | a forced solo hero; the semantics of `singleplayer` are UNVERIFIED |
| SPAWNER `delayMax` | `delaymax` | `encode_xmlb` lowercases it anyway |
| FR106 outro (XML1 extra-credit glyphs `{ | } ~` and `~11` colour codes) | trimmed to "Well Done!" | the extra credits do not exist in XML2; XML2 fonts may lack the glyphs (UNVERIFIED) |

**Reward items (zones.py).** The 19 `rewarditem` names (BANDS_OF_BEAST, CLAWS_OF_RAGE, MASK_OF_XORN,
SHIAR_*, ...) exist in XML1 `items.eng` as `type="equipment"` with `<require cat="character|level">` and
`<activepowerup>`. Today `translate_item` turns XML1 equipment into plain `item` (SPEC 11.3).

- Plan: a provider `frontend.dr_reward_items(ctx)` adds these names to zones' referenced-item set.
- New equipment translation for them: `class` gloves / belt / armor chosen per slot; `<require>` kept; each
  `<activepowerup powerup=P level=L [scope_node]>` becomes `<enhancement><powerup life="-1"><affecter .../>`
  using a small table: `strength|speed|body|mind` -> `attribute=<same> level=L`; `atk_damage_scale` ->
  `affect_type="scale" attribute="damage" level=L` (+ scope). Unknown powerups: reported, bonus dropped.
- UNVERIFIED mapping; the fallback is the Titanium `rewardxp` for those 19.

**Arena worlds (zones.py).** Add `nosave="true"` to `arena/*` worlds, as every XML2 DR arena has (VERIFIED on
`dr_sewers1`; UNVERIFIED whether XMen2.exe needs it).

**No UI change.** XML2's `UI/menus/danger_room.*` stays. It is the engine's class with modes 1..3 (drmode 0 in
story from `dangerRoomMenu()`, drmode 1 from the main menu).

**characters.py** drops its "XML2 Danger Room ... dropped NPCs" defer when `--frontend xml1` (the XML2 table is
gone).

#### B.5 Validator (new V16 "danger room")

| Check | Severity |
|---|---|
| decodes; grades <= 8; courses per grade <= 25; total courses <= 75 | error |
| every COURSE `arena` equals an ARENA `title`; every ARENA zone is a converted zone | error |
| every character (SPAWNER / MUST*) is in stats names; `hero` in herostat names | error |
| every course has a Titanium REWARD; every `rewarditem` is in `Data/items` with `type=equipment` (warn if downgraded to item) | error / warn |
| Freshman `unlocked`; grades 1..n-1 each contain a `rewardexam` course | error |
| every `loadDangerRoomCourse` literal in installed content (zone XMLB inline code, scripts) names a course | error |
| every non-startloaded course has at least one disk | warn |
| no `requirement` / `reward` / `duration` left | error |

#### B.6 Risks

| Risk | Mitigation |
|---|---|
| grade progression is not exam-driven | then set `unlocked="true"` on every grade (courses still need disks); in-game check 4 |
| course menu with a single REWARD tier misbehaves | add Adamantium / Vibranium (B.4) |
| main-menu DR (drmode 1) with a forced hero who is locked in the profile (Magma) | the check below; Magma unlocks at mansion1 in the story |
| XML1 arena spawn slots (5..8) vs XML2 `slot` semantics | XML1 SPAWNERs carry no `slot`; the exe then picks free starts (UNVERIFIED) |

#### B.7 In-game checks

1. In story (mansion1a subbasement console, `dangerRoomMenu()`): the menu lists Freshman with the 8 startloaded
   FR courses.
2. Run FR106 in `arena/arena_dr`: Magma alone; smash the crates; completion gives the Titanium XP.
3. Pick up the FR108 disk in `nyc1_1_5`, then the console lists "Teamwork 101".
4. QE100 passed opens Sophomore.
5. A challenge course (for example CHROG) awards its item (if B.4 equipment lands).
6. Main menu Danger Room with a profile of level 6 or more: Sparring / Skirmish use XML1's 9 non-training arenas.

---------------------------------------------------------------------------------------------------------------

## C. Review, codex, trivia, credits

### C.1 What XML1 has

| Table | File | Content |
|---|---|---|
| review_paths | `xml1_loose/data/review_paths.eng` (11,627 B; also `xml1_assets`) | 149 `<item type name value [group] [reward_*]>`: 34 `cin` (i101-i105, i107, r102-r505, int101-int109), 13 `comic` (`textures/comic/*_cov`, `group`=hero, `reward_{speed,mind,strength,body,focus}` 2-4), 38 `concept` (concept01-20, marvel_art01-18 `group="marvel"`), 64 `load` (`textures/loading/*`). No `act`, `unlocked` or `duration`. |
| codex | `xml1_loose/data/codex.eng` (22,700 B) | 26 `<character name description [anim] [scale]>`: 15 heroes (`anim="menu_idle"`), 11 villains with no anim (Magneto, MagnetoBoss, AvalancheScripted, BlobAct1a, ...). All 26 names exist in the port's stats (VERIFIED). `Magneto` resolves to the herostat placeholder (skin 0002 / `00_testguy`). |
| trivia | `xml1_loose/data/trivia.eng` (12,940 B) | 50 questions, 5 answers each, 1 `correct`; no `act` |
| credits | `xml1_loose/data/credits.eng` (24,477 B) | 513 `<line type text>` (header / nameheader / name) |
| textures | `xml1_assets/textures/comic` (13, 3.4 MB), `concept` (42 incl. concept21-24 unused, 11 MB), `loading` (67, 18 MB) | on the disc (VERIFIED) |
| menus | `ui/menus/review*.eng`, `review_{cinematics,comics,concept,loadscreens}.eng` (`pathstype=`), `codex*.eng`, `trivia.eng`, `credits.xml`, `credits_end.xml` (`endgame="true"`), `image_viewer.eng` | XML1 used one list menu per category; XML2 uses one tabbed menu |
| unlock sources | 12 comic and 20 concept pickups `imageViewer('textures/comic/X.png' | 'textures/concept/conceptNN')` in zones; in-mansion consoles `reviewComics / Concept / Cinematics / LoadScreens()`, `codexMenu(0|1)`, `triviaMenu()` (mansion1a, 2, 3, 4, 5, 6, 7, 8) | - |

**XML1 data quirks:**

- The Colossus pickup (`muir_in3`) calls `imageViewer('textures/comic/0901.png')`, but the review value is
  `col_cov` and no `comic/0901` texture exists.
- No zone unlocks `night_cov`.
- `r505` and `r309` are played only by default.xbe code: r505 after the end credits (xbe string beside
  `data/credits.xml` / `music/menu_a`), r309 from the xbe main-menu class (0x17e6fa).

### C.2 What the port does today

| Thing | State |
|---|---|
| `Data/review_paths`, `codex`, `trivia`, `credits` | XML2's (SPEC 4.4 "kept; deferred") |
| XML1 comic and concept pickups | unlock XML2 entries of the same path: `rogue_cov`, `storm_cov` and `concept01..20` become **XML2** art with XML2 rewards. The other 10 comics match nothing. |
| mansion consoles | open XML2's menus with XML2 data (XML2 codex characters and trivia) |
| XML1 textures | 61 loading screens installed for zoneinfo (numeric +14000). `acolytes`, `astral_king`, `mission_brief`, `sub_basement` are not installed. `x_jet` and `characters_menu` collide, so **XML2's image shows** for XML1 zones that use `x_jet` (3 zoneinfo entries). Comic and concept textures are not installed. |

### C.3 XMen2.exe's review system (VERIFIED)

| Fact | Address |
|---|---|
| categories `load`=0, `cin`=1, `comic`=2, `concept`=3, `stat`=4 | table 0x6d9414 |
| **<= 90 entries per category** (unlock bits: 3 dwords per category; also mirrored into the profile) | 0x4ae646 (`cmp ebp,0x5a`), 0x4adb47 |
| entry attrs: type, value, unlocked, act, count, platform, duration, skiptime, name, group, `reward_{strength,speed,body,mind}` (**no `focus`**) | 0x4ae310..0x4ae375, 0x4ae706, 0x4add15 |
| unlock match: value compared with the text before the first `.` stripped on both sides | 0x4ae530 |
| `imageViewer(p)`: if `p` contains "concept", unlock(3, p) + message 153; else if it contains "comic", unlock(2, p) + message 154. It no longer opens a viewer. | 0x49e440 |
| movie start unlocks `cin` by name | 0x5c9e92 (in 0x5c9df0) |
| loading screen unlocks `load` by its texture path | 0x5bb8d2 |
| `group="marvel"` concept entries are special-cased in the list and excluded from the unlock-all cheats; the same code exists in default.xbe (xbe 0x1807b3) | 0x5d08d5, 0x5d1328 |
| trivia: `act` read with default **1** and compared **equal** to the current act; per-act progress counter | 0x5e75b5..0x5e75db |
| codex: `characters/character name` (+ description, anim, scale); `codexMenu(i)` sets a filter | 0x5b0be0, 0x49e250 |
| credits menu (`CREDITS_MENU`, `endgame="true"` on `credits_end`) plays `music/menu_a` | 0x5b1b84 |

### C.4 Conversion plan (frontend.py; every table written as an `.XMLB` + `.engb` pair with English text)

#### C.4.1 review_paths

| XML1 entry | XML2 output |
|---|---|
| `cin` i101-i105, i107 | value = `media.movie_name` (`xi101`, ...), `unlocked="true"` (XML2 marks its own logos and promo unlocked), `duration` from the ADX header (below) |
| `cin` r*, int* | value kept, `duration` added; unlocks when played. r505 needs D.1; r309 is never played by XMen2.exe (open question E.6). |
| (new) | `<item type="cin" name="Credits" value="credits" unlocked="true"/>` (XML2 convention; Credits from Review) |
| `comic` | value `textures/comic/x1/<stem>` (namespace, C.4.2); `group` kept; `reward_focus` becomes `reward_mind` (XMen2.exe reads only strength / speed / body / mind); amounts kept (scaling: open question E.5) |
| `concept` | value `textures/concept/x1/<stem>`; `group="marvel"` kept (same code path as XML1) |
| `load` | value = `C.map_loading_texture(v)`, then the collision rename (C.4.2); must equal what zoneinfo shows |
| XML2 `stat` rows | none (XML1 has no collectible counts; the Stats tab is empty) |

Counts after conversion: cin 35, comic 13, concept 38, load 64. All are <= 90.

**Durations** in seconds (`probes/sfd_dur.py`; method checked against XML2's own values, cine01 149.72 vs listed
149.44, i106 52.28 vs 52.28):

| Movie | s | Movie | s | Movie | s | Movie | s | Movie | s |
|---|---|---|---|---|---|---|---|---|---|
| i101 | 13.00 | i102 | 10.40 | i103 | 17.63 | i104 | 4.00 | i105 | 4.00 |
| i107 | 71.00 | int101 | 24.02 | int102 | 22.16 | int103 | 12.23 | int104 | 12.63 |
| int105 | 10.37 | int106 | 12.03 | int107 | 12.20 | int108 | 10.77 | int109 | 10.37 |
| r102 | 94.26 | r103 | 13.15 | r104 | 56.29 | r105 | 15.53 | r106 | 106.73 |
| r201 | 56.37 | r202 | 81.17 | r203 | 51.63 | r204 | 70.83 | r206 | 83.00 |
| r301 | 81.13 | r302 | 12.21 | r305 | 21.69 | r306 | 13.35 | r309 | 24.06 |
| r501 | 110.91 | r503 | 49.53 | r504 | 53.47 | r505 | 81.13 | | |

Compute these in the pipeline: extend `media._adx_header` with `samples = int.from_bytes(head[12:16], 'big')`.

#### C.4.2 Texture imports and namespacing (frontend.py imports; the rewrites are shared providers)

| Set | Source | Output | Why |
|---|---|---|---|
| comics (13) | `xml1_assets/textures/comic/*.igb` | `Textures/comic/x1/<stem>.IGB` | `rogue_cov` and `storm_cov` collide with XML2; the whole set is namespaced for uniformity. The path still contains "comic" (imageViewer rule). |
| concept (38 referenced of 42) | `xml1_assets/textures/concept/*.igb` | `Textures/concept/x1/<stem>.IGB` | 27 collide (concept01-24, marvel_art04/12/17). The path contains "concept". |
| loading (3 that review needs and the build lacks) | `xml1_assets/textures/loading/acolytes.igb`, `x_jet.igb`, `characters_menu.igb` | `acolytes` keeps its name; the 2 colliding ones become `x1_x_jet`, `x1_characters_menu` | the collision fix also corrects the 3 XML1 zoneinfo entries that show XML2's `x_jet` today. `astral_king`, `mission_brief` and `sub_basement` are referenced by nothing (skip). |

Rewrites:

- `scripts.rewrite_data_tree` (zone XMLB inline code) and any installed script:
  - `imageViewer('textures/comic/X.png')` -> `imageViewer('textures/comic/x1/X')`
  - `imageViewer('textures/concept/Y')` -> `imageViewer('textures/concept/x1/Y')`
  - fix `0901` -> `col_cov` (the XML1 quirk, reported)
- Inline data code stays under 255 bytes (V7).
- zoneinfo `loading` for the 2 renamed names (zones).
- Put the mapping in `common.py` (`map_review_texture`, pure) so scripts, zones and frontend agree.

#### C.4.3 codex

- The XML1 26 entries, in XML1 order.
- `Magneto` becomes `MagnetoScripted` (npcstat, `charactername="Magneto"`, skin 16501, anim DB `x1_25_magneto`):
  the herostat `Magneto` is the DEFAULTMAN placeholder. UNVERIFIED which of name / charactername the list shows.
- `anim`: heroes keep `menu_idle` (present in XML1 hero anim DBs, VERIFIED for `x1_01_cyclops`); villains get
  `anim="idle"` (their anim DBs have `idle`, not `menu_idle`: VERIFIED for MagnetoBoss, Avalanche, Shadow King,
  ProfX).
- `scale` kept.
- No UI change.

#### C.4.4 trivia

- XML1's 50 questions, 5 answers each, `correct` kept.
- `act` is required (C.3), and trivia consoles exist in port acts 1, 3, 5, 6, 8, 9 (`zone_acts.json` of
  mansion1a_2, 2_2, 3_2, 4_2, 5_2, 7_2, 8_2).
- **Recommended:** split the 50 in XML1 order over those 6 acts (9 / 9 / 8 / 8 / 8 / 8).
- Alternative: every question in every act (repeats, and XP farming).
- Which one: open question E.4.
- 5 answers in XML2's `answers` LISTBOX (XML2 uses 4): UNVERIFIED layout, in-game check.

#### C.4.5 credits

- XML1's 513 lines (same schema; XML2 adds `texture` lines).
- Optional: append a short "PC port" block. Keep or drop XML2's PC-version credits? Open question E.7.
- `credits_end` stays XML2's menu (`endgame="true"`).

#### C.4.6 No UI changes

XML2's `review`, `codex`, `trivia`, `credits`, `image_viewer` and `movie` menus and packages stay. They are
engine classes; only their data changes.

#### C.5 Validator (new V17 "review / codex / trivia / credits")

| Check | Severity |
|---|---|
| review_paths: <= 90 per category; every `load` / `comic` / `concept` value resolves to an installed `Textures/<v>.IGB`; every `cin` value has a movie (warn with `--no-movies`) or is `credits` | error |
| every `imageViewer` literal in installed content, with the extension stripped, equals a comic or concept value and contains "comic" or "concept" | error |
| every loading texture a zoneinfo entry names equals a `load` value (else: a screen that can never unlock) | warn |
| no `reward_focus`; comic `group` names a herostat hero | error / warn |
| codex: name in stats; `anim` is present in that character's anim DB (IGB string scan) | error / warn |
| trivia: 2..5 answers and exactly 1 `correct` per question; every act with a trivia console has at least 1 question | error / warn |
| credits: line types in {header, nameheader, name, texture, pagebreak} | error |

#### C.6 Risks

| Risk | Mitigation |
|---|---|
| `duration` missing or wrong breaks review playback | computed per movie (C.4.1) |
| `marvel` concept art never unlocks (as in XML1: same code) | faithful; option: drop `group` so the cheat or a pickup can unlock them (E.6) |
| the XML2 review list groups by `act` (XML1 entries have none) | XML2 itself has 42 concept rows without `act` |
| trivia after the last question of an act | 0x5e7607 path (UNVERIFIED: repeat or stop) |

#### C.7 In-game checks

1. Main menu Review: tabs Screens / Cinematics / Comics / Concepts. The logos and Credits are unlocked; the
   Credits entry rolls XML1 credits with XML1 music.
2. New game, then pick up the Wolverine comic in `nyc1_1_4`: message 154; Review > Comics shows the XML1
   Wolverine cover.
3. Watch r102 (the opening), then Review > Cinematics lists it as unlocked.
4. Load `haarp_ext01`, pick up sketch book `art_haarpsoldierb`: message 153; Review > Concepts shows XML1
   "HAARP Soldier 2".
5. mansion1a_1 codex console: XML1 roster models idle (heroes `menu_idle`, villains `idle`).
6. mansion1a_2 trivia: XML1 questions, 5 answers, XP counter.
7. A zone whose zoneinfo uses `x_jet`: the XML1 X-Jet loading screen shows, then Review > Screens lists it.

---------------------------------------------------------------------------------------------------------------

## D. Found on the way (outside A-C, needs a decision)

| # | Finding | Evidence | Proposal |
|---|---|---|---|
| D.1 | **End of campaign loads an XML2 zone.** XML1's finale `mastermold/stage3death.py` plays R501, then `openmenu("credits_end")`. XML2's CREDITS_MENU in endgame mode then runs `saveloadProcess(2)` and `loadZone('act5/egypt/egypt6','')`. Egypt6 exists in the base install, with XML2 NPCs that were dropped. XML1 instead played r505 after the credits. | 0x5b1cbf / 0x5b1df4; `UI/menus/credits_end.XMLB endgame="true"`; xbe strings `r505` beside `data/credits.xml` | xml2-fix (later batch): repoint the push operand at 0x5b1cbf+1 to `"runscript x1/menus/postgame"`. The port writes `Scripts/x1/menus/postgame.py`: `startMovie("r505","s")`, `waitsignal("s")`, `mainMenuExit()`. That also unlocks r505 in Review. |
| D.2 | XML2's Danger Room is broken in the port today (68 dropped spawner NPCs) | characters defer in `build/_heroes/_build/report.json` | B fixes it |
| D.3 | XML1's main-menu idle promo (i107) | xbe 0x17e8c7..0x17e933 (`MAP/showMovies`); XMen2.exe MAIN_MENU keeps the idle timer (0x5c9754) but no attract call was found | optional xml2-fix feature; low priority |
| D.4 | XML1 `x_jet` loading screen shows XML2's image in 3 XML1 zones | C.2 | C.4.2 |

---------------------------------------------------------------------------------------------------------------

## E. Open questions for Owen

1. Main menu: 7 buttons (XML1's 6 plus Quit in the hidden 7th slot), or 6 buttons (Quit replaces Credits;
   Credits in Review)? Default: 7.
2. Intro: pure XML1 (Activision, Marvel, Raven, VV, Sofdec), or also keep XML2's Beenox logo, since the port runs
   on Beenox's PC engine? Default: pure XML1.
3. Main-menu loading screen (`menu/main_back` zoneinfo): XML1 `x_mansion` (Xavier Institute), or another XML1
   screen? Same question for the MAIN_MENU `image`.
4. Trivia: split XML1's 50 questions across the 6 mansion acts (default), or repeat all 50 in each act?
5. Tuning: Danger Room Titanium XP by XML2's reclevel curve; comic stat rewards as XML1 (+2..4) or scaled x4 like
   the hero stats (heroes.py STAT_SCALE)?
6. Unobtainable-in-XML1 items: the Nightcrawler comic, the `marvel` concept group and r309 "Death". Leave them
   faithful (locked), or mark them `unlocked="true"`?
7. Credits: XML1's only, or XML1's plus a short port / XML2-PC block?

---------------------------------------------------------------------------------------------------------------

## F. Implementation order and pipeline wiring

| Step | Change | Files |
|---|---|---|
| 1 | `--frontend xml1|xml2` switch; `C.MODULE_ORDER += ('frontend',)` after media; `plan_content_opts` rerun rule | `build_xml1.py`, `common.py` |
| 2 | backdrop zone + zoneinfo loading + arena `nosave` + loading collisions + DR reward items as references + equipment translation | `zones.py` |
| 3 | intro script, `main_back_main` install, `imageViewer` literal rewrite | `scripts.py` (+ selftest) |
| 4 | menu music allowlist; ADX samples / duration provider | `common.py` (`planned_sound_banks`), `media.py` |
| 5 | `UI/menus/main` + `x1_menu_main.IGB` (renames) + `main.PKGB`; `Data/{dangerroom,review_paths,codex,trivia,credits}` pairs; textures comic / concept / loading | new `frontend.py`, `frontend_selftest.py` |
| 6 | V15 / V16 / V17; flip V6's frontend rule | `validate.py` (+ selftest) |
| 7 | SPEC section 20 (this design as built), HANDOFF | docs |

Each step can be built with `--only` and checked offline. In-game: A.4.10, then B.7, then C.7. D.1 needs an
xml2-fix change.

---------------------------------------------------------------------------------------------------------------

## G. Dialogs over XML1's main menu: the menu camera (2026-09-28, after the M2 build)

Symptom (in game, build/_heroes): Begin Story ran `newgame` (0x5f3610: `resetgame`, then `startgamedialog`), the
difficulty prompt was active (Enter accepted Normal) but not drawn; the mouse could not leave it. `--frontend xml2`
builds showed it. Read from XMen2.exe (VERIFIED at the addresses; Ghidra decompiles of the functions named):

| What | Where | Consequence |
|---|---|---|
| `startgamedialog` builds the prompt in the dialog manager (singleton 0x8b13ec, vtable 0x6a332c): title 0x866, options 0x867..0x869 (`setDifficultyLevel(%d)`, the last only if the profile unlocked Hard), default = the game's difficulty, then vt+0x68 (show) | 0x5f2090 | every popup (the save / load lists: 161 calls to 0x5eb300 in 0x4b0000..0x4b6000) goes through the same manager |
| dialog init: models `ui/hud/dialog`, two `ui/models/m_review_list_arrow`, `ui/hud/dialog_select`, the box placed at (0, -700, 0); a text object | 0x5e95a0 | the box lies at y -700 (its geometry spans x 75..438, z 56..322: the 512 x 384 menu frame); its models carry igLightingStateAttr (unlit) |
| dialog text object: node at (0, -800, 0), text rectangle 87, 287, 340 x 240 in virtual-screen units | 0x5f1370, 0x5e927a | |
| show (vt+0x68): when a menu is open (menu manager vt+0x204) the box, arrows, selection bar and text are attached to menu layer 0 (menu manager vt+0x108 -> layer vt+0x2c), else to the HUD | 0x5ea1b0 -> 0x5e91c0 / 0x5e90d0 | over the main menu the dialog is drawn in the main menu's layer |
| menu manager: 2 layers (0x8605c), layer 0 type 0, draw order 200, orthographic (vt+0x4c(1)); layer 1 type 1, order 150, lit; the text system (manager+0xe0, 4 groups) attached to layer 0 at y -800, another at -850 | 0x5d9160 (0x5d9218..0x5d92b6) | |
| the open menus' IGBs (a name-ordered tree of 2) go to the layers in name order; each layer selects the IGB's camera when it brought one (vt+0x38(1)) | 0x5d7740, 0x5d7ba0, 0x5d73f0 | a menu's IGB camera is the camera of layer 0 |
| a menu's `lighting` / `perspective_camera` go to layer 0 on open; an `<items igb=...>` child's to layer 1 | 0x5d9fb0 / 0x5d9fd0; 0x5abc10 | |
| layer camera: view = the camera's graph path transform; orthographic (flag +0xcc = 1): width / height = the virtual screen, centred on the camera, near / far = the camera's (+0x30 / +0x34); perspective otherwise (fov +0x2c) | 0x583570 -> 0x56c9d0 / 0x56c960 | the menu shows world x / z around the camera; anything outside [camera y + near, camera y + far] is clipped |
| mouse: window pixels -> virtual screen (width, height; y up) with no camera; MAIN_MENU hit-tests item rectangles built from node positions + bounds (world x / z) | 0x5f9eb0, 0x5c9320, 0x5bc530 | the mouse matches the picture only with the camera at the virtual screen's centre (256, 192) |

Cameras: every x2m_* menu IGB XML2 uses has its camera transform at (256, -1000, 192), fov 25, near 100 (far
1000..1300): overlays at y -700..-850 are 150..300 in front of it. XML1's `menu_main.igb` has `Camera01` at (254,
-1108.19, 141), fov 25, near 897, far 1263 (XML2's unused `menu_*` leftovers - menu_options, menu_shop, loading, ... -
have (256, -1108.19, 192 / 182) with the same 897 / 1263: XML1's convention). So over XML1's menu the dialog box,
its text and the menu help line (0x5d62e0, the text system at -800) are all in front of the near plane (the port's
main menu screenshots show no "Select" help line: the same clipping), and the drawn menu is 51 units (z) / 2 units (x) off the mouse's frame. XML1 itself never asked for a
difficulty: default.xbe has no difficulty string; its `newgame` (xbe 0x18d0b0) is `resetgame` + `beginmission alison`.

Fix (SPEC 21.2.1): the pipeline moves XML1's menu scene rigidly so `Camera01` sits at (256, -1000, 192) and sets its
near plane to 100 (`frontend.reframe_menu_igb`; `xml1build/igb_file.py` reads the IGB layout for the in-place edit).
Menu item text is not affected: a text item draws into its own text object in its node's local frame (0x5c61d0 ->
0x5eecf0 with the item's bounds, not its world rectangle), so it sits at the node's depth (button text y 2.68) and
moves with the node. Rejected: only lowering the near plane (the dialog would be drawn 51 units high, off its mouse
rows); an `<items>` back IGB for XML1's scene in layer 1 (the dialog would show, but the XML1 camera would stay off
the mouse frame, and MAIN_MENU items bound to a second layer's IGB are untested paths); an xml2-fix hook (a data fix
exists).

Follow-up (2026-09-28, SPEC 21.2.2): the prompt is gone from the XML1 front end. Begin Story's usecmd is
`resetgame;runscript setDifficultyLevel(1)` - `newgame` (0x5f3610 = `resetgame` 0x5f2e70 + `startgamedialog`) with the
prompt replaced by what its Normal option (text 0x868) runs. `setDifficultyLevel` (0x4a0930) writes the difficulty
(0x729960 vt+0x26c -> `[+0x60c]` = 0x729f6c) and queues `runscript startFirstMission()` (0x4a0ab1) unless the profile
has Hard unlocked (0x72c530 vt+0xb0: `[+0x229]` bit 2, set by the end credits after a Normal win, 0x5b1d44), in which
case it offers XML2's New Game+ statistics choice (0x86a); xml2-fix `[Game] NewGamePlus=0` (723e592) jumps past that
offer (je 0x4a099e -> nop + jmp 0x4a0a9c). The save / load texts with XML2's name: SPEC 21.2.3.
