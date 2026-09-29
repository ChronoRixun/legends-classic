"""Test helper: add an instance of an existing entity type at a new position in a zone XMLB/engb.

usage: add_spawn_inst.py <zone_file> <entinst_type> <x> <y> <z>
Copies the first <inst> of that <entinst> group, moves it and appends it. `extents` are entity-local in XML2
(zones section 17), so they are copied unchanged.
"""
import copy, sys
import xmlb

path, etype, x, y, z = sys.argv[1], sys.argv[2], *map(float, sys.argv[3:6])
root = xmlb.decode(open(path, 'rb').read())
group = next(g for g in root.iter('entinst') if g.get('type') == etype)
inst = copy.deepcopy(group[0])
inst.set('pos', f'{x:g} {y:g} {z:g}')
inst.set('name', etype)
group.append(inst)
open(path, 'wb').write(xmlb.encode(root))
print('added', etype, 'at', inst.get('pos'), 'group now', len(group))
