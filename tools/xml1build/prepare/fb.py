"""xml1build.prepare.fb - XML1 .fb bundles (tools/fb_unpack.py's record layout, from bytes) and fb_unpack's rules.

A bundle is a sequence of records: name (0x80 bytes, NUL-padded, latin-1), type (0x40 bytes), u32 size, data.
fb_unpack.py unpacked every bundle of assetsfb.zip into one loose tree:
  * bundles in the order of sorted(glob('<assets>/**/*.fb')) ON WINDOWS, i.e. the paths sorted with '\\' as the
    separator (xml1_loose/_fb_manifest.json's key order proves it: 'maps/mansion/dr_mag2/*.fb' come before
    'maps/mansion/dr_mag/*.fb' there, because '\\' (0x5C) sorts after '2'; see bundle_order_key);
  * entry name = name.lstrip('/').lower(); the manifest lists every entry of every bundle as [name, type];
  * the FIRST bundle (in that order) that carries a name writes the file; a later copy with other bytes is a
    'conflicting duplicate' and is not written."""
from __future__ import annotations

import struct

HEADER = 0xC4                  # name 0x80 + type 0x40 + u32 size


class BundleError(ValueError):
    pass


def entries(data: bytes, where='bundle'):
    """yield (name, kind, data) for every record of a bundle (fb_unpack.entries on bytes)."""
    off = 0
    n = len(data)
    while off + HEADER <= n:
        name = data[off:off + 0x80].split(b'\0')[0].decode('latin-1')
        kind = data[off + 0x80:off + 0xC0].split(b'\0')[0].decode('latin-1')
        size, = struct.unpack_from('<I', data, off + 0xC0)
        body = data[off + HEADER:off + HEADER + size]
        if not name or len(body) != size:
            raise BundleError(f'{where}: bad entry at {off:#x}')
        yield name, kind, body
        off += HEADER + size


def entry_name(name: str) -> str:
    """the loose-tree path fb_unpack gave an entry: leading '/' stripped, lower case ('\\' read as '/', which is how
    Windows created the file)."""
    return name.replace('\\', '/').lstrip('/').lower()


def bundle_order_key(rel: str) -> str:
    """fb_unpack.py's bundle order: its glob ran on Windows, so it sorted 'packages\\generated\\maps\\...' - the
    relative path with '\\' separators. ('\\' is 0x5C, above '/', '.', the digits and upper case but below '_' and
    the lower case letters, so 'dr_mag/x.fb' < 'dr_mag2/y.fb' with '/' but not with '\\'.)"""
    return rel.replace('/', '\\')


def build(records) -> bytes:
    """a bundle from [(name, kind, data)] (synthetic tests)."""
    out = bytearray()
    for name, kind, data in records:
        nb, kb = name.encode('latin-1'), kind.encode('latin-1')
        if len(nb) >= 0x80 or len(kb) >= 0x40:
            raise BundleError(f'name/type too long: {name!r} / {kind!r}')
        out += nb.ljust(0x80, b'\0') + kb.ljust(0x40, b'\0') + struct.pack('<I', len(data)) + bytes(data)
    return bytes(out)
