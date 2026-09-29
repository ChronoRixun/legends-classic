import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, collections
sys.path.insert(0, _REPO + '/research/characters')
from common import parse_x1_text, load_xmlb, X1L, X2
x1 = collections.Counter(); x2 = collections.Counter(); ch1 = collections.Counter()
for f in ('herostat', 'npcstat'):
    for st in parse_x1_text(f'{X1L}/data/{f}.eng').iter('stats'):
        for k in st.attrib: x1[k.lower()] += 1
        for c in st: ch1[c.tag.lower()] += 1
    for st in load_xmlb(f'{X2}/Data/{f}.XMLB').iter('stats'):
        for k in st.attrib: x2[k.lower()] += 1
exe = open(X2 + '/XMen2.exe', 'rb').read().lower()
only1 = sorted(k for k in x1 if k not in x2)
print('XML1-only stats attrs:', [(k, x1[k], (b'\0' + k.encode() + b'\0') in exe) for k in only1])
print('XML1 children:', dict(ch1))
