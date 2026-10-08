"""The first game's combat balance (issue #14): the power-attack marker, the seven basic melee values, the [Balance]
keys and the switch that holds all of it back. Styles, events and values are invented; only the engine's attribute
names and the seven shared event names appear."""
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from xml1build import balance as B, combat_events as CE, common as C, fix_ini as FI, heroes as H, x1schema as S


class switched:
    """the balance switch for the length of a with block."""

    def __init__(self, on):
        self.on = on

    def __enter__(self):
        self.before = B.X1_BALANCE
        B.X1_BALANCE = self.on

    def __exit__(self, *exc):
        B.X1_BALANCE = self.before


def x1_shared():
    """XML1-style shared events: a basic hit that says it is no power attack, a power attack, a child of each, and
    one that says nothing."""
    root = ET.Element('combat_events')
    ET.SubElement(root, 'event', {'name': 'punch', 'type': 'ce_atk_melee', 'powerattack': 'false'})
    ET.SubElement(root, 'event', {'name': 'zap', 'type': 'ce_atk_blast', 'powerattack': 'true'})
    ET.SubElement(root, 'event', {'name': 'zap_wide', 'inherit': 'zap'})
    ET.SubElement(root, 'event', {'name': 'punch_heavy', 'inherit': 'punch'})
    ET.SubElement(root, 'event', {'name': 'shove', 'type': 'ce_atk_melee'})
    return root


def x2_shared():
    """the shipped shared events: the basic hits are normal, the blast says none, one event says nothing."""
    root = ET.Element('combat_events')
    for name, damage in (('punch', '2 3'), ('kick', '2 3'), ('punch_heavy', '3 5'), ('kick_heavy', '3 5'),
                         ('move_damage', '3 5'), ('punch_veryheavy', '6 9'), ('kick_veryheavy', '6 9')):
        ET.SubElement(root, 'event', {'name': name, 'type': 'ce_atk_melee', 'damage': damage, 'damagescale': 'normal'})
    ET.SubElement(root, 'event', {'name': 'zap', 'type': 'ce_atk_blast', 'damagescale': 'none'})
    ET.SubElement(root, 'event', {'name': 'shove', 'type': 'ce_atk_melee'})
    ET.SubElement(root, 'event', {'name': 'slam', 'inherit': 'punch_heavy', 'damage': '7 8'})
    return root


def style():
    root = ET.Element('fightstyle', {'name': 'ps_invented'})
    ET.SubElement(root, 'event', {'name': 'swipe', 'inherit': 'punch', 'powerattack': 'true', 'damage': '5 6'})
    ET.SubElement(root, 'event', {'name': 'swipe_big', 'inherit': 'swipe', 'damage': '9 9'})
    ET.SubElement(root, 'event', {'name': 'jab', 'inherit': 'swipe', 'powerattack': 'false'})
    ET.SubElement(root, 'event', {'name': 'bolt', 'inherit': 'zap'})
    move = ET.SubElement(root, 'fightmove', {'name': 'attack1'})
    ET.SubElement(move, 'trigger', {'name': 'punch', 'time': '0.2'})                           # a basic hit
    ET.SubElement(move, 'trigger', {'name': 'punch', 'time': '0.4', 'powerattack': 'true'})    # flagged itself
    ET.SubElement(move, 'trigger', {'name': 'swipe_big', 'time': '0.6'})                       # through two events
    ET.SubElement(move, 'trigger', {'name': 'bolt', 'time': '0.8'})                            # already none
    ET.SubElement(move, 'trigger', {'name': 'shove', 'time': '0.9', 'powerattack': 'true'})    # no scale anywhere
    ET.SubElement(move, 'trigger', {'name': 'jab', 'time': '1.0'})
    return root


def tables():
    return B.x1_power_events(x1_shared()), B.shared_scales(x2_shared())


def scales(root):
    return [(e.tag, e.get('name'), e.get('damagescale')) for e in root.iter() if e.tag in ('event', 'trigger')]


def test_the_switch_is_on_since_the_release_and_the_environment_no_longer_overrides_it():
    assert B.X1_BALANCE is True and B.enabled()                    # on since 0.2.0 (SPEC 69.2)
    os.environ['XML1BUILD_X1_BALANCE'] = '0'                       # the pre-release override is gone:
    try:
        assert B.enabled()                                         # the variable changes nothing
    finally:
        os.environ.pop('XML1BUILD_X1_BALANCE', None)
    assert not hasattr(B, 'X1_BALANCE_ENV')
    with switched(False):                                          # a test can still flip the module attribute
        assert not B.enabled()
    assert B.enabled()


