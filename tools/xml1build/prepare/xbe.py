"""xml1build.prepare.xbe - the XBE header and certificate of default.xbe (BUILDER_DESIGN.md 1.1, identification).

XBE image header (offsets from the file start): 'XBEH' magic (0x000), base address (0x104), size of headers (0x108),
size of image (0x10C), size of image header (0x110), time/date stamp (0x114), certificate address (0x118, a
virtual address: file offset = address - base).
Certificate: size (0x00), time/date (0x04), title ID (0x08), title name (0x0C, 40 UTF-16LE characters), alternate
title IDs (0x5C, 16 x u32), allowed media (0x9C), game region (0xA0), game ratings (0xA4), disk number (0xA8),
version (0xAC).

X-Men Legends (Owen's World dump): title 'X-Men Legends', title ID 0x4156001E ('AV' = Activision, game 0x1E),
version 1, region 7 (North America + Japan + rest of world)."""
from __future__ import annotations

import struct

from . import PrepareError

XML1_TITLE_ID = 0x4156001E
XBE_MAGIC = b'XBEH'


def parse(data: bytes) -> dict:
    """{'title_id', 'title_id_hex', 'title', 'version', 'region', 'disk', 'timestamp', 'alt_title_ids',
    'publisher'}; raises PrepareError(E_ISO_WRONG_GAME) when it is no XBE."""
    if len(data) < 0x178 or data[:4] != XBE_MAGIC:
        raise PrepareError('E_ISO_WRONG_GAME', 'default.xbe is not an Xbox executable (no XBEH header)',
                           'the image is damaged or not an Xbox game', {'xbe': 'bad header'})
    base, = struct.unpack_from('<I', data, 0x104)
    stamp, cert_va = struct.unpack_from('<II', data, 0x114)
    off = cert_va - base
    if off < 0 or off + 0xB0 > len(data):
        raise PrepareError('E_ISO_WRONG_GAME', f'default.xbe: certificate address {cert_va:#x} outside the file',
                           'the image is damaged', {'xbe': 'bad certificate'})
    c = data[off:off + 0xB0]
    title_id, = struct.unpack_from('<I', c, 0x08)
    title = c[0x0C:0x0C + 80].decode('utf-16-le', errors='replace').split('\0', 1)[0]
    alt = [x for x in struct.unpack_from('<16I', c, 0x5C) if x]
    media, region, ratings, disk, version = struct.unpack_from('<5I', c, 0x9C)
    pub = bytes([(title_id >> 24) & 0xFF, (title_id >> 16) & 0xFF])
    return {'title_id': title_id, 'title_id_hex': f'0x{title_id:08X}', 'title': title, 'version': version,
            'region': region, 'disk': disk, 'timestamp': stamp, 'alt_title_ids': [f'0x{x:08X}' for x in alt],
            'publisher': pub.decode('latin-1') if all(0x20 <= b < 0x7F for b in pub) else pub.hex(),
            'allowed_media': media, 'ratings': ratings}


def check_xml1(info: dict):
    """raise E_ISO_WRONG_GAME unless this is X-Men Legends (title ID 0x4156001E)."""
    if info['title_id'] != XML1_TITLE_ID:
        raise PrepareError('E_ISO_WRONG_GAME', f'this disc is "{info["title"]}" (title ID {info["title_id_hex"]}), '
                           f'not X-Men Legends (0x{XML1_TITLE_ID:08X})',
                           'choose your X-Men Legends (Xbox) disc image',
                           {'title_id': info['title_id_hex'], 'title': info['title']})
