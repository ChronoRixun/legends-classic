"""Invented saves, encoded from the a30ec29 recomp wire definitions.

No player data or recomp/game source is included. Integers are explicitly LE;
the shared native portions use the existing synthetic retail fixture.
"""
import struct

from test_xml1_save_import import char, marker, retail, save


def selections(rows=()):
    out = struct.pack('<H', len(rows))
    for name, powers in rows:
        for text in (name, *powers):
            raw = text.encode('ascii')
            assert len(raw) < 20
            out += raw + bytes(20 - len(raw))
    return out


def identities(rows=()):
    out = b'TLID' + bytes((1, 0, len(rows), 0))
    for tid, name, filename, selector in rows:
        strings = [s.encode('ascii') for s in (name, filename, selector)]
        out += bytes((tid, *map(len, strings))) + b''.join(strings)
    return out


def character(version, *, talents=(), vitality=(0, 0), auto_equip=0, **kwargs):
    # The native prefix stays 44 bytes in every version.
    raw = char(**kwargs)[:44]
    if version >= 5:
        raw += bytes(vitality)
    if version >= 6:
        raw += bytes((auto_equip,))
    raw += bytes((len(talents),))
    width, bits = (3, 4) if version == 1 else (4, 6)
    for tid, *values in talents:
        packed = sum(value << (i * bits) for i, value in enumerate(values))
        raw += bytes((tid,)) + packed.to_bytes(width, 'little')
    equipment = kwargs.get('equipment', ())
    return raw + bytes((len(equipment),)) + bytes(equipment)


def difficulty(version, live=2, retained=0, acts=(1, 1)):
    out = b'XML1DIF\0' + struct.pack('<Iii', version, live, retained)
    if version >= 2:
        out += bytes(acts)
    if version >= 3:
        out += (b'none\0' + bytes(27) + struct.pack('<3fB', 0, 0, 0, 1)) * 2
    if version >= 4:
        out += struct.pack('<ff', 0, 0)
    if version >= 5:
        out += bytes((2, 3, 4, 5))
    return out


def stash(live=(), snapshot=(), valid=0):
    body = struct.pack('<I', valid)
    for rows in (live, snapshot):
        body += struct.pack('<I', len(rows))
        for name, quantity in rows:
            name = name.encode('ascii')
            body += struct.pack('<II', len(name), quantity) + name
    return b'XML1STSH' + struct.pack('<II', 1, 16 + len(body)) + body


def recomp_save(version=6, *, ids=(1, 2), records=None, power_rows=(), talent_rows=(),
                adjuncts=b'', unlocked=None, party=('hero_a', 'hero_b'), snapshots=48):
    original, base = save(talents=False)
    native = original[24:]
    parts, offsets = [], {}
    def add(name, data):
        offsets[name] = sum(map(len, parts))
        parts.append(data)
    add('prefix', native[:base['hero0']])
    extra = b''
    if version >= 3:
        extra = selections(power_rows)
    if version >= 4:
        tlid = identities(talent_rows)
        extra = struct.pack('<HH', len(extra), len(tlid)) + extra + tlid
    bitmap = bytearray(32)
    for ident in ids:
        bitmap[ident // 8] |= 1 << (ident % 8)
    add('header', b'XML1CHR\0' + struct.pack('<HHHH', version, 48 + len(extra), snapshots, 0) + bytes(bitmap) + extra)
    records = records or {}
    for ident in sorted(ids):
        add('hero' + str(ident), character(version, **records.get(ident, {})))
    add('unlock_marker', marker(retail.MARKERS['unlocked']))
    unlocked = list(ids) if unlocked is None else unlocked
    add('unlock', bytes(unlocked) + bytes(256 - len(unlocked)) + struct.pack('<I', len(unlocked)))
    add('restore_marker', marker(retail.MARKERS['restore']))
    add('restore_valid', b'\0')
    for i in range(snapshots):
        add('restore' + str(i), character(version))
    add('native_tail', native[base['inventory']:base['variables']])
    add('adjuncts', adjuncts)
    add('variables', native[base['variables']:])
    payload = bytearray(b''.join(parts))
    # Replace the mission's party with caller-supplied invented names.
    mission_offset = offsets['native_tail'] + base['mission'] - base['inventory']
    offsets['mission'] = mission_offset
    for i in range(4):
        name = party[i].encode('ascii') if i < len(party) else b''
        payload[mission_offset + 0xa4 + i * 32:mission_offset + 0xc4 + i * 32] = name + bytes(32 - len(name))
    return struct.pack('<I', len(payload)) + bytes(20) + payload, offsets
