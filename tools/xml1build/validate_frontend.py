"""xml1build.validate_frontend - validator checks V15-V17 for the front end (SPEC.md section 21; M2_DESIGN A.4.8,
B.5, C.5). Called by validate.Validator.run_all with the Validator (reads <out>, the registry, ctx.args) and a
Check. Pure: never writes game files.

  V15 front end    --frontend xml1: menu/main_back converted from XML1 (world zonescript + nosave, camera path
                   mp_camera, zoneinfo entry + loading screen); UI/menus/main = MAIN_MENU over an IGB that has every
                   item node; the xml2-fix MainMenuItems contract (frontend.MAIN_MENU_ITEMS are shown text items,
                   each with a usecmd but the Quit slot's; no label_option06 / label_option09, which XMen2.exe acts
                   on by itself); every usecmd command is an XMen2.exe console command, openmenu targets exist,
                   runscript code is valid; Begin Story runs frontend.BEGIN_STORY_CMD and no item newgame /
                   startgamedialog (XML1 had no difficulty prompt, SPEC 21.2.2); every base igct*.bnx that names XML2
                   rewritten by frontend without the name, igct.bnx EMSG_NO_DATA_DEVNUM = frontend.IGCT_NO_DATA,
                   Data/strings (both halves) by frontend with no English text naming XML2 (SPEC 21.2.3); up/down
                   chain (warn); one Play Online item (frontend.PLAY_ONLINE_CMD) in the up/down chain, not in the
                   Quit slot (SPEC 21.2.4); x1_menu_main.IGB = XML1's menu_main.igb re-framed
                   on XML2's menu camera with its buttons spread over XML1's span (frontend.menu_igb) with every node
                   the menu names, every shown button's nodes on screen (MENU_EDGE margin) and MENU_MIN_SPACING
                   apart, its camera at frontend.MENU_CAMERA_POS seeing XMen2.exe's overlay depths (dialogs, help
                   line); the package
                   resolves; the intro plays XML1's logos and ends in mainMenuExit();
                   menu_a / menu_c are XML1's music. Both front ends: the end-of-campaign script. --frontend xml2:
                   every front-end file (igct*.bnx and Data/strings included) is XML2's (nothing registered).
  V16 danger room  Data/dangerroom against XMen2.exe's loader (<= 8 grades, <= 25 courses per grade, <= 75) and the
                   build: arenas are converted zones, spawner / hero names in stats, one Titanium REWARD per course,
                   reward items are XML2 equipment, Freshman unlocked, an exam in every grade but the last, every
                   loadDangerRoomCourse literal names a course, disks for the other courses (warn), no XML1 points,
                   every rewardxp the --xp-curve value (SPEC 23.1: 0 with xml1, the reclevel curve with xml2).
  V17 review       review_paths caps / textures / movies, imageViewer literals = comic / concept values, zoneinfo
                   loading screens are Review entries (warn), comic rewards in XMen2.exe's four stats; codex names /
                   anims; trivia answers + acts; credits line types, no credit / trivia text with a character
                   XMen2.exe's text renderer reads as a code (frontend.unescaped_menu_codes: '#NNN', '~NN', '$NAME';
                   SPEC 21.4.1); the credits menus credits / credits_end = CREDITS_MENU over XML1's IGBs re-framed on XML2's
                   menu camera, XML2's endgame, no image, packages listing XML1's IGB (SPEC 21.4.2); UI/menus/review
                   (both halves) = XML2's REVIEW_PATHS_MENU without the Stats tab, the four category tabs kept
                   (SPEC 21.4.3).
"""
from __future__ import annotations

import collections
import re
from pathlib import Path

from . import common as C
from . import frontend as F

_IMAGE_VIEWER = re.compile(r'''imageViewer\s*\(\s*['"]([^'"]*)['"]''', re.I)
_LOAD_DR = re.compile(r'''loadDangerRoomCourse\s*\(\s*['"]([^'"]*)['"]''', re.I)
_START_MOVIE = re.compile(r'''startMovie\s*\(\s*['"]([^'"]+)['"]''')
_PERSONAL_ITEM = re.compile(r'''personalItem\s*\(\s*['"]([^'"]*)['"]''', re.I)
FRONTEND_TABLES = ('Data/dangerroom', 'Data/review_paths', 'Data/codex', 'Data/trivia', 'Data/credits')
FRONTEND_FILES = (F.MENU_REL + '.XMLB', F.MENU_REL + '.engb', F.MENU_PKG_REL + '.PKGB', F.MENU_IGB_REL,
                  'Scripts/menus/intro_normal.py', 'Scripts/menus/main_back_main.py')


def _console_cmds(ctx):
    names = set()
    p = ctx.research_path('scripts/xml2_console_cmds.txt')
    try:
        for line in p.read_text(encoding='utf-8', errors='replace').splitlines():
            m = re.match(r'^(\w+)\s+handler', line)
            if m:
                names.add(m.group(1).lower())
    except OSError:
        pass
    return names


def _tree(v, rel):
    return v.tree(rel)


def _registered_by(v, rel, owner):
    e = v.entry(rel)
    return e is not None and (e['owner'] == owner or owner in e.get('history', []))


def _raw_hits(v, rx, key, exts):
    """{literal: [rel]} of regex rx over every registered file with one of exts whose bytes contain `key`
    (lowercase bytes; decoded XMLB attribute values / latin-1 script text)."""
    hits = collections.defaultdict(list)
    for n, e in v.reg.items():
        if not n.endswith(exts):
            continue
        p = v.idx.path(n)
        if p is None:
            continue
        data = p.read_bytes()
        if key not in data.lower():
            continue
        if n.endswith('.py'):
            text = data.decode('latin-1')
        else:
            try:
                root = v.tree(n)
            except Exception:              # noqa: BLE001
                root = None
            if root is None:
                continue
            text = '\n'.join(val for el in root.iter() for val in el.attrib.values() if val)
        for m in rx.finditer(text):
            hits[m.group(1)].append(e['rel'])
    return hits


