"""Collect every function-call identifier in XML1 and XML2 scripts (files + inline actscript etc.
attributes are handled in sweep.py) and check them against the extracted registration tables."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import json, os, re, collections

SF = json.load(open(_REPO + r'/research/sweep/script_functions.json'))
CALL = re.compile(r'(?<![\w.])([A-Za-z_][A-Za-z0-9_]*)\s*\(')
KEYWORDS = {'if', 'elif', 'while', 'for', 'and', 'or', 'not', 'return', 'print', 'def', 'in', 'int', 'str',
            'float', 'len', 'range'}


def strip_comments(text):
    out = []
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith('#') or s.startswith(';'):
            continue
        out.append(line)
    return '\n'.join(out)


def calls_in(text):
    # XML1/XML2 scripts are Python-like; some call engine functions through the 'game' module
    text = re.sub(r'(?<![\w.])game\.', '', strip_comments(text))
    return [m.group(1) for m in CALL.finditer(text) if m.group(1) not in KEYWORDS]


def scan(root):
    c = collections.Counter()
    files = collections.defaultdict(set)
    for d, _, fs in os.walk(root):
        for f in fs:
            if f.lower().endswith('.py'):
                p = os.path.join(d, f)
                for name in calls_in(open(p, encoding='latin-1').read()):
                    c[name] += 1
                    files[name].add(os.path.relpath(p, root).replace(os.sep, '/'))
    return c, files


if __name__ == '__main__':
    t1 = {k.lower() for k in SF['xml1']}
    t2 = {k.lower() for k in SF['xml2']}
    c1, f1 = collections.Counter(), collections.defaultdict(set)
    for r in (_REPO + r'/xml1_loose/scripts', _REPO + r'/xml1_assets/scripts'):
        c, f = scan(r)
        c1.update(c)
        for k, v in f.items():
            f1[k] |= v
    c2, f2 = scan(_XML2 + r'/Scripts')
    print('XML1 scripts: %d distinct call names' % len(c1))
    print('  not in XML1 table:', sorted((k, n) for k, n in c1.items() if k.lower() not in t1))
    print('XML2 scripts: %d distinct call names' % len(c2))
    print('  not in XML2 table:', sorted((k, n) for k, n in c2.items() if k.lower() not in t2))
    miss = sorted(((k, n) for k, n in c1.items() if k.lower() not in t2), key=lambda x: -x[1])
    print('XML1 calls not registered in XML2 exe (%d names, %d calls):' % (len(miss), sum(n for _, n in miss)))
    for k, n in miss:
        print('   %-28s %5d  in XML1 table: %s  files: %d' % (k, n, k.lower() in t1, len(f1[k])))
    json.dump({'xml1_calls': dict(c1), 'xml2_calls': dict(c2),
               'xml1_missing_in_xml2': {k: {'calls': n, 'files': sorted(f1[k])} for k, n in miss}},
              open(_REPO + r'/research/sweep/script_calls.json', 'w'), indent=1)
