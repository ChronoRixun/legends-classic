"""Exhaustive IGB meta-type check: collect the ig* meta-object/field type names serialised in every XML1
character-related IGB (actors/, hud/, ui/) and every XML2 IGB, and list XML1 types XML2 never uses
(e.g. platform-specific image/geometry types that the PC runtime might not register)."""
import collections, os, re
from common import *

TYPE = re.compile(rb'\x00(ig[A-Z][A-Za-z0-9_]+)(?=\x00)')


def types(path):
    return {m.group(1).decode() for m in TYPE.finditer(open(path, 'rb').read())}


x2 = collections.Counter()
for rel, p in x2_index().items():
    if rel.endswith('.igb'):
        x2.update(types(p))
x1 = collections.Counter()
per = collections.defaultdict(set)
for rel, p in x1_files().items():
    if rel.endswith('.igb') and rel.split('/')[0] in ('actors', 'hud', 'ui'):
        t = types(p)
        x1.update(t)
        for x in t:
            per[x].add(rel)
missing = sorted(t for t in x1 if t not in x2)
print(f'XML1 actor/hud/ui IGB types: {len(x1)}; XML2 IGB types (all files): {len(x2)}')
print('XML1 types never seen in any XML2 IGB:', missing)
for t in missing:
    print(f'  {t}: {len(per[t])} files e.g. {sorted(per[t])[:5]}')
