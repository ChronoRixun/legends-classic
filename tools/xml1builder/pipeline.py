"""xml1builder.pipeline - the adapter between the builder and the port's pipeline (tools/xml1build).

The only builder module that knows the pipeline's internals; kept thin on purpose (the prepare API may still move):
  * the prepare stages' run() functions (xml1build.prepare.{disc,tables,scripts,sound,music}) and the tail of
    prepare.prepared_sources (the Sources a prepared build reads);
  * build_xml1.parse_args for the play-build profile (every CONTENT_OPTS default: the builder has one profile);
  * the content modules (C.run_step over C.MODULE_ORDER), C.sweep_stale, validate.run + heroes.validate_out, as
    build_xml1.main runs them, in builder mode (args.builder_mode: the proxy files stay, V1 allows them, every file
    written is hashed and read back, no music snapshot);
  * the base sync, re-done here with hashes: C.sync_base's rules (copy when size or mtime differ, never the proxy,
    no *.sfd without movies), every copy read back against the source's sha1.

commands.build drives it stage by stage through these methods; the unit tests drive the same orchestration with a
stub that has the same methods (tests/unit/builder_stub.py)."""
from __future__ import annotations

import importlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import manifest as M
from . import plan as PL
from .errors import BuilderError, io_cause, io_in_chain
from .inputs import describe_disc

KEEP_STAGE = ('stage', 'version', 'key', 'disc_id', 'movies', 'seconds')
SYNC_THREADS = 8


