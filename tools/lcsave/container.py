"""The LC save container (SPEC-new-save.md sections 1-2, revision 2.3): header, section table, sections made of
schema-described records. The schemas below ARE the format definition (the C++ port mirrors them, CONVERTER-PORT.md
section 3); `encode_record` / `decode_record` are the only code that interprets them.

Schema grammar - a record schema is a tuple of (field name, type) where type is one of
  u8 u16 u32 i32 u64 f32          scalars (little-endian)
  id                              u32 identity (keys.py grammar), validated per field's domain by the validator
  str                             u16 byte count + bytes (cp1252)
  f32x3                           three f32
  bytes:N                         N raw bytes
  tail                            every remaining byte of the record (only as the last field)
  list:<T>                        u32 count + count x T, where T is a scalar type, 'id', 'str' or a record name
  rec:<Name>                      one embedded record (u32 rsize + fields)
  packed:<Name>                   one embedded fixed element without rsize (the frozen element types)
A record is framed by u32 rsize (bytes that follow). Section payload = head record + the section's lists in order.
"""
from __future__ import annotations

import struct

from . import layout as L
from .keys import crc32

# ---- frozen element types (SPEC 1.4: never change; 'packed', no rsize)
PACKED = {
    'ENH': (('enhancement', 'id'), ('value', 'u32')),                                     # 8 bytes
    'TAL': (('talent', 'id'), ('rank', 'u8'), ('pending', 'u8'), ('cap', 'u8'), ('base', 'u8'), ('byte5', 'u8')),  # 9
    'OBJ': (('objective', 'id'), ('counter', 'u8'), ('flags', 'u8')),                       # 6
    'GRD': (('grade', 'id'), ('value', 'u8')),                                              # 5
    'DEFSTATE': (('item', 'id'), ('quantity', 'u32'), ('flag', 'u8')),                      # 9
}
# ---- records (framed by rsize; fields may be appended in a later section minor)
RECORDS = {
    'KEY': (('id', 'u32'), ('domain', 'u8'), ('key', 'str')),
    'INST': (('definition', 'id'), ('name_a', 'id'), ('name_b', 'id'), ('special', 'id'), ('location', 'u8'),
             ('prefixes', 'list:packed:ENH'), ('own', 'list:packed:ENH'), ('suffixes', 'list:packed:ENH')),
    'WITEM': (('handle', 'u32'), ('instance', 'rec:INST')),
    'PWR': (('button', 'u8'), ('name', 'str'), ('flags', 'u8')),          # flags: HERO minor 1 (SPEC 2.6)
    'HREC': (('hero', 'id'), ('traits', 'u16x16'), ('skill_points', 'u32'), ('trait_points', 'u32'), ('level', 'u16'),
             ('ai_level', 'u8'), ('ai_attack', 'u8'), ('talents', 'list:packed:TAL'), ('equipped', 'list:rec:INST'),
             ('vitals_valid', 'u8'), ('health', 'f32'), ('energy', 'f32'), ('player_seat', 'i32'), ('experience', 'u32'),
             ('ack_level', 'u16'), ('health_boosts', 'u16'), ('energy_boosts', 'u16'), ('levels_purchased', 'u8'),
             ('points_bought', 'u8'), ('respec_count', 'u8'), ('skirmish_boost', 'u8'), ('flags', 'u32'),
             ('powers', 'list:rec:PWR'), ('costume', 'id'), ('costumes_unlocked', 'list:id')),
    'RREC': (('owner', 'id'), ('traits', 'u16x16'), ('skill_points', 'u32'), ('trait_points', 'u32'), ('level', 'u16'),
             ('ai_level', 'u8'), ('ai_attack', 'u8'), ('talents', 'list:packed:TAL'), ('equipped', 'list:rec:INST'),
             ('vitals_valid', 'u8'), ('health', 'f32'), ('energy', 'f32'), ('player_seat', 'i32'), ('experience', 'u32'),
             ('ack_level', 'u16'), ('health_boosts', 'u16'), ('energy_boosts', 'u16'), ('levels_purchased', 'u8'),
             ('points_bought', 'u8'), ('respec_count', 'u8'), ('skirmish_boost', 'u8'), ('flags', 'u32')),
    'SEAT': (('seat', 'u8'), ('hero', 'id'), ('position', 'f32x3'), ('orientation', 'f32x3')),
    'SNAP': (('zone', 'id'), ('flags', 'u32'), ('seats', 'list:rec:SEAT'), ('objectives', 'list:packed:OBJ'),
             ('anchor_pos', 'f32x3'), ('anchor_orient', 'f32x3')),
    'CRS': (('course', 'id'), ('flags', 'u32'), ('tiers', 'bytes:3'), ('largest_hit', 'u32'), ('largest_hit_hero', 'id'),
            ('least_damage', 'u16'), ('least_damage_hero', 'id'), ('best_time', 'u16'), ('best_combo', 'u8'),
            ('most_health_packs', 'u8'), ('most_health_packs_hero', 'id'), ('most_energy_packs', 'u8'),
            ('most_energy_packs_hero', 'id'), ('most_defeats', 'u8'), ('most_defeats_hero', 'id')),
    'STATE': (('list', 'u8'), ('entity_tag', 'u32'), ('ordinal', 'u32'), ('placement_index', 'u32'), ('def_name', 'u32'),
              ('inst_name', 'u32'), ('flags_a', 'u32'), ('flags_b', 'u32'), ('position', 'f32x3'), ('payload_kind', 'u8'),
              ('payload', 'tail')),
    'FOG': (('encoding', 'u16'), ('width', 'u16'), ('height', 'u16'), ('data', 'tail')),
    'ZREC': (('zone', 'id'), ('identity_mode', 'u8'), ('content_hash', 'bytes:20'), ('time_stamp', 'f32'), ('flag', 'u8'),
             ('capture_flags', 'u32'), ('conversation', 'list:u32'), ('conversation_digest', 'bytes:32'),
             ('names', 'list:str'), ('states', 'list:rec:STATE'), ('fog', 'rec:FOG')),
    'VAR': (('name', 'str'), ('value', 'u32')),
    'SCORE': (('course', 'id'), ('party_a', 'list:id'), ('party_b', 'list:id'), ('score', 'u32')),
}
# ---- sections: (head schema, ((list name, element type), ...)); the lists follow the head in this order
SECTIONS = {
    'META': ((('saved_at', 'u64'), ('description', 'str'), ('origin', 'u8'), ('zone', 'id'), ('act', 'u16'),
              ('difficulty', 'u32'), ('play_time', 'f32'), ('writer', 'str'), ('slot', 'u8')),
             (('mods', 'str'),)),
    'KEYS': ((), (('keys', 'rec:KEY'),)),
    'GAME': ((('timer_threshold', 'f32'), ('timer_remaining', 'f32'), ('timer_after_add', 'f32'),
              ('timer_last_add', 'f32'), ('timer_script', 'str'), ('recall_cooldown', 'f32'), ('xtreme_charges', 'i32'),
              ('xtreme_pips', 'i32'), ('loading_name', 'str'), ('recall_zone', 'id'), ('recall_pos', 'f32x3'),
              ('act', 'u16'), ('value_608', 'u32'), ('difficulty', 'u32'), ('play_time', 'f32'), ('team_potion', 'u8'),
              ('counter_a', 'u8'), ('counter_b', 'u8'), ('flags', 'u32')),
             (('trivia', 'id'),)),
    'ITEM': ((('tech_bits', 'u32'), ('health_items', 'u32'), ('energy_items', 'u32')),
             (('def_state', 'packed:DEFSTATE'), ('key_counts', 'packed:DEFSTATE'), ('instances', 'rec:INST'),
              ('world', 'rec:WITEM'))),
    'HERO': ((), (('heroes', 'rec:HREC'),)),
    'ULCK': ((), (('unlocked', 'id'),)),
    'REST': ((('bank_valid', 'u8'),), (('records', 'rec:RREC'),)),
    'MISS': ((('stack_depth', 'u32'),), (('snapshots', 'rec:SNAP'),)),      # current first, then the stack frames
    'DNGR': ((), (('courses', 'rec:CRS'), ('grades', 'packed:GRD'))),
    'REVW': ((), (('unlocked', 'id'), ('seen', 'id'))),
    'ZONE': ((('newest_time', 'f32'), ('container_flag', 'u8')), (('records', 'rec:ZREC'),)),
    'SVAR': ((), (('zone_vars', 'rec:VAR'), ('game_vars', 'rec:VAR'))),
    'XTRC': ((), (('unlocked', 'id'),)),
    'PRFO': ((('options', 'u32'), ('player_name', 'str')), ()),
    'PRFS': ((), (('scores', 'rec:SCORE'),)),
    'PRFP': ((('highest_level', 'u16'), ('flags', 'u32')), (('characters', 'id'), ('review', 'id'))),
    'LGCY': ((('original_name', 'str'), ('original_size', 'u32'), ('sha1', 'bytes:20'), ('start_era', 'u32'),
              ('writer_era', 'u32'), ('def_count_byte', 'u32'), ('zone_records_dropped', 'u32'),
              ('world_items_dropped', 'u32'), ('zone_vars_dropped', 'u32'), ('other_dropped', 'u32')),
             (('notes', 'str'),)),
}
SECTION_FLAGS = {'META': L.SECTION_REQUIRED, 'KEYS': L.SECTION_KEEP, 'LGCY': L.SECTION_KEEP}
# the newest minor of each section this code reads and writes (SPEC 1.4); a section not listed is at 0.
# HERO 1: the power slot's flag byte appended to `PWR` (SPEC revision 2.3)
SECTION_MINOR = {'HERO': 1}
CAMPAIGN_SECTIONS = ('META', 'KEYS', 'GAME', 'ITEM', 'HERO', 'ULCK', 'REST', 'MISS', 'DNGR', 'REVW', 'ZONE', 'SVAR',
                     'XTRC', 'PRFO', 'PRFP', 'PRFS', 'LGCY')
