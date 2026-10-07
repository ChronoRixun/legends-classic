"""xml1build.frontend - XML1's front end, Danger Room and Review data on XMen2.exe (SPEC.md section 21;
research/frontend/M2_DESIGN.md sections A, B, C).

Runs after media (common.MODULE_ORDER). With --frontend xml2 it writes only D and E (XML2's front end exactly as
before SPEC 21). With --frontend xml1 (the default) it writes A-E:

  A. Main menu (M2_DESIGN A.4.6, fallback A3; the renamed back-nodes of the first cut drew no text):
     * UI/menus/x1_menu_main.IGB = XML1's ui/menus/menu_main.igb (the 3D logo, XML1's button layout and lights;
       nodes buttonN = the text anchors, buttonN_back = the button meshes, buttonN_highlight = the focus models)
       re-framed on XML2's menu camera (reframe_menu_igb, SPEC 21.2): the whole scene moved rigidly so its camera
       sits where every XML2 menu camera sits, with XML2's near plane. Same picture; XMen2.exe's own overlays in the
       menu layer (every dialog - the New Game difficulty prompt, the save / load lists - and the help line) are
       drawn instead of clipped, and the mouse frame matches the drawn buttons. XML2 ships an unrelated
       UI/menus/menu_main.IGB (a 27 KB prototype nothing uses), hence the x1_ name: the port never overwrites that
       base file, and the menu file and package name the IGB.
     * UI/menus/main.{XMLB,engb}: XML1's main.eng in XML2's schema (English text in both, like every XML1 import):
       text on button1..7 in XML1's order Begin Story, Load Game, Danger Room, Options, Review, Credits + Quit
       (button7, XML1's hidden debug slot); buttonN_back disabled MENU_ITEM_MODELs; focus highlight via <onfocus>
       (XMen2.exe does not read XML1's focusitemname/focusmodel); up/down one cycle; every button's action in its
       usecmd, so keys and pad work without an exe change (Danger Room: XMen2.exe's own line for its item,
       "set drmode 1;openmenu danger_room", 0x68d184); fullscreen="false" so the zone shows. Begin Story runs
       BEGIN_STORY_CMD, XMen2.exe's newgame without its difficulty prompt (XML1 had none): resetgame, then what the
       prompt's Normal option runs (SPEC 21.2.2).
     * The PC's save / load messages (igct*.bnx in the game folder, SPEC 21.2.3) and Data/strings' English texts with
       the port's name "X-Men Legends" instead of XML2's (igct_retext, strings_retext).
     * Play Online (SPEC 21.2.4) on button7 (usecmd "openmenu online": XML2's online screens; the item's accept
       first also avoids the fresh-boot crash of a console openmenu online), Quit on button8; the 8 buttons are
       spread over XML1's button1..7 span (space_menu_buttons), which is all XML1's layout has on screen.
     * XMen2.exe's MAIN_MENU looks its mouse items and its Quit item up by XML2's names (0x5c933f..0x5c93bf,
       0x5c9691..0x5c99a1): xml2-fix [Game] MainMenuItems (MAIN_MENU_ITEMS, written by tools/harness.py) points
       those name operands at button1..6 + button8, so the mouse hovers / clicks those and button8 quits (no console
       command or script function quits; the exe sets its quit flag 0x6f3a2d itself). Play Online is keys / pad
       only: the exe's mouse clamps slots after the sixth to Quit (MAIN_MENU_ITEMS_MOUSE_ALL: the value for an
       xml2-fix that lifts the clamp).
     * Packages/generated/maps/package/menus/main.PKGB: the IGB, XML2's PC copies of model_button /
       model_button_highlight / model_hide, and the menu file.
     (The backdrop zone menu/main_back is converted by zones, the intro script is written by scripts, the menu
     music is installed by media: SPEC 21.)
  B. Data/dangerroom.{XMLB,engb}: XML1's 15 arenas / 6 grades / 62 courses in XMen2.exe's schema (loader
     0x4d4079..0x4d48cc): Freshman unlocked="true"; QE200 gets rewardexam (XMen2.exe opens grade n+1 by the exam
     of grade n; XML1 gated Junior by points); requirement / reward / duration dropped (never read); hero= kept +
     singleplayer; one Titanium REWARD per course: the XML1 rewarditem, else rewardxp by the build's XP curve
     (course_reward_xp, SPEC 23.1): 0 with --xp-curve xml1 (XML1 gave no completion XP: default.xbe 0xc53f2 adds
     the course's reward to the Danger Room points only), XML2's reclevel curve (xp_curve) with xml2; XML1's
     extra-credit outro glyphs trimmed. The 19 reward items are added to Data/items by zones as
     XML2 equipment (translate_equipment, zones.items_to_add).
  C. Data/review_paths / codex / trivia / credits (each .XMLB + .engb, English):
     * review_paths: XML1's 149 entries, cin values through media.movie_name with ADX durations
       (media.movie_duration), logos + promo unlocked, a Credits entry; comic / concept values in their x1/
       namespace (common.map_review_texture; the imageViewer literals follow, scripts.rewrite_data_tree), comic
       reward_focus -> reward_mind (XMen2.exe reads strength/speed/body/mind only) and amounts scaled like the hero
       stats (heroes.STAT_SCALE; speed by the heroes speed slope); load values = what zoneinfo shows.
       Textures/comic/x1/*, Textures/concept/x1/* and the loading screens Review needs are imported.
     * codex: XML1's 26 entries in order; Magneto -> MagnetoScripted (the herostat Magneto is the placeholder);
       anim = the XML1 anim if the character's anim DB has it, else menu_idle, else idle.
     * trivia: XML1's 50 questions split in order over the acts that have a trivia console (XMen2.exe shows
       only the current act's questions, act default 1, 0x5e75b5); renderer codes escaped like the credits'.
     * credits: XML1's 513 lines + a short port block (PORT_CREDITS), every '#' / '$' / '~' / '|' written '|c'
       (XMen2.exe's text renderer reads '#NNN' as pen x = NNN: "NYC Acolyte #1, Shadow" drew over itself).
     * UI/menus/credits + credits_end (+ packages): XML2's CREDITS_MENUs over XML1's own IGBs (x1_menu_credits: the
       credits page; x1_menu_credits_end: black), re-framed on XML2's menu camera, with image="" (no background
       sprite: XML2's hero collage, or whatever image the last menu set, would cover them).
     * UI/menus/review.{XMLB,engb}: XML2's REVIEW_PATHS_MENU without the Stats tab (option05_text, option05_focus;
       XML1's Review had no Stats, and XML2's lists its acts 1-5 from exe code); xml2-fix [Game] ReviewStats=0
       (REVIEW_STATS_KEY, written by tools/harness.py) makes the tab change wrap at 4 (SPEC 21.4.3).
     * UI/menus/codex.{XMLB,engb}: XML2's CODEX_MENU without its list's icon cells (CODEX_ICON_ATTRS on the
       MENU_ITEM_LISTCODEX item and the CODEX_ICON_PRECACHE texture; issue #48). XML1's codex list was text only;
       XML2's draws cell `textureicon` of mini_convo_icons per entry, and XML1's NPCs have no textureicon, so every
       NPC entry drew cell 0 (Cyclops). Without `icons` the list draws no cell (0x5c269e reads it only when present).

  D. Data/personal/<item>.{XMLB,engb} + Textures/personal/*.IGB (both front ends: in-zone data, issue #47): the
     first game's 36 bedroom items (personalItem('<hero>NN') in the mansion *_2 zones; XMen2.exe's personalItem
     0x49e570 opens the PERSONAL_MENU, whose loader 0x5cedd0 reads data/personal/<item>). XML2 shipped only one
     leftover (wolverine01, naming a texture it never shipped: the engine's default texture was drawn) and no
     Textures/personal, so every other item showed the last image the menu manager had set - the mansion's loading
     screen. The ITEM schema is the same in both games (texture + text); the text is written with
     escape_menu_text, the texture is XML1's IGB under the same name. UI/menus/personal and menu_personal.IGB stay
     XML2's (the same PERSONAL_MENU as XML1's). Known gap (SPEC 56): XMen2.exe draws the item's
     picture but not its text box - the text is loaded and word-wrapped in memory.

  E. UI/menus/pda.{XMLB,engb} (both front ends: the pause menu in every zone, issue #89, SPEC 64): XML2's PDA_MENU
     without the Blink Portal entry (PDA_PORTAL_LABEL removed, its PDA_PORTAL_MODELS hidden, the up / down chain
     re-linked past it). The first game had no portal; XML2's opens one to X-Men Legends II's towns.

Providers (pure, usable before / without run): dr_reward_items(ctx), translate_equipment(ctx, item),
xp_curve(ctx), trivia_acts(ctx), review_entries(ctx), review_menu_trees(ctx), menu_plan(), igb_string_fields(data),
reframe_menu_igb(data), menu_igb_camera(data), and the table builders.
Everything is written through ctx; nothing outside <out> is touched.
"""
from __future__ import annotations

import collections
import re
import xml.etree.ElementTree as ET

from . import common as C

MODULE = 'frontend'

# ================================================================================================ A. main menu
X1_MAIN_MENU = 'ui/menus/main.eng'
X1_MENU_IGB = 'ui/menus/menu_main.igb'
MENU_IGB_NAME = 'x1_menu_main'                       # UI/menus/menu_main.IGB is XML2's own (27 KB prototype)
MENU_IGB_REL = f'UI/menus/{MENU_IGB_NAME}.IGB'
MENU_REL = 'UI/menus/main'
MENU_PKG_DIR = 'Packages/generated/maps/package/menus'
MENU_PKG_REL = f'{MENU_PKG_DIR}/main'
# Begin Story (SPEC 21.2.2): XML1 asked for no difficulty (default.xbe has no difficulty text; its newgame, xbe
# 0x18d0b0, is resetgame + beginmission alison). XMen2.exe's newgame (0x5f3610) is resetgame (0x5f2e70), then
# startgamedialog (0x5f2090): the Easy / Normal / Hard prompt (texts 0x866..0x869), whose Normal option (0x868) runs
# the script setDifficultyLevel(1). Begin Story runs those steps itself: resetgame, then what Normal runs.
# setDifficultyLevel (0x4a0930, script table 0x68b7a8) writes the difficulty through the game object's setter
# (0x729960 vt+0x26c 0x469d40 -> [0x729960+0x60c] = 0x729f6c; 0 Easy, 1 Normal, 2 Hard) and then, unless the profile
# has Hard unlocked (0x72c530 vt+0xb0 0x48f730: [+0x229] bit 2, which the end credits set after a win on Normal,
# 0x5b1d44), queues "runscript startFirstMission()" (0x4a0ab1): the starting team, then Scripts/menus/new_game.py
# (difficulty < 2, 0x4a7c42). With Hard unlocked it shows XML2's New Game+ choice instead (0x86a, "use default / saved
# statistics"; XML1 had none): xml2-fix [Game] NewGamePlus=0 (tools/harness.py writes it for this menu) skips it.
BEGIN_STORY_CMD = 'resetgame;runscript setDifficultyLevel(1)'
# console commands that open the difficulty prompt: none of the XML1 main menu's items may run them
NEW_GAME_PROMPT_CMDS = ('newgame', 'startgamedialog')
# Play Online (SPEC 21.2.4): what XMen2.exe itself runs for XML2's item (menu manager vt+0x6c("online"), 0x5c9857)
PLAY_ONLINE_CMD = 'openmenu online'
# XML1's buttons as XML1's main.eng binds them: text on the text node buttonN, buttonN_back the button mesh (a
# disabled model), buttonN_highlight the focus model. (N, text (None: XML1 main.eng's buttonN text), usecmd)
MENU_BUTTONS = (
    (1, None, BEGIN_STORY_CMD),                                  # XML1: newgame (no difficulty prompt in XML1)
    (2, None, 'runscript saveloadProcess(3)'),
    # XMen2.exe's own line for its Danger Room item (0x68d184, pushed at 0x5c98fb; drmode 1 = the profile mode of
    # the main menu). Its story-level-6 gate (0x5c98e3) is not reproduced: XML1's main menu had none either.
    (3, None, 'set drmode 1;openmenu danger_room'),
    (4, None, 'options_main'),                                   # XML2's PC options (XML1: openmenu options)
    (5, None, 'set reviewmode -1;openmenu review'),              # XML2's review menu
    (6, None, 'openmenu credits'),
    # Play Online (SPEC 21.2.4; research/online/port_online_test.md): XML2's online screens are in the build, but
    # XMen2.exe opens them from MAIN_MENU only for an item named label_option09 (0x5c9803 -> 0x5c9857), a name XML1's
    # menu must not use (EXE_MENU_FORBIDDEN). `openmenu online` by console on a fresh boot crashes at Host / Join
    # (igControllerManager::getController from 0x5517db); after the accept of a main-menu item it works: so a real
    # item, whose accept runs first, both reaches the screens and avoids the crash. Last before Quit, as in XML2.
    (7, 'Play Online', PLAY_ONLINE_CMD),
    # Quit: no console command or script function quits; with xml2-fix MainMenuItems the exe's own Quit handles it
    # (text "Quit" 0x5c9986, quit flag 0x6f3a2d on accept 0x5c96dd, its usecmd replaced by the dummy "Bidon" 0x5c99d5)
    (8, 'Quit', None),
)
MENU_NODES = 9                                       # XML1's IGB has button1..9 (7..9: XML1's debug slots)
# XML1's layout has room for 7 buttons on screen: button1..7 (its button8 / button9 debug slots sit at / below the
# bottom edge of the view). The port's 8 buttons are spread evenly over the span of XML1's button1..button7
# (space_menu_buttons): top and bottom stay XML1's, the spacing is 6/7 of XML1's (SPEC 21.2.4).
MENU_SPAN = (1, 7)
MENU_TEXT_STYLE = 'STYLE_MENU_BLACK'                 # XML1's (xbe style table 0x458d80: colours 9 / focus 10 /
#                                                      disabled 5, font big); XMen2.exe's has the same indices and
#                                                      font (dim white -> white on focus; XML1's colours were blue)
MENU_TEXT_ALIGN = {'textalignx': 'TEXT_ALIGN_CENTER_X', 'textaligny': 'TEXT_ALIGN_CENTER_Y'}   # both exes' default
MENU_FOCUS_MODEL = 'ui/models/model_button_highlight'
MENU_NOFOCUS_MODEL = 'ui/models/model_hide'
MENU_MODELS = ('ui/models/model_button', 'ui/models/model_button_highlight', 'ui/models/model_hide')
MENU_IMAGE = C.FRONTEND_MENU_LOADING                 # MAIN_MENU image (XML2: an XML2 loading screen; E.3)
# xml2-fix [Game] MainMenuItems (tools/harness.py writes it): our items for XMen2.exe's MAIN_MENU name slots, in the
# DLL's order label_option04, 05, 06, 07, 08, 09 (the mouse handler's hit-test slots 0..5, 0x5c933f..0x5c938f),
# debug_text (slot 6 and the Quit role). The Danger Room gate and Play Online compare the focused item's name with
# label_option06 / label_option09 through the cells 0x6e6628 / 0x6e662c, which the DLL leaves alone.
# XMen2.exe's mouse has 6 item slots + Quit: the first 6 buttons with an action get them, Quit (the button without
# one) the Quit slot; Play Online (MAIN_MENU_KEYS_ONLY) is reached by keys / pad only. The hit-test does look up two
# more names (slots 7 / 8, `debug` / `debug_focus`, 0x5c93af / 0x5c93bf), but it clamps every slot >= 6 to 6
# (0x5c944b cmp edi,6 / mov ebx,6: Quit's models), so an item named for slot 7 would focus - and accept - Quit.
# MAIN_MENU_ITEMS_MOUSE_ALL is the value for an xml2-fix that lifts that clamp for slot 7 (0x5c944d imm8 6 -> 8:
# slot 7 then focuses its own item, slot 8 stays Quit's focus model); never write it for a DLL without that change.
MAIN_MENU_MOUSE_SLOTS = 6
MAIN_MENU_ITEMS = tuple(f'button{b[0]}' for b in MENU_BUTTONS if b[2])[:MAIN_MENU_MOUSE_SLOTS] + \
    tuple(f'button{b[0]}' for b in MENU_BUTTONS if not b[2])
