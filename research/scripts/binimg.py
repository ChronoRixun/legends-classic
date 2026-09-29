"""Load a PE (via pefile) or an Xbox XBE into a flat virtual-memory image.

Image(path) -> .base, .mem (bytearray covering [base, base+len)), .sections [(name, va, vsize)],
.text (va_lo, va_hi), .u32(va), .cstr(va), .va2file(va) (XBE only).
"""
import struct


class Image:
    def __init__(self, path):
        data = open(path, 'rb').read()
        self.path = path
        self.sections = []
        if data[:4] == b'XBEH':
            self.kind = 'xbe'
            base, = struct.unpack_from('<I', data, 0x104)
            nsec, secaddr = struct.unpack_from('<II', data, 0x11C)
            self.base = base
            secs = []
            top = 0
            for i in range(nsec):
                o = secaddr - base + i * 56
                flags, va, vs, ra, rs, na = struct.unpack_from('<IIIIII', data, o)
                no = na - base
                name = data[no:data.index(b'\0', no)].decode()
                secs.append((name, va, vs, ra, rs))
                top = max(top, va + vs)
            mem = bytearray(top - base)
            hdr = struct.unpack_from('<I', data, 0x108)[0]
            mem[0:hdr] = data[0:hdr]
            for name, va, vs, ra, rs in secs:
                n = min(rs, vs)
                mem[va - base:va - base + n] = data[ra:ra + n]
                self.sections.append((name, va, vs))
            self._secs_raw = secs
        else:
            import pefile
            self.kind = 'pe'
            pe = pefile.PE(path)
            self.base = pe.OPTIONAL_HEADER.ImageBase
            mem = bytearray(pe.get_memory_mapped_image())
            for s in pe.sections:
                self.sections.append((s.Name.rstrip(b'\0').decode(errors='replace'),
                                      self.base + s.VirtualAddress, s.Misc_VirtualSize))
        self.mem = mem
        t = [s for s in self.sections if s[0] == '.text'][0]
        self.text = (t[1], t[1] + t[2])

    def ok(self, va):
        return self.base <= va < self.base + len(self.mem)

    def u32(self, va):
        return struct.unpack_from('<I', self.mem, va - self.base)[0]

    def cstr(self, va, maxlen=200):
        if not self.ok(va):
            return None
        r = va - self.base
        e = self.mem.find(b'\0', r, r + maxlen)
        if e < 0:
            return None
        s = bytes(self.mem[r:e])
        try:
            return s.decode('ascii')
        except UnicodeDecodeError:
            return None

    def va2file(self, va):
        for name, sva, vs, ra, rs in self._secs_raw:
            if sva <= va < sva + rs:
                return ra + va - sva
        return None
