"""Invented course/actor fixtures for the course-only spawn cloak conversion."""
import xml.etree.ElementTree as ET
import tempfile
from pathlib import Path

from xml1build import danger_room_actors as D
from xml1build import fix_ini as FI


def fixture():
    stats = ET.Element('statslist')
    scout = ET.SubElement(stats, 'stats', name='TinScout', skin='12345', team='enemy', powerstyle='ps_tin')
    ET.SubElement(scout, 'Talent', name='spawn_invis', level='1')
    ET.SubElement(scout, 'Race', name='Robot')
    ET.SubElement(scout, 'talent', name='later_cloak', level='2')
    ET.SubElement(scout, 'talent', name='fightstyle_example')
    ET.SubElement(stats, 'stats', name='PlainScout', skin='12346', team='enemy')
    campaign = ET.SubElement(stats, 'stats', name='CampaignOnly')
    ET.SubElement(campaign, 'talent', name='spawn_invis')
    courses = ET.Element('root')
    first = ET.SubElement(courses, 'COURSE', name='exercise_a')
    ET.SubElement(first, 'SPAWNER', character='TINSCOUT', count='3')
    ET.SubElement(first, 'MUSTDIE', character='TinScout')
    ET.SubElement(first, 'MUSTSURVIVE', character='TinScout')
    ET.SubElement(first, 'SPAWNER', character='PlainScout')
    second = ET.SubElement(courses, 'COURSE', name='exercise_b')
    ET.SubElement(second, 'SPAWNER', character='TinScout')
    return courses, stats


def test_variants_cover_every_course_spawn_kind_without_mutating_campaign_data():
    courses, stats = fixture()
    before = ET.tostring(stats), ET.tostring(courses)
    plan = D.actor_variants(courses, stats)
    assert set(plan) == {'tinscout'} and len(set(plan.values())) == 1
    alias = plan['tinscout']
    assert len(alias) < 19 and alias != 'tinscout'
    clone = D.visible_variant(stats[0], alias)
    assert clone.get('skin') == '12345' and clone.get('team') == 'enemy'
    assert clone.get('powerstyle') == 'ps_tin' and not D.has_spawn_cloak(clone)
    assert [c.get('name') for c in clone if c.tag.lower() == 'talent'] == ['later_cloak', 'fightstyle_example']
    assert (ET.tostring(stats), ET.tostring(courses)) == before
    # Reordering courses or unrelated stats cannot renumber persistent aliases.
    stats.insert(0, ET.Element('stats', name='AnotherScout'))
    courses[:] = list(reversed(courses))
    assert D.actor_variants(courses, stats) == plan


def test_alias_collision_is_rejected_instead_of_replacing_a_real_actor():
    courses, stats = fixture()
    alias = D.actor_variants(courses, stats)['tinscout']
    stats.append(ET.Element('stats', name=alias))
    try:
        D.actor_variants(courses, stats)
    except ValueError:
        return
    raise AssertionError('existing actor would be overwritten')


def test_party_fallback_requires_a_companion_that_recognizes_the_key():
    keys = {'Game': {'DangerRoomParty': 'xml1'}}
    assert FI.game_keys(xml1_opening=True)['DangerRoomParty'] == 'xml1'
    assert 'DangerRoomParty' not in FI.game_keys(xml1_opening=False)
    assert 'DangerRoomParty' in FI.PORT_OWNED['Game']
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'companion.dll'
        dll.write_bytes(b'SYNTHETIC')
        try:
            FI.check_release_dll(dll, keys)
        except FI.FixTooOld as exc:
            assert exc.missing == ['[Game] DangerRoomParty']
        else:
            raise AssertionError('unsupported companion accepted')
        dll.write_bytes(b'SYNTHETIC' + 'DangerRoomParty'.encode('utf-16le'))
        FI.check_release_dll(dll, keys)


def test_training_gauges_require_the_presentation_fix_without_changing_course_data():
    keys = {'Game': {'DangerRoomHealthBars': 'xml1'}}
    assert FI.game_keys(xml1_opening=True)['DangerRoomHealthBars'] == 'xml1'
    assert 'DangerRoomHealthBars' not in FI.game_keys(xml1_opening=False)
    assert 'DangerRoomHealthBars' in FI.PORT_OWNED['Game']
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'companion.dll'
        dll.write_bytes(b'SYNTHETIC')
        try:
            FI.check_release_dll(dll, keys)
        except FI.FixTooOld as exc:
            assert exc.missing == ['[Game] DangerRoomHealthBars']
        else:
            raise AssertionError('companion without training gauges accepted')
        dll.write_bytes(b'SYNTHETIC' + 'DangerRoomHealthBars'.encode('utf-16le'))
        FI.check_release_dll(dll, keys)


def test_boxed_harm_requires_supported_companion():
    keys = {'Game': {'BoxHarmOrigin': 'xml1'}}
    assert FI.game_keys(xml1_opening=True)['BoxHarmOrigin'] == 'xml1'
    assert 'BoxHarmOrigin' not in FI.game_keys(xml1_opening=False)
    assert 'BoxHarmOrigin' in FI.PORT_OWNED['Game']
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'companion.dll'
        dll.write_bytes(b'SYNTHETIC')
        try:
            FI.check_release_dll(dll, keys)
        except FI.FixTooOld as exc:
            assert exc.missing == ['[Game] BoxHarmOrigin']
        else:
            raise AssertionError('companion without training gauges accepted')
        dll.write_bytes(b'SYNTHETIC' + 'BoxHarmOrigin'.encode('utf-16le'))
        FI.check_release_dll(dll, keys)