PROFILE_SECTIONS = ('META', 'KEYS', 'PRFO', 'PRFP', 'PRFS', 'LGCY')
REQUIRED = {L.KIND_CAMPAIGN: [t for t in CAMPAIGN_SECTIONS if t not in ('KEYS', 'LGCY')],
            L.KIND_PROFILE: ('META', 'PRFO', 'PRFP', 'PRFS'),
            L.KIND_TRANSFER: [t for t in CAMPAIGN_SECTIONS if t not in ('KEYS', 'LGCY', 'PRFO', 'PRFP', 'PRFS')]}
# the list ceilings of SPEC 2.16 (reader ceilings, not format limits)
CEILINGS = {'u32': 1 << 20, 'id': 65536, 'str': 16384, 'rec:KEY': 65536, 'rec:INST': 4096, 'rec:WITEM': 16384,
            'rec:PWR': 4, 'rec:HREC': 1024, 'rec:RREC': 1024, 'rec:SEAT': 4, 'rec:SNAP': 17, 'rec:CRS': 65536,
            'rec:STATE': 65536, 'rec:ZREC': 256, 'rec:VAR': 4096, 'rec:SCORE': 1024, 'packed:ENH': 64,
            'packed:TAL': 256, 'packed:OBJ': 65536, 'packed:GRD': 256, 'packed:DEFSTATE': 65536}
