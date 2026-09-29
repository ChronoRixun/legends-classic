"""xml1build.prepare.image - read an Xbox disc image in place (BUILDER_DESIGN.md 1.1): format detection, the XDVDFS
file system, and SubFile windows onto its (contiguous) files. No copy of the image is ever made.

XDVDFS (the Xbox game partition's file system):
  * volume descriptor at partition offset 0x10000 (sector 32): 'MICROSOFT*XBOX*MEDIA' (20 bytes), root directory
    sector (u32), root directory size (u32), FILETIME (8), ..., the same 20-byte magic again at +0x7EC;
  * a directory is a table of entries forming a binary search tree: u16 left, u16 right (offsets of the child
    entries in 4-byte units; 0 = none), u32 first sector, u32 size, u8 attributes (0x10 = directory), u8 name
    length, name (latin-1); entries are 4-byte aligned and never cross a sector; 0xFF bytes pad a sector's unused
    tail (a 'left' of 0xFFFF). An empty directory has size 0;
  * every file is ONE contiguous extent: sector * 2048 from the partition start, `size` bytes.

Where the partition starts (probed in this order; the design's table in 1.1):
  0x18300000  a Redump XGD1 full image (video partition first; X-Men Legends is XGD1)
  0x0FD90000  XGD2,  0x02080000  XGD3
  0           an XISO (extract-xiso / xdvdfs rewritten or trimmed game partition)

Everything else is rejected with a specific code (prepare.PrepareError): E_ISO_COMPRESSED (CCI / CSO / an archive),
E_ISO_NOT_XBOX (+ detail['detected']: ps2, ps1, gamecube, wii, iso9660, unknown), E_ISO_FOLDER (a directory),
E_ISO_NOT_FOUND, E_ISO_READ (truncated / unreadable)."""
from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from pathlib import Path

from . import PrepareError

SECTOR = 2048
MAGIC = b'MICROSOFT*XBOX*MEDIA'
VOLUME_OFFSET = 0x10000                        # sector 32 of the partition
PARTITIONS = ((0x18300000, 'redump-xgd1'), (0x0FD90000, 'redump-xgd2'), (0x02080000, 'redump-xgd3'), (0, 'xiso'))
ATTR_DIRECTORY = 0x10


@dataclass(frozen=True)
class Entry:
    path: str          # '/'-separated, spelled as on the disc ('sounds/zsds/a/c/aco_e_m.zsm')
    sector: int
    size: int
    is_dir: bool


class SubFile(io.RawIOBase):
    """A read-only, seekable window [offset, offset + size) of an open binary file: what zipfile needs to open
    assetsfb.zip where it lies inside the image. Shares the parent handle (not thread-safe: one reader at a time)."""

    def __init__(self, fh, offset, size):
        super().__init__()
        self._fh, self._off, self._size, self._pos = fh, int(offset), int(size), 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self._pos

    def seek(self, pos, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            p = pos
        elif whence == io.SEEK_CUR:
            p = self._pos + pos
        elif whence == io.SEEK_END:
            p = self._size + pos
        else:
            raise ValueError(f'bad whence {whence}')
        if p < 0:
            raise ValueError('negative seek position')
        self._pos = p
        return p

    def read(self, n=-1):
        left = self._size - self._pos
        if left <= 0:
            return b''
        if n is None or n < 0 or n > left:
            n = left
        self._fh.seek(self._off + self._pos)
        data = self._fh.read(n)
        if len(data) != n:
            raise PrepareError('E_ISO_READ', f'the image ends inside a file (wanted {n} bytes at '
                               f'{self._off + self._pos:#x}, got {len(data)})', 'the image is truncated - dump it again')
        self._pos += n
        return data

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)

    def readall(self):
        return self.read(-1)


def _read_at(fh, offset, n):
    fh.seek(offset)
    return fh.read(n)


