"""Issues #96/#98 on made-up data - no game files: a world pickup (inventoryent) takes its model from the
items table; when XML2's same-named item entry ships without a model (XML2 never places it in the world) and
XML1's entry names one (XML1's zones drop it as a world pickup), the builder must fill XML1's model into the
merged entry and package it - otherwise the placed pickup renders as the engine's missing-model marker."""
import xml.etree.ElementTree as ET

from xml1build import zones as Z


def item(attrib):
    return ET.Element('item', attrib)


def test_fill_item_model_fills_when_xml2_entry_lacks_model():
    x2 = item({'name': 'GIZMO_PASS', 'type': 'item'})
    x1 = item({'name': 'GIZMO_PASS', 'type': 'item', 'model': 'props/gizmo_key'})
    stem = Z.fill_item_model(x2, x1)
    assert x2.get('model') == 'props/gizmo_key'
    assert stem == 'models/props/gizmo_key'


def test_fill_item_model_treats_empty_xml2_model_as_missing():
    x2 = item({'name': 'GIZMO_PASS', 'type': 'item', 'model': ''})
    x1 = item({'name': 'GIZMO_PASS', 'type': 'item', 'model': 'props/gizmo_key'})
    assert Z.fill_item_model(x2, x1) == 'models/props/gizmo_key'
    assert x2.get('model') == 'props/gizmo_key'


def test_fill_item_model_strips_whitespace_and_extension():
    x2 = item({'name': 'GIZMO_PASS'})
    x1 = item({'name': 'GIZMO_PASS', 'model': ' Props/Gizmo_Key.IGB '})
    assert Z.fill_item_model(x2, x1) == 'models/props/gizmo_key'
    assert x2.get('model') == 'Props/Gizmo_Key.IGB'


def test_fill_item_model_keeps_xml2_own_model():
    x2 = item({'name': 'GIZMO_COIN', 'model': 'props/gizmo_coin'})
    x1 = item({'name': 'GIZMO_COIN', 'model': 'props/gizmo_key'})
    assert Z.fill_item_model(x2, x1) is None
    assert x2.get('model') == 'props/gizmo_coin'


def test_fill_item_model_without_xml1_source_or_model():
    x2 = item({'name': 'GIZMO_PASS'})
    assert Z.fill_item_model(x2, None) is None
    assert Z.fill_item_model(x2, item({'name': 'GIZMO_PASS'})) is None
    assert Z.fill_item_model(x2, item({'name': 'GIZMO_PASS', 'model': ''})) is None
    assert x2.get('model') is None
