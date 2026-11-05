"""Bounded XML1-recomp save sections surveyed at revision a30ec29.

Newer upstream formats may differ. No definition name/order is inferred from
the bitmap: mapping needs the exact effective source herostat ID ledger.
Native framing is shared with retail; this decoder alone admits adjuncts.
"""
from __future__ import annotations

import math
import re
import struct

from . import retail
from .errors import ImportRefusal
from .source import CAPACITY

SURVEY_REVISION = 'a30ec29'
MAX_CHARACTERS = 48
SNAPSHOTS = 48
DIFFICULTY_SIZES = {1: 20, 2: 22, 3: 112, 4: 120, 5: 124}


def _damaged(reason, offset):
    raise ImportRefusal('DAMAGED', reason, offset=offset)


def _version(extension, version, offset):
    raise ImportRefusal('RECOMP_VERSION', extension=extension, version=version, offset=offset)


def _text(raw, field, offset, *, zero_padding=False, required=False):
    value = retail.cstring(raw, field, offset)
    if required and not value:
        _damaged('Empty ' + field, offset)
    if zero_padding and any(raw[len(value):]):
        _damaged('Nonzero ' + field + ' padding.', offset)
    return value


def _selections(raw, offset):
    c = retail.Cursor(raw)
    count, = c.unpack('<H', 'power selection count')
    if count > 254 or len(raw) != 2 + count * 100:
        _damaged('Invalid named power selection length.', offset)
    rows, folded = {}, set()
    for _ in range(count):
        name = _text(c.take(20, 'power owner'), 'power owner', offset + c.offset - 20,
                     zero_padding=True, required=True)
        if name.lower() in folded:
            _damaged('Duplicate power selection owner.', offset + c.offset - 20)
        folded.add(name.lower())
        rows[name] = [_text(c.take(20, 'selected power'), 'selected power', offset + c.offset - 20,
                            zero_padding=True) for _ in range(4)]
    return rows


def _identities(raw, offset):
    c = retail.Cursor(raw)
    magic, version, reserved, count, tail = c.unpack('<4s4B', 'talent identity header')
    if magic != b'TLID' or reserved or tail or count > 254:
        _damaged('Invalid talent identity header.', offset)
    if version != 1:
        _version('TLID', version, offset)
    rows, names = {}, set()
    for _ in range(count):
        tid, n, s, q = c.unpack('<4B', 'talent identity lengths')
        if tid in (0, 255) or tid in rows or not 0 < n < 32 or not 0 < s < 32 or not 0 < q < 64:
            _damaged('Invalid or duplicate talent identity.', offset + c.offset - 4)
        values = []
        for length in (n, s, q):
            text = c.take(length, 'talent identity text')
            if b'\0' in text:
                _damaged('Embedded NUL in talent identity.', offset + c.offset - length)
            values.append(_text(text + b'\0', 'talent identity', offset + c.offset - length, required=True))
        name, filename, selector = values
        if name.lower() in names:
            _damaged('Ambiguous talent name.', offset + c.offset)
        names.add(name.lower())
        rows[tid] = dict(name=name, source=filename, selector=selector)
    if c.offset != len(raw):
        _damaged('Trailing talent identity bytes.', offset + c.offset)
    return rows


class Cursor(retail.Cursor):
    def boundary(self, name):
        # Exactly these two cursors are owned by this decoder. A magic at any
        # other native subsystem boundary retains its explicit refusal.
        if name in ('characters', 'variables'):
            self.boundaries[name] = self.offset
        else:
            super().boundary(name)


