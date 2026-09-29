"""Compare the name sets (animation names etc., bones excluded) inside same-named XML1/XML2 actor IGBs
(anim DBs incl. fightstyle_*). Reports how many XML1 names are missing from the XML2 file."""
import json, os, re
from common import *
from igbstr import names

idx = x2_index()
col = json.load(open(os.path.join(HERE, 'collisions.json')))
rows = []
for cat in ('actors/other(fightstyle)', 'actors/animdb(NN_name)', 'actors/other(misc)'):
    for rel in col[cat].get('collision', []):
        a = {n for n in names(os.path.join(X1L, rel)) if not n.startswith('Bip01') and re.match(r'^[\w .-]+$', n) and len(n) > 3}
        b = {n for n in names(idx[rel]) if not n.startswith('Bip01') and re.match(r'^[\w .-]+$', n) and len(n) > 3}
        miss = sorted(a - b)
        rows.append((rel, len(a), len(b), len(a & b), miss))
for rel, na, nb, both, miss in rows:
    print(f'{rel:36} x1={na:4} x2={nb:4} shared={both:4} x1_missing_in_x2={len(miss):4} {miss[:8]}')
