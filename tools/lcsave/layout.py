"""Table-driven byte layouts (defined once; the C++ port mirrors these tables, CONVERTER-PORT.md section 3).

A layout is a tuple of fields (name, type, count). Types: u8 u16 i16 u32 i32 u64 f32, 'bytes' (count raw bytes),
'cstr' (count bytes, NUL-padded text, decoded cp1252 up to the first NUL; the reader also keeps the raw bytes as
'<name>_raw' and the writer re-emits them while the text still matches, because some engine fields carry
uninitialised bytes after the NUL). count = 1 gives a scalar, more gives a
list. `read_struct` / `write_struct` are the only two functions that interpret a layout; `size_of` is its byte
size. Everything little-endian.

OLD_* tables: the fixed records of XMen2.exe's save (SPEC-old-save.md section 1; block offsets as there).
NEW_* tables: the fixed parts of the LC container (SPEC-new-save.md 1.1, 1.2); the variable records are
described by the field lists in container.py, which use the same type names.
"""
from __future__ import annotations

import struct

_FMT = {'u8': 'B', 'u16': 'H', 'i16': 'h', 'u32': 'I', 'i32': 'i', 'u64': 'Q', 'f32': 'f'}


def size_of(layout):
    n = 0
    for name, typ, count in layout:
        n += count if typ in ('bytes', 'cstr') else struct.calcsize(_FMT[typ]) * count
    return n


def read_struct(buf, off, layout):
    """-> (dict, next offset); raises ValueError when the buffer is too short"""
    out = {}
    end = off + size_of(layout)
    if off < 0 or end > len(buf):
        raise ValueError(f'struct needs {end - off} bytes at {off:#x}, buffer has {len(buf):#x}')
    p = off
    for name, typ, count in layout:
        if typ == 'bytes':
            out[name] = bytes(buf[p:p + count]); p += count
        elif typ == 'cstr':
            raw = bytes(buf[p:p + count]); p += count
            out[name] = raw.split(b'\0')[0].decode('cp1252', 'replace')
            out[name + '_raw'] = raw             # the bytes after the NUL are kept (uninitialised in some fields)
        else:
            fmt = '<' + _FMT[typ] * count
            vals = struct.unpack_from(fmt, buf, p); p += struct.calcsize(fmt)
            out[name] = vals[0] if count == 1 else list(vals)
    return out, p


def write_struct(values, layout):
    """dict -> bytes (every field of the layout must be present; a cstr is NUL-padded and must fit)"""
    out = bytearray()
    for name, typ, count in layout:
        v = values[name]
        if typ == 'bytes':
            if len(v) != count:
                raise ValueError(f'{name}: {len(v)} bytes, layout says {count}')
            out += v
        elif typ == 'cstr':
            raw = v.encode('cp1252') if isinstance(v, str) else bytes(v)
            if len(raw) >= count:
                raise ValueError(f'{name}: text of {len(raw)} bytes does not fit {count}')
            kept = values.get(name + '_raw')
            if kept is not None and len(kept) == count and kept.split(b'\0')[0] == raw:
                out += kept
            else:
                out += raw + b'\0' * (count - len(raw))
        else:
            fmt = '<' + _FMT[typ] * count
            out += struct.pack(fmt, *(v if count > 1 else [v]))
    return bytes(out)


