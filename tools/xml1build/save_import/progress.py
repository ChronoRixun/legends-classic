"""Scoped script-variable packing; never treats Xbox integers as entity tokens."""
from __future__ import annotations

from .errors import ImportRefusal


def pack_variables(source, rows, scope, approximated):
    output, masks = {}, {}
    seen = set()
    for family, cells in source.items():
        for cell in cells:
            name, value = cell['name'], cell['value']
            candidates = [r for r in rows if r['family'] == family and r['name'].lower() == name and r['scope'] == scope]
            if len(candidates) > 1:
                raise ImportRefusal('BUILD', 'Ambiguous scoped variable mappings.', variable=name)
            if not candidates:
                if value:
                    approximated('unmapped_variable', f'{family}:{name}', value, None,
                                 'No final scoped storage mapping; the checkpoint initializes it.')
                continue
            row = candidates[0]
            identity = (family, name, scope)
            if identity in seen:
                raise ImportRefusal('CONTEXT', 'Duplicate variable mapping.')
            seen.add(identity)
            if row['kind'] == 'transient':
                approximated('transient_variable', f'{family}:{name}', value, None,
                             'Old-world entity handles and timers are reset at checkpoint entry.')
                continue
            target = row['target']
            if not 0 < len(target.encode('ascii')) < 12:
                raise ImportRefusal('BUILD', 'Target variable name exceeds the native limit.')
            if row.get('source_signed') and value & 0x80000000:
                value -= 0x100000000
            width, first = row['width'], row.get('first_bit', 1)
            if not 1 <= width <= 32 or not 1 <= first <= 33 - width:
                raise ImportRefusal('BUILD', 'Variable storage width is invalid.')
            signed = row.get('signed', False)
            lo, hi = (-(1 << (width - 1)), (1 << (width - 1)) - 1) if signed else (0, (1 << width) - 1)
            if not lo <= value <= hi:
                raise ImportRefusal('CAPACITY', 'A source counter does not fit its final target width.', variable=name, value=value, minimum=lo, maximum=hi)
            if row['kind'] not in ('pack', 'flag'):
                raise ImportRefusal('BUILD', 'Unsupported persistent variable storage kind.')
            bits = ((1 << width) - 1) << (first - 1)
            if masks.get(target, 0) & bits:
                raise ImportRefusal('BUILD', 'Overlapping final variable storage ranges.', variable=target)
            masks[target] = masks.get(target, 0) | bits
            output[target] = output.get(target, 0) | ((value & ((1 << width) - 1)) << (first - 1))
    if len(output) > 16:
        raise ImportRefusal('CAPACITY', 'Too many persistent script variables for the native game.')
    return [dict(name=name, value=value) for name, value in sorted(output.items())]


def checkpoint(ir, recipes):
    if ir['side_depth']:
        raise ImportRefusal('SIDE_MISSION')
    mission = ir['mission']
    values = {(family, row['name']): row['value'] for family, rows in ir['variables'].items() for row in rows}
    matches = []
    for r in recipes:
        if r['mission_id'] != mission['mission_id'] or r['source_zone'].lower() != mission['zone'].lower():
            continue
        if all((p['family'], p['name']) in values and values[(p['family'], p['name'])] == p['value'] for p in r.get('predicates', [])):
            matches.append(r)
    if len(matches) != 1:
        raise ImportRefusal('CONTEXT', 'Exactly one checkpoint recipe must match.', matches=len(matches), mission_id=mission['mission_id'], zone=mission['zone'])
    recipe = matches[0]
    # Only the four confirmed copied timer floats are checked here. Other CGame
    # semantics remain unresolved and are reported/defaulted by the mapper.
    import struct
    if any(x != 0 for x in struct.unpack_from('<4f', ir['game'])):
        raise ImportRefusal('CONTEXT', 'This checkpoint requires idle source timers.')
    party = [n.lower() for n in mission['party'] if n]
    if not party or len(party) != len(set(party)) or any(n not in recipe['allowed_party'] for n in party):
        raise ImportRefusal('CONTEXT', 'The saved party is not allowed by this checkpoint.')
    return recipe
