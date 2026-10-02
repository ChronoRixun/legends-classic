"""Narrow script/data replacements for XML1 boss phase states absent from XMen2.exe.

Only issue #2's three encounters are handled. Original phase counters, timers, rewards and
follow-on scripts remain authoritative. Output scripts use CRLF, like the rest of the builder.
"""
import re

MAGNETO_STAGES = frozenset(f'asteroid_m/stage{i}' for i in range(2, 6))
MAGNETO_ZONE = 'maps/astroid_m/visit1/asteroid2_1'
SHADOW_SCRIPTS = frozenset(('astral/savepx/sk1pain', 'astral/savepx/dropshield'))
MASTER_SPAWN = 'mastermold/mmspawn'
SHADOW_ZONE = 'maps/astral/savepx/final_astral'


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


def guard_before(text, anchor, condition, statement):
    """Insert a guarded action before a unique script anchor; fail closed if source structure changes."""
    lines = text.replace('\r\n', '\n').split('\n')
    locations = [i for i, line in enumerate(lines) if line.strip() == anchor]
    if len(locations) != 1:
        raise ValueError(f'boss phase anchor {anchor!r}: expected once, got {len(locations)}')
    i = locations[0]
    block = [f'if {condition}', '     ' + statement, 'endif']
    if lines[max(0, i - len(block)):i] != block:
        lines[i:i] = block
    return '\r\n'.join(lines)


def rewrite_script(ref, text):
    ref = _ref(ref)
    if ref in MAGNETO_STAGES:
        stage = ref[-1]
        text, count = insert_after_call(text, 'setPatternSequence', 'magneto', f'mag{stage}',
                                       ['setInvulnerable("magneto", "FALSE" )'])
        if not count and 'setInvulnerable("magneto", "FALSE" )' not in text:
            raise ValueError(f'{ref}: missing boss phase transition')
    elif ref in SHADOW_SCRIPTS:
        for state, enabled in (('sk3', 'TRUE'), ('sk4', 'FALSE')):
            text, _ = insert_after_call(text, 'setPatternSequence', 'shadowking', state,
                                       [f'setInvulnerable("shadowking", "{enabled}" )'])
    elif ref == MASTER_SPAWN:
        # checkcore sets stage 4 when the shield is permanently disabled. Do not restore it
        # on a later spawn/load after the cores have been completed.
        text = guard_before(text, 'if stage == 0', 'stage < 4',
                            'setCombatNode("mastermold", "shockshield_on" )')
    return text


def relocate_spawn(root, spawn_type, floor_type):
    """Use an existing walkable spawn position; preserve the boss instance's identity and facing."""
    groups = {e.get('type'): e for e in root.iter('entinst')}
    source = list(groups.get(floor_type, ()))
    target = list(groups.get(spawn_type, ()))
    if len(source) != 1 or len(target) != 1 or not source[0].get('pos'):
        raise ValueError('boss floor placement: expected one boss and one floor start')
    pos = source[0].get('pos')
    if target[0].get('pos') == pos:
        return 0
    target[0].set('pos', pos)
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
        return relocate_spawn(root, 'sp_shadowking01', 'player_start')
    if _ref(rel) == MAGNETO_ZONE:
        return protect_relay(root, 'shieldup', 'magneto', 'magshield')
    return 0
