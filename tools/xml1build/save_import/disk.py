"""Bounded read-only Xbox HDD access; no mount, export, backing file or writes.

QCOW2 v2/v3 uses standard L1/L2 tables (512-byte sectors, zlib compression).
Xbox PARTINFO entries describe sector ranges; a stock disk without that table
uses only the fixed retail E geometry. FATX names are byte names, at most 42
bytes; no host paths are constructed from them. All extracted data stays in RAM.
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import struct
import zlib

from .errors import ImportRefusal
from .source import CAPACITY, MAX_DEPTH, MAX_ENTRIES, TITLE_ID, digest, envelope, safe_path

MAX_READ = 16 << 20
MAX_IO = 64 << 20
MAX_VIRTUAL = 2 << 40
STOCK_E = (0xabe80000, 0x9896b0 * 512)
PART_MAGIC = b'****PARTINFO****'


def refuse(reason, *, unsupported=False, **detail):
    raise ImportRefusal('DISK_VERSION' if unsupported else 'DISK_DAMAGED', reason, **detail)


def identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def span(offset, size, limit, what):
    if offset < 0 or size < 0 or offset > limit or size > limit - offset:
        refuse(what + ' is outside its container.', offset=offset, size=size)


@contextmanager
def open_image(path):
    """On Windows deny writers/deletion while inspecting, including a live xemu."""
    path = safe_path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        refuse('Choose a regular local HDD image.', unsupported=True)
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        import msvcrt
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        api.CreateFileW.restype = wintypes.HANDLE
        api.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = api.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x00200000, None)
        if handle == wintypes.HANDLE(-1).value:
            error = ctypes.get_last_error()
            if error in (32, 33):
                raise ImportRefusal('BUSY', 'The HDD image is in use. Close its writer before inspecting it.')
            raise ctypes.WinError(error)
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY | os.O_NOINHERIT)
        except BaseException:
            api.CloseHandle(handle)
            raise
    else:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        if identity(before) != identity(os.fstat(stream.fileno())):
            raise ImportRefusal('CHANGED', 'The image changed before opening.')
        yield stream, before
        if identity(before) != identity(os.fstat(stream.fileno())) or identity(before) != identity(safe_path(path).stat()):
            raise ImportRefusal('CHANGED', 'The image changed while being inspected.')


class Disk:
    def __init__(self, stream, physical):
        self.stream, self.physical = stream, physical
        self.io = 0
        self.reads = {}
        self.regions = []
        self.l2 = OrderedDict()
        self.compressed = OrderedDict()
        self.expanded = 0
        magic = self.at(0, min(physical, 4))
        self.format = 'raw'
        self.size = physical
        if magic != b'QFI\xfb':
            if physical < 512 or physical % 512 or physical > MAX_VIRTUAL:
                refuse('Unknown image format or raw sector geometry.', unsupported=True)
            return
        self.format = 'qcow2'
        h = self.at(0, 72)
        version, backing, backing_size, bits, size, crypt, n1, l1off, ref_off, ref_count, snapshots, snap_off = struct.unpack_from('>IQIIQIIQQIIQ', h, 4)
        self._version = version
        if version not in (2, 3):
            refuse('Only QCOW2 versions 2 and 3 are supported.', unsupported=True)
        if backing or backing_size:
            refuse('QCOW2 backing chains are unsupported. Select a standalone flattened image.', unsupported=True)
        if crypt:
            refuse('Encrypted QCOW2 images are unsupported.', unsupported=True)
        if snapshots or snap_off:
            refuse('QCOW2 internal snapshots are unsupported.', unsupported=True)
        if not 9 <= bits <= 21 or size < 512 or size % 512 or size > MAX_VIRTUAL:
            refuse('Invalid QCOW2 cluster or virtual size.')
        self.bits, self.cluster, self.size = bits, 1 << bits, size
        header_length = 72
        if version == 3:
            v3 = self.at(72, 32)
            incompatible, compatible, autoclear, ref_order, header_length = struct.unpack('>QQQII', v3)
            if incompatible:
                refuse('QCOW2 dirty/corrupt or unsupported incompatible features.', unsupported=True, features=incompatible)
            if ref_order != 4:
                refuse('Nonstandard QCOW2 refcount width is unsupported.', unsupported=True)
            if not 104 <= header_length <= self.cluster:
                refuse('Invalid QCOW2 header length.')
        self.region(0, self.cluster, 'header')
        # Cap table allocation independently of virtual size, before reading it.
        needed = (size + self.cluster * (self.cluster // 8) - 1) // (self.cluster * (self.cluster // 8))
        if n1 < needed or n1 > (8 << 20) // 8:
            refuse('Invalid or excessive QCOW2 L1 table size.')
        self.region(l1off, ((n1 * 8 + self.cluster - 1) // self.cluster) * self.cluster, 'L1')
        if not ref_count or ref_count * self.cluster > 8 << 20:
            refuse('Invalid or excessive QCOW2 refcount table.')
        self.region(ref_off, ref_count * self.cluster, 'refcount table')
        ref_table = self.at(ref_off, ref_count * self.cluster)
        for (off,) in struct.iter_unpack('>Q', ref_table):
            if off:
                self.region(off, self.cluster, 'refcount block')
        self.l1 = self.at(l1off, n1 * 8)
        for (entry,) in struct.iter_unpack('>Q', self.l1):
            if entry & ~((1 << 63) | 0x00fffffffffffe00):
                refuse('Reserved bits in QCOW2 L1 entry.')
            off = entry & 0x00fffffffffffe00
            if off:
                self.region(off, self.cluster, 'L2')
            elif entry:
                refuse('Flags on an unallocated QCOW2 L1 entry.')

    def region(self, offset, size, role):
        if len(self.regions) >= 4096:
            refuse('QCOW2 mapping metadata exceeds the inspection budget.', unsupported=True)
        if offset % self.cluster or size % self.cluster or (not offset and role != 'header'):
            refuse('Misaligned QCOW2 ' + role + '.')
        span(offset, size, self.physical, 'QCOW2 ' + role)
        for lo, hi, old in self.regions:
            if offset < hi and lo < offset + size:
                if (offset, offset + size, role) == (lo, hi, old) and role == 'L2':
                    return
                refuse('Overlapping QCOW2 metadata.')
        self.regions.append((offset, offset + size, role))

    def data_span(self, offset, size):
        span(offset, size, self.physical, 'QCOW2 data')
        if any(offset < hi and lo < offset + size for lo, hi, _ in self.regions):
            refuse('QCOW2 data overlaps mapping metadata.')

    def at(self, offset, size):
        span(offset, size, self.physical, 'Physical read')
        self.io += size
        if size > MAX_READ or self.io > MAX_IO:
            refuse('Image inspection exceeds the bounded I/O budget.', unsupported=True)
        self.stream.seek(offset)
        data = self.stream.read(size)
        if len(data) != size:
            refuse('Truncated physical image read.')
        value = digest(data)
        key = (offset, size)
        if key in self.reads and self.reads[key] != value:
            raise ImportRefusal('CHANGED', 'Image bytes changed during inspection.')
        self.reads[key] = value
        return data

    def read(self, offset, size):
        span(offset, size, self.size, 'Guest read')
        if size > MAX_READ:
            refuse('Guest read exceeds the bounded read size.')
        if self.format == 'raw':
            return self.at(offset, size)
        out = bytearray()
        while size:
            ci, inside = divmod(offset, self.cluster)
            i1, i2 = divmod(ci, self.cluster // 8)
            l2off = struct.unpack_from('>Q', self.l1, i1 * 8)[0] & 0x00fffffffffffe00
            take = min(size, self.cluster - inside)
            entry = 0
            if l2off:
                if l2off not in self.l2:
                    self.l2[l2off] = self.at(l2off, self.cluster)
                    if len(self.l2) > 8:
                        self.l2.popitem(last=False)
                entry = struct.unpack_from('>Q', self.l2[l2off], i2 * 8)[0]
                self.l2.move_to_end(l2off)
            if entry & (1 << 62):
                if entry & (1 << 63):
                    refuse('Invalid compressed QCOW2 flags.')
                shift = 62 - (self.bits - 8)
                physical = entry & ((1 << shift) - 1)
                sectors = ((entry >> shift) & ((1 << (self.bits - 8)) - 1)) + 1
                packed_size = sectors * 512 - (physical & 511)
                self.data_span(physical, packed_size)
                if entry not in self.compressed:
                    self.expanded += self.cluster
                    if self.expanded > MAX_IO:
                        refuse('Image inspection exceeds the decompression budget.', unsupported=True)
                    packed = self.at(physical, packed_size)
                    try:
                        decoder = zlib.decompressobj(-15)
                        block = decoder.decompress(packed, self.cluster + 1)
                    except zlib.error:
                        refuse('Invalid compressed QCOW2 cluster.')
                    if len(block) != self.cluster or not decoder.eof:
                        refuse('Compressed QCOW2 cluster has invalid expanded size.')
                    self.compressed[entry] = block
                    while len(self.compressed) > 8 or len(self.compressed) * self.cluster > 8 << 20:
                        self.compressed.popitem(last=False)
                block = self.compressed[entry]
                self.compressed.move_to_end(entry)
                out += block[inside:inside + take]
            else:
                allowed = (1 << 63) | 0x00fffffffffffe00 | (1 if self._version == 3 else 0)
                if entry & ~allowed:
                    refuse('Reserved bits in QCOW2 L2 entry.')
                physical = entry & 0x00fffffffffffe00
                if physical:
                    if physical % self.cluster:
                        refuse('Misaligned QCOW2 data cluster.')
                    self.data_span(physical, self.cluster)
                elif entry & (1 << 63):
                    refuse('Flags on an unallocated QCOW2 data entry.')
                out += bytes(take) if entry & 1 or not physical else self.at(physical + inside, take)
            offset += take
            size -= take
        return bytes(out)

    def snapshot(self):
        encoded = repr(sorted(self.reads.items())).encode('ascii')
        return hashlib.sha256(encoded).hexdigest()


def e_partition(disk):
    header = disk.read(0, 512)
    if header[:16] == PART_MAGIC:
        ranges, chosen = [], None
        for i in range(14):
            row = header[48 + i * 32:80 + i * 32]
            name, flags, first, count, reserved = struct.unpack('<16sIIII', row)
            if flags & ~0x80000000:
                refuse('Unknown Xbox partition flags.', unsupported=True)
            if not flags:
                continue
            if not first or not count:
                refuse('Empty active Xbox partition.')
            start, size = first * 512, count * 512
            span(start, size, disk.size, 'Xbox partition')
            if any(start < hi and lo < start + size for lo, hi in ranges):
                refuse('Overlapping Xbox partitions.')
            ranges.append((start, start + size))
            if i == 0:
                if name.rstrip(b'\0 ') not in (b'XBOX DATA', b'E', b'E:'):
                    refuse('The first Xbox partition is not the E data partition.', unsupported=True)
                chosen = start, size
        if chosen is None:
            refuse('No active E data partition in the Xbox partition table.', unsupported=True)
        return (*chosen, 'PARTINFO')
    start, size = STOCK_E
    if start + size > disk.size or disk.read(start, 4) != b'FATX':
        refuse('No supported Xbox partition table or stock E FATX volume.', unsupported=True)
    return start, size, 'retail-fixed'


@dataclass(frozen=True)
class Entry:
    name: str
    directory: bool
    cluster: int
    size: int


class Fatx:
    def __init__(self, disk, start, size):
        self.disk, self.start, self.size = disk, start, size
        h = self.read(0, 4096)
        if h[:4] != b'FATX':
            refuse('The E partition has no FATX superblock.', unsupported=True)
        spc, self.root = struct.unpack_from('<II', h, 8)
        if spc not in (1, 2, 4, 8, 16, 32, 64, 128):
            refuse('Invalid FATX sectors per cluster.')
        self.cluster = spc * 512
        capacity = size // self.cluster
        self.width = 2 if capacity < 65525 else 4
        fat_size = ((capacity + 1) * self.width + 4095) & ~4095
        self.data = 4096 + fat_size
        self.count = (size - self.data) // self.cluster
        if self.count < 1:
            refuse('FATX data region is empty.')
        self.valid_cluster(self.root)
        self.owners = {}
        self.scanned = 0

    def read(self, offset, size):
        span(offset, size, self.size, 'FATX partition read')
        return self.disk.read(self.start + offset, size)

    def valid_cluster(self, cluster):
        if not 1 <= cluster <= self.count or cluster >= (0xfff0 if self.width == 2 else 0xfffffff0):
            refuse('FATX cluster is free, reserved, bad or outside the data region.', cluster=cluster)

    def chain(self, first, owner, *, expected=None):
        seen, cluster = set(), first
        limit = 1024 if expected is None else expected
        while True:
            self.valid_cluster(cluster)
            if cluster in seen or len(seen) >= limit:
                refuse('Cyclic or excessive FATX cluster chain.')
            if cluster in self.owners and self.owners[cluster] != owner:
                refuse('Cross-linked FATX file or directory clusters.')
            self.owners[cluster] = owner
            seen.add(cluster)
            data = self.read(self.data + (cluster - 1) * self.cluster, self.cluster)
            next_cluster = int.from_bytes(self.read(4096 + cluster * self.width, self.width), 'little')
            end = next_cluster >= (0xfff8 if self.width == 2 else 0xfffffff8)
            if expected is not None and (len(seen) == expected) != end:
                refuse('FATX file length and cluster chain disagree.')
            yield data
            if end:
                return
            cluster = next_cluster

    def entries(self, first, owner):
        names, rows, ended = set(), [], False
        # Validate the complete chain even after a directory end marker.
        for block in self.chain(first, owner):
            if ended:
                continue
            for off in range(0, self.cluster, 64):
                row = block[off:off + 64]
                n, flags = row[:2]
                if n in (0, 255):
                    ended = True
                    break
                if n == 0xe5:
                    continue
                if n > 42 or flags & ~0x3f or flags & 8:
                    refuse('Invalid FATX directory entry.')
                raw_name = row[2:2 + n]
                if any(c < 32 or c in b'\\/:*?"<>|' for c in raw_name) or raw_name in (b'.', b'..'):
                    refuse('Unsafe FATX filename.')
                name = raw_name.decode('latin-1')
                if name.lower() in names:
                    refuse('Ambiguous case-insensitive FATX names.')
                names.add(name.lower())
                cluster, size = struct.unpack_from('<II', row, 44)
                if flags & 16 or size:
                    self.valid_cluster(cluster)
                elif cluster:
                    refuse('Nonempty cluster chain for an empty FATX file.')
                self.scanned += 1
                if self.scanned > 8192:
                    refuse('FATX directory scan exceeds the entry budget.', unsupported=True)
                rows.append(Entry(name, bool(flags & 16), cluster, size))
        return rows

    def subdir(self, first, owner, name):
        row = next((e for e in self.entries(first, owner) if e.name.lower() == name.lower()), None)
        if row is None or not row.directory:
            raise ImportRefusal('INPUT', 'No XML1 UDATA title folder was found in E:.')
        return row.cluster

    def campaigns(self):
        udata = self.subdir(self.root, 'E:', 'UDATA')
        title = self.subdir(udata, 'E:/UDATA', TITLE_ID)
        queue = [(title, 'E:/UDATA/' + TITLE_ID, 0)]
        found, entries = [], 0
        while queue:
            cluster, parent, depth = queue.pop(0)
            for row in self.entries(cluster, parent):
                entries += 1
                if entries > MAX_ENTRIES:
                    refuse('The title folder exceeds the bounded entry count.', unsupported=True)
                path = parent + '/' + row.name
                if row.directory:
                    if depth == MAX_DEPTH:
                        refuse('The title folder is too deeply nested.', unsupported=True)
                    queue.append((row.cluster, path, depth + 1))
                elif row.name.lower() == 'save.dat':
                    found.append((path, row))
        if not found:
            raise ImportRefusal('INPUT', 'No save.dat exists in E:/UDATA/' + TITLE_ID + '.')
        return found

    def file(self, path, row):
        if row.directory or row.size < 24 or row.size > CAPACITY + 24:
            refuse('The campaign is not a bounded Xbox envelope.')
        count = (row.size + self.cluster - 1) // self.cluster
        return b''.join(self.chain(row.cluster, path, expected=count))[:row.size]


@dataclass(frozen=True)
class ImageSource:
    root: Path
    path: Path
    sha256: str
    payload: bytes
    signature_status: str
    campaign: str
    image_snapshot: str
    image_identity: tuple
    image_format: str
    partition_layout: str

    @property
    def binding(self):
        return dict(kind='hdd-image', campaign=self.campaign, image_snapshot=self.image_snapshot,
                    image_identity=list(self.image_identity), image_format=self.image_format)

    def recheck(self):
        try:
            _, current = inspect_image(self.path, campaign=self.campaign)
        except (ImportRefusal, OSError) as e:
            if isinstance(e, ImportRefusal) and e.code == 'E_XML1_BUSY':
                raise
            raise ImportRefusal('CHANGED', 'The HDD image can no longer be read as previewed.') from e
        if current.sha256 != self.sha256 or current.binding != self.binding:
            raise ImportRefusal('CHANGED', 'The HDD image or selected campaign changed.')


def inspect_image(path, *, campaign=None, verifier=None, discover_only=False):
    path = safe_path(path)
    with open_image(path) as (stream, before):
        disk = Disk(stream, before.st_size)
        start, size, layout = e_partition(disk)
        fs = Fatx(disk, start, size)
        rows = fs.campaigns()
        candidates = [dict(folder=str(path), label=p.rsplit('/', 1)[0], campaign=p.rsplit('/', 1)[0]) for p, _ in rows]
        selected = rows
        if campaign is not None:
            selected = [(p, row) for p, row in rows if p.rsplit('/', 1)[0] == campaign]
            if len(selected) != 1:
                raise ImportRefusal('INPUT', 'Choose a campaign from this image discovery result.')
        if len(selected) != 1:
            if discover_only:
                return candidates, None
            raise ImportRefusal('MULTIPLE', 'Select one HDD campaign with --campaign.', candidates=candidates)
        entry_path, row = selected[0]
        raw = fs.file(entry_path, row)
        payload, status = envelope(raw, verifier)
        source = ImageSource(path, path, digest(raw), payload, status, entry_path.rsplit('/', 1)[0],
                             disk.snapshot(), identity(before), disk.format, layout)
        return candidates, source
