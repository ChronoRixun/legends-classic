import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, sys, collections
sys.path.insert(0, _REPO + '/research/characters')
from common import X2, load_xmlb
names = {st.get('name').lower() for f in ('herostat', 'npcstat') for st in load_xmlb(f'{X2}/Data/{f}.XMLB').iter('stats')}
tok = collections.Counter()
for d, _, fs in os.walk(X2 + '/Conversations'):
    for f in fs:
        if f.lower().endswith('.engb'):
            for m in re.finditer(rb'%([A-Za-z0-9_]+)%', open(os.path.join(d, f), 'rb').read()):
                tok[m.group(1).decode().lower()] += 1
match = {t: c for t, c in tok.items() if t in names}
print('distinct %TOKEN%', len(tok), 'matching stats names', len(match))
print('non-matching', sorted((t, c) for t, c in tok.items() if t not in names)[:30])
