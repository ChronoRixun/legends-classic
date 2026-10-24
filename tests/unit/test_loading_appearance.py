"""Synthetic loading-service and camera selection contracts."""
import copy
import struct
import xml.etree.ElementTree as ET
from types import SimpleNamespace

from xml1build import loading_appearance as L
from xml1build import validate_frontend as V
from xml1build.validate import Check
from xml1build.igb_file import IgbFile, IgbError
from test_main_appearance import fixture, raises


def camera_scene(count=1):
    fields = [(2, 'i'), (3, 'i'), (4, 'b')]
    specs = [('igDataList', None, fields), ('igGraphPathList', 'igDataList', fields),
             ('igSceneInfo', None, [(7, 'r')]), ('igGraphPath', None, [(2, 'r')])]
    objects = [('igSceneInfo', {7: 1}), ('igGraphPathList', {2: count, 3: count, 4: 3}),
               ('igGraphPath', {2: -1})]
    return fixture(specs, objects, (struct.pack('<i', 2),))


def test_loading_camera_selection_preserves_original_graph_and_references():
    source = camera_scene()
    result = IgbFile(L.retire_camera(source))
    assert result.obj(1).get(2) == 0 and result.obj(1).get(4) == -1
    assert result.obj(2).name == 'igGraphPath' and result.obj(2).get(2) == -1
    assert result.ref_list(3) == [2] and len(result.data) == len(source)
    raises(IgbError, lambda: L.retire_camera(camera_scene(0)))
    raises(IgbError, lambda: L.retire_camera(camera_scene(2)))


def test_loading_skin_keeps_native_no_stack_class_and_precache_lifecycle():
    native = ET.fromstring('<MENU igb="synth_native" type="LOADING_MENU" no_stack="true">'
                           '<precache type="xml_resident" filename="data/synth"/>'
                           '<items file="synth_helper" igb="synth_back"/></MENU>')
    before = ET.tostring(native)
    result = L.loading_tree(native)
    assert result.get('type') == 'LOADING_MENU' and result.get('no_stack') == 'true'
    assert ET.tostring(result[0]) == ET.tostring(native[0])
    assert ET.tostring(result[1]) == ET.tostring(native[1])
    assert result.find("item[@name='loadstatus']").get('gamevar') == 'loadstatus'
    assert ET.tostring(native) == before


def test_loading_validator_rejects_wrong_service_and_missing_dynamic_status():
    matrix = [float(i in (0, 5, 10, 15)) for i in range(16)]
    matrix[12:15] = [53, -880, 27]
    scene = fixture([('igTransform', None, [(2, 's'), (8, 'm'), (11, 'r')]),
                     ('igHashedUserInfo', None, [(2, 's'), (3, 'r')]),
                     ('igAABox', None, [(2, 'v'), (3, 'v')])], [
        ('igTransform', {2: 'loadstatus', 8: matrix, 11: -1}),
        ('igHashedUserInfo', {2: 'loadstatus', 3: 2}),
        ('igAABox', {2: [0, 0, -8], 3: [400, 0, 8]})])
    root = L.loading_tree(ET.Element('MENU', type='LOADING_MENU', no_stack='true'))
    validator = SimpleNamespace(ctx=SimpleNamespace(opt=lambda k: 'xml1'),
                                tree=lambda rel: root, read=lambda rel: scene)
    ck = Check('V-TBD-loading', 'synth loading')
    V.v_classic_loading(validator, ck)
    assert not ck.errors, ck.errors
    root.set('type', 'IMAGE_VIEWER_MENU')
    root.find('item').attrib.pop('gamevar')
    ck = Check('V-TBD-loading', 'synth loading')
    V.v_classic_loading(validator, ck)
    assert any('class/lifecycle' in p for p in ck.errors)
    assert any('status field' in p for p in ck.errors)
