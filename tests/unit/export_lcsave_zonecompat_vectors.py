"""Export synthetic append compatibility and cache-resave byte parity cases."""
import sys
import shutil
import struct
import copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from test_lcsave_zonecompat import fixture, _reviewed_maps, _drop_guard, GATE_EDIT
from test_lcsave_durable import _env, _converted, _secs
from test_lcsave import _xmlb
import xmlb
from lcsave import convert, oldsave, zonecompat as Z, binds, container, lcfiles, layout as L

EQUIVALENCE_VARIANTS = ('equivalent', 'equivalent_legacy', 'equivalent_rejected', 'reviewed', 'retarget',
                        'full_permuted', 'full_bad_digest')


def equivalence_fixture(folder, variant):
    """Full-length (equivalence) rows (zonecompat.attest_equivalent): -> (env, saved).
    equivalent / equivalent_legacy: an exact record (current capture / legacy provenance) on a map whose definitions
    then gain xml1heaviness; equivalent_rejected: plus another definition edit (no row, record discarded);
    reviewed: a reviewed actscript edit (a synthetic REVIEWED_CHANGES row for this zone); retarget: an append row of
    the previous build re-targeted through an equivalence; full_permuted / full_bad_digest: a full-length row whose
    placements are not the current list (read as a prefix row) or whose digest is wrong (no row matches)."""
    if variant == 'retarget':
        env, saved, _ = fixture(str(folder))
        appended = Path(folder) / 'appended'
        shutil.copytree(env.binds.build, appended)
        path = Path(env.binds.zone_file('zone/x/y'))
        root = xmlb.decode(path.read_bytes())
        next(e for e in root.iter('entity') if e.get('name') == 'gate').set('xml1heaviness', '5')
        _xmlb(str(path), root)
        report = Z.generate(appended, env.binds.build)
        assert report['accepted'] == ['zone/x/y'] and report['retargeted'] == 1, report
    elif variant == 'reviewed':
        shipped = Z.REVIEWED_CHANGES
        Z.REVIEWED_CHANGES = frozenset({GATE_EDIT})
        try:
            env, saved, old, _ = _reviewed_maps(str(folder), _drop_guard('gate'))
            before = Path(folder) / 'before'
            shutil.copytree(env.binds.build, before)
            (before / Path(env.binds.zone_file('zone/x/y')).relative_to(env.binds.build)).write_bytes(old)
            report = Z.generate(before, env.binds.build)
        finally:
            Z.REVIEWED_CHANGES = shipped
        assert report['accepted'] == ['zone/x/y'], report
    else:
        env = _env(str(folder))
        _, saved = _converted(env)                      # a legacy-provenance record (capture_flags 2)
        if variant != 'equivalent_legacy':
            captures = convert.loaded_zone_metadata(saved, env)
            captures[0]['capture_flags'] = 0
            native, _ = convert.reverse_slot(saved, env)
            result = convert.old_stream_to_new(oldsave.write_slot(native), env, now=0, zone_captures=captures,
                                               require_capture_metadata=True)
            assert result.refused is None, result.refused
            saved = result.file_bytes
        previous = Path(folder) / 'previous'
        shutil.copytree(env.binds.build, previous)
        path = Path(env.binds.zone_file('zone/x/y'))
        root = xmlb.decode(path.read_bytes())
        for name in ('gate', 'lamp'):
            next(e for e in root.iter('entity') if e.get('name') == name).set('xml1heaviness', '4')
        if variant == 'equivalent_rejected':
            next(e for e in root.iter('entity') if e.get('name') == 'lamp').set('health', '99')
        _xmlb(str(path), root)
        report = Z.generate(previous, env.binds.build)
        assert report['rejected' if variant == 'equivalent_rejected' else 'accepted'] == ['zone/x/y'], report
        if variant in ('full_permuted', 'full_bad_digest'):
            rows = Z.load(env.binds.build)
            row = next(r for r in rows if r['zone'] == Z.zone_hash('zone/x/y'))
            if variant == 'full_permuted':
                row['placements'][0], row['placements'][1] = row['placements'][1], row['placements'][0]
            else:
                row['digest'] = bytes(32)
            (Path(env.binds.build) / Z.REL).write_bytes(Z.encode(rows))   # a valid CRC over the edited row
    env.binds._zones.clear()
    env.binds.zone_prefixes = Z.load(env.binds.build)
    for rel, blob in lcfiles.write_build_files(env.binds.build, 13, cat=env.catalogue, model=env.model)[0].items():
        q = Path(env.binds.build) / rel; q.parent.mkdir(parents=True, exist_ok=True); q.write_bytes(blob)
    return env, saved


