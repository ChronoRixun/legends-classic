"""The builder end to end on a stub pipeline (BUILDER_DESIGN.md 6.1): the event stream (schema, order), exit codes,
cancel at every stage and the resume, the lock, the state machine, verify (missing / changed / extra files, the
report), the repair by a rebuild, the keep-list (the launcher's / player's files survive build, rebuild and clean),
the ini merge, clean. No game data."""
import io
import json
import os
import queue
import sys
import tempfile
import threading
from pathlib import Path

import builder_stub as B
from xml1builder import cli, events, manifest as M


class Stdin:
    """a stdin that stays open (the launcher keeps its pipe) until close(); put('cancel') sends a line."""

    def __init__(self):
        self.q = queue.Queue()

    def __iter__(self):
        while True:
            line = self.q.get()
            if line is None:
                return
            yield line

    def put(self, line):
        self.q.put(line + '\n')

    def close(self):
        self.q.put(None)


def run(argv, *, stub=None, stdin=None, exit_fn=None):
    """cli.main with captured stdout / stderr -> (exit code, [events], stderr text)."""
    B.StubPipeline.instances.clear()
    for k in ('fail_stage', 'io_stage', 'crash_stage', 'cancel_at', 'corrupt_after_write', 'corrupt_copy', 'busy',
              'module_fn'):
        setattr(B.StubPipeline, k, (stub or {}).get(k))
    B.StubPipeline.validate_errors = (stub or {}).get('validate_errors', 0)
    out, err = io.StringIO(), io.StringIO()
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    stdin = stdin if stdin is not None else Stdin()
    try:
        code = cli.main(argv, pipeline_factory=B.StubPipeline, stdin=stdin, fd_redirect=False, exit_fn=exit_fn)
    finally:
        sys.stdout, sys.stderr = saved
        if isinstance(stdin, Stdin):
            stdin.close()
    evs = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
    return code, evs, err.getvalue()


def check_stream(evs):
    assert evs and evs[0]['ev'] == 'hello' and evs[-1]['ev'] == 'result', [e['ev'] for e in evs]
    for e in evs:
        assert not events.check_event(e), (e, events.check_event(e))
    kinds = [e['ev'] for e in evs]
    if 'plan' in kinds:
        first_stage = min([i for i, k in enumerate(kinds) if k in ('stage', 'progress')] or [len(kinds)])
        assert kinds.index('plan') < first_stage
    ts = [e['t'] for e in evs]
    assert ts == sorted(ts)
    return {e['ev']: e for e in evs}


def setup(td):
    td = Path(td)
    xml2 = B.make_xml2(td / 'X-Men Legends II')
    (td / 'discs').mkdir()
    iso = B.make_iso(td / 'discs' / 'xml1.iso')
    return xml2, iso, td / 'X-Men Legends (Port)', td / 'cache'


def build_argv(xml2, iso, out, cache, *extra):
    return ['build', '--iso', str(iso), '--xml2', str(xml2), '--out', str(out), '--cache', str(cache),
            '--events', 'jsonl', '--allow-unknown-exe', *extra]


def test_version_and_usage():
    code, evs, _ = run(['--version', '--events', 'jsonl'])
    assert code == 0 and [e['ev'] for e in evs] == ['hello', 'result'] and evs[1]['version'] == evs[0]['builder']
    code, evs, _ = run(['build', '--events', 'jsonl', '--bogus'])
    assert code == 2 and evs[-2]['code'] == 'E_USAGE' and evs[-1]['exit'] == 2
    code, evs, _ = run(['--events', 'jsonl'])
    assert code == 2 and evs[-2]['code'] == 'E_USAGE'
    code, evs, _ = run(['clean', '--events', 'jsonl'])
    assert code == 2 and evs[-2]['code'] == 'E_USAGE'


