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
                                              'ObjectiveDescriptions': '1', 'BreakRule': 'xml1',
                                              'PlacementCrush': 'xml1', 'ObjectWorldImpact': 'xml1', 'DoubleHeal': '0', 'ExplosiveFirstHit': '1',
                                              'RankCosts': '1', 'LevelSkillPoints': 'xml1',
                                              'LevelStatPoints': 'xml1', 'Xml1Multipart': '1', 'DeathRule': 'xml1',
                                              'NpcPowerRule': 'xml1', 'StunRule': 'xml1', 'DangerRoomParty': 'xml1', 'DangerRoomHealthBars': 'xml1', 'ResistanceDisplay': 'xml1', 'ClassicHud': 'xml1', 'ClassicCodex': '1', 'ClassicSpeakers': '1', 'BoxHarmOrigin': 'xml1', 'HarmSingleChain': 'single', 'OnlineConversations': 'lockstep', 'PersonalItemPicture': 'window', 'ComboPopupGuard': '1', 'PackAmount': 'xml1', 'SoloMode': '1', 'X1Leader': '1',
                                              'DeathSwitchClear': '1'},
                                     'Limits': {'ActorSlots': '127', 'ResourceNames': '1024', 'ItemEnhancements': '512',
                                                'FightStyles': '32', 'EffectCurves': '3600', 'MoveTriggers': '64', 'EntityCapacity': '1',
                                                'ScriptFunctions': '1024'},
                                     'Engine': {'ModelPools': 'x4'}}
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
        assert g['ClassicMainBackdrop'] == '1' and g['DangerRoomGate'] == 'button3'
        assert g['PostgameScript'] == FI.POSTGAME_SCRIPT and g['WindowTitle'] == 'X-Men Legends'
        assert g['NewGamePlus'] == '0' and g['ReviewStats'] == '0' and g['XPCurve'] == 'xml1' and g['Xtract'] == '0' and g['RevivalCost'] == 'xml1'
        assert keys['Online'] == {'GameVersion': FI.PORT_GAME_VERSION, 'FastTransfer': '1', 'ReceiveValidation': '1', 'JoinInProgress': '1', 'TickRate': '60', **FI.broker_keys()} and set(g) <= set(FI.PORT_OWNED['Game'])
        assert keys['Save'] == {'Format': 'lc'} and 'Format' in FI.PORT_OWNED['Save']
        # the harness builds its test ini from the same keys
        sys.path.insert(0, str(Path(C.__file__).resolve().parents[1]))
        import harness
        text = harness.ini_text('windowed', 1, 1, False, save_folder='X-Men Legends', limits=True, postgame=FI.POSTGAME_SCRIPT,
                                main_menu_items=g['MainMenuItems'], xp_curve='xml1', new_game_plus='0',
                                port_identity=True, review_stats='0', xtract='0')
        parsed = FI.parse_ini(text)
        assert parsed['Game'] == g and parsed['Limits'] == keys['Limits'] and parsed['Online'] == keys['Online']
        assert parsed['Engine'] == keys['Engine'] == {'ModelPools': 'x4'} and 'ModelPools' in FI.PORT_OWNED['Engine']


