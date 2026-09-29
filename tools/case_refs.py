"""Find XML1 script string literals that name a map entity with different letter case.

XML1 resolved entity names case-insensitively; if XMen2.exe does not, such references silently miss (first case:
nyc/alison subwaydowna/subwaydownb -> insts subway_downA / subway_downB, so the subway teleport never fires).

usage: case_refs.py [--json out.json]
"""
import collections
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'xml1_loose')
NAME_RE = re.compile(r'<(?:entity|inst)\b[^>]*?\bname="([^"]+)"', re.I)
LIT_RE = re.compile(r'"([^"\r\n]{2,80})"')


def main():
    names_by_zone = {}
    for dp, _, fs in os.walk(os.path.join(ROOT, 'maps')):
        for f in fs:
            if f.lower().endswith(('.eng', '.xml')) and not f.lower().endswith(('.chr', '.nav')):
                zone = os.path.relpath(os.path.join(dp, f), os.path.join(ROOT, 'maps')).replace(os.sep, '/').rsplit('.', 1)[0]
                text = open(os.path.join(dp, f), encoding='latin-1', errors='replace').read()
                names_by_zone[zone] = set(NAME_RE.findall(text))
    exact = set().union(*names_by_zone.values())
    lower = collections.defaultdict(set)
    for n in exact:
        lower[n.lower()].add(n)
    hits = collections.defaultdict(list)
    for dp, _, fs in os.walk(os.path.join(ROOT, 'scripts')):
        for f in fs:
            if not f.lower().endswith('.py'):
                continue
            rel = os.path.relpath(os.path.join(dp, f), os.path.join(ROOT, 'scripts')).replace(os.sep, '/')
            text = open(os.path.join(dp, f), encoding='latin-1', errors='replace').read()
            for ln, line in enumerate(text.splitlines(), 1):
                for lit in LIT_RE.findall(line):
                    if lit in exact or lit.lower() not in lower:
                        continue
                    cands = lower[lit.lower()]
                    if lit in cands:
                        continue
                    fn = line.strip().split('(')[0].strip()
                    hits[rel].append({'line': ln, 'literal': lit, 'map_names': sorted(cands), 'call': fn})
    total = sum(len(v) for v in hits.values())
    calls = collections.Counter(h['call'] for v in hits.values() for h in v)
    print(f'{total} case-mismatched entity references in {len(hits)} scripts; by call: {dict(calls.most_common(12))}')
    for rel in sorted(hits)[:25]:
        for h in hits[rel][:3]:
            print(f'  {rel}:{h["line"]} {h["call"]}("{h["literal"]}") -> map {h["map_names"]}')
    if '--json' in sys.argv:
        out = sys.argv[sys.argv.index('--json') + 1]
        json.dump(hits, open(out, 'w'), indent=1)
        print('written', out)


if __name__ == '__main__':
    main()
