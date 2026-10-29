"""Confirmed retail wire layout from SAVE-IMPORT-DESIGN section 3.

Unresolved spans remain raw bytes. No target-native structures are used here.
Recomp extensions are recognized only at their documented subsystem boundary.
"""
from __future__ import annotations

import math
import re
import struct

from .errors import ImportRefusal
from .source import CAPACITY

HEROES = ('default', 'beast', 'colossus', 'cyclops', 'frost', 'gambit', 'iceman', 'jubilee',
          'magma', 'nightcrawler', 'phoenix', 'profxastral', 'psylocke', 'rogue', 'storm', 'wolverine')
MARKERS = {'courses': '[DANGERROOM: COURSES]', 'grades': '[DANGERROOM: GRADES]',
           'credits': '[DANGERROOM: CREDITS]', 'unlocked': '[CHARACTERSUNLOCKED]',
           'restore': '[CHARACTERSRESTORE]', 'strings': '[MAP: ZONESTRINGS]',
           'zones': '[MAP: ZONES]', 'mission': '[MAP: MISSION STATE]'}
EXTENSIONS = (b'XML1CHR\0', b'XML1PRG\0', b'XML1DIF\0', b'XML1STSH')


def cstring(raw, field, offset=0, *, display=False):
    if b'\0' not in raw:
        raise ImportRefusal('DAMAGED', 'Unterminated ' + field, offset=offset)
    text = raw.split(b'\0', 1)[0]
    if any(b < 32 or b == 127 or (b > 126 and not display) for b in text):
        raise ImportRefusal('DAMAGED', 'Invalid identifier in ' + field, offset=offset)
    try:
        return text.decode('cp1252' if display else 'ascii')
    except UnicodeError as e:
        raise ImportRefusal('DAMAGED', 'Invalid display text encoding.', offset=offset) from e


class Cursor:
    def __init__(self, data):
        self.data, self.offset, self.boundaries = data, 0, {}

    def take(self, count, field):
        start = self.offset
        if count < 0 or count > len(self.data) - start:
            raise ImportRefusal('DAMAGED', 'Truncated ' + field, offset=start)
        self.offset += count
        return self.data[start:self.offset]

    def unpack(self, fmt, field):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt), field))

    def boundary(self, name):
        self.boundaries[name] = self.offset
        for magic in EXTENSIONS:
            if self.data[self.offset:self.offset + len(magic)] == magic:
                width = 2 if magic == b'XML1CHR\0' else 4
                version = int.from_bytes(self.data[self.offset + 8:self.offset + 8 + width], 'little') if len(self.data) >= self.offset + 8 + width else None
                raise ImportRefusal('RECOMP_VERSION', extension=magic.rstrip(b'\0').decode('ascii'),
                                    version=version, offset=self.offset)

    def marker(self, name=None):
        self.boundary(name or 'begin')
        start = self.offset
        raw = self.take(52, 'marker')
        if raw[0] != 10 or raw[51] != 10:
            raise ImportRefusal('DAMAGED', 'Marker newline boundaries do not match.', offset=start)
        text = cstring(raw[1:51], 'marker', start, display=name not in MARKERS)
        if name in MARKERS and text != MARKERS[name]:
            raise ImportRefusal('DAMAGED', 'Unexpected subsystem marker.', offset=start, expected=MARKERS[name])
        return text


