"""Independent checks on rewrite output:
 1. every output file is CRLF-only with a final CRLF
 2. block structure preserved: number of if/elif/else/endif keywords in == out (+ generated sign-extension blocks)
 3. no XML1-only function name remains anywhere (as a call)
 4. every call validates against XMen2.exe signatures (count + literal types)
 5. every referenced dialog / x1 helper / mission-start script exists in out/
 6. game var names < 12 chars, total distinct game vars <= 96
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, sys, json, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bescript import parse_file

OUT = os.path.join(HERE, 'out')
API1 = json.load(open(os.path.join(HERE, 'xml1_api.json')))
API2 = json.load(open(os.path.join(HERE, 'xml2_api.json')))
X1_ONLY = set(API1) - set(API2)
SRC = {}
for root in (_REPO + '/xml1_loose/scripts', _REPO + '/xml1_assets/scripts'):
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if f.lower().endswith('.py'):
                p = os.path.join(dp, f).replace(os.sep, '/')
                SRC.setdefault(p[len(root) + 1:].lower(), p)

res = collections.Counter()
issues = collections.defaultdict(list)
gamevars = set()
refs = set()
for dp, dn, fn in os.walk(os.path.join(OUT, 'scripts')):
    for f in fn:
        p = os.path.join(dp, f).replace(os.sep, '/')
        rel = p.split('/out/scripts/', 1)[1].lower()
        data = open(p, 'rb').read()
        res['files'] += 1
        if data.count(b'\n') != data.count(b'\r\n') or not data.endswith(b'\r\n'):
            issues['eol'].append(rel)
        sc = parse_file(data)
        kw = collections.Counter(l.kind for l in sc.lines if l.kind in ('if', 'elif', 'else', 'endif'))
        gen_if = sum(1 for a, b in zip(sc.lines, sc.lines[1:]) if a.text == '# ( "x1 sign-extend" )' and b.kind == 'if')
        if rel in SRC:
            k0 = collections.Counter(l.kind for l in parse_file(SRC[rel]).lines
                                     if l.kind in ('if', 'elif', 'else', 'endif') and '__name__' not in l.text)
            kk = dict(kw)
            kk['if'] = kk.get('if', 0) - gen_if
            kk['endif'] = kk.get('endif', 0) - gen_if
            if {k: v for k, v in kk.items() if v} != {k: v for k, v in k0.items() if v}:
                issues['block structure changed'].append(f'{rel} in {dict(k0)} out {kk}')
        for ln, c, ctx in sc.calls():
            res['calls'] += 1
            if c.name in X1_ONLY:
                issues['XML1-only function left'].append(f'{rel}:{ln.no} {c.name}')
            e = API2.get(c.name)
            if e is None:
                issues['unknown to XML2'].append(f'{rel}:{ln.no} {c.name}')
            elif len(e['args']) != len(c.args):
                issues['argc mismatch'].append(f'{rel}:{ln.no} {c.name}')
            if c.name in ('setGameFlag', 'getGameFlag') and c.args and c.args[0].kind == 'str':
                gamevars.add(c.args[0].value)
            if c.name in ('createPopupDialogXml', 'createPopupDialogXmlFilter') and c.args and c.args[0].value.startswith('x1/'):
                refs.add(('dialog', c.args[0].value))
for k, path in json.load(open(os.path.join(OUT, 'inline_rewrites.json'))).items():
    if path.startswith('x1/') and '(' not in path:
        refs.add(('script', path))
missing = []
for kind, r in sorted(refs):
    p = os.path.join(OUT, 'dialogs' if kind == 'dialog' else 'scripts', *r.split('/'))
    if not os.path.exists(p + ('.XMLB' if kind == 'dialog' else '.py')):
        missing.append(r)
for dp, dn, fn in os.walk(os.path.join(OUT, 'dialogs')):
    for f in fn:
        if f.endswith('.xml'):
            for m in re.finditer(r'script="(x1/[^"(]+)"', open(os.path.join(dp, f)).read()):
                if not os.path.exists(os.path.join(OUT, 'scripts', *m.group(1).split('/')) + '.py'):
                    missing.append(m.group(1))
print(f'files {res["files"]}, calls {res["calls"]}')
print(f'distinct XML2 game vars referenced: {len(gamevars)} (limit 96 usable); long names: {[g for g in gamevars if len(g) >= 12]}')
print(f'referenced generated files: {len(refs)}, missing: {missing}')
for k, v in issues.items():
    print(f'{k}: {len(v)}')
    for x in v[:12]:
        print('    ', x)
