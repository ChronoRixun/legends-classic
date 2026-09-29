"""Build clean API tables from scan_functable output and diff XML1 vs XML2.

Writes xml1_api.json, xml2_api.json ({name: {ret, args, func, table}}) and api_diff.txt.
"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))


def load(fn, tables):
    raw = json.load(open(os.path.join(HERE, fn)))
    api = {}
    for e in raw:
        if e['table'] not in tables:
            continue
        api[e['name']] = {'ret': e['ret'], 'args': e['args'], 'func': e['func'], 'table': e['table']}
    return api


x2 = load('xml2_api_raw.json', {'0068a908', '006903d8'})
x1 = load('xml1_api_raw.json', {'003d0b88', '003d5620'})
json.dump(x2, open(os.path.join(HERE, 'xml2_api.json'), 'w'), indent=1, sort_keys=True)
json.dump(x1, open(os.path.join(HERE, 'xml1_api.json'), 'w'), indent=1, sort_keys=True)

low2 = {k.lower(): k for k in x2}
out = []
out.append(f'XML1 default.xbe: {len(x1)} registered script functions '
           f'(main table 0x3d0b88, builtin/operator table 0x3d5620)')
out.append(f'XML2 XMen2.exe : {len(x2)} registered script functions '
           f'(main table 0x68a908, builtin/operator table 0x6903d8)')
out.append('Entry layout both games: {void* func, char* name, char* ret_sig, char* arg_sig}; '
           'sig chars: n=none i=int f=float s=string a=any/entity? w=wait v=vector?')
out.append('')
only1 = sorted(set(x1) - set(x2), key=str.lower)
only2 = sorted(set(x2) - set(x1), key=str.lower)
out.append(f'== In XML1 but NOT in XML2 ({len(only1)}):')
for k in only1:
    e = x1[k]
    ci = low2.get(k.lower())
    note = f'   (case-insensitive match in XML2: {ci} {x2[ci]["ret"]}({x2[ci]["args"]}))' if ci else ''
    out.append(f'  {k:32} {e["ret"]}({e["args"]}){note}')
out.append('')
out.append(f'== Same name, different signature ({sum(1 for k in set(x1) & set(x2) if (x1[k]["ret"], x1[k]["args"]) != (x2[k]["ret"], x2[k]["args"]))}):')
for k in sorted(set(x1) & set(x2), key=str.lower):
    a, b = x1[k], x2[k]
    if (a['ret'], a['args']) != (b['ret'], b['args']):
        out.append(f'  {k:32} XML1 {a["ret"]}({a["args"]})  ->  XML2 {b["ret"]}({b["args"]})')
out.append('')
out.append(f'== In XML2 but NOT in XML1 ({len(only2)}):')
for k in only2:
    e = x2[k]
    out.append(f'  {k:32} {e["ret"]}({e["args"]})')
out.append('')
out.append('== Full XML2 API:')
for k in sorted(x2, key=str.lower):
    e = x2[k]
    out.append(f'  {k:32} {e["ret"]}({e["args"]})  func {e["func"]}')
out.append('')
out.append('== Full XML1 API:')
for k in sorted(x1, key=str.lower):
    e = x1[k]
    out.append(f'  {k:32} {e["ret"]}({e["args"]})  func {e["func"]}')
open(os.path.join(HERE, 'api_diff.txt'), 'w').write('\n'.join(out) + '\n')
print('\n'.join(out[:120]))