def test_shared_tables():
    power, scale = tables()
    assert power == {'punch': False, 'zap': True, 'zap_wide': True, 'punch_heavy': False}      # 'shove' says nothing
    assert scale['punch'] == 'normal' and scale['zap'] == 'none' and scale['shove'] is None
    assert scale['slam'] == 'normal'                                                           # its parent's
    assert B.x1_power_events(None) == {} and B.shared_scales(None) == {}


def test_power_attacks_are_marked_once_at_the_top_of_their_chain():
    power, scale = tables()
    root = style()
    flags = B.x1_power_elements(root, power)
    changes = B.mark_power_attacks(root, flags, scale)
    assert scales(root) == [
        ('event', 'swipe', 'x1power'),          # PowerAttack on a normal punch
        ('event', 'swipe_big', None),           # inherits the marker with the rest of the attack data
        ('event', 'jab', 'normal'),             # XML1 says this child is no power attack
        ('event', 'bolt', None),                # a power attack, but the shipped event is none already
        ('trigger', 'punch', None),             # a basic hit stays a basic hit
        ('trigger', 'punch', 'x1power'),        # flagged on the trigger
        ('trigger', 'swipe_big', None),
        ('trigger', 'bolt', None),
        ('trigger', 'shove', None),             # no damagescale anywhere up the chain: left alone
        ('trigger', 'jab', None)]
    assert changes == {'x1_power_attack:event': 1, 'x1_power_attack:trigger': 1, 'x1_power_attack:cleared': 1}
    assert B.count_markers(root) == 2
    assert not B.mark_power_attacks(root, B.x1_power_elements(root, power), scale)             # idempotent
    assert B.count_markers(root) == 2


def test_an_element_that_sets_its_own_scale_keeps_it():
    power, scale = tables()
    root = ET.Element('fightstyle')
    ET.SubElement(root, 'event', {'name': 'beam_a', 'inherit': 'punch', 'powerattack': 'true', 'damagescale': 'none'})
    ET.SubElement(root, 'event', {'name': 'beam_b', 'inherit': 'punch', 'powerattack': 'true',
                                  'damagescale': 'difficulty'})
    ET.SubElement(root, 'event', {'name': 'beam_c', 'type': 'ce_atk_melee', 'powerattack': 'true'})   # no parent
    assert not B.mark_power_attacks(root, B.x1_power_elements(root, power), scale)
    assert [e.get('damagescale') for e in root] == ['none', 'difficulty', None]


def test_convert_marks_only_for_a_balance_build():
    plain, marked = style(), style()
    S.convert(plain, 'data/powerstyles/ps_invented.xml')
    assert B.count_markers(plain) == 0
    changes = S.convert(marked, 'data/powerstyles/ps_invented.xml', None, None, tables())
    assert B.count_markers(marked) == 2 and changes['x1_power_attack:event'] == 1
    # everything else the conversion does is the same with and without the marker
    for a, b in zip(plain.iter(), marked.iter()):
        assert {k: v for k, v in a.attrib.items() if k != 'damagescale'} == \
               {k: v for k, v in b.attrib.items() if k != 'damagescale'}
    other = style()
    assert not S.convert(other, 'data/entities/invented.xml', None, None, tables()).get('x1_power_attack:event')
    assert B.count_markers(other) == 0                                    # not a style file


def values():
    root = ET.Element('values')
    for name, lo, hi in (('L1', '4', '5'), ('L2', '9', '11'), ('L3', '15', '18')):
        ET.SubElement(root, 'value', {'name': name, 'min': lo, 'max': hi})
    return H.Values(root)


