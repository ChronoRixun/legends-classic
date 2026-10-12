"""xml1build.savefiles - the build's save-format data files (SPEC 70): Data/lcsave/catalogue.lcc,
Data/lcsave/legacy.lcm and the .lcbind file beside every save-bound data file, written from the build's own
data at the end of the content modules (the formats: SPEC-new-save 3.4 / 5.3, the writers: tools/lcsave/lcfiles.py;
what XML2 Fix 1.4 does with them: SPEC-new-save 3.5).

The module runs after every other content module (common.MODULE_ORDER) because the .lcbind headers carry the
SHA-1 of the finished data files. Every key of the build must be in the master catalogue
(tools/lcsave/data/catalogue.json, hashes only - decision D3): a key that is not stops the build, and the
catalogue is updated from a build of the release before it ships (SPEC-new-save 3.3).
"""
from __future__ import annotations

import glob
import os
from pathlib import Path
import sys

# tools/ is on sys.path when the build runs (build_xml1.py / the builder's pipeline); lcsave lives beside xml1build
from lcsave import lcfiles as LF
from lcsave import typed_registry as TR  # noqa: E402

REPORT_KEY = 'content_fingerprint'           # <out>/_build/report.json build.content_fingerprint
MODULE = 'savefiles'


def content_version():
    """the content version the files are stamped with (tools/xml1builder; 0 when built outside the launcher
    package, which never ships)."""
    try:
        from xml1builder import CONTENT_VERSION
        return CONTENT_VERSION
    except ImportError:
        return 0


def expected_files(out):
    """(files {rel: bytes}, problems) of the save-file set for the build in <out> (lcsave.lcfiles)."""
    return LF.write_build_files(str(out), content_version())


def run(ctx):
    out = str(ctx.out)
    files, problems = expected_files(out)
    for prob in problems:
        # a key of the build the master catalogue does not know: update tools/lcsave/data/catalogue.json from
        # this build (python -m lcsave catalogue --build <out> --previous ... --content-version N) before shipping
        ctx.error(f'catalogue: {prob}')
    for rel, data in sorted(files.items()):
        ctx.write_bytes(rel, data, source='lcsave: the save-format data files (SPEC 70)')
    fp = LF.content_fingerprint(out)
    ctx.shared[REPORT_KEY] = fp
    ctx.note(f'{len(files)} save-format files written; content fingerprint {fp}')
    # SPEC 85: the typed entity-id registry of the SHIPPED scripts (this module runs last, after the scripts module
    # wrote Scripts/), which the entity-capacity DLL verifies against the installed tree before it migrates a legacy
    # save's typed fields (PHASE-A-PLAN section 4). A scripts tree the scanner cannot classify fails the build.
    code, scan, messages = typed_registry_for(out, ctx)
    for m in messages:
        ctx.note(f'typed entity ids: {m}')
    if code != 0 or scan is None:
        ctx.error('typed entity ids: the shipped scripts could not be classified; no registry written')
    else:
        ctx.write_bytes(REGISTRY_REL, TR.registry_text(scan).encode('ascii'),
                        source='lcsave: the typed entity-id registry of the shipped scripts (SPEC 85)')


REGISTRY_REL = 'Data/lcsave/typed-entity-ids.txt'


def typed_registry_for(out, ctx=None):
    """-> (exit code, scan dict or None, messages): the registry of <out>/Scripts (the shipped tree). In a build the
    script API comes through ctx.research_path like every other research table, so the frozen builder reads its
    bundled copy (_internal/research/...); without a ctx (tests, the developer CLI) it is the repo's research/."""
    from . import typed_entity_ids as TE
    scripts = Path(out) / 'Scripts'
    messages = []
    try:
        api = TR.load_api(ctx.research_path('scripts/xml2_api.json') if ctx is not None else TE.DEFAULT_API)
        scan = TR.scan_scripts(str(scripts), api)
    except (TR.RegistryError, OSError, ValueError) as e:
        return 1, None, [f'refused: {e}']
    keys = [(t['scope'], t['key']) for t in scan['typed_fields']]
    messages.append(f"scripts {len(scan['files'])} files, fingerprint {scan['fingerprint']}, typed keys {len(keys)}: "
                    + ', '.join(f'{s}/{k}' for s, k in keys))
    if scan['problems']:
        return 1, scan, messages + ['refused: ' + '; '.join(scan['problems'])]
    return 0, scan, messages


def validate(v, ck):
    """V39 (SPEC 70): the build carries the whole save-file set and every file verifies - byte-identical to the
    set computed from the build's own data (SPEC-new-save 3.4), readable by the format's readers, and every key
    in the master catalogue (SPEC-new-save 3.3's builder rule)."""
    out = str(v.ctx.out)
    try:
        files, problems = expected_files(out)
    except Exception as e:  # noqa: BLE001 - a build whose data cannot be numbered fails the check, not the run
        ck.error(f'the save-file set cannot be computed from this build: {e}')
        return
    for prob in problems:
        ck.error(f'catalogue: {prob}')
    ck.set('files_expected', len(files))
    missing = written = bad = 0
    for rel, want in sorted(files.items()):
        p = os.path.join(out, rel.replace('/', os.sep))
        if not os.path.isfile(p):
            ck.error(f'{rel} missing: XML2 Fix 1.4 cannot verify the save tables without it (SPEC-new-save 3.5)')
            missing += 1
            continue
        got = open(p, 'rb').read()
        if got != want:
            ck.error(f'{rel} differs from the set this build\'s data produces '
                     f'({len(got)} vs {len(want)} bytes): a stale or edited file')
            bad += 1
            continue
        try:
            if rel.endswith('.lcbind'):
                LF.read_lcbind(got)
            elif rel.endswith('.lcc'):
                LF.read_catalogue_lcc(got)
            elif rel.endswith('/conversation.lcm'):
                LF.read_conversation_lcm(got)
            elif rel.endswith('.lcm'):
                LF.read_legacy_lcm(got)
        except LF.LCFileError as e:
            ck.error(f'{rel} does not parse: {e}')
            bad += 1
            continue
        written += 1
    # V50 (SPEC 85): the registry is present and is exactly the shipped scripts' (fingerprint and keys).
    reg = os.path.join(out, REGISTRY_REL.replace('/', os.sep))
    if not os.path.isfile(reg):
        ck.error(f'{REGISTRY_REL} missing: the entity-capacity DLL refuses legacy saves without it (SPEC 85)')
    else:
        ok, reason = TR.verify_registry(TR.read_registry_file(reg), str(Path(out) / 'Scripts'))
        if not ok:
            ck.error(f'{REGISTRY_REL} does not match the shipped scripts: {reason}')
    extra = [p for p in glob.glob(os.path.join(out, 'Data', '**', '*.lcbind'), recursive=True)
             if os.path.relpath(p, out).replace(os.sep, '/') not in files]
    for p in extra:
        ck.error(f'{os.path.relpath(p, out).replace(os.sep, "/")}: a .lcbind no data file of this build owns')
    ck.set('files_ok', written)
    ck.set('files_missing', missing)
    ck.set('files_bad', bad + len(extra))
    fp = LF.content_fingerprint(out)
    ck.set('content_fingerprint', fp or '')
    if fp is None:
        ck.error('no content fingerprint: the save-file set is absent')
