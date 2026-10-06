"""SPEC 35 (2026-10-01, the haarp_ext02 bridge softlock) on made-up data - no game files:
entities a zone's scripts name by string literal, and entities whose own script moves "_OWNER_" along a motion
path, get smartent="false" (zones.pin_scripted_entities); XMen2.exe streams every other entity by hero distance."""
import xml.etree.ElementTree as ET

from xml1build import zones as Z

ZONE = """<world name="world" zonescript="made/up/zone">
<entinst type="rover"><inst name="rover" pos="900 -1400 300"/></entinst>
<entinst type="gate"><inst name="gate" pos="900 -1100 300"/></entinst>
<entity name="rover" classname="physent" model="made/up/rover" spawnscript="made/up/rover_setup"/>
<entity name="rover_base" classname="physent" model="made/up/rover_base" smartent="false"/>
<entity name="gate" classname="doorent" startenabled="false" toggleonact="true"/>
<entity name="decor_crate" classname="physent" model="made/up/crate"/>
<entity name="start01" classname="playerstartent"/>
<entity name="pond" classname="waterent"/>
<entity name="floor_pad" classname="physent" actscript="made/up/liftoff"/>
<entity name="floor_pad2" classname="physent" actscript="x=1\\n\\rstartMotionPath('_OWNER_','made/up/lift/mp_lift','TRUE','')"/>
<entity name="guard_spawner" classname="monsterspawnerent" startenabled="false"/>
<entity name="hint_sign" classname="physent" actscript="setInvisible('decor_crate','TRUE')"/>
<entity name="nameless" classname="physent"/>
<entity name="noclass" model="made/up/thing"/>
<entity name="stream_me" classname="physent" smartent="true"/>
<entinst type="hex_tank"><inst name="tank1" pos="1 2 3"/><inst name="tank2" pos="4 5 6"/><inst name="hex_tank" pos="7 8 9"/></entinst>
<entity name="hex_tank" classname="physent" model="made/up/hex"/>
<entinst type="barrel"><inst name="barrel" pos="0 0 0"/></entinst>
<entity name="barrel" classname="physent" model="made/up/barrel"/>
</world>"""

SCRIPTS = {
    'made/up/zone': 'setGameFlag("made", 1, 1 )\r\nact("guard_spawner", "guard_spawner" )\r\n',
    'made/up/reveal': ('setInvisible("rover", "FALSE" )\r\nact("gate", "gate" )\r\n'
                       'startMotionPath("rover", "made/up/rover/mp_rover", "FALSE", "rover_done" )\r\n'
                       'waitsignal ( "rover_done" )\r\nsound (  "PLAY_SOUND", "zone_shared/objects/x", "_ACTIVE_HERO_", "" )\r\n'
                       "copyOriginAndAngles('_HERO1_', 'stream_me' )\r\n"),
    'made/up/rover_setup': 'setInvisible("_OWNER_", "TRUE" )\r\n',
    'made/up/liftoff': 'startMotionPath("_OWNER_", "made/up/lift/mp_lift", "TRUE", "" )\r\n',
    'made/up/tanks': 'startMotionPath("tank2", "made/up/tanks/mp_tank2", "FALSE", "" )\r\n',
    'made/up/unreadable': None,
}


def pins_of(zone=ZONE, scripts=SCRIPTS):
    root = ET.fromstring(zone)
    pinned = Z.pin_scripted_entities(root, dict(scripts))
    return root, pinned, {n: why for n, _, why in pinned}


def test_script_name_literals_keep_plain_names_only():
    names = Z.script_name_literals([SCRIPTS['made/up/reveal'], None, "act('a_b-c.d', 'x')"])
    assert {'rover', 'gate', 'rover_done', 'stream_me', 'a_b-c.d', 'x', 'play_sound', 'false'} <= names
    assert not any('/' in n for n in names)                        # paths and sound names never qualify
    assert not any(n.startswith('_') for n in names)               # _HERO1_ / _ACTIVE_HERO_ / _OWNER_ are not names


