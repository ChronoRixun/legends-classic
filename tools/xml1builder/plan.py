"""xml1builder.plan - the build's stages, their weights and the progress / ETA arithmetic (BUILDER_DESIGN.md 2.3).

Weights are measured seconds on Owen's PC (Ryzen 7 5700X, 8 jobs, the compiled sound kernel; SPEC.md 27.9 and the
phase-1b build logs): P1 17 s (13 s without movies), P2 25-46 s, P3 8 s, P4 18 s on 8 jobs / 26 s on 4, P5 93 s on 8
jobs / 100 s on 4 (memory-bound), base sync 36 s (a first copy of 2.3 GB; ~4 s when <out> already has it), content
modules ~70 s (media checks the 61 music banks on a first build), validator ~45 s, the final verification ~10 s.
Without the kernel the sound stages run the numpy path, ~7x slower. A cached stage weighs CACHED_WEIGHT.

overall = sum(weight * fraction done) / sum(weight); eta = the predicted seconds left, scaled by how fast the
finished stages ran against their prediction (0.4x..3x). Progress events are rate-limited to one per RATE seconds
per stage (the last one of a stage always goes out). Stages without their own counter (tables, scripts, sweep) get
a time-based fraction from the ticker (at most 95 % until the stage ends)."""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    id: str
    title: str
    unit: str
    cacheable: bool = False


STAGES = (
    Stage('probe', 'Checking your files', 'checks'),
    Stage('extract', 'Reading the disc', 'files', True),
    Stage('tables', 'Preparing tables', 'tables', True),
    Stage('scripts', 'Rewriting scripts', 'scripts', True),
    Stage('sound', 'Converting sound banks', 'banks', True),
    Stage('music', 'Fixing the music', 'banks', True),
    Stage('sync', 'Copying X-Men Legends II', 'files'),
    Stage('content', 'Building the game', 'files'),
    Stage('sweep', 'Removing old files', 'files'),
    Stage('validate', 'Checking the build', 'checks'),
    Stage('finish', 'Verifying the files', 'files'),
)
STAGE_IDS = tuple(s.id for s in STAGES)
PREPARE_STAGES = ('extract', 'tables', 'scripts', 'sound', 'music')
BY_ID = {s.id: s for s in STAGES}
CACHED_WEIGHT = 0.5
RATE = 0.25                     # seconds between progress events of one stage (~4 per second)
# stages with a counter of their own (files, banks, checks): the ticker never guesses them, even while their first
# unit takes long (P5's first music bank finishes after ~20 s)
COUNTED = frozenset({'extract', 'sound', 'music', 'sync', 'content', 'validate', 'finish'})
EXPECTED_FILES = 8132           # files a play build registers (movies on; the phase-1b prepared build)
EXPECTED_FILES_NO_MOVIES = 8084


def default_jobs() -> int:
    return max(1, os.cpu_count() or 1)


def weights(*, jobs=None, kernel=True, movies=True, synced=False, hashed=False) -> dict:
    """predicted seconds per stage. synced: <out> already holds a copy of the base install (a rebuild); hashed: the
    previous manifest's hashes can be reused for the unchanged files."""
    jobs = max(1, int(jobs or default_jobs()))
    sound = max(17.0, 100.0 / jobs + 4)
    music = max(60.0, 380.0 / jobs)
    if not kernel:
        sound, music = sound * 7, music * 7
    return {'probe': 3.0, 'extract': 17.0 if movies else 13.0, 'tables': 35.0, 'scripts': 8.0,
            'sound': round(sound, 1), 'music': round(music, 1), 'sync': 4.0 if synced else 36.0,
            'content': 70.0, 'sweep': 2.0, 'validate': 45.0, 'finish': 4.0 if hashed else 12.0}


def estimate(*, jobs=None, kernel=True, movies=True) -> dict:
    """info's time estimate: a first build (nothing cached) and a rebuild (prepare cached, <out> synced)."""
    w = weights(jobs=jobs, kernel=kernel, movies=movies)
    first = sum(w.values())
    rw = weights(jobs=jobs, kernel=kernel, movies=movies, synced=True, hashed=True)
    rebuild = sum(v for k, v in rw.items() if k not in PREPARE_STAGES) + CACHED_WEIGHT * len(PREPARE_STAGES)
    return {'cores': os.cpu_count() or 1, 'jobs': max(1, int(jobs or default_jobs())), 'kernel': bool(kernel),
            'first_build_s': int(round(first)), 'rebuild_s': int(round(rebuild))}


def make_plan(weight_map: dict, cached: set) -> list:
    """the plan event's stages: [{id, title, weight, cached}] (weight = predicted seconds, an integer >= 1)."""
    return [{'id': s.id, 'title': s.title, 'weight': max(1, int(round(weight_map.get(s.id, 1)))),
             'cached': s.id in cached} for s in STAGES]


