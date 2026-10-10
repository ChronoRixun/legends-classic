"""lcsave (the LC save format and the old-save converter): invented data only - a tiny synthetic build written as
XMLB, synthetic old saves built from the layout tables, synthetic era models. Names are made up ("hero_a",
"zone/x/y") and never game text."""
import json
import os
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import xmlb  # noqa: E402
from lcsave import keys, layout as L, oldsave, binds, catalogue as catmod, legacy, container, convert, dump  # noqa: E402


# ------------------------------------------------------------------------------------------------ keys
def test_keys_canonical_and_ids():
    assert keys.canonical_key('Hero_A', 'Skin_60s') == b'hero_a/skin_60s'
    assert keys.canonical_key('a/b', '50%') == b'a%2fb/50%25'
    assert keys.key_hash('x') == keys.key_hash('X')
    assert len(keys.key_hash('x')) == 64
    v = keys.make_id(7, 300)
    assert keys.id_domain(v) == 7 and keys.id_serial(v) == 300 and not keys.is_keyref(v)
    r = keys.make_keyref(5)
    assert keys.is_keyref(r) and keys.id_domain(r) == 0
    assert keys.crc32(b'123456789') == 0xcbf43926           # the CRC-32 check value
    for bad in ((0, 1), (128, 1), (1, 0), (1, 0x1000000)):
        try:
            keys.make_id(*bad)
            assert False, bad
        except ValueError:
            pass


# ------------------------------------------------------------------------------------------------ layout
def test_layout_struct_roundtrip_and_sizes():
    lay = (('a', 'u8', 1), ('b', 'u16', 2), ('c', 'cstr', 6), ('d', 'f32', 1), ('e', 'bytes', 3))
    assert L.size_of(lay) == 1 + 4 + 6 + 4 + 3
    v = dict(a=7, b=[1, 65535], c='hi', d=1.5, e=b'xyz')
    raw = L.write_struct(v, lay)
    back, end = L.read_struct(raw, 0, lay)
    assert end == len(raw) and back['a'] == 7 and back['b'] == [1, 65535] and back['c'] == 'hi' and back['d'] == 1.5
    assert back['c_raw'] == b'hi\0\0\0\0'
    back['c_raw'] = b'hi\0ZZ\0'                       # bytes after the NUL are kept while the text matches
    assert L.write_struct(back, lay)[5:11] == b'hi\0ZZ\0'
    try:
        L.read_struct(raw[:-1], 0, lay)
        assert False
    except ValueError:
        pass
    assert L.size_of(L.NEW_HEADER) == 0x88 and L.size_of(L.OLD_ZONE_RECORD_TAIL) + 4 + 768 * 0x18 == 0x55e0


# ------------------------------------------------------------------------------------------------ synthetic build
HEROES = ['hero_a', 'hero_b']
NPCS = ['npc_a', 'npc_b', 'npc_c']
SHARED = ['sh_fight', 'sh_might', 'sh_boss', 'sh_acro', 'sh_tough']
HERO_TAL = {'hero_a': ['a_one', 'a_two', 'a_three'], 'hero_b': ['b_one', 'b_two']}
ITEMS = [('belt_x', 'belt', 2), ('glove_x', 'gloves', 1), ('potion_x', None, 0), ('armor_x', 'armor', 1)]


def _xmlb(path, root):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(xmlb.encode(root))


