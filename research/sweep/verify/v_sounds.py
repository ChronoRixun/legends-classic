import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, collections
L = _REPO + r'/xml1_loose/maps'
S1 = _REPO + r'/xml1_xbox/sounds/zsds'
S2 = _XML2 + r'/Sounds'
banks = collections.defaultdict(set)
for d, _, fs in os.walk(L):
    for f in fs:
        if f.endswith(('.xml', '.eng')):
            t = open(os.path.join(d, f), encoding='latin-1').read()
            for m in re.finditer(r'<entity\b[^>]*>', t, re.I):
                e = m.group(0)
                if re.search(r'\bname="world"', e, re.I):
                    s = re.search(r'\bsoundfile="([^"]*)"', e, re.I)
                    if s:
                        banks[s.group(1).lower()].add(os.path.relpath(os.path.join(d, f), L))


def bankset(root):
    out = set()
    for d, _, fs in os.walk(root):
        for f in fs:
            m = re.match(r'^(.*)_[acdmv]\.(zss|zsm)$', f, re.I)
            if m:
                out.add(m.group(1).lower())
    return out


b1 = bankset(S1)
b2 = bankset(S2)
print('world soundfile banks', len(banks))
print('  in XML1 zsds', len([b for b in banks if b in b1]), ' missing:', {b: sorted(banks[b])[:3] for b in banks if b not in b1})
print('  in XML2', [b for b in banks if b in b2])
print('XML1 banks', len(b1), 'XML2 banks', len(b2), 'collide', len(b1 & b2), sorted(b1 & b2))
