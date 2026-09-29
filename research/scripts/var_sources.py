"""For every XML1 store write that takes a script variable, find which function produced that variable
(last assignment above it in the same script).  Used to size packed storage."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, json, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bescript import parse_file

SET = {'setMissionVar', 'setGameVar'}
src = collections.defaultdict(collections.Counter)
for root in (_REPO + '/xml1_loose/scripts', _REPO + '/xml1_assets/scripts'):
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if not f.lower().endswith('.py'):
                continue
            sc = parse_file(os.path.join(dp, f))
            last = {}
            for ln in sc.lines:
                if ln.kind == 'assign':
                    v = ln.value
                    last[ln.target] = v.value.name if v.kind == 'call' else v.kind
                if ln.kind == 'call' and ln.call.name in SET and len(ln.call.args) == 2:
                    n, val = ln.call.args
                    if n.kind == 'str' and val.kind == 'ident':
                        src[n.value][last.get(val.text, '?')] += 1
json.dump({k: dict(v) for k, v in src.items()}, open(os.path.join(HERE, 'var_sources.json'), 'w'), indent=1)
for k in sorted(src, key=str.lower):
    print(f'{k:14} {dict(src[k])}')
