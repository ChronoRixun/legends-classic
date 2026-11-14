"""NPC-name-dependent XML1 rescue volumes with incompatible player-owner filters.

XML1 activation 0x28420 tests actor+0x335 bit 0x20. XML2 0x41b5b0
instead requires a controller at actor+0x3d4. Following a hero does not
assign one (0x4a48f0), so these neutral NPCs never reach their scripts.

Hive arrival (SPEC "Hive rescue arrival"): the Subject Retention Center's one
authored volume covers only the south half of Gateway's room. XML2 followers
led in by the north-east stairs reach Gateway and the waitspot without
entering it. A second resident volume with the same definition contract
covers that side of the room; it is appended after every numbered tail so
saved ordinals keep their meaning. The shared script then rescues only the
five freed Morlocks, so Gateway and other neutral actors are never sent to
the portal.
"""
import copy
import re
import xml.etree.ElementTree as ET


RESCUES = {
    'arbiter/a_int/arb3_1': ('rescue_trigger', 'arbiter/rescue_complete'),
    **{f'arbiter/a_int/arb3_{i}': ('trigger_touch01', 'arbiter/rescue_complete') for i in range(2, 5)},
    'demo/a_int/arb3_1': ('rescue_trigger', 'arbiter/rescue_complete'),
    'demo/a_int/arb3_2': ('trigger_touch01', 'arbiter/rescue_complete'),
    'nyc/riots/nyc3_1_2': ('trigger_amb', 'nyc/riots/rescue_complete2'),
    'nyc/riots/nyc3_1_3': ('trigger_touch01', 'nyc/riots/rescue_complete3'),
    'nyc/riots/nyc3_2_1': ('trigger_touch01', 'nyc/riots/rescue_complete4'),
    'hive/h_int/hive2_2_4': ('trigger_prisoner3', 'hive/h_int/hive_trigger_rescue'),
}

HIVE_ZONE = 'hive/h_int/hive2_2_4'
HIVE_SCRIPT = 'hive/h_int/hive_trigger_rescue'
HIVE_RESCUEES = tuple(f'rescuee{i}' for i in range(1, 6))
RESCUEE_SCRIPT = 'hive/h_int/use_rescuee'
ARRIVAL_MARKER = 'xml1rescuearrival'
ARRIVAL = 'lc_rescue_arrival_trigger_prisoner3'
# World box x 1790..2200, y 1192..1720, z -120..120: the north-east stair foot, the landing,
# the waitspot and the portal, north of the authored box (y <= 1192.26) and at least 63 units
# east of Gateway's origin (x 1720.69); Kincaid's waypoints (y <= 614) stay outside.
ARRIVAL_POS = '1995 1456 -120'
ARRIVAL_EXTENTS = '-205 -264 0 205 264 240'
GUARD_MARKER = '# ( "x1: Legends Classic rescues only the freed Morlocks (Gateway arrival volume)" )'
GUARD_FLAG = 'lc_rescuee'


def _zone(rel):
    return re.sub(r'\.(eng|xml|engb|xmlb)$', '', str(rel).replace('\\', '/').lower()).removeprefix('maps/')


def _trigger(root, rel):
    spec = RESCUES.get(_zone(rel))
    if spec is None:
        return None
    name, script = spec
    rows = [el for el in root.iter('entity') if el.get('name') == name]
    if len(rows) != 1:
        raise ValueError('escort rescue: expected one named volume definition')
    el = rows[0]
    expected = {'classname': 'gameent', 'team': 'none', 'actmatchteam': 'true',
                'actontouch': 'true', 'actleader': 'false', 'boxcollision': 'true', 'actscript': script}
    if any(el.get(k) != v for k, v in expected.items()) or el.get('actteamplayer') not in {'true', 'false'}:
        raise ValueError('escort rescue: changed script or activation filters')
    placements = [inst for group in root.iter('entinst') if group.get('type') == name
                  for inst in group.findall('inst')]
    if len(placements) != 1:
        raise ValueError('escort rescue: expected one volume placement')
    return el


def names(root):
    """Appended rescue-arrival definitions (they follow every other numbered tail)."""
    return {e.get('name') for e in root.iter('entity') if e.get(ARRIVAL_MARKER) == 'true'}


def _arrival_definition(el):
    attrs = dict(el.attrib)
    attrs.update(name=ARRIVAL, actteamplayer='false')   # the corrected owner filter (convert)
    attrs[ARRIVAL_MARKER] = 'true'
    return attrs


def _arrival_placement():
    return dict(name=ARRIVAL, pos=ARRIVAL_POS, extents=ARRIVAL_EXTENTS)


def _rescuee_names(root):
    return sorted(e.get('monster_name') or '' for e in root.iter('entity')
                  if e.get('classname') == 'monsterspawnerent' and e.get('monster_actscript') == RESCUEE_SCRIPT)


