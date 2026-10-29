"""Synthetic world-table and validation regressions for the private Guard node."""
import copy
import xml.etree.ElementTree as ET
from xml1build import guard_block as G
from types import SimpleNamespace
from collections import Counter, defaultdict


def test_guard_block_both_variants_and_preservation():
    for ext in ('.XMLB', '.engb'):
        top = ET.Element('FightStyle')
        reaction = ET.SubElement(top, 'FightMove', name='block', handler='ch_pain')
        retail = ET.SubElement(top, 'FightMove', name='blocking', handler='ch_block')
        before = [ET.tostring(n) for n in top]
        G.install(top)
        assert [ET.tostring(n) for n in list(top)[:2]] == before, ext
        assert top[0] is reaction and top[1] is retail
        assert G.problems(top) == []
        G.install(top)
        assert len(top) == 3 and G.problems(top) == []


def test_guard_block_rejects_missing_or_incomplete_energy_lifecycle():
    top = ET.Element('FightStyle')
    assert G.problems(top)
    G.install(top)
    for mutation in ('handler', 'animation', 'skill', 'level', 'upkeep', 'cleanup', 'release', 'extra'):
        changed = copy.deepcopy(top)
        node = changed[0]
        if mutation == 'handler':
            node.set('handler', 'ch_block')
        elif mutation == 'animation':
            node.set('animenum', 'ea_idle1')
        elif mutation == 'skill':
            ET.SubElement(node, 'require', cat='skill', item='block')
        elif mutation == 'level':
            node.find('trigger/affecter').set('level', '%missing_talent_value')
        elif mutation == 'upkeep':
            node.find('trigger').set('powerusage', '0')
        elif mutation == 'cleanup':
            node.findall('trigger')[1].set('remove_on_node_end', 'false')
        elif mutation == 'release':
            node.find('chain').set('result', 'guardblocking')
        else:
            ET.SubElement(node, 'trigger', name='powerup')
        assert G.problems(changed), mutation


def test_world_table_pipeline_emits_both_native_block_variants():
    from xml1build.zones import Zones
    native = ET.Element('FightStyle')
    ET.SubElement(native, 'FightMove', name='block', handler='ch_pain')
    ET.SubElement(native, 'FightMove', name='blocking', handler='ch_block')
    emitted = {}

    class Context:
        def read_x1_xml(self, rel):
            if rel != 'data/shared_nodes.eng':
                raise KeyError(rel)
            return ET.Element('FightStyle')

        def base_exists(self, rel):
            return rel in ('Data/shared_nodes.XMLB', 'Data/shared_nodes.engb')

        def read_base_xmlb(self, rel):
            return copy.deepcopy(native)

        def write_xmlb_pair(self, stem, xmlb, engb, **kw):
            emitted[stem + '.XMLB'] = xmlb
            emitted[stem + '.engb'] = engb

        def x1_schema(self, *args):
            pass

        def error(self, *args):
            pass  # Other world tables are outside this focused synthetic fixture.

        def note(self, *args):
            pass

    converter = Zones.__new__(Zones)
    converter.ctx = Context()
    converter.prov = SimpleNamespace(rewrite_data_tree=lambda *args: None)
    converter.item_refs = defaultdict(set)
    converter.counts = Counter()
    converter.dr_reward_items = lambda: {}
    converter.merge_package = lambda *args, **kwargs: None
    converter.build_world_tables()
    assert set(emitted) == {'Data/shared_nodes.XMLB', 'Data/shared_nodes.engb'}
    for root in emitted.values():
        assert G.problems(root) == []
        assert [ET.tostring(n) for n in list(root)[:2]] == [ET.tostring(n) for n in native]