MAIN_MENU_QUIT_SLOT = 6
MAIN_MENU_KEYS_ONLY = tuple(f'button{b[0]}' for b in MENU_BUTTONS if b[2])[MAIN_MENU_MOUSE_SLOTS:]
MAIN_MENU_ITEMS_MOUSE_ALL = MAIN_MENU_ITEMS + MAIN_MENU_KEYS_ONLY
MAIN_MENU_CLAMP_VA = 0x5c944d                        # the imm8 of `cmp edi, 6` (retail bytes 83 ff 06)
# names XMen2.exe's MAIN_MENU acts on by itself, whatever the usecmd (so no item may have them): label_option06 ->
# the level-6 gate + "set drmode 1;openmenu danger_room" (0x5c988e), label_option09 -> openmenu online (0x5c9803)
EXE_MENU_FORBIDDEN = ('label_option06', 'label_option09')


def menu_plan():
    """[(item, text-or-None, usecmd-or-None)] (MENU_BUTTONS with the item names; pure)."""
    return [(f'button{i}', text, cmd) for i, text, cmd in MENU_BUTTONS]


def menu_node_names():
    """every IGB node the menu file names: buttonN_back / buttonN_highlight / buttonN (N = 1..MENU_NODES),
    desctext1, version."""
    out = []
    for suffix in ('_back', '_highlight', ''):
        out += [f'button{i}{suffix}' for i in range(1, MENU_NODES + 1)]
    return out + ['desctext1', 'version']


def igb_string_fields(data):
    """Counter {value: occurrences} of the IGB's length-prefixed string fields (u32 padded_len, then the text,
    NUL-terminated and zero padded to 4; research/frontend/probes/igbnames.py's rule)."""
    import struct
    seen = collections.Counter()
    for m in re.finditer(rb'[A-Za-z0-9_\-. \\/:]{2,}\x00', data):
        s = m.start()
        if s < 4:
            continue
        (plen,) = struct.unpack_from('<I', data, s - 4)
        body = m.group(0)[:-1]
        if plen % 4 or not len(body) + 1 <= plen <= len(body) + 4:
            continue
        seen[body.decode()] += 1
    return seen


# ---- the menu IGB's camera (SPEC 21.2; research/frontend/M2_DESIGN.md section G)
# XMen2.exe draws a menu's IGB in menu layer 0 (the IGBs of the open menus go to the layers in name order, 0x5d7740)
# through the IGB's own camera (0x5d7740: vt+0x38(1) once the IGB brought one): an orthographic view the size of the
# virtual screen centred on that camera (0x583570 -> 0x56c9d0; perspective_camera="true" is the other branch),
# clipped by the camera's near / far planes (igCamera +0x30 / +0x34). XMen2.exe's own overlays share that layer at
# fixed depths: the dialog box of every popup (the New Game difficulty prompt 0x5f2090, the save / load lists,
# 0x5eb300's dialogs) at y -700 (0x5e95a0; 0x5e91c0 attaches it to layer 0 while a menu is open), the text system
# (dialog text 0x5f1370, the menu help line) at y -800 (0x5d92aa) and -850 (0x5d9299). The mouse maps the window
# onto the virtual screen 1:1 (0x5f9eb0) and hit-tests item rectangles made of node positions (0x5bc530), so the
# drawn menu matches the mouse only with the camera at the virtual screen's centre. Every x2m_* menu IGB XML2 uses
# has the camera below. XML1's menu_main.igb has Camera01 at (254, -1108.19, 141), near 897, far 1263 (XML1's
# convention; XML2's unused menu_* leftovers have it too): the overlays lie in front of its near plane (the dialog
# is active but not drawn) and the view sits 51 units off the mouse frame.
MENU_CAMERA_POS = (256.0, -1000.0, 192.0)       # x2m_main.IGB, the transform of its igCamera 'Camera'
MENU_CAMERA_NEAR = 100.0                        # x2m_main.IGB igCamera near plane (far 1100)
MENU_CAMERA_ROWS = ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0))    # both cameras: looking +y, z up
MENU_OVERLAY_DEPTHS = (-700.0, -800.0, -850.0)  # the dialog box, the text system (see above)
MENU_SCREEN = (512.0, 384.0)                    # the virtual screen the camera's view covers (x, z around it)
MENU_EDGE = 16.0                                # a shown button's nodes stay this far inside it (half a focus bar)
MENU_MIN_SPACING = 20.0                         # shown buttons at least this far apart (XML1: 32.6, the port: 27.9)
XML2_MENU_CAMERA_IGB = 'ui/menus/x2m_main'      # frontend_selftest reads the constants back from XML2's file
# the node types the re-frame knows how to move in world coordinates (any other type there is refused; under a
# transform everything is local and moves with it)
_FRAME_NODE_TYPES = frozenset(('igGroup', 'igTransform', 'igGeometry', 'igAttrSet', 'igLightStateSet', 'igLightSet',
                               'igCamera', 'igUserInfo', 'igHashedUserInfo'))


def _rows(m):
    return tuple(tuple(m[4 * r + c] for c in range(3)) for r in range(3))


def menu_igb_camera(data):
    """the camera of a menu IGB: {'pos', 'rows', 'fov', 'near', 'far', 'name'} or {'problem': text}."""
    from . import igb_file as G
    try:
        g = G.IgbFile(data)
    except G.IgbError as ex:
        return {'problem': f'not an IGB this reader can place: {ex}'}
    frame = _scene_frame(g)
    if frame['problems']:
        return {'problem': '; '.join(frame['problems'][:3])}
    cam, tf = frame['camera'], frame['camera_transform']
    m = tf.get(8)

    def scalar(slot):
        v = cam.get(slot)
        return v[0] if isinstance(v, list) and len(v) == 1 else None
    return {'pos': tuple(m[12:15]), 'rows': _rows(m), 'fov': scalar(8), 'near': scalar(9), 'far': scalar(10),
            'name': cam.get(2)}


def _scene_frame(g):
    """walk the IGB's scene graph from its igSceneInfo: what sits in world coordinates (the transforms outside any
    transform, the bounds and vertex arrays of geometry outside any transform, the lights they switch on) and the
    one camera with its transform. {'transforms', 'bounds', 'vertex_arrays', 'lights', 'camera',
    'camera_transform', 'problems'}; objects by reference number."""
    out = {'transforms': {}, 'bounds': set(), 'vertex_arrays': {}, 'lights': set(), 'camera': None,
           'camera_transform': None, 'problems': []}
    probs = out['problems']
    infos = g.objects_of('igSceneInfo')
    if len(infos) != 1:
        probs.append(f'{len(infos)} igSceneInfo objects (expected 1)')
        return out
    root = g.obj(infos[0].get(5))
    if root is None or not root.decoded or not g.isa(root, 'igNode'):
        probs.append('the igSceneInfo scene graph (slot 5) is not a node')
        return out
    local_bounds, cameras, seen = set(), [], {}
    stack = [(root.ref, None, False)]          # (reference, the transform it hangs from directly, under a transform)
    while stack:
        ref, parent, under = stack.pop()
        o = g.obj(ref)
        if o is None or not o.decoded or not g.isa(o, 'igNode'):
            probs.append(f'scene graph item {ref}: not a readable node')
            continue
        if ref in seen:
            if seen[ref] != under:
                probs.append(f'{o.name} {o.get(2)!r} hangs both in and outside a transform')
            continue
        seen[ref] = under
        if not under and o.name not in _FRAME_NODE_TYPES:
            probs.append(f'{o.name} {o.get(2)!r} in world coordinates: the re-frame does not know how to move it')
            continue
        bound = o.get(3)
        if isinstance(bound, int) and bound >= 0:
            (local_bounds if under else out['bounds']).add(bound)
        if g.isa(o, 'igCamera'):
            cameras.append((o, parent, under))
            continue
        if g.isa(o, 'igLightSet'):                 # slot 7 = its igLightList
            if not under:
                ls = g.list_items(o.get(7))
                if ls is None:
                    probs.append(f'igLightSet {o.get(2)!r}: no readable light list')
                else:
                    out['lights'].update(ls)
            continue
        is_tf = g.isa(o, 'igTransform')
        if is_tf and not under:
            out['transforms'][ref] = o
        if g.isa(o, 'igAttrSet') and not under:    # slot 8 = its igAttrList (geometry: the igGeometryAttr)
            attrs = g.list_items(o.get(8))
            if attrs is None:
                probs.append(f'{o.name} {o.get(2)!r}: no readable attribute list')
            for a in attrs or ():
                ao = g.obj(a)
                if ao is None or not ao.decoded:
                    probs.append(f'{o.name} {o.get(2)!r}: attribute {a} not readable')
                elif g.isa(ao, 'igGeometryAttr'):
                    va = g.obj(ao.get(4))
                    if va is None or not va.decoded or not g.isa(va, 'igVertexArray'):
                        probs.append(f'{o.name} {o.get(2)!r}: geometry attribute {a} has no readable vertex array')
                    else:
                        out['vertex_arrays'][va.ref] = va
                elif g.isa(ao, 'igLightAttr'):
                    out['lights'].add(a)
        if g.isa(o, 'igLightStateSet') and not under:   # slot 8 = its igLightStateAttrList (slot 4: the light)
            for a in g.list_items(o.get(8)) or ():
                sa = g.obj(a)
                if sa is not None and sa.decoded and g.isa(sa, 'igLightStateAttr'):
                    out['lights'].add(sa.get(4))
        if g.isa(o, 'igGroup'):
            kids = g.list_items(o.get(7))
            if kids is None:
                if o.get(7) not in (None, -1):
                    probs.append(f'{o.name} {o.get(2)!r}: no readable child list')
                kids = []
            for k in reversed(kids):
                stack.append((k, ref if is_tf else None, under or is_tf))
    for b in out['bounds'] & local_bounds:
        probs.append(f'bound {b} is shared by a world node and a local one')
    for lt in list(out['lights']):
        lo = g.obj(lt)
        if lo is None or not lo.decoded or not g.isa(lo, 'igLightAttr'):
            probs.append(f'light {lt}: not a readable igLightAttr')
            out['lights'].discard(lt)
    if len(cameras) != 1:
        probs.append(f'{len(cameras)} cameras in the scene graph (expected 1)')
        return out
    cam, parent, _under = cameras[0]
    tf = out['transforms'].get(parent)
    if tf is None:
        probs.append(f'camera {cam.get(2)!r} does not hang directly from a transform in world coordinates')
        return out
    out['camera'], out['camera_transform'] = cam, tf
    return out