def make_build(folder, shared=SHARED, items=ITEMS, zone_entities=None, hero_extra_talent=None):
    D = os.path.join(folder, 'Data')
    hs = ET.Element('characters')
    for h in HEROES:
        e = ET.SubElement(hs, 'stats', name=h, skin='0101', skin_60s='02', skin_future='03')
        for t in HERO_TAL[h] + ['sh_fight', 'sh_acro', 'sh_tough'] + ([hero_extra_talent] if hero_extra_talent else []):
            ET.SubElement(e, 'talent', name=t, level='1')
    _xmlb(os.path.join(D, 'herostat.engb'), hs)
    ns = ET.Element('characters')
    for n in NPCS:
        ET.SubElement(ns, 'stats', name=n)
    _xmlb(os.path.join(D, 'npcstat.engb'), ns)
    sh = ET.Element('talents')
    for n in shared:
        ET.SubElement(sh, 'talent', name=n)
    _xmlb(os.path.join(D, 'shared_talents.engb'), sh)
    for h, lst in HERO_TAL.items():
        r = ET.Element('talents')
        for n in lst:
            ET.SubElement(r, 'talent', name=n)
        _xmlb(os.path.join(D, 'talents', h + '.engb'), r)
    inv = ET.Element('inventory')
    pre = ET.SubElement(inv, 'prefixes')
    for g in ('p_one', 'p_two'):
        ET.SubElement(pre, 'enhancement', groupname=g, enemy_level='1')
    suf = ET.SubElement(inv, 'suffixes')
    ET.SubElement(suf, 'enhancement', groupname='s_one', enemy_level='1')
    names = ET.SubElement(inv, 'ItemNames')
    ET.SubElement(names, 'rare', name='rare_a')
    cn = ET.SubElement(inv, 'ClassNames')
    ET.SubElement(cn, 'RareClass', **{'class': 'belt', 'name': 'cls_belt_a'})
    tr = ET.SubElement(inv, 'tr_item', displayname='special')
    ET.SubElement(tr, 'require', item='belt_x')
    ET.SubElement(tr, 'enhancement', powerup='x')
    for name, cls, nown in items:
        attrs = {'name': name, 'type': 'equipment' if cls else 'potion'}
        if cls:
            attrs['class'] = cls
        it = ET.SubElement(inv, 'item', **attrs)
        for k in range(nown):
            ET.SubElement(it, 'enhancement', powerup=f'own{k}')
    for n in ('KEY1', 'KEY2', 'KEY3', 'KEYCARD1', 'KEYCARD2', 'KEYCARD3'):
        ET.SubElement(inv, 'item', name=n, type='item')
    _xmlb(os.path.join(D, 'items.engb'), inv)
    ms = ET.Element('missions')
    ET.SubElement(ms, 'mission', file='data/missions/act_x.xmlb')
    _xmlb(os.path.join(D, 'missions', 'missions.XMLB'), ms)
    act = ET.Element('MISSIONS')
    m = ET.SubElement(act, 'MISSION', name='m1')
    for o in ('obj_a', 'obj_b', 'obj_c'):
        ET.SubElement(m, 'OBJECTIVE', name=o)
    ET.SubElement(m, 'OBJECTIVE')                           # an unnamed objective
    _xmlb(os.path.join(D, 'missions', 'act_x.engb'), act)
    dr = ET.Element('dangerroom')
    g = ET.SubElement(dr, 'GRADE', name='grade_a')
    for c in ('course_a', 'course_b'):
        ET.SubElement(g, 'COURSE', name=c)
    ET.SubElement(dr, 'ARENA', zone='dr/arena_a')
    _xmlb(os.path.join(D, 'dangerroom.engb'), dr)
    rv = ET.Element('review')
    for t, n in (('load', 'l1'), ('load', 'l2'), ('cin', 'c1'), ('concept', 'k1')):
        ET.SubElement(rv, 'item', type=t, name=n, value='v')
    _xmlb(os.path.join(D, 'review_paths.engb'), rv)
    xp = ET.Element('xpoints')
    ET.SubElement(xp, 'xpoint', zone='zone/x/y', name='centre_a')
    _xmlb(os.path.join(D, 'xtraction_points.engb'), xp)
    tv = ET.Element('trivia')
    for a in ('1', '1', '2'):
        ET.SubElement(tv, 'question', act=a, text='q')
    _xmlb(os.path.join(D, 'trivia.engb'), tv)
    zi = ET.Element('zoneinfo')
    for z in ('zone/x/y', 'zone/x/z'):
        ET.SubElement(zi, 'zone', name=z)
    _xmlb(os.path.join(D, 'zoneinfo.engb'), zi)
    os.makedirs(os.path.join(folder, 'Conversations'), exist_ok=True)
    open(os.path.join(folder, 'Conversations', 'c.engb'), 'wb').write(b'conv')
    pkg = ET.Element('packagedef'); ET.SubElement(pkg, 'xml', filename='conversations/c')
    for name in ('y.pkgb', 'z.pkgb'):
        _xmlb(os.path.join(folder, 'Packages', 'generated', 'maps', 'zone', 'x', name), pkg)
    # the zone: definitions and placed instances
    w = ET.Element('world')
    defs = [('gate', 'gameent', {}), ('crate', 'physent', {}), ('crate_pinned', 'physent', {'smartent': 'false'}),
            ('spawner_a', 'monsterspawnerent', {}), ('spawner_b', 'monsterspawnerent', {'monster_smartent': 'true', 'instantspawn': 'true'}),
            ('lamp', 'lightent', {}), ('spot', 'ent', {})]
    for name, cls, extra in defs:
        ET.SubElement(w, 'entity', name=name, classname=cls, **extra)
    for t, insts in (zone_entities or [('gate', ['gate01', 'gate02']), ('crate', ['crate01']), ('crate_pinned', ['crate02']),
                                       ('spawner_a', ['sp01']), ('spawner_b', ['sp02']), ('lamp', ['lamp01']), ('spot', ['spot01'])]):
        ei = ET.SubElement(w, 'entinst', type=t)
        for n in insts:
            ET.SubElement(ei, 'inst', name=n)
    _xmlb(os.path.join(folder, 'Maps', 'zone', 'x', 'y.engb'), w)
    return folder


