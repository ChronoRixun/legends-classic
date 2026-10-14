"""Conservative spawn-floor residency for ordinary placed props (issue #81).

The native floor sweep, not a calculated Z, places the object. Static collision
triangles only select candidates; movable supports and unreadable bounds defer
the selection. Proven shallow-overlap models also need the native load sweep.
Newly numbered instances are appended to preserve old ordinals.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import math
import xml.etree.ElementTree as ET
from collections import Counter

import numpy as np

from .buoys import numbers, model_bounds
from .igb_file import IgbFile

MARKER = 'xml1settle'
EMBEDDED_MARKER = 'xml1embeddedfloor'
MIN_GAP = 3.0
# Shallow floor overlap is a different selection from an unsupported raised
# prop. Limit it to the model checked under real hits; expanding this set needs
# a source-hull audit and a surviving-hit check for the additional model.
EMBEDDED_MODELS = frozenset({'haarp/crate_tarp'})
MIN_PENETRATION = 0.25
MAX_NEW_RESIDENTS = 64
MAX_RESIDENTS = 128


def collision_triangles(data):
    """The source hull's triangle records: three XYZ + auxiliary-word vertices."""
    g = IgbFile(data)
    hulls = g.objects_of('igCollideHull')
    if len(hulls) != 1 or not hulls[0].decoded:
        raise ValueError('no unique readable collision hull')
    hull = hulls[0]
    count = hull.get(7)
    vertices = g.obj(hull.get(5))
    if not isinstance(count, int) or not 0 < count <= 262144 or vertices is None:
        raise ValueError('invalid collision triangle count/list')
    if not vertices.decoded or not g.isa(vertices, 'igFloatList') or vertices.get(2) != count * 12:
        raise ValueError('invalid collision triangle list')
    block = g.block(vertices.get(4))
    if block is None or block[1] != count * 48:
        raise ValueError('invalid collision triangle block')
    triangles = np.frombuffer(g.data, dtype='<f4', count=count * 12, offset=block[0])
    triangles = triangles.reshape(count, 3, 4)[:, :, :3].astype(np.float64)
    if not np.isfinite(triangles).all() or (np.abs(triangles) > 1e7).any():
        raise ValueError('invalid collision coordinates')
    return triangles


class Floor:
    def __init__(self, triangles):
        t = np.asarray(triangles, dtype=np.float64)
        if t.ndim != 3 or t.shape[1:] != (3, 3) or not np.isfinite(t).all():
            raise ValueError('invalid triangles')
        self.triangles = t
        self.a = t[:, 0]
        self.b = t[:, 1] - self.a
        self.c = t[:, 2] - self.a
        self.d = self.b[:, 0] * self.c[:, 1] - self.b[:, 1] * self.c[:, 0]

    def below(self, x, y, bottom):
        a, b, c, d = self.a, self.b, self.c, self.d
        with np.errstate(all='ignore'):
            u = ((x-a[:, 0])*c[:, 1] - (y-a[:, 1])*c[:, 0]) / d
            v = (b[:, 0]*(y-a[:, 1]) - b[:, 1]*(x-a[:, 0])) / d
            z = a[:, 2] + u*b[:, 2] + v*c[:, 2]
            hit = (np.abs(d) > 1e-8) & (u >= -1e-6) & (v >= -1e-6) & (u+v <= 1+1e-6) & (z <= bottom+2)
        return float(np.max(z[hit])) if hit.any() else None

    def under_footprint(self, box):
        """Highest static support in the conservative XY box, not just its centre.

        Corners handle triangles covering the box; clipped triangle edges handle
        narrow curbs/platforms inside it, including ones none of the corners hit.
        """
        heights = [self.below(x, y, box[2]) for x, y in itertools.product(
            (box[0], box[3]), (box[1], box[4]))]
        heights.append(self.below((box[0]+box[3])/2, (box[1]+box[4])/2, box[2]))
        for i in range(3):
            start = self.triangles[:, i]
            delta = self.triangles[:, (i+1) % 3] - start
            low = np.zeros(len(start))
            high = np.ones(len(start))
            # A vertical wall edge inside the XY box is a side obstruction,
            # not a floor beneath the prop.
            ok = np.abs(self.d) > 1e-8
            with np.errstate(all='ignore'):
                for axis in (0, 1):
                    moving = np.abs(delta[:, axis]) > 1e-12
                    a = (box[axis]-start[:, axis]) / delta[:, axis]
                    b = (box[axis+3]-start[:, axis]) / delta[:, axis]
                    low = np.where(moving, np.maximum(low, np.minimum(a, b)), low)
                    high = np.where(moving, np.minimum(high, np.maximum(a, b)), high)
                    ok &= moving | ((start[:, axis] >= box[axis]) & (start[:, axis] <= box[axis+3]))
                limit = (box[2]+2-start[:, 2]) / delta[:, 2]
                rising = delta[:, 2] > 1e-12
                falling = delta[:, 2] < -1e-12
                high = np.where(rising, np.minimum(high, limit), high)
                low = np.where(falling, np.maximum(low, limit), low)
                ok &= rising | falling | (start[:, 2] <= box[2]+2)
                ok &= low <= high
                z = np.maximum(start[:, 2]+low*delta[:, 2], start[:, 2]+high*delta[:, 2])
            if ok.any():
                heights.append(float(np.max(z[ok])))
        return max((h for h in heights if h is not None), default=None)


