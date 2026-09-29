"""XDVDFS reading, image format detection, SubFile, XBE certificate, .fb bundles (BUILDER_DESIGN.md 6.1)."""
import io
import struct
import tempfile
import zipfile
from pathlib import Path

import synth
from xml1build.prepare import PrepareError, fb, image, xbe

FILES = {'default.xbe': b'x' * 100, 'a/b/c.bin': bytes(range(256)) * 20, 'a/empty.dat': b'',
         'Z/Upper.TXT': b'hello', 'a/b/d.bin': b'\x01' * 5000}


def _expect(code, fn, *a):
    try:
        fn(*a)
    except PrepareError as e:
        assert e.code == code, (e.code, code, str(e))
        return e
    raise AssertionError(f'expected {code}')


def _read_all(img):
    return {e.path: img.read_file(e.path) for e in img.entries.values() if not e.is_dir}


def test_xiso_offset_0_chain_and_balanced():
    for tree in ('chain', 'balanced'):
        part = synth.xdvdfs(FILES, dirs=('emptydir',), tree=tree)
        with image.XdvdfsImage(io.BytesIO(part)) as img:
            assert img.format == 'xiso' and img.partition == 0
            assert _read_all(img) == FILES, tree
            assert img.get('emptydir').is_dir and img.get('A/B').is_dir     # case-insensitive lookup
            assert [e.path for e in img.files_under('a/b')] == ['a/b/c.bin', 'a/b/d.bin']
            assert img.get('z/upper.txt').path == 'Z/Upper.TXT'               # spelling kept


def test_directory_table_spanning_sectors():
    many = {f'dir/file_with_a_long_name_{i:03d}.bin': bytes([i]) * (i + 1) for i in range(120)}
    part = synth.xdvdfs(many)
    with image.XdvdfsImage(io.BytesIO(part)) as img:
        assert img.get('dir').size > 2 * image.SECTOR                       # the table spans 3+ sectors (0xFF pads)
        assert _read_all(img) == many


def test_redump_layout_virtual():
    part = synth.xdvdfs(FILES)
    with image.XdvdfsImage(synth.ZeroPrefixed(part, synth.XGD1)) as img:
        assert img.format == 'redump-xgd1' and img.partition == synth.XGD1
        assert _read_all(img) == FILES


def test_redump_layout_sparse_file():
    part = synth.xdvdfs(FILES)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'redump.iso'
        if not synth.write_sparse(p, part, synth.XGD1):
            print('    (skipped: no sparse files here; the virtual Redump test covers the offset logic)')
            return
        with image.open_image(p) as img:
            assert img.format == 'redump-xgd1'
            assert _read_all(img) == FILES


def test_subfile_window():
    raw = bytes(range(256)) * 4
    sf = image.SubFile(io.BytesIO(raw), 100, 50)
    assert sf.read(10) == raw[100:110] and sf.tell() == 10
    sf.seek(-5, io.SEEK_END)
    assert sf.read() == raw[145:150] and sf.read(3) == b''
    sf.seek(20)
    assert sf.read(1000) == raw[120:150]
    # zipfile works on a window inside a bigger file
    zb = synth.zip_bytes({'x/y.txt': b'data' * 100})
    blob = b'\xAA' * 777 + zb + b'\xBB' * 333
    with zipfile.ZipFile(image.SubFile(io.BytesIO(blob), 777, len(zb))) as z:
        assert z.read('x/y.txt') == b'data' * 100


def test_truncated_image():
    part = synth.xdvdfs({'big.bin': b'\x07' * 10000})
    _expect('E_ISO_READ', image.XdvdfsImage, io.BytesIO(part[:len(part) - 4096]))


def test_detection_errors():
    def img(b):
        return io.BytesIO(b)
    _expect('E_ISO_COMPRESSED', image.XdvdfsImage, img(b'CCIM' + bytes(0x20000)))
    _expect('E_ISO_COMPRESSED', image.XdvdfsImage, img(b'CISO' + bytes(0x20000)))
    _expect('E_ISO_COMPRESSED', image.XdvdfsImage, img(synth.zip_bytes({'game.iso': b'x'})))
    gc = bytearray(0x20000)
    gc[0:6] = b'GXLE52'
    struct.pack_into('>I', gc, 0x1C, 0xC2339F3D)
    e = _expect('E_ISO_NOT_XBOX', image.XdvdfsImage, img(bytes(gc)))
    assert e.detail['detected'] == 'gamecube'
    wii = bytearray(0x20000)
    struct.pack_into('>I', wii, 0x18, 0x5D1C9EA3)
    assert _expect('E_ISO_NOT_XBOX', image.XdvdfsImage, img(bytes(wii))).detail['detected'] == 'wii'
    for cnf, kind in ((b'BOOT2 = cdrom0:\\SLUS_209.99;1\r\n', 'ps2'), (b'BOOT = cdrom:\\SLUS_000.01;1\r\n', 'ps1'),
                      (None, 'iso9660')):
        e = _expect('E_ISO_NOT_XBOX', image.XdvdfsImage, img(_iso9660(cnf)))
        assert e.detail['detected'] == kind, (kind, e.detail)
    assert _expect('E_ISO_NOT_XBOX', image.XdvdfsImage, img(b'\x13' * 0x30000)).detail['detected'] == 'unknown'
    with tempfile.TemporaryDirectory() as td:
        _expect('E_ISO_FOLDER', image.open_image, td)
        _expect('E_ISO_NOT_FOUND', image.open_image, Path(td) / 'missing.iso')