def test_build_verify_repair_clean():
    with tempfile.TemporaryDirectory() as td:
        xml2, iso, out, cache = setup(td)
        code, evs, err = run(build_argv(xml2, iso, out, cache))
        assert code == 0, err
        last = check_stream(evs)
        plan = [s['id'] for s in last['plan']['stages']]
        assert plan[0] == 'probe' and plan[-1] == 'finish' and not any(s['cached'] for s in last['plan']['stages'])
        done = [e['id'] for e in evs if e['ev'] == 'stage' and e['state'] == 'done']
        assert done == plan
        res = last['result']
        assert res['ok'] and res['exit'] == 0 and res['verify']['state'] == 'current'
        # warnings carry their count as data (check_stream: every warning has an integer detail.count)
        pipe = [e for e in evs if e['ev'] == 'warning' and e['code'] == 'W_PIPELINE']
        assert [(e['stage'], e['detail']['count'], e['count']) for e in pipe] == [('content', 2, 2), ('validate', 1, 1)]
        st = res['stamp']
        assert st['builder']['content_version'] == cli.CONTENT_VERSION and st['profile']['movies'] is True
        assert st['requires']['xml2fix'].startswith('>=') and st['finished'].endswith('Z')
        assert st['outputs']['bytes'] > 0 and st['source']['repo'].endswith('legends-classic')
        assert (out / '_build' / 'stamp.json').is_file() and not (out / '_build' / 'building.json').exists()
        assert not (out / '_build' / 'lock').exists() and not (cache / 'lock').exists()
        assert (out / '_build' / 'builder.log').is_file() and (out / '_build' / M.VERIFY_REPORT).is_file()
        assert not (out / '_build' / M.JOURNAL).exists()
        # the proxy files of the XML2 install are never copied; the port's keys are in the ini
        assert not (out / 'dinput.dll').exists() and not (out / 'mods').exists()
        assert 'NewGameTeam=wolverine' in (out / 'xml2-fix.ini').read_text()
        assert (cache / B.IDENT['disc_id'] / 'disc.json').is_file()
        man = M.load(out)
        assert {'XMen2.exe', 'Data/xml1/herostat_x1.txt', 'Movies/x1_intro.sfd'} <= set(man['files'])
        assert all(e['sha1'] and e['size'] >= 0 for e in man['files'].values())

        # the launcher / the player add their files: a rebuild keeps them and the launcher's ini keys
        (out / 'dinput.dll').write_bytes(b'xml2-fix')
        (out / 'xml2-fix.log').write_text('log')
        (out / 'mods' / 'My Mod').mkdir(parents=True)
        (out / 'mods' / 'My Mod' / 'readme.txt').write_text('mine')
        ini = out / 'xml2-fix.ini'
        ini.write_text(ini.read_text() + '[Display]\nMode=borderless\n; mine\n[Discord]\nEnabled=0\n')
        code, evs, _ = run(['verify', '--out', str(out), '--events', 'jsonl'])
        v = check_stream(evs)['result']['verify']
        assert code == 0 and v['state'] == 'current' and v['counts'].get('extra') is None, v

        # damage: a missing file, a changed byte, a stray file
        (out / 'Data' / 'xml1' / 'herostat_x1.txt').unlink()
        p = out / 'Scripts' / 'x1' / 'menus' / 'postgame.py'
        p.write_bytes(b'X' + p.read_bytes()[1:])
        (out / 'Data' / 'stray.txt').write_text('not ours')
        code, evs, _ = run(['verify', '--out', str(out), '--events', 'jsonl', '--xml2', str(xml2)])
        v = check_stream(evs)['result']['verify']
        assert code == 0 and v['state'] == 'damaged'
        groups = {g['code']: g for g in v['groups']}
        assert groups['missing']['files'][0]['path'] == 'Data/xml1/herostat_x1.txt'
        ch = groups['changed']['files'][0]
        assert ch['path'] == 'Scripts/x1/menus/postgame.py' and ch['expected']['sha1'] != ch['found']['sha1']
        assert groups['extra']['files'][0]['path'] == 'Data/stray.txt'
        assert all(g['cause_hint'] for g in v['groups']) and v['counts']['missing'] == 1
        rep = json.loads((out / '_build' / M.VERIFY_REPORT).read_text())
        assert rep['state'] == 'damaged' and rep['counts']['changed'] == 1
        assert str(Path(td)) not in json.dumps(rep)                     # relative paths only

        # the repair is a rebuild: the damage is gone, the stray file swept, the player's files kept
        code, evs, _ = run(build_argv(xml2, iso, out, cache))
        last = check_stream(evs)
        assert code == 0 and all(s['cached'] for s in last['plan']['stages'] if s['id'] in
                                 ('extract', 'tables', 'scripts', 'sound', 'music'))
        assert (out / 'Data' / 'xml1' / 'herostat_x1.txt').is_file() and not (out / 'Data' / 'stray.txt').exists()
        assert (out / 'dinput.dll').read_bytes() == b'xml2-fix' and (out / 'mods' / 'My Mod' / 'readme.txt').is_file()
        text = ini.read_text()
        assert 'Mode=borderless' in text and '; mine' in text and 'Enabled=0' in text and 'NewGameTeam=wolverine' in text
        code, evs, _ = run(['verify', '--out', str(out), '--events', 'jsonl'])
        assert evs[-1]['verify']['state'] == 'current'

        # a base file damaged with its size and mtime kept: the build's final verification copies it again
        exe = out / 'XMen2.exe'
        st = exe.stat()
        exe.write_bytes(b'Z' + exe.read_bytes()[1:])
        os.utime(exe, ns=(st.st_atime_ns, st.st_mtime_ns))
        code, evs, _ = run(build_argv(xml2, iso, out, cache))
        assert code == 0 and evs[-1]['verify']['repaired'] == 1
        assert exe.read_bytes() == (xml2 / 'XMen2.exe').read_bytes()
        # a module's copy that does not match its source is copied again from it
        code, evs, _ = run(build_argv(xml2, iso, out, cache), stub={'corrupt_copy': True})
        assert code == 0 and evs[-1]['verify']['repaired'] == 1
        assert (out / 'Sounds' / 'eng' / 'x1' / 'copied.zss').read_bytes().startswith(b'copied from')

        # clean: only the build goes; mods stay without --mods; the launcher's files are the launcher's
        code, evs, _ = run(['clean', '--out', str(out), '--events', 'jsonl', '--dry-run'])
        assert code == 0 and evs[-1]['clean']['files'] > 0 and (out / 'XMen2.exe').exists()
        code, evs, _ = run(['clean', '--out', str(out), '--events', 'jsonl'])
        c = evs[-1]['clean']
        assert code == 0 and not c['failed']
        left = sorted(p.relative_to(out).as_posix() for p in out.rglob('*'))
        assert left == ['dinput.dll', 'mods', 'mods/My Mod', 'mods/My Mod/readme.txt', 'xml2-fix.ini', 'xml2-fix.log']
        assert (xml2 / 'XMen2.exe').is_file() and (cache / B.IDENT['disc_id']).is_dir()
        # Free up: the cache only
        code, evs, _ = run(['clean', '--cache', str(cache), '--events', 'jsonl'])
        assert code == 0 and evs[-1]['clean']['cache_bytes'] > 0 and not (cache / B.IDENT['disc_id']).exists()