def _true(attrs, key):
    return attrs.get(key, '').strip().lower() in ('true', '1')


def _box(attrs, read_bounds):
    pos = numbers(attrs.get('pos'), 3)
    angles = numbers(attrs.get('orient', '0 0 0'), 3)
    box = numbers(attrs['extents'], 6) if attrs.get('extents') else read_bounds(attrs.get('model', ''))
    if box is None:
        raise ValueError('unreadable model bounds')
    box = numbers(box, 6)
    if any(box[i] > box[i+3] for i in range(3)):
        raise ValueError('reversed model bounds')
    corners = list(itertools.product(*zip(box[:3], box[3:])))
    cx, cy, cz = map(math.cos, angles)
    sx, sy, sz = map(math.sin, angles)
    pts = []
    for x, y, z in corners:
        y, z = y*cx-z*sx, y*sx+z*cx
        x, z = x*cy+z*sy, -x*sy+z*cy
        x, y = x*cz-y*sz, x*sz+y*cz
        pts.append((pos[0]+x, pos[1]+y, pos[2]+z))
    tilted = abs(angles[0]) > .001 or abs(angles[1]) > .001
    return tuple(min(p[i] for p in pts) for i in range(3)) + tuple(max(p[i] for p in pts) for i in range(3)), tilted


def survey(root, triangles, read_bounds):
    """Per-instance classifications, with no tree mutation or inferred final Z."""
    floor = Floor(triangles)
    definitions = {e.get('name'): e for e in root.iter('entity')}
    placements, unresolved = [], False
    support_bounds = getattr(read_bounds, 'support', read_bounds)
    for gi, group in enumerate(root.findall('entinst')):
        definition = definitions.get(group.get('type'))
        if definition is None:
            continue
        for ii, inst in enumerate(group.findall('inst')):
            attrs = {**definition.attrib, **inst.attrib}
            cls = attrs.get('classname', '').lower()
            if cls not in ('physent', 'gameent', 'doorent', 'moverent') or _true(attrs, 'nocollide') or _true(attrs, 'noclip'):
                continue
            try:
                box, tilted = _box(attrs, support_bounds)
            except (ValueError, OSError, KeyError, TypeError):
                unresolved = True
                box, tilted = None, False
            placements.append((group, inst, definition, attrs, box, tilted, gi, ii))
    rows = []
    for group, inst, definition, attrs, box, tilted, gi, ii in placements:
        if attrs.get('classname', '').lower() != 'physent' or attrs.get(MARKER) == 'true':
            continue
        row = {'name': inst.get('name'), 'type': group.get('type'), 'group': gi, 'instance': ii, 'status': 'fixed'}
        rows.append(row)
        try:
            mass = float(attrs.get('mass', '1'))
            gravity = float(attrs.get('gravitymod', '1'))
            if not math.isfinite(mass) or not math.isfinite(gravity):
                raise ValueError('invalid physics values')
            if _true(attrs, 'nogravity') or mass <= 0 or gravity <= 0:
                continue
            try:
                box, tilted = _box(attrs, read_bounds)
            except (ValueError, OSError, KeyError, TypeError):
                row['status'] = 'unreadable_bounds'
                continue
            if box is None:
                row['status'] = 'unreadable_bounds'
                continue
            if tilted:
                row['status'] = 'tilted'
                continue
            pos = numbers(attrs.get('pos'), 3)
            z = floor.below(pos[0], pos[1], box[2])
            row.update(pos=list(pos), bottom=box[2], static_floor=z)
            if z is None:
                row['status'] = 'no_static_floor'
                continue
            row['gap'] = box[2]-z
            embedded = attrs.get('model', '').lower() in EMBEDDED_MODELS and row['gap'] < -MIN_PENETRATION
            if row['gap'] <= MIN_GAP and not embedded:
                row['status'] = 'near_floor'
                continue
            support = floor.under_footprint(box)
            if support is not None:
                row['center_floor'] = z
                row['static_floor'] = support
                row['gap'] = box[2]-support
                if row['gap'] <= MIN_GAP and not embedded:
                    row['status'] = 'static_footprint_support'
                    continue
            if attrs.get('smartent', '').strip().lower() in ('false', '0'):
                row['status'] = 'already_resident'
                continue
            if attrs.get('startenabled', '').strip().lower() in ('false', '0') or any(k.endswith('script') and v for k, v in attrs.items()):
                row['status'] = 'scripted_or_disabled'
                continue
            # A missing support bound must never silently turn a table-top prop
            # into a floor prop. Native load sweeps cannot hit dormant supports.
            if unresolved:
                row['status'] = 'unreadable_support'
                continue
            supports = [other for other in placements if other[1] is not inst and other[4] is not None
                        and other[4][5] > z+2 and other[4][2] < box[2]-2
                        and all(other[4][i] <= box[i+3] and other[4][i+3] >= box[i] for i in (0, 1))]
            if supports:
                row['status'] = 'possible_prop_support'
                row['supports'] = [p[1].get('name') for p in supports]
                continue
            row['status'] = 'settle'
            if embedded:
                row['reason'] = 'embedded_floor'
        except (ValueError, TypeError, OverflowError):
            row['status'] = 'invalid_placement'
    residents = sum(len(g.findall('inst')) for g in root.findall('entinst')
                    if definitions.get(g.get('type')) is not None
                    and definitions[g.get('type')].get('smartent', '').strip().lower() in ('false', '0'))
    selected = sum(r['status'] == 'settle' for r in rows)
    if selected > MAX_NEW_RESIDENTS or residents+selected > MAX_RESIDENTS:
        for row in rows:
            if row['status'] == 'settle':
                row['status'] = 'residency_budget'
    return rows


