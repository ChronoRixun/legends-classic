"""For a singleton getter, list which script functions call which vtable slot on it (XML1 vs XML2)."""
import re, json, collections, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))


def scan(asm, getter, lo, hi, api):
    lines = open(os.path.join(HERE, asm)).read().splitlines()
    fs = sorted((int(v['func'], 16), k) for k, v in json.load(open(os.path.join(HERE, api))).items())
    res = collections.defaultdict(set)
    for i, l in enumerate(lines):
        try:
            a = int(l.split()[0], 16)
        except (ValueError, IndexError):
            continue
        if not (lo <= a < hi):
            continue
        if l.endswith('call 0x' + getter):
            for w in lines[i + 1:i + 8]:
                m = re.search(r'call dword ptr \[e[a-d]x \+ (0x[0-9a-f]+)\]$', w)
                if m:
                    fn = [f for f in fs if f[0] <= a]
                    res[m.group(1)].add(fn[-1][1] if fn else '?')
                    break
    return res


g1, g2 = sys.argv[1], sys.argv[2]
r1 = scan('xml1_text.asm', g1, 0x98000, 0xa2000, 'xml1_api.json')
r2 = scan('xml2_text.asm', g2, 0x49d000, 0x4a9000, 'xml2_api.json')
for k in sorted(set(r1) | set(r2), key=lambda x: int(x, 16)):
    print(k, 'XML1:', sorted(r1.get(k, [])), ' XML2:', sorted(r2.get(k, [])))
