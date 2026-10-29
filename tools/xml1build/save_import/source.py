"""Bounded, read-only extracted-folder and Xbox envelope reader.

Envelope: u32 payload length, 20 opaque signature bytes, exactly length bytes.
XBE writer 0x11fe50 / reader 0x120120. SHA-256 is provenance, not authentication.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import struct

from .errors import ImportRefusal

TITLE_ID = '4156001e'
CAPACITY = 0x2fc00
MAX_ENTRIES = 256
MAX_DEPTH = 4


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(value, *, directory=False):
    """Reject network/device paths and every existing reparse ancestor before resolving."""
    text = os.fspath(value)
    if text.startswith(('\\\\', '//')) or '://' in text or '\x00' in text:
        raise ImportRefusal('INPUT', 'Only local extracted folders are supported.')
    if '..' in text.replace('\\', '/').split('/'):
        raise ImportRefusal('INPUT', 'Choose a folder without parent traversals.')
    # Reject alternate data streams, but allow a Windows drive prefix.
    if ':' in re.sub(r'^[A-Za-z]:', '', text):
        raise ImportRefusal('INPUT', 'Alternate streams are not supported.')
    p = Path(os.path.abspath(text))
    for node in reversed((p, *p.parents)):
        try:
            st = node.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & 0x400:
            raise ImportRefusal('INPUT', 'Links and reparse points are not supported.')
    if directory and not p.is_dir():
        raise ImportRefusal('INPUT', 'The selected folder does not exist.')
    return p


def bounded_read(path, maximum):
    p = safe_path(path)
    st = p.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > maximum:
        raise ImportRefusal('DAMAGED', 'Input is not a bounded regular file.')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(p, flags)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    current = safe_path(p).stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    if len(data) > maximum or identity(st) != identity(before) or identity(before) != identity(after) or identity(after) != identity(current):
        raise ImportRefusal('CHANGED', 'Input changed while being read.')
    return data


def campaigns(folder):
    root = safe_path(folder, directory=True)
    chain = list(reversed((root, *root.parents)))
    for i, node in enumerate(chain):
        if node.name.lower() == 'tdata':
            raise ImportRefusal('INPUT', 'Select the extracted UDATA campaign folder.')
        if node.name.lower() == 'udata' and i + 1 < len(chain) and chain[i + 1].name.lower() != TITLE_ID:
            raise ImportRefusal('VERSION', 'This UDATA folder belongs to another title.')
    queue, found, count = [(root, 0)], [], 0
    while queue:
        current, depth = queue.pop(0)
        names = set()
        for p in sorted(current.iterdir(), key=lambda p: p.name.lower()):
            count += 1
            if count > MAX_ENTRIES:
                raise ImportRefusal('INPUT', 'Choose a smaller title or campaign folder.')
            name = p.name.lower()
            if name in names:
                raise ImportRefusal('INPUT', 'Case-insensitive filenames are ambiguous.')
            names.add(name)
            safe_path(p)
            if p.is_dir():
                if depth == MAX_DEPTH:
                    raise ImportRefusal('INPUT', 'The selected folder is too deeply nested.')
                # When selecting UDATA itself, never walk another title.
                if current.name.lower() != 'udata' or name == TITLE_ID:
                    queue.append((p, depth + 1))
            elif name == 'save.dat':
                if not p.is_file():
                    raise ImportRefusal('INPUT', 'save.dat must be a regular file.')
                found.append(p)
    if not found:
        raise ImportRefusal('INPUT', 'No save.dat was found in the selected folder.')
    return root, found


@dataclass(frozen=True)
class Source:
    root: Path
    path: Path
    sha256: str
    payload: bytes
    signature_status: str

    def recheck(self):
        if digest(bounded_read(self.path, CAPACITY + 24)) != self.sha256:
            raise ImportRefusal('CHANGED', 'The source campaign changed.')


def envelope(data, verifier=None):
    if len(data) < 24:
        raise ImportRefusal('DAMAGED', 'Xbox envelope is truncated.', offset=0)
    length = struct.unpack_from('<I', data)[0]
    if length > CAPACITY or len(data) != 24 + length:
        raise ImportRefusal('DAMAGED', 'Xbox payload length or EOF does not match.', offset=0)
    payload = data[24:]
    status = 'unavailable'
    if verifier is not None:
        checked = verifier(payload, data[4:24])
        if checked is False:
            raise ImportRefusal('DAMAGED', 'Xbox signature verification failed.')
        if checked is not True and checked is not None:
            raise ImportRefusal('VERSION', 'Invalid signature-verifier result.')
        status = 'verified' if checked else 'unavailable'
    return payload, status


def read_source(folder, verifier=None):
    root, paths = campaigns(folder)
    if len(paths) != 1:
        raise ImportRefusal('MULTIPLE', candidates=[str(p.parent.relative_to(root)).replace('\\', '/') for p in paths])
    data = bounded_read(paths[0], CAPACITY + 24)
    payload, status = envelope(data, verifier)
    return Source(root, paths[0], digest(data), payload, status)
