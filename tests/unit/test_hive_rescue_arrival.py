"""Synthetic Hive rescue arrival: a second resident volume appended last, and the freed-Morlock script guard."""
import copy
import inspect
import xml.etree.ElementTree as ET

from xml1build import common as C, escort_triggers as E, zones
from xml1build import death_targets as DT, offset_residents as RO, progression_relays as PR
from xml1build import settle as SE, x1schema as XS
from lcsave import zonecompat as Z
from lcsave.binds import numbered_entities
from test_escort_triggers import fixture

ZONE = E.HIVE_ZONE
REL = 'maps/' + ZONE + '.eng'

# Invented script in the shape the guard expects (no game text): one activator-name read, a waypoint request.
SCRIPT = '\r\n'.join(['# invented header', 'who = getName("_ACTIVATOR_" )', 'seen = getZoneVar(who )',
                      'if seen == 0', '     setWaypointPath("_ACTIVATOR_", "invented_path", 1 )',
                      '     setZoneVar(who, 1 )', 'endif', ''])


def converted():
    root = fixture(ZONE)
    assert E.convert(root, ZONE) == 1
    return root


def box(pos, extents):
    p = [float(v) for v in pos.split()]
    e = [float(v) for v in extents.split()]
    return [p[i] + e[i] for i in range(3)], [p[i] + e[3 + i] for i in range(3)]


def test_arrival_is_appended_last_with_the_authored_contract():
    root = converted()
    old = [(t, n) for t, n, _ in numbered_entities(root)[0]]
    trigger = copy.deepcopy(root.find(f'entity[@name="{E.RESCUES[ZONE][0]}"]').attrib)
    assert E.append_arrivals(root, REL) == 1
    arrival = root.find(f'entity[@name="{E.ARRIVAL}"]').attrib
    assert {k: v for k, v in arrival.items() if k not in ('name', E.ARRIVAL_MARKER)} == \
        {k: v for k, v in trigger.items() if k != 'name'}
    assert arrival['actteamplayer'] == 'false' and arrival['team'] == 'none' and arrival['actmatchteam'] == 'true'
    last = root.findall('entinst')[-1]
    assert last.get('type') == E.ARRIVAL
    assert [i.attrib for i in last] == [dict(name=E.ARRIVAL, pos=E.ARRIVAL_POS, extents=E.ARRIVAL_EXTENTS)]
    new = [(t, n) for t, n, _ in numbered_entities(root)[0]]
    assert new[:len(old)] == old and new[len(old):] == [(E.ARRIVAL, E.ARRIVAL)]
    before = C.encode_xmlb(root)
    assert E.append_arrivals(root, REL) == 0 and C.encode_xmlb(root) == before      # idempotent
    assert E.problems(root, REL) == []
    assert root.find(f'entity[@name="{E.RESCUES[ZONE][0]}"]').attrib == trigger    # authored volume untouched


def test_arrival_box_spares_gateway_and_kincaid_and_reaches_the_landing():
    lo, hi = box(E.ARRIVAL_POS, E.ARRIVAL_EXTENTS)
    inside = lambda x, y: lo[0] <= x <= hi[0] and lo[1] <= y <= hi[1]
    assert lo[0] - 1720.69 >= 60                         # Gateway's origin, with margin for his bound
    assert lo[1] >= 1192 and not inside(1814.69, 614.0)  # north of the authored box; Kincaid's waypoints outside
    assert inside(1845.32, 1431.58) and inside(2033.6, 1433.1) and inside(2190.0, 1470.0)
    assert (lo[2], hi[2]) == (-120.0, 120.0)


def test_saved_prefix_attests_as_an_append_and_not_as_an_equivalent():
    root = converted()
    previous = C.encode_xmlb(root)
    E.append_arrivals(root, REL)
    current = C.encode_xmlb(root)
    proof = Z.attest(ZONE, previous, current)
    assert proof is not None and proof['fresh_aliases'] == proof['ambiguous_aliases'] == []
    assert len(proof['placements']) == len(numbered_entities(C.decode_xmlb(previous))[0])
    assert Z.attest_equivalent(ZONE, previous, current) is None