def _check_script(v, ck, rel, want_movies, what):
    """a generated front-end script: registered by scripts, V7-clean, plays want_movies (in order), ends in
    mainMenuExit()."""
    if not v.exists(rel):
        ck.error(f'{rel}: missing ({what})')
        return
    if not _registered_by(v, rel, 'scripts'):
        ck.error(f'{rel}: not written by the scripts module ({what})')
    res = v.script(rel)
    for p in (res.problems if res else []):
        (ck.error if p.severity == 'error' else ck.warn)(p.text(rel))
    calls = [c.name for c in (res.calls if res else [])]
    movies = res.literal_args('startMovie', 0) if res else []
    if [str(m).lower() for m in movies] != [m.lower() for m in want_movies]:
        ck.error(f'{rel}: startMovie targets {movies}, expected {want_movies} ({what})')
    if not calls or calls[-1] != 'mainMenuExit':
        ck.error(f'{rel}: the last statement is {calls[-1:] or "none"}, expected mainMenuExit() (mainmenuexit loads '
                 f'menu/main_back, 0x5f27a0)')
    missing = [str(m) for m in movies if not v.exists(v.movie_rel(str(m)))]
    if missing and v.no_movies:
        ck.warn(f'{rel}: movies {missing} not in this --no-movies build (a missing movie signals at once)')
    for m in (missing if not v.no_movies else ()):
        ck.error(f'{rel}: movie {v.movie_rel(m)} missing')
    ck.count('frontend_scripts_checked')


