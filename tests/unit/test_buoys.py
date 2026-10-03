"""Invented grids, map bounds and gate geometry only; no game assets."""
import copy
import random
import xml.etree.ElementTree as ET
from xml1build import buoys as B


def inputs(cells, size=40):
    zone=ET.Element('world')
    ET.SubElement(zone,'entity',name='world',extent_min='0 0 -120',extent_max='9600 9600 500')
    nav=ET.Element('nav',cellsize=str(size))
    for q in cells:
        ET.SubElement(nav,'c',p=' '.join(map(str,q)))
    return nav,zone


def rejects(fn):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError('invalid input accepted')


def test_buoy_frame_roundtrip_negative_coordinates_and_heights():
    w=ET.Element('entity',extent_min='-251 241 -103',extent_max='4601 5861 701')
    f=B.Frame.from_world(w,40)
    assert f.origin==(-340.,260.,-97.) and f.bias==(-9,6)
    for q in ((0,0,0),(11,4,7),(100,100,40),(1,1,254)):
        assert f.pack(f.world(q))==q
    q=f.cell('-8 7 -91')
    assert q==(1,1,1) and f.world(q)==(-300.,300.,-85.)
    rejects(lambda:f.cell('10000 1 0'))
    rejects(lambda:f.world((0,0,255)))
    rejects(lambda:B.Frame.from_world(ET.Element('entity',extent_min='nan 0 0',extent_max='100 100 100'),40))


def test_buoy_boy_roundtrip_and_caps():
    root=ET.Element('buoy')
    ET.SubElement(root,'b',n='0 0 0 2 -1 -1 -1 -1 -1 -1 -1')
    ET.SubElement(root,'b',n='1 0 0 1')
    assert B.read_boy(root)==([(0,0,0),(1,0,0)],[(2,),(1,)])
    for bad in ('0 0 0 0','0 0 0 9','0 0 0 2 -1 2','0 0 255','0 0 0 2 2'):
        r=copy.deepcopy(root);r[0].set('n',bad);rejects(lambda:B.read_boy(r))
    r=ET.Element('buoy')
    for i in range(289):ET.SubElement(r,'b',n=f'{i%100} 0 0')
    rejects(lambda:B.read_boy(r))
    r=ET.Element('buoy')
    for i in range(10):ET.SubElement(r,'b',n=f'{i} 0 0')
    r[0].set('n','0 0 0 2 3 4 5 6 7 8 9 10')
    rejects(lambda:B.read_boy(r))


def test_buoy_long_corridor_is_connected_covered_and_deterministic():
    cells=[(x,y,0) for x in range(180) for y in range(3)]
    nav,zone=inputs(cells);a,rep=B.generate(nav,zone)
    assert rep['components']==rep['graph_components']==1
    assert rep['nodes']>10 and rep['coverage_gaps']==0 and not rep['node_budget_hit']
    nodes,edges=B.read_boy(a)
    assert max(map(len,edges))<=8
    seen={1};todo=[1]
    while todo:
        for n in edges[todo.pop()-1]:
            if n not in seen:seen.add(n);todo.append(n)
    assert len(seen)==len(nodes)
    random.Random(41).shuffle(cells)
    b,other=B.generate(inputs(cells)[0],zone)
    assert ET.tostring(a)==ET.tostring(b) and rep==other


def test_buoy_component_budget_reports_uncovered_cells():
    nav,zone=inputs([(x*3,y*3,0) for x in range(20) for y in range(20)])
    root,rep=B.generate(nav,zone)
    assert len(root)==288 and rep['components']==400
    assert rep['node_budget_hit'] and rep['coverage_gaps']==112
    assert all(not neighbors for neighbors in B.read_boy(root)[1])


def test_buoy_script_transition_and_jump_link_never_make_walk_edges():
    nav,zone=inputs([(0,0,0),(1,0,0),(5,0,0),(6,0,0)])
    ET.SubElement(nav,'link',src='1 0 0',dest='5 0 0',code='4',cost='10')
    ET.SubElement(zone,'entity',name='test_warp',classname='triggerent',actontouch='true',actscript='test/transport')
    root,rep=B.generate(nav,zone)
    assert rep['components']==rep['graph_components']==2
    assert rep['restricted_links']==1 and rep['nodes']==2
    assert B.read_boy(root)[1]==[(),()]
    nav,zone=inputs([(0,0,0),(1,0,60)])
    assert B.generate(nav,zone)[1]['components']==2


