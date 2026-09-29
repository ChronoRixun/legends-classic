"""independent recount of XML2 stats names; checks output npcstat diff vs XML2."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, collections
sys.path.insert(0, _REPO + '/tools')
import xmlb

X2 = _XML2
OUT = _REPO + '/research/characters/out'


def names(path):
    r = xmlb.decode(open(path, 'rb').read())
    return [(s.get('name'), s.get('platform')) for s in r.iter('stats')], r


tot = {}
for ext in ('XMLB', 'engb'):
    h, _ = names(f'{X2}/Data/herostat.{ext}')
    n, _ = names(f'{X2}/Data/npcstat.{ext}')
    allk = [a.lower() for a, _ in h + n]
    print(ext, 'herostat', len(h), 'npcstat', len(n), 'unique', len(set(allk)),
          'platforms', collections.Counter(p for _, p in h + n))
    tot[ext] = n

# diff of the prototype npcstat against the original
for v in ('grso_riot_scheme', 'grso_riot_orig', 'grso_riot_animprefix'):
    for ext in ('XMLB', 'engb'):
        o = xmlb.decode(open(f'{X2}/Data/npcstat.{ext}', 'rb').read())
        m = xmlb.decode(open(f'{OUT}/{v}/Data/npcstat.{ext}', 'rb').read())
        a, b = list(o), list(m)
        d = [(i, x.get('name'), y.get('name')) for i, (x, y) in enumerate(zip(a, b))
             if xmlb.to_text(x) != xmlb.to_text(y)]
        print(v, ext, len(a), len(b), 'diffs', d)
    x = open(f'{OUT}/{v}/Data/npcstat.XMLB', 'rb').read()
    y = open(f'{OUT}/{v}/Data/npcstat.engb', 'rb').read()
    print(v, 'XMLB == engb bytes:', x == y)
ox = open(f'{X2}/Data/npcstat.XMLB', 'rb').read()
oy = open(f'{X2}/Data/npcstat.engb', 'rb').read()
print('XML2 original npcstat XMLB == engb:', ox == oy, len(ox), len(oy))
ta = xmlb.decode(ox); tb = xmlb.decode(oy)
diffs = [(x.get('name'), ) for x, y in zip(ta, tb) if xmlb.to_text(x) != xmlb.to_text(y)]
print('XML2 XMLB vs engb differing entries:', len(diffs), diffs[:10])
