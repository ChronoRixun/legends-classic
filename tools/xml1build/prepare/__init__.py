"""xml1build.prepare - the prepare phase (BUILDER_DESIGN.md 1.5; SPEC.md section 27): regenerate, on the user's PC,
every game-derived input the pipeline reads, from the XML1 Xbox disc image + the XML2 install, into a cache.

Stages (each a module with STAGE, VERSION and run(...); outputs are published atomically by renaming a
'.partial' directory, and reused while their cache key - stage version + digests of the inputs - matches):

  P1 disc    (disc.py)    the disc image -> loose/ (the .fb bundles unpacked, _fb_manifest.json), assets/
                          (assetsfb.zip unzipped, minus the bundles), xbox/ (default.xbe, sounds/zsds, movies/ntsc),
                          movies.json.  = today's xml1_loose / xml1_assets / xml1_xbox (the parts the build reads).
  P2 tables  (tables.py)  P1 + the XML2 install -> mission_plan.json (+ the mission text files), collisions.json,
                          x2_stats_refs.json, names_xml1.json.  = the tracked research/ copies.
  P3 scripts (scripts.py) P1 + P2 -> out/ (the rewritten XML1 scripts, dialogs, missions, zone acts, inline
                          rewrites).  = research/scripts/out (rewrite_scripts.py, retired into this stage)
  P4 sound   (sound.py)   P1 + P2 names + XML2's Sounds/eng -> all_ima/eng (every bank converted 1:1) and
                          merged/eng.  = research/sound/out/{all_ima,merged}/eng
  P5 music   (music.py)   P1 + XML2's Sounds/eng -> banks/eng (tools/fix_music.py fix; every bank checked with
                          media_music.check_bank).  = research/sound/music0x20/banks/eng

prepared_sources runs them in that order and hands the build a Sources whose research overrides point at them
(scripts/out, sound/out, sound/music0x20, and P2's four tables).

Cache layout (<cache> = --cache):
  <cache>/<disc_id>/disc/                           P1 (stage.json = its key + counts)
  <cache>/<disc_id>/prepared/<stage>-v<N>-<digest>/ P2 tables, P3 scripts, P4 sound, P5 music
disc_id = the first 12 hex of default.xbe's md5 + the first 8 of the sha1 of assetsfb.zip's central directory (every
member's name, size and CRC-32), so it names the disc content, not the image file or its layout."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path


class PrepareError(RuntimeError):
    """An input the prepare phase cannot use. code: a stable E_* string (BUILDER_DESIGN.md 2.3); hint: what to do;
    detail: machine-readable facts (what was detected)."""

    def __init__(self, code, msg, hint=None, detail=None):
        super().__init__(f'{code}: {msg}' + (f' ({hint})' if hint else ''))
        self.code, self.msg, self.hint, self.detail = code, msg, hint, dict(detail or {})


class Cancelled(RuntimeError):
    """the cancel callback asked a stage to stop (its .partial directory is left for the next run to delete)."""


class StageFailed(RuntimeError):
    """a stage could not produce a correct output from usable inputs (our bug, not the user's input): nothing is
    published. code: a stable E_* string; detail: machine-readable facts."""

    def __init__(self, code, msg, detail=None):
        super().__init__(f'{code}: {msg}')
        self.code, self.msg, self.detail = code, msg, dict(detail or {})


def ntfs_walk(root):
    """os.walk(root) in NTFS directory order on every file system (FindFirstFile on NTFS lists a directory sorted by
    the upper-cased names; checked equal to os.walk on the P1 trees), with '/'-joined paths. Yields
    (dirpath, dirnames, filenames); dirnames may be pruned in place, as with os.walk."""
    stack = [str(root).replace('\\', '/').rstrip('/') or '/']
    while stack:
        d = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        dirs = sorted((e.name for e in entries if e.is_dir()), key=str.upper)
        files = sorted((e.name for e in entries if not e.is_dir()), key=str.upper)
        yield d, dirs, files
        stack.extend(f'{d}/{x}' for x in reversed(dirs))


def find_ci(root, *parts):
    """root/<parts> matched case-insensitively component by component (the XML2 install on a case-sensitive file
    system), or None."""
    p = Path(root)
    for part in parts:
        if (p / part).exists():
            p = p / part
            continue
        try:
            hit = next((c for c in p.iterdir() if c.name.lower() == part.lower()), None)
        except OSError:
            return None
        if hit is None:
            return None
        p = hit
    return p


def sha1_file(p) -> str:
    h = hashlib.sha1()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def listing_digest(root) -> str:
    """digest of a tree's listing (rel, size, mtime_ns), for cache keys over an input we do not hash."""
    rows = []
    root = str(root)
    for d, _, fs in ntfs_walk(root):
        for f in fs:
            p = f'{d}/{f}'
            st = os.stat(p)
            rows.append((p[len(root):].lower(), st.st_size, st.st_mtime_ns))
    return digest(rows)


def write_json_crlf(path, obj):
    """json.dump(obj, open(path, 'w'), indent=1) as the research tools wrote it on Windows (ASCII, CRLF)."""
    Path(path).write_bytes(json.dumps(obj, indent=1).replace('\n', '\r\n').encode('ascii'))


def rebase_paths(obj, rebase):
    """obj with every string that starts with rebase[0] (either separator) starting with rebase[1] instead: the
    stages write into '<final>.partial' and publish by renaming, so reports name the final directory."""
    if not rebase:
        return obj
    old, new = rebase
    olds = (old, old.replace('/', '\\'))
    if isinstance(obj, dict):
        return {k: rebase_paths(v, rebase) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(rebase_paths(v, rebase) for v in obj)
    if isinstance(obj, str):
        for o in olds:
            if obj.startswith(o):
                return new + obj[len(o):]
    return obj


MEMORY_ENV = 'XML1_PREPARE_MEMORY_MB'     # override the memory budget of the sound stages' worker pools (MB)


def available_memory_mb():
    """memory a stage may plan for, in MB: the smaller of the free physical memory and the free commit (Windows:
    GlobalMemoryStatusEx; Linux: MemAvailable), or None when unknown. $XML1_PREPARE_MEMORY_MB overrides it."""
    v = os.environ.get(MEMORY_ENV)
    if v:
        try:
            return max(0, int(v))
        except ValueError:
            pass
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes as W

            class MS(ctypes.Structure):
                _fields_ = [('dwLength', W.DWORD), ('dwMemoryLoad', W.DWORD)] + \
                    [(n, ctypes.c_ulonglong) for n in ('ullTotalPhys', 'ullAvailPhys', 'ullTotalPageFile',
                                                         'ullAvailPageFile', 'ullTotalVirtual', 'ullAvailVirtual',
                                                         'ullAvailExtendedVirtual')]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            if not ctypes.WinDLL('kernel32').GlobalMemoryStatusEx(ctypes.byref(m)):
                return None
            return int(min(m.ullAvailPhys, m.ullAvailPageFile) >> 20)
        with open('/proc/meminfo') as fh:
            for line in fh:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) >> 10
    except (OSError, ValueError, AttributeError):
        return None
    return None


def memory_budget_mb(reserve=1024, share=0.85):
    """the worker-pool budget: share of available_memory_mb() minus a reserve for the parent and the system (None
    when unknown: no memory limit, only the job count)."""
    a = available_memory_mb()
    return None if a is None else max(0, int(a * share) - reserve)


def pool_map(fn, items, jobs, *, cancel=None, progress=None, unit='items', cost=None, budget=None):
    """[fn(item) for item in items], in a process pool of min(jobs, len(items)) workers when jobs > 1 (one item per
    task, started in list order, so put the biggest first). Results come back in item order.
    cost(item) -> MB and budget (MB): an item starts only while the estimated memory of the running items plus its
    own fits the budget (one item always runs), so big items run few at a time and small ones many - the sound
    stages' workers peak at 0.5-2.7 GB each and 16 big ones exceed a 32 GB PC.
    While waiting the cancel flag is checked: a cancel terminates the workers and raises Cancelled.
    progress(done, total, unit)."""
    items = list(items)
    n = len(items)
    out = [None] * n
    if jobs <= 1 or n <= 1:
        for i, it in enumerate(items):
            check_cancel(cancel)
            out[i] = fn(it)
            if progress is not None:
                progress(i + 1, n, unit)
        return out
    import collections
    import multiprocessing as mp
    import queue
    workers = min(jobs, n)
    costs = [float(cost(it)) if cost else 0.0 for it in items]
    pending = collections.deque(range(n))
    running = {}                                   # index -> cost
    q = queue.Queue()
    pool = mp.Pool(workers)
    try:
        done = 0
        while done < n:
            while pending and len(running) < workers and (
                    not running or budget is None or sum(running.values()) + costs[pending[0]] <= budget):
                i = pending.popleft()
                running[i] = costs[i]
                pool.apply_async(_indexed, ((fn, i, items[i]),), callback=q.put,
                                 error_callback=lambda e, i=i: q.put((i, _Failed(e))))
            try:
                i, r = q.get(timeout=0.5)
            except queue.Empty:
                check_cancel(cancel)
                continue
            if isinstance(r, _Failed):
                raise r.exc
            running.pop(i, None)
            out[i] = r
            done += 1
            if progress is not None:
                progress(done, n, unit)
            check_cancel(cancel)
        pool.close()
    except BaseException:
        pool.terminate()
        raise
    finally:
        pool.join()
    return out


class _Failed:
    def __init__(self, exc):
        self.exc = exc


def _indexed(a):
    fn, i, it = a
    return i, fn(it)


def digest(obj) -> str:
    """sha1 of a JSON-able object (sorted keys, compact): cache keys."""
    return hashlib.sha1(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def check_cancel(cancel):
    if cancel is not None and (cancel.is_set() if hasattr(cancel, 'is_set') else cancel()):
        raise Cancelled('cancelled')


def read_stage(d: Path):
    """stage.json of a published stage directory, or None."""
    try:
        return json.loads((Path(d) / 'stage.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def rmtree(p: Path):
    """delete a directory tree (read-only files too)."""
    def onexc(fn, path, exc):
        os.chmod(path, 0o666)
        fn(path)
    if Path(p).exists():
        shutil.rmtree(p, onexc=onexc)


RENAME_TRIES = 40                 # x RENAME_WAIT: ~10 s
RENAME_WAIT = 0.25


def rename(src: Path, dst: Path, tries: int = RENAME_TRIES, wait: float = RENAME_WAIT):
    """Path.rename that waits out a transient Windows lock. Right after a stage writes thousands of files, an
    antivirus or indexer scan can still hold one of them open, and renaming the directory then fails with
    PermissionError (WinError 5); the same rename succeeds moments later (seen 2026-10-01 on the scripts stage)."""
    for i in range(tries):
        try:
            return Path(src).rename(dst)
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(wait)

def publish(partial: Path, final: Path, stage: dict):
    """write stage.json into the finished partial directory and rename it to final (replacing an older final)."""
    stage = dict(stage, published=time.strftime('%Y-%m-%dT%H:%M:%S'))
    (partial / 'stage.json').write_text(json.dumps(stage, indent=1), encoding='utf-8')
    if final.exists():
        old = final.with_name(final.name + '.old')
        rmtree(old)
        rename(final, old)
        rmtree(old)
    rename(partial, final)
    return stage


STAGES = ('disc', 'tables', 'scripts', 'sound', 'music')
# research-relative prefixes the prepared stages replace (Sources overrides): stage -> (rel, dir below the stage's)
STAGE_OVERRIDES = {'scripts': ('scripts/out', 'out'), 'sound': ('sound/out', ''), 'music': ('sound/music0x20', '')}


def run_stages(cache: Path, xml2: Path, iso: Path | None = None, *, stages=STAGES, jobs=None, movies=True,
               log=print, cancel=None, progress=None, force=()) -> dict:
    """run (or reuse) the prepare stages in order; returns {stage: {'dir', 'stage', 'cached'}}. P1 and P2 always run
    (every later stage needs them; each is reused while its key matches); `stages` picks which of P3-P5 run;
    force = stage names to re-run although cached; progress(stage, done, total, unit).

    With iso: P1 is keyed by that image's content (re-run when the key changes). Without: the cache must hold
    exactly one published P1 disc (the user may have removed the image after the first build)."""
    from . import disc as P1, tables as P2, scripts as P3, sound as P4, music as P5
    cache = Path(cache).resolve()
    xml2 = Path(xml2)

    def prog(stage):
        return (lambda done, total, unit: progress(stage, done, total, unit)) if progress else None

    res = {}
    if iso is not None:
        d1 = P1.run(iso, cache, log=log, cancel=cancel, movies=movies, force='disc' in force,
                    progress=prog('disc'))
    else:
        found = P1.find_published(cache)
        if not found:
            raise PrepareError('E_CACHE_EMPTY', f'the cache {cache} holds no prepared disc',
                               'pass --iso with your X-Men Legends Xbox disc image')
        if len(found) > 1:
            raise PrepareError('E_CACHE_AMBIGUOUS', f'the cache {cache} holds {len(found)} prepared discs '
                               f'({", ".join(p.parent.name for p in found)})', 'pass --iso to pick one')
        d1 = {'dir': found[0], 'stage': read_stage(found[0]), 'cached': True}
        if movies and not P1.has_movies(d1['stage']):
            raise PrepareError('E_CACHE_NO_MOVIES', f'the cached disc {d1["dir"]} was prepared without its movies',
                               'pass --iso to add them, or build with --no-movies')
        log(f'[prepare] disc: using {d1["dir"]} (no --iso)')
    res['disc'] = d1

    res['tables'] = P2.run(d1['dir'], xml2, log=log, cancel=cancel, force='tables' in force)
    want = stages.__contains__
    t2 = res['tables']['dir']
    if want('scripts'):
        res['scripts'] = P3.run(d1['dir'], t2, log=log, cancel=cancel, force='scripts' in force)
    if want('sound'):
        res['sound'] = P4.run(d1['dir'], t2, xml2, jobs=jobs, log=log, cancel=cancel, progress=prog('sound'),
                              force='sound' in force)
    if want('music'):
        res['music'] = P5.run(d1['dir'], xml2, jobs=jobs, log=log, cancel=cancel, progress=prog('music'),
                              force='music' in force)
    return res


def prepared_sources(cache: Path, xml2: Path, iso: Path | None = None, *, jobs=None, movies=True, log=print,
                     cancel=None, progress=None):
    """run (or reuse) every prepare stage and return the prepared Sources for a build (run_stages; movies=False:
    a --no-movies build, P1 need not copy the movie files)."""
    from ..sources import Sources
    res = run_stages(cache, xml2, iso, jobs=jobs, movies=movies, log=log, cancel=cancel, progress=progress)
    keys = ('stage', 'version', 'key', 'disc_id', 'movies', 'seconds')
    stages = {name: {k: r['stage'].get(k) for k in keys if k in r['stage']} for name, r in res.items()}
    overrides = {}
    for name, (rel, sub) in STAGE_OVERRIDES.items():
        overrides[rel] = res[name]['dir'] / sub if sub else res[name]['dir']
    return Sources.prepared(res['disc']['dir'], xml2, tables_dir=res['tables']['dir'], cache=Path(cache).resolve(),
                            stages=stages, overrides=overrides)
