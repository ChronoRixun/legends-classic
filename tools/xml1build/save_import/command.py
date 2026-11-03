"""Launcher-facing preview and opt-in transactions; output uses builder events."""
from __future__ import annotations

import json

from lcsave import container
from xml1builder.events import MachinePath

from .errors import ImportRefusal
from .companion import Companion
from .mapper import map_campaign
from . import recomp, retail
from .source import bounded_read, discover_source, digest, is_recomp, read_source, safe_path
from .tables import ImportTable
from .transaction import check_destination, install_campaign, slot_status, undo_campaign
from .writer_lock import PROTOCOL as WRITER_LOCK_PROTOCOL

# Coordinator's only public admission switch. Leave False until the real-save,
# native-loader and live writer-lease checklist in docs/XML1-SAVE-IMPORT.md passes.
# Tables, INI settings and launcher capability claims cannot override this.
PLAYER_INSTALL_ENABLED = False


def capabilities(experimental=False):
    admitted = PLAYER_INSTALL_ENABLED or experimental
    return dict(schema=1, extracted_folders=True, hdd_images=True, recomp_extensions=True,
                player_install=admitted, merge_unlocks=False, undo=admitted,
                writer_lock=WRITER_LOCK_PROTOCOL,
                backup_policy='empty-slot-only; retained campaign copy and report')


def _machine_paths(row, *names):
    """Mark operational paths only at the event boundary; internals stay real."""
    return dict(row, **{name: MachinePath(row[name]) for name in names})


def decode_source(source, table=None):
    kind = getattr(source, 'kind', None)
    if kind == 'recomp' or (kind != 'xemu' and is_recomp(source.payload)):
        if table is not None and not table.recomp:
            raise ImportRefusal('IDENTITY', 'A recomp save needs its effective source definition ledger.')
        return recomp.decode(source.payload, definitions=table.definitions if table is not None else None)
    if table is not None and table.recomp:
        raise ImportRefusal('IDENTITY', 'The selected source profile describes a different save family.')
    return retail.decode(source.payload, **(dict(hero_names=table.source['hero_names']) if table is not None else {}))


def source_summary(source, ir):
    is_extended = ir['decoder'].startswith('recomp-')
    return dict(schema=1, source_sha256=source.sha256, decoder=ir['decoder'],
                source_container=getattr(source, 'binding', dict(kind='extracted-folder')),
                description=ir['description'], signature_status=source.signature_status,
                signature_message='Xbox signature not checked.',
                identity_status=('Unresolved definition IDs; names require the exact effective source herostat ledger.' if is_extended else
                                 'Provisional stock roster; mapping requires a build-bound import table.'),
                heroes=[dict(name=h['name'], definition_id=h['definition_id'], level=h['level'], experience=h['experience'],
                             unlocked=h['definition_id'] in ir['unlocked']) for h in ir['heroes']],
                difficulty=ir.get('difficulty'),
                progress=dict(zone=ir['mission']['zone'], mission_id=ir['mission']['mission_id'],
                              party=ir['mission']['party'], side_mission_depth=ir['side_depth']),
                player_use_validated=False)


