"""Synthetic regressions for the first game's bedroom items (issue #47)."""
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from xml1build import common as C
from xml1build import frontend as F
from xml1build import validate_frontend as VF
from xml1build.validate import Check

ITEMS = {
    'data/personal/inventedhero01.eng': ('textures/personal/inv_1.png', 'An invented photo, #1 of 2.'),
    'data/personal/inventedhero02.eng': ('textures/personal/inv_2.png', 'Another invented keepsake.'),
}


def x1_ctx():
    writes, imports = {}, []

    def read(rel):
        tex, text = ITEMS[rel]
        return ET.Element('ITEM', {'text': text, 'texture': tex})

    def write_xmlb(rel_noext, root, exts, source=None):
        for e in exts:
            writes[rel_noext + e] = ET.tostring(root)
        return [rel_noext + e for e in exts]

    def import_x1_asset(rel, out_rel_noext=None):
        imports.append((rel, out_rel_noext))
        return SimpleNamespace(status='written')

    ctx = SimpleNamespace(
        x1_rels=lambda prefix: sorted(list(ITEMS) + ['data/personal/inventedhero01.fre',
                                                     'data/personal/sub/ignored.eng']),
        read_x1_xml=read, x1_schema=lambda root, rel: {}, write_xmlb=write_xmlb,
        registry=SimpleNamespace(get=lambda rel: None),
        base_index=SimpleNamespace(find=lambda rel, exts: None),
        import_x1_asset=import_x1_asset)
    return ctx, writes, imports


def test_every_item_is_written_with_escaped_text_and_its_texture_imported():
    ctx, writes, imports = x1_ctx()
    rep = F.write_personal_items(ctx)
    assert rep['items'] == ['inventedhero01', 'inventedhero02'] and not rep['problems']
    assert sorted(writes) == ['Data/personal/inventedhero01.XMLB', 'Data/personal/inventedhero01.engb',
                              'Data/personal/inventedhero02.XMLB', 'Data/personal/inventedhero02.engb']
    first = ET.fromstring(writes['Data/personal/inventedhero01.engb'])
    assert first.get('text') == 'An invented photo, |#1 of 2.'      # '#' would move the pen
    assert first.get('texture') == 'textures/personal/inv_1.png'     # the engine resolves the IGB itself
    assert imports == [('textures/personal/inv_1.igb', 'textures/personal/inv_1'),
                       ('textures/personal/inv_2.igb', 'textures/personal/inv_2')]
    assert rep['textures'] == {'written': 2}


def test_texture_value_forms():
    assert F.personal_texture_rel('textures/personal/inv_1.png') == 'textures/personal/inv_1'
    assert F.personal_texture_rel('Textures\\Personal\\INV_2') == 'textures/personal/inv_2'
    assert F.personal_texture_rel('') is None


def validator(folder, files, owners):
    """files: rel -> Element or script text."""
    v = SimpleNamespace(reg={}, ctx=None)
    paths = {}
    for rel, content in files.items():
        p = folder / rel.replace('/', '_')
        p.write_bytes(content.encode('latin-1') if isinstance(content, str) else C.encode_xmlb(content))
        n = C.norm(rel)
        paths[n] = p
        v.reg[n] = {'rel': rel, 'owner': owners.get(rel, 'zones')}
    v.idx = SimpleNamespace(path=lambda n: paths.get(C.norm(n)))
    v.tree = lambda rel: C.decode_xmlb(paths[C.norm(rel)].read_bytes()) if C.norm(rel) in paths else None
    v.entry = lambda rel: v.reg.get(C.norm(rel))
    v.exists = lambda rel: C.norm(rel) in paths
    ck = Check('V30', 'personal items')
    VF.v_personal_items(v, ck)
    return ck


def zone_with_item():
    w = ET.Element('world')
    ET.SubElement(w, 'entity', {'name': 'trigger_use01', 'actscript': "personalItem('inventedhero01')"})
    return w


def item(text='Invented.', tex='textures/personal/inv_1.png'):
    return ET.Element('ITEM', {'text': text, 'texture': tex})


def test_validator_accepts_converted_items_and_rejects_each_gap():
    with tempfile.TemporaryDirectory() as temp:
        good = {'maps/invented/bedrooms.engb': zone_with_item(), 'Data/personal/inventedhero01.XMLB': item(),
                'Data/personal/inventedhero01.engb': item(), 'Textures/personal/inv_1.IGB': 'igb'}
        owners = {'Data/personal/inventedhero01.XMLB': 'frontend', 'Data/personal/inventedhero01.engb': 'frontend'}
        ok = validator(Path(temp), good, owners)
        assert not ok.errors and ok.counts == {'personal_items': 1, 'personal_items_ok': 1}
    cases = [
        (lambda f: f.pop('Data/personal/inventedhero01.engb'), 'missing'),          # the loading-screen bug
        (lambda f: f.pop('Textures/personal/inv_1.IGB'), 'default texture'),        # the two-colour bug
        (lambda f: f.update({'Data/personal/inventedhero01.engb': item(text='')}), 'no text'),
        (lambda f: f.update({'Data/personal/inventedhero01.engb': item(text='#1 raw')}), 'unescaped'),
    ]
    for change, word in cases:
        with tempfile.TemporaryDirectory() as temp:
            files = dict(good)
            change(files)
            errs = validator(Path(temp), files, owners).errors
            assert len(errs) == 1 and word in errs[0], (word, errs)
    with tempfile.TemporaryDirectory() as temp:                                        # XML2's leftover file
        errs = validator(Path(temp), good, {}).errors
        assert len(errs) == 2 and all('not the first game' in e for e in errs)
    with tempfile.TemporaryDirectory() as temp:                                        # a script literal counts too
        files = {'Scripts/invented/room.py': "personalItem('inventedhero02')\r\n"}
        errs = validator(Path(temp), files, {}).errors
        assert len(errs) == 2 and 'inventedhero02' in errs[0]
