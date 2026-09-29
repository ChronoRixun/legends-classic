"""xml1builder.events - the event stream and the human text (BUILDER_DESIGN.md 2.3, 2.4).

--events jsonl: stdout carries only events, one JSON object per line (UTF-8, flushed per line); every event has
"ev" and "t" (ms since start). Human text - the builder's own lines and everything the pipeline prints - goes to
stderr and to the log. To keep stray output (a worker process, a C library) out of the event stream, the original
stdout is duplicated for the events and file descriptor 1 is pointed at stderr.
--events text (the default): the events are rendered as human lines on stdout (progress at most every 2 s).

Event kinds (schema 1; the launcher's fake builder is the reference):
  hello     {v, builder, content_version, commit, pid, project}                              always first
  plan      {stages: [{id, title, weight, cached}]}                                        build, once
  stage     {id, state: start|done, seconds, cached}
  progress  {stage, done, total, unit, pct, overall, eta_s}                                 <= 4/s per stage
  log       {level, stage, msg}
  warning   {stage, code, msg, detail: {count, ...}, count?}     detail.count: how many (files, pipeline warnings);
                                                                 W_PIPELINE also keeps its top-level count
  error     {stage, code, msg, hint, detail}
  result    {ok, exit, ...}                  info / verify / clean: result.info / result.verify / result.clean

Every string of every event and every human line passes through mask() (the user profile folder shown as
%USERPROFILE%): logs, events and the launcher's Copy details / Report end up in bug reports.

The log (<out>/_build/builder.log, rotated: builder.log, builder.1.log, builder.2.log; before <out> is known, --log
or <cache>/logs/builder-<time>.log) gets the human text and every event but progress."""
from __future__ import annotations

import datetime
import io
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

LOG_KEEP = 3                       # builder.log + builder.1.log + builder.2.log
TEXT_PROGRESS_EVERY = 2.0          # seconds between progress lines in text mode
_MASK = [None, None]               # (the profile folders it was made for, the compiled pattern)


def _mask_rx():
    profs = tuple(p.rstrip('\\/') for p in (os.environ.get('USERPROFILE'), os.environ.get('HOME')) if p and len(p) > 3)
    if _MASK[0] != profs:
        forms = set()
        for prof in profs:
            # as typed, with either separator, and doubled backslashes (a repr'd dict in a human line)
            back = prof.replace('/', '\\')
            forms |= {prof, prof.replace('\\', '/'), back, back.replace('\\', '\\\\')}
        alts = '|'.join(re.escape(f) for f in sorted(forms, key=len, reverse=True))
        # any case (Windows paths), and only the whole folder name (<profile>, not <profile>2)
        _MASK[:] = [profs, re.compile(f'(?:{alts})(?![\\w-])', re.IGNORECASE) if alts else None]
    return _MASK[1]


def mask(value):
    """a path (or any text) with the user profile folder shown as %USERPROFILE% (logs and events are shared in bug
    reports). The one helper: Output applies it to every event and every human line."""
    text = str(value)
    rx = _mask_rx()
    return rx.sub('%USERPROFILE%', text) if rx is not None else text