def test_cancel_at_every_stage_then_resume():
    stages = ['extract', 'tables', 'scripts', 'sound', 'music', 'sync', 'content', 'sweep', 'validate', 'finish']
    with tempfile.TemporaryDirectory() as td:
        xml2, iso, out, cache = setup(td)
        for sid in stages:
            code, evs, err = run(build_argv(xml2, iso, out, cache), stub={'cancel_at': sid})
            check_stream(evs)
            assert code == 5 and evs[-1]['exit'] == 5 and evs[-1]['cancelled'], (sid, evs[-3:], err[-500:])
            assert (out / '_build' / 'building.json').is_file() and not (out / '_build' / 'stamp.json').exists()
            assert not (out / '_build' / 'lock').exists() and not (cache / 'lock').exists()
            code, evs, _ = run(['info', '--out', str(out), '--events', 'jsonl'])
            assert evs[-1]['info']['out']['state'] == 'incomplete'
        # an interrupted build is still the builder's: clean would know its files (journal)
        assert M.read_journal(out)
        code, evs, _ = run(build_argv(xml2, iso, out, cache))
        plan = next(e for e in evs if e['ev'] == 'plan')
        assert code == 0 and all(s['cached'] for s in plan['stages'] if s['id'] in stages[:5]), plan
        code, evs, _ = run(['info', '--out', str(out), '--events', 'jsonl'])
        assert evs[-1]['info']['out']['state'] == 'current'


