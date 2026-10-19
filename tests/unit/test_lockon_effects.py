import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import harness
from xml1build import common as C, fix_ini as F, lockon_effects as L
from xml1build.validate import Check


def fixture(out, values=('invented/scan', 'invented/contact', 'invented/marked'), name='invented'):
    root = ET.Element('PowerStyle')
    move = ET.SubElement(root, 'FightMove', name='search', handler='ch_lockon')
    for value in values:
        ET.SubElement(move, 'trigger', name='effect', time='-1', effect=value)
    style = out / 'Data/powerstyles' / (name + '.xmlb')
    style.parent.mkdir(parents=True, exist_ok=True)
    style.write_bytes(C.encode_xmlb(root))
    for value in values:
        effect = out / 'Effects' / (value + '.XMLB')
        effect.parent.mkdir(parents=True, exist_ok=True)
        effect.write_bytes(C.encode_xmlb(ET.Element('Effect', looptime='0.1')))
    return style


def test_lockon_paths_preserve_roles_and_require_assets():
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        assert L.keys(out) == {}
        fixture(out)
        assert F.build_lockon_effects(out) == {L.KEY: 'invented/scan,invented/contact,invented/marked', L.AIM_KEY: '1'}
        (out / 'Effects/invented/contact.XMLB').unlink()
        ck = Check('V62', 'lock-on effects')
        L.validate(type('Context', (), {'out': out})(), ck)
        assert L.inspect(out)[1] == ['lock-on effect missing or empty: invented/contact']
        try:
            L.keys(out)
        except ValueError as exc:
            assert 'invented/contact' in str(exc)
        else:
            assert False, 'missing visual dependency was accepted'


def test_lockon_rejects_ambiguous_or_malformed_contract():
    for values in [('invented/scan',), ('invented/scan', 'invented/contact', 'invented/marked', 'invented/extra')]:
        with tempfile.TemporaryDirectory() as temp:
            fixture(Path(temp), values)
            assert L.inspect(temp)[1]
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        fixture(out)
        fixture(out, ('other/scan', 'other/contact', 'other/marked'), 'other')
        assert 'disagree' in L.inspect(out)[1][0]
    root = ET.fromstring('<PowerStyle><FightMove name="search" handler="ch_lockon">'
                         '<trigger name="effect" time="-1" effect="../escape"/>'
                         '<trigger name="effect" time="-1" effect="valid/contact"/>'
                         '<trigger name="effect" time="-1" effect="valid/marked"/>'
                         '</FightMove></PowerStyle>')
    assert L.paths(root) == (set(), ['search'])


def test_lockon_harness_scope_and_companion_check():
    keys = {L.KEY: 'invented/scan,invented/contact,invented/marked', L.AIM_KEY: '1'}
    assert L.KEY in F.PORT_OWNED['Game']
    assert L.KEY in harness.ini_text('windowed', 1280, 720, True, port_identity=True, lockon_effects=keys)
    assert L.KEY not in harness.ini_text('windowed', 1280, 720, True, lockon_effects=keys)
    assert L.KEY not in harness.ini_text('windowed', 1280, 720, True, xml1_opening=False,
                                        port_identity=True, lockon_effects=keys)
    with tempfile.TemporaryDirectory() as temp:
        dll = Path(temp) / 'synthetic.dll'
        dll.write_bytes(b'invented old companion')
        assert F.old_fix_keys(dll, {'Game': keys}) == ['[Game] ' + L.KEY, '[Game] ' + L.AIM_KEY]
        dll.write_bytes((L.KEY + L.AIM_KEY).encode('utf-16le'))
        assert not F.old_fix_keys(dll, {'Game': keys})
