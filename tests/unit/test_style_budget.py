"""SPEC 43 / V23: the fighting / power style registry budget, on invented packages and stats built in code."""
import xml.etree.ElementTree as ET
from types import SimpleNamespace

from xml1build import fix_ini as FI
from xml1build import style_budget as SB
from xml1build.validate import Check


def styles(*names):
    return [('fightstyle', f'data/fightstyles/{n}') for n in names]


def test_capacity_is_what_the_shipped_ini_asks_for():
    assert SB.capacity() == int(FI.LIMITS['FightStyles']) == 32 and 'FightStyles' in FI.PORT_OWNED['Limits']
    assert SB.capacity({}) == SB.STOCK_STYLES == 19                      # no key: the game's own registry
    assert SB.capacity({'FightStyles': 'many'}) == 19 and SB.capacity({'FightStyles': '7'}) == 19


def test_package_styles_counts_distinct_files_only():
    entries = [('fightstyle', r'Data\FightStyles\Style_A'), ('model', 'models/thing'),
               ('fightstyle', 'data/fightstyles/style_a'), ('FIGHTSTYLE', 'data/powerstyles/style_b'),
               ('fightstyle', ''), ('xml', 'data/fightstyles/style_c')]
    assert SB.package_styles(entries) == ['data/fightstyles/style_a', 'data/powerstyles/style_b']
    assert SB.package_styles(None) == []


def test_worst_party_counts_shared_styles_once():
    base = {'p1', 'p2', 'shared'}
    heroes = {'hero_a': {'a'}, 'hero_b': {'b', 'move'}, 'hero_c': {'c', 'move'}, 'hero_d': {'d'},
              'hero_e': {'shared'}}                                       # hero_e's style is in the base already
    n, party = SB.worst_party(base, heroes, size=2)
    assert (n, party) == (3 + 3, ('hero_a', 'hero_b'))                    # b + move + one more; first in name order
    n, party = SB.worst_party(base, heroes, size=4)
    assert n == 3 + 5 and 'hero_e' not in party                           # a, b, c, d, move
    assert SB.worst_party(base, {}, size=4) == (3, ())
    assert SB.worst_party(base, {'hero_a': {'a'}}, size=4) == (4, ('hero_a',))   # fewer heroes than seats


def test_zone_count_adds_permanent_zone_npc_and_party():
    rep = SB.zone_count(['data/fightstyles/perm'], styles('zone_a', 'perm'), {'data/fightstyles/npc'},
                        {'hero_a': {'data/powerstyles/a'}}, size=4)
    assert rep == {'total': 4, 'base': 3, 'party': ['hero_a'],
                   'zone_styles': ['data/fightstyles/zone_a', 'data/fightstyles/perm']}


class FakeValidator:
    """The parts of validate.Validator V23 reads."""

    def __init__(self, zone_extra, combat_off=False, npc_extra=()):
        hero = ET.Element('stats', {'name': 'Hero_A', 'skin': '0101', 'powerstyle': 'ps_a'})
        npc = ET.Element('stats', {'name': 'Guard', 'skin': '0201'})
        default = ET.Element('stats', {'name': 'default', 'skin': '0002'})
        self._stats = {'variants': {'.engb': {'herostat': [default, hero], 'npcstat': [npc]}},
                       'by_name': {'hero_a': ('herostat', hero), 'guard': ('npcstat', npc)}}
        zone = styles(*zone_extra) + ([('combat_is', 'off')] if combat_off else [])
        self.pkgs = {'packages/generated/maps/package/permanent.pkgb': styles('perm_a'),
                     'packages/generated/maps/package/permanent_fightstyles.pkgb': styles('perm_a', 'perm_b'),
                     'packages/generated/characters/hero_a_0101.pkgb': [('fightstyle', 'data/powerstyles/ps_a')],
                     'packages/generated/characters/hero_a_0101_nc.pkgb': [],
                     'packages/generated/characters/guard_0201.pkgb': styles(*npc_extra),
                     'packages/generated/maps/test/hall.pkgb': zone}
        self.scan = SimpleNamespace(pkg=self.pkgs)
        chrb = ET.Element('characters')
        ET.SubElement(chrb, 'character', {'name': 'Guard'})
        ET.SubElement(chrb, 'character', {'name': 'Hero_A'})
        self.trees = {'maps/test/hall.chrb': chrb}

    def stats(self):
        return self._stats

    def tree(self, rel):
        return self.trees.get(rel)

    def converted_zones(self):
        return ['test/hall']

    def zone_pkg(self, zone):
        return self.pkgs.get(f'packages/generated/maps/{zone}.pkgb')


def run(v):
    ck = Check('V23', 'fight styles')
    SB.validate(v, ck)
    return ck


def test_validate_passes_warns_and_fails_at_the_capacity():
    cap = SB.capacity()
    room = cap - 2 - 1                                # 2 permanent styles and the hero's power style
    ck = run(FakeValidator([f'z{i}' for i in range(room - 1)]))
    assert not ck.errors and not ck.warnings
    assert ck.counts['max_styles'] == cap - 1 and ck.counts['max_zone'] == 'test/hall'
    assert ck.counts['zones_over_stock'] == 1 and ck.details['zones']['test/hall']['party'] == ['hero_a']
    ck = run(FakeValidator([f'z{i}' for i in range(room)]))
    assert not ck.errors and len(ck.warnings) == 1 and 'test/hall' in ck.warnings[0]
    ck = run(FakeValidator([f'z{i}' for i in range(room + 1)]))
    assert len(ck.errors) == 1 and 'hero_a' in ck.errors[0] and str(cap + 1) in ck.errors[0]


def test_validate_counts_npc_packages_and_uses_nc_packages_with_combat_off():
    cap = SB.capacity()
    zone = [f'z{i}' for i in range(cap - 2 - 1)]      # full with the hero's power style
    assert len(run(FakeValidator(zone)).warnings) == 1
    ck = run(FakeValidator(zone, npc_extra=['guard_style']))      # a CHRB character's package adds a style
    assert len(ck.errors) == 1
    ck = run(FakeValidator(zone, combat_off=True))                # combat off: the hero's _nc package has no style
    assert not ck.errors and not ck.warnings and ck.details['zones']['test/hall']['combat_off'] is True


def test_validate_checks_against_the_stock_registry_without_the_key():
    saved = dict(FI.LIMITS)
    try:
        FI.LIMITS.pop('FightStyles')
        ck = run(FakeValidator([f'z{i}' for i in range(17)]))     # 2 + 17 + 1 = 20 > 19
        assert ck.counts['capacity'] == 19 and len(ck.errors) == 1
    finally:
        FI.LIMITS.clear()
        FI.LIMITS.update(saved)