def mask_all(obj):
    """obj (an event's fields) with mask() applied to every string (and path) in it."""
    if isinstance(obj, str):
        return mask(obj)
    if isinstance(obj, dict):
        return {k: mask_all(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [mask_all(v) for v in obj]
    if isinstance(obj, os.PathLike):
        return mask(os.fspath(obj))
    return obj


def rotate_logs(path: Path, keep=LOG_KEEP):
    """builder.log -> builder.1.log -> builder.2.log (the oldest is dropped)."""
    if not path.exists():
        return
    stem, suffix = path.stem, path.suffix
    for index in range(keep - 1, 0, -1):
        newer = path if index == 1 else path.with_name(f'{stem}.{index - 1}{suffix}')
        older = path.with_name(f'{stem}.{index}{suffix}')
        if newer.exists():
            try:
                os.replace(newer, older)
            except OSError:
                pass


class _LineTee(io.TextIOBase):
    """sys.stdout replacement for the pipeline's prints: whole lines go to `sink(line)`."""

    def __init__(self, sink):
        self._sink = sink
        self._buf = ''
        self._lock = threading.Lock()

    def writable(self):
        return True

    def write(self, text):
        if not text:
            return 0
        lines = []
        with self._lock:
            self._buf += str(text)
            while '\n' in self._buf:
                line, self._buf = self._buf.split('\n', 1)
                lines.append(line.rstrip('\r'))
        for line in lines:
            self._sink(line)
        return len(text)

    def flush(self):
        with self._lock:
            line, self._buf = self._buf, ''
        if line:
            self._sink(line)


class Output:
    """Events + human text + the log file. Thread-safe."""

    def __init__(self, jsonl=False, quiet=False, log_file=None, *, stdout=None, stderr=None, clock=time.monotonic):
        self.jsonl, self.quiet = jsonl, quiet
        self._clock = clock
        self._start = clock()
        self._lock = threading.RLock()
        self._stdout = stdout or sys.stdout
        self._stderr = stderr or sys.stderr
        if jsonl and hasattr(self._stdout, 'reconfigure'):
            try:
                self._stdout.reconfigure(newline='\n')         # every event line ends with LF (no CRLF on Windows)
            except (ValueError, OSError):
                pass
        self._events = self._stdout
        self._log = None
        self.log_path = None
        self._pending = []
        self._saved_stdout = None
        self._text_last = {}
        self.titles = {}
        if log_file:
            self.open_log(Path(log_file), rotate=False)

    # ------------------------------------------------------------------ stream setup
    def capture_stdout(self, fd_redirect=True):
        """route the pipeline's prints (sys.stdout) to human(); in jsonl mode also point fd 1 at stderr so nothing
        but events reaches the real stdout (fd_redirect=False in tests)."""
        if self._saved_stdout is not None:
            return
        if self.jsonl and fd_redirect:
            try:
                self._stdout.flush()
                fd = os.dup(self._stdout.fileno())
                self._events = open(fd, 'w', encoding='utf-8', newline='\n', buffering=1, closefd=True)
                os.dup2(self._stderr.fileno(), 1)
            except (OSError, ValueError, AttributeError, io.UnsupportedOperation):
                self._events = self._stdout
        self._saved_stdout = sys.stdout
        sys.stdout = _LineTee(self.human)

    def restore_stdout(self):
        if self._saved_stdout is not None:
            try:
                sys.stdout.flush()
            except (OSError, ValueError):
                pass
            sys.stdout = self._saved_stdout
            self._saved_stdout = None

    def t(self) -> int:
        return int((self._clock() - self._start) * 1000)

    # ------------------------------------------------------------------ events
    def event(self, ev, **fields):
        if ev == 'warning':                    # every warning says how many: detail.count (default 1)
            detail = dict(fields.get('detail') or {})
            detail.setdefault('count', fields.get('count', 1))
            fields['detail'] = detail
        record = {'ev': ev, 't': self.t(), **mask_all(fields)}
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            if self.jsonl:
                try:
                    self._events.write(line + '\n')
                    self._events.flush()
                except (OSError, ValueError):
                    pass
            else:
                self._render_text(record)
            if ev != 'progress':
                self._write_log(line)
        return record

    def _render_text(self, r):
        ev = r['ev']
        text = None
        if ev == 'hello':
            text = f"xml1-builder {r.get('builder')} ({r.get('project', '')}; content {r.get('content_version')}, " \
                   f"commit {r.get('commit')})"
        elif ev == 'plan':
            self.titles = {s['id']: s.get('title', s['id']) for s in r.get('stages', [])}
            text = 'plan: ' + ', '.join(f"{s['id']}{' (cached)' if s.get('cached') else ''}" for s in r['stages'])
        elif ev == 'stage':
            title = self.titles.get(r.get('id'), r.get('id'))
            if r.get('state') == 'start':
                text = f"== {title}"
            else:
                text = f"== {title}: done in {r.get('seconds')} s{' (cached)' if r.get('cached') else ''}"
        elif ev == 'progress':
            now = self._clock()
            key = r.get('stage')
            if r.get('done') == r.get('total') and r.get('total'):
                pass
            elif now - self._text_last.get(key, 0) < TEXT_PROGRESS_EVERY:
                return
            self._text_last[key] = now
            count = f" {r['done']}/{r['total']} {r.get('unit', '')}".rstrip() if r.get('total') else ''
            eta = r.get('eta_s')
            left = f", about {_duration(eta)} left" if isinstance(eta, (int, float)) and eta > 0 else ''
            text = f"   {key}: {r.get('pct', 0):.0f}%{count} - overall {r.get('overall', 0):.0f}%{left}"
        elif ev == 'log':
            text = f"[{r.get('stage')}] {r.get('msg')}"
        elif ev == 'warning':
            text = f"warning {r.get('code')}: {r.get('msg')}"
        elif ev == 'error':
            text = f"error {r.get('code')}: {r.get('msg')}" + (f"\n  hint: {r['hint']}" if r.get('hint') else '')
        elif ev == 'result':
            text = f"result: {'ok' if r.get('ok') else 'failed'} (exit {r.get('exit')})"
        if text is not None and not self.quiet:
            try:
                self._stdout.write(text + '\n')
                self._stdout.flush()
            except (OSError, ValueError):
                pass

    # ------------------------------------------------------------------ human text + log
    def human(self, text):
        """a line of human text: stderr in jsonl mode, stdout otherwise; always the log (profile paths masked)."""
        text = mask(text)
        with self._lock:
            if not self.quiet:
                stream = self._stderr if self.jsonl else self._stdout
                try:
                    stream.write(text + '\n')
                    stream.flush()
                except (OSError, ValueError):
                    pass
            self._write_log(text)

    def open_log(self, path: Path, rotate=True):
        """start (or move) the log file; lines logged before are written into it first."""
        path = Path(path)
        with self._lock:
            if self._log is not None and self.log_path == path:
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            if rotate:
                rotate_logs(path)
            previous, self._log = self._log, open(path, 'a', encoding='utf-8')
            self.log_path = path
            if previous is not None:
                previous.close()
            for line in self._pending:
                self._log.write(line + '\n')
            self._pending = []
            self._log.flush()

    def _write_log(self, line):
        stamp = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        entry = f'{stamp} {line}'
        if self._log is not None:
            try:
                self._log.write(entry + '\n')
                self._log.flush()
            except (OSError, ValueError):
                pass
        else:
            self._pending.append(entry)
            if len(self._pending) > 20000:
                del self._pending[:10000]

    def close(self):
        self.restore_stdout()
        with self._lock:
            if self._log is not None:
                try:
                    self._log.close()
                except OSError:
                    pass
                self._log = None
            if self._events is not self._stdout:
                try:
                    self._events.flush()
                except (OSError, ValueError):
                    pass


def _duration(seconds):
    seconds = int(seconds)
    if seconds < 90:
        return f'{seconds} s'
    minutes = round(seconds / 60)
    return f'{minutes} min' if minutes < 90 else f'{minutes // 60} h {minutes % 60} min'


# ------------------------------------------------------------------------------------------------ schema
REQUIRED = {
    'hello': {'v', 'builder', 'content_version', 'commit', 'pid'},
    'plan': {'stages'},
    'stage': {'id', 'state'},
    'progress': {'stage', 'done', 'total', 'unit', 'pct', 'overall', 'eta_s'},
    'log': {'level', 'stage', 'msg'},
    'warning': {'stage', 'code', 'msg', 'detail'},
    'error': {'stage', 'code', 'msg', 'hint', 'detail'},
    'result': {'ok', 'exit'},
}


def check_event(record: dict) -> list:
    """schema problems of one event (the unit tests and the smoke tests use it); [] = valid."""
    problems = []
    ev = record.get('ev')
    if ev not in REQUIRED:
        return [f'unknown event {ev!r}']
    if not isinstance(record.get('t'), int):
        problems.append('t is not an integer')
    missing = REQUIRED[ev] - set(record)
    if missing:
        problems.append(f'{ev}: missing {sorted(missing)}')
    if ev == 'plan':
        for s in record.get('stages', []):
            if not {'id', 'title', 'weight', 'cached'} <= set(s):
                problems.append(f'plan stage {s} lacks id/title/weight/cached')
    if ev == 'stage' and record.get('state') not in ('start', 'done'):
        problems.append(f"stage state {record.get('state')!r}")
    if ev == 'progress':
        for k in ('done', 'total', 'eta_s'):
            if not isinstance(record.get(k), int):
                problems.append(f'progress.{k} is not an integer')
        if not 0 <= float(record.get('overall', -1)) <= 100:
            problems.append('progress.overall outside 0..100')
    if ev == 'error' and not isinstance(record.get('detail'), dict):
        problems.append('error.detail is not an object')
    if ev == 'warning':
        detail = record.get('detail')
        if not (isinstance(detail, dict) and isinstance(detail.get('count'), int)):
            problems.append('warning.detail.count is not an integer')
    if ev == 'result' and not isinstance(record.get('exit'), int):
        problems.append('result.exit is not an integer')
    return problems
