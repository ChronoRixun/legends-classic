"""Synthetic reactions and attacks; no owned game data or renderer required."""
import xml.etree.ElementTree as ET

from xml1build import puzzle_reactions as P


def xml(text):
    return ET.fromstring(text)


def shared():
    return xml('''<events><event name="beam" type="ce_atk_beam"
      damagetype="dmg_energy" damagelevel="1"/>
      <event name="punch" type="ce_atk_punch" damagetype="dmg_physical"/></events>''')


def target(reaction):
    return xml(f'''<map><entity classname="powertriggerent" name="test_socket" reactpower="{reaction}"/>
      <entinst type="test_socket"><inst name="test_socket" pos="0 0 0"/></entinst></map>''')


def test_puzzle_charge_accepts_energy_without_energize_and_preserves_weld():
    style = xml('''<style><FightMove name="power1"><trigger name="test_ray" inherit="beam">
      <damageMod name="dmgmod_weld"/></trigger></FightMove></style>''')
    p = P.producers(style, shared())
    assert p['charge'] == p['weld'] == {'power1'}
    assert not P.missing_producers(target('charge'), {'test_hero': p})


def test_puzzle_physical_weld_cannot_substitute_for_charge():
    style = xml('''<style><FightMove name="power1"><trigger name="test_hit" inherit="punch">
      <damageMod name="dmgmod_weld"/></trigger></FightMove></style>''')
    p = P.producers(style, shared())
    assert p['weld'] and not p['charge']
    assert P.missing_producers(target('charge'), {'test_hero': p}) == [('test_socket', 'charge')]


def test_puzzle_move_uses_damage_type_and_does_not_require_positive_level():
    assert P.accepts('move', P.DAMAGE_TYPES['dmg_wind'], set(), 0)
    assert P.accepts('move', P.DAMAGE_TYPES['dmg_telekinesis'], set(), 0)
    assert not P.accepts('move', P.DAMAGE_TYPES['dmg_physical'], set(), 10)
    assert not P.accepts('move', P.DAMAGE_TYPES['dmg_mental'], set(), 10)


def test_puzzle_bridge_requires_environment_and_one_exact_supported_type():
    mods = {'dmgmod_environment'}
    assert P.accepts('bridge', 0x40000, mods, 1)
    assert not P.accepts('bridge', 0x40000, set(), 1)
    assert not P.accepts('bridge', 0x40080, mods, 1)
    assert not P.accepts('bridge', 0x40000, mods, 0)
    assert P.accepts('extinguish', 0, {'dmgmod_extinguish'}, 1)


def test_puzzle_level_is_a_literal_byte_not_a_talent_reference():
    style = xml('''<style><FightMove name="power1">
      <trigger name="test_ray" inherit="beam" damagelevel="%test_level"/>
      </FightMove></style>''')
    assert not P.producers(style, shared())['charge']
    trigger = style.find('.//trigger')
    for value in ('0', '256', '0 10'):
        trigger.set('damagelevel', value)
        assert not P.producers(style, shared())['charge']
    trigger.set('damagelevel', '2')
    assert P.producers(style, shared())['charge']


def test_puzzle_unused_local_event_is_not_a_producer():
    style = xml('''<style><FightMove name="power1"><event name="unused" inherit="beam"/>
      <trigger name="test_hit" inherit="punch"/></FightMove></style>''')
    assert not P.producers(style, shared())['charge']


def test_puzzle_move_and_event_inheritance_keep_modifiers_and_tag_updates():
    style = xml('''<style><event name="test_parent" inherit="beam"><damageMod name="dmgmod_weld"/></event>
      <FightMove name="test_base"><event name="test_child" inherit="test_parent"/>
      <trigger tag="1" name="test_child"/></FightMove>
      <FightMove name="power1" inherit="test_base"><trigger tag="1" damagelevel="0"/></FightMove>
      <FightMove name="power2" inherit="power1"><trigger tag="1" damagelevel="2"/></FightMove></style>''')
    p = P.producers(style, shared())
    assert p['charge'] == p['weld'] == {'power2'}


def test_puzzle_chain_destination_counts_but_unreachable_helper_does_not():
    style = xml('''<style><FightMove name="power1"><chain action="Idle" result="test_hold"/></FightMove>
      <FightMove name="test_hold"><trigger name="test_ray" inherit="beam"/></FightMove>
      <FightMove name="unused"><trigger name="test_hit" inherit="punch">
      <damageMod name="dmgmod_extinguish"/></trigger></FightMove></style>''')
    p = P.producers(style, shared())
    assert p['charge'] == {'test_hold'} and not p['extinguish']


