"""xml1builder.manifest - what the build put into <out>, file by file, and checking it (verify, clean).

The build's area in <out> is everything except what the launcher and the player own - dinput.dll, xml2-fix.* and
mods/ at the root (OWNED_ROOT = xml1build.common.PROXY_PATTERNS) - and the build metadata (META_ROOT: _build/, ...).
Saves live in Documents, never in <out>.

  <out>/_build/manifest.json   written at the end of a build: every file of the area with its size and sha1, kind
                               "base" (copied from X-Men Legends II; its source's size / mtime / sha1 in "src") or
                               "built" (written by the pipeline; the sha1 it was written and read back with)
  <out>/_build/journal.txt     every path a build writes, appended as it goes: `clean` of an interrupted build
                               deletes exactly these (with the manifest and the registry); removed when a build ends
  <out>/_build/verify-report.json  the last verification (verify, and the end of every build): relative paths,
                               sizes, hashes, versions and reason codes only - never file contents - for the
                               launcher's "Report a problem"

Verification groups (codes are stable; cause_hint is English text for the player / a bug report):
  missing          a file of the manifest is gone
  changed          its size or sha1 differs (expected vs found)
  unreadable       it cannot be read (in use, or blocked)
  extra            a file in the area the build did not make
  xml2_changed     (verify --xml2) X-Men Legends II's files differ from the ones this port was built from
  xml2_not_retail  (from the stamp) the XML2 install differed from a retail install when the port was built
  disc_unknown / disc_damaged / disc_changed   (verify --iso [--deep]) the disc image"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import stamp as S

OWNED_ROOT = ('dinput.dll', 'mods', 'xml2-fix.*')        # = xml1build.common.PROXY_PATTERNS (unit-tested)
META_ROOT = ('_build', '_tour.json', '.codegpt-game.json')   # = xml1build.common.META_NAMES
MANIFEST = 'manifest.json'
JOURNAL = 'journal.txt'
VERIFY_REPORT = 'verify-report.json'
FORMAT = 1
TMP_RX = re.compile(r'\.tmp\d+(_\d+)?$', re.IGNORECASE)     # common._atomic_* / stamp.write_json temp files
LIST_LIMIT = 500                                           # files listed per group in verify-report.json
EVENT_LIMIT = 20                                           # ... and in the result event

CAUSES = {
    'missing': 'Files missing: deleted after the build, or quarantined by an antivirus program.',
    'changed': 'Files changed after the build: another program or a mod edited them (or the disk damaged them).',
    'unreadable': 'Files that could not be read: in use by another program, or blocked by an antivirus program.',
    'extra': 'Files the build did not make: added by another program, a mod copied into the game folders, or left '
             'over from an interrupted build (a rebuild removes them).',
    'xml2_changed': "X-Men Legends II's files differ from the ones this port was built from: the XML2 install was "
                    'modified, updated or repaired since.',
    'xml2_not_retail': "X-Men Legends II's files differed from a retail install when this port was built: the XML2 "
                       'install was modified (a mod or a patch installed into it).',
    'disc_unknown': "The disc image doesn't match a known good dump (a different release, or a modified image).",
    'disc_damaged': 'The disc image is damaged: a file inside it fails its checksum.',
    'disc_changed': 'The disc image is not the one this port was built from.',
}
REPAIRS = {'missing', 'changed', 'unreadable'}           # the groups that make a build `damaged`


def owned(rel: str) -> bool:
    """a root entry the launcher / the player own, or build metadata: never part of the build's area."""
    top = rel.replace('\\', '/').split('/', 1)[0].lower()
    return top in META_ROOT or any(fnmatch.fnmatchcase(top, p) for p in OWNED_ROOT)


def area_files(out) -> dict:
    """{lower rel: actual rel} of every file in the build's area of <out>."""
    out = str(out)
    found = {}
    for dirpath, dirnames, filenames in os.walk(out):
        rel_dir = os.path.relpath(dirpath, out).replace(os.sep, '/')
        if rel_dir == '.':
            rel_dir = ''
            dirnames[:] = [d for d in dirnames if not owned(d)]
            filenames = [f for f in filenames if not owned(f)]
        for f in filenames:
            rel = f'{rel_dir}/{f}' if rel_dir else f
            found[rel.lower()] = rel
    return found


