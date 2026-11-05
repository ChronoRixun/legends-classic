"""Verified extracted originals, using invented bytes only; no loose overlay is an input."""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import synth
from xml1build.prepare import PrepareError, disc, image
from xml1builder import commands, inputs
from xml1builder.errors import BuilderError


def originals():
    files = synth.xml1_disc_files()
    return {k: v for k, v in files.items() if k in ('default.xbe', 'z/assetsfb.zip')
            or k.startswith(('sounds/zsds/', 'movies/ntsc/'))}


@contextlib.contextmanager
def fixture():
    files = originals()
    ref = {'id': 'synthetic-world', 'files': {
        k: [len(v), hashlib.sha256(v).hexdigest()] for k, v in files.items()}}
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'install'
        root.mkdir()
        for rel, body in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)
        from xml1build.prepare import folder
        with patch.object(folder, 'references', return_value=[ref]):
            yield Path(td), root, files, ref


def refused(code, fn, *args, file=None, **kwargs):
    try:
        fn(*args, **kwargs)
    except (PrepareError, BuilderError) as e:
        assert e.code == code, (e.code, str(e))
        if file:
            assert file in str(e) and e.detail['file'] == file, (str(e), e.detail)
        return e
    raise AssertionError(f'expected {code}')


def tree_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_folder_verified_info_and_case_insensitive_reads():
    with fixture() as (_td, root, files, _ref):
        (root / 'default.xbe').rename(root / 'DEFAULT.XBE')
        ident, info = inputs.identify(root)
        assert info['format'] == 'folder' and info['verified'] is True
        assert info['verified_files'] == len(files) and info['dump'] == 'synthetic-world'
        with image.open_image(root) as img:
            assert img.read_file('DEFAULT.XBE') == files['default.xbe']
            assert img.get('sounds').is_dir
            assert {e.path: img.read_file(e.path) for e in img.entries.values() if not e.is_dir} == files
            assert img.listing() == sorted(img.listing())
        assert ident['source_snapshot']


def test_folder_refuses_altered_original_even_when_size_is_unchanged():
    with fixture() as (_td, root, files, _ref):
        rel = next(k for k in files if k.startswith('sounds/'))
        (root / rel).write_bytes(b'?' * len(files[rel]))
        e = refused('E_ISO_FOLDER_MODIFIED', inputs.identify, root, file=rel)
        assert e.exit_code == 3


def test_folder_refuses_missing_original_and_unknown_xbe():
    with fixture() as (_td, root, files, _ref):
        rel = next(k for k in files if k.startswith('movies/'))
        (root / rel).unlink()
        refused('E_ISO_FOLDER_MISSING', inputs.identify, root, file=rel)
    with fixture() as (_td, root, files, _ref):
        (root / 'default.xbe').write_bytes(b'?' * len(files['default.xbe']))
        refused('E_ISO_FOLDER_MODIFIED', inputs.identify, root, file='default.xbe')


def test_folder_overlay_never_enters_reader_or_extracted_output():
    with fixture() as (td, root, files, _ref):
        for rel in ('data/colors.xml', 'loose/data/colors.xml', 'UDATA/player.dat', 'pc-settings.ini',
                    'sounds/zsds/extra.bin', 'movies/ntsc/extra.sfd'):
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'overlay only')
        (root / '.xml1-player-layout').write_text('synthetic layout')
        before = tree_bytes(root)
        _ident, info = inputs.identify(root)
        assert info['recomp_layout'] is True
        with image.open_image(root) as img:
            assert img.get('data/colors.xml') is None
            assert img.get('sounds/zsds/extra.bin') is None
        r = disc.run(root, td / 'cache', log=lambda *_: None)
        assert (r['dir'] / 'assets/data/colors.xml').read_bytes() == b'<colors/>'
        assert not (r['dir'] / 'xbox/sounds/zsds/extra.bin').exists()
        assert tree_bytes(root) == before


