"""Count stats entries / unique names in XML2 herostat+npcstat (both .xmlb and .engb) and XML1."""
import collections
from common import *

for ext in ('XMLB', 'engb'):
    names = []
    for f in ('herostat', 'npcstat'):
        root = load_xmlb(f'{X2}/Data/{f}.{ext}')
        for st in root.iter('stats'):
            names.append((f, st.get('name'), st.get('platform')))
    low = collections.Counter(n.lower() for _, n, _ in names)
    exact = collections.Counter(n for _, n, _ in names)
    print(f'XML2 {ext}: entries={len(names)} unique(case-insens)={len(low)} unique(exact)={len(exact)}')
    print('  dup names:', [(n, c) for n, c in low.items() if c > 1])
    print('  platform-tagged:', [(f, n, p) for f, n, p in names if p])

x1 = []
for f in ('herostat', 'npcstat'):
    root = parse_x1_text(f'{X1L}/data/{f}.eng')
    for st in root.iter('stats'):
        x1.append((f, st.get('name')))
low1 = collections.Counter(n.lower() for _, n in x1)
print(f'XML1: entries={len(x1)} unique(case-insens)={len(low1)} dups={[n for n, c in low1.items() if c > 1]}')
x2names = {n.lower() for _, n, _ in names}
shared = sorted(n for n in low1 if n in x2names)
print(f'XML1 names also present in XML2 ({len(shared)}):', shared)
print(f'XML1-only names: {len(low1) - len(shared)}; union = {len(x2names | set(low1))}')
