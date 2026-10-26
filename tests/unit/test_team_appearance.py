"""Synthetic TEAM contracts protect point math, gear and unknown native fields."""
import copy
import xml.etree.ElementTree as ET

from xml1build import team_appearance as A
from xml1build.igb_file import IgbFile, IgbError
from test_main_appearance import raises


def native():
    return ET.fromstring('<MENU type="TEAM_MENU" no_stack="true">'
        '<items file="team_back" igb="x2m_team_back" act_background="team" lighting="true"/>'
        '<precache type="model" filename="ui/menus/x2m_team_back"/>'
        '<anim type="details_open" start="0.4" end="0.56"/>'
        '<item name="body" type="SYNTHETIC_STAT" mode="2 4" style="SYNTHETIC" '
        'cost="7" gamevar="synthetic_points" up="speed" down="focus"/>'
        '<item name="equipment" mode="4" type="MENU_ITEM_LISTBOX" icons_cols="4" '
        'icons_rows="4" usecmd="synthetic_equip" saved_id="synthetic_item"/>'
        '<item name="skill_list" mode="3" type="MENU_ITEM_SKILLS" '
        'talent="synthetic_power" disabled_model="synthetic_disabled"/>'
        '<item name="track01" type="MENU_ITEM_MODEL" model="synthetic_track"/>'
        '</MENU>')


def test_team_conversion_is_pure_and_retains_all_native_gameplay_fields():
    root = native()
    before = ET.tostring(root)
    result = A.tree(root)
    assert ET.tostring(root) == before
    assert not A.control_problems(root, result)
    assert result.find('items').get('act_background') is None
    assert result.find('items').get('file') == 'team_back'
    assert result.find("item[@name='skill_list']").get('disabled_model') == 'synthetic_disabled'


def test_team_contract_detects_cost_stat_inventory_talent_and_animation_changes():
    root = native()
    changes = [('body', 'cost', '6'), ('body', 'gamevar', 'other_points'),
               ('equipment', 'saved_id', 'other_item'), ('equipment', 'icons_cols', '2'),
               ('equipment', 'usecmd', 'other_equip'), ('skill_list', 'talent', 'other_power'),
               ('skill_list', 'mode', '4')]
    for name, key, value in changes:
        result = A.tree(root)
        result.find(f"item[@name='{name}']").set(key, value)
        assert A.control_problems(root, result), (name, key)
    result = A.tree(root)
    result.find('anim').set('end', '0.7')
    assert A.control_problems(root, result)
    result = A.tree(root)
    result.append(copy.deepcopy(result.find("item[@name='equipment']")))
    assert A.control_problems(root, result)


def test_team_panel_retires_empty_footer_without_changing_texture_coordinates():
    from test_menu_conversion import flat_panel
    graph = IgbFile(flat_panel((0, 0, 1, 0, 0, 1, 1, 1)))
    values = graph.block_floats(3)
    values[2::3] = [z-25 for z in values[2::3]]
    graph.set_block_floats(3, values)
    for slot in (2, 3):
        graph.set_floats(graph.obj(1), slot, [graph.obj(1).get(slot)[2]-25], 2)
    before = graph.edited()
    result = IgbFile(A.panel_source(before))
    assert result.block_floats(3)[2::3] == [0, 0, 75, 75]
    assert result.block_floats(4) == graph.block_floats(4)
    assert result.block_floats(3)[0::3] == graph.block_floats(3)[0::3]
    raises(IgbError, lambda: A.panel_source(flat_panel((0, 0, 1, 0, 0, 1, 1, 1))))


def test_team_equipment_lists_retain_focusable_styles_separate_from_body_text():
    from xml1build import pause_appearance as P
    root = native()
    root.find("item[@name='equipment']").set('style', 'SYNTHETIC_FOCUSABLE')
    ET.SubElement(root, 'item', name='equipment_inv', style='SYNTHETIC_FOCUSABLE')
    result = A.tree(root)
    for name in ('equipment', 'equipment_inv'):
        assert result.find(f"item[@name='{name}']").get('style') == P.LIST_STYLE
    assert result.find("item[@name='body']").get('style') == P.BODY_STYLE
    assert not A.control_problems(root, result)


def test_smaller_room_does_not_zoom_a_tall_native_preview_out_of_the_view():
    import math
    native_actor, native_camera = (0, 0, 0), (0, -80, 60)
    room_scale, mapped_actor = .8, (40, 50, -60)
    mapped_camera = (40, -14, -12)
    old_distance = math.dist(native_actor, native_camera)
    # A synthetic 700-pixel native preview fits a 720-pixel view. Scaling its
    # camera offset alone enlarges it to 875 pixels and cuts off its head.
    assert 700*old_distance/math.dist(mapped_actor, mapped_camera) > 720
    corrected = A.detail_camera_position(mapped_camera, mapped_actor, room_scale)
    assert math.isclose(math.dist(corrected, mapped_actor), old_distance)
    assert 700*old_distance/math.dist(corrected, mapped_actor) <= 720
    raises(IgbError, lambda: A.detail_camera_position(mapped_camera, mapped_actor, 0))


