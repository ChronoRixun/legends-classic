"""Synthetic modal bounds and shared style contracts, independent of message text."""
import xml.etree.ElementTree as ET

from xml1build import dialog_appearance as D, menu_conversion as M, menu_theme as T
from xml1build.igb_file import IgbFile
from test_menu_conversion import flat_panel
from test_main_appearance import palette


def dialog_fixture():
    colors,styles,_ = T.allocate(ET.Element('colors'),ET.Element('styles'),palette(),(
        T.text_style('STYLE_NORMAL'),T.text_style('STYLE_MENU',normal=1,focus=4,allow=True)))
    data,_ = M.fit_flat_panel(flat_panel((0,0,1,0,0,1,1,1)),D.RECT,border=10)
    return colors,styles,data


def test_shared_modal_validator_rejects_frame_drift_without_changing_native_content_rect():
    colors,styles,data = dialog_fixture()
    assert not D.problems(colors,styles,data)
    graph = IgbFile(data)
    array = graph.objects_of('igVertexArray1_1')[0]
    ref = graph.ref_list(array.get(2))[0]
    vertices = graph.block_floats(ref)
    vertices[0] -= 1
    graph.set_block_floats(ref,vertices)
    assert any('bounds drift' in p for p in D.problems(colors,styles,graph.edited()))


def test_shared_modal_validator_keeps_pc_font_indices_and_modern_colour_bindings():
    colors,styles,data = dialog_fixture()
    styles.find("style[@name='STYLE_MENU']").set('color_focus','999')
    styles.find("style[@name='STYLE_NORMAL']").set('font','synth_console_only')
    errors = D.problems(colors,styles,data)
    assert any('STYLE_MENU' in p for p in errors)
    assert any('STYLE_NORMAL' in p for p in errors)
