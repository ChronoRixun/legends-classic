"""Launcher-facing R1 preview/refusal command; all output uses builder events."""
from __future__ import annotations

import json

from lcsave import container

from .errors import ImportRefusal
from .mapper import map_campaign
from .retail import decode
from .source import bounded_read, discover_source, digest, read_source, safe_path
from .tables import ImportTable
from .transaction import check_destination, slot_status
from .writer_lock import PROTOCOL as WRITER_LOCK_PROTOCOL

# No real source save, checkpoint golden or C++ economy/load parity was supplied
# in round 1. A user-editable table must not override this release gate.
PLAYER_INSTALL_ENABLED = False


def capabilities():
    return dict(schema=1, extracted_folders=True, hdd_images=True, recomp_extensions=False,
                player_install=PLAYER_INSTALL_ENABLED, merge_unlocks=False, undo=False,
                writer_lock=WRITER_LOCK_PROTOCOL,
                backup_policy='empty-slot-only; retained campaign copy and report')


def source_summary(source, ir):
    return dict(schema=1, source_sha256=source.sha256, decoder=ir['decoder'],
                source_container=getattr(source, 'binding', dict(kind='extracted-folder')),
                description=ir['description'], signature_status=source.signature_status,
                signature_message='Xbox signature not checked.',
                identity_status='Provisional stock roster; mapping requires a build-bound import table.',
                heroes=[dict(name=h['name'], level=h['level'], experience=h['experience'],
                             unlocked=h['definition_id'] in ir['unlocked']) for h in ir['heroes']],
                progress=dict(zone=ir['mission']['zone'], mission_id=ir['mission']['mission_id'],
                              party=ir['mission']['party'], side_mission_depth=ir['side_depth']),
                player_use_validated=False)


def run(args, output, cancel):
    from xml1builder.errors import BuilderError
    try:
        cancel.check()
        if sum(bool(x) for x in (args.inspect_source, args.list_slots, args.undo_import)) > 1:
            raise BuilderError('E_USAGE', 'Choose one import operation.', exit_code=2)
        if args.list_slots:
            if not args.save_dir:
                raise BuilderError('E_USAGE', '--list-slots needs --save-dir.', exit_code=2)
            status = slot_status(args.save_dir)
            cancel.check()
            output.event('result', ok=True, exit=0, imported=False, slots=status['slots'],
                         imports=status['imports'], capabilities=capabilities())
            return 0
        if args.undo_import:
            # The cooperating writer lease exists; player installation still
            # requires real-source/native acceptance and admitted producers.
            raise ImportRefusal('UNVALIDATED', 'Undo still requires admitted player imports and native acceptance.')
        if args.inspect_source:
            if not args.source:
                raise BuilderError('E_USAGE', '--inspect-source needs a save folder or HDD image.', exit_code=2)
            candidates, original = discover_source(args.source, campaign=args.campaign)
            summary = None
            if original is not None:
                summary = source_summary(original, decode(original.payload))
                original.recheck()
            cancel.check()
            output.event('result', ok=True, exit=0, imported=False, source_report=summary,
                         candidates=candidates, capabilities=capabilities())
            return 0
        if not args.source or args.slot is None or not args.build or not args.save_dir:
            raise BuilderError('E_USAGE', 'import-xml1-save needs a save folder or HDD image, --slot, --build and --save-dir.', exit_code=2)
        if not 0 <= args.slot <= 9:
            raise BuilderError('E_USAGE', '--slot must be between 0 and 9.', exit_code=2)
        cancel.check()
        source = read_source(args.source, campaign=args.campaign)
        output.event('log', level='info', stage='import', msg='Found one Xbox campaign. Your original will remain unchanged.',
                     detail=dict(source_sha256=source.sha256, signature_status=source.signature_status))
        output.event('warning', stage='import', code='W_XML1_SIGNATURE', msg='Xbox signature not checked.', detail={})
        # Parse the stock wire layout first, even if this installation has no
        # admitted mapping table. This gives a specific recomp/damage refusal.
        ir = decode(source.payload)
        output.event('log', level='info', stage='import', msg='Read the campaign records.',
                     detail=dict(decoder=ir['decoder'], heroes=len(ir['heroes']), cached_zones=len(ir['zones']),
                                 side_mission_depth=ir['side_depth'], mission_id=ir['mission']['mission_id'],
                                 consumed_bytes=ir['consumed'], slack_bytes=len(ir['slack'])))
        if ir['side_depth']:
            raise ImportRefusal('SIDE_MISSION')
        dest = check_destination(args.save_dir, args.slot, source.root)
        table = ImportTable(args.build, args.import_table)
        # A pinned source profile can name a stock-shaped synthetic registry;
        # the parser still consumes exactly sixteen normal and 17 restore rows.
        ir = decode(source.payload, hero_names=table.source['hero_names'])
        profile_path = safe_path(dest / 'profile.lcsave')
        profile = bounded_read(profile_path, container.MAX_FILE) if profile_path.exists() else None
        cancel.check()
        data, report, merged = map_campaign(ir, source, table, slot=args.slot,
                                           allow_inferred=args.allow_inferred, profile_bytes=profile,
                                           merge_unlocks=args.merge_unlocks)
        binding = dict(source_sha256=source.sha256, target_fingerprint=table.fingerprint,
                       source_container=getattr(source, 'binding', dict(kind='extracted-folder')),
                       table_sha256=table.sha256, slot=args.slot, merge_unlocks=args.merge_unlocks,
                       allow_inferred=args.allow_inferred, profile_sha256=digest(profile) if profile else None,
                       checkpoint=report['checkpoint'])
        preview_token = digest(json.dumps(binding, sort_keys=True, separators=(',', ':')).encode('utf-8'))
        report['preview_token'] = preview_token
        report['source_container'] = getattr(source, 'binding', dict(kind='extracted-folder'))
        for row in report['approximated']:
            output.event('warning', stage='import', code='W_XML1_APPROXIMATED', msg=row['reason'], detail=row)
        source.recheck()
        table.recheck()
        cancel.check()
        if args.dry_run:
            output.event('result', ok=True, exit=0, imported=False, dry_run=True, import_report=report, capabilities=capabilities(),
                         msg='Preview only. Continue from ' + report['checkpoint'] + '. No files were written.')
            return 0
        if not args.preview_token or args.preview_token != preview_token:
            raise ImportRefusal('CHANGED', 'Apply needs the token from a matching dry-run preview.')
        if not PLAYER_INSTALL_ENABLED:
            raise ImportRefusal('UNVALIDATED', 'Round 1 has no admitted retail checkpoint or C++ native acceptance.', import_report=report)
        # Reserved for the subsequent native-validation/launcher-lock milestone.
        # The empty-slot primitive is tested separately; global profile apply
        # needs a recoverable multi-file transaction before enabling this gate.
        raise ImportRefusal('UNVALIDATED')
    except ImportRefusal as e:
        raise BuilderError(e.code, e.msg, detail=e.detail, stage='import', exit_code=2) from e
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        raise BuilderError('E_XML1_INPUT', 'The selected save source or installation could not be read.',
                           detail=dict(reason=type(e).__name__), stage='import', exit_code=2) from e
