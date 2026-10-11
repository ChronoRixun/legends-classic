"""The typed entity-id registry (PHASE-A-PLAN section 4): which script variables hold World entity tokens, so
that the LC -> native boundary of the entity-capacity build can translate a legacy (feature-0, retail eight-bit)
save's typed fields into contiguous ten-bit tokens - and nothing else.

The registry is derived from a prepared scripts tree by the scan of entity-capacity round6 (scripts/round6_models.py,
reproduced here line for line): a local assigned from `getID(` / `getIDString(` is a token local; a literal
`setZoneVar("key", local)` / `setGameVar("key", local)` of such a local makes (scope, key) a typed field. The scan
refuses (no registry) when a typed key also has a writer that is neither a token local nor the literal 0, or when a
token local enters an f-operator (fadd/fsub/fmul/fdiv: the lossy float routes). The registry is tied to the scripts
it was derived from by a fingerprint: SHA-256 over "relative-posix-path\\0sha256-of-the-file\\n" for every *.py file
of the tree, in the tree's path order (the lower-cased path components, as Python sorts WindowsPath). The engine
verifies that fingerprint over its own scripts tree before it enables legacy migration (verify_registry); the C++
lcsave computes it with the same algorithm (typed_registry.cpp).

File format (text, LF, ASCII; the C++ reader parses exactly this):

    lcsave-typed-entity-ids 1
    fingerprint <64 hex digits>
    files <count of *.py files hashed>
    key<TAB><scope><TAB><key>        one line per typed field, sorted by (scope, key); scope is Zone or Game

No game content: the file carries variable names only (the names scripts give their stored ids).
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import re
from pathlib import Path

from . import layout as L

REGISTRY_FORMAT = 'lcsave-typed-entity-ids'
REGISTRY_VERSION = 1
SCOPES = ('Zone', 'Game')
TOKEN_FUNCTIONS = ('getid', 'getidstring')         # lower-cased: a local assigned from these is a token local
FLOAT_OPERATORS = ('fadd', 'fsub', 'fmul', 'fdiv')
ZERO_LITERALS = ('0', '0.0')
MAX_KEY_BYTES = 11                                  # the engine's script-variable name field is 12 bytes with its NUL
_ASSIGN = re.compile(r'\s*(\w+)\s*=\s*(\w+)\s*\(')
_SETVAR = re.compile(r'\s*set(Zone|Game)Var\s*\(\s*"([^"]+)"\s*,\s*([^,)]+)')


class RegistryError(ValueError):
    """the registry (file or scan) cannot be used; the message says why"""


# ------------------------------------------------------------------------------------------------ scripts tree
def script_files(root):
    """[(relative posix path, absolute Path)] of every *.py regular file under `root`, in the fingerprint's order:
    by the lower-cased path components (WindowsPath order, which the round6 scan used through sorted(rglob))."""
    root = Path(root)
    if not root.is_dir():
        raise RegistryError(f'scripts root is not a directory: {root}')
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in filenames:
            if not name.lower().endswith('.py'):
                continue
            p = Path(dirpath) / name
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if not rel.isascii():
                raise RegistryError(f'script path is not ASCII: {rel!r}')
            found.append((rel, p))
    found.sort(key=lambda e: e[0].lower().split('/'))
    return found


def hash_files(files):
    """[{'path', 'sha256'}] of the listed files (bytes read once each)"""
    return [{'path': rel, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for rel, p in files]


def fingerprint_of(hashed):
    return hashlib.sha256(''.join(f"{x['path']}\0{x['sha256']}\n" for x in hashed).encode()).hexdigest()


def scripts_fingerprint(root):
    """-> (fingerprint hex, file count) over the scripts tree (the same algorithm as the scan)"""
    hashed = hash_files(script_files(root))
    return fingerprint_of(hashed), len(hashed)


# ------------------------------------------------------------------------------------------------ scan
def scan_scripts(root, api):
    """the round6 scan over a prepared scripts tree. `api`: the xml2_api.json dict (function -> {'ret': type}).
    -> dict(fingerprint, files, getID_calls, getID_assignments, writers, typed_fields, float_tainted, problems);
    `problems` non-empty means no registry may be written (mixed writers / float-tainted token locals)."""
    files = script_files(root)
    hashed = []
    rows, writers, calls, float_tainted = [], collections.defaultdict(list), 0, []
    for rel, p in files:
        raw = p.read_bytes()
        hashed.append({'path': rel, 'sha256': hashlib.sha256(raw).hexdigest()})
        try:
            s = raw.decode('cp1252')
        except UnicodeDecodeError as e:
            raise RegistryError(f'{rel}: not cp1252 text ({e})') from e
        types, taint = {}, {}
        for ln, line in enumerate(s.splitlines(), 1):
            clean = line.split('#', 1)[0]
            m = _ASSIGN.match(clean)
            if m:
                v, fn = m.groups()
                types[v] = api.get(fn, {}).get('ret')
                taint[v] = fn.lower() in TOKEN_FUNCTIONS
                if fn.lower() == 'getid':
                    calls += 1
                    rows.append({'file': rel, 'line': ln, 'local': v, 'return_type': types[v]})
                if fn in FLOAT_OPERATORS and any(re.search(r'\b' + re.escape(k) + r'\b', clean.split('(', 1)[1])
                                                 for k, vv in taint.items() if vv):
                    float_tainted.append({'file': rel, 'line': ln})
            m = _SETVAR.match(clean)
            if m:
                scope, key, value = m.groups()
                value = value.strip()
                writers[(scope, key)].append({'file': rel, 'line': ln,
                                              'value_kind': 'world_token' if taint.get(value) else 'zero' if value in ZERO_LITERALS else 'other',
                                              'value_type': types.get(value)})
    typed, problems = [], []
    for (scope, key), rr in writers.items():
        if not any(r['value_kind'] == 'world_token' for r in rr):
            continue
        mixed = [r for r in rr if r['value_kind'] not in ('world_token', 'zero')]
        if mixed:
            problems.append(f'{scope} variable {key!r} has mixed writers: token locals and ' +
                            ', '.join(f"{r['file']}:{r['line']} ({r['value_kind']})" for r in mixed))
        if len(key.encode('cp1252')) > MAX_KEY_BYTES:
            problems.append(f'{scope} variable {key!r} does not fit the engine name field ({MAX_KEY_BYTES} bytes)')
        if not key.isascii() or not key.isprintable() or any(c in key for c in '\t\r\n'):
            problems.append(f'{scope} variable {key!r} is not a printable ASCII name')
        typed.append({'scope': scope, 'key': key, 'writers': rr, 'all_known_writers_token_or_zero': not mixed})
    for row in float_tainted:
        problems.append(f"{row['file']}:{row['line']}: a getID local enters a float operator (lossy); the registry cannot vouch for it")
    typed.sort(key=lambda t: (t['scope'], t['key']))
    return dict(fingerprint=fingerprint_of(hashed), files=hashed, getID_calls=calls, getID_assignments=rows,
                writers={f'{s}/{k}': v for (s, k), v in writers.items()}, typed_fields=typed,
                float_tainted=float_tainted, problems=problems)


def load_api(path):
    with open(path, 'rb') as f:
        api = json.loads(f.read().decode('utf-8'))
    if not isinstance(api, dict):
        raise RegistryError('xml2_api.json is not an object')
    return api


# ------------------------------------------------------------------------------------------------ file
def registry_text(scan):
    """the registry file's text from a scan result (refused when the scan recorded problems)"""
    if scan['problems']:
        raise RegistryError('no registry: ' + '; '.join(scan['problems']))
    lines = [f'{REGISTRY_FORMAT} {REGISTRY_VERSION}', f"fingerprint {scan['fingerprint']}", f"files {len(scan['files'])}"]
    for t in sorted(scan['typed_fields'], key=lambda t: (t['scope'], t['key'])):
        lines.append(f"key\t{t['scope']}\t{t['key']}")
    return '\n'.join(lines) + '\n'


