"""Walk the script-function table forwards and backwards from a known record (name VA),
independently of the researcher's scanner. Prints every 16-byte record and counts them."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, struct, json, re
sys.path.insert(0, _REPO + r'/research/sweep/verify')
from v_img import Img, X1, X2

IDENT = re.compile(rb'^[A-Za-z_][A-Za-z0-9_]*$')


def rec_at(im, o):
    h, n, r, a = struct.unpack_from('<4I', im.b, o)
    name = im.cstr(n, 80)
    ret = im.cstr(r, 20)
    args = b'' if a == 0 else im.cstr(a, 20)
    ok = (name is not None and IDENT.match(name) and ret is not None and re.match(rb'^[a-z]{0,3}$', ret)
          and args is not None and re.match(rb'^[a-z]{0,16}$', args))
    return ok, (h, name, ret, args)


def walk(path, anchor):
    im = Img(path)
    hit = im.b.find(b'\0' + anchor + b'\0') + 1
    sv = im.va(hit)
    ref = im.dword_refs(sv)
    assert len(ref) == 1, ref
    o = ref[0] - 4
    start = o
    while True:
        ok, r = rec_at(im, start - 16)
        if not ok:
            break
        start -= 16
    end = o
    while True:
        ok, r = rec_at(im, end + 16)
        if not ok:
            break
        end += 16
    recs = []
    for x in range(start, end + 16, 16):
        ok, (h, n, r, a) = rec_at(im, x)
        recs.append({'va': hex(im.va(x)), 'handler': hex(h), 'name': n.decode(), 'ret': r.decode(), 'args': a.decode()})
    # what follows the table
    tail = struct.unpack_from('<4I', im.b, end + 16)
    head = struct.unpack_from('<4I', im.b, start - 16)
    return recs, [hex(t) for t in head], [hex(t) for t in tail]


out = {}
for g, p, anchor in (('xml1', X1, b'screenFade'), ('xml2', X2, b'cameraFade')):
    recs, head, tail = walk(p, anchor)
    out[g] = recs
    print(g, 'records', len(recs), 'first', recs[0], 'last', recs[-1])
    print('   dwords before table', head, ' after', tail)
    names = [r['name'] for r in recs]
    dups = set(n for n in names if names.count(n) > 1)
    print('   dup names', dups)
json.dump(out, open(_REPO + r'/research/sweep/verify/v_table.json', 'w'), indent=1)
