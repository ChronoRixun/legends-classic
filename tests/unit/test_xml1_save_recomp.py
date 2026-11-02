"""Synthetic recomp decoding/mapping acceptance; no real-save acceptance."""
import struct
import copy
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import xmlb

from save_import_recomp_fixture import difficulty, recomp_save, stash
from test_xml1_save_import import refused
from xml1build.save_import import source
from test_xml1_save_import import fixture, tables, mapper, container, retail, refresh_bindings, _xmlb


def recomp_fixture(folder, *, extra=0):
    build, src, dest, mapping, _ = fixture(folder)
    # LC's destination has 21 slots; added entries are synthetic locked pads.
    herostat = xmlb.decode((build / 'Data/herostat.engb').read_bytes())
    for i in range(5):
        ET.SubElement(herostat, 'stats', name=f'target_pad_{i}', skin='0101')
    _xmlb(str(build / 'Data/herostat.engb'), herostat)
    refresh_bindings(build, mapping)
    original_table = tables.ImportTable(build)
    # Deliberately move both supported records past the first 21 positions.
    definitions = {i + 1: f'extra_{i}' for i in range(extra)}
    definitions.update({99: 'hero_b', 103: 'hero_a'})
    mapping['source'].update(kind='recomp', herostat_sha256='a' * 64,
                             definitions={str(i): n for i, n in definitions.items()})
    mapping['source']['hero_names'] = list(definitions.values())
    mapping['heroes'] = {n: mapping['heroes'][n] for n in ('hero_a', 'hero_b')}
    mapping['talents'] = {n: mapping['talents'][n] for n in ('hero_a', 'hero_b')}
    mapping['checkpoints'][0]['allowed_party'] = ['hero_a', 'hero_b']
    # Native target-only rows remain locked and need explicit pinned defaults.
    from test_xml1_save_import import NAMES
    mapping['target_defaults'] = {}
    for name in [*NAMES[2:], *(f'target_pad_{i}' for i in range(5))]:
        default = mapper.defaults(container.RECORDS['HREC'])
        default.update(level=1, ack_level=1, player_seat=-1, talents=[], equipped=[], powers=[],
                       costume=original_table.resolve('COST', name, 'skin'),
                       costumes_unlocked=[original_table.resolve('COST', name, 'skin')],
                       traits=[12, 0, 0, 0, 14, 0, 0, 0, 16, 0, 0, 0, 20, 0, 0, 0])
        mapping['target_defaults'][name] = default
    (build / tables.TABLE_REL).write_text(json.dumps(mapping), encoding='ascii', newline='\n')
    raw, pos = recomp_save(ids=tuple(definitions), adjuncts=difficulty(5),
        records={103: dict(vitality=(7, 8), auto_equip=1)})
    (src / 'save.dat').write_bytes(raw)
    return build, src, dest, mapping, pos


def test_recomp_mapping_48_records_uses_exact_ids_and_keeps_difficulty():
    from xml1build.save_import import recomp
    with tempfile.TemporaryDirectory() as d:
        build, src, _, mapping, _ = recomp_fixture(d, extra=46)
        table = tables.ImportTable(build)
        original = source.read_source(src, source_kind='recomp')
        ir = recomp.decode(original.payload, definitions={int(k): v for k, v in table.source['definitions'].items()})
        encoded, report, _ = mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True, now=0, serial=42)
        sections = container.read_file(encoded)['sections']
        assert sections['META']['data']['difficulty'] == sections['GAME']['data']['difficulty'] == 2
        heroes = sections['HERO']['data']['heroes']
        assert len(heroes) == 21
        assert heroes[0]['hero'] == table.resolve('STAT', 'hero_a')
        assert [s['hero'] for s in sections['MISS']['data']['snapshots'][0]['seats']] == [
            table.resolve('STAT', 'hero_a'), table.resolve('STAT', 'hero_b')]
        assert set(sections['ULCK']['data']['unlocked']) == {table.resolve('STAT', n) for n in ('hero_a', 'hero_b')}
        assert heroes[0]['health_boosts'] == 7 and heroes[0]['energy_boosts'] == 8
        assert len([r for r in report['skipped'] if r['field'].startswith('unsupported_hero.')]) == 46
        assert any(r['code'] == 'auto_equip' for r in report['approximated'])
        assert any(r['field'] == 'difficulty' and r['value'] == 2 for r in report['imported'])