def test_binds_numbering_rule_and_keys():
    with tempfile.TemporaryDirectory() as d:
        b = binds.Binds(make_build(d))
        z = b.zone_numbering('zone/x/y')
        # gameent numbered, physent only when smartent="false", spawner numbered unless (monster_smartent and
        # instantspawn and not checkteam), lightent smart by default, plain ent numbered
        assert [(t, n) for t, n, _ in z['numbered']] == [('gate', 'gate01'), ('gate', 'gate02'), ('crate_pinned', 'crate02'),
                                                          ('spawner_a', 'sp01'), ('spot', 'spot01')]
        assert [p for _, _, p in z['numbered']] == [0, 1, 3, 4, 7]
        assert z['problems'] == []
        assert b.stat == [None, 'hero_a', 'hero_b', 'npc_a', 'npc_b', 'npc_c'] and b.hero_count == 2
        assert b.key_talent(3) == ('shared', 'sh_acro') and b.key_talent(201) == ('hero_a', 'a_two') and b.key_talent(299) is None
        assert b.key_costume('hero_a', 3) == ('hero_a', 'skin_60s') and b.costume['hero_a'] == {0: 'skin', 3: 'skin_60s', 6: 'skin_future'}
        assert b.prefix_range == (0, 2) and b.suffix_range == (2, 3) and b.trit_range == (3, 4)
        assert b.item_own[0] == [4, 5] and b.item_own[1] == [6] and b.item_own[2] == [] and b.enhancement[6] == ('i', 'glove_x', 'e1')
        assert b.objective == [('act_x', 'obj_a'), ('act_x', 'obj_b'), ('act_x', 'obj_c'), ('act_x', 'o1')]
        assert b.review[(0, 1)] == ('load', 'l2') and b.review[(1, 0)] == ('cin', 'c1') and b.review[(3, 0)] == ('concept', 'k1')
        assert b.key_trivia(1, 1) == ('1', 'q2') and b.key_trivia(2, 0) == ('2', 'q1')
        T = b.hash_tables()
        assert T['ENHC_ranges'] == {'prefix': [0, 2], 'suffix': [2, 3], 'trit': [3, 4]} and len(T['conversation_digest']) == 64


# ------------------------------------------------------------------------------------------------ synthetic old save
def _instance(d, own=(), prefixes=(), suffixes=(), name_a=0xff, name_b=0xff, special=0xff, location=2):
    return dict(definition=d, name_a=name_a, name_b=name_b, special=special, location=location,
                prefixes=[dict(record=r, value=v) for r, v in prefixes], own=[dict(record=r, value=v) for r, v in own],
                suffixes=[dict(record=r, value=v) for r, v in suffixes])


def _attr(level=1, talents=()):
    a = dict(trait_base=[1, 1, 1, 1], trait_pending=[0] * 4, trait_bonus=[0] * 4, trait_bonus2=[0] * 4, skill_points=0,
             trait_points=0, level=level, ai_level=1, ai_attack=0, pad17=0)
    ents = [dict(id=i, rank_bits=r | 0x40, pending_cap_bits=0, base_bits=1 | 0x2c, byte5=0, pad6=0) for i, r in talents]
    ents.sort(key=lambda e: e['id'])
    a['count'] = len(ents); a['bitmap'] = (1 << len(ents)) - 1
    ents += [dict(id=0, rank_bits=0, pending_cap_bits=0, base_bits=0, byte5=0, pad6=0) for _ in range(L.OLD_TALENT_ENTRIES - len(ents))]
    a['talents'] = ents
    return a


def _equip(items=(), xp=0):
    return dict(equipped=list(items), health=0.0, energy=0.0, player_seat=-1, vitals_valid=0, pad0d=[0, 0, 0], experience=xp,
                ack_level=1, health_boosts=0, energy_boosts=0, levels_purchased=0, points_bought=0, respec_count=0,
                skirmish_boost=0, flags=0)


def _snapshot(zone='', names=('', '', '', ''), objectives=None):
    s = convert._empty_snapshot()
    s['zone'] = zone; s['seat_names'] = list(names)
    if objectives:
        for i, v in objectives.items():
            s['objectives'][i] = v
    return s


