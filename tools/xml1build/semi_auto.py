"""Source-derived metadata for XML2 Fix's NPC weapon brain (gameplay-agreement rule 16 revision 10).

The characters stage derives the contract from the owner's XML1 npcstat, weapon and powerstyle trees and records it
in _build/semi_auto.json (build_contract); fix_ini.port_keys exports it as [Game] NpcSemiAuto=xml1 plus the
[NpcSemiAuto] rows (ini_sections), so every XML1 build restores the original weapon brain by default, as
NpcPowerRule=xml1 restores XML1's powers. No game names or weapon values are embedded here: callers supply their own
parsed source trees.
"""
from __future__ import annotations

import math
import re
import struct


def _attrs(element):
    return {key.lower(): value for key, value in element.attrib.items()}


# The original weapon prototype's type enum (default.xbe parser table 0x44fc44) and flag bits
# of the schema 4 flags word; XML2 Fix's npc_semi_auto_rules.hpp uses the same values.
TYPES = {'bullet': 0, 'flame': 1, 'projectile': 2, 'beam': 3}
CONTINUOUS, RAPIDFIRE, DEFAULT_HANDLER = 0x10, 0x20, 0x40
KNOWN_FLAGS = 3 | CONTINUOUS | RAPIDFIRE | DEFAULT_HANDLER
SCHEMA = 4
_ROW = re.compile(r'[a-z0-9_]{1,31}(\|[0-9a-f]{8}){8}')


def _true(value):
    return (value or '').lower() in ('true', '1', 'yes', 'on')


def _bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def contract(stats, weapons, styles):
    """Return canonical INI records and explicit exclusions, without editing data.

    styles maps case-insensitive source style stems to parsed trees. Every gun primary of the
    original weapon brain qualifies: a ch_weapon_semi_auto power_attack of any weapon type
    (bullet, flame, projectile, beam) - discrete, with a warm-up before every shot, or a
    continuous beam that warms up once - and a default-handler (no handler) power_attack of
    a discrete weapon without warm-up (the pistol). Zero recoil is admitted only for a
    continuous beam. A missing style or another handler is not permission to treat the
    weapon as a gun primary, and source-authored gun AI attributes stay excluded.

    Schema 4 rows carry name|recoil|range|burst|leader|warmup|flags|tracetime|accuracy (eight lowercase hex
    digits each; IEEE-754 binary32 for the timings and range; flags = the type enum in bits
    0-1, continuous beam 0x10, rapid fire 0x20, default-handler primary 0x40).
    """
    definitions = {_attrs(w).get('name', '').lower(): _attrs(w)
                   for w in weapons.iter() if w.tag.lower() == 'weapon'}
    styles = {key.lower(): tree for key, tree in styles.items()}
    records, excluded, seen = [], [], set()
    for actor in stats.iter():
        if actor.tag.lower() != 'stats':
            continue
        attrs = _attrs(actor)
        name = attrs.get('name', '').lower()
        weapon = definitions.get(attrs.get('weapon', '').lower())
        if not weapon:
            continue
        reason = ''
        kind = weapon.get('type', '').lower()
        continuous = _true(weapon.get('continuousbeam'))
        recoil = warmup = distance = burst = tracetime = accuracy = 0.0
        try:
            recoil = float(weapon.get('recoiltime', '0'))
            warmup = float(weapon.get('warmuptime', '0'))
            distance = float(weapon.get('range', '0'))
            # Original prototype constructor: omitted bursttime is 1.0 second.
            burst = float(weapon.get('bursttime', '1'))
            # Weapon prototype defaults: trace time (+0x1bc) and accuracy (+0x1b0) are zero.
            tracetime = float(weapon.get('tracetime', '0'))
            accuracy = float(weapon.get('accuracy', '0'))
            if not math.isfinite(tracetime) or not 0 <= tracetime <= 60:
                reason = 'invalid source trace time'
            if not math.isfinite(accuracy) or not 0 <= accuracy <= 360:
                reason = 'invalid source accuracy'
            if not math.isfinite(warmup) or not 0 <= warmup <= 60:
                reason = 'invalid source warm-up'
            if not math.isfinite(recoil) or not 0 <= recoil <= 60 or (recoil == 0 and not continuous):
                reason = 'invalid or absent recoil'
            if not math.isfinite(distance) or not 75 < distance <= 65535 or not distance.is_integer():
                reason = 'invalid or absent source weapon range'
            if not math.isfinite(burst) or not 0 < burst <= 60:
                reason = 'invalid source burst duration'
        except ValueError:
            reason = 'invalid timing declaration'
        style = styles.get(attrs.get('powerstyle', weapon.get('powerstyle', '')).lower())
        primary = next((m for m in style.iter() if m.tag.lower() == 'fightmove'
                        and _attrs(m).get('name', '').lower() == 'power_attack'), None) if style is not None else None
        handler = _attrs(primary).get('handler', '').lower() if primary is not None else None
        default = handler == ''
        if primary is None or handler not in ('ch_weapon_semi_auto', ''):
            reason = 'no source gun primary move'
        elif default and (continuous or warmup != 0):
            reason = 'default-handler primary with a warm-up or continuous beam has no original gate path'
        elif any(m.tag.lower() == 'fightmove' and (_attrs(m).get('handler', '').lower() == 'ch_weapon_semi_auto'
                                                    or (default and m is primary))
                 and any(key in _attrs(m) for key in ('aitype', 'aireusetime')) for m in style.iter()):
            reason = 'authored gun AI attributes require a separate compatibility contract'
        if kind not in TYPES:
            reason = 'melee weapons have no gun primary'
        if reason:
            excluded.append({'actor': name, 'reason': reason})
            continue
        if not re.fullmatch(r'[a-z0-9_]{1,31}', name) or name in seen:
            raise ValueError('invalid or duplicate semi-auto actor identity')
        seen.add(name)
        flags = (TYPES[kind] | (CONTINUOUS if continuous else 0) |
                 (RAPIDFIRE if _true(weapon.get('rapidfire')) else 0) | (DEFAULT_HANDLER if default else 0))
        words = [_bits(recoil), _bits(distance), _bits(burst), int(_true(attrs.get('leader'))), _bits(warmup), flags,
                 _bits(tracetime), _bits(accuracy)]
        records.append(name + ''.join(f'|{bits:08x}' for bits in words))
    if len(records) > 64:
        raise ValueError('semi-auto contract exceeds the native bound')
    return {'schema': SCHEMA, 'records': sorted(records, key=lambda row: row.split('|')[0]),
            'excluded': sorted(excluded, key=lambda row: row['actor'])}


