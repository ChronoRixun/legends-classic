"""Offline workflow release policy checks: python tools/test_release_metadata.py."""
import json
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import release_metadata as R


class ReleaseTests(unittest.TestCase):
    def test_tags_and_flags(self):
        for tag, base, pre in [('v1.8.0', '1.8.0', False),
                               ('v1.8.0-beta.2', '1.8.0', True),
                               ('v0.3.0-rc.1', '0.3.0', True)]:
            with self.subTest(tag=tag):
                meta = R.metadata(tag)
                self.assertEqual(meta['version'], tag[1:])
                self.assertEqual(meta['base'], base)
                self.assertEqual(meta['flags'], ['--prerelease', '--latest=false'] if pre else [])
                self.assertEqual(R.release_version(tag, base), tag[1:])
        self.assertEqual(R.release_version(None, '0.3.0'), '0.3.0')
        for tag in ['malformed', '0.3.0', 'v00.3.0', 'v0.3.0-beta', 'v0.3.0-beta.02',
                    'v0.3.0-alpha.1', 'v0.3.0+build', 'v0.3.0-rc.1\n', 'v0.3.0-beta.2/evil']:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                R.metadata(tag)
        with self.assertRaises(ValueError):
            R.release_version('v0.3.0-beta.2', '0.2.5')

    def test_notes(self):
        changelog = '# Changes\n\n## v1.8.0\n\nOther.\n\n## v0.3.0 - date\n\nNew.\n### Fix\nDetail.\n\n## v0.2.5\nOld.\n'
        stable = R.release_notes('v0.3.0', 24, changelog, 'hash  zip\n')
        for suffix in ['beta.2', 'rc.1']:
            notes = R.release_notes('v0.3.0-' + suffix, 24, changelog, 'hash  zip\n')
            self.assertTrue(notes.startswith('Beta - test build\n\n'))
            self.assertIn('builder v0.3.0-' + suffix, notes)
            self.assertIn('New.\n### Fix\nDetail.', notes)
            self.assertNotIn('Other.', notes)
            self.assertNotIn('Old.', notes)
            self.assertIn('hash  zip', notes)
        self.assertFalse(stable.startswith('Beta'))
        # Stable tags keep the old missing-section behavior; prereleases require base notes.
        R.release_notes('v9.0.0', 24, changelog, '')
        with self.assertRaises(ValueError):
            R.release_notes('v9.0.0-beta.1', 24, changelog, '')

    def test_cli(self):
        p = subprocess.run([sys.executable, str(Path(R.__file__)), '--tag', 'v0.3.0-rc.1'],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)['flags'], ['--prerelease', '--latest=false'])
        p = subprocess.run([sys.executable, str(Path(R.__file__)), '--tag', 'malformed'],
                           capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)

    def test_builder_tag_check_and_manifest(self):
        import freeze_builder as F
        from xml1builder import VERSION
        tag = 'v' + VERSION + '-beta.2'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(F.main(['--check-tag', tag]), 0)
            self.assertEqual(F.main(['--check-tag', 'malformed']), 1)
            self.assertEqual(F.main(['--check-tag', 'v9.9.9-beta.2']), 1)
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td)
            version = R.release_version(tag, VERSION)
            archive = dist / F.zip_name(version)
            archive.write_bytes(b'synthetic archive')
            manifest = F.write_manifest(dist, archive, '0.0.0', version=version)
            self.assertEqual(set(manifest), {'version', 'content_version', 'zip', 'size', 'sha256',
                                             'min_launcher', 'requires_xml2fix'})
            self.assertEqual(manifest['version'], version)
            self.assertEqual(manifest['requires_xml2fix'], '>=1.8.0-beta.6')
            self.assertEqual(manifest['zip'], f'xml1-builder-{version}-win64.zip')
            self.assertEqual(json.loads((dist / 'xml1-builder.json').read_text())['version'], version)

    def test_frozen_builder_reports_full_version(self):
        from xml1builder import VERSION
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / 'xml1builder' / 'data'
            data.mkdir(parents=True)
            version = VERSION + '-rc.1'
            (data / 'build-info.json').write_text(json.dumps({'version': version}), encoding='utf-8')
            # Simulate the frozen package before import, in a fresh interpreter.
            code = ('import sys; sys.path.insert(0, sys.argv[1]); '
                    'sys.frozen=True; sys._MEIPASS=sys.argv[2]; '
                    'import xml1builder; print(xml1builder.VERSION)')
            p = subprocess.run([sys.executable, '-c', code, str(Path(R.__file__).parent), td],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout.strip(), version)

    def test_freeze_orchestration_keeps_tag_in_all_release_outputs(self):
        import ast
        import os
        import types
        from unittest.mock import patch
        import freeze_builder as F
        from xml1builder import VERSION

        # Exercise the real freezer orchestration and zip/manifest/checksum generation; only the
        # native toolchain and game-independent research packaging are replaced by synthetic inputs.
        def fake_pyinstaller(dist, work, gen, kernel):
            folder = dist / F.APP
            data = folder / '_internal' / 'xml1builder' / 'data'
            data.mkdir(parents=True)
            (folder / F.EXE_NAME).write_bytes(b'synthetic builder executable')
            (data / 'build-info.json').write_bytes((gen / 'build-info.json').read_bytes())

        spec = ast.parse((F.TOOLS / 'xml1builder' / 'xml1-builder.spec').read_text(encoding='utf-8'))
        v4 = next(node for node in spec.body if isinstance(node, ast.FunctionDef) and node.name == '_v4')
        scope = {}
        exec(compile(ast.Module(body=[v4], type_ignores=[]), '<numeric VERSIONINFO>', 'exec'), scope)
        for suffix in ['', '-beta.2', '-rc.1']:
            version = VERSION + suffix
            with self.subTest(version=version), tempfile.TemporaryDirectory() as td, \
                 patch.dict(os.environ, XML1_RELEASE_TAG='v' + version), \
                 patch.dict(sys.modules, PyInstaller=types.SimpleNamespace(__version__='synthetic')), \
                 patch.object(F, 'run_pyinstaller', side_effect=fake_pyinstaller), \
                 patch.object(F, 'guard_bundle'), patch.object(F, 'package_research', return_value={}), \
                 patch.object(F, 'git', return_value=''), contextlib.redirect_stdout(io.StringIO()):
                dist, work = Path(td) / 'dist', Path(td) / 'work'
                self.assertEqual(F.main(['--no-kernel', '--dist', str(dist), '--work', str(work)]), 0)
                info = json.loads((work / 'gen/build-info.json').read_text())
                manifest = json.loads((dist / 'xml1-builder.json').read_text())
                self.assertEqual(info['version'], version)
                self.assertEqual(manifest['version'], version)
                self.assertEqual(manifest['requires_xml2fix'], '>=1.8.0-beta.6' if suffix else '>=1.8')
                self.assertEqual(manifest['zip'], f'xml1-builder-{version}-win64.zip')
                self.assertTrue((dist / manifest['zip']).is_file())
                self.assertIn(manifest['zip'], (dist / 'SHA256SUMS.txt').read_text())
                self.assertEqual(scope['_v4'](version), tuple(map(int, VERSION.split('.'))) + (0,))


if __name__ == '__main__':
    unittest.main()
