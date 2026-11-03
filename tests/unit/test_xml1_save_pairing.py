"""Invented companion markers and transaction refusals; never load a DLL."""
from pathlib import Path
import os
import tempfile
from unittest.mock import patch

from test_builder_cli import run
from test_xml1_save_import import file_hashes
from test_xml1_save_install import apply, error, preview, setup, undo
from xml1build.save_import import command, transaction
from xml1build.save_import.writer_lock import WriterLock


def paired_dll(build, suffix=b''):
    # Synthetic marker fixture, not a PE image or a fragment of a game DLL.
    data = b'MZ invented companion\0lc-save-writer/1\0.lc-save-writer.lock\0' + suffix
    (build / 'dinput.dll').write_bytes(data)
    return data


def test_pairing_missing_or_old_dll_refuses_install_without_writes():
    for data in (None, b'MZ invented older fix', b'MZ lc-save-writer/10\0.lc-save-writer.lock\0',
                 b'MZ lc-save-writer/1\0unrelated-lock\0'):
        with tempfile.TemporaryDirectory() as tmp:
            args, build, _, dest = setup(tmp)
            if data is None:
                (build / 'dinput.dll').unlink(missing_ok=True)
            else:
                (build / 'dinput.dll').write_bytes(data)
            args += ['--experimental-save-import']
            report = preview(args)
            before = file_hashes(Path(tmp))
            code, events = apply(args, report)
            assert code == 2, events
            error(events, 'DLL')
            assert not (dest / '.lc-save-writer.lock').exists()
            assert file_hashes(Path(tmp)) == before


def test_pairing_preview_binds_dll_and_rechecks_it_under_the_lease():
    for phase in ('after-preview', 'under-lease'):
        with tempfile.TemporaryDirectory() as tmp:
            args, build, _, dest = setup(tmp)
            paired_dll(build)
            args += ['--experimental-save-import']
            report = preview(args)
            assert report['companion']['protocol'] == 'lc-save-writer/1'
            acquire = WriterLock.__enter__

            def enter(lease):
                held = acquire(lease)
                paired_dll(build, b'changed')
                return held

            if phase == 'after-preview':
                paired_dll(build, b'changed')
                code, events = apply(args, report)
            else:
                with patch.object(WriterLock, '__enter__', enter):
                    code, events = apply(args, report)
            assert code == 2, events
            error(events, 'CHANGED')
            assert not (dest / 'saveslot0.lcsave').exists()
            assert not list(dest.glob('*.tmp'))


def test_pairing_undo_requires_build_and_cooperating_installed_dll():
    with tempfile.TemporaryDirectory() as tmp:
        args, build, _, dest = setup(tmp)
        paired_dll(build)
        args += ['--experimental-save-import']
        code, events = apply(args, preview(args))
        assert code == 0, events
        txn = events[-1]['transaction_id']
        code, events, _ = run(['import-xml1-save', '--save-dir', str(dest), '--undo-import', txn,
                               '--experimental-save-import', '--events', 'jsonl'])
        assert code == 2 and events[-2]['code'] == 'E_USAGE', events
        (build / 'dinput.dll').write_bytes(b'MZ invented older fix')
        before = file_hashes(Path(tmp))
        code, events = undo(dest, txn, '--experimental-save-import')
        assert code == 2, events
        error(events, 'DLL')
        assert file_hashes(Path(tmp)) == before
        paired_dll(build)
        code, events = undo(dest, txn, '--experimental-save-import')
        assert code == 0 and events[-1]['undone'], events


def test_pairing_single_public_switch_remains_off_and_controls_both_operations():
    assert command.PLAYER_INSTALL_ENABLED is False
    assert command.capabilities()['player_install'] is False
    with tempfile.TemporaryDirectory() as tmp:
        args, build, _, dest = setup(tmp)
        paired_dll(build)
        with patch.object(command, 'PLAYER_INSTALL_ENABLED', True):
            assert command.capabilities()['player_install'] is True
            assert command.capabilities()['merge_unlocks'] is False
            code, events = apply(args, preview(args))
            assert code == 0 and events[-1]['imported'], events
            code, events = undo(dest, events[-1]['transaction_id'])
            assert code == 0 and events[-1]['undone'], events


def test_pairing_import_log_cannot_overwrite_sources_build_data_or_player_slots():
    with tempfile.TemporaryDirectory() as tmp:
        args, build, image, dest = setup(tmp)
        alias = Path(tmp) / 'linked-log.txt'
        os.link(image, alias)
        for target in (image, build / 'Data/lcsave/xml1-import.json', dest / 'saveslot7.lcsave', alias):
            before = file_hashes(Path(tmp))
            code, events, _ = run(args + ['--dry-run', '--log', str(target)])
            assert code == 2 and events[-2]['code'] == 'E_OUT_UNSAFE', events
            assert file_hashes(Path(tmp)) == before
