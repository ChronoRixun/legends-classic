"""A stub pipeline for the builder's unit tests (BUILDER_DESIGN.md 6.1 "the builder with a stub pipeline"): the
same methods as xml1builder.pipeline.RealPipeline, acting on tiny made-up folders - no game data, no xml1build
content modules. The base sync and the base re-copy are the real ones (they only need xml1build.common).

Knobs (attributes): fail_stage (a stage id: StageFailed-like E_PIPELINE), io_stage (an OSError), crash_stage (a bug:
E_INTERNAL), cancel_at (the stage during which the token is set), validate_errors (n), corrupt_after_write (a rel
the content stage damages right after writing: the finish stage must catch it), busy (a rel the sweep can't delete:
EBUSY, as if another program held it open - on Windows the tests hold files open for real), module_fn (fn(ctx, job):
run as a content module, through RealPipeline.run_module with a real xml1build BuildContext in builder mode)."""
import contextlib
import errno
import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

from xml1build import common as C
from xml1builder import manifest as M, resources as R
from xml1builder.pipeline import RealPipeline

CONTENT = {'Data/xml1/herostat_x1.txt': b'made-up hero table\n', 'Scripts/x1/menus/postgame.py': b'print\r\n',
           'UI/menus/x1_main.txt': b'made-up menu\n', 'packages/generated/x1/nyc1_1.txt': b'made-up package\n'}
MOVIES = {'Movies/x1_intro.sfd': b'made-up movie\n'}
_KNOWN = (R.load_json('known_dumps.json', {}) or {}).get('dumps', [{}])[0]
IDENT = {'format': 'xiso', 'xbe': {'title': 'X-Men Legends', 'title_id_hex': '0x4156001E'},
         'xbe_md5': _KNOWN.get('xbe_md5', 'x' * 32), 'zip_digest': _KNOWN.get('zip_digest', 'z' * 40),
         'listing_digest': 'l' * 40, 'disc_id': '1e1a766ae4dcstubdisc', 'image_size': 4096}