def test_arrival_fails_closed_and_validator_rejects_changes():
    root = converted()
    root.remove(root.find('entity[@name="invented_cell_rescuee5"]'))
    before = C.encode_xmlb(root)
    try:
        E.append_arrivals(root, REL)
    except ValueError:
        pass
    else:
        raise AssertionError('changed rescuee set must reject')
    assert C.encode_xmlb(root) == before
    for change in ('moved', 'not_last', 'altered', 'missing'):
        root = converted()
        E.append_arrivals(root, REL)
        if change == 'moved':
            root.findall('entinst')[-1].find('inst').set('pos', '1720 1340 -120')
        elif change == 'not_last':
            ET.SubElement(ET.SubElement(root, 'entinst', type='invented_cell_rescuee1'), 'inst', name='x', pos='0 0 0')
        elif change == 'altered':
            root.find(f'entity[@name="{E.ARRIVAL}"]').set('actscript', 'invented/other')
        else:
            root.remove(root.find(f'entity[@name="{E.ARRIVAL}"]'))
        assert E.problems(root, REL), change
    other_zone = next(z for z in E.RESCUES if z != ZONE)
    other = fixture(other_zone)
    assert E.append_arrivals(other, 'maps/' + other_zone + '.eng') == 0
    ET.SubElement(other, 'entity', name='stray', **{E.ARRIVAL_MARKER: 'true'})
    assert E.arrival_problems(other, 'maps/invented/zone.eng')


def test_arrival_follows_every_older_numbered_tail():
    root = converted()
    ET.SubElement(root, 'entity', name='x1_settle_0', classname='physent', smartent='false', **{SE.MARKER: 'true'})
    ET.SubElement(ET.SubElement(root, 'entinst', type='x1_settle_0'), 'inst', name='box', pos='9 9 9')
    ET.SubElement(root, 'entity', name='lava', classname='affectableharment', smartent='false',
                  **{XS.HAZARD_BOUNDS_MARKER: 'true'})
    ET.SubElement(ET.SubElement(root, 'entinst', type='lava'), 'inst', name='lava', pos='1 1 1',
                  extents='-1 -1 -1 1 1 1')
    ET.SubElement(root, 'entity', name=RO.PREFIX + 'field', classname='physent', smartent='false',
                  **{RO.MARKER: 'true'})
    ET.SubElement(ET.SubElement(root, 'entinst', type=RO.PREFIX + 'field'), 'inst', name='field', pos='0 0 0')
    assert E.append_arrivals(root, REL) == 1
    assert SE.numbered_tail_problems(root, XS.post_settle_names(root, REL)) == []
    assert XS.hazard_bounds_tail_problems(root) == []
    assert XS.numbered_entinst_tail_problems(root, REL) == []
    assert not [p for p in DT.problems(root) if 'saved ordinals' in p]
    assert not [p for p in RO.problems(root) if 'saved ordinals' in p]
    assert E.problems(root, REL) == []


def test_progression_validator_ignores_the_later_arrival_tail():
    from test_progression_relays import world
    zone_name = 'sewers/grso/sewers3_1_1'
    root = world()
    assert PR.convert(root, zone_name, {}) == 1
    ET.SubElement(root, 'entity', name='invented_arrival', classname='gameent', **{E.ARRIVAL_MARKER: 'true'})
    ET.SubElement(ET.SubElement(root, 'entinst', type='invented_arrival'), 'inst', name='invented_arrival',
                  pos='0 0 0')
    assert not PR.problems(root, zone_name)


def test_zone_conversion_appends_the_arrival_after_the_offset_residents():
    source = inspect.getsource(zones)
    start = source.index('    def mutate_zone(')
    body = source[start:source.index('\n    def ', start + 10)]
    assert body.index('self.convert_offset_residents(zone, root, st)') < body.index('ETG.append_arrivals(root')


def test_script_guard_wraps_the_body_for_the_five_rescuees_only():
    fixed = E.rewrite_script('scripts/' + E.HIVE_SCRIPT + '.py', SCRIPT)
    lines = fixed.split('\r\n')
    assert lines[:2] == SCRIPT.split('\r\n')[:2]
    assert E.GUARD_MARKER in lines and lines[-2:] == ['endif', '']
    assert [l for l in lines if l.startswith('if who == ')] == [f'if who == "{n}"' for n in E.HIVE_RESCUEES]
    assert '          setWaypointPath("_ACTIVATOR_", "invented_path", 1 )' in lines   # one level deeper
    assert E.rewrite_script(E.HIVE_SCRIPT, fixed) == fixed                             # idempotent
    assert E.script_problems(SCRIPT) and E.script_problems(fixed) == []
    assert E.rewrite_script('invented/other', SCRIPT) == SCRIPT


def test_script_guard_fails_closed_on_a_changed_source():
    for bad in (SCRIPT.replace('getName', 'getID'), SCRIPT.replace('setWaypointPath', 'setPath'),
                SCRIPT + 'again = getName("_ACTIVATOR_" )\r\n'):
        try:
            E.rewrite_script(E.HIVE_SCRIPT, bad)
        except ValueError:
            continue
        raise AssertionError('changed rescue script must reject')
    fixed = E.rewrite_script(E.HIVE_SCRIPT, SCRIPT)
    assert E.script_problems(fixed.replace('rescuee5', 'invented6'))


def test_script_rewrite_runs_in_the_base_text_pass():
    from xml1build import scripts
    assert 'ETG.rewrite_script(ref, text)' in inspect.getsource(scripts._base_text)
