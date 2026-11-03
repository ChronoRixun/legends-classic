"""Invented sparse Xbox images; no game bytes, external tools or real images."""
from pathlib import Path
import struct
import zlib


class Guest:
    def __init__(self, size):
        self.size = size
        self.sectors = {}

    def put(self, offset, data):
        assert offset >= 0 and offset + len(data) <= self.size
        while data:
            sector, inside = divmod(offset, 512)
            take = min(len(data), 512 - inside)
            self.sectors.setdefault(sector, bytearray(512))[inside:inside + take] = data[:take]
            offset += take
            data = data[take:]

    def raw(self, path):
        with Path(path).open('xb') as stream:
            stream.truncate(self.size)
            for sector, data in sorted(self.sectors.items()):
                stream.seek(sector * 512)
                stream.write(data)
        return Path(path)

    def qcow(self, path, *, version=3, compressed=False):
        cluster = 65536
        guests = {}
        for sector, data in self.sectors.items():
            ci, inside = divmod(sector * 512, cluster)
            guests.setdefault(ci, bytearray(cluster))[inside:inside + 512] = data
        l1_count = (self.size + cluster * 8192 - 1) // (cluster * 8192)
        l1 = bytearray(cluster)
        groups = sorted({ci // 8192 for ci in guests})
        l2s = {group: bytearray(cluster) for group in groups}
        next_cluster = 4 + len(groups)
        blocks = {}
        for i, group in enumerate(groups):
            struct.pack_into('>Q', l1, group * 8, (1 << 63) | ((4 + i) * cluster))
        for ci, data in sorted(guests.items()):
            physical = next_cluster * cluster
            next_cluster += 1
            if compressed:
                encoder = zlib.compressobj(wbits=-15)
                packed = encoder.compress(data) + encoder.flush()
                sectors = (len(packed) + 511) // 512
                assert sectors <= 128
                entry = (1 << 62) | ((sectors - 1) << 54) | physical
                blocks[physical] = packed + bytes(sectors * 512 - len(packed))
            else:
                entry = (1 << 63) | physical
                blocks[physical] = data
            group, slot = divmod(ci, 8192)
            struct.pack_into('>Q', l2s[group], slot * 8, entry)
        h = bytearray(cluster)
        h[:4] = b'QFI\xfb'
        struct.pack_into('>IQIIQIIQQIIQ', h, 4, version, 0, 0, 16, self.size, 0,
                         l1_count, cluster, 2 * cluster, 1, 0, 0)
        if version == 3:
            struct.pack_into('>QQQII', h, 72, 0, 0, 0, 4, 104)
        ref_table = bytearray(cluster)
        struct.pack_into('>Q', ref_table, 0, 3 * cluster)
        ref_block = bytearray(cluster)
        for i in range(next_cluster):
            struct.pack_into('>H', ref_block, i * 2, 1)
        with Path(path).open('xb') as stream:
            stream.truncate(next_cluster * cluster)
            for data in (h, l1, ref_table, ref_block, *l2s.values()):
                stream.write(data)
            for physical, data in blocks.items():
                stream.seek(physical)
                stream.write(data)
        return Path(path)


def entry(name, cluster=0, size=0, directory=False):
    row = bytearray(64)
    raw = name.encode('latin-1')
    assert 0 < len(raw) <= 42
    row[0], row[1] = len(raw), 16 if directory else 32
    row[2:2 + len(raw)] = raw
    struct.pack_into('<II', row, 44, cluster, size)
    return row


def xbox(save, *, fat32=False, multiple=False, stock=False):
    """Return guest sectors and useful offsets for adversarial test mutations."""
    start = 0xabe80000 if stock else 0x10000
    length = 0x9896b0 * 512 if stock else (36 << 20 if fat32 else 2 << 20)
    spc = 32 if stock else 1
    cluster = spc * 512
    guest = Guest(8 << 30 if stock else start + length)
    table = bytearray(512)
    if not stock:
        table[:16] = b'****PARTINFO****'
        table[48:80] = struct.pack('<16sIIII', b'XBOX DATA', 0x80000000, start // 512, length // 512, 0)
    guest.put(0, table)
    h = bytearray(4096)
    h[:4] = b'FATX'
    struct.pack_into('<III', h, 4, 0x12345678, spc, 1)
    guest.put(start, h)
    # Geometry spelled out in the fixture; assertions in tests cover known cases.
    capacity = length // cluster
    width = 2 if capacity < 65525 else 4
    fat_size = ((capacity + 1) * width + 4095) & ~4095
    data = start + 4096 + fat_size
    fat = bytearray(fat_size)
    eof = (1 << (width * 8)) - 1
    def link(number, following=eof):
        fat[number * width:(number + 1) * width] = following.to_bytes(width, 'little')
    def block(number, payload):
        assert len(payload) <= cluster
        guest.put(data + (number - 1) * cluster, payload + b'\xff' * (cluster - len(payload)))
    for number in (0, 1, 2, 3, 4, 6, 7, 9):
        link(number)
    block(1, entry('UDATA', 2, directory=True) + entry('unrelated'))
    block(2, entry('4156001e', 3, directory=True) + entry('other_title', 7, directory=True))
    block(7, b'')
    slot_name = 'campaign_' + 'x' * 33  # full 42-byte FATX name
    if cluster == 512:
        link(3, 9)
        block(3, b''.join(entry('metadata_' + str(i)) for i in range(8)))
        block(9, entry(slot_name, 4, directory=True) + (entry('second', 6, directory=True) if multiple else b''))
    else:
        block(3, entry(slot_name, 4, directory=True) + (entry('second', 6, directory=True) if multiple else b''))
    count = (len(save) + cluster - 1) // cluster
    chain = [100 + 3 * i for i in range(count)]  # deliberately noncontiguous
    for i, number in enumerate(chain):
        link(number, chain[i + 1] if i + 1 < count else eof)
        block(number, save[i * cluster:(i + 1) * cluster])
    block(4, entry('save.dat', chain[0], len(save)))
    if multiple:
        # Distinct allocated chains; never manufacture a filesystem cross-link.
        second_chain = [1000 + 3 * i for i in range(count)]
        for i, number in enumerate(second_chain):
            link(number, second_chain[i + 1] if i + 1 < count else eof)
            block(number, save[i * cluster:(i + 1) * cluster])
        block(6, entry('SAVE.DAT', second_chain[0], len(save)))
    guest.put(start + 4096, fat)
    return guest, dict(start=start, length=length, width=width, fat=start + 4096, data=data,
                       chain=chain, slot=data + 3 * cluster, title=data + 2 * cluster,
                       title_tail=data + 8 * cluster, cluster=cluster,
                       campaign='E:/UDATA/4156001e/' + slot_name)
