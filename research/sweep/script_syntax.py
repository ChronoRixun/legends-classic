"""Script-syntax features in XML1 vs XML2 scripts that the XML2 script loader might treat differently."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import collections, os, re, json

ROOTS1 = [_REPO + r'/xml1_loose/scripts', _REPO + r'/xml1_assets/scripts']
ROOT2 = _XML2 + r'/Scripts'


def feats(root_list):
    c = collections.Counter()
    ex = collections.defaultdict(list)
    for root in root_list:
        for d, _, fs in os.walk(root):
            for f in fs:
                if not f.lower().endswith('.py'):
                    continue
                p = os.path.join(d, f)
                raw = open(p, 'rb').read()
                rel = os.path.relpath(p, root).replace(os.sep, '/')
                c['files'] += 1
                t = raw.decode('latin-1')
                lines = [l for l in t.replace('\r\n', '\n').split('\n')]
                code = [l for l in lines if l.strip() and not l.lstrip().startswith('#')]

                def hit(k):
                    c[k] += 1
                    if len(ex[k]) < 6:
                        ex[k].append(rel)
                if not raw.strip():
                    hit('empty')
                if b'\n' in raw.replace(b'\r\n', b''):
                    hit('lf_only_lines')
                if code and code[0][:1] in (' ', '\t'):
                    hit('first_code_line_indented')
                if any(l.lstrip().startswith(';') for l in lines):
                    hit('semicolon_comment_lines')
                if re.search(r'^\s*def\s', t, re.M):
                    hit('def')
                if re.search(r'^\s*import\s', t, re.M):
                    hit('import')
                if re.search(r'^\s*(if|elif|while)\b[^\n]*:\s*$', t, re.M):
                    hit('colon_style_if')
                if re.search(r'^\s*(if|elif|while)\b[^:\n]*$', t, re.M):
                    hit('behaved_style_if_no_colon')
                if re.search(r'^\s*endif\b', t, re.M):
                    hit('endif')
                if re.search(r'[\x80-\xff]', t):
                    hit('high_bytes')
                if '\t' in t:
                    hit('tabs')
    return c, ex


c1, e1 = feats(ROOTS1)
c2, e2 = feats([ROOT2])
out = {'xml1': dict(c1), 'xml2': dict(c2), 'xml1_examples': e1, 'xml2_examples': e2}
json.dump(out, open(_REPO + r'/research/sweep/script_syntax.json', 'w'), indent=1)
for k in sorted(set(c1) | set(c2)):
    print('%-28s xml1 %5d  xml2 %5d   e.g. %s | %s' % (k, c1[k], c2[k], e1.get(k, [])[:2], e2.get(k, [])[:1]))
