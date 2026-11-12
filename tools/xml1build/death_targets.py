"""Latch destruction delivery while retaining original door save identities.

Only fixed-console, one-shot, non-autoclosing gates qualify. A resident listener
shares the target name and records activation; a separate native scheduled
action retries it. Door and console definitions and placements are unchanged.
Restored, indestructible console stumps latch the corresponding original event.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET

MARKER = 'xml1deathrelay'
STUMP_MARKER = 'xml1deathrelaystump'
PREFIX = 'x1/death_targets/'
FLAG_BIT = 1  # XMen2.exe's game-flag bit arguments are one-based (1..32).
_SEPARATORS = re.compile(r'[ ,\t\r\n]+')
_SAFE_NAME = re.compile(r'[A-Za-z0-9_]+\Z')


def links(root):
    definitions = {e.get('name'): e for e in root.iter('entity')}
    placed, by_type = {}, {}
    for group in root.findall('entinst'):
        for inst in group.findall('inst'):
            placed.setdefault(inst.get('name', '').lower(), []).append((group.get('type'), inst))
            by_type.setdefault(group.get('type'), []).append(inst)
    result = {}
    for source in definitions.values():
        if source.get('classname') != 'physent' or source.get('actondeath', '').lower() != 'true':
            continue
        stump = definitions.get(source.get('deathspawn'))
        if stump is None or stump.get('classname') != 'physent' or stump.get('name') in by_type:
            continue
        if stump.get('spawnscript') and stump.get(STUMP_MARKER) != 'true':
            continue
        if stump.get('nogravity') != 'true' or stump.get('mass') != '0' or stump.get('structure') not in ('2', '10'):
            continue
        value = source.get('acttargets', '') if source.get('acttargets') or source.get('actscript') else source.get('deathtargets', '')
        for target in filter(None, _SEPARATORS.split(value.strip())):
            if not _SAFE_NAME.fullmatch(target):
                continue
            for typ, inst in placed.get(target.lower(), ()):
                door = definitions.get(typ)
                if door is None or door.get('classname') != 'doorent' or door.get('smartent') is not None:
                    continue
                if door.get('actonuse') != 'false' or door.get('toggleonact') != 'true' or door.get('actcountdisable') != '1' or door.get('autoclosedelay', '0') != '0':
                    continue
                if door.get('startenabled', 'true') != 'true' or door.get('requirekey') or any(
                        door.get(key, '').lower() == 'true' for key in ('actleader', 'actteamplayer', 'actmatchteam', 'actmustface')):
                    continue
                for origin in by_type.get(source.get('name'), ()):
                    try:
                        pos = tuple(float(v) for v in origin.get('pos', '').split())
                    except ValueError:
                        continue
                    if len(pos) == 3:
                        result.setdefault(inst.get('name').lower(), dict(target=inst.get('name'), door=typ, stump=stump.get('name'), sources=[]))['sources'].append((source.get('name'), pos))
    selected = list(result.values())
    for i, left in enumerate(selected):
        for right in selected[i + 1:]:
            if left['stump'] != right['stump']:
                continue
            if any(a != b and all(abs(x-y) <= 16 for x,y in zip(p,q))
                   for a,p in left['sources'] for b,q in right['sources']):
                raise ValueError('ambiguous destroyed-console origins')
    return selected


def door_targets(root):
    selected = {link['door'] for link in links(root)}
    return [e for e in root.iter('entity') if e.get('name') in selected]


def names(root):
    return {e.get('name') for e in root.iter('entity') if e.get(MARKER) == 'true'}


def flag(zone, target):
    return 'lh' + hashlib.sha256((zone.lower() + '|' + target.lower()).encode('ascii')).hexdigest()[:6]


def convert(root, zone='synthetic/zone', scripts=None):
    """Append listeners/pollers; emit generated ref -> source through scripts.

    Native firstact/actrescheduledelay drives short scripts; no waiting contexts
    or recursive script calls are needed. Existing door states stay smart.
    """
    scripts = scripts if scripts is not None else {}
    selected = links(root)
    definitions = {e.get('name'): e for e in root.iter('entity')}
    stumps, changed = {}, 0
    for link in selected:
        target = link['target']
        key = flag(zone, target)
        ref = PREFIX + zone.lower() + '/' + target.lower()
        scripts[ref] = (f'lc_dt_open = getGameFlag("{key}", {FLAG_BIT})\n'
                        f'if lc_dt_open == 1\n    act("{target}", "{target}")\nendif\n')
        listener, poller = 'lc_dt_listen_' + target, 'lc_dt_poll_' + target
        common = dict(classname='actionent', startenabled='true', actonuse='false', toggleonact='false',
                      smartent='false', xml1deathrelay='true', xml1deathtarget=target)
        attrs = {listener: dict(common, actscript=f'setGameFlag("{key}",{FLAG_BIT},1)', xml1deathrole='listen'),
                 poller: dict(common, actscript=ref, firstact='0.25', actrescheduledelay='0.25', xml1deathrole='poll')}
        existed = listener in definitions or poller in definitions
        for name, values in attrs.items():
            values = dict(values, name=name)
            if name in definitions:
                if definitions[name].attrib != values:
                    raise ValueError('destruction relay name collision: ' + name)
                groups = [g for g in root.findall('entinst') if g.get('type') == name]
                expected_inst = dict(name=target if name == listener else name, pos='0 0 0')
                if len(groups) != 1 or len(groups[0]) != 1 or groups[0][0].attrib != expected_inst:
                    raise ValueError('destruction relay placement differs: ' + name)
                continue
            definitions[name] = ET.SubElement(root, 'entity', values)
            group = ET.SubElement(root, 'entinst', type=name)
            ET.SubElement(group, 'inst', name=target if name == listener else name, pos='0 0 0')
        changed += not existed
        stumps.setdefault(link['stump'], []).append((key, link['sources']))
    for name, entries in stumps.items():
        ref = PREFIX + zone.lower() + '/stump_' + name.lower()
        lines = ['waittimed(0.25)', 'lc_dt_x = getPosX("_OWNER_")',
                 'lc_dt_y = getPosY("_OWNER_")', 'lc_dt_z = getPosZ("_OWNER_")']
        for key, origins in entries:
            for _, pos in origins:
                tests = []
                for axis, value in zip('XYZ', pos):
                    tests += [f'lc_dt_{axis.lower()} >= {int(value)-8}', f'lc_dt_{axis.lower()} <= {int(value)+8}']
                for depth, test in enumerate(tests):
                    lines.append('    ' * depth + 'if ' + test)
                lines.append('    ' * len(tests) + f'setGameFlag("{key}",{FLAG_BIT},1)')
                lines.extend('    ' * depth + 'endif' for depth in reversed(range(len(tests))))
        scripts[ref] = '\n'.join(lines) + '\n'
        stump = definitions[name]
        stump.set('smartent', 'false')
        stump.set('spawnscript', ref)
        stump.set(STUMP_MARKER, 'true')
    return changed


def problems(root, zone='synthetic/zone'):
    import copy
    expected = copy.deepcopy(root)
    try:
        missing = convert(expected, zone)
    except ValueError as exc:
        return [str(exc)]
    out = ['missing destruction delivery relay' for _ in range(missing)]
    marked = names(root)
    expected_names = {prefix + link['target'] for link in links(root) for prefix in ('lc_dt_listen_', 'lc_dt_poll_')}
    out += ['invalid destruction relay marker: ' + name for name in sorted(marked - expected_names)]
    stump_names = {link['stump'] for link in links(root)}
    out += ['invalid destruction stump marker: ' + e.get('name', '') for e in root.iter('entity')
            if e.get(STUMP_MARKER) == 'true' and e.get('name') not in stump_names]
    from . import offset_residents as RO
    from . import progression_relays as PR
    later = PR.names(root) | RO.names(root)
    in_tail = False
    for group in root.findall('entinst'):
        if group.get('type') in marked:
            in_tail = True
        elif in_tail and group.get('type') not in later:
            out.append('new destruction relay precedes an old entinst (saved ordinals shift)')
    for link in links(root):
        actual = next(e for e in root.iter('entity') if e.get('name') == link['stump'])
        wanted = next(e for e in expected.iter('entity') if e.get('name') == link['stump'])
        if actual.attrib != wanted.attrib:
            out.append('destruction stump needs resident recovery script')
    return out
