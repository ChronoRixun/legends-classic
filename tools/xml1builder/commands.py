"""xml1builder.commands - info, build, verify and clean (BUILDER_DESIGN.md 2.1; the launcher's fake builder is the
protocol reference: the same events, result fields, error codes and exit codes).

build: probe (disc image, XML2 install, destination, space; locks; plan) -> the prepare stages P1-P5 (cached) ->
sync (the base install; every copy read back against its source) -> content (the pipeline's modules, builder mode:
the sha1 of every file written from memory is recorded) -> sweep (never the launcher's / player's files) -> validate
-> finish: every file of the build read back against its expected hash (the XML2 source for base files, the recorded
sha1 for written files, the source for the modules' copies; a copy that differs is copied again, a written file that
differs or is gone is E_IO naming it), the manifest, the port's xml2-fix.ini keys (merged), verify-report.json, the
stamp (last). The read-back runs at the end on 8 threads rather than after each write: reopening every file right
after writing it made the content modules 2-4x slower on Windows (an antivirus scan per open).

Re-running into the same folder is the rebuild, the resume after a cancel and the repair of a damaged build: the
prepare stages come from the cache, every content module rewrites its files, the sync copies again what differs by
size or time, the final read-back copies again what differs by content (90-105 s on Owen's PC)."""
from __future__ import annotations

import datetime
import os
import platform
import re
import shutil
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from . import CONTENT_VERSION, DISCLAIMER, ISSUES_URL, PROJECT, REPO, VERSION
from . import inputs as I
from . import manifest as M
from . import plan as PL
from . import space as SP
from . import stamp as S
from .errors import IO_CAUSES, BuilderError, Cancelled, REPORT_HINT, io_error, io_in_chain
from .events import mask
from .lock import FileLock, LockHeld

HASH_JOBS = max(1, min(8, os.cpu_count() or 1))
VALIDATE_CHECKS = 22                       # validate V1..V21 + heroes_validate
_V_LINE = re.compile(r'^V\d+ .+ \.\.\.$')


def version_info() -> dict:
    from . import resources as R
    return {'version': VERSION, 'content_version': CONTENT_VERSION, 'commit': R.commit()}


def default_cache() -> Path:
    base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), '.cache')
    return Path(base) / 'xml1-builder' / 'cache'


def _overlap(a: Path, b: Path) -> bool:
    a, b = a.resolve(), b.resolve()
    return a == b or a in b.parents or b in a.parents


def _inside(child: Path, parent: Path) -> bool:
    c, p = child.resolve(), parent.resolve()
    return c == p or p in c.parents


# ================================================================================================ the build's state
@dataclass
class Job:
    out: Path
    xml2: Path
    cache: Path
    iso: Path | None
    movies: bool
    jobs: int
    prepare_jobs: int
    disc: dict = field(default_factory=dict)
    ident: dict | None = None
    xml2_info: dict = field(default_factory=dict)
    listing: dict = field(default_factory=dict)
    prev_manifest: dict | None = None
    prepared: dict = field(default_factory=dict)
    sources: object = None
    base_files: dict = field(default_factory=dict)
    trusted: dict = field(default_factory=dict)
    journal: object = None
    ctx: object = None
    args: object = None
    t0: float = 0.0
    warnings: int = 0
    stages: dict = field(default_factory=dict)
    kept: dict = field(default_factory=dict)      # {rel: errors.IO_CAUSES code}: strays the sweep could not delete


class Ctl:
    """what a stage of the pipeline gets: the cancel token, progress, logs; and the pipeline's checkpoint."""

    def __init__(self, output, cancel, job):
        self.output, self.cancel, self.job = output, cancel, job
        self.progress_obj = None
        self.stage = 'probe'
        self.module = None
        self.writes = 0
        self.expected_writes = PL.EXPECTED_FILES
        self.checks = 0

    def check(self):
        self.cancel.check()

    def progress(self, sid, done, total, unit=None, force=False):
        if self.progress_obj is not None:
            self.progress_obj.update(sid, done, total, unit, force=force)

    def progress_fn(self, sid):
        return lambda done, total, unit=None: self.progress(sid, done, total, unit)

    def human(self, text):
        self.output.human(text)

    def prepare_log(self, text):
        self.output.human(text)
        text = str(text)
        if text.startswith('[prepare] '):
            self.output.event('log', level='info', stage=self.stage, msg=text[len('[prepare] '):][:400])

    def checkpoint(self, kind, detail=None):
        """xml1build.common.checkpoint: cancel, progress, the journal."""
        self.cancel.check()
        if kind == 'write':
            rel = detail
            self.job.journal.add(rel)
            self.job.trusted.pop(rel.lower(), None)          # written again: the final verification reads it back
            if self.stage == 'content':
                self.writes += 1
                self.progress('content', min(self.writes, self.expected_writes), self.expected_writes, 'files')
        elif kind == 'log':
            module, msg = detail
            if self.stage == 'content' and msg == 'start':
                self.output.event('log', level='info', stage='content', msg=f'{module}: running')
            elif self.stage == 'validate' and module == 'validate' and _V_LINE.match(str(msg)):
                self.checks += 1
                self.progress('validate', min(self.checks, VALIDATE_CHECKS), VALIDATE_CHECKS, 'checks')
            elif self.stage == 'validate' and module == 'heroes_validate' and msg == 'start':
                self.progress('validate', VALIDATE_CHECKS - 1, VALIDATE_CHECKS, 'checks')