# ------------------------------------------------------------------------------------------------ old save
OLD_PAYLOAD = 0x2fc00          # slot payload length (envelope u32 at file offset 0x80)
OLD_ENVELOPE = 0x84            # 0x80 description + u32 length
OLD_SLOT_SIZE = OLD_ENVELOPE + OLD_PAYLOAD
OLD_PROFILE_PAYLOAD = 0x228
OLD_TAG = 52                   # marker, 50 text bytes, marker
OLD_TAG_MARKER = 0x0a
OLD_DEF_STATE_PAIRS = 160
OLD_TALENT_ENTRIES = 19
OLD_UNLOCKED_SLOTS = 298
OLD_RESTORE_RECORDS = 22
OLD_SIDE_FRAMES = 2
OLD_DR_COURSES = 75
OLD_DR_GRADES = 8
OLD_DR_COURSE_BYTES = 26
OLD_ZONE_STRING_SLOTS = 0x800
OLD_ZONE_ARENA = 0x3800
OLD_ZONE_STATES = 768
OLD_ZONE_ORDINALS = 256
OLD_ZONE_DYNAMIC = 300
OLD_ZONE_SMART = 768
OLD_FOG_BYTES = 0x34c
OLD_ZONE_RECORD = 0x55e0
OLD_SCRIPT_ZONE_VARS = 32
OLD_SCRIPT_GAME_VARS = 100
OLD_HIGH_SCORES = 10
OLD_SECTION_TAGS = ('[SAVEGAMEBEGIN', '[CHARACTERSUNLOCKED]', '[CHARACTERSRESTORE]', '[DANGERROOM: COURSES]',
                    '[DANGERROOM: GRADES]', '[DANGERROOM: END]', '[MAP: ZONESTRINGS]', '[MAP: ZONES]',
                    '[MAP: MISSION STATE]', '[SAVEGAMEEND')

# items section head (old 1.4) up to the carried-item count
OLD_ITEM_HEAD = (
    ('def_count', 'u8', 1),
    ('def_state', 'u8', OLD_DEF_STATE_PAIRS * 2),      # pairs {quantity, flag} by definition index
    ('tech_bits', 'u32', 1),
    ('health_items', 'u32', 1),
    ('energy_items', 'u32', 1),
    ('key_counts', 'u32', 6),                          # KEY1-3, KEYCARD1-3 by definition name
)
# item instance fixed head (old 1.5); then three lists of {u16 record, u32 value} with u32 counts
OLD_INSTANCE_HEAD = (
    ('definition', 'u8', 1),
    ('name_a', 'u8', 1),         # instance+0x2c, 0xff = none
    ('name_b', 'u8', 1),         # instance+0x2d, 0xff = none
    ('special', 'u8', 1),        # instance+0x2f, 0xff = none
    ('location', 'u8', 1),       # instance+0x2e
)
OLD_ENH_ELEMENT = (('record', 'u16', 1), ('value', 'u32', 1))
# CAttributes scalars (old 1.6 a), 0x18 bytes
OLD_ATTR_SCALARS = (
    ('trait_base', 'u8', 4), ('trait_pending', 'u8', 4), ('trait_bonus', 'u8', 4), ('trait_bonus2', 'u8', 4),
    ('skill_points', 'u16', 1), ('trait_points', 'u16', 1), ('level', 'u8', 1), ('ai_level', 'u8', 1),
    ('ai_attack', 'u8', 1), ('pad17', 'u8', 1),
)
# talent heap entry (old 1.6 b), 8 bytes
OLD_TALENT_ENTRY = (('id', 'u16', 1), ('rank_bits', 'u8', 1), ('pending_cap_bits', 'u8', 1), ('base_bits', 'u8', 1),
                    ('byte5', 'u8', 1), ('pad6', 'u16', 1))
