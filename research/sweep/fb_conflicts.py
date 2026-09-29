"""Find files that appear in several XML1 .fb bundles with DIFFERENT content. tools/fb_unpack.py keeps only
the first copy (sorted bundle path order), so xml1_loose may hold e.g. a demo/ variant of a shared file.
Also lists 0-byte entries. Writes fb_conflicts.json."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import collections, glob, hashlib, json, os, sys
sys.path.insert(0, _REPO + r'/tools')
from fb_unpack import entries

SRC = _REPO + r'/xml1_assets'
seen = collections.defaultdict(dict)   # name -> {hash: [bundles]}
sizes = {}
empty = collections.defaultdict(list)
for fb in sorted(glob.glob(os.path.join(SRC, '**', '*.fb'), recursive=True)):
    rel = os.path.relpath(fb, SRC).replace(os.sep, '/')
    for name, kind, data in entries(fb):
        name = name.lstrip('/').lower()
        h = hashlib.md5(data).hexdigest()
        seen[name].setdefault(h, []).append(rel)
        sizes[(name, h)] = len(data)
        if not data:
            empty[name].append(rel)
conf = {n: [{'md5': h, 'size': sizes[(n, h)], 'bundles': b[:6], 'n_bundles': len(b)} for h, b in v.items()]
        for n, v in seen.items() if len(v) > 1}
# which copy did fb_unpack keep? the first bundle in sorted order
kept_first = {}
for n, variants in conf.items():
    first = min((b for v in variants for b in v['bundles']))
    kept_first[n] = first
cat = collections.Counter(n.split('/')[0] for n in conf)
demo_won = [n for n, b in kept_first.items() if '/demo/' in b]
json.dump({'conflicts': conf, 'kept_first_bundle': kept_first, 'empty_entries': empty,
           'demo_variant_kept': demo_won},
          open(_REPO + r'/research/sweep/fb_conflicts.json', 'w'), indent=1, sort_keys=True)
print('unique names', len(seen), 'conflicting names', len(conf), dict(cat))
print('conflicts where a demo/ bundle copy was kept in xml1_loose:', len(demo_won), demo_won[:30])
print('empty entries', len(empty))
for n in list(conf)[:25]:
    print('  ', n, [(v['size'], v['n_bundles'], v['bundles'][0]) for v in conf[n]])