def detect(fh, size) -> dict:
    """{'format': ..., 'partition': offset} for an Xbox image; raises PrepareError for anything else."""
    for off, fmt in PARTITIONS:
        if off + VOLUME_OFFSET + SECTOR > size:
            continue
        vd = _read_at(fh, off + VOLUME_OFFSET, SECTOR)
        if vd[:20] == MAGIC and vd[0x7EC:0x7EC + 20] == MAGIC:
            return {'format': fmt, 'partition': off}
    head = _read_at(fh, 0, 0x40)
    if head[:4] == b'CCIM':
        raise PrepareError('E_ISO_COMPRESSED', 'this is a compressed CCI image', 'decompress it to an ISO first '
                           '(e.g. with the tool that made it: Repackinator / cci2iso), then choose the .iso',
                           {'detected': 'cci'})
    if head[:4] in (b'CISO', b'ZISO'):
        raise PrepareError('E_ISO_COMPRESSED', f'this is a compressed {head[:4].decode()} image',
                           'decompress it to an ISO first (e.g. ciso / maxcso --decompress), then choose the .iso',
                           {'detected': head[:4].decode().lower()})
    for sig, kind in ((b'PK\x03\x04', 'zip'), (b'7z\xbc\xaf\x27\x1c', '7z'), (b'Rar!\x1a\x07', 'rar')):
        if head.startswith(sig):
            raise PrepareError('E_ISO_COMPRESSED', f'this is a {kind} archive, not a disc image',
                               'extract the .iso from the archive first', {'detected': kind})
    if len(head) >= 0x20 and struct.unpack_from('>I', head, 0x1C)[0] == 0xC2339F3D:
        raise PrepareError('E_ISO_NOT_XBOX', 'this is a GameCube disc image; the builder needs the Xbox version of '
                           'X-Men Legends', None, {'detected': 'gamecube', 'game_code': head[:6].decode('latin-1')})
    if len(head) >= 0x1C and struct.unpack_from('>I', head, 0x18)[0] == 0x5D1C9EA3:
        raise PrepareError('E_ISO_NOT_XBOX', 'this is a Wii disc image; the builder needs the Xbox version of '
                           'X-Men Legends', None, {'detected': 'wii'})
    pvd = _read_at(fh, 0x8000, SECTOR) if size >= 0x8000 + SECTOR else b''
    if pvd[1:6] == b'CD001':
        cnf = _iso9660_root_file(fh, pvd, 'SYSTEM.CNF')
        if cnf is not None and b'BOOT2' in cnf.upper():
            kind, what = 'ps2', 'a PlayStation 2 disc image'
        elif cnf is not None and b'BOOT' in cnf.upper():
            kind, what = 'ps1', 'a PlayStation disc image'
        else:
            kind, what = 'iso9660', 'an ISO 9660 image (a PC or other disc)'
        raise PrepareError('E_ISO_NOT_XBOX', f'this is {what}, not an Xbox disc image; the builder needs your '
                           'X-Men Legends Xbox disc', None, {'detected': kind})
    raise PrepareError('E_ISO_NOT_XBOX', 'no Xbox file system (XDVDFS) found in this file',
                       'choose an Xbox disc image (.iso / .xiso)', {'detected': 'unknown'})


