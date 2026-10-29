"""lc-save-writer/1: exclusive handle lease, never a PID or existence lock.

The cooperating DLL holds this same file open for its entire SaveLC lifetime.
Importer transactions hold it across all rechecks and filesystem mutations.
The file persists; process death releases the kernel lease automatically. Never
unlink it: deleting/recreating locks can allow two owners of different inodes.
"""
from __future__ import annotations

import os
import stat

from .errors import ImportRefusal
from .source import safe_path

LOCK_NAME = '.lc-save-writer.lock'
PROTOCOL = 'lc-save-writer/1'


class WriterLock:
    def __init__(self, save_dir):
        self.directory = safe_path(save_dir, directory=True)
        self.fd = None

    def __enter__(self):
        if self.fd is not None:
            raise RuntimeError('WriterLock cannot be acquired twice.')
        # Never automatically clear a pre-protocol lock: it may be live.
        legacy = safe_path(self.directory / '.xml1-import.lock')
        try:
            legacy.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ImportRefusal('BUSY', 'A legacy importer lock requires manual review after all writers close.')
        path = safe_path(self.directory / LOCK_NAME)
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            import msvcrt
            api = ctypes.WinDLL('kernel32', use_last_error=True)
            api.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
            api.CreateFileW.restype = wintypes.HANDLE
            api.CloseHandle.argtypes = (wintypes.HANDLE,)
            # GENERIC_READ|WRITE, share=0, OPEN_ALWAYS, OPEN_REPARSE_POINT.
            handle = api.CreateFileW(str(path), 0xc0000000, 0, None, 4, 0x00200000, None)
            if handle == wintypes.HANDLE(-1).value:
                error = ctypes.get_last_error()
                if error in (32, 33):
                    raise ImportRefusal('BUSY', 'The game or another importer holds the SaveLC writer lease.')
                raise ctypes.WinError(error)
            try:
                fd = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY | os.O_NOINHERIT)
            except BaseException:
                api.CloseHandle(handle)
                raise
        else:
            import fcntl
            fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as e:
                os.close(fd)
                raise ImportRefusal('BUSY') from e
            except BaseException:
                os.close(fd)
                raise
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ImportRefusal('INPUT', 'The writer lease must be a regular file.')
            safe_path(path)
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd
        return self

    def __exit__(self, exc_type, exc, tb):
        fd, self.fd = self.fd, None
        if fd is not None:
            os.close(fd)
        return False