def test_failures_and_exit_codes():
    with tempfile.TemporaryDirectory() as td:
        xml2, iso, out, cache = setup(td)
        for knob, code_want, err_want in (({'fail_stage': 'sound'}, 1, 'E_PIPELINE'),
                                          ({'validate_errors': 3}, 1, 'E_VALIDATE'),
                                          ({'io_stage': 'content'}, 6, 'E_IO'),
                                          ({'crash_stage': 'sweep'}, 70, 'E_INTERNAL'),
                                          ({'corrupt_after_write': 'UI/menus/x1_main.txt'}, 6, 'E_IO')):
            code, evs, err = run(build_argv(xml2, iso, out, cache), stub=knob)
            last = check_stream(evs)
            assert code == code_want and last['error']['code'] == err_want, (knob, code, last.get('error'), err[-800:])
            assert last['result']['exit'] == code_want and not (out / '_build' / 'lock').exists()
            assert (out / '_build' / 'building.json').is_file()
        assert "'E_PIPELINE'" not in err
        # the disc image missing, the XML2 install missing / not English / an unknown exe
        code, evs, _ = run(build_argv(xml2, Path(td) / 'gone.iso', out, cache))
        assert code == 3 and evs[-2]['code'] == 'E_ISO_NOT_FOUND'
        code, evs, _ = run(build_argv(Path(td) / 'nothing', iso, out, cache))
        assert code == 3 and evs[-2]['code'] == 'E_XML2_NOT_FOUND'
        argv = [a for a in build_argv(xml2, iso, out, cache) if a != '--allow-unknown-exe']
        code, evs, _ = run(argv)
        assert code == 3 and evs[-2]['code'] == 'E_XML2_UNKNOWN_EXE' and evs[-2]['detail']['exe_md5']


