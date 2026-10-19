"""Export synthetic append compatibility and cache-resave byte parity cases."""
import sys
import shutil
import struct
import copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from test_lcsave_zonecompat import fixture
from lcsave import convert, oldsave, zonecompat as Z, binds, layout as L


def main(destination):
    out = Path(destination)
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    for variant in ('append', 'tailstate', 'renamed', 'ambiguous', 'xmlbonly', 'position', 'definition', 'reorder','world','smartdefinition',
                    'escaped', 'bad_digest', 'rebound_prefix', 'past_prefix'):
        folder = out / variant
        folder.mkdir()
        env, saved, _ = fixture(str(folder), variant)
        (folder / 'input.lcsave').write_bytes(saved)
        restored, _ = convert.reverse_slot(saved, env)
        (folder / 'expected.old').write_bytes(oldsave.write_slot(restored))
        metadata = convert.loaded_zone_metadata(saved, env)
        (folder / 'expected.metadata').write_bytes(''.join(
            f"{c['zone']}\t{e['ordinal']}\t{e['placement_index']}\t{e['definition_name']}\t{e['instance_name']}\n"
            for c in metadata for e in c['entities']).encode('utf-8'))
        lines.append(f'{variant}\t{variant}/build\treverse\t0\n')
        if variant not in ('append', 'tailstate', 'renamed'): continue
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
    (out / 'cases.tsv').write_text(''.join(lines))
    print('Verified', len(lines), 'zone prefix parity vectors')


if __name__ == '__main__':
    main(sys.argv[1])