MAX_FILE = 64 << 20
MAX_SECTIONS = 4096
_SCALAR = {'u8': '<B', 'u16': '<H', 'u32': '<I', 'i32': '<i', 'u64': '<Q', 'f32': '<f', 'id': '<I'}


class ContainerError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ record codec
def encode_value(typ, v):
    if typ in _SCALAR:
        return struct.pack(_SCALAR[typ], v)
    if typ == 'str':
        raw = v.encode('cp1252') if isinstance(v, str) else bytes(v)
        if len(raw) > 65535:
            raise ContainerError('str too long')
        return struct.pack('<H', len(raw)) + raw
    if typ == 'f32x3':
        return struct.pack('<3f', *v)
    if typ == 'u16x16':
        return struct.pack('<16H', *v)
    if typ.startswith('bytes:'):
        n = int(typ[6:])
        if len(v) != n:
            raise ContainerError(f'bytes:{n} given {len(v)}')
        return bytes(v)
    if typ == 'tail':
        return bytes(v)
    if typ.startswith('list:'):
        et = typ[5:]
        return struct.pack('<I', len(v)) + b''.join(encode_value(et, x) for x in v)
    if typ.startswith('rec:'):
        return encode_record(typ[4:], v)
    if typ.startswith('packed:'):
        return b''.join(encode_value(t, v[n]) for n, t in PACKED[typ[7:]])
    raise ContainerError(f'unknown type {typ}')


