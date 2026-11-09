"""Append resident delivery actions without changing existing door/save identities.

Only audited one-shot gates qualify. Pollers consult saved prerequisites and skip open doors.
Healer's guard-death activation is caught by a resident listener; a local touch volume can
reconstruct its latch on older saves, where dead guards have no event left to deliver.
"""
from __future__ import annotations
import copy
import hashlib
import xml.etree.ElementTree as ET

MARKER = 'xml1progressionrelay'
PREFIX = 'x1/progression/'
HEALER = 'sewers/healer/sewers2_1_4'
EXITS = {'sewers/grso/sewers3_1_1': ('exitdoor1', 'ladders', 'porters'),
         'sewers/grso/sewers3_1_2': ('exitdoor2', 'ladders2', 'porters2')}
NUKE = 'nuke_plant/nuke/nuke2_2'


def flag(zone, target):
    return 'lp' + hashlib.sha256((zone.lower() + '|' + target.lower()).encode('ascii')).hexdigest()[:6]


def names(root):
    return {e.get('name') for e in root.iter('entity') if e.get(MARKER)}


def convert(root, zone, scripts=None):
    """Return newly protected target count; emit ref->text. Existing entities are immutable."""
    zone = zone.lower()
    scripts = {} if scripts is None else scripts
    defs = {e.get('name'): e for e in root.iter('entity')}
    placed = {i.get('name'): (g, i) for g in root.findall('entinst') for i in g.findall('inst')}
    targets = ([EXITS[zone][0]] if zone in EXITS else ['healer_door'] if zone == HEALER else
               ['blastdoor_nuke_n04', 'blastdoor_nuke_n05'] if zone == NUKE else [])
    added = 0

    def append(name, attrs, instances):
        attrs = dict(attrs, name=name)
        if name in defs:
            groups = [g for g in root.findall('entinst') if g.get('type') == name]
            if defs[name].attrib != attrs or len(groups) != 1 or [i.attrib for i in groups[0]] != instances:
                raise ValueError('progression relay collision: ' + name)
            return False
        defs[name] = ET.SubElement(root, 'entity', attrs)
        group = ET.SubElement(root, 'entinst', type=name)
        for inst in instances:
            ET.SubElement(group, 'inst', inst)
        return True

    for target in targets:
        if target not in placed:
            continue
        group, inst = placed[target]
        door = defs.get(group.get('type'))
        if door is None or door.get('classname') != 'doorent' or door.get('smartent') == 'false':
            raise ValueError('progression target must retain its original streamed door: ' + target)
        ref = PREFIX + zone + '/' + target
        if zone in EXITS:
            _, a, b = EXITS[zone]
            conditions = [f'lc_pr_a = getObjective("{a}", "COMPLETE")',
                          f'lc_pr_b = getObjective("{b}", "COMPLETE")',
                          'if lc_pr_a == 1', '    if lc_pr_b == 1']
            depth = 2
        elif zone == HEALER:
            key = flag(zone, target)
            conditions = [f'lc_pr_a = getGameFlag("{key}", 1)', 'if lc_pr_a == 1']
            depth = 1
            listen = 'lc_pr_listen_' + target
            append(listen, dict(classname='actionent', smartent='false', startenabled='true',
                                actonuse='false', toggleonact='false', xml1progressionrelay='listen',
                                actscript=f'setGameFlag("{key}",1,1)'),
                   [dict(name='trigger_enabler', pos=inst.get('pos', '0 0 0'))])
            guards = [i for g in root.findall('entinst') if g.get('type') == 'ss_morlockclawb09' for i in g]
            if not guards:
                raise ValueError('missing healer guard recovery origins')
            recover = 'lc_pr_recover_' + target
            recovery_ref = PREFIX + zone + '/guards'
            scripts[recovery_ref] = ('waittimed(0.25)\nlc_pr_alive = alive("scripted_grunt")\n'
                                     f'if lc_pr_alive < 1\n    setGameFlag("{key}",1,1)\nendif\n')
            # Each volume lies at an original guard origin: dormant remote guards never imply death.
            append(recover, dict(classname='gameent', smartent='false', startenabled='true',
                                 actontouch='true', actonuse='false', actteamplayer='true',
                                 actmatchteam='true', team='hero', boxcollision='true', nocollide='true',
                                 toggleonact='false', xml1progressionrelay='recover', actscript=recovery_ref),
                   [dict(name=recover+'_'+str(n), pos=i.get('pos'), extents='-96 -96 -24 96 96 144')
                    for n, i in enumerate(guards)])
        else:
            conditions = ['lc_pr_panel = getID("trigger_use02")', 'if lc_pr_panel > 0',
                          '    lc_pr_a = getEnable(lc_pr_panel)', '    if lc_pr_a == 0']
            depth = 2
        lines = list(conditions)
        def line(text, extra=0):
            lines.append('    ' * (depth + extra) + text)
        line(f'lc_pr_id = getID("{target}")')
        line('if lc_pr_id > 0')
        line('lc_pr_open = getOpened(lc_pr_id)', 1)
        line('if lc_pr_open == 0', 1)
        line(('act' if zone == NUKE else 'setEnable') + '(lc_pr_id, ' +
             ('lc_pr_id)' if zone == NUKE else '"TRUE")'), 2)
        line('endif', 1)
        line('endif')
        lines += ['    ' * d + 'endif' for d in reversed(range(depth))]
        scripts[ref] = '\n'.join(lines) + '\n'
        poll = 'lc_pr_poll_' + target
        added += append(poll, dict(classname='actionent', smartent='false', startenabled='true',
                                   actonuse='false', toggleonact='false', xml1progressionrelay='poll',
                                   xml1progressiontarget=target, firstact='0.25', actrescheduledelay='0.25',
                                   actscript=ref), [dict(name=poll, pos=inst.get('pos', '0 0 0'))])
    return added


def problems(root, zone):
    # Reconstruct the complete generated tail from the immutable original map. Merely carrying a marker
    # cannot exempt an arbitrary action from numbering checks or claim streaming coverage.
    expected = copy.deepcopy(root)
    marked = names(root)
    for child in list(expected):
        if ((child.tag == 'entity' and child.get('name') in marked) or
                (child.tag == 'entinst' and child.get('type') in marked)):
            expected.remove(child)
    try:
        convert(expected, zone)
    except ValueError as exc:
        return [str(exc)]
    def canonical(e):
        return (e.tag, sorted(e.attrib.items()), [canonical(c) for c in e])
    errors = []
    if canonical(root) != canonical(expected):
        errors.append('missing, altered or unexpected progression delivery relay')
    in_tail = False
    for group in root.findall('entinst'):
        if group.get('type') in marked:
            in_tail = True
        elif in_tail:
            errors.append('progression relay precedes an old placement (saved ordinals shift)')
    return errors