def make_old_save(shared_ids=(0, 3, 4), def_count=10, zone=True, costume_mask=3, power_flags=(1, 1, 1, 1)):
    """an old slot model for the synthetic build (hero 0 = hero_a holds shared ids and own talents)"""
    heroes = [dict(attributes=_attr(5, [(shared_ids[0], 2), (shared_ids[1], 3), (shared_ids[2], 1), (200, 4), (202, 1)]),
                   equipment=_equip([_instance(0, own=[(4, 7)], prefixes=[(1, 9)], location=1)], xp=1234),
                   powers=['power1', '', 'power3', ''], power_flags=list(power_flags), powers_raw=None, power_pad=0,
                   costume=3, costume_mask=costume_mask),
              dict(attributes=_attr(1, [(0, 1), (300, 1)]), equipment=_equip(), powers=['', '', '', ''], powers_raw=None, power_pad=0,
                   costume=0, costume_mask=3)]
    items = dict(def_count=def_count, def_state=[0] * 320, tech_bits=55, health_items=2, energy_items=0, key_counts=[1, 0, 0, 2, 0, 0],
                 carried=[_instance(2, location=2), _instance(1, own=[(6, 3)], suffixes=[(2, 5)], location=3),
                          _instance(0, own=[(5, 1)], name_a=0, name_b=0, special=0, location=2)],
                 world=[dict(slot=5, instance=_instance(3, own=[(7, 1)]))])
    items['def_state'][2 * 2] = 3                      # potion quantity 3
    restore = [dict(attributes=_attr(), equipment=_equip()) for _ in range(L.OLD_RESTORE_RECORDS)]
    game = dict(timer_threshold=0.0, timer_remaining=0.0, timer_after_add=0.0, timer_last_add=0.0, timer_script='', recall_cooldown=0.0,
                xtreme_charges=1, xtreme_pips=2, loading_name='', recall_zone='none', recall_pos=[0.0, 0.0, 0.0], act=2,
                unused_a5=b'\0' * 6, pad_ab=0, trivia=[0b11, 1 << 18] + [0] * 6, value_608=0, difficulty=1, play_time=99.5,
                flags_d8=2, flags_d9=0x20 | 0x40, flags_da=2 | 4, pad_db=0)
    strings = dict(generation=1, offsets=[0] * L.OLD_ZONE_STRING_SLOTS, used=2, arena=bytearray(L.OLD_ZONE_ARENA))
    strings['offsets'][0] = 1

    def intern(slot, text):
        off = strings['used']; raw = text.encode()
        strings['arena'][off:off + len(raw) + 1] = raw + b'\0'; strings['offsets'][slot] = off; strings['used'] = off + len(raw) + 1
        return (1 << 24) | slot
    zones = []
    if zone:
        h_zone = intern(10, 'zone/x/y'); h_gate = intern(11, 'gate'); h_g1 = intern(12, 'gate01'); h_g2 = intern(13, 'gate02')
        h_crate = intern(14, 'crate_pinned'); h_c2 = intern(15, 'crate02'); h_dyn = intern(16, 'loot'); h_dn = intern(17, 'loot01')
        empty = dict(def_name=0, inst_name=0, payload=b'\0' * 8, flags_a=0, flags_b=0, position=[0, 0, 0])
        states = [dict(empty) for _ in range(L.OLD_ZONE_STATES)]
        states[1] = dict(def_name=h_gate, inst_name=h_g1, payload=b'\x01\x02\x03\x04\x05\x06\x07\x08', flags_a=0, flags_b=8, position=[10, -20, 30])
        states[2] = dict(def_name=h_gate, inst_name=h_g2, payload=b'\x11' * 8, flags_a=0, flags_b=8, position=[1, 2, 3])
        states[3] = dict(def_name=h_crate, inst_name=h_c2, payload=b'\x22' * 8, flags_a=0, flags_b=8 | 16, position=[4, 5, 6])
        states[4] = dict(def_name=h_dyn, inst_name=h_dn, payload=bytes([5]) + struct.pack('<h', 3) + b'\x33' * 5, flags_a=1, flags_b=0, position=[7, 8, 9])
        om = [0] * L.OLD_ZONE_ORDINALS
        om[0] = 1; om[1] = 2; om[2] = 3                      # ordinals 1, 2, 3 (gate01, gate02, crate02 in the synthetic numbering)
        zones.append(dict(name_handle=h_zone, states=states, pad_4804=0, state_count=5, ordinal_map=om, pad_4a0c=0,
                          dynamic=[4] + [0] * (L.OLD_ZONE_DYNAMIC - 1), pad_4c68=0, dynamic_count=1,
                          smart=[0] * L.OLD_ZONE_SMART, pad_5270=0, smart_count=0, fog=b'\x5a' * L.OLD_FOG_BYTES,
                          conversation=[1, 0, 0, 0, 0], time_stamp=12.5, flag=0, pad_55dd=[0, 0, 0]))
    strings['arena'] = bytes(strings['arena'])
    profile = dict(options=[0x0a, 0x87, 0x0f], player_name='player', high_scores=[dict(course=0, pad1=[0, 0, 0], party_a=[0] * 6, count_a=0,
                   party_b=[0] * 6, count_b=0, score=0) for _ in range(L.OLD_HIGH_SCORES)], pad_1b4=0, score_count=0,
                   char_unlock=[0b110] + [0] * 9, review=[1] + [0] * 14, pad_220=0, highest_level=5, flags_229=0, pad_22a=[0, 0])
    sv = {'zone': [dict(name='', value_be=b'\0' * 4) for _ in range(L.OLD_SCRIPT_ZONE_VARS)],
          'game': [dict(name='gv_one', value_be=b'\0\0\0\x07')] + [dict(name='', value_be=b'\0' * 4) for _ in range(L.OLD_SCRIPT_GAME_VARS - 1)]}
    m = dict(description='desc', description_raw=None, begin_tag='[SAVEGAMEBEGIN: desc]', end_tag='[SAVEGAMEEND: desc]', items=items,
             heroes=heroes, unlocked=dict(entries=[1, 2, 4] + [0] * (L.OLD_UNLOCKED_SLOTS - 3), count=3), restore_flag=0, restore=restore,
             game=game, side=dict(frames=[_snapshot(), _snapshot()], pad_4d8=0, count=0),
             danger_room=dict(courses=[dict(flags=1, tier0=0, tier1=1, tier2=0, largest_hit=100, largest_hit_hero=2, least_damage=5,
                                            least_damage_hero=0, best_time=60, best_combo=9, most_health_packs=1, most_health_packs_hero=0,
                                            most_energy_packs=0, most_energy_packs_hero=0, most_defeats=3, most_defeats_hero=1)] * 2,
                              course_residue=[0] * (L.OLD_DR_COURSES - 2), grades=[3] + [0] * 7),
             review=dict(unlocked=[0b11] + [0] * 15, seen=[0] * 3 + [1] + [0] * 12), zone_strings=strings, zones=zones,
             mission=_snapshot('zone/x/y', ('hero_a', '', 'hero_b', ''), {0: 1, 2: 0x41}), profile=profile, script_vars=sv, town_centres=1)
    return m