def reframe_menu_igb(data):
    """(bytes, report): an XML1 menu IGB moved rigidly so its camera sits at MENU_CAMERA_POS (where every XML2
    menu camera sits), with XML2's near plane MENU_CAMERA_NEAR (if the file's is farther) and its own far plane.
    Every world position moves by the camera's offset: the transforms outside any transform (the camera's, the
    text anchors, the button meshes and focus models), the vertices and bounds of the geometry outside any
    transform (the 3D logo, its backing plate) and the lights they switch on (positions). The picture through the
    camera is the same; XMen2.exe's overlays at MENU_OVERLAY_DEPTHS come inside the view; the virtual screen maps
    1:1 onto the world again (the mouse). Byte sizes are unchanged. A file that already has the camera there comes
    back unchanged.
    report: {'problems', 'camera': {'from', 'to', 'near', 'far', 'fov'}, 'delta', 'counts', 'edits': [(offset,
    length)]}; bytes None with any problem (nothing half-moved)."""
    from . import igb_file as G
    rep = {'problems': [], 'counts': {}, 'edits': [], 'camera': {}, 'delta': None}
    try:
        g = G.IgbFile(data)
    except G.IgbError as ex:
        rep['problems'].append(f'not an IGB this reader can place: {ex}')
        return None, rep
    frame = _scene_frame(g)
    rep['problems'] += frame['problems']
    if rep['problems']:
        return None, rep
    cam, ctf = frame['camera'], frame['camera_transform']
    m = ctf.get(8)
    if any(abs(a - b) > 1e-4 for r, t in zip(_rows(m), MENU_CAMERA_ROWS) for a, b in zip(r, t)):
        rep['problems'].append(f'camera {cam.get(2)!r} is turned {_rows(m)}, not like XML2\'s menu cameras '
                               f'{MENU_CAMERA_ROWS}: a move alone cannot re-frame it')
    fov, near, far = cam.get(8), cam.get(9), cam.get(10)
    if not all(isinstance(v, list) and len(v) == 1 for v in (fov, near, far)):
        rep['problems'].append(f'camera {cam.get(2)!r}: fov / near / far are not floats')
        return None, rep
    fov, near, far = fov[0], near[0], far[0]
    pos = tuple(m[12:15])
    delta = tuple(t - p for t, p in zip(MENU_CAMERA_POS, pos))
    new_near = min(near, MENU_CAMERA_NEAR)
    y = MENU_CAMERA_POS[1]
    for depth in MENU_OVERLAY_DEPTHS:
        if not y + new_near <= depth <= y + far:
            rep['problems'].append(f'overlay depth {depth} outside the re-framed view {y + new_near}..{y + far}')
    if rep['problems']:
        return None, rep

    def write_floats(obj, slot, values, first=0):
        g.set_floats(obj, slot, values, first)
        rep['edits'].append((obj.fields[slot].offset + 4 * first, 4 * len(values)))

    def moved(v):
        return [a + b for a, b in zip(v, delta)]

    counts = collections.Counter()
    for o in frame['transforms'].values():
        write_floats(o, 8, moved(o.get(8)[12:15]), 12)
        counts['transforms'] += 1
    for b in sorted(frame['bounds']):
        box = g.obj(b)
        if box is None or not box.decoded or not g.isa(box, 'igAABox'):
            rep['problems'].append(f'bound {b}: not an igAABox')
            continue
        write_floats(box, 2, moved(box.get(2)))
        write_floats(box, 3, moved(box.get(3)))
        counts['bounds'] += 1
    for va in frame['vertex_arrays'].values():
        comps = g.ref_list(va.get(2))            # the component blocks, position first
        count, fmt = va.get(3), va.get(6)
        blk = g.block(comps[0]) if comps else None
        if not isinstance(fmt, int) or not fmt & 1 or blk is None or not isinstance(count, int) \
                or blk[1] != 12 * count:
            rep['problems'].append(f'vertex array {va.ref}: format {fmt}, {count} vertices, position block '
                                   f'{blk and blk[1]} bytes - not positions this re-frame can move')
            continue
        xyz = g.block_floats(comps[0])
        for i in range(0, len(xyz), 3):
            xyz[i:i + 3] = moved(xyz[i:i + 3])
        g.set_block_floats(comps[0], xyz)
        rep['edits'].append(blk)
        counts['vertex_blocks'] += 1
        counts['vertices'] += count
    for lt in sorted(frame['lights']):
        lo = g.obj(lt)
        f = lo.fields.get(6)
        if f is None or f.type != 'igVec3fMetaField':
            rep['problems'].append(f'light {lt}: no position (slot 6 Vec3f)')
            continue
        write_floats(lo, 6, moved(lo.get(6)))
        counts['lights'] += 1
    if new_near != near:
        write_floats(cam, 9, [new_near])
    if rep['problems']:
        return None, rep
    rep['camera'] = {'name': cam.get(2), 'from': pos, 'to': MENU_CAMERA_POS, 'near': (near, new_near), 'far': far,
                     'fov': fov}
    rep['delta'] = delta
    rep['counts'] = dict(counts)
    return g.edited(), rep


MENU_BUTTON_KINDS = ('', '_back', '_highlight')      # the text anchor, the button mesh, the focus model


def menu_button_z(data):
    """{node name: z} of the button nodes (buttonN / _back / _highlight, N = 1..MENU_NODES) of a menu IGB: their
    world transforms' translation z, the screen's vertical (pure; {} when the scene cannot be read)."""
    from . import igb_file as G
    try:
        g = G.IgbFile(data)
    except G.IgbError:
        return {}
    names = {f'button{i}{k}' for i in range(1, MENU_NODES + 1) for k in MENU_BUTTON_KINDS}
    return {o.get(2): o.get(8)[14] for o in _scene_frame(g)['transforms'].values() if o.get(2) in names}


def space_menu_buttons(data, count=None):
    """(bytes, report): the button nodes of buttons 1..count (default: the menu's MENU_BUTTONS) moved in z only, so
    the count buttons spread evenly over the span of XML1's buttons MENU_SPAN (each kind - text anchor, mesh, focus
    model - from its own button MENU_SPAN[0] z to its own button MENU_SPAN[1] z: the offsets between the kinds stay
    XML1's). count = the span's size keeps XML1's own positions (the file unchanged). The nodes carry no bounds (the
    item rectangles are made of their positions, 0x5bc530), so the translation is all that moves. Same size; bytes
    None with a problem (a button node missing or not a world transform). report: {'problems', 'moved': {name: (z0,
    z1)}, 'spacing': (XML1's, ours) of the text anchors, 'edits': [(offset, length)]}."""
    from . import igb_file as G
    count = len(MENU_BUTTONS) if count is None else count
    rep = {'problems': [], 'moved': {}, 'spacing': None, 'edits': []}
    try:
        g = G.IgbFile(data)
    except G.IgbError as ex:
        rep['problems'].append(f'not an IGB this reader can place: {ex}')
        return None, rep
    frame = _scene_frame(g)
    rep['problems'] += frame['problems']
    by_name = {o.get(2): o for o in frame['transforms'].values()}
    first, last = MENU_SPAN
    if not 2 <= count <= MENU_NODES:
        rep['problems'].append(f'{count} buttons: the IGB has button nodes 1..{MENU_NODES}')
    for k in MENU_BUTTON_KINDS:
        for i in sorted({first, last} | set(range(1, count + 1))):
            if f'button{i}{k}' not in by_name:
                rep['problems'].append(f'button{i}{k}: not a transform in world coordinates')
    if rep['problems']:
        return None, rep
    if count == last - first + 1:
        return bytes(data), rep
    for k in MENU_BUTTON_KINDS:
        za, zb = by_name[f'button{first}{k}'].get(8)[14], by_name[f'button{last}{k}'].get(8)[14]
        step = (zb - za) / (count - 1)
        if not k:
            rep['spacing'] = ((zb - za) / (last - first), step)
        for i in range(1, count + 1):
            o = by_name[f'button{i}{k}']
            z0, z1 = o.get(8)[14], za + (i - 1) * step
            if z0 != z1:
                g.set_floats(o, 8, [z1], 14)
                rep['edits'].append((o.fields[8].offset + 4 * 14, 4))
                rep['moved'][f'button{i}{k}'] = (z0, z1)
    return g.edited(), rep


def menu_igb(ctx):
    """(bytes, report): XML1's menu_main.igb re-framed on XML2's menu camera (reframe_menu_igb), its buttons spread
    over XML1's span for the port's MENU_BUTTONS (space_menu_buttons). report: source, problems (the re-frame's,
    the spacing's, a node the menu file names that the IGB lacks), nodes {name: string fields}, camera (the
    re-frame's report without its edit list), spacing (the spacing's report without its edit list)."""
    src = ctx.x1_path(X1_MENU_IGB)
    if src is None:
        return None, {'problems': [f'{X1_MENU_IGB} is not on the XML1 disc'], 'nodes': {}}
    data, frame = reframe_menu_igb(src.read_bytes())
    summary = {k: v for k, v in frame.items() if k != 'edits'}
    summary['edited_ranges'] = len(frame['edits'])
    if data is None:
        return None, {'problems': [f'{X1_MENU_IGB}: {p}' for p in frame['problems']], 'nodes': {},
                      'camera': summary, 'source': str(src)}
    data, spaced = space_menu_buttons(data)
    spacing = {k: v for k, v in spaced.items() if k != 'edits'}
    if data is None:
        return None, {'problems': [f'{X1_MENU_IGB}: {p}' for p in spaced['problems']], 'nodes': {},
                      'camera': summary, 'spacing': spacing, 'source': str(src)}
    fields = igb_string_fields(data)
    nodes = {n: fields.get(n, 0) for n in menu_node_names()}
    problems = [f'{n}: not a node of {X1_MENU_IGB}' for n, c in nodes.items() if not c]
    return data, {'nodes': nodes, 'problems': problems, 'source': str(src), 'camera': summary, 'spacing': spacing}


def _x1_menu_texts(ctx):
    """{button index: text} from XML1's main.eng (buttonN items)."""
    out = {}
    try:
        root = ctx.read_x1_xml(X1_MAIN_MENU)
    except KeyError:
        root = None
    for it in (root.iter('item') if root is not None else ()):
        m = re.fullmatch(r'button(\d)', it.get('name') or '')
        if m and it.get('text'):
            out[int(m.group(1))] = it.get('text')
    return out


