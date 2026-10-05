"""The builder's pieces without game data (BUILDER_DESIGN.md 6.1): the event schema and writer, the plan / progress
arithmetic, locks, the state machine, cancel, the ini merge, the keep-proxy sweep and builder mode in
xml1build.common (registry sha1 + read-back), the manifest checks, the disc / XML2 identification on synthetic
inputs."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import builder_stub as B
import synth
from xml1build import common as C, fix_ini as FI
from xml1builder import cancel as CA, events as E, inputs as I, lock as L, manifest as M, plan as PL, stamp as S
from xml1builder.errors import BuilderError, Cancelled, exit_for


# ------------------------------------------------------------------------------------------------ events
def test_event_writer_jsonl_and_schema():
    out, err = io.StringIO(), io.StringIO()
    o = E.Output(jsonl=True, stdout=out, stderr=err)
    o.event('hello', v=1, builder='0.1.0', content_version=1, commit='abc', pid=1)
    o.event('progress', stage='sync', done=1, total=2, unit='files', pct=50.0, overall=10.0, eta_s=5)
    o.human('a human line')
    o.capture_stdout(fd_redirect=False)
    try:
        print('[zones] printed by the pipeline')
    finally:
        o.restore_stdout()
    lines = out.getvalue().splitlines()
    assert len(lines) == 2 and all(not E.check_event(json.loads(x)) for x in lines)
    assert 'a human line' in err.getvalue() and '[zones] printed by the pipeline' in err.getvalue()
    assert E.check_event({'ev': 'progress', 't': 1, 'stage': 's', 'done': 1, 'total': 2, 'unit': '', 'pct': 1,
                          'overall': 120, 'eta_s': 1})
    assert E.check_event({'ev': 'nope', 't': 0})
    assert E.check_event({'ev': 'error', 't': 0, 'stage': 'p', 'code': 'E', 'msg': 'm', 'hint': '', 'detail': []})


def test_log_rotation_and_mask():
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / 'builder.log'
        for i in range(4):
            o = E.Output(jsonl=True, stdout=io.StringIO(), stderr=io.StringIO())
            o.human(f'run {i}')
            o.open_log(log, rotate=True)
            o.close()
        assert 'run 3' in log.read_text() and 'run 2' in (Path(td) / 'builder.1.log').read_text()
        assert 'run 1' in (Path(td) / 'builder.2.log').read_text() and not (Path(td) / 'builder.3.log').exists()
    prof = os.environ.get('USERPROFILE') or os.environ.get('HOME')
    if prof and len(prof) > 3:
        assert E.mask(prof + '\\x.iso') == '%USERPROFILE%\\x.iso'


def test_mask_every_message():
    """one helper (events.mask) masks the profile folder in every event field and every human / log line: any case,
    either separator, doubled backslashes (a repr), never a longer folder name."""
    saved = {k: os.environ.get(k) for k in ('USERPROFILE', 'HOME')}
    prof, home = 'D:\\Profiles\\Test User', '/srv/profiles/test user'     # placeholders, no real profile folder
    os.environ['USERPROFILE'], os.environ['HOME'] = prof, home
    try:
        assert E.mask(prof + '\\x.iso') == '%USERPROFILE%\\x.iso' and E.mask(prof) == '%USERPROFILE%'
        assert E.mask('d:\\profiles\\TEST USER\\x') == '%USERPROFILE%\\x' and E.mask('D:/Profiles/Test User/x') == '%USERPROFILE%/x'
        assert E.mask(repr({'p': prof + '\\x'})) == repr({'p': '%USERPROFILE%\\x'})
        assert E.mask(prof + 's\\x') == prof + 's\\x'                                    # another user's folder
        assert E.mask(home + '/.cache (the cache).') == '%USERPROFILE%/.cache (the cache).'
        assert E.mask_all({'a': [prof, (Path(home) / 'x', 3)], 'b': None}) == \
            {'a': ['%USERPROFILE%', [E.mask(Path(home) / 'x'), 3]], 'b': None}
        with tempfile.TemporaryDirectory() as td:
            out, err = io.StringIO(), io.StringIO()
            o = E.Output(jsonl=True, stdout=out, stderr=err, log_file=Path(td) / 'builder.log')
            o.event('error', stage='probe', code='E_ISO_NOT_FOUND', msg=f'No such file: {prof}\\x.iso.', hint='',
                    detail={'path': prof + '\\x.iso', 'list': [prof + '\\y']})
            o.event('warning', stage='finish', code='W_X', msg=f'{prof}\\z')
            o.human(f'[prepare] disc: using {prof}\\AppData\\Local\\cache')
            o.close()
            text = out.getvalue() + err.getvalue() + (Path(td) / 'builder.log').read_text(encoding='utf-8')
        assert 'test user' not in text.lower() and text.count('%USERPROFILE%') == 10, text
        warning = json.loads(out.getvalue().splitlines()[1])
        assert warning['detail'] == {'count': 1} and not E.check_event(warning)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    assert E.check_event({'ev': 'warning', 't': 0, 'stage': 's', 'code': 'W', 'msg': 'm'})      # no detail.count


# ------------------------------------------------------------------------------------------------ plan
def test_weights_estimate_and_plan():
    w4 = PL.weights(jobs=4)
    w16 = PL.weights(jobs=16)
    assert w4['music'] == 95.0 and w16['music'] == 60.0 and w4['sound'] == 29.0 and w16['sound'] == 17.0
    assert PL.weights(jobs=4, kernel=False)['music'] == 665.0
    assert PL.weights(synced=True)['sync'] < PL.weights()['sync']
    est = PL.estimate(jobs=8)
    assert est['first_build_s'] > est['rebuild_s'] > 60
    plan = PL.make_plan(w4, {'extract', 'tables'})
    assert [s['id'] for s in plan] == list(PL.STAGE_IDS) and plan[1]['cached'] and not plan[3]['cached']
    assert all(isinstance(s['weight'], int) and s['weight'] >= 1 for s in plan)


def test_progress_overall_eta_rate_limit_and_tick():
    now = [0.0]
    sent = []
    plan = [{'id': 'a', 'weight': 10, 'cached': False}, {'id': 'b', 'weight': 30, 'cached': False},
            {'id': 'c', 'weight': 99, 'cached': True}]
    p = PL.Progress(plan, lambda **f: sent.append(f), clock=lambda: now[0])
    p.start('a')
    p.update('a', 1, 10)
    p.update('a', 2, 10)                          # within 0.25 s: dropped
    assert len(sent) == 1 and sent[0]['done'] == 1 and sent[0]['unit'] == 'checks' or sent[0]['unit'] == ''
    now[0] = 20.0                                 # a took twice its prediction
    p.update('a', 10, 10)
    assert sent[-1]['done'] == 10 and sent[-1]['pct'] == 100.0
    p.finish('a')
    total = 10 + 30 + PL.CACHED_WEIGHT
    assert abs(p.overall() - 100 * 10 / total) < 0.01
    assert p.speed() == 2.0 and p.eta() == int(round((30 + PL.CACHED_WEIGHT) * 2.0))
    p.start('b')
    now[0] = 30.0                                 # no counter for 10 s: the ticker's time-based fraction
    p.tick()
    assert sent[-1]['stage'] == 'b' and sent[-1]['total'] == 0 and 0 < sent[-1]['pct'] <= 95
    before = p.overall()
    p.update('b', 0, 100)                         # a counter below the time-based guess never moves overall back
    assert p.overall() >= before
    for f in sent:
        assert not E.check_event(dict(f, ev='progress', t=0)), f
    # a stage with its own counter (P5's banks) is never guessed, even before its first bank is done
    q = PL.Progress([{'id': 'music', 'weight': 90, 'cached': False}], lambda **f: sent.append(f), clock=lambda: now[0])
    q.start('music')
    now[0] += 60
    q.tick()
    assert q.frac['music'] == 0.0
    q.update('music', 2, 61)
    assert abs(q.frac['music'] - 2 / 61) < 1e-9


# ------------------------------------------------------------------------------------------------ locks
def test_lock_exclusive_stale_and_old_format():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'lock'
        a = L.FileLock(path, 'build').acquire()
        holder = json.loads(path.read_text())
        assert holder['pid'] == os.getpid() and a.held
        try:
            L.FileLock(path).acquire()          # our own pid is alive
            raise AssertionError('acquired twice')
        except L.LockHeld as e:
            assert e.holder['pid'] == os.getpid()
        a.release()
        assert not path.exists()
        dead = subprocess.Popen([sys.executable, '-c', 'pass'])
        dead.wait()
        path.write_text(str(dead.pid))           # the fake builder's format, a dead holder
        with L.FileLock(path) as b:
            assert b.held and json.loads(path.read_text())['pid'] == os.getpid()
        assert not path.exists()
        live = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        try:
            path.write_text(json.dumps({'pid': live.pid, 'started': L.process_started(live.pid)}))
            try:
                L.FileLock(path).acquire()
                raise AssertionError('took a live lock')
            except L.LockHeld:
                pass
            if os.name == 'nt':                    # the same pid with another start time: a recycled pid
                path.write_text(json.dumps({'pid': live.pid, 'started': 12345}))
                with L.FileLock(path):
                    pass
        finally:
            live.kill()
            live.wait()


# ------------------------------------------------------------------------------------------------ state machine
def test_out_states():
    prof = {'frontend': 'xml1', 'tiles': 'used'}
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / 'port'
        assert S.out_state(out, content_version=2)[0] == 'absent'
        out.mkdir()
        assert S.out_state(out, content_version=2)[0] == 'absent'
        # the launcher's / the player's files and build metadata only: absent (as build accepts it), not foreign
        for rel in ('dinput.dll', 'XML2-FIX.ini', 'xml2-fix.log', 'mods/My Mod/a.txt', '_build/x.json'):
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_text('x')
        assert S.out_state(out, content_version=2) == ('absent', [], None) and not M.has_area_files(out)
        (out / 'mods' / 'b').mkdir()
        (out / 'Data').mkdir()
        assert S.out_state(out, content_version=2)[0] == 'absent'                   # (an empty folder is no file)
        (out / 'Data' / 'y.txt').write_text('y')
        assert S.out_state(out, content_version=2)[0] == 'foreign' and M.has_area_files(out)
        (out / 'Data' / 'y.txt').unlink()
        shutil.rmtree(out / '_build')
        (out / 'x.txt').write_text('x')
        assert S.out_state(out, content_version=2)[0] == 'foreign'
        (out / '_build').mkdir()
        assert S.out_state(out, content_version=2)[0] == 'foreign'          # a build_xml1.py folder is not ours
        S.start_building(out, {'inputs': {}})
        assert S.out_state(out, content_version=2)[0] == 'incomplete'
        st = S.make_stamp(version={'version': '1', 'commit': 'c', 'content_version': 2}, profile=prof, movies=True,
                          disc={'digest': 'D'}, xml2={'base_digest': 'X'}, requires={}, outputs={}, result={})
        S.write_json(out / '_build' / 'stamp.json', st)
        assert S.out_state(out, content_version=2)[0] == 'incomplete'        # building.json still there
        S.end_building(out)
        assert S.out_state(out, content_version=2, profile=prof, disc_digest='D', xml2_digest='X')[0] == 'current'
        state, reasons, _ = S.out_state(out, content_version=3, profile=dict(prof, tiles='folder'), disc_digest='E',
                                        xml2_digest='Y')
        assert state == 'stale' and len(reasons) == 4, reasons


# ------------------------------------------------------------------------------------------------ cancel
def test_cancel_token_and_stdin():
    tok = CA.CancelToken(grace=60)
    assert not tok.is_set() and not tok()
    tok.check()
    CA.watch_stdin(tok, io.StringIO('hello\n  CANCEL \n')).join(2)
    assert tok.is_set() and tok.reason == 'cancel'
    try:
        tok.check()
        raise AssertionError('no Cancelled')
    except Cancelled:
        pass
    tok.finished()
    eof = CA.CancelToken(grace=60)
    CA.watch_stdin(eof, io.StringIO('')).join(2)
    assert eof.is_set() and eof.reason == 'eof'
    eof.finished()
    # prepare.check_cancel takes the token
    from xml1build import prepare
    try:
        prepare.check_cancel(eof)
        raise AssertionError('prepare did not see the cancel')
    except prepare.Cancelled:
        pass
    assert issubclass(Cancelled, BaseException) and not issubclass(Cancelled, Exception)


def test_os_io_errors_name_the_file_and_the_cause():
    import errno
    from types import SimpleNamespace
    from xml1build import prepare
    from xml1builder import commands as CMD, errors as ER
    with tempfile.TemporaryDirectory() as td:
        out, cache = Path(td) / 'out', Path(td) / 'cache'
        (out / 'Data').mkdir(parents=True)
        (cache / 'disc1').mkdir(parents=True)
        roots = [(out, 'out'), (cache, 'cache')]
        full = OSError(errno.ENOSPC, 'No space left on device', str(out / 'Data' / 'x1.igb.tmp12_34'))
        err = ER.io_error(full, 'content', roots)
        assert err.code == 'E_IO' and err.exit_code == 6 and err.stage == 'content' and 'space' in err.hint
        assert err.detail['path'] == 'Data/x1.igb' and err.detail['cause'] == 'disk_full' and err.detail['where'] == 'out'
        assert err.msg == 'A file could not be read or written: Data/x1.igb (the disk is full).'
        # os.replace(temp, file) names the file second; a read-only file
        ro = out / 'Data' / 'ro.bin'
        ro.write_bytes(b'r')
        os.chmod(ro, 0o444)
        try:
            e = PermissionError(errno.EACCES, 'Permission denied', str(ro) + '.tmp9', None, str(ro))
            if os.name == 'nt' or os.geteuid() != 0:
                assert ER.io_error(e, 'sync', roots).detail['cause'] == 'read_only'
        finally:
            os.chmod(ro, 0o666)
        if os.name == 'nt':                      # a file another program holds open: replace = 5, delete = 32
            held = out / 'Data' / 'held.bin'
            held.write_bytes(b'h')
            tmp = out / 'Data' / 'held.bin.tmp1_2'
            tmp.write_bytes(b'new')
            with B.held_open(held):
                for op in (lambda: os.replace(tmp, held), held.unlink):
                    try:
                        op()
                        raise AssertionError('a held file was replaced / deleted')
                    except PermissionError as e:
                        err = ER.io_error(e, 'content', roots)
                        assert err.detail['cause'] == 'held' and err.detail['path'] == 'Data/held.bin', err.detail
                        assert err.msg.endswith('Data/held.bin (another program has it open).')
        e = OSError(errno.EIO, 'Input/output error', str(cache / 'disc1' / 'bank.zss'))
        err = ER.io_error(e, 'music', roots)
        assert err.detail['where'] == 'cache' and err.detail['cause'] == 'disk_error' and 'disc1/bank.zss (in the build cache)' in err.msg
        # not an OS-level cause: a module's own FileNotFoundError is not mapped (E_PIPELINE); raised straight to the
        # builder it is still E_IO (its strerror), with the file named
        nf = FileNotFoundError(errno.ENOENT, 'No such file or directory', str(out / 'gone.bin'))
        assert ER.io_cause(nf) is None and ER.io_error(nf, 'x', roots) is None
        assert ER.io_error(nf, 'x', roots, strict=False).msg == 'A file could not be read or written: gone.bin (No such file or directory).'
        # wrapped (raise ... from): found in the chain; failure() maps it, also inside a StageFailed
        try:
            try:
                raise full
            except OSError as inner:
                raise prepare.StageFailed('E_PREPARE_MUSIC', 'a bank failed') from inner
        except prepare.StageFailed as sf:
            assert ER.io_in_chain(sf) is full
            job = SimpleNamespace(out=out, cache=cache, xml2=Path(td) / 'xml2')
            got = CMD.failure(sf, 'music', job)
            assert got.code == 'E_IO' and got.detail['path'] == 'Data/x1.igb' and got.stage == 'music'
        assert ER.io_in_chain(ValueError('x')) is None
        assert CMD.failure(prepare.StageFailed('E_PREPARE_MUSIC', 'x'), 'music').code == 'E_PIPELINE'
        assert CMD.failure(RuntimeError('x'), 'content').code == 'E_INTERNAL'
        assert ER.io_cause(C.WriteCheckError('a', 'b', 'c')) is None


def test_exit_codes():
    assert exit_for('E_ISO_WRONG_GAME') == 3 and exit_for('E_XML2_UNKNOWN_EXE') == 3 and exit_for('E_SPACE') == 4
    assert exit_for('E_OUT_LOCKED') == 2 and exit_for('E_CACHE_LOCKED') == 2 and exit_for('E_IO') == 6
    assert exit_for('E_INTERNAL') == 70 and exit_for('E_VALIDATE') == 1 and exit_for('E_CACHE_EMPTY') == 3
    assert BuilderError('E_PIPELINE', 'x').hint.startswith('This is a bug')


# ------------------------------------------------------------------------------------------------ ini
def test_ini_merge_keeps_foreign_keys_comments_and_endings():
    src = ('; the launcher\r\n[Display]\r\nMode=borderless\r\nWidth=0\r\n\r\n[Game]\r\n; comment\r\n'
           'newgameteam = storm\r\nAddHero=1\r\nXPCurve=xml1\r\n\r\n[Online]\r\nLocalIP=192.0.2.5\r\n')
    keys = {'Game': {'NewGameTeam': 'wolverine', 'ResetUnlocks': '0'}, 'Limits': {'ActorSlots': '127'},
            'Online': {'GameVersion': 'X1.0'}}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'xml2-fix.ini'
        p.write_bytes(src.encode('latin-1'))
        assert FI.merge_ini(p, keys, {'Game': ['XPCurve', 'PostgameScript']})
        text = p.read_bytes().decode('latin-1')
        assert '\n' not in text.replace('\r\n', '')                         # CRLF kept everywhere
        parsed = FI.parse_ini(text)
        assert parsed['Display'] == {'Mode': 'borderless', 'Width': '0'}
        assert parsed['Game']['newgameteam'] == 'wolverine' and parsed['Game']['ResetUnlocks'] == '0'
        assert parsed['Game']['AddHero'] == '1' and 'XPCurve' not in parsed['Game']       # dropped: only ours
        assert parsed['Online'] == {'LocalIP': '192.0.2.5', 'GameVersion': 'X1.0'}
        assert parsed['Limits'] == {'ActorSlots': '127'} and '; the launcher' in text and '; comment' in text
        assert not FI.merge_ini(p, keys)                                    # idempotent: nothing to change
        # LF files stay LF; UTF-16 files (WritePrivateProfileStringW) stay UTF-16
        q = Path(td) / 'lf.ini'
        q.write_bytes(b'[Display]\nMode=windowed\n')
        FI.merge_ini(q, keys)
        assert b'\r' not in q.read_bytes() and FI.read_ini(q)['Game']['NewGameTeam'] == 'wolverine'
        u = Path(td) / 'u16.ini'
        u.write_bytes(b'\xff\xfe' + '[Display]\r\nMode=fullscreen\r\n'.encode('utf-16-le'))
        FI.merge_ini(u, keys)
        assert u.read_bytes().startswith(b'\xff\xfe') and FI.read_ini(u)['Display']['Mode'] == 'fullscreen'
        n = Path(td) / 'new.ini'
        FI.merge_ini(n, keys)
        assert n.read_bytes().startswith(b'[Game]\r\n') and FI.read_ini(n)['Limits']['ActorSlots'] == '127'


def test_port_keys_from_a_synthetic_build():
    import xml.etree.ElementTree as ET
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        assert FI.port_keys(out) == {'Game': {'NewGameTeam': 'wolverine', 'ResetUnlocks': '0',
                                              'SaveFolder': 'X-Men Legends', 'ForcedTeams': '1',
                                              'GeometrySharingBlendIndices': '1', 'CharacterLadderPaths': '1',
                                              'ObjectiveDescriptions': '1'},
                                     'Limits': {'ActorSlots': '127', 'ResourceNames': '1024', 'ItemEnhancements': '512',
                                                'FightStyles': '32'}}
        menu = ET.Element('menu', type='MAIN_MENU')
        for i in range(1, 9):
            attrs = {'name': f'button{i}', 'text': f't{i}'}
            if i != 8:
                attrs['usecmd'] = 'x'
            ET.SubElement(menu, 'item', attrs)
        review = ET.Element('menu', type='REVIEW_PATHS_MENU')
        ET.SubElement(review, 'item', name='option01_text')
        for rel, root in ((FI.MAIN_MENU_FILE, menu), (FI.REVIEW_MENU_FILE, review)):
            p = out.joinpath(*rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(C.encode_xmlb(root))
        (out / 'Scripts' / 'x1' / 'menus').mkdir(parents=True)
        (out / 'Scripts' / 'x1' / 'menus' / 'postgame.py').write_bytes(b'x')
        (out / '_build').mkdir()
        (out / '_build' / 'report.json').write_text(json.dumps({'build': {'xp_curve': 'xml1', 'forced_teams': 'seat'}}))
        keys = FI.port_keys(out)
        g = keys['Game']
        assert g['MainMenuItems'] == 'button1,button2,button3,button4,button5,button6,button8,button7'
        assert g['PostgameScript'] == FI.POSTGAME_SCRIPT and g['WindowTitle'] == 'X-Men Legends'
        assert g['NewGamePlus'] == '0' and g['ReviewStats'] == '0' and g['XPCurve'] == 'xml1'
        assert keys['Online'] == {'GameVersion': 'X1.0'} and set(g) <= set(FI.PORT_OWNED['Game'])
        # the harness builds its test ini from the same keys
        sys.path.insert(0, str(Path(C.__file__).resolve().parents[1]))
        import harness
        text = harness.ini_text('windowed', 1, 1, False, save_folder='X-Men Legends', limits=True, postgame=FI.POSTGAME_SCRIPT,
                                main_menu_items=g['MainMenuItems'], xp_curve='xml1', new_game_plus='0',
                                port_identity=True, review_stats='0')
        parsed = FI.parse_ini(text)
        assert parsed['Game'] == g and parsed['Limits'] == keys['Limits'] and parsed['Online'] == keys['Online']


def test_harness_installs_write_the_shipped_limits_by_default():
    # test builds must run with the [Limits] every shipped build has; --stock-limits is the opt-out, --limits a no-op
    sys.path.insert(0, str(Path(C.__file__).resolve().parents[1]))
    import harness
    p = harness.parser()
    assert p.parse_args(['install', 'out']).stock_limits is False
    assert p.parse_args(['install', 'out', '--limits']).stock_limits is False
    assert p.parse_args(['install', 'out', '--stock-limits']).stock_limits is True


# ------------------------------------------------------------------------------------------------ builder mode in xml1build
def test_sweep_keeps_the_proxy_in_builder_mode_only():
    with tempfile.TemporaryDirectory() as td:
        base, out = Path(td) / 'base', Path(td) / 'out'
        for rel in ('XMen2.exe', 'Data/a.xmlb', 'dinput.dll', 'mods/m.txt', 'xml2-fix.ini'):
            (base / rel).parent.mkdir(parents=True, exist_ok=True)
            (base / rel).write_bytes(b'b')
        C.sync_base(base, out, log=lambda *a: None)
        assert not (out / 'dinput.dll').exists() and not (out / 'mods').exists()
        for rel in ('dinput.dll', 'xml2-fix.ini', 'xml2-fix.log', 'mods/My Mod/x.txt', 'Data/stray.txt',
                    '_build/stamp.json', '_build/lock'):
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_bytes(b'o')
        idx = C.FileIndex(base, exclude_top=C.PROXY_PATTERNS)
        removed = C.sweep_stale(out, idx, C.Registry(), keep_proxy=True, log=lambda *a: None)
        assert removed == ['Data/stray.txt']
        for rel in ('dinput.dll', 'xml2-fix.ini', 'xml2-fix.log', 'mods/My Mod/x.txt', '_build/stamp.json',
                    '_build/lock', 'XMen2.exe', 'Data/a.xmlb'):
            assert (out / rel).is_file(), rel
        removed = C.sweep_stale(out, idx, C.Registry(), log=lambda *a: None)           # build_xml1.py: as always
        assert sorted(removed) == ['dinput.dll', 'mods/My Mod/x.txt', 'xml2-fix.ini', 'xml2-fix.log']
        assert (out / '_build' / 'lock').is_file()
    assert set(M.OWNED_ROOT) == set(C.PROXY_PATTERNS) and set(M.META_ROOT) == set(C.META_NAMES)
    assert set(I.PROXY) == set(C.PROXY_PATTERNS)


def test_sweep_keeps_what_it_cannot_delete_and_v2_allows_it_in_builder_mode():
    import errno
    from xml1build import validate as VD
    with tempfile.TemporaryDirectory() as td:
        base, out = Path(td) / 'base', Path(td) / 'out'
        for rel in ('XMen2.exe', 'Data/a.xmlb'):
            (base / rel).parent.mkdir(parents=True, exist_ok=True)
            (base / rel).write_bytes(b'b')
        C.sync_base(base, out, log=lambda *a: None)
        held = out / 'Data' / 'held.txt'
        held.write_bytes(b'h')
        (out / 'Data' / 'gone.txt').write_bytes(b'g')
        idx = C.FileIndex(base, exclude_top=C.PROXY_PATTERNS)
        failed, lines = {}, []
        with B.held_open(held) as real:
            unlink = Path.unlink
            if not real:                           # POSIX deletes open files: the error a held file gives
                def busy(self, *a, **k):
                    if self.name == 'held.txt':
                        raise OSError(errno.EBUSY, 'Device or resource busy', str(self))
                    return unlink(self, *a, **k)
                Path.unlink = busy
            try:
                removed = C.sweep_stale(out, idx, C.Registry(), keep_proxy=True, log=lines.append, failed=failed)
            finally:
                Path.unlink = unlink
            assert removed == ['Data/gone.txt'] and list(failed) == ['Data/held.txt'] and held.is_file()
            from xml1builder import errors as ER
            assert ER.io_cause(failed['Data/held.txt']) == 'held' and 'cannot remove Data/held.txt' in lines[0]
        for mode in (False, True):                 # V2: an error (build_xml1.py), allowed in builder mode
            ctx = C.BuildContext(out, base, args=C.default_args(out=str(out), base=str(base), builder_mode=mode),
                                 sources=C.Sources.developer(base))
            ctx.shared['sweep_kept'] = sorted(failed)
            ck = VD.Check('V2', 'registry')
            VD.Validator(ctx).v2_registry(ck)
            assert bool(ck.errors) is not mode and bool(ck.allowed) is mode, (mode, ck.errors, ck.allowed)


def test_builder_mode_registry_sha1_and_checkpoint():
    with tempfile.TemporaryDirectory() as td:
        base, out = Path(td) / 'base', Path(td) / 'out'
        (base / 'Data').mkdir(parents=True)
        (base / 'XMen2.exe').write_bytes(b'exe')
        (base / 'Data' / 'b.bin').write_bytes(b'base')
        (out / 'mods').mkdir(parents=True)
        (out / 'mods' / 'x.txt').write_text('mine')
        src = Path(td) / 'src.bin'
        src.write_bytes(b'source bytes')
        sources = C.Sources.developer(base)
        for mode in (False, True):
            args = C.default_args(out=str(out), base=str(base), builder_mode=mode)
            ctx = C.BuildContext(out, base, args=args, sources=sources)
            assert ctx.check_writes is mode and (('mods/x.txt' in ctx.out_index) is (not mode))
            ctx.module = 'm'
            ctx.write_bytes('Data/new.bin', b'new')
            ctx.copy_file(src, 'Data/copy.bin')
            e1, e2 = ctx.registry.get('Data/new.bin'), ctx.registry.get('Data/copy.bin')
            # write_bytes records the sha1 of what it wrote; a copy's reference is its source (checked at the end)
            assert ('sha1' in e1) is mode and 'sha1' not in e2 and e2['source'] == str(src)
            if mode:
                import hashlib
                assert e1['sha1'] == hashlib.sha1(b'new').hexdigest()
        seen = []
        prev = C.set_checkpoint(lambda kind, d: seen.append((kind, d)))
        try:
            ctx.write_bytes('Data/c.bin', b'c')
            ctx.log('hello')
        finally:
            C.set_checkpoint(prev)
        assert ('write', 'Data/c.bin') in seen and ('log', ('m', 'hello')) in seen


# ------------------------------------------------------------------------------------------------ manifest
def test_manifest_check_groups_and_clean_targets():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        files = {}
        for rel, data in (('A.bin', b'a'), ('Data/B.bin', b'bb'), ('Data/C.bin', b'ccc')):
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_bytes(data)
            files[rel] = {'size': len(data), 'sha1': M.sha1_file(out / rel)[1], 'kind': 'built'}
        for rel in ('dinput.dll', 'xml2-fix.ini', 'mods/m/x.txt', '_build/stamp.json'):
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_bytes(b'owned')
        r = M.check_files(out, files, jobs=2)
        assert r['ok'] == 3 and not (r['missing'] or r['changed'] or r['extra'])
        (out / 'A.bin').unlink()
        (out / 'Data' / 'B.bin').write_bytes(b'bX')                     # same size, other bytes
        (out / 'Data' / 'C.bin').write_bytes(b'cccc')                   # other size
        (out / 'Data' / 'stray.txt').write_text('s')
        (out / 'Data' / 'D.bin.tmp123_456').write_text('t')
        r = M.check_files(out, files, jobs=2)
        assert [x['path'] for x in r['missing']] == ['A.bin']
        assert sorted(x['path'] for x in r['changed']) == ['Data/B.bin', 'Data/C.bin']
        assert sorted(x['path'] for x in r['extra']) == ['Data/D.bin.tmp123_456', 'Data/stray.txt']
        g = {x['code']: x for x in M.groups_of(r)}
        assert set(g) == {'missing', 'changed', 'extra'} and all(x['cause_hint'] for x in g.values())
        counts = M.counts_of(r, list(g.values()))
        assert counts == {'files': 3, 'ok': 0, 'missing': 1, 'changed': 2, 'extra': 2}
        # clean deletes the manifest's files, the journal's and temp files - never a stray file or an owned one
        M.save(out, files, builder='t')
        j = M.Journal(out).open()
        j.add('Data/journal_only.bin')
        j.close()
        (out / 'Data' / 'journal_only.bin').write_text('j')
        t = M.clean_targets(out)
        assert t == ['Data/B.bin', 'Data/C.bin', 'Data/D.bin.tmp123_456', 'Data/journal_only.bin'], t
        # trusted stats skip the hash (the build's own read-back)
        st = (out / 'Data' / 'B.bin').stat()
        files['Data/B.bin']['sha1'] = M.sha1_file(out / 'Data' / 'B.bin')[1]
        r = M.check_files(out, {'Data/B.bin': files['Data/B.bin']}, trusted={'data/b.bin': (st.st_size, st.st_mtime_ns)})
        assert r['ok'] == 1


# ------------------------------------------------------------------------------------------------ inputs
def test_identify_synthetic_discs():
    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / 'xml1.iso'
        good.write_bytes(synth.xdvdfs(synth.xml1_disc_files()))
        ident, disc = I.identify(good)
        assert disc['title_id'] == '0x4156001E' and disc['format'] == 'xiso' and not disc['known']
        assert disc['disc_id'] == ident['disc_id'] and len(disc['digest']) == 40
        other = Path(td) / 'other.iso'
        other.write_bytes(synth.xdvdfs(synth.xml1_disc_files(title_id=0x41560017)))
        for path, code, key in ((other, 'E_ISO_WRONG_GAME', 'title_id'), (Path(td), 'E_ISO_NOT_XBOX', 'detected'),
                                (Path(td) / 'gone.iso', 'E_ISO_NOT_FOUND', 'path')):
            try:
                I.identify(path)
                raise AssertionError(path)
            except BuilderError as e:
                assert e.code == code and key in e.detail and e.exit_code == 3 and e.msg.endswith('.'), (e.code, e.detail)
        demo = Path(td) / 'demo.iso'
        demo.write_bytes(synth.xdvdfs(synth.xml1_disc_files(drop=('z/',))))
        try:
            I.identify(demo)
            raise AssertionError('demo')
        except BuilderError as e:
            assert e.code == 'E_ISO_INCOMPLETE' and e.detail['missing']
        assert I.deep_check_disc(good) == []


def test_xml2_checks():
    with tempfile.TemporaryDirectory() as td:
        xml2 = B.make_xml2(Path(td) / 'xml2')
        try:
            I.check_xml2(xml2)
            raise AssertionError('unknown exe accepted')
        except BuilderError as e:
            assert e.code == 'E_XML2_UNKNOWN_EXE' and e.exit_code == 3
        warned = []
        info = I.check_xml2(xml2, allow_unknown=True, warn=lambda *a: warned.append(a[0]))
        assert warned == ['W_XML2_UNKNOWN_EXE'] and info['base_files'] == 5 and info['language'] == 'ENG'
        assert info['reference'] and info['modified_count'] > 0          # a stand-in is not a retail install
        (xml2 / 'XMen2.exe').write_bytes(B.pe32(image_base=0x10000))
        try:
            I.check_xml2(xml2, allow_unknown=True)
            raise AssertionError('wrong image base accepted')
        except BuilderError as e:
            assert e.code == 'E_XML2_NOT_FOUND'
        (xml2 / 'XMen2.exe').write_bytes(B.pe32())
        (xml2 / 'Data' / 'herostat.engb').unlink()
        try:
            I.check_xml2(xml2, allow_unknown=True)
            raise AssertionError('no English data accepted')
        except BuilderError as e:
            assert e.code == 'E_XML2_LANGUAGE'
    ref = I.retail_files()
    assert len(ref) > 10000 and all(len(v) == 2 for v in list(ref.values())[:10])
    assert I.known_exes() and I.known_dumps()


def test_stdin_watch_never_blocks_dll_loads_or_subprocess():
    """a blocking read on a stdin pipe makes GetFileType on it block (Windows): every DLL whose C runtime starts
    up then hangs under the loader lock (numpy's OpenBLAS did). The watcher polls instead."""
    code = ('import sys, time, subprocess\n'
            f'sys.path.insert(0, {str(Path(C.__file__).resolve().parents[1])!r})\n'
            'from xml1builder.cancel import CancelToken, watch_stdin\n'
            'tok = CancelToken(grace=600)\n'
            'watch_stdin(tok)\n'
            'time.sleep(0.5)\n'
            'try:\n    import numpy\nexcept ImportError:\n    pass\n'
            'subprocess.run([sys.executable, "-c", "pass"], timeout=20)\n'
            'print("loaded", flush=True)\n'
            'while not tok.is_set():\n    time.sleep(0.05)\n'
            'print(tok.reason, flush=True)\n'
            'tok.finished()\n')
    for send, want in ((b'noise\r\n  cancel \r\n', 'cancel'), (None, 'eof')):
        p = subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            first = p.stdout.readline().decode().strip()
            assert first == 'loaded', first
            if send:
                p.stdin.write(send)
                p.stdin.flush()
            else:
                p.stdin.close()
            assert p.stdout.readline().decode().strip() == want
            assert p.wait(timeout=20) == 0
        finally:
            if p.poll() is None:
                p.kill()


def test_xml1_builds_ask_for_the_geometry_sharing_fix():
    """SPEC 44: the key is XML1's (xml2-fix leaves the fix off without it); an XML2-opening ini carries none."""
    assert FI.game_keys(xml1_opening=True)['GeometrySharingBlendIndices'] == '1'
    assert 'GeometrySharingBlendIndices' not in FI.game_keys(xml1_opening=False)
    assert 'GeometrySharingBlendIndices' in FI.PORT_OWNED['Game']


def test_xml1_builds_ask_for_character_ladder_paths():
    """SPEC 46: the key is XML1's (xml2-fix keeps ladder paths off without it); an XML2-opening ini has none."""
    assert FI.game_keys(xml1_opening=True)['CharacterLadderPaths'] == '1'
    assert 'CharacterLadderPaths' not in FI.game_keys(xml1_opening=False)
    assert 'CharacterLadderPaths' in FI.PORT_OWNED['Game']


def test_xml1_builds_ask_for_objective_descriptions():
    """SPEC 47: the key is XML1's (xml2-fix keeps XML2's journal text without it); an XML2-opening ini has none."""
    assert FI.game_keys(xml1_opening=True)['ObjectiveDescriptions'] == '1'
    assert 'ObjectiveDescriptions' not in FI.game_keys(xml1_opening=False)
    assert 'ObjectiveDescriptions' in FI.PORT_OWNED['Game']