def test_oldsave_roundtrip_and_refusals():
    m = make_old_save()
    raw = oldsave.write_slot(m)
    assert len(raw) == L.OLD_SLOT_SIZE
    back = oldsave.read_slot(raw)
    assert oldsave.write_slot(back) == raw
    assert len(back['heroes']) == 2 and back['items']['world'][0]['slot'] == 5 and back['mission']['zone'] == 'zone/x/y'
    # refusals: size, length field, a tag out of place, an index outside its table
    for bad in (raw[:-1], raw[:0x80] + b'\x01\x00\x00\x00' + raw[0x84:], raw[:0x84] + b'\0' * 52 + raw[0x84 + 52:]):
        try:
            oldsave.read_slot(bad); assert False
        except oldsave.OldSaveError:
            pass
    m2 = make_old_save(); m2['zones'][0]['ordinal_map'][0] = 700
    try:
        oldsave.read_slot(oldsave.write_slot(m2)); assert False
    except oldsave.OldSaveError as e:
        assert 'ordinal' in str(e)


# ------------------------------------------------------------------------------------------------ container
def test_container_roundtrip_validation_and_damage():
    hdr = dict(writer_version=0x00010001, content_version=13, catalogue_revision=1, campaign_serial=42, save_sequence=1)
    sec = [('META', 1, 0, L.SECTION_REQUIRED, dict(saved_at=1, description='d', origin=1, zone=0, act=1, difficulty=1, play_time=1.0, writer='w', slot=0, mods=['m1'])),
           ('PRFO', 1, 0, 0, dict(options=5, player_name='p')),
           ('PRFP', 1, 0, 0, dict(highest_level=3, flags=0, characters=[keys.make_id(1, 1)], review=[])),
           ('PRFS', 1, 0, 0, dict(scores=[dict(course=keys.make_id(11, 1), party_a=[keys.make_id(1, 1)], party_b=[], score=9)]))]
    buf = container.write_file(L.KIND_PROFILE, sec, hdr)
    f = container.read_file(buf, L.KIND_PROFILE)
    assert f['order'] == ['META', 'PRFO', 'PRFP', 'PRFS'] and f['sections']['PRFS']['data']['scores'][0]['score'] == 9
    assert f['sections']['META']['data']['mods'] == ['m1'] and f['header']['campaign_serial'] == 42
    # every damaged byte of the header and of the body is refused
    for i in list(range(0, 0x88, 7)) + list(range(0x88, len(buf), 11)):
        bad = bytearray(buf); bad[i] ^= 0xff
        try:
            container.read_file(bytes(bad)); assert False, i
        except container.ContainerError:
            pass
    try:
        container.read_file(buf, L.KIND_CAMPAIGN); assert False
    except container.ContainerError:
        pass
    # a truncated list count is refused; an unknown optional section is kept, an unknown REQUIRED one refused
    sec2 = sec + [('XXXX', 1, 0, 0, {})]
    try:
        container.encode_section('XXXX', {}); assert False
    except KeyError:
        pass
    # newer content in a known section: refused unless EXT-DROPPABLE
    data = container.encode_section('PRFO', dict(options=5, player_name='p')) + b'\x01\x02'
    assert container.decode_section('PRFO', data).get('_extra') == b'\x01\x02'
    # a section minor above the reader's (SPEC 1.4): "needs a newer version" unless the writer marked it EXT-DROPPABLE
    for flags, ok in ((0, False), (L.SECTION_EXT_DROPPABLE, True)):
        newer = [sec[0], ('PRFO', 1, container.SECTION_MINOR.get('PRFO', 0) + 1, flags, dict(options=5, player_name='p'))] + sec[2:]
        try:
            container.read_file(container.write_file(L.KIND_PROFILE, newer, hdr), L.KIND_PROFILE)
            assert ok
        except container.ContainerError as e:
            assert not ok and 'needs a newer version' in str(e)


