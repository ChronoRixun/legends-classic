"""Which registered script functions are no-op stubs (handler = 'xor eax,eax; ret' / 'ret')?
Cross-referenced with XML1 script usage. Updates script_functions.json with a 'stub' flag."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import json, struct, capstone, collections
from script_table import Image, X1, X2

SF_PATH = _REPO + r'/research/sweep/script_functions.json'
SF = json.load(open(SF_PATH))
CALLS = json.load(open(_REPO + r'/research/sweep/script_calls.json'))['xml1_calls']
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)


def is_stub(im, va):
    o = im.off(va)
    ins = list(md.disasm(im.b[o:o + 16], va, count=3))
    txt = ['%s %s' % (i.mnemonic, i.op_str) for i in ins]
    if txt and txt[0].startswith('ret'):
        return True, txt
    if len(txt) > 1 and txt[0] == 'xor eax, eax' and txt[1].startswith('ret'):
        return True, txt
    return False, txt


for game, path in (('xml2', X2), ('xml1', X1)):
    im = Image(path)
    for name, rec in SF[game].items():
        s, txt = is_stub(im, int(rec['handler'], 16))
        rec['stub'] = s
json.dump(SF, open(SF_PATH, 'w'), indent=1, sort_keys=True)
l1 = {k.lower(): k for k in SF['xml1']}
print('XML2 stub functions:', sorted(k for k, v in SF['xml2'].items() if v['stub']))
print('XML1 stub functions:', sorted(k for k, v in SF['xml1'].items() if v['stub']))
used = collections.Counter({k: n for k, n in CALLS.items()})
bad = []
for k, v in SF['xml2'].items():
    if v['stub'] and k.lower() in l1 and not SF['xml1'][l1[k.lower()]]['stub']:
        n = sum(c for name, c in used.items() if name.lower() == k.lower())
        bad.append((k, n))
print('real in XML1 but stubbed in XML2 (name, XML1 calls):', sorted(bad, key=lambda x: -x[1]))