def test_buoy_closed_script_gate_excludes_cells_and_crossing_edges():
    nav,zone=inputs([(x,0,0) for x in range(12)])
    ET.SubElement(zone,'entity',name='test_gate',classname='doorent',startenabled='false',actscript='test/open')
    group=ET.SubElement(zone,'entinst',type='test_gate')
    ET.SubElement(group,'inst',name='test_gate_instance',pos='220 20 0',extents='-2 -80 -50 2 80 100')
    root,rep=B.generate(nav,zone)
    assert rep['components']==rep['graph_components']==2 and rep['gate_cells']>0
    assert all(not neighbors for neighbors in B.read_boy(root)[1])
    group[0].attrib.pop('extents')
    root,rep=B.generate(nav,zone)
    assert len(root)==0 and rep['coverage_gaps']==12 and 'gate' in rep['problems'][0]


def test_buoy_native_only_loads_first_two_height_records():
    nav,zone=inputs([(0,0,0),(0,0,48),(0,0,96),(1,0,0)])
    root,rep=B.generate(nav,zone)
    assert rep['rejected_cells']==1 and rep['coverage_gaps']==1
    f=B.Frame.from_world(zone[0],40)
    assert f.cell('0 0 96') not in B.read_boy(root)[0]


def test_buoy_empty_nav_stays_empty_and_bad_frame_is_reported():
    nav,zone=inputs([])
    root,rep=B.generate(nav,zone)
    assert not len(root) and rep['empty_nav'] and rep['coverage_gaps']==0
    nav,zone=inputs([(0,0,0)])
    zone[0].attrib.pop('extent_min')
    root,rep=B.generate(nav,zone)
    assert not len(root) and rep['coverage_gaps']==1 and rep['problems']


def test_buoy_geometry_fallback_and_zero_z_keep_native_bounds():
    bounds=(-251.25,131.75,-218.25,3187.5,2956.25,418.75)
    w=ET.Element('entity')
    f=B.Frame.from_world(w,40,bounds)
    assert f.origin==(-340.,140.,-212.25)
    w.set('extent_min','-111 250 0');w.set('extent_max','3000 3000 0')
    f=B.Frame.from_world(w,40,bounds)
    assert f.origin==(-100.,260.,-212.25)
    assert f.pack(f.world((8,6,13)))==(8,6,13)


def test_buoy_tilted_gate_uses_conservative_rotation_bound():
    nav,zone=inputs([(x,0,0) for x in range(12)])
    ET.SubElement(zone,'entity',name='test_tilted_gate',classname='doorent')
    g=ET.SubElement(zone,'entinst',type='test_tilted_gate')
    ET.SubElement(g,'inst',name='test_tilted_gate',pos='220 20 0',orient='0.5 0.2 0.3',extents='-2 -50 -20 2 50 80')
    _,rep=B.generate(nav,zone)
    assert not rep['problems'] and rep['gate_cells']>=4 and rep['components']==2


def test_buoy_prefers_clearance_in_a_wide_corridor():
    nav,zone=inputs([(x,y,0) for x in range(60) for y in range(9)])
    root,rep=B.generate(nav,zone)
    nodes,_=B.read_boy(root)
    assert rep['coverage_gaps']==0
    assert all(1<=y<=7 for _,y,_ in nodes)
    assert all(1<=x<=58 for x,_,_ in nodes)


def test_buoy_hanging_gate_blocks_character_height_not_only_feet():
    nav,zone=inputs([(x,0,0) for x in range(12)])
    ET.SubElement(zone,'entity',name='test_hanging_gate',classname='doorent')
    g=ET.SubElement(zone,'entinst',type='test_hanging_gate')
    ET.SubElement(g,'inst',name='test_hanging_gate',pos='220 20 80',extents='-3 -100 0 3 100 70')
    _,rep=B.generate(nav,zone)
    assert rep['components']==2 and rep['gate_cells']>0


def _ctx(buoys=None, builder_mode=False):
    from types import SimpleNamespace
    return SimpleNamespace(opt=lambda name, default=None: buoys if name == 'buoys' else default,
                           args=SimpleNamespace(builder_mode=builder_mode))


