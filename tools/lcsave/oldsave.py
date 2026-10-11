"""XMen2.exe's own save format (SPEC-old-save.md section 1): a bounds-checked reader (file -> model) and the writer
(model -> bytes) used by the reverse check and the tests.

The model is plain dicts and lists; every byte of the payload is represented (pads, stale entries and residue
included) so that write(read(b)) == b for every file the engine wrote. The reader refuses (OldSaveError) anything
the engine itself does not bound (old 1.18): a count beyond a reader ceiling, an index outside its table, a tag
that is not where the layout says, a payload that does not tile.
"""
from __future__ import annotations

import struct

from . import layout as L
from .layout import read_struct, write_struct, size_of

# reader ceilings for the unbounded old counts (SPEC-new-save 2.16; the engine's caps where it has one)
CEIL_INSTANCES = 4096
CEIL_ENH_PER_LIST = 64
CEIL_EQUIPPED = 3            # the engine refuses a 4th (0x4b9a10); the loader does not bound it (fail closed here)
CEIL_HERO_BLOCKS = 64
CEIL_ZONE_RECORDS = 5        # the container holds 5 (old 1.13); the loader does not bound it
CEIL_WORLD_SLOT = 150


class OldSaveError(ValueError):
    pass


class _Reader:
    def __init__(self, buf, base):
        self.b = buf; self.p = base

    def struct(self, lay):
        v, self.p = read_struct(self.b, self.p, lay)
        return v

    def u8(self):
        return self.struct((('v', 'u8', 1),))['v']

    def u16(self):
        return self.struct((('v', 'u16', 1),))['v']

    def i16(self):
        return self.struct((('v', 'i16', 1),))['v']

    def u32(self):
        return self.struct((('v', 'u32', 1),))['v']

    def take(self, n):
        if self.p + n > len(self.b):
            raise OldSaveError(f'need {n} bytes at {self.p:#x}, payload ends at {len(self.b):#x}')
        v = bytes(self.b[self.p:self.p + n]); self.p += n
        return v

    def tag(self, expect):
        raw = self.take(L.OLD_TAG)
        text = raw[1:51].split(b'\0')[0].decode('cp1252', 'replace')
        if raw[0] != L.OLD_TAG_MARKER or raw[51] != L.OLD_TAG_MARKER or not text.startswith(expect):
            raise OldSaveError(f'expected tag {expect!r} at payload {self.p - L.OLD_TAG:#x}, found {text[:40]!r}')
        return text

    def peek_tag(self, expect):
        raw = self.b[self.p:self.p + L.OLD_TAG]
        return len(raw) == L.OLD_TAG and raw[0] == L.OLD_TAG_MARKER and raw[1:51].startswith(expect.encode())


def _read_instance(r):
    inst = r.struct(L.OLD_INSTANCE_HEAD)
    for name in ('prefixes', 'own', 'suffixes'):
        n = r.u32()
        if n > CEIL_ENH_PER_LIST:
            raise OldSaveError(f'enhancement list {name} count {n} > {CEIL_ENH_PER_LIST}')
        inst[name] = [r.struct(L.OLD_ENH_ELEMENT) for _ in range(n)]
    return inst


def _write_instance(inst):
    out = bytearray(write_struct(inst, L.OLD_INSTANCE_HEAD))
    for name in ('prefixes', 'own', 'suffixes'):
        out += struct.pack('<I', len(inst[name]))
        for e in inst[name]:
            out += write_struct(e, L.OLD_ENH_ELEMENT)
    return bytes(out)


def _read_attributes(r):
    a = r.struct(L.OLD_ATTR_SCALARS)
    a['talents'] = [r.struct(L.OLD_TALENT_ENTRY) for _ in range(L.OLD_TALENT_ENTRIES)]
    a.update(r.struct(L.OLD_TALENT_HEAP_TAIL))
    if a['count'] > L.OLD_TALENT_ENTRIES:
        raise OldSaveError(f'talent count {a["count"]} > {L.OLD_TALENT_ENTRIES}')
    return a


def _write_attributes(a):
    out = bytearray(write_struct(a, L.OLD_ATTR_SCALARS))
    for e in a['talents']:
        out += write_struct(e, L.OLD_TALENT_ENTRY)
    out += write_struct(a, L.OLD_TALENT_HEAP_TAIL)
    return bytes(out)


def _read_equipment(r):
    n = r.u8()
    if n > CEIL_EQUIPPED:
        raise OldSaveError(f'equipped count {n} > {CEIL_EQUIPPED}')
    eq = dict(equipped=[_read_instance(r) for _ in range(n)])
    eq.update(r.struct(L.OLD_EQUIP_TAIL))
    return eq


