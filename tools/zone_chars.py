"""For built zones: every character the zone needs (.CHRB + spawner character= / monster_skin), its stats
entry, skin, and whether the character package and its files exist.

usage: zone_chars.py <build_dir> <zone> [<zone> ...]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xmlb


def load(path):
    return xmlb.decode(open(path, 'rb').read())


def main(build, zones):
    idx = {}
    for d, _, fs in os.walk(build):
        for f in fs:
            idx[os.path.relpath(os.path.join(d, f), build).replace(os.sep, '/').lower()] = 1
    stats = {}
    for f in ('Data/herostat.engb', 'Data/npcstat.engb'):
        for e in load(os.path.join(build, f)).iter('stats'):
            stats[(e.get('name') or '').lower()] = (f.split('/')[1].split('.')[0], dict(e.attrib))
    for zone in zones:
        print('==', zone)
        need = {}
        chrb = os.path.join(build, 'Maps', *zone.split('/')) + '.CHRB'
        if os.path.exists(chrb):
            for c in load(chrb).iter('character'):
                need[(c.get('name') or '').lower()] = None
        zroot = load(os.path.join(build, 'Maps', *zone.split('/')) + '.engb')
        for e in zroot.iter('entity'):
            if e.get('character'):
                need.setdefault(e.get('character').lower(), e.get('monster_skin'))
        combat_off = False
        pkg = os.path.join(build, 'Packages', 'generated', 'maps', *zone.split('/')) + '.PKGB'
        if os.path.exists(pkg):
            combat_off = any(e.tag == 'combat_is' and e.get('filename') == 'off' for e in load(pkg))
        for name, mskin in sorted(need.items()):
            st = stats.get(name)
            if st is None:
                print(f'  {name:28} NO STATS ENTRY')
                continue
            src, a = st
            skin = mskin or a.get('skin')
            suffix = '_nc' if combat_off else ''
            pk = f'packages/generated/characters/{a.get("name", name).lower()}_{skin}{suffix}.pkgb'
            have_pkg = pk in idx
            missing = []
            if have_pkg:
                for pe in load(os.path.join(build, *pk.split('/'))):
                    fn = (pe.get('filename') or '').lower()
                    if pe.tag in ('actorskin', 'actoranimdb') and not fn.startswith('actors/'):
                        fn = 'actors/' + fn
                    if pe.tag == 'effect' and not fn.startswith('effects/'):
                        fn = 'effects/' + fn
                    if not any(fn + ext in idx for ext in ('', '.igb', '.xmlb', '.engb', '.py')):
                        missing.append((pe.tag, fn))
            print(f'  {name:28} {src:8} skin={skin} anims={a.get("characteranims")} pkg={"ok" if have_pkg else "MISSING " + pk}'
                  + (f' missing-files={missing[:4]}' if missing else ''))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