# ================================================================================================ V15
def v15_front_end(v, ck):
    ctx = v.ctx
    mode = C.frontend_mode(ctx)
    ck.set('frontend', mode)
    from . import scripts as S
    from . import media as M
    # end of campaign (both front ends, SPEC 21 D.1)
    _check_script(v, ck, C.script_rel(S.POSTGAME_REF), [M.movie_name(ctx, S.POSTGAME_MOVIE)],
                  'end of campaign, xml2-fix PostgameScript')
    if mode == 'xml2':
        bad = [f for f in FRONTEND_FILES + tuple(t + e for t in FRONTEND_TABLES for e in ('.XMLB', '.engb'))
               if v.entry(f) is not None]
        bad += [f for f in F.igct_files(ctx) + [F.STRINGS_REL + '.XMLB', F.STRINGS_REL + '.engb']
                if v.entry(f) is not None]
        for f in bad:
            ck.error(f'{v.entry(f)["rel"]}: registered by {v.entry(f)["owner"]} although --frontend xml2 keeps '
                     f'XML2\'s front end')
        for p in C.FRONTEND_PREFIXES:
            for n in v.reg:
                if n.startswith(p):
                    ck.error(f'{v.reg[n]["rel"]}: XML2 front-end file rewritten under --frontend xml2')
        ck.note('--frontend xml2: XML2\'s front end kept (V6 checks menu/main_back)')
        return
    # ---- menu/main_back = XML1's (the SPEC 11.1 exception is gone)
    for z in C.MENU_ZONES:
        zx = f'Maps/{z}.XMLB'
        if not _registered_by(v, zx, 'zones'):
            ck.error(f'{zx}: not converted from XML1 by zones (--frontend xml1: XML1\'s backdrop replaces XML2\'s)')
            continue
        world, _ = v.zone_world(z)
        world = world or {}
        if not world.get('zonescript'):
            ck.error(f'{z}: world has no zonescript (the camera path script)')
        elif not v.exists(C.script_rel(world['zonescript'])):
            ck.error(f'{z}: zonescript {world["zonescript"]} is not installed')
        if (world.get('nosave') or '').lower() != 'true':
            ck.error(f'{z}: world lacks nosave="true" (XML2\'s menu backdrop has it)')
        mp = 'MotionPaths/menus/main_back.IGB'
        data = v.read(mp)
        if data is None or b'mp_camera\x00' not in data:
            ck.error(f'{mp}: missing or without the mp_camera object')
        elif not _registered_by(v, mp, 'zones'):
            ck.error(f'{mp}: still XML2\'s camera path')
        zi = v.zoneinfo()
        ent = None
        for ext, d in zi.items():
            if d and z in d:
                ent = d[z][0]
        if ent is None:
            ck.error(f'Data/zoneinfo: no entry for {z}')
        else:
            load = ent.get('loading')
            if not load:
                ck.error(f'Data/zoneinfo {z}: no loading screen')
            elif not v.exists(f'{load}.igb'):
                ck.error(f'Data/zoneinfo {z}: loading screen {load}.IGB missing')
            elif C.norm(load) != C.norm(C.FRONTEND_MENU_LOADING):
                ck.warn(f'Data/zoneinfo {z}: loading {load}, expected {C.FRONTEND_MENU_LOADING}')
    # ---- the menu file
    cmds = _console_cmds(ctx)
    igb_names = set()
    shown_buttons = set()
    for ext in ('.XMLB', '.engb'):
        rel = F.MENU_REL + ext
        if not _registered_by(v, rel, 'frontend'):
            ck.error(f'{rel}: not written by the frontend module')
        root = _tree(v, rel)
        if root is None:
            ck.error(f'{rel}: missing or does not decode')
            continue
        if root.get('type') != 'MAIN_MENU':
            ck.error(f'{rel}: type {root.get("type")!r}, expected MAIN_MENU')
        if (root.get('fullscreen') or '').lower() != 'false':
            ck.error(f'{rel}: fullscreen must be "false" so the backdrop zone shows')
        igb = root.get('igb') or ''
        igb_rel = f'UI/menus/{igb}.IGB'
        data = v.read(igb_rel)
        if data is None:
            ck.error(f'{rel}: igb {igb!r} -> {igb_rel} missing')
            continue
        items = {it.get('name'): it for it in root.iter('item')}
        for name in items:
            if (b'\x00' + (name or '').encode() + b'\x00') not in data and not re.search(
                    rb'[\x00-\x04]' + re.escape((name or '').encode()) + rb'\x00', data):
                ck.error(f'{rel}: item {name!r} is not a node of {igb_rel} (the menu binds items to IGB nodes)')
        # xml2-fix [Game] MainMenuItems names these for XMen2.exe's MAIN_MENU slots (mouse 0x5c933f..0x5c939f,
        # Quit 0x5c9691..0x5c99a1): each a focusable text item, all but the Quit slot with their action in a usecmd
        # (keys and pad work without the DLL); the Quit slot's item without one (the exe quits on it and replaces
        # its usecmd with "Bidon", 0x5c99d5)
        for k, name in enumerate(F.MAIN_MENU_ITEMS):
            it = items.get(name)
            if it is None:
                ck.error(f'{rel}: no item {name!r} (xml2-fix MainMenuItems slot {k})')
                continue
            if (it.get('enabled') or '').lower() == 'false' or (it.get('hide') or '').lower() == 'true' \
                    or it.get('type') or not it.get('text'):
                ck.error(f'{rel}: {name} (MainMenuItems slot {k}) is not a shown, focusable text item')
            if k == F.MAIN_MENU_QUIT_SLOT:
                if it.get('usecmd'):
                    ck.error(f'{rel}: {name} is the Quit slot but has usecmd {it.get("usecmd")!r}')
            elif not it.get('usecmd'):
                ck.error(f'{rel}: {name} (MainMenuItems slot {k}) has no usecmd (keys / pad would do nothing '
                         f'without xml2-fix)')
        for name in F.EXE_MENU_FORBIDDEN:
            if name in items:
                ck.error(f'{rel}: item {name!r} present (XMen2.exe acts on that name by itself: 0x5c988e Danger '
                         f'Room gate / 0x5c9803 online menu)')
        for name, it in items.items():
            cmd = it.get('usecmd')
            for part in (cmd.split(';') if cmd else ()):
                words = part.strip().split(None, 1)
                if not words:
                    continue
                if words[0].lower() not in cmds:
                    ck.error(f'{rel}: {name} usecmd {part!r}: {words[0]!r} is not an XMen2.exe console command')
                elif words[0].lower() == 'openmenu':
                    tgt = (words[1] if len(words) > 1 else '').strip()
                    if not v.exists(f'UI/menus/{tgt}.xmlb'):
                        ck.error(f'{rel}: {name} opens menu {tgt!r}, which has no UI/menus/{tgt}.XMLB')
                elif words[0].lower() == 'runscript':
                    code = (words[1] if len(words) > 1 else '').strip()
                    res = v.checker.check_console_code(code, x1_output=True)
                    for p in res.problems:
                        (ck.error if p.severity == 'error' else ck.warn)(f'{rel}: {name} usecmd: {p.kind}: {p.msg}')
            for d in ('up', 'down'):
                t = it.get(d)
                if t and t not in items:
                    ck.warn(f'{rel}: {name} {d}={t!r} is not an item')
            # XML1 asked for no difficulty (SPEC 21.2.2): no item may open XMen2.exe's prompt
            for c, _ in F.usecmd_commands(cmd):
                if c in F.NEW_GAME_PROMPT_CMDS:
                    ck.error(f'{rel}: {name} usecmd {cmd!r} runs {c}, which opens XMen2.exe\'s difficulty prompt '
                             f'(XML1 had none; Begin Story runs {F.BEGIN_STORY_CMD!r})')
        # Begin Story = XMen2.exe's newgame without the prompt: resetgame, then what its Normal option runs
        begin = items.get(F.MAIN_MENU_ITEMS[0])
        if begin is not None and begin.get('usecmd') != F.BEGIN_STORY_CMD:
            ck.error(f'{rel}: Begin Story ({F.MAIN_MENU_ITEMS[0]}) usecmd {begin.get("usecmd")!r}, expected '
                     f'{F.BEGIN_STORY_CMD!r} (a New Game on Normal without the difficulty prompt, SPEC 21.2.2)')
        # the focus chain: down from the startactive item visits every focusable item and returns
        start = next((n for n, it in items.items() if (it.get('startactive') or '').lower() == 'true'), None)
        chain, cur = [], start
        while cur and cur not in chain and len(chain) < 50:
            chain.append(cur)
            cur = (items.get(cur).get('down') if items.get(cur) is not None else None)
        focusable = [n for n, it in items.items() if it.get('down') or it.get('up')]
        if cur != start or set(chain) != set(focusable):
            ck.warn(f'{rel}: the up/down focus chain {chain} is not one cycle over {focusable}')
        # Play Online (SPEC 21.2.4): one shown text item runs XMen2.exe's own line for XML2's item, and the keys / pad
        # reach it (XMen2.exe's mouse has no slot for it; a console `openmenu online` on a fresh boot crashes at Host /
        # Join, the item's accept first avoids that)
        online = [n for n, it in items.items() if F.PLAY_ONLINE_CMD in
                  [f'{c} {r}'.strip() for c, r in F.usecmd_commands(it.get('usecmd'))]]
        if len(online) != 1:
            ck.error(f'{rel}: {len(online)} items run {F.PLAY_ONLINE_CMD!r} (expected one: Play Online)')
        else:
            it = items[online[0]]
            if not it.get('text') or it.get('type') or (it.get('hide') or '').lower() == 'true' \
                    or (it.get('enabled') or '').lower() == 'false':
                ck.error(f'{rel}: Play Online ({online[0]}) is not a shown, focusable text item')
            if online[0] not in chain:
                ck.error(f'{rel}: Play Online ({online[0]}) is not in the up/down chain {chain} (keys / pad '
                         f'cannot reach it)')
            if online[0] in F.MAIN_MENU_ITEMS[F.MAIN_MENU_QUIT_SLOT:]:
                ck.error(f'{rel}: Play Online ({online[0]}) is named for xml2-fix MainMenuItems\' Quit slot')
        shown_buttons |= {n for n, it in items.items() if it.get('text') and not it.get('type')
                          and (it.get('hide') or '').lower() != 'true'}
        igb_names |= set(items)
        ck.set('menu_items', len(items))
    # ---- the menu IGB: XML1's re-framed on XML2's menu camera, with every node the menu file names
    data = v.read(F.MENU_IGB_REL)
    if data is None:
        ck.error(f'{F.MENU_IGB_REL}: missing')
    else:
        if ctx.x1_path(F.X1_MENU_IGB) is not None:
            want, frame = F.menu_igb(ctx)
            if want is None:
                ck.error(f'{F.MENU_IGB_REL}: XML1\'s {F.X1_MENU_IGB} does not re-frame / space: '
                         f'{frame["problems"][:3]}')
            elif want != data:
                ck.error(f'{F.MENU_IGB_REL}: differs from XML1\'s {F.X1_MENU_IGB} re-framed on XML2\'s menu camera '
                         f'with its buttons spread over XML1\'s span (frontend.menu_igb)')
        # XMen2.exe draws its dialogs / help line in the menu's layer at fixed depths, through the IGB's camera
        # (SPEC 21.2): the camera must sit where XML2's menu cameras sit and see those depths
        cam = F.menu_igb_camera(data)
        if cam.get('problem'):
            ck.error(f'{F.MENU_IGB_REL}: camera: {cam["problem"]}')
        else:
            if any(abs(a - b) > 1e-3 for a, b in zip(cam['pos'], F.MENU_CAMERA_POS)):
                ck.error(f'{F.MENU_IGB_REL}: camera {cam["name"]!r} at {cam["pos"]}, not XML2\'s menu camera '
                         f'{F.MENU_CAMERA_POS} (the mouse frame and the dialogs assume it)')
            y = cam['pos'][1]
            for depth in F.MENU_OVERLAY_DEPTHS:
                if cam['near'] is None or cam['far'] is None or not y + cam['near'] <= depth <= y + cam['far']:
                    ck.error(f'{F.MENU_IGB_REL}: camera near {cam["near"]} / far {cam["far"]} clip XMen2.exe\'s '
                             f'overlay depth {depth} (dialogs / help line not drawn)')
            ck.set('menu_igb_camera', f'{cam["name"]} {tuple(round(c, 2) for c in cam["pos"])} '
                                      f'near {cam["near"]} far {cam["far"]}')
        fields = F.igb_string_fields(data)
        for name in F.menu_node_names():
            if not fields.get(name):
                ck.error(f'{F.MENU_IGB_REL}: no node {name!r}')
        # every shown button on screen: its text anchor, mesh and focus model inside the camera's view (the virtual
        # screen around the camera), and the buttons apart (SPEC 21.2.4)
        zs = F.menu_button_z(data)
        lo, hi = F.MENU_CAMERA_POS[2] - F.MENU_SCREEN[1] / 2 + F.MENU_EDGE, \
            F.MENU_CAMERA_POS[2] + F.MENU_SCREEN[1] / 2 - F.MENU_EDGE
        for name in sorted(shown_buttons):
            for k in F.MENU_BUTTON_KINDS:
                z = zs.get(name + k)
                if z is None:
                    ck.error(f'{F.MENU_IGB_REL}: shown button {name}: no node {name + k} in world coordinates')
                elif not lo <= z <= hi:
                    ck.error(f'{F.MENU_IGB_REL}: {name + k} at z {z:.1f}, outside the screen with its margin '
                             f'({lo}..{hi}): the button is cut or not drawn')
        texts = sorted(zs.get(n, 0.0) for n in shown_buttons)
        gaps = [b - a for a, b in zip(texts, texts[1:])]
        if gaps and min(gaps) < F.MENU_MIN_SPACING:
            ck.error(f'{F.MENU_IGB_REL}: shown buttons {min(gaps):.1f} apart (< {F.MENU_MIN_SPACING}): they overlap')
        ck.set('menu_button_spacing', round(min(gaps), 2) if gaps else None)
    # ---- the package
    pk = F.MENU_PKG_REL + '.PKGB'
    ents = v.scan.pkg.get(C.norm(pk))
    if ents is None:
        ck.error(f'{pk}: missing or not registered')
    else:
        for kind, fn in ents:
            cands = C.package_entry_files(kind, fn)
            if cands and not any(v.exists(c) for c in cands):
                ck.error(f'{pk}: {kind} {fn} resolves to nothing')
        names = {C.norm(fn) for _, fn in ents}
        for want in (f'ui/menus/{F.MENU_IGB_NAME}', 'ui/menus/main'):
            if want not in names:
                ck.error(f'{pk}: does not list {want}')
    # ---- the PC's save / load messages (igct*.bnx, 0x55e9b0): the port's name wherever XML2's own names XML2
    named = 0
    for rel in F.igct_files(ctx):
        if not F.IGCT_NAME.search(ctx.base_index.path(rel).read_bytes()):
            continue
        named += 1
        data = v.read(rel)
        if not _registered_by(v, rel, 'frontend'):
            ck.error(f'{rel}: not written by the frontend module (XML2\'s save / load messages name X-Men Legends 2)')
        elif data is None or F.IGCT_NAME.search(data):
            ck.error(f'{rel}: still names XML2 ({F.IGCT_NAME.pattern.decode()})')
    rel, key, want = F.IGCT_NO_DATA
    got = F.igct_text(v.read(rel) or b'', key)
    if got != want:
        ck.error(f'{rel}: {key} (the Load Game dialog without saves) is {got!r}, expected {want!r}')
    ck.set('igct_files_renamed', named)
    # ... and Data/strings' English texts (3328 is the PC's damaged-save message, 0x55eb30 code 43)
    srel = F.STRINGS_REL + '.engb'
    st = _tree(v, srel)
    left = [el.get('id') for el in (st.iter('string') if st is not None else ()) if F.NAME_TEXT.search(el.get('text') or '')]
    if left:
        ck.error(f'{srel}: texts {left[:8]} still name XML2 (frontend.strings_retext)')
    if not _registered_by(v, srel, 'frontend') or not _registered_by(v, F.STRINGS_REL + '.XMLB', 'frontend'):
        ck.error(f'{F.STRINGS_REL}: not written by the frontend module (both halves; SPEC 21.2.3)')
    # ---- intro
    _check_script(v, ck, 'Scripts/menus/intro_normal.py', [M.movie_name(ctx, m) for m in S.FRONTEND_INTRO_MOVIES],
                  "XML1's intro logos")
    # ---- menu music
    plan = ctx.planned_sound_banks()
    for stem in C.FRONTEND_MUSIC:
        rel = f'sounds/eng/{stem[0]}/{stem[1]}/{stem}.zss'
        pe = plan.get(rel)
        e = v.entry(rel)
        if not pe or pe.get('kind') != 'x1':
            ck.error(f'{rel}: not planned as XML1 music (kind {pe and pe.get("kind")})')
        if e is None:
            ck.error(f'{rel}: not installed by media')
            continue
        src = e.get('source') or ''
        if 'sound/out/merged' in C.norm(src):
            ck.error(f'{rel}: installed from the merged XML2 bank {src}, expected XML1\'s menu music')
        f = v.banks.facts(C.norm(rel))
        if f.get('error'):
            ck.error(f'{rel}: does not parse: {f["error"]}')
        ck.count('frontend_music_banks')


