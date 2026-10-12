#!/usr/bin/env python3
"""xml1build.typed_entity_ids - the typed entity-id registry of a prepared scripts tree (PHASE-A-PLAN section 4).

    python tools/xml1build/typed_entity_ids.py SCRIPTS_ROOT OUT_FILE [--api research/scripts/xml2_api.json]
                                               [--expect-fingerprint HEX] [--expect-keys N] [--report out.json]
    python tools/xml1build/typed_entity_ids.py --check REGISTRY SCRIPTS_ROOT

Scans every *.py under SCRIPTS_ROOT with the round6 census algorithm (tools/lcsave/typed_registry.py: `v = fn(`
assignments, getID/getIDString taint, literal set(Zone|Game)Var keys, the float-operator taint check, the
fingerprint over the sorted "relative-posix-path\\0sha256\\n" lines) and writes the registry file the entity-capacity
build's loader reads before it migrates a legacy save's typed fields. Exit 0 and the file written only when every
typed key has nothing but token-local / literal-zero writers and no token local enters a float operator; otherwise
exit 1 with the reasons and no file (a changed script schema must be classified, never guessed). --check verifies
an existing registry against a tree (the engine's check) and exits 1 when it does not match.

The registry carries variable names only (no game content). The scripts tree is read, never written.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))              # tools/: lcsave lives beside xml1build

from lcsave import typed_registry as T  # noqa: E402

DEFAULT_API = HERE.parents[1] / 'research' / 'scripts' / 'xml2_api.json'


def generate(scripts_root, out_file, api_path=DEFAULT_API, expect_fingerprint=None, expect_keys=None, report_path=None):
    """-> (exit code, scan dict or None, messages)"""
    messages = []
    try:
        api = T.load_api(api_path)
        scan = T.scan_scripts(scripts_root, api)
    except (T.RegistryError, OSError, ValueError) as e:
        return 1, None, [f'refused: {e}']
    keys = [(t['scope'], t['key']) for t in scan['typed_fields']]
    messages.append(f"scripts {len(scan['files'])} files, fingerprint {scan['fingerprint']}, getID assignments {scan['getID_calls']}, "
                    f"typed keys {len(keys)}: {', '.join(f'{s}/{k}' for s, k in keys)}")
    problems = list(scan['problems'])
    if expect_fingerprint is not None and scan['fingerprint'] != expect_fingerprint.lower():
        problems.append(f"fingerprint {scan['fingerprint']} is not the expected {expect_fingerprint.lower()}")
    if expect_keys is not None and len(keys) != expect_keys:
        problems.append(f'{len(keys)} typed keys, expected {expect_keys}')
    if report_path:
        Path(report_path).write_text(json.dumps(dict(fingerprint=scan['fingerprint'], files=len(scan['files']),
                                                     getID_calls=scan['getID_calls'], getID_assignments=scan['getID_assignments'],
                                                     typed_fields=scan['typed_fields'], float_tainted=scan['float_tainted'],
                                                     problems=problems), indent=1))
    if problems:
        return 1, scan, messages + ['refused: no registry written: ' + '; '.join(problems)]
    text = T.registry_text(scan)
    out = Path(out_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(text.encode('ascii'))
    back = T.load_registry(out.read_bytes())
    if back['fingerprint'] != scan['fingerprint'] or back['keys'] != set(keys):
        return 1, scan, messages + ['refused: the written registry does not read back']
    messages.append(f'wrote {out}')
    return 0, scan, messages


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('scripts_root', nargs='?')
    ap.add_argument('out_file', nargs='?')
    ap.add_argument('--api', default=str(DEFAULT_API))
    ap.add_argument('--expect-fingerprint')
    ap.add_argument('--expect-keys', type=int)
    ap.add_argument('--report')
    ap.add_argument('--check', nargs=2, metavar=('REGISTRY', 'SCRIPTS_ROOT'))
    a = ap.parse_args(argv)
    if a.check:
        ok, reason = T.verify_registry(a.check[0], a.check[1])
        print('registry verified' if ok else f'registry refused: {reason}')
        return 0 if ok else 1
    if not a.scripts_root or not a.out_file:
        ap.error('SCRIPTS_ROOT and OUT_FILE are required (or --check REGISTRY SCRIPTS_ROOT)')
    code, _, messages = generate(a.scripts_root, a.out_file, a.api, a.expect_fingerprint, a.expect_keys, a.report)
    for m in messages:
        print(m)
    return code


if __name__ == '__main__':
    sys.exit(main())
