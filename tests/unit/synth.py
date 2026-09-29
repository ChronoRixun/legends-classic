"""Synthetic fixtures for the unit tests (BUILDER_DESIGN.md 6.1): tiny XDVDFS images, XBE headers, .fb bundles and
zips made in memory - no game data anywhere."""
import io
import os
import struct
import sys
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from xml1build.prepare import fb as FB  # noqa: E402

SECTOR = 2048
MAGIC = b'MICROSOFT*XBOX*MEDIA'
XGD1 = 0x18300000


# ---------------------------------------------------------------------------------------------------- XDVDFS
def _tree(files, dirs):
    root = {}
    for d in dirs:
        node = root
        for part in d.strip('/').split('/'):
            node = node.setdefault(part, {})
    for path, data in files.items():
        parts = path.strip('/').split('/')
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = bytes(data)
    return root


def _entry_len(name):
    return (14 + len(name.encode('latin-1')) + 3) & ~3


def _tree_order(names, tree):
    """(entries in table order - the tree root first -, {name: (left name, right name)})."""
    if tree == 'chain':
        return names, {n: (None, names[i + 1] if i + 1 < len(names) else None) for i, n in enumerate(names)}
    kids, order = {}, []

    def build(lo, hi):
        if lo >= hi:
            return None
        mid = (lo + hi) // 2
        order.append(names[mid])
        kids[names[mid]] = (build(lo, mid), build(mid + 1, hi))
        return names[mid]
    build(0, len(names))
    return order, kids


