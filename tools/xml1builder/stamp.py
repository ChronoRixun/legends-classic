"""xml1builder.stamp - the build's state files and the state machine (BUILDER_DESIGN.md 2.6-2.8).

  <out>/_build/building.json  written when a build starts, removed when it ends well: its presence = incomplete
  <out>/_build/stamp.json     written last, atomically (fields: the launcher's fake builder + design 2.8)

States (out_state; `damaged` is verify's): absent (missing or empty folder, or one holding only what the launcher and
the player own - dinput.dll, xml2-fix.*, mods/ - or build metadata without a builder marker), foreign (other files,
no builder _build/), incomplete (building.json, or no stamp), stale (an older content version, another profile,
another disc or XML2 install), current. `build` refuses exactly the foreign folders (E_OUT_FOREIGN)."""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

BUILD_DIR = '_build'
STAMP = 'stamp.json'
BUILDING = 'building.json'
FORMAT = 1


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(path, data, indent=1):
    """atomic: a temp file in the same folder, then os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'{path.name}.tmp{os.getpid()}')
    tmp.write_text(json.dumps(data, indent=indent, default=str), encoding='utf-8')
    os.replace(tmp, path)
    return path


def build_dir(out) -> Path:
    return Path(out) / BUILD_DIR


def builder_folder(out) -> bool:
    """did the builder make this folder? (a stamp or a building marker in _build/)"""
    b = build_dir(out)
    return (b / STAMP).is_file() or (b / BUILDING).is_file()


def is_empty(out) -> bool:
    out = Path(out)
    return not out.exists() or (out.is_dir() and not any(out.iterdir()))


def read_stamp(out):
    s = read_json(build_dir(out) / STAMP)
    return s if isinstance(s, dict) else None


def start_building(out, record: dict):
    write_json(build_dir(out) / BUILDING, dict(record, started=utc_now()))


def end_building(out):
    try:
        (build_dir(out) / BUILDING).unlink()
    except FileNotFoundError:
        pass


def out_state(out, *, content_version: int, profile: dict | None = None, disc_digest=None, xml2_digest=None):
    """-> (state, reasons, stamp) per design 2.7 (without damaged). profile: the builder's profile without 'movies'
    (a stamp's movies choice is the player's, not a reason to rebuild); disc_digest / xml2_digest: the inputs now
    (None = not known, not compared)."""
    out = Path(out)
    if not out.exists() or is_empty(out):
        return 'absent', [], None
    if not out.is_dir():
        return 'foreign', ['the destination is a file'], None
    if not builder_folder(out):
        from .manifest import has_area_files          # (manifest imports this module)
        if not has_area_files(out):                   # the launcher's / the player's files only: build accepts it
            return 'absent', [], None
        return 'foreign', ['files, but no build made by the builder (_build/stamp.json)'], None
    stamp = read_stamp(out)
    if (build_dir(out) / BUILDING).is_file() or not stamp:
        return 'incomplete', ['a build was started and did not finish'], stamp
    reasons = []
    have = int((stamp.get('builder') or {}).get('content_version') or 0)
    if have < content_version:
        reasons.append(f'content version {have} < {content_version}')
    if profile is not None:
        stamped = dict(stamp.get('profile') or {})
        stamped.pop('movies', None)
        if stamped != profile:
            changed = sorted(k for k in set(stamped) | set(profile) if stamped.get(k) != profile.get(k))
            reasons.append(f'the build profile changed ({", ".join(changed)})')
    inputs = stamp.get('inputs') or {}
    if disc_digest and (inputs.get('disc') or {}).get('digest') not in (None, disc_digest):
        reasons.append('a different disc image')
    if xml2_digest and (inputs.get('xml2') or {}).get('base_digest') not in (None, xml2_digest):
        reasons.append('X-Men Legends II changed')
    return ('stale' if reasons else 'current'), reasons, stamp


def make_stamp(*, version: dict, profile: dict, movies: bool, disc: dict, xml2: dict, requires: dict, outputs: dict,
               result: dict, source: dict | None = None) -> dict:
    """the stamp (design 2.8, with the fields the launcher's fake builder writes)."""
    return {'format': FORMAT,
            'builder': {'version': version['version'], 'commit': version['commit'],
                        'content_version': version['content_version']},
            'source': source or {},
            'profile': dict(profile, movies=bool(movies)),
            'inputs': {'disc': disc, 'xml2': xml2},
            'requires': requires,
            'outputs': outputs,
            'result': result,
            'finished': utc_now()}