def encode_record(name, v):
    body = b''.join(encode_value(t, v[n]) for n, t in RECORDS[name])
    return struct.pack('<I', len(body)) + body


class _Dec:
    def __init__(self, buf, p, end):
        self.b, self.p, self.end = buf, p, end

    def need(self, n):
        if self.p + n > self.end:
            raise ContainerError(f'record truncated at {self.p:#x} (needs {n}, ends {self.end:#x})')


def decode_value(d, typ):
    if typ in _SCALAR:
        d.need(struct.calcsize(_SCALAR[typ]))
        v = struct.unpack_from(_SCALAR[typ], d.b, d.p)[0]; d.p += struct.calcsize(_SCALAR[typ])
        return v
    if typ == 'str':
        d.need(2)
        n = struct.unpack_from('<H', d.b, d.p)[0]; d.p += 2
        d.need(n)
        v = bytes(d.b[d.p:d.p + n]).decode('cp1252', 'replace'); d.p += n
        return v
    if typ == 'f32x3':
        d.need(12); v = list(struct.unpack_from('<3f', d.b, d.p)); d.p += 12
        return v
    if typ == 'u16x16':
        d.need(32); v = list(struct.unpack_from('<16H', d.b, d.p)); d.p += 32
        return v
    if typ.startswith('bytes:'):
        n = int(typ[6:]); d.need(n); v = bytes(d.b[d.p:d.p + n]); d.p += n
        return v
    if typ == 'tail':
        v = bytes(d.b[d.p:d.end]); d.p = d.end
        return v
    if typ.startswith('list:'):
        et = typ[5:]
        d.need(4)
        n = struct.unpack_from('<I', d.b, d.p)[0]; d.p += 4
        ceiling = CEILINGS.get(et, 65536)
        if n > ceiling:
            raise ContainerError(f'list of {et}: count {n} above the reader ceiling {ceiling}')
        return [decode_value(d, et) for _ in range(n)]
    if typ.startswith('rec:'):
        return decode_record(d, typ[4:])
    if typ.startswith('packed:'):
        return {n: decode_value(d, t) for n, t in PACKED[typ[7:]]}
    raise ContainerError(f'unknown type {typ}')


def decode_record(d, name):
    d.need(4)
    rsize = struct.unpack_from('<I', d.b, d.p)[0]; d.p += 4
    if d.p + rsize > d.end:
        raise ContainerError(f'record {name}: rsize {rsize} runs past its parent')
    sub = _Dec(d.b, d.p, d.p + rsize)
    out = {}
    for n, t in RECORDS[name]:
        if sub.p >= sub.end and t != 'tail' and not t.startswith('list'):
            break                      # a shorter (older) record: later fields absent (section minor rules)
        out[n] = decode_value(sub, t)
    out['_extra'] = bytes(sub.b[sub.p:sub.end]) if sub.p < sub.end else b''
    d.p = sub.end
    return out