def test_recomp_golden_preview_losses_and_explicit_difficulty():
    from xml1build.save_import import recomp
    with tempfile.TemporaryDirectory() as d:
        build, src, _, _, _ = recomp_fixture(d, extra=1)
        table = tables.ImportTable(build)
        original = source.read_source(src)
        ir = recomp.decode(original.payload, definitions=table.definitions)
        encoded, report, _ = mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True, now=0, serial=42)
        # A checked-in semantic golden remains readable and ignores provenance
        # hashes that depend on temporary synthetic-build bindings.
        golden = dict(decoder=report['decoder'], checkpoint=report['checkpoint'], difficulty=report['difficulty'],
            party=report['progress']['party'],
            loss_fields=[r['field'] for r in report['skipped']],
            approximations=[r['code'] for r in report['approximated']],
            output_heroes=len(container.read_file(encoded)['sections']['HERO']['data']['heroes']))
        assert golden == dict(decoder='recomp-chr-v6', checkpoint='Invented checkpoint', difficulty=2,
            party=['hero_a', 'hero_b', '', ''], output_heroes=21,
            loss_fields=['unsupported_hero.1', 'game_records', 'hero_b.other_costume_unlocks',
                'hero_a.other_costume_unlocks', *[f'hero_{i}' for i in range(2, 16)],
                *[f'target_pad_{i}' for i in range(5)], 'recomp.campaign_extra', 'embedded_profile', 'other_travel_unlocks'],
            approximations=['checkpoint', 'retained_state', 'base_traits', 'stat_points', 'ai', 'vitals',
                'auto_equip', 'base_traits', 'stat_points', 'ai', 'vitals', 'objective_visibility', 'equipment_conservation'])


def test_recomp_unsupported_active_hero_and_missing_definition_refuse():
    from xml1build.save_import import recomp
    with tempfile.TemporaryDirectory() as d:
        build, src, _, _, _ = recomp_fixture(d, extra=1)
        table = tables.ImportTable(build)
        original = source.read_source(src, source_kind='recomp')
        defs = {int(k): v for k, v in table.source['definitions'].items()}
        ir = recomp.decode(original.payload, definitions=defs)
        ir['mission']['party'][0] = 'extra_0'
        e = refused(lambda: mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True), 'IDENTITY')
        assert e.detail['hero'] == 'extra_0'
        del defs[103]
        refused(lambda: recomp.decode(original.payload, definitions=defs), 'IDENTITY')


def test_recomp_discovery_install_root_and_cli_preview_remain_read_only():
    from test_builder_cli import run
    with tempfile.TemporaryDirectory() as d:
        build, src, dest, _, _ = recomp_fixture(d)
        install = Path(d) / 'install'
        campaign = install / 'UDATA' / source.TITLE_ID / 'invented_campaign'
        campaign.mkdir(parents=True)
        (campaign / 'save.dat').write_bytes((src / 'save.dat').read_bytes())
        # An unrelated asset subtree must not be traversed.
        (install / 'assets').mkdir()
        for i in range(260):
            (install / 'assets' / f'entry{i}').write_text('invented')
        before = {p: source.digest(p.read_bytes()) for p in Path(d).rglob('*') if p.is_file()}
        code, events, _ = run(['import-xml1-save', str(install), '--source-kind', 'recomp', '--inspect-source', '--events', 'jsonl'])
        assert code == 0, events
        result = events[-1]
        assert result['source_report']['source_container']['kind'] == 'recomp'
        assert result['source_report']['heroes'][0]['definition_id'] == 99
        assert result['source_report']['identity_status'].startswith('Unresolved')
        assert result['capabilities']['recomp_extensions'] is True
        assert result['capabilities']['player_install'] is False and result['capabilities']['undo'] is False
        argv = ['import-xml1-save', str(install), '--source-kind', 'recomp', '--build', str(build),
                '--save-dir', str(dest), '--slot', '0', '--allow-inferred', '--events', 'jsonl']
        code, events, _ = run(argv + ['--dry-run'])
        assert code == 0, events
        report = events[-1]['import_report']
        assert report['difficulty'] == 2 and report['source_container']['kind'] == 'recomp'
        code, events, _ = run(argv + ['--preview-token', report['preview_token']])
        assert code == 2 and any(e.get('code') == 'E_XML1_UNVALIDATED' for e in events)
        assert before == {p: source.digest(p.read_bytes()) for p in Path(d).rglob('*') if p.is_file()}


