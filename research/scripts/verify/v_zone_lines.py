"""Per-zone total statement count of packaged scripts: XML2 (PKGB) vs XML1 source vs XML1 rewritten.
Context: XMen2.exe allocates one instruction node per script line from a fixed pool of 0x26c (620)
nodes (0x4d7e6e) and at most 0x78 (120) script objects (0x4d86d1). This measures how much the rewrite
inflates per-zone script size relative to what XML2's own zones use."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, json, re, collections
sys.path.insert(0, _REPO + '/tools')
import xmlb

X2 = _XML2
OUT = _REPO + '/research/scripts/out/scripts'
LOOSE = _REPO + '/xml1_loose'


MODE = os.environ.get('MODE', 'stmts')
LIT = re.compile(r'"[^"]*"|\'[^\']*\'|(?<![A-Za-z_0-9.])[-+]?\d+(?:\.\d*)?')


def stmts(path):
    """MODE=stmts: non-comment statements; MODE=lits: string+numeric literals in them."""
    try:
        t = open(path, 'rb').read().decode('latin-1')
    except OSError:
        return None
    n = 0
    for line in t.replace('\r\n', '\n').split('\n'):
        s = line.strip()
        if s and not s.startswith('#'):
            n += len(LIT.findall(s)) if MODE == 'lits' else 1
    return n


# XML2 script index (case-insensitive)
x2idx = {}
for dp, dn, fn in os.walk(X2 + '/Scripts'):
    for f in fn:
        p = os.path.join(dp, f)
        x2idx[os.path.relpath(p, X2 + '/Scripts').replace('\\', '/').lower()] = p

x2tot = []
root = X2 + '/Packages/generated/maps'
for dp, dn, fn in os.walk(root):
    for f in fn:
        if not f.upper().endswith('.PKGB'):
            continue
        p = os.path.join(dp, f)
        e = xmlb.decode(open(p, 'rb').read())
        tot = 0
        cnt = 0
        seenk = set()
        for el in e.iter():
            if el.get('type', '').lower() == 'script' or el.tag.lower() == 'script':
                fname = (el.get('filename') or el.get('name') or '').replace('\\', '/').lower()
                key = fname[len('scripts/'):] if fname.startswith('scripts/') else fname
                if not key.endswith('.py'):
                    key += '.py'
                sp = x2idx.get(key)
                if sp and key not in seenk:
                    seenk.add(key)
                    tot += stmts(sp) or 0
                    cnt += 1
        x2tot.append((tot, cnt, os.path.relpath(p, root)))
x2tot.sort()
print('XML2 zones', len(x2tot), 'max per-zone packaged script statements:', x2tot[-5:])
print('  median', x2tot[len(x2tot) // 2])

man = json.load(open(LOOSE + '/_fb_manifest.json'))
res = []
for b, files in man.items():
    if '/maps/' not in b.replace('\\', '/'):
        continue
    src = out = cnt = 0
    seen1 = set()
    for fpath, kind in files:
        if kind != 'script':
            continue
        rel = fpath.replace('\\', '/').lower()
        if rel in seen1:
            continue
        seen1.add(rel)
        rel2 = rel[len('scripts/'):] if rel.startswith('scripts/') else rel
        a = stmts(os.path.join(LOOSE, rel))
        o = stmts(os.path.join(OUT, rel2))
        src += a or 0
        out += o or 0
        cnt += 1
    res.append((out, src, cnt, b))
res.sort()
print('XML1 zones', len(res))
print('  top by rewritten statements (out, src, nscripts, bundle):')
for r in res[-8:]:
    print('    ', r)
tot_src = sum(r[1] for r in res)
tot_out = sum(r[0] for r in res)
print('  total statements src %d -> out %d (x%.2f)' % (tot_src, tot_out, tot_out / max(tot_src, 1)))
print('  zones whose rewritten total exceeds XML2 max (%d): %d' % (x2tot[-1][0], sum(1 for r in res if r[0] > x2tot[-1][0])))