# ------------------------------------------------------------------------------------------------ sections
def encode_section(tag, data):
    head, lists = SECTIONS[tag]
    body = b''.join(encode_value(t, data[n]) for n, t in head)
    out = struct.pack('<I', len(body)) + body
    for name, et in lists:
        out += encode_value('list:' + et, data[name])
    return out


def decode_section(tag, payload):
    head, lists = SECTIONS[tag]
    d = _Dec(payload, 0, len(payload))
    d.need(4)
    hsize = struct.unpack_from('<I', payload, 0)[0]; d.p = 4
    if 4 + hsize > len(payload):
        raise ContainerError(f'{tag}: head size {hsize} beyond the payload')
    hd = _Dec(payload, 4, 4 + hsize)
    out = {}
    for n, t in head:
        if hd.p >= hd.end:
            break
        out[n] = decode_value(hd, t)
    d.p = 4 + hsize
    for name, et in lists:
        if d.p >= d.end:
            out[name] = []             # an older writer without this list
            continue
        out[name] = decode_value(d, 'list:' + et)
    if d.p != d.end:
        out['_extra'] = bytes(payload[d.p:])
    return out


# ------------------------------------------------------------------------------------------------ file
def write_file(kind, sections, header):
    """sections: list of (tag, major, minor, flags, data dict) in file order; header: dict of the NEW_HEADER
    fields that are not computed here (writer_version, content_version, catalogue_revision, campaign_serial,
    save_sequence). -> bytes"""
    payloads = []
    for tag, major, minor, flags, data in sections:
        if isinstance(data, bytes):
            payloads.append((tag, major, minor, flags, data, 0))
        elif '_opaque_payload' in data:
            payloads.append((tag, major, minor, flags, data['_opaque_payload'], data['_opaque_records']))
        else:
            payloads.append((tag, major, minor, flags, encode_section(tag, data), len(data.get(next((n for n, _ in SECTIONS[tag][1]), '_'), [])) if SECTIONS[tag][1] else 0))
    table_off = L.NEW_HEADER_SIZE
    off = table_off + L.NEW_SECTION_ENTRY_SIZE * len(payloads)
    entries = bytearray()
    body = bytearray()
    for tag, major, minor, flags, pl, nrec in payloads:
        pad = (-len(pl)) % 4
        entries += L.write_struct(dict(tag=tag.encode('ascii'), major=major, minor=minor, flags=flags, offset=off,
                                       length=len(pl), records=nrec, crc=crc32(pl)), L.NEW_SECTION_ENTRY)
        body += pl + b'\0' * pad
        off += len(pl) + pad
    after = bytes(entries) + bytes(body)
    optional = header.get('optional_features', 0) | (L.OPTIONAL_KEYS_PRESENT if any(t == 'KEYS' for t, *_ in payloads) else 0)
    h = dict(magic=L.NEW_MAGIC, kind=kind, header_size_8=L.NEW_HEADER_SIZE // 8, major=1, minor=0, reserved_0e=0,
             required_features=0, optional_features=optional, file_length=L.NEW_HEADER_SIZE + len(after),
             section_count=len(payloads), section_table_offset=table_off, writer_version=header['writer_version'],
             content_version=header['content_version'], catalogue_revision=header['catalogue_revision'],
             campaign_serial=header['campaign_serial'], body_crc=crc32(after), save_sequence=header['save_sequence'],
             reserved_40=b'\0' * 0x40, legacy_length_guard=0, header_crc=0)
    hb = bytearray(L.write_struct(h, L.NEW_HEADER))
    hb[0x84:0x88] = struct.pack('<I', crc32(bytes(hb[:0x84])))
    return bytes(hb) + after


