"""P1 `disc` end to end on a synthetic X-Men Legends disc (BUILDER_DESIGN.md 6.1): identification, the three trees,
fb_unpack's rules (Windows glob order, first bundle wins, lower-case names, CRLF manifest), the cache key."""

import json
import tempfile
from pathlib import Path

import synth
from xml1build.prepare import PrepareError, disc as P1, image


def _image(files, tmp, name='xml1.iso'):
    p = Path(tmp) / name
    p.write_bytes(synth.xdvdfs(files))                   # an XISO (partition at offset 0)
    return p


def _files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}


def test_p1_trees_and_rules():
    with tempfile.TemporaryDirectory() as td:
        iso = _image(synth.xml1_disc_files(), td)
        r = P1.run(iso, Path(td) / 'cache', log=lambda m: None)
        d = r['dir']
        assert not r['cached'] and d.name == 'disc' and (d / 'stage.json').is_file()
        st = r['stage']
        assert st['identity']['format'] == 'xiso' and st['identity']['xbe']['title'] == 'X-Men Legends'
        xbox = _files(d / 'xbox')
        assert sorted(xbox) == ['default.xbe', 'movies/ntsc/i/1/i101.sfd', 'sounds/zsds/a/c/aco_m.zsm']
        assets = _files(d / 'assets')
        assert sorted(assets) == ['data/colors.xml', 'scripts/menus/start.py']      # no .fb bundles
        assert (d / 'assets' / 'textures').is_dir()                                  # the zip's folder entry
        loose = _files(d / 'loose')
        # Windows glob order: dr_mag2/y.fb before dr_mag/x.fb, so y's data/shared.xml (<b/>) wins over x's (<c/>);
        # characters/c_0001.fb sorts first of all and its '/Data/Shared.XML' (<a/>) wins over both
        assert loose['data/shared.xml'] == b'<a/>'
        assert loose['actors/0001.igb'] == b'skin one' and loose['on'] == b'' and loose['maps/x/y.eng'] == b'<world/>'
        man_bytes = loose.pop(P1.MANIFEST)
        assert b'\r\n' in man_bytes and b'\n' not in man_bytes.replace(b'\r\n', b'')
        man = json.loads(man_bytes)
        assert list(man) == ['packages/generated/characters/c_0001.fb', 'packages/generated/maps/a/dr_mag2/y.fb',
                             'packages/generated/maps/a/dr_mag/x.fb']
        assert man['packages/generated/characters/c_0001.fb'][1] == ['data/shared.xml', 'xml']
        assert st['counts']['conflicting_duplicates'] == 2 and st['counts']['identical_duplicates'] == 1
        assert st['conflicts'] == [['data/shared.xml', 'packages/generated/maps/a/dr_mag2/y.fb'],
                                   ['data/shared.xml', 'packages/generated/maps/a/dr_mag/x.fb']]
        movies = json.loads((d / 'movies.json').read_text())
        assert [m['name'] for m in movies] == ['i101'] and movies[0]['path'] == 'movies/ntsc/i/1/i101.sfd'
        # cached while the key matches; the same content in a Redump layout has the same key
        again = P1.run(iso, Path(td) / 'cache', log=lambda m: None)
        assert again['cached'] and again['dir'] == d
        redump = synth.ZeroPrefixed(synth.xdvdfs(synth.xml1_disc_files()), synth.XGD1)
        with image.XdvdfsImage(redump) as img:
            ident = P1.identify(img)
            assert img.format == 'redump-xgd1' and P1.stage_key(ident) == st['key']
        assert P1.find_published(Path(td) / 'cache') == [d]
        # other content -> another disc id / key
        iso2 = _image(synth.xml1_disc_files(extra_zip={'data/new.xml': b'<n/>'}), td, 'other.iso')
        with image.open_image(iso2) as img:
            assert P1.stage_key(P1.identify(img)) != st['key']


def _code(files, tmp, name):
    iso = _image(files, tmp, name)
    try:
        P1.run(iso, Path(tmp) / 'cache', log=lambda m: None)
    except PrepareError as e:
        return e.code, e.detail
    return None, None


def test_p1_identification_errors():
    with tempfile.TemporaryDirectory() as td:
        code, detail = _code(synth.xml1_disc_files(title_id=0x4D530004), td, 'wrong.iso')
        assert code == 'E_ISO_WRONG_GAME' and detail['title_id'] == '0x4D530004'
        code, detail = _code(synth.xml1_disc_files(drop=('sounds/',)), td, 'nosound.iso')
        assert code == 'E_ISO_INCOMPLETE' and detail['missing'] == ['sounds/zsds/']
        code, detail = _code(synth.xml1_disc_files(drop=('movies/ntsc',)), td, 'nomovie.iso')
        assert code == 'E_ISO_INCOMPLETE' and detail['missing'] == ['movies/ntsc/*.sfd']
        code, _ = _code(synth.xml1_disc_files(drop=('default.xbe',)), td, 'noxbe.iso')
        assert code == 'E_ISO_WRONG_GAME'
        # a zip member escaping the tree, and a damaged member (CRC) are read errors
        code, _ = _code(synth.xml1_disc_files(extra_zip={'../evil.txt': b'x'}), td, 'evil.iso')
        assert code == 'E_ISO_READ'
        for n, member in enumerate(('data/colors.xml', 'packages/generated/maps/a/dr_mag/x.fb')):
            files = synth.xml1_disc_files()
            z = bytearray(files['z/assetsfb.zip'])
            i = z.find(b'PK\x03\x04')
            while z[i + 30:i + 30 + len(member)] != member.encode():     # the member's local header
                i = z.find(b'PK\x03\x04', i + 4)
            data_at = i + 30 + int.from_bytes(z[i + 26:i + 28], 'little') + int.from_bytes(z[i + 28:i + 30], 'little')
            z[data_at + 1] ^= 0x5A                                       # damage its compressed data
            files['z/assetsfb.zip'] = bytes(z)
            code, _ = _code(files, td, f'crc{n}.iso')
            assert code == 'E_ISO_READ', (member, code)
        # nothing half-written is published
        assert all(p.name != 'disc' for p in (Path(td) / 'cache').rglob('disc'))


def test_p1_expected_one_sided_rules():
    rules = P1.expected_one_sided()
    xbox = ['z/assetsfb.zip', 'movies/pal/i/1/i101.sfd', 'media/dsstdfx.bin', 'OptionsImage.xpr', 'build.ini',
            'alchemy.ini', 'sounds/badaudio.wav']
    assert all(any(fn(r) for fn, _ in rules['xml1_xbox']) for r in xbox)
    assert not any(fn('sounds/zsds/a/c/aco_m.zsm') for fn, _ in rules['xml1_xbox'])
    assert any(fn('packages/generated/maps/x.fb') for fn, _ in rules['xml1_assets'])
    assert not any(fn('data/colors.xml') for fn, _ in rules['xml1_assets'])