def _write_equipment(eq):
    out = bytearray(struct.pack('<B', len(eq['equipped'])))
    for i in eq['equipped']:
        out += _write_instance(i)
    out += write_struct(eq, L.OLD_EQUIP_TAIL)
    return bytes(out)


_POWER_SLOT = (('v', 'cstr', L.OLD_POWER_NAME), ('flags', 'u8', 1))


def _read_powers(r):
    slots = [read_struct(r.b, r.p + i * L.OLD_POWER_SLOT, _POWER_SLOT)[0] for i in range(4)]
    raw = r.take(4 * L.OLD_POWER_SLOT)
    pad = r.u8()
    return dict(powers=[s['v'] for s in slots], power_flags=[s['flags'] for s in slots], powers_raw=raw, power_pad=pad)


def _write_powers(h):
    """each slot: the name and the whole flag byte (bit 0 = usable); `powers_raw` (a template's bytes) is kept for a
    slot whose name and flag byte it already holds, so that stale bytes after a name's NUL survive a byte-exact reverse"""
    out = bytearray()
    raw = h.get('powers_raw')
    flags = h.get('power_flags') or [L.POWER_USABLE] * 4
    for k, n in enumerate(h['powers']):
        if raw is not None:
            kept = raw[k * L.OLD_POWER_SLOT:(k + 1) * L.OLD_POWER_SLOT]
            v = read_struct(kept, 0, _POWER_SLOT)[0]
            if v['v'] == n and v['flags'] == flags[k]:
                out += kept
                continue
        out += write_struct({'v': n, 'flags': flags[k]}, _POWER_SLOT)
    out += struct.pack('<B', h.get('power_pad', 0))
    return bytes(out)


def _read_snapshot(r):
    s = r.struct(L.OLD_SNAPSHOT)
    s['seat_names'] = [s.pop(f'seat_name{i}') for i in range(4)]
    return s


def _write_snapshot(s):
    d = dict(s)
    for i in range(4):
        d[f'seat_name{i}'] = s['seat_names'][i]
    return write_struct(d, L.OLD_SNAPSHOT)


def _read_zone_record(r, native):
    """one zone record of the native layout `native` (the state records and the tail sized by it); bounds are
    checked against the descriptor before anything is kept"""
    start = r.p
    if r.p + native.record_size > len(r.b):
        raise OldSaveError(f'zone record needs {native.record_size} bytes at {r.p:#x}, payload ends at {len(r.b):#x}')
    z = {'name_handle': r.u32()}
    z['states'] = [r.struct(L.OLD_STATE_RECORD) for _ in range(native.states)]
    z.update(r.struct(native.zone_record_tail()))
    if r.p - start != native.record_size:
        raise OldSaveError('zone record size')
    if z['state_count'] > native.states or z['dynamic_count'] > native.dynamic or z['smart_count'] > native.smart:
        raise OldSaveError('zone record counts beyond the engine tables')
    return z


def zone_record_matches(z, native):
    """the model's zone record has the array sizes of `native` (a record read with one layout never writes as another)"""
    return (len(z['states']) == native.states and len(z['ordinal_map']) == native.ordinals
            and len(z['dynamic']) == native.dynamic and len(z['smart']) == native.smart)


def _write_zone_record(z, native):
    if not zone_record_matches(z, native):
        raise OldSaveError(f'zone record does not match the native layout {native.id}')
    out = bytearray(struct.pack('<I', z['name_handle']))
    for s in z['states']:
        out += write_struct(s, L.OLD_STATE_RECORD)
    out += write_struct(z, native.zone_record_tail())
    return bytes(out)


def read_profile_block(buf, off=0):
    """the 0x228 profile bytes (old 1.15) -> dict"""
    r = _Reader(buf, off)
    p = r.struct(L.OLD_PROFILE_HEAD)
    p['high_scores'] = [r.struct(L.OLD_HIGH_SCORE) for _ in range(L.OLD_HIGH_SCORES)]
    p.update(r.struct(L.OLD_PROFILE_TAIL))
    if p['score_count'] > L.OLD_HIGH_SCORES:
        raise OldSaveError(f'high-score count {p["score_count"]} > {L.OLD_HIGH_SCORES}')
    return p, r.p


def write_profile_block(p):
    out = bytearray(write_struct(p, L.OLD_PROFILE_HEAD))
    for s in p['high_scores']:
        out += write_struct(s, L.OLD_HIGH_SCORE)
    out += write_struct(p, L.OLD_PROFILE_TAIL)
    return bytes(out)


