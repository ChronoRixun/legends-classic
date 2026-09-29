"""Offline report on one built zone: files present, package entries that do not resolve, sizes, script.

usage: zone_report.py <build_dir> <zone> [<zone> ...]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xmlb

KIND_DIRS = {'actorskin': 'actors/', 'actoranimdb': 'actors/'}


def index(build):
    idx = {}
    for d, _, fs in os.walk(build):
        for f in fs:
            rel = os.path.relpath(os.path.join(d, f), build).replace(os.sep, '/').lower()
            idx[rel] = os.path.getsize(os.path.join(d, f))
    return idx


def resolve(idx, kind, fn):
    fn = fn.lower().replace('\\', '/')
    if kind in KIND_DIRS and not fn.startswith(KIND_DIRS[kind]):
        fn = KIND_DIRS[kind] + fn
    for cand in (fn, fn + '.igb', fn + '.xmlb', fn + '.engb', fn + '.py', fn + '.navb', fn + '.chrb', fn + '.boyb'):
        if cand in idx:
            return cand
    return None


def report(build, idx, zone):
    print('==', zone)
    base = 'maps/' + zone.lower()
    files = {k: v for k, v in idx.items() if k.startswith(base + '.')}
    print('  zone files:', {k.rsplit('.', 1)[1]: v for k, v in files.items()})
    pkg = os.path.join(build, 'Packages', 'generated', 'maps', *zone.split('/')) + '.PKGB'
    if not os.path.exists(pkg):
        print('  NO PACKAGE', pkg)
        return
    entries = list(xmlb.decode(open(pkg, 'rb').read()))
    missing, total = [], 0
    for e in entries:
        fn = e.get('filename') or ''
        if fn in ('on', 'off'):
            continue
        r = resolve(idx, e.tag, fn)
        if r is None:
            missing.append((e.tag, fn))
        else:
            total += idx[r]
    print(f'  package entries {len(entries)}, resolved bytes {total / 1e6:.1f} MB, unresolved {len(missing)}')
    for m in missing[:15]:
        print('   missing', m)
    zx = os.path.join(build, 'Maps', *zone.split('/')) + '.XMLB'
    for cand in (zx, zx[:-5] + '.engb'):
        if os.path.exists(cand):
            root = xmlb.decode(open(cand, 'rb').read())
            world = next((el for el in root.iter('entity') if el.get('name') == 'world'), None)
            ents = sum(1 for _ in root.iter('entity'))
            insts = sum(1 for _ in root.iter('inst'))
            print(f'  {os.path.basename(cand)}: entities {ents}, instances {insts}, world {dict(world.attrib) if world is not None else None}')
            break


if __name__ == '__main__':
    build = sys.argv[1]
    idx = index(build)
    for z in sys.argv[2:]:
        report(build, idx, z)
