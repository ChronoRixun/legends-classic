"""xml1build.frontend_selftest - standalone self-test of the SPEC 21 front end (frontend.py and the front-end parts of
common / scripts / zones / media). Never writes game files and never launches the game.

usage (from tools/):
  python -m xml1build.frontend_selftest                      unit checks of the pure providers (no build needed)
  python -m xml1build.frontend_selftest --out <build>        + the build's front-end files (either front end)
  python -m xml1build.frontend_selftest --out <build> --compare <reference build>
                                                             + every file either build registered is byte-identical
                                                               between the two, except the expected differences
                                                               (--frontend xml2 against a build from before SPEC 21:
                                                               only the end-of-campaign script is new)
Exit code 0 = every check passed.

Unit checks (U1-U17): the menu IGB (XML1's re-framed on XML2's menu camera: only the moved floats change, every
world position by the camera's offset, the overlay depths come into view, idempotent, the constants = XML2's
x2m_main camera; the 8 buttons spread evenly over XML1's button1..7 span, on screen; every node the menu names, the
string-field rule), the
MAIN_MENU file (XML1's items in XML1's order, texts, usecmds - Begin Story = resetgame + the difficulty prompt's Normal
choice, no item opening the prompt -, Play Online = openmenu online, the Quit slot on button8, the xml2-fix
MainMenuItems list = harness.py's, which reads it off the menu (a pre-Play Online menu too, not XML2's) and writes
NewGamePlus=0 with it, XMen2.exe's mouse-slot clamp bytes), the Danger Room table (grades, exams, rewards, dropped XML1 points, the extra-credit trim), the
XP curve (XML2's own rows reproduced, interpolation, clamping), the 19 reward items as equipment, the review
namespace (common.map_review_texture in both modes), review_paths, trivia split, credits (U9: the 21 '#' lines
escaped '|#', no text code left, the escape rules), codex names, the
generated intro / postgame scripts, the sound plan (menu music kind per mode), the menu zone's kept XML2 package
entries, the Danger Room completion XP per --xp-curve (U14: XML1's 0 / XML2's reclevel curve; with --out the build's
table against its own curve), the save / load messages (U15: igct*.bnx with the port's name in exactly the keys that
named XML2, idempotent, and Data/strings' 19 English texts, its .XMLB half unchanged; with --out the build's files:
rewritten under xml1, XML2's under xml2), the credits menus (U16: XML2's CREDITS_MENUs over XML1's IGBs re-framed on
XML2's menu camera, no image, endgame kept on credits_end, packages listing XML1's IGB), the review menu (U17: XML2's
without the Stats tab's two items, both halves; harness.py's ReviewStats=0 for it, none for XML2's).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from xml1build import common as C          # noqa: E402
from xml1build import frontend as F        # noqa: E402

FAIL = collections.defaultdict(list)
INFO = collections.OrderedDict()
SCRATCH = C.ROOT / 'build' / '_selftest_frontend'          # never written; a ctx needs an <out> path


def fail(kind, msg):
    FAIL[kind].append(str(msg))


def ctx_for(mode, out=None, xp_curve=None):
    out = Path(out) if out else SCRATCH
    kw = {'xp_curve': xp_curve} if xp_curve else {}
    args = C.args_for_out(out, frontend=mode, **kw) if out != SCRATCH else \
        C.default_args(out=str(out), frontend=mode, **kw)
    return C.BuildContext(out, args=args, scan_out=out != SCRATCH,
                          registry=C.Registry.load(out / '_build' / 'registry.json') if out != SCRATCH else None)


# ================================================================================================ unit checks
def u1_menu_igb(ctx):
    from xml1build import igb_file as G
    data, rep = F.menu_igb(ctx)
    if data is None:
        fail('U1', rep['problems'])
        return
    src = ctx.x1_path(F.X1_MENU_IGB).read_bytes()
    # SPEC 21.2: XML1's IGB re-framed on XML2's menu camera: same size, only the moved floats differ; SPEC 21.2.4: then
    # its 8 buttons spread over XML1's button1..7 span (z floats of the button nodes only)
    again, frame = F.reframe_menu_igb(src)
    spaced, srep = F.space_menu_buttons(again) if again is not None else (None, {'edits': [], 'problems': ['-']})
    if spaced != data or len(data) != len(src) or data == src or srep['problems']:
        fail('U1', 'x1_menu_main.IGB is not XML1\'s menu_main.igb re-framed and spaced (same size, camera moved)')
        return
    covered = bytearray(len(src))
    for off, n in frame['edits'] + srep['edits']:
        covered[off:off + n] = b'\x01' * n
    stray = [i for i in range(len(src)) if src[i] != data[i] and not covered[i]]
    if stray:
        fail('U1', f'{len(stray)} changed bytes outside the re-frame\'s edits (first at 0x{stray[0]:x})')
    u1_spacing(again, data, srep)
    data = again                               # the re-frame's checks below: XML1's file against the re-framed one
    cam0, cam1 = F.menu_igb_camera(src), F.menu_igb_camera(data)
    if cam0.get('problem') or cam1.get('problem'):
        fail('U1', f'camera: {cam0.get("problem")} / {cam1.get("problem")}')
        return
    delta = tuple(b - a for a, b in zip(cam0['pos'], cam1['pos']))
    if any(abs(a - b) > 1e-4 for a, b in zip(cam1['pos'], F.MENU_CAMERA_POS)) or cam1['near'] != F.MENU_CAMERA_NEAR \
            or cam1['far'] != cam0['far'] or cam1['fov'] != cam0['fov'] or cam1['rows'] != cam0['rows']:
        fail('U1', f'camera {cam0} -> {cam1}')
    for depth in F.MENU_OVERLAY_DEPTHS:        # XMen2.exe's dialog box / text system depths: clipped before, seen after
        if cam0['pos'][1] + cam0['near'] <= depth or not cam1['pos'][1] + cam1['near'] <= depth <= cam1['pos'][1] + cam1['far']:
            fail('U1', f'overlay depth {depth}: XML1 view {cam0["pos"][1] + cam0["near"]}.., re-framed '
                       f'{cam1["pos"][1] + cam1["near"]}..{cam1["pos"][1] + cam1["far"]}')
    # every world position moved by the camera's offset: the picture through the camera is the same
    g0, g1 = G.IgbFile(src), G.IgbFile(data)

    def off(a, b):
        return max(abs((y - x) - d) for x, y, d in zip(a, b, delta))
    worst = 0.0
    named = {}
    for o0 in g0.objects:
        o1 = g1.obj(o0.ref)
        if o0.name == 'igTransform':
            named[o0.get(2)] = off(o0.get(8)[12:15], o1.get(8)[12:15]) if o0.get(8) != o1.get(8) else None
        elif o0.name == 'igLightAttr':
            worst = max(worst, off(o0.get(6), o1.get(6)))
    moved = {n for n, v in named.items() if v is not None}
    want = set(F.menu_node_names()) | {'Camera01'}
    if moved != want:
        fail('U1', f'moved transforms {sorted(moved ^ want)} differ from the menu nodes + Camera01')
    worst = max([worst] + [v for v in named.values() if v is not None])
    for ref in (r for r, b in g0.blocks.items() if g0.data[b[0]:b[0] + b[1]] != g1.data[b[0]:b[0] + b[1]]):
        xyz0, xyz1 = g0.block_floats(ref), g1.block_floats(ref)
        worst = max(worst, max(off(xyz0[i:i + 3], xyz1[i:i + 3]) for i in range(0, len(xyz0), 3)))
    if worst > 1e-3:
        fail('U1', f'a world position moved {worst} away from the camera\'s offset {delta}')
    if F.reframe_menu_igb(data)[0] != data:
        fail('U1', 're-framing the re-framed IGB changes it (not idempotent)')
    counts = frame['counts']
    if counts != {'transforms': 30, 'bounds': 5, 'vertex_blocks': 4, 'vertices': 3587, 'lights': 5}:
        fail('U1', f'moved {counts} (XML1\'s menu_main.igb: 30 transforms, 5 bounds, 4 vertex blocks / 3587 '
                   f'vertices, 5 lights)')
    INFO['U1 camera'] = f'{cam0["pos"]} near {cam0["near"]} -> {cam1["pos"]} near {cam1["near"]}; moved {counts}'
    # the constants are XML2's own menu camera (x2m_main.IGB), when the XML2 install is there
    p = ctx.base_index.path(F.XML2_MENU_CAMERA_IGB + '.igb')
    if p is not None:
        x2 = F.menu_igb_camera(p.read_bytes())
        if x2.get('problem') or tuple(x2['pos']) != F.MENU_CAMERA_POS or x2['near'] != F.MENU_CAMERA_NEAR or \
                any(abs(a - b) > 1e-4 for r, t in zip(x2['rows'], F.MENU_CAMERA_ROWS) for a, b in zip(r, t)):
            fail('U1', f'XML2\'s {F.XML2_MENU_CAMERA_IGB} camera {x2} is not frontend.MENU_CAMERA_*')
    else:
        INFO['U1 XML2 camera'] = f'{F.XML2_MENU_CAMERA_IGB} not in the base install: constants not cross-checked'
    # a scene the re-frame cannot move is refused whole (a truncated file)
    if F.reframe_menu_igb(src[:-8])[0] is not None:
        fail('U1', 'a truncated IGB was re-framed')
    # XML1's nodes, each 3 string fields (node name, ItemName value, path); nothing renamed any more
    for name in F.menu_node_names():
        if rep['nodes'].get(name) != 3:
            fail('U1', f'{name}: {rep["nodes"].get(name)} string fields (expected 3)')
    for gone in ('label_option04', 'label_credits', 'debug_text'):
        if F.igb_string_fields(data).get(gone):
            fail('U1', f'{gone} in the IGB (the renames of the first cut are gone)')
    # the field rule on a hand-made field: 'abcdef' padded to 8, a string without the length prefix is not a field
    probe = b'\x00\x00\x00\x00' + (8).to_bytes(4, 'little') + b'abcdef\x00\x00' + b'\x00\x00\x00\x00xyz\x00'
    if dict(F.igb_string_fields(probe)) != {'abcdef': 1}:
        fail('U1', f'igb_string_fields on a probe: {dict(F.igb_string_fields(probe))}')
    INFO['U1 nodes'] = len(rep['nodes'])
    if rep['problems']:
        fail('U1', rep['problems'])


def u1_spacing(framed, data, srep):
    """SPEC 21.2.4: the port's buttons spread evenly over XML1's button1..button7 span, each kind (text anchor, mesh,
    focus model) from its own button1 z to its own button7 z; nothing else of the scene moves."""
    z0, z1 = F.menu_button_z(framed), F.menu_button_z(data)
    n = len(F.MENU_BUTTONS)
    first, last = F.MENU_SPAN
    if n != 8 or (first, last) != (1, 7):
        fail('U1', f'{n} buttons over the span {F.MENU_SPAN} (expected 8 over XML1\'s 1..7)')
    for k in F.MENU_BUTTON_KINDS:
        zs = [z1[f'button{i}{k}'] for i in range(1, n + 1)]
        steps = [a - b for a, b in zip(zs, zs[1:])]
        want = (z0[f'button{first}{k}'] - z0[f'button{last}{k}']) / (n - 1)
        if abs(zs[0] - z0[f'button{first}{k}']) > 1e-3 or abs(zs[-1] - z0[f'button{last}{k}']) > 1e-3 or \
                any(abs(st - want) > 1e-3 for st in steps):
            fail('U1', f'button*{k}: z {[round(z, 2) for z in zs]} not {first}..{last} of XML1 evenly ({want:.2f})')
        for i in range(n + 1, F.MENU_NODES + 1):
            if z1[f'button{i}{k}'] != z0[f'button{i}{k}']:
                fail('U1', f'button{i}{k} (hidden) moved')
    moved = set(srep['moved'])
    if not moved <= {f'button{i}{k}' for i in range(2, n + 1) for k in F.MENU_BUTTON_KINDS}:
        fail('U1', f'spacing moved {sorted(moved)}')
    # the whole 8 fit the screen with a focus bar's margin, and stay apart (V15's rule)
    lo = F.MENU_CAMERA_POS[2] - F.MENU_SCREEN[1] / 2 + F.MENU_EDGE
    if min(z1[f'button{i}{k}'] for i in range(1, n + 1) for k in F.MENU_BUTTON_KINDS) < lo or \
            abs(srep['spacing'][1]) < F.MENU_MIN_SPACING or abs(srep['spacing'][0]) < abs(srep['spacing'][1]):
        fail('U1', f'spacing {srep["spacing"]}: off screen or too tight')
    # 7 buttons keep XML1's own positions
    if F.space_menu_buttons(framed, last - first + 1)[0] != framed:
        fail('U1', 'space_menu_buttons with XML1\'s 7 buttons changes the file')
    INFO['U1 spacing'] = f'XML1 {abs(srep["spacing"][0]):.2f} -> {abs(srep["spacing"][1]):.2f} ' \
                         f'({len(moved)} nodes moved)'


def u2_menu(ctx):
    root = F.menu_tree(ctx)
    items = {it.get('name'): it for it in root.iter('item')}
    x1 = ctx.read_x1_xml(F.X1_MAIN_MENU)
    x1_items = [it.get('name') for it in x1.iter('item')]
    if [it.get('name') for it in root.iter('item')] != x1_items:
        fail('U2', f'item names / order differ from XML1\'s main.eng: {list(items)} vs {x1_items}')
    for n in F.EXE_MENU_FORBIDDEN:
        if n in items:
            fail('U2', f'{n} present')
    if root.get('type') != 'MAIN_MENU' or root.get('fullscreen') != 'false' or root.get('igb') != F.MENU_IGB_NAME:
        fail('U2', f'menu attributes {root.attrib}')
    order = [n for n, _t, _c in F.menu_plan()]
    nshown = len(order)
    # xml2-fix MainMenuItems: the 6 mouse slots = XML1's 6 buttons, Quit = button8; Play Online (button7) keys / pad
    # only until xml2-fix lifts the mouse clamp (SPEC 21.2.4; MAIN_MENU_ITEMS_MOUSE_ALL = the value then)
    if order != [f'button{i}' for i in range(1, 9)] or \
            F.MAIN_MENU_ITEMS != tuple(f'button{i}' for i in (1, 2, 3, 4, 5, 6, 8)) or \
            F.MAIN_MENU_KEYS_ONLY != ('button7',) or F.MAIN_MENU_ITEMS_MOUSE_ALL != F.MAIN_MENU_ITEMS + ('button7',):
        fail('U2', f'MAIN_MENU_ITEMS {F.MAIN_MENU_ITEMS} / keys only {F.MAIN_MENU_KEYS_ONLY} vs the buttons {order}')
    texts = [items[n].get('text') for n in order]
    if texts != ['Begin Story', 'Load Game', 'Danger Room', 'Options', 'Review', 'Credits', 'Play Online', 'Quit']:
        fail('U2', f'button texts {texts}')
    cmds = [items[n].get('usecmd') for n in order]
    if cmds != ['resetgame;runscript setDifficultyLevel(1)', 'runscript saveloadProcess(3)',
                'set drmode 1;openmenu danger_room', 'options_main', 'set reviewmode -1;openmenu review',
                'openmenu credits', 'openmenu online', None] or F.PLAY_ONLINE_CMD != 'openmenu online':
        fail('U2', f'usecmds {cmds}')
    # XMen2.exe's retail bytes the proposed clamp change relies on (cmp edi, 6 / mov ebx, 6 / jge +2)
    exe = ctx.base_index.path('XMen2.exe')
    if exe is not None:
        import pefile
        pe = pefile.PE(str(exe), fast_load=True)
        at = F.MAIN_MENU_CLAMP_VA - 2 - pe.OPTIONAL_HEADER.ImageBase
        got = pe.get_memory_mapped_image()[at:at + 10]
        if got != bytes.fromhex('83ff06bb060000007d02'):
            fail('U2', f'XMen2.exe at 0x{F.MAIN_MENU_CLAMP_VA - 2:x}: {got.hex()} (the mouse slot clamp)')
    # Begin Story (SPEC 21.2.2): XML1's newgame (no prompt) = XMen2.exe's resetgame + its prompt's Normal choice
    x1_begin = next((it.get('usecmd') for it in x1.iter('item') if it.get('name') == 'button1'), None)
    if x1_begin != 'newgame' or F.BEGIN_STORY_CMD != cmds[0]:
        fail('U2', f'Begin Story: XML1 {x1_begin!r}, ours {cmds[0]!r}, BEGIN_STORY_CMD {F.BEGIN_STORY_CMD!r}')
    if F.usecmd_commands(F.BEGIN_STORY_CMD) != [('resetgame', ''), ('runscript', 'setDifficultyLevel(1)')]:
        fail('U2', f'usecmd_commands(BEGIN_STORY_CMD) {F.usecmd_commands(F.BEGIN_STORY_CMD)}')
    prompt = [(n, c) for n in order for c, _ in F.usecmd_commands(items[n].get('usecmd'))
              if c in F.NEW_GAME_PROMPT_CMDS]
    if prompt:
        fail('U2', f'items opening the difficulty prompt: {prompt}')
    if F.MAIN_MENU_ITEMS[F.MAIN_MENU_QUIT_SLOT] != 'button8' or items['button8'].get('usecmd') or \
            order[-1] != 'button8':
        fail('U2', 'the Quit slot is not button8 (the last button) without a usecmd')
    for n in order:
        it = items[n]
        if it.get('style') != 'STYLE_MENU_BLACK' or it.get('enabled') or it.get('hide') or it.get('type') \
                or it.get('textalignx') != 'TEXT_ALIGN_CENTER_X' or it.get('textaligny') != 'TEXT_ALIGN_CENTER_Y':
            fail('U2', f'{n}: {it.attrib}')
    for i in range(1, F.MENU_NODES + 1):
        back, hl = items[f'button{i}_back'], items[f'button{i}_highlight']
        if back.get('type') != 'MENU_ITEM_MODEL' or back.get('enabled') != 'false':
            fail('U2', f'button{i}_back: {back.attrib}')
        if (back.get('hide') == 'true') != (i > nshown) or (hl.get('hide') == 'true') != (i > nshown):
            fail('U2', f'button{i}: back / highlight hidden {back.get("hide")} / {hl.get("hide")}')
    for i in range(nshown + 1, F.MENU_NODES + 1):
        if items[f'button{i}'].get('hide') != 'true' or items[f'button{i}'].get('enabled') != 'false' \
                or items[f'button{i}'].get('text'):
            fail('U2', f'button{i} (XML1 debug slot) not hidden: {items[f"button{i}"].attrib}')
    # harness.py writes the same list into xml2-fix.ini, read off the build's menu (builds from before Play Online:
    # button1..7, Quit on button7)
    import harness
    if harness.MAIN_MENU_ITEMS != ','.join(F.MAIN_MENU_ITEMS):
        fail('U2', f'harness.MAIN_MENU_ITEMS {harness.MAIN_MENU_ITEMS!r} != {",".join(F.MAIN_MENU_ITEMS)!r}')
    if harness.menu_items_for(root) != harness.MAIN_MENU_ITEMS or harness.menu_items_for(ET.Element('MENU')):
        fail('U2', 'harness.menu_items_for does not recognise the XML1 menu (or takes an empty one)')
    legacy = ET.fromstring(ET.tostring(root))
    for it in list(legacy):
        if it.get('name') == 'button7':
            legacy.remove(it)
        elif it.get('name') == 'button8':
            it.set('name', 'button7')
    if harness.menu_items_for(legacy) != ','.join(f'button{i}' for i in range(1, 8)):
        fail('U2', f'harness.menu_items_for on a menu from before Play Online: {harness.menu_items_for(legacy)!r}')
    x2 = ctx.base_index.path('UI/menus/main.XMLB')
    if x2 is not None and harness.menu_items_for(C.decode_xmlb(x2.read_bytes())):
        fail('U2', 'harness.menu_items_for takes XML2\'s own main menu')
    # ... and NewGamePlus=0 with it (XML2's New Game+ choice after a win on Normal; XML1 had none)
    ini = harness.ini_text('windowed', 1280, 720, False, main_menu_items=harness.MAIN_MENU_ITEMS,
                           new_game_plus=harness.NEW_GAME_PLUS)
    if harness.NEW_GAME_PLUS != '0' or 'NewGamePlus=0' not in ini.split('\r\n') or \
            'NewGamePlus' in harness.ini_text('windowed', 1280, 720, False):
        fail('U2', f'harness NewGamePlus: {harness.NEW_GAME_PLUS!r} / {ini!r}')
    cur, seen = order[0], []
    while cur not in seen:
        seen.append(cur)
        cur = items[cur].get('down')
    if seen != order or items[order[0]].get('up') != order[-1]:
        fail('U2', f'focus chain {seen}')
    for n in order:
        foc = items[n].findall('onfocus')
        if sorted(f.get('type') for f in foc) != ['focus', 'nofocus'] or len({f.get('item') for f in foc}) != 1:
            fail('U2', f'{n}: onfocus {[f.attrib for f in foc]}')
    pk = [(e.tag, e.get('filename')) for e in F.menu_package()]
    if ('model', f'ui/menus/{F.MENU_IGB_NAME}') not in pk or ('xml', 'ui/menus/main') not in pk:
        fail('U2', f'package {pk}')
    INFO['U2 items'] = len(items)


def u3_dangerroom(ctx):
    root, rep = F.dangerroom_tree(ctx)
    if root is None:
        fail('U3', rep)
        return
    grades = list(root.iter('GRADE'))
    courses = list(root.iter('COURSE'))
    if [g.get('name') for g in grades] != ['Freshman', 'Sophomore', 'Junior', 'Senior', 'X-Man', 'Legend']:
        fail('U3', f'grades {[g.get("name") for g in grades]}')
    if len(courses) != 62 or len(list(root.iter('ARENA'))) != 15:
        fail('U3', f'{len(courses)} courses, {len(list(root.iter("ARENA")))} arenas')
    if grades[0].get('unlocked') != 'true' or any(g.get('unlocked') for g in grades[1:]):
        fail('U3', 'only Freshman is unlocked')
    for g in grades[:-1]:
        if not any(c.get('rewardexam') == 'true' for c in g.iter('COURSE')):
            fail('U3', f'{g.get("name")}: no exam')
    for c in courses:
        if any(k in c.attrib for k in F.DR_DROP_ATTRS):
            fail('U3', f'{c.get("name")}: XML1 points left')
        rw = c.findall('REWARD')
        if len(rw) != 1 or rw[0].get('type') != 'Titanium' or not (rw[0].get('rewardxp') or rw[0].get('rewarditem')):
            fail('U3', f'{c.get("name")}: rewards {[r.attrib for r in rw]}')
        if c.get('hero') and (c.get('singleplayer') != 'true' or c.get('hero') != c.get('hero').lower()):
            fail('U3', f'{c.get("name")}: hero {c.get("hero")} singleplayer {c.get("singleplayer")}')
        for k in ('intro', 'outro', 'hint'):
            if F.DR_GLYPHS.search(c.get(k) or '') and '~' in (c.get(k) or ''):
                fail('U3', f'{c.get("name")} {k}: XML1 glyph codes left')
    fr106 = next(c for c in courses if c.get('name') == 'FR106')
    if fr106.get('outro') != 'Well Done!':
        fail('U3', f'FR106 outro {fr106.get("outro")!r}')
    items = [r.get('rewarditem') for c in courses for r in c.findall('REWARD') if r.get('rewarditem')]
    if len(items) != 19 or items != F.dr_reward_items(ctx):
        fail('U3', f'reward items {items}')
    INFO['U3 courses'] = len(courses)


def u4_xp(ctx):
    curve = F.xp_curve(ctx)
    for rl, xp in ((1, 200), (8, 2500), (15, 4500), (21, 6250), (27, 10000), (38, 25000)):
        if F.reward_xp(curve, rl) != xp:
            fail('U4', f'rl{rl}: {F.reward_xp(curve, rl)} != {xp}')
    if F.reward_xp(curve, 9) != 2750 or F.reward_xp(curve, 0) != 200 or F.reward_xp(curve, 99) != curve[-1][1]:
        fail('U4', f'interpolation / clamp: rl9 {F.reward_xp(curve, 9)}, rl0 {F.reward_xp(curve, 0)}, '
                   f'rl99 {F.reward_xp(curve, 99)}')
    INFO['U4 curve points'] = len(curve)


def u14_xp_curve():
    """SPEC 23.1: a non-item course's rewardxp follows --xp-curve: XML1's 0 (default xml1), XML2's reclevel curve
    with xml2; the Danger Room table carries it."""
    x1, x2 = ctx_for('xml1'), ctx_for('xml1', xp_curve='xml2')
    if C.xp_curve_mode(x1) != 'xml1' or C.xp_curve_mode(x2) != 'xml2':
        fail('U14', f'modes {C.xp_curve_mode(x1)} / {C.xp_curve_mode(x2)}')
    curve = F.xp_curve(x1)
    for rl in (1, 8, 9, 38):
        if F.course_reward_xp(x1, curve, rl) != F.DR_XML1_REWARD_XP or \
                F.course_reward_xp(x2, curve, rl) != F.reward_xp(curve, rl):
            fail('U14', f'rl{rl}: {F.course_reward_xp(x1, curve, rl)} / {F.course_reward_xp(x2, curve, rl)}')
    for ctx, want in ((x1, lambda c: str(F.DR_XML1_REWARD_XP)), (x2, lambda c: str(F.reward_xp(curve, c.get('reclevel'))))):
        root, rep = F.dangerroom_tree(ctx)
        for c in root.iter('COURSE'):
            for r in c.findall('REWARD'):
                if r.get('rewardxp') is not None and r.get('rewardxp') != want(c):
                    fail('U14', f'{C.xp_curve_mode(ctx)} {c.get("name")}: rewardxp {r.get("rewardxp")} != {want(c)}')
        if rep.get('xp_mode') != C.xp_curve_mode(ctx):
            fail('U14', f'report xp_mode {rep.get("xp_mode")}')
    INFO['U14 XML1 Danger Room completion XP'] = F.DR_XML1_REWARD_XP


def u5_equipment(ctx):
    x1 = {(it.get('name') or ''): it for it in ctx.read_x1_xml('data/items.eng').iter('item')}
    classes = collections.Counter()
    for name in F.dr_reward_items(ctx):
        el, note = F.translate_equipment(ctx, x1[name])
        if el is None:
            fail('U5', f'{name}: {note}')
            continue
        classes[el.get('class')] += 1
        if el.get('type') != 'equipment' or el.get('class') not in ('gloves', 'armor', 'belt') or \
                el.get('model') != f'pickups/equip_{el.get("class")}_c' or el.get('enemy_level') != '-1':
            fail('U5', f'{name}: {el.attrib}')
        for r in el.findall('require'):
            if r.get('cat') not in ('character', 'level') or (r.get('item') and r.get('item') != r.get('item').lower()):
                fail('U5', f'{name}: require {r.attrib}')
        for e in el.findall('enhancement'):
            pu = e.find('powerup')
            if not e.get('description') or pu is None or pu.get('life') != '-1' or not pu.findall('affecter'):
                fail('U5', f'{name}: enhancement shape')
    b = x1['BANDS_OF_BEAST']
    el, _ = F.translate_equipment(ctx, b)
    affs = [a.attrib for a in el.iter('affecter')]
    if affs != [{'affect_type': 'scale', 'attribute': 'damage', 'level': '1.2', 'scope_node': 'beast_power'},
                {'attribute': 'strength', 'level': '20'}]:
        fail('U5', f'BANDS_OF_BEAST affecters {affs}')
    el, note = F.translate_equipment(ctx, x1['GAUNTLETS_OF_WRATH'])
    if 'drain_time' not in note:
        fail('U5', f'GAUNTLETS_OF_WRATH: drain_time not reported ({note})')
    el, _ = F.translate_equipment(ctx, x1['MASK_OF_XORN'])
    if [a.attrib for a in el.iter('affecter')] != [{'affect_type': 'scale', 'attribute': 'power_cost', 'level': '0'}]:
        fail('U5', 'MASK_OF_XORN')
    el, _ = F.translate_equipment(ctx, x1['SHIAR_MIND_GEM'])
    if [a.attrib for a in el.iter('affecter')] != [{'attribute': 'resist_mental', 'level': '0.5'}]:
        fail('U5', 'SHIAR_MIND_GEM')
    INFO['U5 classes'] = dict(classes)


def u6_namespace():
    x1 = ctx_for('xml1')
    x2 = ctx_for('xml2')
    cases = {'textures/comic/beast_cov.png': ('textures/comic/x1/beast_cov', 'textures/comic/beast_cov'),
             'textures/comic/0901.png': ('textures/comic/x1/col_cov', 'textures/comic/0901'),
             'Textures\\Concept\\concept07': ('textures/concept/x1/concept07', 'textures/concept/concept07'),
             'textures/loading/x_jet': ('textures/loading/x1_x_jet', 'textures/loading/x_jet'),
             'textures/loading/characters_menu': ('textures/loading/x1_characters_menu',
                                                  'textures/loading/characters_menu'),
             'textures/loading/0501': ('textures/loading/14501', 'textures/loading/0501'),
             'textures/loading/x_mansion': ('textures/loading/x_mansion', 'textures/loading/x_mansion'),
             'textures/comic/x1/beast_cov': ('textures/comic/x1/beast_cov', 'textures/comic/x1/beast_cov')}
    for p, (w1, w2) in cases.items():
        if C.map_review_texture(x1, p) != w1 or C.map_review_texture(x2, p) != w2:
            fail('U6', f'{p}: {C.map_review_texture(x1, p)} / {C.map_review_texture(x2, p)}')
    if C.x1_loading_source('textures/loading/x1_x_jet') != 'textures/loading/x_jet' or \
            C.x1_loading_source('textures/loading/x_jet') is not None:
        fail('U6', 'x1_loading_source')
    if C.frontend_zones(x1) or C.frontend_zones(x2) != C.FRONTEND_ZONES or C.frontend_prefixes(x1):
        fail('U6', 'frontend_zones per mode')


def u7_review(ctx):
    root, tex, rep = F.review_entries(ctx)
    c = collections.Counter(it.get('type') for it in root)
    if c != {'cin': 35, 'load': 64, 'comic': 13, 'concept': 38}:
        fail('U7', f'counts {dict(c)}')
    for it in root:
        a = it.attrib
        if a.get('type') == 'cin' and a.get('value') != 'credits' and not a.get('duration'):
            fail('U7', f'{a}: no duration')
        if a.get('type') == 'comic':
            if 'reward_focus' in a or not a['value'].startswith('textures/comic/x1/'):
                fail('U7', f'comic {a}')
        if a.get('type') == 'concept' and not a['value'].startswith('textures/concept/x1/'):
            fail('U7', f'concept {a}')
    first = root[0].attrib
    if first != F.REVIEW_CREDITS:
        fail('U7', f'first entry {first}')
    unlocked = sorted(it.get('value') for it in root if it.get('unlocked') == 'true')
    if unlocked != sorted(['credits', 'xi101', 'xi102', 'xi103', 'xi104', 'xi105', 'xi107']):
        fail('U7', f'unlocked {unlocked}')
    ice = next(it for it in root if it.get('value') == 'textures/comic/x1/ice_cov')
    if ice.get('reward_body') != '8' or ice.get('reward_mind') != '8':        # XML1 body 2, focus 2 -> x4
        fail('U7', f'ice_cov rewards {ice.attrib}')
    cyc = next(it for it in root if it.get('value') == 'textures/comic/x1/cyc_cov')
    if cyc.get('reward_speed') != '4' or cyc.get('reward_mind') != '8':       # speed by the speed slope (2)
        fail('U7', f'cyc_cov rewards {cyc.attrib}')
    r102 = next(it for it in root if it.get('value') == 'r102')
    if abs(float(r102.get('duration')) - 94.26) > 0.05:
        fail('U7', f'r102 duration {r102.get("duration")}')
    INFO['U7 textures'] = len(tex)


def u8_trivia(ctx):
    root, rep = F.trivia_tree(ctx)
    if rep.get('split') != {1: 9, 3: 9, 5: 8, 6: 8, 8: 8, 9: 8}:
        fail('U8', f'split {rep.get("split")}')
    for q in root.iter('question'):
        ans = q.findall('answer')
        if len(ans) != 5 or sum(1 for a in ans if a.get('correct') == 'true') != 1:
            fail('U8', f'question {q.get("text")[:40]!r}')
        for el in [q] + ans:
            if F.unescaped_menu_codes(el.get('text')):
                fail('U8', f'text code left in {el.get("text")[:40]!r}')
    # XML1's one '#' (a trivia question naming a comic issue "#1") written '|#' (SPEC 21.4.1)
    if rep['counts'].get('escaped_texts') != 1 or not any(
            '|#1 ' in (q.get('text') or '') for q in root.iter('question')):
        fail('U8', f'escaped trivia texts {rep["counts"]}')


def u9_credits(ctx):
    root, rep = F.credits_tree(ctx)
    lines = list(root.iter('line'))
    if len(lines) != 513 + len(F.PORT_CREDITS):
        fail('U9', f'{len(lines)} lines')
    bad = {ln.get('type') for ln in lines} - set(F.CREDIT_LINE_TYPES)
    if bad:
        fail('U9', f'types {bad}')
    texts = ' '.join(ln.get('text') or '' for ln in lines[-len(F.PORT_CREDITS):])
    for w in ('ChronoRixun', 'xml2-fix', 'Legends Classic', 'unofficial fan port'):
        if w not in texts:
            fail('U9', f'port block lacks {w!r}')
    # SPEC 21.4.1: XML1's 21 lines with '#N' written '|#N' (XMen2.exe reads '#NNN' as pen x = NNN), nothing else
    # changed, nothing left the renderer reads as a code
    x1 = [ln for ln in ctx.read_x1_xml(F.X1_CREDITS) if ln.tag == 'line']
    changed = [(a.get('text'), b.get('text')) for a, b in zip(x1, lines) if a.attrib != b.attrib]
    if rep['counts']['escaped_lines'] != 21 or len(changed) != 21 or \
            any(new != old.replace('#', '|#') for old, new in changed):
        fail('U9', f'{rep["counts"]["escaped_lines"]} escaped lines, changed {changed[:3]}...')
    left = [ln.get('text') for ln in lines if F.unescaped_menu_codes(ln.get('text'))]
    if left:
        fail('U9', f'credit texts with text codes left: {left[:3]}')
    if ('NYC Acolyte #1, Shadow', 'NYC Acolyte |#1, Shadow') not in changed:
        fail('U9', 'the late-game test\'s line "NYC Acolyte #1, Shadow" is not escaped')
    # the escape rules on hand-made texts (the renderer's reading, 0x5ef2e0)
    probes = {'#1': [(0, '#')], '|#1': [], '~12a~~': [(0, '~'), (4, '~'), (5, '~')], '|~|~': [], '$MENU_OK': [(0, '$')],
              'a|': [(1, '|')], '||': [], 'plain': []}
    for t, want in probes.items():
        if F.unescaped_menu_codes(t) != want or F.unescaped_menu_codes(F.escape_menu_text(t)):
            fail('U9', f'{t!r}: codes {F.unescaped_menu_codes(t)} (expected {want}), escaped '
                       f'{F.escape_menu_text(t)!r} -> {F.unescaped_menu_codes(F.escape_menu_text(t))}')
    INFO['U9 escaped credit lines'] = rep['counts']['escaped_lines']


def u16_credits_menus(ctx):
    """SPEC 21.4.2: the credits menus are XML2's with XML1's IGBs (re-framed on XML2's menu camera) and no image; the
    packages list XML1's IGB instead of x2m_credits."""
    import xmlb as XB
    for name, x1_rel, igb_name in F.CREDITS_MENUS:
        data, rep = F.credits_menu_igb(ctx, x1_rel)
        src = ctx.x1_path(x1_rel).read_bytes()
        if data is None or rep['problems'] or len(data) != len(src) or data == src:
            fail('U16', f'{name}: {x1_rel} not re-framed: {rep["problems"]}')
            continue
        cam = F.menu_igb_camera(data)
        if tuple(cam['pos']) != F.MENU_CAMERA_POS or cam['near'] != F.MENU_CAMERA_NEAR or \
                not all(cam['pos'][1] + cam['near'] <= d <= cam['pos'][1] + cam['far'] for d in F.MENU_OVERLAY_DEPTHS):
            fail('U16', f'{name}: camera {cam}')
        if F.reframe_menu_igb(data)[0] != data:
            fail('U16', f'{name}: the re-frame is not idempotent')
        base = XB.decode(ctx.base_index.path(f'UI/menus/{name}.XMLB').read_bytes())
        menu = F.credits_menu_tree(ctx, name, igb_name)
        want = dict(base.attrib, igb=igb_name, **F.CREDITS_MENU_SET)
        if menu.attrib != want or [c.attrib for c in menu] != [c.attrib for c in base] or not base.get('image') \
                or menu.get('image') != '':
            fail('U16', f'{name}: menu {menu.attrib} vs XML2\'s {base.attrib}')
        pkg = [(e.tag, e.get('filename')) for e in F.credits_menu_package(ctx, name, igb_name)]
        bpkg = [(e.tag, e.get('filename')) for e in
                XB.decode(ctx.base_index.path(f'{F.MENU_PKG_DIR}/{name}.PKGB').read_bytes())]
        if pkg != [('model', f'ui/menus/{igb_name}')] + [e for e in bpkg if e != ('model', 'ui/menus/x2m_credits')] \
                or ('model', 'ui/menus/x2m_credits') not in bpkg:
            fail('U16', f'{name}: package {pkg} vs XML2\'s {bpkg}')
    # the end credits keep XML2's endgame (the win bookkeeping, xml2-fix PostgameScript); XML1's backdrops: the
    # credits page (a textured plane, its 512x512 image inside the IGB) and a black plane alone
    from xml1build import igb_file as G
    ends = {n: (F.credits_menu_tree(ctx, n, i).get('endgame'),
                len(G.IgbFile(F.credits_menu_igb(ctx, x)[0]).objects_of('igImage'))) for n, x, i in F.CREDITS_MENUS}
    if ends != {'credits': (None, 1), 'credits_end': ('true', 0)}:
        fail('U16', f'endgame / images per menu: {ends}')
    INFO['U16 credits menus'] = [i for _, _, i in F.CREDITS_MENUS]


def u17_review_menu(ctx):
    """SPEC 21.4.3: the review menu is XML2's (both halves) without the Stats tab's two items, everything else in
    order; harness.py writes xml2-fix ReviewStats=0 for it and nothing for XML2's menu."""
    import harness
    x, e, removed = F.review_menu_trees(ctx)
    if x is None or removed != sorted(F.REVIEW_STATS_ITEMS):
        fail('U17', f'review_menu_trees: removed {removed}')
        return
    for ext, tree in (('.XMLB', x), ('.engb', e)):
        base = C.decode_xmlb(ctx.base_index.path(F.REVIEW_MENU_REL + ext).read_bytes())
        kept = [c for c in base if not (c.tag == 'item' and c.get('name') in F.REVIEW_STATS_ITEMS)]
        if len(kept) != len(base) - len(F.REVIEW_STATS_ITEMS) or tree.attrib != base.attrib or \
                [C.encode_xmlb(c) for c in tree] != [C.encode_xmlb(c) for c in kept]:
            fail('U17', f'{F.REVIEW_MENU_REL}{ext}: not XML2\'s minus {F.REVIEW_STATS_ITEMS}')
        names = [it.get('name') for it in tree.iter('item')]
        if tree.get('type') != F.REVIEW_MENU_TYPE or any(t not in names for t in F.REVIEW_TAB_ITEMS) or \
                any(n in names for n in F.REVIEW_STATS_ITEMS):
            fail('U17', f'{F.REVIEW_MENU_REL}{ext}: tabs {names}')
        if harness.review_stats_for(tree) != F.REVIEW_STATS_KEY[2] or harness.review_stats_for(base) is not None:
            fail('U17', f'harness.review_stats_for: {harness.review_stats_for(tree)!r} / XML2\'s '
                        f'{harness.review_stats_for(base)!r}')
    if (harness.REVIEW_STATS, harness.REVIEW_STATS_LABEL) != (F.REVIEW_STATS_KEY[2], F.REVIEW_STATS_ITEMS[0]) or \
            F.REVIEW_STATS_KEY[:2] != ('Game', 'ReviewStats'):
        fail('U17', f'harness {harness.REVIEW_STATS!r} {harness.REVIEW_STATS_LABEL!r} vs {F.REVIEW_STATS_KEY}')
    ini = harness.ini_text('windowed', 1280, 720, False, review_stats=harness.REVIEW_STATS).split('\r\n')
    game = ini[ini.index('[Game]') + 1:] if '[Game]' in ini else []
    if 'ReviewStats=0' not in game or 'ReviewStats' in harness.ini_text('windowed', 1280, 720, False):
        fail('U17', f'harness ini: {ini}')
    if harness.review_stats_for(ET.Element('MENU')) is not None or harness.review_stats_for(None) is not None:
        fail('U17', 'harness.review_stats_for takes a menu that is no REVIEW_PATHS_MENU')
    INFO['U17 review menu without'] = removed


def u10_codex(ctx):
    root, rep = F.codex_tree(ctx)
    names = [c.get('name') for c in root.iter('character')]
    if len(names) != 26 or 'MagnetoScripted' not in names or 'Magneto' in names:
        fail('U10', f'names {names}')


def u11_scripts():
    from xml1build import scripts as S
    x1, x2 = ctx_for('xml1'), ctx_for('xml2')
    g1, g2 = S.frontend_scripts(x1), S.frontend_scripts(x2)
    if sorted(g1) != sorted([S.FRONTEND_INTRO, S.POSTGAME_REF]) or sorted(g2) != [S.POSTGAME_REF]:
        fail('U11', f'generated {sorted(g1)} / {sorted(g2)}')
    intro = [l for l in g1[S.FRONTEND_INTRO]['lines'] if not l.startswith('#')]
    want = []
    for i, m in enumerate(('xi102', 'xi101', 'xi103', 'xi104', 'xi105'), 1):
        want += [f'startMovie("{m}", "afterMovie{i}")', f'waitsignal("afterMovie{i}")']
    if intro != want + ['mainMenuExit()']:
        fail('U11', f'intro {intro}')
    post = [l for l in g1[S.POSTGAME_REF]['lines'] if not l.startswith('#')]
    if post != ['startMovie("r505", "postgame")', 'waitsignal("postgame")', 'mainMenuExit()']:
        fail('U11', f'postgame {post}')
    from xml1build import scripts_lint as L
    for ref, g in g1.items():
        probs, _ = L.lint_lines(g['lines'], x1.xml2_api)
        if probs:
            fail('U11', f'{ref}: {probs}')
    if 'menus/main_back_main' in S.frontend_keep_xml2(x1) or 'menus/main_back_main' not in S.frontend_keep_xml2(x2):
        fail('U11', 'frontend_keep_xml2 per mode')


def u12_sound_plan():
    x1, x2 = ctx_for('xml1'), ctx_for('xml2')
    for stem in C.FRONTEND_MUSIC:
        rel = f'sounds/eng/{stem[0]}/{stem[1]}/{stem}.zss'
        p1, p2 = x1.planned_sound_banks().get(rel), x2.planned_sound_banks().get(rel)
        if not p1 or p1['kind'] != 'x1' or not p1.get('frontend') or not p2 or p2['kind'] != 'merged':
            fail('U12', f'{rel}: xml1 {p1 and p1["kind"]} / xml2 {p2 and p2["kind"]}')
    from xml1build import media as M
    if M.movie_duration(x1, 'i101') != 13.0 or M.movie_name(x1, 'i101') != 'xi101':
        fail('U12', 'media movie_duration / movie_name')


def u13_menu_zone(ctx):
    from xml1build import zones as Z
    z = Z.Zones.__new__(Z.Zones)
    z.ctx, z.counts = ctx, collections.Counter()
    got = z.menu_zone_xml2_entries('menu/main_back')
    if sorted(got) != [('bigconvmap', 'off'), ('xml', 'data/npcstat')] or z.menu_zone_xml2_entries('nyc/alison/nyc1_1_1'):
        fail('U13', f'menu zone entries {got}')


def u15_igct(ctx):
    """the save / load messages (SPEC 21.2.3): every base igct*.bnx that names XML2 gets the port's name in exactly
    those keys, nothing else changes, idempotent; igct.bnx's Load Game line is the wanted text."""
    files = F.igct_files(ctx)
    if 'igct.bnx' not in files:
        fail('U15', f'igct_files {files}')
    for rel in files:
        src = ctx.base_index.path(rel).read_bytes()
        new, keys = F.igct_retext(src)
        again, keys2 = F.igct_retext(new)
        if keys2 or again != new:
            fail('U15', f'{rel}: not idempotent ({keys2})')
        if F.IGCT_NAME.search(new):
            fail('U15', f'{rel}: still names XML2')
        a, b = src.split(b'\n'), new.split(b'\n')
        changed = [x.split(b'=', 1)[0].decode('latin-1') for x, y in zip(a, b) if x != y]
        if len(a) != len(b) or changed != keys:
            fail('U15', f'{rel}: changed lines {changed} vs keys {keys}')
        for x, y in zip(a, b):
            if x != y and F.IGCT_NAME.sub(b'', x) != y.replace(F.IGCT_PORT_NAME, b''):
                fail('U15', f'{rel}: {x!r} -> {y!r} changes more than the name')
        if rel == 'igct.bnx':
            INFO['U15 igct.bnx keys'] = keys
            if keys != ['EMSG_INSUF_SPC_DEVNUM_BLOCKS', 'EMSG_NO_DATA_DEVNUM', 'EMSG_NO_GAME_DEVNUM_BLOCKS']:
                fail('U15', f'igct.bnx keys {keys}')
            want_rel, key, want = F.IGCT_NO_DATA
            if F.igct_text(src, key) != 'No X-men Legends 2 save data present on hard disk.' or \
                    F.igct_text(new, key) != want:
                fail('U15', f'{key}: {F.igct_text(src, key)!r} -> {F.igct_text(new, key)!r}')
    INFO['U15 igct files'] = len(files)
    # Data/strings: the English texts only (the .XMLB half, keys, stays XML2's byte for byte)
    sx, se, ids = F.strings_retext(ctx)
    base_x = ctx.base_index.path(F.STRINGS_REL + '.XMLB').read_bytes()
    base_e = C.decode_xmlb(ctx.base_index.path(F.STRINGS_REL + '.engb').read_bytes())
    if C.encode_xmlb(sx) != base_x:
        fail('U15', 'Data/strings.XMLB would change')
    was = {el.get('id'): el.get('text') for el in base_e.iter('string')}
    now = {el.get('id'): el.get('text') for el in se.iter('string')}
    diff = sorted((k for k in was if was[k] != now.get(k)), key=int)
    if diff != ids or set(was) != set(now) or len(ids) != 19 or \
            any(F.NAME_TEXT.search(t or '') for t in now.values()):
        fail('U15', f'Data/strings.engb: changed {diff} vs renamed {ids}')
    damaged = 'X-Men Legends save data appears to be damaged and cannot be used. Press $MENU_ACCEPT to continue.'
    if now.get('3328') != damaged:
        fail('U15', f'Data/strings 3328 (the PC\'s damaged-save message): {now.get("3328")!r}')
    INFO['U15 strings ids'] = len(ids)


# ================================================================================================ build checks
def b_build(out):
    """the build's front-end files against the providers (the validator's V15-V17 do the full checks)."""
    b = C.build_options(out)
    mode = b.get('frontend') or 'xml2'
    INFO['build frontend'] = mode
    ctx = ctx_for(mode, out)
    reg = ctx.registry.entries
    if mode == 'xml1':
        for rel in (F.MENU_REL + '.XMLB', F.MENU_REL + '.engb', F.MENU_PKG_REL + '.PKGB', F.MENU_IGB_REL,
                    F.DR_REL + '.XMLB', F.REVIEW_REL + '.engb', F.CODEX_REL + '.engb', F.TRIVIA_REL + '.engb',
                    F.CREDITS_REL + '.engb', F.REVIEW_MENU_REL + '.XMLB', F.REVIEW_MENU_REL + '.engb') + tuple(
                        r for n, _, i in F.CREDITS_MENUS for r in (
                            f'UI/menus/{n}.XMLB', f'UI/menus/{i}.IGB', f'{F.MENU_PKG_DIR}/{n}.PKGB')):
            e = reg.get(C.norm(rel))
            if e is None or e['owner'] != 'frontend':
                fail('B', f'{rel}: owner {e and e["owner"]}')
        data, _ = F.menu_igb(ctx)
        p = ctx.out_index.path(F.MENU_IGB_REL)
        if p is None or p.read_bytes() != data:
            fail('B', f'{F.MENU_IGB_REL} differs from frontend.menu_igb')
        for rel in ('Maps/menu/main_back.XMLB', 'MotionPaths/menus/main_back.IGB'):
            e = reg.get(C.norm(rel))
            if e is None or e['owner'] != 'zones':
                fail('B', f'{rel}: not converted by zones')
        e = reg.get('scripts/menus/intro_normal.py')
        if e is None or e['owner'] != 'scripts':
            fail('B', 'intro_normal.py not generated')
        for rel in F.igct_files(ctx):
            want, keys = F.igct_retext(ctx.base_index.path(rel).read_bytes())
            p = ctx.out_index.path(rel)
            if keys and (p is None or p.read_bytes() != want or (reg.get(C.norm(rel)) or {}).get('owner') != 'frontend'):
                fail('B', f'{rel}: not frontend.igct_retext of the base file')
        sx, se, _ids = F.strings_retext(ctx)
        for ext, tree in (('.XMLB', sx), ('.engb', se)):
            p = ctx.out_index.path(F.STRINGS_REL + ext)
            if p is None or p.read_bytes() != C.encode_xmlb(tree) or \
                    (reg.get(C.norm(F.STRINGS_REL + ext)) or {}).get('owner') != 'frontend':
                fail('B', f'{F.STRINGS_REL}{ext}: not frontend.strings_retext')
    else:
        for n, e in reg.items():
            if e['owner'] == 'frontend':
                fail('B', f'{e["rel"]}: written by frontend under --frontend xml2')
            if n.startswith(C.FRONTEND_PREFIXES) or n in ('scripts/menus/intro_normal.py',
                                                          'scripts/menus/main_back_main.py'):
                fail('B', f'{e["rel"]}: XML2 front-end file registered under --frontend xml2')
        for rel in F.igct_files(ctx) + [F.STRINGS_REL + '.XMLB', F.STRINGS_REL + '.engb']:
            p = ctx.out_index.path(rel)
            if p is None or p.read_bytes() != ctx.base_index.path(rel).read_bytes():
                fail('B', f'{rel}: not XML2\'s under --frontend xml2')
    e = reg.get('scripts/x1/menus/postgame.py')
    if e is None or e['owner'] != 'scripts':
        fail('B', 'x1/menus/postgame.py not written')
    if mode == 'xml1':                                  # SPEC 23.1: the Danger Room rewardxp of the build's curve
        INFO['build xp_curve'] = C.xp_curve_mode(ctx)
        dr = ctx.read_out_xmlb(F.DR_REL + '.XMLB')
        curve = F.xp_curve(ctx)
        for c in dr.iter('COURSE'):
            for r in c.findall('REWARD'):
                want = str(F.course_reward_xp(ctx, curve, c.get('reclevel')))
                if r.get('rewardxp') is not None and r.get('rewardxp') != want:
                    fail('B', f'{c.get("name")}: rewardxp {r.get("rewardxp")} != {want} ({C.xp_curve_mode(ctx)})')


def _digest(p):
    h = hashlib.sha1()
    with open(p, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


# expected differences of a --frontend xml2 build against a build from before SPEC 21
COMPARE_EXPECTED_NEW = {'scripts/x1/menus/postgame.py'}


def b_compare(out, ref):
    """every file either build registered (plus the front-end files the design touches) byte-identical."""
    ra = C.Registry.load(Path(out) / '_build' / 'registry.json').entries
    rb = C.Registry.load(Path(ref) / '_build' / 'registry.json').entries
    ia, ib = C.FileIndex(out, exclude_top=C.META_NAMES + C.PROXY_PATTERNS), \
        C.FileIndex(ref, exclude_top=C.META_NAMES + C.PROXY_PATTERNS)
    touched = set()
    for pre in ('ui/menus/main.', 'ui/menus/x1_menu_main', 'packages/generated/maps/package/menus/main.',
                'maps/menu/main_back.', 'motionpaths/menus/main_back.', 'packages/generated/maps/menu/main_back.',
                'scripts/menus/', 'data/dangerroom.', 'data/review_paths.', 'data/codex.', 'data/trivia.',
                'data/credits.', 'data/zoneinfo.', 'data/items.', 'packages/generated/items.', 'sounds/eng/m/e/menu_',
                'textures/loading/', 'textures/comic/', 'textures/concept/', 'maps/arena/', 'igct',
                'data/strings.', 'ui/menus/credits', 'ui/menus/x1_menu_credits',
                'packages/generated/maps/package/menus/credits', 'ui/menus/review.'):
        touched |= {k for k in ia.keys() if k.startswith(pre)} | {k for k in ib.keys() if k.startswith(pre)}
    keys = sorted((set(ra) | set(rb) | touched) - {k for k in set(ra) | set(rb) if k.endswith('.sfd')})
    diff, only_a, only_b, same = [], [], [], 0
    for k in keys:
        pa, pb = ia.path(k), ib.path(k)
        if pa is None and pb is None:
            continue
        if pb is None:
            only_a.append(k)
        elif pa is None:
            only_b.append(k)
        elif pa.stat().st_size != pb.stat().st_size or _digest(pa) != _digest(pb):
            diff.append(k)
        else:
            same += 1
    INFO['compare identical'] = same
    INFO['compare frontend-touched files'] = len(touched)
    for k in only_a:
        if k not in COMPARE_EXPECTED_NEW:
            fail('C_only_in_out', k)
    for k in only_b:
        fail('C_only_in_ref', k)
    for k in diff:
        fail('C_differs', k)
    INFO['compare expected new'] = sorted(set(only_a) & COMPARE_EXPECTED_NEW)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out')
    ap.add_argument('--compare')
    a = ap.parse_args(argv)
    x1 = ctx_for('xml1')
    for name, fn in (('U1', lambda: u1_menu_igb(x1)), ('U2', lambda: u2_menu(x1)), ('U3', lambda: u3_dangerroom(x1)),
                     ('U4', lambda: u4_xp(x1)), ('U5', lambda: u5_equipment(x1)), ('U6', u6_namespace),
                     ('U7', lambda: u7_review(x1)), ('U8', lambda: u8_trivia(x1)), ('U9', lambda: u9_credits(x1)),
                     ('U10', lambda: u10_codex(x1)), ('U11', u11_scripts), ('U12', u12_sound_plan),
                     ('U13', lambda: u13_menu_zone(x1)), ('U14', u14_xp_curve), ('U15', lambda: u15_igct(x1)),
                     ('U16', lambda: u16_credits_menus(x1)), ('U17', lambda: u17_review_menu(x1))):
        try:
            fn()
        except Exception as ex:          # noqa: BLE001
            import traceback
            fail(name, f'crashed: {type(ex).__name__}: {ex}\n{traceback.format_exc()}')
    if a.out:
        b_build(Path(a.out).resolve())
        if a.compare:
            b_compare(Path(a.out).resolve(), Path(a.compare).resolve())
    for k, v in INFO.items():
        print(f'info {k}: {v}')
    for k, msgs in sorted(FAIL.items()):
        print(f'FAIL {k}: {len(msgs)}')
        for m in msgs[:15]:
            print(f'    - {m}')
    print('frontend_selftest:', 'PASS' if not FAIL else 'FAIL')
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
