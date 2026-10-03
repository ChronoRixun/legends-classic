"""Invented navigation grids, input mappings and gate checks only."""
import xml.etree.ElementTree as ET
import math
from autopilot_nav import nav_data, Routes, calibrated, movement, assist_refusal


def grid(cells, links=()):
    r = ET.Element('nav', cellsize='40')
    for p in cells:
        ET.SubElement(r, 'c', p=' '.join(map(str,p)))
    for a,b in links:
        ET.SubElement(r, 'link', src=' '.join(map(str,a)), dest=' '.join(map(str,b)), code='4', cost='10')
    return nav_data(r)


def test_nav_world_coordinates_and_stairs():
    g = Routes(grid([(0,0,0),(1,0,20),(2,0,40),(2,1,40)]))
    assert g.points[0] == (20,20,0)
    route = g.route((20,20,0),(100,60,40))
    assert route[-1]['pos'] == (100,60,40)
    assert any(p['pos'] == (100,20,40) for p in route)


def test_nav_keeps_explicit_link_and_direction():
    data = grid([(0,0,0),(3,0,100)], [((0,0,0),(3,0,100))])
    g = Routes(data)
    assert any(p['transition']==4 for p in g.route((20,20,0),(140,20,100)))
    try:
        g.route((140,20,100),(20,20,0))
    except ValueError:
        pass
    else:
        assert False


def test_nav_script_transition_requires_trigger_wait():
    data = grid([(0,0,0),(1,0,0),(10,0,-100),(11,0,-100)])
    data['script_transitions'] = [{'name':'switch_test','src':(60,20,0),'dest':(420,20,-100),'use':True}]
    route = Routes(data).route((20,20,0),(460,20,-100))
    scripts = [p for p in route if isinstance(p['transition'],dict)]
    assert len(scripts)==1 and scripts[0]['transition']['name']=='switch_test'
    assert scripts[0]['transition']['use'] is True


def test_nav_rejects_malformed_and_disconnected_data():
    for attrs in ({'cellsize':'nan'},{'cellsize':'0'}):
        try:
            nav_data(ET.Element('nav',**attrs))
        except ValueError:
            pass
        else:
            assert False
    g=Routes(grid([(0,0,0),(10,0,0)]))
    try:
        g.route((20,20,0),(420,20,0))
    except ValueError:
        pass
    else:
        assert False


def test_nav_rotated_camera_calibration():
    samples = {'W':((0,0,0),(20,0,0),.2),'S':((0,0,0),(-20,0,0),.2),
               'A':((0,0,0),(0,20,0),.2),'D':((0,0,0),(0,-20,0),.2)}
    mapping=calibrated(samples)
    assert movement(mapping,(0,0,0),(30,0,0))[0]=='W'
    assert set(movement(mapping,(0,0,0),(30,30,0))[0].split('+'))=={'W','A'}


def test_nav_blocked_calibration_not_guessed():
    try:
        calibrated({'W':((0,0,0),(20,0,0),.2),'D':((0,0,0),(0,0,0),.2)})
    except ValueError:
        pass
    else:
        assert False


def test_nav_assist_never_bypasses_scripts_or_barriers():
    state={'script_controls_locked':False,'loading':False}
    target={'node':2,'pos':(80,0,0)}
    assert assist_refusal(state,(0,0,0),target,[],set()) is None
    for s in ({**state,'script_controls_locked':True},{'loading':False},{**state,'popup':True}):
        assert assist_refusal(s,(0,0,0),target,[],set())
    assert assist_refusal(state,(0,0,0),target,[{'bounds':[30,-20,-20,50,20,50]}],set())
    assert assist_refusal(state,(0,0,0),target,[],{2})
    assert assist_refusal(state,(0,0,0),{'node':'goal','pos':(80,0,0)},[],set())


def test_nav_unknown_script_lock_stays_unknown():
    assert assist_refusal({'loading':False},(0,0,0),{'node':1,'pos':(40,0,0)},[],set())


def test_nav_script_edge_assist_is_refused():
    state={'script_controls_locked':False,'loading':False}
    assert assist_refusal(state,(0,0,0),{'node':2,'pos':(40,0,0),'transition':{'kind':'script'}},[],set())


def test_nav_team_menu_uses_normal_accept():
    from autopilot_core import ui_action
    assert ui_action({'menu':'team','menu_open':True})=='ENTER'


def test_nav_recalibration_does_not_reset_stall_budget():
    import time
    from types import SimpleNamespace
    from autopilot_navigation import Navigator
    n=Navigator.__new__(Navigator)
    n.driver=SimpleNamespace()
    n.goal_name='goal_test';n.mapping=None;n.recovery=2;n.progress_at=time.monotonic()-30
    before=n.progress_at
    n.calibrate=lambda: setattr(n,'mapping',{'W':(100,0),'A':(0,100)})
    n.read=lambda: ({},(0,0,0))
    assert n.step({}, {'x':0,'y':0,'z':0}, {'name':'goal_test','pos':(100,0,0)})
    assert n.progress_at==before and n.recovery==2
