"""Build-bound import metadata from invented owned inputs and explicit ledgers."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import xmlb

import synth
from xml1build import common as C
from test_xml1_save_import import fixture, refused, file_hashes
from xml1build.save_import import source, tables


class Context:
    def __init__(self, **values):
        self.__dict__.update(values)


def owned_fixture(folder):
    build, src, dest, mapping, _ = fixture(folder)
    owned = Path(folder) / 'owned'
    (owned / 'data').mkdir(parents=True)
    (owned / 'default.xbe').write_bytes(synth.xbe())
    heroes = ET.Element('characters')
    for name in mapping['source']['hero_names']:
        hero = ET.SubElement(heroes, 'stats', name=name)
        ET.SubElement(hero, 'talent', name='sh_fight')
        if name == 'hero_a':
            ET.SubElement(hero, 'talent', name='a_one')
    (owned / 'data/herostat.eng').write_bytes(ET.tostring(heroes))
    items = ET.Element('items')
    for i in range(16):
        ET.SubElement(items, 'item', name='health_item' if i == 14 else f'item_{i}',
                      type='equipment' if i in (12, 13, 15) else ('health' if i == 14 else 'xp'))
    (owned / 'data/items.eng').write_bytes(ET.tostring(items))
    mappings = {k: copy.deepcopy(v) for k, v in mapping.items()
                if k not in ('schema', 'source', 'target_files', 'release_ready', 'acceptance', 'items', 'talents')}
    ledger = dict(schema=1, evidence=['invented-test-ledger/v1'], source_profile=copy.deepcopy(mapping['source']),
                  source_files=file_hashes(owned), native_talents={'0': 'sh_fight', '17': 'a_one'},
                  talent_files={}, source_maxima={str(i): 10 if i == 14 else 255 for i in range(16)},
                  pack_limits=dict(health=10, energy=10), mappings=mappings)
    ledger['source_profile'].pop('xbe_sha256')
    ledger_path = Path(folder) / 'private-ledger.json'
    ledger_path.write_text(json.dumps(ledger), encoding='ascii')
    storage = {'m:counter': dict(kind='pack', gamevar='x1v01', first_bit=1, nbits=5, signed=True),
               'g:global': dict(kind='pack', gamevar='x1g01', first_bit=1, nbits=32, signed=False)}
    context = Context(out=build, sources=SimpleNamespace(x1_xbox=owned),
                              x1_path=lambda name: owned / name,
                              research_json=lambda name: storage,
                              args=SimpleNamespace(experimental_save_import=True, import_ledger=str(ledger_path)))
    context.registry = C.Registry()
    for name in file_hashes(build):
        context.registry.record(name, 'invented-build')
    empty_base = Path(folder) / 'empty-base'
    empty_base.mkdir()
    context.base_index = C.FileIndex(empty_base)
    return context, ledger, ledger_path, owned, src, dest


def test_shipping_derives_owned_names_indices_and_binds_final_data():
    from xml1build.save_import import shipping
    with tempfile.TemporaryDirectory() as folder:
        ctx, ledger, _, owned, src, _ = owned_fixture(folder)
        before = file_hashes(owned)
        generated = shipping.from_owned_inputs(ctx)
        assert generated['schema'] == 2 and generated['release_ready'] is False
        assert generated['source']['xbe_sha256'] == source.digest((owned / 'default.xbe').read_bytes())
        assert generated['talents']['hero_a']['17'] == ['hero_a', 'a_one']
        assert '17' not in generated['talents']['hero_b']
        assert next(r for r in generated['items'] if r['source_index'] == 12)['target'] == 'belt_x'
        assert '_build/report.json' not in generated['target_files']
        path = ctx.out / tables.TABLE_REL
        path.write_text(json.dumps(generated), encoding='ascii')
        table = tables.ImportTable(ctx.out)
        from xml1build.save_import.command import decode_source
        from xml1build.save_import.mapper import map_campaign
        original = source.read_source(src)
        _, report, _ = map_campaign(decode_source(original, table), original, table, slot=0, allow_inferred=True)
        assert report['checkpoint'] == ledger['mappings']['checkpoints'][0]['name']
        assert file_hashes(owned) == before
        # The final report/INI are written after savefiles. Runtime checks still
        # bind both, while schema 2 pins all finished Data/Scripts at generation.
        record = ctx.out / '_build/report.json'
        record.write_text(json.dumps(dict(build=dict(save_layout='w2', loot='xml1', xp_curve='xml1'), seconds=42)))
        refused(table.recheck, 'CHANGED')
        tables.ImportTable(ctx.out)
        (ctx.out / 'Scripts/invented.py').write_text('changed = 1\n')
        refused(lambda: tables.ImportTable(ctx.out), 'BUILD')


def test_shipping_missing_evidence_changed_source_and_absent_checkpoint_refuse():
    from xml1build.save_import import shipping
    for change in ('evidence', 'checkpoint', 'source', 'roster'):
        with tempfile.TemporaryDirectory() as folder:
            ctx, ledger, path, owned, _, _ = owned_fixture(folder)
            if change == 'evidence':
                ledger['evidence'] = []
            elif change == 'checkpoint':
                ledger['mappings']['checkpoints'] = []
            elif change == 'source':
                (owned / 'data/items.eng').write_text('<items/>')
            else:
                ledger['source_profile']['hero_names'][0] = 'unknown_hero'
            path.write_text(json.dumps(ledger), encoding='ascii')
            before = file_hashes(Path(folder))
            refused(lambda: shipping.from_owned_inputs(ctx), 'BUILD')
            assert file_hashes(Path(folder)) == before


def test_shipping_writer_is_opt_in_and_uses_the_build_owned_writer():
    from xml1build.save_import import shipping
    with tempfile.TemporaryDirectory() as folder:
        ctx, _, _, _, _, _ = owned_fixture(folder)
        writes = []
        ctx.write_bytes = lambda rel, data, **kw: writes.append((rel, data, kw))
        ctx.note = lambda message: None
        ctx.args.experimental_save_import = False
        refused(lambda: shipping.run(ctx), 'UNVALIDATED')
        assert not writes
        ctx.args.experimental_save_import = True
        shipping.run(ctx)
        assert len(writes) == 1 and writes[0][0] == tables.TABLE_REL
        assert json.loads(writes[0][1])['schema'] == 2
        assert b'\r\n' not in writes[0][1]
        ctx.args.import_ledger = None
        shipping.run(ctx)
        assert len(writes) == 1


def test_shipping_variables_use_final_narrowing_and_refuse_zone_lifetimes():
    from xml1build.save_import import shipping
    with tempfile.TemporaryDirectory() as folder:
        ctx, ledger, path, _, _, _ = owned_fixture(folder)
        storage = {'m:stage': dict(kind='pack', gamevar='x1g02', first_bit=3, nbits=8, signed=True)}
        ctx.research_json = lambda name: storage
        ledger['mappings']['variables'] = [dict(family='mission', name='stage', scope='invented',
            kind='pack', target='stale', first_bit=1, width=32, signed=False, source_signed=True)]
        path.write_text(json.dumps(ledger), encoding='ascii')
        generated = shipping.from_owned_inputs(ctx)
        row = generated['variables'][0]
        assert (row['target'], row['first_bit'], row['width'], row['signed']) == ('x1g02', 3, 5, True)
        storage['m:stage']['kind'] = 'zone'
        refused(lambda: shipping.from_owned_inputs(ctx), 'BUILD')


def test_shipping_cli_refuses_unsafe_ledger_destinations_before_opening_logs():
    from test_builder_cli import run
    with tempfile.TemporaryDirectory() as folder:
        ledger = Path(folder) / 'private-ledger.json'
        ledger.write_text('invented private evidence', encoding='ascii')
        before = ledger.read_bytes()
        args = ['build', '--import-ledger', str(ledger), '--events', 'jsonl']
        code, events, _ = run(args)
        assert code == 2 and events[-2]['code'] == 'E_USAGE', events
        for options in (['--log', str(ledger)], ['--out', folder], ['--cache', folder]):
            code, events, _ = run(args + ['--experimental-save-import', *options])
            assert code == 2 and events[-2]['code'] == 'E_OUT_UNSAFE', events
            assert ledger.read_bytes() == before


def test_shipping_invalid_recipes_and_progression_refuse_before_publication():
    from xml1build.save_import import shipping
    for change in ('pose', 'xp', 'target'):
        with tempfile.TemporaryDirectory() as folder:
            ctx, ledger, path, _, _, _ = owned_fixture(folder)
            if change == 'pose':
                ledger['mappings']['checkpoints'][0]['anchor_pose'] = [0.] * 5
            elif change == 'xp':
                ledger['mappings']['xp_thresholds'] = [0, 100, 50]
            else:
                ledger['mappings']['checkpoints'][0]['target_zone'] = 'unknown/target'
            path.write_text(json.dumps(ledger), encoding='ascii')
            before = file_hashes(Path(folder))
            refused(lambda: shipping.from_owned_inputs(ctx), 'BUILD')
            assert file_hashes(Path(folder)) == before


def test_shipping_native_ids_and_item_indices_reject_numeric_aliases():
    from xml1build.save_import import shipping
    for field, key, value in (('native_talents', '017', 'sh_fight'), ('source_maxima', '012', 1)):
        with tempfile.TemporaryDirectory() as folder:
            ctx, ledger, path, _, _, _ = owned_fixture(folder)
            ledger[field][key] = value
            path.write_text(json.dumps(ledger), encoding='ascii')
            refused(lambda: shipping.from_owned_inputs(ctx), 'BUILD')


def test_shipping_rebuild_binds_files_that_survive_the_existing_sweep():
    from xml1build.save_import import shipping
    with tempfile.TemporaryDirectory() as folder:
        ctx, _, _, _, _, _ = owned_fixture(folder)
        stale = ctx.out / 'Data/obsolete-private-input.json'
        stale.write_text('{}', encoding='ascii')
        generated = shipping.from_owned_inputs(ctx)
        assert 'Data/obsolete-private-input.json' not in generated['target_files']
        (ctx.out / tables.TABLE_REL).write_text(json.dumps(generated), encoding='ascii')
        # Exercise the actual builder cleanup consumer, then the actual importer.
        removed = C.sweep_stale(ctx.out, ctx.base_index, ctx.registry, log=lambda text: None, keep_proxy=True)
        assert 'Data/obsolete-private-input.json' in removed
        tables.ImportTable(ctx.out)


def test_shipping_source_profiles_share_the_reader_validation():
    from xml1build.save_import import shipping
    for change in ('id', 'kind', 'definition'):
        with tempfile.TemporaryDirectory() as folder:
            ctx, ledger, path, _, _, _ = owned_fixture(folder)
            profile = ledger['source_profile']
            if change == 'id':
                profile.pop('id')
            elif change == 'kind':
                profile['kind'] = 'unknown'
            else:
                profile['kind'] = 'recomp'
                profile['definitions'] = {str(i + 1): n for i, n in enumerate(profile['hero_names'])}
                profile['definitions']['01'] = profile['definitions'].pop('1')
            path.write_text(json.dumps(ledger), encoding='ascii')
            refused(lambda: shipping.from_owned_inputs(ctx), 'BUILD')


def test_shipping_target_only_defaults_are_required_and_native_validated():
    from xml1build.save_import import shipping, mapper
    from test_xml1_save_import import refresh_bindings, _xmlb
    with tempfile.TemporaryDirectory() as folder:
        ctx, ledger, path, _, _, _ = owned_fixture(folder)
        stats = xmlb.decode((ctx.out / 'Data/herostat.engb').read_bytes())
        ET.SubElement(stats, 'stats', name='target_pad', skin='0101')
        _xmlb(str(ctx.out / 'Data/herostat.engb'), stats)
        old = json.loads((ctx.out / tables.TABLE_REL).read_text())
        refresh_bindings(ctx.out, old)
        for name in file_hashes(ctx.out):
            ctx.registry.record(name, 'invented-build')
        refused(lambda: shipping.from_owned_inputs(ctx), 'BUILD')
        ledger['mappings']['target_defaults'] = {'target_pad': {'level': 1}}
        path.write_text(json.dumps(ledger), encoding='ascii')
        refused(lambda: shipping.from_owned_inputs(ctx), 'BUILD')
        from lcsave import convert, keys
        environment = convert.Environment(str(ctx.out), catalogue=tables.installed_catalogue(
            (ctx.out / 'Data/lcsave/catalogue.lcc').read_bytes()))
        def resolve(domain, *fields):
            return environment.id_of(domain, keys.key_hash(*fields))
        default = mapper.defaults(mapper.container.RECORDS['HREC'])
        default.update(level=1, ack_level=1, player_seat=-1, talents=[], equipped=[], powers=[],
                       costume=resolve('COST', 'target_pad', 'skin'),
                       costumes_unlocked=[resolve('COST', 'target_pad', 'skin')])
        ledger['mappings']['target_defaults']['target_pad'] = default
        path.write_text(json.dumps(ledger), encoding='ascii')
        generated = shipping.from_owned_inputs(ctx)
        assert generated['target_defaults']['target_pad']['hero'] == resolve('STAT', 'target_pad')
        (ctx.out / tables.TABLE_REL).write_text(json.dumps(generated), encoding='ascii')
        equipment = mapper._instance(tables.ImportTable(ctx.out), 'belt_x', 0)
        ledger['mappings']['target_defaults']['target_pad']['equipped'] = [equipment] * 4
        path.write_text(json.dumps(ledger), encoding='ascii')
        refused(lambda: shipping.from_owned_inputs(ctx), 'BUILD')
        ledger['mappings']['target_defaults']['target_pad']['equipped'] = []
        for powers in ([dict(button=4, name='power1', flags=1)],
                       [dict(button=0, name='power1', flags=1)] * 2):
            ledger['mappings']['target_defaults']['target_pad']['powers'] = powers
            path.write_text(json.dumps(ledger), encoding='ascii')
            refused(lambda: shipping.from_owned_inputs(ctx), 'BUILD')
        ledger['mappings']['target_defaults']['target_pad']['powers'] = []
        ledger['mappings']['target_defaults']['target_pad']['costume'] = resolve('COST', 'hero_a', 'skin')
        path.write_text(json.dumps(ledger), encoding='ascii')
        refused(lambda: shipping.from_owned_inputs(ctx), 'BUILD')


def test_shipping_recomp_definition_ids_survive_sorted_json_keys():
    from xml1build.save_import import shipping
    with tempfile.TemporaryDirectory() as folder:
        ctx, ledger, path, _, _, _ = owned_fixture(folder)
        profile = ledger['source_profile']
        profile['kind'] = 'recomp'
        profile['definitions'] = {str(i + 1): name for i, name in enumerate(profile['hero_names'])}
        path.write_text(json.dumps(ledger), encoding='ascii')
        generated = shipping.from_owned_inputs(ctx)
        (ctx.out / tables.TABLE_REL).write_text(json.dumps(generated, sort_keys=True), encoding='ascii')
        table = tables.ImportTable(ctx.out)
        assert table.definitions[2] == profile['hero_names'][1]
        assert table.definitions[10] == profile['hero_names'][9]