def test_container_record_schema_vectors():
    # the frozen element sizes of SPEC 2.5-2.10 (the C++ port pins the same numbers)
    assert len(container.encode_value('packed:ENH', dict(enhancement=1, value=2))) == 8
    assert len(container.encode_value('packed:TAL', dict(talent=1, rank=2, pending=3, cap=1, base=1, byte5=0))) == 9
    assert len(container.encode_value('packed:OBJ', dict(objective=1, counter=2, flags=1))) == 6
    assert len(container.encode_value('packed:GRD', dict(grade=1, value=2))) == 5
    assert len(container.encode_value('packed:DEFSTATE', dict(item=1, quantity=2, flag=0))) == 9
    r = container.encode_record('VAR', dict(name='ab', value=7))
    assert r == struct.pack('<I', 8) + b'\x02\x00ab' + struct.pack('<I', 7)
    # PWR (HERO minor 1): button, name, the slot's whole flag byte; a HERO 1.0 record (no flag byte) decodes without it
    r = container.encode_record('PWR', dict(button=2, name='ab', flags=0x80))
    assert r == struct.pack('<I', 6) + b'\x02\x02\x00ab\x80'
    assert container.decode_record(container._Dec(r, 0, len(r)), 'PWR')['flags'] == 0x80
    r10 = struct.pack('<I', 5) + b'\x02\x02\x00ab'
    assert 'flags' not in container.decode_record(container._Dec(r10, 0, len(r10)), 'PWR')
    assert container.SECTION_MINOR['HERO'] == 1


# ------------------------------------------------------------------------------------------------ catalogue
def test_catalogue_invariants_and_update_refusal():
    c = catmod.Catalogue()
    a = c.add('ITEM', keys.key_hash('item_a')); b = c.add('ITEM', keys.key_hash('item_b'))
    assert keys.id_domain(a) == 2 and keys.id_serial(b) == 2 and c.lookup('ITEM', keys.key_hash('ITEM_A')) == a
    prev = catmod.Catalogue(json.loads(json.dumps(c.data)))
    c.update({'ITEM': [keys.key_hash('item_a'), keys.key_hash('item_b'), keys.key_hash('item_c')]}, 14)
    assert c.counts()['ITEM'] == 3 and c.check_invariants(prev) == []
    try:
        c.update({'ITEM': [keys.key_hash('item_a'), keys.key_hash('item_d')]}, 15); assert False
    except catmod.CatalogueError:
        pass
    broken = catmod.Catalogue(json.loads(json.dumps(c.data)))
    broken.data['domains']['ITEM']['entries'][0]['hash'] = keys.key_hash('renamed')
    assert any('lost its key hash' in p for p in broken.check_invariants(prev))


# ------------------------------------------------------------------------------------------------ legacy
def test_align_and_zone_record_eras():
    assert legacy.align(['a', 'b', 'V', 'c'], ['a', 'b', 'c', 'V']) == ([1, 2, 4, 3], [])        # a moved unique entity
    assert legacy.align(['a', 'c'], ['a', 'b', 'c']) == ([1, 3], [])                              # an insertion
    m, amb = legacy.align(['x', 'x'], ['x', 'x', 'x'])                                            # twins: undecidable
    assert amb == [1, 2]
    m, amb = legacy.align(['a', 'gone'], ['a'])
    assert m == [1, 0] and amb == [2]


def _era_model(ref_binds, era_binds, cv_ref=13, cv_era=5):
    ref = ref_binds.hash_tables(); ref['content_version'] = cv_ref
    model = {'reference': ref, 'eras': {}}
    model['eras'][str(cv_ref)] = legacy.build_era_entry(ref_binds, ref, ref_binds)
    model['eras'][str(cv_era)] = legacy.build_era_entry(era_binds, ref, ref_binds)
    return model