def load_registry(blob):
    """registry file bytes (or text) -> dict(version, fingerprint, files, keys={(scope, key)}); RegistryError
    on anything malformed (the engine refuses legacy migration on a registry it cannot read)"""
    if isinstance(blob, (bytes, bytearray)):
        if not bytes(blob).isascii():
            raise RegistryError('typed registry: not ASCII text')
        text = bytes(blob).decode('ascii')
    else:
        text = blob
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    if not lines or lines[0].split(' ') != [REGISTRY_FORMAT, str(REGISTRY_VERSION)]:
        raise RegistryError(f'typed registry: not a {REGISTRY_FORMAT} {REGISTRY_VERSION} file')
    out = dict(version=REGISTRY_VERSION, fingerprint=None, files=None, keys=set())
    for n, line in enumerate(lines[1:], 2):
        if line.endswith('\r'):
            raise RegistryError(f'typed registry line {n}: CR line ends are not allowed')
        if line.startswith('fingerprint '):
            v = line[len('fingerprint '):]
            if len(v) != 64 or any(c not in '0123456789abcdef' for c in v) or out['fingerprint'] is not None:
                raise RegistryError(f'typed registry line {n}: bad fingerprint')
            out['fingerprint'] = v
        elif line.startswith('files '):
            v = line[len('files '):]
            if not v.isdigit() or out['files'] is not None:
                raise RegistryError(f'typed registry line {n}: bad file count')
            out['files'] = int(v)
        elif line.startswith('key\t'):
            parts = line.split('\t')
            if len(parts) != 3 or parts[1] not in SCOPES or not parts[2] or not parts[2].isprintable():
                raise RegistryError(f'typed registry line {n}: bad key line')
            if (parts[1], parts[2]) in out['keys']:
                raise RegistryError(f'typed registry line {n}: duplicate key')
            out['keys'].add((parts[1], parts[2]))
        else:
            raise RegistryError(f'typed registry line {n}: unknown line')
    if out['fingerprint'] is None or out['files'] is None:
        raise RegistryError('typed registry: fingerprint or file count missing')
    return out