def character(c, *, max_talents=64, max_equipped=3):
    offset = c.offset
    raw = c.take(44, 'character scalars')
    health, energy, seat = struct.unpack_from('<ffi', raw)
    if not math.isfinite(health) or not math.isfinite(energy) or seat not in (-1, 0, 1, 2, 3):
        raise ImportRefusal('DAMAGED', 'Invalid character vitals or control seat.', offset=offset)
    count, = c.unpack('<B', 'talent count')
    if count > max_talents:
        raise ImportRefusal('DAMAGED', 'Talent count exceeds this source profile.', offset=c.offset - 1)
    talents, ids = [], set()
    for _ in range(count):
        native, packed = c.unpack('<B3s', 'talent')
        if native in ids:
            raise ImportRefusal('DAMAGED', 'Duplicate native talent ID.', offset=c.offset - 4)
        ids.add(native)
        bits = int.from_bytes(packed, 'little')
        talents.append(dict(native_id=native, rank=bits & 15, pending=(bits >> 4) & 15,
                            bonus=(bits >> 8) & 15, limit=(bits >> 12) & 15,
                            baseline=(bits >> 16) & 15, padding=(bits >> 20) & 15))
    equipped, = c.unpack('<B', 'equipped count')
    if equipped > max_equipped:
        raise ImportRefusal('DAMAGED', 'Equipment count exceeds this source profile.', offset=c.offset - 1)
    return dict(offset=offset, raw=raw, health=health, energy=energy, seat=seat, validity=raw[12],
                experience=struct.unpack_from('<I', raw, 16)[0], level=raw[20], ack_level=raw[21],
                skin=raw[22], base=list(raw[23:27]), pending=list(raw[27:31]), bonus=list(raw[31:35]),
                bonus2=list(raw[35:39]), trait_points=raw[39], skill_points=raw[40],
                ai_level=raw[41] & 15, ai_power=raw[41] >> 4, talents=talents,
                equipped=list(c.take(equipped, 'equipped IDs')))


def objective_counter(word):
    """Exact XBE 0x84927: movsx word; shl AX,4; sar EAX,4.

    Bit 15 supplies the high sign extension; bit 11 alone is NOT a sign bit.
    """
    return (word & 0xfff) - (0x1000 if word & 0x8000 else 0)


def snapshot(raw):
    zone = cstring(raw[:64], 'mission zone')
    if zone and (not re.fullmatch(r'[A-Za-z0-9_/-]+', zone) or '..' in zone.split('/')):
        raise ImportRefusal('DAMAGED', 'Invalid mission zone identifier.')
    poses = struct.unpack_from('<24f', raw, 0x40)
    anchor = struct.unpack_from('<6f', raw, 0x168)
    if not all(math.isfinite(x) for x in (*poses, *anchor)):
        raise ImportRefusal('DAMAGED', 'Nonfinite mission pose.')
    party = [cstring(raw[0xa4 + i * 32:0xc4 + i * 32], 'party name') for i in range(4)]
    objectives = []
    for i in range(16):
        word, flags, extra = struct.unpack_from('<HBB', raw, 0x126 + i * 4)
        objectives.append(dict(counter=objective_counter(word), enabled=bool(flags & 1), complete=bool(flags & 2),
                               required=bool(flags & 4), hidden=bool(flags & 8), raw_word=word,
                               unknown=bytes((flags & 0xf0, extra))))
    return dict(raw=raw, zone=zone, party=party, poses=poses, anchor=anchor,
                mission_id=raw[0x180], objectives=objectives)