def read_file(buf, expect_kind=None):
    """validate (SPEC 1.3 steps 1-4) and decode -> dict(header, sections={tag: dict(entry, data)}, order=[tags])"""
    if len(buf) < L.NEW_HEADER_SIZE:
        raise ContainerError('file shorter than the header')
    h, _ = L.read_struct(buf, 0, L.NEW_HEADER)
    if h['magic'] != L.NEW_MAGIC:
        raise ContainerError('not an LC save (magic)')
    if crc32(bytes(buf[:0x84])) != h['header_crc']:
        raise ContainerError('header CRC mismatch (damaged)')
    if h['header_size_8'] * 8 != L.NEW_HEADER_SIZE or h['major'] != 1:
        raise ContainerError(f'format major {h["major"]} / header size not supported (needs a newer version)')
    if h['required_features']:
        raise ContainerError(f'required feature bits {h["required_features"]:#x} not implemented (needs a newer version)')
    if expect_kind is not None and h['kind'] != expect_kind:
        raise ContainerError(f'file kind {h["kind"]} is not the expected {expect_kind}')
    if h['file_length'] != len(buf) or len(buf) > MAX_FILE:
        raise ContainerError(f'file length field {h["file_length"]} does not match the file ({len(buf)})')
    if h['legacy_length_guard'] != 0:
        raise ContainerError('legacy length guard is not 0')
    if not 1 <= h['section_count'] <= MAX_SECTIONS:
        raise ContainerError('section count')
    to = h['section_table_offset']
    if to < L.NEW_HEADER_SIZE or to + h['section_count'] * L.NEW_SECTION_ENTRY_SIZE > len(buf):
        raise ContainerError('section table outside the file')
    if crc32(bytes(buf[to:])) != h['body_crc']:
        raise ContainerError('body CRC mismatch (damaged)')
    entries = []
    last_end = to + h['section_count'] * L.NEW_SECTION_ENTRY_SIZE
    seen = set()
    for i in range(h['section_count']):
        e, _ = L.read_struct(buf, to + i * L.NEW_SECTION_ENTRY_SIZE, L.NEW_SECTION_ENTRY)
        tag = e['tag'].decode('ascii', 'replace')
        if not all(32 < c < 127 for c in e['tag']):
            raise ContainerError('section tag is not printable ASCII')
        if tag in seen:
            raise ContainerError(f'section {tag} appears twice')
        seen.add(tag)
        if e['offset'] < last_end or e['offset'] + e['length'] > len(buf):
            raise ContainerError(f'section {tag}: not ascending / outside the file')
        pl = bytes(buf[e['offset']:e['offset'] + e['length']])
        if crc32(pl) != e['crc']:
            raise ContainerError(f'section {tag}: CRC mismatch (damaged)')
        last_end = e['offset'] + e['length']
        entries.append((tag, e, pl))
    sections = {}
    order = []
    for tag, e, pl in entries:
        if tag in SECTIONS:
            if e['major'] > 1:
                raise ContainerError(f'section {tag}: major {e["major"]} not supported (needs a newer version)')
            if e['minor'] > SECTION_MINOR.get(tag, 0) and not (e['flags'] & L.SECTION_EXT_DROPPABLE):
                raise ContainerError(f'section {tag}: minor {e["minor"]} not supported (needs a newer version)')
            data = decode_section(tag, pl)
            if data.get('_extra') and not (e['flags'] & L.SECTION_EXT_DROPPABLE):
                raise ContainerError(f'section {tag}: newer content that may not be dropped (needs a newer version)')
        elif e['flags'] & L.SECTION_REQUIRED:
            raise ContainerError(f'unknown section {tag} is REQUIRED (needs a newer version)')
        else:
            data = None
        sections[tag] = dict(entry=e, data=data, payload=pl)
        order.append(tag)
    for tag in REQUIRED.get(h['kind'], ()):
        if tag not in sections:
            raise ContainerError(f'section {tag} missing')
    return dict(header=h, sections=sections, order=order)
