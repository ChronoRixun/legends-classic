import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, collections
sys.path.insert(0, _REPO + r'/tools')
import xmlb
R = _XML2 + r'/Maps'
zones = {}
for d, _, fs in os.walk(R):
    for f in fs:
        if f.lower().endswith('.xmlb'):
            rel = os.path.relpath(os.path.join(d, f), R).replace(os.sep, '/').lower()[:-5]
            zones[rel] = os.path.join(d, f)
names = collections.defaultdict(list)
for z in zones:
    names[z.split('/')[-1]].append(z)
c = collections.Counter()
ex = collections.defaultdict(list)
for z, p in zones.items():
    try:
        r = xmlb.decode(open(p, 'rb').read())
    except Exception:
        continue
    for e in r.iter():
        v = e.attrib.get('nextzone')
        if not v:
            continue
        v = v.lower().replace('\\', '/')
        d = z.rsplit('/', 1)[0]
        if '/' in v:
            k = 'full-ok' if v in zones else 'full-missing'
        elif d + '/' + v in zones:
            k = 'short-samedir'
        elif v in names:
            k = 'short-crossdir'
        else:
            k = 'short-missing'
        c[k] += 1
        if len(ex[k]) < 8:
            ex[k].append((z, v))
print(dict(c))
for k, v in ex.items():
    print(k, v)