def zone_string(table, handle):
    """text of a zone string handle (generation << 24 | slot) in the saved string table; '' for 0"""
    if handle == 0:
        return ''
    slot = handle & 0xffffff
    if slot >= L.OLD_ZONE_STRING_SLOTS:
        raise OldSaveError(f'zone string handle {handle:#x}: slot beyond the table')
    off = table['offsets'][slot]
    if off == 0 or off >= L.OLD_ZONE_ARENA:
        raise OldSaveError(f'zone string handle {handle:#x}: slot {slot} is free or its offset {off:#x} is outside the arena')
    arena = table['arena']
    end = arena.find(b'\0', off)
    if end < 0:
        raise OldSaveError(f'zone string at {off:#x} is not terminated')
    return arena[off:end].decode('cp1252', 'replace')


def read_slot(buf, native=L.RETAIL):
    """a complete slot file (0x84 + payload bytes of the native layout `native`, RETAIL: 0x2fc00) -> model dict.
    Refuses anything inconsistent. The layout is the caller's explicit choice: a file of another layout's size is
    refused, never re-interpreted."""
    if len(buf) != native.slot_size:
        raise OldSaveError(f'file size {len(buf)} is not the slot size {native.slot_size} (0x84 + {native.payload:#x})')
    desc = bytes(buf[:0x80]).split(b'\0')[0].decode('cp1252', 'replace')
    plen = struct.unpack_from('<I', buf, 0x80)[0]
    if plen != native.payload:
        raise OldSaveError(f'payload length field {plen:#x} is not {native.payload:#x}')
    m = {'description': desc, 'description_raw': bytes(buf[:0x80])}
    r = _Reader(buf, L.OLD_ENVELOPE)
    m['begin_tag'] = r.tag('[SAVEGAMEBEGIN')
    # ---- items (old 1.4)
    it = r.struct(L.OLD_ITEM_HEAD)
    n1 = r.u32()
    if n1 > CEIL_INSTANCES:
        raise OldSaveError(f'carried item count {n1} > {CEIL_INSTANCES}')
    it['carried'] = [_read_instance(r) for _ in range(n1)]
    n2 = r.u32()
    if n2 > CEIL_WORLD_SLOT:
        raise OldSaveError(f'world item count {n2} > {CEIL_WORLD_SLOT}')
    it['world'] = []
    for _ in range(n2):
        slot = r.u32()
        if slot >= CEIL_WORLD_SLOT:
            raise OldSaveError(f'world item slot {slot} >= {CEIL_WORLD_SLOT}')
        it['world'].append(dict(slot=slot, instance=_read_instance(r)))
    m['items'] = it
    # ---- hero blocks (old 1.6): no count; until the next tag
    heroes = []
    while not r.peek_tag('[CHARACTERSUNLOCKED]'):
        if len(heroes) >= CEIL_HERO_BLOCKS:
            raise OldSaveError(f'no [CHARACTERSUNLOCKED] tag after {CEIL_HERO_BLOCKS} hero blocks')
        h = {'attributes': _read_attributes(r), 'equipment': _read_equipment(r)}
        h.update(_read_powers(r))
        h.update(r.struct(L.OLD_COSTUME))
        heroes.append(h)
    m['heroes'] = heroes
    # ---- unlocked list and restore records (old 1.7)
    r.tag('[CHARACTERSUNLOCKED]')
    ul = [r.i16() for _ in range(L.OLD_UNLOCKED_SLOTS)]
    uc = r.u32()
    if uc > L.OLD_UNLOCKED_SLOTS:
        raise OldSaveError(f'unlocked count {uc} > {L.OLD_UNLOCKED_SLOTS}')
    m['unlocked'] = dict(entries=ul, count=uc)
    r.tag('[CHARACTERSRESTORE]')
    m['restore_flag'] = r.u8()
    m['restore'] = [{'attributes': _read_attributes(r), 'equipment': _read_equipment(r)} for _ in range(L.OLD_RESTORE_RECORDS)]
    # ---- game block (old 1.8)
    m['game'] = r.struct(L.OLD_GAME_BLOCK)
    # ---- side-mission stack (old 1.9)
    m['side'] = dict(frames=[_read_snapshot(r) for _ in range(L.OLD_SIDE_FRAMES)])
    m['side'].update(r.struct(L.OLD_SIDE_TAIL))
    if m['side']['count'] > L.OLD_SIDE_FRAMES:
        raise OldSaveError(f'side-mission stack count {m["side"]["count"]} > {L.OLD_SIDE_FRAMES}')
    # ---- Danger Room (old 1.10): the live course count is not stored; find the split that lands on the next tag
    r.tag('[DANGERROOM: COURSES]')
    start = r.p
    live = None
    for n in range(L.OLD_DR_COURSES + 1):
        end = start + n * L.OLD_DR_COURSE_BYTES + (L.OLD_DR_COURSES - n)
        if end + L.OLD_TAG <= len(buf) and buf[end] == L.OLD_TAG_MARKER and buf[end + 1:end + 21] == b'[DANGERROOM: GRADES]':
            live = n
            break
    if live is None:
        raise OldSaveError('cannot find [DANGERROOM: GRADES] after the course records')
    dr = {'courses': [r.struct(L.OLD_DR_COURSE) for _ in range(live)],
          'course_residue': list(r.take(L.OLD_DR_COURSES - live))}
    r.tag('[DANGERROOM: GRADES]')
    dr['grades'] = list(r.take(L.OLD_DR_GRADES))
    r.tag('[DANGERROOM: END]')
    m['danger_room'] = dr
    # ---- Review (old 1.11)
    m['review'] = r.struct(L.OLD_REVIEW)
    # ---- map (old 1.12-1.14)
    r.tag('[MAP: ZONESTRINGS]')
    m['zone_strings'] = r.struct(L.OLD_ZONE_STRINGS)
    r.tag('[MAP: ZONES]')
    nz = r.u32()
    if nz > CEIL_ZONE_RECORDS or nz > native.record_count:
        raise OldSaveError(f'zone record count {nz} > {CEIL_ZONE_RECORDS}')
    m['zones'] = [_read_zone_record(r, native) for _ in range(nz)]
    r.tag('[MAP: MISSION STATE]')
    m['mission'] = _read_snapshot(r)
    # ---- profile, script variables, town centres (old 1.15-1.17)
    m['profile'], r.p = read_profile_block(buf, r.p)
    sv = {'zone': [r.struct(L.OLD_SCRIPT_VAR) for _ in range(L.OLD_SCRIPT_ZONE_VARS)],
          'game': [r.struct(L.OLD_SCRIPT_VAR) for _ in range(L.OLD_SCRIPT_GAME_VARS)]}
    m['script_vars'] = sv
    m['town_centres'] = r.u32()
    m['end_tag'] = r.tag('[SAVEGAMEEND')
    m['used'] = r.p - L.OLD_ENVELOPE
    slack = bytes(buf[r.p:])
    m['slack_nonzero'] = sum(1 for x in slack if x)
    m['slack'] = slack if m['slack_nonzero'] else None
    _check_indices(m)
    return m