def _characters(c, definitions):
    start = c.offset
    magic, version, size, snapshots, reserved, bitmap = c.unpack('<8s4H32s', 'XML1CHR header')
    if magic != b'XML1CHR\0':
        _damaged('Expected an XML1CHR section at the character boundary.', start)
    if not 1 <= version <= 6:
        _version('XML1CHR', version, start)
    if size < 48 or (version < 3 and size != 48) or snapshots != SNAPSHOTS or reserved:
        _damaged('Invalid XML1CHR header size, snapshot count or reserved word.', start)
    ids = [i for i in range(256) if bitmap[i // 8] & (1 << (i % 8))]
    if not ids or len(ids) > MAX_CHARACTERS or any(i in (0, 255) for i in ids):
        _damaged('Invalid character definition bitmap.', start + 16)
    header = c.take(size - 48, 'XML1CHR extended header')
    powers, identities = {}, {}
    if version == 3:
        powers = _selections(header, start + 48)
    elif version >= 4:
        h = retail.Cursor(header)
        selection_bytes, identity_bytes = h.unpack('<HH', 'XML1CHR header frame lengths')
        if selection_bytes + identity_bytes + 4 != len(header):
            _damaged('XML1CHR header frames do not sum to the declared length.', start + 48)
        powers = _selections(h.take(selection_bytes, 'power selections'), start + 52)
        identities = _identities(h.take(identity_bytes, 'talent identities'), start + 52 + selection_bytes)
    def record(cursor):
        value = retail.character(cursor, max_talents=254, version=version)
        if version >= 4 and any(t['native_id'] not in identities for t in value['talents']):
            _damaged('A talent record has no saved identity.', value['offset'])
        return value
    chars = []
    for ident in ids:
        if definitions is not None and ident not in definitions:
            raise ImportRefusal('IDENTITY', 'Saved definition is absent from the effective source ledger.', definition_id=ident)
        chars.append(dict(record(c), definition_id=ident, name=definitions[ident] if definitions is not None else f'definition_{ident}',
                          identity_resolved=definitions is not None))
    unlocked = retail._unlocks(c)
    valid, restore = retail._restore(c, SNAPSHOTS, record)
    return dict(heroes=chars, unlocked=unlocked, restore_valid=valid, restore=restore,
                character_version=version, power_selections=powers, talent_identities=identities)


def _difficulty(c):
    start = c.offset
    _, version = c.unpack('<8sI', 'XML1DIF header')
    if version not in DIFFICULTY_SIZES:
        _version('XML1DIF', version, start)
    raw = c.take(DIFFICULTY_SIZES[version] - 12, 'XML1DIF body')
    live, retained = struct.unpack_from('<ii', raw)
    if live not in (0, 1, 2) or retained not in (0, 1, 2):
        _damaged('Unsupported difficulty value.', start + 12)
    result = dict(version=version, difficulty=live, retained_difficulty=retained)
    if version >= 2:
        result['acts'] = list(raw[8:10])
        if any(not 1 <= act <= 9 for act in result['acts']):
            _damaged('Invalid campaign act.', start + 20)
    if version >= 3:
        recalls = []
        for i in range(2):
            at = 10 + 45 * i
            zone = _text(raw[at:at + 32], 'recall zone', start + 12 + at, required=True)
            position = list(struct.unpack_from('<3f', raw, at + 32))
            enabled = raw[at + 44]
            if enabled > 1 or not all(math.isfinite(x) for x in position):
                _damaged('Invalid recall position or flag.', start + 12 + at)
            recalls.append(dict(zone=zone, position=position, enabled=bool(enabled)))
        result['recalls'] = recalls
    if version >= 4:
        cooldowns = list(struct.unpack_from('<2f', raw, 100))
        if any(not math.isfinite(x) or x < 0 for x in cooldowns):
            _damaged('Invalid recall cooldown.', start + 112)
        result['cooldowns'] = cooldowns
    if version >= 5:
        result['pickup_bonuses'] = [list(raw[108:110]), list(raw[110:112])]
    return result


def _stash(c, inventory):
    start = c.offset
    _, version, size = c.unpack('<8sII', 'XML1STSH header')
    if version != 1:
        _version('XML1STSH', version, start)
    if size < 28:
        _damaged('Invalid stash section length.', start + 12)
    body = retail.Cursor(c.take(size - 16, 'XML1STSH body'))
    valid, = body.unpack('<I', 'stash snapshot validity')
    if valid not in (0, 1) or valid != inventory[0x280]:
        _damaged('Stash and native inventory snapshot validity disagree.', start + 16)
    result = dict(valid=bool(valid))
    for family in ('live', 'snapshot'):
        count, = body.unpack('<I', 'stash item count')
        if count > 60:
            _damaged('Stash item count exceeds capacity.', start + 16 + body.offset - 4)
        rows, names, total = [], set(), 0
        for _ in range(count):
            length, quantity = body.unpack('<II', 'stash item length and quantity')
            if not length or not 0 < quantity <= 60 or total + quantity > 60:
                _damaged('Invalid stash name length or quantity.', start + 16 + body.offset - 8)
            raw = body.take(length, 'stash item name')
            if b'\0' in raw:
                _damaged('Embedded NUL in stash item name.', start + 16 + body.offset - length)
            name = _text(raw + b'\0', 'stash item name', start + 16 + body.offset - length, required=True)
            if name.lower() in names:
                _damaged('Ambiguous stash item name.', start + 16 + body.offset - length)
            names.add(name.lower())
            rows.append(dict(name=name, quantity=quantity))
            total += quantity
        result[family] = rows
    if body.offset != len(body.data) or (not valid and result['snapshot']):
        _damaged('Trailing stash bytes or invalid snapshot contents.', start)
    return result


def _adjuncts(c, inventory):
    result = dict(hard_unlocked=False, difficulty=1, campaign_extra={}, stash=dict(valid=False, live=[], snapshot=[]))
    if c.data[c.offset:c.offset + 8] == b'XML1PRG\0':
        start = c.offset
        _, version, unlocked = c.unpack('<8sII', 'XML1PRG section')
        if version != 1:
            _version('XML1PRG', version, start)
        if unlocked not in (0, 1):
            _damaged('Invalid hard-difficulty unlock flag.', start + 12)
        result['hard_unlocked'] = bool(unlocked)
    if c.data[c.offset:c.offset + 8] == b'XML1DIF\0':
        result['campaign_extra'] = _difficulty(c)
        result['difficulty'] = result['campaign_extra']['difficulty']
    if c.data[c.offset:c.offset + 8] == b'XML1STSH':
        result['stash'] = _stash(c, inventory)
    # Never silently treat reordered, duplicate or unknown adjuncts as native
    # variable cells. Magic is inspected only at the current cursor.
    c.boundary('adjunct_end')
    return result


def decode(payload, *, definitions=None):
    if not 0 < len(payload) <= CAPACITY:
        raise ImportRefusal('VERSION', 'Unsupported recomp payload size.')
    if definitions is not None:
        if (not isinstance(definitions, dict) or not definitions or
            any(type(i) is not int or not 1 <= i <= 254 or not isinstance(n, str) or
                not re.fullmatch(r'[A-Za-z0-9_]+', n) for i, n in definitions.items()) or
            len({n.lower() for n in definitions.values()}) != len(definitions)):
            raise ImportRefusal('IDENTITY', 'Invalid effective source definition ledger.')
    result = retail._decode(payload, lambda c: _characters(c, definitions), cursor_type=Cursor, read_adjuncts=_adjuncts)
    result['decoder'] = 'recomp-chr-v' + str(result['character_version'])
    result['survey_revision'] = SURVEY_REVISION
    return result
