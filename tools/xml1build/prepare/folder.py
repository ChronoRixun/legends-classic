"""A bounded, read-only view of verified originals in an extracted Xbox install.

Only packaged reference paths enter the image-reader interface. Recomp loose
assets, settings and saves are never opened or recursively walked. Hashes cover
the archive itself as well as every original sound/movie, even without movies.
"""
from __future__ import annotations

import hashlib
import io
import os
import stat
from pathlib import Path

from . import PrepareError, check_cancel, digest
from .image import Entry

REFERENCE_FILE = 'known_dump_files.json'
MAX_ENTRIES = 10000
MAX_DEPTH = 32
CHUNK = 8 << 20


def references():
    from xml1builder import resources
    return (resources.load_json(REFERENCE_FILE, {}) or {}).get('dumps', [])


def consumed(path):
    """The P1 original-file contract, including movies.json's inputs with --no-movies."""
    return path in ('default.xbe', 'z/assetsfb.zip') or path.startswith(('sounds/zsds/', 'movies/ntsc/'))


def safe_path(path):
    n = str(path).replace('\\', '/')
    parts = n.split('/')
    if len(parts) > MAX_DEPTH or any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in parts) \
            or ':' in n or '\0' in n:
        raise PrepareError('E_ISO_FOLDER_UNSAFE', f'unsafe extracted-install path {n!r}',
                           'choose an ordinary folder containing your original extracted disc files', {'file': n})
    return n.lower()


def _fail(code, rel, reason):
    raise PrepareError(code, f'original {rel}: {reason}',
                       'restore this original file from your own known-good Xbox disc; keep the loose recomp '
                       'assets separate from the originals', {'file': rel})


def _regular(st, rel, directory=False):
    if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        _fail('E_ISO_FOLDER_UNSAFE', rel, 'links and junctions are not supported')
    if not (stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode)):
        _fail('E_ISO_FOLDER_UNSAFE', rel, 'expected an ordinary directory' if directory else 'expected an ordinary file')
    if not directory and st.st_nlink != 1:
        _fail('E_ISO_FOLDER_UNSAFE', rel, 'hard links are not supported')


def _signature(st):
    # On Windows 3.14 lstat's legacy ctime is creation time, while fstat may
    # expose change time. Compare birthtime explicitly there. Open handles
    # deny writers on Windows; POSIX ctime detects writes with restored mtime.
    extra = st.st_birthtime_ns if os.name == 'nt' else st.st_ctime_ns
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, extra]