def test_the_seven_basic_attacks_get_the_first_games_values():
    shared = x2_shared()
    assert len(B.basic_attack_problems(shared, values())) == 7
    changed = B.apply_basic_attack_values(shared, values())
    assert sum(changed.values()) == 7 and set(changed) == {f'x1_basic_attack:{n}' for n in B.BASIC_ATTACK_VALUES}
    got = {e.get('name'): e.get('damage') for e in shared}
    assert got['punch'] == got['kick'] == '4 5'
    assert got['punch_heavy'] == got['kick_heavy'] == got['move_damage'] == '9 11'
    assert got['punch_veryheavy'] == got['kick_veryheavy'] == '15 18'
    assert got['slam'] == '7 8' and got['zap'] is None                    # nothing else is touched
    assert all(e.get('damagescale') == 'normal' for e in shared if e.get('name') in B.BASIC_ATTACK_VALUES)
    assert not B.apply_basic_attack_values(shared, values()) and not B.basic_attack_problems(shared, values())
    assert not B.apply_basic_attack_values(None, values()) and not B.apply_basic_attack_values(x2_shared(), None)
    assert set(B.BASIC_ATTACK_VALUES) <= set(CE.X1_SHARED_EVENT_VALUES)
    for name, code in B.BASIC_ATTACK_VALUES.items():                      # the same codes SPEC 33 writes on styles
        assert CE.X1_SHARED_EVENT_VALUES[name][0] == (('damage', code),)


def synthetic_build(out, report):
    (out / 'Scripts' / 'x1' / 'menus').mkdir(parents=True)
    (out / 'Scripts' / 'x1' / 'menus' / 'postgame.py').write_bytes(b'x')
    (out / '_build').mkdir()
    (out / '_build' / 'report.json').write_text(json.dumps({'build': report}))


def test_ini_keys_only_for_a_balance_build_with_the_switch_on():
    with tempfile.TemporaryDirectory() as td:
        plain, bal = Path(td) / 'plain', Path(td) / 'bal'
        synthetic_build(plain, {'xp_curve': 'xml1', B.REPORT_KEY: 'xml2'})
        synthetic_build(bal, {'xp_curve': 'xml1', B.REPORT_KEY: B.REPORT_ON})
        with switched(False):
            for out in (plain, bal):                                     # switch off: no balance keys anywhere
                keys = FI.port_keys(out)
                assert 'Balance' not in keys and keys['Online'] == {'GameVersion': FI.PORT_GAME_VERSION}
            assert 'Balance' not in FI.port_owned() and FI.port_owned() == FI.PORT_OWNED
            assert 'Balance' not in FI.dropped_keys({'Game': {}})
        with switched(True):
            keys = FI.port_keys(plain)
            assert 'Balance' not in keys and keys['Online'] == {'GameVersion': FI.PORT_GAME_VERSION}
            keys = FI.port_keys(bal)
            assert keys['Online'] == {'GameVersion': FI.PORT_GAME_VERSION}             # one version: every build is a balance build
            assert keys['Balance'] == {'EnemyHealthPerBody': '10', 'HeroHealthPerBody': '2.5', 'HeroStatScale': str(H.STAT_SCALE),
                                       'NativeStatHeroes': 'ProfXAstral,ProfXGladiator', 'StrengthBonus': '0.1',
                                       'MindBonus': '0.1', 'MightBonus': '0.05', 'PowerAttacks': 'xml1',
                                       'HitChance': 'xml1', 'Rounding': 'xml1', 'DamageRolls': 'xml1'}
            assert set(keys['Balance']) <= set(FI.port_owned()['Balance'])
            # a build that stops being a balance build drops the section's keys, tuning keys included
            gone = FI.dropped_keys(FI.port_keys(plain))['Balance']
            assert 'HitChance' in gone and 'HitChanceBase' in gone and 'HeroHealthPerBody' in gone
            # the harness writes the same section
            sys.path.insert(0, str(Path(C.__file__).resolve().parents[1]))
            import harness
            text = harness.ini_text('windowed', 1280, 720, True, port_identity=True, balance=True)
            assert FI.parse_ini(text)['Balance'] == keys['Balance'] and f'GameVersion={FI.PORT_GAME_VERSION}' in text
            assert '[Balance]' not in harness.ini_text('windowed', 1280, 720, True, port_identity=True)


def test_ini_merge_of_the_balance_section_keeps_the_rest():
    with switched(True), tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'xml2-fix.ini'
        p.write_bytes(b'[Display]\r\nMode=windowed\r\n\r\n[Balance]\r\nHitChanceBase=26\r\nMine=1\r\n')
        keys = {'Balance': FI.balance_keys()}
        FI.merge_ini(p, keys, FI.dropped_keys(keys))
        got = FI.read_ini(p)
        assert got['Display'] == {'Mode': 'windowed'} and got['Balance']['HitChance'] == 'xml1'
        assert 'HitChanceBase' not in got['Balance'] and got['Balance']['Mine'] == '1'      # a foreign key stays
