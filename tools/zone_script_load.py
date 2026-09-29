"""Count script statements each zone package pulls in (XMen2.exe has a 620 instruction-node pool).

usage: zone_script_load.py <build_dir> [<zone> ...]   (no zones: all zones in _tour.json order)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xmlb


def statements(path):
    n = 0
    for line in open(path, 'rb').read().decode('latin-1').split('\r\n'):
        s = line.strip()
        if s and not s.startswith('#'):
            n += 1
    return n


def zone_load(build, zone):
    pkg = os.path.join(build, 'Packages', 'generated', 'maps', *zone.split('/')) + '.PKGB'
    if not os.path.exists(pkg):
        return None, 0
    total, count = 0, 0
    for e in xmlb.decode(open(pkg, 'rb').read()):
        if e.tag != 'script':
            continue
        fn = (e.get('filename') or '').replace('\\', '/')
        for cand in (fn + '.py', fn + '.PY'):
            p = os.path.join(build, *cand.split('/'))
            if os.path.exists(p):
                total += statements(p)
                count += 1
                break
            p = os.path.join(build, 'Scripts', *cand.split('/')[1:]) if cand.lower().startswith('scripts/') else None
            if p and os.path.exists(p):
                total += statements(p)
                count += 1
                break
    return total, count


if __name__ == '__main__':
    build = sys.argv[1]
    zones = sys.argv[2:] or json.load(open(os.path.join(build, '_tour.json')))['order']
    rows = [(z, *zone_load(build, z)) for z in zones]
    for z, total, count in sorted(rows, key=lambda r: -(r[1] or 0))[:25]:
        print(f'{total:5} statements in {count:3} scripts  {z}')
