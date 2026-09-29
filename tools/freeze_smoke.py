"""Smoke tests of a frozen builder folder, without game data (BUILDER_DESIGN.md 6.1 "Packaging"; CI runs them after
tools/freeze_builder.py). The folder can be the dist output or the unpacked release zip.

    python tools/freeze_smoke.py <dist/xml1-builder> [--info build-info.json]

Checks (each prints PASS / FAIL; exit 1 on any failure):
  layout      xml1-builder.exe + _internal/: the package data, build-info.json, every packaged research table
              (xml1builder.resources.RESEARCH_DATA; graph.json the text-free copy), ima_kernel.c (+ the kernel DLL
              when build-info names one)
  version     --version (text) and --version --events jsonl: hello {v, builder, content_version, commit} + result
  jsonl       every stdout line of an --events jsonl run is one JSON object with "ev" and "t"
  wrong game  info --iso <synthetic XISO, title ID 0x41560017> -> exit 3, error E_ISO_WRONG_GAME (detail.title_id)
  xml1 disc   info --iso <synthetic XML1 XISO> -> exit 0, result.info.iso: title ID 0x4156001E, not a known dump;
              estimate.kernel = the DLL is bundled
  xml2        info --xml2 <a stand-in install> -> exit 3, E_XML2_UNKNOWN_EXE
  usage       an unknown option -> exit 2, E_USAGE
  root        with $XML1_PORT_ROOT pointing somewhere else the frozen builder still reads only its own bundle
              (resources.setup overrides it; check_root would stop it with E_INTERNAL)"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tests' / 'unit'))        # synth: the synthetic disc images of the unit tests
import synth  # noqa: E402  (also puts tools/ on sys.path)
import builder_stub  # noqa: E402
from xml1builder import CONTENT_VERSION, SCHEMA, VERSION  # noqa: E402
from xml1builder import resources as R  # noqa: E402

FAILED = []


def check(name, ok, detail=''):
    print(f'{"PASS" if ok else "FAIL"} {name}' + (f': {detail}' if detail and not ok else ''), flush=True)
    if not ok:
        FAILED.append(name)


def run(exe, *args, env=None, timeout=120):
    t0 = time.time()
    p = subprocess.run([str(exe), *args], capture_output=True, text=True, encoding='utf-8', errors='replace',
                       stdin=subprocess.DEVNULL, env=env, timeout=timeout)
    return p, time.time() - t0


def events(stdout):
    evs = []
    for line in stdout.splitlines():
        if line.strip():
            evs.append(json.loads(line))
    return evs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='freeze_smoke.py')
    ap.add_argument('folder')
    ap.add_argument('--info', help='the build-info.json the folder was frozen with (expected commit / kernel)')
    a = ap.parse_args(argv)
    folder = Path(a.folder).resolve()
    exe = folder / 'xml1-builder.exe'
    internal = folder / '_internal'
    info = json.loads(Path(a.info).read_text(encoding='utf-8')) if a.info else \
        json.loads((internal / 'xml1builder' / 'data' / 'build-info.json').read_text(encoding='utf-8'))

    # ---- layout
    missing = [p for p in [exe, internal / 'xml1builder' / 'data' / 'build-info.json',
                           internal / 'xml1builder' / 'data' / 'known_dumps.json',
                           internal / 'xml1builder' / 'data' / 'known_xml2.json',
                           internal / 'xml1builder' / 'data' / 'xml2_retail_files.json.gz',
                           internal / 'xml1build' / 'lib' / 'ima_kernel.c']
               + [internal / 'research' / rel for rel in R.RESEARCH_DATA] if not p.is_file()]
    kernel = info.get('kernel')
    if kernel:
        dll = internal / 'xml1build' / 'lib' / kernel['file']
        if not dll.is_file():
            missing.append(dll)
    check('layout', not missing, ', '.join(str(p) for p in missing))
    graph = internal / 'research' / 'sweep' / 'graph.json'
    check('packaged tables', graph.is_file() and R.PACKAGED_MARK in json.loads(graph.read_text(encoding='utf-8')),
          'research/sweep/graph.json is not the packaged (text-free) copy')
    bundled = json.loads((internal / 'xml1builder' / 'data' / 'build-info.json').read_text(encoding='utf-8'))
    check('build-info', bundled.get('commit') == info.get('commit') and bundled.get('version') == VERSION,
          f'{bundled.get("commit")} / {bundled.get("version")}')

    env = dict(os.environ)
    env.pop('XML1_PORT_ROOT', None)

    # ---- version
    p, dt = run(exe, '--version', env=env)
    check(f'version text ({dt:.1f} s)', p.returncode == 0 and f'xml1-builder {VERSION} ' in p.stdout
          and str(info.get('commit')) in p.stdout, p.stdout + p.stderr)
    p, dt = run(exe, '--version', '--events', 'jsonl', env=env)
    try:
        evs = events(p.stdout)
        hello, result = evs[0], evs[-1]
        ok = (p.returncode == 0 and hello['ev'] == 'hello' and hello['v'] == SCHEMA and hello['builder'] == VERSION
              and hello['content_version'] == CONTENT_VERSION and hello['commit'] == info.get('commit')
              and result['ev'] == 'result' and result['ok'] is True and result['exit'] == 0)
        check(f'version jsonl ({dt:.1f} s)', ok, p.stdout)
    except (ValueError, KeyError, IndexError) as e:
        check('version jsonl', False, f'{e}: {p.stdout!r}')

    with tempfile.TemporaryDirectory(prefix='xml1-smoke-') as td:
        td = Path(td)
        wrong = td / 'other.iso'
        wrong.write_bytes(synth.xdvdfs(synth.xml1_disc_files(title_id=0x41560017)))
        good = td / 'xml1.iso'
        good.write_bytes(synth.xdvdfs(synth.xml1_disc_files()))
        xml2 = builder_stub.make_xml2(td / 'xml2')
        cache = td / 'cache'

        # ---- wrong game
        p, dt = run(exe, 'info', '--iso', str(wrong), '--cache', str(cache), '--events', 'jsonl', env=env)
        try:
            evs = events(p.stdout)
            check('jsonl stream', all('ev' in e and 't' in e for e in evs), p.stdout)
            err = [e for e in evs if e['ev'] == 'error']
            check(f'wrong game ({dt:.1f} s)', p.returncode == 3 and err and err[0]['code'] == 'E_ISO_WRONG_GAME'
                  and err[0]['detail'].get('title_id') == '0x41560017', p.stdout + p.stderr[-2000:])
        except (ValueError, KeyError) as e:
            check('wrong game', False, f'{e}: {p.stdout!r} {p.stderr[-2000:]}')

        # ---- a synthetic XML1 disc
        p, dt = run(exe, 'info', '--iso', str(good), '--cache', str(cache), '--events', 'jsonl', env=env)
        try:
            evs = events(p.stdout)
            res = evs[-1]
            iso = res.get('info', {}).get('iso') or {}
            est = res.get('info', {}).get('estimate') or {}
            check(f'xml1 disc ({dt:.1f} s)', p.returncode == 0 and res['ok'] and iso.get('title_id') == '0x4156001E'
                  and iso.get('known') is False, p.stdout + p.stderr[-2000:])
            check('kernel bundled', bool(est.get('kernel')) == bool(kernel), json.dumps(est))
        except (ValueError, KeyError, IndexError) as e:
            check('xml1 disc', False, f'{e}: {p.stdout!r} {p.stderr[-2000:]}')

        # ---- an XML2 stand-in (not a retail exe)
        p, dt = run(exe, 'info', '--xml2', str(xml2), '--events', 'jsonl', env=env)
        try:
            err = [e for e in events(p.stdout) if e['ev'] == 'error']
            check(f'xml2 stand-in ({dt:.1f} s)', p.returncode == 3 and err and err[0]['code'] == 'E_XML2_UNKNOWN_EXE',
                  p.stdout + p.stderr[-2000:])
        except (ValueError, KeyError) as e:
            check('xml2 stand-in', False, f'{e}: {p.stdout!r}')

        # ---- usage
        p, _ = run(exe, 'info', '--no-such-option', '--events', 'jsonl', env=env)
        try:
            err = [e for e in events(p.stdout) if e['ev'] == 'error']
            check('usage error', p.returncode == 2 and err and err[0]['code'] == 'E_USAGE', p.stdout)
        except (ValueError, KeyError) as e:
            check('usage error', False, f'{e}: {p.stdout!r}')

        # ---- a foreign XML1_PORT_ROOT cannot redirect the frozen builder
        bogus = td / 'not-the-bundle'
        bogus.mkdir()
        p, _ = run(exe, 'info', '--iso', str(good), '--cache', str(cache), '--events', 'jsonl',
                   env=dict(env, XML1_PORT_ROOT=str(bogus)))
        try:
            res = events(p.stdout)[-1]
            check('root override ignored', p.returncode == 0 and res['ok'], p.stdout + p.stderr[-2000:])
        except (ValueError, IndexError) as e:
            check('root override ignored', False, f'{e}: {p.stdout!r}')

    print(f'{"FAILED: " + ", ".join(FAILED) if FAILED else "all smoke tests passed"}')
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
