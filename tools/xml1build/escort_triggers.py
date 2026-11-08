"""NPC-name-dependent XML1 rescue volumes with incompatible player-owner filters.

XML1 activation 0x28420 tests actor+0x335 bit 0x20. XML2 0x41b5b0
instead requires a controller at actor+0x3d4. Following a hero does not
assign one (0x4a48f0), so these neutral NPCs never reach their scripts.
"""
import re


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
    return ['rescue volume requires a player controller'] if el is not None and el.get('actteamplayer') != 'false' else []