def menu_tree(ctx):
    """the UI/menus/main tree: XML1's main.eng (item names, order, style) in XML2's MAIN_MENU schema over
    x1_menu_main; English text."""
    texts = _x1_menu_texts(ctx)
    try:
        x1 = ctx.read_x1_xml(X1_MAIN_MENU)
    except KeyError:
        x1 = None
    desc = (x1.get('desctext1') if x1 is not None else None) or '$MENU_ACCEPT Select'
    root = ET.Element('MENU', {
        'name': 'main', 'igb': MENU_IGB_NAME, 'type': 'MAIN_MENU', 'fullscreen': 'false', 'gamepause': 'false',
        'resetcontroller': 'true', 'updownonly': 'true', 'lighting': 'true', 'fadein': 'false', 'fadeout': 'false',
        'desctext1': desc, 'image': MENU_IMAGE})
    shown = [b[0] for b in MENU_BUTTONS]
    hidden = {'enabled': 'false', 'hide': 'true'}
    for i in range(1, MENU_NODES + 1):                   # the button meshes (XML1: enabled="false")
        ET.SubElement(root, 'item', {'name': f'button{i}_back', 'type': 'MENU_ITEM_MODEL', 'enabled': 'false',
                                     **({} if i in shown else {'hide': 'true'})})
    for i in range(1, MENU_NODES + 1):                   # the focus models, swapped by <onfocus>
        ET.SubElement(root, 'item', {'name': f'button{i}_highlight', 'type': 'MENU_ITEM_MODEL',
                                     **({} if i in shown else hidden)})
    order = [f'button{i}' for i in shown]
    n = len(order)
    for k, (i, text, cmd) in enumerate(MENU_BUTTONS):
        a = {'name': order[k], 'text': text or texts.get(i) or order[k], 'style': MENU_TEXT_STYLE, **MENU_TEXT_ALIGN,
             'up': order[k - 1], 'down': order[(k + 1) % n]}
        if k == 0:
            a['startactive'] = 'true'
        if cmd:
            a['usecmd'] = cmd
        el = ET.SubElement(root, 'item', a)
        ET.SubElement(el, 'onfocus', {'item': f'button{i}_highlight', 'type': 'focus', 'model': MENU_FOCUS_MODEL})
        ET.SubElement(el, 'onfocus', {'item': f'button{i}_highlight', 'type': 'nofocus', 'model': MENU_NOFOCUS_MODEL})
    for i in range(1, MENU_NODES + 1):                   # XML1's debug slots: no text, never focused
        if i not in shown:
            ET.SubElement(root, 'item', {'name': f'button{i}', 'style': MENU_TEXT_STYLE, **hidden})
    ET.SubElement(root, 'item', {'name': 'desctext1', 'style': 'STYLE_DESC'})
    ET.SubElement(root, 'item', {'name': 'version', 'style': 'STYLE_DESC', 'textalignx': 'TEXT_ALIGN_LEFT',
                                 'gamevar': 'version'})
    return root


def usecmd_commands(cmd):
    """[(command, rest)] of a usecmd line as XMen2.exe's console runs it (0x55beb0: ';' separates commands, the first
    word names the command; pure)."""
    out = []
    for part in (cmd or '').split(';'):
        words = part.strip().split(None, 1)
        if words:
            out.append((words[0].lower(), words[1].strip() if len(words) > 1 else ''))
    return out


# ------------------------------------------------------------------------------------------ the PC's save messages
# XMen2.exe's PC save / load messages are not in Data/strings (whose "X-Men Legends 2" lines are the PS2 / Xbox /
# GameCube memory-card texts): its message function (0x55e9b0) maps each message code to a key of igct<lang>.bnx in
# the game folder (key=text lines, CRLF, latin-1; "igct" + "" for eng, 0x4032b2), e.g. EMSG_NO_DATA_DEVNUM (0x55ea04)
# = the Load Game dialog's no-save-data message, which names XML2. Three keys name the game
# (EMSG_INSUF_SPC_DEVNUM_BLOCKS 0x55e9e2, EMSG_NO_DATA_DEVNUM, EMSG_NO_GAME_DEVNUM_BLOCKS 0x55ea4a); the port gives them
# its own name, XML1's spelling "X-Men Legends" (XML1 strings.eng 3105), in every language file, nothing else changed.
IGCT_GLOB = 'igct*.bnx'
IGCT_NAME = re.compile(rb'X-[Mm]en Legends (?:2|II)(?![0-9A-Za-z])')
IGCT_PORT_NAME = b'X-Men Legends'
IGCT_NO_DATA = ('igct.bnx', 'EMSG_NO_DATA_DEVNUM', 'No X-Men Legends save data present on hard disk.')


def igct_retext(data):
    """(bytes, [keys changed]): an igct*.bnx with XML2's name in its texts replaced by the port's (pure; bytes
    otherwise identical, idempotent)."""
    keys = []
    out = []
    for line in data.split(b'\n'):
        new = IGCT_NAME.sub(IGCT_PORT_NAME, line)
        if new != line:
            keys.append(line.split(b'=', 1)[0].decode('latin-1'))
        out.append(new)
    return b'\n'.join(out), keys


def igct_text(data, key):
    """the text of `key` in an igct*.bnx, or None (pure)."""
    for line in data.split(b'\n'):
        k, sep, v = line.partition(b'=')
        if sep and k.decode('latin-1').strip() == key:
            return v.rstrip(b'\r').decode('latin-1')
    return None


def igct_files(ctx):
    """[actual rel] of the base install's igct*.bnx (the game folder's root)."""
    import fnmatch
    return sorted(r for r in ctx.base_index if '/' not in r and fnmatch.fnmatch(r.lower(), IGCT_GLOB))


# Data/strings: 19 texts name XML2, the memory-card texts of the consoles (3105, 3203.., 3300.., 3500..) - and one the
# PC can show: the message function's fallback (0x55ea74 -> 0x55eb30, strings 0xc80 + code for the codes without an
# igct key) gives code 43 = 0xd00 (3328, @MEMCARD@XBOX_DELETE_CORRUPT_QUERY) "X-Men Legends 2 save data appears to be
# damaged ...". The English half (.engb, the texts) gets the port's name like igct; the .XMLB half (keys) is XML2's,
# written back unchanged so the localized pair stays whole (V3).
STRINGS_REL = 'Data/strings'
NAME_TEXT = re.compile(IGCT_NAME.pattern.decode())


def strings_retext(ctx):
    """(xmlb root, engb root, [ids renamed]): XML2's Data/strings with the port's name in the English texts."""
    x = ctx.read_base_xmlb(STRINGS_REL + '.XMLB')
    e = ctx.read_base_xmlb(STRINGS_REL + '.engb')
    ids = []
    for el in e.iter('string'):
        t = el.get('text') or ''
        if NAME_TEXT.search(t):
            el.set('text', NAME_TEXT.sub(IGCT_PORT_NAME.decode(), t))
            ids.append(el.get('id'))
    return x, e, ids


def menu_package():
    root = ET.Element('packagedef')
    ET.SubElement(root, 'model', {'filename': f'ui/menus/{MENU_IGB_NAME}'})
    for m in MENU_MODELS:
        ET.SubElement(root, 'model', {'filename': m})
    ET.SubElement(root, 'xml', {'filename': 'ui/menus/main'})
    return root


# ================================================================================================ B. Danger Room
X1_DANGERROOM = 'data/dangerroom.eng'
DR_REL = 'Data/dangerroom'
DR_DROP_ATTRS = {'requirement': 'XML1 points gate (XMen2.exe never reads it; startloaded and disks still gate)',
                 'reward': 'XML1 points (never read by XMen2.exe)',
                 'duration': 'CHEMM only; XML1 ignored it too'}
# XMen2.exe opens grade n+1 when the rewardexam course of grade n is passed (XML2's 5 exams = its 5 grade
# transitions); XML1 has no exam flag on QE200 (Junior was gated by points), so it gets one
DR_EXAM_FIXES = {'QE200': 'XML1 gated Junior by points (requirement); XMen2.exe needs the grade exam'}
DR_GRADE_LIMIT, DR_COURSES_PER_GRADE, DR_COURSES_TOTAL = 8, 25, 75       # 0x4d43a5, 0x4d4463, BSS 0x784e00 stride 0x78
DR_XP_ROUND = 50
# SPEC 23.1: XP a course completion gives with --xp-curve xml1 = XML1's. default.xbe's first completion of a course
# (0xc53ee..0xc5428) adds the course's `reward` to the Danger Room points total (word 0x4e70c4; each extra credit
# +1 more, 0xc5809 / 0xc5835 / 0xc5910 / 0xc59c3), the points `requirement` gates; no XP award is called (the roster
# award is registry vt+0xcc, 0x55180, and no Danger Room code calls it). XML1's Danger Room XP came from the kills
# (the FR101 outro says so). XMen2.exe's reward code skips a rewardxp of 0 (0x4c8fb3, 0x5d0b7d).
DR_XML1_REWARD_XP = 0
DR_EXTRA_CREDIT = re.compile(r'(\\n)+\s*You can also earn', re.I)        # XML1 FR106 outro (glyphs { | } ~, ~NN)
DR_GLYPHS = re.compile(r'~\d\d|[{|}]')


def _x1_dr(ctx):
    try:
        return ctx.read_x1_xml(X1_DANGERROOM)
    except KeyError:
        return None


def dr_reward_items(ctx):
    """XML1 item names the XML1 Danger Room courses award (rewarditem; 19), in file order (pure)."""
    root = _x1_dr(ctx)
    out = []
    for c in (root.iter('COURSE') if root is not None else ()):
        v = (c.get('rewarditem') or '').strip()
        if v and v not in out:
            out.append(v)
    return out


def xp_curve(ctx):
    """[(reclevel, xp)] from XML2's own Data/dangerroom.engb: per reclevel the smallest Titanium rewardxp of a
    non-exam course (rl1 200, rl8 2500, rl15 4500, rl21 6250, rl27 10000, rl38 25000 ...)."""
    rows = collections.defaultdict(list)
    try:
        root = ctx.read_base_xmlb('Data/dangerroom.engb')
    except KeyError:
        root = None
    for c in (root.iter('COURSE') if root is not None else ()):
        if (c.get('rewardexam') or '').lower() == 'true':
            continue
        for r in c.findall('REWARD'):
            if r.get('type') == 'Titanium' and r.get('rewardxp'):
                try:
                    rows[int(c.get('reclevel'))].append(int(r.get('rewardxp')))
                except (TypeError, ValueError):
                    pass
    return sorted((rl, min(v)) for rl, v in rows.items())


def reward_xp(curve, reclevel):
    """piecewise-linear interpolation of the curve (clamped at both ends), rounded to DR_XP_ROUND."""
    if not curve:
        return 1000
    try:
        rl = float(reclevel)
    except (TypeError, ValueError):
        rl = curve[0][0]
    if rl <= curve[0][0]:
        v = curve[0][1]
    elif rl >= curve[-1][0]:
        v = curve[-1][1]
    else:
        v = curve[-1][1]
        for (a, xa), (b, xb) in zip(curve, curve[1:]):
            if a <= rl <= b:
                v = xa + (xb - xa) * (rl - a) / (b - a)
                break
    return int(max(DR_XP_ROUND, round(v / DR_XP_ROUND) * DR_XP_ROUND))


def course_reward_xp(ctx, curve, reclevel):
    """a non-item course's Titanium rewardxp by the build's XP curve (SPEC 23.1): XML1's 0 (DR_XML1_REWARD_XP) with
    --xp-curve xml1, XML2's reclevel curve (reward_xp) with xml2."""
    return DR_XML1_REWARD_XP if C.xp_curve_mode(ctx) == 'xml1' else reward_xp(curve, reclevel)


def _trim_extra_credit(v):
    m = DR_EXTRA_CREDIT.search(v)
    return v[:m.start()].rstrip() if m else v


def dangerroom_tree(ctx):
    """(root, report) of Data/dangerroom from XML1's table (XMen2.exe schema). report: counts and changes."""
    x1 = _x1_dr(ctx)
    rep = collections.Counter()
    notes = []
    if x1 is None:
        return None, {'error': f'{X1_DANGERROOM} missing on the XML1 disc'}
    curve = xp_curve(ctx)
    root = ET.Element('DANGERROOM')
    grades = [g for g in x1 if g.tag == 'GRADE']
    for a in x1:
        if a.tag == 'ARENA':
            el = ET.SubElement(root, 'ARENA', dict(a.attrib))
            if el.get('zone'):
                el.set('zone', C.norm(el.get('zone')))
            rep['arenas'] += 1
    for gi, g in enumerate(grades):
        ga = dict(g.attrib)
        if gi == 0:
            ga['unlocked'] = 'true'
        ge = ET.SubElement(root, 'GRADE', ga)
        rep['grades'] += 1
        for c in g:
            if c.tag != 'COURSE':
                continue
            ca = {k: v for k, v in c.attrib.items() if k not in DR_DROP_ATTRS}
            for k in DR_DROP_ATTRS:
                if k in c.attrib:
                    rep[f'dropped_{k}'] += 1
            name = ca.get('name', '')
            if name in DR_EXAM_FIXES and (ca.get('rewardexam') or '').lower() != 'true':
                ca['rewardexam'] = 'true'
                notes.append(f'{name}: rewardexam="true" added ({DR_EXAM_FIXES[name]})')
            item = (ca.pop('rewarditem', '') or '').strip()
            # A throw course needs canthrow="true" (XML2's FR104 convention; loader 0x4d4644): in the port no hero has
            # the grab talent (SPEC_heroes 6), so without it FR112's grabstart combat node could never be done.
            if any((ca.get(k) or '').lower() == 'grabstart' for k in ('combatnode', 'combatnode2', 'combatnode3', 'combatnode4')) \
                    and (ca.get('canthrow') or '').lower() != 'true':
                ca['canthrow'] = 'true'
                notes.append(f'{name}: canthrow="true" added (grabstart combat node; no port hero has the grab talent)')
                rep['canthrow_added'] += 1
            if ca.get('hero'):
                ca['hero'] = ca['hero'].lower()
                ca.setdefault('singleplayer', 'true')
                rep['forced_hero_courses'] += 1
            for k in ('intro', 'outro', 'hint'):
                if ca.get(k) and DR_EXTRA_CREDIT.search(ca[k]):
                    new = _trim_extra_credit(ca[k])
                    notes.append(f'{name} {k}: XML1 extra-credit glyph text trimmed -> {new!r}')
                    ca[k] = new
            ce = ET.SubElement(ge, 'COURSE', ca)
            for s in c:
                if s.tag in ('SPAWNER', 'MUSTDIE', 'MUSTSURVIVE'):
                    ET.SubElement(ce, s.tag, {k.lower(): v for k, v in s.attrib.items()})
                    rep['spawners'] += 1
            if item:
                ET.SubElement(ce, 'REWARD', {'type': 'Titanium', 'rewarditem': item})
                rep['reward_items'] += 1
            else:
                ET.SubElement(ce, 'REWARD', {'type': 'Titanium',
                                             'rewardxp': str(course_reward_xp(ctx, curve, ca.get('reclevel')))})
                rep['reward_xp'] += 1
            rep['courses'] += 1
    return root, {'counts': dict(rep), 'notes': notes, 'xp_curve': curve, 'xp_mode': C.xp_curve_mode(ctx)}