def _table_layout(node, tree='chain'):
    """[(offset, name)] of a directory table (entries never cross a sector), its padded size and the tree links."""
    offs, pos = [], 0
    order, kids = _tree_order(sorted(node, key=str.upper), tree)
    for name in order:
        ln = _entry_len(name)
        if pos // SECTOR != (pos + ln - 1) // SECTOR:
            pos = (pos // SECTOR + 1) * SECTOR
        offs.append((pos, name))
        pos += ln
    size = ((pos + SECTOR - 1) // SECTOR) * SECTOR if pos else 0
    return offs, size, kids


def xdvdfs(files, dirs=(), *, tree='chain'):
    """the bytes of an XDVDFS partition holding files {path: bytes} (+ empty dirs). tree='chain' links each entry
    to the next through 'right'; 'balanced' builds a binary search tree (left and right children)."""
    root = _tree(files, dirs)
    layouts = {}
    order = []

    def plan(node, path):
        layouts[path] = _table_layout(node, tree)
        order.append(path)
        for name, child in node.items():
            if isinstance(child, dict):
                plan(child, f'{path}/{name}' if path else name)
    plan(root, '')
    sector = 33
    where = {}
    for path in order:
        size = layouts[path][1]
        where[path] = (sector if size else 0, size)
        sector += size // SECTOR
    data_at = {}

    def alloc(node, path):
        nonlocal sector
        for name, child in node.items():
            p = f'{path}/{name}' if path else name
            if isinstance(child, dict):
                alloc(child, p)
            else:
                data_at[p] = (sector if child else 0, len(child))
                sector += (len(child) + SECTOR - 1) // SECTOR
    alloc(root, '')
    img = bytearray(sector * SECTOR)
    vd = bytearray(SECTOR)
    vd[0:20] = MAGIC
    struct.pack_into('<II', vd, 20, *where[''])
    vd[0x7EC:0x7EC + 20] = MAGIC
    img[32 * SECTOR:33 * SECTOR] = vd

    def fill(node, path):
        offs, size, kids = layouts[path]
        if not size:
            return
        tbl = bytearray(b'\xff' * size)
        idx = {name: off for off, name in offs}
        names = [n for _, n in offs]
        links = {n: tuple(idx[k] // 4 if k else 0 for k in kids[n]) for n in names}
        for n in names:
            child = node[n]
            p = f'{path}/{n}' if path else n
            first, length = where[p] if isinstance(child, dict) else data_at[p]
            nb = n.encode('latin-1')
            left, right = links[n]
            ent = struct.pack('<HHIIBB', left, right, first, length, 0x10 if isinstance(child, dict) else 0x20,
                              len(nb)) + nb
            ent = ent.ljust(_entry_len(n), b'\0')
            tbl[idx[n]:idx[n] + len(ent)] = ent
        s = where[path][0] * SECTOR
        img[s:s + size] = tbl
        for n in names:
            if isinstance(node[n], dict):
                fill(node[n], f'{path}/{n}' if path else n)
    fill(root, '')
    for p, (first, length) in data_at.items():
        if length:
            node = root
            for part in p.split('/')[:-1]:
                node = node[part]
            img[first * SECTOR:first * SECTOR + length] = node[p.split('/')[-1]]
    return bytes(img)


class ZeroPrefixed(io.RawIOBase):
    """a virtual file: `prefix` zero bytes followed by `data` (a Redump-layout image without 400 MB on disk)."""

    def __init__(self, data, prefix, name='<redump>'):
        super().__init__()
        self.data, self.prefix, self.pos, self.name = data, prefix, 0, name

    def readable(self):
        return True

    def seekable(self):
        return True

    def seek(self, pos, whence=0):
        self.pos = pos if whence == 0 else self.pos + pos if whence == 1 else self.prefix + len(self.data) + pos
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        end = self.prefix + len(self.data)
        if n is None or n < 0:
            n = end - self.pos
        n = max(0, min(n, end - self.pos))
        out = bytearray()
        p = self.pos
        if p < self.prefix:
            z = min(n, self.prefix - p)
            out += bytes(z)
            p += z
            n -= z
        if n:
            out += self.data[p - self.prefix:p - self.prefix + n]
            p += n
        self.pos = p
        return bytes(out)

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)


def write_sparse(path, data, offset):
    """write data at offset into a new file, sparse where the OS allows (NTFS: FSCTL_SET_SPARSE; others: holes
    come for free). Returns True when the file is sparse (or the OS makes holes by itself)."""
    sparse = True
    with open(path, 'wb') as fh:
        if os.name == 'nt':
            try:
                import ctypes
                import msvcrt
                from ctypes import wintypes
                k32 = ctypes.WinDLL('kernel32', use_last_error=True)
                k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                                wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                                wintypes.LPVOID]
                ret = wintypes.DWORD()
                sparse = bool(k32.DeviceIoControl(msvcrt.get_osfhandle(fh.fileno()), 0x000900C4, None, 0, None, 0,
                                                  ctypes.byref(ret), None))
            except (OSError, AttributeError, ImportError):
                sparse = False
        if not sparse:
            return False
        fh.seek(offset)
        fh.write(data)
    return True


# ---------------------------------------------------------------------------------------------------- XBE
def xbe(title_id=0x4156001E, title='X-Men Legends', version=1, region=7, alt=()):
    base, cert_off = 0x10000, 0x180
    b = bytearray(0x400)
    b[0:4] = b'XBEH'
    struct.pack_into('<I', b, 0x104, base)
    struct.pack_into('<II', b, 0x114, 1092605368, base + cert_off)
    c = bytearray(0x1D0)
    struct.pack_into('<I', c, 0x00, 0x1D0)
    struct.pack_into('<I', c, 0x08, title_id)
    name = title.encode('utf-16-le')[:80]
    c[0x0C:0x0C + len(name)] = name
    for i, a in enumerate(alt[:16]):
        struct.pack_into('<I', c, 0x5C + 4 * i, a)
    struct.pack_into('<5I', c, 0x9C, 0x202, region, 3, 0, version)
    b[cert_off:cert_off + len(c)] = c[:0x400 - cert_off]
    return bytes(b)


# ---------------------------------------------------------------------------------------------------- zip / fb
def bundle(records):
    return FB.build(records)


def zip_bytes(members, dirs=()):
    """a deflated zip: members {name: bytes} in the given order, directory entries first."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, 'w', zipfile.ZIP_DEFLATED) as z:
        for d in dirs:
            z.writestr(zipfile.ZipInfo(d.rstrip('/') + '/'), b'')
        for name, data in members.items():
            z.writestr(name, data)
    return bio.getvalue()


def xml1_disc_files(title_id=0x4156001E, extra_zip=None, drop=()):
    """the files of a tiny fake X-Men Legends disc: default.xbe, z/assetsfb.zip (a data file, an empty folder and
    three bundles with duplicate / conflicting entries), a ZSND-named file, an NTSC movie name."""
    b1 = bundle([('actors/0001.igb', 'actorskin', b'skin one'), ('/Data/Shared.XML', 'xml', b'<a/>'),
                 ('on', 'combat_is', b'')])
    b2 = bundle([('data/shared.xml', 'xml', b'<b/>'),                      # conflicts: dr_mag2 sorts first
                 ('actors/0001.igb', 'actorskin', b'skin one'),            # identical duplicate
                 ('maps/x/y.eng', 'zonexml', b'<world/>')])
    b3 = bundle([('data/shared.xml', 'xml', b'<c/>')])
    members = {'data/colors.xml': b'<colors/>', 'packages/generated/maps/a/dr_mag/x.fb': b3,
               'packages/generated/maps/a/dr_mag2/y.fb': b2, 'packages/generated/characters/c_0001.fb': b1,
               'scripts/menus/start.py': b'print\r\n'}
    members.update(extra_zip or {})
    files = {'default.xbe': xbe(title_id), 'z/assetsfb.zip': zip_bytes(members, dirs=('textures',)),
             'sounds/zsds/a/c/aco_m.zsm': b'ZSNDXBOX' + bytes(56), 'movies/ntsc/i/1/i101.sfd': bytes(4096),
             'movies/pal/i/1/i101.sfd': bytes(2048), 'OptionsImage.xpr': b'XPR0'}
    for d in drop:
        files = {k: v for k, v in files.items() if not k.startswith(d)}
    return files
