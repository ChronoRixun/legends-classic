"""Names played by XML1 scripts via sound("PLAY_SOUND", "<name>", ...) -- not captured by simlookup.names_from.
Resolve them per zone (script dir -> maps dir -> world soundfile) like zone_coverage.py variant A."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, sys, collections
sys.path.insert(0, _REPO + '/research/sound')
from simlookup import load_banks, resolve
import zsnd

LOOSE = _REPO + '/xml1_loose'
X1 = _REPO + '/xml1_xbox/sounds/zsds'
X2 = _XML2 + '/Sounds/eng'
rx = re.compile(r'\bsound\s*\(\s*"PLAY_SOUND"\s*,\s*"([^"]+)"', re.I)
# map dir -> soundfiles
dir_sf = collections.defaultdict(set)
for dp, dn, fn in os.walk(LOOSE + '/maps'):
    for f in fn:
        if f.endswith('.eng'):
            m = re.search(r'soundfile="([^"]+)"', open(os.path.join(dp, f), 'rb').read().decode('latin-1'))
            if m:
                rel = os.path.relpath(dp, LOOSE + '/maps').replace('\\', '/')
                dir_sf[rel].add(m.group(1).lower())
ZONES = set(os.path.basename(p).rsplit('_', 1)[0] for p in zsnd.iter_banks(X1) if re.search(r'_[acdv]\.zs[sm]$', p))
CHAR = [p for p in zsnd.iter_banks(X1) if os.path.basename(p).rsplit('_', 1)[0] not in ZONES
        and not os.path.basename(p).startswith(('x_', 'menu_'))]
G2 = [X2 + '/x/_/x_common.zsm', X2 + '/x/_/x_voice.zss']
cache = {}
tot = ok = nozone = 0
misses = collections.Counter()
for dp, dn, fn in os.walk(LOOSE + '/scripts'):
    for f in fn:
        if not f.endswith('.py'):
            continue
        t = open(os.path.join(dp, f), 'rb').read().decode('latin-1')
        names = set(n.replace('\\', '/').lower() for n in rx.findall(t))
        if not names:
            continue
        rel = os.path.relpath(dp, LOOSE + '/scripts').replace('\\', '/')
        sfs = dir_sf.get(rel) or set()
        if not sfs:
            nozone += len(names)
            for n in names:
                misses['(no zone for %s) %s' % (rel, n)] += 1
            continue
        for n in names:
            tot += 1
            hit = False
            for z in sfs:
                zb = []
                for suf in 'macvd':
                    for ext in ('zsm', 'zss'):
                        p = '%s/%s/%s/%s_%s.%s' % (X1, z[0], z[1], z, suf, ext)
                        if os.path.exists(p):
                            zb.append(p); break
                key = (z,)
                if key not in cache:
                    cache[key] = load_banks(zb + CHAR + G2)
                if resolve(n, z, cache[key])[1]:
                    hit = True
            ok += hit
            if not hit:
                misses[n] += 1
print('script PLAY_SOUND names (per script file, zone-resolvable): %d resolved / %d ; names in scripts without a zone dir: %d' % (ok, tot, nozone))
print(misses.most_common(25))
