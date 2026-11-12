"""Resident placements whose model lies away from their origin (Toad's cell forcefield, issue: brig walk-through).

XMen2.exe keeps a physical entity "smart" unless its definition says smartent="false" (0x498a05): at zone load the
entity is released (0x486212-0x486242) and its record is re-created only when its POSITION enters a box around the
camera (CSmartEntMgr vtable 0x68e440, update 0x4b7100: the camera's +-250 box joined with a +-750 box 350 units
along its view). XML1 keeps an absent smartent false, so every placed prop stays alive. Some XML1 props are modelled
in world coordinates and placed at or near the zone origin: subbasement2's brig forcefield is at 0 0 0 while its
geometry and collision hull lie 2,400 units away at the cell. In XMen2.exe the entity is never re-created while the
heroes stand at the cell, so the forcefield neither collides nor exists there. Over XML2's own 15,233 smart
placements the origin is never more than 64 units outside the model's bounds (horizontally); the props beyond that
it ships carry smartent="false". This pass gives the same residency to XML1 placements beyond that envelope.

Ordinals: XMen2.exe numbers non-smart placements in entinst order and saved zone records find entities by that
number, so a selected instance moves to a generated resident copy of its definition whose entinst group is appended
after every existing group (after the settle, fall-volume, hazard, destruction and progression tails). Unselected
instances, names, positions, models and every older ordinal stay as they were.
"""
from __future__ import annotations

import copy
import hashlib
import math
import xml.etree.ElementTree as ET

MARKER = 'xml1offsetresident'
PREFIX = 'x1_offset_'
# XML2's largest horizontal origin-to-bounds distance over its smart placements (Act1 .. Act5, 15,233 placements).
XML2_SMART_ENVELOPE = 64.0
# Placed classes XMen2.exe keeps smart by default (lcsave.binds.SMART_DEFAULT_TRUE) less actors and tiles, which the
# port never places this way (every hit of the census is a physent; see SPEC "Props modelled away from their origin").
CLASSES = frozenset({'physent', 'affectableharment', 'doorent', 'guidedprojectileent', 'inventoryent', 'moverent',
                     'powertriggerent', 'projectileent', 'tornadoent', 'projectiletornadoent', 'rememberent',
                     'sentryent', 'lightent'})
MAX_NEW_RESIDENTS = 64
MAX_RESIDENTS = 128


def names(root):
    return {e.get('name') for e in root.iter('entity') if e.get(MARKER) == 'true'}


def _numbers(value, count):
    out = tuple(float(v) for v in str(value).split())
    if len(out) != count or not all(math.isfinite(v) and abs(v) <= 1e7 for v in out):
        raise ValueError('invalid numbers')
    return out


def model_box(data):
    """The model's own bounds: render scene bounds joined with its collision hull (either may be absent)."""
    from .buoys import model_bounds
    from .settle import collision_triangles
    boxes = []
    try:
        boxes.append(tuple(model_bounds(data)))
    except (ValueError, TypeError, KeyError):
        pass
    try:
        v = collision_triangles(data).reshape(-1, 3)
        boxes.append(tuple(float(x) for x in v.min(axis=0)) + tuple(float(x) for x in v.max(axis=0)))
    except (ValueError, TypeError, KeyError):
        pass
    if not boxes:
        raise ValueError('no readable model bounds')
    return tuple(min(b[i] for b in boxes) for i in range(3)) + tuple(max(b[i] for b in boxes) for i in range(3, 6))


def placed_box(attrs, box):
    """`box` (model space) moved by the placement's scale, orient and pos: world-space AABB."""
    from .settle import _box
    scale = attrs.get('scale', '').strip()
    if scale:
        s = _numbers(scale, 1)[0]
        if not 0 < s <= 1000:
            raise ValueError('invalid scale')
        box = tuple(v * s for v in box)
    world, _ = _box({'pos': attrs.get('pos', '0 0 0'), 'orient': attrs.get('orient', '0 0 0'),
                     'extents': ' '.join(repr(float(v)) for v in box)}, None)
    return world


def origin_gap(attrs, box):
    """Horizontal distance from the placement's origin to its own world-space bounds (0 inside)."""
    pos = _numbers(attrs.get('pos', '0 0 0'), 3)
    w = placed_box(attrs, box)
    dx = max(w[0] - pos[0], 0.0, pos[0] - w[3])
    dy = max(w[1] - pos[1], 0.0, pos[1] - w[4])
    return math.hypot(dx, dy), w