class Progress:
    """per-stage fractions -> overall % and ETA; emits rate-limited progress events through emit(**fields)."""

    def __init__(self, plan, emit, *, clock=time.monotonic, rate=RATE):
        self._clock, self._rate, self._emit = clock, rate, emit
        self.eff = {s['id']: (CACHED_WEIGHT if s['cached'] else float(s['weight'])) for s in plan}
        self.order = [s['id'] for s in plan]
        self.total = sum(self.eff.values()) or 1.0
        self.frac = {sid: 0.0 for sid in self.order}
        self.done = set()
        self.actual = {}
        self.started = {}
        self.current = None
        self._last_emit = {}
        self._last_real = {}
        self._overall = 0.0
        self._lock = threading.RLock()
        self.units = {s.id: s.unit for s in STAGES}

    def start(self, sid):
        with self._lock:
            self.current = sid
            self.started[sid] = self._clock()

    def finish(self, sid) -> float:
        with self._lock:
            seconds = self._clock() - self.started.get(sid, self._clock())
            self.frac[sid] = 1.0
            self.done.add(sid)
            self.actual[sid] = seconds
            if self.current == sid:
                self.current = None
            return seconds

    def speed(self) -> float:
        """actual / predicted seconds of the finished stages (1.0 until 5 predicted seconds are done)."""
        pred = sum(self.eff[s] for s in self.done if self.eff[s] > CACHED_WEIGHT)
        real = sum(self.actual[s] for s in self.done if self.eff[s] > CACHED_WEIGHT)
        if pred < 5:
            return 1.0
        return min(3.0, max(0.4, real / pred))

    def overall(self) -> float:
        with self._lock:
            value = 100.0 * sum(self.eff[s] * self.frac[s] for s in self.order) / self.total
            self._overall = max(self._overall, min(100.0, value))
            return self._overall

    def eta(self) -> int:
        with self._lock:
            factor = self.speed()
            left = 0.0
            for s in self.order:
                if s in self.done:
                    continue
                f = self.frac[s]
                if s == self.current and f >= 0.1 and s in self.started:
                    elapsed = self._clock() - self.started[s]
                    left += elapsed * (1 - f) / f
                else:
                    left += self.eff[s] * (1 - f) * factor
            return int(round(left))

    def update(self, sid, done, total, unit=None, *, force=False, real=True):
        """a stage's counter moved: done of total units (total 0 = unknown). Emits when due."""
        with self._lock:
            if sid in self.done:
                return
            if total and real:
                f = min(1.0, done / total)
                # the first counter replaces a time-based guess; later ones only move forward (overall never
                # goes back either way: overall() keeps its maximum)
                self.frac[sid] = f if sid not in self._last_real else max(self.frac[sid], f)
            if real:
                self._last_real[sid] = self._clock()
            now = self._clock()
            due = force or (total and done >= total) or now - self._last_emit.get(sid, -1e9) >= self._rate
            if not due:
                return
            self._last_emit[sid] = now
            pct = round(100.0 * self.frac[sid], 1)
            fields = {'stage': sid, 'done': int(done), 'total': int(total), 'unit': unit or self.units.get(sid, ''),
                      'pct': pct, 'overall': round(self.overall(), 1), 'eta_s': self.eta()}
        self._emit(**fields)

    def tick(self):
        """the ticker (every ~0.5 s): a stage that has never reported a counter gets a time-based fraction."""
        with self._lock:
            sid = self.current
            counted = sid in COUNTED and self.eff.get(sid, 0) > CACHED_WEIGHT
            if sid is None or sid in self.done or sid not in self.started or sid in self._last_real or counted:
                return                                    # a stage with its own counter is never guessed
            now = self._clock()
            if now - self.started[sid] < 1.0:
                return
            elapsed = now - self.started[sid]
            guess = min(0.95, elapsed / max(self.eff[sid] * self.speed(), 0.5))
            if guess <= self.frac[sid]:
                return
            self.frac[sid] = guess
            if now - self._last_emit.get(sid, -1e9) < self._rate:
                return
            self._last_emit[sid] = now
            fields = {'stage': sid, 'done': 0, 'total': 0, 'unit': '', 'pct': round(100.0 * guess, 1),
                      'overall': round(self.overall(), 1), 'eta_s': self.eta()}
        self._emit(**fields)


class Ticker:
    """calls progress.tick() every `every` seconds on a daemon thread until stop()."""

    def __init__(self, progress, every=0.5):
        self._progress, self._every = progress, every
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='xml1builder-ticker', daemon=True)

    def _run(self):
        while not self._stop.wait(self._every):
            try:
                self._progress.tick()
            except Exception:  # noqa: BLE001 - a display helper must never break the build
                pass

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=2)