def test_buoy_validator_detects_changed_network_and_reports_gaps():
    from types import SimpleNamespace
    from xml1build.validate import Check
    nav,zone=inputs([(x*3,y*3,0) for x in range(20) for y in range(20)])
    boy,report=B.generate(nav,zone)
    trees={'maps/test/room.xmlb':zone,'maps/test/room.navb':nav,'maps/test/room.boyb':boy}
    v=SimpleNamespace(converted_zones=lambda:['test/room'],tree=trees.get,read=lambda _:None,ctx=_ctx())
    ck=Check('V22','buoys');B.validate(v,ck)
    assert not ck.errors and ck.warnings and ck.details['zones']['test/room']['coverage_gaps']==112
    boy[0].set('n','0 0 0 999')
    ck=Check('V22','buoys');B.validate(v,ck)
    assert ck.errors


def test_buoy_native_height_reciprocal_is_not_exact_division():
    import struct
    nav,zone=inputs([(0,0,6),(1,0,18),(2,0,30)])
    frame=B.Frame.from_world(zone[0],40)
    assert struct.pack('<f',B.HEIGHT_RECIPROCAL)==bytes.fromhex('7eaaaa3d')
    # At an exact layer boundary, 1/12 incorrectly selects the NEXT layer.
    assert frame.cell('0 0 6')==(0,0,10)
    assert frame.cell('1 0 18')==(1,0,11)
    assert frame.cell('2 0 30')==(2,0,12)
    assert frame.world(frame.cell('0 0 6'))==(20.,20.,6.)


def test_buoy_native_stair_step_range_and_separate_floors():
    nav,zone=inputs([(0,0,0),(1,0,48),(2,0,108)])
    _,rep=B.generate(nav,zone)
    assert rep['components']==2  # 48 is a native walk step; 60 needs a special transition.
    nav,zone=inputs([(0,0,0),(0,0,24),(1,0,0),(1,0,24)])
    _,rep=B.generate(nav,zone)
    assert rep['components']==2  # do not join overlapping floors within the step tolerance.


