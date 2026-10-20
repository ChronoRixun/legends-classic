"""Synthetic localized resources and companion capability checks."""
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from xml1build import fix_ini as FI, resistance_hud as R


def resources():
    source = ET.Element('strings')
    output = ET.Element('strings')
    for pc, original in R.STRING_IDS.items():
        text = f'invented subtitle {original}'
        ET.SubElement(source, 'string', id=str(original), text=text)
        ET.SubElement(output, 'string', id=str(pc), text=text)
    colors = ET.Element('COLORS')
    for i in range(25):
        ET.SubElement(colors, 'COLOR', value=f'{i / 32} 0.2 0.3 1')
    out_colors = ET.Element('colors')
    for pc, original in R.COLOR_IDS.items():
        ET.SubElement(out_colors, 'color', id=str(pc), value=colors[original].get('value'))
    return source, colors, output, out_colors


def test_resource_pairing_detects_missing_text_and_swapped_damage_colors():
    args = resources()
    assert R.resource_problems(*args) == []
    args[2].remove(args[2][0])
    assert len(R.resource_problems(*args)) == 1
    args = resources()
    args[3][1].set('value', args[3][2].get('value'))
    assert len(R.resource_problems(*args)) == 1
    args[3][1].set('value', 'nan invalid')
    assert len(R.resource_problems(*args)) == 1


def test_port_enables_the_display_and_rejects_a_companion_that_ignores_it():
    assert 'ResistanceDisplay' not in FI.RELEASE_16_KEYS['Game']
    assert 'ResistanceDisplay' in FI.RELEASE_17_KEYS['Game']
    assert FI.game_keys()['ResistanceDisplay'] == 'xml1'
    assert 'ResistanceDisplay' not in FI.game_keys(xml1_opening=False)
    assert 'ResistanceDisplay' in FI.PORT_OWNED['Game']
    with tempfile.TemporaryDirectory() as folder:
        dll = Path(folder) / 'dinput.dll'
        dll.write_bytes(b'MZ synthetic older companion')
        try:
            FI.check_release_dll(dll, {'Game': {'ResistanceDisplay': 'xml1'}})
        except FI.FixTooOld as exc:
            assert exc.missing == ['[Game] ResistanceDisplay']
        else:
            raise AssertionError('unsupported resistance display was silently accepted')
        dll.write_bytes(b'MZ' + 'ResistanceDisplay'.encode('utf-16le'))
        FI.check_release_dll(dll, {'Game': {'ResistanceDisplay': 'xml1'}})


def test_port_requests_online_conversations_and_rejects_a_companion_that_ignores_it():
    keys = {'Game': {'OnlineConversations': 'lockstep'}}
    assert 'OnlineConversations' not in FI.RELEASE_16_KEYS['Game']
    assert 'OnlineConversations' in FI.RELEASE_17_KEYS['Game']
    assert FI.game_keys()['OnlineConversations'] == 'lockstep'
    assert 'OnlineConversations' not in FI.game_keys(xml1_opening=False)
    assert 'OnlineConversations' in FI.PORT_OWNED['Game']
    with tempfile.TemporaryDirectory() as folder:
        dll = Path(folder) / 'dinput.dll'
        dll.write_bytes(b'MZ synthetic older companion' + 'ResistanceDisplay'.encode('utf-16le'))
        try:
            FI.check_release_dll(dll, keys)
        except FI.FixTooOld as exc:
            assert exc.missing == ['[Game] OnlineConversations']
        else:
            raise AssertionError('a companion without the online conversation rule was silently accepted')
        dll.write_bytes(b'MZ' + 'OnlineConversations'.encode('utf-16le'))
        FI.check_release_dll(dll, keys)


def test_port_requests_the_personal_item_picture_window_and_rejects_a_companion_that_ignores_it():
    keys = {'Game': {'PersonalItemPicture': 'window'}}
    assert 'PersonalItemPicture' not in FI.RELEASE_16_KEYS['Game']
    assert 'PersonalItemPicture' in FI.RELEASE_17_KEYS['Game']
    assert FI.game_keys()['PersonalItemPicture'] == 'window'
    assert 'PersonalItemPicture' not in FI.game_keys(xml1_opening=False)
    assert 'PersonalItemPicture' in FI.PORT_OWNED['Game']
    with tempfile.TemporaryDirectory() as folder:
        dll = Path(folder) / 'dinput.dll'
        dll.write_bytes(b'MZ synthetic older companion' + 'ResistanceDisplay'.encode('utf-16le'))
        try:
            FI.check_release_dll(dll, keys)
        except FI.FixTooOld as exc:
            assert exc.missing == ['[Game] PersonalItemPicture']
        else:
            raise AssertionError('a companion without the picture window was silently accepted')
        dll.write_bytes(b'MZ' + 'PersonalItemPicture'.encode('utf-16le'))
        FI.check_release_dll(dll, keys)
