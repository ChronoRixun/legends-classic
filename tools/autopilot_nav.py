"""Offline navigation grids and ordinary-input feedback rules; no engine writes.

XML1 .nav is parsed by the builder's shared text importer and encoded as NAVB;
empty source files are omitted. Nonempty files retain cellsize, c/p and directed
link/src/dest/code/cost records. XY are cell indices, Z is world height. We use
cell centres (index + 0.5) * cellsize and verify them through live movement.
Neighbor connections are inferred cardinal walk edges with bounded height change;
explicit links retain their transition code instead of silently becoming stairs.
"""
from __future__ import annotations
from collections import defaultdict
import heapq
import itertools
import math


def point(value):
    try:
        values = tuple(map(float, value.split())) if isinstance(value, str) else tuple(map(float, value))
        if len(values) != 3 or not all(math.isfinite(v) and abs(v) < 1e7 for v in values):
            raise ValueError('invalid navigation point')
        return values
    except (TypeError, OverflowError) as exc:
        raise ValueError('invalid navigation point') from exc


def nav_data(root, world=None):
    size = root.get('cellsize')
    if size is None:
        from xml1build.buoys import f32, numbers
        spatial = numbers((world if world is not None else {}).get('mapcellsize', '120 120 120'), 3)
        if any(not 1 <= v <= 10000 for v in spatial):
            raise ValueError('invalid spatial cell size')
        # Match Frame.from_world and the native loader's float32 multiplication.
        size = f32(f32(spatial[0]) * f32(1 / 3))
    else:
        size = float(size)
    if not math.isfinite(size) or not 1 <= size <= 1024:
        raise ValueError('invalid navigation cell size')
    cells = list(dict.fromkeys(point(e.get('p', '')) for e in root.iter('c')))
    if len(cells) > 50000:
        raise ValueError('navigation grid exceeds observation budget')
    links = []
    for e in root.iter('link'):
        src, dst = point(e.get('src', '')), point(e.get('dest', ''))
        cost = float(e.get('cost', '1'))
        if not math.isfinite(cost) or cost < 0:
            raise ValueError('invalid link cost')
        links.append({'src': src, 'dest': dst, 'code': int(e.get('code', '0')), 'cost': cost})
    return {'source': 'xml1_nav_encoded_as_navb', 'cellsize': size, 'cells': cells, 'links': links}


class Routes:
    def __init__(self, data, anchors=()):
        self.data = data or {}
        size = self.data.get('cellsize', 40)
        cells = [tuple(c) for c in self.data.get('cells', [])]
        self.points = [((x + .5) * size, (y + .5) * size, z) for x, y, z in cells]
        self.edges = defaultdict(list)
        self.source = self.data.get('source', 'sparse_map_entities')
        if not cells:
            self.points = [point(a['pos']) for a in anchors]
            # Sparse fallback is explicitly inferred, not asserted collision connectivity.
            for i, a in enumerate(self.points):
                for j, b in enumerate(self.points):
                    if i != j and math.dist(a, b) <= 220 and abs(a[2] - b[2]) <= 40:
                        self.edges[i].append((j, math.dist(a, b), 0))
        xy = defaultdict(list)
        for i, (x, y, z) in enumerate(cells):
            xy[x, y].append(i)
        for i, (x, y, z) in enumerate(cells):
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                for j in xy[x + dx, y + dy]:
                    if abs(z - cells[j][2]) <= 48:
                        self.edges[i].append((j, math.dist(self.points[i], self.points[j]), 0))
        index = {p: i for i, p in enumerate(cells)}
        for link in self.data.get('links', []):
            src, dst = index.get(tuple(link['src'])), index.get(tuple(link['dest']))
            if src is not None and dst is not None:
                self.edges[src].append((dst, max(math.dist(self.points[src], self.points[dst]), link['cost']), link['code']))

        # Attach transports to either NAVB cells or sparse anchors, never to a
        # trigger appended by a preceding transition.
        base_points = range(len(self.points))
        for transition in self.data.get('script_transitions', []):
            if not base_points:
                break
            a, b = point(transition['src']), point(transition['dest'])
            src = min(base_points, key=lambda i: math.dist(a, self.points[i]))
            dst = min(base_points, key=lambda i: math.dist(b, self.points[i]))
            if math.dist(a, self.points[src]) > 200 or math.dist(b, self.points[dst]) > 200:
                continue
            trigger = len(self.points)
            self.points.append(a)
            self.edges[src].append((trigger, max(1., math.dist(a, self.points[src])), 0))
            self.edges[trigger].append((dst, 40., {'kind': 'script', **transition}))

    def nearest(self, pos):
        if not self.points:
            raise ValueError('zone has neither navigation cells nor map anchors')
        return min(range(len(self.points)), key=lambda i: math.dist(pos, self.points[i]))

    def route(self, start, goal):
        begin, end = self.nearest(start), self.nearest(goal)
        if math.dist(start, self.points[begin]) > 300 or math.dist(goal, self.points[end]) > 400:
            raise ValueError('goal or start is too far from observed navigation data')
        distance, previous = {begin: 0.}, {}
        queue = [(0., begin)]
        while queue:
            _, node = heapq.heappop(queue)
            if node == end:
                break
            for next_node, cost, code in self.edges[node]:
                candidate = distance[node] + cost
                if candidate < distance.get(next_node, math.inf):
                    distance[next_node] = candidate
                    previous[next_node] = node, code
                    heapq.heappush(queue, (candidate, next_node))
        if end != begin and end not in previous:
            raise ValueError('navigation components disconnected; no safe route inferred')
        nodes = [{'pos': self.points[end], 'transition': previous.get(end, (None, 0))[1], 'node': end}]
        node = end
        while node != begin:
            node = previous[node][0]
            nodes.append({'pos': self.points[node], 'transition': previous.get(node, (None, 0))[1], 'node': node})
        nodes.reverse()
        # Preserve corners and every explicit link. Long collinear runs are safe to condense.
        out = []
        for item in nodes:
            if len(out) >= 2 and not item['transition'] and not out[-1]['transition']:
                a, b, c = out[-2]['pos'], out[-1]['pos'], item['pos']
                ab, bc = (b[0]-a[0], b[1]-a[1]), (c[0]-b[0], c[1]-b[1])
                if abs(ab[0]*bc[1]-ab[1]*bc[0]) < .01 and ab[0]*bc[0]+ab[1]*bc[1] > 0 and abs(c[2]-a[2]) <= 48 and math.dist(a,c) <= 160:
                    out.pop()
            out.append(item)
        out.append({'pos': tuple(goal), 'transition': 0, 'node': 'goal'})
        return out


