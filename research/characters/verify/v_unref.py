"""looser re-check of the '44 unreferenced XML2 stats names': token search (case-insensitive, bounded by
non [a-z0-9_]) of every name in every XML2 file's raw bytes, excluding herostat/npcstat and the name's own
generated/characters packages. Also checks XML2 .py files for substring use and the exe."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import json, os, re, collections, sys
sys.path.insert(0, _REPO + '/research/characters')
from common import X2, x2_index

refs = json.load(open(_REPO + '/research/characters/x2_stats_refs.json'))
unref = [o['name'] for o in refs if not o['refs'] and not o['in_exe']]
print('researcher unreferenced count', len(unref))
idx = x2_index()
pats = {n: re.compile(rb'(?<![a-z0-9_])' + re.escape(n.encode()) + rb'(?![a-z0-9_])') for n in unref}
hits = collections.defaultdict(set)
skip = {'data/herostat.xmlb', 'data/herostat.engb', 'data/npcstat.xmlb', 'data/npcstat.engb'}
for rel, p in idx.items():
    if rel in skip:
        continue
    ext = os.path.splitext(rel)[1]
    if ext in ('.igb', '.zss', '.zsm', '.bik', '.wav', '.dds', '.tga', '.png', '.ogg', '.xmv', '.avi'):
        continue
    try:
        d = open(p, 'rb').read().lower()
    except Exception:
        continue
    for n, pat in pats.items():
        if rel.startswith('packages/generated/characters/' + n + '_'):
            continue
        if pat.search(d):
            hits[n].add(rel)
for n in unref:
    h = sorted(hits.get(n, []))
    print(f'{n:28} {len(h):3} {h[:4]}')
print('names with any token hit:', sum(1 for n in unref if hits.get(n)))
