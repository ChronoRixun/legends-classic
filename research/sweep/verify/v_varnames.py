import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, collections
roots = [_REPO + r'/xml1_loose/scripts', _REPO + r'/xml1_assets/scripts']
pat = re.compile(r'(?<![\w])(?:game\.)?(get|set)(MissionVar|MissionFlag|GameVar)\s*\(\s*["\']([^"\']*)["\']')
names = collections.defaultdict(set)
seen = set()
for r in roots:
    for d, _, fs in os.walk(r):
        for f in fs:
            if not f.endswith('.py'):
                continue
            rel = os.path.relpath(os.path.join(d, f), r).lower()
            if rel in seen:
                continue
            seen.add(rel)
            t = open(os.path.join(d, f), encoding='latin-1').read()
            for gs, kind, n in pat.findall(t):
                names[kind].add(n)
for k, v in names.items():
    long = sorted(n for n in v if len(n) > 11)
    print(k, 'distinct', len(v), 'max len', max(len(n) for n in v), 'names >11 chars:', len(long), long[:15])
    # prefix collisions after truncation to 11 chars
    tr = collections.defaultdict(set)
    for n in v:
        tr[n[:11].lower()].add(n)
    print('   truncation collisions (11 chars):', {a: b for a, b in tr.items() if len(b) > 1})