OLD_TALENT_HEAP_TAIL = (('bitmap', 'u32', 1), ('count', 'u32', 1))
# equipment tail (old 1.6 c), 0x1c bytes after the equipped instances
OLD_EQUIP_TAIL = (
    ('health', 'f32', 1), ('energy', 'f32', 1), ('player_seat', 'i32', 1), ('vitals_valid', 'u8', 1),
    ('pad0d', 'u8', 3), ('experience', 'u32', 1), ('ack_level', 'u8', 1), ('health_boosts', 'u8', 1),
    ('energy_boosts', 'u8', 1), ('levels_purchased', 'u8', 1), ('points_bought', 'u8', 1), ('respec_count', 'u8', 1),
    ('skirmish_boost', 'u8', 1), ('flags', 'u8', 1),
)
# powers (old 1.6 d) and costume (e)
# four slots of 21 bytes: a NUL-terminated fight-move name in 20 bytes (at most 19, the engine's cap 0x4b84d8) and one
# flag byte whose bit 0 is the slot's "usable" flag (CStats+0xc4 + 0x15 n + 0x14; get 0x4b83b0, set 0x4b83e0); then a pad
OLD_POWERS = (('power', 'cstr', 20), ('power_flags', 'u8', 1)) * 4 + (('pad54', 'u8', 1),)   # handled as lists by oldsave
OLD_POWER_SLOT = 21
OLD_POWER_NAME = 20
POWER_USABLE = 1          # bit 0 of the flag byte; also the value of a slot the new format does not list (SPEC 2.6)
OLD_COSTUME = (('costume', 'u8', 1), ('costume_mask', 'u32', 1))
# game block (old 1.8), 0xdc bytes
OLD_GAME_BLOCK = (
    ('timer_threshold', 'f32', 1), ('timer_remaining', 'f32', 1), ('timer_after_add', 'f32', 1),
    ('timer_last_add', 'f32', 1), ('timer_script', 'cstr', 0x40), ('recall_cooldown', 'f32', 1),
    ('xtreme_charges', 'i16', 1), ('xtreme_pips', 'i16', 1), ('loading_name', 'cstr', 0x20),
    ('recall_zone', 'cstr', 0x20), ('recall_pos', 'f32', 3), ('act', 'u8', 1), ('unused_a5', 'bytes', 6),
    ('pad_ab', 'u8', 1), ('trivia', 'u32', 8), ('value_608', 'u32', 1), ('difficulty', 'u32', 1),
    ('play_time', 'f32', 1), ('flags_d8', 'u8', 1), ('flags_d9', 'u8', 1), ('flags_da', 'u8', 1), ('pad_db', 'u8', 1),
)
# mission snapshot (old 1.9), 0x26c bytes
OLD_SNAPSHOT = (
    ('zone', 'cstr', 0x40), ('seat_pose', 'f32', 24), ('pad_a0', 'u32', 1), ('seat_name0', 'cstr', 0x20),
    ('seat_name1', 'cstr', 0x20), ('seat_name2', 'cstr', 0x20), ('seat_name3', 'cstr', 0x20), ('pad_124', 'u8', 1),
    ('objectives', 'u8', 300), ('objective_301', 'u8', 1), ('pad_252', 'u16', 1), ('anchor_pos', 'f32', 3),
    ('anchor_orient', 'f32', 3),
)
OLD_SIDE_TAIL = (('pad_4d8', 'u32', 1), ('count', 'u32', 1))
# Danger Room course record (old 1.10, unknowns report U5), 26 bytes
OLD_DR_COURSE = (
    ('flags', 'u8', 1), ('tier0', 'u8', 1), ('tier1', 'u8', 1), ('tier2', 'u8', 1), ('largest_hit', 'u32', 1),
    ('largest_hit_hero', 'u16', 1), ('least_damage', 'u16', 1), ('least_damage_hero', 'u16', 1), ('best_time', 'u16', 1),
    ('best_combo', 'u8', 1), ('most_health_packs', 'u8', 1), ('most_health_packs_hero', 'u16', 1),
    ('most_energy_packs', 'u8', 1), ('most_energy_packs_hero', 'u16', 1), ('most_defeats', 'u8', 1),
    ('most_defeats_hero', 'u16', 1),
)
OLD_REVIEW = (('unlocked', 'u32', 16), ('seen', 'u32', 16))           # 5 x 3 dwords used + 1 pad dword each
# zone string table (old 1.12), 0x5808 bytes
OLD_ZONE_STRINGS = (('generation', 'u32', 1), ('offsets', 'u32', OLD_ZONE_STRING_SLOTS), ('used', 'u32', 1),
                    ('arena', 'bytes', OLD_ZONE_ARENA))
# entity state record (old 1.13), 0x18 bytes
OLD_STATE_RECORD = (('def_name', 'u32', 1), ('inst_name', 'u32', 1), ('payload', 'bytes', 8), ('flags_a', 'u8', 1),
                    ('flags_b', 'u8', 1), ('position', 'i16', 3))