def test_folder_and_iso_extract_identical_consumed_bytes_with_separate_caches():
    with fixture() as (td, root, files, _ref):
        iso = td / 'fixture.iso'
        iso.write_bytes(synth.xdvdfs(files))
        a = disc.run(iso, td / 'cache', log=lambda *_: None)
        b = disc.run(root, td / 'cache', log=lambda *_: None)
        assert a['dir'] != b['dir'] and a['stage']['key'] != b['stage']['key']
        aa, bb = tree_bytes(a['dir']), tree_bytes(b['dir'])
        aa.pop('stage.json')
        bb.pop('stage.json')
        assert aa == bb
        assert disc.run(root, td / 'cache', log=lambda *_: None)['cached']
        assert inputs.disc_digest(a['stage']['identity']) != inputs.disc_digest(b['stage']['identity'])


def test_folder_cannot_reuse_cache_after_an_original_changes():
    with fixture() as (td, root, files, _ref):
        disc.run(root, td / 'cache', log=lambda *_: None)
        rel = next(k for k in files if k.startswith('sounds/'))
        (root / rel).write_bytes(b'?' * len(files[rel]))
        refused('E_ISO_FOLDER_MODIFIED', disc.run, root, td / 'cache', log=lambda *_: None, file=rel)


def test_folder_detects_change_after_probe_and_on_open_handle():
    with fixture() as (_td, root, files, _ref):
        ident, _info = inputs.identify(root)
        rel = next(k for k in files if k.startswith('sounds/'))
        img = image.open_image(root)
        try:
            with img.open_file(rel) as fh:
                try:
                    (root / rel).write_bytes(b'?' * len(files[rel]))
                except PermissionError:
                    assert os.name == 'nt' and fh.read() == files[rel]  # read handle denies Windows writers
                else:
                    refused('E_ISO_SOURCE_CHANGED', fh.read, file=rel)
        finally:
            img.close()
        (root / rel).write_bytes(b'?' * len(files[rel]))
        refused('E_ISO_FOLDER_MODIFIED', inputs.check_source_unchanged, root, ident, file=rel)


def test_folder_refuses_changes_during_extraction_before_publish():
    with fixture() as (td, root, files, _ref):
        rel = next(k for k in files if k.startswith('sounds/'))
        changed = False

        def progress(*_args):
            nonlocal changed
            if not changed:
                changed = True
                (root / rel).write_bytes(b'?' * len(files[rel]))

        refused('E_ISO_SOURCE_CHANGED', disc.run, root, td / 'cache', log=lambda *_: None, progress=progress,
                file=rel)
        assert not list((td / 'cache').glob('*/disc/stage.json'))


def test_folder_refuses_traversal_and_unreferenced_reads():
    with fixture() as (_td, root, _files, _ref):
        with image.open_image(root) as img:
            for rel in ('../default.xbe', '/default.xbe', 'z/../../outside', 'C:/outside',
                        'z\\..\\default.xbe', 'z//assetsfb.zip', './default.xbe', 'default.xbe:stream'):
                refused('E_ISO_FOLDER_UNSAFE', img.open_file, rel)
            try:
                img.open_file('pc-settings.ini')
            except KeyError:
                pass
            else:
                raise AssertionError('unreferenced file was read')


def test_folder_refuses_unsafe_reference_paths():
    with fixture() as (_td, root, _files, ref):
        ref['files']['../outside'] = [0, hashlib.sha256(b'').hexdigest()]
        refused('E_ISO_FOLDER_UNSAFE', inputs.identify, root)


def test_folder_refuses_case_collisions():
    with fixture() as (_td, root, files, _ref):
        other = root / 'DEFAULT.XBE'
        if other.exists():
            # Windows normally folds case. Exercise the same directory enumeration contract there.
            import xml1build.prepare.folder as folder
            real = os.scandir

            @contextlib.contextmanager
            def colliding(path):
                with real(path) as scan:
                    rows = list(scan)
                if Path(path) == root:
                    from types import SimpleNamespace
                    rows.append(SimpleNamespace(name='DEFAULT.XBE'))
                yield iter(rows)

            with patch.object(folder.os, 'scandir', colliding):
                refused('E_ISO_FOLDER_UNSAFE', inputs.identify, root)
        else:
            other.write_bytes(files['default.xbe'])
            refused('E_ISO_FOLDER_UNSAFE', inputs.identify, root)