def zones_text(metadata):
    """expected.zones: per applied capture, its zone, current and source map hashes and fresh-tail size."""
    return ''.join(f"{c['zone']}\t{c['placement_sha1'].hex()}\t{c.get('source_placement_sha1', bytes(20)).hex()}\t"
                   f"{len(c.get('fresh_entities', []))}\n" for c in metadata).encode('utf-8')


def main(destination):
    out = Path(destination)
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    for variant in ('append', 'tailstate', 'renamed', 'ambiguous', 'xmlbonly', 'position', 'definition', 'reorder','world','smartdefinition',
                    'escaped', 'bad_digest', 'rebound_prefix', 'past_prefix') + EQUIVALENCE_VARIANTS:
        folder = out / variant
        folder.mkdir()
        if variant in EQUIVALENCE_VARIANTS:
            env, saved = equivalence_fixture(folder, variant)
        else:
            env, saved, _ = fixture(str(folder), variant)
        (folder / 'input.lcsave').write_bytes(saved)
        restored, _ = convert.reverse_slot(saved, env)
        (folder / 'expected.old').write_bytes(oldsave.write_slot(restored))
        metadata = convert.loaded_zone_metadata(saved, env)
        (folder / 'expected.metadata').write_bytes(''.join(
            f"{c['zone']}\t{e['ordinal']}\t{e['placement_index']}\t{e['definition_name']}\t{e['instance_name']}\n"
            for c in metadata for e in c['entities']).encode('utf-8'))
        (folder / 'expected.zones').write_bytes(zones_text(metadata))
        applied = bool(restored['zones'])
        if variant in EQUIVALENCE_VARIANTS:
            # An equivalence row reads the record exactly (no source hash, no fresh tail); a rejected zone, a
            # non-equivalent full-length row and a wrong digest discard it.
            assert applied == (variant in ('equivalent', 'equivalent_legacy', 'reviewed', 'retarget')), variant
            if variant in ('equivalent', 'equivalent_legacy', 'reviewed'):
                assert metadata and not metadata[0].get('source_placement_sha1') and not metadata[0].get('fresh_entities')
            if variant == 'retarget':
                assert metadata[0]['source_placement_sha1'] != metadata[0]['placement_sha1'] and metadata[0]['fresh_entities']
        lines.append(f'{variant}\t{variant}/build\treverse\t0\n')
        if variant not in ('append', 'tailstate', 'renamed', 'equivalent', 'equivalent_legacy', 'reviewed', 'retarget'): continue
        for sequence in (2, 3):
            row = out / f'{variant}_save{sequence}'
            row.mkdir()
            (row / 'input.lcsave').write_bytes(saved)
            restored, _ = convert.reverse_slot(saved, env)
            result = convert.old_stream_to_new(oldsave.write_slot(restored), env, now=-11644473600,
                retained_file=saved, zone_captures=convert.loaded_zone_metadata(saved, env),
                require_capture_metadata=True, campaign_serial=17, save_sequence=sequence)
            assert result.refused is None, result.refused
            (row / 'expected.lcsave').write_bytes(result.file_bytes)
            lines.append(f'{row.name}\t{variant}/build\tcampaign\t{sequence}\n')
            saved = result.file_bytes
    raw = (out/'append/build'/Z.REL).read_bytes()
    rows = Z.decode(raw)
    damaged = bytearray(raw); damaged[-1] ^= 1
    version = bytearray(raw); struct.pack_into('<I',version,8,99)
    overflow = bytearray(raw); struct.pack_into('<I',overflow,12,4097)
    duplicate = dict(rows[-1]); duplicate['placements'] = [duplicate['placements'][0]] * len(duplicate['placements'])
    cases = [('truncated',raw[:23]), ('crc',damaged), ('version',version), ('count',overflow),
             ('placements',Z.encode([duplicate]))]
    for name, bad in cases:
        folder = out / ('bad_' + name)
        shutil.copytree(out/'append/build',folder/'build')
        (folder/'build'/Z.REL).write_bytes(bad)
        try: binds.Binds(str(folder/'build'))
        except binds.BindError as e: (folder/'expected.error').write_text(str(e))
        else: raise AssertionError('damaged metadata accepted')
        lines.append(f'{folder.name}\t{folder.name}/build\trefuse-tables\t0\n')
    # Both native layouts, with and without the receiver's optional sidecar.
    # Include the full fresh/source metadata and a cached, unvisited LC resave.
    for native in (L.RETAIL, L.E10A2):
        for missing in (False, True):
            name = f'transfer_{native.ordinals}_{int(missing)}'
            folder = out / name
            folder.mkdir()
            env, saved, _ = fixture(str(folder))
            restored, _ = convert.reverse_slot(saved, env, native=native, registry={"keys": set()})
            stream = oldsave.write_slot(restored, native=native)
            if missing:
                (Path(env.binds.build) / Z.REL).unlink()
                env.binds.zone_prefixes = []
            metadata = convert.native_zone_metadata(stream, env, native=native)
            assert metadata[0]['fresh_entities']
            result = convert.old_stream_to_new(stream, env, now=-11644473600, native=native,
                zone_captures=metadata, require_capture_metadata=True, campaign_serial=17, save_sequence=2)
            assert result.refused is None, result.refused
            (folder / 'input.raw').write_bytes(stream)
            (folder / 'expected.lcsave').write_bytes(result.file_bytes)
            text = ''
            for c in metadata:
                text += f"{c['zone']}\t{c['placement_sha1'].hex()}\t{c['source_placement_sha1'].hex()}\n"
                for e in c['entities']:
                    text += f"saved\t{e['ordinal']}\t{e['placement_index']}\t{e['source_placement_index']}\t{e['definition_name']}\t{e['instance_name']}\n"
                for e in c['fresh_entities']:
                    text += f"fresh\t{e['ordinal']}\t{e['placement_index']}\t{e['definition_name']}\t{e['instance_name']}\n"
            (folder / 'expected.transfer').write_text(text, encoding='utf-8', newline='\n')
            mode = 'native-transfer' if native == L.RETAIL else 'native-transfer-e10a2'
            lines.append(f'{name}\t{name}/build\t{mode}\t2\n')
            if native != L.RETAIL or not missing:
                continue
            for mutation in ('alive', 'tailstate', 'wrong_zone', 'wrong_map', 'duplicate_placement', 'empty_prefix', 'overflow', 'leading_zero'):
                broken = copy.deepcopy(restored)
                record = broken['zones'][0]; sentinel = record['states'][0]
                if mutation == 'alive': sentinel['flags_b'] = 8
                elif mutation == 'tailstate': record['ordinal_map'][3] = record['ordinal_map'][0]
                else:
                    table = broken['zone_strings']; offset = table['offsets'][sentinel['def_name'] & 0xffffff]
                    fields = oldsave.zone_string(table, sentinel['def_name']).split('|')
                    if mutation == 'wrong_zone': fields[1] = '0'*64
                    elif mutation == 'wrong_map': fields[3] = '0'*40
                    elif mutation == 'duplicate_placement': fields[4] = '0,0,0'
                    elif mutation == 'overflow': fields[4] = '4294967296'
                    elif mutation == 'leading_zero': fields[4] = '01'
                    else: fields[4] = ''
                    text = '|'.join(fields).encode() + b'\0'
                    arena = bytearray(table['arena']); arena[offset:offset+len(text)] = text; table['arena'] = bytes(arena)
                row = out / ('transfer_bad_' + mutation); row.mkdir()
                stream = oldsave.write_slot(broken)
                (row / 'input.raw').write_bytes(stream)
                try: convert.native_zone_metadata(stream, env)
                except ValueError as e: (row / 'expected.error').write_text(str(e))
                else: raise AssertionError('invalid transfer accepted: ' + mutation)
                lines.append(f'{row.name}\t{name}/build\tnative-transfer-refuse\t0\n')
    # A native transfer of an equivalence-applied record (both layouts): a plain exact record, no fresh-tail sentinel.
    for native in (L.RETAIL, L.E10A2):
        name = f'transfer_equivalent_{native.ordinals}'
        folder = out / name
        folder.mkdir()
        env, saved = equivalence_fixture(folder, 'equivalent')
        restored, _ = convert.reverse_slot(saved, env, native=native, registry={"keys": set()})
        assert restored['zones']
        stream = oldsave.write_slot(restored, native=native)
        metadata = convert.native_zone_metadata(stream, env, native=native)
        assert metadata and not metadata[0].get('fresh_entities')
        result = convert.old_stream_to_new(stream, env, now=-11644473600, native=native,
            zone_captures=metadata, require_capture_metadata=True, campaign_serial=17, save_sequence=2)
        assert result.refused is None, result.refused
        (folder / 'input.raw').write_bytes(stream)
        (folder / 'expected.lcsave').write_bytes(result.file_bytes)
        lines.append(f'{name}\t{name}/build\t{"native-transfer" if native == L.RETAIL else "native-transfer-e10a2"}\t2\n')
    (out / 'cases.tsv').write_text(''.join(lines))
    print('Verified', len(lines), 'zone prefix parity vectors')


if __name__ == '__main__':
    main(sys.argv[1])
