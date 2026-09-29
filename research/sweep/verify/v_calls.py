"""Independent recount of XML1 script calls to functions absent from XML2's table.
Checks double counting between xml1_loose/scripts and xml1_assets/scripts."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, json, collections, hashlib, sys

VT = json.load(open(_REPO + r'/research/sweep/verify/v_table.json'))
SF = json.load(open(_REPO + r'/research/sweep/script_functions.json'))
x1 = {k.lower() for k in SF['xml1']}
x2 = {k.lower() for k in SF['xml2']}

roots = [_REPO + r'/xml1_loose/scripts', _REPO + r'/xml1_assets/scripts']
files = {}
for r in roots:
    for d, _, fs in os.walk(r):
        for f in fs:
            if f.lower().endswith('.py'):
                p = os.path.join(d, f)
                rel = os.path.relpath(p, r).replace(os.sep, '/').lower()
                files.setdefault(rel, []).append(p)
both = [k for k, v in files.items() if len(v) > 1]
print('distinct rel paths', len(files), 'in both trees', len(both))
same = sum(1 for k in both if open(files[k][0], 'rb').read() == open(files[k][1], 'rb').read())
print('   of which identical bytes', same)
if both:
    print('   example', both[:5])

CALL = re.compile(r'(?<![\w.])(?:game\.)?([A-Za-z_][A-Za-z0-9_]*)\s*\(')


def calls(text):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('#'):
            continue
        # strip trailing comments crudely (not in strings)
        out.extend(m.group(1) for m in CALL.finditer(line))
    return out


cnt_all = collections.Counter()
cnt_dedup = collections.Counter()
for rel, ps in files.items():
    for i, p in enumerate(ps):
        cs = calls(open(p, encoding='latin-1').read())
        for c in cs:
            cnt_all[c] += 1
            if i == 0:
                cnt_dedup[c] += 1

miss_all = {k: v for k, v in cnt_all.items() if k.lower() in x1 and k.lower() not in x2}
miss_dd = {k: v for k, v in cnt_dedup.items() if k.lower() in x1 and k.lower() not in x2}
print('missing (engine fn in x1, not in x2) - counting both trees:', len(miss_all), sum(miss_all.values()))
print('missing - dedup by relative path:', len(miss_dd), sum(miss_dd.values()))
for k, v in sorted(miss_dd.items(), key=lambda x: -x[1]):
    print('   %-24s %4d (all-trees %d)' % (k, v, miss_all[k]))
unknown = {k: v for k, v in cnt_dedup.items() if k.lower() not in x1}
print('call names not in XML1 table (dedup):', len(unknown))
print('   ', sorted(unknown.items(), key=lambda x: -x[1])[:60])
# case mismatches: names used with a case different from the table
case = {k: v for k, v in cnt_dedup.items() if k.lower() in x1 and k not in SF['xml1']}
print('case-variant calls:', case)
