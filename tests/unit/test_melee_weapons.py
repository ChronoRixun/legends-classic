"""Synthetic melee weapon metadata and ini regressions; no game fixtures."""
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from xml1build import balance as B, common as C, fix_ini as FI, heroes as H, melee_weapons as M


def values():
    root = ET.Element('values')
    ET.SubElement(root, 'value', {'name': 'invented_bonus', 'min': '2.9', 'max': '40'})
    return H.Values(root)


def weapon():
    return {'name': 'invented_stick', 'category': 'melee', 'attacktype': 'punch',
            'damage': 'invented_bonus', 'damagetype': 'dmg_energy'}


def test_bonus_is_the_truncated_minimum_not_maximum_mean_or_new_roll():
    assert M.weapon_bonus(weapon(), values()) == 2
    assert M.weapon_bonus(dict(weapon(), category='ranged'), values()) is None
    assert M.weapon_bonus(None, values()) is None
    assert M.profile(weapon(), values()) == dict(zip(M.FIELDS, ('1', '2', '32768')))


def test_only_melee_armed_source_entries_get_metadata_without_new_talents_or_styles():
    source = ET.Element('stats', {'name': 'invented_guard', 'weapon': 'invented_stick'})
    out = ET.Element('stats', {'name': 'invented_guard', 'powerstyle': 'invented_style'})
    ET.SubElement(out, 'talent', {'name': 'fightstyle_invented', 'level': '1'})
    unarmed = ET.Element('stats', {'name': 'invented_civilian'})
    counts = {}
    builder = SimpleNamespace(ctx=SimpleNamespace(x1_values=values, set_count=lambda k,v: counts.update({k:v})),
                              x1_weapons={'invented_stick': weapon()})
    M.apply(builder, [(out,'xml1'), (unarmed,'xml1')], [source, unarmed])
    assert counts == {'melee_weapon_entries': 1}
    assert out.get('powerstyle') == 'invented_style'
    assert [t.attrib for t in out] == [{'name': 'fightstyle_invented', 'level': '1'}]
    assert [out.get(k) for k in M.FIELDS] == ['1', '2', '32768']
    assert not any(unarmed.get(k) for k in M.FIELDS)


def test_disabled_switch_does_no_io_and_does_not_change_stats():
    entries = [(ET.Element('stats', {'name': 'invented_actor'}), 'xml1')]
    before = ET.tostring(entries[0][0])
    old = B.X1_BALANCE
    try:
        B.X1_BALANCE = False
        M.apply(SimpleNamespace(), entries, [])
    finally:
        B.X1_BALANCE = old
    assert ET.tostring(entries[0][0]) == before


def test_ini_records_are_sorted_and_read_from_the_build_by_the_shipping_writer():
    root = ET.Element('npcstat')
    for name in ('invented_z', 'invented_a'):
        ET.SubElement(root, 'stats', dict(name=name, **M.profile(weapon(), values())))
    ET.SubElement(root, 'stats', {'name': 'invented_unarmed'})
    want = 'invented_a:1:2:32768|invented_z:1:2:32768'
    assert M.ini_value(root) == want
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp, 'Data', 'npcstat.engb')
        path.parent.mkdir()
        path.write_bytes(C.encode_xmlb(root))
        assert FI.balance_keys(tmp)['MeleeWeapons'] == want
        assert FI.balance_keys(tmp)['DamageRolls'] == 'xml1'


def test_incomplete_duplicate_or_invalid_metadata_is_refused():
    for attrs in ({'name':'invented_bad', M.FIELDS[0]:'1'},
                  dict(name='invented:bad', **M.profile(weapon(), values())),
                  dict(name='invented_bad', **dict(zip(M.FIELDS, ('1','-2','128')))),
                  dict(name='invented_bad', **dict(zip(M.FIELDS, ('1','2','8'))))):
        root = ET.Element('npcstat')
        ET.SubElement(root, 'stats', attrs)
        try:
            M.ini_value(root)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid metadata accepted')
    root = ET.Element('npcstat')
    for _ in range(2):
        ET.SubElement(root, 'stats', dict(name='invented_duplicate', **M.profile(weapon(), values())))
    try:
        M.ini_value(root)
    except ValueError:
        pass
    else:
        raise AssertionError('duplicate accepted')


def test_validator_catches_missing_armed_entries_and_a_bad_localized_half():
    source = ET.Element('stats', {'name': 'invented_guard', 'weapon': 'invented_stick'})
    built = ET.Element('stats', dict(name='invented_guard', **M.profile(weapon(), values())))
    roots = {ext: ET.Element('npcstat') for ext in ('.XMLB', '.engb')}
    for root in roots.values():
        root.append(ET.fromstring(ET.tostring(built)))
    by_name = {'invented_guard': ('npcstat', built)}
    v = SimpleNamespace(ctx=SimpleNamespace(x1_values=values),
                        x1_stats=lambda: {'invented_guard': ('npcstat', source)},
                        x1_weapons=lambda: {'invented_stick': weapon()},
                        stats=lambda: {'by_name': by_name},
                        tree=lambda rel: roots['.engb' if rel.endswith('.engb') else '.XMLB'])
    def check():
        errors, counts = [], {}
        ck = SimpleNamespace(error=errors.append, count=lambda k: counts.update({k: counts.get(k,0)+1}),
                             set=lambda k,v: counts.update({k:v}))
        M.validate(v, ck)
        return errors, counts
    assert check()[0] == [] and check()[1]['melee_weapon_entries_checked'] == 1
    roots['.XMLB'][0].set(M.FIELDS[1], '99')
    assert any('npcstat.XMLB' in e for e in check()[0])
    by_name.clear()
    assert any('missing from build' in e for e in check()[0])