def failure(exc, stage, job=None) -> BuilderError:
    """any exception of a build as the BuilderError reported for it. An OS-level I/O error (a file held open, a full
    or failing drive: errors.io_cause) is E_IO naming the file (relative to <out> / the cache / the XML2 folder of
    `job`) and the cause, also when a stage wrapped it; E_PIPELINE / E_INTERNAL are left for our bugs."""
    if isinstance(exc, BuilderError):
        if exc.stage is None:
            exc.stage = stage
        return exc
    roots = [(job.out, 'out'), (job.cache, 'cache'), (job.xml2, 'xml2')] if job is not None else []
    try:
        from xml1build import prepare
        from xml1build.common import WriteCheckError
    except ImportError:                                   # a stub pipeline in the tests
        prepare = WriteCheckError = None
    if WriteCheckError is not None and isinstance(exc, WriteCheckError):
        return BuilderError('E_IO', f'A file did not read back as it was written: {exc.rel} (an antivirus program, '
                            'a full or failing disk).', None,
                            {'path': exc.rel, 'expected_sha1': exc.want, 'found_sha1': exc.got, 'size': exc.size},
                            stage)
    if prepare is not None and isinstance(exc, prepare.PrepareError):
        return BuilderError(exc.code, exc.msg[:1].upper() + exc.msg[1:] + ('' if exc.msg.endswith('.') else '.'),
                            (exc.hint[:1].upper() + exc.hint[1:]) if exc.hint else None, exc.detail, stage)
    if isinstance(exc, OSError):                          # raised straight through (prepare, sync, finish, ...)
        return io_error(exc, stage, roots, strict=False)
    wrapped = io_in_chain(exc)                            # an OSError a stage or a module wrapped
    if wrapped is not None:
        return io_error(wrapped, stage, roots)
    if prepare is not None and isinstance(exc, prepare.StageFailed):
        return BuilderError('E_PIPELINE', f'A step of the build failed: {stage} ({exc.msg[:300]}).', None,
                            {'module': stage, 'code': exc.code, **{k: v for k, v in exc.detail.items()
                                                                  if isinstance(v, (int, str))}}, stage)
    return BuilderError('E_INTERNAL', f'Internal error: {type(exc).__name__}: {exc}', REPORT_HINT, {}, stage)


def is_cancel(exc) -> bool:
    if isinstance(exc, (Cancelled, KeyboardInterrupt)):
        return True
    try:
        from xml1build import prepare
        return isinstance(exc, prepare.Cancelled)
    except ImportError:
        return False


def log_header(output, command, argv, extra=()):
    """the log's first lines (design 2.4): versions, the machine, the command line (profile path masked)."""
    v = version_info()
    output.human(f'{PROJECT} xml1-builder {v["version"]} (content {v["content_version"]}, commit {v["commit"]}); '
                 f'{REPO}')
    for line in DISCLAIMER:
        output.human(line)
    from . import resources as R
    output.human(f'python {platform.python_version()} ({platform.architecture()[0]}); {platform.platform()}; '
                 f'{os.cpu_count()} logical CPUs; frozen={R.frozen()}; data {mask(R.repo_root())}')
    output.human(f'command: {command}; argv: {mask(" ".join(argv))}')
    for line in extra:
        output.human(line)


# ================================================================================================ checks
def check_destination(out: Path, *, xml2=None, cache=None, iso=None, pipeline=None):
    """E_OUT_UNSAFE / E_OUT_FOREIGN before anything is written."""
    out = Path(out)
    if len(out.resolve().parts) <= 1:
        raise BuilderError('E_OUT_UNSAFE', 'The game can\'t be built at the root of a drive.', None,
                           {'out': mask(out)})
    for other, label in ((xml2, 'X-Men Legends II\'s folder'), (cache, 'the build cache')):
        if other and _overlap(out, Path(other)):
            raise BuilderError('E_OUT_UNSAFE', f'The game can\'t be built inside {label} (or around it).', None,
                               {'out': mask(out), 'conflict': mask(other)})
    if iso and _inside(Path(iso), out):
        raise BuilderError('E_OUT_UNSAFE', 'The disc image is inside the destination folder.', None,
                           {'out': mask(out), 'conflict': mask(iso)})
    if pipeline is not None and xml2:
        pipeline.check_out_safe(out, xml2, (cache,) if cache else ())
    if out.exists() and not out.is_dir():
        raise BuilderError('E_OUT_FOREIGN', 'The destination is a file, not a folder.', None, {'out': mask(out)})
    # the same rule as info / verify (stamp.out_state): only the launcher's / the player's files = absent
    if out.exists() and S.out_state(out, content_version=CONTENT_VERSION)[0] == 'foreign':
        raise BuilderError('E_OUT_FOREIGN', 'The destination folder already holds other files.', None,
                           {'out': mask(out)})


def check_cache(cache: Path, *, xml2=None):
    if xml2 and _overlap(Path(cache), Path(xml2)):
        raise BuilderError('E_OUT_UNSAFE', 'The build cache can\'t be inside X-Men Legends II\'s folder.', None,
                           {'cache': mask(cache), 'conflict': mask(xml2)})