def has_area_files(out) -> bool:
    """does the build's area of <out> hold any file? (area_files, stopping at the first: a foreign folder can be big)"""
    top = True
    for dirpath, dirnames, filenames in os.walk(str(out)):
        if top:
            dirnames[:] = [d for d in dirnames if not owned(d)]
            filenames = [f for f in filenames if not owned(f)]
            top = False
        if filenames:
            return True
    return False


def sha1_file(path) -> tuple:
    """(size, sha1 hex) of a file, read in 1 MB blocks."""
    h = hashlib.sha1()
    size = 0
    with open(path, 'rb') as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            size += len(b)
            h.update(b)
    return size, h.hexdigest()


def hash_files(items, *, jobs=8, cancel=None, progress=None) -> dict:
    """{key: (size, sha1) | OSError} for items [(key, path)], on `jobs` threads (hashlib releases the GIL);
    cancel() / cancel.check() is polled between files; progress(done, total)."""
    items = list(items)
    total = len(items)
    results = {}
    if not items:
        return results
    lock = threading.Lock()
    state = {'done': 0}

    def check():
        if cancel is None:
            return
        if hasattr(cancel, 'check'):
            cancel.check()
        elif cancel():
            raise KeyboardInterrupt

    def one(item):
        key, path = item
        check()
        try:
            r = sha1_file(path)
        except OSError as e:
            r = e
        with lock:
            results[key] = r
            state['done'] += 1
            done = state['done']
        if progress is not None:
            progress(done, total)

    if jobs <= 1:
        for it in items:
            one(it)
        return results
    with ThreadPoolExecutor(max_workers=jobs, thread_name_prefix='xml1builder-hash') as pool:
        futures = [pool.submit(one, it) for it in items]
        try:
            for f in futures:
                f.result()
        except BaseException:
            for f in futures:
                f.cancel()
            raise
    return results


# ------------------------------------------------------------------------------------------------ the manifest
def load(out) -> dict | None:
    m = S.read_json(S.build_dir(out) / MANIFEST)
    return m if isinstance(m, dict) and isinstance(m.get('files'), dict) else None


def save(out, files: dict, *, builder: str) -> dict:
    doc = {'format': FORMAT, 'builder': builder, 'created': S.utc_now(), 'files': dict(sorted(files.items()))}
    S.write_json(S.build_dir(out) / MANIFEST, doc, indent=0)
    return doc


def manifest_digest(files: dict) -> str:
    h = hashlib.sha1()
    for rel in sorted(files, key=str.lower):
        e = files[rel]
        h.update(f'{rel.lower()}\t{e["size"]}\t{e["sha1"]}\n'.encode('utf-8'))
    return h.hexdigest()


class Journal:
    """<out>/_build/journal.txt: one written path per line, appended (thread-safe)."""

    def __init__(self, out):
        self.path = S.build_dir(out) / JOURNAL
        self._lock = threading.Lock()
        self._buf = []
        self._fh = None

    def open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, 'a', encoding='utf-8', newline='\n')
        return self

    def add(self, rel):
        with self._lock:
            self._buf.append(str(rel).replace('\\', '/'))
            if len(self._buf) >= 256:
                self._flush()

    def _flush(self):
        if self._fh is not None and self._buf:
            self._fh.write('\n'.join(self._buf) + '\n')
            self._fh.flush()
        self._buf = []

    def close(self):
        with self._lock:
            self._flush()
            if self._fh is not None:
                self._fh.close()
                self._fh = None

    def remove(self):
        self.close()
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def read_journal(out) -> list:
    try:
        return [ln for ln in (S.build_dir(out) / JOURNAL).read_text(encoding='utf-8').splitlines() if ln.strip()]
    except OSError:
        return []


