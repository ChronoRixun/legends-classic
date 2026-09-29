"""Independent validator of research/scripts/out/scripts against XMen2.exe's registration table.
Checks per statement: function registered (case-insensitive), argc == len(argsig), literal types,
variable types (ret sig of assigning function), use-before-assign, if/endif balance, CRLF,
unknown bare identifiers, XML1-only functions remaining. Also compares block keyword counts to the source."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, json, sys, collections
V = _REPO + '/research/scripts/verify'
OUT = sys.argv[1] if len(sys.argv) > 1 else _REPO + '/research/scripts/out/scripts'
tabs = json.load(open(V + '/tables.json'))
X2 = {e[2].lower(): (e[3], e[4]) for t in tabs['xml2'].values() for e in t}
X1 = {e[2].lower(): (e[3], e[4]) for t in tabs['xml1'].values() for e in t}
OPS = ['==', '!=', '<=', '>=', '<', '>']
NUM = re.compile(r'^[+-]?(\d+\.?\d*|\.\d+)$')
IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

stats = collections.Counter()
problems = []


def split_args(s):
    out, cur, q, depth = [], '', None, 0
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
            continue
        if ch in '"\'':
            q = ch
            cur += ch
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip())
            cur = ''
            continue
        cur += ch
    if cur.strip() or out:
        out.append(cur.strip())
    return out


def strip_comment(line):
    q = None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
            continue
        if ch in '"\'':
            q = ch
        elif ch == '#':
            return line[:i]
    return line


def argkind(a, vars_):
    if len(a) >= 2 and a[0] in '"\'' and a[-1] == a[0]:
        return 's'
    if NUM.match(a):
        return 'n'
    if IDENT.match(a):
        if a.lower() in ('_owner_', '_activator_'):
            return 'ent'
        if a.lower() in vars_:
            return 'v:' + vars_[a.lower()]
        return 'undef'
    if '(' in a:
        return 'call'
    return 'other'


def check_call(rel, ln, name, args, vars_):
    n = name.lower()
    if n.startswith('game.'):
        n = n[5:]
    if n not in X2:
        problems.append((rel, ln, 'unregistered', name))
        return None
    ret, sig = X2[n]
    if len(args) != len(sig):
        problems.append((rel, ln, f'argc {len(args)} != {len(sig)}', name))
        return ret
    for a, t in zip(args, sig):
        k = argkind(a, vars_)
        if k == 'call':
            problems.append((rel, ln, 'nested call arg', f'{name}: {a}'))
            continue
        if k == 'undef':
            problems.append((rel, ln, 'undefined identifier arg', f'{name}: {a}'))
            continue
        if t in 'if':
            if k == 's' or k == 'v:s':
                problems.append((rel, ln, f'type: {t} got string', f'{name}: {a}'))
        elif t == 's':
            if k == 'n' or k in ('v:i', 'v:f'):
                problems.append((rel, ln, 's got number', f'{name}: {a}'))
    return ret


CALLRE = re.compile(r'^([A-Za-z_][A-Za-z0-9_.]*)\s*\((.*)\)\s*$')


def check_file(path, rel):
    raw = open(path, 'rb').read()
    txt = raw.decode('latin-1')
    if '\n' in txt.replace('\r\n', ''):
        problems.append((rel, 0, 'bare LF', ''))
    lines = txt.split('\r\n')
    vars_ = {}
    depth = 0
    kw = collections.Counter()
    for ln, line in enumerate(lines, 1):
        s = strip_comment(line).strip()
        if not s:
            continue
        stats['statements'] += 1
        first = re.split(r'[\s(]', s, 1)[0].lower()
        if first in ('if', 'elif', 'elseif'):
            kw[first] += 1
            if first == 'if':
                depth += 1
            cond = s[len(first):].strip().rstrip(':')
            op = next((o for o in OPS if o in cond), None)
            if op is None:
                problems.append((rel, ln, 'if without comparison', s))
                continue
            l, r = [x.strip() for x in cond.split(op, 1)]
            for a in (l, r):
                k = argkind(a, vars_)
                if k in ('undef', 'call', 'other'):
                    problems.append((rel, ln, f'if operand {k}', a))
            continue
        if first in ('else', 'endif'):
            kw[first] += 1
            if first == 'endif':
                depth -= 1
                if depth < 0:
                    problems.append((rel, ln, 'endif underflow', ''))
            continue
        if first == 'def' or '__name__' in s:
            kw['def/name'] += 1
            continue
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', s)
        if m and not s.startswith('=='):
            tgt, rhs = m.group(1), m.group(2).strip()
            mc = CALLRE.match(rhs)
            if not mc:
                problems.append((rel, ln, 'assignment of non-call', s))
                vars_[tgt.lower()] = 'n'
                continue
            ret = check_call(rel, ln, mc.group(1), split_args(mc.group(2)), vars_)
            stats['calls'] += 1
            vars_[tgt.lower()] = ret or '?'
            continue
        mc = CALLRE.match(s)
        if mc:
            if mc.group(1).lower() == 'main':
                problems.append((rel, ln, 'main call left', s))
                continue
            check_call(rel, ln, mc.group(1), split_args(mc.group(2)), vars_)
            stats['calls'] += 1
            continue
        problems.append((rel, ln, 'unparsed statement', s))
    if depth != 0:
        problems.append((rel, 0, f'if/endif imbalance {depth}', ''))
    return kw


def main():
    nfiles = 0
    kws = {}
    for dp, dn, fn in os.walk(OUT):
        for f in fn:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, OUT).replace('\\', '/')
            nfiles += 1
            kws[rel.lower()] = check_file(p, rel)
    print('files', nfiles, dict(stats))
    c = collections.Counter(p[2] for p in problems)
    print('problem kinds:', c.most_common())
    by = collections.defaultdict(list)
    for p in problems:
        by[p[2]].append(p)
    for k, lst in by.items():
        print('==', k, len(lst))
        for p in lst[:12]:
            print('   ', p[0], p[1], p[3][:120])
    # compare block keyword counts with source
    src_roots = [_REPO + '/xml1_loose/scripts', _REPO + '/xml1_assets/scripts']
    mism = []
    seen = set()
    for root in src_roots:
        for dp, dn, fn in os.walk(root):
            for f in fn:
                if not f.lower().endswith('.py'):
                    continue
                p = os.path.join(dp, f)
                rel = os.path.relpath(p, root).replace('\\', '/').lower()
                if rel in seen:
                    continue
                seen.add(rel)
                if rel not in kws:
                    mism.append((rel, 'missing in output'))
                    continue
                t = open(p, 'rb').read().decode('latin-1').replace('\r\n', '\n').split('\n')
                kc = collections.Counter()
                for line in t:
                    s = strip_comment(line).strip()
                    first = re.split(r'[\s(:]', s, 1)[0].lower() if s else ''
                    if first in ('if', 'elif', 'elseif', 'else', 'endif'):
                        kc[first] += 1
                o = kws[rel]
                for k in ('if', 'elif', 'elseif', 'else', 'endif'):
                    # generated sign-extension adds if/endif pairs; allow extra if==endif pairs
                    pass
                if (o['elif'], o['elseif'], o['else']) != (kc['elif'], kc['elseif'], kc['else']) or \
                        (o['if'] - kc['if']) != (o['endif'] - kc['endif']) or o['if'] < kc['if']:
                    mism.append((rel, dict(kc), {k: o[k] for k in ('if', 'elif', 'elseif', 'else', 'endif')}))
    print('source scripts', len(seen), 'block-structure mismatches', len(mism))
    for m in mism[:30]:
        print('   ', m)
    extra = [k for k in kws if k not in seen]
    print('output files not in source (generated):', len(extra), extra[:10])


main()
