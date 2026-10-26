"""Synthetic PC actions, bindings and sprite-state contracts."""
import xml.etree.ElementTree as ET
from PIL import Image

from xml1build import options_appearance as O
from test_main_appearance import raises


def test_options_skin_preserves_every_native_setting_action_and_binding_hint():
    native = ET.Element('MENU', type='OPTIONS_MENU', desctext1='$MENU_BACK Synth return',
                        desctext4='$MENU_OTHER Synth advanced', no_stack='true')
    for i,name in enumerate(O.ROWS):
        item = ET.SubElement(native,'item',name=name,text=f'Invented setting {i}',
                              usecmd=f'synth_set_{i}', leftcmd=f'synth_dec_{i}',
                              rightcmd=f'synth_inc_{i}', gamevar=f'synth_var_{i}',
                              up=O.ROWS[i-1], down=O.ROWS[(i+1)%10], mode='3', style='SYNTH')
        ET.SubElement(item,'onfocus',item='fx_vol',type='focus')
    for name in (*O.VALUES,'vibration'):
        ET.SubElement(native,'item',name=name,type='MENU_ITEM_BINARY',gamevar='synth_value',style='SYNTH')
    for name in O.FOCUS:
        ET.SubElement(native,'item',name=name,type='MENU_ITEM_MODEL',model='ui/models/synth_focus')
    before = ET.tostring(native)
    result = O.options_tree(native,23)
    assert result.get('type') == 'OPTIONS_MENU' and result.get('no_stack') == 'true'
    assert result.get('desctext4') == '$MENU_OTHER Synth advanced'
    for old in native.findall('item'):
        new = result.find(f"item[@name='{old.get('name')}']")
        assert new is not None
        for key in ('text','type','mode','gamevar','usecmd','leftcmd','rightcmd','up','down'):
            assert new.get(key) == old.get(key), (old.get('name'),key)
    assert result.find("item[@name='label_effects_volume']/onfocus[@item='fx_vol']") is not None
    assert ET.tostring(native) == before
    assert not O.control_problems(native,result)
    result.find("item[@name='label_view_shake']").set('usecmd','synth_wrong_action')
    result.find("item[@name='fx_vol']").set('enabled','false')
    errors = O.control_problems(native,result)
    assert any('label_view_shake.usecmd' in error for error in errors)
    assert any('fx_vol.enabled' in error for error in errors)


def test_options_sprite_states_keep_cells_alpha_and_selected_disabled_order():
    source = Image.new('RGBA',(16,16),(100,50,20,128))
    result = O.state_atlas(source,(20,100),5,(2,2,18,18))
    assert result.size == (20,100)
    assert result.getpixel((3,3)) == (80,40,16,128)
    assert result.getpixel((3,23)) == (125,62,25,128)
    assert result.getpixel((3,63)) == (55,28,11,128)
    assert result.getpixel((0,0)) == (0,0,0,0)
    assert result.getpixel((3,20)) == (0,0,0,0)
    assert source.getpixel((3,3)) == (100,50,20,128)
    raises(ValueError,lambda:O.state_atlas(source,(20,99),5,(2,2,18,18)))


def test_options_control_recolor_keeps_neutral_states_and_exact_native_alpha():
    source = Image.new('RGBA',(2,1))
    source.putdata([(255,80,0,127),(64,64,64,99)])
    result = O.recolor_sprite(source,(.4,.75,.95))
    assert result.getpixel((0,0)) == (102,191,242,127)
    assert result.getpixel((1,0)) == (64,64,64,99)
    assert source.getpixel((0,0)) == (255,80,0,127)


def test_options_package_retires_console_prototype_and_keeps_native_dynamic_precaches():
    native = ET.fromstring('<packagedef><model filename="ui/menus/x2m_options"/>'
        '<model filename="ui/models/m_options_controls_ps2"/>'
        '<model filename="ui/models/synth_dynamic"/></packagedef>')
    before = ET.tostring(native)
    root = ET.fromstring('<MENU igb="lc_options"><item name="synth" model="ui/models/synth_panel"/></MENU>')
    entries = {(e.tag,e.get('filename')) for e in O.options_package(root,native)}
    assert entries == {('model','ui/menus/lc_options'),('model','ui/models/synth_dynamic'),
                       ('model','ui/models/synth_panel')}
    assert ET.tostring(native) == before


def test_toggle_highlight_uses_one_resolution_row_at_native_baseline():
    # Toggle widget is 38 virtual pixels tall; its label is 21 below its origin.
    # A full-height border spans adjacent 24-pixel rows. Keep the same solid
    # selection strip used by Resolution in the bottom half of this atlas.
    source = Image.new('RGBA',(306,28),(30,100,180,255))
    result = O.toggle_highlight(source)
    assert result.size == (307,56)
    assert result.getbbox() == (0,28,307,56)
    assert result.getpixel((120,40)) == source.getpixel((120,12))
    assert result.getpixel((120,20)) == (0,0,0,0)
    assert 28*38/56 < 24