# zone record (old 1.13), 0x55e0 bytes; the 768 state records are read separately
OLD_ZONE_RECORD_TAIL = (
    ('pad_4804', 'u32', 1), ('state_count', 'u32', 1), ('ordinal_map', 'u16', OLD_ZONE_ORDINALS), ('pad_4a0c', 'u32', 1),
    ('dynamic', 'u16', OLD_ZONE_DYNAMIC), ('pad_4c68', 'u32', 1), ('dynamic_count', 'u32', 1),
    ('smart', 'u16', OLD_ZONE_SMART), ('pad_5270', 'u32', 1), ('smart_count', 'u32', 1), ('fog', 'bytes', OLD_FOG_BYTES),
    ('conversation', 'u32', 5), ('time_stamp', 'f32', 1), ('flag', 'u8', 1), ('pad_55dd', 'u8', 3),
)
# profile (old 1.15), 0x228 bytes
OLD_HIGH_SCORE = (('course', 'u8', 1), ('pad1', 'u8', 3), ('party_a', 'u16', 6), ('count_a', 'u32', 1),
                  ('party_b', 'u16', 6), ('count_b', 'u32', 1), ('score', 'u32', 1))
OLD_PROFILE_HEAD = (('options', 'u8', 3), ('player_name', 'cstr', 0x21))
OLD_PROFILE_TAIL = (('pad_1b4', 'u32', 1), ('score_count', 'u32', 1), ('char_unlock', 'u32', 10),
                    ('review', 'u32', 15), ('pad_220', 'u32', 1), ('highest_level', 'u8', 1), ('flags_229', 'u8', 1),
                    ('pad_22a', 'u8', 2))
OLD_SCRIPT_VAR = (('name', 'cstr', 12), ('value_be', 'bytes', 4))      # value: 4 big-endian bytes

# ------------------------------------------------------------------------------------------------ new container
NEW_MAGIC = b'LCSAVE1\0'
NEW_HEADER_SIZE = 0x88
NEW_SECTION_ENTRY_SIZE = 24
NEW_HEADER = (
    ('magic', 'bytes', 8), ('kind', 'u8', 1), ('header_size_8', 'u8', 1), ('major', 'u16', 1), ('minor', 'u16', 1),
    ('reserved_0e', 'u16', 1), ('required_features', 'u32', 1), ('optional_features', 'u32', 1), ('file_length', 'u32', 1),
    ('section_count', 'u32', 1), ('section_table_offset', 'u32', 1), ('writer_version', 'u32', 1),
    ('content_version', 'u32', 1), ('catalogue_revision', 'u32', 1), ('campaign_serial', 'u64', 1), ('body_crc', 'u32', 1),
    ('save_sequence', 'u32', 1), ('reserved_40', 'bytes', 0x40), ('legacy_length_guard', 'u32', 1), ('header_crc', 'u32', 1),
)
NEW_SECTION_ENTRY = (('tag', 'bytes', 4), ('major', 'u8', 1), ('minor', 'u8', 1), ('flags', 'u16', 1), ('offset', 'u32', 1),
                     ('length', 'u32', 1), ('records', 'u32', 1), ('crc', 'u32', 1))
SECTION_REQUIRED = 1
SECTION_KEEP = 2
SECTION_EXT_DROPPABLE = 8
KIND_CAMPAIGN, KIND_PROFILE, KIND_TRANSFER = 1, 2, 3
OPTIONAL_KEYS_PRESENT = 1
assert size_of(NEW_HEADER) == NEW_HEADER_SIZE
assert size_of(NEW_SECTION_ENTRY) == NEW_SECTION_ENTRY_SIZE
assert size_of(OLD_GAME_BLOCK) == 0xdc and size_of(OLD_SNAPSHOT) == 0x26c and size_of(OLD_ATTR_SCALARS) == 0x18
assert size_of(OLD_EQUIP_TAIL) == 0x1c and size_of(OLD_DR_COURSE) == 26 and size_of(OLD_STATE_RECORD) == 0x18
assert size_of(OLD_ZONE_STRINGS) == 0x5808 and 4 + 768 * 0x18 + size_of(OLD_ZONE_RECORD_TAIL) == OLD_ZONE_RECORD
assert size_of(OLD_PROFILE_HEAD) + 10 * size_of(OLD_HIGH_SCORE) + size_of(OLD_PROFILE_TAIL) == OLD_PROFILE_PAYLOAD