def convert(root, rows):
    """Pin only selected placements; keep old numbered entities in their order."""
    selected = {(r['group'], r['instance']): r.get('reason') == 'embedded_floor'
                for r in rows if r['status'] == 'settle'}
    if not selected:
        return 0
    definitions = {e.get('name'): e for e in root.iter('entity')}
    used = set(definitions)
    aliases = {}
    # Check every generated name before changing the tree. A collision must not
    # leave already removed instances stranded in an unattached temporary group.
    for gi, group in enumerate(root.findall('entinst')):
        source = definitions.get(group.get('type'))
        if source is None or source.get(MARKER) == 'true':
            continue
        for embedded in (False, True):
            key = source.get('name'), embedded
            if key in aliases or not any(selected.get((gi, ii)) is embedded
                                         for ii, _ in enumerate(group.findall('inst'))):
                continue
            digest = hashlib.sha256(key[0].encode('utf-8')).hexdigest()[:16]
            alias = ('x1_embedded_' if embedded else 'x1_settle_') + digest
            if alias in used:
                raise ValueError('settle entity alias collision')
            used.add(alias)
            aliases[key] = alias
    new_groups, clones, changed = [], set(), 0
    for gi, group in enumerate(list(root.findall('entinst'))):
        source = definitions.get(group.get('type'))
        if source is None or source.get(MARKER) == 'true':
            continue
        new = {}
        for ii, inst in enumerate(list(group.findall('inst'))):
            if (gi, ii) not in selected:
                continue
            embedded = selected[(gi, ii)]
            key = source.get('name'), embedded
            alias = aliases[key]
            if key not in clones:
                clone = copy.deepcopy(source)
                clone.set('name', alias)
                clone.set('smartent', 'false')
                clone.set(MARKER, 'true')
                if embedded:
                    clone.set(EMBEDDED_MARKER, 'true')
                root.append(clone)
                clones.add(key)
            if embedded not in new:
                new[embedded] = ET.Element(group.tag, {**group.attrib, 'type': alias})
                new_groups.append((embedded, new[embedded]))
            group.remove(inst)
            new[embedded].append(inst)
            changed += 1
        if not list(group):
            root.remove(group)
    # Previously generated settlement groups keep their exact instance order.
    # The new floor-overlap residents follow them, including another group of
    # the same source definition (saved ordinals identify placements, not names).
    for _, group in sorted(new_groups, key=lambda item: item[0]):
        root.append(group)
    return changed