def test_mapper_preserves_explicit_difficulty_for_retail_too():
    with tempfile.TemporaryDirectory() as d:
        build, src, _, _, _ = fixture(d)
        original = source.read_source(src)
        table = tables.ImportTable(build)
        ir = retail.decode(original.payload, hero_names=table.source['hero_names'])
        ir['difficulty'] = 0  # a source decoder's explicit value; zero is Easy
        encoded, report, _ = mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True, now=0, serial=42)
        assert container.read_file(encoded)['sections']['GAME']['data']['difficulty'] == 0
        assert report['difficulty'] == 0 and not any(r['code'] == 'difficulty' for r in report['approximated'])


def test_recomp_named_talent_identity_overrides_runtime_byte_ledger_and_preserves_rank():
    from xml1build.save_import import recomp
    with tempfile.TemporaryDirectory() as d:
        build, src, _, mapping, _ = recomp_fixture(d)
        mapping['named_talents'] = {'hero_a': [dict(name='invented_skill', source='invented.xml',
            selector='Talent:invented_skill;Talents', target=['hero_a', 'a_one'])]}
        mapping['heroes']['hero_a']['power_selections'] = {'move_a': 'power1', 'move_b': 'power2', '': ''}
        # Reused byte 17 intentionally has a different numeric-ledger meaning.
        mapping['talents']['hero_a']['17'] = ['shared', 'sh_fight']
        (build / tables.TABLE_REL).write_text(json.dumps(mapping), encoding='ascii', newline='\n')
        raw, _ = recomp_save(ids=(99, 103), records={103: dict(talents=[(17, 47, 0, 0, 3, 1)])},
            talent_rows=[(17, 'invented_skill', 'invented.xml', 'Talent:invented_skill;Talents')],
            power_rows=[('hero_a', ['move_a', 'move_b', '', ''])])
        (src / 'save.dat').write_bytes(raw)
        original = source.read_source(src)
        table = tables.ImportTable(build)
        ir = recomp.decode(original.payload, definitions=table.definitions)
        encoded, report, _ = mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True, now=0, serial=42)
        hero = container.read_file(encoded)['sections']['HERO']['data']['heroes'][0]
        assert hero['talents'] == [dict(talent=table.resolve('TALN', 'hero_a', 'a_one'), rank=47, pending=0, cap=3, base=1, byte5=0)]
        assert [(p['name'], p['flags']) for p in hero['powers']] == [('power1', 1), ('power2', 1), ('', 0), ('', 0)]
        # Matching a name alone must never identify a different source/selector.
        ir['talent_identities'][17]['selector'] = 'Talent:other;Talents'
        refused(lambda: mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True), 'IDENTITY')


def test_recomp_expanded_progression_refuses_unrepresentable_cap_baseline_and_pending():
    from xml1build.save_import import recomp
    with tempfile.TemporaryDirectory() as d:
        build, src, _, mapping, _ = recomp_fixture(d)
        # V2 has expanded six-bit values but still needs a proven byte ledger.
        for field, values, code in [('limit', (47, 0, 0, 4, 1), 'CAPACITY'),
                                    ('baseline', (47, 0, 0, 3, 4), 'CAPACITY'),
                                    ('pending', (47, 1, 0, 3, 1), 'CONTEXT')]:
            raw, _ = recomp_save(2, ids=(99, 103), records={103: dict(talents=[(17, *values)])})
            (src / 'save.dat').write_bytes(raw)
            original = source.read_source(src)
            table = tables.ImportTable(build)
            ir = recomp.decode(original.payload, definitions=table.definitions)
            refused(lambda: mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True), code)