# ================================================================================================ V16
def v16_danger_room(v, ck):
    ctx = v.ctx
    if C.frontend_mode(ctx) != 'xml1':
        ck.note('--frontend xml2: XML2\'s Danger Room table kept (not checked)')
        return
    names = v.stats_names()
    heroes = {(el.get('name') or '').lower() for el in (v.stats()['variants'].get('.engb') or {}).get('herostat', [])}
    conv = set(v.converted_zones())
    items = {}
    it_root = v.tree('Data/items.engb')
    for it in (it_root.iter('item') if it_root is not None else ()):
        items[(it.get('name') or '').lower()] = it
    course_names, startloaded = set(), set()
    curve, xp_mode = F.xp_curve(ctx), C.xp_curve_mode(ctx)
    for ext in ('.engb', '.XMLB'):
        rel = F.DR_REL + ext
        root = _tree(v, rel)
        if root is None:
            ck.error(f'{rel}: missing or does not decode')
            continue
        if not _registered_by(v, rel, 'frontend'):
            ck.error(f'{rel}: not written by the frontend module')
        arenas = {a.get('title'): a for a in root.iter('ARENA')}
        for t, a in arenas.items():
            z = C.norm(a.get('zone') or '')
            if z not in conv:
                ck.error(f'{rel}: arena {t!r} zone {z!r} is not a converted zone')
        grades = list(root.iter('GRADE'))
        if len(grades) > F.DR_GRADE_LIMIT:
            ck.error(f'{rel}: {len(grades)} grades > {F.DR_GRADE_LIMIT} (0x4d43a5)')
        if grades and (grades[0].get('unlocked') or '').lower() != 'true':
            ck.error(f'{rel}: the first grade {grades[0].get("name")!r} is not unlocked (nothing would be available)')
        total = 0
        for gi, g in enumerate(grades):
            cs = list(g.iter('COURSE'))
            total += len(cs)
            if len(cs) > F.DR_COURSES_PER_GRADE:
                ck.error(f'{rel}: grade {g.get("name")!r} has {len(cs)} courses > {F.DR_COURSES_PER_GRADE} (0x4d4463)')
            if gi < len(grades) - 1 and not any((c.get('rewardexam') or '').lower() == 'true' for c in cs):
                ck.error(f'{rel}: grade {g.get("name")!r} has no rewardexam course (the next grade never opens)')
            for c in cs:
                cn = c.get('name') or ''
                course_names.add(cn.lower())
                if c.get('arena') not in arenas:
                    ck.error(f'{rel}: {cn}: arena {c.get("arena")!r} is no ARENA title')
                for k in F.DR_DROP_ATTRS:
                    if k in c.attrib:
                        ck.error(f'{rel}: {cn}: XML1 attribute {k!r} left (XMen2.exe never reads it)')
                if c.get('hero') and c.get('hero').lower() not in heroes:
                    ck.error(f'{rel}: {cn}: hero {c.get("hero")!r} is not a herostat hero')
                for s in c:
                    if s.tag in ('SPAWNER', 'MUSTDIE', 'MUSTSURVIVE'):
                        ch = (s.get('character') or '').lower()
                        if ch not in names:
                            ck.error(f'{rel}: {cn}: {s.tag} character {s.get("character")!r} is not in the stats')
                rewards = [r for r in c.findall('REWARD') if r.get('type') == 'Titanium']
                if not rewards:
                    ck.error(f'{rel}: {cn}: no Titanium REWARD')
                for r in rewards:
                    xp = r.get('rewardxp')
                    if xp is not None and xp != str(F.course_reward_xp(ctx, curve, c.get('reclevel'))):
                        ck.error(f'{rel}: {cn}: rewardxp {xp} is not the --xp-curve {xp_mode} value '
                                 f'{F.course_reward_xp(ctx, curve, c.get("reclevel"))} (SPEC 23.1)')
                    ri = (r.get('rewarditem') or '').lower()
                    if ri:
                        it = items.get(ri)
                        if it is None:
                            ck.error(f'{rel}: {cn}: reward item {r.get("rewarditem")!r} is not in Data/items')
                        elif it.get('type') != 'equipment':
                            ck.warn(f'{rel}: {cn}: reward item {r.get("rewarditem")!r} is type {it.get("type")!r} '
                                    f'(XML1 equipment downgraded)')
                        else:
                            ck.count('reward_items_equipment')
        if total > F.DR_COURSES_TOTAL:
            ck.error(f'{rel}: {total} courses > {F.DR_COURSES_TOTAL} (record table at 0x784e00)')
        if ext == '.engb':
            ck.set('courses', total)
            ck.set('grades', len(grades))
            ck.set('arenas', len(arenas))
            startloaded = {(c.get('name') or '').lower() for c in root.iter('COURSE')
                           if (c.get('startloaded') or '').lower() == 'true'}
    # loadDangerRoomCourse literals in installed content
    hits = _raw_hits(v, _LOAD_DR, b'loaddangerroomcourse', ('.xmlb', '.engb', '.py'))
    disks = set()
    for lit, rels in sorted(hits.items()):
        for name in re.split(r'[\s,]+', lit):
            if not name:
                continue
            disks.add(name.lower())
            if name.lower() not in course_names:
                ck.error(f'loadDangerRoomCourse({name!r}) in {sorted(set(rels))[:3]}: no such course')
    ck.set('disk_literals', len(disks))
    if course_names:
        no_disk = sorted(n for n in course_names if n not in disks and n not in startloaded)
        for n in no_disk:
            ck.warn(f'course {n.upper()}: neither startloaded nor loaded by any disk (never available)')


