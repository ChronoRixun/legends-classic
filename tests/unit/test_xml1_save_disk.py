"""Read-only disk/CLI acceptance with invented raw and QCOW2 FATX images."""
import os
from pathlib import Path
import random
import struct
import tempfile
import zlib
import io

from xml1build.save_import import disk, source
from test_xml1_save_import import save, fixture, refused, file_hashes
from save_import_disk_fixture import xbox, Guest, entry


def test_disk_raw_qcow2_fatx16_fatx32_fragmented_and_long_names():
    raw, _ = save()
    with tempfile.TemporaryDirectory() as tmp:
        for fat32 in (False, True):
            guest, offsets = xbox(raw, fat32=fat32)
            assert offsets['width'] == (4 if fat32 else 2)
            assert offsets['data'] == (0x5a000 if fat32 else 0x14000)
            for kind in ('raw', 'qcow2'):
                path = getattr(guest, 'raw' if kind == 'raw' else 'qcow')(Path(tmp) / f'{kind}-{fat32}.img')
                before = source.digest(path.read_bytes())
                candidates, loaded = disk.inspect_image(path)
                assert loaded.payload == raw[24:]
                assert loaded.sha256 == source.digest(raw)
                assert loaded.signature_status == 'unavailable'
                assert loaded.image_format == kind and loaded.partition_layout == 'PARTINFO'
                assert candidates[0]['campaign'] == offsets['campaign']
                assert len(candidates[0]['campaign'].rsplit('/', 1)[1]) == 42
                loaded.recheck()
                assert source.digest(path.read_bytes()) == before
                assert sorted(p.name for p in Path(tmp).iterdir()) == sorted(f'{k}-{f}.img' for f in (False, True) for k in ('raw', 'qcow2') if (Path(tmp) / f'{k}-{f}.img').exists())


def test_disk_qcow_versions_compression_and_stock_without_partition_table():
    raw, _ = save()
    with tempfile.TemporaryDirectory() as tmp:
        for stock, version, compressed in ((False, 2, False), (False, 3, True), (True, 3, False), (True, 2, True)):
            guest, _ = xbox(raw, stock=stock)
            path = guest.qcow(Path(tmp) / f'{stock}-{version}-{compressed}.qcow2', version=version, compressed=compressed)
            _, loaded = disk.inspect_image(path)
            assert loaded.payload == raw[24:]
            assert loaded.partition_layout == ('retail-fixed' if stock else 'PARTINFO')
            loaded.recheck()


def test_disk_multiple_campaigns_require_explicit_selection():
    raw, _ = save()
    with tempfile.TemporaryDirectory() as tmp:
        guest, offsets = xbox(raw, multiple=True)
        path = guest.qcow(Path(tmp) / 'multiple.qcow2')
        rows, loaded = disk.inspect_image(path, discover_only=True)
        assert len(rows) == 2 and loaded is None
        refused(lambda: source.read_source(path), 'MULTIPLE')
        chosen = source.read_source(path, campaign=offsets['campaign'])
        assert chosen.campaign == offsets['campaign']
        chosen.recheck()
        refused(lambda: source.read_source(path, campaign='E:/UDATA/4156001e/../other'), 'INPUT')
        refused(lambda: source.read_source(tmp, campaign=offsets['campaign']), 'INPUT')


