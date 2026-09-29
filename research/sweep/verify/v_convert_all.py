"""Re-run stock tools/convert_zone.Converter on all 210 zone bundles into a scratch target.
The 'existing' set is the real XML2 file list (paths only, read-only); writes go to verify/x2stub.
Only data/zoneinfo.xmlb is physically copied (the converter rewrites it)."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, json, shutil, traceback, collections
sys.path.insert(0, _REPO + r'/tools')
import convert_zone, xmlb

X1 = _REPO + r'/xml1_loose'
X2 = _XML2
OUT = _REPO + r'/research/sweep/verify/x2stub'
if os.path.exists(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT + '/Data')
shutil.copy(X2 + '/Data/zoneinfo.XMLB', OUT + '/Data/zoneinfo.XMLB')


class C(convert_zone.Converter):
    def __init__(self):
        self.x1, self.x2 = X1, OUT
        self.manifest = json.load(open(os.path.join(X1, '_fb_manifest.json')))
        self.existing = {}
        for d, _, files in os.walk(X2):
            for f in files:
                p = os.path.relpath(os.path.join(d, f), X2).replace(os.sep, '/').lower()
                self.existing[p] = os.path.join(d, f)
        self.existing['data/zoneinfo.xmlb'] = OUT + '/Data/zoneinfo.XMLB'
        self.original = set(self.existing)
        self.written, self.kept_xml2, self.missing = [], [], []


c = C()
zones = sorted(k[len('packages/generated/maps/'):-3] for k in c.manifest
               if k.startswith('packages/generated/maps/') and not k.startswith('packages/generated/maps/package/'))
print('zones', len(zones))
errs = []
per_zone_kept = {}
for z in zones:
    k0 = len(c.kept_xml2)
    try:
        c.zone(z)
    except Exception as ex:
        errs.append((z, repr(ex)[:200]))
    per_zone_kept[z] = c.kept_xml2[k0:]
print('errors', len(errs))
for e in errs:
    print('  ', e)
print('written', len(c.written), 'kept_xml2 refs', len(c.kept_xml2), 'missing', len(c.missing))
kept_actors = [k for k in c.kept_xml2 if k.startswith('actors/')]
print('kept XML2 actor references (per zone, summed):', len(kept_actors), 'distinct', len(set(kept_actors)))
kc = collections.Counter(k.split('/')[0] for k in c.kept_xml2)
print('kept by top dir', kc.most_common())
zones_with_kept = sum(1 for z, v in per_zone_kept.items() if v)
print('zones with any kept XML2 file', zones_with_kept)
# invalid tiny XMLB outputs
tiny = []
for d, _, fs in os.walk(OUT):
    for f in fs:
        p = os.path.join(d, f)
        if os.path.getsize(p) <= 8:
            tiny.append(os.path.relpath(p, OUT))
print('outputs <= 8 bytes', len(tiny), tiny[:10])
zero = []
for d, _, fs in os.walk(OUT):
    for f in fs:
        if os.path.getsize(os.path.join(d, f)) == 0:
            zero.append(os.path.relpath(os.path.join(d, f), OUT))
print('zero-byte outputs', zero)
json.dump({'errors': errs, 'missing': c.missing, 'kept': per_zone_kept}, open(OUT + '_result.json', 'w'), indent=0)
