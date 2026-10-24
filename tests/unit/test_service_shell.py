"""Invented service definitions protect economy, gates and native input ownership."""
import xml.etree.ElementTree as ET

from xml1build import service_shell as H
from xml1build.igb_file import IgbError
from test_main_appearance import fixture, raises


def native():
    return ET.fromstring('<MENU type="SYNTHETIC_SERVICE" gamepause="false" all_controllers="true" '
        'desctext1="$MENU_OK Choose"><item name="list" type="MENU_ITEM_LISTBOX" mode="1" '
        'usecmd="synthetic_purchase" gamevar="synthetic_stock" enabled="true" price="31" '
        'startactive="true" style="SYNTHETIC"><onfocus type="list_focus" '
        'model="ui/models/synthetic_select" loop="1"/></item>'
        '<item name="hinge" type="MENU_ITEM_MODEL" model="ui/models/synthetic_hinge"/></MENU>')


def test_service_shell_keeps_economy_and_permission_attributes_and_event_callbacks():
    source = native()
    before = ET.tostring(source)
    root = H.tree(source, 'synthetic_classic',
                  {'ui/models/synthetic_select': 'ui/models/synthetic_classic_select'}, ('hinge',), ('list',))
    assert ET.tostring(source) == before
    assert not H.control_problems(source, root, ('hinge',))
    assert root.find("item[@name='hinge']").get('hide') == 'true'
    assert root.find("item[@name='list']/onfocus").get('model') == 'ui/models/synthetic_classic_select'


def test_service_contract_rejects_price_stock_gate_and_callback_changes():
    source = native()
    for key, value in [('price', '30'), ('gamevar', 'other_stock'), ('enabled', 'false'),
                       ('usecmd', 'other_purchase'), ('mode', '0')]:
        root = H.tree(source, 'synthetic_classic', {}, ('hinge',))
        root.find("item[@name='list']").set(key, value)
        assert H.control_problems(source, root, ('hinge',))
    root = H.tree(source, 'synthetic_classic', {}, ('hinge',))
    root.find("item[@name='list']/onfocus").set('type', 'other_callback')
    assert H.control_problems(source, root, ('hinge',))


def test_missing_root_bound_unions_only_transform_free_model_boxes():
    schemas = [('igSceneInfo', None, [(5, 'r')]),
               ('igGroup', None, [(3, 'r')]),
               ('igAABox', None, [(2, 'v'), (3, 'v')]),
               ('igTransform', None, [(2, 's')])]
    objects = [('igSceneInfo', {5: 1}), ('igGroup', {3: -1}),
               ('igAABox', {2: [-40, -2, -12], 3: [35, 1, 10]}),
               ('igAABox', {2: [-45, -4, -10], 3: [40, 0, 12]})]
    assert H.model_rectangle(fixture(schemas, objects)) == (-45, -12, 40, 12)
    objects.append(('igTransform', {2: 'synthetic_offset'}))
    raises(IgbError, lambda: H.model_rectangle(fixture(schemas, objects)))


def test_service_frame_keeps_native_depth_behind_inventory_counters():
    from types import SimpleNamespace
    from test_menu_conversion import flat_panel
    from xml1build.igb_file import IgbFile
    native = fixture([('igSceneInfo', None, [(5, 'r')]), ('igGroup', None, [(3, 'r')]),
                      ('igAABox', None, [(2, 'v'), (3, 'v')])],
                     [('igSceneInfo', {5: 1}), ('igGroup', {3: 2}),
                      ('igAABox', {2: [-50, -8, -20], 3: [50, 0, 20]})])
    source = IgbFile(flat_panel((0, 0, 1, 0, 0, 1, 1, 1)))
    positions = source.block_floats(3)
    positions[1::3] = [-18] * 4
    source.set_block_floats(3, positions)
    for slot in (2, 3):
        source.set_floats(source.obj(1), slot, [-18], 1)
    writes = []
    ctx = SimpleNamespace(base_index=SimpleNamespace(path=lambda rel: SimpleNamespace(read_bytes=lambda: native)),
                          write_bytes=lambda rel, data, **kw: writes.append(data))
    H.frame(ctx, source.edited(), 'ui/models/synthetic', 'ui/models/synthetic_classic')
    result = IgbFile(writes[0])
    depths = result.block_floats(3)[1::3]
    assert depths == [-4] * 4
    assert min(depths)-2 > -12  # Inventory frame anchor -2, native counter text -12.
    assert H.frame_problems(source.edited(), (0, 0, 100, 100), depth=(-8, 0))
    assert not H.frame_problems(writes[0], (-50, -20, 50, 20), depth=(-8, 0))
