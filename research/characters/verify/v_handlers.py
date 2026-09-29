"""independent: ch_* handler strings in XMen2.exe (+ all XML2 DLLs) vs XML1 default.xbe; and every handler used by
XML2's own powerstyles/fightstyles must be in the exe set (method sanity check)."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import glob, os, re, sys, collections
sys.path.insert(0, _REPO + '/research/characters')
from common import load_xmlb, X2, X1L, parse_x1_text


def strs(p, pat=rb'ch_[a-z0-9_]+'):
    d = open(p, 'rb').read()
    s = {m.group().decode().lower() for m in re.finditer(rb'(?<![A-Za-z0-9_])' + pat + rb'(?=\x00)', d, re.I)}
    # utf-16
    s |= {m.group().decode('utf-16le').lower() for m in re.finditer(rb'c\x00h\x00_\x00(?:[a-z0-9_]\x00)+', d, re.I)}
    return s


x2 = strs(f'{X2}/XMen2.exe')
dll = set()
for p in glob.glob(f'{X2}/*.dll') + glob.glob(f'{X2}/plugins/**/*.dll', recursive=True):
    dll |= strs(p)
x1 = strs(_REPO + '/xml1_xbox/default.xbe')
print('XMen2.exe ch_*', len(x2), ' DLLs ch_*', len(dll), ' default.xbe ch_*', len(x1))
only1 = sorted(x1 - x2 - dll)
print('XML1-only', len(only1), only1)
# XML2 data usage
used2 = collections.Counter()
for p in glob.glob(f'{X2}/Data/powerstyles/*.XMLB') + glob.glob(f'{X2}/Data/fightstyles/*.XMLB'):
    for el in load_xmlb(p).iter():
        h = el.get('handler')
        if h:
            used2[h.lower()] += 1
print('XML2 data handlers', len(used2), 'not in exe strings:', sorted(set(used2) - x2))
used1 = collections.Counter()
for p in glob.glob(f'{X1L}/data/powerstyles/*') + glob.glob(f'{X1L}/data/fightstyles/*'):
    if not p.endswith(('.eng', '.xml')):
        continue
    for el in parse_x1_text(p).iter():
        h = el.get('handler')
        if h:
            used1[h.lower()] += 1
print('XML1 data handlers', len(used1), 'not in XMen2.exe:', {h: used1[h] for h in sorted(set(used1) - x2)})
print('XML1 data handlers not in default.xbe:', sorted(set(used1) - x1))