# ================================================================================================ info
def cmd_info(a, output, pipeline_factory):
    info = {}
    fail = None
    pipeline = None
    try:
        disc = ident = None
        if a.iso:
            pipeline = pipeline_factory()
            ident, disc = pipeline.identify(a.iso)
            info['iso'] = disc
            if not disc['known']:
                output.event('warning', stage='probe', code='W_ISO_UNKNOWN_DUMP',
                             msg='This disc image is not in the list of known dumps; the build checks it anyway.')
        listing = None
        if a.xml2:
            listing = I.base_listing(a.xml2) if Path(a.xml2).is_dir() else {}
            info['xml2'] = I.check_xml2(a.xml2, allow_unknown=a.allow_unknown_exe, listing=listing,
                                        warn=lambda code, msg, detail: output.event('warning', stage='probe', code=code,
                                                                                    msg=msg, detail=detail))
        profile = None
        if a.out:
            profile = (pipeline or pipeline_factory()).profile()
            state, reasons, stamp = S.out_state(a.out, content_version=CONTENT_VERSION, profile=profile,
                                                disc_digest=disc['digest'] if disc else None,
                                                xml2_digest=info['xml2']['base_digest'] if 'xml2' in info else None)
            info['out'] = {'path': mask(a.out), 'state': state, 'reasons': reasons, 'stamp': stamp}
        stamp_disc = ((info.get('out') or {}).get('stamp') or {}).get('inputs', {}).get('disc', {}).get('disc_id')
        disc_id = disc['disc_id'] if disc else stamp_disc
        cache = Path(a.cache) if a.cache else None
        if cache:
            stages = []
            if disc_id and (cache / disc_id).is_dir():
                if a.xml2 and 'xml2' in info:
                    stages = sorted((pipeline or pipeline_factory()).predict_cached(
                        cache, disc_id, ident, Path(a.xml2), not a.no_movies), key=PL.STAGE_IDS.index)
                else:
                    stages = published_stages(cache / disc_id)
            sizes = {c.name: (SP.folder_bytes(c) if c.is_dir() else c.stat().st_size)
                     for c in cache.iterdir()} if cache.is_dir() else {}
            info['cache'] = {'path': mask(cache), 'bytes': sum(sizes.values()), 'disc_bytes': sizes.get(disc_id, 0),
                             'disc_id': disc_id, 'stages': stages}
        if disc:
            movies = not a.no_movies
            info['space'] = SP.report(out=a.out, cache=a.cache, disc_id=disc['disc_id'], movies=movies,
                                      sizes=(pipeline or pipeline_factory()).sizes(movies))
            kernel = (pipeline or pipeline_factory()).kernel_present()
            info['estimate'] = PL.estimate(jobs=a.jobs, kernel=kernel, movies=movies)
            cached = set((info.get('cache') or {}).get('stages') or [])
            if set(PL.PREPARE_STAGES) <= cached:
                info['estimate']['first_build_s'] = info['estimate']['rebuild_s']
    except BuilderError as e:
        fail = e
    if fail is not None:
        output.event('error', stage='probe', code=fail.code, msg=fail.msg, hint=fail.hint, detail=fail.detail)
    code = fail.exit_code if fail is not None else 0
    output.event('result', ok=code == 0, exit=code, info=info)
    return code


def published_stages(disc_root: Path) -> list:
    """the prepare stages with a published directory for this disc (without their keys: info without --xml2)."""
    names = {'extract': 'disc', 'tables': 'tables', 'scripts': 'scripts', 'sound': 'sound', 'music': 'music'}
    found = []
    for sid in PL.PREPARE_STAGES:
        if sid == 'extract':
            ok = (disc_root / 'disc' / 'stage.json').is_file()
        else:
            ok = any((d / 'stage.json').is_file() for d in (disc_root / 'prepared').glob(f'{names[sid]}-v*')
                     if not d.name.endswith(('.partial', '.old')))
        if ok:
            found.append(sid)
    return found