# ---- the 19 challenge reward items as XML2 equipment (called by zones.items_to_add; SPEC 21 B.4)
EQUIP_ARMOR_WORDS = ('MANTLE', 'ARMOR', 'SHIELD', 'AURA', 'GLADIATOR')
EQUIP_BELT_WORDS = ('GEM', 'MEDALLION', 'IMPLANTS', 'MASK', 'HEART', 'ACROBAT', 'SKYBURST')
EQUIP_ATTRS = {'cost': '10000', 'enemy_level': '-1', 'heft': 'light', 'quality': 'legend', 'unique': 'true'}
STAT_WORDS = {'strength': 'Striking', 'speed': 'Speed', 'body': 'Body', 'mind': 'Focus'}   # XML2 item texts
RESIST_WORDS = {'dmg_mental': ('resist_mental', 'Mental'), 'dmg_energy': ('resist_energy', 'Energy'),
                'dmg_physical': ('resist_physical', 'Physical')}
DAMAGE_WORDS = {'dmg_cold': 'Cold', 'dmg_electricity': 'Electricity', 'dmg_wind': 'Wind', 'dmg_mental': 'Mental',
                'dmg_telekinesis': 'Telekinesis', 'dmg_physical': 'Physical', 'dmg_energy': 'Energy',
                'dmg_fire': 'Fire'}


def stat_scale(stat):
    """XML1 -> XML2 stat scale for a bonus (heroes.py): body / mind / strength x STAT_SCALE (4); speed by the speed
    map's slope (2 per XML1 point: XML2's speed band is narrow); 'traits' (all four) by the smaller, 2."""
    from .heroes import STAT_SCALE, SPEED_MAP
    return {'speed': SPEED_MAP[1], 'traits': SPEED_MAP[1]}.get(stat, STAT_SCALE)


def equipment_class(name):
    n = name.upper()
    if any(w in n for w in EQUIP_ARMOR_WORDS):
        return 'armor'
    if any(w in n for w in EQUIP_BELT_WORDS):
        return 'belt'
    return 'gloves'