def test_folder_refuses_junction_and_linked_ancestor():
    if os.name != 'nt':
        raise unittest.SkipTest('Windows junction regression; symlink case runs separately')
    with fixture() as (td, root, _files, _ref):
        alias = td / 'alias'
        r = subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(root)], capture_output=True)
        assert r.returncode == 0, r.stderr
        try:
            refused('E_ISO_FOLDER_UNSAFE', inputs.identify, alias)
            refused('E_ISO_FOLDER_UNSAFE', inputs.identify, alias / 'z')
        finally:
            os.rmdir(alias.absolute())


def test_folder_refuses_hardlinked_original():
    with fixture() as (td, root, _files, _ref):
        os.link(root / 'default.xbe', td / 'hardlink')
        refused('E_ISO_FOLDER_UNSAFE', inputs.identify, root)


def test_folder_refuses_symlink_in_consumed_tree():
    with fixture() as (td, root, _files, _ref):
        target = td / 'archive'
        (root / 'z').rename(target)
        try:
            (root / 'z').symlink_to(target, target_is_directory=True)
        except OSError as e:
            raise unittest.SkipTest(f'symlinks unavailable: {e.errno}')
        refused('E_ISO_FOLDER_UNSAFE', inputs.identify, root)


def test_folder_output_and_cache_cannot_overlap_source():
    with fixture() as (td, root, _files, _ref):
        for out in (root, root / 'out', td):
            refused('E_OUT_UNSAFE', commands.check_destination, out, iso=root)
        for cache in (root, root / 'cache', td):
            refused('E_OUT_UNSAFE', commands.check_cache, cache, iso=root)


def test_folder_deep_verification_reads_archive():
    with fixture() as (_td, root, _files, _ref):
        assert inputs.deep_check_disc(root) == []


def test_folder_reference_generation_requires_whole_image_trust():
    from xml1builder import devdata
    with fixture() as (td, _root, files, ref):
        iso = td / 'fixture.iso'
        iso.write_bytes(synth.xdvdfs(files))
        ident, _info = inputs.identify(iso)
        known = {'id': ref['id'], **{k: ident[k] for k in ('xbe_md5', 'zip_digest', 'listing_digest')},
                 'images': [{'format': 'xiso', 'size': iso.stat().st_size,
                             'sha256': hashlib.sha256(iso.read_bytes()).hexdigest()}]}
        result = devdata.folder_reference(iso, [known])
        assert result['files'] == ref['files'] and result['id'] == ref['id']
        # Matching executable / ZIP-directory alone cannot bless modified media.
        data = bytearray(iso.read_bytes())
        data[-1] ^= 1
        iso.write_bytes(data)
        try:
            devdata.folder_reference(iso, [known])
        except ValueError as e:
            assert 'SHA-256' in str(e)
        else:
            raise AssertionError('untrusted whole image supplied reference hashes')


def run_cli(argv, pipeline=None):
    from test_builder_cli import Stdin
    from xml1builder import cli
    from xml1builder.pipeline import RealPipeline
    out, err = io.StringIO(), io.StringIO()
    stdin = Stdin()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main([*argv, '--events', 'jsonl'], pipeline_factory=pipeline or RealPipeline,
                            stdin=stdin, fd_redirect=False)
    finally:
        stdin.close()
    rows = [json.loads(line) for line in out.getvalue().splitlines()]
    from test_builder_cli import check_stream
    check_stream(rows)
    return code, rows, err.getvalue()


def test_folder_cli_info_reports_verification_and_failure_file():
    with fixture() as (_td, root, _files, _ref):
        code, rows, err = run_cli(['info', '--iso', str(root)])
        assert code == 0, err
        assert rows[-1]['info']['iso']['verified'] is True
        assert 'Verified extracted install:' in err
        (root / 'z/assetsfb.zip').write_bytes(b'changed')
        code, rows, _err = run_cli(['info', '--iso', str(root)])
        assert code == 3 and rows[-2]['detail']['file'] == 'z/assetsfb.zip'


def test_folder_cli_does_not_write_logs_output_or_cache_into_source():
    import builder_stub as B
    with fixture() as (td, root, _files, _ref):
        before = tree_bytes(root)
        for command in ('info', 'build', 'verify', 'clean'):
            code, rows, _err = run_cli([command, '--iso', str(root), '--log', str(root / 'builder.log'),
                                       '--out', str(td / 'out')], B.StubPipeline)
            assert code == 2 and rows[-2]['code'] == 'E_OUT_UNSAFE'
        xml2 = B.make_xml2(td / 'xml2')
        for extra in (['--out', str(root / 'out'), '--cache', str(td / 'cache')],
                      ['--out', str(td / 'out'), '--cache', str(root / 'cache')]):
            code, rows, _err = run_cli(['build', '--iso', str(root), '--xml2', str(xml2), *extra], B.StubPipeline)
            assert code == 2 and rows[-2]['code'] == 'E_OUT_UNSAFE'
        assert tree_bytes(root) == before