def _check_indices(m):
    """the consistency the engine never checks (old 1.18) but a converter must"""
    for z in m['zones']:
        n = z['state_count']
        for k, idx in enumerate(z['ordinal_map']):
            if idx and idx >= n:
                raise OldSaveError(f'zone record: ordinal {k + 1} names state record {idx} >= count {n}')
        for lst, cnt, what in ((z['dynamic'], z['dynamic_count'], 'dynamic'), (z['smart'], z['smart_count'], 'smart')):
            for idx in lst[:cnt]:
                if idx == 0 or idx >= n:
                    raise OldSaveError(f'zone record: {what} list names state record {idx} (count {n})')
        zone_string(m['zone_strings'], z['name_handle'])
        for idx in range(1, n):
            s = z['states'][idx]
            zone_string(m['zone_strings'], s['def_name'])
            zone_string(m['zone_strings'], s['inst_name'])
    for i, e in enumerate(m['unlocked']['entries'][:m['unlocked']['count']]):
        if e < 0:
            raise OldSaveError(f'unlocked entry {i} is negative')


def _tag_bytes(text):
    raw = text.encode('cp1252')
    body = raw + b'\0' + b'*' * (50 - len(raw) - 1) if len(raw) < 50 else raw[:50]
    return bytes([L.OLD_TAG_MARKER]) + body + bytes([L.OLD_TAG_MARKER])