def test_destination_rules_and_lock():
    with tempfile.TemporaryDirectory() as td:
        xml2, iso, out, cache = setup(td)
        foreign = Path(td) / 'Documents'
        foreign.mkdir()
        (foreign / 'letter.txt').write_text('mine')
        code, evs, _ = run(build_argv(xml2, iso, foreign, cache))
        assert code == 2 and evs[-2]['code'] == 'E_OUT_FOREIGN' and (foreign / 'letter.txt').is_file()
        code, evs, _ = run(build_argv(xml2, iso, xml2 / 'port', cache))
        assert code == 2 and evs[-2]['code'] == 'E_OUT_UNSAFE'
        code, evs, _ = run(build_argv(xml2, iso, cache / 'port', cache))
        assert code == 2 and evs[-2]['code'] == 'E_OUT_UNSAFE'
        code, evs, _ = run(build_argv(xml2, iso, iso.parent, cache))
        assert code == 2 and evs[-2]['code'] in ('E_OUT_UNSAFE', 'E_OUT_FOREIGN')
        code, evs, _ = run(['clean', '--out', str(foreign), '--events', 'jsonl'])
        assert code == 2 and evs[-2]['code'] == 'E_OUT_FOREIGN' and (foreign / 'letter.txt').is_file()
        code, evs, _ = run(['info', '--out', str(foreign), '--events', 'jsonl'])
        assert evs[-1]['info']['out']['state'] == 'foreign'
        # a folder holding only the launcher's / the player's files (and a stray _build/) is fine: info calls it
        # absent, as build accepts it
        pre = Path(td) / 'pre'
        for rel in ('dinput.dll', 'xml2-fix.ini', 'xml2-fix.log', 'mods/My Mod/readme.txt', '_build/old.txt'):
            (pre / rel).parent.mkdir(parents=True, exist_ok=True)
            (pre / rel).write_bytes(b'x')
        code, evs, _ = run(['info', '--out', str(pre), '--events', 'jsonl'])
        assert code == 0 and evs[-1]['info']['out']['state'] == 'absent', evs[-1]
        code, evs, _ = run(['verify', '--out', str(pre), '--events', 'jsonl'])
        assert evs[-1]['verify']['state'] == 'absent'
        code, evs, _ = run(build_argv(xml2, iso, pre, cache))
        assert code == 0 and (pre / 'dinput.dll').read_bytes() == b'x'
        # a live lock holder: E_OUT_LOCKED; a dead one is taken over
        code, evs, _ = run(build_argv(xml2, iso, out, cache))
        assert code == 0
        import subprocess
        holder = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        try:
            (out / '_build' / 'lock').write_text(json.dumps({'pid': holder.pid}))
            code, evs, _ = run(build_argv(xml2, iso, out, cache))
            assert code == 2 and evs[-2]['code'] == 'E_OUT_LOCKED' and evs[-2]['detail']['pid'] == holder.pid
            (out / '_build' / 'lock').unlink()
            (cache / 'lock').write_text(json.dumps({'pid': holder.pid}))
            code, evs, _ = run(build_argv(xml2, iso, out, cache))
            assert code == 2 and evs[-2]['code'] == 'E_CACHE_LOCKED'
        finally:
            holder.kill()
            holder.wait()
        code, evs, _ = run(build_argv(xml2, iso, out, cache))            # the holder is gone: taken over
        assert code == 0 and not (cache / 'lock').exists()


def test_info_states_and_no_iso():
    with tempfile.TemporaryDirectory() as td:
        xml2, iso, out, cache = setup(td)
        code, evs, _ = run(['info', '--out', str(out), '--cache', str(cache), '--events', 'jsonl'])
        info = evs[-1]['info']
        assert code == 0 and info['out']['state'] == 'absent' and info['cache']['bytes'] == 0 and 'iso' not in info
        code, evs, _ = run(['info', '--iso', str(iso), '--xml2', str(xml2), '--out', str(out), '--cache', str(cache),
                            '--allow-unknown-exe', '--events', 'jsonl'])
        info = check_stream(evs)['result']['info']
        assert info['iso']['known'] and info['xml2']['base_files'] == 5 and 'estimate' in info and 'space' in info
        assert run(build_argv(xml2, iso, out, cache, '--no-movies'))[0] == 0
        code, evs, _ = run(['info', '--out', str(out), '--cache', str(cache), '--events', 'jsonl'])
        info = evs[-1]['info']
        assert info['out']['state'] == 'current' and info['out']['stamp']['profile']['movies'] is False
        assert info['cache']['stages'] == ['extract', 'tables', 'scripts', 'sound', 'music']
        # a newer content version makes the build stale
        st = json.loads((out / '_build' / 'stamp.json').read_text())
        st['builder']['content_version'] = 0
        (out / '_build' / 'stamp.json').write_text(json.dumps(st))
        code, evs, _ = run(['info', '--out', str(out), '--events', 'jsonl'])
        assert evs[-1]['info']['out']['state'] == 'stale'
        # a rebuild without --iso takes the disc from the cache
        argv = [a for a in build_argv(xml2, iso, out, cache, '--no-movies')]
        i = argv.index('--iso')
        del argv[i:i + 2]
        code, evs, err = run(argv)
        assert code == 0, err
        code, evs, _ = run(['info', '--out', str(out), '--events', 'jsonl'])
        assert evs[-1]['info']['out']['state'] == 'current'


