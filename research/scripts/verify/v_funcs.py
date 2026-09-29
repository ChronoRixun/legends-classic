"""Independent: set of function names called by XML1 scripts vs XML2/XML1 registration tables."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, json, sys, collections
V = _REPO + '/research/scripts/verify'
tabs = json.load(open(V + '/tables.json'))
x2 = {e[2].lower(): e for t in tabs['xml2'].values() for e in t}
x1 = {e[2].lower(): e for t in tabs['xml1'].values() for e in t}

KW = {'if', 'elif', 'elseif', 'else', 'endif', 'def', 'and', 'or', 'not', 'print', 'return', 'while', 'for', 'in'}
CALL = re.compile(r'([A-Za-z_][A-Za-z0-9_.]*)\s*\(')


def strip(line):
    # remove comment and string contents
    out = []
    q = None
    for ch in line:
        if q:
            if ch == q:
                q = None
                out.append(ch)
            continue
        if ch in '"\'':
            q = ch
            out.append(ch)
            continue
        if ch == '#':
            break
        out.append(ch)
    return ''.join(out)


def scan(root, files=None):
    uses = collections.Counter()
    fcount = collections.Counter()
    nfiles = 0
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if not f.lower().endswith('.py'):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root).replace('\\', '/').lower()
            if files is not None and rel not in files:
                continue
            nfiles += 1
            seen = set()
            for line in open(p, 'rb').read().decode('latin1').replace('\r\n', '\n').split('\n'):
                s = strip(line)
                for m in CALL.finditer(s):
                    n = m.group(1)
                    if n.lower().startswith('game.'):
                        n = n[5:]
                    if n.lower() in KW:
                        continue
                    uses[n.lower()] += 1
                    seen.add(n.lower())
            for n in seen:
                fcount[n] += 1
    return uses, fcount, nfiles


if __name__ == '__main__':
    loose_root = _REPO + '/xml1_loose/scripts'
    uses, fcount, n = scan(loose_root)
    print('loose files', n, 'distinct call names', len(uses))
    notx2 = sorted((k for k in uses if k not in x2), key=lambda k: -uses[k])
    inx2 = [k for k in uses if k in x2]
    notx1 = [k for k in uses if k not in x1]
    print('registered in XML2:', len(inx2), ' not registered in XML2:', len(notx2), ' not registered in XML1:', len(notx1))
    for k in notx2:
        print('   %-28s %5d calls  x1reg=%s' % (k, uses[k], k in x1))
    print('not in XML1 table:', notx1)
    # XML2 script-files-based count (what the "143/152" might have been)
    x2uses, _, n2 = scan(_XML2 + '/Scripts')
    print('xml2 script files', n2, 'distinct names used', len(x2uses))
    inx2files = [k for k in uses if k in x2uses]
    print('XML1 names that appear in XML2 script files:', len(inx2files), 'of', len(uses))
    print('XML2 script-file names not registered in XML2 exe:', sorted(k for k in x2uses if k not in x2))
    # names registered XML1 not XML2
    print('XML1-registered not XML2-registered:', len([k for k in x1 if k not in x2]), sorted(k for k in x1 if k not in x2))
    json.dump({'loose': uses}, open(V + '/funcs_used.json', 'w'))
