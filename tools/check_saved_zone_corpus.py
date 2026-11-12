"""Run the offline G3 host, preserving positive and negative corpus expectations.

The historical corpus includes one synthetic 224-definition capacity experiment.
See docs/saved-zone-corpus.md. Its exact bytes must remain refused by normal builds;
all other inputs must load and pass every host check. No save is rewritten here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


SYNTHETIC_SHA1 = 'd1e97a5e373e0cb1064d40ba46743af1db0070bb'
SYNTHETIC_ID = SYNTHETIC_SHA1[:12]
SYNTHETIC_ERROR = 'item: id 0x20000e2 is not in this build (parked / unknown)'


def classify(rows, host_exit):
    """rows: (list id, actual input SHA-1, native host JSON verdict). Fail closed."""
    loaded, refused, unexpected = 0, 0, []
    host_failures = False
    seen = set()
    for identity, digest, result in rows:
        host_failures |= bool(result.get('failures'))
        if identity in seen or result.get('id') != identity:
            unexpected.append(f'{identity}: duplicate or missing/mismatched host verdict')
        elif identity == SYNTHETIC_ID or digest == SYNTHETIC_SHA1:
            if (identity == SYNTHETIC_ID and digest == SYNTHETIC_SHA1
                    and result.get('kind') == 'lc-campaign' and result.get('dump') is True
                    and result.get('w2_load') is False
                    and result.get('w2_load_error') == SYNTHETIC_ERROR
                    and result.get('failures') == ['w2 load: ' + SYNTHETIC_ERROR]):
                refused += 1
            else:
                unexpected.append(f'{identity}: synthetic provenance/refusal changed')
        elif ((result.get('dump') is True
               or (result.get('kind') == 'retail-settings' and result.get('size') == 684
                   and result.get('import') is True and result.get('import_error') == ''
                   and result.get('w2_save') is True and result.get('w2_idempotent') is True))
              and result.get('w2_load') is True
              and result.get('failures') == []):
            loaded += 1
        else:
            unexpected.append(f'{identity}: unexpected native host failure or incomplete verdict')
        seen.add(identity)
    if not seen:
        unexpected.append('empty corpus')
    if host_exit != int(host_failures):
        unexpected.append(f'native host exit {host_exit} disagrees with verdicts')
    return dict(total=len(rows), passed=loaded + refused, loaded=loaded,
                expected_refusals=refused, unexpected=unexpected, host_exit=host_exit)


def superseded_path(out):
    """A sibling name for an older --out: never overwritten, never deleted."""
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    base = out.with_name(out.name + '.superseded-' + stamp)
    candidate, suffix = base, 2
    while candidate.exists():
        candidate, suffix = out.with_name(f'{base.name}-{suffix}'), suffix + 1
    return candidate


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--host', required=True, type=Path)
    ap.add_argument('--list', required=True, type=Path)
    ap.add_argument('--data', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path, help='new output directory')
    ap.add_argument('--replace-existing', action='store_true',
                    help='move an existing --out aside to <out>.superseded-<UTC stamp> instead of refusing')
    ap.add_argument('--require-count', type=int, default=148)
    args = ap.parse_args(argv)
    # A new directory prevents stale verdicts from satisfying a crashed/partial run.
    inputs = []
    for line in args.list.read_text(encoding='utf-8').splitlines():
        identity, path = line.split('\t', 1)
        if not identity or Path(identity).name != identity or '/' in identity or '\\' in identity:
            raise ValueError('unsafe corpus id')
        path = Path(path)
        inputs.append((identity, path, hashlib.sha1(path.read_bytes()).hexdigest()))
    if args.out.exists():
        if not args.replace_existing:
            print(f'G3: --out already exists: {args.out}; rerun with --replace-existing to move it aside '
                  f'and start from an empty directory', file=sys.stderr)
            return 1
        stale = superseded_path(args.out)
        args.out.rename(stale)
        print(f'G3: existing --out moved to {stale}')
    args.out.mkdir(parents=True, exist_ok=False)
    command = [str(args.host.resolve()), '--list', str(args.list.resolve()),
               '--data', str(args.data.resolve()), '--registry',
               str((args.data / 'Data/lcsave/typed-entity-ids.txt').resolve()),
               '--out', str(args.out.resolve()), '--w2-only', '1', '--economy', '1']
    flags = subprocess.IDLE_PRIORITY_CLASS if os.name == 'nt' else 0
    with (args.out / 'native.log').open('wb') as log:
        run = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    rows = []
    changed = []
    for identity, path, digest in inputs:
        verdict = args.out / (identity + '.json')
        rows.append((identity, digest, json.loads(verdict.read_text()) if verdict.exists() else {}))
        if hashlib.sha1(path.read_bytes()).hexdigest() != digest:
            changed.append(f'{identity}: input changed during gate')
    summary = classify(rows, run.returncode)
    summary['unexpected'].extend(changed)
    if len(rows) != args.require_count:
        summary['unexpected'].append(f'expected {args.require_count} inputs, got {len(rows)}')
    summary['input_sha1'] = {identity: digest for identity, _, digest in inputs}
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(f"G3: {summary['passed']}/{summary['total']} expectations satisfied; "
          f"{summary['loaded']} loaded, {summary['expected_refusals']} expected refusal(s), "
          f"{len(summary['unexpected'])} unexpected")
    for error in summary['unexpected']:
        print('FAIL: ' + error)
    return int(bool(summary['unexpected']))


if __name__ == '__main__':
    raise SystemExit(main())
