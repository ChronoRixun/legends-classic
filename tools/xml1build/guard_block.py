"""Private Guard fallback: PC rank-one energy policy, independent of saved talents.

Rule 46 registers ch_guard_block only with GuardDecideRule=xml1. The node is
emitted into both shared tables so enabling the INI option cannot leave an
unresolved node. The native ch_pain reaction and retail blocking stay intact.
"""
import xml.etree.ElementTree as ET


def make_node():
    node = ET.Element('FightMove', name='guardblocking', handler='ch_guard_block',
                      animenum='ea_blocking', lockangles='true', locktransitionangles='true')
    ET.SubElement(node, 'trigger', name='powerusage', powerusage='1', time='-1')
    effect = ET.SubElement(node, 'trigger', name='powerup', time='0', life='-1',
                           remove_on_node_end='true')
    ET.SubElement(effect, 'affecter', affect_type='scale', attribute='damage_to_energy', level='1')
    ET.SubElement(node, 'chain', action='special', result='idle')
    return node


def install(top):
    for old in list(top):
        if (old.get('name') or '').lower() == 'guardblocking':
            top.remove(old)
    top.append(make_node())


def problems(root):
    nodes = [n for n in root.iter() if (n.get('name') or '').lower() == 'guardblocking']
    if len(nodes) != 1:
        return ['requires exactly one guardblocking node']
    node = nodes[0]
    expected = make_node()
    issues = []
    if any(node.get(k) != v for k, v in expected.attrib.items()):
        issues.append('guardblocking handler, animation or locking differs from the native block contract')
    if node.findall('require'):
        issues.append('guardblocking must not require a saved block skill')
    for child in expected:
        if not any(c.tag == child.tag and c.attrib == child.attrib and
                   [(a.tag, a.attrib) for a in c] == [(a.tag, a.attrib) for a in child]
                   for c in node):
            issues.append(f'guardblocking missing exact native {child.tag} contract: {child.attrib}')
    if len(node) != len(expected):
        issues.append('guardblocking has unexpected effects or chains')
    return issues
