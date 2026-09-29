"""xml1builder.cancel - stopping a build (BUILDER_DESIGN.md 2.5).

  * CancelToken: set by a `cancel` line on stdin, by EOF on stdin (the launcher went away) - both only in jsonl
    mode, as the launcher's fake builder does - or by Ctrl+C (KeyboardInterrupt, handled by the caller). The prepare
    stages poll it (prepare.check_cancel takes it: it has is_set()), the pipeline hits it at every checkpoint
    (xml1build.common.checkpoint: every ctx.log line, every file written, every base file synced).
  * The hard stop: the builder must exit within 15 s of `cancel` (the launcher kills its job object after that). A
    checkpoint is normally reached in well under a second, but a validator check or a worker pool can run for tens
    of seconds without one; so once cancelled, a watchdog gives the build GRACE seconds to unwind and then calls
    on_hard_stop (the caller writes the result event and releases its locks) and os._exit(5). Every file write is
    atomic and building.json stays, so a hard stop leaves an `incomplete` build that the next run resumes.
  * A job object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (Windows): the builder puts itself in it, so its worker
    processes (the prepare stages' and media's process pools) die with it however it ends. Nested in the launcher's
    own job object on Windows 8+; if that fails the builder logs it and carries on."""
from __future__ import annotations

import os
import sys
import threading
import time

from .errors import Cancelled

GRACE = 10.0          # seconds from cancel to the hard stop (the launcher allows 15)


class CancelToken:
    def __init__(self, grace=GRACE, exit_fn=os._exit):
        self._event = threading.Event()
        self.reason = None
        self.when = None
        self.grace = grace
        self._exit_fn = exit_fn
        self._hard_stop = None
        self._finished = threading.Event()
        self._lock = threading.Lock()

    # prepare.check_cancel() accepts an object with is_set() or a callable
    def is_set(self) -> bool:
        return self._event.is_set()

    def __call__(self) -> bool:
        return self._event.is_set()

    def set(self, reason='cancel'):
        with self._lock:
            if self._event.is_set():
                return
            self.reason, self.when = reason, time.monotonic()
            self._event.set()
        threading.Thread(target=self._watchdog, name='xml1builder-cancel-watchdog', daemon=True).start()

    def check(self):
        if self._event.is_set():
            raise Cancelled(self.reason or 'cancel')

    def on_hard_stop(self, fn):
        """fn() runs (on the watchdog thread) right before a hard stop: emit the result, release the locks."""
        self._hard_stop = fn

    def finished(self):
        """the command ended normally: no hard stop any more."""
        self._finished.set()

    def _watchdog(self):
        if self._finished.wait(self.grace):
            return
        try:
            if self._hard_stop is not None:
                self._hard_stop()
        finally:
            try:
                sys.stderr.flush()
            except (OSError, ValueError):
                pass
            self._exit_fn(5)


POLL = 0.2           # seconds between looks at a stdin pipe (Windows)


def watch_stdin(token: CancelToken, stream=None, log=None):
    """a daemon thread watching stdin: a `cancel` line (any case, surrounding space ignored) or EOF sets the token.

    stream: a test's line iterable. The real stdin on Windows is never read with a blocking ReadFile: while one
    thread waits in a synchronous read on a pipe, GetFileType on that pipe blocks too - and every DLL whose C runtime
    starts up calls it for the standard handles, under the loader lock (numpy's OpenBLAS hung the builder that way),
    as does subprocess when it duplicates the standard handles. So the pipe is polled with PeekNamedPipe and only
    what is there is read. A console stdin has no cancel channel (Ctrl+C is)."""
    if stream is not None:
        target = lambda: _watch_lines(token, stream)          # noqa: E731
    elif os.name == 'nt':
        target = lambda: _watch_windows(token, log)           # noqa: E731
    else:
        target = lambda: _watch_posix(token)                  # noqa: E731
    t = threading.Thread(target=target, name='xml1builder-stdin', daemon=True)
    t.start()
    return t


def _feed(token, buf: bytes) -> bytes:
    """act on the complete lines in buf; returns the unfinished rest."""
    while b'\n' in buf:
        line, buf = buf.split(b'\n', 1)
        if line.strip().lower() == b'cancel':
            token.set('cancel')
    return buf