def open_readonly(path):
    """Read an original, denying concurrent writes/deletes on Windows."""
    if os.name != 'nt':
        return open(path, 'rb')
    import ctypes
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    # GENERIC_READ, FILE_SHARE_READ (no writes/deletes), OPEN_EXISTING,
    # FILE_FLAG_OPEN_REPARSE_POINT (never follow a swapped final component).
    handle = create(str(path), 0x80000000, 1, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close = kernel.CloseHandle
        close.argtypes, close.restype = (wintypes.HANDLE,), wintypes.BOOL
        close(handle)
        raise
    return os.fdopen(fd, 'rb')


class _CheckedFile(io.BufferedIOBase):
    """Seekable verified handle; check replacement/truncation before and after every read."""
    def __init__(self, owner, rel, fh):
        self.owner, self.rel, self.fh = owner, rel, fh

    def readable(self):
        return True

    def seekable(self):
        return True

    def _check(self):
        self.owner._check_file(self.rel, self.fh)

    def read(self, size=-1):
        self._check()
        data = self.fh.read(size)
        self._check()
        return data

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    def seek(self, offset, whence=io.SEEK_SET):
        self._check()
        return self.fh.seek(offset, whence)

    def tell(self):
        self._check()
        return self.fh.tell()

    def close(self):
        if not self.closed:
            self.fh.close()
        super().close()


class FolderImage:
    """The XdvdfsImage read interface restricted to trusted originals, with SHA-256 verification.

    No file in this folder is written. Canonical paths come from the reference,
    so host case, overlay files and empty directories cannot change output.
    """
    format = 'folder'
    partition = None

    def __init__(self, path, *, cancel=None):
        # Do not resolve away a symlink/junction before it can be refused.
        self.path = Path(os.path.abspath(path))
        self.cancel = cancel
        self.entries, self._paths, self._stats, self._dirs, self._scans = {}, {}, {}, {}, {}
        self._handles = []
        self._check_root(initial=True)
        refs = references()
        if not refs:
            _fail('E_ISO_FOLDER_REFERENCE', 'default.xbe', 'the builder has no trusted extracted-file reference')
        for ref in refs:
            files = ref.get('files', {})
            if not files or len(files) > MAX_ENTRIES or 'default.xbe' not in files or 'z/assetsfb.zip' not in files \
                    or not any(p.startswith('sounds/zsds/') for p in files) \
                    or not any(p.startswith('movies/ntsc/') for p in files):
                _fail('E_ISO_FOLDER_REFERENCE', 'default.xbe', 'the packaged reference is incomplete')
            for rel, row in files.items():
                if safe_path(rel) != rel or not consumed(rel):
                    _fail('E_ISO_FOLDER_UNSAFE', rel, 'unsafe original-file reference')
                if len(row) != 2 or not isinstance(row[0], int) or row[0] < 0 or len(row[1]) != 64 \
                        or any(c not in '0123456789abcdef' for c in row[1]):
                    _fail('E_ISO_FOLDER_REFERENCE', rel, 'invalid packaged size or SHA-256')
        xbe = self._locate('default.xbe')
        st = xbe.lstat()
        _regular(st, 'default.xbe')
        self._paths['default.xbe'], self._stats['default.xbe'] = xbe, _signature(st)
        with self._open('default.xbe') as fh:
            xbe_hash = self._hash('default.xbe', fh)
        self.reference = next((r for r in refs if r['files']['default.xbe'] == [st.st_size, xbe_hash]), None)
        if self.reference is None:
            _fail('E_ISO_FOLDER_MODIFIED', 'default.xbe', 'does not match a trusted original (size/SHA-256)')
        self.reference_digest = digest(self.reference['files'])
        for rel, (size, expected) in sorted(self.reference['files'].items()):
            p = self._locate(rel)
            st = p.lstat()
            _regular(st, rel)
            if st.st_size != size:
                _fail('E_ISO_FOLDER_MODIFIED', rel, 'does not match the trusted original size')
            self._paths[rel], self._stats[rel] = p, _signature(st)
            with self._open(rel) as fh:
                if self._hash(rel, fh) != expected:
                    _fail('E_ISO_FOLDER_MODIFIED', rel, 'does not match the trusted original SHA-256')
            self.entries[rel] = Entry(rel, 0, size, False)
            parts = rel.split('/')
            for i in range(1, len(parts)):
                parent = '/'.join(parts[:i])
                self.entries[parent] = Entry(parent, 0, 0, True)
        self.size = sum(e.size for e in self.entries.values())
        self.recomp_layout = '.xml1-player-layout' in self._scan(self.path)
        self.assert_unchanged()

    def _check_root(self, initial=False):
        check_cancel(self.cancel)
        for p in (*reversed(self.path.parents), self.path):
            try:
                st = p.lstat()
            except OSError:
                _fail('E_ISO_FOLDER_MISSING' if initial else 'E_ISO_SOURCE_CHANGED', '.', 'source folder disappeared')
            _regular(st, '.', directory=True)
            ident = [st.st_dev, st.st_ino]
            key = str(p)
            if not initial and self._dirs.get(key) != ident:
                _fail('E_ISO_SOURCE_CHANGED', '.', 'source folder or its ancestor changed during the build')
            self._dirs[key] = ident

    def _scan(self, directory):
        if directory not in self._scans:
            names = {}
            with os.scandir(directory) as rows:
                for row in rows:
                    low = row.name.lower()
                    if low in names:
                        _fail('E_ISO_FOLDER_UNSAFE', low, 'case-colliding names in the source folder')
                    names[low] = row.name
                    if len(names) > MAX_ENTRIES:
                        _fail('E_ISO_FOLDER_UNSAFE', '.', 'too many entries in an original-file directory')
            self._scans[directory] = names
        return self._scans[directory]

    def _locate(self, rel):
        self._check_root()
        p = self.path
        parts = rel.split('/')
        for i, component in enumerate(parts):
            name = self._scan(p).get(component)
            if name is None:
                _fail('E_ISO_FOLDER_MISSING', rel, 'required original is missing')
            p = p / name
            st = p.lstat()
            directory = i < len(parts) - 1
            _regular(st, rel, directory=directory)
            if directory:
                key, ident = str(p), [st.st_dev, st.st_ino]
                if key in self._dirs and self._dirs[key] != ident:
                    _fail('E_ISO_SOURCE_CHANGED', rel, 'original-file directory changed during the build')
                self._dirs[key] = ident
        return p

    def _check_file(self, rel, fh=None):
        try:
            self._check_root()
            p = self._paths[rel]
            for parent in p.parents:
                if parent == self.path:
                    break
                st = parent.lstat()
                _regular(st, rel, directory=True)
                if self._dirs.get(str(parent)) != [st.st_dev, st.st_ino]:
                    _fail('E_ISO_SOURCE_CHANGED', rel, 'original-file directory changed during the build')
            st = p.lstat()
            _regular(st, rel)
            if _signature(st) != self._stats[rel] or (fh is not None and _signature(os.fstat(fh.fileno())) != self._stats[rel]):
                _fail('E_ISO_SOURCE_CHANGED', rel, 'original changed during the build')
        except OSError:
            _fail('E_ISO_SOURCE_CHANGED', rel, 'original disappeared or became unreadable during the build')

    def _open(self, rel):
        self._check_file(rel)
        fh = open_readonly(self._paths[rel])
        try:
            self._check_file(rel, fh)
        except BaseException:
            fh.close()
            raise
        return fh

    def _hash(self, rel, fh):
        h = hashlib.sha256()
        while True:
            self._check_file(rel, fh)
            data = fh.read(CHUNK)
            self._check_file(rel, fh)
            if not data:
                return h.hexdigest()
            h.update(data)

    def assert_unchanged(self):
        self._scans.clear()
        for rel in self._stats:
            self._check_file(rel)
            if self._locate(rel) != self._paths[rel]:
                _fail('E_ISO_SOURCE_CHANGED', rel, 'original path changed during the build')

    def identity(self):
        return {'source_kind': 'folder', 'source_reference': self.reference['id'],
                'source_digest': self.reference_digest, 'source_snapshot': digest(self._stats),
                'verified_files': len(self._stats), 'recomp_layout': self.recomp_layout}

    def check_destination(self, path):
        target, source = Path(path).resolve(), self.path.resolve()
        if target == source or source in target.parents or target in source.parents:
            _fail('E_ISO_FOLDER_UNSAFE', '.', 'output or cache overlaps the extracted source install')

    def get(self, path):
        return self.entries.get(safe_path(path))

    def files_under(self, prefix):
        p = safe_path(prefix) + '/'
        return sorted((e for k, e in self.entries.items() if k.startswith(p) and not e.is_dir), key=lambda e: e.path)

    def open_file(self, path):
        rel = safe_path(path)
        e = self.entries.get(rel)
        if e is None or e.is_dir:
            raise KeyError(path)
        fh = self._open(rel)
        try:
            if self._hash(rel, fh) != self.reference['files'][rel][1]:
                _fail('E_ISO_SOURCE_CHANGED', rel, 'original content changed during the build')
            fh.seek(0)
        except BaseException:
            fh.close()
            raise
        stream = _CheckedFile(self, rel, fh)
        self._handles.append(stream)
        return stream

    def read_file(self, path):
        with self.open_file(path) as fh:
            return fh.read()

    def copy_file(self, path, dst, chunk=CHUNK, hasher=None):
        self.check_destination(dst)
        with self.open_file(path) as src:
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            n = 0
            with open(dst, 'wb') as out:
                while data := src.read(chunk):
                    if hasher is not None:
                        hasher.update(data)
                    out.write(data)
                    n += len(data)
            return n

    def listing(self):
        return sorted((e.path, e.size, e.is_dir) for e in self.entries.values())

    def close(self):
        for fh in self._handles:
            fh.close()
        self._handles.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_exc):
        try:
            if exc_type is None:
                self.assert_unchanged()
        finally:
            self.close()
