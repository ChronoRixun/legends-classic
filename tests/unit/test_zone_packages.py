"""SPEC 29.1: zone packages list the weapon variant styles their characters use (xml1build.zones) - no game data."""
import collections
import types

from xml1build import zones as Z


def fake(shared):
    return types.SimpleNamespace(ctx=types.SimpleNamespace(shared=shared), counts=collections.Counter())


SHARED = {'weapon_variant_base': {'x1_ps_grso_mp5': 'ps_grso', 'x1_ps_grso_laser_gun': 'ps_grso',
                                  'x1_ps_flamethrower_flamethrower': 'ps_flamethrower'},
          'stats_powerstyle': {'haarpsoldier': 'x1_ps_grso_mp5', 'grso_laser': 'x1_ps_grso_laser_gun',
                               'haarpflamethrower': 'x1_ps_flamethrower_flamethrower', 'grso_officer': 'ps_grso',
                               'haarpsoldiermelee': 'ps_def'}}


def test_base_style_becomes_the_variants_the_zone_uses():
    z = fake(SHARED)
    out = Z.Zones.weapon_variant_entries(z, ('fightstyle', 'data/powerstyles/ps_grso'),
                                         ['HAARPSoldier', 'grso_laser', 'HAARPSoldierMelee'], 'haarp/ext/haarp_ext01')
    assert out == [('fightstyle', 'data/powerstyles/x1_ps_grso_laser_gun'), ('fightstyle', 'data/powerstyles/x1_ps_grso_mp5')]
    assert z.counts['zone_base_styles_replaced'] == 1 and z.counts['zone_style_variants'] == 2


def test_base_kept_when_a_character_still_uses_it():
    z = fake(SHARED)
    out = Z.Zones.weapon_variant_entries(z, ('fightstyle', 'data/powerstyles/ps_grso'),
                                         ['HAARPSoldier', 'grso_officer'], 'z')
    assert out == [('fightstyle', 'data/powerstyles/ps_grso'), ('fightstyle', 'data/powerstyles/x1_ps_grso_mp5')]


def test_other_entries_untouched():
    z = fake(SHARED)
    assert Z.Zones.weapon_variant_entries(z, ('fightstyle', 'data/powerstyles/ps_def'), ['HAARPSoldierMelee'], 'z') == \
        [('fightstyle', 'data/powerstyles/ps_def')]
    assert Z.Zones.weapon_variant_entries(z, ('actorskin', '19801'), ['HAARPSoldier'], 'z') == [('actorskin', '19801')]
    assert Z.Zones.weapon_variant_entries(fake({}), ('fightstyle', 'data/powerstyles/ps_grso'), ['HAARPSoldier'], 'z') == \
        [('fightstyle', 'data/powerstyles/ps_grso')]
