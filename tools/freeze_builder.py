"""Freeze the builder: xml1-builder.exe (PyInstaller one folder), its release zip and the launcher's manifest
(BUILDER_DESIGN.md 3.2, 3.3, 4.5; SPEC.md 27.13).

    python tools/freeze_builder.py [--dist DIR] [--work DIR] [--kernel DLL | --no-kernel] [--min-launcher V]
                                   [--smoke] [--check-tag vX.Y.Z]

Run it with the Python the builder ships (requirements-freeze.txt: CPython 3.14 x64, numpy, PyInstaller), from a
venv or CI. Steps:
  1. the compiled sound kernel (default: build/native/ima_kernel-<platform>.dll from tools/build_sound_kernel.py) must
     load and pass adpcm_c's self-check; --no-kernel freezes without it (the sound stages then run on numpy, 6-8x
     slower);
  2. <work>/gen/build-info.json: version, content version, commit (+ dirty), Python / numpy / PyInstaller versions,
     the kernel's sha256, the bootloader kind ($XML1_BOOTLOADER: wheel | source); <work>/gen/research/: the research
     tables the frozen builder reads (xml1builder.resources.RESEARCH_DATA), the text-bearing ones packaged without
     their game text (PACKAGED_STRIP / PACKAGED_KEEP; BUILDER_DESIGN.md 5.2);
  3. PyInstaller with tools/xml1builder/xml1-builder.spec -> <dist>/xml1-builder/ (xml1-builder.exe + _internal/);
     then the content guard (tools/check_no_game_content.py) over the bundled data (_internal/research,
     _internal/xml1builder/data): a finding stops the freeze;
  4. <dist>/xml1-builder-<VERSION>-win64.zip (xml1-builder.exe and _internal/ at the top: the launcher's
     tool_install unpacks it into tools\\xml1-builder\\<version>\\), <dist>/xml1-builder.json (the release manifest
     the launcher's tool_install::parse_manifest reads: version, content_version, zip, size, sha256, min_launcher,
     requires_xml2fix) and <dist>/SHA256SUMS.txt;
  5. --smoke: tools/freeze_smoke.py against the frozen folder (no game data).
--check-tag vX.Y.Z (CI on a tag): exit 1 unless the tag is v<VERSION>.
Defaults: --dist <repo>/dist, --work <repo>/build/freeze (both gitignored). No UPX, ever (BUILDER_DESIGN.md 3.3).
The bootloader is the PyInstaller wheel's prebuilt one unless CI rebuilt it from source (the release workflow's
`bootloader` input; design 3.3 step 1)."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / 'tools'
SPEC = TOOLS / 'xml1builder' / 'xml1-builder.spec'
EXE_NAME = 'xml1-builder.exe'
APP = 'xml1-builder'

from xml1builder import CONTENT_VERSION, MIN_LAUNCHER, VERSION  # noqa: E402  (tools/ = this script's folder)
from xml1builder import resources as R  # noqa: E402
from xml1build import fix_ini  # noqa: E402
from xml1build.lib import adpcm_c  # noqa: E402


def zip_name(version=VERSION) -> str:
    return f'{APP}-{version}-win64.zip'


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def git(*args) -> str:
    try:
        return subprocess.run(['git', '-C', str(REPO), *args], capture_output=True, text=True, check=True,
                              stdin=subprocess.DEVNULL).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ''


def check_kernel(path: Path) -> str:
    """load + self-check the library in this process (the same code the frozen builder runs); -> status line."""
    os.environ[adpcm_c.ENV] = str(path)
    if not adpcm_c.load():
        raise SystemExit(f'sound kernel not usable: {adpcm_c.STATUS}\n'
                         'build it with: python tools/build_sound_kernel.py (or freeze with --no-kernel)')
    return adpcm_c.STATUS


def build_info(kernel: Path | None) -> dict:
    import numpy
    import PyInstaller
    commit = git('rev-parse', 'HEAD')
    dirty = bool(git('status', '--porcelain', '--untracked-files=no'))
    info = {'version': VERSION, 'content_version': CONTENT_VERSION, 'commit': commit[:12] or 'unknown',
            'commit_full': commit or 'unknown', 'dirty': dirty,
            'built': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'python': sys.version.split()[0], 'numpy': numpy.__version__, 'pyinstaller': PyInstaller.__version__,
            'bootloader': os.environ.get('XML1_BOOTLOADER', 'wheel'),
            'kernel': None}
    if kernel:
        info['kernel'] = {'file': adpcm_c.lib_name(), 'sha256': sha256_file(kernel), 'source_sha1': adpcm_c.source_sha1()}
    if os.environ.get('GITHUB_RUN_ID'):
        info['ci'] = {'run_id': os.environ['GITHUB_RUN_ID'], 'repository': os.environ.get('GITHUB_REPOSITORY', ''),
                      'ref': os.environ.get('GITHUB_REF', '')}
    return info


def _strip(obj, keys):
    if isinstance(obj, dict):
        return {k: _strip(v, keys) for k, v in obj.items() if k not in keys}
    if isinstance(obj, list):
        return [_strip(v, keys) for v in obj]
    return obj


def package_research(dest: Path) -> dict:
    """<dest>/<rel> for every table the frozen builder reads (R.RESEARCH_DATA): copied, or packaged without game text
    - R.PACKAGED_STRIP drops those keys everywhere and adds R.PACKAGED_MARK (the pipeline then takes mission texts
    from the disc), R.PACKAGED_KEEP keeps only the fields the pipeline reads. -> {rel: (source bytes, packaged bytes)}"""
    sizes = {}
    for rel in R.RESEARCH_DATA:
        src, out = REPO / 'research' / rel, dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if rel in R.PACKAGED_STRIP:
            data = _strip(json.loads(src.read_text(encoding='utf-8')), set(R.PACKAGED_STRIP[rel]))
            data = {R.PACKAGED_MARK: 'packaged by tools/freeze_builder.py without the fields '
                                     + ', '.join(R.PACKAGED_STRIP[rel]) + ' (no game text in a release)', **data}
            out.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8', newline='\n')
        elif rel in R.PACKAGED_KEEP:
            keep = R.PACKAGED_KEEP[rel]
            data = json.loads(src.read_text(encoding='utf-8'))
            data = {k: ({f: v[f] for f in keep if f in v} if isinstance(v, dict) else v) for k, v in data.items()}
            out.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8', newline='\n')
        else:
            shutil.copyfile(src, out)
        sizes[rel] = (src.stat().st_size, out.stat().st_size)
    return sizes


def guard_bundle(folder: Path):
    """the content guard over the data the bundle carries (not the Python runtime: its DLLs are binaries by nature)."""
    internal = folder / '_internal'
    cmd = [sys.executable, str(TOOLS / 'check_no_game_content.py'), str(internal / 'research'),
           str(internal / 'xml1builder' / 'data'), '--repo', str(internal), '--allow', str(REPO / '.content-guard-allow')]
    rc = subprocess.run(cmd).returncode
    if rc:
        raise SystemExit('the bundled data failed the content guard: nothing from the games may ship')


def run_pyinstaller(dist: Path, work: Path, gen: Path, kernel: Path | None):
    env = dict(os.environ, XML1_FREEZE_GEN=str(gen), XML1_FREEZE_KERNEL=str(kernel or ''))
    env.pop('XML1_PORT_ROOT', None)
    env.pop(adpcm_c.ENV, None)
    cmd = [sys.executable, '-m', 'PyInstaller', str(SPEC), '--noconfirm', '--clean', '--log-level', 'WARN',
           '--distpath', str(dist), '--workpath', str(work / 'pyinstaller')]
    print('>', ' '.join(cmd), flush=True)
    rc = subprocess.run(cmd, env=env, cwd=str(REPO)).returncode
    if rc:
        raise SystemExit(f'PyInstaller failed (exit {rc})')


def make_zip(folder: Path, archive: Path):
    """every file of the frozen folder, exe at the top level; sorted entries."""
    tmp = archive.with_suffix('.zip.partial')
    files = sorted(p for p in folder.rglob('*') if p.is_file())
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            z.write(p, p.relative_to(folder).as_posix())
    os.replace(tmp, archive)
    return len(files)


def write_manifest(dist: Path, archive: Path, min_launcher: str) -> dict:
    """xml1-builder.json - the fields and types ultimate-legends' tool_install::parse_manifest reads (branch
    xml1-entry): version (string), content_version (int), zip (a file name next to the manifest), size (uint64 > 0),
    sha256 (64 lower-case hex), min_launcher, requires_xml2fix (strings)."""
    manifest = {'version': VERSION, 'content_version': CONTENT_VERSION, 'zip': archive.name,
                'size': archive.stat().st_size, 'sha256': sha256_file(archive), 'min_launcher': min_launcher,
                'requires_xml2fix': '>=' + fix_ini.REQUIRED_XML2FIX}
    (dist / 'xml1-builder.json').write_text(json.dumps(manifest, indent=1) + '\n', encoding='utf-8', newline='\n')
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='freeze_builder.py', description=__doc__.split('\n\n')[0])
    ap.add_argument('--dist', default=str(REPO / 'dist'))
    ap.add_argument('--work', default=str(REPO / 'build' / 'freeze'))
    k = ap.add_mutually_exclusive_group()
    k.add_argument('--kernel', help='the compiled sound kernel to ship (default: build/native/<lib>)')
    k.add_argument('--no-kernel', dest='no_kernel', action='store_true', help='freeze without the kernel (numpy)')
    ap.add_argument('--min-launcher', dest='min_launcher', default=MIN_LAUNCHER,
                    help=f'the manifest\'s min_launcher (default {MIN_LAUNCHER})')
    ap.add_argument('--smoke', action='store_true', help='run tools/freeze_smoke.py on the result')
    ap.add_argument('--check-tag', dest='check_tag', help='only check that this tag is v<VERSION>')
    a = ap.parse_args(argv)

    if a.check_tag is not None:
        if a.check_tag != f'v{VERSION}':
            print(f'tag {a.check_tag}, but the builder is version {VERSION}: update VERSION in '
                  'tools/xml1builder/__init__.py (and CONTENT_VERSION when the output changes)')
            return 1
        print(f'tag {a.check_tag} = builder {VERSION} (content {CONTENT_VERSION})')
        return 0
    if os.name != 'nt':
        print('warning: the release is Windows x64 only (BUILDER_DESIGN.md 3.4); this freezes for this platform')
    t0 = time.time()
    dist, work = Path(a.dist).resolve(), Path(a.work).resolve()
    gen = work / 'gen'
    shutil.rmtree(gen, ignore_errors=True)
    gen.mkdir(parents=True)

    kernel = None
    if not a.no_kernel:
        kernel = Path(a.kernel or Path(adpcm_c.default_dir()) / adpcm_c.lib_name()).resolve()
        if not kernel.is_file():
            raise SystemExit(f'no sound kernel at {kernel}: run python tools/build_sound_kernel.py first '
                             '(or freeze with --no-kernel)')
        print('sound kernel:', check_kernel(kernel))
    info = build_info(kernel)
    (gen / 'build-info.json').write_text(json.dumps(info, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('build-info:', json.dumps(info))
    for rel, (a_size, b_size) in package_research(gen / 'research').items():
        print(f'research/{rel}: {a_size:,} -> {b_size:,} bytes' + (' (packaged)' if a_size != b_size else ''))

    folder = dist / APP
    shutil.rmtree(folder, ignore_errors=True)
    run_pyinstaller(dist, work, gen, kernel)
    exe = folder / EXE_NAME
    if not exe.is_file():
        raise SystemExit(f'{exe} was not made')
    size = sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
    print(f'frozen: {folder} ({size / 1e6:.1f} MB unpacked)')
    guard_bundle(folder)

    for old in dist.glob(f'{APP}-*-win64.zip'):
        old.unlink()
    archive = dist / zip_name()
    n = make_zip(folder, archive)
    manifest = write_manifest(dist, archive, a.min_launcher)
    (dist / 'SHA256SUMS.txt').write_text(
        f'{manifest["sha256"]}  {archive.name}\n{sha256_file(exe)}  {APP}/{EXE_NAME}\n', encoding='utf-8', newline='\n')
    print(f'zip: {archive} ({n} files, {manifest["size"] / 1e6:.1f} MB, sha256 {manifest["sha256"]})')
    print('manifest:', json.dumps(manifest))
    if a.smoke:
        rc = subprocess.run([sys.executable, str(TOOLS / 'freeze_smoke.py'), str(folder), '--info',
                             str(gen / 'build-info.json')]).returncode
        if rc:
            print('smoke tests FAILED')
            return 1
    print(f'done in {time.time() - t0:.0f} s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