# ================================================================================================ build
def cmd_build(a, output, cancel, pipeline_factory):
    t_start = time.monotonic()
    for name in ('xml2', 'out'):
        if not getattr(a, name):
            raise BuilderError('E_USAGE', f'build needs --{name}.', '', {})
    out_dir = Path(a.out).resolve()
    xml2 = Path(a.xml2).resolve()
    cache = Path(a.cache).resolve() if a.cache else default_cache()
    iso = Path(a.iso).resolve() if a.iso else None
    movies = not a.no_movies
    prepare_jobs = max(1, a.jobs or PL.default_jobs())
    jobs = max(1, a.jobs or max(1, (os.cpu_count() or 2) // 2))
    job = Job(out=out_dir, xml2=xml2, cache=cache, iso=iso, movies=movies, jobs=jobs, prepare_jobs=prepare_jobs)
    ctl = Ctl(output, cancel, job)
    pipeline = pipeline_factory()
    out_lock = cache_lock = None
    log_ready = False
    installed = None

    def warn(code, msg, detail=None, stage='probe', count=None):
        """a warning event; detail.count = how many (files, ...; default 1). count: W_PIPELINE's number of pipeline
        warnings (also the top-level count, as before; added to the stamp's warnings)."""
        fields = {'stage': stage, 'code': code, 'msg': msg, 'detail': dict(detail or {})}
        if count is not None:
            fields['count'] = count
            fields['detail'].setdefault('count', count)
        output.event('warning', **fields)
        job.warnings += count if count is not None else 1

    def hard_stop():
        output.human('cancel: the build did not stop in time; ending it now (it resumes where it left off)')
        output.event('result', ok=False, exit=5, cancelled=True, out=mask(out_dir))
        for lk in (out_lock, cache_lock):
            if lk is not None:
                lk.release()
        output.close()

    cancel.on_hard_stop(hard_stop)
    try:
        # ---------------------------------------------------------------- probe
        if iso is not None:
            job.ident, job.disc = pipeline.identify(iso)
        else:
            prefer = ((S.read_stamp(out_dir) or S.read_json(S.build_dir(out_dir) / S.BUILDING, {}) or {})
                      .get('inputs', {}).get('disc', {}).get('disc_id'))
            found = pipeline.cached_disc(cache, prefer) or (pipeline.cached_disc(cache) if prefer else None)
            if not found:
                raise BuilderError('E_USAGE', 'build needs --iso (the build cache holds no prepared disc to use '
                                   'instead).', 'Choose your X-Men Legends Xbox disc image.', {'cache': mask(cache)})
            job.ident, job.disc = found
        if not job.disc.get('known'):
            warn('W_ISO_UNKNOWN_DUMP', 'This disc image is not in the list of known dumps; the build checks it '
                                       'anyway.')
        check_cache(cache, xml2=xml2)
        job.listing = I.base_listing(xml2) if xml2.is_dir() else {}
        job.xml2_info = I.check_xml2(xml2, allow_unknown=a.allow_unknown_exe, listing=job.listing,
                                     warn=lambda code, msg, detail: warn(code, msg, detail))
        check_destination(out_dir, xml2=xml2, cache=cache, iso=iso, pipeline=pipeline)
        space = SP.report(out=out_dir, cache=cache, disc_id=job.disc['disc_id'], movies=movies,
                          sizes=pipeline.sizes(movies))
        for where in ('out', 'cache'):
            if where in space and not space[where]['ok']:
                raise BuilderError('E_SPACE', f'Not enough free space on {space[where]["volume"]}.', None,
                                   space[where])
        if a.link_base:
            warn('W_LINK_BASE', '--link-base (hard links) is not supported yet: the base files are copied.')

        # ---------------------------------------------------------------- locks, log, state
        (out_dir / S.BUILD_DIR).mkdir(parents=True, exist_ok=True)
        try:
            out_lock = FileLock(out_dir / S.BUILD_DIR / 'lock', 'build').acquire()
        except LockHeld as e:
            raise BuilderError('E_OUT_LOCKED', 'Another build is writing to this folder.', None,
                               {'pid': e.holder.get('pid')}) from None
        try:
            cache.mkdir(parents=True, exist_ok=True)
            cache_lock = FileLock(cache / 'lock', f'build {mask(out_dir)}').acquire()
        except LockHeld as e:
            raise BuilderError('E_CACHE_LOCKED', 'Another build is using the build cache.', None,
                               {'pid': e.holder.get('pid'), 'cache': mask(cache)}) from None
        if not a.log:
            output.open_log(out_dir / S.BUILD_DIR / 'builder.log', rotate=True)
        log_ready = True
        output.human(f'inputs: disc {job.disc.get("format")} {job.disc.get("title_id")} xbe {job.disc.get("xbe_md5")} '
                     f'known={job.disc.get("dump") or False}; XML2 exe {job.xml2_info.get("exe_md5")} '
                     f'({job.xml2_info.get("base_files")} base files); movies={movies}; jobs={jobs}/{prepare_jobs}')
        output.human(f'space: {space}')
        job.prev_manifest = M.load(out_dir)
        S.start_building(out_dir, {'builder': version_info(), 'inputs': {'disc': {'disc_id': job.disc['disc_id']}},
                                   'movies': movies})
        job.journal = M.Journal(out_dir).open()

        cached = pipeline.predict_cached(cache, job.disc['disc_id'], job.ident if iso is not None else None, xml2,
                                         movies)
        kernel = True
        if not {'sound', 'music'} <= cached:
            kernel, status = pipeline.sound_kernel()
            output.human(f'sound codec: {status}')
        synced = (out_dir / 'XMen2.exe').is_file()
        weights = PL.weights(jobs=prepare_jobs, kernel=kernel, movies=movies, synced=synced,
                             hashed=job.prev_manifest is not None)
        plan = PL.make_plan(weights, cached)
        output.event('plan', stages=plan)
        progress = PL.Progress(plan, lambda **f: output.event('progress', **f))
        ctl.progress_obj = progress
        ctl.expected_writes = pipeline.expected_files(out_dir, movies)
        previous = pipeline.install_checkpoint(ctl.checkpoint)
        installed = previous if previous is not None else True

        with PL.Ticker(progress):
            def run_stage(sid, fn, cached_flag=None, seconds=None):
                ctl.stage = sid
                output.event('stage', id=sid, state='start')
                progress.start(sid)
                r = fn()
                is_cached = bool(r) if cached_flag is None else cached_flag
                took = progress.finish(sid)
                seconds = round(took if seconds is None else seconds, 2)
                job.stages[sid] = {'seconds': seconds, 'cached': is_cached}
                output.event('stage', id=sid, state='done', seconds=seconds, cached=is_cached)
                return r

            # the probe ran before the plan could be made (it decides what is cached): report its real time
            run_stage('probe', lambda: False, cached_flag=False, seconds=time.monotonic() - t_start)
            for sid in PL.PREPARE_STAGES:
                run_stage(sid, lambda sid=sid: pipeline.prepare(sid, job, ctl))
            job.sources = pipeline.sources(job)
            run_stage('sync', lambda: pipeline.sync(job, ctl), cached_flag=False)
            content = run_stage('content', lambda: pipeline.content(job, ctl), cached_flag=False)
            if content['warnings']:
                warn('W_PIPELINE', f'{content["warnings"]} warnings (details in report.json)', stage='content',
                     count=content['warnings'])
            if content['failed'] or content['errors']:
                module = (content['failed'] or ['content'])[0]
                raise BuilderError('E_PIPELINE', f'A step of the build failed: {module}.', None,
                                   {'module': module, 'failed': content['failed'], 'errors': content['errors'],
                                    'first': content['first_errors']}, 'content')
            run_stage('sweep', lambda: pipeline.sweep(job, ctl), cached_flag=False)
            val = run_stage('validate', lambda: pipeline.validate(job, ctl), cached_flag=False)
            pipeline.write_report(job, _builder_block(job))
            if val['warnings']:
                warn('W_PIPELINE', f'{val["warnings"]} warnings (details in report.json)', stage='validate',
                     count=val['warnings'])
            if val['errors'] or not val['ok']:
                raise BuilderError('E_VALIDATE', 'The finished build did not pass its checks.', None,
                                   {'errors': val['errors'], 'first': val['first_errors']}, 'validate')
            fin = run_stage('finish', lambda: finish(a, output, job, ctl, pipeline, warn), cached_flag=False)
        stamp_doc, verify_summary = fin
        pipeline.write_report(job, _builder_block(job))
        cancel.finished()
        if a.drop_cache:
            if cache_lock is not None:
                drop = cache / job.disc['disc_id']
                if drop.is_dir():
                    _rmtree(drop)
                    output.human(f'--drop-cache: deleted {mask(drop)}')
        seconds = round(time.monotonic() - t_start, 1)
        output.human(f'build finished in {seconds} s: {verify_summary["files"]} files verified, {job.warnings} warnings')
        if not (out_dir / 'dinput.dll').is_file():
            output.human('Next: X-Men Legends needs the XML2 Fix (dinput.dll, xml2-fix 1.2.0 or newer) in this folder; '
                         'the Ultimate Legends launcher installs it, or copy it from the xml2-fix release.')
        output.event('result', ok=True, exit=0, out=mask(out_dir), report=mask(out_dir / S.BUILD_DIR / 'report.json'),
                     log=mask(output.log_path) if output.log_path else None, errors=0, warnings=job.warnings,
                     stamp=stamp_doc, verify=verify_summary, seconds=seconds)
        return 0
    except BaseException as exc:  # noqa: BLE001 - every way out reports a result
        cancel.finished()
        stage = ctl.stage
        if job.ctx is not None:
            try:
                pipeline.write_report(job, _builder_block(job, failed_stage=stage))
            except Exception:  # noqa: BLE001
                pass
        if not log_ready and not a.log:
            try:
                output.open_log(cache / 'logs' / f'builder-{datetime.datetime.now():%Y%m%d-%H%M%S}.log', rotate=False)
            except OSError:
                pass
        if is_cancel(exc):
            output.human(f'cancelled during {stage}; the next build resumes from the cache')
            output.event('result', ok=False, exit=5, cancelled=True, stage=stage, out=mask(out_dir))
            return 5
        err = failure(exc, stage, job)
        if err.code == 'E_INTERNAL':
            output.human(traceback.format_exc())
        output.event('error', stage=err.stage or stage, code=err.code, msg=err.msg, hint=err.hint, detail=err.detail)
        output.event('result', ok=False, exit=err.exit_code, out=mask(out_dir),
                     log=mask(output.log_path) if output.log_path else None)
        return err.exit_code
    finally:
        if installed is not None:
            pipeline.install_checkpoint(None if installed is True else installed)
        if job.journal is not None:
            job.journal.close()
        for lk in (cache_lock, out_lock):
            if lk is not None:
                lk.release()


def _builder_block(job, failed_stage=None) -> dict:
    v = version_info()
    return {'version': v['version'], 'commit': v['commit'], 'content_version': v['content_version'],
            'stages': job.stages, 'failed_stage': failed_stage, 'movies': job.movies, 'jobs': job.jobs,
            'prepare_jobs': job.prepare_jobs, 'disc': {k: job.disc.get(k) for k in ('format', 'title_id', 'disc_id',
                                                                                  'known', 'dump')}}


def finish(a, output, job, ctl, pipeline, warn):
    """the last stage: verify every file against its expected hash (repairing damaged base files), the manifest,
    the ini, verify-report.json, the stamp. -> (stamp, verify summary)."""
    out_dir = job.out
    hook = getattr(pipeline, 'before_finish', None)
    if hook is not None:                                  # a test pipeline's cancel / failure knobs
        hook(job, ctl)
    files = {}
    built = pipeline.built_files(job)
    # the modules' copies are checked against their sources (write_bytes recorded the sha1 of what it wrote)
    copies = {rel: e['source'] for rel, e in built.items() if not e.get('sha1')}
    if copies:
        hashed = M.hash_files(list(copies.items()), jobs=HASH_JOBS, cancel=ctl.cancel)
        for rel, r in hashed.items():
            if isinstance(r, OSError):
                raise BuilderError('E_IO', f'The source of {rel} can\'t be read ({type(r).__name__}).', None,
                                   {'path': rel}, 'finish')
            built[rel]['size'], built[rel]['sha1'] = r
    sources = {rel: built[rel].pop('source') for rel in copies}
    built_low = {r.lower() for r in built}
    for rel, e in job.base_files.items():
        if rel.lower() not in built_low:
            files[rel] = e
    files.update(built)
    res = M.check_files(out_dir, files, jobs=HASH_JOBS, cancel=ctl.cancel, trusted=job.trusted,
                        progress=lambda d, t: ctl.progress('finish', d, t, 'files'))
    by_low = {r.lower(): r for r in files}
    repaired = []
    for item in res['missing'] + res['changed']:
        rel = by_low.get(item['path'].lower(), item['path'])
        entry = files.get(rel)
        if entry is not None and entry.get('kind') == 'base':
            files[rel] = pipeline.recopy_base(job, rel)
            repaired.append(rel)
            continue
        if rel in sources:                                # a copy that does not match its source: copy it again
            pipeline.recopy(job, rel, sources[rel], entry['sha1'])
            repaired.append(rel)
            continue
        what = 'is missing' if item in res['missing'] else 'changed'
        raise BuilderError('E_IO', f'{rel} {what} right after the build wrote it (an antivirus program, or a disk '
                           'error).', None, {'path': rel, 'expected': item.get('expected'), 'found': item.get('found')},
                           'finish')
    if res['unreadable']:
        first = res['unreadable'][0]
        raise BuilderError('E_IO', f'{first["path"]} can\'t be read after the build ({first.get("error")}).', None,
                           {'path': first['path'], 'count': len(res['unreadable'])}, 'finish')
    if repaired:
        output.human(f'finish: {len(repaired)} file(s) that did not match their source copied again: {repaired[:10]}')
        output.event('log', level='info', stage='finish', msg=f'{len(repaired)} damaged file(s) copied again')
    extra = [x for x in res['extra'] if not x.get('temp')]
    if extra:
        # the sweep deletes every file the build did not make; one it could not delete (another program has it
        # open) stays, and the build still succeeds: named here (design 2.9 "Held files")
        msg = f'{len(extra)} file(s) in the game folders that the build did not make (first: {extra[0]["path"]})'
        detail = {'files': [x['path'] for x in extra[:20]], 'count': len(extra)}
        kept_low = {r.lower(): cause for r, cause in job.kept.items()}
        kept = [x['path'] for x in extra if x['path'].lower() in kept_low]
        if kept:
            cause = kept_low[kept[0].lower()]
            words = IO_CAUSES.get(cause, 'it could not be deleted')
            msg += (f': the rebuild could not remove it because {words}' if len(extra) == 1 else
                    f'; the rebuild could not remove {len(kept)} of them (first: {kept[0]}) because {words}')
            detail.update(not_removed=kept[:20], cause=cause)
        warn('W_EXTRA_FILES', msg, detail, stage='finish')
    M.save(out_dir, files, builder=VERSION)
    # the XML2 install against the retail reference, by content (the sync hashed every source)
    hashes = {rel: e['src']['sha1'] for rel, e in job.base_files.items() if e.get('src')}
    cmp = I.compare_retail(job.listing, hashes)
    modified = I.modified_list(cmp)
    if modified:
        warn('W_XML2_MODIFIED', f'{len(modified)} file(s) of X-Men Legends II differ from a retail install '
                                f'(first: {modified[0]}); the build used them as they are.',
             {'files': modified[:20], 'count': len(modified)}, stage='finish')
    keys = pipeline.port_keys(out_dir)
    if not a.no_ini:
        pipeline.write_ini(out_dir, keys)
    total_bytes = sum(e['size'] for e in files.values())
    n_built = sum(1 for e in files.values() if e['kind'] == 'built')
    digest = M.manifest_digest(files)
    verify_summary = {'state': 'current', 'files': len(files), 'ok': len(files), 'repaired': len(repaired),
                      'extra': len(extra)}
    v = version_info()
    disc = job.disc
    stamp_doc = S.make_stamp(
        version=v, profile=pipeline.profile(), movies=job.movies,
        disc={'format': disc.get('format'), 'title_id': disc.get('title_id'), 'xbe_md5': disc.get('xbe_md5'),
              'zip_digest': disc.get('zip_digest'), 'digest': disc.get('digest'), 'disc_id': disc.get('disc_id'),
              'known': disc.get('dump') or False},
        xml2={'exe_md5': job.xml2_info.get('exe_md5'), 'exe': job.xml2_info.get('exe'),
              'base_digest': job.xml2_info.get('base_digest'), 'base_files': job.xml2_info.get('base_files'),
              'modified': modified[:I.MODIFIED_LIMIT], 'modified_count': len(modified)},
        requires={'xml2fix': pipeline.required_xml2fix(), 'ini': keys},
        outputs={'files': len(files), 'bytes': total_bytes, 'built_files': n_built, 'base_files': len(files) - n_built,
                 'manifest_sha1': digest, 'registry_sha1': digest},
        result={'errors': 0, 'warnings': job.warnings,
                'seconds': round(sum(s.get('seconds', 0) for s in job.stages.values()), 1),
                'repaired': len(repaired)},
        source={'project': PROJECT, 'repo': f'https://github.com/{REPO}', 'issues': ISSUES_URL})
    groups = M.groups_of({'extra': extra}, [M.group('xml2_not_retail', [{'path': m} for m in modified])])
    M.write_report(out_dir, verify_report_doc('build', 'current', [], verify_summary, groups, stamp_doc))
    S.write_json(S.build_dir(out_dir) / S.STAMP, stamp_doc)
    S.end_building(out_dir)
    job.journal.remove()
    output.human(f'manifest: {len(files)} files ({n_built} built, {len(files) - n_built} base), {total_bytes} bytes, '
                 f'sha1 {digest}')
    return stamp_doc, verify_summary


def verify_report_doc(command, state, reasons, counts, groups, stamp_doc) -> dict:
    """verify-report.json: versions, the state, counts, the groups - relative paths, sizes, hashes, codes only."""
    v = version_info()
    st = stamp_doc or {}
    return {'format': 1, 'command': command, 'verified': S.utc_now(),
            'builder': {'version': v['version'], 'content_version': v['content_version'], 'commit': v['commit']},
            'build': {'builder': st.get('builder'), 'finished': st.get('finished'), 'profile': st.get('profile'),
                      'inputs': st.get('inputs'), 'outputs': st.get('outputs')},
            'state': state, 'reasons': reasons[:50], 'counts': counts, 'groups': groups,
            'python': platform.python_version(), 'os': platform.platform()}


# ================================================================================================ verify
def cmd_verify(a, output, cancel, pipeline_factory):
    target = Path(a.out)
    pipeline = pipeline_factory()
    disc_digest = xml2_digest = None
    extra_groups = []
    if a.iso and Path(a.iso).is_file():
        ident, disc = pipeline.identify(a.iso)
        disc_digest = disc['digest']
        if not disc['known']:
            extra_groups.append(M.group('disc_unknown', [{'path': Path(a.iso).name, 'xbe_md5': disc['xbe_md5'],
                                                          'zip_digest': disc['zip_digest']}]))
        if a.deep:
            problems = I.deep_check_disc(a.iso)
            if problems:
                extra_groups.append(M.group('disc_damaged', [{'problem': p} for p in problems]))
    listing = None
    if a.xml2 and Path(a.xml2).is_dir():
        listing = I.base_listing(a.xml2)
        xml2_digest = I.base_digest(listing)
    state, reasons, stamp_doc = S.out_state(target, content_version=CONTENT_VERSION, profile=pipeline.profile(),
                                            disc_digest=disc_digest, xml2_digest=xml2_digest)
    if disc_digest and stamp_doc and ((stamp_doc.get('inputs') or {}).get('disc') or {}).get('digest') not in (
            None, disc_digest):
        extra_groups.append(M.group('disc_changed', [{'path': Path(a.iso).name}]))
    res = {'files': 0, 'ok': 0}
    if state in ('current', 'stale'):
        man = M.load(target)
        if man is None:
            state = 'damaged'
            reasons.append('the build has no file manifest (_build/manifest.json): rebuild to repair it')
        else:
            progress = PL.Progress([{'id': 'verify', 'weight': 1, 'cached': False}],
                                   lambda **f: output.event('progress', **f))
            progress.start('verify')
            res = M.check_files(target, man['files'], jobs=HASH_JOBS, cancel=cancel,
                                progress=lambda d, t: progress.update('verify', d, t, 'files'))
            if listing is not None:
                movies = bool(((stamp_doc or {}).get('profile') or {}).get('movies', True))
                extra_groups.append(M.group('xml2_changed', xml2_changes(a.xml2, listing, man['files'], movies)))
            for code in ('missing', 'changed', 'unreadable'):
                reasons += [f'{code}: {x["path"]}' for x in res[code][:200]]
            if any(res[c] for c in M.REPAIRS):
                state = 'damaged'
    if stamp_doc:
        mod = ((stamp_doc.get('inputs') or {}).get('xml2') or {}).get('modified') or []
        extra_groups.append(M.group('xml2_not_retail', [{'path': m} for m in mod]))
    groups = M.groups_of(res, extra_groups)
    counts = M.counts_of(res, groups)
    report = None
    if state not in ('absent', 'foreign') and S.build_dir(target).is_dir():
        try:
            report = M.write_report(target, verify_report_doc('verify', state, reasons, counts, groups, stamp_doc))
        except OSError as e:
            output.human(f'verify: could not write verify-report.json: {e}')
    output.human(f'verify: {state} ({res.get("files", 0)} files checked; {counts})')
    output.event('result', ok=True, exit=0, verify={'state': state, 'reasons': reasons, 'files': res.get('files', 0),
                                                     'ok': res.get('ok', 0), 'counts': counts,
                                                     'groups': M.trim_groups(groups), 'stamp': stamp_doc,
                                                     'report': mask(report) if report else None})
    return 0


def xml2_changes(xml2, listing: dict, files: dict, movies=True) -> list:
    """base files whose X-Men Legends II source differs from the one the build copied (stat first, hash on doubt);
    a --no-movies build never copied the *.sfd movies."""
    now = {rel.lower(): (rel, v) for rel, v in listing.items() if movies or not rel.lower().endswith('.sfd')}
    changed = []
    seen = set()
    for rel, e in files.items():
        src = e.get('src')
        if e.get('kind') != 'base' or not src:
            continue
        low = rel.lower()
        seen.add(low)
        have = now.get(low)
        if have is None:
            changed.append({'path': rel, 'change': 'missing', 'expected': {'size': src['size'], 'sha1': src['sha1']}})
            continue
        size, mtime = have[1]
        if size == src['size'] and mtime == src.get('mtime_ns'):
            continue
        try:
            got = M.sha1_file(Path(xml2) / have[0])
        except OSError:
            got = (size, None)
        if got[1] != src['sha1']:
            changed.append({'path': rel, 'change': 'changed', 'expected': {'size': src['size'], 'sha1': src['sha1']},
                            'found': {'size': got[0], 'sha1': got[1]}})
    in_manifest = {r.lower() for r in files}              # (a base file a module replaced is 'built' there)
    for low, (rel, v) in now.items():
        if low not in seen and low not in in_manifest:
            changed.append({'path': rel, 'change': 'added', 'found': {'size': v[0]}})
    return changed


# ================================================================================================ clean
def _rmtree(path):
    def onexc(fn, p, exc):
        try:
            os.chmod(p, 0o666)
            fn(p)
        except OSError:
            pass
    shutil.rmtree(path, onexc=onexc)


def _unlink(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except PermissionError:
        try:
            os.chmod(path, 0o666)
            path.unlink()
            return True
        except OSError:
            return False
    except FileNotFoundError:
        return False


def cmd_clean(a, output, cancel):
    result = {'files': 0, 'bytes': 0, 'kept': [], 'cache_bytes': 0, 'dry_run': bool(a.dry_run), 'failed': []}
    if not a.out and not a.cache:
        raise BuilderError('E_USAGE', 'clean needs --out or --cache.', '', {})
    disc_id = None
    if a.out:
        target = Path(a.out)
        if target.exists():
            if not target.is_dir() or not S.builder_folder(target):
                raise BuilderError('E_OUT_FOREIGN', 'This folder was not made by the builder, so it deletes nothing '
                                   'in it.', 'Delete the folder yourself if you no longer need it.',
                                   {'out': mask(target)})
            st = S.read_stamp(target) or S.read_json(S.build_dir(target) / S.BUILDING, {}) or {}
            disc_id = (st.get('inputs') or {}).get('disc', {}).get('disc_id')
            lock = FileLock(S.build_dir(target) / 'lock', 'clean')
            try:
                lock.acquire()
            except LockHeld as e:
                raise BuilderError('E_OUT_LOCKED', 'A build is writing to this folder.', None,
                                   {'pid': e.holder.get('pid')}) from None
            try:
                for rel in M.clean_targets(target):
                    cancel.check()
                    p = target / rel
                    try:
                        size = p.stat().st_size
                    except OSError:
                        continue
                    if a.dry_run or _unlink(p):
                        result['files'] += 1
                        result['bytes'] += size
                    else:
                        result['failed'].append(rel)
                mods = next((c for c in target.iterdir() if c.name.lower() == 'mods'), None)
                if a.mods and mods is not None:
                    for p in mods.rglob('*'):
                        if p.is_file():
                            result['files'] += 1
                            result['bytes'] += p.stat().st_size
                    if not a.dry_run:
                        _rmtree(mods)
            finally:
                lock.release()
            if not a.dry_run:
                _rmtree(S.build_dir(target))
                M.remove_empty_dirs(target, keep_top=() if a.mods else ('mods',))
            result['kept'] = sorted(p.name for p in target.iterdir()) if target.exists() else []
            if not a.dry_run and target.exists() and not any(target.iterdir()):
                target.rmdir()
    if a.cache:
        cache = Path(a.cache)
        if cache.is_dir():
            lock = FileLock(cache / 'lock', 'clean')
            try:
                lock.acquire()
            except LockHeld as e:
                raise BuilderError('E_CACHE_LOCKED', 'A build is using the build cache.', None,
                                   {'pid': e.holder.get('pid')}) from None
            try:
                if a.out:
                    victims = [cache / disc_id] if disc_id and (cache / disc_id).is_dir() else []
                else:
                    victims = [d for d in cache.iterdir() if d.is_dir() and ((d / 'disc.json').is_file()
                                                                              or (d / 'disc').is_dir())]
                for d in victims:
                    result['cache_bytes'] += SP.folder_bytes(d)
                    if not a.dry_run:
                        _rmtree(d)
            finally:
                lock.release()
    output.human(f'clean: {result["files"]} files, {result["bytes"]} bytes; cache {result["cache_bytes"]} bytes'
                 + (' (dry run)' if a.dry_run else ''))
    output.event('result', ok=True, exit=0, clean=result)
    return 0