def test_buoy_native_block_budget_and_unknown_cell_restrictions():
    nav,zone=inputs([((i%28)*9,(i//28)*9,0) for i in range(201)])
    zone[0].set('extent_max','10000 10000 500')
    _,rep=B.generate(nav,zone)
    assert rep['nav_blocks']==200 and rep['nav_block_budget_hit'] and rep['coverage_gaps']==1
    nav,zone=inputs([(0,0,0),(1,0,0),(2,0,0)])
    nav[1].set('t','1')
    _,rep=B.generate(nav,zone)
    assert rep['components']==2 and rep['restricted_cells']==1 and rep['coverage_gaps']==1


def test_buoy_directed_backbone_preserves_one_way_reachability():
    report={}
    arcs=B.sparse_arcs({0:[(1,40.)],1:[(2,40.)],2:[]},report)
    assert arcs==[{1},{2},set()]
    assert report['directed_connectivity_gaps']==0
    # A floor that has no incoming native step is covered by a nearby useful
    # node, rather than becoming an attractive isolated attachment waypoint.
    nav,zone=inputs([(0,0,0),(0,0,24),(1,0,12)])
    root,rep=B.generate(nav,zone)
    f=B.Frame.from_world(zone[0],40)
    assert rep['components']==1 and rep['coverage_gaps']==0
    assert f.cell('0 0 0') not in B.read_boy(root)[0]


def test_buoy_global_edge_budget_keeps_a_strong_backbone():
    graph={a:[(b,float(abs(a-b)+1)) for b in range(80) if a!=b] for a in range(80)}
    report={};arcs=B.sparse_arcs(graph,report)
    assert sum(map(len,arcs))<=B.EDGE_CAP==349 and max(map(len,arcs))<=8
    assert report['directed_connectivity_gaps']==0 and report['edge_budget_hits']>0
    root=ET.Element('buoy')
    for i in range(50):
        neighbors=[(i+j)%50+1 for j in range(1,8)]
        ET.SubElement(root,'b',n=' '.join(map(str,[i,0,0]+neighbors)))
    rejects(lambda:B.read_boy(root))
    root[-1].set('n',' '.join(root[-1].get('n').split()[:-1]))
    assert sum(map(len,B.read_boy(root)[1]))==349


def test_buoy_missing_nav_cellsize_uses_native_spatial_scale():
    nav,zone=inputs([(0,0,0),(1,0,0)])
    nav.attrib.pop('cellsize')
    zone[0].set('mapcellsize','180 120 120')
    frame=B.Frame.from_world(zone[0],None)
    assert frame.size==60 and frame.origin[:2]==(30.,30.)
    assert not B.generate(nav,zone)[1]['problems']


def test_buoy_validator_modes_player_build_and_empty_switch():
    from types import SimpleNamespace
    from xml1build.validate import Check
    nav,zone=inputs([(x*3,y*3,0) for x in range(20) for y in range(20)])
    boy,_=B.generate(nav,zone)
    trees={'maps/test/room.xmlb':zone,'maps/test/room.navb':nav,'maps/test/room.boyb':boy}
    # player build: structural checks only - a content change that keeps the invariants is not re-derived
    v=SimpleNamespace(converted_zones=lambda:['test/room'],tree=trees.get,read=lambda _:None,
                      ctx=_ctx(builder_mode=True))
    ck=Check('V22','buoys');B.validate(v,ck)
    assert not ck.errors and ck.details['zones']['test/room']['nodes']==len(list(boy))
    boy[0].set('n','0 0 0 999')                      # an invalid neighbour index still fails
    ck=Check('V22','buoys');B.validate(v,ck)
    assert ck.errors
    # --buoys empty: every network must be empty
    empty,_=B.generate(None,None)
    v=SimpleNamespace(converted_zones=lambda:['test/room'],read=lambda _:None,ctx=_ctx(buoys='empty'),
                      tree={**trees,'maps/test/room.boyb':empty}.get)
    ck=Check('V22','buoys');B.validate(v,ck)
    assert not ck.errors
    v.tree={**trees,'maps/test/room.boyb':B.generate(nav,zone)[0]}.get
    ck=Check('V22','buoys');B.validate(v,ck)
    assert ck.errors


def test_zone_buoy_network_warns_for_a_handled_generation_failure():
    # generate() handles a zone with no world entity itself (empty network + problems); zones must still warn
    from types import SimpleNamespace
    from xml1build import zones as Z
    nav, _ = inputs([(0, 0, 0), (1, 0, 0)])
    warnings = []
    trees = {'nav': nav, 'zone': ET.Element('world')}
    ctx = SimpleNamespace(opt=lambda name, default=None: None, warn=warnings.append,
                          read_out_xmlb=lambda rel: trees[rel],
                          out_index=SimpleNamespace(path=lambda rel: None))
    zones = Z.Zones.__new__(Z.Zones)
    zones.ctx = ctx
    buoy, report = zones.buoy_network('test/room', 'maps/test/room', SimpleNamespace(out_rels=['nav']),
                                      SimpleNamespace(out_rels=['zone']), True, False)
    assert len(list(buoy)) == 0 and report['problems']
    assert len(warnings) == 1 and 'test/room' in warnings[0]
    # --buoys empty: no generation, no warning
    ctx.opt = lambda name, default=None: 'empty' if name == 'buoys' else default
    warnings.clear()
    buoy, _ = zones.buoy_network('test/room', 'maps/test/room', None, None, True, False)
    assert len(list(buoy)) == 0 and not warnings


def test_standalone_checks_recover_the_recorded_buoy_mode():
    import json
    import tempfile
    from pathlib import Path
    from xml1build import common as C
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        (out / '_build').mkdir()
        report = out / '_build' / 'report.json'
        report.write_text(json.dumps({'build': {'frontend': 'xml1', 'buoys': 'generate'}}), encoding='utf-8')
        assert C.args_for_out(out).buoys == 'generate'
        report.write_text(json.dumps({'build': {'frontend': 'xml1', 'buoys': 'empty'}}), encoding='utf-8')
        assert C.args_for_out(out).buoys == 'empty'
        # a build made before SPEC 42 recorded no mode and wrote empty networks
        report.write_text(json.dumps({'build': {'frontend': 'xml1'}}), encoding='utf-8')
        assert C.args_for_out(out).buoys == 'empty'
