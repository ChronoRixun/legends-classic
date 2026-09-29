"""independent same-path collision counts (XML1 loose vs XML2 install), bytes for IGB; tree-compare for XML."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, sys, collections, hashlib
sys.path.insert(0, _REPO + '/research/characters')
from common import X1L, X2, x2_index, parse_x1_text, load_xmlb, canon

idx = x2_index()
cats = collections.defaultdict(lambda: collections.Counter())


def h(p):
    return hashlib.sha1(open(p, 'rb').read()).digest()


for d, _, fs in os.walk(X1L):
    for f in fs:
        p = os.path.join(d, f)
        rel = os.path.relpath(p, X1L).replace(os.sep, '/').lower()
        stem, ext = os.path.splitext(rel)
        if rel.startswith('actors/') and ext == '.igb':
            c = 'actors_skin' if re.fullmatch(r'actors/\d{4}', stem) else (
                'actors_fightstyle' if re.match(r'actors/(fightstyle_|moveset_)', stem) else
                'actors_common' if stem == 'actors/common' else 'actors_anim')
        elif rel.startswith('hud/hud_head_'):
            c = 'hud_head'
        elif rel.startswith('ui/hud/characters/'):
            c = 'ui_hud_chars'
        elif rel.startswith('ui/models/characters/'):
            c = 'ui_models_chars'
        elif rel.startswith('data/powerstyles/') and ext in ('.eng', '.xml'):
            c = 'powerstyles'
        elif rel.startswith('data/fightstyles/') and ext in ('.eng', '.xml'):
            c = 'fightstyles'
        else:
            continue
        cats[c]['total'] += 1
        if ext == '.igb':
            q = idx.get(rel)
            if q is None:
                continue
            cats[c]['same_name'] += 1
            cats[c]['identical' if h(p) == h(q) else 'differ'] += 1
        else:
            q = idx.get(stem + '.xmlb')
            if q is None:
                continue
            cats[c]['same_name'] += 1
            a = canon(parse_x1_text(p))
            b = canon(load_xmlb(q))
            cats[c]['identical' if a == b else 'differ'] += 1
for c, v in sorted(cats.items()):
    print(f'{c:20} {dict(v)}')
