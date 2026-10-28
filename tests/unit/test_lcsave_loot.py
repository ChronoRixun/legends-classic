"""Loot step 1, save side (DESIGN 8.3, offline part): an old save of the legacy item table loads in a build that carries
the first game's economy - legacy gear, quantities and obtained flags intact -, a Danger Room reward instance gets
the definition's rebuilt own list (the lcsave reference of the own_rebuilt migration), and definitions over 160 /
enhancement records over 512 round-trip in the W2 layout. Invented build, invented saves: no game data."""
import copy
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import xmlb
from test_lcsave import ITEMS, _era_model, make_build, make_old_save
from test_lcsave_native_layout import registry_fixture, typed_old_save
from lcsave import binds, catalogue as CAT, container, convert, keys, layout as L, legacy, oldsave
from xml1build import loot as LOOT

NEW_ITEMS = 175                       # 4 + 175 + 6 keys = 185 definitions, as the economy's table
REBUILT = 'glove_x'                   # the legacy definition whose own bonuses are converted again in place


def _items_path(folder):
    return os.path.join(folder, 'Data', 'items.engb')


def make_loot_build(folder):
    """the legacy synthetic build, then the economy's changes to its item table: one legacy definition gets a new own
    list (3 records instead of 1) and 175 definitions with 3 own records each are appended after the keys"""
    make_build(folder, items=ITEMS)
    p = _items_path(folder)
    root = xmlb.decode(open(p, 'rb').read())
    glove = next(e for e in root if e.tag == 'item' and e.get('name') == REBUILT)
    for e in glove.findall('enhancement'):
        glove.remove(e)
    for k in range(3):
        ET.SubElement(glove, 'enhancement', powerup=f'rebuilt{k}')
    for n in range(NEW_ITEMS):
        it = ET.SubElement(root, 'item', name=f'lc_x1_n{n:03d}', type='equipment', **{'class': 'gloves'})
        for k in range(3):
            ET.SubElement(it, 'enhancement', powerup=f'new{k}')
    open(p, 'wb').write(xmlb.encode(root))
    return folder


def loot_env(d):
    legacy_dir = make_build(os.path.join(d, 'legacy'), items=ITEMS)
    loot_dir = make_loot_build(os.path.join(d, 'loot'))
    lb, nb = binds.Binds(legacy_dir), binds.Binds(loot_dir)
    model = _era_model(lb, lb)
    cat = CAT.Catalogue()
    for cv in ('13', '5'):
        cat.update(CAT.tables_from_hashes(legacy.Era(model, cv).tables), 13)
    # what loot.derived_catalogue does to the master: append the build's new keys, mark the rebuilt definitions
    cat.extend(CAT.tables_from_hashes(nb.hash_tables(include_conversation_digest=False)), 14)
    cat.set_attribute_bits('ITEM', keys.key_hash(REBUILT), CAT.ITEM_OWN_REBUILT)
    ep = os.path.join(d, 'eras.json')
    with open(ep, 'w') as f:
        json.dump(model, f)
    return convert.Environment(loot_dir, eras_path=ep, catalogue=cat), lb, nb, loot_dir


def test_the_loot_build_is_over_both_retail_limits():
    with tempfile.TemporaryDirectory() as d:
        env, lb, nb, _ = loot_env(d)
        assert len(lb.item) == 10 and len(nb.item) == 10 + NEW_ITEMS and len(nb.item) > 160
        assert len(nb.enhancement) > 512 and len(lb.enhancement) < 20
        # the legacy definitions keep their positions; the new ones follow the keys
        assert nb.item[:10] == lb.item and nb.item[10] == 'lc_x1_n000'
        assert nb.item_own[1] == [6, 7, 8] and lb.item_own[1] == [6]               # the rebuilt definition: three records now
        assert nb.item_own[3] != lb.item_own[3]                                      # the records after it moved


