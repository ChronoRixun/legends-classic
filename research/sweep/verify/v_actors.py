"""Independent: XML1 actor file name collisions with XML2 Actors/, skin number ranges, pyro_hero skin evidence."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, sys, hashlib, collections
sys.path.insert(0, _REPO + r'/tools')
import xmlb

L = _REPO + r'/xml1_loose/actors'
X2 = _XML2 + r'/Actors'


def h(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


x1 = {f.lower(): os.path.join(L, f) for f in os.listdir(L)}
x2 = {f.lower(): os.path.join(X2, f) for f in os.listdir(X2)}
print('XML1 actors', len(x1), 'XML2 actors', len(x2))
common = sorted(set(x1) & set(x2))
same = [f for f in common if h(x1[f]) == h(x2[f])]
diff = [f for f in common if f not in same]
print('same name', len(common), 'identical', len(same), 'different', len(diff))
anim = [f for f in diff if not re.match(r'^\d+\.igb$', f)]
print('different non-numeric (anim dbs etc):', len(anim), anim[:40])
skins = [f for f in diff if re.match(r'^\d+\.igb$', f)]
print('different numeric skins', len(skins))
# skin number ranges
x2num = sorted(int(f[:-4]) for f in x2 if re.match(r'^\d+\.igb$', f))
x1num = sorted(int(f[:-4]) for f in x1 if re.match(r'^\d+\.igb$', f))
print('XML2 numeric skin count', len(x2num), 'max', x2num[-1], '5-digit:', [n for n in x2num if n >= 10000][:30])
print('XML1 numeric skin count', len(x1num), 'max', x1num[-1], 'min', x1num[0])
codes1 = sorted(set(n // 100 for n in x1num))
codes2 = sorted(set(n // 100 for n in x2num))
print('XML1 char codes (skin//100):', len(codes1), codes1)
print('XML2 char codes:', len(codes2))
print('XML1 codes free in XML2:', [c for c in codes1 if c not in codes2])
print('any XML2 skins in 30000-39999:', [n for n in x2num if 30000 <= n < 40000])
# Pyro_hero
hs = xmlb.decode(open(_XML2 + r'/Data/herostat.XMLB', 'rb').read())
for e in hs.iter():
    if e.attrib.get('name', '').lower() in ('pyro_hero', 'pyro'):
        print('herostat', {k: v for k, v in e.attrib.items() if k.startswith('skin') or k in ('name', 'characteranims')})
print('11401 exists', '11401.igb' in x2, '11402 exists', '11402.igb' in x2)
