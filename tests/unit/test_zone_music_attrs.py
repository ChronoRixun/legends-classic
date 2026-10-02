"""SPEC 38 (2026-10-01 audit W8, issue #7) on made-up data - no game files:
XML1's per-zone music override attributes (zones.world_music_attrs). The audit read them as lost overrides; the
builder-side investigation (SPEC 38) found the attributes dead in XML1 retail too - neither default.xbe nor
XMen2.exe contains their names, and no override value names any audio on either disc - so the port plays the
soundfile banks exactly as the Xbox did. The builder collects the attributes for the zone report and says so."""
import xml.etree.ElementTree as ET

from xml1build import zones as Z


def test_world_music_attrs_collects_the_three_attributes():
    world = ET.fromstring('<entity name="world" soundfile="madeup" combatmusic="madeup_combat" '
                          'ambientmusic="madeup_amb" intromusic="madeup_intro"/>')
    assert Z.world_music_attrs(world) == {'ambientmusic': 'madeup_amb', 'combatmusic': 'madeup_combat',
                                          'intromusic': 'madeup_intro'}


def test_world_music_attrs_ignores_absent_and_empty():
    world = ET.fromstring('<entity name="world" soundfile="madeup" combatmusic=""/>')
    assert Z.world_music_attrs(world) == {}
    bare = ET.fromstring('<entity name="world"/>')
    assert Z.world_music_attrs(bare) == {}


def test_music_attrs_are_reported_not_written_to_the_zone():
    # the converted zone XML never carries the attributes: XMen2.exe has no such strings (and neither did
    # default.xbe - SPEC 38), so the engine reads only soundfile, as on the Xbox
    world = ET.fromstring('<entity name="world" soundfile="madeup" combatmusic="madeup_combat"/>')
    Z.world_music_attrs(world)
    assert 'combatmusic' not in world.attrib or world.get('soundfile') == 'madeup'
    assert Z.MUSIC_ATTRS == ('ambientmusic', 'combatmusic', 'intromusic')
