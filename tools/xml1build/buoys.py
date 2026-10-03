"""Generate XML2 long-range BOYB networks from XML1 walk grids (SPEC 42).

XML1 has no .boy files or buoy section in .nav: this is generation, not conversion.
Engine contract (unpacked retail XMen2.exe): spatial bounds 0x463f30, NAV frame
0x490e10, cell loader 0x494470, BOY loader 0x494a30, world decode 0x490980.
The spatial grid defaults to 120 units. NAV origin is its snapped XY minimum + cellsize/2
and the effective (explicit or scene-root) minimum Z + 6. NAV c/p heights load as trunc((z+12-origin.z)*0.083333f).
BOY b/n stores three unsigned bytes followed by up to eight one-based neighbors;
zero is reserved, at most 288 real nodes. Far-path attachment 0x495790 uses a
strict 640-unit radius. Generated edges never encode special jump/drop actions.
All functions are offline; derived data belongs only in builder output/metadata.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import heapq
import itertools
import math
import struct
import xml.etree.ElementTree as ET

NODE_CAP = 288
NEIGHBOR_CAP = 8
EDGE_CAP = 349                      # 0x4936d0: 350 link slots; 0x493810 reserves slot zero
ATTACH_RADIUS = 640
COVER_DISTANCE = 280                 # walk distance, stronger than Euclidean attachment
HEIGHT_RECIPROCAL = struct.unpack('<f', struct.pack('<I', 0x3daaaa7e))[0]  # 0x689b30, deliberately not 1/12
STEP_HEIGHT = 48                     # 0x495d00: ordinary neighbor height delta is strictly between -5 and +5 quanta
GRID_BLOCK_CAP = 200                 # 0x493210: 9x9-cell blocks; a missing 201st block is not loaded
MAX_CELLS = 131072                   # native 252*252 grid, at most two height layers


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def numbers(value, count):
    try:
        out = tuple(float(v) for v in value.split()) if isinstance(value, str) else tuple(map(float, value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('unreadable navigation coordinates') from exc
    if len(out) != count or not all(math.isfinite(v) and abs(v) <= 1e7 for v in out):
        raise ValueError('invalid navigation coordinates')
    return out


@dataclass(frozen=True)
class Frame:
    size: float
    origin: tuple
    bias: tuple
    dimensions: tuple

    @classmethod
    def from_world(cls, world, size, map_bounds=None):
        spatial=numbers(world.get('mapcellsize','120 120 120'),3)
        if any(not 1<=v<=10000 for v in spatial):
            raise ValueError('invalid spatial cell size')
        spatial=tuple(map(f32,spatial))
        # 0x494470: absent cellSize uses spatial X times float 0x3eaaaaab (0x682fe4).
        size = f32(spatial[0]*f32(1/3)) if size is None else f32(float(size))
        if not math.isfinite(size) or not 1 <= size <= 1024:
            raise ValueError('invalid cellsize')
        # Zone loader 0x4857ca..0x485878 starts with the map geometry bounds.
        # Explicit XY replaces them; an explicit Z of zero means keep geometry Z.
        values=[]
        for k,offset in (('extent_min',0),('extent_max',3)):
            declared=numbers(world.get(k),3) if world.get(k) else None
            if map_bounds is None:
                if declared is None or declared[2]==0:
                    raise ValueError('geometry bounds required for missing/zero extents')
                v=declared
            else:
                v=list(numbers(map_bounds,6)[offset:offset+3])
                if declared:
                    v[:2]=declared[:2]
                    if declared[2]!=0:
                        v[2]=declared[2]
            values.append(tuple(map(f32,v)))
        lo,hi=values
        if any(lo[i]>=hi[i] for i in range(2)) or lo[2]>hi[2]:
            raise ValueError('reversed or degenerate map bounds')
        inv=tuple(f32(1/v) for v in spatial)
        low=[math.floor(f32(lo[i]*inv[i]))*spatial[i] for i in range(3)]
        high=[math.ceil(f32(f32(hi[i]+spatial[i]/2)*inv[i]))*spatial[i] for i in range(3)]
        if any(int(f32((high[i]-low[i])/spatial[i]))>84 for i in range(2)):
            # 0x464147..0x464219: inward rounding when the expanded grid is too big.
            low=[int(f32(math.ceil(lo[i])*inv[i]))*spatial[i] for i in range(3)]
            high=[int(f32((math.floor(hi[i])+spatial[i]/2)*inv[i]))*spatial[i] for i in range(3)]
            if any(int(f32((high[i]-low[i])/spatial[i]))>84 for i in range(2)):
                # 0x464261: retain the unsnapped geometry bounds as the last fallback.
                low,high=list(lo),list(hi)
        origin = tuple(f32(low[i] + size/2) for i in range(2)) + (f32(lo[2] + 6),)
        bias = tuple(int(f32(low[i] * f32(1/size))) for i in range(2))
        dimensions = tuple(min(252, int(f32((high[i] - low[i]) * f32(1/size)))) for i in range(2))
        return cls(size, origin, bias, dimensions)

    def cell(self, p):
        x, y, z = numbers(p, 3)
        if any(v != int(v) for v in (x, y, z)):
            raise ValueError('NAV coordinates must be integers')
        q = (int(x) - self.bias[0], int(y) - self.bias[1], int(f32(f32(f32(z + 12) - self.origin[2]) * HEIGHT_RECIPROCAL)))
        if not (0 <= q[0] < self.dimensions[0] and 0 <= q[1] < self.dimensions[1] and 0 <= q[2] < 255):
            raise ValueError('NAV cell outside native coordinate range')
        return q

    def world(self, q):
        q = numbers(q, 3)
        if any(v != int(v) or not 0 <= v < 255 for v in q):
            raise ValueError('invalid packed buoy coordinate')
        return tuple(f32(self.origin[i] + f32(q[i] * (self.size if i < 2 else 12))) for i in range(3))

    def pack(self, world):
        q = tuple(round((v-self.origin[i])/(self.size if i < 2 else 12)) for i,v in enumerate(numbers(world,3)))
        if any(not 0 <= v < 255 for v in q):
            raise ValueError('world point outside packed coordinate range')
        return q


def read_boy(root):
    if root.tag.lower() != 'buoy':
        raise ValueError('BOY root is not buoy')
    nodes, edges = [], []
    for e in root:
        if e.tag.lower() != 'b':
            raise ValueError('unknown BOY record')
        try:
            row = tuple(map(int, e.get('n', '').split()))
        except ValueError as exc:
            raise ValueError('noninteger BOY record') from exc
        if not 3 <= len(row) <= 3+NEIGHBOR_CAP or any(not 0 <= v < 255 for v in row[:3]):
            raise ValueError('invalid BOY coordinate or degree')
        neighbors = row[3:]
        if -1 in neighbors:
            end = neighbors.index(-1)
            if any(n != -1 for n in neighbors[end:]):
                raise ValueError('BOY data after neighbor terminator')
            neighbors = neighbors[:end]
        nodes.append(row[:3]);edges.append(neighbors)
    if len(nodes) > NODE_CAP:
        raise ValueError('BOY node budget exceeded')
    if sum(map(len,edges))>EDGE_CAP:
        raise ValueError('BOY directed edge budget exceeded')
    for i, neighbors in enumerate(edges, 1):
        if len(set(neighbors)) != len(neighbors) or any(not 1 <= n <= len(nodes) or n == i for n in neighbors):
            raise ValueError('invalid BOY neighbor index')
    return nodes, edges


def model_bounds(data):
    """Conservative transformed scene-graph AABox union; unreadable models fail closed."""
    from .igb_file import IgbFile
    g = IgbFile(data)
    scenes = g.objects_of('igSceneInfo')
    if len(scenes) != 1:
        raise ValueError('gate model has no unique scene')
    identity = tuple(1. if i % 5 == 0 else 0. for i in range(16))
    points = []

    def transform(p, m):
        return tuple(sum(p[j]*m[j*4+i] for j in range(3))+m[12+i] for i in range(3))

    def visit(ref, matrix, ancestors):
        if ref in ancestors or len(ancestors) > 128:
            raise ValueError('gate model scene cycle/depth')
        o = g.obj(ref)
        if o is None or not o.decoded or not g.isa(o, 'igNode'):
            raise ValueError('unreadable gate model node')
        box = g.obj(o.get(3))
        if box is not None:
            if not box.decoded or not g.isa(box, 'igAABox'):
                raise ValueError('unsupported gate model bound')
            lo, hi = numbers(box.get(2),3), numbers(box.get(3),3)
            points.extend(transform(c, matrix) for c in itertools.product(*zip(lo,hi)))
        if g.isa(o, 'igTransform'):
            local = numbers(o.get(8),16)
            matrix = tuple(sum(local[r*4+k]*matrix[k*4+c] for k in range(4)) for r in range(4) for c in range(4))
        if g.isa(o, 'igGroup'):
            children = g.list_items(o.get(7))
            if children is None and o.get(7) not in (None,-1):
                raise ValueError('unreadable gate model children')
            for child in children or ():
                visit(child, matrix, ancestors | {ref})
    visit(scenes[0].get(5),identity,set())
    if not points:
        raise ValueError('gate model has no readable bounds')
    return tuple(min(p[i] for p in points) for i in range(3))+tuple(max(p[i] for p in points) for i in range(3))



def map_bounds(data):
    """The scene root's authored aggregate box, as the native map bound accessor.

    Descendant bounds may already be expressed in their parent's frame. Re-unioning
    and transforming them can double-transform decoration and inflate the map.
    """
    from .igb_file import IgbFile
    g=IgbFile(data)
    scenes=g.objects_of('igSceneInfo')
    if len(scenes)!=1:
        raise ValueError('map has no unique scene')
    node=g.obj(scenes[0].get(5))
    box=g.obj(node.get(3)) if node is not None and node.decoded else None
    if box is None or not box.decoded or not g.isa(box,'igAABox'):
        raise ValueError('map scene root has no readable aggregate bounds')
    return numbers(box.get(2),3)+numbers(box.get(3),3)

def barriers(zone, read_model):
    """Closed/movable geometry stays excluded even when later opened by a script.

    This intentionally sacrifices long-range connectivity at dynamic gates. No
    activation, teleport or special NAV link becomes a static buoy edge.
    """
    defs = {e.get('name','').lower():dict(e.attrib) for e in zone.iter('entity')}
    boxes, unresolved = [], []
    for group in zone.iter('entinst'):
        base = defs.get(group.get('type','').lower(), {})
        for inst in group.findall('inst'):
            attrs = {**base, **inst.attrib}
            kind = attrs.get('classname','').lower()
            label = ' '.join(attrs.get(k,'') for k in ('name','model','classname')).lower()
            gate = ('door' in kind or 'mover' in kind or 'elevator' in kind or
                    any(k in label for k in ('bridge','gate','lift')) or
                    (kind in ('physent','gameent') and attrs.get('startenabled','').lower() == 'false'))
            if not gate:
                continue
            name = attrs.get('name','unnamed')
            try:
                pos = numbers(attrs.get('pos'),3)
                orient = numbers(attrs.get('orient','0 0 0'),3)
                if attrs.get('extents'):
                    bounds = numbers(attrs['extents'],6)
                elif attrs.get('model') and read_model:
                    model = attrs['model'].replace('\\','/').lower().removesuffix('.igb')
                    if not model.startswith('models/'):
                        model = 'models/'+model
                    bounds = model_bounds(read_model(model+'.igb'))
                else:
                    raise ValueError('gate lacks bounds/model')
                if any(bounds[i] > bounds[i+3] for i in range(3)):
                    raise ValueError('reversed gate bounds')
                corners=list(itertools.product(*zip(bounds[:3],bounds[3:])))
                if abs(orient[0]) > .001 or abs(orient[1]) > .001:
                    # A sphere around all corners contains every possible Euler
                    # rotation; conservative without assuming engine axis order.
                    radius=max(math.sqrt(sum(v*v for v in corner)) for corner in corners)
                    points=[tuple(v-radius for v in pos),tuple(v+radius for v in pos)]
                else:
                    c,s = math.cos(orient[2]),math.sin(orient[2])
                    points=[(pos[0]+x*c-y*s,pos[1]+x*s+y*c,pos[2]+z) for x,y,z in corners]
                # Grid points are feet positions: include body height below an
                # obstacle, so a hanging door is not mistaken for a walk-under gap.
                boxes.append(tuple(min(p[i] for p in points)-(128 if i==2 else 32) for i in range(3))+
                             tuple(max(p[i] for p in points)+32 for i in range(3)))
            except (ValueError,KeyError,OSError,TypeError) as exc:
                unresolved.append(name+': '+str(exc))
    return boxes, unresolved


def inside(p, box):
    return all(box[i] <= p[i] <= box[i+3] for i in range(3))


def intersects(a,b,box):
    low,high = 0.,1.
    for i in range(3):
        delta=b[i]-a[i]
        if abs(delta)<1e-8:
            if not box[i] <= a[i] <= box[i+3]:
                return False
        else:
            x,y=sorted(((box[i]-a[i])/delta,(box[i+3]-a[i])/delta))
            low,high=max(low,x),min(high,y)
            if low>high:
                return False
    return True


def walk_graph(nav,frame,boxes):
    raw = list(nav.iter('c'))
    if len(raw)>MAX_CELLS:
        raise ValueError('NAV input exceeds cell budget')
    cells, rejected = set(), 0
    slots = defaultdict(list)
    blocks = set()
    restricted_xy = set()
    block_budget_hit = False
    for e in raw:
        try:
            q = frame.cell(e.get('p'))
            block=(q[0]//9,q[1]//9)
            if block not in blocks and len(blocks)==GRID_BLOCK_CAP:
                rejected+=1;block_budget_hit=True;continue
            blocks.add(block)
            # Native c/t is a cell restriction byte. The converted corpus has none;
            # do not invent universal edges through an unmodeled nonzero restriction.
            try:
                if int(e.get('t','0'))!=0:
                    restricted_xy.add(q[:2])
            except ValueError:
                restricted_xy.add(q[:2])
            # 0x494470 consumes the first two records at an XY location, then
            # ignores further layers. Preserve that file-order selection, including
            # duplicate records; never emit a buoy on a floor the engine did not load.
            if len(slots[q[:2]]) < 2:
                slots[q[:2]].append(q)
                cells.add(q)
            elif q not in slots[q[:2]]:
                rejected += 1
        except ValueError:
            rejected += 1
    by_xy = defaultdict(list)
    for q in sorted(cells):
        by_xy[q[:2]].append(q)
    restricted = set()
    for link in nav.iter('link'):
        try:
            a,b=frame.cell(link.get('src')),frame.cell(link.get('dest',link.get('dst')))
            restricted.add((a,b));restricted.add((b,a))
        except ValueError:
            pass
    blocked = {q for q in cells if any(inside(frame.world(q),box) for box in boxes)}
    restricted_cells={q for q in cells if q[:2] in restricted_xy}
    points = sorted(cells-blocked-restricted_cells)
    world = {p:frame.world(p) for p in points}
    graph = {p:[] for p in points}
    def nearest_layer(xy,height):
        layers=by_xy.get(xy,())
        if not layers:
            return None
        # 0x490950: midpoint selection, ties go to the upper native layer.
        if len(layers)==2 and height>=layers[0][2]+(layers[1][2]-layers[0][2])//2:
            return layers[1]
        return layers[0]
    for p in points:
        for dx,dy in ((-1,0),(0,-1),(0,1),(1,0)):
            q=nearest_layer((p[0]+dx,p[1]+dy),p[2])
            if q not in graph or abs(p[2]-q[2])*12>STEP_HEIGHT or (p,q) in restricted:
                continue
            # Native nearest-layer steps can be one-way. Preserve that direction;
            # imposing reciprocity invents isolated lower-floor waypoints.
            if any(intersects(world[p],world[q],box) for box in boxes):
                continue
            graph[p].append((q,math.dist(world[p],world[q])))
    return graph, {'nav_cells':len(cells),'rejected_cells':rejected,'gate_cells':len(blocked),
                   'restricted_links':len(list(nav.iter('link'))),'restricted_cells':len(restricted_cells),
                   'nav_block_budget_hit':block_budget_hit,'nav_blocks':len(blocks)}



def weak_graph(graph):
    both={p:{} for p in graph}
    for p in graph:
        for q,cost in graph[p]:
            both[p][q]=min(cost,both[p].get(q,math.inf))
            both[q][p]=min(cost,both[q].get(p,math.inf))
    return {p:sorted(edges.items()) for p,edges in both.items()}


def components(graph):
    neighbors=weak_graph(graph)
    unseen=set(graph);out=[]
    while unseen:
        start=min(unseen);unseen.remove(start);group=[start];queue=deque([start])
        while queue:
            for q,_ in neighbors[queue.popleft()]:
                if q in unseen:
                    unseen.remove(q);queue.append(q);group.append(q)
        out.append(sorted(group))
    return out


def strong_components(graph):
    reverse={p:[] for p in graph}
    for p in graph:
        for q,cost in graph[p]:reverse[q].append((p,cost))
    seen=set();order=[]
    for root in sorted(graph):
        stack=[(root,False)]
        while stack:
            p,done=stack.pop()
            if done:order.append(p)
            elif p not in seen:
                seen.add(p);stack.append((p,True))
                stack.extend((q,False) for q,_ in reversed(graph[p]))
    seen=set();groups=[]
    for root in reversed(order):
        if root in seen:continue
        group=[];stack=[root];seen.add(root)
        while stack:
            p=stack.pop();group.append(p)
            for q,_ in reverse[p]:
                if q not in seen:seen.add(q);stack.append(q)
        groups.append(sorted(group))
    return sorted(groups,key=lambda g:g[0]),reverse


def sparse_arcs(graph,report):
    """Preserve directed reachability with bounded out/in trees before extra arcs."""
    groups,reverse=strong_components(graph)
    group_of={p:i for i,group in enumerate(groups) for p in group}
    adjacent=[set() for _ in graph];edge_count=0;refused=set()
    def add(a,b):
        nonlocal edge_count
        if b in adjacent[a]:return True
        if len(adjacent[a])>=NEIGHBOR_CAP:
            refused.add(('neighbor',a,b));return False
        if edge_count>=EDGE_CAP:
            refused.add(('edge',a,b));return False
        adjacent[a].add(b);edge_count+=1;return True
    for group in groups:
        members=set(group);root=group[0]
        for backwards in (False,True):
            reached={root};queue=[]
            def offer(p):
                for q,cost in (reverse if backwards else graph)[p]:
                    if q in members and q not in reached:
                        heapq.heappush(queue,(cost,q,p) if backwards else (cost,p,q))
            offer(root)
            while queue:
                _,a,b=heapq.heappop(queue);old,new=(b,a) if backwards else (a,b)
                if old not in reached or new in reached or not add(a,b):continue
                reached.add(new);offer(new)
    ports=defaultdict(list)
    arcs=sorted((cost,a,b) for a in graph for b,cost in graph[a])
    for cost,a,b in arcs:
        if group_of[a]!=group_of[b]:ports[group_of[a],group_of[b]].append((cost,a,b))
    for pair in sorted(ports):
        for _,a,b in ports[pair]:
            if add(a,b):break
    for _,a,b in arcs:add(a,b)
    chosen={a:[(b,1.) for b in sorted(adjacent[a])] for a in graph}
    def reachable(g,start):
        seen={start};queue=[start]
        while queue:
            for q,_ in g[queue.pop()]:
                if q not in seen:seen.add(q);queue.append(q)
        return seen
    report['directed_connectivity_gaps']=sum(len(reachable(graph,a)-reachable(chosen,a)) for a in graph)
    report['neighbor_budget_hits']=sum(kind=='neighbor' for kind,_,_ in refused)
    report['edge_budget_hits']=sum(kind=='edge' for kind,_,_ in refused)
    report['edges']=edge_count
    report['graph_components']=len(components(chosen))
    return adjacent


def generate(nav,zone,read_model=None,map_data=None):
    """Return (BOY XML, diagnostics). Never invent a frame or cross an unknown gate."""
    root=ET.Element('buoy')
    report={'nodes':0,'components':0,'coverage_gaps':0,'node_budget_hit':False,
            'neighbor_budget_hits':0,'edge_budget_hits':0,'edge_budget_hit':False,'edges':0,'directed_connectivity_gaps':0,'graph_components':0,'nav_cells':0,'gate_cells':0,
            'rejected_cells':0,'restricted_links':0,'restricted_cells':0,'nav_block_budget_hit':False,'nav_blocks':0,'empty_nav':nav is None or not list(nav.iter('c')),
            'problems':[]}
    if report['empty_nav']:
        return root,report
    try:
        world=next(e for e in zone.iter('entity') if e.get('name','').lower()=='world')
        needs_geometry=any(not world.get(k) or numbers(world.get(k),3)[2]==0 for k in ('extent_min','extent_max'))
        bounds=map_bounds(map_data) if needs_geometry and map_data is not None else None
        frame=Frame.from_world(world,nav.get('cellsize'),bounds)
        boxes,unresolved=barriers(zone,read_model)
        if unresolved:
            raise ValueError('unresolved gate bounds: '+'; '.join(unresolved))
        graph,counts=walk_graph(nav,frame,boxes)
        report.update(counts)
    except (ValueError,StopIteration,OverflowError) as exc:
        report['coverage_gaps']=len(list(nav.iter('c')))
        report['problems'].append(str(exc) or 'no world entity')
        return root,report
    walk=weak_graph(graph)
    groups=components(graph)
    incoming=defaultdict(int)
    for p in graph:
        for q,_ in graph[p]:incoming[q]+=1
    through={p:min(len(graph[p]),incoming[p]) for p in graph}
    report.update(components=len(groups),origin=frame.origin,bias=frame.bias,dimensions=frame.dimensions)
    # Prefer interior floor cells over boundary corners. Authored NAV says a
    # cell exists, not that a hero-sized body can stand at every edge of it.
    clearance={p:math.inf for p in graph}
    frontier=[]
    for p in sorted(graph):
        if len({q[:2] for q,_ in walk[p]})<4:
            clearance[p]=0.;heapq.heappush(frontier,(0.,p))
    while frontier:
        d,p=heapq.heappop(frontier)
        if d!=clearance[p]:
            continue
        for q,cost in walk[p]:
            if d+cost<clearance[q]:
                clearance[q]=d+cost;heapq.heappush(frontier,(d+cost,q))
    def interior(p):
        near={p:0.};queue=[(0.,p)]
        while queue:
            d,q=heapq.heappop(queue)
            if d!=near[q]:
                continue
            for nxt,cost in walk[q]:
                if d+cost<=COVER_DISTANCE/2 and d+cost<near.get(nxt,math.inf):
                    near[nxt]=d+cost;heapq.heappush(queue,(d+cost,nxt))
        return min(near,key=lambda q:(through[q]==0,-min(clearance[q],frame.size*2),-through[q],near[q],q))
    # Incremental multi-source Dijkstra: every remaining eligible cell gets a
    # measured walk distance to a coverage node, never a straight-line shortcut.
    distance={p:math.inf for p in graph};owner={};selected=[]
    def seed(p):
        index=len(selected);selected.append(p)
        distance[p]=0.;owner[p]=index;queue=[(0.,p)]
        while queue:
            d,q=heapq.heappop(queue)
            if d!=distance[q]:
                continue
            for nxt,cost in walk[q]:
                candidate=d+cost
                if candidate<distance[nxt]:
                    distance[nxt]=candidate;owner[nxt]=index
                    heapq.heappush(queue,(candidate,nxt))
    # Give every component a node before spending budget on denser coverage.
    for group in groups[:NODE_CAP]:
        seed(min(group,key=lambda p:(through[p]==0,-min(clearance[p],frame.size*2),-through[p],p)))
    while graph and len(selected)<NODE_CAP:
        p=max(sorted(graph),key=lambda p:distance[p])
        if distance[p]<=COVER_DISTANCE:
            break
        if 2*(len(selected)+1-min(len(groups),NODE_CAP))>EDGE_CAP:
            report['edge_budget_hit']=True;break
        seed(interior(p))
    report['coverage_gaps']=sum(d>=ATTACH_RADIUS for d in distance.values())+report['rejected_cells']+report['restricted_cells']
    report['node_budget_hit']=len(selected)==NODE_CAP and any(d>COVER_DISTANCE for d in distance.values())
    report['max_attachment_walk']=max((d for d in distance.values() if math.isfinite(d)),default=0.)
    # Weak Voronoi adjacency proposes local neighbors; a directed native walk
    # search must witness EACH emitted direction. Never manufacture a reverse edge.
    pairs=set()
    for p in sorted(walk):
        for q,_ in walk[p]:
            if p in owner and q in owner and owner[p]!=owner[q]:
                pairs.add(tuple(sorted((owner[p],owner[q]))))
    index={p:i for i,p in enumerate(selected)}
    candidate={i:[] for i in range(len(selected))}
    for i,start in enumerate(selected):
        distances={start:0.};queue=[(0.,start)]
        while queue:
            d,p=heapq.heappop(queue)
            if d!=distances[p]:continue
            if p in index and tuple(sorted((i,index[p]))) in pairs:
                candidate[i].append((index[p],d))
            for q,cost in graph[p]:
                if d+cost<ATTACH_RADIUS and d+cost<distances.get(q,math.inf):
                    distances[q]=d+cost;heapq.heappush(queue,(d+cost,q))
        candidate[i].sort()
    adjacent=sparse_arcs(candidate,report)
    if report['graph_components']>report['components'] or report['directed_connectivity_gaps']:
        report['problems'].append('directed walk connectivity incomplete under generation budgets')
    # Stable numbering independent of Dijkstra visitation and source XML ordering.
    permutation=sorted(range(len(selected)),key=lambda i:selected[i]);index={old:new+1 for new,old in enumerate(permutation)}
    for old in permutation:
        values=(*selected[old],*sorted(index[n] for n in adjacent[old]))
        ET.SubElement(root,'b',n=' '.join(map(str,values)))
    report['nodes']=len(selected)
    read_boy(root)                       # caps, coordinate and index invariant
    return root,report


def validate(v, ck):
    """V22. Developer/CI builds re-derive every zone's network from the output grids, maps and models and compare
    (never trusting cached build notes). Player builds (builder mode) check the structural invariants only: the
    full regeneration doubles the stage's time on every rebuild, and the same code path already ran in zones.
    --buoys empty builds must carry empty networks everywhere."""
    import os
    from . import common as C
    mode = (v.ctx.opt('buoys') or os.environ.get('XML1BUILD_BUOYS') or 'generate').lower()
    full = not C.builder_mode(v.ctx.args)
    details = {}
    empty = []
    for zone in sorted(v.converted_zones()):
        actual = v.tree(f'maps/{zone}.boyb')
        try:
            nodes, edges = read_boy(actual) if actual is not None else (None, None)
        except ValueError as exc:
            ck.error(f'{zone}: {exc}')
            continue
        if nodes is None:
            ck.error(f'{zone}: no buoy network written')
            continue
        if mode == 'empty':
            if nodes:
                ck.error(f'{zone}: --buoys empty build carries {len(nodes)} buoy nodes')
            continue
        if not full:
            details[zone] = {'nodes': len(nodes), 'edges': sum(map(len, edges))}
            if not nodes:
                empty.append(zone)
            continue
        tree = v.tree(f'maps/{zone}.xmlb')
        if tree is None:
            tree = v.tree(f'maps/{zone}.engb')
        if tree is None:
            ck.error(f'{zone}: cannot validate buoys without a zone tree')
            continue
        try:
            expected, report = generate(v.tree(f'maps/{zone}.navb'), tree, v.read, v.read(f'maps/{zone}.igb'))
        except Exception as exc:                # noqa: BLE001 - zones falls back to the empty network the same way
            expected, report = generate(None, None)
            report['problems'].append(f'generation failed: {type(exc).__name__}: {exc}')
        details[zone] = report
        if report['empty_nav']:
            empty.append(zone)
        if read_boy(expected) != (nodes, edges):
            ck.error(f'{zone}: buoy network differs from deterministic walk-only generation')
        if report['coverage_gaps'] or report['problems']:
            ck.warn(f"{zone}: buoy coverage gaps={report['coverage_gaps']}; " + '; '.join(report['problems']))
        if (report['node_budget_hit'] or report['neighbor_budget_hits'] or report['nav_block_budget_hit']
                or report['edge_budget_hit'] or report['edge_budget_hits']):
            ck.warn(f"{zone}: buoy budget hits: nodes={report['node_budget_hit']}, "
                    f"neighbors={report['neighbor_budget_hits']}, "
                    f"edges={report['edge_budget_hit']}/{report['edge_budget_hits']}, "
                    f"NAV blocks={report['nav_block_budget_hit']}")
    if mode == 'empty':
        ck.note('--buoys empty: every converted zone carries the empty buoy network (the pre-SPEC 42 output)')
        return
    ck.details['zones'] = details
    ck.details['empty_nav_zones'] = empty
    ck.set('nodes', sum(r['nodes'] for r in details.values()))
    ck.set('edges', sum(r['edges'] for r in details.values()))
    if full:
        ck.set('directed_connectivity_gaps', sum(r['directed_connectivity_gaps'] for r in details.values()))
        ck.set('coverage_gaps', sum(r['coverage_gaps'] for r in details.values()))
        ck.note(f'{len(empty)} zones retain empty buoy networks because their NAV grid is empty: ' + ', '.join(empty))
    else:
        ck.note(f'player build: structural buoy checks only ({len(empty)} zones carry an empty network); '
                'developer and CI builds regenerate and compare every zone')
