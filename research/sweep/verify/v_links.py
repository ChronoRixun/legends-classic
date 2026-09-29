"""Independent: zonelink nextzone/prevzone resolution across all XML1 zone files."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, json, collections
L = _REPO + r'/xml1_loose'
m = json.load(open(L + '/_fb_manifest.json'))
zones = sorted(k[len('packages/generated/maps/'):-3] for k in m
               if k.startswith('packages/generated/maps/') and not k.startswith('packages/generated/maps/package/'))
zset = set(z.lower() for z in zones)
byname = collections.defaultdict(list)
for z in zones:
    byname[z.split('/')[-1].lower()].append(z.lower())
stats = collections.Counter()
unres = collections.Counter()
attrs = collections.Counter()
for z in zones:
    zf = None
    for n, kind in m['packages/generated/maps/' + z + '.fb']:
        if kind == 'zonexml' and n.startswith('maps/' + z + '.'):
            zf = n
    if zf is None:
        stats['no_zonexml'] += 1
        continue
    p = os.path.join(L, zf)
    if not os.path.getsize(p):
        continue
    t = open(p, encoding='latin-1').read()
    for e in re.findall(r'<entity\b[^>]*>', t, re.I | re.S):
        for a in ('nextzone', 'prevzone'):
            mm = re.search(r'\b' + a + r'="([^"]*)"', e, re.I)
            if not mm:
                continue
            v = mm.group(1).strip().replace('\\', '/').lower()
            attrs[a] += 1
            if not v:
                stats[a + ':empty'] += 1
                continue
            d = z.lower().rsplit('/', 1)[0]
            if v in zset:
                stats[a + ':full'] += 1
            elif d + '/' + v in zset:
                stats[a + ':same_dir'] += 1
            elif len(byname[v.split('/')[-1]]) == 1:
                stats[a + ':unique_elsewhere'] += 1
            elif len(byname[v.split('/')[-1]]) > 1:
                stats[a + ':ambiguous'] += 1
            else:
                stats[a + ':unresolved'] += 1
                unres[(a, v)] += 1
print(dict(attrs))
for k, v in sorted(stats.items()):
    print(k, v)
print('unresolved', sorted(unres.items())[:40])