def test_folder_cli_build_verify_deep_and_mutation_before_stamp():
    import builder_stub as B
    from xml1builder.pipeline import RealPipeline

    class FolderPipeline(B.StubPipeline):
        identify = RealPipeline.identify

        def prepare(self, sid, job, ctl):
            if sid == 'extract':
                return RealPipeline.prepare(self, sid, job, ctl)
            return super().prepare(sid, job, ctl)

    class ChangeAfterExtract(FolderPipeline):
        def validate(self, job, ctl):
            (job.iso / 'z/assetsfb.zip').write_bytes(b'changed')
            return super().validate(job, ctl)

    with fixture() as (td, root, _files, _ref):
        xml2 = B.make_xml2(td / 'xml2')
        args = ['build', '--iso', str(root), '--xml2', str(xml2), '--out', str(td / 'out'),
                '--cache', str(td / 'cache'), '--allow-unknown-exe']
        code, rows, err = run_cli(args, FolderPipeline)
        assert code == 0, err
        assert rows[-1]['stamp']['inputs']['disc']['format'] == 'folder'
        code, rows, err = run_cli(['verify', '--iso', str(root), '--out', str(td / 'out'), '--deep'], FolderPipeline)
        assert code == 0 and rows[-1]['verify']['state'] == 'current', err
        (root / 'z/assetsfb.zip').write_bytes(b'changed')
        code, rows, err = run_cli(['verify', '--iso', str(root), '--out', str(td / 'out'), '--deep'], FolderPipeline)
        assert code == 3 and rows[-2]['detail']['file'] == 'z/assetsfb.zip', err
    with fixture() as (td, root, _files, _ref):
        xml2 = B.make_xml2(td / 'xml2')
        args = ['build', '--iso', str(root), '--xml2', str(xml2), '--out', str(td / 'out'),
                '--cache', str(td / 'cache'), '--allow-unknown-exe']
        code, rows, err = run_cli(args, ChangeAfterExtract)
        assert code == 3 and rows[-2]['detail']['file'] == 'z/assetsfb.zip', err
        assert not (td / 'out/_build/stamp.json').exists()


def test_folder_prepare_and_copy_refuse_source_as_destination():
    with fixture() as (td, root, _files, _ref):
        before = tree_bytes(root)
        refused('E_ISO_FOLDER_UNSAFE', disc.run, root, root / 'cache', log=lambda *_: None)
        with image.open_image(root) as img:
            refused('E_ISO_FOLDER_UNSAFE', img.copy_file, 'default.xbe', root / 'copied.bin')
            refused('E_ISO_FOLDER_UNSAFE', disc.extract, img, root / 'cache', log=lambda *_: None)
        assert tree_bytes(root) == before


def test_folder_no_movies_then_add_movies_matches_iso():
    with fixture() as (td, root, files, _ref):
        iso = td / 'fixture.iso'
        iso.write_bytes(synth.xdvdfs(files))
        a = disc.run(iso, td / 'cache', movies=False, log=lambda *_: None)
        b = disc.run(root, td / 'cache', movies=False, log=lambda *_: None)
        aa, bb = tree_bytes(a['dir']), tree_bytes(b['dir'])
        aa.pop('stage.json')
        bb.pop('stage.json')
        assert aa == bb and not (b['dir'] / 'xbox/movies').exists()
        a = disc.run(iso, td / 'cache', movies=True, log=lambda *_: None)
        b = disc.run(root, td / 'cache', movies=True, log=lambda *_: None)
        aa, bb = tree_bytes(a['dir']), tree_bytes(b['dir'])
        aa.pop('stage.json')
        bb.pop('stage.json')
        assert aa == bb and a['cached'] and b['cached']


