"""Scoped compatibility for scripted approaches blocked by XML2 world geometry."""
import math
import re

# Script -> (zone, spawner, actor, authored end-of-approach marker). The combat
# setup, hazards, allegiance and death script remain the source's own.
APPROACHES = {
    'haarp/int/pyro_intro': ('haarp/int/haarp2_6', 'sp_pyroact01', 'pyro', 'wp_door_spot01'),
}


def _ref(value):
    value = str(value).replace('\\', '/').lower()
    if value.startswith('scripts/'):
        value = value[len('scripts/'):]
    return re.sub(r'\.py$', '', value)


def _placement(actor, marker):
    return ['waittimed ( 0.100 )', f'copyOriginAndAngles("{actor}", "{marker}" )']


def place_after_spawn(text, spawner, actor, marker):
    """Finish a reviewed scripted approach at its existing marker after actor birth.

    act() schedules the spawner; the short game-time wait lets its spawn script
    install the authored waypoint path before the placement. Keep conditional
    scope, and reject source changes rather than silently omitting the correction.
    """
    lines = text.replace('\r\n', '\n').split('\n')
    pattern = re.compile(r'^(\s*)act\s*\(\s*([\'"])' + re.escape(spawner) +
                         r'\2\s*,\s*([\'"])' + re.escape(spawner) + r'\3\s*\)\s*$', re.I)
    matches = [(i, pattern.fullmatch(line)) for i, line in enumerate(lines) if pattern.fullmatch(line)]
    if len(matches) != 1:
        raise ValueError('scripted approach: expected one spawner activation')
    i, match = matches[0]
    block = [match[1] + line for line in _placement(actor, marker)]
    if lines[i + 1:i + 1 + len(block)] != block:
        lines[i + 1:i + 1] = block
    return '\r\n'.join(lines)


def placement_problems(text, spawner, actor, marker):
    try:
        fixed = place_after_spawn(text, spawner, actor, marker)
    except ValueError as ex:
        return [str(ex)]
    normalized = text.replace('\r\n', '\n').replace('\n', '\r\n')
    return [] if fixed == normalized else ['missing the ordered post-spawn wait and approach-marker placement']


def rewrite_script(ref, text):
    entry = APPROACHES.get(_ref(ref))
    if entry is not None:
        _zone, spawner, actor, marker = entry
        return place_after_spawn(text, spawner, actor, marker)
    return text


def validate(validator, ck):
    """V47 (SPEC 78): a converted intro must keep its reviewed placement and marker."""
    for ref, (zone, spawner, actor, marker) in APPROACHES.items():
        rel = f'scripts/{ref}.py'
        if not validator.is_x1(rel):
            continue
        data = validator.read(rel)
        if data is None:
            ck.error(f'{rel}: scripted approach intro is missing')
            continue
        ck.count('intros_checked')
        for problem in placement_problems(data.decode('utf-8-sig'), spawner, actor, marker):
            ck.error(f'{rel}: {problem}')
        root = validator.tree(f'maps/{zone}.engb')
        if root is None:
            root = validator.tree(f'maps/{zone}.xmlb')
        markers = [] if root is None else [el for el in root.iter('inst') if el.get('name') == marker]
        if len(markers) != 1:
            ck.error(f'maps/{zone}: expected one authored approach marker {marker}')
            continue
        try:
            coords = [float(value) for value in markers[0].get('pos', '').split()]
        except ValueError:
            coords = []
        if len(coords) != 3 or not all(math.isfinite(value) for value in coords):
            ck.error(f'maps/{zone}: approach marker {marker} has no usable position')