def test_named_entities_are_pinned_in_document_order():
    root, pinned, why = pins_of()
    assert [n for n, _, _ in pinned] == ['rover', 'gate', 'decor_crate', 'floor_pad', 'floor_pad2', 'guard_spawner',
                                         'hex_tank']
    assert why['rover'] == 'named by a zone script'               # startMotionPath target (the bridge tank)
    assert why['gate'] == 'named by a zone script'                 # act() target 900 units from the heroes
    assert why['decor_crate'] == 'named by a zone script'          # named only by an entity's inline actscript
    assert why['guard_spawner'] == 'named by a zone script'        # named by the world's zonescript
    ents = {e.get('name'): e for e in root.iter('entity')}
    for n in ('rover', 'gate', 'decor_crate', 'floor_pad', 'floor_pad2', 'guard_spawner'):
        assert ents[n].get('smartent') == 'false', n


def test_instance_names_pin_their_entity_type():
    root, _, why = pins_of()
    ents = {e.get('name'): e for e in root.iter('entity')}
    assert why['hex_tank'] == 'type of the instance(s) tank2'    # the script names the inst, not the type
    assert ents['hex_tank'].get('smartent') == 'false'
    assert ents['barrel'].get('smartent') is None                  # an inst nobody names pins nothing
    insts = [i for ei in root.iter('entinst') for i in ei]
    assert not any(i.get('smartent') for i in insts)               # smartent never goes on an inst


def test_owner_motion_paths_pin_the_owner():
    _, _, why = pins_of()
    assert why['floor_pad'] == 'actscript moves _OWNER_ on a motion path'     # by script ref
    assert why['floor_pad2'] == 'actscript moves _OWNER_ on a motion path'    # by inline code


def test_untouched_entities():
    root, _, why = pins_of()
    ents = {e.get('name'): e for e in root.iter('entity')}
    assert ents['rover_base'].get('smartent') == 'false' and 'rover_base' not in why   # XML1's own value stays
    assert ents['stream_me'].get('smartent') == 'true' and 'stream_me' not in why      # named, but XML1 chose
    assert ents['start01'].get('smartent') is None                 # playerstartent: never pinned
    assert ents['pond'].get('smartent') is None                    # waterent: never pinned
    assert ents['hint_sign'].get('smartent') is None               # has inline code, is not named itself
    assert ents['nameless'].get('smartent') is None                # named by nothing
    assert ents['noclass'].get('smartent') is None                 # no classname: left alone


def test_second_run_is_a_no_op_and_unreadable_scripts_are_ignored():
    root = ET.fromstring(ZONE)
    first = Z.pin_scripted_entities(root, dict(SCRIPTS))
    again = Z.pin_scripted_entities(root, dict(SCRIPTS))
    assert first and again == []
    root2 = ET.fromstring(ZONE)                                    # only the entities' inline code remains
    assert Z.pin_scripted_entities(root2, {'made/up/unreadable': None}) == [
        ('decor_crate', 'physent', 'named by a zone script'),
        ('floor_pad2', 'physent', 'actscript moves _OWNER_ on a motion path')]


def test_a_hero_unlock_does_not_pin_an_entity_of_the_same_name():
    # since 0.1.8 a mission zone's script unlocks its heroes; a spawner sharing a hero's name must stay smart, or it
    # takes an ordinal and every saved zone record of the zone lands on the next entity
    zone = """<world name="world">
<entinst type="hero_x"><inst name="hero_x" pos="0 0 0"/></entinst>
<entity name="hero_x" classname="monsterspawnerent" monster_name="someone"/>
<entity name="crate_y" classname="physent"/>
</world>"""
    unlock = {'made/up/zone': 'unlockCharacter("hero_x", "" )\r\nunlockCharacter( "crate_y","")\r\n'}
    assert Z.pin_scripted_entities(ET.fromstring(zone), unlock) == []
    named = {'made/up/zone': 'unlockCharacter("crate_y", "" )\r\nact("hero_x", "hero_x" )\r\n'}
    assert [n for n, _, _ in Z.pin_scripted_entities(ET.fromstring(zone), named)] == ['hero_x']
