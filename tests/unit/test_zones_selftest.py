"""Self-test expectations on synthetic inherited tables and retained packages."""
import copy
import xml.etree.ElementTree as ET

from xml1build import zones_selftest as T


def tables():
    base = ET.fromstring('<items><item name="PASS" type="item"><bonus value="2"/></item>'
                         '<item name="COIN" model="props/coin"/></items>')
    source = {'pass': ET.fromstring('<item name="pass" model=" props/pass.igb "/>'),
              'coin': ET.fromstring('<item name="coin" model="props/other"/>')}
    output = copy.deepcopy(base)
    output[0].set('model', 'props/pass.igb')
    output.append(ET.Element('item', {'name': 'NEW'}))
    T.C.normalize_attrs(base)
    T.C.normalize_attrs(output)
    return list(base), list(output), source


def test_world_prefix_accepts_only_source_model_fill_and_new_tail():
    base, output, source = tables()
    assert T.world_table_prefix_matches(base, output, source)
    assert base[0].get('model') is None   # the check must not mutate its input


def test_world_prefix_requires_the_expected_fill():
    base, output, source = tables()
    del output[0].attrib['model']
    assert not T.world_table_prefix_matches(base, output, source)


def test_world_prefix_rejects_wrong_model_and_unrelated_changes():
    for target, attr, value in ((0, 'model', 'props/wrong'), (0, 'type', 'equipment'),
                                (0, 'name', 'OTHER'), (1, 'model', 'props/other')):
        base, output, source = tables()
        output[target].set(attr, value)
        assert not T.world_table_prefix_matches(base, output, source)


def test_world_prefix_rejects_child_changes_missing_entries_and_reordering():
    for mutate in (lambda o: o[0][0].set('value', '3'), lambda o: o.pop(1),
                   lambda o: o.reverse(), lambda o: o[0].append(ET.Element('extra'))):
        base, output, source = tables()
        mutate(output)
        assert not T.world_table_prefix_matches(base, output, source)


def test_world_prefix_without_source_keeps_strict_inherited_comparison():
    base, output, source = tables()
    assert T.world_table_prefix_matches(base, base)
    assert not T.world_table_prefix_matches(base, output)
    assert not T.world_table_prefix_matches(base, output, {})
    source['pass'].attrib.pop('model')
    assert not T.world_table_prefix_matches(base, output, source)


def test_world_prefix_blank_base_model_is_filled_but_other_tags_are_preserved():
    base, output, source = tables()
    base[0].set('model', ' ')
    assert T.world_table_prefix_matches(base, output, source)
    base[0].tag = output[0].tag = 'prefix'
    assert not T.world_table_prefix_matches(base, output, source)


def packages():
    base = ET.fromstring('<packagedef name="fixture"><script filename="scripts/fixture"/>'
                         '<fightstyle filename="data/powerstyles/fixture"/><boy filename="maps/fixture"/>'
                         '</packagedef>')
    talents = ['data/talents/alpha', 'data/talents/beta']
    output = copy.deepcopy(base)
    for name in reversed(talents):
        output.insert(0, ET.Element('xml_talents', {'filename': name}))
    return base, output, talents


def test_retained_package_accepts_exact_required_prefix_and_preserves_inputs():
    base, output, talents = packages()
    assert T.retained_package_matches(base, output, talents)
    assert len(base) == 3


def test_retained_package_rejects_missing_extra_wrong_and_reordered_talents():
    for mutate in (lambda o: o.remove(o[0]),
                   lambda o: o.insert(0, ET.Element('xml_talents', {'filename': 'data/talents/extra'})),
                   lambda o: o[0].set('filename', 'data/talents/wrong'),
                   lambda o: o.__setitem__(slice(0, 2), o[:2][::-1])):
        base, output, talents = packages()
        mutate(output)
        assert not T.retained_package_matches(base, output, talents)


def test_retained_package_rejects_base_suffix_or_root_changes():
    for mutate in (lambda o: o[2].set('filename', 'scripts/other'), lambda o: o.remove(o[-1]),
                   lambda o: o.append(ET.Element('model', {'filename': 'props/extra'})),
                   lambda o: o.set('name', 'other'), lambda o: o[0].set('extra', '1')):
        base, output, talents = packages()
        mutate(output)
        assert not T.retained_package_matches(base, output, talents)


def test_retained_package_requires_nonempty_talents_and_unpatched_base():
    base, output, talents = packages()
    assert not T.retained_package_matches(base, base, [])
    base.insert(0, ET.Element('xml_talents', {'filename': talents[0]}))
    assert not T.retained_package_matches(base, output, talents)
