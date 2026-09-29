"""Exhaustive syntax/API analysis of every XML1 and XML2 BehavEd script.

Writes:
  script_analysis.txt   human-readable report
  script_analysis.json  machine-readable (per-corpus usage, per-function arg shapes)
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, json, collections, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bescript import parse_file

XML1_LOOSE = _REPO + '/xml1_loose/scripts'
XML1_ASSETS = _REPO + '/xml1_assets/scripts'
XML2 = _XML2 + '/Scripts'

API1 = json.load(open(os.path.join(HERE, 'xml1_api.json')))
API2 = json.load(open(os.path.join(HERE, 'xml2_api.json')))
API2_LC = {k.lower(): k for k in API2}
API1_LC = {k.lower(): k for k in API1}


def files(root, exclude_rel=()):
    out = []
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if f.lower().endswith('.py'):
                p = os.path.join(dp, f).replace('\\', '/')
                rel = p[len(root) + 1:]
                if rel.lower() in exclude_rel:
                    continue
                out.append((rel, p))
    return sorted(out)


loose = files(XML1_LOOSE)
loose_rel = {r.lower() for r, _ in loose}
assets = files(XML1_ASSETS, exclude_rel=loose_rel)
xml2 = files(XML2)
# XML2 dev/test folders (work/ and legacy 'import game' python) are not shipped content
CORPORA = {'xml1_loose': loose, 'xml1_assets_only': assets, 'xml2': xml2}


def argkind(a):
    return {'str': 's', 'num': 'n', 'ident': 'v', 'call': 'c', 'expr': 'x', 'empty': '_'}[a.kind]


def check_sig(api, call):
    """mirror XMen2.exe 0x4d8970: exact arg count; 'i'/'f' need number, 's' needs string, others any.
    returns None if OK else reason"""
    e = api.get(call.name)
    if e is None:
        return 'unknown'
    sig = e['args']
    if len(call.args) != len(sig):
        return f'argc {len(call.args)}!={len(sig)}'
    for a, c in zip(call.args, sig):
        if c in 'if' and a.kind == 'str':
            return f'type str-for-{c}'
        if c == 's' and a.kind == 'num':
            return 'type num-for-s'
    return None


stats = {}
for cname, flist in CORPORA.items():
    S = collections.defaultdict(collections.Counter)
    shapes = collections.defaultdict(collections.Counter)
    sites = collections.defaultdict(list)
    idents_as_args = collections.Counter()
    magic = collections.Counter()
    for rel, p in flist:
        sc = parse_file(p)
        S['eol'][sc.eol] += 1
        S['final_newline'][sc.final_newline] += 1
        S['bom'][sc.bom] += 1
        S['nonascii'][sc.nonascii] += 1
        S['tab_indent'][sc.tabs] += 1
        first = next((l for l in sc.lines if l.kind != 'blank'), None)
        S['header'][first.text[:22] if first and first.kind == 'comment' and 'BehavEd' in first.text else ('(none)' if first is None or first.kind != 'comment' else 'other comment')] += 1
        depth = 0
        maxdepth = 0
        balance_bad = False
        for ln in sc.lines:
            S['linekind'][ln.kind] += 1
            if ln.kind in ('comment',):
                t = ln.text
                S['comment_form']['# ( "..." )' if re.match(r'#\s*\(\s*".*"\s*\)\s*$', t) else '# free text'] += 1
            if ln.trailing_comment:
                S['trailing_comment'][True] += 1
            if ln.kind not in ('blank', 'comment'):
                ind = ln.indent
                S['indent_chars'][('tab' if '\t' in ind else '') + ('space' if ' ' in ind else '') or 'none'] += 1
                if ' ' in ind and '\t' not in ind:
                    S['indent_width'][len(ind)] += 1
                if ln.raw != ln.raw.rstrip(' \t'):
                    S['trailing_ws'][True] += 1
            if ln.kind in ('if', 'elif', 'else', 'endif'):
                kw = getattr(ln, 'kw', ln.kind)
                S['keyword'][kw + (':' if getattr(ln, 'colon', False) else '')] += 1
                if ln.kind == 'if':
                    depth += 1
                    maxdepth = max(maxdepth, depth)
                elif ln.kind == 'endif':
                    depth -= 1
                    if depth < 0:
                        balance_bad = True
                if ln.cond:
                    if ln.cond[0] == 'raw':
                        S['cond_shape']['raw:' + ln.cond[1][:40]] += 1
                    else:
                        l, op, r = ln.cond
                        S['cond_op'][op] += 1
                        S['cond_shape'][f'{argkind(l)} {op} {argkind(r)}'] += 1
                        if r.kind == 'str':
                            S['cond_str_rhs'][r.text] += 1
            elif ln.kind in ('def', 'import', 'while', 'endwhile', 'for', 'return', 'pass', 'from', 'print'):
                S['keyword'][ln.kind] += 1
            elif ln.kind == 'assign':
                S['assign_rhs'][argkind(ln.value)] += 1
                if ln.value.kind == 'expr':
                    S['assign_expr'][ln.value.text[:50]] += 1
            elif ln.kind == 'other':
                S['other_lines'][ln.text[:70]] += 1
            if ln.kind == 'call' and ln.call.trailing:
                S['call_trailing'][ln.call.trailing[:40]] += 1
            if ln.kind == 'call':
                S['space_before_paren'][repr(ln.call.space_before_paren)] += 1
        if depth != 0 or balance_bad:
            S['if_unbalanced_files'][rel] += 1
        S['max_if_depth'][maxdepth] += 1
        for ln, call, ctx in sc.calls():
            S['call_ctx'][ctx] += 1
            if call.prefix:
                S['prefix'][call.prefix] += 1
            S['func'][call.name] += 1
            shape = ''.join(argkind(a) for a in call.args)
            shapes[call.name][shape] += 1
            sites[call.name].append(f'{rel}:{ln.no}')
            for a in call.args:
                if a.kind == 'ident':
                    idents_as_args[a.text] += 1
                if a.kind == 'str':
                    if '\\' in a.value:
                        S['str_backslash'][a.value[:60]] += 1
                    if a.quote == "'":
                        S['single_quoted'][call.name] += 1
                    if re.fullmatch(r'_[A-Z0-9_]+_', a.value or ''):
                        magic[a.value] += 1
                    if a.value != a.value.strip():
                        S['str_padded'][call.name] += 1
                    if '"' in a.value or "'" in a.value:
                        S['str_embedded_quote'][call.name] += 1
                if a.kind in ('expr', 'empty'):
                    S['arg_expr'][a.text[:50]] += 1
            own = API1 if cname.startswith('xml1') else API2
            r = check_sig(own, call)
            if r:
                S['own_api_fail'][f'{call.name}: {r}'] += 1
            if cname.startswith('xml1'):
                r2 = check_sig(API2, call)
                if r2:
                    S['xml2_api_fail'][f'{call.name}: {r2}'] += 1
    S['magic'] = magic
    S['idents_as_args'] = idents_as_args
    stats[cname] = {'S': S, 'shapes': shapes, 'sites': sites, 'nfiles': len(flist)}

# ---- report
out = []
w = out.append
w('BehavEd script analysis (all files parsed; XML2 = every .py/.PY under <XML2 folder>/Scripts)')
for c, d in stats.items():
    w(f'  {c}: {d["nfiles"]} files, {sum(d["S"]["func"].values())} calls, {len(d["S"]["func"])} distinct functions')
w('')
keys = ['eol', 'final_newline', 'bom', 'nonascii', 'tab_indent', 'header', 'linekind', 'comment_form', 'trailing_comment',
        'indent_chars', 'indent_width', 'trailing_ws', 'keyword', 'cond_op', 'cond_shape', 'cond_str_rhs', 'assign_rhs',
        'assign_expr', 'call_ctx', 'prefix', 'space_before_paren', 'call_trailing', 'str_backslash', 'single_quoted',
        'str_padded', 'str_embedded_quote', 'arg_expr', 'other_lines', 'if_unbalanced_files', 'max_if_depth', 'magic']
for k in keys:
    w(f'== {k}')
    allv = set()
    for c in stats:
        allv |= set(stats[c]['S'][k])
    rows = sorted(allv, key=lambda v: -sum(stats[c]['S'][k][v] for c in stats))
    for v in rows[:40]:
        cnts = '  '.join(f'{stats[c]["S"][k][v]:6}' for c in stats)
        flag = ''
        x1 = stats['xml1_loose']['S'][k][v] + stats['xml1_assets_only']['S'][k][v]
        if x1 and not stats['xml2']['S'][k][v]:
            flag = '   <-- XML1 only'
        w(f'  {cnts}   {str(v)[:70]}{flag}')
    if len(rows) > 40:
        w(f'  ... {len(rows) - 40} more')
    w('')

w('== identifiers used as call arguments (variables / bare words)  [xml1_loose xml1_assets xml2]')
allv = set()
for c in stats:
    allv |= set(stats[c]['S']['idents_as_args'])
for v in sorted(allv, key=lambda v: -sum(stats[c]['S']['idents_as_args'][v] for c in stats))[:80]:
    w(f'  ' + '  '.join(f'{stats[c]["S"]["idents_as_args"][v]:5}' for c in stats) + f'   {v}')
w('')

w('== XML1 calls that fail XML1\'s OWN registered signature (engine would drop the line on Xbox too)')
for c in ('xml1_loose', 'xml1_assets_only'):
    for v, n in stats[c]['S']['own_api_fail'].most_common():
        w(f'  {c:16} {n:5}  {v}')
w('')
w('== XML2 calls that fail XML2\'s own signature (shows what the engine tolerates / dead scripts)')
for v, n in stats['xml2']['S']['own_api_fail'].most_common(60):
    w(f'  {n:5}  {v}')
w('')
w('== XML1 calls that would FAIL on XML2 (unknown function / wrong argc / wrong literal type) -> line dropped')
agg = collections.Counter()
for c in ('xml1_loose', 'xml1_assets_only'):
    agg.update(stats[c]['S']['xml2_api_fail'])
for v, n in agg.most_common():
    w(f'  {n:5}  {v}')
w('')

w('== Per-function arg shapes (s=string n=number v=variable/bareword c=call x=expr) XML1 vs XML2, only where they differ')
f1 = collections.Counter()
f1.update(stats['xml1_loose']['S']['func']); f1.update(stats['xml1_assets_only']['S']['func'])
for fn in sorted(f1, key=str.lower):
    s1 = collections.Counter(); s1.update(stats['xml1_loose']['shapes'][fn]); s1.update(stats['xml1_assets_only']['shapes'][fn])
    s2 = stats['xml2']['shapes'].get(fn, collections.Counter())
    lens1 = {len(k) for k in s1}
    lens2 = {len(k) for k in s2}
    if s2 and lens1 != lens2 or (set(s1) - set(s2) and s2):
        w(f'  {fn:28} API1 {API1.get(fn, {}).get("args", "?"):7} API2 {API2.get(fn, {}).get("args", "-"):7} '
          f'XML1 {dict(s1.most_common(6))}  XML2 {dict(s2.most_common(6))}')
w('')
w('== Function usage table: name, XML1 calls, XML2 calls, in XML1 API, in XML2 API')
f2 = stats['xml2']['S']['func']
for fn in sorted(set(f1) | set(f2), key=str.lower):
    w(f'  {fn:32} {f1[fn]:6} {f2[fn]:6}   api1={"Y" if fn in API1 else ("ci:" + API1_LC[fn.lower()] if fn.lower() in API1_LC else "-")}'
      f' api2={"Y" if fn in API2 else ("ci:" + API2_LC[fn.lower()] if fn.lower() in API2_LC else "-")}')
open(os.path.join(HERE, 'script_analysis.txt'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')

js = {}
for c, d in stats.items():
    js[c] = {'nfiles': d['nfiles'],
             'S': {k: {str(kk): vv for kk, vv in v.items()} for k, v in d['S'].items()},
             'shapes': {k: dict(v) for k, v in d['shapes'].items()},
             'sites': dict(d['sites'])}
json.dump(js, open(os.path.join(HERE, 'script_analysis.json'), 'w'), indent=0)
print('\n'.join(out[:60]))
