"""Synthetic registry-contract and noncombat precache regressions."""
from xml1build import talent_budget as TB


def test_minimal_path_boundary_and_default_interval():
    assert TB.loader_problems({'data/shared_talents', 'data/talents/' + 'a' * 45}, {'a' * 45}) == []
    assert any('63' in s for s in TB.loader_problems({'data/talents/' + 'a' * 46}, {'a' * 46}))
    assert any('default' in s for s in TB.loader_problems(
        {'data/talents/unknown_a', 'data/talents/unknown_b'}, set()))
    assert TB.loader_problems({'data/talents/known_a', 'data/talents/unknown_a'}, {'known_a'}) == []


def test_minimal_props_removed_only_for_overflow():
    counts = {'data/shared_talents': frozenset('s' + str(i) for i in range(63))}
    heroes = {}
    for h in ('aa', 'bb', 'cc', 'dd', 'prop'):
        f = 'data/talents/' + h
        counts[f] = frozenset(h + str(i) for i in range(8))
        heroes[h] = {f}
    eligible = {'data/talents/prop': 'reviewed noncombat prop, excluded from seated party'}
    base = {'data/shared_talents', 'data/talents/prop'}
    kept, drops = TB.prune_props(base, eligible, {h: heroes[h] for h in ('aa', 'bb', 'cc', 'dd')}, counts)
    assert kept == {'data/shared_talents'} and list(drops) == ['data/talents/prop']
    kept, drops = TB.prune_props(base, eligible, {'aa': heroes['aa']}, counts)
    assert kept == base and drops == {}


def test_minimal_required_or_fighting_hero_never_dropped():
    counts = {'data/shared_talents': frozenset('s' + str(i) for i in range(99)),
              'data/talents/fighter': frozenset({'attack', 'armor'})}
    base = set(counts)
    kept, drops = TB.prune_props(base, {}, {}, counts)
    assert kept == base and drops == {}
    assert TB.problems(TB.demand(kept, counts))


def test_minimal_full_validator_handles_hero_npc_without_npcstat_row():
    import xml.etree.ElementTree as ET
    from types import SimpleNamespace
    from test_talent_overflow import FakeV, FakeCheck
    v = FakeV(['s1'], {}, {'data/talents/hero_aa': ['h1']})
    stat = ET.Element('stats', name='hero_aa', powerstyle='invented_style', skin='12345')
    v._stats['variants'] = {'.engb': {'herostat': [stat]}}
    v._stats['by_name'] = {'hero_aa': ('herostat', stat)}
    v.scan = SimpleNamespace(pkg={
        'packages/generated/characters/hero_aa_12345.pkgb': [('xml_talents', 'data/talents/hero_aa')],
        'packages/generated/characters/hero_aa_12345_nc.pkgb': [('xml_talents', 'data/talents/hero_aa')],
    })
    chrb = ET.Element('characters')
    ET.SubElement(chrb, 'character', name='hero_aa')
    tree = v.tree
    v.tree = lambda rel: chrb if rel == 'maps/invented/yard.chrb' else tree(rel)
    v.converted_zones = lambda: ['invented/yard']
    v.zone_pkg = lambda zone: [('xml_talents', 'data/talents/hero_aa')]
    ck = FakeCheck()
    TB.validate(v, ck)
    assert not ck.errors, ck.errors
    assert ck.counts['zones_checked'] == 1


class PropContext:
    """Synthetic package-emitter inputs with an actual cached hero plan."""
    def __init__(self, shared_count=63):
        import xml.etree.ElementTree as ET
        names = ('aa', 'bb', 'cc', 'dd', 'prop_aa')
        self.shared = {'heroes_plan': {'heroes': names,
                                      'style': {name: 'invented_' + name for name in names}}}
        self.notes = []
        self.trees = {'Data/npcstat.engb': ET.Element('stats')}
        for rel, values in [('data/shared_talents', ['s' + str(i) for i in range(shared_count)])] + [
                ('data/talents/' + n, [n + str(i) for i in range(8)]) for n in names]:
            root = ET.Element('talents')
            for value in values:
                ET.SubElement(root, 'talent', name=value)
            self.trees[rel + '.engb'] = root

    def read_out_xmlb(self, rel):
        return self.trees.get(rel)

    def read_x1_xml(self, rel):
        import xml.etree.ElementTree as ET
        assert rel == 'data/dangerroom.eng'
        return ET.Element('dangerroom')

    def note(self, text):
        self.notes.append(text)


def test_minimal_pruning_prevents_early_prop_style_binding_on_saved_load():
    import xml.etree.ElementTree as ET
    from unittest.mock import patch
    for shared_count, dropped in ((63, True), (50, False)):
        ctx = PropContext(shared_count)
        root = ET.Element('package')
        ET.SubElement(root, 'xml_talents', filename='data/talents/prop_aa')
        ET.SubElement(root, 'fightstyle', filename='data/powerstyles/invented_prop_aa')
        ET.SubElement(root, 'model', filename='models/invented_prop')
        ET.SubElement(root, 'fightstyle', filename='data/powerstyles/invented_aa')
        with patch.dict(TB.PROP_HERO_ROLES, {'invented/ship': {'prop_aa': 'reviewed scene prop'}}):
            result = TB.prune_zone_precache(ctx, 'invented/ship', root)
        files = {e.get('filename') for e in result}
        assert ('data/talents/prop_aa' not in files) == dropped
        assert ('data/powerstyles/invented_prop_aa' not in files) == dropped
        assert 'data/powerstyles/invented_aa' in files
        assert 'models/invented_prop' in files


def test_minimal_emitter_includes_script_only_playable_hero():
    from xml1build import zones as Z
    ctx = PropContext()
    ctx.shared['heroes_plan']['heroes'] = ['invented_hero']
    texts = {'invented/start': 'spawnMonster("invented_hero")'}
    result = Z.zone_npc_talent_entries(ctx, 'invented/yard', [], ['scripts/invented/start'], texts.get)
    assert result == ['data/talents/invented_hero']
