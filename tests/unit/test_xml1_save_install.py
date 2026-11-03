"""Opt-in CLI transactions on invented HDD/recomp saves; no native-game proof."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

from save_import_disk_fixture import xbox
from test_builder_cli import check_stream, run
from test_xml1_save_import import fixture, file_hashes, make_profile
from test_xml1_save_recomp import recomp_fixture
from xml1build.save_import import command, mapper, source, tables, transaction
from xml1build.save_import.writer_lock import WriterLock
from xml1builder.errors import Cancelled


def setup(folder, kind='xemu'):
    build, src, dest, _, _ = (recomp_fixture if kind == 'recomp' else fixture)(folder)
    # Invented marker bytes; this fixture never loads or executes a DLL.
    (build / 'dinput.dll').write_bytes(b'MZ invented companion\0lc-save-writer/1\0.lc-save-writer.lock\0')
    if kind == 'xemu':
        guest, _ = xbox((src / 'save.dat').read_bytes(), fat32=True)
        src = guest.qcow(Path(folder) / 'invented-hdd.qcow2', compressed=True)
    (dest / 'profile.lcsave').write_bytes(make_profile(tables.ImportTable(build)))
    (dest / 'saveslot7.lcsave').write_bytes(b'invented unrelated slot')
    args = ['import-xml1-save', str(src), '--source-kind', kind, '--build', str(build),
            '--save-dir', str(dest), '--slot', '0', '--allow-inferred', '--events', 'jsonl']
    return args, build, src, dest


def preview(args):
    code, events, _ = run(args + ['--dry-run'])
    check_stream(events)
    assert code == 0, events
    assert events[-1]['dry_run'] and events[-1]['imported'] is False
    return events[-1]['import_report']


def apply(args, report):
    code, events, _ = run(args + ['--preview-token', report['preview_token']])
    check_stream(events)
    return code, events


def error(events, code):
    assert events[-1]['ok'] is False and events[-1]['exit'] == 2, events
    assert events[-2]['code'] == 'E_XML1_' + code, events


def undo(dest, transaction_id, *extra):
    code, events, _ = run(['import-xml1-save', '--save-dir', str(dest), '--undo-import', transaction_id,
                           '--build', str(Path(dest).parent / 'build'), '--events', 'jsonl', *extra])
    check_stream(events)
    return code, events


def test_install_cli_paths_under_fake_user_profile_remain_usable():
    # Force the real-player Documents/TEMP layout on every host. Reuse the
    # discovery, report/backup reads and Undo checks that exposed this defect.
    from test_xml1_save_import import test_xml1_launcher_source_discovery_and_slots_are_read_only
    with tempfile.TemporaryDirectory() as workspace:
        profile = Path(workspace) / 'invented profile'
        scratch = profile / 'AppData' / 'Local' / 'Temp'
        scratch.mkdir(parents=True)
        values = dict(USERPROFILE=str(profile), HOME=str(profile), TEMP=str(scratch), TMP=str(scratch))
        with patch.dict(os.environ, values), patch.object(tempfile, 'tempdir', str(scratch)):
            test_xml1_launcher_source_discovery_and_slots_are_read_only()
            test_install_cli_absent_profile_stays_absent_and_creation_invalidates_preview()
            test_install_cli_hdd_and_recomp_manifest_untouched_undo_and_preservation()
            with tempfile.TemporaryDirectory() as folder:
                build, src, dest, _, _ = fixture(folder)
                guest, _ = xbox((src / 'save.dat').read_bytes(), multiple=True)
                image = guest.qcow(Path(folder) / 'multiple.qcow2')
                code, events, _ = run(['import-xml1-save', str(image), '--build', str(build),
                                       '--save-dir', str(dest), '--slot', '0', '--dry-run', '--events', 'jsonl'])
                error(events, 'MULTIPLE')
                assert code == 2
                assert all(Path(row['folder']) == image for row in events[-2]['detail']['candidates'])
                selected = events[-2]['detail']['candidates'][0]
                code, inspected, _ = run(['import-xml1-save', selected['folder'], '--campaign', selected['campaign'],
                                          '--inspect-source', '--events', 'jsonl'])
                assert code == 0 and inspected[-1]['source_report'], inspected


def test_install_cli_absent_profile_stays_absent_and_creation_invalidates_preview():
    with tempfile.TemporaryDirectory() as tmp:
        args, _, _, dest = setup(tmp, 'recomp')
        args += ['--experimental-save-import']
        profile = dest / 'profile.lcsave'
        original = profile.read_bytes()
        os.remove(str(profile.absolute()))
        report = preview(args)
        assert report['profile_sha256'] is None and not profile.exists()
        profile.write_bytes(original)
        before = file_hashes(Path(tmp))
        code, events = apply(args, report)
        error(events, 'CHANGED')
        assert file_hashes(Path(tmp)) == before
        os.remove(str(profile.absolute()))
        code, events = apply(args, report)
        assert code == 0 and events[-1]['imported'] is True, events
        assert not profile.exists()
        manifest = json.loads(Path(events[-1]['report']).read_text())
        assert manifest['profile_sha256'] is None


def test_install_cli_hdd_and_recomp_manifest_untouched_undo_and_preservation():
    for kind in ('xemu', 'recomp'):
        with tempfile.TemporaryDirectory() as tmp:
            args, build, src, dest = setup(tmp, kind)
            args += ['--experimental-save-import']
            before = file_hashes(Path(tmp))
            report = preview(args)
            assert file_hashes(Path(tmp)) == before  # preview never creates the lease
            code, events = apply(args, report)
            assert code == 0, events
            result = events[-1]
            assert result['ok'] and result['imported'] and result['dry_run'] is False
            assert result['slot'] == 0 and result['checkpoint'] == report['checkpoint']
            assert result['preview_token'] == report['preview_token']
            assert result['capabilities']['player_install'] and result['capabilities']['undo']
            assert result['capabilities']['merge_unlocks'] is False
            target = dest / 'saveslot0.lcsave'
            raw = target.read_bytes()
            assert source.digest(raw) == result['output_sha256']
            assert Path(result['path']) == target
            assert Path(result['backup']).read_bytes() == raw
            ledger = json.loads(Path(result['report']).read_text())
            assert ledger['output_name'] == target.name  # report stores resolvable relative names
            assert '%USERPROFILE%' not in Path(result['report']).read_text()
            code, history, _ = run(['import-xml1-save', '--list-slots', '--save-dir', str(dest), '--events', 'jsonl'])
            assert code == 0, history
            saved = history[-1]['imports'][0]
            assert saved['report'] == result['report'] and saved['backup'] == result['backup']
            assert json.loads(Path(saved['report']).read_text()) == ledger
            assert Path(saved['backup']).read_bytes() == raw
            for key in ('source_sha256', 'source_profile', 'decoder', 'target_fingerprint',
                        'import_table_sha256', 'checkpoint', 'approximated', 'skipped', 'profile_sha256'):
                assert ledger[key] == report[key], key
            assert ledger['mapping_version'] == mapper.MAPPING_VERSION
            assert ledger['output_sha256'] == result['output_sha256']
            assert ledger['output_bytes'] == len(raw)
            assert ledger['transaction_id'] == result['transaction_id']
            assert ledger['output_name'] == target.name and ledger['backup_name'] == 'campaign.lcsave'
            assert ledger['experimental_save_import'] is True and ledger['player_use_validated'] is False
            assert ledger['merge_unlocks'] is False and ledger['approximated'] and ledger['skipped']
            if kind == 'xemu':
                assert ledger['source_container']['kind'] == 'hdd-image'
                assert ledger['source_container']['campaign']
            else:
                assert ledger['source_herostat_sha256'] and ledger['survey_revision']
            for path, digest in before.items():
                assert source.digest((Path(tmp) / path).read_bytes()) == digest, path
            assert not list(dest.glob('*.tmp'))
            code, events = undo(dest, result['transaction_id'], '--experimental-save-import')
            assert code == 0 and events[-1]['undone'] is True, events
            assert events[-1]['slot'] == 0 and events[-1]['transaction_id'] == result['transaction_id']
            assert not target.exists()
            assert Path(events[-1]['retained']).read_bytes() == raw
            assert Path(events[-1]['backup']).read_bytes() == raw
            assert transaction.slot_status(dest)['slots'][0]['occupied'] is False
            assert transaction.slot_status(dest)['imports'][0]['undo_available'] is False
            for path, digest in before.items():
                assert source.digest((Path(tmp) / path).read_bytes()) == digest, path


def test_install_cli_single_admission_default_off_token_bound_and_merge_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        args, build, src, dest = setup(tmp)
        # Even affirmative table metadata cannot admit writes.
        path = build / tables.TABLE_REL
        mapping = json.loads(path.read_text())
        mapping.update(release_ready=True, acceptance=['invented claimed acceptance'])
        path.write_text(json.dumps(mapping), encoding='ascii')
        before = file_hashes(Path(tmp))
        report = preview(args)
        assert command.capabilities()['player_install'] is False and command.capabilities()['undo'] is False
        code, events = apply(args, report)
        assert code == 2
        error(events, 'UNVALIDATED')
        code, events = apply(args + ['--experimental-save-import'], report)
        error(events, 'CHANGED')  # flag must match the approved preview
        code, events = undo(dest, 'a' * 32)
        error(events, 'UNVALIDATED')
        code, events, _ = run(args + ['--experimental-save-import', '--merge-unlocks', '--dry-run'])
        error(events, 'MERGE')
        assert file_hashes(Path(tmp)) == before


def test_install_cli_occupied_primary_backup_and_pending_refuse():
    for name in ('saveslot0.lcsave', 'SaveSlot0.bak', 'saveslot0.pending'):
        with tempfile.TemporaryDirectory() as tmp:
            args, _, _, dest = setup(tmp)
            args += ['--experimental-save-import']
            report = preview(args)
            (dest / name).write_bytes(b'invented existing player save')
            before = file_hashes(Path(tmp))
            code, events = apply(args, report)
            error(events, 'SLOT')
            assert file_hashes(Path(tmp)) == before


def test_install_cli_lease_blocks_apply_and_undo_and_changed_slot_is_preserved():
    with tempfile.TemporaryDirectory() as tmp:
        args, _, _, dest = setup(tmp)
        args += ['--experimental-save-import']
        report = preview(args)
        with WriterLock(dest):
            pass
        before = file_hashes(Path(tmp))
        with WriterLock(dest):
            code, events = apply(args, report)
            error(events, 'BUSY')
        assert file_hashes(Path(tmp)) == before
        code, events = apply(args, report)
        assert code == 0, events
        txn = events[-1]['transaction_id']
        before = file_hashes(Path(tmp))
        with WriterLock(dest):
            code, events = undo(dest, txn, '--experimental-save-import')
            error(events, 'BUSY')
        assert file_hashes(Path(tmp)) == before
        code, events = undo(dest, txn, '--experimental-save-import', '--dry-run')
        assert code == 2 and events[-2]['code'] == 'E_USAGE'
        target = dest / 'saveslot0.lcsave'
        target.write_bytes(target.read_bytes() + b'invented later player progress')
        before = file_hashes(Path(tmp))
        code, events = undo(dest, txn, '--experimental-save-import')
        error(events, 'CHANGED')
        assert 'played and saved' in events[-2]['msg']
        assert file_hashes(Path(tmp)) == before


def test_install_cli_profile_drift_under_lease_refuses_before_publication():
    for phase in ('acquire', 'publish'):
        with tempfile.TemporaryDirectory() as tmp:
            args, _, _, dest = setup(tmp)
            args += ['--experimental-save-import']
            report = preview(args)
            actual = transaction._write_new
            acquire = WriterLock.__enter__
            changed = b'invented concurrent profile'
            def enter(lease):
                held = acquire(lease)
                if phase == 'acquire':
                    (dest / 'profile.lcsave').write_bytes(changed)
                return held
            def write(path, data, on_created=lambda: None):
                actual(path, data, on_created)
                if phase == 'publish' and path.name == 'report.json':
                    (dest / 'profile.lcsave').write_bytes(changed)
            with patch.object(WriterLock, '__enter__', enter), patch.object(transaction, '_write_new', write):
                code, events = apply(args, report)
            error(events, 'CHANGED')
            assert not (dest / 'saveslot0.lcsave').exists()
            assert not list(dest.glob('*.tmp'))
            assert (dest / 'profile.lcsave').read_bytes() == changed


def test_install_cli_cancellation_and_partial_write_or_ledger_failure_leave_slot_empty():
    for phase in ('partial', 'report', 'cancel'):
        with tempfile.TemporaryDirectory() as tmp:
            args, _, _, dest = setup(tmp)
            args += ['--experimental-save-import']
            report = preview(args)
            before = file_hashes(Path(tmp))
            actual = transaction._write_new
            def write(path, data, on_created=lambda: None):
                if phase == 'partial' and path.name.endswith('.tmp'):
                    with open(path, 'xb') as stream:
                        on_created()
                        stream.write(data[:len(data) // 2])
                    raise OSError('invented interrupted write')
                actual(path, data, on_created)
                if path.name == 'report.json':
                    if phase == 'cancel':
                        raise Cancelled('invented cancellation')
                    raise OSError('invented report flush failure')
            with patch.object(transaction, '_write_new', write):
                code, events = apply(args, report)
            assert code == (5 if phase == 'cancel' else 6), events
            assert events[-1]['ok'] is False and events[-1].get('imported') is not True
            assert not (dest / 'saveslot0.lcsave').exists()
            assert not list(dest.glob('*.tmp'))
            for path, digest in before.items():
                assert source.digest((Path(tmp) / path).read_bytes()) == digest, path
            with WriterLock(dest):
                pass


def test_install_cli_process_death_before_and_after_atomic_publication():
    # Real process death bypasses finally/cleanup. Before publication, pending
    # artifacts reserve the slot; after it, the complete campaign has its ledger.
    script = '''
import json, os, sys
from unittest.mock import patch
sys.path[:0] = ['tools', 'tests/unit']
from test_builder_cli import run
from xml1build.save_import import transaction
phase, args = sys.argv[1], json.loads(sys.argv[2])
actual_write, actual_link = transaction._write_new, transaction.os.link
def write(path, data, on_created=lambda: None):
    if phase == 'partial' and path.name.endswith('.tmp'):
        with open(path, 'xb') as stream:
            on_created()
            stream.write(data[:len(data)//2])
            stream.flush()
            os.fsync(stream.fileno())
            os._exit(91)
    actual_write(path, data, on_created)
def link(src, dst):
    if phase == 'after':
        actual_link(src, dst)
    os._exit(91)
with patch.object(transaction, '_write_new', write), patch.object(transaction.os, 'link', link):
    run(args)
os._exit(92)
'''
    for phase in ('partial', 'before', 'after'):
        with tempfile.TemporaryDirectory() as tmp:
            args, _, _, dest = setup(tmp)
            args += ['--experimental-save-import']
            report = preview(args)
            before = file_hashes(Path(tmp))
            flags = subprocess.CREATE_NO_WINDOW | subprocess.IDLE_PRIORITY_CLASS if os.name == 'nt' else 0
            child = subprocess.run([sys.executable, '-B', '-c', script, phase,
                                    json.dumps(args + ['--preview-token', report['preview_token']])],
                                   cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True,
                                   creationflags=flags, timeout=30)
            assert child.returncode == 91, (child.returncode, child.stdout, child.stderr)
            target = dest / 'saveslot0.lcsave'
            assert target.exists() == (phase == 'after')
            status = transaction.slot_status(dest)
            assert status['slots'][0]['occupied'] is True
            if phase == 'after':
                ledger = next((dest / '.xml1-imports').glob('*/report.json'))
                manifest = json.loads(ledger.read_text())
                assert source.digest(target.read_bytes()) == manifest['output_sha256']
                assert (ledger.parent / 'campaign.lcsave').read_bytes() == target.read_bytes()
            else:
                assert not any(row['undo_available'] for row in status['imports'])
            for path, digest in before.items():
                assert source.digest((Path(tmp) / path).read_bytes()) == digest, path
            with WriterLock(dest):  # process death releases the kernel lease
                pass
            code, events = apply(args, report)
            error(events, 'SLOT')  # never guess whether a crash's pending files are safe to delete