def _iso9660_root_file(fh, pvd, name):
    """bytes (first 4 KB) of a file in an ISO 9660 image's root directory, or None."""
    try:
        rec = pvd[156:156 + 34]
        lba, size = struct.unpack_from('<I', rec, 2)[0], struct.unpack_from('<I', rec, 10)[0]
        data = _read_at(fh, lba * SECTOR, min(size, 64 * SECTOR))
        pos = 0
        while pos < len(data):
            ln = data[pos]
            if ln == 0:
                pos = (pos // SECTOR + 1) * SECTOR
                continue
            nl = data[pos + 32]
            fname = data[pos + 33:pos + 33 + nl].decode('latin-1').upper().split(';')[0]
            if fname == name.upper():
                flba, fsize = struct.unpack_from('<I', data, pos + 2)[0], struct.unpack_from('<I', data, pos + 10)[0]
                return _read_at(fh, flba * SECTOR, min(fsize, 4096))
            pos += ln
    except (struct.error, IndexError):
        return None
    return None


class XdvdfsImage:
    """An open Xbox disc image: .format, .partition, .entries {lower path: Entry}; open_file(path) -> SubFile.

    path: the image file, or an open seekable binary file object. Use as a context manager (closes the handle)."""

    def __init__(self, path):
        if isinstance(path, (str, Path)):
            p = Path(path)
            if p.is_dir():
                raise PrepareError('E_ISO_FOLDER', f'{p} is a folder; the builder reads the disc image itself',
                                   'choose the .iso file (make one from your disc: see DUMPING.md)')
            if not p.is_file():
                raise PrepareError('E_ISO_NOT_FOUND', f'no such file: {p}')
            self.path, self.size, self.fh = p, p.stat().st_size, open(p, 'rb')
        else:                               # an open binary file object (tests: virtual images)
            fh = path
            fh.seek(0, io.SEEK_END)
            self.path, self.size, self.fh = Path(getattr(fh, 'name', None) or '<image>'), fh.tell(), fh
        try:
            d = detect(self.fh, self.size)
            self.format, self.partition = d['format'], d['partition']
            vd = _read_at(self.fh, self.partition + VOLUME_OFFSET, SECTOR)
            self.root_sector, self.root_size = struct.unpack_from('<II', vd, 20)
            self.entries = {}
            self._walk(self.root_sector, self.root_size, '')
        except BaseException:
            self.fh.close()
            raise

    def close(self):
        self.fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _walk(self, sector, size, prefix, depth=0):
        if depth > 64:
            raise PrepareError('E_ISO_READ', f'directory nesting too deep under {prefix!r}', 'the image is damaged')
        if size == 0:
            return
        start = self.partition + sector * SECTOR
        if start + size > self.size:
            raise PrepareError('E_ISO_READ', f'directory {prefix or "/"} lies beyond the end of the image',
                               'the image is truncated - dump it again')
        data = _read_at(self.fh, start, size)
        stack, seen = [0], set()
        while stack:
            off = stack.pop()
            if off in seen or off + 14 > len(data):
                continue
            seen.add(off)
            left, right, first, length, attrs, nlen = struct.unpack_from('<HHIIBB', data, off)
            if left == 0xFFFF:                       # sector padding, not an entry
                continue
            name = data[off + 14:off + 14 + nlen].decode('latin-1')
            if left:
                stack.append(left * 4)
            if right:
                stack.append(right * 4)
            if not name or '/' in name or '\\' in name or name in ('.', '..'):
                raise PrepareError('E_ISO_READ', f'bad directory entry {name!r} under {prefix or "/"}',
                                   'the image is damaged')
            path = f'{prefix}/{name}' if prefix else name
            is_dir = bool(attrs & ATTR_DIRECTORY)
            self.entries[path.lower()] = Entry(path, first, length, is_dir)
            if is_dir:
                self._walk(first, length, path, depth + 1)
            elif self.partition + first * SECTOR + length > self.size:
                raise PrepareError('E_ISO_READ', f'{path} lies beyond the end of the image',
                                   'the image is truncated - dump it again')

    # ------------------------------------------------------------------ access
    def get(self, path) -> Entry | None:
        return self.entries.get(str(path).replace('\\', '/').strip('/').lower())

    def files_under(self, prefix):
        """[Entry] of the files under a directory (any case), sorted by path."""
        p = str(prefix).replace('\\', '/').strip('/').lower() + '/'
        return sorted((e for k, e in self.entries.items() if k.startswith(p) and not e.is_dir),
                      key=lambda e: e.path)

    def open_file(self, path) -> SubFile:
        e = self.get(path)
        if e is None or e.is_dir:
            raise KeyError(path)
        return SubFile(self.fh, self.partition + e.sector * SECTOR, e.size)

    def read_file(self, path) -> bytes:
        return self.open_file(path).read()

    def copy_file(self, path, dst: Path, chunk=8 << 20, hasher=None):
        """copy one file of the image to dst (parents created); returns its size."""
        src = self.open_file(path)
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with open(dst, 'wb') as o:
            while True:
                b = src.read(chunk)
                if not b:
                    break
                if hasher is not None:
                    hasher.update(b)
                o.write(b)
                n += len(b)
        return n

    def listing(self):
        """[(path, size, is_dir)] sorted: the layout-independent content listing (cache keys)."""
        return sorted((e.path, e.size, e.is_dir) for e in self.entries.values())


def open_image(path) -> XdvdfsImage:
    return XdvdfsImage(path)