def test_disk_malformed_partitions_superblocks_directory_and_chains_refuse():
    raw, _ = save()
    mutations = [
        ('out-part', lambda g, p: g.put(72, struct.pack('<I', 0xffffffff))),
        ('overlap', lambda g, p: g.put(80, struct.pack('<16sIIII', b'XBOX SHELL', 0x80000000, p['start'] // 512, 8, 0))),
        ('cluster-size', lambda g, p: g.put(p['start'] + 8, struct.pack('<I', 3))),
        ('root-oob', lambda g, p: g.put(p['start'] + 12, struct.pack('<I', 0xffff))),
        ('name-length', lambda g, p: g.put(p['slot'], bytes((43,)))),
        ('name-path', lambda g, p: g.put(p['slot'] + 2, b'../x.dat')),
        ('duplicate', lambda g, p: g.put(p['slot'] + 64, entry('SAVE.DAT', 999, len(raw)))),
        ('oversize', lambda g, p: g.put(p['slot'] + 48, struct.pack('<I', source.CAPACITY + 25))),
        ('free-chain', lambda g, p: g.put(p['fat'] + 100 * 2, b'\0\0')),
        ('bad-chain', lambda g, p: g.put(p['fat'] + 100 * 2, b'\xf7\xff')),
        ('reserved-chain', lambda g, p: g.put(p['fat'] + 100 * 2, b'\xf0\xff')),
        ('oob-chain', lambda g, p: g.put(p['fat'] + 100 * 2, b'\x00\x40')),
        ('cycle', lambda g, p: g.put(p['fat'] + 100 * 2, struct.pack('<H', 100))),
        ('short-chain', lambda g, p: g.put(p['fat'] + 100 * 2, b'\xff\xff')),
        ('long-chain', lambda g, p: g.put(p['fat'] + p['chain'][-1] * 2, struct.pack('<H', 100))),
        ('dir-cycle', lambda g, p: g.put(p['fat'] + 9 * 2, struct.pack('<H', 3))),
        ('dir-crosslink', lambda g, p: g.put(p['title_tail'] + 64, entry('twin', 4, directory=True))),
        ('file-dir-crosslink', lambda g, p: g.put(p['slot'] + 44, struct.pack('<I', 3))),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        for name, mutate in mutations:
            guest, offsets = xbox(raw)
            mutate(guest, offsets)
            path = guest.qcow(Path(tmp) / (name + '.qcow2'))
            before = source.digest(path.read_bytes())
            refused(lambda: source.read_source(path), 'DISK_DAMAGED')
            assert source.digest(path.read_bytes()) == before


def test_disk_missing_title_tdata_unknown_and_encrypted_refuse_clearly():
    raw, _ = save()
    with tempfile.TemporaryDirectory() as tmp:
        guest, p = xbox(raw)
        guest.put(p['data'], entry('TDATA', 2, directory=True) + b'\xff' * 64)
        refused(lambda: source.read_source(guest.qcow(Path(tmp) / 'tdata.qcow2')), 'INPUT')
        guest, p = xbox(raw)
        guest.put(p['data'] + p['cluster'] + 2, b'415600ff')
        refused(lambda: source.read_source(guest.qcow(Path(tmp) / 'other-title.qcow2')), 'INPUT')
        path = Path(tmp) / 'unknown.img'
        path.write_bytes(b'unknown' * 100)
        refused(lambda: source.read_source(path), 'DISK_VERSION')
        for name, offset, value in (('crypt', 32, struct.pack('>I', 1)), ('backing', 8, struct.pack('>Q', 128)),
                                    ('dirty', 72, struct.pack('>Q', 1)), ('extended-l2', 72, struct.pack('>Q', 16)),
                                    ('version', 4, struct.pack('>I', 9)), ('snapshot', 60, struct.pack('>I', 1))):
            guest, _ = xbox(raw)
            path = guest.qcow(Path(tmp) / (name + '.qcow2'))
            with path.open('r+b') as stream:
                stream.seek(offset); stream.write(value)
            refused(lambda: source.read_source(path), 'DISK_VERSION')


def test_disk_qcow_bounds_reserved_bits_and_truncation_controls():
    raw, _ = save()
    with tempfile.TemporaryDirectory() as tmp:
        for name, offset, value in (
            ('bits', 20, struct.pack('>I', 63)),
            ('l1-count', 36, struct.pack('>I', 0xffffffff)),
            ('l1-oob', 40, struct.pack('>Q', 0xffffffffffff0000)),
            ('l1-overlap', 40, struct.pack('>Q', 0)),
            ('l1-misaligned', 65536, struct.pack('>Q', 0x40200)),
            ('l1-reserved', 65536, struct.pack('>Q', 1 << 62)),
            ('data-overlap', 4 * 65536, struct.pack('>Q', (1 << 63) | 65536)),
            ('data-refcount-overlap', 4 * 65536, struct.pack('>Q', (1 << 63) | (3 * 65536))),
            ('refcount-oob', 2 * 65536, struct.pack('>Q', 0x10000000000)),
            ('data-oob', 4 * 65536, struct.pack('>Q', (1 << 63) | 0x10000000000)),
            ('l2-reserved', 4 * 65536, struct.pack('>Q', 2)),
        ):
            guest, _ = xbox(raw)
            path = guest.qcow(Path(tmp) / (name + '.qcow2'))
            with path.open('r+b') as stream:
                stream.seek(offset); stream.write(value)
            refused(lambda: source.read_source(path), 'DISK_DAMAGED')
        guest, _ = xbox(raw)
        full = guest.qcow(Path(tmp) / 'full.qcow2').read_bytes()
        for length in (4, 24, 71, 103, 65536, len(full) - 1):
            path = Path(tmp) / f'truncated-{length}.qcow2'
            path.write_bytes(full[:length])
            refused(lambda: source.read_source(path), 'DISK_DAMAGED')


def test_disk_guest_cross_cluster_reads_sparse_zero_and_budget():
    with tempfile.TemporaryDirectory() as tmp:
        guest = Guest(8 << 30)
        guest.put(65536 - 3, b'abcdef')
        guest.put(6 << 30, b'far')  # different L1/L2 mapping table
        path = guest.qcow(Path(tmp) / 'sparse.qcow2')
        with disk.open_image(path) as (stream, st):
            reader = disk.Disk(stream, st.st_size)
            assert reader.read(65536 - 5, 10) == b'\0\0abcdef\0\0'
            assert reader.read(4 << 30, 512) == bytes(512)
            assert reader.read(6 << 30, 3) == b'far'
            refused(lambda: reader.read(reader.size - 1, 2), 'DISK_DAMAGED')
            refused(lambda: reader.read(0, disk.MAX_READ + 1), 'DISK_DAMAGED')
            reader.io = disk.MAX_IO
            refused(lambda: reader.at(0, 1), 'DISK_VERSION')


def test_disk_source_recheck_detects_changed_image_and_selected_content():
    raw, _ = save()
    with tempfile.TemporaryDirectory() as tmp:
        guest, p = xbox(raw)
        path = guest.raw(Path(tmp) / 'changed.raw')
        loaded = source.read_source(path)
        before = path.stat()
        with path.open('r+b') as stream:
            stream.seek(p['data'] + (100 - 1) * 512 + 5)
            stream.write(b'Q')  # opaque Xbox signature; preserve length and mtime
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        refused(loaded.recheck, 'CHANGED')
        with path.open('r+b') as stream:
            stream.seek(0); stream.write(bytes(512))
        refused(loaded.recheck, 'CHANGED')


def test_disk_windows_read_handle_refuses_live_writer_and_blocks_writes():
    if os.name != 'nt':
        from unittest import SkipTest
        raise SkipTest('Windows file sharing contract.')
    raw, _ = save()
    with tempfile.TemporaryDirectory() as tmp:
        guest, _ = xbox(raw)
        path = guest.qcow(Path(tmp) / 'sharing.qcow2')
        before = source.digest(path.read_bytes())
        with path.open('r+b'):
            refused(lambda: source.read_source(path), 'BUSY')
        with disk.open_image(path):
            try:
                with path.open('r+b'):
                    pass
            except PermissionError:
                pass
            else:
                raise AssertionError('A writer opened the image during inspection.')
        assert source.digest(path.read_bytes()) == before


def test_disk_compressed_damage_and_fatx32_bad_cluster_controls():
    raw, _ = save()
    with tempfile.TemporaryDirectory() as tmp:
        for number, bad in enumerate((b'\xff' * 20, b'oversized')):
            guest, _ = xbox(raw)
            path = guest.qcow(Path(tmp) / f'compressed-bad-{number}.qcow2', compressed=True)
            with path.open('r+b') as stream:
                stream.seek(4 * 65536)
                pointer = int.from_bytes(stream.read(8), 'big') & ((1 << 54) - 1)
                if bad == b'oversized':
                    encoder = zlib.compressobj(wbits=-15)
                    bad = encoder.compress(bytes(65537)) + encoder.flush()
                stream.seek(pointer); stream.write(bad)
            refused(lambda: source.read_source(path), 'DISK_DAMAGED')
        for value in (0, 0xfffffff0, 0xfffffff7, 0x7fffffff, 100):
            guest, p = xbox(raw, fat32=True)
            guest.put(p['fat'] + 100 * 4, struct.pack('<I', value))
            path = guest.qcow(Path(tmp) / f'fat32-bad-{value}.qcow2')
            refused(lambda: source.read_source(path), 'DISK_DAMAGED')


def test_disk_deterministic_structure_mutations_never_escape_parser_refusals():
    from xml1build.save_import.errors import ImportRefusal
    raw, _ = save()
    with tempfile.TemporaryDirectory() as tmp:
        guest, p = xbox(raw)
        for path in (guest.raw(Path(tmp) / 'fuzz.raw'), guest.qcow(Path(tmp) / 'fuzz.qcow2')):
            original = path.read_bytes()
            rng = random.Random(2156001)
            offsets = ([p['start'], p['fat'], p['slot'], p['title_tail']] if path.suffix == '.raw'
                       else [65536, 2 * 65536, 4 * 65536])
            offsets.append(0)
            for trial in range(150):
                data = bytearray(original)
                offset = rng.choice(offsets) + rng.randrange(64)
                data[offset:offset + 4] = rng.getrandbits(32).to_bytes(4, 'little')
                try:
                    reader = disk.Disk(io.BytesIO(data), len(data))
                    start, size, _ = disk.e_partition(reader)
                    fs = disk.Fatx(reader, start, size)
                    for name, row in fs.campaigns():
                        source.envelope(fs.file(name, row))
                except ImportRefusal:
                    pass


def test_disk_cli_inspect_and_dry_preview_end_to_end_without_source_writes():
    from test_builder_cli import run, check_stream
    with tempfile.TemporaryDirectory() as tmp:
        build, src, dest, _, _ = fixture(tmp)
        raw = (src / 'save.dat').read_bytes()
        guest, p = xbox(raw, fat32=True)
        image = guest.qcow(Path(tmp) / 'invented-hdd.qcow2', compressed=True)
        before = file_hashes(Path(tmp))
        code, events, _ = run(['import-xml1-save', str(image), '--inspect-source', '--events', 'jsonl'])
        check_stream(events)
        assert code == 0, events
        result = events[-1]
        assert result['capabilities']['hdd_images'] and not result['capabilities']['player_install']
        assert result['source_report']['source_sha256'] == source.digest(raw)
        assert result['source_report']['heroes'][0]['level'] == 5
        args = ['import-xml1-save', str(image), '--build', str(build), '--save-dir', str(dest),
                '--slot', '0', '--allow-inferred', '--events', 'jsonl']
        code, events, _ = run(args + ['--dry-run'])
        check_stream(events)
        assert code == 0, events
        result = events[-1]
        assert result['dry_run'] and result['imported'] is False
        report = result['import_report']
        assert report['checkpoint'] == 'Invented checkpoint'
        assert report['source_container']['campaign'] == p['campaign']
        code, events, _ = run(args + ['--preview-token', report['preview_token']])
        assert code == 2 and any(e.get('code') == 'E_XML1_UNVALIDATED' for e in events), events
        assert file_hashes(Path(tmp)) == before


def test_disk_cli_multiple_selection_and_refusal_framing():
    from test_builder_cli import run, check_stream
    raw, _ = save()
    with tempfile.TemporaryDirectory() as tmp:
        guest, p = xbox(raw, multiple=True)
        image = guest.qcow(Path(tmp) / 'multi.qcow2')
        args = ['import-xml1-save', str(image), '--inspect-source', '--events', 'jsonl']
        code, events, _ = run(args)
        assert code == 0 and events[-1]['source_report'] is None
        assert len(events[-1]['candidates']) == 2
        code, events, _ = run(args + ['--campaign', p['campaign']])
        assert code == 0 and events[-1]['source_report']['progress']['mission_id'] == 7
        bad = Path(tmp) / 'bad.img'; bad.write_bytes(b'QFI\xfb')
        code, events, _ = run(['import-xml1-save', str(bad), '--inspect-source', '--events', 'jsonl'])
        check_stream(events)
        assert code == 2 and events[-2]['code'] == 'E_XML1_DISK_DAMAGED', events
