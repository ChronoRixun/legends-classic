"""Resolve every entry of zone packages against a build tree; list missing or zero-size files.

usage: pkg_resolve.py <build_dir> <zone> [<zone> ...]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xmlb

PRE = {'actorskin': 'actors/', 'actoranimdb': 'actors/', 'effect': 'effects/'}
EXTS = ('', '.igb', '.xmlb', '.engb', '.py', '.navb', '.chrb', '.boyb', '.zam')


def main(build, zones):
    idx = {}
    for d, _, fs in os.walk(build):
        for f in fs:
            p = os.path.join(d, f)
            idx[os.path.relpath(p, build).replace(os.sep, '/').lower()] = os.path.getsize(p)
    for z in zones:
        pkg = os.path.join(build, 'Packages', 'generated', 'maps', *z.split('/')) + '.PKGB'
        entries = list(xmlb.decode(open(pkg, 'rb').read()))
        miss, zero = [], []
        for e in entries:
            fn = (e.get('filename') or '').lower().replace(chr(92), '/')
            if fn in ('on', 'off'):
                continue
            pre = PRE.get(e.tag, '')
            if pre and not fn.startswith(pre):
                fn = pre + fn
            hit = next((fn + x for x in EXTS if fn + x in idx), None)
            if hit is None:
                miss.append((e.tag, fn))
            elif idx[hit] == 0:
                zero.append(hit)
        print(z, 'entries', len(entries), 'missing', miss, 'zero-size', zero)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
