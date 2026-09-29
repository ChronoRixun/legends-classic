"""Decompile every XMLB-family file of the XML2 install to text under research/characters/x2text/
(mirror of the install tree, lowercase paths, '.txt' appended) so it can be grepped."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys
sys.path.insert(0, _REPO + '/tools')
import xmlb

X2 = _XML2
OUT = _REPO + '/research/characters/x2text'
EXTS = ('.xmlb', '.engb', '.chrb', '.navb', '.boyb', '.pkgb')
n = bad = 0
for d, _, files in os.walk(X2):
    for f in files:
        if not f.lower().endswith(EXTS):
            continue
        src = os.path.join(d, f)
        rel = os.path.relpath(src, X2).replace(os.sep, '/').lower()
        dst = os.path.join(OUT, rel + '.txt')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            txt = xmlb.to_text(xmlb.decode(open(src, 'rb').read()))
        except Exception as e:
            bad += 1
            print('fail', rel, e)
            continue
        open(dst, 'w', encoding='latin-1').write(txt)
        n += 1
print('decoded', n, 'failed', bad)
