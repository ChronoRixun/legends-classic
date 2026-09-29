"""Exhaustively find every place XML1 data refers to a skin number (or skin-named file) so a renumbering
can rewrite all of them. Scans every XML1 text XML (.xml/.eng/.chr/.nav) attribute value and every
.py script for tokens equal to a known XML1 skin id, or paths containing actors/<id>, hud_head_<id>,
characters/<id>. Prints (file-category, tag, attribute) -> count, and script hits."""
import collections, os, re
from common import *

files = x1_files()
skins = {re.match(r'actors/(\d{4,5})\.igb$', p).group(1) for p in files if re.match(r'actors/(\d{4,5})\.igb$', p)}
skins |= {re.match(r'hud/hud_head_(\d{4,5})\.igb$', p).group(1) for p in files if re.match(r'hud/hud_head_(\d{4,5})\.igb$', p)}
skins |= {re.match(r'ui/(?:hud|models)/characters/(\d{4,5})\.igb$', p).group(1) for p in files if re.match(r'ui/(?:hud|models)/characters/(\d{4,5})\.igb$', p)}
tok = re.compile(r'(?<![\d.])(\d{4,5})(?![\d.])')
hits = collections.Counter()
examples = {}
for rel, p in sorted(files.items()):
    ext = os.path.splitext(rel)[1]
    top = rel.split('/')[0]
    if ext in ('.xml', '.eng', '.chr', '.nav'):
        try:
            root = parse_x1_text(p)
        except Exception as e:
            print('parse fail', rel, e)
            continue
        for el in root.iter():
            for k, v in el.attrib.items():
                for m in tok.finditer(v):
                    if m.group(1) in skins:
                        key = (top if top != 'data' else '/'.join(rel.split('/')[:2]), el.tag.lower(), k.lower())
                        hits[key] += 1
                        examples.setdefault(key, (rel, v))
    elif ext == '.py':
        txt = open(p, encoding='latin-1').read()
        for m in re.finditer(r'["\']([^"\']*)["\']', txt):
            s = m.group(1)
            for t in tok.finditer(s):
                if t.group(1) in skins:
                    key = (top, 'py-string', re.sub(r'\d{4,5}', 'N', s)[:40])
                    hits[key] += 1
                    examples.setdefault(key, (rel, s))
print(len(skins), 'XML1 skin ids (actors/hud/ui numeric names)')
for key, n in sorted(hits.items(), key=lambda x: -x[1]):
    print(f'{n:5}  {key}  e.g. {examples[key]}')