def test_an_old_save_loads_with_legacy_gear_quantities_and_obtained_flags():
    with tempfile.TemporaryDirectory() as d:
        env, lb, nb, _ = loot_env(d)
        _, _, reg = registry_fixture(d)
        m = typed_old_save(len(lb.item))
        # obtained flags / quantities by legacy definition index: a unique flagged as obtained, the potion held thrice
        m['items']['def_state'][0:2] = [0, 1]
        m['items']['def_state'][2 * 5:2 * 5 + 2] = [4, 1]                            # KEY2: quantity 4, flag set
        raw = oldsave.write_slot(m)
        res = convert.convert_slot(raw, 'beta7.save', env, now=0)
        assert res.refused is None, res.refused
        model, _ = convert.reverse_slot(res.file_bytes, env, native=L.W2, registry=reg)
        assert model['items']['def_count'] == len(nb.item)
        # the legacy definitions keep their positions, so quantity and flag come back at the same indices
        assert model['items']['def_state'][0:2] == [0, 1] and model['items']['def_state'][4:6] == [3, 0]
        assert model['items']['def_state'][10:12] == [4, 1]
        assert all(v == 0 for v in model['items']['def_state'][2 * len(lb.item):2 * len(nb.item)])      # nothing obtained among the new
        # equipped legacy gear: a definition the economy did not rebuild keeps its own list (record 4 is belt_x e1)
        eq = model['heroes'][0]['equipment']['equipped'][0]
        assert eq['definition'] == 0 and [(e['record'], e['value']) for e in eq['own']] == [(4, 7)]
        assert eq['prefixes'] and eq['location'] == 1
        # a definition after the rebuilt one: its record moved from 7 to 9 and its value is untouched
        world = model['items']['world'][0]['instance']
        assert world['definition'] == 3 and [e['record'] for e in world['own']] == [nb.item_own[3][0]]
        assert world['own'][0]['value'] == 1
        carried = model['items']['carried']
        assert carried[0]['definition'] == 2 and carried[0]['own'] == []


def test_a_rebuilt_reward_instance_gets_the_rebuilt_own_list():
    with tempfile.TemporaryDirectory() as d:
        env, lb, nb, _ = loot_env(d)
        _, _, reg = registry_fixture(d)
        raw = oldsave.write_slot(typed_old_save(len(lb.item)))
        res = convert.convert_slot(raw, 'beta7.save', env, now=0)
        assert res.refused is None, res.refused
        model, _ = convert.reverse_slot(res.file_bytes, env, native=L.W2, registry=reg)
        glove = next(i for i in model['items']['carried'] if i['definition'] == 1)
        assert [e['record'] for e in glove['own']] == nb.item_own[1] == [6, 7, 8]       # the definition's current list
        assert [e['value'] for e in glove['own']] == [0, 0, 0]                      # fixed interpolation
        assert [e['record'] for e in glove['suffixes']] == [2]                            # affixes of the instance stay
        assert env.catalogue.attributes_of(env.catalogue.lookup('ITEM', keys.key_hash(REBUILT))) & CAT.ITEM_OWN_REBUILT
        belt = next(i for i in model['items']['carried'] if i['definition'] == 0)
        assert [e['record'] for e in belt['own']] == [5]                                  # another definition: unchanged


def shrunk_env(d, rebuilt=True):
    """like loot_env, but the rebuilt definition's list SHRANK: one legacy record (glove_x e1), none in the new table
    (the shape of the three Shiar rewards; Goddess Medallion and Phoenix Mantle lose their third record)"""
    legacy_dir = make_build(os.path.join(d, 'legacy'), items=ITEMS)
    loot_dir = make_build(os.path.join(d, 'loot'), items=ITEMS)
    p = _items_path(loot_dir)
    root = xmlb.decode(open(p, 'rb').read())
    glove = next(e for e in root if e.tag == 'item' and e.get('name') == REBUILT)
    for e in glove.findall('enhancement'):
        glove.remove(e)
    open(p, 'wb').write(xmlb.encode(root))
    lb, nb = binds.Binds(legacy_dir), binds.Binds(loot_dir)
    model = _era_model(lb, lb)
    cat = CAT.Catalogue()
    for cv in ('13', '5'):
        cat.update(CAT.tables_from_hashes(legacy.Era(model, cv).tables), 13)
    cat.extend(CAT.tables_from_hashes(nb.hash_tables(include_conversation_digest=False)), 14)
    if rebuilt:
        cat.set_attribute_bits('ITEM', keys.key_hash(REBUILT), CAT.ITEM_OWN_REBUILT)
    ep = os.path.join(d, 'eras.json')
    with open(ep, 'w') as f:
        json.dump(model, f)
    return convert.Environment(loot_dir, eras_path=ep, catalogue=cat), lb, nb


def test_a_rebuilt_reward_whose_list_shrank_still_loads_with_the_current_list():
    # An old instance names records the new item table no longer has (Goddess Medallion 3 -> 2, the Shiar items 1 -> 0).
    # The migration replaces the list, so those ids must never be resolved: before this fix the load was refused with
    # "enhancement: id ... is not in this build (parked / unknown)".
    with tempfile.TemporaryDirectory() as d:
        env, lb, nb = shrunk_env(d)
        assert lb.item_own[1] == [6] and nb.item_own[1] == []
        raw = oldsave.write_slot(make_old_save(def_count=len(lb.item)))
        res = convert.convert_slot(raw, 'beta7.save', env, now=0)
        assert res.refused is None, res.refused
        model, _ = convert.reverse_slot(res.file_bytes, env)
        glove = next(i for i in model['items']['carried'] if i['definition'] == 1)
        assert glove['own'] == [] and [e['record'] for e in glove['suffixes']] == [2]       # affixes of the instance stay
        belt = next(i for i in model['items']['carried'] if i['definition'] == 0)
        assert [e['record'] for e in belt['own']] == [5]                                    # another definition: unchanged


