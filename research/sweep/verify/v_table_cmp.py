import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import json
sf = json.load(open(_REPO + r'/research/sweep/script_functions.json'))
vt = json.load(open(_REPO + r'/research/sweep/verify/v_table.json'))
for g in ('xml1', 'xml2'):
    mine = {r['name']: r for r in vt[g]}
    theirs = sf[g]
    print(g, 'theirs', len(theirs), 'mine', len(mine))
    extra = sorted(set(theirs) - set(mine))
    print('  in theirs not mine:', len(extra))
    for e in extra:
        print('    ', e, theirs[e])
    print('  in mine not theirs:', sorted(set(mine) - set(theirs)))
    diff = [(k, mine[k]['handler'], theirs[k]['handler'], mine[k]['args'], theirs[k]['args'])
            for k in mine if k in theirs and (mine[k]['handler'] != theirs[k]['handler'] or mine[k]['args'] != theirs[k]['args'] or mine[k]['ret'] != theirs[k]['ret'])]
    print('  field diffs:', diff)
