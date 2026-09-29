import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, 'inline_scan.json')))
files = set()
for r in [_REPO + '/xml1_loose/scripts', _REPO + '/xml1_assets/scripts']:
    for dp, dn, fn in os.walk(r):
        for f in fn:
            if f.lower().endswith('.py'):
                files.add(os.path.join(dp, f).replace(os.sep, '/').split('/scripts/', 1)[1][:-3].lower())
fixed = 0
still = []
bs = 0
for k, v in d['refs_missing'].items():
    if chr(92) in k:
        bs += v
    n = k.replace(chr(92), '/').lower().strip()
    if n in files:
        fixed += v
    else:
        still.append((k, v))
print('refs using backslashes:', bs)
print('resolved after normalising slashes+case:', fixed, '; still missing:', len(still), sum(v for k, v in still))
for k, v in sorted(still):
    print('  ', v, k)