def _iso9660(system_cnf):
    """a minimal ISO 9660 image: PVD at sector 16, root directory at sector 20, SYSTEM.CNF at sector 21."""
    b = bytearray(24 * 2048)
    pvd = bytearray(2048)
    pvd[0], pvd[1:6], pvd[6] = 1, b'CD001', 1
    root = bytearray(34)
    root[0] = 34
    struct.pack_into('<I', root, 2, 20)
    struct.pack_into('<I', root, 10, 2048)
    root[25], root[32], root[33] = 2, 1, 0
    pvd[156:190] = root
    b[16 * 2048:17 * 2048] = pvd
    d = bytearray(2048)
    pos = 0
    for name, lba, size, flags in ((b'\0', 20, 2048, 2), (b'\1', 20, 2048, 2)) + \
            (((b'SYSTEM.CNF;1', 21, len(system_cnf), 0),) if system_cnf else ((b'README.TXT;1', 21, 5, 0),)):
        ln = 33 + len(name) + (1 if len(name) % 2 == 0 else 0)
        d[pos] = ln
        struct.pack_into('<I', d, pos + 2, lba)
        struct.pack_into('<I', d, pos + 10, size)
        d[pos + 25], d[pos + 32] = flags, len(name)
        d[pos + 33:pos + 33 + len(name)] = name
        pos += ln
    b[20 * 2048:21 * 2048] = d
    content = system_cnf or b'hello'
    b[21 * 2048:21 * 2048 + len(content)] = content
    return bytes(b)


def test_xbe_certificate():
    info = xbe.parse(synth.xbe())
    assert info['title_id'] == 0x4156001E and info['title_id_hex'] == '0x4156001E'
    assert info['title'] == 'X-Men Legends' and info['version'] == 1 and info['region'] == 7
    assert info['publisher'] == 'AV' and info['alt_title_ids'] == []
    xbe.check_xml1(info)
    other = xbe.parse(synth.xbe(title_id=0x4D530004, title='Some Other Game', alt=(0x12345678,)))
    assert other['alt_title_ids'] == ['0x12345678']
    e = _expect('E_ISO_WRONG_GAME', xbe.check_xml1, other)
    assert e.detail == {'title_id': '0x4D530004', 'title': 'Some Other Game'}
    _expect('E_ISO_WRONG_GAME', xbe.parse, b'MZ' + bytes(0x400))
    bad = bytearray(synth.xbe())
    struct.pack_into('<I', bad, 0x118, 0x7FFF0000)                          # certificate outside the file
    _expect('E_ISO_WRONG_GAME', xbe.parse, bytes(bad))


def test_fb_bundle_roundtrip_and_order():
    recs = [('actors/0001.igb', 'actorskin', b'abc'), ('/Data/X.XML', 'xml', b''), ('on', 'combat_is', b'z' * 300)]
    data = fb.build(recs)
    assert list(fb.entries(data)) == recs
    try:
        list(fb.entries(data[:-1], 'cut'))
        raise AssertionError('a truncated bundle must fail')
    except fb.BundleError:
        pass
    rels = ['packages/generated/maps/mansion/dr_mag/dr_mag01.fb', 'packages/generated/maps/mansion/dr_mag2/mag_nyc1.fb',
            'packages/generated/maps/mansion/dr_mag.fb', 'packages/generated/maps/Mansion/z.fb']
    assert sorted(rels, key=fb.bundle_order_key) == [rels[3], rels[2], rels[1], rels[0]]
    assert sorted(rels) != sorted(rels, key=fb.bundle_order_key)            # '/' order differs: the rule matters
    assert fb.entry_name('/Data\\X.XML') == 'data/x.xml'
