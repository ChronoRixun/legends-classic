"""Synthetic regressions for the first game's bedroom items (issue #47)."""
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from xml1build import common as C
from xml1build import frontend as F
from xml1build import personal_art as PA
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

    def write_bytes(rel, data, source=None, replace=False, shared=False):
        writes[rel] = data
        return rel

    def x1_path(rel):
        return SimpleNamespace(read_bytes=lambda: b'invented-igb:' + rel.encode('latin-1'))

    def import_x1_asset(rel, out_rel_noext=None):
        imports.append((rel, out_rel_noext))
        return SimpleNamespace(status='written')

    ctx = SimpleNamespace(
        x1_rels=lambda prefix: sorted(list(ITEMS) + ['data/personal/inventedhero01.fre',
                                                     'data/personal/sub/ignored.eng']),
        read_x1_xml=read, x1_schema=lambda root, rel: {}, write_xmlb=write_xmlb,
        registry=SimpleNamespace(get=lambda rel: None),
        base_index=SimpleNamespace(find=lambda rel, exts: None),
        x1_path=x1_path, write_bytes=write_bytes,
        import_x1_asset=import_x1_asset)
    return ctx, writes, imports


class swap:
    """set attribute, restore on exit (run.py has no monkeypatch fixture)."""
    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value
    def __enter__(self):
        self.old = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.value)
    def __exit__(self, *exc):
        setattr(self.obj, self.name, self.old)


def fake_recompose(data=b'framed-512x384'):
    return swap(PA, 'recompose_igb', lambda raw: (data + b':' + raw, {'levels': [(512, 384)]}))


def test_every_item_is_written_with_escaped_text_and_its_texture_imported():
    with fake_recompose():
        ctx, writes, imports = x1_ctx()
        rep = F.write_personal_items(ctx)
    assert rep['items'] == ['inventedhero01', 'inventedhero02'] and not rep['problems']
    assert sorted(writes) == ['Data/personal/inventedhero01.XMLB', 'Data/personal/inventedhero01.engb',
                              'Data/personal/inventedhero02.XMLB', 'Data/personal/inventedhero02.engb',
                              'textures/personal/inv_1.igb', 'textures/personal/inv_2.igb']
    first = ET.fromstring(writes['Data/personal/inventedhero01.engb'])
    assert first.get('text') == 'An invented photo, |#1 of 2.'      # '#' would move the pen
    assert first.get('texture') == 'textures/personal/inv_1.png'     # the engine resolves the IGB itself
    assert imports == []                                             # the byte copy is only the fallback
    assert writes['textures/personal/inv_1.igb'] == b'framed-512x384:invented-igb:textures/personal/inv_1.igb'
    assert rep['textures'] == {'written': 2}


def test_a_texture_that_cannot_be_reframed_falls_back_to_the_byte_copy_and_is_reported():
    def fail(raw):
        raise PA.G.IgbError('invented unreadable layout')
    with swap(PA, 'recompose_igb', fail):
        ctx, writes, imports = x1_ctx()
        rep = F.write_personal_items(ctx)
    assert rep['problems'] and all('_unframed' in p for p in rep['problems'])
    assert imports == [('textures/personal/inv_1.igb', 'textures/personal/inv_1'),
                       ('textures/personal/inv_2.igb', 'textures/personal/inv_2')]
    assert rep['textures'] == {'written_unframed': 2}


def test_personal_art_compose_places_the_art_in_the_window_over_a_soft_backdrop():
    w, h = 512, 256
    art = [((255, 0, 0) if x < w // 2 else (0, 0, 255)) for y in range(h) for x in range(w)]
    canvas = PA.compose(art, w, h)
    W, H = PA.SCREEN
    assert len(canvas) == W * H
    win = PA.WINDOW
    left = canvas[(win[1] + win[3]) // 2 * W + win[0] + 16]
    right = canvas[(win[1] + win[3]) // 2 * W + win[2] - 16]
    assert left[0] > 200 and left[2] < 55              # the window shows the art: red on the left
    assert right[2] > 200 and right[0] < 55            # ... blue on the right
    above = canvas[(win[1] - 24) * W + W // 2]         # the backdrop is the smoothed seam (purple, not red/blue)
    assert 60 < above[0] < 200 and 60 < above[2] < 200


def test_personal_art_dxt_roundtrip_keeps_solid_and_two_tone_blocks():
    solid = [(200, 40, 8)] * 16
    out = PA.dxt_decode(PA.dxt_encode(solid, 4, 4), 4, 4)
    assert all(max(abs(a - b) for a, b in zip(p, (200, 40, 8))) <= 8 for p in out)
    two = [(255, 255, 255)] * 8 + [(0, 0, 0)] * 8
    out = PA.dxt_decode(PA.dxt_encode(two, 4, 4), 4, 4)
    assert all(p == (255, 255, 255) for p in out[:8]) and all(p == (0, 0, 0) for p in out[8:])
    odd = [(9, 99, 199)] * (6 * 2)                     # not a multiple of 4: edge-clamped blocks
    assert len(PA.dxt_encode(odd, 6, 2)) == 2 * 16


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


def test_validator_flags_a_texture_that_is_not_reframed():
    with tempfile.TemporaryDirectory() as temp:
        good = {'maps/invented/bedrooms.engb': zone_with_item(), 'Data/personal/inventedhero01.XMLB': item(),
                'Data/personal/inventedhero01.engb': item(), 'Textures/personal/inv_1.IGB': 'igb'}
        owners = {'Data/personal/inventedhero01.XMLB': 'frontend', 'Data/personal/inventedhero01.engb': 'frontend'}
        with swap(VF, '_personal_texture_size', lambda v, rel: (512, 384)):
            assert not validator(Path(temp), good, owners).errors
        with swap(VF, '_personal_texture_size', lambda v, rel: (512, 256)):
            errs = validator(Path(temp), good, owners).errors
        assert len(errs) == 1 and '512x384' in errs[0] and '512x256' in errs[0]