def movement(mapping, origin, target):
    dx, dy = target[0]-origin[0], target[1]-origin[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return None
    candidates = []
    for n in (1, 2):
        for keys in itertools.combinations(mapping, n):
            if set(keys) in ({'W', 'S'}, {'A', 'D'}):
                continue
            x = sum(mapping[k][0] for k in keys);y = sum(mapping[k][1] for k in keys)
            speed = math.hypot(x, y)
            if speed > 10:
                score = (dx*x+dy*y)/(length*speed)
                candidates.append((score, keys, speed))
    if not candidates:
        raise ValueError('no measured movement vectors')
    score, keys, speed = max(candidates)
    if score < .5:
        raise ValueError('calibration does not span the required direction')
    return '+'.join(keys), max(80, min(350, round(1000 * length / speed * .65)))


def calibrated(samples):
    mapping = {k: ((b[0]-a[0])/seconds, (b[1]-a[1])/seconds)
               for k, (a, b, seconds) in samples.items() if seconds > 0 and math.dist(a[:2], b[:2]) >= 3}
    spans = [abs(a[0]*b[1]-a[1]*b[0])/(math.hypot(*a)*math.hypot(*b))
             for a, b in itertools.combinations(mapping.values(), 2)]
    if not spans or max(spans) < .4:
        raise ValueError('movement calibration blocked or collinear')
    return mapping


def intersects(start, end, bounds, pad=24):
    low, high = 0., 1.
    for axis in range(3):
        a, b = bounds[axis]-pad, bounds[axis+3]+pad
        delta = end[axis]-start[axis]
        if abs(delta) < .001:
            if not a <= start[axis] <= b:
                return False
        else:
            u, v = sorted(((a-start[axis])/delta, (b-start[axis])/delta))
            low, high = max(low, u), min(high, v)
            if low > high:
                return False
    return True


def assist_refusal(state, start, target, barriers, already_used):
    if state.get('script_controls_locked') is not False:
        return 'script control lock is active or unknown'
    if state.get('loading') is not False or state.get('popup') or state.get('menu_open') or state.get('conversation', {}).get('open'):
        return 'loading or modal script/UI state'
    if isinstance(target.get('transition'), dict):
        return 'script-owned transition boundary'
    if target['node'] == 'goal':
        return 'final goal activation is a script/interaction boundary'
    if target['node'] in already_used:
        return 'assist already attempted at this route point'
    if math.dist(start, target['pos']) > 240:
        return 'assist would skip more than a local navigation step'
    if any(intersects(start, target['pos'], b['bounds']) for b in barriers):
        return 'door, elevator, bridge or activation volume intersects the step'
    return None
