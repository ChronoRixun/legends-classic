"""Decode all XML2 dialogs and generated x1 dialogs; list tags/attributes and check option scripts."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, collections
sys.path.insert(0, _REPO + '/tools')
import xmlb

def walk(root):
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if f.lower().endswith(('.xmlb', '.engb')):
                yield os.path.join(dp, f)

def stats(root, show=3):
    tags = collections.Counter()
    attrs = collections.defaultdict(collections.Counter)
    scripts = []
    shown = 0
    for p in walk(root):
        e = xmlb.decode(open(p, 'rb').read())
        for el in e.iter():
            tags[el.tag] += 1
            for k, v in el.attrib.items():
                attrs[el.tag][k] += 1
                if 'script' in k.lower():
                    scripts.append((os.path.relpath(p, root), el.tag, k, v))
        if shown < show:
            print('----', p)
            print(xmlb.to_text(e)[:800] if hasattr(xmlb, 'to_text') else e)
            shown += 1
    print('tags', dict(tags))
    for t, c in attrs.items():
        print('  ', t, dict(c))
    return scripts

print('== XML2')
s2 = stats(_XML2 + '/Dialogs', 2)
for s in s2[:30]:
    print('   ', s)
print('== x1 generated')
s1 = stats(_REPO + '/research/scripts/out/dialogs/x1', 0)
L = [len('runscript ' + v) for _, _, _, v in s1]
sp = [v for _, _, _, v in s1 if ' ' in v or ';' in v]
print('option scripts', len(s1), 'max runscript cmd len', max(L), 'with space/semicolon', len(sp), sp[:5])
print(sorted(set(v for _, _, _, v in s1))[:20])
long_ = [v for _, _, _, v in s1 if len('runscript ' + v) > 127]
print('over 127 chars:', long_)
