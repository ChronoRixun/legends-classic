"""Identity primitives (SPEC-new-save 3.1-3.3): domains, canonical key bytes, the key hash, the id grammar, CRC-32.

Defined once here and mirrored byte for byte by the C++ port (CONVERTER-PORT.md section 2); tests/unit/
test_lcsave_keys.py pins the vectors.
"""
from __future__ import annotations

import hashlib
import zlib

# domain number -> tag (SPEC-new-save 3.2; the number is the high byte of a catalogue id)
DOMAINS = {
    1: 'STAT', 2: 'ITEM', 3: 'ENHC', 4: 'NAMA', 5: 'NAMB', 6: 'TRIT', 7: 'TALN', 8: 'COST', 9: 'MSNF', 10: 'OBJV',
    11: 'DRCS', 12: 'DRGR', 13: 'REVW', 14: 'XPNT', 15: 'ZONE', 16: 'TRIV',
}
DOMAIN_NUMBER = {tag: n for n, tag in DOMAINS.items()}
KEYREF_BIT = 0x80000000
SERIAL_MAX = 0xFFFFFF


def canonical_field(text):
    """one key field: ASCII letters lower-cased, '%' -> '%25', '/' -> '%2f'; bytes as the engine has them (cp1252)"""
    if isinstance(text, str):
        raw = text.encode('cp1252', 'replace')
    else:
        raw = bytes(text)
    out = bytearray()
    for b in raw:
        if 65 <= b <= 90:
            out.append(b + 32)
        elif b == 0x25:
            out += b'%25'
        elif b == 0x2f:
            out += b'%2f'
        else:
            out.append(b)
    return bytes(out)


def canonical_key(*fields):
    """the canonical key bytes of a list of fields: fields joined with '/'"""
    return b'/'.join(canonical_field(f) for f in fields)


def key_hash(*fields):
    """SHA-256 of the canonical key bytes, as 64 lower-case hex characters (this is what the repository stores)"""
    return hashlib.sha256(canonical_key(*fields)).hexdigest()


def make_id(domain, serial):
    """catalogue id: domain << 24 | serial (domain 1..127, serial 1..0xFFFFFF)"""
    if not 1 <= domain <= 127 or not 1 <= serial <= SERIAL_MAX:
        raise ValueError(f'bad id parts domain={domain} serial={serial}')
    return (domain << 24) | serial


def make_keyref(index):
    """key reference: bit 31 | 0-based index into the file's KEYS list"""
    if not 0 <= index < KEYREF_BIT:
        raise ValueError('bad key reference index')
    return KEYREF_BIT | index


def id_domain(value):
    """the domain number of a catalogue id (0 for 0 and for key references)"""
    if value == 0 or value & KEYREF_BIT:
        return 0
    return (value >> 24) & 0x7f


def id_serial(value):
    return value & SERIAL_MAX


def is_keyref(value):
    return bool(value & KEYREF_BIT)


def crc32(data, start=0):
    """CRC-32 (IEEE 802.3, the zlib polynomial) of data; `start` continues an earlier value"""
    return zlib.crc32(data, start) & 0xffffffff


def sha1_hex(data):
    return hashlib.sha1(data).hexdigest()


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()
