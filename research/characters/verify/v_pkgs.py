"""empirical check of package naming: XML2 stats name + skin -> packages/generated/characters/<name>_<skin>[_nc].pkgb"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, sys, collections
sys.path.insert(0, _REPO + '/research/characters')
from common import load_xmlb, X2, x2_index

idx = x2_index()
pk = {p for p in idx if p.startswith('packages/generated/characters/')}
print('character packages', len(pk))
res = collections.Counter()
missing = []
for f in ('herostat', 'npcstat'):
    for st in load_xmlb(f'{X2}/Data/{f}.XMLB').iter('stats'):
        n = st.get('name').lower()
        s = st.get('skin')
        for suf in ('', '_nc'):
            p = f'packages/generated/characters/{n}_{s}{suf}.pkgb'
            ok = p in pk
            res[(f, suf, ok)] += 1
            if not ok:
                missing.append(p)
print(res)
print('missing examples', missing[:15])
# package names that don't match any stats name
stats_names = set()
for f in ('herostat', 'npcstat'):
    stats_names |= {st.get('name').lower() for st in load_xmlb(f'{X2}/Data/{f}.XMLB').iter('stats')}
unmatched = []
for p in sorted(pk):
    b = os.path.basename(p)[:-5]
    m = re.fullmatch(r'(.+)_(\d{4,5})(_nc)?', b)
    if not m or m.group(1) not in stats_names:
        unmatched.append(b)
print('packages not matching <statsname>_<skin>[_nc]:', len(unmatched), unmatched[:30])