def _watch_lines(token, stream):
    try:
        for line in stream:
            if str(line).strip().lower() == 'cancel':
                token.set('cancel')
                return
        token.set('eof')
    except (OSError, ValueError):
        token.set('eof')


def _watch_posix(token):
    import select
    try:
        fd = sys.stdin.fileno()
    except (AttributeError, OSError, ValueError):
        token.set('eof')
        return
    buf = b''
    try:
        while not token.is_set():
            ready, _, _ = select.select([fd], [], [], POLL * 5)
            if not ready:
                continue
            data = os.read(fd, 4096)
            if not data:
                token.set('eof')
                return
            buf = _feed(token, buf + data)
    except (OSError, ValueError):
        token.set('eof')


def _watch_windows(token, log=None):
    import ctypes
    import msvcrt
    from ctypes import wintypes as W
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.GetFileType.argtypes = [W.HANDLE]
    k32.PeekNamedPipe.argtypes = [W.HANDLE, W.LPVOID, W.DWORD, ctypes.POINTER(W.DWORD), ctypes.POINTER(W.DWORD),
                                  ctypes.POINTER(W.DWORD)]
    k32.ReadFile.argtypes = [W.HANDLE, W.LPVOID, W.DWORD, ctypes.POINTER(W.DWORD), W.LPVOID]
    try:
        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
    except (AttributeError, OSError, ValueError):
        token.set('eof')                                   # no stdin at all: nobody can send cancel
        return
    kind = k32.GetFileType(handle)
    if kind == 2:                                          # FILE_TYPE_CHAR: a console (or NUL): Ctrl+C only
        if log:
            log('cancel: stdin is a console; cancel with Ctrl+C')
        return
    buf = b''
    if kind != 3:                                          # a file: it ends; read it whole (no blocking wait)
        try:
            data = sys.stdin.buffer.read()
        except (OSError, ValueError):
            data = b''
        _feed(token, data + b'\n')
        token.set('eof')
        return
    avail = W.DWORD()
    got = W.DWORD()
    chunk = ctypes.create_string_buffer(4096)
    while not token.is_set():
        if not k32.PeekNamedPipe(handle, None, 0, None, ctypes.byref(avail), None):
            token.set('eof')                               # ERROR_BROKEN_PIPE: the launcher went away
            return
        if avail.value:
            n = min(avail.value, len(chunk))
            if not k32.ReadFile(handle, chunk, n, ctypes.byref(got), None):
                token.set('eof')
                return
            buf = _feed(token, buf + chunk.raw[:got.value])
            continue
        time.sleep(POLL)


_JOB = None


def own_job_object(log=None) -> bool:
    """put this process into a new job object that kills its members when the last handle closes (when the builder
    ends, however it ends). The handle is kept for the life of the process. Windows only; False elsewhere or on
    failure."""
    global _JOB
    if _JOB is not None:
        return True
    if os.name != 'nt':
        return False
    try:
        import ctypes
        from ctypes import wintypes as W

        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.CreateJobObjectW.restype = W.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, W.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
        k32.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
        k32.GetCurrentProcess.restype = W.HANDLE

        class BASIC(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                        ('LimitFlags', W.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', W.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', W.DWORD), ('SchedulingClass', W.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ('ReadOperationCount', 'WriteOperationCount',
                                                       'OtherOperationCount', 'ReadTransferCount',
                                                       'WriteTransferCount', 'OtherTransferCount')]

        class EXTENDED(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', BASIC), ('IoInfo', IO), ('ProcessMemoryLimit', ctypes.c_size_t),
                        ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t),
                        ('PeakJobMemoryUsed', ctypes.c_size_t)]

        job = k32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(ctypes.get_last_error(), 'CreateJobObjectW')
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):   # Extended = 9
            raise OSError(ctypes.get_last_error(), 'SetInformationJobObject')
        if not k32.AssignProcessToJobObject(job, k32.GetCurrentProcess()):
            raise OSError(ctypes.get_last_error(), 'AssignProcessToJobObject')
        _JOB = job
        return True
    except (OSError, AttributeError) as e:
        if log:
            log(f'cancel: no job object for the worker processes ({e}); they still stop with the pool')
        return False