def pe32(image_base=0x400000, extra=b''):
    """a minimal PE32 header (MZ, PE, optional header magic 0x10B, the image base)."""
    b = bytearray(0x200)
    b[0:2] = b'MZ'
    struct.pack_into('<I', b, 0x3C, 0x80)
    b[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<H', b, 0x84, 0x14C)
    struct.pack_into('<H', b, 0x98, 0x10B)
    struct.pack_into('<I', b, 0xB4, image_base)
    return bytes(b) + extra


def make_xml2(folder):
    """a small stand-in for an X-Men Legends II install (with the proxy files a player has)."""
    folder = Path(folder)
    for rel, data in {'XMen2.exe': pe32(extra=b'stub'), 'Data/herostat.engb': b'stand-in herostat',
                      'Sounds/eng/shared.zss': b'stand-in bank' * 16, 'Movies/logo.sfd': b'stand-in movie',
                      'build.ini': b'DefaultTextLanguage = eng\r\n', 'dinput.dll': b'the player\'s proxy',
                      'xml2-fix.ini': b'[Display]\r\nMode=windowed\r\n', 'mods/load-order.txt': b'mine\r\n'}.items():
        p = folder / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return folder


def make_iso(path):
    Path(path).write_bytes(b'stub disc image\n')
    return Path(path)


@contextlib.contextmanager
def held_open(path):
    """`path` open in another process (a Python file handle in a child process, as a player's editor or the running
    game would hold it): on Windows nothing can delete or replace it meanwhile (WinError 32 / 5); yields True. POSIX
    deletes and replaces open files: yields False, the caller simulates the failure."""
    if os.name != 'nt':
        yield False
        return
    child = subprocess.Popen([sys.executable, '-c', 'import sys, time; f = open(sys.argv[1], "rb"); '
                              'print("held", flush=True); time.sleep(120)', str(path)], stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == 'held'
        yield True
    finally:
        child.kill()
        child.wait()
        child.stdout.close()


class StubPipeline(RealPipeline):
    name = 'stub'
    fail_stage = io_stage = crash_stage = cancel_at = corrupt_after_write = corrupt_copy = busy = module_fn = None
    validate_errors = 0
    instances = []

    def __init__(self):
        super().__init__()
        self.registry = {}
        self.calls = []
        self._checkpoint = None
        StubPipeline.instances.append(self)

    def _knobs(self, sid, ctl):
        self.calls.append(sid)
        if self.cancel_at == sid:
            ctl.cancel.set('cancel')
            ctl.check()
        if self.fail_stage == sid:
            from xml1build import prepare
            raise prepare.StageFailed('E_PREPARE_STUB', f'stub failure in {sid}', {'stage': sid})
        if self.io_stage == sid:
            raise PermissionError(13, 'Access is denied', str(ctl.job.out / 'Data' / 'locked.bin'))
        if self.crash_stage == sid:
            raise RuntimeError(f'stub crash in {sid}')

    # ---- probe
    def identify(self, iso):
        if not Path(iso).is_file():                       # the real identification's E_ISO_NOT_FOUND (and text)
            from xml1builder.inputs import identify
            return identify(iso)
        from xml1builder.inputs import describe_disc
        return dict(IDENT), describe_disc(IDENT, iso)

    def cached_disc(self, cache, disc_id=None):
        from xml1builder.inputs import describe_disc
        d = Path(cache) / IDENT['disc_id'] / 'disc' / 'stage.json'
        return (dict(IDENT), describe_disc(IDENT, None)) if d.is_file() else None

    def profile(self):
        return {'frontend': 'xml1', 'forced_teams': 'seat', 'newgame': 'keepteam', 'xp_curve': 'xml1',
                'tiles': 'used', 'hero_roster': '21', 'hero_icons': 'xml1', 'hero_bleed': 'on', 'blackbird': 'menu',
                'npc_scaling': 'off'}

    def expected_files(self, out, movies):
        return len(CONTENT) + (len(MOVIES) if movies else 0)

    def sizes(self, movies):
        return 10_000, 10_000

    def sound_kernel(self):
        return True, 'stub'

    def kernel_present(self):
        return True

    def predict_cached(self, cache, disc_id, ident, xml2, movies):
        root = Path(cache) / disc_id
        return {sid for sid in ('extract', 'tables', 'scripts', 'sound', 'music')
                if (root / self._dir(sid) / 'stage.json').is_file()}

    @staticmethod
    def _dir(sid):
        return 'disc' if sid == 'extract' else f'prepared/{sid}-v1-stub'

    def check_out_safe(self, out, xml2, protected=()):
        pass

    # ---- prepare
    def prepare(self, sid, job, ctl):
        root = Path(job.cache) / job.disc['disc_id']
        d = root / self._dir(sid)
        if (d / 'stage.json').is_file():
            if sid == 'extract':
                self._disc_marker(job, {'dir': d})
            return True
        for i in range(4):
            ctl.check()
            ctl.progress(sid, i + 1, 4, 'files')
            if i == 1:
                self._knobs(sid, ctl)
        d.mkdir(parents=True, exist_ok=True)
        (d / 'stage.json').write_text(json.dumps({'stage': sid}), encoding='utf-8')
        if sid == 'extract':
            self._disc_marker(job, {'dir': d})
        return False

    def sources(self, job):
        return None

    # ---- build
    def sync(self, job, ctl):
        self._knobs('sync', ctl)
        return super().sync(job, ctl)

    def install_checkpoint(self, fn):
        prev, self._checkpoint = self._checkpoint, fn
        return prev

    def _write(self, job, rel, data):
        p = Path(job.out) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f'.tmp{os.getpid()}')
        tmp.write_bytes(data)
        os.replace(tmp, p)
        got = M.sha1_file(p)[1]
        want = hashlib.sha1(data).hexdigest()
        assert got == want
        self.registry[rel] = {'size': len(data), 'sha1': want, 'kind': 'built', 'owner': 'stub'}
        if self._checkpoint:
            self._checkpoint('write', rel)

    def content(self, job, ctl):
        job.ctx = object()
        files = dict(CONTENT, **(MOVIES if job.movies else {}))
        for i, (rel, data) in enumerate(files.items()):
            if self._checkpoint:
                self._checkpoint('log', ('stub', 'start' if i == 0 else f'writing {rel}'))
            if i == 1:
                self._knobs('content', ctl)
            self._write(job, rel, data)
            if rel == self.corrupt_after_write:
                p = Path(job.out) / rel
                p.write_bytes(b'X' + p.read_bytes()[1:])
        # a copied file (ctx.copy_file): no sha1 of its own, its source is the reference
        src = Path(job.cache) / job.disc['disc_id'] / 'disc' / 'copy_source.bin'
        src.write_bytes(b'copied from the prepare cache.' * 8)
        rel = 'Sounds/eng/x1/copied.zss'
        p = Path(job.out) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(src.read_bytes())
        self.registry[rel] = {'size': p.stat().st_size, 'sha1': None, 'kind': 'built', 'owner': 'stub',
                              'source': str(src)}
        if self._checkpoint:
            self._checkpoint('write', rel)
        if self.corrupt_copy:
            p.write_bytes(b'damaged')
        failed = []
        if StubPipeline.module_fn is not None:            # (the class attribute: a plain function, not a method)
            ctx = C.BuildContext(Path(job.out), Path(job.xml2), sources=C.Sources.developer(Path(job.xml2)),
                                 args=C.default_args(out=str(job.out), base=str(job.xml2), builder_mode=True))
            if not self.run_module(ctx, 'stub_module', lambda c: StubPipeline.module_fn(c, job)):
                failed.append('stub_module')
        return {'failed': failed, 'errors': len(failed), 'warnings': 2, 'first_errors': []}

    def sweep(self, job, ctl):
        """as C.sweep_stale in builder mode: what the build did not make goes; what can't be deleted stays."""
        self._knobs('sweep', ctl)
        keep = {r.lower() for r in self.registry} | {r.lower() for r in job.base_files}
        removed = 0
        kept = {}
        for low, actual in M.area_files(job.out).items():
            if low not in keep:
                try:
                    if self.busy and actual.lower() == self.busy.lower():
                        raise OSError(errno.EBUSY, 'Device or resource busy', str(Path(job.out) / actual))
                    (Path(job.out) / actual).unlink()
                    removed += 1
                except OSError as e:
                    kept[actual] = e
        self.note_kept(job, kept)
        M.remove_empty_dirs(job.out, keep_top=('mods',))
        return {'removed': removed}

    def validate(self, job, ctl):
        self._knobs('validate', ctl)
        n = self.validate_errors
        return {'ok': n == 0, 'errors': n, 'warnings': 1, 'first_errors': ['[validate] stub error'] * min(n, 3)}

    def built_files(self, job):
        return {rel: dict(e) for rel, e in self.registry.items()}

    def write_report(self, job, builder):
        p = Path(job.out) / '_build' / 'report.json'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({'builder': builder, 'stub': True}), encoding='utf-8')
        return p

    def port_keys(self, out):
        return {'Game': {'NewGameTeam': 'wolverine', 'ResetUnlocks': '0'}, 'Limits': {'ActorSlots': '127'}}

    def before_finish(self, job, ctl):
        self._knobs('finish', ctl)
