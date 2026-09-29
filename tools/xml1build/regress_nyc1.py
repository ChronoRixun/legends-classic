"""Regression guard: the build <out> must contain everything the in-game-proven xml2_test had for
nyc/alison/nyc1_1_1 + grso_riot + the converted nyc1_* / grso_m banks.

usage: python tools/xml1build/regress_nyc1.py <out>
Reads only; prints PASS/FAIL lines and exits 1 on any failure. The XML1 source zone and the converted banks are read
through the build's Sources (Sources.for_out: a prepared build's cache, else the developer folders, SPEC 27); the
proven references (xml2_test, research/characters/out/grso_riot_scheme) are developer files in the repo.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))              # run as a file: make the xml1build package importable
from xml1build import common as C  # noqa: E402
from xml1build.lib import zsnd  # noqa: E402
import xmlb  # noqa: E402

TEST = ROOT / 'xml2_test'
SCHEME = ROOT / 'research/characters/out/grso_riot_scheme'
ZONE = 'nyc/alison/nyc1_1_1'
SRC = C.Sources.developer()                     # main(): the <out> build's Sources
IMA = SRC.research_path('sound/out/all_ima/eng')

fails, passes = [], []


def ok(cond, msg):
    (passes if cond else fails).append(msg)
    print(('PASS ' if cond else 'FAIL ') + msg)
    return cond


def find(root: Path, rel):
    """case-insensitive path lookup under root."""
    cur = root
    for part in rel.replace('\\', '/').split('/'):
        if not cur.is_dir():
            return None
        m = next((e for e in cur.iterdir() if e.name.lower() == part.lower()), None)
        if m is None:
            return None
        cur = m
    return cur


def dec(p):
    return xmlb.decode(Path(p).read_bytes())


def world(root):
    return C.find_world(root)


def _inst_key(group, inst):
    return (group.get('type'), inst.get('name'), inst.get('pos'))


def test_only_insts(proven, ours):
    """Remove from `proven` (in place) every <entinst>/<inst> that is neither in `ours` nor in the XML1 source zone
    (test spawns added to the live xml2_test copy); returns their keys. Instances the XML1 source has stay, so a
    lost instance still makes the comparison fail."""
    src = C.parse_x1_text(SRC.x1_loose / f'maps/{ZONE}.eng')
    src_keys = {_inst_key(g, i) for g in src.iter('entinst') for i in g if i.tag == 'inst'}
    our_keys = {_inst_key(g, i) for g in ours.iter('entinst') for i in g if i.tag == 'inst'}
    removed = []
    for g in proven.iter('entinst'):
        for i in list(g):
            k = _inst_key(g, i)
            if i.tag == 'inst' and k not in our_keys and k not in src_keys:
                g.remove(i)
                removed.append(k)
    return removed


def main(out):
    global SRC, IMA
    out = Path(out)
    SRC = C.Sources.for_out(out)
    IMA = SRC.research_path('sound/out/all_ima/eng')
    # ---------------------------------------------------------------- zone files
    zfiles = {}
    for ext in ('.XMLB', '.engb', '.CHRB', '.NAVB', '.BOYB', '.IGB'):
        p = find(out, f'Maps/{ZONE}{ext}')
        zfiles[ext] = p
        ok(p is not None and p.stat().st_size > 8, f'zone file Maps/{ZONE}{ext} present ({p.stat().st_size if p else 0} bytes)')
        tp = find(TEST, f'Maps/{ZONE}{ext}')
        if p is not None and tp is not None:
            same = p.read_bytes() == tp.read_bytes()
            if not same and ext in ('.XMLB', '.engb'):
                # the review fixes of round 1 change the proven zone's data only through x1schema (XML1-only
                # entity classes XMen2.exe does not register -> XML2 classes; 'persistant' -> 'persistent'), and
                # SPEC 17 (2026-09-27, verified in game: the subway stairs, every zone exit) rewrote every <inst
                # extents> from XML1's world-space box to XMen2.exe's entity-local one (zones.convert_inst_extents),
                # and zones section 25 (2026-09-28, verified in game: both heroes spawn) marks one-position hero
                # starts allinone="true" (zones.mark_allinone_starts): the proven copy with exactly those applied
                # must equal ours byte for byte
                from xml1build import x1schema as XS
                from xml1build import zones as Z
                pt = dec(tp)
                ch = XS.convert_entities(pt)
                boxes = Z.convert_inst_extents(pt)
                allinone = Z.mark_allinone_starts(pt)
                # xml2_test is also the orchestrator's live test copy: test-only spawn instances added there with
                # tools/add_spawn_inst.py (an <inst> that is in neither our file nor the XML1 source zone) are not
                # conversion output; an <inst> the XML1 source has but ours lacks is a real loss and still fails
                extra = test_only_insts(pt, dec(p))
                ow, pw = world(dec(p)), world(pt)
                tour = ow is not None and pw is not None and (ow.get('zonescript') or '').startswith('x1/tour/')
                if tour:                                      # --tour build: testhooks' zonescript (SPEC 7)
                    pw.set('zonescript', ow.get('zonescript'))
                fixed = C.encode_xmlb(pt)
                if fixed == p.read_bytes():
                    ok(True, f'  {ext} = proven xml2_test copy + the documented x1schema fixes only '
                             f'{sorted(set(f"{k}:{d}" for k, d in ch))} ({len(ch)} changes) + SPEC 17 inst extents '
                             f'{dict(sorted(boxes.items()))} + section 25 allinone starts {allinone}'
                             + (f'; ignored {len(extra)} test-only spawn instance(s) xml2_test gained after the proven '
                                f'run (add_spawn_inst.py, absent from the XML1 source): {extra}' if extra else '')
                             + (f'; tour build: world zonescript {ow.get("zonescript")!r} from testhooks' if tour else ''))
                    continue
            if not same and ext in ('.XMLB', '.engb', '.CHRB', '.NAVB', '.BOYB'):
                a, b = dec(p), dec(tp)
                sa = [(e.tag, sorted(e.attrib.items())) for e in a.iter()]
                sb = [(e.tag, sorted(e.attrib.items())) for e in b.iter()]
                diff = [(x, y) for x, y in zip(sa, sb) if x != y]
                ok(False, f'  {ext} differs from proven xml2_test copy: {len(sa)} vs {len(sb)} elements, '
                          f'{len(diff)} differing, first {diff[:2]}')
            else:
                ok(same, f'  {ext} byte-identical to proven xml2_test copy')
    for ext in ('.XMLB', '.engb'):
        if zfiles[ext]:
            w = world(dec(zfiles[ext]))
            ok(w is not None and w.get('soundfile') == 'nyc1',
               f'world soundfile="nyc1" in {ext} (got {w.get("soundfile") if w is not None else None!r}, '
               f'zonescript={w.get("zonescript") if w is not None else None!r})')
    if zfiles['.CHRB']:
        names = [e.get('name') for e in dec(zfiles['.CHRB']).iter('character')]
        ok('grso_riot' in names, f'CHRB lists grso_riot ({names})')

    # ---------------------------------------------------------------- zone package
    zp = find(out, f'Packages/generated/maps/{ZONE}.PKGB')
    ok(zp is not None, 'zone package present')
    if zp:
        ours = {(e.tag.lower(), (e.get('filename') or '').lower()) for e in dec(zp)}
        proven = [(e.tag.lower(), (e.get('filename') or '').lower()) for e in dec(find(TEST, f'Packages/generated/maps/{ZONE}.PKGB'))]
        missing = []
        for k, f in proven:
            # the proven package used XML1's raw entry forms; ours uses the SPEC forms (map_package_entry)
            k2, f2 = C.map_package_entry(k, f)
            if (k, f) in ours or (k2.lower(), f2.lower()) in ours:
                continue
            # zones section 16: the area's mission anim DB is installed as the zone's own zone_<leaf> DB
            if k == 'actoranimdb' and f2.lower().split('/')[-1].startswith('mission_') and \
                    ('actoranimdb', 'zone_' + ZONE.rsplit('/', 1)[-1]) in ours:
                continue
            # zones section 26: XML1's automap texture (never read by XMen2.exe) is replaced by Automaps/<zone>.zam
            if k == 'texture' and f.replace('\\', '/').startswith('textures/automap/') and \
                    ('zam', f'automaps/{ZONE}') in ours:
                continue
            missing.append((k, f))
        ok(not missing, f'zone package covers all {len(proven)} proven entries (ours {len(ours)}); missing {missing[:10]}')
        for need in [('zonexml', f'maps/{ZONE}'), ('characters', f'maps/{ZONE}'), ('boy', f'maps/{ZONE}'),
                     ('model', f'maps/{ZONE}'), ('nav', f'maps/{ZONE}'), ('actorskin', '19810'),
                     ('zam', f'automaps/{ZONE}')]:
            ok(need in ours, f'  zone package has {need}')
        # every entry resolves in <out>
        idx = C.FileIndex(out, exclude_top=C.META_NAMES)
        unres = []
        for k, f in sorted(ours):
            cands = C.package_entry_files(k, f)
            if cands is None:
                continue
            if not any(c in idx for c in cands):
                unres.append((k, f))
        ok(not unres, f'  all zone package entries resolve in <out> ({len(ours)}); unresolved {unres[:10]}')
        # XML1 effects the zone packages: converted to XML2's packed colours (no red/green/blue left)
        from xml1build import x1schema as XS
        bad = []
        neff = 0
        for k, f in sorted(ours):
            if k != 'effect':
                continue
            ep = find(out, f'Effects/{f}.XMLB')
            if ep is None:
                continue
            neff += 1
            if XS.color_channel_elements(dec(ep)):
                bad.append(f)
        ok(not bad, f'  {neff} packaged effects carry XML2 colours only (no XML1 red/green/blue); unconverted {bad[:5]}')

    # ---------------------------------------------------------------- npcstat grso_riot
    proven_stats = next(s for s in dec(SCHEME / 'Data/npcstat.XMLB').iter('stats') if s.get('name') == 'grso_riot')
    for ext in ('.XMLB', '.engb'):
        p = find(out, f'Data/npcstat{ext}')
        ents = [s for s in dec(p).iter('stats') if (s.get('name') or '').lower() == 'grso_riot'] if p else []
        ok(len(ents) == 1, f'npcstat{ext}: exactly one grso_riot entry ({len(ents)})')
        if ents:
            s = ents[0]
            ok(s.get('skin') == '19810', f'  npcstat{ext} grso_riot skin={s.get("skin")}')
            ok(s.get('characteranims') == '53_grso', f'  npcstat{ext} grso_riot characteranims={s.get("characteranims")}')
            pa = dict(proven_stats.attrib)
            if ext == '.engb':
                pa.pop('charactername', None)
            diffs = {k: (v, s.get(k)) for k, v in pa.items() if s.get(k) != v and k != 'charactername'}
            ok(not diffs, f'  npcstat{ext} grso_riot attributes match proven scheme (sounddir={s.get("sounddir")!r}); diffs {diffs}')
            kids = sorted((c.tag, tuple(sorted(c.attrib.items()))) for c in s)
            pkids = sorted((c.tag, tuple(sorted(c.attrib.items()))) for c in proven_stats)
            miss = [k for k in pkids if k not in kids]
            ok(not miss, f'  npcstat{ext} grso_riot children include proven ones; missing {miss}')
    hs = find(out, 'Data/herostat.XMLB')
    ok(hs is not None and not any((s.get('name') or '').lower() == 'grso_riot' for s in dec(hs).iter('stats')),
       'grso_riot not in herostat')

    # ---------------------------------------------------------------- character packages
    for nm in ('grso_riot_19810', 'grso_riot_19810_nc'):
        p = find(out, f'Packages/generated/characters/{nm}.PKGB')
        ok(p is not None, f'package {nm}.PKGB present')
        if p:
            ours = {(e.tag.lower(), (e.get('filename') or '').lower()) for e in dec(p)}
            proven = [(e.tag.lower(), (e.get('filename') or '').lower())
                      for e in dec(SCHEME / f'Packages/generated/characters/{nm}.PKGB')]
            miss = [x for x in proven if x not in ours]
            ok(not miss, f'  {nm} has all {len(proven)} proven entries (ours {len(ours)}); missing {miss}')

    # ---------------------------------------------------------------- actors / UI with renamed internals
    for rel in ('Actors/19810.IGB', 'Actors/53_grso.IGB', 'UI/HUD/characters/19810.IGB'):
        p = find(out, rel)
        sp = SCHEME / rel
        ok(p is not None, f'{rel} present')
        if p and sp.is_file():
            ok(p.read_bytes() == sp.read_bytes(), f'  {rel} byte-identical to the proven scheme file')
    p = find(out, 'Actors/19810.IGB')
    if p:
        data = p.read_bytes()
        for s in (b'19810', b'19810_outline', b'19810_skel'):
            ok(s in data, f'  Actors/19810.IGB contains {s.decode()!r}')
        import re
        # node names are whole NUL-terminated strings; embedded texture source paths ('58_Soldiers\\5810-7.png')
        # are not names the engine looks up and stay as in the proven file
        old = [m.group(0) for m in re.finditer(rb'(?<![0-9A-Za-z_\\/])5810(_outline|_skel)?\x00', data)]
        ok(not old, f'  Actors/19810.IGB has no old 5810 / 5810_outline / 5810_skel node names ({len(old)})')
    ok(find(out, 'Actors/5810.IGB') is None, 'no unmapped Actors/5810.IGB')

    # ---------------------------------------------------------------- sound banks
    for bank in ('n/y/nyc1_m.zsm', 'n/y/nyc1_a.zss', 'n/y/nyc1_c.zss', 'n/y/nyc1_d.zsm', 'n/y/nyc1_v.zss', 'g/r/grso_m.zsm'):
        p = find(out, f'Sounds/eng/{bank}')
        ok(p is not None, f'bank Sounds/eng/{bank} present ({p.stat().st_size if p else 0} bytes)')
        if not p:
            continue
        data = p.read_bytes()
        try:
            b = zsnd.load(str(p), strict=True)
            ok(True, f'  {bank} parses strictly (zsnd): {len(getattr(b, "samples", []) or [])} samples, '
                     f'{len(getattr(b, "sounds", []) or [])} sounds')
        except Exception as e:  # noqa: BLE001
            ok(False, f'  {bank} does not parse: {e}')
        src = IMA / bank
        tp = find(TEST, f'Sounds/eng/{bank}') or find(TEST, f'Sounds/eng/{bank}.off')
        if bank.endswith(('_a.zss', '_c.zss')):
            print(f'INFO  {bank}: music bank from the fixed-layout set (by design differs from all_ima); '
                  f'== all_ima {data == src.read_bytes()}, == xml2_test {tp is not None and data == tp.read_bytes()}')
        else:
            ok(data == src.read_bytes(), f'  {bank} byte-identical to research all_ima (the converted bank)')
            if tp is not None:
                ok(data == tp.read_bytes(), f'  {bank} byte-identical to the proven xml2_test copy ({tp.name})')

    print(f'\n{len(passes)} passed, {len(fails)} failed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