def test_held_stray_is_named_by_a_warning():
    """a file the build did not make that another program holds open: the rebuild can't delete it, still succeeds
    (exit 0) and names it (W_EXTRA_FILES: detail.not_removed, the cause); the next rebuild removes it."""
    with tempfile.TemporaryDirectory() as td:
        xml2, iso, out, cache = setup(td)
        assert run(build_argv(xml2, iso, out, cache))[0] == 0
        stray = out / 'Data' / 'stray-held-open.txt'
        stray.write_text('held by another program')
        with B.held_open(stray) as real:
            code, evs, err = run(build_argv(xml2, iso, out, cache), stub=None if real else {'busy': 'Data/stray-held-open.txt'})
        last = check_stream(evs)
        assert code == 0 and last['result']['ok'], (last.get('error'), err[-800:])
        extra = [e for e in evs if e['ev'] == 'warning' and e['code'] == 'W_EXTRA_FILES']
        assert len(extra) == 1 and stray.is_file(), extra
        w = extra[0]
        assert w['detail']['files'] == w['detail']['not_removed'] == ['Data/stray-held-open.txt'] and w['detail']['count'] == 1
        assert w['detail']['cause'] == 'held' and w['msg'].startswith('1 file(s) ') and 'another program has it open' in w['msg']
        code, evs, _ = run(['verify', '--out', str(out), '--events', 'jsonl'])
        assert evs[-1]['verify']['state'] == 'current' and evs[-1]['verify']['counts']['extra'] == 1
        code, evs, _ = run(build_argv(xml2, iso, out, cache))              # released: the rebuild removes it
        assert code == 0 and not stray.exists() and not any(e.get('code') == 'W_EXTRA_FILES' for e in evs)


def test_os_io_errors_in_the_modules_are_e_io():
    """an OS-level I/O error in a content module (a file held open, a full disk - also wrapped by the module) is E_IO
    (exit 6) naming the file relative to the game folder and the cause; a module's other errors stay E_PIPELINE."""
    import errno

    def held_write(ctx, job):                          # a module writing a file another program holds open
        target = Path(job.out) / 'Data' / 'held.bin'
        if os.name == 'nt':
            ctx.write_bytes('Data/held.bin', b'new content')             # real: os.replace -> WinError 5
            raise AssertionError('a file another program holds open was replaced')
        raise OSError(errno.EBUSY, 'Device or resource busy', str(target))   # POSIX replaces open files

    def full_disk(ctx, job):
        try:
            raise OSError(errno.ENOSPC, 'No space left on device', str(Path(job.out) / 'Data' / 'x1.igb.tmp12_34'))
        except OSError as e:
            raise RuntimeError('the module wrapped it') from e

    def missing(ctx, job):
        raise FileNotFoundError(errno.ENOENT, 'No such file or directory', str(Path(job.out) / 'Data' / 'nope.bin'))

    with tempfile.TemporaryDirectory() as td:
        xml2, iso, out, cache = setup(td)
        assert run(build_argv(xml2, iso, out, cache))[0] == 0
        held = out / 'Data' / 'held.bin'
        held.write_bytes(b'old')
        with B.held_open(held):
            code, evs, err = run(build_argv(xml2, iso, out, cache), stub={'module_fn': held_write})
        e = check_stream(evs)['error']
        assert code == 6 and e['code'] == 'E_IO' and e['stage'] == 'content', (e, err[-1500:])
        assert e['detail']['path'] == 'Data/held.bin' and e['detail']['where'] == 'out' and e['detail']['cause'] == 'held'
        assert e['msg'] == 'A file could not be read or written: Data/held.bin (another program has it open).', e
        assert 'bug in the builder' not in e['hint'] and held.read_bytes() == b'old'
        code, evs, _ = run(build_argv(xml2, iso, out, cache), stub={'module_fn': full_disk})
        e = check_stream(evs)['error']
        assert code == 6 and e['code'] == 'E_IO' and e['detail']['cause'] == 'disk_full' and e['detail']['path'] == 'Data/x1.igb'
        code, evs, _ = run(build_argv(xml2, iso, out, cache), stub={'module_fn': missing})
        e = check_stream(evs)['error']
        assert code == 1 and e['code'] == 'E_PIPELINE' and e['detail']['module'] == 'stub_module'
        assert run(build_argv(xml2, iso, out, cache))[0] == 0