def test_recomp_stash_copy_conservation_and_unknown_named_items_refuse():
    from xml1build.save_import import recomp
    with tempfile.TemporaryDirectory() as d:
        build, src, _, mapping, _ = recomp_fixture(d)
        mapping['items'][0]['source_name'] = 'invented_gear'
        (build / tables.TABLE_REL).write_text(json.dumps(mapping), encoding='ascii', newline='\n')
        raw, _ = recomp_save(ids=(99, 103), adjuncts=stash([('invented_gear', 3)]),
                              records={103: dict(equipment=[12])})
        (src / 'save.dat').write_bytes(raw)
        original = source.read_source(src)
        table = tables.ImportTable(build)
        ir = recomp.decode(original.payload, definitions=table.definitions)
        encoded, report, _ = mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True, now=0, serial=42)
        sections = container.read_file(encoded)['sections']
        assert len(sections['ITEM']['data']['instances']) == 5  # 2 carried + 3 stash
        assert len(sections['HERO']['data']['heroes'][0]['equipped']) == 1
        assert any(r['code'] == 'stash_location' for r in report['approximated'])
        ir['stash']['live'][0]['name'] = 'unmapped_gear'
        refused(lambda: mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True), 'IDENTITY')


def test_recomp_unknown_unlock_and_unresolved_ledger_refuse():
    from xml1build.save_import import recomp
    with tempfile.TemporaryDirectory() as d:
        build, src, _, mapping, _ = recomp_fixture(d)
        original = source.read_source(src)
        table = tables.ImportTable(build)
        ir = recomp.decode(original.payload, definitions=table.definitions)
        ir['unlocked'].append(104)
        refused(lambda: mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True), 'IDENTITY')
        del mapping['source']['herostat_sha256']
        (build / tables.TABLE_REL).write_text(json.dumps(mapping), encoding='ascii', newline='\n')
        refused(lambda: tables.ImportTable(build), 'VERSION')
        refused(lambda: recomp.decode(original.payload, definitions={99: 'hero_a', 103: 'HERO_A'}), 'IDENTITY')


def test_recomp_all_character_versions_and_sparse_definition_ids():
    from xml1build.save_import import recomp
    for version in range(1, 7):
        raw, pos = recomp_save(version, ids=(2, 41, 99), records={99: dict(vitality=(7, 8), auto_equip=1)})
        ir = recomp.decode(raw[24:], definitions={2: 'hero_b', 41: 'extra_a', 99: 'hero_a'})
        assert ir['decoder'] == f'recomp-chr-v{version}'
        assert [h['definition_id'] for h in ir['heroes']] == [2, 41, 99]
        assert [h['name'] for h in ir['heroes']] == ['hero_b', 'extra_a', 'hero_a']
        assert len(ir['restore']) == 48 and ir['consumed'] == len(raw) - 24
        assert ir['boundaries']['characters'] == 0x5c6
        assert ir['heroes'][2]['vitality'] == ([7, 8] if version >= 5 else [0, 0])
        assert ir['heroes'][2]['auto_equip'] == (version >= 6)


def test_recomp_expanded_talents_named_selections_and_identities():
    from xml1build.save_import import recomp
    for version in range(1, 7):
        rank = 13 if version == 1 else 47
        raw, _ = recomp_save(version, records={1: dict(talents=[(17, rank, 0, 2, 3, 1)])},
            power_rows=[('hero_a', ['power1', 'power2', '', 'power9'])],
            talent_rows=[(17, 'invented_skill', 'invented.xml', 'Talent:invented_skill;Talents')])
        ir = recomp.decode(raw[24:], definitions={1: 'hero_a', 2: 'hero_b'})
        assert ir['heroes'][0]['talents'][0]['rank'] == rank
        assert ir['power_selections'] == ({'hero_a': ['power1', 'power2', '', 'power9']} if version >= 3 else {})
        assert list(ir['talent_identities']) == ([17] if version >= 4 else [])


