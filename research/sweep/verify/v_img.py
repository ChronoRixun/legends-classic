"""Independent image loader for XBE and PE (verifier)."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import struct

X2 = _XML2 + r'/XMen2.exe'
X1 = _REPO + r'/xml1_xbox/default.xbe'


class Img:
    def __init__(self, path):
        b = open(path, 'rb').read()
        self.b = b
        self.secs = []  # (va, vsize, raw, rawsize, name)
        if b[:4] == b'XBEH':
            base = struct.unpack_from('<I', b, 0x104)[0]
            n = struct.unpack_from('<I', b, 0x11c)[0]
            hdr = struct.unpack_from('<I', b, 0x120)[0]
            for i in range(n):
                o = hdr - base + i * 56
                flags, va, vsize, raw, rsize, nameaddr = struct.unpack_from('<6I', b, o)
                no = nameaddr - base
                nm = b[no:b.find(b'\0', no)].decode('latin1')
                self.secs.append((va, vsize, raw, rsize, nm, flags))
        else:
            e_lfanew = struct.unpack_from('<I', b, 0x3c)[0]
            nsec = struct.unpack_from('<H', b, e_lfanew + 6)[0]
            optsz = struct.unpack_from('<H', b, e_lfanew + 20)[0]
            ib = struct.unpack_from('<I', b, e_lfanew + 24 + 28)[0]
            so = e_lfanew + 24 + optsz
            for i in range(nsec):
                o = so + i * 40
                nm = b[o:o + 8].rstrip(b'\0').decode('latin1')
                vsize, vaddr, rsize, raw = struct.unpack_from('<4I', b, o + 8)
                ch = struct.unpack_from('<I', b, o + 36)[0]
                self.secs.append((ib + vaddr, vsize, raw, rsize, nm, ch))

    def off(self, v):
        for va, vs, raw, rs, nm, fl in self.secs:
            if va <= v < va + min(vs, rs) if rs else False:
                return raw + v - va
        return None

    def va(self, off):
        for va, vs, raw, rs, nm, fl in self.secs:
            if raw <= off < raw + rs:
                return va + off - raw
        return None

    def cstr(self, v, maxlen=200):
        o = self.off(v)
        if o is None:
            return None
        e = self.b.find(b'\0', o, o + maxlen)
        if e < 0:
            return None
        return self.b[o:e]

    def find_all(self, s):
        res = []
        i = self.b.find(s)
        while i >= 0:
            res.append(i)
            i = self.b.find(s, i + 1)
        return res

    def dword_refs(self, v):
        """file offsets of 4-byte little-endian occurrences of v"""
        return self.find_all(struct.pack('<I', v))
