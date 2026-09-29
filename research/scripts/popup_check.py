"""Verify that every XML1 inline popup sequence (createPopupDialog ... showPopupDialog) is straight-line
code inside one block, so it can be replaced by one generated XML2 dialog file."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bescript import parse_file

POP = {'createPopupDialog', 'addPopupDialogOption', 'canCancelDialog', 'showPopupDialog'}
stats = collections.Counter()
bad = []
for root in (_REPO + '/xml1_loose/scripts', _REPO + '/xml1_assets/scripts'):
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if not f.lower().endswith('.py'):
                continue
            p = os.path.join(dp, f)
            sc = parse_file(p)
            state = None
            for ln in sc.lines:
                if ln.kind in ('blank', 'comment'):
                    continue
                name = ln.call.name if ln.kind == 'call' else None
                if name == 'createPopupDialog':
                    if state:
                        bad.append((p, ln.no, 'create while open'))
                    state = {'indent': ln.indent, 'opts': 0}
                    stats['create'] += 1
                elif name in POP:
                    if not state:
                        bad.append((p, ln.no, f'{name} without create'))
                        continue
                    if ln.indent != state['indent']:
                        bad.append((p, ln.no, f'{name} at different indent'))
                    if name == 'addPopupDialogOption':
                        state['opts'] += 1
                    if name == 'showPopupDialog':
                        stats[f'opts={state["opts"]}'] += 1
                        state = None
                elif state:
                    bad.append((p, ln.no, f'other statement inside popup sequence: {ln.text[:50]}'))
            if state:
                bad.append((p, 0, 'unterminated popup'))
print(dict(stats))
print(len(bad), 'irregular sequences')
for b in bad[:40]:
    print(' ', b)