# ================================================================================================ V17
def v17_review(v, ck):
    ctx = v.ctx
    if C.frontend_mode(ctx) != 'xml1':
        ck.note('--frontend xml2: XML2\'s review / codex / trivia / credits kept (not checked)')
        return
    heroes = {(el.get('name') or '').lower() for el in (v.stats()['variants'].get('.engb') or {}).get('herostat', [])}
    values = collections.defaultdict(set)
    for ext in ('.engb', '.xmlb'):
        rel = F.REVIEW_REL + ext
        root = _tree(v, rel)
        if root is None:
            ck.error(f'{rel}: missing or does not decode')
            continue
        if not _registered_by(v, rel, 'frontend'):
            ck.error(f'{rel}: not written by the frontend module')
        per = collections.Counter()
        no_movie = []
        for it in root.iter('item'):
            t = (it.get('type') or '').lower()
            val = C.norm(it.get('value') or '')
            per[t] += 1
            values[t].add(val)
            if t in ('load', 'comic', 'concept'):
                if not v.exists(f'{val}.igb'):
                    ck.error(f'{rel}: {t} {val}: Textures file {val}.IGB missing')
                if t in ('comic', 'concept') and t not in val:
                    ck.error(f'{rel}: {t} value {val} lacks "{t}" (imageViewer picks the category by substring, 0x49e440)')
            elif t == 'cin':
                if val != 'credits' and not v.exists(v.movie_rel(val)):
                    if v.no_movies:
                        no_movie.append(val)
                    else:
                        ck.error(f'{rel}: cin {val}: {v.movie_rel(val)} missing')
            if t == 'comic':
                if 'reward_focus' in it.attrib:
                    ck.error(f'{rel}: {val}: reward_focus (XMen2.exe reads strength/speed/body/mind only, 0x4ae706)')
                if it.get('group') and it.get('group').lower() not in heroes:
                    ck.warn(f'{rel}: {val}: group {it.get("group")!r} is not a herostat hero')
        if no_movie and ext == '.engb':
            ck.warn(f'{rel}: {len(no_movie)} cin entries have no movie in this --no-movies build: {no_movie[:6]}...')
        for t, n in per.items():
            if n > F.REVIEW_MAX_PER_TYPE:
                ck.error(f'{rel}: {n} {t} entries > {F.REVIEW_MAX_PER_TYPE} per category (0x4ae646)')
            ck.set(f'review_{t}', n)
    # imageViewer literals in installed content
    hits = _raw_hits(v, _IMAGE_VIEWER, b'imageviewer', ('.xmlb', '.engb', '.py'))
    for lit, rels in sorted(hits.items()):
        val = C.split_ext(C.norm(lit))[0]
        cat = 'concept' if 'concept' in val else 'comic' if 'comic' in val else None
        if cat is None:
            ck.error(f'imageViewer({lit!r}) in {sorted(set(rels))[:3]}: neither "comic" nor "concept" (unlocks nothing)')
        elif val.split('.', 1)[0] not in values.get(cat, set()):
            ck.error(f'imageViewer({lit!r}) in {sorted(set(rels))[:3]}: no Review {cat} entry {val}')
        else:
            ck.count('image_viewer_ok')
    # zoneinfo loading screens are Review entries
    zi = v.zoneinfo()
    for ext, d in zi.items():
        if not d or ext != '.engb':
            continue
        miss = sorted({C.norm(z[0].get('loading')) for n, z in d.items() if z and z[0].get('loading')} -
                      values.get('load', set()))
        x1_miss = [m for m in miss if any(C.norm(z[0].get('loading') or '') == m and n in set(v.converted_zones())
                                          for n, z in d.items() if z)]
        if x1_miss:
            ck.warn(f'Data/zoneinfo{ext}: {len(x1_miss)} loading screens of XML1 zones are no Review load entry '
                    f'(they can never unlock): {x1_miss[:8]}')
    # codex
    stats = v.stats()['by_name']
    for ext in ('.engb', '.XMLB'):
        rel = F.CODEX_REL + ext
        root = _tree(v, rel)
        if root is None:
            ck.error(f'{rel}: missing or does not decode')
            continue
        for c in root.iter('character'):
            nm = (c.get('name') or '').lower()
            if nm not in stats:
                ck.error(f'{rel}: character {c.get("name")!r} is not in the stats')
                continue
            if ext == '.engb':
                animdb = stats[nm][1].get('characteranims')
                has = F.anim_db_has(ctx, animdb, c.get('anim') or '')
                if not has:
                    ck.warn(f'{rel}: {c.get("name")}: anim {c.get("anim")!r} not found in Actors/{animdb}.IGB')
                ck.count('codex_characters')
    # trivia
    from collections import Counter
    for ext in ('.engb', '.XMLB'):
        rel = F.TRIVIA_REL + ext
        root = _tree(v, rel)
        if root is None:
            ck.error(f'{rel}: missing or does not decode')
            continue
        per_act = Counter()
        for q in root.iter('question'):
            ans = q.findall('answer')
            if not 2 <= len(ans) <= 5:
                ck.error(f'{rel}: {q.get("text", "")[:50]!r}: {len(ans)} answers (2..5)')
            if sum(1 for a in ans if (a.get('correct') or '').lower() == 'true') != 1:
                ck.error(f'{rel}: {q.get("text", "")[:50]!r}: not exactly one correct answer')
            per_act[q.get('act') or '1'] += 1
            for el in [q] + ans:            # XMen2.exe's renderer codes: literal ones written '|c' (SPEC 21.4.1)
                c = F.unescaped_menu_codes(el.get('text'))
                if c:
                    ck.error(f'{rel}: trivia text {el.get("text")[:50]!r}: {"".join(ch for _, ch in c)!r} not '
                             f'escaped (XMen2.exe reads it as a text code; write "|c")')
        for act in F.trivia_acts(ctx):
            if not per_act.get(str(act)):
                ck.warn(f'{rel}: act {act} has a trivia console but no question')
        if ext == '.engb':
            ck.details['trivia_per_act'] = dict(per_act)
    # credits
    for ext in ('.engb', '.xmlb'):
        rel = F.CREDITS_REL + ext
        root = _tree(v, rel)
        if root is None:
            ck.error(f'{rel}: missing or does not decode')
            continue
        bad = sorted({ln.get('type') for ln in root.iter('line')} - set(F.CREDIT_LINE_TYPES))
        if bad:
            ck.error(f'{rel}: line types {bad} are not XML2 credit line types')
        # XMen2.exe's text renderer reads '#NNN' (pen x), '~NN' (colour), '$NAME' (a token) inside the text: a
        # literal one must be written '|c' (SPEC 21.4.1; "NYC Acolyte #1, Shadow" drew over itself)
        coded = [(ln.get('text'), F.unescaped_menu_codes(ln.get('text'))) for ln in root.iter('line')]
        coded = [(t, c) for t, c in coded if c]
        for t, c in coded[:8]:
            ck.error(f'{rel}: credit line {t!r}: {"".join(ch for _, ch in c)!r} not escaped (XMen2.exe reads it as a '
                     f'text code; write "|c")')
        if len(coded) > 8:
            ck.error(f'{rel}: {len(coded) - 8} more credit lines with unescaped text codes')
        if ext == '.engb':
            ck.set('credit_lines', sum(1 for _ in root.iter('line')))
            ck.set('credit_lines_escaped', sum(1 for ln in root.iter('line') if '|' in (ln.get('text') or '')))
    # the credits menus: XML2's CREDITS_MENU over XML1's IGB (re-framed on XML2's menu camera), no XML2 image
    # (SPEC 21.4.2)
    for name, x1_rel, igb_name in F.CREDITS_MENUS:
        rel = f'UI/menus/{name}.XMLB'
        root = _tree(v, rel)
        if root is None:
            ck.error(f'{rel}: missing or does not decode')
            continue
        if not _registered_by(v, rel, 'frontend'):
            ck.error(f'{rel}: not written by the frontend module (XML2\'s credits menu shows XML2\'s hero collage)')
        base = v.ctx.read_base_xmlb(rel)
        if root.get('type') != 'CREDITS_MENU' or root.get('igb') != igb_name or \
                root.get('endgame') != base.get('endgame'):
            ck.error(f'{rel}: type {root.get("type")!r} igb {root.get("igb")!r} endgame {root.get("endgame")!r}, '
                     f'expected CREDITS_MENU over {igb_name} with XML2\'s endgame {base.get("endgame")!r}')
        for k, want in F.CREDITS_MENU_SET.items():
            if root.get(k) != want:
                ck.error(f'{rel}: {k}={root.get(k)!r}, expected {want!r} (a menu opens with the menu manager\'s last '
                         f'image as its background sprite unless it empties it: XML2\'s collage, the online art)')
        igb_rel = f'UI/menus/{igb_name}.IGB'
        data = v.read(igb_rel)
        want, rep = F.credits_menu_igb(ctx, x1_rel)
        if data is None:
            ck.error(f'{igb_rel}: missing')
        elif want is None or want != data:
            ck.error(f'{igb_rel}: not XML1\'s {x1_rel} re-framed on XML2\'s menu camera '
                     f'({rep["problems"][:2] or "differs"})')
        else:
            cam = F.menu_igb_camera(data)
            y = cam['pos'][1]
            if any(abs(a - b) > 1e-3 for a, b in zip(cam['pos'], F.MENU_CAMERA_POS)) or \
                    not all(y + cam['near'] <= d <= y + cam['far'] for d in F.MENU_OVERLAY_DEPTHS):
                ck.error(f'{igb_rel}: camera {cam["pos"]} near {cam["near"]} far {cam["far"]} does not see '
                         f'XMen2.exe\'s text depths {F.MENU_OVERLAY_DEPTHS} (the credits would not be drawn)')
        pk = f'{F.MENU_PKG_DIR}/{name}.PKGB'
        ents = v.scan.pkg.get(C.norm(pk))
        names = {C.norm(fn) for _, fn in (ents or ())}
        if ents is None or f'ui/menus/{igb_name}' not in names or f'ui/menus/{name}' not in names:
            ck.error(f'{pk}: missing, or does not list ui/menus/{igb_name} and ui/menus/{name}')
        elif any(n.startswith('ui/menus/') and n not in (f'ui/menus/{igb_name}', f'ui/menus/{name}') for n in names):
            ck.error(f'{pk}: still lists XML2\'s credits IGB ({sorted(names)})')
        ck.count('credits_menus_ok')
    # the review menu: XML2's REVIEW_PATHS_MENU without the Stats tab (XML1 had none; XML2's lists its acts 1-5 from
    # exe code), the four category tabs kept; xml2-fix ReviewStats=0 wraps the tab change at 4 (SPEC 21.4.3)
    want_x, want_e, _removed = F.review_menu_trees(ctx)
    for ext, want in (('.XMLB', want_x), ('.engb', want_e)):
        rel = F.REVIEW_MENU_REL + ext
        root = _tree(v, rel)
        if root is None:
            ck.error(f'{rel}: missing or does not decode')
            continue
        if not _registered_by(v, rel, 'frontend'):
            ck.error(f'{rel}: not written by the frontend module (XML2\'s review menu has a Stats tab listing XML2\'s '
                     f'acts 1-5)')
        names = [it.get('name') for it in root.iter('item')]
        stats = [n for n in names if n in F.REVIEW_STATS_ITEMS]
        tabs = [t for t in F.REVIEW_TAB_ITEMS if t not in names]
        if root.get('type') != F.REVIEW_MENU_TYPE or stats or tabs:
            ck.error(f'{rel}: type {root.get("type")!r}, Stats tab items {stats}, category tabs missing {tabs} '
                     f'(expected {F.REVIEW_MENU_TYPE} with {list(F.REVIEW_TAB_ITEMS)} and no '
                     f'{list(F.REVIEW_STATS_ITEMS)})')
        elif want is None or C.encode_xmlb(root) != C.encode_xmlb(want):
            ck.error(f'{rel}: not XML2\'s review menu without its Stats tab (frontend.review_menu_trees)')
        else:
            ck.count('review_menu_ok')


