"""Scan every XML1 data file (.eng/.xml/.chr/.nav/.boy... English + language-neutral) for inline script
code in attributes, parse it with the BehavEd line parser, and report functions that do not exist
(or have a different signature) in XML2.

An attribute value is treated as inline code when it contains '(' ; otherwise, if the attribute is a
known script attribute, it is a script-file reference (checked for existence).
Lines inside inline code are separated by the literal 4-char sequence \\n\\r (XMen2.exe splits inline
code on that string, 0x68d348) or by real newlines.
Output: inline_scan.txt, inline_scan.json
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, json, collections, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bescript import parse_line

API2 = json.load(open(os.path.join(HERE, 'xml2_api.json')))
API1 = json.load(open(os.path.join(HERE, 'xml1_api.json')))
ROOTS = [_REPO + '/xml1_loose', _REPO + '/xml1_assets']
SCRIPT_ATTR = re.compile(r'(script|scriptfile|scriptok|scriptcancel)$', re.I)
ATTR = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"([^"]*)"')
LANG_SKIP = ('.fre', '.ger', '.ita', '.spa')

script_files = set()
for r in ROOTS:
    for dp, dn, fn in os.walk(r + '/scripts'):
        for f in fn:
            if f.lower().endswith('.py'):
                script_files.add(os.path.join(dp, f).replace('\\', '/').split('/scripts/', 1)[1][:-3].lower())

calls = collections.Counter()
fails = collections.Counter()
attrs = collections.Counter()
refs_missing = collections.Counter()
examples = collections.defaultdict(list)
seen_files = set()
n_inline = n_refs = 0
for r in ROOTS:
    for dp, dn, fn in os.walk(r):
        if '/scripts' in dp.replace('\\', '/') or 'packages' in dp.replace('\\', '/'):
            continue
        for f in fn:
            fl = f.lower()
            if fl.endswith(LANG_SKIP) or not fl.endswith(('.eng', '.xml', '.chr', '.nav', '.boy', '.menu')):
                continue
            p = os.path.join(dp, f).replace('\\', '/')
            rel = p.split('xml1-port/', 1)[1]
            key = rel.split('/', 1)[1].lower()
            if key in seen_files:
                continue
            seen_files.add(key)
            t = open(p, encoding='latin-1').read()
            for m in ATTR.finditer(t):
                an, av = m.group(1), m.group(2)
                if '(' in av and re.search(r'[A-Za-z_]\w*\s*\(', av):
                    attrs[an.lower()] += 1
                    n_inline += 1
                    for piece in re.split(r'\\n\\r|\\r\\n|\\n|\n|\r', av):
                        if not piece.strip():
                            continue
                        ln = parse_line(0, piece.replace('&apos;', "'").replace('&quot;', '"'))
                        cl = []
                        if ln.kind == 'call':
                            cl = [ln.call]
                        elif ln.kind == 'assign' and ln.value.kind == 'call':
                            cl = [ln.value.value]
                        for c in cl:
                            calls[c.name] += 1
                            e2 = API2.get(c.name)
                            if e2 is None:
                                why = 'unknown in XML2'
                            elif len(e2['args']) != len(c.args):
                                why = f'argc {len(c.args)} != XML2 {len(e2["args"])}'
                            else:
                                why = None
                            if why:
                                fails[f'{c.name}: {why}'] += 1
                                if len(examples[c.name]) < 3:
                                    examples[c.name].append(f'{rel} {an}="{av[:90]}"')
                elif SCRIPT_ATTR.search(an) and av.strip() and not av.strip().startswith('%'):
                    n_refs += 1
                    attrs[an.lower() + ' (file ref)'] += 1
                    if av.strip().lower() not in script_files:
                        refs_missing[av.strip()] += 1

out = [f'data files scanned (English/neutral, dedup loose+assets): {len(seen_files)}',
       f'inline code attributes: {n_inline}; script-file reference attributes: {n_refs}',
       'attributes carrying script: ' + ', '.join(f'{k}={v}' for k, v in attrs.most_common()),
       '', '== functions called from inline data code (count)']
for k, v in calls.most_common():
    out.append(f'  {v:5} {k}{"" if k in API2 else "   <-- not in XML2"}')
out.append('')
out.append('== inline calls that would be dropped by XMen2.exe')
for k, v in fails.most_common():
    out.append(f'  {v:5} {k}')
    for e in examples[k.split(':')[0]]:
        out.append(f'          e.g. {e}')
out.append('')
out.append(f'== script-file references that do not resolve to any XML1 script file ({len(refs_missing)})')
for k, v in refs_missing.most_common(40):
    out.append(f'  {v:4} {k}')
open(os.path.join(HERE, 'inline_scan.txt'), 'w').write('\n'.join(out) + '\n')
json.dump({'calls': calls, 'fails': fails, 'attrs': attrs, 'refs_missing': refs_missing},
          open(os.path.join(HERE, 'inline_scan.json'), 'w'), indent=1)
print('\n'.join(out))
