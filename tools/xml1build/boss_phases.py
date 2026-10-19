"""Narrow script/data replacements for XML1 boss phase states absent from XMen2.exe.

Handles the Magneto, Shadow King and HAARP boss encounters. Original phase counters, timers, rewards and
follow-on scripts remain authoritative. Output scripts use CRLF, like the rest of the builder.
"""
import re

MAGNETO_STAGES = frozenset(f'asteroid_m/stage{i}' for i in range(2, 6))
MAGNETO_ZONE = 'maps/astroid_m/visit1/asteroid2_1'
SHADOW_SCRIPTS = frozenset(('astral/savepx/sk1pain', 'astral/savepx/dropshield'))
SHADOW_START = 'astral/savepx/final_astral'
SHADOW_ZONE = 'maps/astral/savepx/final_astral'
SHADOW_FLOOR_MARKER = 'wp_bossmaster3000_04'
SHADOW_DEFEATED = 'astral/savepx/shadowking_defeated'
TOAD_ZONE = 'maps/haarp/ext/haarp_ext_boss'
TOAD_LANDING_SCRIPTS = frozenset(f'haarp/ext/pillar{i:02}' for i in range(1, 5))


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


def end_on_real_death(text, store, count_check, real, images, done_var, dispel=4):
    """SPEC 36.5: a death script shared by a boss and the images he summoned ends the fight when the REAL one is
    gone, whatever the kill order. XML1 counted three deaths; on XMen2.exe an image that dies after the real one runs
    nothing, so image -> real -> image never reached the count. After the counter is stored (`store`, a unique line),
    the script waits half a second, asks alive(real), and the condition line (`count_check`, e.g. 'if n == 3') becomes
    'if go == 1': the old count still ends it, so does the real one's death; a zone var `done_var` (read and set in
    the same frame) lets exactly one run end the fight; the leftover images are removed. Fails closed if the source
    shape changes; a second call is a no-op."""
    if f'getZoneVar("{done_var}" )' in text:
        return text
    lines = text.replace('\r\n', '\n').split('\n')
    at =[i for i, line in enumerate(lines) if line.strip() == store]
    check = [i for i, line in enumerate(lines) if line.strip() == count_check]
    if len(at) != 1 or len(check) != 1 or check[0] < at[0]:
        raise ValueError(f'end_on_real_death: expected one {store!r} before one {count_check!r}')
    count = count_check.split()[1]
    limit = count_check.split()[-1]
    block = ['go = iadd(0, 0 )',
             f'if {count} >= {limit}', '     go = iadd(1, 0 )', 'endif',
             'waittimed ( 0.500 )',
             f'realalive = alive("{real}" )',
             'if realalive == 0', '     go = iadd(1, 0 )', 'endif',
             f'ending = getZoneVar("{done_var}" )',
             'if ending == 1', '     go = iadd(0, 0 )', 'endif',
             'if go == 1', f'     setZoneVar("{done_var}", 1 )']
    block += [f'     remove ( "{images}", "{images}" )'] * dispel + ['endif']
    lines[check[0]] = lines[check[0]].replace(count_check, 'if go == 1')
    lines[at[0] + 1:at[0] + 1] = block
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
    elif ref == SHADOW_DEFEATED:
        # SPEC 36.5: the second form's death ends the fight whatever happened to his mirror images
        text = end_on_real_death(text, 'setZoneVar("deadsks", deadsks )', 'if deadsks == 3', 'shadowking2',
                                 'shadowkingtwo', 'sk_ending')
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


def npc_landing_triggers(root, scripts):
    """Find the encounter's authored enemy-only landing volumes; reject changed filters.

    XML1's actteamplayer tests actor+0x335 bit 0x20 (0x28420); XML2 instead requires
    actor+0x3d4 != -1 (0x41b5b0), excluding the boss. Its team check and the script's
    named-activator check still restrict each volume after removing this extra filter.
    """
    found = []
    for el in root.iter('entity'):
        if _ref(el.get('actscript', '')) not in scripts:
            continue
        expected = {'classname': 'gameent', 'team': 'enemy', 'actmatchteam': 'true',
                    'actontouch': 'true', 'actleader': 'false'}
        if any(el.get(k, '').lower() != v for k, v in expected.items()):
            raise ValueError('boss landing trigger: unexpected activation filter')
        found.append(el)
    if len(found) != len(scripts) or {_ref(el.get('actscript')) for el in found} != set(scripts):
        raise ValueError('boss landing trigger: expected one volume per landing script')
    return found


def allow_npc_landings(root, scripts):
    """Keep placement, ordinals, targets and scripts; only remove the player-controller gate."""
    rows = npc_landing_triggers(root, scripts)
    count = 0
    for el in rows:
        if el.get('actteamplayer', '').lower() != 'false':
            el.set('actteamplayer', 'false')
            count += 1
    return count


def landing_trigger_problems(root, rel):
    if _ref(rel) != TOAD_ZONE:
        return []
    try:
        rows = npc_landing_triggers(root, TOAD_LANDING_SCRIPTS)
    except ValueError as exc:
        return [str(exc)]
    return [f'{el.get("name")}: boss landing requires a player controller'
            for el in rows if el.get('actteamplayer', '').lower() != 'false']


def rewrite_data(root, rel):
    if _ref(rel) == TOAD_ZONE:
        return allow_npc_landings(root, TOAD_LANDING_SCRIPTS)
    if _ref(rel) == SHADOW_ZONE:
        return relocate_spawn(root, 'sp_shadowking01', 'waypoint',
                              floor_name=SHADOW_FLOOR_MARKER, height_type='player_start')
    if _ref(rel) == MAGNETO_ZONE:
        return protect_relay(root, 'shieldup', 'magneto', 'magshield')
    return 0
