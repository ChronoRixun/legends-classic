"""Extract the script-function registration tables from XMen2.exe (PE) and default.xbe (XBE).

Record layout (16 bytes): {void *handler, char *name, char *return_sig, char *arg_sig}; see extract().
sig chars seen: n(none) i(int) f(float) s(string) a(actor) b(bool?) ...
We scan every 4-byte aligned position of the data sections for runs of such records.
Writes script_functions.json {game: {name: {ret, args, handler}}} and prints a comparison."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import json, struct, re, sys

X2 = _XML2 + r'/XMen2.exe'
X1 = _REPO + r'/xml1_xbox/default.xbe'
IDENT = re.compile(rb'^[A-Za-z_][A-Za-z0-9_]*$')
SIG = re.compile(rb'^[a-z]{0,12}$')


class Image:
    def __init__(self, path):
        b = open(path, 'rb').read()
        self.b = b
        self.secs = []
        if b[:4] == b'XBEH':
            base = struct.unpack_from('<I', b, 0x104)[0]
            n, hdr = struct.unpack_from('<II', b, 0x11c)
            for i in range(n):
                o = hdr - base + i * 56
                flags, va, vsize, raw, rsize, name = struct.unpack_from('<6I', b, o)
                nm = b[name - base:b.find(b'\0', name - base)]
                # every XBE section has flag 4 set; the game code lives in .text
                self.secs.append((va, raw, rsize, nm == b'.text'))
        else:
            import pefile
            pe = pefile.PE(data=b)
            ib = pe.OPTIONAL_HEADER.ImageBase
            for s in pe.sections:
                self.secs.append((ib + s.VirtualAddress, s.PointerToRawData, s.SizeOfRawData,
                                  bool(s.Characteristics & 0x20000000)))

    def off(self, v):
        for va, raw, size, x in self.secs:
            if va <= v < va + size:
                return raw + v - va

    def is_code(self, v):
        return any(va <= v < va + size and x for va, raw, size, x in self.secs)

    def cstr(self, v):
        o = self.off(v)
        if o is None:
            return None
        e = self.b.find(b'\0', o, o + 80)
        if e < 0:
            return None
        return self.b[o:e]


def extract(path):
    """Record layout is {void *handler, char *name, char *ret_sig, char *arg_sig} (16 bytes).
    Proven on default.xbe: the dword before 'blackbirdMenu'(sss) is 0x9a370, which formats
    "setblackbirdparms %s %s %s FALSE FALSE" from three string args; and both tables end right after an
    arg_sig field (XMen2.exe: 'SetDontShowWarningOff' record is followed by the float pi).
    A NULL arg_sig means no arguments."""
    im = Image(path)
    out = {}
    for va, raw, size, x in im.secs:
        if x:
            continue
        for o in range(raw + 4, raw + size - 12, 4):
            h, n, r, a = struct.unpack_from('<4I', im.b, o - 4)
            if not im.is_code(h):
                continue
            name = im.cstr(n)
            if not name or not IDENT.match(name) or len(name) < 2:
                continue
            rs = im.cstr(r)
            as_ = b'' if a == 0 else im.cstr(a)
            if rs is None or as_ is None or not SIG.match(rs) or not SIG.match(as_) or len(rs) > 1:
                continue
            out[name.decode()] = {'ret': rs.decode(), 'args': as_.decode(), 'handler': hex(h),
                                  'record_va': hex(va + o - 4 - raw)}
    return out


if __name__ == '__main__':
    x2 = extract(X2)
    x1 = extract(X1)
    json.dump({'xml2': x2, 'xml1': x1}, open(_REPO + r'/research/sweep/script_functions.json', 'w'),
              indent=1, sort_keys=True)
    print('XML2 functions:', len(x2), ' XML1 functions:', len(x1))
    l2 = {k.lower(): k for k in x2}
    l1 = {k.lower(): k for k in x1}
    only1 = sorted(k for k in l1 if k not in l2)
    only2 = sorted(k for k in l2 if k not in l1)
    print('XML1-only (%d):' % len(only1), [l1[k] + '(' + x1[l1[k]]['args'] + ')' for k in only1])
    print('XML2-only (%d):' % len(only2))
    sigdiff = [(l1[k], x1[l1[k]]['ret'] + ':' + x1[l1[k]]['args'], x2[l2[k]]['ret'] + ':' + x2[l2[k]]['args'])
               for k in l1 if k in l2 and (x1[l1[k]]['args'], x1[l1[k]]['ret']) != (x2[l2[k]]['args'], x2[l2[k]]['ret'])]
    print('signature changes (%d):' % len(sigdiff))
    for s in sorted(sigdiff):
        print('   ', s)