def test_team_primary_portrait_lighting_stays_native_while_helper_lights_remain():
    for value in (None, 'false', 'true'):
        root = native()
        if value is not None:
            root.set('lighting', value)
        result = A.tree(root)
        assert result.get('lighting') == value
        assert result.find('items').get('lighting') == 'true'
        assert not A.control_problems(root, result)
        result.set('lighting', 'true' if value != 'true' else 'false')
        assert A.control_problems(root, result)


def test_room_retires_animated_white_beams_and_preserves_blue_podium():
    import struct
    from test_main_appearance import fixture
    schemas = [('igTransform',None,[(2,'s'),(7,'r')]),
               ('igNodeList',None,[(2,'i'),(3,'i'),(4,'b')]),
               ('igGeometry',None,[(2,'s')])]
    objects=[]
    names = [f'Lightrays_{i:02}' for i in range(4)] + \
            [f'LightPulse{i//4+1}_{i%4:02}' for i in range(16)] + ['BluePodium']
    for i,name in enumerate(names):
        objects.extend([('igTransform',{2:name,7:i*3+1}),
                        ('igNodeList',{2:1,3:1,4:i}),('igGeometry',{2:'synth_mesh'})])
    data=fixture(schemas,objects,tuple(struct.pack('<i',i*3+2) for i in range(len(names))))
    result=IgbFile(A.quiet_room(data))
    for i in range(len(names)):
        assert result.obj(i*3+1).get(2) == (0 if i<20 else 1)
        if i<20:
            assert result.obj(i*3+1).get(3)==0 and result.obj(i*3+1).get(4)==-1
    assert IgbFile(data).obj(1).get(2)==1


def test_team_helper_retires_white_loop_effects_without_changing_actor_callbacks():
    root=ET.fromstring('<MENU_ITEMS>'+''.join(
        f'<item name="pad{i:02}_loopfx" type="MENU_ITEM_EFFECT" effect="menu/pad_loop"/>'
        f'<item name="pad{i:02}" type="MENU_ITEM_MODEL" model="synth_pad"/>'
        f'<item name="pad{i:02}_model" type="MENU_ITEM_ACTORMODEL"><onfocus type="focus" model="synth_select"/></item>'
        for i in range(1,5))+'</MENU_ITEMS>')
    before=ET.tostring(root)
    result=A.helper_tree(root)
    assert ET.tostring(root)==before
    for i in range(1,5):
        assert result.find(f"item[@name='pad{i:02}_loopfx']").get('effect') is None
        assert result.find(f"item[@name='pad{i:02}_loopfx']").get('hide')=='true'
        assert ET.tostring(result.find(f"item[@name='pad{i:02}_model']")) == ET.tostring(root.find(f"item[@name='pad{i:02}_model']"))


def test_seated_hero_marker_keeps_flat_blue_pad_without_four_white_beams_or_gold_rings():
    import struct
    from test_main_appearance import fixture
    schemas = [('igTransform',None,[(2,'s'),(7,'r')]),
               ('igNodeList',None,[(2,'i'),(3,'i'),(4,'b')]),
               ('igGeometry',None,[(2,'s')])]
    names = ['$nn$_Pedastal_Spot_03']*2 + ['$nn$_Pedastal_Spot_04']*2 + \
            ['$nn$_SelectionRing']*2 + ['$nn$_TransporterPad']*2
    objects=[]
    for i,name in enumerate(names):
        objects.extend([('igTransform',{2:name,7:i*3+1}),
                        ('igNodeList',{2:1,3:1,4:i}),('igGeometry',{2:'synthetic_mesh'})])
    data=fixture(schemas,objects,tuple(struct.pack('<i',i*3+2) for i in range(len(names))))
    result=IgbFile(A.quiet_marker(data))
    assert [result.obj(i*3+1).get(2) for i in range(len(names))] == [0]*6+[1]*2
    assert all(result.obj(i*3+1).get(3)==0 and result.obj(i*3+1).get(4)==-1 for i in range(6))
    assert [IgbFile(data).obj(i*3+1).get(2) for i in range(len(names))] == [1]*8
    raises(IgbError, lambda: A.quiet_marker(fixture(schemas,[],())))


def test_native_pad_effect_remains_loadable_but_cannot_emit_white_pulses():
    root=ET.fromstring('<Effect looptime="1"><Cylinder name="synthetic" alpha="0.8 -0.8 1 0.8 -0.8 1" texture="synthetic_grad"/><ParticleCloud name="synthetic_sparks" alpha="0 0 0 0 0 0"/></Effect>')
    before=ET.tostring(root);result=A.quiet_pad_effect(root)
    assert ET.tostring(root)==before
    assert result.get('looptime')=='1' and len(result)==2
    assert all(e.get('alpha')=='0 0 0 0 0 0' for e in result)
    assert result[0].get('texture')=='synthetic_grad'
