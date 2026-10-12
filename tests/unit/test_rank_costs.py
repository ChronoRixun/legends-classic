"""Issue #35: XML1's per-rank skill costs - the ini key and V-H16 (xml1build.rank_costs) on invented talents."""
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from xml1build import fix_ini
from xml1build import rank_costs as RC

def source_stats():
    """An invented hero's XML1-style <stats>: built in code, 'cost' on rank 3 and on an Xtreme-style rank 1."""
    stats = ET.Element('stats', name='Zephyr')
    gale = ET.SubElement(stats, 'Talent', name='gale_strike', power='0')
    for text in ('a', 'b'):
        ET.SubElement(gale, 'level', description=text)
    ET.SubElement(gale, 'level', description='c', descname='Gale Form', cost='2')
    ET.SubElement(ET.SubElement(stats, 'Talent', name='zephyr_xtreme', power='3'), 'level', description='x', cost='2')
    ET.SubElement(ET.SubElement(stats, 'Talent', name='calm'), 'level', description='p')
    return stats


def built(levels_by_talent):
    root = ET.Element('talents')
    for name, levels in levels_by_talent.items():
        t = ET.SubElement(root, 'talent', name=name)
        ET.SubElement(t, 'talentvalues')
        for cost, count in levels:
            attrs = {'count': count} if count is not None else {}
            if cost is not None:
                attrs['cost'] = cost
            ET.SubElement(t, 'level', attrs)
    return RC.built_levels(root)


def good():
    return {'gale_strike': [(None, '1'), (None, '1'), ('2', '1')], 'zephyr_xtreme': [('2', '1'), (None, '1')],
            'calm': [(None, '1')]}


def test_source_costs_by_rank():
    assert RC.source_costs(source_stats()) == {'gale_strike': {3: '2'}, 'zephyr_xtreme': {1: '2'}}


def test_faithful_build_passes_and_counts():
    b = built(good())
    assert RC.problems(RC.source_costs(source_stats()), b, 'talents/zephyr') == []
    assert RC.costed_ranks(b) == 2


def test_lost_cost_is_an_error():
    lv = good()
    lv['gale_strike'][2] = (None, '1')
    msgs = RC.problems(RC.source_costs(source_stats()), built(lv), 'w')
    assert any('gale_strike rank 3 costs 2 in XML1' in m for m in msgs)


def test_moved_or_invented_cost_is_an_error():
    lv = good()
    lv['gale_strike'][1] = ('2', '1')
    lv['calm'][0] = ('2', '1')
    msgs = RC.problems(RC.source_costs(source_stats()), built(lv), 'w')
    assert any('gale_strike rank 2 carries cost' in m for m in msgs)
    assert any('calm rank 1 carries cost' in m for m in msgs)


def test_multi_rank_level_before_a_cost_is_an_error():
    lv = good()
    lv['gale_strike'][0] = (None, '2')
    msgs = RC.problems(RC.source_costs(source_stats()), built(lv), 'w')
    assert any('covers more or fewer ranks' in m for m in msgs)


def test_value_outside_the_fix_range_is_an_error():
    src = {'gale_strike': {3: '9'}}
    lv = {'gale_strike': [(None, '1'), (None, '1'), ('9', '1')]}
    assert any('outside 1..7' in m for m in RC.problems(src, built(lv), 'w'))


def test_missing_talent_is_an_error():
    lv = good()
    del lv['zephyr_xtreme']
    assert any('zephyr_xtreme has XML1 rank costs' in m for m in RC.problems(RC.source_costs(source_stats()), built(lv), 'w'))


def test_port_owns_and_enables_rank_costs():
    assert 'RankCosts' in fix_ini.PORT_OWNED['Game']
    assert fix_ini.game_keys()['RankCosts'] == '1'
    assert 'RankCosts' not in fix_ini.game_keys(xml1_opening=False)


def test_rank_costs_key_dropped_on_stock_merge():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'settings.ini'
        path.write_text('[Game]\nRankCosts=0\nKeepMe=example\n')
        port = {'Game': fix_ini.game_keys()}
        fix_ini.merge_ini(path, port, fix_ini.dropped_keys(port))
        assert fix_ini.read_ini(path)['Game']['RankCosts'] == '1'
        stock = {'Game': fix_ini.game_keys(xml1_opening=False)}
        fix_ini.merge_ini(path, stock, fix_ini.dropped_keys(stock))
        parsed = fix_ini.read_ini(path)['Game']
        assert 'RankCosts' not in parsed and parsed['KeepMe'] == 'example'
