"""For every XML1 zone (zone xml with soundfile=), collect the sound names its package uses (zone xml, conversations,
dialogs, scripts, fight/powerstyles listed in its .fb bundle) and simulate XML2's lookup against:
  A) the zone's converted banks + XML2's own x_common/x_voice (what a straight drop-in gives)
  B) A + XML1's x_common/x_voice entries (what merge_zsnd.py adds)
Keys are preserved by convert_zsnd.py, so the XML1 originals stand in for the converted banks here."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, json, collections
import zsnd
from simlookup import load_banks, resolve, names_from

X1 = _REPO + '/xml1_xbox/sounds/zsds'
X2 = _XML2 + '/Sounds/eng'
LOOSE = _REPO + '/xml1_loose'
man = json.load(open(LOOSE + '/_fb_manifest.json'))

def zone_banks(z):
    out = []
    for suf in 'macvd':
        for ext in ('zsm', 'zss'):
            p = '%s/%s/%s/%s_%s.%s' % (X1, z[0], z[1], z, suf, ext)
            if os.path.exists(p):
                out.append(p)
                break
    return out

cache = {}
def banks(paths):
    k = tuple(paths)
    if k not in cache:
        cache[k] = load_banks(paths)
    return cache[k]

G2 = [X2 + '/x/_/x_common.zsm', X2 + '/x/_/x_voice.zss']
ZONES = set(os.path.basename(p).rsplit('_', 1)[0] for p in zsnd.iter_banks(X1) if re.search(r'_[acdv]\.zs[sm]$', p))
CHAR = [p for p in zsnd.iter_banks(X1) if os.path.basename(p).rsplit('_', 1)[0] not in ZONES
        and not os.path.basename(p).startswith(('x_', 'menu_'))]
G1 = [X1 + '/x/_/x_common.zsm', X1 + '/x/_/x_voice.zss']
tot = collections.Counter()
miss_names = collections.Counter()
rows = []
for bundle, files in sorted(man.items()):
    zx = [f for f, k in files if k == 'zonexml' and f.endswith('.eng')]
    if not zx:
        continue
    zpath = os.path.join(LOOSE, zx[0])
    if not os.path.exists(zpath):
        continue
    m = re.search(r'soundfile="([^"]+)"', open(zpath, 'rb').read().decode('latin-1'))
    if not m:
        continue
    z = m.group(1).lower()
    srcs = [os.path.join(LOOSE, f) for f, k in files if f.endswith(('.eng', '.xml', '.py')) and k in ('zonexml', 'xml', 'xml_resident', 'script', 'fightstyle')]
    names = sorted(set(n.replace('\\', '/').lower() for n in names_from([s for s in srcs if os.path.exists(s)])))
    zb = zone_banks(z)
    A = banks(zb + CHAR + G2)
    B = banks(zb + CHAR + G2 + G1)
    ra = [resolve(n, z, A) for n in names]
    rb = [resolve(n, z, B) for n in names]
    na = sum(1 for r in ra if r[1]); nb = sum(1 for r in rb if r[1])
    for n, r in zip(names, rb):
        if not r[1]:
            miss_names[n] += 1
    rows.append((bundle.split('generated/maps/')[-1], z, len(names), na, nb))
    tot['names'] += len(names); tot['A'] += na; tot['B'] += nb
for r in rows:
    print('%-42s soundfile=%-7s names=%3d  zone+char banks+xml2 globals=%3d  +xml1 globals=%3d' % r)
print(dict(tot))
print('most common unresolved (after merge):', miss_names.most_common(40))
