"""xml1builder.lock - one build at a time per output folder and per cache (BUILDER_DESIGN.md 2.6).

A lock is a file created exclusively (O_CREAT | O_EXCL) holding {"pid", "started", "command"}; `started` is the
holder's process creation time where the OS gives it (Windows: GetProcessTimes), so a recycled pid is not mistaken
for the holder. A lock whose holder is gone (a crashed or killed builder) is taken over. <out>/_build/lock guards
the output folder (E_OUT_LOCKED), <cache>/lock the prepare cache (two builders on one cache would delete each
other's .partial stage directories; E_CACHE_LOCKED)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


class LockHeld(Exception):
    def __init__(self, path, holder):
        super().__init__(f'{path} is held by pid {holder.get("pid")}')
        self.path, self.holder = Path(path), holder


_K32 = None


def _k32():
    """kernel32 with the prototypes this module uses (handles are pointer-sized)."""
    global _K32
    if _K32 is None:
        import ctypes
        from ctypes import wintypes as W
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.OpenProcess.restype = W.HANDLE
        k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        k.GetProcessTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4
        k.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
        k.CloseHandle.argtypes = [W.HANDLE]
        _K32 = k
    return _K32


def process_started(pid: int):
    """the process's creation time (Windows FILETIME ticks) or None when unknown / not running."""
    if os.name != 'nt':
        return None
    try:
        import ctypes
        from ctypes import wintypes as W
        k32 = _k32()
        handle = k32.OpenProcess(0x1000, False, int(pid))            # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            times = [W.FILETIME() for _ in range(4)]
            if not k32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
                return None
            return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        finally:
            k32.CloseHandle(handle)
    except (OSError, AttributeError):
        return None


def pid_alive(pid: int, started=None) -> bool:
    """is `pid` running (and, when `started` is known, the same process that took the lock)?"""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes as W
        k32 = _k32()
        handle = k32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5          # ERROR_ACCESS_DENIED: it exists
        try:
            code = W.DWORD()
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:     # STILL_ACTIVE
                return False
        finally:
            k32.CloseHandle(handle)
        if started is not None:
            now = process_started(pid)
            return now is None or now == started
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


class FileLock:
    def __init__(self, path, command=''):
        self.path = Path(path)
        self.command = command
        self.held = False

    def read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except ValueError:
            try:                                          # the fake builder's / an old format: just the pid
                return {'pid': int(self.path.read_text(encoding='utf-8').strip() or 0)}
            except (OSError, ValueError):
                return {}
        except OSError:
            return {}

    def acquire(self):
        """take the lock (a stale one is taken over); raises LockHeld when a live builder holds it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps({'pid': os.getpid(), 'started': process_started(os.getpid()), 'command': self.command,
                           'time': time.strftime('%Y-%m-%dT%H:%M:%S')}).encode('utf-8')
        for _ in range(3):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                holder = self.read()
                if holder.get('pid') and pid_alive(holder.get('pid'), holder.get('started')):
                    raise LockHeld(self.path, holder)
                try:
                    self.path.unlink()                    # stale: its builder is gone
                except FileNotFoundError:
                    pass
                except OSError:
                    time.sleep(0.2)
                continue
            try:
                os.write(fd, body)
            finally:
                os.close(fd)
            self.held = True
            return self
        raise LockHeld(self.path, self.read())

    def release(self):
        if not self.held:
            return
        self.held = False
        try:
            if self.read().get('pid') == os.getpid():
                self.path.unlink()
        except OSError:
            pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