def test_recomp_campaign_adjunct_versions_and_stash():
    from xml1build.save_import import recomp
    for version in range(1, 6):
        raw, _ = recomp_save(adjuncts=b'XML1PRG\0' + struct.pack('<II', 1, 1) +
                             difficulty(version) + stash([('invented_gear', 3)]))
        ir = recomp.decode(raw[24:])
        assert ir['difficulty'] == 2 and ir['campaign_extra']['retained_difficulty'] == 0
        assert ir['hard_unlocked'] is True
        assert ir['stash']['live'] == [dict(name='invented_gear', quantity=3)]
        assert ir['campaign_extra']['version'] == version
    raw, _ = recomp_save()
    ir = recomp.decode(raw[24:])
    assert ir['difficulty'] == 1 and ir['hard_unlocked'] is False and ir['stash']['live'] == []


def test_recomp_truncation_header_limits_versions_and_expanded_padding():
    from xml1build.save_import import recomp
    raw, pos = recomp_save(records={1: dict(talents=[(17, 47, 0, 0, 3, 1)])},
        talent_rows=[(17, 'invented_skill', 'invented.xml', 'Talent:invented_skill;Talents')])
    payload = raw[24:]
    for cut in sorted({0, 1, len(payload) - 1, *(v for v in pos.values()), *(v + 1 for v in pos.values())}):
        refused(lambda cut=cut: recomp.decode(payload[:cut]), 'VERSION' if cut == 0 else 'DAMAGED')
    for off, fmt, value, code in ((8, '<H', 7, 'RECOMP_VERSION'), (10, '<H', 47, 'DAMAGED'),
                                  (12, '<H', 17, 'DAMAGED'), (14, '<H', 1, 'DAMAGED')):
        bad = bytearray(payload)
        struct.pack_into(fmt, bad, pos['header'] + off, value)
        refused(lambda: recomp.decode(bad), code)
    bad = bytearray(payload)
    bad[pos['hero1'] + 47 + 1 + 4] |= 0xc0
    refused(lambda: recomp.decode(bad), 'DAMAGED')
    refused(lambda: recomp.decode(bytes(source.CAPACITY + 1)), 'VERSION')


def test_recomp_every_header_version_truncates_and_rejects_invalid_bitmaps():
    from xml1build.save_import import recomp
    for version in range(1, 7):
        raw, pos = recomp_save(version, ids=(2, 254))
        payload = raw[24:]
        for end in range(pos['header'], pos['hero2'] + 1):
            refused(lambda end=end: recomp.decode(payload[:end]), 'DAMAGED')
        for name in ('hero2', 'hero254', 'restore0', 'restore47'):
            for delta in (1, 12, 43, 44, 45):
                refused(lambda name=name, delta=delta: recomp.decode(payload[:pos[name] + delta]), 'DAMAGED')
        for bitmap in (bytes(32), b'\1' + bytes(31), bytes(31) + b'\x80', b'\xfe' + b'\xff' * 6 + bytes(25)):
            bad = bytearray(payload)
            bad[pos['header'] + 16:pos['header'] + 48] = bitmap
            refused(lambda: recomp.decode(bad), 'DAMAGED')
        if version >= 6:
            bad = bytearray(payload)
            bad[pos['hero2'] + 46] = 2
            refused(lambda: recomp.decode(bad), 'DAMAGED')


def test_recomp_corrupt_selection_and_identity_frames_refuse():
    from xml1build.save_import import recomp
    from save_import_recomp_fixture import selections, identities
    for extra in (selections([('hero_a', ['a', '', '', ''])])[:-1],
                  selections([('hero_a', ['', '', '', '']), ('HERO_A', ['', '', '', ''])]),
                  b'\xff\xff', b'\0\0x'):
        raw, pos = recomp_save(3)
        native = raw[24:]
        bad = bytearray(native[:pos['header'] + 48] + extra + native[pos['hero1']:])
        struct.pack_into('<H', bad, pos['header'] + 10, 48 + len(extra))
        refused(lambda: recomp.decode(bad), 'DAMAGED')
    raw, pos = recomp_save(4, power_rows=[('hero_a', ['power1', '', '', ''])],
        talent_rows=[(17, 'invented', 'invented.xml', 'Talent:invented;Talents')])
    payload = raw[24:]
    # Framed lengths, TLID version/reserved, ID zero, name length zero,
    # selection padding, and byte strings containing NUL all refuse.
    sel_bytes = struct.unpack_from('<H', payload, pos['header'] + 48)[0]
    tlid = pos['header'] + 52 + sel_bytes
    for off, value, code in ((pos['header'] + 48, 0, 'DAMAGED'), (tlid + 4, 2, 'RECOMP_VERSION'),
                             (tlid + 5, 1, 'DAMAGED'), (tlid + 7, 1, 'DAMAGED'),
                             (tlid + 8, 0, 'DAMAGED'), (tlid + 9, 0, 'DAMAGED'),
                             (tlid + 12, 0, 'DAMAGED'), (pos['header'] + 52 + 2 + 19, 1, 'DAMAGED')):
        bad = bytearray(payload)
        bad[off] = value
        refused(lambda: recomp.decode(bad), code)
    for entries in ([(17, 'a', 'a.xml', 'a'), (17, 'b', 'b.xml', 'b')],
                    [(17, 'a', 'a.xml', 'a'), (18, 'A', 'b.xml', 'b')]):
        raw, _ = recomp_save(4, talent_rows=entries)
        refused(lambda: recomp.decode(raw[24:]), 'DAMAGED')
    raw, _ = recomp_save(4, records={1: dict(talents=[(17, 1, 0, 0, 3, 0)])})
    refused(lambda: recomp.decode(raw[24:]), 'DAMAGED')


