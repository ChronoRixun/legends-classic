"""xml1build.validate_selftest - standalone self-test of validate.py against the REAL pipeline (not part of the build).

usage: python -m xml1build.validate_selftest [--out <dir>] [--no-build] [--skip-negative] [--skip-tour] [--movies]
default --out: build/_selftest_validate/out  (must be under build/)

Passes (each prints one summary line per check; every validate.json is kept as _build/validate_<label>.json):
  build      tools/build_xml1.py --no-movies --test-ini --start-zone nyc/alison/nyc1_1_1 (all five real modules,
             the sweep and the in-build validate step with ctx.shared) -> exit code and in-build validate result
  positive   validate standalone on that tree (context rebuilt from _build/registry.json, no ctx.shared)
  negative   one or more injected defects per check (V1..V10), every expected finding asserted by check id + text,
             plus two findings that must NOT be errors (an inherited dropped line, an inherited dead reference)
  restored   defects removed again; the per-check error/warning counts must equal the positive pass
  tour       build_xml1.py --tour 5 (V11 positive), then injected tour defects (V11 negative), then restored
  movies     (--movies) build_xml1.py --only media without --no-movies: XML1 movies copied, V9 in error mode
Writes only under --out. Never launches the game; never touches the XML2 install, xml1_*, research/ or xml2_test.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xml1build import common as C          # noqa: E402
from xml1build import validate as V        # noqa: E402
import build_xml1                          # noqa: E402  tools/build_xml1.py

DEFAULT_OUT = C.ROOT / 'build' / '_selftest_validate' / 'out'
START_ZONE = 'nyc/alison/nyc1_1_1'


# ============================================================================================ build / validate
def run_build(out, *extra):
    argv = ['--out', str(out), '--test-ini', *extra]
    print(f'[selftest] build_xml1.py {" ".join(argv)}', flush=True)
    t0 = time.time()
    rc = build_xml1.main(argv)
    print(f'[selftest] build exit code {rc} ({time.time() - t0:.0f}s)', flush=True)
    return rc


def load_ctx(out, **kw):
    """a BuildContext over an existing build (what validate.main does), args as the build had them."""
    args = C.default_args(out=str(out), base=str(C.DEFAULT_BASE), **kw)
    reg = C.Registry.load(Path(out) / '_build' / 'registry.json')
    return C.BuildContext(out, C.DEFAULT_BASE, args=args, registry=reg)


def validate(ctx, label):
    ctx.report.modules.pop('validate', None)
    t0 = time.time()
    ok = C.run_step(ctx, 'validate', V.run)
    doc = json.loads((ctx.build_dir / 'validate.json').read_text(encoding='utf-8'))
    shutil.copy2(ctx.build_dir / 'validate.json', ctx.build_dir / f'validate_{label}.json')
    print_doc(doc, label, time.time() - t0, ok)
    return doc


def print_doc(doc, label, secs=0.0, ok=True):
    s = doc['summary']
    print(f'[selftest] {label}: {s["result"]} errors={s["errors"]} warnings={s["warnings"]} allowed={s["allowed"]} '
          f'step_ok={ok} ({secs:.0f}s) counts={s["counts"]}', flush=True)
    for cid, c in doc['checks'].items():
        crashed = ' CRASHED' if c['status'] == 'crashed' else ''
        print(f'    {cid:4} {c["status"]:8} E{len(c["errors"]):<5} W{len(c["warnings"]):<5} A{len(c["allowed"]):<4}'
              f'{crashed}', flush=True)


def report_modules(out):
    """content-module status of the last build (their errors are theirs; the selftest asserts validate only)."""
    try:
        rep = json.loads((Path(out) / '_build' / 'report.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return
    for name, m in rep['modules'].items():
        if name == 'validate':
            continue
        print(f'[selftest]   module {name}: {m["status"]}, {len(m["errors"])} errors'
              + (f' (first: {m["errors"][0][:140]})' if m['errors'] else ''), flush=True)


def shape(doc):
    return {k: (len(v['errors']), len(v['warnings']), len(v['allowed'])) for k, v in doc['checks'].items()}


# ============================================================================================ defect injection
class Mutator:
    """Applies defects through (or around) the ctx writers and restores files, mtimes and registry entries."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.undo = []

    def _save(self, rel):
        n = C.norm(rel)
        a = self.ctx.out_index.get(n)
        p = self.ctx.out / a if a else None
        data = p.read_bytes() if p and p.is_file() else None
        st = p.stat() if data is not None else None
        entry = dict(self.ctx.registry.entries[n]) if n in self.ctx.registry.entries else None
        self.undo.append((n, a, data, st, entry))
        return entry

    def write(self, rel, data, owner, register=True, keep_source=False):
        prev = self._save(rel)
        if register:
            old, self.ctx.module = self.ctx.module, owner
            try:
                actual = self.ctx.write_bytes(rel, data, replace=True)
            finally:
                self.ctx.module = old
            if keep_source and prev is not None:
                self.ctx.registry.entries[C.norm(actual)]['source'] = prev.get('source')
        else:
            p = self.ctx.out_path(rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            self.ctx.out_index.add(p.relative_to(self.ctx.out).as_posix())

    def patch_tree(self, rel, fn, owner, keep_source=True):
        root = self.ctx.read_out_xmlb(rel)
        fn(root)
        self.write(rel, C.encode_xmlb(root), owner, keep_source=keep_source)

    def raw_append(self, rel, data):
        """change a registered file behind the registry's back (V2 size check)."""
        self._save(rel)
        p = self.ctx.out_index.path(rel)
        p.write_bytes(p.read_bytes() + data)

    def delete(self, rel):
        self._save(rel)
        p = self.ctx.out_index.path(rel)
        if p:
            p.unlink()
        self.ctx.out_index.discard(rel)

    def drop(self, rel):
        """delete a registered file AND its registry entry (as if its module never wrote it)."""
        self.delete(rel)
        self.ctx.registry.entries.pop(C.norm(rel), None)

    def restore(self):
        for n, a, data, st, entry in reversed(self.undo):
            if a is None:
                p = self.ctx.out_index.path(n)
                if p and p.exists():
                    p.unlink()
                self.ctx.out_index.discard(n)
            else:
                p = self.ctx.out / a
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
                self.ctx.out_index.add(a)
            if entry is None:
                self.ctx.registry.entries.pop(n, None)
            else:
                self.ctx.registry.entries[n] = entry
        self.undo.clear()


def _find_stats(root, name):
    return next(el for el in root.iter('stats') if (el.get('name') or '').lower() == name)


def negative(ctx):
    """inject defects; returns (missing expected findings, unexpected errors for must-not-error cases, doc)."""
    m = Mutator(ctx)
    expect = []                                   # (check id, substring) that must appear as error or warning
    expect_err = []                               # (check id, substring) that must be an ERROR
    not_error = []                                # (check id, substring) that must appear, but NOT as an error
    enc = C.encode_xmlb
    small = ctx.research_path('sound/out/all_ima/eng/g/r/grso_m.zsm')
    z = START_ZONE

    # V1: proxy file at the root (never registered) -> also a stale file for V2
    m.write('dinput.dll', b'MZ proxy', 'build', register=False)
    expect_err += [('V1', 'dinput.dll: xml2-fix proxy'), ('V2', 'dinput.dll: neither an XML2 base file')]

    # V2: a registered script changed after registration; an XML2 bank shadowed by an unmerged all_ima copy;
    #     a 0-byte IGB (empty XML1 source copied)
    m.raw_append('Scripts/x1/missions/begin_alison.py', b'\r\n')
    m.write('Sounds/eng/b/i/bishop_m.zsm', small.read_bytes(), 'media')
    ctx.registry.entries['sounds/eng/b/i/bishop_m.zsm']['source'] = str(small)
    m.write('Actors/zz_selftest_empty.IGB', b'', 'characters')
    expect_err += [('V2', 'begin_alison.py: size'), ('V2', 'bishop_m.zsm: replaces/shadows XML2 bank'),
                   ('V2', 'zz_selftest_empty.IGB: 0-byte file')]
    expect += [('V8', 'bishop_m.zsm: registered bank not in')]

    # V3: uppercase / unsorted attribute names (raw xmlb.encode bypasses the writer), header-only file,
    #     a localized pair split (XMLB rewritten, XML2's engb left)
    bad = ET.Element('test', {'b': '1', 'A': '2'})
    m.write('Data/zz_selftest_unsorted.XMLB', V.xmlb.encode(bad), 'zones')
    m.write('Data/zz_selftest_empty.XMLB', struct.pack('<II', 0x11B1, 1), 'zones')
    # (Data/strings_svs: nobody writes it; the XML1 front end writes both halves of Data/strings, SPEC 21.2.3)
    m.write('Data/strings_svs.XMLB', ctx.out_index.path('Data/strings_svs.XMLB').read_bytes(), 'zones')
    expect_err += [('V3', 'zz_selftest_unsorted.XMLB: <test> non-lowercase'), ('V3', 'zz_selftest_empty.XMLB: 8 bytes'),
                   ('V3', 'strings_svs.XMLB: rewritten by zones but')]

    # V4: package with a capitalised actors/ prefix, a missing model, an unknown kind and an unmapped XML1 skin
    pk = ET.Element('packagedef')
    for k, f in (('actorskin', 'Actors/19810'), ('model', 'models/zz/does_not_exist'), ('weapon', 'x'),
                 ('actorskin', '5810')):
        ET.SubElement(pk, k, filename=f)
    m.write('Packages/generated/characters/zz_selftest_19810.PKGB', enc(pk), 'characters')
    expect_err += [('V4', 'lowercase "actors/" prefix'), ('V4', 'models/zz/does_not_exist'),
                   ('V4', 'unknown entry kind <weapon'), ('V4', '<actorskin filename="5810"> is an unmapped XML1')]

    # V5: npcstat (engb only): a hero name, an over-long name, a bad skin, grso_riot un-mapped back to 5810
    def npc(root):
        ET.SubElement(root, 'stats', {'name': 'Wolverine', 'skin': '19810', 'characteranims': '53_grso'})
        ET.SubElement(root, 'stats', {'name': 'zz_selftest_name_that_is_far_too_long_x', 'skin': '999'})
        _find_stats(root, 'grso_riot').set('skin', '5810')
    m.patch_tree('Data/npcstat.engb', npc, 'characters')
    expect_err += [("V5", "'wolverine' is in herostat and npcstat"), ('V5', 'longer than 31'),
                   ('V5', 'XMLB and engb list different names'), ('V5', "skin '999' is not 4-5 digits"),
                   ('V5', "grso_riot (xml1): namespace: skin='5810', but XML1 skin='5810' maps to '19810'"),
                   ('V5', 'skin differs between XMLB')]

    # V6 (+V5/V7): the start zone's .engb: soundfile too long, a dangling nextzone, an unmapped monster_skin,
    #     an over-long inline script (V7); the XMLB keeps the old world -> world attribute mismatch
    def zone(root):
        C.find_world(root).set('soundfile', 'toolongname1')
        ET.SubElement(root, 'entity', {'name': 'zz_link', 'nextzone': 'zz_no_such_zone', 'classname': 'zonelinkent'})
        ET.SubElement(root, 'entity', {'name': 'zz_skin', 'monster_skin': '5810', 'classname': 'monsterspawnerent'})
        ET.SubElement(root, 'entity', {'name': 'zz_inline',
                                       'actscript': 'setGameFlag("x", 1, 1)\\n\\r' + 'waittimed(1.0)\\n\\r' * 30})
    m.patch_tree(f'Maps/{z}.engb', zone, 'zones')
    expect_err += [('V6', "soundfile 'toolongname1' is 12 chars"), ('V6', 'differs between .engb'),
                   ('V6', "nextzone 'zz_no_such_zone' resolves to no zone"), ('V7', 'inline length'),
                   ('V5', f'Maps/{z}.engb: <entity monster_skin="5810"> is an unmapped XML1 reference')]

    # V7: a bad script (LF endings, wrong case, argc, type, forbidden, long flag name, bit, open if), its CRLF
    #     twin, a regression (XML1-order sound() args) and an inherited drop (XML1 lacks disallowResponse too)
    bad_py = ('SetGameFlag("a", 1, 1 )\n'
              'setGameFlag("abc", 1 )\n'
              'objective(1, "EOBJCMD_SHOW" )\n'
              'beginMission("alison" )\n'
              'setGameFlag("waytoolongflagname", 40, 1 )\n'
              'x = getZoneVar("v" )\n'
              'setEnable(x, "TRUE" )\n'
              'sound("PLAY_SOUND", 1.0, "nyc1/zone_shared/x", "" )\n'
              'disallowResponse(1 )\n'
              'if x == 1\n').encode('latin-1')
    m.write('Scripts/x1/zz_selftest/bad.py', bad_py, 'scripts')
    m.write('Scripts/x1/zz_selftest/bad_crlf.py', bad_py.replace(b'\n', b'\r\n'), 'scripts')
    expect_err += [('V7', 'line endings'), ('V7', "registered as 'setGameFlag'"), ('V7', 'setGameFlag() takes 3 args'),
                   ('V7', 'objective() arg 1 is a number literal'), ('V7', 'beginMission(): XML2 beginMission'),
                   ('V7', 'name longer than 11'), ('V7', 'bit index outside 1..32'), ('V7', 'never closed'),
                   ('V7', 'bad_crlf.py:8: type: sound() arg 2 is a number literal'),
                   ('V7', 'bad_crlf.py:9: argc: disallowResponse() takes 0 args')]   # not XML1 text: no inheritance
    # the real inherited case: verbatim XML1 conversation code whose function XML1 did not have either
    not_error += [('V7', '1_2_37.engb <response scriptfile="game.disallowResponse(')]
    dlg = ET.Element('dialog', {'text': 'x'})
    ET.SubElement(dlg, 'option', {'script': 'x1/missions/begin alison', 'text': 'a'})
    ET.SubElement(dlg, 'option', {'script': 'muir_is/muir1/loadsewers_selftest', 'text': 'b'})
    ET.SubElement(dlg, 'option', {'script': 'unlockCharacter("wolverine","")' + 'x' * 130, 'text': 'c'})
    m.write('Dialogs/x1/zz_selftest.XMLB', enc(dlg), 'scripts')
    m.write('Dialogs/x1/zz_selftest.engb', enc(dlg), 'scripts')
    expect_err += [('V7', 'contains whitespace or ";"'), ('V7', 'loadsewers_selftest.py does not exist'),
                   ('V7', 'console length')]
    # zone loads: an XML1 zone the build lost (its Maps files removed), one the disc never had and one the
    # disc ships empty (both inherited)
    lost = 'mocap/mocap1/briefing_1_1_6_5'
    for ext in ('.XMLB', '.engb'):
        if ctx.out_exists(f'Maps/{lost}{ext}'):
            m.delete(f'Maps/{lost}{ext}')
    m.write('Scripts/x1/zz_selftest/loads.py',
            (f'loadMapKeepTeam("{lost}" )\r\nwaittimed(1.0 )\r\nloadMapKeepTeam("zz/lost_zone" )\r\n'
             f'waittimed(1.0 )\r\nloadMapKeepTeam("astral/savepx/astral1_1" )\r\n').encode('latin-1'), 'scripts')
    expect_err += [('V7', f'loads.py: loadMapKeepTeam("{lost}") -> XML1 zone {lost} is convertible but not in')]
    not_error += [('V7', 'loads.py: loadMapKeepTeam("zz/lost_zone") -> no Maps/zz/lost_zone.XMLB: the zone is not on'),
                  ('V7', 'loads.py: loadMapKeepTeam("astral/savepx/astral1_1") -> no Maps/astral/savepx/astral1_1.XMLB:'
                         ' XML1 zone skipped')]

    # V5 namespace files: a skin IGB installed without the in-IGB rename, a HUD head that was never written
    m.write('Actors/19810.IGB', ctx.x1_path('actors/5810.igb').read_bytes(), 'characters', keep_source=True)
    hud = next(r for r in ctx.x1_rels('hud/') if r.endswith('.igb') and not ctx.x1_is_empty(r))
    hud_out = C.map_ui_path(hud[:-4]) + '.igb'
    m.drop(hud_out)
    expect_err += [('V5', 'Actors/19810.IGB: in-IGB rename incomplete'),
                   ('V5', f'XML1 {hud} -> {hud_out} is not in <out>')]
    # V3: a localized XML1 conversation written as .XMLB only
    conv = next(n for n, e in sorted(ctx.registry.entries.items())
                if n.startswith('conversations/') and n.endswith('.engb') and (e.get('source') or '').endswith('.eng'))
    m.drop(conv)
    expect_err.append(('V3', f'but {conv} was not written'))
    # V6: a character lost from the start zone's CHRB (grso_riot spawns there)
    m.patch_tree(f'Maps/{z}.CHRB', lambda r: [r.remove(c) for c in list(r.iter('character'))
                                                if (c.get('name') or '').lower() == 'grso_riot'], 'zones')
    expect_err += [('V6', f"{z}: CHRB lost XML1 .chr character(s) ['grso_riot']"),
                   ('V6', "world soundfile 'toolongname1' but the XML1 zone has soundfile='nyc1'")]
    # V7 missions: a listed mission file that does not exist, act 1 over the 75-objective cap
    m.patch_tree('Data/missions/missions.XMLB', lambda r: r.append(ET.Element('MISSION', {'name': 'zz_missing'})),
                 'scripts', keep_source=False)

    def act1(r):
        objs = list(r.iter('OBJECTIVE'))
        for i in range(80 - len(objs)):
            e = ET.SubElement(r, 'OBJECTIVE', dict(objs[0].attrib))
            e.set('name', f'zz_obj{i}')
    m.patch_tree('Data/missions/x1_act01.engb', act1, 'scripts', keep_source=False)
    expect_err += [('V7', "lists 'zz_missing' but Data/missions/zz_missing"),
                   ('V7', 'act 1: 80 objectives > 75')]

    # V8: a stereo sample in a .zsm
    b = bytearray(small.read_bytes())
    t1_count, t1_keys, t1_ents = struct.unpack_from('<III', b, 0x10 + 12)
    b[t1_ents + 2] |= 0x02
    m.write('Sounds/eng/z/z/zz_selftest_m.zsm', bytes(b), 'media')
    expect_err.append(('V8', 'stereo sample'))

    # V9: an XML1 script playing a renamed XML1 movie name, a removed subtitle half
    m.write('Scripts/x1/zz_selftest/movie.py', b'startMovie("i101", "done" )\r\nwaitsignal("done" )\r\n', 'scripts')
    m.delete('Movies/int101.engb')
    expect_err += [('V9', 'XML1\'s i101 was renamed xi101'), ('V9', 'Movies/int101.engb missing')]

    # V10: new game pointing at a zone that does not exist
    m.write('Scripts/menus/new_game_hard.py', b'setCurrentAct(1 )\r\nloadMapKeepTeam("zz/no/zone" )\r\n', 'testhooks')
    expect_err += [('V10', 'Maps/zz/no/zone.XMLB is not in <out>'), ('V10', "loads 'zz/no/zone'")]

    # fix round 1 checks
    # V3: an XML1-only entity class left in a zone (XMen2.exe would make it a bare 'ent')
    m.patch_tree(f'Maps/{z}.XMLB', lambda r: C.iter_roots(r)[0].append(
        ET.Element('entity', {'name': 'zz_harm', 'classname': 'harmtargetent', 'damage': '5'})), 'zones')
    expect_err.append(('V3', "entity 'zz_harm' classname='harmtargetent' is not an XMen2.exe entity class"))
    # V3: an XML1-sourced effect that still carries red/green/blue curves
    eff = next(n for n, e in sorted(ctx.registry.entries.items())
               if n.startswith('effects/') and n.endswith('.xmlb') and (e.get('source') or '').endswith('.xml'))

    def xml1_colours(r):
        prim = next(el for el in r.iter() if el.get('startcolor1') is not None)
        prim.set('red', '0 0 1 0 0 1')
    m.patch_tree(eff, xml1_colours, 'zones')
    expect_err.append(('V3', 'still use XML1 red/green/blue colour curves'))
    # V6: an XML1-schema item (unknown type, activepowerup) in the items table; XML2's front end rewritten
    def item(r):
        it = ET.SubElement(C.iter_roots(r)[0], 'item', {'name': 'zz_selftest_item', 'type': 'skill'})
        ET.SubElement(it, 'activepowerup', {'powerup': 'mind', 'level': '1'})
    m.patch_tree('Data/items.engb', item, 'zones', keep_source=False)
    expect_err += [('V6', 'XML1 <activepowerup> in the items table'),
                   ('V6', "type='skill' is not an XMen2.exe item type")]
    if C.frontend_mode(ctx) == 'xml2':
        m.write('Maps/menu/main_back.XMLB', ctx.out_index.path('Maps/menu/main_back.XMLB').read_bytes(), 'zones')
        expect_err.append(('V6', 'XML2 front-end file of menu/main_back was rewritten'))
    else:
        # SPEC 21 V15: XMen2.exe's MAIN_MENU contract (label_option09 opens the online menu, 0x5c9857)
        m.patch_tree('UI/menus/main.engb', lambda r: ET.SubElement(r, 'item', {'name': 'label_option09'}), 'frontend')
        expect_err.append(('V15', "item 'label_option09' present"))
        # SPEC 21.2 V15: XML1's menu IGB as on the disc (Camera01 at y -1108 with near 897 clips XMen2.exe's dialogs)
        from xml1build import frontend as F
        m.write(F.MENU_IGB_REL, ctx.x1_path(F.X1_MENU_IGB).read_bytes(), 'frontend')
        expect_err += [('V15', 're-framed on XML2\'s menu camera with its buttons spread over XML1\'s span'),
                       ('V15', 'overlay depth -700.0 (dialogs / help line not drawn)'),
                       ('V15', 'button8 at z -51.5, outside the screen')]
        # SPEC 21.2.4 V15: Play Online dropped out of the keys' up/down chain (button6 -> button8)

        def online_unreachable(r):
            items = {it.get('name'): it for it in r.iter('item')}
            items['button6'].set('down', 'button8')
            items['button8'].set('up', 'button6')
            items['button7'].set('up', 'button7')
            items['button7'].set('down', 'button7')
        m.patch_tree('UI/menus/main.engb', online_unreachable, 'frontend')
        expect_err.append(('V15', 'Play Online (button7) is not in the up/down chain'))
        # SPEC 21.4.1 / 21.4.2 V17: a credit line with a bare '#' (drawn over itself), XML2's backdrop image back on
        # the credits menu

        def bare_hash(r):
            next(ln for ln in r.iter('line') if '|#' in (ln.get('text') or '')).set('text', 'NYC Acolyte #1, Shadow')
        m.patch_tree(F.CREDITS_REL + '.engb', bare_hash, 'frontend')
        expect_err.append(('V17', "credit line 'NYC Acolyte #1, Shadow': '#' not escaped"))
        m.patch_tree('UI/menus/credits.XMLB', lambda r: r.set('image', 'textures/loading/credits01'), 'frontend')
        expect_err.append(('V17', "UI/menus/credits.XMLB: image='textures/loading/credits01'"))
        # SPEC 21.4.3 V17: XML2's review menu back (its Stats tab lists XML2's acts 1-5)
        m.write(F.REVIEW_MENU_REL + '.engb', ctx.base_index.path(F.REVIEW_MENU_REL + '.engb').read_bytes(), 'frontend')
        expect_err.append(('V17', "UI/menus/review.engb: type 'REVIEW_PATHS_MENU', Stats tab items ['option05_focus', "
                                  "'option05_text']"))
        # SPEC 21.2.2 V15: Begin Story back on XMen2.exe's newgame (the difficulty prompt XML1 never had)

        def begin_story_prompt(r):
            next(it for it in r.iter('item') if it.get('name') == F.MAIN_MENU_ITEMS[0]).set('usecmd', 'newgame')
        m.patch_tree('UI/menus/main.XMLB', begin_story_prompt, 'frontend')
        expect_err += [('V15', "button1 usecmd 'newgame' runs newgame, which opens XMen2.exe's difficulty prompt"),
                       ('V15', "Begin Story (button1) usecmd 'newgame', expected")]
        # SPEC 21.2.3 V15: XML2's save / load messages back (the Load Game dialog's "No X-men Legends 2 save data")
        m.write('igct.bnx', ctx.base_index.path('igct.bnx').read_bytes(), 'frontend')
        expect_err += [('V15', 'igct.bnx: still names XML2'),
                       ('V15', "EMSG_NO_DATA_DEVNUM (the Load Game dialog without saves) is 'No X-men Legends 2 save")]
    # SPEC 22 V18: Magma's lava_rift back on XML1's blast_ranged (the in-game bug), an affecter XMen2.exe does not
    # register, a FightMove handler nobody assessed

    def combat(r):
        ev = next(e for e in r if e.tag == 'event' and e.get('name') == 'lava_rift')
        ev.set('inherit', 'blast_ranged')
        p3 = next(mv for mv in r if mv.tag == 'FightMove' and mv.get('name') == 'power3')
        ET.SubElement(ET.SubElement(p3, 'trigger', {'name': 'powerup', 'time': '0'}), 'affecter',
                      {'attribute': 'atk_damage_scale', 'level': '0.5'})
        p3.set('handler', 'ch_zz_selftest')
    m.patch_tree('Data/powerstyles/ps_magma.XMLB', combat, 'heroes')
    expect_err += [('V18', 'unresolved lava_rift'), ('V18', 'affecter atk_damage_scale'),
                   ('V18', 'ch_zz_selftest is not registered')]
    # SPEC 24 V19: an XML1 value code back in an NPC style (XMen2.exe reads it as 0), an XML1 npcstat entry without its
    # NPC energy talent

    def code_left(r):
        next(e for e in r if e.tag == 'event' and e.get('name') == 'flame_dmg').set('damage', 'L3')

    def no_energy(r):
        st = next(s for s in r.iter('stats') if (s.get('name') or '').lower() == 'pyroact1')
        for t in [t for t in st if t.tag == 'talent' and t.get('name') == 'x1_npc_energy']:
            st.remove(t)
    for rel, fn in (('Data/powerstyles/x1_ps_pyro.XMLB', code_left), ('Data/npcstat.engb', no_energy)):
        m.patch_tree(rel, fn, (ctx.registry.entries.get(C.norm(rel)) or {}).get('owner') or 'characters')
    expect_err += [('V19', 'flame_dmg <event damage="L3">'), ('V19', 'PyroAct1: x1_npc_energy ranks [], [13]')]
    # V7: a mixed-case zone literal in an XML1 script (SPEC 4.1)
    m.write('Scripts/x1/zz_selftest/case.py', b'loadMapKeepTeam("Mansion/Man3/mansion3_2" )\r\n', 'scripts')
    not_error.append(('V7', 'loadMapKeepTeam("Mansion/Man3/mansion3_2"): zone literal is not normalised'))

    # fix round 2 checks
    # V6: an XML1-only speaker alias left in a conversation, and a token no stats table ever had (inherited)
    conv2 = next(n for n, e in sorted(ctx.registry.entries.items())
                 if n.startswith('conversations/') and n.endswith('.engb') and n != conv and e['owner'] == 'zones')

    def speakers(r):
        C.iter_roots(r)[0].append(ET.Element('line', {'text': '%ALISON%selftest line'}))
        C.iter_roots(r)[0].append(ET.Element('line', {'text': '%ZZSELFTESTNOBODY%selftest line'}))
    m.patch_tree(conv2, speakers, 'zones')
    expect_err.append(('V6', 'XML1-only speaker alias %ALISON%'))
    not_error.append(('V6', "'%ZZSELFTESTNOBODY%': 1"))
    # V3: a remapped scan turret that lost its fixed mount
    tz = 'haarp/ext/haarp_ext02'

    def unmount(r):
        t = next(el for el in r.iter() if el.get('name') == 'tank_turret' and el.get('classname'))
        t.attrib.pop('nogravity', None)
    m.patch_tree(f'Maps/{tz}.engb', unmount, 'zones')
    expect_err.append(('V3', "turret physent 'tank_turret' lacks ['nogravity']=true"))
    # V6: an XML2 zone registered in the Xtraction network again
    def xtraction(r):
        e = next(z for z in r.iter('zone') if z.get('name') == 'act1/sanctuary/sanctuary1')
        e.set('extraction', 'true')
        e.set('towncenter', 'true')
    m.patch_tree('Data/zoneinfo.engb', xtraction, 'zones')
    # kept on purpose (zones.STRIP_XTRACTION): reported as a known-limitation warning, not an error
    expect.append(('V6', "zone 'act1/sanctuary/sanctuary1' (not an XML1 zone) keeps Xtraction attributes"))
    # V6 (section 15): the town centre of an act the scripts select (act 7, nyc/riots) is unregistered

    def no_towncenter(r):
        for z in r.iter('zone'):
            if (z.get('act') or '') == '7' and (z.get('towncenter') or '').lower() == 'true':
                del z.attrib['towncenter']
    m.patch_tree('Data/zoneinfo.engb', no_towncenter, 'zones')
    expect_err.append(('V6', 'Data/zoneinfo.engb: act 7 has no registered town centre'))
    # V7: an XML1 animation enum XMen2.exe does not have
    m.write('Scripts/x1/zz_selftest/anim.py', b'playanim("EA_MISSION3", "_OWNER_", "NONE", "" )\r\n', 'scripts')
    expect_err.append(('V7', "animation enum EA_MISSION3 is XML1's"))
    # V6: a zone the act plan gives an entry act whose zone script lost its setCurrentAct
    az = 'sewers/hub/sewers1_1_3'
    if ctx.out_exists(f'Scripts/x1/zones/{az}.py'):
        m.write(f'Scripts/x1/zones/{az}.py', b'# selftest: act removed\r\nwaittimed(1.0 )\r\n', 'scripts')
        expect_err.append(('V6', f'{az}: the scripts act plan gives it an act on entry'))

    expect_err += forced_teams_defects(ctx, m)
    expect_err += npc_double_defects(ctx, m)
    doc = validate(ctx, 'negative')
    missing = []
    for cid, sub in expect:
        c = doc['checks'][cid]
        if not any(sub in x for x in c['errors'] + c['warnings']):
            missing.append((cid, 'error/warn', sub))
    for cid, sub in expect_err:
        if not any(sub in x for x in doc['checks'][cid]['errors']):
            missing.append((cid, 'error', sub))
    for cid, sub in not_error:
        c = doc['checks'][cid]
        if any(sub in x for x in c['errors']):
            missing.append((cid, 'must NOT be an error', sub))
        elif not any(sub in x for x in c['warnings']):
            missing.append((cid, 'warning', sub))
    m.restore()
    return missing, doc


def npc_double_defects(ctx, m):
    """V6 (SPEC 18.1): nuke2_2's renamed Colossus double addressed by the hero's name again - by its spawnscript and
    as the speaker of its conversation - and the double's speaker stats entry gone; returns the expected errors."""
    rel = 'Scripts/nuke_plant/nuke/colossus_holding.py'
    text = ctx.out_index.path(rel).read_bytes()
    assert b'"colossus_x1double"' in text, rel
    m.write(rel, text.replace(b'"colossus_x1double"', b'"colossus"'), 'scripts', keep_source=True)

    def as_hero(r):
        for el in r.iter():
            t = el.get('text') or ''
            if '%COLOSSUS_X1DOUBLE%' in t:
                el.set('text', t.replace('%COLOSSUS_X1DOUBLE%', '%COLOSSUS%'))
    m.patch_tree('Conversations/nuke_plant/nuke/2_3_4.engb', as_hero, 'zones')

    def no_speaker(r):
        for el in list(r):
            if (el.get('name') or '').lower() == 'psylocke_x1double':
                r.remove(el)
    m.patch_tree('Data/npcstat.engb', no_speaker, 'heroes')
    m.patch_tree('Data/npcstat.XMLB', no_speaker, 'heroes')
    # SPEC 18.1 speakers (2026-09-29): Mystique-as-Cyclops' line back on the hero's token, and a Cyclops line nobody
    # reviewed in dr_mag2's join zone (its NPC double stands there as cyclops_x1double)

    def npc_as_hero(r):
        for el in r.iter():
            t = el.get('text') or ''
            if '%CYCLOPS_SCRIPTED%' in t:
                el.set('text', t.replace('%CYCLOPS_SCRIPTED%', '%CYCLOPS%'))
    m.patch_tree('Conversations/nyc/alison/1_1_09.engb', npc_as_hero, 'zones')

    def unreviewed(r):
        C.iter_roots(r)[0].append(ET.Element('line', {'text': '%CYCLOPS%selftest line'}))
    m.patch_tree('Conversations/mansion/dr_mag2/2_2_2.engb', unreviewed, 'zones')
    # the NPC Alison's line back on the party hero's token, and her Danger Room double's speaker entry labelled like
    # Magma instead of XML1's "Alison" (default.xbe string 503)

    def alison_as_magma(r):
        for el in r.iter():
            t = el.get('text') or ''
            if '%ALISON%' in t:
                el.set('text', t.replace('%ALISON%', '%MAGMA%'))
    m.patch_tree('Conversations/nyc/alison/1_1_5_1b.engb', alison_as_magma, 'zones')

    def magma_label(r):
        for el in r.iter('stats'):
            if (el.get('name') or '').lower() == 'alison_scripted':
                el.set('charactername', 'Magma')
    m.patch_tree('Data/npcstat.engb', magma_label, 'heroes')
    return [('V6', 'playanim("colossus") addresses the hero, not the renamed NPC'),
            ('V6', 'speaker %COLOSSUS% names the hero, not the renamed NPC'),
            ('V6', 'speaker %PSYLOCKE_X1DOUBLE% has no stats entry'),
            ('V6', 'conversations/nyc/alison/1_1_09: speaker %CYCLOPS% (1x) names the hero, not the NPC "cyclops_scripted"'),
            ('V6', 'speaker review (18.1): mansion/dr_mag2/mag_nyc4: conversations/mansion/dr_mag2/2_2_2 %CYCLOPS%'),
            ('V6', 'conversations/nyc/alison/1_1_5_1b: speaker %MAGMA% (1x) names the hero, not the NPC "alison"'),
            ('V6', "npcstat.engb speaker entry alison_scripted: charactername 'Magma'")]


def forced_teams_defects(ctx, m):
    """V14 (SPEC 19, seat builds): inject one defect per rule through Mutator m; returns the expected errors."""
    if C.forced_teams_mode(ctx) != 'seat':
        return []

    def edit(rel, old, new):
        text = ctx.out_index.path(rel).read_bytes().decode('latin-1')
        assert old in text, (rel, old)
        m.write(rel, text.replace(old, new, 1).encode('latin-1'), 'scripts', keep_source=True)

    # V14b: the guard variable of a skinset block is not declared (without the DLL the if line would be dropped)
    edit('Scripts/x1/missions/begin_haarp.py', 'x1ft = iadd(0, 0 )\r\n', '')
    # V14c: a seat block that seats another party than the plan
    edit('Scripts/x1/missions/begin_mansion1.py', 'seatParty("magma", "", "", "" )', 'seatParty("magma", "storm", "", "" )')
    # V14d: a skinset hero without that costume
    edit('Scripts/x1/missions/begin_mansion2.py', 'setSkinset("civilian", "magma" )', 'setSkinset("civilian", "wolverine" )')
    # V14e: dr_mag1 pushes the party but its end site no longer pops it
    edit('Scripts/mansion/dr_mag/fmvexit.py', 'popParty("mansion/man2/subbasement2" )', 'debug("x1: selftest" )')
    # V14f: addHero outside the join scripts (guarded, so only V14f fires)
    m.write('Scripts/zz_selftest_addhero.py', b'x1ah = iadd(0, 0 )\r\nx1ah = xml2fixFeature("addhero" )\r\n'
            b'if x1ah == 1\r\n     x1ah = addHero("storm" )\r\nendif\r\n', 'scripts')
    # V14f: joinHero before the NPC double's remove (the double must go before the reload; joinHero ends its branch)
    edit('Scripts/mansion/dr_mag2/blob/add_cyclops.py',
         '     remove ( "cyclops_x1double", "cyclops_x1double" )\r\n     x1ah = joinHero("cyclops" )\r\n',
         '     x1ah = joinHero("cyclops" )\r\n     remove ( "cyclops_x1double", "cyclops_x1double" )\r\n')
    # V14h + V7: the join popup without its wait (still up when the reload / team menu comes)
    edit('Scripts/nyc/alison/add_cyclops.py', 'createPopupDialogXml("dialogs/tut15" )\r\nwaittimed ( 0.500 )\r\n',
         'createPopupDialogXml("dialogs/tut15" )\r\n')
    # V14h: mag_nyc4's zone script without the late removes of the double
    edit('Scripts/x1/zones/mansion/dr_mag2/mag_nyc4.py', 'if x1j == 1\r\n     waittimed', 'if x1j == 0\r\n     waittimed')
    # V6: nyc1_1_3's slot-2 start disabled again (zones section 18: Cyclops unspawned at every later load)
    m.patch_tree('Maps/nyc/alison/nyc1_1_3.XMLB', lambda r: [e.set('startenabled', 'false') for e in r.iter('entity')
                                                             if e.get('name') == 'player_start01'], 'zones')
    want = [('V14', 'V14b: Scripts/x1/missions/begin_haarp.py'), ('V14', 'mansion1 seats [\'magma\', \'storm\']'),
            ('V14', 'wolverine has no skin_civilian'), ('V14', 'side mission dr_mag1: push sites'),
            ('V14', 'addHero outside the join scripts'), ('V14', 'joinHero is not right after remove'),
            ('V14', 'is not followed by a waittimed'), ('V7', 'popup pending'),
            ('V14', 'does not end with the late removes'), ('V6', 'player_start01 (slot 2) startenabled="false"')]
    # V14c (--start-party builds): the New Game hook seats a hero it did not unlock
    party = [h.strip().lower() for h in str(ctx.opt('start_party') or '').split(',') if h.strip()]
    if party:
        edit('Scripts/menus/new_game.py', f'unlockCharacter("{party[0]}", "" )\r\n', '')
        want.append(('V14', f"the --start-party hook seats ['{party[0]}'] without an unlockCharacter"))
    return want


def negative_tour(ctx):
    m = Mutator(ctx)
    p = ctx.out / '_tour.json'
    d = json.loads(p.read_text(encoding='utf-8'))
    saved = p.read_bytes()
    saved_st = p.stat()
    d['stops'][0]['next'] = 'zz/not/next'
    p.write_text(json.dumps(d), encoding='utf-8')
    z = d['stops'][1]['zone']
    m.patch_tree(f'Maps/{z}.XMLB', lambda r: C.find_world(r).set('zonescript', 'x1/tour/wrong'), 'testhooks')
    z2 = d['stops'][2]['zone']
    m.patch_tree(f'Packages/generated/maps/{z2}.PKGB',
                 lambda r: [r.remove(e) for e in list(r) if e.tag == 'script' and 'x1/tour/' in (e.get('filename') or '')],
                 'testhooks', keep_source=False)
    expect = [('V11', "next 'zz/not/next'"), ('V11', "zonescript 'x1/tour/wrong'"),
              ('V11', f'stop 2 {z2}: zone package does not list')]
    doc = validate(ctx, 'negative_tour')
    missing = [(cid, sub) for cid, sub in expect if not any(sub in x for x in doc['checks'][cid]['errors'])]
    p.write_bytes(saved)
    os.utime(p, ns=(saved_st.st_atime_ns, saved_st.st_mtime_ns))
    m.restore()
    return missing


# ============================================================================================ main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    ap.add_argument('--no-build', action='store_true', help='reuse the existing --start-zone build in --out')
    ap.add_argument('--skip-negative', action='store_true')
    ap.add_argument('--skip-tour', action='store_true')
    ap.add_argument('--movies', action='store_true', help='finish with a movies build (--only media, ~1.1 GB copy)')
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if (C.ROOT / 'build').resolve() not in out.parents:
        raise SystemExit(f'refusing --out outside {C.ROOT / "build"}')
    t0 = time.time()
    rc = 0
    if not a.no_build:
        run_build(out, '--no-movies', '--start-zone', START_ZONE)
        doc_b = json.loads((out / '_build' / 'validate.json').read_text(encoding='utf-8'))
        shutil.copy2(out / '_build' / 'validate.json', out / '_build' / 'validate_build.json')
        print_doc(doc_b, 'build (in-build validate, with ctx.shared)')
        report_modules(out)
        if doc_b['summary']['errors'] or any(c['status'] == 'crashed' for c in doc_b['checks'].values()):
            print('[selftest] FAIL: the in-build validate step reports errors / crashed')
            rc = 1
    ctx = load_ctx(out, no_movies=True, start_zone=START_ZONE)
    doc_a = validate(ctx, 'positive')
    if doc_a['summary']['errors'] or any(c['status'] == 'crashed' for c in doc_a['checks'].values()):
        rc = 1
    if not a.skip_negative:
        missing, _ = negative(ctx)
        if missing:
            rc = 1
            print('[selftest] NEGATIVE PASS: expected findings NOT reported as required:')
            for x in missing:
                print('    ', x)
        else:
            print('[selftest] negative pass: every injected defect was reported with the expected severity')
        doc_r = validate(ctx, 'restored')
        same = shape(doc_r) == shape(doc_a)
        print(f'[selftest] restored == positive: {same}')
        if not same:
            rc = 1
            print('    positive', shape(doc_a))
            print('    restored', shape(doc_r))
    if not a.skip_tour:
        run_build(out, '--no-movies', '--tour', '5')
        report_modules(out)
        ctx = load_ctx(out, no_movies=True, tour=5.0)
        doc_t = validate(ctx, 'tour')
        if doc_t['summary']['errors'] or doc_t['checks']['V11']['status'] != 'ok':
            rc = 1
            print('[selftest] FAIL: tour build does not validate cleanly (V11 must be ok)')
        if not a.skip_negative:
            mt = negative_tour(ctx)
            if mt:
                rc = 1
                print('[selftest] TOUR NEGATIVE: not reported:', mt)
            else:
                print('[selftest] tour negative pass: every injected defect was reported')
            doc_tr = validate(ctx, 'tour_restored')
            if shape(doc_tr) != shape(doc_t):
                rc = 1
                print('[selftest] tour restored != tour positive', shape(doc_t), shape(doc_tr))
        # back to the plain --start-zone build (the tour hook rewrote zone scripts / packages)
        run_build(out, '--no-movies', '--start-zone', START_ZONE)
    if a.movies:
        run_build(out, '--only', 'media', '--start-zone', START_ZONE)
        report_modules(out)
        ctx = load_ctx(out, no_movies=False, start_zone=START_ZONE)
        doc_m = validate(ctx, 'movies')
        v9 = doc_m['checks']['V9']
        print(f'[selftest] movies: V9 {v9["status"]} counts={v9["counts"]}')
        if doc_m['summary']['errors'] or v9['counts'].get('movies_missing', 0):
            rc = 1
            print('[selftest] FAIL: movies build does not validate cleanly')
        if not a.skip_negative:
            # an XML1 movie that is no longer a byte copy, and a missing one referenced by an XML1 script
            mm = Mutator(ctx)
            mm.raw_append('Movies/ntsc/eng/r/1/r102.sfd', b'\0')
            mm.delete('Movies/ntsc/eng/r/1/r106.sfd')
            doc_n = validate(ctx, 'movies_negative')
            errs = doc_n['checks']['V9']['errors']
            want = ['r102.sfd: size differs from the XML1 source', 'startMovie("R106")',
                    'XML1 movie r106 -> movies/ntsc/eng/r/1/r106.sfd missing']
            miss = [w for w in want if not any(w in x for x in errs)]
            mm.restore()
            if miss:
                rc = 1
                print('[selftest] MOVIES NEGATIVE: not reported:', miss)
            else:
                print('[selftest] movies negative pass: every injected defect was reported')
    print(f'[selftest] done in {time.time() - t0:.0f}s, rc={rc}')
    return rc


if __name__ == '__main__':
    sys.exit(main())