class RealPipeline:
    name = 'xml1build'

    def __init__(self):
        from xml1build import common as C
        self.C = C

    # ------------------------------------------------------------------ probe
    def identify(self, iso):
        """(P1 identity, info.iso) of a disc image (the builder's error mapping)."""
        from .inputs import identify
        return identify(iso)

    def cached_disc(self, cache, disc_id=None):
        """(P1 identity, info.iso) of a disc prepared in the cache (--iso left out), or None. disc_id picks one;
        without it the cache must hold exactly one."""
        from xml1build.prepare import disc as P1, read_stage
        found = [d for d in P1.find_published(cache) if disc_id is None or d.parent.name == disc_id]
        if len(found) != 1:
            return None
        st = read_stage(found[0]) or {}
        ident = dict(st.get('identity') or {})
        if not ident:
            return None
        return ident, describe_disc(ident, None)

    def profile(self) -> dict:
        import build_xml1
        args = build_xml1.parse_args(['--out', '.'])
        return {opt: getattr(args, opt) for opt in build_xml1.CONTENT_OPTS}

    def expected_files(self, out, movies) -> int:
        reg = self.C.Registry.load(Path(out) / '_build' / 'registry.json')
        if len(reg.entries) > 1000:
            return len(reg.entries)
        return PL.EXPECTED_FILES if movies else PL.EXPECTED_FILES_NO_MOVIES

    def sizes(self, movies):
        """(output bytes, cache bytes) a build needs (space.py's measured estimates)."""
        from . import space
        return space.OUT_BYTES[bool(movies)], space.CACHE_BYTES[bool(movies)]

    def sound_kernel(self):
        """(kernel in use?, status line) - the sound stages' codec (a 0.4 s self-check)."""
        try:
            from xml1build.lib import adpcm
            return adpcm.codec_name() == 'kernel', adpcm.codec_status()
        except Exception as e:  # noqa: BLE001 - numpy missing etc.: the stages will say so themselves
            return False, f'unknown ({type(e).__name__}: {e})'

    def kernel_present(self) -> bool:
        """is a compiled sound kernel there at all (without loading it; for info's estimate)?"""
        try:
            from xml1build.lib import adpcm_c
            return not adpcm_c.disabled() and any(os.path.isfile(p) for p in adpcm_c.candidates())
        except Exception:  # noqa: BLE001
            return False

    def predict_cached(self, cache, disc_id, ident, xml2, movies) -> set:
        """the prepare stages whose published output a build would reuse (the plan's `cached`); computed with the
        stages' own cache keys. ident None = the disc is taken from the cache (no --iso)."""
        from xml1build.prepare import disc as P1, read_stage
        cached = set()
        disc_dir = Path(cache) / disc_id / P1.STAGE
        st = read_stage(disc_dir)
        if not st or st.get('stage') != P1.STAGE:
            return cached
        if ident is not None and st.get('key') != P1.stage_key(ident):
            return cached
        if movies and not P1.has_movies(st):
            return cached
        cached.add('extract')
        try:
            from xml1build.prepare import tables as P2, scripts as P3
            from xml1build.sources import REPO_ROOT
            k2 = P2.stage_key(st, P2.xml2_digest(P2.xml2_index(xml2)))
            t_dir = self._published(disc_dir.parent, P2.STAGE, k2)
            if t_dir is not None:
                cached.add('tables')
                if self._published(disc_dir.parent, P3.STAGE, P3.stage_key(st, t_dir, REPO_ROOT / 'research')):
                    cached.add('scripts')
            from xml1build.prepare import sound as P4, music as P5
            eng = P4.xml2_sounds(xml2)
            if t_dir is not None and self._published(disc_dir.parent, P4.STAGE, P4.stage_key(st, t_dir, eng)):
                cached.add('sound')
            if self._published(disc_dir.parent, P5.STAGE, P5.stage_key(st, eng)):
                cached.add('music')
        except Exception:  # noqa: BLE001 - only a hint for the plan; the stages decide for themselves
            pass
        return cached

    @staticmethod
    def _published(disc_root: Path, stage: str, key: str):
        from xml1build.prepare import read_stage
        for d in sorted((disc_root / 'prepared').glob(f'{stage}-v*')):
            if d.name.endswith(('.partial', '.old')):
                continue
            st = read_stage(d)
            if st and st.get('key') == key:
                return d
        return None

    # ------------------------------------------------------------------ prepare (P1-P5)
    def prepare(self, sid, job, ctl) -> bool:
        """run (or reuse) one prepare stage; returns True when it was cached."""
        from xml1build import prepare
        from xml1build.prepare import disc as P1, tables as P2, scripts as P3, sound as P4, music as P5
        res = job.prepared
        log = ctl.prepare_log
        prog = ctl.progress_fn(sid)
        if sid == 'extract':
            if job.iso is not None:
                r = P1.run(job.iso, job.cache, log=log, cancel=ctl.cancel, progress=prog, movies=job.movies)
            else:
                d = Path(job.cache) / job.disc['disc_id'] / P1.STAGE
                st = prepare.read_stage(d)
                if not st:
                    raise prepare.PrepareError('E_CACHE_EMPTY', f'the cache {job.cache} holds no prepared disc',
                                               'pass --iso with your X-Men Legends Xbox disc image')
                if job.movies and not P1.has_movies(st):
                    raise prepare.PrepareError('E_CACHE_NO_MOVIES', 'the cached disc was prepared without its movies',
                                               'pass --iso to add them, or build with --no-movies')
                log(f'[prepare] disc: using {d} (no --iso)')
                r = {'dir': d, 'stage': st, 'cached': True}
            res['disc'] = r
            self._disc_marker(job, r)
        elif sid == 'tables':
            res['tables'] = r = P2.run(res['disc']['dir'], job.xml2, log=log, cancel=ctl.cancel)
        elif sid == 'scripts':
            res['scripts'] = r = P3.run(res['disc']['dir'], res['tables']['dir'], log=log, cancel=ctl.cancel)
        elif sid == 'sound':
            res['sound'] = r = P4.run(res['disc']['dir'], res['tables']['dir'], job.xml2, jobs=job.prepare_jobs,
                                      log=log, cancel=ctl.cancel, progress=prog)
        elif sid == 'music':
            res['music'] = r = P5.run(res['disc']['dir'], job.xml2, jobs=job.prepare_jobs, log=log,
                                      cancel=ctl.cancel, progress=prog)
        else:
            raise ValueError(sid)
        return bool(r.get('cached'))

    @staticmethod
    def _disc_marker(job, r):
        """<cache>/<disc_id>/disc.json: what the folder holds (clean --cache and the launcher's Free up find it)."""
        from .stamp import write_json, utc_now
        d = Path(r['dir']).parent
        try:
            write_json(d / 'disc.json', {'disc_id': d.name, 'title': job.disc.get('title'),
                                         'title_id': job.disc.get('title_id'), 'known': job.disc.get('known'),
                                         'dump': job.disc.get('dump'), 'updated': utc_now()})
        except OSError:
            pass

    def sources(self, job):
        """the prepared Sources (= the tail of xml1build.prepare.prepared_sources)."""
        from xml1build import prepare
        from xml1build.sources import Sources
        res = job.prepared
        stages = {name: {k: r['stage'].get(k) for k in KEEP_STAGE if k in r['stage']} for name, r in res.items()}
        overrides = {rel: (res[name]['dir'] / sub if sub else res[name]['dir'])
                     for name, (rel, sub) in prepare.STAGE_OVERRIDES.items()}
        return Sources.prepared(res['disc']['dir'], job.xml2, tables_dir=res['tables']['dir'],
                                cache=Path(job.cache).resolve(), stages=stages, overrides=overrides)

    # ------------------------------------------------------------------ the build
    def build_args(self, job):
        import build_xml1
        argv = ['--out', str(job.out), '--base', str(job.xml2), '--jobs', str(job.jobs)]
        if not job.movies:
            argv.append('--no-movies')
        args = build_xml1.parse_args(argv)
        args.builder_mode = True
        args.sources, args.cache, args.iso = 'prepared', str(job.cache), str(job.iso) if job.iso else None
        return args

    def check_out_safe(self, out, xml2, protected=()):
        """C._check_out_safe with the prepared Sources' protected trees; raises BuilderError(E_OUT_UNSAFE)."""
        from xml1build.sources import REPO_ROOT
        trees = tuple(Path(p) for p in protected) + (REPO_ROOT / 'research', REPO_ROOT / 'tools')
        try:
            self.C._check_out_safe(Path(out), Path(xml2), trees)
        except ValueError as e:
            raise BuilderError('E_OUT_UNSAFE', f'The game can\'t be built there: {e}.', None,
                               {'reason': str(e)}) from e

    def sync(self, job, ctl):
        """the base install -> <out> (C.sync_base's rules), every copy read back against its source's sha1.
        Sets job.base_files {rel: manifest entry} and adds the files hashed here to job.trusted."""
        C = self.C
        out, base = Path(job.out), Path(job.xml2)
        prev = {k.lower(): v for k, v in ((job.prev_manifest or {}).get('files') or {}).items()}
        items = sorted(rel for rel in job.listing if job.movies or not rel.lower().endswith('.sfd'))
        total = len(items)
        done = [0]
        entries = {}
        stats = {'copied': 0, 'unchanged': 0, 'bytes': 0}

        def one(rel):
            ctl.check()
            src, dst = base / rel, out / rel
            s = src.stat()
            p = prev.get(rel.lower()) or {}
            ps = p.get('src') or {}
            src_sha1 = ps.get('sha1') if (p.get('kind') == 'base' and ps.get('size') == s.st_size
                                          and ps.get('mtime_ns') == s.st_mtime_ns) else None
            copied = False
            if dst.is_file():
                d = dst.stat()
                same = d.st_size == s.st_size and int(d.st_mtime) == int(s.st_mtime)
            else:
                same = False
            if not same:
                C._atomic_copy(src, dst)
                copied = True
            if src_sha1 is None:
                src_sha1 = M.sha1_file(src)[1]
            d = dst.stat()
            if copied:
                got = M.sha1_file(dst)[1]
                if got != src_sha1:
                    raise C.WriteCheckError(rel, src_sha1, got, d.st_size)
                job.trusted[rel.lower()] = (d.st_size, d.st_mtime_ns)
            job.journal.add(rel)
            entry = {'size': s.st_size, 'sha1': src_sha1, 'kind': 'base', 'mtime_ns': d.st_mtime_ns,
                     'src': {'size': s.st_size, 'mtime_ns': s.st_mtime_ns, 'sha1': src_sha1}}
            return rel, entry, copied, s.st_size

        with ThreadPoolExecutor(max_workers=SYNC_THREADS, thread_name_prefix='xml1builder-sync') as pool:
            futures = [pool.submit(one, rel) for rel in items]
            try:
                for f in futures:
                    rel, entry, copied, size = f.result()
                    entries[rel] = entry
                    stats['copied' if copied else 'unchanged'] += 1
                    stats['bytes'] += size if copied else 0
                    done[0] += 1
                    ctl.progress('sync', done[0], total, 'files')
            except BaseException:
                for f in futures:
                    f.cancel()
                raise
        job.base_files = entries
        ctl.human(f'[build] base sync: {stats}')
        return stats

    def recopy_base(self, job, rel) -> dict:
        """copy one base file again (the final verification found it damaged) and read it back."""
        C = self.C
        src, dst = Path(job.xml2) / rel, Path(job.out) / rel
        C._atomic_copy(src, dst)
        want = M.sha1_file(src)[1]
        got = M.sha1_file(dst)[1]
        st, d = src.stat(), dst.stat()
        if got != want:
            raise C.WriteCheckError(rel, want, got, d.st_size)
        job.trusted[rel.lower()] = (d.st_size, d.st_mtime_ns)
        return {'size': st.st_size, 'sha1': want, 'kind': 'base', 'mtime_ns': d.st_mtime_ns,
                'src': {'size': st.st_size, 'mtime_ns': st.st_mtime_ns, 'sha1': want}}

    def content(self, job, ctl) -> dict:
        """the content modules in order (C.run_step each). -> {'failed': [module, ...]}."""
        C = self.C
        out = Path(job.out)
        (out / '_build').mkdir(parents=True, exist_ok=True)
        (out / '_build' / 'sources.json').write_text(json.dumps(job.sources.describe(), indent=1), encoding='utf-8')
        args = self.build_args(job)
        ctx = C.BuildContext(out, job.xml2, args=args, registry=C.Registry(), sources=job.sources)
        ctx.shared['selected_modules'] = list(C.MODULE_ORDER)
        job.ctx, job.args, job.t0 = ctx, args, time.time()
        failed = []
        for name in C.MODULE_ORDER:
            ctl.check()
            ctl.module = name
            mod = importlib.import_module(f'xml1build.{name}')
            if not self.run_module(ctx, name, mod.run):
                failed.append(name)
        ctl.module = None
        return {'failed': failed, 'errors': self._count(ctx, C.MODULE_ORDER, 'errors'),
                'warnings': self._count(ctx, C.MODULE_ORDER, 'warnings'),
                'first_errors': self._first(ctx, C.MODULE_ORDER)}

    def run_module(self, ctx, name, fn) -> bool:
        """C.run_step(ctx, name, fn), except that an OS-level I/O error (errors.io_cause: a file another program
        holds open, a full or failing drive), raised by fn or wrapped in what it raised, ends the build right there
        as that OSError (the builder reports E_IO naming the file) instead of a failed step (E_PIPELINE: our bug).
        run_step still records the step as failed in report.json."""
        seen = []

        def guarded(c):
            try:
                return fn(c)
            except Exception as e:  # noqa: BLE001 - noted, then run_step handles it as always
                io = io_in_chain(e)
                if io is not None:
                    seen.append(io)
                raise
        ok = self.C.run_step(ctx, name, guarded)
        if seen:
            raise seen[0]
        return ok

    def sweep(self, job, ctl) -> dict:
        C = self.C
        ctx = job.ctx
        kept = {}
        removed = C.sweep_stale(job.out, ctx.base_index, ctx.registry, skip_sfd=not job.movies, keep_proxy=True,
                                log=ctl.human, failed=kept)
        self.note_kept(job, kept)
        tour = Path(job.out) / '_tour.json'
        if tour.is_file():
            tour.unlink()
        ctx.out_index.scan()
        (Path(job.out) / '_build' / 'registry.json').write_text(json.dumps(ctx.registry.to_json(), indent=0),
                                                                 encoding='utf-8')
        return {'removed': len(removed)}

    @staticmethod
    def note_kept(job, kept: dict):
        """the files the sweep could not delete ({rel: OSError}; another program has them open) stay: the build does
        not need them gone. job.kept {rel: cause} (finish names them: W_EXTRA_FILES); ctx.shared['sweep_kept'] (the
        validator's V2 allows them in builder mode instead of failing the build)."""
        job.kept = {rel: io_cause(e, Path(job.out) / rel) or 'other' for rel, e in kept.items()}
        shared = getattr(job.ctx, 'shared', None)
        if kept and isinstance(shared, dict):
            shared['sweep_kept'] = sorted(kept)

    def validate(self, job, ctl) -> dict:
        C = self.C
        ctx = job.ctx
        validate = importlib.import_module('xml1build.validate')
        heroes = importlib.import_module('xml1build.heroes')
        ok = self.run_module(ctx, 'validate', validate.run)
        ok &= self.run_module(ctx, 'heroes_validate', heroes.validate_out)
        steps = ('validate', 'heroes_validate')
        return {'ok': ok, 'errors': self._count(ctx, steps, 'errors'), 'warnings': self._count(ctx, steps, 'warnings'),
                'first_errors': self._first(ctx, steps)}

    def built_files(self, job) -> dict:
        """{rel: manifest entry} of every file the modules registered: write_bytes' files with the sha1 of the bytes
        written; copies with sha1 None and 'source' (the caller hashes the sources: they are the reference)."""
        out = {}
        for e in job.ctx.registry.entries.values():
            rel = e['rel']
            entry = {'size': int(e['size']), 'sha1': e.get('sha1'), 'kind': 'built', 'owner': e.get('owner')}
            if not entry['sha1']:
                src = e.get('source')
                if src and Path(src).is_file():
                    entry['source'] = src
                else:                              # neither: the file as it is (should not happen in builder mode)
                    entry['size'], entry['sha1'] = M.sha1_file(Path(job.out) / rel)
            out[rel] = entry
        return out

    def recopy(self, job, rel, source, want):
        """copy a module's file again from its source (the final verification found it damaged); read it back."""
        C = self.C
        dst = Path(job.out) / rel
        C._atomic_copy(Path(source), dst)
        got = M.sha1_file(dst)[1]
        if got != want:
            raise C.WriteCheckError(rel, want, got, dst.stat().st_size)
        d = dst.stat()
        job.trusted[rel.lower()] = (d.st_size, d.st_mtime_ns)

    def write_report(self, job, builder: dict) -> Path | None:
        """<out>/_build/report.json as build_xml1.py writes it (+ a 'builder' block)."""
        ctx = getattr(job, 'ctx', None)
        if ctx is None:
            return None
        import build_xml1
        a = job.args
        rep = ctx.report.to_json()
        rep['build'] = {'out': Path(job.out).as_posix(), 'base': Path(job.xml2).as_posix(),
                        'selected': list(self.C.MODULE_ORDER), 'forced_rerun': [], 'start_zone': None, 'tour': None,
                        'no_movies': not job.movies, **{opt: getattr(a, opt) for opt in build_xml1.CONTENT_OPTS},
                        'start_party': None, 'start_skinset': None, 'files_registered': len(ctx.registry.entries),
                        'seconds': round(time.time() - job.t0, 1), 'shared_keys': sorted(ctx.shared),
                        'sources': 'prepared', 'builder_mode': True}
        rep['builder'] = builder
        p = Path(job.out) / '_build' / 'report.json'
        p.write_text(json.dumps(rep, indent=1, default=str), encoding='utf-8')
        return p

    def port_keys(self, out) -> dict:
        from xml1build import fix_ini
        return fix_ini.port_keys(out)

    def write_ini(self, out, keys):
        from xml1build import fix_ini
        return fix_ini.write_port_keys(out, keys)

    def required_xml2fix(self) -> str:
        from xml1build import fix_ini
        return '>=' + fix_ini.REQUIRED_XML2FIX

    def install_checkpoint(self, fn):
        return self.C.set_checkpoint(fn)

    @staticmethod
    def _count(ctx, modules, kind) -> int:
        return sum(len(ctx.report.modules.get(m, {}).get(kind, [])) for m in modules)

    @staticmethod
    def _first(ctx, modules, n=3) -> list:
        out = []
        for m in modules:
            for msg in ctx.report.modules.get(m, {}).get('errors', []):
                if len(out) < n:
                    out.append(f'[{m}] {str(msg).splitlines()[0][:300]}')
        return out
