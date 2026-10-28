"""Rule 43 on an invented eleven-rank decide/drain pair. No game inputs."""
import hashlib
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import build_xml1
from xml1build import common as C
from xml1build import fix_ini as FI
from xml1build import heroes as H


def fixture():
    root = ET.Element('PowerStyle')
    for decide in (True, False):
        prefix = 'ability_drain_decide' if decide else 'ability_drain'
        previous = None
        for rank in range(1, 12):
            name = (('power_smash' if decide else 'ability_drain') if rank == 11 else f'{prefix}{rank}')
            attrs = {'name': name}
            if previous:
                attrs.update(inherit=previous, fallback=previous)
            else:
                attrs.update(handler='ch_roguedecide' if decide else 'ch_attack', animenum='ea_power2', icon='1')
            move = ET.SubElement(root, 'FightMove', attrs)
            ET.SubElement(move, 'require', cat='skill', item='invented_drain', level=str(rank))
            if decide:
                ET.SubElement(move, 'trigger', name='powerusage', tag='1', powerusage=str(7 + 3 * rank))
                ET.SubElement(move, 'chain', action='Special', result='ability_drain' if rank == 11 else f'ability_drain{rank}')
                ET.SubElement(move, 'chain', action='Special2', result='drain_notarget')
            else:
                ET.SubElement(move, 'trigger', name='punch', tag='2', time='0.3', damage=str(20 + rank))
            previous = name
    ET.SubElement(root, 'FightMove', name='drain_notarget', animenum='ea_idle')
    return root


def collapse(enabled=False):
    sc = H.StyleCollapse('rogue', fixture(), H.Values(ET.fromstring('<values/>')),
                         {'invented_drain': {'power': '1', 'levels': 11}},
                         set(H.UNREGISTERED_HANDLERS_DEFAULT), rogue_decide=enabled)
    out = sc.run()
    assert not sc.report['errors'], sc.report['errors']
    return sc, out


def test_rogue_decide_keeps_two_collapsed_nodes_and_all_eleven_ranks():
    sc, out = collapse(True)
    moves = {m.get('name'): m for m in out.findall('FightMove')}
    assert set(moves) == {'power2', 'ability_drain', 'drain_notarget'}
    assert moves['power2'].get('handler') == 'ch_roguedecide'
    chains = {c.get('action').lower(): c.get('result') for c in moves['power2'].findall('chain')}
    assert chains == {'special': 'ability_drain', 'special2': 'drain_notarget'}
    assert not sc.report['transplanted']
    assert 'ch_roguedecide' not in sc.report['unregistered_handlers']
    assert len(sc.report['collapsed']['power2']['ranks']) == 11
    assert len(sc.report['collapsed']['ability_drain']['ranks']) == 11
    assert sc.report['chain_map']['power_smash'] == 'power2'
    assert sc.report['chain_map']['ability_drain'] == 'ability_drain'
    energy = moves['power2'].find("trigger[@name='powerusage']")
    assert energy is not None and energy.get('tag') == '1'
    ref = energy.get('powerusage').removeprefix('%')
    assert sc.talentvalues['invented_drain'][ref] == {i: str(7 + 3 * i) for i in range(1, 12)}
    assert not moves['ability_drain'].findall("trigger[@name='powerusage']")


def test_rogue_decide_off_retains_d15_transplant_and_output_bytes():
    sc, out = collapse(False)
    moves = {m.get('name'): m for m in out.findall('FightMove')}
    assert set(moves) == {'power2', 'drain_notarget'}
    assert moves['power2'].get('handler') == 'ch_attack'
    assert len(sc.report['transplanted']) == 1
    energy = moves['power2'].find("trigger[@name='powerusage']")
    assert energy.get('tag') == '90' and energy.get('time') == '0'
    # Snapshot generated with heroes.py from the requested source commit.
    assert hashlib.sha256(ET.tostring(out)).hexdigest() == '217b2bd0239cbe39e9275be7610073ee3fbab24b920c33bc32ea52d6005e77ff'


def test_rogue_decide_option_and_ini_are_coupled_and_off_drops_stale_key():
    assert build_xml1.parse_args(['--out', '.']).rogue_decide == 'xml1'  # default since 0.4.1-beta.1 (beta 8)
    assert build_xml1.parse_args(['--out', '.', '--rogue-decide', 'xml1']).rogue_decide == 'xml1'
    assert build_xml1.CONTENT_OPTS['rogue_decide'] == ('heroes', 'xml1')
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        meta = out / '_build'
        meta.mkdir()
        for value in ('xml1', 'xml2', None):
            record = {'build': {key: default for key, (_, default) in build_xml1.CONTENT_OPTS.items()}}
            if value:
                record['build']['rogue_decide'] = value
            else:
                record['build'].pop('rogue_decide')
            (meta / 'report.json').write_text(json.dumps(record), encoding='utf-8')
            keys = FI.port_keys(out)
            assert (keys['Game'].get('Xml1RogueDecide') == 'xml1') == (value == 'xml1')
            assert ('Xml1RogueDecide' in FI.dropped_keys(keys).get('Game', [])) == (value != 'xml1')
            assert getattr(C.args_for_out(out), 'rogue_decide', None) == value
            merged = FI.merge_text('[Game]\nXml1RogueDecide=xml1\nKeepMe=7\n', keys, FI.dropped_keys(keys))
            assert ('Xml1RogueDecide=xml1' in merged) == (value == 'xml1')
            assert 'KeepMe=7' in merged
            args = build_xml1.parse_args(['--out', td, '--save-layout', 'retail',      # the record's (CONTENT_OPTS) layout
                                          '--rogue-decide', 'xml2' if value in ('xml1', None) else 'xml1'])
            assert 'heroes' in build_xml1.plan_content_opts(out, args, [])
            assert build_xml1.plan_content_opts(out, args, ['heroes']) == []