def test_profile_paths_masked_in_every_message():
    """E_ISO_NOT_FOUND's text named the disc image with the profile folder unmasked: no event, human line or log line
    of the builder shows the profile folder."""
    def strings(obj):
        if isinstance(obj, str):
            return [obj]
        if isinstance(obj, dict):
            return [s for v in obj.values() for s in strings(v)]
        if isinstance(obj, list):
            return [s for v in obj for s in strings(v)]
        return []

    saved = {k: os.environ.get(k) for k in ('USERPROFILE', 'HOME')}
    with tempfile.TemporaryDirectory() as td:
        prof = Path(td).resolve()
        forms = {str(prof).lower(), prof.as_posix().lower(), str(prof).replace('\\', '\\\\').lower()}
        os.environ['USERPROFILE'] = os.environ['HOME'] = str(prof)
        try:
            xml2, iso, out, cache = setup(prof)
            code, evs, err = run(build_argv(xml2, prof / 'gone.iso', out, cache))
            e = evs[-2]
            assert code == 3 and e['code'] == 'E_ISO_NOT_FOUND' and '%USERPROFILE%' in e['msg'], e
            texts = [s.lower() for s in strings(evs)] + [err.lower()]
            assert not any(f in s for f in forms for s in texts), [s for s in texts if any(f in s for f in forms)]
            code, evs, err = run(build_argv(xml2, iso, out, cache))
            assert code == 0
            texts = [s.lower() for s in strings(evs)] + [err.lower(), (out / '_build' / 'builder.log').read_text().lower()]
            assert not any(f in s for f in forms for s in texts)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def test_hard_stop_when_cancel_is_ignored():
    """a stage that never reaches a checkpoint: the watchdog emits the result and exits with 5."""
    from xml1builder.cancel import CancelToken
    exited = []
    done = threading.Event()

    def fake_exit(code):
        exited.append(code)
        done.set()

    tok = CancelToken(grace=0.3, exit_fn=fake_exit)
    stopped = []
    tok.on_hard_stop(lambda: stopped.append(True))
    tok.set('cancel')
    assert done.wait(3) and exited == [5] and stopped == [True]
    tok2 = CancelToken(grace=0.3, exit_fn=fake_exit)
    tok2.set('cancel')
    tok2.finished()                                   # the command ended in time: no hard stop
    threading.Event().wait(0.6)
    assert exited == [5]


def test_text_mode_and_log():
    with tempfile.TemporaryDirectory() as td:
        xml2, iso, out, cache = setup(td)
        argv = [a for a in build_argv(xml2, iso, out, cache) if a not in ('--events', 'jsonl')]
        out_s, err_s = io.StringIO(), io.StringIO()
        saved = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out_s, err_s
        try:
            code = cli.main(argv, pipeline_factory=B.StubPipeline, stdin=Stdin(), fd_redirect=False)
        finally:
            sys.stdout, sys.stderr = saved
        text = out_s.getvalue()
        assert code == 0 and '== Reading the disc' in text and 'result: ok' in text and '{"ev"' not in text
        log = (out / '_build' / 'builder.log').read_text(encoding='utf-8')
        assert '"ev": "plan"' in log and 'Legends Classic xml1-builder' in log and '"ev": "progress"' not in log
        # the second build rotates the log
        assert run(build_argv(xml2, iso, out, cache))[0] == 0
        assert (out / '_build' / 'builder.1.log').is_file()