def v_codex_icons(v, ck):
    """V29 (issue #48): with --frontend xml1 the codex menu (both halves) is the frontend module's, and its list
    draws no icon cells - XML1's codex list was text only, and an entry without a stats textureicon draws cell 0."""
    if C.frontend_mode(v.ctx) != 'xml1':
        ck.note('--frontend xml2: XML2\'s codex menu kept (not checked)')
        return
    for ext in ('.XMLB', '.engb'):
        rel = F.CODEX_MENU_REL + ext
        root = _tree(v, rel)
        if root is None:
            ck.error(f'{rel}: missing or does not decode')
            continue
        if not _registered_by(v, rel, 'frontend'):
            ck.error(f'{rel}: not written by the frontend module (XML2\'s list draws an icon cell per entry)')
        for p in F.codex_icon_problems(root):
            ck.error(f'{rel}: {p} (the list would draw mini_convo_icons cells; XML1\'s NPC entries all get cell 0)')
        if not any((it.get('type') or '').upper() == F.CODEX_LIST_TYPE for it in root.iter('item')):
            ck.error(f'{rel}: no {F.CODEX_LIST_TYPE} item')
        ck.count('codex_menu_halves')


def v_pda_portal(v, ck):
    """V35 (issue #89; SPEC 64): in both front ends the pause menu (UI/menus/pda, both halves) is the frontend
    module's and offers no Blink Portal - no portal label item, nothing navigates to it, its panel models hidden.
    XML2's entry opens a portal to X-Men Legends II's towns; the first game had none."""
    for ext in ('.XMLB', '.engb'):
        rel = F.PDA_MENU_REL + ext
        root = _tree(v, rel)
        if root is None:
            ck.error(f'{rel}: missing or does not decode')
            continue
        if not _registered_by(v, rel, 'frontend'):
            ck.error(f'{rel}: not written by the frontend module (XML2\'s pause menu has the Blink Portal)')
        if (root.get('type') or '').upper() != F.PDA_MENU_TYPE:
            ck.error(f'{rel}: type {root.get("type")!r}, expected {F.PDA_MENU_TYPE}')
        for p in F.pda_portal_problems(root):
            ck.error(f'{rel}: {p} (the Blink Portal leads to X-Men Legends II\'s towns, issue #89)')
        ck.count('pda_menu_halves')

