"""Empty-slot installation primitive, with prewritten report/hash ledger.

The CLI's R1 acceptance gate runs before this primitive. No multi-file global
profile transaction is admitted yet; profile bytes are never changed here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

from lcsave import container, layout as L

from .errors import ImportRefusal
from .source import bounded_read, digest, safe_path


def check_destination(save_dir, slot, source_root, *, own_temp=None):
    dest = safe_path(save_dir, directory=True)
    root = safe_path(source_root, directory=True)
    if dest == root or dest.is_relative_to(root) or root.is_relative_to(dest):
        raise ImportRefusal('INPUT', 'The source and target save folders overlap.')
    prefix = f'saveslot{slot}'
    for p in dest.iterdir():
        if p != own_temp and p.name.lower().startswith(prefix):
            raise ImportRefusal('SLOT', 'The slot has a primary, backup or pending save.')
    return dest


def _write_new(path, data, on_created=lambda: None):
    with open(path, 'xb') as stream:
        on_created()  # record ownership only after exclusive creation succeeds
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def install_campaign(data, report, save_dir, source, table, *, cancel=lambda: None, before_link=lambda: None):
    """No overwrite, no source writes, no success before report and final install.

    Report files are a per-import ledger. A report is effective only when its
    output_name exists and has output_sha256; a crash can leave an orphan report
    or temp, which slot management must show as pending rather than successful.
    """
    slot = report['slot']
    dest = check_destination(save_dir, slot, source.root)
    lock = dest / '.xml1-import.lock'
    owned_lock = False
    owned_files, owned_dirs = [], []
    installed = False
    try:
        try:
            with open(lock, 'xb') as stream:
                owned_lock = True
                stream.write(str(os.getpid()).encode('ascii'))
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as e:
            raise ImportRefusal('BUSY') from e
        cancel()
        source.recheck()
        table.recheck()
        check_destination(dest, slot, source.root)
        container.read_file(data, L.KIND_CAMPAIGN)
        if digest(data) != report['output_sha256']:
            raise ValueError('Output report hash does not match the campaign.')
        txn = uuid.uuid4().hex
        temp = dest / f'saveslot{slot}.xml1-{txn}.tmp'
        _write_new(temp, data, lambda: owned_files.append(temp))
        if bounded_read(temp, container.MAX_FILE) != data:
            raise OSError('The staged campaign could not be read back.')
        metadata = safe_path(dest / '.xml1-imports')
        metadata.mkdir(exist_ok=True)
        report_dir = metadata / txn
        report_dir.mkdir()
        owned_dirs.append(report_dir)
        report_path = report_dir / 'report.json'
        final_report = dict(report, transaction_id=txn, output_name=f'saveslot{slot}.lcsave',
                            ledger_rule='Effective only while output_name exists with output_sha256.')
        report_data = (json.dumps(final_report, indent=2, ensure_ascii=True) + '\n').encode('utf-8')
        _write_new(report_path, report_data, lambda: owned_files.append(report_path))
        if bounded_read(report_path, 16 << 20) != report_data:
            raise OSError('The import report could not be read back.')
        cancel()
        source.recheck()
        table.recheck()
        before_link()  # deterministic failure/race injection for synthetic tests
        cancel()
        source.recheck()
        table.recheck()
        check_destination(dest, slot, source.root, own_temp=temp)
        target = dest / f'saveslot{slot}.lcsave'
        try:
            # Hard-link creation is atomic and fails if target already exists.
            # Never fall back to replace(), which could destroy a player's save.
            os.link(temp, target)
        except FileExistsError as e:
            raise ImportRefusal('SLOT') from e
        installed = True
        return dict(path=target, report=report_path, output_sha256=digest(data))
    finally:
        # Absolute, operation-owned paths only. Retain the preflushed ledger
        # after success; cleanup failures cannot turn a committed import into
        # a reported failure. A stale temp is visible as a pending slot.
        for p in reversed(owned_files):
            if installed and p.name == 'report.json':
                continue
            try:
                os.remove(str(p.absolute()))
            except OSError:
                pass
        if not installed:
            for p in reversed(owned_dirs):
                try:
                    os.rmdir(str(p.absolute()))
                except OSError:
                    pass
        if owned_lock:
            try:
                os.remove(str(lock.absolute()))
            except OSError:
                pass