def write_slot(m, native=L.RETAIL):
    """model -> the complete slot file bytes (0x84 + the payload of `native`, RETAIL: 0x2fc00). Tags are rebuilt
    from their text. Every zone record must have the array sizes of `native` (refused otherwise)."""
    for z in m['zones']:
        if not zone_record_matches(z, native):
            raise OldSaveError(f'zone record does not match the native layout {native.id}')
    if len(m['zones']) > native.record_count:
        raise OldSaveError(f'zone record count {len(m["zones"])} > {native.record_count}')
    out = bytearray()
    out += m['description_raw'] if m.get('description_raw') is not None else write_struct({'v': m['description']}, (('v', 'cstr', 0x80),))
    out += struct.pack('<I', native.payload)
    out += m.get('begin_tag_raw') or _tag_bytes(m['begin_tag'])
    it = m['items']
    out += write_struct(it, L.OLD_ITEM_HEAD)
    out += struct.pack('<I', len(it['carried']))
    for i in it['carried']:
        out += _write_instance(i)
    out += struct.pack('<I', len(it['world']))
    for w in it['world']:
        out += struct.pack('<I', w['slot']) + _write_instance(w['instance'])
    for h in m['heroes']:
        out += _write_attributes(h['attributes']) + _write_equipment(h['equipment']) + _write_powers(h)
        out += write_struct(h, L.OLD_COSTUME)
    out += _tag_bytes('[CHARACTERSUNLOCKED]')
    out += struct.pack('<298h', *m['unlocked']['entries']) + struct.pack('<I', m['unlocked']['count'])
    out += _tag_bytes('[CHARACTERSRESTORE]') + struct.pack('<B', m['restore_flag'])
    for rr in m['restore']:
        out += _write_attributes(rr['attributes']) + _write_equipment(rr['equipment'])
    out += write_struct(m['game'], L.OLD_GAME_BLOCK)
    for f in m['side']['frames']:
        out += _write_snapshot(f)
    out += write_struct(m['side'], L.OLD_SIDE_TAIL)
    out += _tag_bytes('[DANGERROOM: COURSES]')
    for c in m['danger_room']['courses']:
        out += write_struct(c, L.OLD_DR_COURSE)
    out += bytes(m['danger_room']['course_residue'])
    out += _tag_bytes('[DANGERROOM: GRADES]') + bytes(m['danger_room']['grades']) + _tag_bytes('[DANGERROOM: END]')
    out += write_struct(m['review'], L.OLD_REVIEW)
    out += _tag_bytes('[MAP: ZONESTRINGS]') + write_struct(m['zone_strings'], L.OLD_ZONE_STRINGS)
    out += _tag_bytes('[MAP: ZONES]') + struct.pack('<I', len(m['zones']))
    for z in m['zones']:
        out += _write_zone_record(z, native)
    out += _tag_bytes('[MAP: MISSION STATE]') + _write_snapshot(m['mission'])
    out += write_profile_block(m['profile'])
    for kind in ('zone', 'game'):
        for v in m['script_vars'][kind]:
            out += write_struct(v, L.OLD_SCRIPT_VAR)
    out += struct.pack('<I', m['town_centres'])
    out += m.get('end_tag_raw') or _tag_bytes(m['end_tag'])
    if len(out) > native.slot_size:
        raise OldSaveError(f'model does not fit the payload: {len(out) - L.OLD_ENVELOPE} > {native.payload}')
    slack = m.get('slack')
    out += slack if slack else b'\0' * (native.slot_size - len(out))
    if len(out) != native.slot_size:
        raise OldSaveError('slack length')
    return bytes(out)


def zone_record_layout(z):
    """the native layout whose array sizes a model's zone record has, or None"""
    for native in L.NATIVE_LAYOUTS.values():
        if zone_record_matches(z, native):
            return native
    return None


def read_profile_file(buf):
    """settings.dat (0x84 + 0x228) -> (description, profile dict)"""
    if len(buf) != L.OLD_ENVELOPE + L.OLD_PROFILE_PAYLOAD:
        raise OldSaveError(f'file size {len(buf)} is not the settings size {L.OLD_ENVELOPE + L.OLD_PROFILE_PAYLOAD}')
    plen = struct.unpack_from('<I', buf, 0x80)[0]
    if plen != L.OLD_PROFILE_PAYLOAD:
        raise OldSaveError(f'payload length field {plen:#x} is not {L.OLD_PROFILE_PAYLOAD:#x}')
    desc = bytes(buf[:0x80]).split(b'\0')[0].decode('cp1252', 'replace')
    p, end = read_profile_block(buf, L.OLD_ENVELOPE)
    return desc, p


def write_profile_file(desc, p):
    return write_struct({'v': desc}, (('v', 'cstr', 0x80),)) + struct.pack('<I', L.OLD_PROFILE_PAYLOAD) + write_profile_block(p)


def script_var_value(v):
    """the 32-bit value of a script variable record (stored as 4 big-endian bytes)"""
    return struct.unpack('>I', v['value_be'])[0]


def talent_fields(e):
    """the meaningful bits of a talent heap entry (old 1.6 b)"""
    return dict(id=e['id'], rank=e['rank_bits'] & 0x3f, pending=e['pending_cap_bits'] & 0x3f,
                cap=e['pending_cap_bits'] >> 6, base=e['base_bits'] & 3, byte5=e['byte5'])