def run(args, output, cancel):
    from xml1builder.errors import BuilderError
    try:
        cancel.check()
        # One invocation-local admission switch controls both producers. Neither
        # table metadata nor the launcher's separate admission can enable it.
        admitted = PLAYER_INSTALL_ENABLED or args.experimental_save_import
        if sum(bool(x) for x in (args.inspect_source, args.list_slots, args.undo_import)) > 1:
            raise BuilderError('E_USAGE', 'Choose one import operation.', exit_code=2)
        if args.merge_unlocks:
            raise ImportRefusal('MERGE', 'Global-profile merging is disabled, including for experimental imports.')
        if args.list_slots:
            if not args.save_dir:
                raise BuilderError('E_USAGE', '--list-slots needs --save-dir.', exit_code=2)
            status = slot_status(args.save_dir)
            cancel.check()
            output.event('result', ok=True, exit=0, imported=False, slots=status['slots'],
                         imports=[_machine_paths(row, 'backup', 'report') for row in status['imports']],
                         capabilities=capabilities(admitted))
            return 0
        if args.undo_import:
            if not args.save_dir or args.dry_run:
                raise BuilderError('E_USAGE', 'Undo needs --save-dir and cannot be combined with --dry-run.', exit_code=2)
            if not admitted:
                raise ImportRefusal('UNVALIDATED', 'Experimental Undo requires --experimental-save-import.')
            if not args.build:
                raise BuilderError('E_USAGE', 'Undo needs --build to verify the installed companion DLL.', exit_code=2)
            companion = Companion(args.build)
            companion.require()
            result = undo_campaign(args.save_dir, args.undo_import, cancel=cancel.check, recheck=companion.recheck)
            output.event('result', ok=True, exit=0, imported=False, **_machine_paths(result, 'retained', 'backup'),
                         capabilities=capabilities(admitted), msg='Removed the unchanged imported slot. Copies were retained.')
            return 0
        if args.inspect_source:
            if not args.source:
                raise BuilderError('E_USAGE', '--inspect-source needs a save folder or HDD image.', exit_code=2)
            candidates, original = discover_source(args.source, campaign=args.campaign, source_kind=args.source_kind)
            summary = None
            if original is not None:
                summary = source_summary(original, decode_source(original))
                original.recheck()
            cancel.check()
            output.event('result', ok=True, exit=0, imported=False, source_report=summary,
                         candidates=[_machine_paths(row, 'folder') for row in candidates],
                         capabilities=capabilities(admitted))
            return 0
        if not args.source or args.slot is None or not args.build or not args.save_dir:
            raise BuilderError('E_USAGE', 'import-xml1-save needs a save folder or HDD image, --slot, --build and --save-dir.', exit_code=2)
        if not 0 <= args.slot <= 9:
            raise BuilderError('E_USAGE', '--slot must be between 0 and 9.', exit_code=2)
        cancel.check()
        source = read_source(args.source, campaign=args.campaign, source_kind=args.source_kind)
        output.event('log', level='info', stage='import', msg='Found one Xbox campaign. Your original will remain unchanged.',
                     detail=dict(source_sha256=source.sha256, signature_status=source.signature_status))
        output.event('warning', stage='import', code='W_XML1_SIGNATURE', msg='Xbox signature not checked.', detail={})
        # Parse source facts before requiring an installed mapping table.
        ir = decode_source(source)
        output.event('log', level='info', stage='import', msg='Read the campaign records.',
                     detail=dict(decoder=ir['decoder'], heroes=len(ir['heroes']), cached_zones=len(ir['zones']),
                                 side_mission_depth=ir['side_depth'], mission_id=ir['mission']['mission_id'],
                                 consumed_bytes=ir['consumed'], slack_bytes=len(ir['slack'])))
        if ir['side_depth']:
            raise ImportRefusal('SIDE_MISSION')
        dest = check_destination(args.save_dir, args.slot, source.root)
        table = ImportTable(args.build, args.import_table)
        companion = Companion(args.build)
        ir = decode_source(source, table)
        profile_path = safe_path(dest / 'profile.lcsave')
        profile = bounded_read(profile_path, container.MAX_FILE) if profile_path.exists() else None
        cancel.check()
        data, report, merged = map_campaign(ir, source, table, slot=args.slot,
                                           allow_inferred=args.allow_inferred, profile_bytes=profile,
                                           merge_unlocks=args.merge_unlocks)
        if merged is not None:
            raise ImportRefusal('MERGE', 'Global-profile merging is disabled.')
        binding = dict(source_sha256=source.sha256, target_fingerprint=table.fingerprint,
                       source_container=getattr(source, 'binding', dict(kind='extracted-folder')),
                       table_sha256=table.sha256, slot=args.slot, merge_unlocks=args.merge_unlocks,
                       allow_inferred=args.allow_inferred, profile_sha256=digest(profile) if profile is not None else None,
                       checkpoint=report['checkpoint'], mapping_version=report['mapping_version'],
                       experimental_save_import=args.experimental_save_import,
                       player_install_enabled=PLAYER_INSTALL_ENABLED, companion=companion.report)
        preview_token = digest(json.dumps(binding, sort_keys=True, separators=(',', ':')).encode('utf-8'))
        report['preview_token'] = preview_token
        report['source_container'] = getattr(source, 'binding', dict(kind='extracted-folder'))
        report['profile_sha256'] = binding['profile_sha256']
        report['experimental_save_import'] = args.experimental_save_import
        report['player_install_enabled'] = PLAYER_INSTALL_ENABLED
        report['companion'] = companion.report
        for row in report['approximated']:
            output.event('warning', stage='import', code='W_XML1_APPROXIMATED', msg=row['reason'], detail=row)
        source.recheck()
        table.recheck()
        companion.recheck()
        cancel.check()
        if args.dry_run:
            output.event('result', ok=True, exit=0, imported=False, dry_run=True, import_report=report, capabilities=capabilities(admitted),
                         msg='Preview only. Continue from ' + report['checkpoint'] + '. No files were written.')
            return 0
        if not args.preview_token or args.preview_token != preview_token:
            raise ImportRefusal('CHANGED', 'Apply needs the token from a matching dry-run preview.')
        if not admitted:
            raise ImportRefusal('UNVALIDATED', 'Experimental Install requires --experimental-save-import.', import_report=report)
        companion.require()

        def recheck_profile():
            companion.recheck()
            current = bounded_read(profile_path, container.MAX_FILE) if profile_path.exists() else None
            if current != profile:
                raise ImportRefusal('CHANGED', 'The global profile changed after analysis. Preview again.')

        installed = install_campaign(data, report, dest, source, table, cancel=cancel.check, recheck=recheck_profile)
        output.event('result', ok=True, exit=0, imported=True, dry_run=False, slot=args.slot,
                     checkpoint=report['checkpoint'], preview_token=preview_token,
                     output_sha256=installed['output_sha256'], transaction_id=installed['transaction_id'],
                     backup=MachinePath(installed['backup']), report=MachinePath(installed['report']),
                     path=MachinePath(installed['path']),
                     import_report=report, capabilities=capabilities(admitted),
                     msg='Installed the imported campaign into the empty slot.')
        return 0
    except ImportRefusal as e:
        msg = e.msg
        detail = dict(e.detail)
        if e.code == 'E_XML1_MULTIPLE':
            # HDD picker candidates are operational even in a refusal event.
            # Extracted-folder refusals use relative campaign labels instead.
            detail['candidates'] = [_machine_paths(row, 'folder') if isinstance(row, dict) else row
                                    for row in detail.get('candidates', [])]
        if args.undo_import and e.code == 'E_XML1_CHANGED':
            msg = ('Undo requires the unchanged imported slot and its retained copy. '
                   'If you have played and saved this slot, keep it to preserve your progress.')
        raise BuilderError(e.code, msg, detail=detail, stage='import', exit_code=2) from e
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        raise BuilderError('E_XML1_INPUT', 'The selected save source or installation could not be read.',
                           detail=dict(reason=type(e).__name__), stage='import', exit_code=2) from e
