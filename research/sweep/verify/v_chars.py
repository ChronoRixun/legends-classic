"""Independent check: characters referenced by XML1 zone .chr files vs XML1/XML2 stat tables."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, sys, json, collections
sys.path.insert(0, _REPO + r'/tools')
import xmlb

L = _REPO + r'/xml1_loose'
A = _REPO + r'/xml1_assets/data'
X2 = _XML2 + r'/Data'


def names_text(path):
    t = open(path, encoding='latin-1').read()
    return set(m.lower() for m in re.findall(r'<stats\s[^>]*?\bname="([^"]*)"', t, re.I))


def names_bin(path):
    root = xmlb.decode(open(path, 'rb').read())
    out = set()
    for e in root.iter():
        if e.tag.lower() == 'stats' and 'name' in e.attrib:
            out.add(e.attrib['name'].lower())
    return out


x1 = names_text(A + '/npcstat.eng') | names_text(A + '/herostat.eng')
x2 = set()
for f in ('npcstat.XMLB', 'npcstat.engb', 'herostat.XMLB', 'herostat.engb'):
    s = names_bin(os.path.join(X2, f))
    print(f, len(s))
    x2 |= s
print('XML1 stat names', len(x1), 'XML2 stat names', len(x2))

zone_chars = collections.defaultdict(set)
for d, _, fs in os.walk(L + '/maps'):
    for f in fs:
        if f.endswith('.chr'):
            p = os.path.join(d, f)
            t = open(p, encoding='latin-1').read()
            for m in re.findall(r'<character\s[^>]*?name="([^"]*)"', t, re.I):
                zone_chars[m.lower()].add(os.path.relpath(p, L).replace(os.sep, '/'))
allc = set(zone_chars)
print('distinct characters in zone .chr files', len(allc))
print('  in XML1 stats', len(allc & x1), ' not in XML1', sorted(allc - x1))
print('  in XML2 stats', len(allc & x2), ' missing from XML2', len(allc - x2))
print('  present in XML2:', sorted(allc & x2))
print('  grso_riot in x2?', 'grso_riot' in x2, ' in x1?', 'grso_riot' in x1)