CONTRACT_FILE = 'semi_auto.json'   # <out>/_build/<CONTRACT_FILE>, written by the characters stage


def _style_names(stats, weapons):
    """lower powerstyle stems the weapon actors of `stats` name (actor override first, else the weapon's)."""
    definitions = {_attrs(w).get('name', '').lower(): _attrs(w)
                   for w in weapons.iter() if w.tag.lower() == 'weapon'}
    names = set()
    for actor in stats.iter():
        if actor.tag.lower() != 'stats':
            continue
        attrs = _attrs(actor)
        weapon = definitions.get(attrs.get('weapon', '').lower())
        if weapon:
            name = attrs.get('powerstyle', weapon.get('powerstyle', '')).lower()
            if name:
                names.add(name)
    return names


def build_contract(ctx, built_names=None):
    """Characters stage: the contract from the owner's XML1 sources -> <out>/_build/semi_auto.json. Rows whose actor
    the build does not carry (built_names: lower npcstat/herostat names) move to the exclusions. Returns the contract,
    or None (and nothing written) when the XML1 npcstat or weapon tree is not readable."""
    try:
        stats = ctx.read_x1_xml('data/npcstat.eng')
        weapons = ctx.read_x1_xml('data/weapons/weapons.eng')
    except KeyError as exc:
        ctx.warn(f'NPC weapon brain contract not built ({exc}): officers keep the stock PC weapon AI')
        return None
    if stats is None or weapons is None:
        ctx.warn('NPC weapon brain contract not built (empty XML1 npcstat or weapons): stock PC weapon AI')
        return None
    styles = {}
    for name in sorted(_style_names(stats, weapons)):
        rel = next((r for r in (f'data/powerstyles/{name}.eng', f'data/powerstyles/{name}.xml') if ctx.x1_path(r)), None)
        if rel is not None:
            tree = ctx.read_x1_xml(rel)
            if tree is not None:
                styles[name] = tree
    data = contract(stats, weapons, styles)
    if built_names is not None:
        kept = [row for row in data['records'] if row.split('|')[0] in built_names]
        data['excluded'] = sorted(data['excluded'] + [{'actor': row.split('|')[0], 'reason': 'actor not in this build'}
                                                      for row in data['records'] if row not in kept],
                                  key=lambda row: row['actor'])
        data['records'] = kept
    ctx.write_meta(CONTRACT_FILE, data)
    return data


def ini_sections(data):
    """The xml2-fix.ini export of a contract: [Game] NpcPowerRule/NpcSemiAuto=xml1 and the [NpcSemiAuto] rows.
    Raises ValueError for a missing, empty or malformed contract (the caller then writes no weapon-brain keys)."""
    records = data.get('records', [])
    if data.get('schema') != SCHEMA or not 1 <= len(records) <= 64:
        raise ValueError('missing or unsupported semi-auto contract')
    names = set()
    for row in records:
        if not isinstance(row, str) or not _ROW.fullmatch(row):
            raise ValueError('invalid semi-auto record')
        name, *words = row.split('|')
        recoil, distance, burst = [struct.unpack('<f', struct.pack('<I', int(bits, 16)))[0] for bits in words[:3]]
        leader = int(words[3], 16)
        warmup = struct.unpack('<f', struct.pack('<I', int(words[4], 16)))[0]
        flags = int(words[5], 16)
        tracetime, accuracy = [struct.unpack('<f', struct.pack('<I', int(bits, 16)))[0] for bits in words[6:]]
        if (name in names or not all(map(math.isfinite, (recoil, distance, burst, warmup, tracetime, accuracy)))
                or not 0 <= recoil <= 60 or (recoil == 0 and (words[0] != '00000000' or not flags & CONTINUOUS))
                or not 75 < distance <= 65535 or not distance.is_integer()
                or not 0 < burst <= 60 or leader > 1
                or not 0 <= warmup <= 60 or (warmup == 0 and words[4] != '00000000')
                or flags & ~KNOWN_FLAGS
                or not 0 <= tracetime <= 60 or (tracetime == 0 and words[6] != '00000000')
                or not 0 <= accuracy <= 360 or (accuracy == 0 and words[7] != '00000000')
                or (flags & DEFAULT_HANDLER and (flags & CONTINUOUS or warmup != 0))):
            raise ValueError('duplicate actor or invalid weapon parameters')
        names.add(name)
    return {'Game': {'NpcPowerRule': 'xml1', 'NpcSemiAuto': 'xml1'},
            'NpcSemiAuto': {'Count': str(len(records)),
                            **{f'W{i}': row for i, row in enumerate(sorted(records, key=lambda row: row.split('|')[0]), 1)}}}
