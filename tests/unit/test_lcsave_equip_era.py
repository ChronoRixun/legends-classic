"""Mixed talent/item eras and explicit restore-bank ownership, invented fixtures only."""
import copy
import json
import os
import tempfile
from test_lcsave import make_build, make_old_save, _era_model, _attr, _equip, _instance, ITEMS
from lcsave import binds, catalogue, legacy, convert, container, oldsave, keys, dump


def mixed_fixture(folder, restore=False):
    ref = binds.Binds(make_build(os.path.join(folder, 'build')))
    old = binds.Binds(make_build(os.path.join(folder, 'old'),
        shared=['sh_fight', 'sh_might', 'sh_acro', 'sh_tough'],
        items=[ITEMS[0], ITEMS[2], ITEMS[1], ITEMS[3]],
        zone_entities=[('gate', ['gate01', 'gate02']), ('crate', ['crate01']),
                       ('spawner_a', ['sp01']), ('crate_pinned', ['crate02']), ('spot', ['spot01'])]))
    model = _era_model(ref, old)
    cat = catalogue.Catalogue()
    for era in legacy.eras_of(model):
        cat.update(catalogue.tables_from_hashes(era.tables), 13)
    ep, cp = os.path.join(folder, 'eras.json'), os.path.join(folder, 'cat.json')
    with open(ep, 'w') as f:
        json.dump(model, f)
    cat.save(cp)
    env = convert.Environment(ref.build, eras_path=ep, catalogue_path=cp)
    native = make_old_save(shared_ids=(0, 2, 3), def_count=len(ref.item))
    # The writer's glove definition/own record belonged to the potion in the start era.
    moved = _instance(1, own=[(6, 17)], location=1)
    native['heroes'][0]['equipment']['equipped'] = [] if restore else [moved]
    if restore:
        native['restore'][1] = dict(attributes=_attr(talents=[(2, 3)]), equipment=_equip([moved]))
        native['restore_flag'] = 1
    return env, native


def test_equipped_items_use_writer_era_in_hero_and_restore_bank():
    for restore in (False, True):
        with tempfile.TemporaryDirectory() as folder:
            env, native = mixed_fixture(folder, restore)
            result = convert.convert_slot(oldsave.write_slot(native), 'synthetic.save', env, now=0)
            assert result.refused is None, result.refused
            assert (result.era['start'], result.era['items']) == (5, 13)
            f = container.read_file(result.file_bytes)
            record = (f['sections']['REST']['data']['records'][0] if restore
                      else f['sections']['HERO']['data']['heroes'][0])
            item = record['equipped'][0]
            assert item['definition'] == env.id_of('ITEM', keys.key_hash('glove_x'))
            assert item['own'][0]['value'] == 17
            before = dump.dump_old(oldsave.read_slot(oldsave.write_slot(native)), env, result.era)
            after = dump.dump_new(result.file_bytes, env)
            before_record = before['restore']['records']['1'] if restore else before['heroes'][0]
            after_record = after['restore']['records']['1'] if restore else after['heroes'][0]
            assert before_record['equipped'] == after_record['equipped']
            back, _ = convert.reverse_slot(result.file_bytes, env)
            equipment = back['restore'][1]['equipment'] if restore else back['heroes'][0]['equipment']
            assert equipment['equipped'][0]['definition'] == 1
            assert equipment['equipped'][0]['own'] == [dict(record=6, value=17)]


def test_restore_slot_16_evidence_belongs_to_stats_index_16():
    # Invented analogue of the audit: stats 16 and 17 hold different era positions.
    from types import SimpleNamespace
    stats = [None] + [keys.key_hash('owner_' + str(i)) for i in range(1, 22)]
    ids = [1, 9, 10, 59, 60]
    def era(cv, owner):
        return SimpleNamespace(cv=cv, hero_shared_holdable={stats[owner]: ids},
                               table=lambda domain: list(range(61)))
    native = dict(heroes=[dict(attributes=_attr()) for _ in range(21)],
                  restore=[dict(attributes=_attr()) for _ in range(22)])
    native['restore'][16]['attributes'] = _attr(talents=[(i, 1) for i in ids])
    selected, evidence = legacy.talent_era(native, [era(13, 17), era(12, 16)], stats)
    assert selected.cv == 12 and evidence['explained'] == 5, evidence
    # Main block 15 and restore 16 merge under their common stats index.
    native['heroes'][15]['attributes'] = copy.deepcopy(native['restore'][16]['attributes'])
    held = legacy.shared_ids_by_hero(native)
    assert held[16] == set(ids) and sum(map(len, held.values())) == 5