def test_puzzle_solo_roster_cannot_borrow_an_unavailable_heros_power():
    plan = {'test_mission': {'zone': 'test/solo/first', 'status': 'seat', 'seat': ['test_melee']}}
    available = P.available_heroes('test/solo/second', plan, ['test_melee', 'test_energy'])
    assert available == {'test_melee'}
    inventory = {'test_melee': {}, 'test_energy': {'charge': {'power1'}}}
    assert P.missing_producers(target('charge'), {h: inventory[h] for h in available})
    plan['other'] = {'zone': 'test/solo/other', 'status': 'seat', 'seat': ['test_melee']}
    assert P.available_heroes('test/solo/second', plan, inventory) == {'test_melee'}
    plan['other']['seat'] = ['test_energy']
    assert P.available_heroes('test/solo/second', plan, inventory) == set(inventory)
    plan['other'] = {'zone': 'test/solo/other', 'status': 'free'}
    assert P.available_heroes('test/solo/second', plan, inventory) == set(inventory)


def test_puzzle_unplaced_definition_is_not_a_progression_requirement():
    root = target('charge')
    root.remove(root.find('entinst'))
    assert not P.missing_producers(root, {})


def test_puzzle_unregistered_attack_type_cannot_satisfy_a_reaction():
    style = xml('''<style><FightMove name="power1"><trigger name="test_ray"
      type="ce_not_registered" damagetype="dmg_energy"/></FightMove></style>''')
    assert not P.producers(style, shared())['charge']


def test_puzzle_overridden_chain_does_not_keep_an_unreachable_producer():
    style = xml('''<style><FightMove name="base"><chain action="Idle" result="test_hold"/></FightMove>
      <FightMove name="power1" inherit="base"><chain action="Idle" result="idle"/></FightMove>
      <FightMove name="test_hold"><trigger name="test_ray" inherit="beam"/></FightMove></style>''')
    assert not P.producers(style, shared())['charge']


def test_puzzle_new_child_trigger_can_use_an_inherited_local_event():
    style = xml('''<style><FightMove name="base"><event name="test_ray" inherit="beam"/></FightMove>
      <FightMove name="power1" inherit="base"><trigger name="test_ray"/></FightMove></style>''')
    assert P.producers(style, shared())['charge'] == {'power1'}


def test_puzzle_validator_rejects_a_missing_solo_producer_even_with_a_roster_donor():
    from types import SimpleNamespace
    from unittest.mock import patch
    from xml1build.validate import Check

    energy = xml('''<style><FightMove name="power1"><trigger name="test_ray" inherit="beam"/>
      </FightMove></style>''')
    melee = xml('''<style><FightMove name="power1"><trigger name="test_hit" inherit="punch"/>
      </FightMove></style>''')
    trees = {P.CE.SHARED_EVENTS_REL: shared(), 'data/powerstyles/test_melee.engb': melee,
             'data/powerstyles/test_energy.engb': energy, 'maps/test/solo/second.engb': target('charge')}
    v = SimpleNamespace(ctx=SimpleNamespace(opt=lambda key: 'seat'), tree=lambda rel: trees.get(rel),
                        stats=lambda: {'by_name': {h: ('herostat', xml(f'<stats powerstyle="{h}"/>'))
                                                  for h in ('test_melee', 'test_energy')}},
                        converted_zones=lambda: ['test/solo/second'])
    plan = {'test_mission': {'zone': 'test/solo/first', 'status': 'seat', 'seat': ['test_melee']}}
    with patch('xml1build.heroes.hero_plan', return_value={'heroes': ['test_melee', 'test_energy']}), \
            patch('xml1build.scripts.forced_party_plan', return_value=plan):
        ck = Check('test', 'test')
        P.validate(v, ck)
        assert len(ck.errors) == 1 and 'test_socket' in ck.errors[0]
        plan['test_mission']['seat'] = ['test_energy']
        ck = Check('test', 'test')
        P.validate(v, ck)
        assert not ck.errors
        energy.find('.//trigger').set('damagetype', 'dmg_physical')
        ck = Check('test', 'test')
        P.validate(v, ck)
        assert len(ck.errors) == 1  # The global donor cannot hide the mutation.