def read_registry_file(path):
    with open(path, 'rb') as f:
        return load_registry(f.read())


def verify_registry(registry, scripts_root):
    """`registry`: a path, file bytes or a loaded dict. -> (ok, reason): ok when the registry reads and its
    fingerprint is the scripts tree's effective fingerprint (same file set, same bytes). Legacy migration must not
    be enabled on a registry that does not verify."""
    try:
        if isinstance(registry, dict):
            reg = registry
        elif isinstance(registry, (bytes, bytearray)):
            reg = load_registry(registry)
        else:
            reg = read_registry_file(registry)
        fingerprint, count = scripts_fingerprint(scripts_root)
    except (RegistryError, OSError) as e:
        return False, f'typed registry cannot be verified: {e}'
    if fingerprint != reg['fingerprint']:
        return False, (f'typed registry fingerprint {reg["fingerprint"][:16]}... does not match the scripts tree '
                       f'{fingerprint[:16]}... ({count} files): a changed script schema needs a regenerated registry')
    if count != reg['files']:
        return False, f'typed registry lists {reg["files"]} files, the scripts tree has {count}'
    return True, ''


# ------------------------------------------------------------------------------------------------ migration
NO_REGISTRY = 'legacy save needs a verified typed entity-id registry before its typed fields can be migrated (none supplied)'


def migrate_script_vars(zone_vars, game_vars, required_features, native, registry, report=None):
    """The LC -> native typed-field adapter (PHASE-A-PLAN section 4), for the SVAR lists of one file:
      feature 0 on a contiguous layout: every registered (scope, key) value is migrate_typed_field'ed (retail
        eight-bit -> ten-bit, or null); a registry is required (NO_REGISTRY otherwise)
      feature 1 on a contiguous layout: registered values are validated (validate_typed_field), never shifted;
        without a registry nothing is touched
      a retail layout: untouched (a feature-1 file was refused before this point)
    Every other value is preserved. -> (zone_vars, game_vars) as new lists; `report` (a dict) receives the counts:
    mode, typed_fields, translated, normalized_to_null, validated."""
    counts = dict(mode='none', typed_fields=0, translated=0, normalized_to_null=0, validated=0)
    legacy = not (required_features & L.FEATURE_ENTITY_LAYOUT_CONTIGUOUS10)
    if native.contiguous and legacy and registry is None:
        raise RegistryError(NO_REGISTRY)
    keys = registry['keys'] if registry is not None else set()
    out = []
    for scope, lst in (('Zone', zone_vars), ('Game', game_vars)):
        new = []
        for v in lst:
            value = v['value']
            if native.contiguous and (scope, v['name']) in keys:
                counts['typed_fields'] += 1
                if legacy:
                    counts['mode'] = 'migrate'
                    mapped = L.migrate_typed_field(value)
                    if value and mapped:
                        counts['translated'] += 1
                    elif value and not mapped:
                        counts['normalized_to_null'] += 1
                else:
                    counts['mode'] = 'validate'
                    mapped = L.validate_typed_field(value)
                    counts['validated'] += 1
                    if value and not mapped:
                        counts['normalized_to_null'] += 1
                value = mapped
            new.append(dict(v, value=value))
        out.append(new)
    if native.contiguous and legacy:
        counts['mode'] = 'migrate'
    elif native.contiguous and registry is not None:
        counts['mode'] = 'validate'
    if report is not None:
        report.update(counts)
    return out[0], out[1]


def migration_note(report):
    """the one ledger line a loader logs for a migration/validation pass"""
    if report['mode'] == 'migrate':
        return (f"typed entity-id migration: {report['typed_fields']} registered fields, {report['translated']} translated, "
                f"{report['normalized_to_null']} normalized to null")
    if report['mode'] == 'validate':
        return (f"typed entity-id validation: {report['typed_fields']} registered fields, "
                f"{report['normalized_to_null']} normalized to null")
    return None