# ------------------------------------------------------------------------------------------------ verification
def check_files(out, files: dict, *, jobs=8, cancel=None, progress=None, trusted=None) -> dict:
    """compare the area of <out> with the manifest `files` ({rel: {size, sha1, kind}}).
    trusted: {lower rel: (size, mtime_ns)} of files hashed earlier in this process (a build's own writes): a file
    whose stat still matches is not hashed again. Returns {files, ok, missing, changed, unreadable, extra} (lists of
    dicts: path, kind, expected, found)."""
    out = Path(out)
    area = area_files(out)
    expected = {rel.lower(): (rel, e) for rel, e in files.items()}
    res = {'files': len(expected), 'ok': 0, 'missing': [], 'changed': [], 'unreadable': [], 'extra': []}
    to_hash = []
    for low, (rel, e) in sorted(expected.items()):
        actual = area.get(low)
        want = {'size': e.get('size'), 'sha1': e.get('sha1')}
        if actual is None:
            res['missing'].append({'path': rel, 'kind': e.get('kind', 'built'), 'expected': want})
            continue
        path = out / actual
        try:
            st = path.stat()
        except OSError as ex:
            res['unreadable'].append({'path': actual, 'kind': e.get('kind', 'built'), 'error': type(ex).__name__})
            continue
        if trusted is not None and trusted.get(low) == (st.st_size, st.st_mtime_ns) and st.st_size == e.get('size'):
            res['ok'] += 1
            continue
        if st.st_size != e.get('size'):
            res['changed'].append({'path': actual, 'kind': e.get('kind', 'built'), 'expected': want,
                                   'found': {'size': st.st_size, 'sha1': None}})
            continue
        to_hash.append((low, path))
    hashed = hash_files(to_hash, jobs=jobs, cancel=cancel, progress=progress)
    for low, path in to_hash:
        rel, e = expected[low]
        actual = area[low]
        r = hashed.get(low)
        want = {'size': e.get('size'), 'sha1': e.get('sha1')}
        if isinstance(r, OSError) or r is None:
            res['unreadable'].append({'path': actual, 'kind': e.get('kind', 'built'),
                                      'error': type(r).__name__ if r is not None else 'unknown'})
        elif r[1] != e.get('sha1') or r[0] != e.get('size'):
            res['changed'].append({'path': actual, 'kind': e.get('kind', 'built'), 'expected': want,
                                   'found': {'size': r[0], 'sha1': r[1]}})
        else:
            res['ok'] += 1
    for low, actual in sorted(area.items()):
        if low not in expected:
            try:
                size = (out / actual).stat().st_size
            except OSError:
                size = None
            res['extra'].append({'path': actual, 'size': size, 'temp': bool(TMP_RX.search(actual))})
    return res


def group(code: str, items: list, limit=LIST_LIMIT) -> dict:
    g = {'code': code, 'count': len(items), 'cause_hint': CAUSES.get(code, ''), 'files': items[:limit]}
    kinds = {}
    for it in items:
        if it.get('kind'):
            kinds[it['kind']] = kinds.get(it['kind'], 0) + 1
    if kinds:
        g['kinds'] = kinds
    return g


def groups_of(res: dict, extra_groups=(), limit=LIST_LIMIT) -> list:
    out = [group(code, res.get(code) or [], limit) for code in ('missing', 'changed', 'unreadable', 'extra')
           if res.get(code)]
    out += [g for g in extra_groups if g.get('count')]
    return out


def counts_of(res: dict, groups: list) -> dict:
    c = {'files': res.get('files', 0), 'ok': res.get('ok', 0)}
    for g in groups:
        c[g['code']] = g['count']
    return c


def trim_groups(groups: list, limit=EVENT_LIMIT) -> list:
    """groups for the result event: the first `limit` files of each."""
    return [dict(g, files=g['files'][:limit]) for g in groups]


def write_report(out, doc: dict):
    S.write_json(S.build_dir(out) / VERIFY_REPORT, doc)
    return S.build_dir(out) / VERIFY_REPORT


# ------------------------------------------------------------------------------------------------ clean
def clean_targets(out) -> list:
    """actual rels the builder made in <out>'s area: the manifest, the registry, the journal and the base-file list
    of every build (also an interrupted one), plus leftover temp files. Never an owned root entry."""
    out = Path(out)
    area = area_files(out)
    wanted = set()
    m = load(out)
    if m:
        wanted |= {r.lower() for r in m['files']}
    reg = S.read_json(S.build_dir(out) / 'registry.json', {}) or {}
    for key, e in (reg.get('entries') or {}).items():
        wanted.add(str((e or {}).get('rel') or key).lower())
    wanted |= {r.lower() for r in read_journal(out)}
    targets = []
    for low, actual in area.items():
        if low in wanted or TMP_RX.search(actual):
            targets.append(actual)
    return sorted(targets)


def remove_empty_dirs(root, keep_top=()):
    """remove the empty folders under root (bottom-up); the root entries in keep_top are left alone."""
    root = Path(root)
    keep = {k.lower() for k in keep_top}
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        p = Path(dirpath)
        if p == root:
            continue
        rel = p.relative_to(root).as_posix()
        if rel.split('/', 1)[0].lower() in keep:
            continue
        try:
            p.rmdir()
        except OSError:
            pass
