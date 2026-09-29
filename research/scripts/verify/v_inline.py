"""Where do the inline_rewrites keys occur (file kind + attribute), and do rewritten values that end up
behind a console 'runscript' (dialog option scripts, blackbirdMenu code) contain spaces/';'?
Also check the 255-byte inline limit and presence of registered functions."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, json, collections, sys
OUT = _REPO + '/research/scripts/out'
rw = json.load(open(OUT + '/inline_rewrites.json'))
tabs = json.load(open(_REPO + '/research/scripts/verify/tables.json'))
X2 = {e[2].lower(): (e[3], e[4]) for t in tabs['xml2'].values() for e in t}
roots = [_REPO + '/xml1_loose', _REPO + '/xml1_assets']
ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
where = collections.defaultdict(set)
for root in roots:
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if not f.lower().endswith(('.eng', '.xml', '.chr')):
                continue
            p = os.path.join(dp, f)
            t = open(p, 'rb').read().decode('latin-1')
            for m in ATTR.finditer(t):
                v = m.group(2)
                if v in rw:
                    where[v].add((os.path.relpath(p, root).replace('\\', '/').split('/')[0] + '/' + os.path.relpath(p, root).replace('\\', '/').split('/')[1] if '/' in os.path.relpath(p, root).replace('\\', '/') else os.path.relpath(p, root), m.group(1).lower()))
print('rewrite keys', len(rw), 'found in data', len(where))
missing = [k for k in rw if k not in where]
print('keys not found verbatim in data files:', len(missing), missing[:5])
kinds = collections.Counter(a for v in where.values() for _, a in v)
print('attributes:', kinds.most_common())
dirs = collections.Counter(d for v in where.values() for d, _ in v)
print('dirs:', dirs.most_common(12))
# rewritten values: length, spaces, functions
longv = [(k, v) for k, v in rw.items() if len(v) > 255]
print('values > 255 chars:', len(longv))
for k, v in rw.items():
    for m in re.finditer(r'([A-Za-z_][A-Za-z0-9_.]*)\s*\(', v):
        n = m.group(1).lower()
        if n.startswith('game.'):
            n = n[5:]
        if n not in X2:
            print('   unregistered in value:', n, '|', v[:100])
# values used in dialog/option-like attributes that go through runscript
risky = []
for k, locs in where.items():
    for d, a in locs:
        if a in ('script', 'scriptok', 'scriptcancel', 'usecmd') or d.startswith('data/dialogs') or 'dialog' in d:
            v = rw[k]
            if ' ' in v or ';' in v:
                risky.append((d, a, k[:60], v[:100]))
print('rewrites with spaces/; in runscript-like attributes:', len(risky))
for r in risky[:20]:
    print('   ', r)