def decode(payload, *, hero_names=HEROES, max_talents=64, max_equipped=3):
    if not 0 < len(payload) <= CAPACITY or len(hero_names) != 16 or len(set(hero_names)) != 16:
        raise ImportRefusal('VERSION', 'Unsupported retail payload or roster profile.')
    c = Cursor(payload)
    begin = c.marker()
    if not begin.startswith('[SAVEGAMEBEGIN: ') or not begin.endswith(']'):
        raise ImportRefusal('DAMAGED', 'Invalid begin marker.', offset=0)
    play_time, = c.unpack('<f', 'play time')
    if not math.isfinite(play_time) or play_time < 0:
        raise ImportRefusal('DAMAGED', 'Invalid accumulated play time.', offset=0x34)
    game = c.take(0x88, 'live game record')
    retained_game = c.take(0x88, 'retained game record')
    side = c.take(0x310, 'side mission storage')
    depth = struct.unpack_from('<I', side, 0x30c)[0]
    if depth > 2:
        raise ImportRefusal('DAMAGED', 'Side mission stack exceeds two frames.', offset=0x454)
    c.marker('courses')
    courses = c.take(200, 'course positions')
    c.marker('grades')
    grades = c.take(8, 'grade positions')
    c.marker('credits')
    credits, = c.unpack('<H', 'Danger Room credits')
    c.boundary('characters')
    chars = [dict(character(c, max_talents=max_talents, max_equipped=max_equipped), name=name,
                  definition_id=i + 1) for i, name in enumerate(hero_names)]
    c.marker('unlocked')
    unlock = c.take(0x104, 'hero unlock bank')
    unlock_count = struct.unpack_from('<I', unlock, 0x100)[0]
    if unlock_count > 256 or len(set(unlock[:unlock_count])) != unlock_count or any(x == 0 for x in unlock[:unlock_count]):
        raise ImportRefusal('DAMAGED', 'Invalid hero unlock count or IDs.')
    c.marker('restore')
    valid, = c.unpack('<B', 'restore validity')
    if valid > 1:
        raise ImportRefusal('DAMAGED', 'Invalid restore validity.')
    restore = [character(c, max_talents=max_talents, max_equipped=max_equipped) for _ in range(17)]
    c.boundary('inventory')
    inventory = c.take(0x289, 'inventory')
    if inventory[0x280] > 1:
        raise ImportRefusal('DAMAGED', 'Invalid inventory snapshot validity.')
    c.boundary('review')
    review = c.take(0x48, 'review banks')
    c.marker('strings')
    strings = c.take(0x5808, 'zone string storage')
    c.marker('zones')
    zone_count, = c.unpack('<I', 'zone count')
    if zone_count > 7:
        raise ImportRefusal('DAMAGED', 'Zone cache exceeds seven records.', offset=c.offset - 4)
    zones = []
    for _ in range(zone_count):
        raw = c.take(0x39bc, 'zone cache')
        for off, maximum in ((0x2ee8, 600), (0x354c, 300), (0x37ac, 300)):
            if struct.unpack_from('<I', raw, off)[0] > maximum:
                raise ImportRefusal('DAMAGED', 'Zone state count exceeds source capacity.', offset=c.offset - 0x39bc + off)
        zones.append(raw)
    c.marker('mission')
    mission = snapshot(c.take(0x184, 'current mission snapshot'))
    c.boundary('profile')
    profile = c.take(0x194, 'embedded profile')
    c.boundary('variables')
    variables = {'mission': [], 'game': []}
    for family, count in (('mission', 32), ('game', 16)):
        names = set()
        for _ in range(count):
            cell = c.take(16, 'script variable')
            name = cstring(cell[:12], 'variable name', c.offset - 16)
            if name:
                if name.lower() in names or not re.fullmatch(r'[A-Za-z0-9_]+', name):
                    raise ImportRefusal('DAMAGED', 'Duplicate or invalid script variable name.', offset=c.offset - 16)
                names.add(name.lower())
                variables[family].append(dict(name=name.lower(), value=int.from_bytes(cell[12:], 'big')))
    c.boundary('end')
    end = c.marker('end_marker')
    if end != '[SAVEGAMEEND: ' + begin[len('[SAVEGAMEBEGIN: '):]:
        raise ImportRefusal('DAMAGED', 'End marker description does not match.', offset=c.boundaries['end'])
    live = [dict(quantity=inventory[2*i], flag=inventory[2*i+1]) for i in range(160)]
    saved = [dict(quantity=inventory[0x140+2*i], flag=inventory[0x141+2*i]) for i in range(160)]
    return dict(decoder='retail-v1', description=begin[16:-1], play_time=play_time, game=game,
                retained_game=retained_game, side=side, side_depth=depth, courses=courses,
                grades=grades, credits=credits, heroes=chars, unlocked=list(unlock[:unlock_count]),
                restore_valid=valid, restore=restore, inventory=live, inventory_snapshot=saved,
                inventory_snapshot_valid=inventory[0x280], tech_bits=struct.unpack_from('<I', inventory, 0x281)[0],
                snapshot_tech_bits=struct.unpack_from('<I', inventory, 0x285)[0], review=review,
                strings=strings, zones=zones, mission=mission, profile=profile, variables=variables,
                consumed=c.offset, slack=payload[c.offset:], boundaries=c.boundaries)
