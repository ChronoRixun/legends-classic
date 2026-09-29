"""Analyse every XML1 variable-store access (mission var / mission flag / game var) across all scripts
AND inline scripts in map/data files, to decide the XML2 scope each variable needs.

Output: var_scope.txt, var_scope.json {name: {kind, sets:[file], gets:[file], dirs, cross_dir, maxlen...}}
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, json, collections, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bescript import parse_file

ROOTS = [('loose', _REPO + '/xml1_loose/scripts'), ('assets', _REPO + '/xml1_assets/scripts')]
FUNCS = {'setMissionVar': ('mvar', 'set'), 'getMissionVar': ('mvar', 'get'),
         'setMissionFlag': ('mflag', 'set'), 'getMissionFlag': ('mflag', 'get'),
         'setGameVar': ('gvar', 'set'), 'getGameVar': ('gvar', 'get'),
         'disallowResponseOnVar': ('any', 'get'), 'allowResponseOnVar': ('any', 'get')}

acc = collections.defaultdict(lambda: {'kinds': set(), 'set': [], 'get': [], 'values': collections.Counter(),
                                        'bits': collections.Counter()})
seen = set()
for tag, root in ROOTS:
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if not f.lower().endswith('.py'):
                continue
            p = os.path.join(dp, f).replace('\\', '/')
            rel = p[len(root) + 1:].lower()
            if rel in seen:
                continue
            seen.add(rel)
            sc = parse_file(p)
            for ln, call, ctx in sc.calls():
                if call.name not in FUNCS or not call.args:
                    continue
                kind, op = FUNCS[call.name]
                a0 = call.args[0]
                name = a0.value if a0.kind == 'str' else f'<{a0.kind}:{a0.text}>'
                e = acc[name]
                e['kinds'].add(kind)
                e[op].append(f'{rel}:{ln.no}')
                if kind in ('mflag',) and len(call.args) > 1:
                    e['bits'][call.args[1].text] += 1
                if op == 'set':
                    v = call.args[-1]
                    e['values'][v.text if v.kind != 'ident' else '<var>'] += 1

# inline script strings in XML1 data (.eng/.xml/.chr ... files) that touch the same stores
DATA_ROOTS = [_REPO + '/xml1_loose', _REPO + '/xml1_assets']
inline = collections.Counter()
call_re = re.compile(r"\b(setMissionVar|getMissionVar|setMissionFlag|getMissionFlag|setGameVar|getGameVar)\s*\(\s*'([^']*)'")
for droot in DATA_ROOTS:
    for dp, dn, fn in os.walk(droot):
        if '/scripts' in dp.replace('\\', '/'):
            continue
        for f in fn:
            if f.lower().endswith(('.fre', '.ger', '.py', '.pyc', '.igb', '.json')):
                continue
            p = os.path.join(dp, f)
            try:
                t = open(p, encoding='latin-1').read()
            except Exception:
                continue
            for m in call_re.finditer(t):
                fnm, name = m.group(1), m.group(2)
                kind, op = FUNCS[fnm]
                rel = p.replace('\\', '/').split('xml1-port/')[1]
                acc[name]['kinds'].add(kind)
                acc[name][op].append(rel + ' (inline)')
                inline[fnm] += 1


def dirs(lst):
    return sorted({'/'.join(x.split(':')[0].split(' ')[0].split('/')[:2]) for x in lst})


out = []
res = {}
for name in sorted(acc, key=str.lower):
    e = acc[name]
    sd, gd = dirs(e['set']), dirs(e['get'])
    alld = sorted(set(sd) | set(gd))
    cross = len(alld) > 1
    res[name] = {'kinds': sorted(e['kinds']), 'sets': e['set'], 'gets': e['get'], 'set_dirs': sd, 'get_dirs': gd,
                 'cross_dir': cross, 'len': len(name), 'values': dict(e['values']), 'bits': dict(e['bits'])}
json.dump(res, open(os.path.join(HERE, 'var_scope.json'), 'w'), indent=1)

kinds = collections.Counter()
for n, r in res.items():
    kinds[(tuple(r['kinds']), r['cross_dir'])] += 1
out.append(f'{len(res)} distinct variable names touched by XML1 scripts + inline data scripts')
out.append(f'inline (map/data) accesses: {dict(inline)}')
out.append('by (kinds, used in >1 script directory): ' + str(dict(kinds)))
long = [n for n in res if len(n) >= 12]
out.append(f'names >= 12 chars (setter silently ignores them in BOTH engines: len check at XML1 0xcb7a1 / XML2 0x4d7081): {long}')
mixed = [n for n, r in res.items() if len(r['kinds']) > 1]
out.append(f'names used with more than one store kind: {mixed}')
never_set = [n for n, r in res.items() if not r['sets']]
never_get = [n for n, r in res.items() if not r['gets']]
out.append(f'never set (always 0): {never_set}')
out.append(f'set but never read: {never_get}')
out.append('')
out.append(f'{"name":16} {"kinds":14} cross  set-dirs -> get-dirs   values / bits')
for n in sorted(res, key=lambda k: (res[k]['kinds'], k.lower())):
    r = res[n]
    out.append(f'{n:16} {",".join(r["kinds"]):14} {"X" if r["cross_dir"] else " "}  {",".join(r["set_dirs"])} -> {",".join(r["get_dirs"])}   {r["values"] or ""} {r["bits"] or ""}')
open(os.path.join(HERE, 'var_scope.txt'), 'w').write('\n'.join(out) + '\n')
print('\n'.join(out[:12]))
