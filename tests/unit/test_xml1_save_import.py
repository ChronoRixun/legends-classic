"""Invented Xbox wire saves -> real LC encoder / Python native W2 loader.

These fixtures are not derived from player saves and establish no retail
checkpoint safety, signature authenticity or real-game acceptance.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import tempfile
from unittest.mock import patch
import xml.etree.ElementTree as ET

import xmlb
from lcsave import binds, catalogue, container, convert, keys, layout as L, lcfiles, oldsave, typed_registry
from xml1build.save_import import ImportRefusal
from xml1build.save_import import identities, mapper, progress, retail, source, tables, transaction

from test_lcsave import make_build, _xmlb

NAMES = ['hero_a', 'hero_b'] + [f'hero_{i}' for i in range(2, 16)]


def refused(fn, code):
    try:
        fn()
    except ImportRefusal as e:
        assert e.code == 'E_XML1_' + code, (e.code, e.detail)
        return e
    raise AssertionError('Expected ' + code)


def marker(text, fill=b'*'):
    raw = text.encode('ascii') + b'\0'
    assert len(raw) <= 50
    return b'\n' + raw + fill * (50 - len(raw)) + b'\n'


def char(*, level=1, xp=0, seat=-1, talents=(), equipment=(), flags=b'\0\0'):
    raw = bytearray(44)
    struct.pack_into('<ffiI', raw, 0, 12.0, 9.0, seat, 1)
    struct.pack_into('<I', raw, 16, xp)
    raw[20:27] = bytes((level, level, 0, 3, 2, 4, 5))
    raw[39:42] = bytes((3, 4, 0x21))
    raw[42:44] = flags
    out = bytes(raw) + bytes((len(talents),))
    for ident, rank, pending, bonus, limit, baseline in talents:
        packed = rank | (pending << 4) | (bonus << 8) | (limit << 12) | (baseline << 16) | (0xa << 20)
        out += bytes((ident,)) + packed.to_bytes(3, 'little')
    return out + bytes((len(equipment),)) + bytes(equipment)


def save(*, zones=0, talents=True, side=0, slack=0, mission_id=7):
    parts, positions = [], {}
    def add(name, raw):
        positions[name] = sum(map(len, parts))
        parts.append(raw)
    add('begin', marker('[SAVEGAMEBEGIN: invented]'))
    add('play_time', struct.pack('<f', 99.5))
    add('game', bytes(0x88))
    add('retained_game', bytes(0x88))
    add('side', bytes(0x30c) + struct.pack('<I', side))
    for name, raw in (('courses', bytes(200)), ('grades', bytes(8)), ('credits', bytes(2))):
        add(name + '_marker', marker(retail.MARKERS[name]))
        add(name, raw)
    for i in range(16):
        ts = [(0, 2, 0, 0, 3, 1), (17, 4, 0, 0, 2, 1)] if i == 0 and talents else []
        add('hero' + str(i), char(level=5 if i == 0 else 1, xp=450 if i == 0 else 0,
                                  seat=0 if i == 0 else -1, talents=ts, equipment=[12] if i == 0 else []))
    add('unlocked_marker', marker(retail.MARKERS['unlocked']))
    add('unlocked', bytes((1, 2)) + bytes(254) + struct.pack('<I', 2))
    add('restore_marker', marker(retail.MARKERS['restore']))
    add('restore_valid', b'\0')
    for i in range(17):
        add('restore' + str(i), char())
    inv = bytearray(0x289)
    inv[24] = 2       # two carried copies, in addition to one equipped
    inv[28] = 3       # three health packs, through dedicated counter only
    inv[0x140 + 24] = 99  # rollback snapshot, never stash
    struct.pack_into('<II', inv, 0x281, 12345, 90000)
    add('inventory', bytes(inv))
    add('review', bytes(0x48))
    add('strings_marker', marker(retail.MARKERS['strings']))
    add('strings', bytes(0x5808))
    add('zones_marker', marker(retail.MARKERS['zones']))
    add('zone_count', struct.pack('<I', zones))
    for i in range(zones):
        add('zone' + str(i), bytes(0x39bc))
    add('mission_marker', marker(retail.MARKERS['mission']))
    snap = bytearray(0x184)
    snap[:9] = b'zone/x/y\0'
    snap[0xa4:0xab] = b'hero_a\0'
    snap[0xc4:0xcb] = b'hero_b\0'
    struct.pack_into('<HBB', snap, 0x126, 3, 3, 0)  # enabled+complete -> target complete bit 0
    struct.pack_into('<HBB', snap, 0x12a, 1, 8, 0)  # hidden -> target hidden bit 1
    snap[0x180] = mission_id
    add('mission', bytes(snap))
    add('profile', bytes(0x194))
    variables = bytearray(0x300)
    variables[:12] = b'counter\0' + bytes(4)
    variables[12:16] = struct.pack('>I', 0xffffffff)
    variables[32*16:32*16+12] = b'global\0' + bytes(5)
    variables[32*16+12:33*16] = struct.pack('>I', 0x12345678)
    add('variables', bytes(variables))
    add('end', marker('[SAVEGAMEEND: invented]'))
    add('slack', b'\xcc' * slack)
    payload = b''.join(parts)
    return struct.pack('<I', len(payload)) + bytes(20) + payload, positions


def fixture(folder):
    folder = Path(folder)
    build = Path(make_build(str(folder / 'build')))
    hs = ET.Element('characters')
    for name in NAMES:
        e = ET.SubElement(hs, 'stats', name=name, skin='0101', skin_60s='02', skin_future='03')
        ET.SubElement(e, 'talent', name='sh_fight', level='1')
    _xmlb(str(build / 'Data/herostat.engb'), hs)
    (build / 'Scripts').mkdir()
    (build / 'Scripts/invented.py').write_text('value = 0\n', encoding='ascii', newline='\n')
    (build / '_build').mkdir()
    (build / '_build/report.json').write_text(json.dumps(dict(build=dict(save_layout='w2', loot='xml1', xp_curve='xml1'))), encoding='ascii')
    (build / 'xml2-fix.ini').write_text('[Limits]\nSaveLayout=w2\nEntityCapacity=1\nItemEnhancements=4096\n[Save]\nFormat=lc\n[Game]\nXml1Economy=1\nXPCurve=xml1\nLevelStatPoints=xml1\nLevelSkillPoints=xml1\n', encoding='ascii', newline='\n')
    b = binds.Binds(str(build))
    cat = catalogue.Catalogue()
    cat.extend(catalogue.tables_from_hashes(b.hash_tables(include_conversation_digest=False)), 13)
    files, problems = lcfiles.bind_files(str(build), cat)
    assert not problems, problems
    files['Data/lcsave/catalogue.lcc'] = lcfiles.write_catalogue_lcc(cat, lcfiles.key_text_index(b), 13)
    for name, data in files.items():
        p = build / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    fp, script_count = typed_registry.scripts_fingerprint(str(build / 'Scripts'))
    (build / 'Data/lcsave/typed-entity-ids.txt').write_text(
        f'{typed_registry.REGISTRY_FORMAT} {typed_registry.REGISTRY_VERSION}\nfingerprint {fp}\nfiles {script_count}\n', encoding='ascii', newline='\n')
    economy = 'belt_x 1 1 40 1 none 0 12\nglove_x 1 1 40 1 none 0 13\narmor_x 1 1 40 1 none 0 15\n'
    (build / 'Data/x1economy.txt').write_text('x1economy 1\ncount 3\nsha256 ' + hashlib.sha256(economy.encode()).hexdigest() + '\n' + economy, encoding='ascii', newline='\n')
    profile = dict(id='invented-retail-profile', title_id=source.TITLE_ID, xbe_sha256='0' * 64,
                   hero_names=NAMES, stat_points_confirmed=False)
    hero_rows = {n: dict(target=n, skins={'0': 'skin'}, powers=[dict(button=0, name='power1', flags=1)]) for n in NAMES}
    talent_ledger = {name: {'0': ['shared', 'sh_fight']} for name in NAMES}
    talent_ledger['hero_a']['17'] = ['hero_a', 'a_one']
    mapping = tables.bind_table(build, profile, heroes=hero_rows, talents=talent_ledger,
        xp_thresholds=[0, 100, 200, 300, 400, 500, 600, 700], items=[
            dict(source_index=12, target='belt_x', route='equipment', maximum=255),
            dict(source_index=14, target='potion_x', route='health', maximum=10, target_maximum=10)],
        quantity_policy='excludes_equipped', variables=[
            dict(family='mission', name='counter', scope='invented', kind='pack', target='x1v01', first_bit=1, width=5, source_signed=True, signed=True),
            dict(family='game', name='global', scope='invented', kind='pack', target='x1g01', first_bit=1, width=32)],
        checkpoints=[dict(name='Invented checkpoint', source_zone='zone/x/y', mission_id=7, target_zone='zone/x/y',
            act=1, scope='invented', allowed_party=NAMES, predicates=[], seat_poses=[[float(i), 0., 0., 0., 0., 0.] for i in range(4)],
            anchor_pose=[0.] * 6, objectives={'0': ['act_x', 'obj_a'], '1': ['act_x', 'obj_b']},
            xtraction=[['zone/x/y', 'centre_a']])])
    path = build / tables.TABLE_REL
    path.write_text(json.dumps(mapping, indent=2), encoding='ascii', newline='\n')
    src = folder / 'source'
    src.mkdir()
    raw, pos = save()
    (src / 'save.dat').write_bytes(raw)
    dest = folder / 'SaveLC'
    dest.mkdir()
    return build, src, dest, mapping, pos


def convert_fixture(folder, **kwargs):
    build, src, dest, mapping, pos = fixture(folder)
    original = source.read_source(src)
    table = tables.ImportTable(build)
    ir = retail.decode(original.payload, hero_names=table.source['hero_names'])
    output, report, merged = mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True, now=0, serial=42, **kwargs)
    return build, src, dest, table, original, ir, output, report, merged


def test_xml1_envelope_every_truncation_and_signature():
    raw, _ = save()
    payload, status = source.envelope(raw)
    assert status == 'unavailable' and len(payload) == len(raw) - 24
    # Every possible file truncation, plus independent framing/size controls.
    for n in range(len(raw)):
        refused(lambda n=n: source.envelope(raw[:n]), 'DAMAGED')
    for bad in (raw + b'x', struct.pack('<I', source.CAPACITY + 1) + bytes(20), raw[:3]):
        refused(lambda bad=bad: source.envelope(bad), 'DAMAGED')
    assert source.envelope(raw, lambda p, s: True)[1] == 'verified'
    assert source.envelope(raw, lambda p, s: None)[1] == 'unavailable'
    refused(lambda: source.envelope(raw, lambda p, s: False), 'DAMAGED')


def test_xml1_retail_offsets_records_padding_and_endian():
    raw, pos = save(zones=7, slack=17)
    ir = retail.decode(source.envelope(raw)[0])
    assert pos['courses_marker'] == 0x458 and pos['courses'] == 0x48c
    assert pos['grades_marker'] == 0x554 and pos['grades'] == 0x588
    assert pos['credits_marker'] == 0x590 and pos['credits'] == 0x5c4 and pos['hero0'] == 0x5c6
    assert len(ir['heroes']) == 16 and len(ir['restore']) == 17 and len(ir['zones']) == 7
    assert ir['heroes'][0]['talents'][1] == dict(native_id=17, rank=4, pending=0, bonus=0, limit=2, baseline=1, padding=10)
    assert ir['heroes'][0]['equipped'] == [12] and ir['description'] == 'invented'
    assert ir['variables']['mission'] == [dict(name='counter', value=0xffffffff)]
    assert ir['variables']['game'] == [dict(name='global', value=0x12345678)]
    assert ir['tech_bits'] == 12345 and ir['snapshot_tech_bits'] == 90000
    assert ir['slack'] == b'\xcc' * 17


def test_xml1_retail_exact_objective_sign_arithmetic():
    for word, want in ((0, 0), (0x7ff, 2047), (0x800, 2048), (0xfff, 4095),
                       (0x8000, -4096), (0x87ff, -2049), (0x8fff, -1), (0xffff, -1), (0x7001, 1)):
        assert retail.objective_counter(word) == want


def test_xml1_retail_boundary_damage_never_scans_for_markers():
    raw, pos = save()
    payload = raw[24:]
    cuts = sorted({p for p in pos.values() if p < len(payload)} | {p+1 for p in pos.values() if p < len(payload)})
    for n in cuts:
        refused(lambda n=n: retail.decode(payload[:n]), 'DAMAGED' if n else 'VERSION')
    for field, offset, value in (('talents', pos['hero0'] + 44, 255), ('equipped', pos['hero0'] + 45 + 8, 4),
                                 ('zones', pos['zone_count'], 8), ('restore validity', pos['restore_valid'], 2)):
        bad = bytearray(payload)
        bad[offset] = value
        refused(lambda bad=bad: retail.decode(bytes(bad)), 'DAMAGED')
    bad = bytearray(payload)
    bad[pos['hero0'] + 45 + 4] = bad[pos['hero0'] + 45]  # duplicate talent key
    refused(lambda: retail.decode(bytes(bad)), 'DAMAGED')
    bad = bytearray(payload)
    bad[pos['courses_marker']] = 0
    refused(lambda: retail.decode(bytes(bad)), 'DAMAGED')
    bad = bytearray(payload)
    bad[pos['end'] + 18] = ord('z')
    refused(lambda: retail.decode(bytes(bad)), 'DAMAGED')


def test_xml1_recomp_versions_are_explicit_refusals():
    raw, pos = save()
    for version in (*range(1, 7), 65535):
        off = pos['hero0']
        modified = raw[24:24+off] + b'XML1CHR\0' + struct.pack('<HH', version, 48) + raw[24+off:]
        e = refused(lambda: retail.decode(modified), 'RECOMP_VERSION')
        assert e.detail['version'] == version and e.detail['offset'] == 0x5c6
    for magic, field in ((b'XML1PRG\0', 'variables'), (b'XML1DIF\0', 'end'), (b'XML1STSH', 'inventory')):
        off = pos[field]
        modified = raw[24:24+off] + magic + b'\1\0' + raw[24+off:]
        refused(lambda: retail.decode(modified), 'RECOMP_VERSION')
    # Magic in bounded slack is NOT an extension: no arbitrary signature scan.
    ir = retail.decode(raw[24:] + b'XML1CHR\0\6\0')
    assert ir['slack'].startswith(b'XML1CHR')


def test_xml1_folder_selection_preservation_and_source_recheck():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        first = root / 'UDATA' / source.TITLE_ID / 'opaque-a'
        second = first.parent / 'opaque-b'
        first.mkdir(parents=True)
        second.mkdir()
        raw, _ = save()
        (first / 'save.dat').write_bytes(raw)
        before = source.digest((first / 'save.dat').read_bytes())
        s = source.read_source(root / 'UDATA')
        assert s.sha256 == before and s.path.parent == first
        (second / 'SAVE.DAT').write_bytes(raw)
        e = refused(lambda: source.read_source(root / 'UDATA'), 'MULTIPLE')
        assert len(e.detail['candidates']) == 2
        assert source.digest((first / 'save.dat').read_bytes()) == before
        (first / 'save.dat').write_bytes(raw + b'x')
        refused(s.recheck, 'CHANGED')
        other = root / 'UDATA' / '00000000'
        other.mkdir()
        refused(lambda: source.read_source(other), 'VERSION')
        tdata = root / 'TDATA'
        tdata.mkdir()
        refused(lambda: source.read_source(tdata), 'INPUT')
        for value in ('//server/share', '\\\\server\\share', 'https://invalid.test/save', 'file.dat:stream'):
            refused(lambda value=value: source.safe_path(value), 'INPUT')


def test_xml1_reparse_points_refuse_before_traversal():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        real = root / 'real'
        real.mkdir()
        (real / 'save.dat').write_bytes(save()[0])
        link = root / 'link'
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError:
            # Simulate the Windows reparse attribute without needing privileges.
            original = Path.lstat
            def reparse(self, *a, **kw):
                st = original(self, *a, **kw)
                if self == real:
                    class Fake:
                        st_mode = st.st_mode
                        st_file_attributes = 0x400
                    return Fake()
                return st
            with patch.object(Path, 'lstat', reparse):
                refused(lambda: source.campaigns(real), 'INPUT')
        else:
            refused(lambda: source.campaigns(link), 'INPUT')


def test_xml1_scoped_packing_signed_extremes_and_overlap():
    rows = [dict(family='mission', name='a', scope='x', kind='pack', target='x1v01', first_bit=32, width=1),
            dict(family='mission', name='b', scope='x', kind='pack', target='x1v01', first_bit=1, width=8, signed=True, source_signed=True),
            dict(family='game', name='a', scope='x', kind='pack', target='x1g01', width=32)]
    cells = {'mission': [dict(name='a', value=1), dict(name='b', value=0xffffff80)], 'game': [dict(name='a', value=0xffffffff)]}
    assert progress.pack_variables(cells, rows, 'x', lambda *a: None) == [dict(name='x1g01', value=0xffffffff), dict(name='x1v01', value=0x80000080)]
    for v in (0xffffff7f, 128):
        bad = copy.deepcopy(cells)
        bad['mission'][1]['value'] = v
        refused(lambda: progress.pack_variables(bad, rows, 'x', lambda *a: None), 'CAPACITY')
    bad = copy.deepcopy(rows)
    bad[1]['first_bit'] = 25
    refused(lambda: progress.pack_variables(cells, bad, 'x', lambda *a: None), 'BUILD')
    for width in (0, 33):
        bad = copy.deepcopy(rows)
        bad[2]['width'] = width
        refused(lambda: progress.pack_variables(cells, bad, 'x', lambda *a: None), 'BUILD')
    missing = []
    assert progress.pack_variables(cells, rows, 'other', lambda *a: missing.append(a)) == []
    assert len(missing) == 3


def test_xml1_real_lc_loader_roundtrip_and_copy_conservation():
    with tempfile.TemporaryDirectory() as d:
        build, src, dest, table, original, ir, raw, report, merged = convert_fixture(d)
        f = container.read_file(raw, L.KIND_CAMPAIGN)
        s = {t: v['data'] for t, v in f['sections'].items()}
        assert 'LGCY' not in s and 'KEYS' not in s and merged is None
        assert f['header']['campaign_serial'] == 42 and f['header']['save_sequence'] == 1
        assert s['META']['origin'] == 1 and s['META']['writer'] == 'XML1 save importer'
        assert s['ITEM']['tech_bits'] == 12345 and s['ITEM']['health_items'] == 3
        assert len(s['ITEM']['instances']) == 2  # NOT snapshot quantity 99, NOT 90000 snapshot bits
        assert len(s['HERO']['heroes'][0]['equipped']) == 1
        assert s['HERO']['heroes'][0]['experience'] == 450 and s['HERO']['heroes'][0]['ack_level'] == 5
        assert s['HERO']['heroes'][0]['traits'][0::4] == [12, 14, 16, 20]
        assert s['HERO']['heroes'][0]['trait_points'] == 12 and s['HERO']['heroes'][0]['skill_points'] == 4
        assert s['MISS']['snapshots'][0]['objectives'][0]['flags'] == 1
        assert s['MISS']['snapshots'][0]['objectives'][1]['flags'] == 2
        assert s['ZONE']['records'] == [] and s['ITEM']['world'] == [] and s['REST']['bank_valid'] == 0
        native, notes = convert.reverse_slot(raw, table.env, native=L.W2)
        native_bytes = oldsave.write_slot(native, L.W2)
        assert oldsave.write_slot(oldsave.read_slot(native_bytes, L.W2), L.W2) == native_bytes
        roundtrip = convert.old_stream_to_new(native_bytes, table.env, native=L.W2,
            campaign_serial=42, now=0, origin=1, writer='XML1 save importer', optional_features=f['header']['optional_features'])
        assert not roundtrip.refused, roundtrip.refused
        again, _ = convert.reverse_slot(roundtrip.file_bytes, table.env, native=L.W2)
        assert oldsave.write_slot(again, L.W2) == native_bytes
        assert report['signature_message'] == 'Xbox signature not checked' and not report['player_use_validated']
        assert report['approximated'] and report['skipped'] and report['imported']
        assert source.digest((src / 'save.dat').read_bytes()) == original.sha256
        assert list(dest.iterdir()) == []


def test_xml1_unknown_talents_pending_and_native_widths_refuse():
    with tempfile.TemporaryDirectory() as d:
        build, src, dest, table, original, ir, raw, report, merged = convert_fixture(d)
        def go(value):
            return mapper.map_campaign(value, original, table, slot=0, allow_inferred=True)
        modified = copy.deepcopy(ir)
        modified['heroes'][0]['talents'][0]['native_id'] = 99
        e = refused(lambda: go(modified), 'IDENTITY')
        assert e.detail['native_id'] == 99
        for field, value, code in (('pending', 1, 'CONTEXT'), ('limit', 4, 'CAPACITY'), ('baseline', 4, 'CAPACITY')):
            modified = copy.deepcopy(ir)
            modified['heroes'][0]['talents'][0][field] = value
            refused(lambda: go(modified), code)
        modified = copy.deepcopy(ir)
        modified['mission']['objectives'][0]['counter'] = 64
        refused(lambda: go(modified), 'CAPACITY')
        modified = copy.deepcopy(ir)
        modified['heroes'][0]['experience'] = 500
        refused(lambda: go(modified), 'DAMAGED')
        refused(lambda: mapper.map_campaign(ir, original, table, slot=0), 'INFERRED')


def test_xml1_checkpoints_and_side_mission_refuse_ambiguity():
    raw, _ = save(side=1)
    ir = retail.decode(raw[24:])
    refused(lambda: progress.checkpoint(ir, []), 'SIDE_MISSION')
    with tempfile.TemporaryDirectory() as d:
        _, _, _, table, _, ir, _, _, _ = convert_fixture(d)
        recipe = table.data['checkpoints'][0]
        refused(lambda: progress.checkpoint(ir, []), 'CONTEXT')
        refused(lambda: progress.checkpoint(ir, [recipe, recipe]), 'CONTEXT')
        bad = copy.deepcopy(recipe)
        bad['predicates'] = [dict(family='mission', name='missing', value=0)]
        refused(lambda: progress.checkpoint(ir, [bad]), 'CONTEXT')
        badir = copy.deepcopy(ir)
        badir['game'] = struct.pack('<f', 1.) + ir['game'][4:]
        refused(lambda: progress.checkpoint(badir, [recipe]), 'CONTEXT')


def test_xml1_table_hashes_active_settings_and_rechecks():
    with tempfile.TemporaryDirectory() as d:
        build, src, dest, mapping, pos = fixture(d)
        t = tables.ImportTable(build)
        t.recheck()
        data = build / 'Data/items.engb'
        old = data.read_bytes()
        data.write_bytes(old + b'x')
        refused(t.recheck, 'CHANGED')
        refused(lambda: tables.ImportTable(build), 'BUILD')
        data.write_bytes(old)
        ini = build / 'xml2-fix.ini'
        ini.write_text(ini.read_text().replace('Xml1Economy=1', 'Xml1Economy=0'), encoding='ascii')
        mapping['target_files'] = tables.build_files(build)
        (build / tables.TABLE_REL).write_text(json.dumps(mapping), encoding='ascii')
        refused(lambda: tables.ImportTable(build), 'BUILD')


def test_xml1_atomic_install_and_occupied_slot_preserve_bytes():
    with tempfile.TemporaryDirectory() as d:
        _, src, dest, table, original, ir, raw, report, _ = convert_fixture(d)
        unrelated = dest / 'saveslot1.lcsave'
        unrelated.write_bytes(b'player slot')
        profile = dest / 'profile.lcsave'
        profile.write_bytes(b'player profile')
        result = transaction.install_campaign(raw, report, dest, original, table)
        assert result['path'].read_bytes() == raw
        assert json.loads(result['report'].read_text())['source_sha256'] == original.sha256
        assert unrelated.read_bytes() == b'player slot' and profile.read_bytes() == b'player profile'
        assert (src / 'save.dat').read_bytes() == save()[0]
        refused(lambda: transaction.install_campaign(raw, report, dest, original, table), 'SLOT')
        assert not (dest / '.xml1-import.lock').exists()


def test_xml1_atomic_races_cancel_report_failure_and_source_change():
    for mode in ('occupied', 'source', 'cancel', 'report'):
        with tempfile.TemporaryDirectory() as d:
            _, src, dest, table, original, ir, raw, report, _ = convert_fixture(d)
            def hook():
                if mode == 'occupied':
                    (dest / 'saveslot0.lcsave').write_bytes(b'concurrent player save')
                elif mode == 'source':
                    (src / 'save.dat').write_bytes(b'changed')
            calls = []
            def cancel():
                calls.append(1)
                if mode == 'cancel' and len(calls) == 2:
                    raise RuntimeError('cancelled')
            actual = transaction._write_new
            def fail_report(path, data, on_created=lambda: None):
                if mode == 'report' and path.name == 'report.json':
                    raise OSError('invented disk full')
                actual(path, data, on_created)
            with patch.object(transaction, '_write_new', fail_report):
                try:
                    transaction.install_campaign(raw, report, dest, original, table, cancel=cancel, before_link=hook)
                except (ImportRefusal, RuntimeError, OSError):
                    pass
                else:
                    raise AssertionError('Expected injected failure')
            if mode == 'occupied':
                assert (dest / 'saveslot0.lcsave').read_bytes() == b'concurrent player save'
            else:
                assert not (dest / 'saveslot0.lcsave').exists()
            assert not list(dest.glob('*.tmp')) and not (dest / '.xml1-import.lock').exists()


def test_xml1_cli_jsonl_dry_run_and_acceptance_gate():
    from test_builder_cli import run, check_stream
    with tempfile.TemporaryDirectory() as d:
        build, src, dest, mapping, pos = fixture(d)
        before = {p.relative_to(Path(d)).as_posix(): source.digest(p.read_bytes()) for p in Path(d).rglob('*') if p.is_file()}
        argv = ['import-xml1-save', str(src), '--build', str(build), '--save-dir', str(dest), '--slot', '0',
                '--allow-inferred', '--events', 'jsonl']
        code, events, _ = run(argv + ['--dry-run'])
        check_stream(events)
        assert code == 0, events
        result = events[-1]
        assert result['dry_run'] and not result['imported']
        report = result['import_report']
        assert report['checkpoint'] == 'Invented checkpoint' and report['approximated']
        after = {p.relative_to(Path(d)).as_posix(): source.digest(p.read_bytes()) for p in Path(d).rglob('*') if p.is_file()}
        assert before == after
        code, events, _ = run(argv + ['--preview-token', report['preview_token']])
        check_stream(events)
        assert code == 2 and [e for e in events if e['ev'] == 'error'][-1]['code'] == 'E_XML1_UNVALIDATED'
        code, events, _ = run(argv + ['--preview-token', 'wrong'])
        assert code == 2 and [e for e in events if e['ev'] == 'error'][-1]['code'] == 'E_XML1_CHANGED'
        code, events, _ = run(argv + ['--dry-run', '--merge-unlocks'])
        assert code == 2 and [e for e in events if e['ev'] == 'error'][-1]['code'] == 'E_XML1_MERGE'
        code, events, _ = run(['info', 'unrelated-positional-value', '--events', 'jsonl'])
        assert code == 2 and [e for e in events if e['ev'] == 'error'][-1]['code'] == 'E_USAGE'
        (src / 'save.dat').write_bytes(save(side=1)[0])
        code, events, _ = run(argv + ['--dry-run'])
        assert code == 2 and [e for e in events if e['ev'] == 'error'][-1]['code'] == 'E_XML1_SIDE_MISSION'
        assert list(dest.iterdir()) == []


def make_profile(table):
    meta = mapper.defaults(container.SECTIONS['META'][0])
    meta.update(description='invented profile', writer='invented', mods=[])
    rows = [
        ('META', 1, 0, L.SECTION_REQUIRED, meta),
        ('PRFO', 1, 0, 0, dict(options=0x1234, player_name='invented player')),
        ('PRFP', 1, 0, 0, dict(highest_level=4, flags=1, characters=[table.resolve('STAT', 'hero_a')], review=[table.resolve('REVW', 'load', 'l1')])),
        ('PRFS', 1, 0, 0, dict(scores=[])),
        ('FUTR', 1, 0, L.SECTION_KEEP, b'invented opaque payload'),
    ]
    header = dict(writer_version=7, content_version=13, catalogue_revision=table.env.catalogue.revision,
                  campaign_serial=123, save_sequence=9)
    return container.write_file(L.KIND_PROFILE, rows, header)


def test_xml1_optional_profile_merge_is_monotonic_and_preserves_extensions():
    with tempfile.TemporaryDirectory() as d:
        build, src, dest, table, original, ir, raw, report, _ = convert_fixture(d)
        profile = make_profile(table)
        patch_data = dict(highest_level=3, flags=2, characters=[table.resolve('STAT', 'hero_b')],
                          review=[table.resolve('REVW', 'cin', 'c1')])
        merged = mapper.merge_profile(profile, patch_data, table.env)
        before, after = container.read_file(profile), container.read_file(merged)
        assert before['sections']['PRFO']['payload'] == after['sections']['PRFO']['payload']
        assert before['sections']['PRFS']['payload'] == after['sections']['PRFS']['payload']
        assert before['sections']['FUTR']['payload'] == after['sections']['FUTR']['payload']
        assert after['header']['campaign_serial'] == 123 and after['header']['save_sequence'] == 10
        p = after['sections']['PRFP']['data']
        assert p['highest_level'] == 4 and p['flags'] == 3
        assert set(p['characters']) == {table.resolve('STAT', 'hero_a'), table.resolve('STAT', 'hero_b')}
        assert len(p['review']) == 2
        profile_path = dest / 'profile.lcsave'
        profile_path.write_bytes(profile)
        # Campaign preview can carry current PC platform options without
        # modifying its source global profile; the merge remains explicit.
        _, _, no_merge = mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True, profile_bytes=profile)
        assert no_merge is None and profile_path.read_bytes() == profile
        table.data['profile_unlock_bits'] = [dict(confirmed=True, field='characters', offset=12, mask=4, target=['hero_b'])]
        mapped = copy.deepcopy(ir)
        mapped['profile'] = ir['profile'][:12] + bytes((4,)) + ir['profile'][13:]
        _, report, merge_bytes = mapper.map_campaign(mapped, original, table, slot=0, allow_inferred=True,
                                                    profile_bytes=profile, merge_unlocks=True)
        assert report['merge_unlocks'] and table.resolve('STAT', 'hero_b') in container.read_file(merge_bytes)['sections']['PRFP']['data']['characters']
        assert profile_path.read_bytes() == profile


def test_xml1_item_routes_and_hero_passive_aliases_use_names():
    r = ET.Element('inventory')
    for name, kind in (('MONEY1', 'money'), ('gear_a', 'equipment'), ('HEALTH_ITEM', 'item'), ('KEY1', 'item')):
        ET.SubElement(r, 'item', name=name, type=kind)
    rows = identities.item_rows(r, [dict(source=1, name='lc_x1_gear_a', flags=0x40)],
                               source_maxima={0: 255, 1: 20, 2: 10, 3: 5}, pack_limits={'health': 10, 'energy': 10})
    assert rows[1]['target'] == 'lc_x1_gear_a' and rows[1]['route'] == 'equipment'
    assert rows[2]['route'] == 'health' and rows[3]['route'] == 'key'
    class InventedBinds:
        hero_talent = {'hero_b': ['x1_hero_b_grappling', 'power_b'], 'hero_a': ['power_a', 'x1_hero_a_grappling']}
        shared_talent = ['flight', 'toughness']
    captured = {17: 'grappling', 8: 'flight', 23: 'power_a', 24: 'power_b'}
    ledgers = identities.talent_rows(captured, {'hero_a': ['grappling', 'flight', 'power_a'],
                                               'hero_b': ['grappling', 'flight', 'power_b']}, InventedBinds())
    assert ledgers['hero_a']['17'] == ['hero_a', 'x1_hero_a_grappling']
    assert ledgers['hero_b']['17'] == ['hero_b', 'x1_hero_b_grappling']
    assert ledgers['hero_a']['8'] == ['shared', 'flight']
    assert '24' not in ledgers['hero_a']
    refused(lambda: identities.named_talent(InventedBinds(), 'hero_a', 'unknown'), 'IDENTITY')


def test_xml1_inclusive_equipment_policy_and_all_resources_have_one_route():
    with tempfile.TemporaryDirectory() as d:
        _, _, _, table, original, ir, _, _, _ = convert_fixture(d)
        table.data['quantity_policy'] = 'includes_equipped'
        output, report, _ = mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True)
        s = container.read_file(output)['sections']
        assert len(s['ITEM']['data']['instances']) == 1
        assert len(s['HERO']['data']['heroes'][0]['equipped']) == 1
        assert s['ITEM']['data']['health_items'] == 3 and not s['ITEM']['data']['def_state']
        changed = copy.deepcopy(ir)
        changed['inventory'][12]['quantity'] = 0
        refused(lambda: mapper.map_campaign(changed, original, table, slot=0, allow_inferred=True), 'DAMAGED')


def test_xml1_invalid_tables_and_typed_handle_targets_refuse():
    with tempfile.TemporaryDirectory() as d:
        build, _, _, mapping, _ = fixture(d)
        path = build / tables.TABLE_REL
        for mutate in (
            lambda x: x.update(xp_thresholds=[0, 200, 100]),
            lambda x: x['talents']['hero_a'].update({'256': ['shared', 'sh_fight']}),
            lambda x: x['variables'][0].update(first_bit=32, width=2),
            lambda x: x['checkpoints'][0].update(anchor_pose=[0.] * 5),
            lambda x: x['items'][0].update(source_index=13),
        ):
            bad = copy.deepcopy(mapping)
            mutate(bad)
            path.write_text(json.dumps(bad), encoding='ascii')
            refused(lambda: tables.ImportTable(build), 'BUILD')
        registry = build / 'Data/lcsave/typed-entity-ids.txt'
        registry.write_text(registry.read_text() + 'key\tgame\tx1v01\n', encoding='ascii', newline='\n')
        mapping['target_files'] = tables.build_files(build)
        path.write_text(json.dumps(mapping), encoding='ascii')
        refused(lambda: tables.ImportTable(build), 'BUILD')


def refresh_bindings(build, mapping):
    cat = tables.installed_catalogue((build / 'Data/lcsave/catalogue.lcc').read_bytes())
    b = binds.Binds(str(build))
    cat.extend(catalogue.tables_from_hashes(b.hash_tables(include_conversation_digest=False)), 13)
    files, problems = lcfiles.bind_files(str(build), cat)
    assert not problems
    files['Data/lcsave/catalogue.lcc'] = lcfiles.write_catalogue_lcc(cat, lcfiles.key_text_index(b), 13)
    for name, value in files.items():
        (build / name).write_bytes(value)
    mapping['target_files'] = tables.build_files(build)
    (build / tables.TABLE_REL).write_text(json.dumps(mapping), encoding='ascii', newline='\n')


def test_xml1_reordered_target_roster_and_item_definitions_keep_identities():
    with tempfile.TemporaryDirectory() as d:
        build, src, dest, mapping, _ = fixture(d)
        initial = tables.ImportTable(build)
        before_hero = initial.resolve('STAT', 'hero_a')
        before_item = initial.resolve('ITEM', 'belt_x')
        heroes = xmlb.decode((build / 'Data/herostat.engb').read_bytes())
        heroes[:] = list(reversed(list(heroes)))
        _xmlb(str(build / 'Data/herostat.engb'), heroes)
        items = xmlb.decode((build / 'Data/items.engb').read_bytes())
        # Keep non-definition sections in place while reversing definitions.
        defs = list(reversed([e for e in items if e.tag.lower() == 'item']))
        for i, node in enumerate(list(items)):
            if node.tag.lower() == 'item':
                items[i] = defs.pop(0)
        _xmlb(str(build / 'Data/items.engb'), items)
        refresh_bindings(build, mapping)
        table = tables.ImportTable(build)
        original = source.read_source(src)
        ir = retail.decode(original.payload, hero_names=NAMES)
        output, _, _ = mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True)
        sections = container.read_file(output)['sections']
        assert sections['HERO']['data']['heroes'][-1]['hero'] == before_hero
        assert sections['HERO']['data']['heroes'][-1]['experience'] == 450
        assert sections['ITEM']['data']['instances'][0]['definition'] == before_item
        native, _ = convert.reverse_slot(output, table.env, native=L.W2)
        assert native['heroes'][-1]['equipment']['equipped'][0]['definition'] == table.env.binds.item.index('belt_x')


def test_xml1_profile_merge_validates_with_w2_sized_item_tables():
    with tempfile.TemporaryDirectory() as d:
        build, src, dest, mapping, _ = fixture(d)
        items = xmlb.decode((build / 'Data/items.engb').read_bytes())
        for i in range(170):
            ET.SubElement(items, 'item', name='invented_extra_' + str(i), type='item')
        _xmlb(str(build / 'Data/items.engb'), items)
        refresh_bindings(build, mapping)
        table = tables.ImportTable(build)
        assert len(table.env.binds.item) > 160
        raw = make_profile(table)
        merged = mapper.merge_profile(raw, dict(highest_level=6, flags=0, characters=[], review=[]), table.env)
        assert container.read_file(merged)['sections']['PRFP']['data']['highest_level'] == 6


def test_xml1_exclusive_temp_creation_never_deletes_a_foreign_file():
    with tempfile.TemporaryDirectory() as d:
        _, _, dest, table, original, ir, raw, report, _ = convert_fixture(d)
        class FixedId:
            hex = 'invented-collision'
        foreign = dest / 'saveslot0.xml1-invented-collision.tmp'
        # Inject after the occupancy check to exercise exclusive-create failure.
        actual = transaction._write_new
        def collision(path, data, on_created=lambda: None):
            if path.suffix == '.tmp':
                path.write_bytes(b'foreign pending bytes')
            return actual(path, data, on_created)
        with patch.object(transaction.uuid, 'uuid4', return_value=FixedId()), patch.object(transaction, '_write_new', collision):
            try:
                transaction.install_campaign(raw, report, dest, original, table)
            except FileExistsError:
                pass
            else:
                raise AssertionError('Expected exclusive-create collision')
        assert foreign.read_bytes() == b'foreign pending bytes'
        assert not (dest / 'saveslot0.lcsave').exists() and not (dest / '.xml1-import.lock').exists()


def file_hashes(folder):
    return {p.relative_to(folder).as_posix(): source.digest(p.read_bytes())
            for p in Path(folder).rglob('*') if p.is_file()}


def test_xml1_launcher_source_discovery_and_slots_are_read_only():
    from test_builder_cli import run, check_stream
    with tempfile.TemporaryDirectory() as d:
        build, src, dest, mapping, pos = fixture(d)
        (dest / 'saveslot1.lcsave').write_bytes(b'existing player campaign')
        (dest / 'saveslot2.backup').write_bytes(b'backup')
        (dest / 'saveslot3.pending.tmp').write_bytes(b'pending')
        before = file_hashes(Path(d))
        code, events, _ = run(['import-xml1-save', '--events', 'jsonl', str(src), '--inspect-source'])
        check_stream(events)
        assert code == 0, events
        result = events[-1]
        assert result['imported'] is False and result['capabilities']['player_install'] is False
        assert not result['capabilities']['hdd_images'] and not result['capabilities']['recomp_extensions']
        report = result['source_report']
        assert report['heroes'][0]['level'] == 5 and len(report['heroes']) == 16
        assert report['progress']['mission_id'] == 7
        assert report['signature_status'] == 'unavailable'
        assert len(result['candidates']) == 1
        assert Path(result['candidates'][0]['folder']) == src
        code, events, _ = run(['import-xml1-save', '--list-slots', '--save-dir', str(dest), '--events', 'jsonl'])
        assert code == 0, events
        assert [r['slot'] for r in events[-1]['slots'] if r['occupied']] == [1, 2, 3]
        assert events[-1]['imports'] == []
        assert file_hashes(Path(d)) == before
        extra = src / 'another'; extra.mkdir()
        (extra / 'save.dat').write_bytes((src / 'save.dat').read_bytes())
        code, events, _ = run(['import-xml1-save', '--events', 'jsonl', str(src), '--inspect-source'])
        assert code == 0 and len(events[-1]['candidates']) == 2
        assert events[-1]['source_report'] is None  # no implicit latest campaign
        code, events, _ = run(['import-xml1-save', '--list-slots', '--inspect-source', '--events', 'jsonl'])
        assert code == 2 and events[-2]['code'] == 'E_USAGE'
        code, events, _ = run(['import-xml1-save', '--undo-import', 'a'*32, '--save-dir', str(dest), '--events', 'jsonl'])
        assert code == 2 and events[-2]['code'] == 'E_XML1_UNVALIDATED'


def test_xml1_retained_campaign_copy_and_unchanged_slot_undo():
    with tempfile.TemporaryDirectory() as d:
        build, src, dest, table, original, ir, raw, report, _ = convert_fixture(d)
        (dest / 'saveslot7.lcsave').write_bytes(b'unrelated campaign')
        (dest / 'profile.lcsave').write_bytes(b'unrelated profile')
        source_before = file_hashes(src)
        saved = transaction.install_campaign(raw, report, dest, original, table)
        assert saved['backup'].read_bytes() == raw
        assert saved['path'].read_bytes() == raw
        ledger = json.loads(saved['report'].read_text())
        assert ledger['backup_name'] == 'campaign.lcsave'
        status = transaction.slot_status(dest)
        assert status['imports'][0]['undo_available'] is True
        undone = transaction.undo_campaign(dest, saved['transaction_id'])
        assert undone['undone'] is True and undone['slot'] == 0
        assert undone['transaction_id'] == saved['transaction_id']
        assert not saved['path'].exists()
        assert Path(undone['retained']).read_bytes() == raw and saved['backup'].read_bytes() == raw
        assert saved['report'].is_file()
        assert transaction.slot_status(dest)['imports'][0]['undo_available'] is False
        assert not transaction.slot_status(dest)['slots'][0]['occupied']
        assert (dest / 'saveslot7.lcsave').read_bytes() == b'unrelated campaign'
        assert (dest / 'profile.lcsave').read_bytes() == b'unrelated profile'
        assert source_before == file_hashes(src)
        refused(lambda: transaction.undo_campaign(dest, saved['transaction_id']), 'CHANGED')
        assert not (dest / '.xml1-import.lock').exists()


def test_xml1_undo_refuses_changed_missing_backup_busy_pending_and_cancel():
    for mode in ('changed', 'missing_backup', 'busy', 'pending', 'cancel'):
        with tempfile.TemporaryDirectory() as d:
            build, src, dest, table, original, ir, raw, report, _ = convert_fixture(d)
            saved = transaction.install_campaign(raw, report, dest, original, table)
            if mode == 'changed': saved['path'].write_bytes(b'new player progress')
            if mode == 'missing_backup': os.remove(str(saved['backup'].absolute()))
            if mode == 'busy': (dest / '.xml1-import.lock').write_bytes(b'another importer')
            if mode == 'pending': (dest / 'saveslot0.backup').write_bytes(b'new backup')
            before = file_hashes(dest)
            if mode == 'cancel':
                from xml1builder.errors import Cancelled
                def cancel(): raise Cancelled('test')
                try:
                    transaction.undo_campaign(dest, saved['transaction_id'], cancel=cancel)
                except Cancelled: pass
                else: raise AssertionError('Expected cancellation')
            else:
                refused(lambda: transaction.undo_campaign(dest, saved['transaction_id']),
                        'BUSY' if mode == 'busy' else 'SLOT' if mode == 'pending' else 'CHANGED')
            assert before == file_hashes(dest), mode
    refused(lambda: transaction.undo_campaign('unused', '../escape'), 'INPUT')


def test_xml1_retained_copy_failure_never_installs_campaign():
    with tempfile.TemporaryDirectory() as d:
        build, src, dest, table, original, ir, raw, report, _ = convert_fixture(d)
        write = transaction._write_new
        def fail(path, data, on_created=lambda: None):
            if path.name == 'campaign.lcsave': raise OSError('disk full during retained copy')
            return write(path, data, on_created)
        with patch.object(transaction, '_write_new', fail):
            try: transaction.install_campaign(raw, report, dest, original, table)
            except OSError: pass
            else: raise AssertionError('Expected retained-copy failure')
        assert not (dest / 'saveslot0.lcsave').exists()
        assert not (dest / '.xml1-import.lock').exists()
        assert not list(dest.glob('*.tmp'))
