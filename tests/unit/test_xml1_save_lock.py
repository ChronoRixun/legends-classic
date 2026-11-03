"""Kernel lease contention/recovery, using only disposable invented SaveLCs."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from xml1build.save_import.writer_lock import WriterLock, LOCK_NAME, PROTOCOL
from test_xml1_save_import import convert_fixture, refused
from xml1build.save_import import transaction


def python_peer(save_dir, *, hold):
    tools = Path(__file__).resolve().parents[2] / 'tools'
    code = ('import sys; sys.path.insert(0, sys.argv[1]); '
            'from xml1build.save_import.writer_lock import WriterLock; '
            'lock=WriterLock(sys.argv[2]); lock.__enter__(); '
            'print("held", flush=True); ' + ('sys.stdin.readline()' if hold else 'lock.__exit__(None,None,None)'))
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.IDLE_PRIORITY_CLASS) if os.name == 'nt' else 0
    return subprocess.Popen([sys.executable, '-B', '-c', code, str(tools), str(save_dir)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, creationflags=flags)


def finish(child):
    try:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)
    finally:
        for stream in (child.stdin, child.stdout, child.stderr):
            if stream:
                stream.close()


def test_writer_lease_same_and_other_process_exclude_and_release():
    with tempfile.TemporaryDirectory(prefix='writer lease_\u00e9_') as tmp:
        path = Path(tmp) / LOCK_NAME
        path.write_bytes(b'persistent stale metadata is not a lease')
        with WriterLock(tmp) as held:
            assert held.fd is not None
            assert not os.get_inheritable(held.fd)
            refused(lambda: WriterLock(tmp).__enter__(), 'BUSY')
            child = python_peer(tmp, hold=False)
            try:
                out, err = child.communicate(timeout=10)
                assert child.returncode != 0 and 'E_XML1_BUSY' not in out
                assert 'ImportRefusal' in err
            finally:
                finish(child)
            assert path.exists()
        assert path.read_bytes() == b'persistent stale metadata is not a lease'
        with WriterLock(tmp):
            pass
        assert path.exists()


def test_writer_lease_crash_recovery_and_normal_child_release():
    with tempfile.TemporaryDirectory() as tmp:
        for crash in (False, True):
            child = python_peer(tmp, hold=True)
            try:
                assert child.stdout.readline().strip() == 'held'
                refused(lambda: WriterLock(tmp).__enter__(), 'BUSY')
                if crash:
                    child.kill()
                    child.communicate(timeout=10)
                else:
                    child.communicate('\n', timeout=10)
                    assert child.returncode == 0
                with WriterLock(tmp):
                    pass
            finally:
                finish(child)
        assert (Path(tmp) / LOCK_NAME).exists()


def test_writer_lease_exception_and_legacy_lock_preservation():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            with WriterLock(tmp):
                raise RuntimeError('invented transaction failure')
        except RuntimeError:
            pass
        with WriterLock(tmp):
            pass
        legacy = Path(tmp) / '.xml1-import.lock'
        legacy.write_bytes(b'1234')
        refused(lambda: WriterLock(tmp).__enter__(), 'BUSY')
        assert legacy.read_bytes() == b'1234'


def test_writer_lease_install_and_undo_hold_across_mutations():
    with tempfile.TemporaryDirectory() as tmp:
        _, _, dest, table, original, _, data, report, _ = convert_fixture(tmp)
        with WriterLock(dest):
            refused(lambda: transaction.install_campaign(data, report, dest, original, table), 'BUSY')
        seen = []
        def before_link():
            refused(lambda: WriterLock(dest).__enter__(), 'BUSY')
            seen.append('held at publication')
        result = transaction.install_campaign(data, report, dest, original, table, before_link=before_link)
        assert seen == ['held at publication']
        with WriterLock(dest):
            refused(lambda: transaction.undo_campaign(dest, result['transaction_id']), 'BUSY')
        def cancel_check():
            refused(lambda: WriterLock(dest).__enter__(), 'BUSY')
            seen.append('held in undo')
        undone = transaction.undo_campaign(dest, result['transaction_id'], cancel=cancel_check)
        assert undone['slot'] == 0 and 'held in undo' in seen
        assert not result['path'].exists() and result['backup'].is_file()
        assert (dest / LOCK_NAME).is_file()


def test_writer_lease_native_protocol_interoperability_if_requested():
    """Optional compiled peer uses the actual DLL header, no game linked/launched."""
    executable = os.environ.get('XML1_IMPORT_LOCK_PEER')
    if not executable:
        from unittest import SkipTest
        raise SkipTest('Set XML1_IMPORT_LOCK_PEER to the compiled xml2_save_writer_lock_test.')
    flags = subprocess.CREATE_NO_WINDOW | subprocess.IDLE_PRIORITY_CLASS
    with tempfile.TemporaryDirectory(prefix='native writer lease_\u00e9_') as tmp:
        # Native -> Python exclusion, native crash -> Python recovery.
        child = subprocess.Popen([executable, 'hold', tmp + os.sep], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, creationflags=flags)
        try:
            assert child.stdout.readline().strip() == 'held ' + PROTOCOL
            refused(lambda: WriterLock(tmp).__enter__(), 'BUSY')
            child.kill(); child.communicate(timeout=10)
            with WriterLock(tmp):
                blocked = subprocess.run([executable, 'once', tmp], capture_output=True, text=True,
                                         creationflags=flags, timeout=10)
                assert blocked.returncode == 3 and blocked.stdout.startswith('busy ')
        finally:
            finish(child)
        released = subprocess.run([executable, 'once', tmp], capture_output=True, text=True,
                                  creationflags=flags, timeout=10)
        assert released.returncode == 0 and released.stdout.strip() == 'held ' + PROTOCOL
        child = python_peer(tmp, hold=True)
        try:
            assert child.stdout.readline().strip() == 'held'
            child.kill(); child.communicate(timeout=10)
            recovered = subprocess.run([executable, 'once', tmp], capture_output=True, text=True,
                                       creationflags=flags, timeout=10)
            assert recovered.returncode == 0 and recovered.stdout.strip() == 'held ' + PROTOCOL
        finally:
            finish(child)
        legacy = Path(tmp) / '.xml1-import.lock'
        legacy.write_bytes(b'old importer')
        blocked = subprocess.run([executable, 'once', tmp], capture_output=True, text=True,
                                 creationflags=flags, timeout=10)
        assert blocked.returncode == 3 and legacy.read_bytes() == b'old importer'