def move_embedded_floor_tail(root):
    """Run after late fall volumes: new overlap residents follow all old ordinals."""
    names = {e.get('name') for e in root.iter('entity') if e.get(EMBEDDED_MARKER) == 'true'}
    for group in list(root.findall('entinst')):
        if group.get('type') in names:
            root.remove(group)
            root.append(group)


def numbered_tail_problems(root, later=()):
    """New residents must follow every pre-existing placement (save ordinals). `later`: entinst types numbered
    after the settled props (x1schema.FALL_KILL_ENABLED_LATE), allowed behind them."""
    marked = {e.get('name') for e in root.iter('entity') if e.get(MARKER) == 'true'}
    embedded = {e.get('name') for e in root.iter('entity') if e.get(EMBEDDED_MARKER) == 'true'}
    out, in_tail = [], False
    for group in root.findall('entinst'):
        if group.get('type') in marked:
            in_tail = True
        elif in_tail and group.get('type') not in later:
            out.append('settled prop precedes an old entinst (saved ordinals shift)')
    in_tail = False
    for group in root.findall('entinst'):
        if group.get('type') in embedded:
            in_tail = True
        elif in_tail:
            out.append('embedded-floor prop precedes an old entinst (saved ordinals shift)')
    return out


def embedded_floor_problems(root, rows):
    """V-TBD: every selected overlap must exist in the built resident tail."""
    expected = Counter()
    for row in rows:
        if row.get('status') == 'settle' and row.get('reason') == 'embedded_floor':
            alias = 'x1_embedded_' + hashlib.sha256(row['type'].encode('utf-8')).hexdigest()[:16]
            expected[(alias, row['name'], tuple(row['pos']))] += 1
    if not expected:
        return []
    definitions = {e.get('name'): e for e in root.iter('entity')}
    actual = Counter()
    for group in root.findall('entinst'):
        definition = definitions.get(group.get('type'))
        if (definition is None or definition.get('smartent', '').lower() not in ('false', '0')
                or definition.get(MARKER) != 'true' or definition.get(EMBEDDED_MARKER) != 'true'):
            continue
        for inst in group:
            try:
                actual[(group.get('type'), inst.get('name'), numbers(inst.get('pos'), 3))] += 1
            except ValueError:
                continue
    return [f'{name}: selected embedded-floor placement is missing from the resident tail ({count})'
            for (_, name, _), count in (expected-actual).items()]


def problems(root, later=()):
    definitions = {e.get('name'): e for e in root.iter('entity')}
    marked = {n for n, e in definitions.items() if e.get(MARKER) == 'true'}
    out = []
    for n in marked:
        e = definitions[n]
        valid = e.get('classname') == 'physent' and e.get('smartent') == 'false'
        valid = valid and not any(_true(e.attrib, k) for k in ('nogravity', 'nocollide', 'noclip'))
        try:
            values = (float(e.get('mass', '1')), float(e.get('gravitymod', '1')))
            valid = valid and all(math.isfinite(v) and v > 0 for v in values)
        except (ValueError, TypeError):
            valid = False
        if not valid:
            out.append(f'{n}: settled prop must be a gravity-enabled resident physent')
    out.extend(numbered_tail_problems(root, later))
    return out


def bounds_reader(read_model):
    cache = {}
    def load(model):
        if not model:
            return None, None
        model = model.replace('\\', '/').lower().removesuffix('.igb')
        rel = model if model.startswith('models/') else 'models/' + model
        if rel not in cache:
            physical, conservative = None, None
            try:
                # Render bounds include foliage and decoration that cannot hold
                # another object. Use the authored physical collision hull.
                data = read_model(rel + '.igb')
                try:
                    vertices = collision_triangles(data).reshape(-1, 3)
                    physical = tuple(np.min(vertices, axis=0)) + tuple(np.max(vertices, axis=0))
                except ValueError:
                    # This may obstruct another object even without a readable
                    # hull. Render bounds are only a conservative support veto,
                    # never grounds for selecting that object for settlement.
                    conservative = model_bounds(data)
            except (ValueError, OSError, TypeError, KeyError):
                pass
            cache[rel] = physical, conservative
        return cache[rel]
    def read_bounds(model):
        return load(model)[0]
    def read_support(model):
        physical, conservative = load(model)
        return physical if physical is not None else conservative
    read_bounds.support = read_support
    return read_bounds