def test_convert_roundtrip_same_era_and_shifted_era():
    with tempfile.TemporaryDirectory() as d:
        ref_dir = make_build(os.path.join(d, 'ref'), hero_extra_talent='sh_might')
        # the old era: one shared talent fewer before sh_acro (positions 2.. shift by one), one zone entity fewer
        old_dir = make_build(os.path.join(d, 'old'), shared=['sh_fight', 'sh_might', 'sh_acro', 'sh_tough'],
                             zone_entities=[('gate', ['gate01', 'gate02']), ('crate', ['crate01']), ('spawner_a', ['sp01']),
                                            ('crate_pinned', ['crate02']), ('spot', ['spot01'])], hero_extra_talent='sh_might')
        rb, ob = binds.Binds(ref_dir), binds.Binds(old_dir)
        model = _era_model(rb, ob)
        cat = catmod.Catalogue()
        for cv in ('13', '5'):
            era = legacy.Era(model, cv)
            cat.update(catmod.tables_from_hashes(era.tables), 13)
        eras_path = os.path.join(d, 'eras.json'); cat_path = os.path.join(d, 'cat.json')
        json.dump(model, open(eras_path, 'w')); cat.save(cat_path)
        env = convert.Environment(ref_dir, eras_path=eras_path, catalogue_path=cat_path)
        # (1) a save written by the reference era: byte-exact reverse
        raw = oldsave.write_slot(make_old_save(shared_ids=(0, 3, 4), def_count=len(rb.item)))
        res = convert.convert_slot(raw, 's.save', env, now=0)
        assert res.refused is None, res.refused
        assert res.era['start'] == 13 and res.era['items'] == 13 and res.era['zones'][0]['era'] == 13
        f = container.read_file(res.file_bytes, L.KIND_CAMPAIGN)
        assert 'KEYS' in f['sections'] and f['header']['optional_features'] & 1
        back, notes = convert.reverse_slot(res.file_bytes, env, template=oldsave.read_slot(raw))
        assert oldsave.write_slot(back) == raw
        d_old = dump.dump_old(oldsave.read_slot(raw), env, res.era)
        d_new = dump.dump_new(res.file_bytes, env)
        assert dump.semantic_diff(d_old, d_new) == []
        assert d_new['heroes'][0]['talents'][0]['talent'] in ('a_one', 'hero_a/a_one')
        assert f['sections']['HERO']['entry']['minor'] == 1
        # (1b) the loader's direction (no template): every power slot comes back with its flag byte (the 21st byte,
        # bit 0 = usable; the game refuses a power whose slot has it at 0) and the names unchanged
        plain, _ = convert.reverse_slot(res.file_bytes, env, template=None)
        raw_slots = oldsave.read_slot(oldsave.write_slot(plain))['heroes'][0]['powers_raw']
        assert [raw_slots[k * 21 + 20] for k in range(4)] == [1, 1, 1, 1]
        assert [raw_slots[k * 21:k * 21 + 20].split(b'\0')[0] for k in range(4)] == [b'power1', b'', b'power3', b'']
        # (1c) a slot whose flag is 0 (the engine clears slots 2/3 itself in some modes) and an empty slot with other
        # bits set survive old -> new -> old (loader, no template) -> new unchanged, and the dumps carry them
        mf = make_old_save(shared_ids=(0, 3, 4), def_count=len(rb.item), power_flags=(1, 0x81, 0, 1))
        rawf = oldsave.write_slot(mf)
        resf = convert.convert_slot(rawf, 's.save', env, now=0)
        assert resf.refused is None, resf.refused
        pw = container.read_file(resf.file_bytes)['sections']['HERO']['data']['heroes'][0]['powers']
        assert [(p['button'], p['name'], p['flags']) for p in pw] == [(0, 'power1', 1), (1, '', 0x81), (2, 'power3', 0)]
        d_newf = dump.dump_new(resf.file_bytes, env)
        assert d_newf['heroes'][0]['powers'] == {'0': dict(name='power1', flags=1), '1': dict(name='', flags=0x81),
                                                '2': dict(name='power3', flags=0)}
        assert dump.semantic_diff(dump.dump_old(oldsave.read_slot(rawf), env, resf.era), d_newf) == []
        plainf, _ = convert.reverse_slot(resf.file_bytes, env, template=None)
        loaded = oldsave.read_slot(oldsave.write_slot(plainf))
        assert loaded['heroes'][0]['power_flags'] == [1, 0x81, 0, 1] and loaded['heroes'][0]['powers_raw'] == oldsave.read_slot(rawf)['heroes'][0]['powers_raw']
        res_again = convert.convert_slot(oldsave.write_slot(plainf), 's.save', env, now=0)
        assert res_again.refused is None and dump.semantic_diff(d_newf, dump.dump_new(res_again.file_bytes, env)) == []
        backf, _ = convert.reverse_slot(resf.file_bytes, env, template=oldsave.read_slot(rawf))
        assert oldsave.write_slot(backf) == rawf
        # (1d) a HERO 1.0 file (SPEC revision 2.2: names only, written by the 0.2.0 candidates) still loads with every
        # slot usable - the flag byte it lacks is read as 1
        f10 = container.read_file(resf.file_bytes)
        secs = []
        for tag in f10['order']:
            e, dat = f10['sections'][tag]['entry'], f10['sections'][tag]['data']
            if tag == 'HERO':
                for h in dat['heroes']:
                    h['powers'] = [dict(button=p['button'], name=p['name']) for p in h['powers'] if p['name']]
            secs.append((tag, e['major'], 0 if tag == 'HERO' else e['minor'], e['flags'], dat))
        saved = container.RECORDS['PWR']
        container.RECORDS['PWR'] = (('button', 'u8'), ('name', 'str'))           # the revision 2.2 writer
        try:
            buf10 = container.write_file(L.KIND_CAMPAIGN, secs, f10['header'])
        finally:
            container.RECORDS['PWR'] = saved
        plain10, _ = convert.reverse_slot(buf10, env, template=None)
        assert oldsave.read_slot(oldsave.write_slot(plain10))['heroes'][0]['power_flags'] == [1, 1, 1, 1]
        assert dump.dump_new(buf10, env)['heroes'][0]['powers'] == {'0': dict(name='power1', flags=1), '2': dict(name='power3', flags=1)}
        # (2) the same ranks saved by the old era: shared ids 2, 3 meant sh_acro, sh_tough there; the zone's
        # numbering had crate02 at ordinal 4 and spawner at 3
        m = make_old_save(shared_ids=(0, 2, 3), def_count=len(ob.item))
        om = m['zones'][0]['ordinal_map']; om[2] = 0; om[3] = 3          # crate02 at ordinal 4 in the old era
        raw2 = oldsave.write_slot(m)
        res2 = convert.convert_slot(raw2, 's.save', env, now=0)
        assert res2.refused is None, res2.refused
        assert res2.era['start'] == 5 and res2.era['zones'][0]['era'] == 5 and not any(res2.dropped.values()), (res2.era, res2.dropped)
        d_old2 = dump.dump_old(oldsave.read_slot(raw2), env, res2.era)
        d_new2 = dump.dump_new(res2.file_bytes, env)
        assert dump.semantic_diff(d_old2, d_new2) == []
        tal = {t['talent']: t['rank'] for t in d_new2['heroes'][0]['talents']}
        assert tal['shared/sh_acro'] == 3 and tal['shared/sh_tough'] == 1           # the ranks came back by name
        states = d_new2['zones'][0]['states']
        crate = next(s for s in states if s['instance'] == 'crate02')
        assert crate['ordinal'] == 3                                              # re-numbered for the reference zone
        back2, _ = convert.reverse_slot(res2.file_bytes, env, template=oldsave.read_slot(raw2))
        assert back2['heroes'][0]['attributes']['talents'][1]['id'] == 3          # sh_acro is position 3 in the reference
        # (3) refusals: an own enhancement of another definition, an objective beyond the table, a bad seat
        m3 = make_old_save(def_count=len(rb.item)); m3['items']['carried'][1]['own'][0]['record'] = 4
        assert 'own enhancement' in convert.convert_slot(oldsave.write_slot(m3), 's', env).refused
        m4 = make_old_save(def_count=len(rb.item)); m4['mission']['objectives'][200] = 1
        assert 'objective index' in convert.convert_slot(oldsave.write_slot(m4), 's', env).refused
        m5 = make_old_save(def_count=len(rb.item)); m5['mission']['seat_names'][1] = 'nobody'
        assert 'seat' in convert.convert_slot(oldsave.write_slot(m5), 's', env).refused
        m6 = make_old_save(def_count=77)
        assert 'definition count' in convert.convert_slot(oldsave.write_slot(m6), 's', env).refused
        # (4) a zone record no era explains is dropped, the rest converts
        m7 = make_old_save(def_count=len(rb.item))
        m7['zones'][0]['ordinal_map'][0], m7['zones'][0]['ordinal_map'][1] = 2, 1    # names swapped against every era
        res7 = convert.convert_slot(oldsave.write_slot(m7), 's', env)
        assert res7.refused is None and res7.dropped['zone_records'] == 1 and 'no builder release' in res7.notes[0]


def test_talent_era_prefers_the_reading_that_keeps_the_ranks():
    with tempfile.TemporaryDirectory() as d:
        ref_dir = make_build(os.path.join(d, 'ref'))
        old_dir = make_build(os.path.join(d, 'old'), shared=['sh_fight', 'sh_might', 'sh_acro', 'sh_tough'])
        rb, ob = binds.Binds(ref_dir), binds.Binds(old_dir)
        model = _era_model(rb, ob)
        eras = legacy.eras_of(model)
        m = make_old_save(shared_ids=(0, 2, 3))        # 2 = sh_boss in the reference (not holdable), sh_acro in the old era
        era, ev = legacy.talent_era(m, eras, model['reference']['STAT'])
        assert era.cv == 5 and ev['unexplained'] == []
        m = make_old_save(shared_ids=(0, 3, 4))        # unambiguous: both eras explain it, the newest wins
        era, ev = legacy.talent_era(m, eras, model['reference']['STAT'])
        assert era.cv == 13