def _num(v, default=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f


def _fmt(f):
    s = f'{f:.3f}'.rstrip('0').rstrip('.')
    return s or '0'


def _damage_text(desc_parts):
    for p in desc_parts:
        if 'damage' in p.lower() and '%' in p:
            return re.sub(r'\^?\d+(\.\d+)?%', '^%d%%', p.strip(), count=1)
    return None


def translate_equipment(ctx, c):
    """XML1 <item type="equipment"> with <require>/<activepowerup> -> (XML2 <item type="equipment">, note) or
    (None, reason). XMen2.exe equipment (0x47aeff): class gloves/armor/belt, <require cat="character|level">
    (0x4ac470: cat trait/level/counter/xtreme/race/character), <enhancement description><powerup life="-1">
    <affecter .../></powerup></enhancement>. Mapping (only affecter attributes XML2's own data uses):
      atk_damage_scale L [+scope_damage | scope_node | <scope> children] -> damage scale L (+ the same scope: the
                         affecter's scope_damage / scope_node as items.engb WPN_X_FISTS / sabertooth_hero do, <scope>
                         children through a powerup_scope affecter as ps_assassindroid does)
      def_damage_scale L scope_damage=dmg_X -> resist_X 1-L
      strength/speed/body/mind L -> same x stat_scale; traits L -> traits x stat_scale
      power_cost L (scale) -> power_cost scale L (ps_bishop's form)
    Other powerups are reported and dropped."""
    name = (c.get('name') or '').strip()
    if (c.get('type') or '').lower() != 'equipment':
        return None, f'{name}: type {c.get("type")!r} is not equipment'
    cls = equipment_class(name)
    a = {'name': name, 'type': 'equipment', 'class': cls, 'model': f'pickups/equip_{cls}_c', **EQUIP_ATTRS}
    if c.get('displayname'):
        a['displayname'] = c.get('displayname')
    el = ET.Element('item', a)
    for r in c.findall('require'):
        ra = {k.lower(): v for k, v in r.attrib.items()}
        if ra.get('cat') == 'character' and ra.get('item'):
            ra['item'] = ra['item'].lower()
        ET.SubElement(el, 'require', ra)
    desc_parts = [p for p in re.split(r'[.,]\s+', c.get('description') or '') if p.strip()]
    dropped, kept = [], []
    for p in c.findall('activepowerup'):
        pw = (p.get('powerup') or '').lower()
        lv = _num(p.get('level'))
        scopes = [dict(s.attrib) for s in p.findall('scope')]
        enh = []                                   # [(description, [affecter attrs], powerup_scope children)]
        if pw == 'atk_damage_scale' and lv is not None:
            aff = {'affect_type': 'scale', 'attribute': 'damage', 'level': _fmt(lv)}
            text = _damage_text(desc_parts)
            if p.get('scope_damage'):
                aff['scope_damage'] = p.get('scope_damage')
                text = text or f'+^%d%% {DAMAGE_WORDS.get(p.get("scope_damage"), "")} Damage'.replace('  ', ' ')
            if p.get('scope_node'):
                aff['scope_node'] = p.get('scope_node')
            if scopes and all(set(s) == {'scope_damage'} for s in scopes):
                for s in scopes:                  # one enhancement per damage type (each scoped on its own)
                    enh.append((f'+^%d%% {DAMAGE_WORDS.get(s["scope_damage"], s["scope_damage"])} Damage',
                                [dict(aff, scope_damage=s['scope_damage'])], []))
            elif scopes:
                what = '/'.join(v.replace('_', ' ').title() for s in scopes for v in s.values())
                enh.append((f'+^%d%% {what} Damage', [aff], scopes))
            else:
                enh.append((text or '+^%d%% Damage', [aff], []))
        elif pw == 'def_damage_scale' and lv is not None and p.get('scope_damage') in RESIST_WORDS:
            attr, word = RESIST_WORDS[p.get('scope_damage')]
            enh.append((f'+^%d%% {word} Resistance', [{'attribute': attr, 'level': _fmt(1.0 - lv)}], []))
        elif pw in STAT_WORDS and lv is not None:
            enh.append((f'+^%d {STAT_WORDS[pw]}', [{'attribute': pw, 'level': _fmt(lv * stat_scale(pw))}], []))
        elif pw == 'traits' and lv is not None:
            enh.append(('+^%d to all traits', [{'attribute': 'traits', 'level': _fmt(lv * stat_scale('traits'))}], []))
        elif pw == 'power_cost' and lv is not None and (p.get('affect_type') or '').lower() == 'scale':
            enh.append(('Mutant powers cost no energy' if lv == 0 else '^%d%% power cost',
                        [{'affect_type': 'scale', 'attribute': 'power_cost', 'level': _fmt(lv)}], []))
        else:
            dropped.append(pw or '?')
            continue
        for text, affs, sc in enh:
            e = ET.SubElement(el, 'enhancement', {'description': text})
            pu = ET.SubElement(e, 'powerup', {'life': '-1'})
            for aff in affs:
                ET.SubElement(pu, 'affecter', aff)
            if sc:
                ps = ET.SubElement(pu, 'affecter', {'attribute': 'powerup_scope'})
                for s in sc:
                    ET.SubElement(ps, 'scope', s)
            kept.append(pw)
    if not el.findall('enhancement'):
        return None, f'{name}: no XML1 bonus maps to an XML2 affecter ({dropped})'
    note = f'equipment {cls}: {kept}' + (f'; dropped (no XML2 affecter): {dropped}' if dropped else '')
    return el, note


# ================================================================================================ C. review etc.
X1_REVIEW = 'data/review_paths.eng'
X1_CODEX = 'data/codex.eng'
X1_TRIVIA = 'data/trivia.eng'
X1_CREDITS = 'data/credits.eng'
REVIEW_REL, CODEX_REL, TRIVIA_REL, CREDITS_REL = 'Data/review_paths', 'Data/codex', 'Data/trivia', 'Data/credits'
REVIEW_TYPES = ('load', 'cin', 'comic', 'concept', 'stat')          # XMen2.exe category table 0x6d9414
REVIEW_MAX_PER_TYPE = 90                                            # 0x4ae646 cmp ebp,0x5a
REVIEW_UNLOCKED_CIN = ('i101', 'i102', 'i103', 'i104', 'i105', 'i107')   # logos + promo (XML2 marks its own so)
REVIEW_CREDITS = {'type': 'cin', 'name': 'Credits', 'value': 'credits', 'unlocked': 'true'}   # XML2 convention
REVIEW_REWARDS = ('reward_strength', 'reward_speed', 'reward_body', 'reward_mind')   # 0x4ae706: no focus
CODEX_NAME_MAP = {'magneto': ('MagnetoScripted', 'the herostat Magneto is the hidden placeholder (skin 0002)')}
CODEX_ANIMS = ('menu_idle', 'idle')
CREDIT_LINE_TYPES = ('header', 'nameheader', 'name', 'name_left', 'texture', 'pagebreak', 'header_small',
                     'paragraph')                                   # the types XML2's own credits use
PORT_CREDITS = (('pagebreak', None), ('name', ''), ('name', ''), ('header', 'Legends Classic'),
                ('header_small', 'An unofficial fan port'), ('name', ''), ('nameheader', 'Project'),
                ('name', 'ChronoRixun'), ('nameheader', 'Engine fixes'), ('name', 'xml2-fix'))


def _x1(ctx, rel):
    try:
        return ctx.read_x1_xml(rel)
    except KeyError:
        return None


def _fmt_seconds(x):
    s = f'{x:.2f}'.rstrip('0').rstrip('.')
    return s or '0'


def comic_rewards(attrs):
    """XML1 comic reward_* -> XMen2.exe's four (focus -> mind), scaled like the hero stats (stat_scale)."""
    out = {}
    for k, v in attrs.items():
        if not k.startswith('reward_'):
            continue
        stat = k[len('reward_'):]
        stat = 'mind' if stat == 'focus' else stat
        n = _num(v)
        if n is None or f'reward_{stat}' not in REVIEW_REWARDS:
            continue
        out[f'reward_{stat}'] = out.get(f'reward_{stat}', 0) + n * stat_scale(stat)
    return {k: str(int(round(v))) for k, v in out.items()}


def review_entries(ctx):
    """(root, textures, report): the review_paths tree, the texture imports it needs [(x1 rel, out rel noext)],
    and a report. Pure."""
    from . import media as M
    x1 = _x1(ctx, X1_REVIEW)
    rep = collections.Counter()
    notes = []
    root = ET.Element('Paths')
    ET.SubElement(root, 'item', dict(REVIEW_CREDITS))
    textures = []
    if x1 is None:
        return root, textures, {'error': f'{X1_REVIEW} missing on the XML1 disc'}
    for it in x1:
        if it.tag != 'item':
            continue
        a = dict(it.attrib)
        t = (a.get('type') or '').lower()
        v = a.get('value') or ''
        if t == 'cin':
            name = C.norm(v)
            new = M.movie_name(ctx, name)
            a['value'] = new
            dur = M.movie_duration(ctx, name)
            if dur:
                a['duration'] = _fmt_seconds(dur)
            else:
                notes.append(f'cin {name}: no ADX duration (movie not on the XML1 disc?)')
            if name in REVIEW_UNLOCKED_CIN:
                a['unlocked'] = 'true'
            if new != name:
                rep['cin_renamed'] += 1
        elif t in ('comic', 'concept', 'load'):
            new = C.map_review_texture(ctx, v)
            a['value'] = new
            if t == 'comic':
                rew = comic_rewards(a)
                for k in [k for k in a if k.startswith('reward_')]:
                    del a[k]
                a.update(rew)
                if a.get('group'):
                    a['group'] = a['group'].lower()
            src = C.split_ext(C.norm(v))[0]
            src = C.x1_loading_source(new) or (src if t == 'load' else
                                                 f'textures/{t}/{new.rsplit("/", 1)[-1]}')
            textures.append((t, src, new))
        else:
            notes.append(f'entry of unknown type {t!r} kept: {a}')
        rep[t] += 1
        ET.SubElement(root, 'item', a)
    return root, textures, {'counts': dict(rep), 'notes': notes}


def _stats_index(ctx):
    """lower name -> (file, element) over <out> herostat + npcstat (.engb, English) as written this build."""
    out = {}
    for f in ('npcstat', 'herostat'):
        for ext in ('.engb', '.XMLB'):
            if ctx.out_exists(f'Data/{f}{ext}'):
                try:
                    for s in ctx.read_out_xmlb(f'Data/{f}{ext}').iter('stats'):
                        out.setdefault((s.get('name') or '').lower(), (f, s))
                except (KeyError, ValueError):
                    pass
                break
    return out


def anim_db_has(ctx, animdb, anim):
    """True when Actors/<animdb>.IGB contains the NUL-terminated anim name (a whole IGB string field)."""
    if not animdb:
        return None
    p = ctx.out_index.path(f'Actors/{animdb}.IGB')
    if p is None:
        return None
    return (b'\x00' + anim.encode() + b'\x00') in p.read_bytes() or re.search(
        rb'[\x00-\x04]' + re.escape(anim.encode()) + rb'\x00', p.read_bytes()) is not None


def codex_tree(ctx):
    x1 = _x1(ctx, X1_CODEX)
    if x1 is None:
        return None, {'error': f'{X1_CODEX} missing on the XML1 disc'}
    stats = _stats_index(ctx)
    root = ET.Element('characters')
    notes, rep = [], collections.Counter()
    for c in x1:
        if c.tag != 'character':
            continue
        a = dict(c.attrib)
        name = a.get('name') or ''
        if name.lower() in CODEX_NAME_MAP:
            new, why = CODEX_NAME_MAP[name.lower()]
            notes.append(f'{name} -> {new} ({why})')
            a['name'] = name = new
        st = stats.get(name.lower())
        animdb = st[1].get('characteranims') if st else None
        want = [x for x in [a.get('anim')] + list(CODEX_ANIMS) if x]
        chosen = None
        for x in dict.fromkeys(want):
            if anim_db_has(ctx, animdb, x):
                chosen = x
                break
        if chosen is None:
            chosen = a.get('anim') or 'idle'
            notes.append(f'{name}: none of {want} found in Actors/{animdb}.IGB; anim {chosen!r} kept (check)')
            rep['anim_unverified'] += 1
        elif chosen != a.get('anim'):
            notes.append(f'{name}: anim {a.get("anim")!r} -> {chosen!r} (what its anim DB {animdb} has)')
            rep['anim_changed'] += 1
        a['anim'] = chosen
        ET.SubElement(root, 'character', a)
        rep['characters'] += 1
    return root, {'counts': dict(rep), 'notes': notes}


def trivia_acts(ctx):
    """Acts in which a trivia console (triviaMenu()) can be used: the research zone_acts.json acts of every XML1
    zone whose zone XML calls triviaMenu (mansion1a_2 .. mansion8_2 -> 1, 3, 5, 6, 8, 9). Pure."""
    za = ctx.research_json('scripts/out/zone_acts.json')
    acts = set()
    for z in ctx.x1_zones():
        for ext in ('.eng', '.xml'):
            p = ctx.x1_path(f'maps/{z}{ext}')
            if p is not None:
                if b'triviamenu' in p.read_bytes().lower():
                    acts |= {int(a) for a in (za.get(z) or {}).get('acts') or ()}
                break
    return sorted(acts)


def trivia_tree(ctx):
    x1 = _x1(ctx, X1_TRIVIA)
    if x1 is None:
        return None, {'error': f'{X1_TRIVIA} missing on the XML1 disc'}
    qs = [q for q in x1 if q.tag == 'question']
    acts = trivia_acts(ctx) or [1]
    base, extra = divmod(len(qs), len(acts))
    sizes = [base + (1 if i < extra else 0) for i in range(len(acts))]
    root = ET.Element('trivia')
    split = {}
    i = 0
    escaped = 0

    def texts(a):                   # XMen2.exe's renderer codes written '|c' ("X-Men #1 featuring": pen x 1)
        nonlocal escaped
        if a.get('text') and escape_menu_text(a['text']) != a['text']:
            a['text'] = escape_menu_text(a['text'])
            escaped += 1
        return a
    for act, n in zip(acts, sizes):
        split[act] = n
        for q in qs[i:i + n]:
            qe = ET.SubElement(root, 'question', texts(dict(q.attrib, act=str(act))))
            for ans in q:
                if ans.tag == 'answer':
                    ET.SubElement(qe, 'answer', texts(dict(ans.attrib)))
        i += n
    return root, {'counts': {'questions': len(qs), 'escaped_texts': escaped}, 'split': split, 'acts': acts}


# ---- the text renderer's codes (SPEC 21.4.1; research/campaign/late_game_test.md B2)
# XMen2.exe's menu / HUD text renderer (0x5ef2e0) reads codes inside the text itself: '#' takes the next 3 characters
# through atoi (0x5ef5dc..0x5ef60a) as code 3000+N, which the draw (0x5ee780, 0x5ee7f2) turns into "pen x = N" - a
# tab; the width (0x596df0) and wrap (0x597c90) measures read it the same way. '~NN' / '~~' are colour on / off (codes
# 1000+NN / 2000, 0x5ef62e), '$NAME' a controller token (0x5ef6dd), and '|c' is the character c itself (0x5ef4fa;
# the width / wrap measures add c's advance and skip both, 0x596e73 / 0x597d92 jump tables). XML1's credits have 21
# lines with '#N': "NYC Acolyte #1, Shadow" drew "Shadow" over the line's start ("#1, " = pen x 1). XML2's own
# texts never show '#', '$', '~' or '|' (its credits have none, nothing escapes them). Every such character of a
# credit text is written as '|c'; the credit fonts have a '#' glyph (x2f_med_pc / x2f_big glyph 35; '|' has none).
MENU_TEXT_CODES = '#$~|'


def escape_menu_text(text):
    """text with every character XMen2.exe's renderer reads as a code written as '|c' (drawn as c; pure)."""
    return ''.join('|' + c if c in MENU_TEXT_CODES else c for c in text or '')


def unescaped_menu_codes(text):
    """[(index, char)]: the characters of `text` XMen2.exe's renderer would read as a code ('#', '$', '~' not
    escaped by a '|' before them; a '|' with nothing after it). Pure."""
    t, out, i = text or '', [], 0
    while i < len(t):
        if t[i] == '|':
            if i + 1 == len(t):
                out.append((i, '|'))
            i += 2
            continue
        if t[i] in MENU_TEXT_CODES:
            out.append((i, t[i]))
        i += 1
    return out


def credits_tree(ctx):
    x1 = _x1(ctx, X1_CREDITS)
    if x1 is None:
        return None, {'error': f'{X1_CREDITS} missing on the XML1 disc'}
    root = ET.Element('credits')
    n = escaped = 0
    for ln in x1:
        if ln.tag == 'line':
            a = dict(ln.attrib)
            if a.get('text') and escape_menu_text(a['text']) != a['text']:
                a['text'] = escape_menu_text(a['text'])
                escaped += 1
            ET.SubElement(root, 'line', a)
            n += 1
    for t, text in PORT_CREDITS:
        ET.SubElement(root, 'line', {'type': t} if text is None else {'type': t, 'text': escape_menu_text(text)})
    return root, {'counts': {'x1_lines': n, 'port_lines': len(PORT_CREDITS), 'escaped_lines': escaped}}


# ---- the credits' backdrop (SPEC 21.4.2; late_game_test.md B5a)
# XML1's credits menus (ui/menus/credits.xml / credits_end.xml: CREDITS_MENU over igb menu_credits / menu_credits_end,
# no image): menu_credits.igb = a black plane and, in front of it, XML1's credits page (credits_page.png, 512x512 DXT
# inside the IGB) lit by one directional light; menu_credits_end.igb = the black plane alone (the end credits roll
# over black). XML2's credits menus draw x2m_credits (a 60% black plane) with the image textures/loading/credits01
# (the MENU `image`: a background sprite, see below), which XML2's credits change
# with their 19 `texture` lines (0x5b1e80): XML1's credits have none, so the port rolled them over XML2's hero
# collage. The port's credits menus are XML2's (type, endgame, precache) with XML1's IGB and an EMPTY image: the
# image is the menu manager's, not the menu's - a menu with `image` sets the manager's current one (vt+0x1c0,
# 0x5bba0f), and every menu then opens with the manager's current image as its background sprite if it is not empty
# (0x5bbbb5..0x5bbbe8 -> menu vt+0x84 = 0x5bb7b0, drawn over XML1's planes). Without the attribute the credits
# showed the last image set (the online screens' Apocalypse art after Play Online, seen in game); image="" empties
# it, so no sprite. The IGBs are re-framed on XML2's menu camera like the main menu's (reframe_menu_igb): with
# XML1's camera (near 897 from y -1108) the credit text, drawn by the text system at y -800 / -850
# (MENU_OVERLAY_DEPTHS), would be clipped.
# (menu name, XML1's IGB, the port's IGB name: XML2 ships unrelated UI/menus/menu_credits*.IGB, hence x1_)
CREDITS_MENUS = (('credits', 'ui/menus/menu_credits.igb', 'x1_menu_credits'),
                 ('credits_end', 'ui/menus/menu_credits_end.igb', 'x1_menu_credits_end'))
CREDITS_MENU_SET = {'image': ''}                   # no background sprite (XML1's menus have no image)


def credits_menu_igb(ctx, x1_rel):
    """(bytes, report): XML1's credits menu IGB re-framed on XML2's menu camera (reframe_menu_igb)."""
    src = ctx.x1_path(x1_rel)
    if src is None:
        return None, {'problems': [f'{x1_rel} is not on the XML1 disc']}
    data, frame = reframe_menu_igb(src.read_bytes())
    rep = {k: v for k, v in frame.items() if k != 'edits'}
    rep['source'] = str(src)
    rep['problems'] = [f'{x1_rel}: {p}' for p in frame['problems']]
    return data, rep


def credits_menu_tree(ctx, name, igb_name):
    """XML2's UI/menus/<name> (CREDITS_MENU, endgame, precache) over igb_name, with an empty image (CREDITS_MENU_SET).
    None when the base install lacks it."""
    try:
        root = ctx.read_base_xmlb(f'UI/menus/{name}.XMLB')
    except (KeyError, FileNotFoundError, ValueError):
        return None
    root.set('igb', igb_name)
    for k, v in CREDITS_MENU_SET.items():
        root.set(k, v)
    return root


def credits_menu_package(ctx, name, igb_name):
    """XML2's Packages/generated/maps/package/menus/<name> with XML1's IGB as its model. None without the base's."""
    try:
        root = ctx.read_base_xmlb(f'{MENU_PKG_DIR}/{name}.PKGB')
    except (KeyError, FileNotFoundError, ValueError):
        return None
    models = [e for e in root if e.tag == 'model' and C.norm(e.get('filename') or '').startswith('ui/menus/')]
    for e in models:
        root.remove(e)
    root.insert(0, ET.Element('model', {'filename': f'ui/menus/{igb_name}'}))
    return root


# ------------------------------------------------------------------------------------ the Review menu's tabs
# SPEC 21.4.3 (Owen: hide Stats - XML1's Review had Cinematics, Comics, Concept Art, Loadscreens). XMen2.exe's
# REVIEW_PATHS_MENU (vtable 0x69ee7c) finds its five tabs by name through the table 0x6e6e28 (option01_text ..
# option05_text, the fifth = Stats) and its Stats page lists XML2's acts 1-5 (0x5d0c20, hard-coded). The port's
# UI/menus/review is XML2's menu without the Stats tab's two items: its label option05_text and the tab backdrop
# option05_focus (an m_invis model its onfocus / nofocus events dress); every lookup of an item the menu lacks
# returns nothing and is skipped (0x5adc10 / 0x5ade70 / 0x5adf80). The tab change itself (left / right, pad, mouse)
# is exe code that wraps at 5: xml2-fix [Game] ReviewStats=0 (REVIEW_STATS_KEY, written by tools/harness.py for a
# build whose review menu has no Stats tab) makes it wrap at 4. Both halves (.XMLB keys, .engb English) are XML2's
# with the same two items removed.
REVIEW_MENU_REL = 'UI/menus/review'
REVIEW_MENU_TYPE = 'REVIEW_PATHS_MENU'
REVIEW_TAB_ITEMS = ('option01_text', 'option02_text', 'option03_text', 'option04_text')   # Screens .. Concepts
REVIEW_STATS_ITEMS = ('option05_text', 'option05_focus')                                   # the Stats tab
REVIEW_STATS_KEY = ('Game', 'ReviewStats', '0')


def review_menu_trees(ctx):
    """(xmlb root, engb root, removed item names): XML2's UI/menus/review halves without the Stats tab's items
    (REVIEW_STATS_ITEMS). (None, None, []) when the base install lacks either half."""
    halves = []
    removed = []
    for ext in ('.XMLB', '.engb'):
        try:
            root = ctx.read_base_xmlb(REVIEW_MENU_REL + ext)
        except (KeyError, FileNotFoundError, ValueError):
            return None, None, []
        gone = [it for it in root.findall('item') if it.get('name') in REVIEW_STATS_ITEMS]
        for it in gone:
            root.remove(it)
        removed.append(sorted(it.get('name') for it in gone))
        halves.append(root)
    return halves[0], halves[1], removed[0] if removed[0] == removed[1] else removed


# ------------------------------------------------------------------------------------ the codex menu's icons
# Issue #48. XML2's UI/menus/codex list item (MENU_ITEM_LISTCODEX) has icons="textures/ui/mini_convo_icons.png"
# with icons_cols / icons_rows 8: the list (built from the stats by name, 0x5b0be0) draws for each entry the cell
# its stats' `textureicon` names (stored only when present, 0x44c329; unset = 0 = Cyclops' face). XML1's codex
# menus had no icons and XML1's stats no textureicon (default.xbe has no such string), so XML1's NPC entries all drew
# Cyclops. The list reads `icons` only when the item has it (0x5c269e..0x5c2711): the port's codex menu is XML2's
# without the three icon attributes and without the icon texture's precache. Both halves (.XMLB keys, .engb
# English) are XML2's with the same changes.
CODEX_MENU_REL = 'UI/menus/codex'
CODEX_LIST_TYPE = 'MENU_ITEM_LISTCODEX'
CODEX_ICON_ATTRS = ('icons', 'icons_cols', 'icons_rows')
CODEX_ICON_PRECACHE = 'textures/ui/mini_convo_icons'


def codex_menu_trees(ctx):
    """(xmlb root, engb root, removed): XML2's UI/menus/codex halves without the list's icon attributes
    (CODEX_ICON_ATTRS) and the icon texture's precache (CODEX_ICON_PRECACHE). removed = sorted change names, the
    same for both halves or a list of both. (None, None, []) when the base install lacks either half."""
    halves, removed = [], []
    for ext in ('.XMLB', '.engb'):
        try:
            root = ctx.read_base_xmlb(CODEX_MENU_REL + ext)
        except (KeyError, FileNotFoundError, ValueError):
            return None, None, []
        gone = []
        for it in root.iter('item'):
            if (it.get('type') or '').upper() == CODEX_LIST_TYPE:
                for k in CODEX_ICON_ATTRS:
                    if k in it.attrib:
                        del it.attrib[k]
                        gone.append(f'{it.get("name")}.{k}')
        for pc in [pc for pc in root.findall('precache') if C.norm(C.split_ext(C.norm(pc.get('filename') or ''))[0])
                   == CODEX_ICON_PRECACHE]:
            root.remove(pc)
            gone.append(f'precache {CODEX_ICON_PRECACHE}')
        removed.append(sorted(gone))
        halves.append(root)
    return halves[0], halves[1], removed[0] if removed[0] == removed[1] else removed


def codex_icon_problems(root):
    """[str]: what in a codex menu tree still draws XML2's icon cells (a list item with icons*, the precache)."""
    out = []
    for it in root.iter('item'):
        if (it.get('type') or '').upper() == CODEX_LIST_TYPE:
            out += [f'list item {it.get("name")!r} has {k}' for k in CODEX_ICON_ATTRS if k in it.attrib]
    out += [f'precache {pc.get("filename")}' for pc in root.findall('precache')
            if C.split_ext(C.norm(pc.get('filename') or ''))[0] == CODEX_ICON_PRECACHE]
    return out


# ------------------------------------------------------------------------------------ the pause menu's Blink Portal
# Issue #89 (SPEC 64). The pause menu in every zone is XML2's UI/menus/pda (PDA_MENU). XMen2.exe's PDA menu finds
# its entries by name (label_option01..09) and acts on some of them in its own code: label_option03 (no usecmd) is
# X-Men Legends II's Blink Portal, which opens a portal to the act's town centre from zoneinfo - for the first
# game's acts 1-5 X-Men Legends II's towns, with no way back but an earlier save. The first game had no portal (its
# pause menu has no such entry, none of its scripts recall). Both front ends play the first game's zones, so the
# port's pda is XML2's without the portal entry (both halves, .XMLB keys and .engb English, the same changes):
#   - the label item PDA_PORTAL_LABEL is removed (with its focus events): nothing left to select or to act on;
#   - its panel models PDA_PORTAL_MODELS stay in the menu, hidden and disabled (the slot is an empty gap);
#   - the items whose up / down named the label point past it (the label's own down / up).
PDA_MENU_REL = 'UI/menus/pda'
PDA_MENU_TYPE = 'PDA_MENU'
PDA_PORTAL_LABEL = 'label_option03'
PDA_PORTAL_MODELS = ('option03', 'option03_light', 'option03_focus', 'pause_bracket_03')


def pda_without_portal(root):
    """Remove the Blink Portal entry from a PDA menu tree in place (see above). Returns the sorted change names
    ('remove <label>', 'hide <model>', '<item>.up|down -> <name>'), or None when `root` is no PDA_MENU with the
    portal label (nothing changed)."""
    if root is None or (root.get('type') or '').upper() != PDA_MENU_TYPE:
        return None
    label = next((it for it in root.findall('item') if it.get('name') == PDA_PORTAL_LABEL), None)
    if label is None:
        return None
    root.remove(label)
    changes = [f'remove {PDA_PORTAL_LABEL}']
    for it in root.iter('item'):
        for way, past in (('up', label.get('up')), ('down', label.get('down'))):
            if it.get(way) == PDA_PORTAL_LABEL:
                if past and past != it.get('name'):
                    it.set(way, past)
                else:
                    del it.attrib[way]
                changes.append(f'{it.get("name")}.{way} -> {it.get(way)}')
    for it in root.findall('item'):
        if it.get('name') in PDA_PORTAL_MODELS:
            it.set('hide', 'true')
            it.set('enabled', 'false')
            changes.append(f'hide {it.get("name")}')
    return sorted(changes)


def pda_menu_trees(ctx):
    """(xmlb root, engb root, changes): XML2's UI/menus/pda halves without the Blink Portal entry
    (pda_without_portal). changes = the sorted change names, the same for both halves or a list of both.
    (None, None, []) when the base install lacks either half; a half without the entry gives None in changes."""
    halves, changes = [], []
    for ext in ('.XMLB', '.engb'):
        try:
            root = ctx.read_base_xmlb(PDA_MENU_REL + ext)
        except (KeyError, FileNotFoundError, ValueError):
            return None, None, []
        changes.append(pda_without_portal(root))
        halves.append(root)
    return halves[0], halves[1], changes[0] if changes[0] == changes[1] else changes


def pda_portal_problems(root):
    """[str]: what in a PDA menu tree still offers the Blink Portal (the label item, a link to it, a shown model)."""
    out = []
    for it in root.iter('item'):
        name = it.get('name')
        if name == PDA_PORTAL_LABEL:
            out.append(f'item {name!r} is in the menu')
        out += [f'item {name!r} {way} -> {PDA_PORTAL_LABEL}' for way in ('up', 'down')
                if it.get(way) == PDA_PORTAL_LABEL]
        if name in PDA_PORTAL_MODELS and ((it.get('hide') or '').lower() != 'true'
                                          or (it.get('enabled') or '').lower() != 'false'):
            out.append(f'model {name!r} is shown')
    return out


def pda_portal_changes_ok(changes):
    """True when `changes` (pda_menu_trees) is one list for both halves that removes the label and hides every
    portal model."""
    return (isinstance(changes, list) and all(isinstance(c, str) for c in changes)
            and f'remove {PDA_PORTAL_LABEL}' in changes
            and all(f'hide {m}' in changes for m in PDA_PORTAL_MODELS))


def write_pda_menu(ctx):
    """Write the pause menu without the Blink Portal (both front ends). Returns the change list, or None (error)."""
    px, pg, changes = pda_menu_trees(ctx)
    if px is None:
        ctx.error(f'pause menu: {PDA_MENU_REL}.XMLB / .engb not in the base install')
        return None
    if not pda_portal_changes_ok(changes):
        ctx.error(f'pause menu: XML2\'s {PDA_MENU_REL} changes {changes}, expected the removal of '
                  f'{PDA_PORTAL_LABEL} and hidden {", ".join(PDA_PORTAL_MODELS)} in both halves')
        return None
    ctx.write_xmlb_pair(PDA_MENU_REL, px, pg, source='frontend:XML2\'s pause menu without the Blink Portal')
    ctx.set_count('pda_portal_changes', len(changes))
    ctx.note(f'pause menu: {PDA_MENU_REL} = XML2\'s without the Blink Portal entry ({"; ".join(changes)}): the '
             f'first game had no portal and X-Men Legends II\'s leads to its towns (issue #89)')
    return changes


# ================================================================================================ D. personal items
PERSONAL_DIR = 'data/personal'                     # XML1 assets/data/personal/<item>.eng; XMen2.exe 0x5cedd0
PERSONAL_REL = 'Data/personal'


def personal_texture_rel(value):
    """an ITEM texture value ('textures/personal/cyc_1.png') -> its IGB name without extension, or None."""
    t = C.norm(value or '')
    if not t:
        return None
    return C.split_ext(t)[0] if C.split_ext(t)[1] in ('.png', '.igb', '.tga', '.bmp') else t


def personal_items(ctx):
    """[(item name, ITEM root, texture rel without extension)] for every XML1 data/personal/<item>.eng (English);
    the text escaped for XMen2.exe's renderer (escape_menu_text), the XML1 schema conversion applied."""
    out = []
    for rel in ctx.x1_rels(PERSONAL_DIR + '/'):
        stem, ext = C.split_ext(rel)
        if ext != '.eng' or '/' in stem[len(PERSONAL_DIR) + 1:]:
            continue
        root = _x1(ctx, rel)
        if root is None:
            continue
        ctx.x1_schema(root, rel)
        for el in root.iter():
            if el.get('text'):
                el.set('text', escape_menu_text(el.get('text')))
        tex = next((personal_texture_rel(el.get('texture')) for el in root.iter() if el.get('texture')), None)
        out.append((stem[len(PERSONAL_DIR) + 1:], root, tex))
    return out


def write_personal_items(ctx):
    """D: write every XML1 personal item and import its texture. Returns a report dict."""
    rep = {'items': [], 'textures': collections.Counter(), 'problems': []}
    for name, root, tex in personal_items(ctx):
        _write_pair(ctx, f'{PERSONAL_REL}/{name}', root, f'XML1 personal item {name}')
        rep['items'].append(name)
        if tex is None:
            rep['problems'].append(f'{PERSONAL_REL}/{name}: no texture')
            continue
        st = _import_texture(ctx, tex + '.igb', tex)
        rep['textures'][st] += 1
        if st not in ('present', 'written', 'kept_xml2'):
            rep['problems'].append(f'{PERSONAL_REL}/{name}: texture {tex} ({st})')
    return rep


# ================================================================================================ run
def _write_pair(ctx, rel_noext, root, why):
    """a localized data table: the same English tree in .XMLB and .engb (every XML1 import does this)."""
    return ctx.write_xmlb(rel_noext, root, ('.XMLB', '.engb'), source=f'frontend:{why}')


def _import_texture(ctx, x1_rel, out_noext):
    """import one XML1 texture under its review name (a byte copy; XML1-wins only for the x1/ names)."""
    rel = C.norm(x1_rel)
    rel = rel if rel.endswith('.igb') else rel + '.igb'
    # registered this build (another module wrote / carried it) or an XML2 base file: nothing to do. <out> alone
    # is not proof: a file of an earlier build that nobody registers now is swept after the modules run.
    if ctx.registry.get(C.norm(out_noext) + '.igb') is not None or ctx.base_index.find(out_noext, ('.IGB',)):
        return 'present'
    res = ctx.import_x1_asset(rel, out_rel_noext=out_noext)
    return res.status


def run(ctx):
    mode = C.frontend_mode(ctx)
    ctx.set_count('frontend_xml1', int(mode == 'xml1'))
    # ---- D. personal items (in-zone data: both front ends)
    prep = write_personal_items(ctx)
    for p in prep['problems']:
        ctx.error(f'personal items: {p}')
    ctx.set_count('personal_items', len(prep['items']))
    for st, n in prep['textures'].items():
        ctx.set_count(f'personal_textures_{st}', n)
    ctx.note(f'personal items: XML1\'s {len(prep["items"])} Data/personal items (XML2\'s leftover wolverine01 '
             f'replaced) and their Textures/personal IGBs ({dict(prep["textures"])})')
    # ---- the pause menu without the Blink Portal (in-zone: both front ends; issue #89)
    write_pda_menu(ctx)
    if mode != 'xml1':
        ctx.note('--frontend xml2: XML2\'s main menu, intro, menu music, Danger Room and Review data are kept '
                 '(nothing written; SPEC 21 A/B fallback)')
        return
    det = {}
    # ---- A. main menu
    data, irep = menu_igb(ctx)
    for p in irep['problems']:
        ctx.error(f'{MENU_IGB_REL}: {p}')
    if data is not None:
        ctx.write_bytes(MENU_IGB_REL, data, source=irep.get('source'))
    menu = menu_tree(ctx)
    ctx.write_xmlb(MENU_REL, menu, ('.XMLB', '.engb'), source='frontend:main menu (XML1 layout, XML2 schema)')
    ctx.write_xmlb(MENU_PKG_REL, menu_package(), ('.PKGB',), source='frontend:main menu package')
    for m in MENU_MODELS:
        if not ctx.out_index.find(m, ('.IGB',)):
            ctx.error(f'main menu model {m} is not in <out> (XML2 ships it)')
    img = _import_texture(ctx, MENU_IMAGE, MENU_IMAGE)
    if img not in ('present', 'written', 'kept_xml2'):
        ctx.error(f'main menu image {MENU_IMAGE}: {img}')
    det['menu'] = {'igb_nodes': irep['nodes'], 'items': menu_plan(), 'xml2fix_main_menu_items': MAIN_MENU_ITEMS,
                   'igb_camera': irep.get('camera')}
    cam = (irep.get('camera') or {}).get('camera') or {}
    moved = (irep.get('camera') or {}).get('counts') or {}
    for k, n in moved.items():
        ctx.set_count(f'menu_igb_moved_{k}', n)
    ctx.note(f'main menu: {MENU_IGB_REL} = XML1 menu_main.igb re-framed on XML2\'s menu camera (camera '
             f'{cam.get("name")} {cam.get("from")} -> {cam.get("to")}, near {cam.get("near")}; moved with it: '
             f'{moved}), so XMen2.exe\'s dialogs and help line are drawn over it and the mouse frame fits; '
             f'UI/menus/main = XML1\'s main.eng in '
             f'XML2\'s schema (text on {MAIN_MENU_ITEMS[0]}..{MAIN_MENU_ITEMS[-1]}, every action in a usecmd; '
             f'{MAIN_MENU_ITEMS[MAIN_MENU_QUIT_SLOT]} = Quit); mouse and Quit need xml2-fix [Game] '
             f'MainMenuItems={",".join(MAIN_MENU_ITEMS)} (tools/harness.py writes it)')
    ctx.note(f'main menu: Begin Story runs {BEGIN_STORY_CMD!r} - XMen2.exe\'s newgame minus its difficulty prompt '
             f'(XML1 had none): Normal, then startFirstMission; XML2\'s New Game+ choice (once Hard is unlocked) is '
             f'skipped by xml2-fix [Game] NewGamePlus=0 (tools/harness.py writes it)')
    # ---- the PC's save / load messages (igct*.bnx): the port's name, not XML2's
    retexted = {}
    for rel in igct_files(ctx):
        data, keys = igct_retext(ctx.base_index.path(rel).read_bytes())
        if keys:
            ctx.write_bytes(rel, data, source=f'frontend:{rel} with the port\'s name')
            retexted[rel] = keys
            ctx.count('igct_texts_renamed', len(keys))
    if not retexted:
        ctx.error(f'no {IGCT_GLOB} in the base install names XML2 (expected {IGCT_NO_DATA[1]} in {IGCT_NO_DATA[0]})')
    det['igct'] = retexted
    sx, se, sids = strings_retext(ctx)
    if sids:
        ctx.write_xmlb_pair(STRINGS_REL, sx, se, source='frontend:Data/strings with the port\'s name (English texts)')
    ctx.set_count('strings_texts_renamed', len(sids))
    det['strings'] = sids
    ctx.note(f'save / load messages: "X-Men Legends 2" -> "{IGCT_PORT_NAME.decode()}" in {len(retexted)} igct*.bnx '
             f'({sorted({k for ks in retexted.values() for k in ks})}) and {len(sids)} {STRINGS_REL} texts '
             f'(the consoles\' memory-card texts and 3328, the PC\'s damaged-save message)')
    # ---- B. Danger Room
    dr, drep = dangerroom_tree(ctx)
    if dr is None:
        ctx.error(drep['error'])
    else:
        _write_pair(ctx, DR_REL, dr, 'XML1 Danger Room courses')
        for n in drep['notes']:
            ctx.note(f'dangerroom: {n}')
        c = drep['counts']
        ctx.set_count('dr_courses', c.get('courses', 0))
        ctx.set_count('dr_grades', c.get('grades', 0))
        ctx.set_count('dr_arenas', c.get('arenas', 0))
        ctx.set_count('dr_reward_items', c.get('reward_items', 0))
        ctx.set_count('dr_points_dropped', c.get('dropped_requirement', 0) + c.get('dropped_reward', 0))
        how = (f'rewardxp {DR_XML1_REWARD_XP} (--xp-curve xml1: XML1 gave no completion XP, only Danger Room '
               f'points)' if drep['xp_mode'] == 'xml1' else
               f'rewardxp from XML2\'s reclevel curve {drep["xp_curve"][:4]}... (--xp-curve xml2)')
        ctx.set_count('dr_reward_xp_courses', c.get('reward_xp', 0))
        ctx.note(f'dangerroom: XML1 {c.get("arenas")} arenas, {c.get("grades")} grades, {c.get("courses")} courses; '
                 f'{c.get("reward_items")} challenge items, {c.get("reward_xp")} Titanium {how}; '
                 f'XML1 points (requirement/reward) dropped: '
                 f'{c.get("dropped_requirement", 0)}/{c.get("dropped_reward", 0)} (XMen2.exe never reads them)')
        ctx.defer('Danger Room Adamantium / Vibranium tiers (XML1\'s extra credits are default.xbe logic): one '
                  'Titanium reward per course (in-game check B.7)')
        det['dangerroom'] = drep
    # ---- C. review / codex / trivia / credits
    rv, textures, rrep = review_entries(ctx)
    if rrep.get('error'):
        ctx.error(rrep['error'])
    missing = []
    for t, src, new in textures:
        st = _import_texture(ctx, src, new)
        if st not in ('present', 'written', 'kept_xml2'):
            missing.append(f'{t} {new} <- {src} ({st})')
        else:
            ctx.count(f'review_textures_{st}')
    for m in missing:
        ctx.error(f'review_paths: texture missing: {m}')
    _write_pair(ctx, REVIEW_REL, rv, 'XML1 review_paths')
    for n in rrep.get('notes', []):
        ctx.note(f'review_paths: {n}')
    det['review'] = rrep
    by_type = collections.Counter(it.get('type') for it in rv)
    for t, n in by_type.items():
        ctx.set_count(f'review_{t}', n)
        if n > REVIEW_MAX_PER_TYPE:
            ctx.error(f'review_paths: {n} {t} entries (XMen2.exe keeps {REVIEW_MAX_PER_TYPE} per category, 0x4ae646)')
    cx, crep = codex_tree(ctx)
    if cx is None:
        ctx.error(crep['error'])
    else:
        _write_pair(ctx, CODEX_REL, cx, 'XML1 codex')
        for n in crep['notes']:
            ctx.note(f'codex: {n}')
        det['codex'] = crep
    tv, trep = trivia_tree(ctx)
    if tv is None:
        ctx.error(trep['error'])
    else:
        _write_pair(ctx, TRIVIA_REL, tv, 'XML1 trivia')
        ctx.note(f'trivia: XML1\'s {trep["counts"]["questions"]} questions split over the trivia-console acts '
                 f'{trep["split"]} (XMen2.exe shows the current act\'s, 0x5e75b5)')
        det['trivia'] = trep
    cr, crrep = credits_tree(ctx)
    if cr is None:
        ctx.error(crrep['error'])
    else:
        _write_pair(ctx, CREDITS_REL, cr, 'XML1 credits + port block')
        ctx.set_count('credit_lines_escaped', crrep['counts']['escaped_lines'])
        ctx.note(f'credits: {crrep["counts"]["escaped_lines"]} XML1 lines with a character XMen2.exe\'s text '
                 f'renderer reads as a code ({MENU_TEXT_CODES!r}; "#1" = pen x 1) written as "|c"')
        det['credits'] = crrep
    # ---- the credits' backdrop: XML1's credits menu IGBs instead of XML2's hero collage
    det['credits_menus'] = {}
    for name, x1_rel, igb_name in CREDITS_MENUS:
        data, irep = credits_menu_igb(ctx, x1_rel)
        menu, pkg = credits_menu_tree(ctx, name, igb_name), credits_menu_package(ctx, name, igb_name)
        probs = irep['problems'] + [f'{what} {rel} not in the base install' for what, rel, v in (
            ('menu', f'UI/menus/{name}.XMLB', menu), ('package', f'{MENU_PKG_DIR}/{name}.PKGB', pkg)) if v is None]
        for p in probs:
            ctx.error(f'credits menu {name}: {p}')
        if probs:
            continue
        ctx.write_bytes(f'UI/menus/{igb_name}.IGB', data, source=irep['source'])
        ctx.write_xmlb(f'UI/menus/{name}', menu, ('.XMLB',), source=f'frontend:XML2\'s {name} menu over XML1\'s IGB')
        ctx.write_xmlb(f'{MENU_PKG_DIR}/{name}', pkg, ('.PKGB',), source=f'frontend:{name} menu package')
        det['credits_menus'][name] = {'igb': igb_name, 'camera': irep.get('camera'), 'counts': irep.get('counts')}
        ctx.count('credits_menus')
    ctx.note(f'credits menus: {", ".join(n for n, _, _ in CREDITS_MENUS)} over XML1\'s IGBs '
             f'({", ".join(i for _, _, i in CREDITS_MENUS)}: the credits page / black, re-framed on XML2\'s menu '
             f'camera), with an empty image {CREDITS_MENU_SET} (no background sprite over them)')
    # ---- the Review menu: XML1's four categories, no Stats tab (SPEC 21.4.3)
    rx, rg, removed = review_menu_trees(ctx)
    if rx is None:
        ctx.error(f'review menu: {REVIEW_MENU_REL}.XMLB / .engb not in the base install')
    elif removed != sorted(REVIEW_STATS_ITEMS):
        ctx.error(f'review menu: XML2\'s {REVIEW_MENU_REL} has Stats tab items {removed}, expected '
                  f'{sorted(REVIEW_STATS_ITEMS)} in both halves')
    else:
        ctx.write_xmlb_pair(REVIEW_MENU_REL, rx, rg, source='frontend:XML2\'s review menu without its Stats tab')
        det['review_menu'] = {'removed': removed, 'xml2fix': '='.join(REVIEW_STATS_KEY[1:])}
        ctx.note(f'review menu: {REVIEW_MENU_REL} = XML2\'s without the Stats tab ({", ".join(removed)}); the tab '
                 f'change wraps at 4 with xml2-fix [{REVIEW_STATS_KEY[0]}] {REVIEW_STATS_KEY[1]}='
                 f'{REVIEW_STATS_KEY[2]} (tools/harness.py writes it)')
    # ---- the codex menu: XML1's text-only list, no icon cells (issue #48)
    kx, kg, kremoved = codex_menu_trees(ctx)
    want = sorted([f'list.{k}' for k in CODEX_ICON_ATTRS] + [f'precache {CODEX_ICON_PRECACHE}'])
    if kx is None:
        ctx.error(f'codex menu: {CODEX_MENU_REL}.XMLB / .engb not in the base install')
    elif kremoved != want:
        ctx.error(f'codex menu: XML2\'s {CODEX_MENU_REL} changes {kremoved}, expected {want} in both halves')
    else:
        ctx.write_xmlb_pair(CODEX_MENU_REL, kx, kg, source='frontend:XML2\'s codex menu without list icons')
        det['codex_menu'] = {'removed': kremoved}
        ctx.note(f'codex menu: {CODEX_MENU_REL} = XML2\'s without the list\'s icon cells ({", ".join(kremoved)}): '
                 f'XML1\'s codex list was text only')
    ctx.write_meta('frontend_detail.json', det)
    ctx.log(f'main menu, dangerroom ({(drep.get("counts") or {}).get("courses")} courses), review '
            f'({dict(by_type)}), codex, trivia, credits written')
