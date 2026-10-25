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


def contract(stats, weapons, styles):
    """Return canonical INI records and explicit exclusions, without editing data.

    styles maps case-insensitive source style stems to parsed trees. Only simple
    non-bullet semi-auto weapons qualify: no continuous beam or warm-up. A
    missing style/handler is not permission to treat another weapon as semi-auto.
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
        if weapon.get('type', '').lower() not in ('beam', 'projectile'):
            reason = 'bullet aiming and continuous/melee weapon brains require separate acceptance'
        elif any(weapon.get(key, '').lower() in ('true', '1', 'yes', 'on')
                 for key in ('rapidfire', 'continuousbeam')):
            reason = 'rapid or continuous weapon requires its own firing-window restore'
        try:
            recoil = float(weapon.get('recoiltime', '0'))
            warmup = float(weapon.get('warmuptime', '0'))
            distance = float(weapon.get('range', '0'))
            # Original prototype constructor: omitted bursttime is 1.0 second.
            burst = float(weapon.get('bursttime', '1'))
            if not math.isfinite(warmup) or warmup != 0:
                reason = 'warm-up requires its separate deadline and charge path'
            if not math.isfinite(recoil) or not 0 < recoil <= 60:
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
        if primary is None or _attrs(primary).get('handler', '').lower() != 'ch_weapon_semi_auto':
            reason = 'no source semi-auto primary move'
        elif any(m.tag.lower() == 'fightmove' and _attrs(m).get('handler', '').lower() == 'ch_weapon_semi_auto'
                 and any(key in _attrs(m) for key in ('aitype', 'aireusetime')) for m in style.iter()):
            reason = 'authored gun AI attributes require a separate compatibility contract'
        if reason:
            excluded.append({'actor': name, 'reason': reason})
            continue
        if not re.fullmatch(r'[a-z0-9_]{1,31}', name) or name in seen:
            raise ValueError('invalid or duplicate semi-auto actor identity')
        seen.add(name)
        words = [struct.unpack('<I', struct.pack('<f', value))[0] for value in (recoil, distance, burst)]
        words.append(int(attrs.get('leader', '').lower() in ('true', '1', 'yes', 'on')))
        records.append(name + ''.join(f'|{bits:08x}' for bits in words))
    if len(records) > 64:
        raise ValueError('semi-auto contract exceeds the native bound')
    return {'schema': 2, 'records': sorted(records, key=lambda row: row.split('|')[0]),
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
    if data.get('schema') != 2 or not 1 <= len(records) <= 64:
        raise ValueError('missing or unsupported semi-auto contract')
    names = set()
    for row in records:
        if not isinstance(row, str) or not re.fullmatch(r'[a-z0-9_]{1,31}(\|[0-9a-f]{8}){4}', row):
            raise ValueError('invalid semi-auto record')
        name, *words = row.split('|')
        recoil, distance, burst = [struct.unpack('<f', struct.pack('<I', int(bits, 16)))[0] for bits in words[:3]]
        leader = int(words[3], 16)
        if (name in names or not all(map(math.isfinite, (recoil, distance, burst)))
                or not 0 < recoil <= 60 or not 75 < distance <= 65535 or not distance.is_integer()
                or not 0 < burst <= 60 or leader > 1):
            raise ValueError('duplicate actor or invalid weapon parameters')
        names.add(name)
    return {'Game': {'NpcPowerRule': 'xml1', 'NpcSemiAuto': 'xml1'},
            'NpcSemiAuto': {'Count': str(len(records)),
                            **{f'W{i}': row for i, row in enumerate(sorted(records, key=lambda row: row.split('|')[0]), 1)}}}
