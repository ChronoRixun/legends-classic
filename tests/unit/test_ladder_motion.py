"""Synthetic tests for source-derived ladder movement, without game assets."""
import math
from xml1build import ladder_motion as L


def test_ladder_motion_keeps_authored_timing_and_relative_displacement():
    keys = L.relative_keys([(2, 0, 9), (3, 1, 5), (5, 0, 0)], [0, 20, 55])
    assert keys == [(0, 0, 0), (1, 1, -4), (3, 0, -9)]
    for bad_points, bad_times in [
        ([(0, 0, 0)], [0]),
        ([(0, 0, 0), (0, 0, -1)], [0, 0]),
        ([(0, 0, 0), (math.nan, 0, -1)], [0, 1]),
        ([(0, 0, 0), (0, 0, 1)], [0, 1]),
        ([(0, 0, 0), (0, 0, -1)], [1, 2]),
    ]:
        try:
            L.relative_keys(bad_points, bad_times)
        except ValueError:
            pass
        else:
            raise AssertionError('malformed or non-descending movement accepted')


def test_ladder_script_preserves_animation_signal_and_restores_collision():
    lines = ['setAIActive("_OWNER_", "FALSE" )',
             'unique = getIDString("_OWNER_" )',
             'playanim("EA_ZONE2", "_OWNER_", "NONE", unique )',
             'waitsignal(unique )', 'setAIActive("_OWNER_", "TRUE" )', '']
    out = L.rewrite_script('sewers/grso/grso_ladder_down', lines)
    assert [x for x in out if x.startswith(('playanim', 'waitsignal'))] == lines[2:4]
    assert out.index('setNoCollide("_OWNER_", "TRUE" )') < out.index(lines[2])
    assert out.index('setNoCollide("_OWNER_", "FALSE" )') > out.index(lines[3])
    assert out.index('setNoClip("_OWNER_", "TRUE" )') < out.index(lines[2])
    assert out.index('setNoClip("_OWNER_", "FALSE" )') > out.index(lines[3])
    assert any('startMotionPath' in x and '"TRUE", ""' in x for x in out)
    assert L.rewrite_script('sewers/grso/grso_ladder_down', out) == out
    assert L.rewrite_script('object_ambi/sewers/grso_slide_down', lines) == lines


def test_changed_ladder_script_fails_closed_instead_of_guessing():
    try:
        L.rewrite_script('sewers/grso/grso_ladder_down', ['playanim("EA_ZONE1")'])
    except ValueError:
        pass
    else:
        raise AssertionError('changed script was silently rewritten')

def test_ladder_script_rejects_unrelated_signal_and_partial_rewrite():
    base = ['setAIActive("_OWNER_", "FALSE" )', 'token = getIDString("_OWNER_" )',
            'playanim("EA_ZONE2", "_OWNER_", "NONE", token )',
            'waitsignal(token )', 'setAIActive("_OWNER_", "TRUE" )']
    changed = list(base); changed[3] = 'waitsignal(other_token )'
    partial = ['startMotionPath("_OWNER_", "x1_ladders/sewers/mp_cabinet", "TRUE", "" )']
    for lines in (changed, partial):
        try:
            L.rewrite_script('sewers/grso/grso_ladder_down', lines)
        except ValueError:
            pass
        else:
            raise AssertionError('incomplete or mismatched ladder sequence accepted')


def test_ground_spawner_gets_the_unconverted_descent_and_ladder_top_spawner_the_path():
    ladder = 'sewers/grso/grso_ladder_down'
    top = {'name': 'roof_guard', 'classname': 'monsterspawnerent', 'monster_spawnscript': ladder,
           'monster_spawnexactlocation': 'true'}
    ground = {'name': 'yard_guard', 'classname': 'monsterspawnerent', 'monster_spawnscript': r'Sewers\Grso\Grso_Ladder_Down.py'}
    assert L.floor_spawn_ref(top) is None
    assert L.floor_spawn_ref(dict(top, monster_spawnexactlocation='1')) is None
    assert L.floor_spawn_ref(ground) == L.floor_ref(ladder) and L.floor_base(L.floor_ref(ladder)) == ladder
    assert L.floor_spawn_ref(dict(ground, monster_spawnexactlocation='false')) == L.floor_ref(ladder)
    assert L.floor_spawn_ref({'CLASSNAME': 'MonsterSpawnerEnt', 'MONSTER_SPAWNSCRIPT': ladder}) == L.floor_ref(ladder)
    # other spawners, other scripts and the floor copy itself are never redirected
    assert L.floor_spawn_ref(dict(ground, classname='gameent')) is None
    assert L.floor_spawn_ref(dict(ground, monster_spawnscript='sewers/grso/some_other_script')) is None
    assert L.floor_spawn_ref(dict(ground, monster_spawnscript=L.floor_ref(ladder))) is None
    assert L.floor_base('sewers/grso/some_other_script_floor') is None
    # the floor copy is the descent as written: the path rewrite leaves it alone
    lines = ['setAIActive("_OWNER_", "FALSE" )', 'tag = getIDString("_OWNER_" )',
             'playanim("EA_ZONE2", "_OWNER_", "NONE", tag )', 'waitsignal(tag )', 'setAIActive("_OWNER_", "TRUE" )']
    assert L.rewrite_script(L.floor_ref(ladder), lines) == lines


def test_validator_names_a_ground_spawner_left_on_the_path():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(
        '<world><entity name="top" classname="monsterspawnerent" monster_spawnscript="sewers/grso/grso_ladder_down" '
        'monster_spawnexactlocation="true"/><entity name="low" classname="monsterspawnerent" '
        'monster_spawnscript="sewers/grso/grso_ladder_down"/><entity name="fixed" classname="monsterspawnerent" '
        'monster_spawnscript="sewers/grso/grso_ladder_down_floor"/></world>')
    assert L.path_spawner_problems(root) == ['low']
