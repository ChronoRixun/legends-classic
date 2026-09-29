import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys
sys.path.insert(0, _REPO + '/research/characters')
from common import parse_x1_text, load_xmlb, X1L, X2
a = {v.get('name'): {k.lower(): x for k, x in v.attrib.items() if k.lower() != 'name'} for v in parse_x1_text(X1L + '/data/values.xml').iter() if v.get('name')}
b = {v.get('name'): {k: x for k, x in v.attrib.items() if k != 'name'} for v in load_xmlb(X2 + '/Data/values.XMLB').iter() if v.get('name')}
print('XML1', len(a), 'XML2', len(b))
miss = sorted(n for n in a if n not in b)
diff = sorted(n for n in a if n in b and a[n] != b[n])
print('missing in XML2', len(miss), miss)
print('different', len(diff), [(n, a[n], b[n]) for n in diff][:30])