def survey(root, read_box):
    """Rows for the placed smart entities whose origin is beyond XML2's envelope. `read_box(model)` -> model box."""
    definitions = {e.get('name'): e for e in root.iter('entity')}
    rows = []
    for gi, group in enumerate(root.findall('entinst')):
        definition = definitions.get(group.get('type'))
        if definition is None or definition.get(MARKER) == 'true':
            continue
        if (definition.get('classname') or '').strip().lower() not in CLASSES:
            continue
        if definition.get('smartent') is not None or not (definition.get('model') or '').strip():
            continue
        for ii, inst in enumerate(group.findall('inst')):
            attrs = {**definition.attrib, **inst.attrib}
            row = {'name': inst.get('name'), 'type': group.get('type'), 'model': definition.get('model'),
                   'group': gi, 'instance': ii}
            try:
                gap, world = origin_gap(attrs, read_box(definition.get('model')))
            except (ValueError, OSError, KeyError, TypeError, OverflowError):
                row['status'] = 'unreadable_bounds'
                rows.append(row)
                continue
            row['gap'] = round(gap, 1)
            row['bounds'] = [round(v, 1) for v in world]
            if gap <= XML2_SMART_ENVELOPE:
                continue
            row['status'] = 'resident'
            rows.append(row)
    selected = sum(r.get('status') == 'resident' for r in rows)
    residents = sum(len(g.findall('inst')) for g in root.findall('entinst')
                    if definitions.get(g.get('type')) is not None
                    and (definitions[g.get('type')].get('smartent') or '').strip().lower() in ('false', '0'))
    if selected > MAX_NEW_RESIDENTS or residents + selected > MAX_RESIDENTS:
        for row in rows:
            if row.get('status') == 'resident':
                row['status'] = 'residency_budget'
    return rows


def alias(type_name):
    return PREFIX + hashlib.sha256(type_name.encode('utf-8')).hexdigest()[:16]


def dedupe_identical_mastermold2(root, zone):
    """Reviewed map-only repair: no placement, ordinal or definition value edits.

    The historical duplicate prevents native prefix-digest verification. Emit
    one copy only when both complete definitions are canonically identical.
    Other zones/names are untouched; conflicting values refuse conversion.
    """
    if zone != 'mastermold/mastermold2':
        return 0
    entries = [e for e in root.findall('entity') if e.get('name') == 'mm_damagestraight_mm']
    if len(entries) < 2:
        return 0
    def canonical(e):
        return [e.tag, sorted(e.attrib.items()), [canonical(c) for c in e]]
    expected = canonical(entries[0])
    if any(canonical(e) != expected for e in entries[1:]):
        raise ValueError('mastermold2: conflicting mm_damagestraight_mm definitions')
    for e in entries[1:]:
        root.remove(e)
    return len(entries) - 1


def convert(root, rows):
    """Move the selected instances into appended resident copies of their definitions. Returns the count."""
    selected = {(r['group'], r['instance']) for r in rows if r.get('status') == 'resident'}
    if not selected:
        return 0
    definitions = {e.get('name'): e for e in root.iter('entity')}
    groups = list(root.findall('entinst'))
    new_groups, aliases, moved = {}, {}, 0
    for gi, group in enumerate(groups):
        picks = [inst for ii, inst in enumerate(group.findall('inst')) if (gi, ii) in selected]
        if not picks:
            continue
        source = definitions[group.get('type')]
        name = aliases.get(source.get('name'))
        if name is None:
            name = alias(source.get('name'))
            if name in definitions:
                raise ValueError('offset resident alias collision: ' + name)
            clone = copy.deepcopy(source)
            clone.set('name', name)
            clone.set('smartent', 'false')
            clone.set(MARKER, 'true')
            root.append(clone)
            definitions[name] = clone
            aliases[source.get('name')] = name
            new_groups[name] = ET.Element(group.tag, {**group.attrib, 'type': name})
        for inst in picks:
            group.remove(inst)
            new_groups[name].append(inst)
            moved += 1
        if not list(group):
            root.remove(group)
    for group in new_groups.values():
        root.append(group)
    return moved


def problems(root):
    """Generated definitions are resident copies; their entinsts follow every other entinst (save ordinals)."""
    marked = names(root)
    out = []
    definitions = {e.get('name'): e for e in root.iter('entity')}
    for n in sorted(marked):
        e = definitions[n]
        if (e.get('smartent') != 'false' or (e.get('classname') or '').strip().lower() not in CLASSES
                or not n.startswith(PREFIX)):
            out.append(f'{n}: offset resident must be a smart-by-default class copy with smartent=false')
    in_tail = False
    for group in root.findall('entinst'):
        if group.get('type') in marked:
            in_tail = True
        elif in_tail:
            out.append('offset resident precedes an old entinst (saved ordinals shift)')
    added = sum(len(g.findall('inst')) for g in root.findall('entinst') if g.get('type') in marked)
    if added > MAX_NEW_RESIDENTS:
        out.append(f'offset residency exceeds {MAX_NEW_RESIDENTS} new instances')
    return out