def test_recomp_every_campaign_adjunct_version_truncates_and_rejects_corruption():
    from xml1build.save_import import recomp
    extensions = [b'XML1PRG\0' + struct.pack('<II', 1, 1), stash([('gear_a', 2)])]
    extensions += [difficulty(v) for v in range(1, 6)]
    for extra in extensions:
        raw, pos = recomp_save(adjuncts=extra)
        payload = raw[24:]
        for count in range(1, len(extra)):
            refused(lambda count=count: recomp.decode(payload[:pos['adjuncts'] + count]), 'DAMAGED')
        bad = bytearray(payload)
        struct.pack_into('<I', bad, pos['adjuncts'] + 8, 99)
        refused(lambda: recomp.decode(bad), 'RECOMP_VERSION')
    for extra in (b'XML1PRG\0' + struct.pack('<II', 1, 2), difficulty(1, live=-1), difficulty(1, retained=3),
                  difficulty(2, acts=(0, 1)), stash([('gear_a', 61)]), stash([('gear_a', 0)]),
                  stash([('gear_a', 2), ('GEAR_A', 2)]), stash([], [('gear_a', 1)], valid=0),
                  stash([], [], valid=1)):
        raw, _ = recomp_save(adjuncts=extra)
        refused(lambda: recomp.decode(raw[24:]), 'DAMAGED')
    for byte_offset, fmt, value in ((22 + 32, '<f', float('nan')), (22 + 44, '<B', 2),
                                    (112, '<f', -1), (116, '<f', float('inf'))):
        extra = bytearray(difficulty(5))
        struct.pack_into(fmt, extra, byte_offset, value)
        raw, _ = recomp_save(adjuncts=extra)
        refused(lambda: recomp.decode(raw[24:]), 'DAMAGED')
    # Native inventory snapshot and stash valid flags must agree.
    raw, pos = recomp_save(adjuncts=stash([], [('gear_a', 2)], valid=1))
    payload = bytearray(raw[24:])
    payload[pos['native_tail'] + 0x280] = 1
    assert recomp.decode(payload)['stash']['snapshot'] == [dict(name='gear_a', quantity=2)]
    for extra in (difficulty(1) * 2, stash() + difficulty(1), b'XML1PRG\0' + struct.pack('<II', 1, 0) + b'XML1PRG\0'):
        raw, _ = recomp_save(adjuncts=extra)
        refused(lambda: recomp.decode(raw[24:]), 'RECOMP_VERSION')


def test_recomp_direct_file_auto_kind_recheck_and_explicit_retail_refusal():
    from xml1build.save_import.command import decode_source
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'save.dat'
        raw, _ = recomp_save()
        path.write_bytes(raw)
        original = source.read_source(path)
        assert original.kind == 'recomp'
        assert decode_source(original)['decoder'] == 'recomp-chr-v6'
        refused(lambda: decode_source(source.read_source(path, source_kind='xemu')), 'RECOMP_VERSION')
        rows, selected = source.discover_source(path, source_kind='recomp')
        assert len(rows) == 1 and selected.sha256 == original.sha256
        path.write_bytes(raw[:-1] + b'x')
        refused(original.recheck, 'CHANGED')