def test_the_shrunk_list_without_the_rebuilt_mark_is_still_refused():
    # negative control: the guard is the catalogue attribute, not a general tolerance for unknown records
    with tempfile.TemporaryDirectory() as d:
        env, lb, nb = shrunk_env(d, rebuilt=False)
        raw = oldsave.write_slot(make_old_save(def_count=len(lb.item)))
        res = convert.convert_slot(raw, 'beta7.save', env, now=0)
        if res.refused is not None:                     # the converter itself may already refuse an unknown record
            assert 'enhancement' in res.refused or 'not in' in res.refused or 'parked' in res.refused
            return
        try:
            convert.reverse_slot(res.file_bytes, env)
            raise AssertionError('an unknown own record was accepted on a definition that is not rebuilt')
        except convert.ConvertError as e:
            assert 'parked / unknown' in str(e) or 'not in' in str(e)


def test_definitions_over_160_and_records_over_512_round_trip_in_the_w2_layout():
    with tempfile.TemporaryDirectory() as d:
        env, lb, nb, _ = loot_env(d)
        root, reg_path, reg = registry_fixture(d)
        raw = oldsave.write_slot(typed_old_save(len(lb.item)))
        legacy_file = convert.convert_slot(raw, 'beta7.save', env, now=0).file_bytes
        model, _ = convert.reverse_slot(legacy_file, env, native=L.W2, registry=reg)
        captures = convert.loaded_zone_metadata(legacy_file, env, native=L.W2, registry=reg)
        m = copy.deepcopy(model)
        last = len(nb.item) - 1                                                  # definition 184: over 160
        high = len(nb.enhancement) - 3                                           # records over 512
        assert last > 160 and high > 512
        bare = dict(copy.deepcopy(m['items']['carried'][0]), prefixes=[], suffixes=[])
        bare.update(definition=last, name_a=0xff, name_b=0xff, special=0xff,
                    own=[dict(record=high + k, value=0) for k in range(3)])
        m['items']['carried'].append(bare)
        m['items']['def_state'][2 * last:2 * last + 2] = [2, 1]
        stream = oldsave.write_slot(m, L.W2)
        r = convert.old_stream_to_new(stream, env, retained_file=legacy_file, zone_captures=captures,
                                      require_capture_metadata=True, campaign_serial=17, save_sequence=2, now=0,
                                      native=L.W2)
        assert r.refused is None, r.refused
        back, _ = convert.reverse_slot(r.file_bytes, env, native=L.W2, registry=reg)
        inst = next(i for i in back['items']['carried'] if i['definition'] == last)
        assert [e['record'] for e in inst['own']] == [high, high + 1, high + 2] and inst['own'][0]['record'] > 512
        assert back['items']['def_state'][2 * last:2 * last + 2] == [2, 1]
        assert oldsave.write_slot(back, L.W2) == oldsave.write_slot(oldsave.read_slot(oldsave.write_slot(back, L.W2), L.W2), L.W2)


def test_derived_catalogue_appends_the_builds_keys_marks_the_rebuilt_and_never_touches_the_master():
    master = CAT.CATALOGUE_FILE
    before = open(master, 'rb').read()
    with tempfile.TemporaryDirectory() as d:
        loot_dir = make_loot_build(os.path.join(d, 'loot'))
        os.makedirs(os.path.join(loot_dir, '_build'), exist_ok=True)
        with open(os.path.join(loot_dir, '_build', LOOT.REPORT_META), 'w') as f:
            json.dump({'rebuilt': [REBUILT]}, f)
        cat = LOOT.derived_catalogue(loot_dir, 99)
        base = CAT.Catalogue.load()
        assert cat.revision == base.revision + 1 and cat.data['content_version'] == 99
        item = cat.lookup('ITEM', keys.key_hash(REBUILT))
        new = cat.lookup('ITEM', keys.key_hash('lc_x1_n000'))
        assert item and new and cat.attributes_of(item) == CAT.ITEM_OWN_REBUILT and cat.attributes_of(new) == 0
        assert len(cat.data['domains']['ITEM']['entries']) > len(base.data['domains']['ITEM']['entries'])
        # ids are assigned in table order after the master's last serial: the same ids a release that commits the
        # appended catalogue (python -m lcsave catalogue --append-only) would give
        serials = [cat.lookup('ITEM', keys.key_hash(f'lc_x1_n{n:03d}')) for n in range(3)]
        assert [keys.id_serial(s) for s in serials] == [keys.id_serial(serials[0]) + i for i in range(3)]
        assert keys.id_serial(serials[0]) >= base.data['domains']['ITEM']['next']
    assert open(master, 'rb').read() == before
