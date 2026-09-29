"""xml1builder.errors - the stable error codes, their exit codes (BUILDER_DESIGN.md 2.2) and English fallback text.

The launcher translates the codes it knows (its i18n `xml1.errors.<code>`) and shows `msg` / `hint` for new ones, so
`msg` is always a complete English sentence. detail carries the facts the launcher shows: title (the game found on a
disc), missing (files), need / free / volume (space), module (a failed step), pid (a lock holder), path / where /
cause (E_IO: the file relative to its folder, IO_CAUSES below)."""
from __future__ import annotations

import errno
import os
import re

from . import ISSUES_URL

REPORT_HINT = f'This is a bug in the builder: please report it at {ISSUES_URL} with the build log.'

# exit codes (2.2)
OK, FAILED, REFUSED, INPUT, SPACE, CANCELLED, IO, INTERNAL = 0, 1, 2, 3, 4, 5, 6, 70

_EXACT = {'E_SPACE': SPACE, 'E_IO': IO, 'E_INTERNAL': INTERNAL, 'E_PIPELINE': FAILED, 'E_VALIDATE': FAILED,
          'E_USAGE': REFUSED, 'E_OUT_UNSAFE': REFUSED, 'E_OUT_FOREIGN': REFUSED, 'E_OUT_LOCKED': REFUSED,
          'E_CACHE_LOCKED': REFUSED, 'E_CANCELLED': CANCELLED}
_PREFIX = (('E_ISO_', INPUT), ('E_XML2_', INPUT), ('E_CACHE_', INPUT), ('E_PREPARE_', FAILED))

HINTS = {
    'E_PIPELINE': REPORT_HINT,
    'E_VALIDATE': REPORT_HINT,
    'E_INTERNAL': REPORT_HINT,
    'E_IO': 'Close X-Men Legends if it is running and check the folder is writable, then try again.',
    'E_SPACE': 'Free up some space or choose a folder on another drive.',
    'E_OUT_LOCKED': 'Another build is writing to this folder: wait for it to finish.',
    'E_CACHE_LOCKED': 'Another build is using the build cache: wait for it to finish.',
    'E_OUT_FOREIGN': 'Choose an empty folder, or one the builder made before.',
    'E_OUT_UNSAFE': 'Choose a separate folder for X-Men Legends.',
    'E_XML2_UNKNOWN_EXE': 'The port needs the retail PC version of X-Men Legends II (XMen2.exe as released).',
    'E_XML2_NOT_FOUND': 'Check X-Men Legends II\'s folder (in the launcher: its page, Settings).',
    'E_XML2_LANGUAGE': 'The port needs the English PC version of X-Men Legends II.',
}


def exit_for(code: str) -> int:
    if code in _EXACT:
        return _EXACT[code]
    for prefix, value in _PREFIX:
        if code.startswith(prefix):
            return value
    return FAILED


class BuilderError(Exception):
    """a failure with a stable code: reported as one `error` event, then `result` with exit_for(code)."""

    def __init__(self, code, msg, hint=None, detail=None, stage=None, exit_code=None):
        super().__init__(f'{code}: {msg}')
        self.code, self.msg = code, msg
        self.hint = HINTS.get(code, '') if hint is None else hint
        self.detail = dict(detail or {})
        self.stage = stage
        self.exit_code = exit_for(code) if exit_code is None else exit_code


# ------------------------------------------------------------------------------------------------ OS-level I/O errors
# An OSError the player's machine caused (a file another program holds open, a full / failing / write-protected
# drive) is E_IO (exit 6) naming the file and the cause, wherever it happens (probe, prepare, sync, a content module,
# the validator, finish); anything else a module raises stays E_PIPELINE (our bug). detail.cause is one of:
IO_CAUSES = {
    'held': 'another program has it open',
    'read_only': 'it is read-only',
    'denied': 'access to it was denied',
    'disk_full': 'the disk is full',
    'drive_read_only': 'the drive is write-protected',
    'disk_error': 'the disk reported an error',
    'drive_gone': 'the drive is not available',
    'too_long': 'its path is too long',
}
IO_HINTS = {
    'held': 'Close the program that has the file open (X-Men Legends, an editor, a file manager or an antivirus '
            'scan), then try again.',
    'disk_full': 'Free up some space on that drive, then try again.',
    'disk_error': 'Check the drive for errors, then try again.',
    'drive_gone': 'Reconnect the drive, then try again.',
    'too_long': 'Choose a folder with a shorter path.',
}
_WINERRORS = {32: 'held', 33: 'held', 5: 'denied', 112: 'disk_full', 39: 'disk_full', 19: 'drive_read_only',
              23: 'disk_error', 483: 'disk_error', 1117: 'disk_error', 21: 'drive_gone', 55: 'drive_gone',
              64: 'drive_gone', 206: 'too_long'}