def test_recomp_every_unmapped_named_power_is_disclosed():
    from xml1build.save_import import recomp
    with tempfile.TemporaryDirectory() as d:
        build, src, _, _, _ = recomp_fixture(d, extra=1)
        raw, _ = recomp_save(ids=(1, 99, 103),
            power_rows=[('extra_0', ['custom_move', '', '', '']), ('uninstantiated', ['other_move', '', '', ''])])
        (src / 'save.dat').write_bytes(raw)
        original = source.read_source(src)
        table = tables.ImportTable(build)
        ir = recomp.decode(original.payload, definitions=table.definitions)
        _, report, _ = mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True, now=0, serial=42)
        assert [r['source'] for r in report['skipped'] if r['field'].startswith('recomp.power_selections.')] == [
            ['custom_move', '', '', ''], ['other_move', '', '', '']]


def test_recomp_unsupported_hero_equipment_becomes_carried_for_both_quantity_policies():
    from xml1build.save_import import recomp
    with tempfile.TemporaryDirectory() as d:
        build, src, _, mapping, _ = recomp_fixture(d, extra=1)
        raw, _ = recomp_save(ids=(1, 99, 103), records={1: dict(equipment=[12]), 103: dict(equipment=[12])})
        (src / 'save.dat').write_bytes(raw)
        for policy, carried in (('excludes_equipped', 3), ('includes_equipped', 1)):
            mapping['quantity_policy'] = policy
            (build / tables.TABLE_REL).write_text(json.dumps(mapping), encoding='ascii', newline='\n')
            original = source.read_source(src)
            table = tables.ImportTable(build)
            ir = recomp.decode(original.payload, definitions=table.definitions)
            encoded, report, _ = mapper.map_campaign(ir, original, table, slot=0, allow_inferred=True, now=0, serial=42)
            sections = container.read_file(encoded)['sections']
            assert len(sections['ITEM']['data']['instances']) == carried
            assert len(sections['HERO']['data']['heroes'][0]['equipped']) == 1
            assert any(r['code'] == 'unsupported_hero_equipment' for r in report['approximated'])


def test_recomp_equipped_id_outside_native_item_bank_refuses_explicitly():
    from xml1build.save_import import recomp
    raw, _ = recomp_save(records={1: dict(equipment=[200])})
    refused(lambda: recomp.decode(raw[24:]), 'DAMAGED')
    # The retail reader shares the same native item bank and must not leave a
    # malformed ID to become an uncaught dictionary lookup during mapping.
    from test_xml1_save_import import save
    raw, pos = save()
    bad = bytearray(raw[24:])
    bad[pos['hero0'] + 54] = 200
    refused(lambda: retail.decode(bad), 'DAMAGED')


def test_recomp_hdd_sources_honor_explicit_family_for_inspection_and_preview():
    from xml1build.save_import.command import decode_source
    from save_import_disk_fixture import xbox
    from test_builder_cli import run
    raw, _ = recomp_save()
    with tempfile.TemporaryDirectory() as d:
        for form in ('raw', 'qcow'):
            guest, offsets = xbox(raw)
            path = getattr(guest, form)(Path(d) / (form + '.img'))
            for kind in ('auto', 'recomp'):
                original = source.read_source(path, source_kind=kind)
                assert decode_source(original)['decoder'] == 'recomp-chr-v6'
                rows, selected = source.discover_source(path, source_kind=kind)
                assert len(rows) == 1 and decode_source(selected)['decoder'] == 'recomp-chr-v6'
                original.recheck()
            original = source.read_source(path, source_kind='xemu')
            refused(lambda: decode_source(original), 'RECOMP_VERSION')
            _, selected = source.discover_source(path, source_kind='xemu')
            refused(lambda: decode_source(selected), 'RECOMP_VERSION')
            code, events, _ = run(['import-xml1-save', str(path), '--source-kind', 'xemu',
                                   '--inspect-source', '--events', 'jsonl'])
            assert code == 2 and any(e.get('code') == 'E_XML1_RECOMP_VERSION' for e in events)