def v_personal_items(v, ck):
    """V30 (issue #47): every personalItem('<item>') literal in installed content has Data/personal/<item>
    (.XMLB and .engb) written by the frontend module, with text and a texture whose IGB is in <out>; a missing
    data file shows the last loading screen, a missing texture the engine's default texture."""
    hits = _raw_hits(v, _PERSONAL_ITEM, b'personalitem', ('.xmlb', '.engb', '.py'))
    for lit, rels in sorted(hits.items()):
        name = C.norm(lit)
        where = sorted(set(rels))[:3]
        ck.count('personal_items')
        textures, problems = {}, 0
        for ext in ('.XMLB', '.engb'):
            rel = f'{F.PERSONAL_REL}/{name}{ext}'
            root = _tree(v, rel)
            if root is None:
                ck.error(f'personalItem({lit!r}) in {where}: {rel} missing or does not decode')
                problems += 1
                continue
            if not _registered_by(v, rel, 'frontend'):
                ck.error(f'personalItem({lit!r}): {rel} is not the first game\'s item (not written by frontend)')
                problems += 1
            items = [el for el in root.iter() if el.get('texture') is not None or el.get('text') is not None]
            if not items or not items[0].get('text'):
                ck.error(f'personalItem({lit!r}): {rel} has no text')
                problems += 1
            elif F.unescaped_menu_codes(items[0].get('text')):
                ck.error(f'personalItem({lit!r}): {rel} text has unescaped renderer codes (write "|c")')
                problems += 1
            tex = F.personal_texture_rel(items[0].get('texture')) if items else None
            if not tex:
                ck.error(f'personalItem({lit!r}): {rel} names no texture')
                problems += 1
            else:
                textures.setdefault(tex, []).append(rel)
        for tex, rels in sorted(textures.items()):
            if not v.exists(f'{tex}.igb'):
                ck.error(f'personalItem({lit!r}): texture {tex}.IGB ({", ".join(rels)}) is not in <out> (the engine '
                         f'draws its default texture)')
                problems += 1
        if not problems:
            ck.count('personal_items_ok')