def append_arrivals(root, rel):
    """Append the Hive arrival volume after every existing entinst; existing entities stay as they are.

    Call it last, after the offset residents. Returns 1 when it appended the volume."""
    if _zone(rel) != HIVE_ZONE:
        return 0
    el = _trigger(root, rel)
    if _rescuee_names(root) != list(HIVE_RESCUEES):
        raise ValueError('escort rescue: unexpected Hive rescuee spawners')
    attrs, inst = _arrival_definition(el), _arrival_placement()
    rows = [e for e in root.iter('entity') if e.get('name') == ARRIVAL]
    groups = [g for g in root.findall('entinst') if g.get('type') == ARRIVAL]
    if rows or groups:
        if (len(rows) != 1 or rows[0].attrib != attrs or len(groups) != 1
                or [i.attrib for i in groups[0]] != [inst]):
            raise ValueError('escort rescue: arrival collision')
        return 0
    ET.SubElement(root, 'entity', attrs)
    ET.SubElement(ET.SubElement(root, 'entinst', type=ARRIVAL), 'inst', inst)
    return 1


def arrival_problems(root, rel):
    """The arrival exists exactly as append_arrivals writes it, in the last entinst; nowhere else."""
    marked = names(root)
    if _zone(rel) != HIVE_ZONE:
        return [f'{n}: rescue arrival outside its zone' for n in sorted(marked)]
    expected = copy.deepcopy(root)
    for child in list(expected):
        if (child.tag == 'entity' and child.get('name') in marked | {ARRIVAL}) or \
                (child.tag == 'entinst' and child.get('type') in marked | {ARRIVAL}):
            expected.remove(child)
    try:
        append_arrivals(expected, rel)
    except ValueError as exc:
        return [str(exc)]
    out = []
    want = [e.attrib for e in expected.iter('entity') if e.get('name') == ARRIVAL]
    have = [e.attrib for e in root.iter('entity') if e.get('name') == ARRIVAL]
    if want != have or marked != {ARRIVAL}:
        out.append('missing or altered Hive rescue arrival volume')
    groups = root.findall('entinst')
    types = [g.get('type') for g in groups]
    if types.count(ARRIVAL) != 1 or types[-1] != ARRIVAL:
        out.append('Hive rescue arrival must be the last entinst (saved ordinals shift)')
    elif [i.attrib for i in groups[-1]] != [_arrival_placement()]:
        out.append('altered Hive rescue arrival placement')
    return out


_GETNAME = re.compile(r'^\s*(\w+)\s*=\s*getName\s*\(\s*"_ACTIVATOR_"\s*\)\s*$')


def _guard(var):
    lines = [GUARD_MARKER, f'{GUARD_FLAG} = iadd(0, 0 )']
    for n in HIVE_RESCUEES:
        lines += [f'if {var} == "{n}"', f'     {GUARD_FLAG} = iadd(0, 1 )', 'endif']
    return lines + [f'if {GUARD_FLAG} == 1']


def _script_ref(ref):
    ref = str(ref).replace('\\', '/').lower()
    return re.sub(r'\.py$', '', ref.removeprefix('scripts/'))


def rewrite_script(ref, text):
    """Hive rescue script: run the authored body only for the five freed Morlocks.

    Gateway, prisonerx and Kincaid are neutral too; the arrival volume must never send them to the portal.
    A changed source (no single activator-name read, no waypoint request) fails closed."""
    if _script_ref(ref) != HIVE_SCRIPT:
        return text
    lines = text.replace('\r\n', '\n').split('\n')
    while lines and not lines[-1].strip():
        lines.pop()
    if GUARD_MARKER in lines:
        if not _is_guarded(lines):
            raise ValueError(f'{ref}: altered rescue guard')
        return '\r\n'.join(lines + [''])
    hits = [i for i, line in enumerate(lines) if _GETNAME.match(line)]
    if len(hits) != 1:
        raise ValueError(f'{ref}: expected one activator name read')
    i = hits[0]
    body = lines[i + 1:]
    if not any(re.match(r'\s*setWaypointPath\s*\(\s*"_ACTIVATOR_"', line) for line in body):
        raise ValueError(f'{ref}: expected the rescue waypoint request')
    out = lines[:i + 1] + _guard(_GETNAME.match(lines[i])[1]) + \
        [('     ' + line) if line.strip() else line for line in body] + ['endif', '']
    return '\r\n'.join(out)


def _is_guarded(lines):
    i = lines.index(GUARD_MARKER)
    if i < 1 or not _GETNAME.match(lines[i - 1]):
        return False
    guard = _guard(_GETNAME.match(lines[i - 1])[1])
    return lines[i:i + len(guard)] == guard and lines[-1] == 'endif' and lines.count(GUARD_MARKER) == 1


def script_problems(text):
    """[] when the shipped rescue script carries exactly the freed-Morlock guard."""
    lines = text.replace('\r\n', '\n').split('\n')
    while lines and not lines[-1].strip():
        lines.pop()
    if GUARD_MARKER not in lines:
        return ['rescue script lacks the freed-Morlock guard']
    return [] if _is_guarded(lines) else ['altered rescue guard']


def convert(root, rel):
    """Clear only the incompatible owner filter; retain names, teams and save order."""
    el = _trigger(root, rel)
    if el is None or el.get('actteamplayer') == 'false':
        return 0
    el.set('actteamplayer', 'false')
    return 1


def problems(root, rel):
    try:
        el = _trigger(root, rel)
    except ValueError as exc:
        return [str(exc)]
    out = ['rescue volume requires a player controller'] if el is not None and el.get('actteamplayer') != 'false' else []
    if el is not None and _zone(rel) == HIVE_ZONE:
        out += arrival_problems(root, rel)
    return out
