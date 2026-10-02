"""Narrow script/data replacements for XML1 boss phase states absent from XMen2.exe.

Only issue #2's Magneto and Shadow King encounters are handled. Original phase counters, timers, rewards and
follow-on scripts remain authoritative. Output scripts use CRLF, like the rest of the builder.
"""
import re

MAGNETO_STAGES = frozenset(f'asteroid_m/stage{i}' for i in range(2, 6))
MAGNETO_ZONE = 'maps/astroid_m/visit1/asteroid2_1'
SHADOW_SCRIPTS = frozenset(('astral/savepx/sk1pain', 'astral/savepx/dropshield'))
SHADOW_START = 'astral/savepx/final_astral'
SHADOW_ZONE = 'maps/astral/savepx/final_astral'
SHADOW_FLOOR_MARKER = 'wp_bossmaster3000_04'


def _ref(path):
    value = str(path).replace('\\', '/').lower()
    if value.startswith('scripts/'):
        value = value[len('scripts/'):]
    return re.sub(r'\.(py|eng|xml|engb|xmlb)$', '', value)


def insert_after_call(text, function, actor, value, statements):
    """Append statements at each matching call, keeping its conditional indentation."""
    lines = text.replace('\r\n', '\n').split('\n')
    pattern = re.compile(r'^(\s*)' + re.escape(function) + r'\s*\(\s*([\'"])' + re.escape(actor) +
                         r'\2\s*,\s*([\'"])' + re.escape(value) + r'\3\s*\)\s*$', re.I)
    out, changed = [], 0
    for i, line in enumerate(lines):
        out.append(line)
        match = pattern.fullmatch(line)
        if match:
            added = [match[1] + stmt for stmt in statements]
            if lines[i + 1:i + 1 + len(added)] != added:
                out.extend(added)
                changed += 1
    return '\r\n'.join(out), changed


def guard_before(text, anchor, condition, statement, setup=()):
    """Insert a guarded action before a unique script anchor; fail closed if source structure changes."""
    lines = text.replace('\r\n', '\n').split('\n')
    locations = [i for i, line in enumerate(lines) if line.strip() == anchor]
    if len(locations) != 1:
        raise ValueError(f'boss phase anchor {anchor!r}: expected once, got {len(locations)}')
    i = locations[0]
    statements = (statement,) if isinstance(statement, str) else statement
    block = list(setup) + [f'if {condition}'] + ['     ' + line for line in statements] + ['endif']
    if lines[max(0, i - len(block)):i] != block:
        lines[i:i] = block
    return '\r\n'.join(lines)


def rewrite_script(ref, text):
    ref = _ref(ref)
    if ref in MAGNETO_STAGES:
        stage = ref[-1]
        text, count = insert_after_call(text, 'setPatternSequence', 'magneto', f'mag{stage}',
                                       ['waittimed ( 0.100 )', 'setInvulnerable("magneto", "FALSE" )'])
        if not count and 'setInvulnerable("magneto", "FALSE" )' not in text:
            raise ValueError(f'{ref}: missing boss phase transition')
    elif ref in SHADOW_SCRIPTS:
        for state, enabled in (('sk3', 'TRUE'), ('sk4', 'FALSE')):
            text, _ = insert_after_call(text, 'setPatternSequence', 'shadowking', state,
                                       [f'setInvulnerable("shadowking", "{enabled}" )'])
    elif ref == SHADOW_START:
        # Also relocate an existing first-form actor on zone entry; changing only the
        # initial spawner would not help a saved actor that still has its old position.
        text = guard_before(text, 'setDefaultTarget("shadowking" )', 'boss_alive == 1',
                            [f'copyOriginAndAngles("shadowking", "{SHADOW_FLOOR_MARKER}" )',
                             'boss_z = getPosZ("player_start" )',
                             'setPosZ("shadowking", boss_z )'],
                            setup=('boss_alive = alive("shadowking" )',))
    return text


def _single_instance(root, entity_type, name=None):
    matches = [inst for group in root.iter('entinst') if group.get('type') == entity_type
               for inst in group if inst.tag == 'inst' and (name is None or inst.get('name') == name)]
    if len(matches) != 1:
        raise ValueError('boss floor placement: expected one matching instance')
    return matches[0]


def relocate_spawn(root, spawn_type, floor_type, *, floor_name=None, height_type=None):
    """Use a named floor marker, optionally at an existing walkable start's height.

    Waypoint Z can be below the visible arena. Retain its XY but use the known floor Z
    in that case. Never change the party start or the second-form spawn.
    """
    source = _single_instance(root, floor_type, floor_name)
    target = _single_instance(root, spawn_type)
    coords = source.get('pos', '').split()
    if len(coords) != 3:
        raise ValueError('boss floor placement: expected three marker coordinates')
    if height_type:
        height = _single_instance(root, height_type).get('pos', '').split()
        if len(height) != 3:
            raise ValueError('boss floor placement: expected three floor coordinates')
        coords[2] = height[2]
    pos = ' '.join(coords)
    if target.get('pos') == pos:
        return 0
    target.set('pos', pos)
    return 1


def protect_relay(root, relay, actor, phase):
    """Attach protection to the existing relay; keep its original targets and counter behavior."""
    count = 0
    for el in root.iter():
        if el.tag.lower() != 'entity' or (el.get('name') or '').lower() != relay:
            continue
        code = el.get('actscript', '')
        command = f'setInvulnerable("{actor}","TRUE")'
        if command in code:
            continue
        expected = r'setPatternSequence\s*\(\s*[\'"]' + re.escape(actor) + r'[\'"]\s*,\s*[\'"]' + re.escape(phase) + r'[\'"]'
        if not re.search(expected, code, re.I):
            raise ValueError(f'{relay}: expected {phase} transition')
        el.set('actscript', code + r'\n\r' + command)
        count += 1
    return count


def rewrite_data(root, rel):
    if _ref(rel) == SHADOW_ZONE:
        return relocate_spawn(root, 'sp_shadowking01', 'waypoint',
                              floor_name=SHADOW_FLOOR_MARKER, height_type='player_start')
    if _ref(rel) == MAGNETO_ZONE:
        return protect_relay(root, 'shieldup', 'magneto', 'magshield')
    return 0