_ERRNOS = {errno.EACCES: 'denied', errno.EPERM: 'denied', errno.EBUSY: 'held', errno.ENOSPC: 'disk_full',
           errno.EROFS: 'drive_read_only', errno.EIO: 'disk_error', errno.ENAMETOOLONG: 'too_long'}
for _name, _cause in (('ETXTBSY', 'held'), ('EDQUOT', 'disk_full')):
    if hasattr(errno, _name):
        _ERRNOS[getattr(errno, _name)] = _cause
_TMP_RX = re.compile(r'\.tmp\d+(_\d+)?$', re.IGNORECASE)     # = manifest.TMP_RX (the atomic writers' temp files)


def io_target(exc) -> str | None:
    """the file an OSError is about: the destination of a rename (os.replace(temp, file): filename2), else filename,
    without an atomic writer's temp suffix (x.igb.tmp123_456 -> x.igb)."""
    for name in (getattr(exc, 'filename2', None), getattr(exc, 'filename', None)):
        if isinstance(name, (str, os.PathLike)) and os.fspath(name):
            return _TMP_RX.sub('', os.fspath(name))
    return None


def io_cause(exc, path=None) -> str | None:
    """the IO_CAUSES code of an OS-level I/O failure, or None when exc is not one (a missing file, a bad argument,
    WriteCheckError: handled elsewhere). A denied access to an existing file is refined: read-only, or on Windows
    another program's open handle (os.replace onto / unlink of a file open elsewhere: WinError 5 / 32)."""
    if not isinstance(exc, OSError):
        return None
    winerror = getattr(exc, 'winerror', None)
    cause = _WINERRORS.get(winerror) if winerror else None
    if cause is None:
        cause = _ERRNOS.get(exc.errno)
    path = path if path is not None else io_target(exc)
    if cause == 'denied' and path is not None:
        try:
            if os.path.isfile(path):
                if not os.access(path, os.W_OK):
                    cause = 'read_only'
                elif os.name == 'nt':
                    cause = 'held'
        except (OSError, ValueError):
            pass
    return cause


def _where(path: str, roots) -> tuple:
    """(the name a message shows, detail.path, detail.where): relative to <out> / the cache / X-Men Legends II's folder
    when the file is inside one of them (roots: [(folder, 'out' | 'cache' | 'xml2')]), else the path (masked)."""
    full = os.path.normcase(os.path.abspath(path))
    for folder, where in roots:
        if not folder:
            continue
        top = os.path.normcase(os.path.abspath(os.fspath(folder)))
        if full.startswith(top.rstrip('\\/') + os.sep):
            rel = os.path.relpath(os.path.abspath(path), os.path.abspath(os.fspath(folder))).replace(os.sep, '/')
            label = {'cache': f'{rel} (in the build cache)', 'xml2': f'{rel} (in X-Men Legends II\'s folder)'}
            return label.get(where, rel), rel, where
    from .events import mask
    return mask(path), mask(path), None


def io_error(exc, stage=None, roots=(), strict=True):
    """the E_IO BuilderError of an OSError: `A file could not be read or written: <file> (<cause>).`, the file relative
    to its folder (roots), detail {path, where, cause, errno, winerror}. strict: None unless io_cause knows the cause
    (a content module's other OSErrors stay E_PIPELINE); not strict: any OSError (the cause then its strerror)."""
    if not isinstance(exc, OSError):
        return None
    target = io_target(exc)
    cause = io_cause(exc, target)
    if cause is None and strict:
        return None
    words = IO_CAUSES.get(cause) or (exc.strerror or type(exc).__name__)
    if target:
        name, rel, where = _where(target, roots)
        msg = f'A file could not be read or written: {name} ({words}).'
    else:
        rel = where = None
        msg = f'A file could not be read or written ({words}).'
    detail = {'path': rel, 'where': where, 'cause': cause or 'other', 'errno': exc.errno,
              'winerror': getattr(exc, 'winerror', None)}
    return BuilderError('E_IO', msg, IO_HINTS.get(cause), detail, stage)


def io_in_chain(exc):
    """the first OSError with an io_cause in exc and its causes / contexts (a module that wrapped it), or None."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, OSError) and io_cause(exc) is not None:
            return exc
        exc = exc.__cause__ or exc.__context__
    return None


class Cancelled(BaseException):
    """the build was asked to stop (a `cancel` line / EOF on stdin, Ctrl+C). A BaseException, so the pipeline's
    `except Exception` handlers (run_step, the validator's per-check guard, worker threads) let it through."""