def test_folder_restored_mtime_cannot_hide_modified_content():
    with fixture() as (_td, root, files, _ref):
        ident, _info = inputs.identify(root)
        rel = next(k for k in files if k.startswith('sounds/'))
        p = root / rel
        st = p.stat()
        p.write_bytes(b'?' * len(files[rel]))
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
        refused('E_ISO_FOLDER_MODIFIED', inputs.check_source_unchanged, root, ident, file=rel)


def test_folder_missing_archive_never_falls_back_to_loose_overlay():
    with fixture() as (_td, root, _files, _ref):
        (root / 'data').mkdir()
        (root / 'data/colors.xml').write_bytes(b'overlay')
        (root / 'z/assetsfb.zip').unlink()
        refused('E_ISO_FOLDER_MISSING', inputs.identify, root, file='z/assetsfb.zip')


def test_folder_developer_build_refuses_source_output_before_preparing():
    import build_xml1
    import builder_stub as B
    with fixture() as (td, root, _files, _ref):
        base = B.make_xml2(td / 'xml2')
        for out in (root, root / 'new-build'):
            with patch.object(build_xml1, 'make_sources', side_effect=AssertionError('prepared before guarding output')):
                with contextlib.redirect_stderr(io.StringIO()):
                    code = build_xml1.main(['--sources', 'prepared', '--iso', str(root), '--base', str(base),
                                            '--cache', str(td / 'cache'), '--out', str(out), '--adopt'])
            assert code == 2


def test_folder_external_hardlinked_log_cannot_modify_an_original():
    with fixture() as (td, root, files, _ref):
        log = td / 'metadata.log'
        os.link(root / 'default.xbe', log)
        code, rows, _err = run_cli(['info', '--iso', str(root), '--log', str(log)])
        assert code == 2 and rows[-2]['code'] == 'E_OUT_UNSAFE'
        assert (root / 'default.xbe').read_bytes() == files['default.xbe']


def test_folder_reference_rejects_or_prevents_mutation_after_authentication():
    from xml1builder import devdata
    with fixture() as (td, _root, files, ref):
        iso = td / 'fixture.iso'
        iso.write_bytes(synth.xdvdfs(files))
        ident, _info = inputs.identify(iso)
        known = {'id': ref['id'], **{k: ident[k] for k in ('xbe_md5', 'zip_digest', 'listing_digest')},
                 'images': [{'format': 'xiso', 'size': iso.stat().st_size,
                             'sha256': hashlib.sha256(iso.read_bytes()).hexdigest()}]}
        original_identify, blocked = disc.identify, []

        def mutate(img):
            identity = original_identify(img)
            rel = next(k for k in files if k.startswith('sounds/'))
            try:
                with open(iso, 'r+b') as out:
                    out.seek(img.get(rel).sector * image.SECTOR)
                    out.write(b'?' * len(files[rel]))
            except PermissionError:
                blocked.append(True)
            return identity

        with patch.object(disc, 'identify', mutate):
            try:
                devdata.folder_reference(iso, [known])
            except ValueError as e:
                assert 'changed' in str(e)
            else:
                assert blocked, 'changed bytes were accepted into the trusted reference'


def test_folder_even_fallback_logs_refuse_hardlinks_before_writing():
    from xml1builder.events import Output
    with fixture() as (td, root, files, _ref):
        log = td / 'metadata.log'
        os.link(root / 'default.xbe', log)
        try:
            output = Output(log_file=log, stdout=io.StringIO(), stderr=io.StringIO())
        except OSError:
            pass
        else:
            output.close()
            raise AssertionError('hardlinked log was opened for writing')
        assert (root / 'default.xbe').read_bytes() == files['default.xbe']


def test_folder_hashing_honors_cancellation_without_publishing_cache():
    from xml1build.prepare import Cancelled
    with fixture() as (td, root, _files, _ref):
        try:
            disc.run(root, td / 'cache', cancel=lambda: True, log=lambda *_: None)
        except Cancelled:
            pass
        else:
            raise AssertionError('cancelled folder hashing continued')
        assert not (td / 'cache').exists()


def test_folder_preflight_io_errors_preserve_cli_events():
    with fixture() as (_td, root, _files, _ref):
        with patch.object(commands, 'check_source_writes', side_effect=PermissionError(13, 'Access denied')):
            code, rows, _err = run_cli(['info', '--iso', str(root)])
        assert code == 6 and rows[-2]['code'] == 'E_IO'