def test_beta2_keys_refuse_a_beta1_dll_and_require_the_beta2_fix():
    # 0.3.0-beta.2 writes [Engine] ModelPools and [Game] ComboPopupGuard, which XML2 Fix 1.8.0-beta.1 does not read
    # (same numeric VERSIONINFO 1.8.0.0): the DLL check names both; beta/rc builders require '>=1.8.0-beta.7' (beta 7).
    keys = {'Game': {'ComboPopupGuard': '1'}, 'Engine': {'ModelPools': 'x4'}}
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        dll.write_bytes(b'MZ' + 'JoinInProgress'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Game] ComboPopupGuard', '[Engine] ModelPools']
        dll.write_bytes(b'MZ' + 'ComboPopupGuard'.encode('utf-16le') + 'ModelPools'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == []
    assert FI.required_xml2fix('0.3.0-beta.3') == FI.required_xml2fix('0.4.0-rc.1') == '>=1.8.0-beta.7'
    assert FI.required_xml2fix('0.4.0') == '>=1.8'


def test_beta3_tick_rate_is_written_port_owned_and_refuses_a_beta2_dll():
    # 0.3.0-beta.3: [Online] TickRate=60 (XML2 Fix 1.8.0-beta.3, gameplay-agreement rule 29) for every port build; a
    # beta.2 DLL (which has the beta.2 keys but not TickRate) is refused by name.
    assert FI.TICK_RATE == '60' and FI.online_keys(port_identity=True)['TickRate'] == '60'
    assert 'TickRate' not in FI.online_keys(port_identity=False)
    assert 'TickRate' in FI.PORT_OWNED['Online'] and 'TickRate' in FI.RELEASE_18_KEYS['Online']
    keys = {'Online': {'JoinInProgress': '1', 'TickRate': '60'}, 'Engine': {'ModelPools': 'x4'}}
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        dll.write_bytes(b'MZ' + ''.join(('JoinInProgress', 'ModelPools', 'ComboPopupGuard')).encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Online] TickRate']
        dll.write_bytes(b'MZ' + ''.join(('JoinInProgress', 'ModelPools', 'TickRate')).encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == []


def test_beta5_classic_keys_refuse_a_beta4_dll_and_require_the_beta5_fix():
    # 0.4.0-beta.5 (the classic look) writes [Game] ClassicHud=xml1 and ClassicCodex=1, first read by XML2 Fix
    # 1.8.0-beta.5. A beta.4 DLL is refused by name, also when it carries a longer key with the same start
    # (ClassicHudPilot): the two are matched with their UTF-16 terminator.
    keys = {'Game': {'ClassicHud': 'xml1', 'ClassicCodex': '1'}}
    assert all(k in FI.RELEASE_18_KEYS['Game'] for k in keys['Game'])
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        dll.write_bytes(b'MZ' + ''.join(('ClassicHudPilot', 'ClassicCodexTrace')).encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Game] ClassicHud', '[Game] ClassicCodex']
        dll.write_bytes(b'MZ' + ''.join(('ClassicHud\0', 'ClassicCodex\0')).encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == []
    assert FI.required_xml2fix('0.4.0') == '>=1.8'


def test_beta6_weapon_brain_keys_refuse_a_beta5_dll_and_require_the_beta6_fix():
    # 0.4.0-beta.6 writes [Game] NpcSemiAuto=xml1 and its [NpcSemiAuto] rows (the officer's weapon brain, XML2 Fix
    # 1.8.0-beta.6, gameplay-agreement rule 16 revision 10). A beta.5 DLL (the classic-look keys, no NpcSemiAuto) would
    # run the stock officer AI, so it is refused by name (beta 7 raises the beta/rc requirement to '>=1.8.0-beta.7').
    keys = {'Game': {'ClassicHud': 'xml1', 'NpcPowerRule': 'xml1', 'NpcSemiAuto': 'xml1'},
            'NpcSemiAuto': {'Count': '1', 'W1': 'guard|3f200000|43c80000|3f800000|00000000'}}
    assert 'NpcSemiAuto' in FI.RELEASE_18_KEYS['Game'] and 'NpcSemiAuto' in FI.PORT_OWNED['Game']
    assert FI.PORT_OWNED['NpcSemiAuto'][:2] == ('Count', 'W1') and FI.PORT_OWNED['NpcSemiAuto'][-1] == 'W64'
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        dll.write_bytes(b'MZ' + ''.join(('ClassicHud\0', 'NpcPowerRule', 'Count')).encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Game] NpcSemiAuto', '[NpcSemiAuto] schema 4 rows']
        dll.write_bytes(b'MZ' + ''.join(('ClassicHud\0', 'NpcPowerRule', 'NpcSemiAuto', 'Count')).encode('utf-16le') + b'NSA4')
        assert FI.old_fix_keys(dll, keys) == []
    assert FI.required_xml2fix('0.4.0') == '>=1.8'


def test_beta7_keys_refuse_a_beta6_dll_and_require_the_beta7_fix():
    # 0.4.0-beta.7 writes schema 3 [NpcSemiAuto] rows (every gun family) and [Game] ClassicSpeakers=1, both first read
    # by XML2 Fix 1.8.0-beta.7. A beta.6 DLL (NpcSemiAuto, no ClassicSpeakers) refuses the schema 3 rows, so it is
    # refused by name; beta/rc builders require '>=1.8.0-beta.7'.
    keys = {'Game': {'NpcPowerRule': 'xml1', 'NpcSemiAuto': 'xml1', 'ClassicSpeakers': '1'},
            'NpcSemiAuto': {'Count': '1', 'W1': 'guard|3f200000|43c80000|3f800000|00000000|00000000|00000002'}}
    assert 'ClassicSpeakers' in FI.RELEASE_18_KEYS['Game'] and 'ClassicSpeakers' in FI.PORT_OWNED['Game']
    assert 'WorldBackfaces' not in FI.game_keys() and 'WorldBackfaces' in FI.PORT_OWNED['Game'] and 'WorldBackfaces' in FI.RELEASE_18_KEYS['Game']
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        dll.write_bytes(b'MZ' + ''.join(('ClassicHud\0', 'NpcPowerRule', 'NpcSemiAuto', 'Count')).encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Game] ClassicSpeakers', '[NpcSemiAuto] schema 4 rows']
        dll.write_bytes(b'MZ' + ''.join(('NpcPowerRule', 'NpcSemiAuto', 'ClassicSpeakers', 'Count')).encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[NpcSemiAuto] schema 4 rows']   # beta 7 before the trace gate
        dll.write_bytes(b'MZ' + ''.join(('NpcPowerRule', 'NpcSemiAuto', 'ClassicSpeakers', 'Count')).encode('utf-16le') + b'NSA4')
        assert FI.old_fix_keys(dll, keys) == []
    assert FI.REQUIRED_XML2FIX_PRERELEASE == 'beta.7'
    assert FI.required_xml2fix('0.4.0-beta.7') == '>=1.8.0-beta.7' and FI.required_xml2fix('0.4.0') == '>=1.8'


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


def test_xml1_builds_ask_for_the_first_games_break_rule():
    """The key belongs to XML1 builds (their entity definitions carry xml1structure); an XML2-opening ini has none,
    and the port owns the key, so a build that stops needing it drops it."""
    assert FI.game_keys(xml1_opening=True)['BreakRule'] == 'xml1'
    assert 'BreakRule' not in FI.game_keys(xml1_opening=False)
    assert 'BreakRule' in FI.PORT_OWNED['Game']
    assert FI.dropped_keys({'Game': {}})['Game'].count('BreakRule') == 1
    # SPEC 63.4: the zone loader's crushes refused while a zone places its objects, for every XML1 build
    assert FI.game_keys(xml1_opening=True)['PlacementCrush'] == 'xml1'
    assert 'PlacementCrush' not in FI.game_keys(xml1_opening=False)
    assert 'PlacementCrush' in FI.PORT_OWNED['Game']
    assert FI.game_keys(xml1_opening=True)['ObjectWorldImpact'] == 'xml1'
    assert 'ObjectWorldImpact' not in FI.game_keys(xml1_opening=False)
    assert 'ObjectWorldImpact' in FI.PORT_OWNED['Game']
    # SPEC 63.5: packs never heal double (nor play XML2's double sound), for every XML1 build
    assert FI.game_keys(xml1_opening=True)['DoubleHeal'] == '0'
    assert 'DoubleHeal' not in FI.game_keys(xml1_opening=False)
    assert 'DoubleHeal' in FI.PORT_OWNED['Game']


def test_xml1_builds_ask_for_the_first_games_npc_power_rule():
    """XML1 charges its enemies for their powers and decides on a melee-range power every 2 s with half the energy;
    XMen2.exe does neither: every XML1 build asks the fix for XML1's rule, an XML2-opening ini has no key, and the port
    owns it, so a stock merge removes it again."""
    assert FI.game_keys(xml1_opening=True)['NpcPowerRule'] == 'xml1'
    assert 'NpcPowerRule' not in FI.game_keys(xml1_opening=False)
    assert 'NpcPowerRule' in FI.PORT_OWNED['Game']
    assert FI.dropped_keys({'Game': {}})['Game'].count('NpcPowerRule') == 1


def test_xml1_builds_ask_for_the_first_games_death_threshold():
    """XML1 kills below 1 health, XMen2.exe at 0: every XML1 build asks the fix for XML1's line; an XML2-opening ini
    has no key, and the port owns it, so a stock merge removes it again."""
    assert FI.game_keys(xml1_opening=True)['DeathRule'] == 'xml1'
    assert 'DeathRule' not in FI.game_keys(xml1_opening=False)
    assert 'DeathRule' in FI.PORT_OWNED['Game']
    assert FI.dropped_keys({'Game': {}})['Game'].count('DeathRule') == 1
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'example.ini'
        path.write_text('[Game]\nDeathRule=xml2\nKeepMe=example\n')
        port = {'Game': FI.game_keys()}
        FI.merge_ini(path, port, FI.dropped_keys(port))
        assert FI.read_ini(path)['Game']['DeathRule'] == 'xml1'
        stock = {'Game': FI.game_keys(xml1_opening=False)}
        FI.merge_ini(path, stock, FI.dropped_keys(stock))
        parsed = FI.read_ini(path)['Game']
        assert 'DeathRule' not in parsed and parsed['KeepMe'] == 'example'


def test_fractional_health_is_reported():
    """SPEC 63.6: a definition with 0 < health < 1 would die on its first hit under DeathRule=xml1."""
    import xml.etree.ElementTree as ET
    from xml1build import x1schema as XS
    root = ET.fromstring('<entities><e classname="physent" name="crate_a" health="0.5"/>'
                         '<e classname="physent" name="crate_b" health="1"/><e classname="physent" name="crate_c" health="0"/>'
                         '<e classname="physent" name="crate_d" health="x"/><e name="crate_e" health="0.25"/></entities>')
    assert XS.fractional_health_problems(root) == [('crate_a', '0.5')]


def test_xml1_builds_ask_for_no_xtract_world_map():
    """issue #46: an XML1 build's ini has the Xtraction Points offer no Xtract world map (xml2-fix 1.3.2 [Game]
    Xtract=0); a build without XML1's postgame (no port build) carries no key, and the port owns it either way."""
    assert FI.game_keys(xml1_opening=True, xtract=FI.XTRACT)['Xtract'] == '0'
    assert 'Xtract' not in FI.game_keys(xml1_opening=True)
    assert 'Xtract' in FI.PORT_OWNED['Game']
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        assert 'Xtract' not in FI.port_keys(out)['Game']                    # no postgame script: not an XML1 build
        (out / 'Scripts' / 'x1' / 'menus').mkdir(parents=True)
        (out / 'Scripts' / 'x1' / 'menus' / 'postgame.py').write_bytes(b'x')
        assert FI.port_keys(out)['Game']['Xtract'] == '0'                   # an XML1 build: no world map anywhere


def test_port_builds_ask_for_the_lc_save_format():
    """SPEC 70: [Save] Format=lc is a port build's (an XML2-opening ini has none), the port owns it, and the
    build needs the xml2-fix that reads it (1.4; 1.5 since the 0.2.2 keys)."""
    assert FI.save_keys(port_identity=True) == {'Format': 'lc'}
    assert FI.save_keys(port_identity=False) == {}
    assert FI.PORT_OWNED['Save'] == ('Format',) and 'ContentFingerprint' in FI.PORT_OWNED['Online']
    assert FI.REQUIRED_XML2FIX == '1.8'


def test_receive_validation_defaults_on_and_requires_supported_companion():
    """Stock receive validation is a local safety switch, written on for every port build."""
    import tempfile
    assert FI.online_keys(port_identity=True)['ReceiveValidation'] == '1'
    assert 'ReceiveValidation' in FI.PORT_OWNED['Online']
    assert 'ReceiveValidation' in FI.RELEASE_16_KEYS['Online']
    keys = {'Online': {'ReceiveValidation': '1'}}
    with tempfile.TemporaryDirectory() as d:
        dll = Path(d) / 'dinput.dll'
        FI.check_release_dll(dll, keys)
        dll.write_bytes(b'MZ older companion')
        try:
            FI.check_release_dll(dll, keys)
        except FI.FixTooOld as exc:
            assert exc.missing == ['[Online] ReceiveValidation']
        else:
            raise AssertionError('a DLL without receive validation was accepted')
        dll.write_bytes(dll.read_bytes() + 'ReceiveValidation'.encode('utf-16le'))
        FI.check_release_dll(dll, keys)


def test_beta_fix_numeric_version_keeps_runtime_capability_checks():
    """Beta DLLs keep numeric VERSIONINFO; require their 1.8 keys, not a textual beta suffix (a DLL's key strings are
    NUL-terminated UTF-16, as the beta.5 keys are matched)."""
    import tempfile
    keys = {section: {key: '1' for key in names} for section, names in FI.RELEASE_18_KEYS.items()}
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        for numeric in ('1.8.0', '1.8.0.0', '1.8.0.2'):
            resource = ('FileVersion\0' + numeric + '\0ProductVersion\0' + numeric + '\0').encode('utf-16le')
            markers = b''.join((key + '\0').encode('utf-16le') for names in FI.RELEASE_18_KEYS.values() for key in names)
            dll.write_bytes(b'MZ synthetic beta fix\0' + resource + markers + b'NSA4')
            FI.check_release_dll(dll, keys)
        # 1.7.1 lacks the companion's 1.8 drop-in capability, even though it has older required keys.
        older = ('ProductVersion\0' + '1.7.1' + '\0').encode('utf-16le')
        markers = b''.join((key + '\0').encode('utf-16le') for names in FI.RELEASE_18_KEYS.values()
                           for key in names if key != 'JoinInProgress')
        dll.write_bytes(b'MZ synthetic old fix\0' + older + markers + b'NSA4')
        try:
            FI.check_release_dll(dll, keys)
        except FI.FixTooOld as exc:
            assert exc.missing == ['[Online] JoinInProgress']
        else:
            raise AssertionError('1.7.1 without the 1.8 drop-in capability was accepted')
    assert FI.REQUIRED_XML2FIX == '1.8'  # stable constant and runtime diagnostics stay unchanged


def test_a_dll_without_the_15_keys_is_refused(tmp_path=None):
    """0.2.2: a companion DLL that doesn't know a 1.5 key the build writes is refused (a 1.4 DLL ignores them)."""
    import tempfile
    keys = {'Game': {'RankCosts': '1', 'X1Leader': '1'}, 'Limits': {'ScriptFunctions': '1024'}}
    with tempfile.TemporaryDirectory() as d:
        dll = Path(d) / 'dinput.dll'
        FI.check_release_dll(dll, keys)                                   # no DLL: a source-only build
        dll.write_bytes(b'MZ' + 'RankCosts'.encode('utf-16le') + 'ScriptFunctions'.encode('utf-16le'))
        try:
            FI.check_release_dll(dll, keys)
        except ValueError as exc:
            assert 'X1Leader' in str(exc) and FI.REQUIRED_XML2FIX in str(exc) and 'RankCosts' not in str(exc)
        else:
            raise AssertionError('an old DLL was accepted')
        dll.write_bytes(dll.read_bytes() + 'X1Leader'.encode('utf-16le'))
        FI.check_release_dll(dll, keys)
        FI.check_release_dll(dll, {'Game': {'NewGameTeam': 'x'}})        # no 1.5 key asked for: nothing to check


def test_old_fix_keys_names_every_unknown_key_and_the_cli_path_writes_anyway():
    """FixTooOld (a ValueError) carries every key an older DLL lacks across the three checks; write_port_keys
    refuses by default (harness, build_xml1) and writes with old_fix_ok (the xml1-builder CLI's warning path)."""
    import tempfile
    keys = {'Game': {'X1Leader': '1'}, 'Limits': {'MoveTriggers': '64', 'EntityCapacity': '1'}, 'Save': {'Format': 'lc'}}
    with tempfile.TemporaryDirectory() as d:
        dll = Path(d) / 'dinput.dll'
        assert FI.old_fix_keys(dll, keys) == []                           # no DLL: nothing to name
        dll.write_bytes(b'MZ ' + 'MoveTriggers'.encode('utf-16le'))     # a 1.3-era DLL that knows only one of them
        assert FI.old_fix_keys(dll, keys) == ['[Limits] EntityCapacity', '[Game] X1Leader']
        try:
            FI.write_port_keys(d, {s: dict(v) for s, v in keys.items()})
        except FI.FixTooOld as exc:
            assert isinstance(exc, ValueError) and exc.missing == ['[Limits] EntityCapacity', '[Game] X1Leader']
            assert f'XML2 Fix {FI.REQUIRED_XML2FIX}' in str(exc)
        else:
            raise AssertionError('an old DLL was accepted')
        assert not (Path(d) / 'xml2-fix.ini').exists()
        FI.write_port_keys(d, {s: dict(v) for s, v in keys.items()}, old_fix_ok=True)
        ini = (Path(d) / 'xml2-fix.ini').read_text()
        assert 'X1Leader=1' in ini and 'EntityCapacity=1' in ini
        try:                                                              # a key set no DLL can run still fails
            FI.old_fix_keys(dll, {'Limits': {'EntityCapacity': '1'}})
        except FI.FixTooOld:
            raise AssertionError('a missing Format=lc is not an old-fix case')
        except ValueError as exc:
            assert 'Format=lc' in str(exc)
        else:
            raise AssertionError('EntityCapacity without Format=lc was accepted')


def test_danger_room_gate_names_the_front_ends_danger_room_item():
    """Issue #63: DangerRoomGate is the XML1 main menu item that opens the Danger Room."""
    from xml1build import frontend as F
    dr = [f'button{n}' for n, _, cmd in F.MENU_BUTTONS if cmd and 'openmenu danger_room' in cmd]
    assert dr == [FI.DANGER_ROOM_GATE_ITEM]
    assert FI.game_keys(main_menu_items='x')['DangerRoomGate'] == FI.DANGER_ROOM_GATE_ITEM
    assert 'DangerRoomGate' not in FI.game_keys()


def test_existing_release_dll_without_npc_power_rule_is_refused():
    """A pre-feature 1.5 DLL knows the other release keys but must not silently omit enemy AI."""
    import tempfile
    keys = {section: {name: 'xml1' for name in names} for section, names in FI.RELEASE_16_KEYS.items()}
    keys['Game']['NpcPowerRule'] = 'xml1'
    with tempfile.TemporaryDirectory() as d:
        dll = Path(d) / 'dinput.dll'
        dll.write_bytes(b'MZ' + b''.join(name.encode('utf-16le') + b'\0\0'
                                       for section in keys.values() for name in section if name != 'NpcPowerRule'))
        try:
            FI.check_release_dll(dll, keys)
        except FI.FixTooOld as exc:
            assert exc.missing == ['[Game] NpcPowerRule']
        else:
            raise AssertionError('a DLL without NpcPowerRule was accepted')
        assert FI.old_fix_keys(dll, keys) == ['[Game] NpcPowerRule']
        dll.write_bytes(dll.read_bytes() + 'NpcPowerRule'.encode('utf-16le'))
        FI.check_release_dll(dll, keys)


def test_existing_release_dll_without_stun_rule_is_refused():
    """A pre-feature 1.5 DLL knows the other release keys but must not silently omit hero reaction ownership."""
    import tempfile
    keys = {section: {name: 'xml1' for name in names} for section, names in FI.RELEASE_16_KEYS.items()}
    keys['Game']['StunRule'] = 'xml1'
    with tempfile.TemporaryDirectory() as d:
        dll = Path(d) / 'dinput.dll'
        dll.write_bytes(b'MZ' + b''.join(name.encode('utf-16le') + b'\0\0'
                                       for section in keys.values() for name in section if name != 'StunRule'))
        try:
            FI.check_release_dll(dll, keys)
        except FI.FixTooOld as exc:
            assert exc.missing == ['[Game] StunRule']
        else:
            raise AssertionError('a DLL without StunRule was accepted')
        assert FI.old_fix_keys(dll, keys) == ['[Game] StunRule']
        dll.write_bytes(dll.read_bytes() + 'StunRule'.encode('utf-16le'))
        FI.check_release_dll(dll, keys)


def test_xml1_builds_write_and_remove_stun_rule():
    assert FI.game_keys(xml1_opening=True)['StunRule'] == 'xml1'
    assert 'StunRule' not in FI.game_keys(xml1_opening=False)
    assert 'StunRule' in FI.PORT_OWNED['Game']
    assert FI.dropped_keys({'Game': {}})['Game'].count('StunRule') == 1


def test_existing_release_dll_without_object_world_impact_is_refused():
    """A pre-feature 1.5 DLL knows the other release keys but must not silently omit world impact physics."""
    import tempfile
    keys = {section: {name: 'xml1' for name in names} for section, names in FI.RELEASE_16_KEYS.items()}
    keys['Game']['ObjectWorldImpact'] = 'xml1'
    with tempfile.TemporaryDirectory() as d:
        dll = Path(d) / 'dinput.dll'
        dll.write_bytes(b'MZ' + b''.join(name.encode('utf-16le') + b'\0\0'
                                       for section in keys.values() for name in section if name != 'ObjectWorldImpact'))
        try:
            FI.check_release_dll(dll, keys)
        except FI.FixTooOld as exc:
            assert exc.missing == ['[Game] ObjectWorldImpact']
        else:
            raise AssertionError('a DLL without ObjectWorldImpact was accepted')
        assert FI.old_fix_keys(dll, keys) == ['[Game] ObjectWorldImpact']
        dll.write_bytes(dll.read_bytes() + 'ObjectWorldImpact'.encode('utf-16le'))
        FI.check_release_dll(dll, keys)


def test_online_broker_defaults_for_deployed_project_broker():
    """[Online] Broker / BrokerPin (0.4.0 launcher contract): one builder setting (fix_ini.PROJECT_BROKER /
    PROJECT_BROKER_PIN). Every port build writes and owns the deployed defaults; empty settings preserve a tester's
    hand-set broker instead."""
    assert FI.PROJECT_BROKER == 'broker.aethyrion.org:10020'
    assert FI.PROJECT_BROKER_PIN == 'ac569104f671775703f3e36a8109519f4e219fb1e8bc68aaa77793cfb3dbad09'
    keys = FI.online_keys(port_identity=True)
    assert keys['Broker'] == FI.PROJECT_BROKER and keys['BrokerPin'] == FI.PROJECT_BROKER_PIN
    assert {'Broker', 'BrokerPin'} <= set(FI.port_owned()['Online'])
    with tempfile.TemporaryDirectory() as tmp:
        ini = Path(tmp) / 'xml2-fix.ini'
        ini.write_text('[Online]\nBroker=old.example.org\nBrokerPin=old\nServer=keep\n')
        FI.write_port_keys(tmp, {'Online': keys})
        written = FI.read_ini(ini)['Online']
        assert written['Broker'] == FI.PROJECT_BROKER and written['BrokerPin'] == FI.PROJECT_BROKER_PIN
        assert written['Server'] == 'keep'
    saved = FI.PROJECT_BROKER, FI.PROJECT_BROKER_PIN
    try:
        FI.PROJECT_BROKER, FI.PROJECT_BROKER_PIN = '', ''
        assert 'Broker' not in FI.online_keys(port_identity=True)
        assert 'Broker' not in FI.port_owned()['Online'] and 'BrokerPin' not in FI.port_owned()['Online']
        FI.PROJECT_BROKER, FI.PROJECT_BROKER_PIN = 'broker.example.org:10020', 'AB' * 32
        keys = FI.online_keys(port_identity=True)
        assert keys['Broker'] == 'broker.example.org:10020' and keys['BrokerPin'] == 'ab' * 32
        assert FI.online_keys(port_identity=False) == {}
        assert {'Broker', 'BrokerPin'} <= set(FI.port_owned()['Online'])
        FI.PROJECT_BROKER_PIN = ''
        assert 'BrokerPin' not in FI.online_keys(port_identity=True)
        FI.PROJECT_BROKER_PIN = 'not-a-pin'
        try:
            FI.online_keys(port_identity=True)
        except ValueError:
            pass
        else:
            raise AssertionError('a malformed pin must be refused')
    finally:
        FI.PROJECT_BROKER, FI.PROJECT_BROKER_PIN = saved


def test_join_in_progress_is_on_for_port_builds_and_needs_fix_18():
    """0.4.0: drop-in co-op ([Online] JoinInProgress=1, rule 26) is written for every port build, is port-owned, and
    an XML2 Fix that does not know the key (older than 1.8) is refused by name."""
    assert FI.online_keys(port_identity=True)['JoinInProgress'] == '1' and FI.JOIN_IN_PROGRESS == '1'
    assert FI.online_keys(port_identity=False) == {}
    assert 'JoinInProgress' in FI.PORT_OWNED['Online'] and 'JoinInProgress' in FI.RELEASE_18_KEYS['Online']
    assert FI.REQUIRED_XML2FIX == '1.8'
    with tempfile.TemporaryDirectory() as d:
        dll = Path(d) / 'dinput.dll'
        dll.write_bytes(b'MZ' + 'ReceiveValidation'.encode('utf-16le'))
        try:
            FI.check_release_dll(dll, {'Online': {'ReceiveValidation': '1', 'JoinInProgress': '1'}})
            raise AssertionError('a fix without JoinInProgress must be refused')
        except FI.FixTooOld as exc:
            assert exc.missing == ['[Online] JoinInProgress'] and FI.REQUIRED_XML2FIX in str(exc)
        dll.write_bytes(b'MZ' + 'ReceiveValidation'.encode('utf-16le') + 'JoinInProgress'.encode('utf-16le'))
        FI.check_release_dll(dll, {'Online': {'ReceiveValidation': '1', 'JoinInProgress': '1'}})


def test_release_identity_040_beta7_is_lc36_and_never_an_older_token():
    """0.4.0-beta.7 (every gun NPC's weapon brain with the bullet trace gate in xml2-fix.ini, the "Alison" speaker
    label in the conversations, the XML1 zone list for one-sided walls) changes the generated output, so it is content
    27 / catalogue 7 / LC36: a token no earlier build carries (0.2.5 LC32, 0.3.0 and the 0.4.0 betas 1-4 LC33, beta 5
    LC34, beta 6 LC35), so neither the stock lobby nor the rooms pair a beta 7 PC with an older build. Content 26 stays
    LC35, 25 LC34 and 24 LC33 (append-only)."""
    from xml1build import release_identity as RI
    from xml1builder import CONTENT_VERSION, VERSION
    assert (VERSION, CONTENT_VERSION) == ('0.4.0', 27) and RI.game_version() == 'LC36'
    assert RI.game_version(content_version=26, catalogue_revision=7) == 'LC35'
    assert RI.game_version(content_version=25, catalogue_revision=7) == 'LC34'
    assert RI.game_version(content_version=24, catalogue_revision=7) == 'LC33'
    assert [r.token for r in RI.HISTORY].count('LC36') == 1 and RI.HISTORY[-1].token == 'LC36'
    assert all(r.token != 'LC36' for r in RI.HISTORY[:-1])
    row = RI.HISTORY[-1]
    assert (row.release, row.content_version, row.catalogue_revision) == ('0.4.0-beta.7', 27, 7)
    assert len(row.bind_manifest) == 64 and row.bind_manifest != RI.HISTORY[-2].bind_manifest


def test_private_candidate_requires_the_release_companion():
    assert FI.required_xml2fix(FI.RI.PRIVATE_CANDIDATE.release) == '>=1.8.0-beta.7'


def test_world_backfaces_is_written_for_the_converted_xml1_zones_only():
    # Owner decision 2026-10-25: rule 30 (XML2 Fix 1.8.0-beta.7, revision 2) applies to the XML1 levels only. The zone
    # list is the zones stage's converted zones; without it no WorldBackfaces key is written (the DLL would apply it to
    # every zone). Invented zone names.
    import json
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        assert 'WorldBackfaces' not in FI.port_keys(out)['Game'] and 'WorldBackfaces' not in FI.port_keys(out)
        (out / '_build').mkdir()
        detail = out / '_build' / 'zones_detail.json'
        detail.write_text(json.dumps({'converted': ['zz/b_zone', 'ZZ\\a_zone', 'yy/c/d_zone', 'zz/b_zone']}), encoding='utf-8')
        keys = FI.port_keys(out)
        assert keys['Game']['WorldBackfaces'] == 'xml1'
        assert keys['WorldBackfaces'] == {'ZoneCount': '3', 'Z1': 'yy/c/d_zone', 'Z2': 'zz/a_zone', 'Z3': 'zz/b_zone'}
        assert FI.dropped_keys(keys)['WorldBackfaces'][0] == 'Z4'          # a longer old list's tail is removed
        for bad in ([], ['a//b'], ['../x'], ['a b'], ['x' * 64], ['z%d' % i for i in range(FI.WORLD_BACKFACES_MAX_ZONES + 1)]):
            detail.write_text(json.dumps({'converted': bad}), encoding='utf-8')
            assert FI.build_world_backfaces(out) == {} and 'WorldBackfaces' not in FI.port_keys(out)['Game'], bad
        detail.write_text('not json', encoding='utf-8')
        assert FI.build_world_backfaces(out) == {}
    assert len(FI.PORT_OWNED['WorldBackfaces']) == 1 + FI.WORLD_BACKFACES_MAX_ZONES


def test_the_unscoped_beta7_dll_is_refused_by_the_zone_list_key():
    # The first beta 7 DLL knew [Game] WorldBackfaces but not [WorldBackfaces] ZoneCount (it would apply rule 30 to
    # every zone); the fixed one reads both. Invented DLL bytes.
    keys = {'Game': {'NpcPowerRule': 'xml1', 'NpcSemiAuto': 'xml1', 'ClassicSpeakers': '1', 'WorldBackfaces': 'xml1'},
            'WorldBackfaces': {'ZoneCount': '1', 'Z1': 'zz/a_zone'}}
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        known = ('NpcPowerRule', 'NpcSemiAuto', 'ClassicSpeakers', 'WorldBackfaces', 'Count')
        dll.write_bytes(b'MZ' + '\0'.join(known).encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[WorldBackfaces] ZoneCount', '[NpcSemiAuto] schema 4 rows']
        dll.write_bytes(b'MZ' + '\0'.join(known + ('ZoneCount',)).encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[NpcSemiAuto] schema 4 rows']   # the zone list alone is not enough
        dll.write_bytes(b'MZ' + '\0'.join(known + ('ZoneCount',)).encode('utf-16le') + b'NSA4')
        assert FI.old_fix_keys(dll, keys) == []
        assert FI.old_fix_keys(dll, {'Game': {'NpcPowerRule': 'xml1'}}) == []   # no rule 30 written: no list needed
