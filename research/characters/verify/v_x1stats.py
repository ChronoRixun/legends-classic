"""XML1 stats: races, skin_* costume attrs, skin prefixes (all XML1 numeric actor ids), weapon usage."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, sys, collections
sys.path.insert(0, _REPO + '/research/characters')
from common import parse_x1_text, X1L, X2, x2_index

races = collections.Counter()
costumes = collections.Counter()
skins = []
for f in ('herostat', 'npcstat'):
    r = parse_x1_text(f'{X1L}/data/{f}.eng')
    for st in r.iter('stats'):
        a = {k.lower(): v for k, v in st.attrib.items()}
        for k in a:
            if k.startswith('skin_'):
                costumes[k] += 1
        skins.append(a.get('skin'))
        for c in st:
            if c.tag.lower() == 'race':
                races[c.get('name').lower()] += 1
print('races', dict(races))
print('costume attrs', dict(costumes))
print('stats skins non-4-digit', [s for s in skins if not re.fullmatch(r'\d{4}', s or '')])

# all numeric actor files in XML1 and XML2
x1ids = sorted({os.path.splitext(f)[0] for f in os.listdir(f'{X1L}/actors') if re.fullmatch(r'\d+\.igb', f.lower())})
x2ids = sorted({os.path.splitext(f)[0] for f in os.listdir(f'{X2}/Actors') if re.fullmatch(r'\d+\.igb', f.lower())})
print('XML1 numeric actor files', len(x1ids), 'lengths', collections.Counter(len(s) for s in x1ids))
print('XML2 numeric actor files', len(x2ids), 'lengths', collections.Counter(len(s) for s in x2ids))
p1 = sorted({int(s[:-2]) for s in x1ids})
p2 = sorted({int(s[:-2]) for s in x2ids})
print('XML1 prefixes', p1)
print('XML1 has prefix 60?', 60 in p1, ' XML1 max prefix', max(p1))
print('XML2 prefixes min/max', min(p2), max(p2), 'set>=136', [p for p in p2 if p >= 136])
mapped = {str(int(s) + 14000) for s in x1ids}
x2set = set(x2ids)
print('mapped ids colliding with XML2 actors:', sorted(mapped & x2set))
print('mapped prefixes colliding with XML2 prefixes:', sorted({int(m[:-2]) for m in mapped} & set(p2)))
# hud heads / ui across XML2
idx = x2_index()
ui = [p for p in idx if re.search(r'(hud_head_|ui/hud/characters/|ui/models/characters/)(\d+)\.igb$', p)]
uip = sorted({int(re.search(r'(\d+)\.igb$', p).group(1)[:-2]) for p in ui})
print('XML2 hud/ui numeric prefixes max', max(uip), [p for p in uip if p >= 136])
mapped_ui = [p for p in ui if int(re.search(r'(\d+)\.igb$', p).group(1)) >= 14000]
print('XML2 hud/ui ids >=14000', mapped_ui[:10])
# every skin-like id referenced anywhere in XML2 text dumps with prefix 140-239
