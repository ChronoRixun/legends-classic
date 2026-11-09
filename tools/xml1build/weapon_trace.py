"""Fail-closed validation of converted, actor-wide nonbullet trace admission."""
import collections
import json
import math
import struct
from pathlib import Path

from . import semi_auto as S

MARKER = '32765 32765'             # inert retail split damage: split_count=0
CAPABILITY = b'lc-npc-beam-trace/1\0'
REQUIREMENT = '[Game] NpcSemiAuto (beam/flame trace gate)'


def keys_require_trace(keys):
    if keys.get('Game', {}).get('NpcSemiAuto') != 'xml1':
        return False
    for key, row in keys.get('NpcSemiAuto', {}).items():
        if not key.startswith('W'):
            continue
        parts = row.split('|')
        if len(parts) == 9 and int(parts[6], 16) & 3 in (1, 3) and int(parts[7], 16):
            return True
    return False


def required(weapon):
    if weapon.get('type', '').lower() not in ('beam', 'flame'):
        return False
    try:
        time = float(weapon.get('tracetime', '0'))
        # Unsupported positive intervals still require a contract: schema-4's
        # bounded parser then refuses them instead of silently emitting ungated
        # full damage. Match source binary32 underflow to zero.
        if math.isnan(time) or time <= 0:
            return False
        try:
            return struct.unpack('<f', struct.pack('<f', time))[0] > 0
        except OverflowError:
            return True
    except (TypeError, ValueError):
        return False


def _attrs(e):
    return {k.lower(): v for k, v in e.attrib.items()}


def _source(ctx, name):
    for ext in ('.eng', '.xml'):
        rel = f'data/powerstyles/{name}{ext}'
        if ctx.x1_path(rel):
            return ctx.read_x1_xml(rel)
    return None


def _resolved(events, attrs, seen=()):
    name = (attrs.get('inherit') or attrs.get('name') or '').lower()
    if name in events and name not in seen and not attrs.get('type'):
        base = _resolved(events, _attrs(events[name]), seen + (name,))
        return dict(base, **{k: v for k, v in attrs.items() if k not in ('name', 'inherit')})
    return dict(attrs, name=name)


def _calls(root, definitions, holder=None, built=False):
    events = {e.get('name', '').lower(): e for e in root.iter('event')}
    calls = []
    for move in root.iter('FightMove'):
        for trigger in move:
            if trigger.tag.lower() != 'trigger':
                continue
            a = _resolved(events, _attrs(trigger))
            weapon = definitions.get(a.get('weapon', '').lower(), holder)
            shot = (a.get('name', '').lower() == 'beam' and a.get('damagescale') == 'difficulty'
                    and a.get('damagelevel') == '1') if built else (
                        a.get('name', '').lower() == 'weapon_fire' and weapon and required(weapon))
            if shot:
                key = (move.get('name', '').lower(), trigger.get('time', '0'), trigger.get('tag', ''))
                calls.append((key, a, weapon))
    return calls


def _variant_matches(base, stem):
    from . import weapons as W
    if base == stem:
        return True
    # The actual name provider removes ps_ when appending a grenade would exceed
    # the engine's width. Re-run that provider rather than assuming a prefix.
    prefixes = [base] + (['x1_' + base[6:]] if base.startswith('x1_ps_') else [])
    return any(stem.startswith(prefix + '_') and
               W.variant_grenade_name(base, stem[len(prefix) + 1:]) == stem for prefix in prefixes)


def validate(v, ck):
    from . import weapons as W
    ctx = v.ctx
    try:
        definitions_root = ctx.read_x1_xml('data/weapons/weapons.eng')
        definitions = {_attrs(w)['name'].lower(): _attrs(w) for w in definitions_root.iter()
                       if w.tag.lower() == 'weapon' and w.get('name')}
        stats = ctx.read_x1_xml('data/npcstat.eng')
    except (KeyError, OSError, AttributeError):
        definitions, stats = {}, None
    styles, holders = {}, collections.defaultdict(list)
    if stats is not None:
        for actor in stats.iter():
            a = _attrs(actor)
            w = definitions.get(a.get('weapon', '').lower())
            if actor.tag.lower() != 'stats' or not w:
                continue
            name = a.get('powerstyle', w.get('powerstyle', '')).lower()
            if name not in styles:
                styles[name] = _source(ctx, name)
            if required(w):
                holders[W.variant_name(name, w['name']).lower()].append((a.get('name', '').lower(), w, name))
    built_holders = {}
    for rel in v.idx.under('data/'):
        if rel.lower() not in ('data/npcstat.xmlb', 'data/npcstat.engb') or v.entry(rel) is None:
            continue
        for actor in v.tree(rel).iter():
            if actor.tag.lower() == 'stats':
                built_holders[actor.get('name', '').lower()] = actor.get('powerstyle', '').lower()
    pending, checked_actors = [], set()
    for rel in v.idx.under('data/powerstyles/'):
        if v.entry(rel) is None or not rel.lower().endswith(('.xmlb', '.engb')):
            continue
        root, stem = v.tree(rel), Path(rel).stem.lower()
        candidates = [row for base, rows in holders.items() if _variant_matches(base, stem) for row in rows]
        bindings = [row for row in candidates if built_holders.get(row[0]) == stem]
        marked = [e for e in root.iter() if e.get('split_damage') == MARKER]
        source = _source(ctx, stem[3:]) if not bindings and stem.startswith('x1_') else None
        named = _calls(source, definitions) if source is not None else []
        if not bindings and (marked or named):
            ck.error(f'{rel}: trace contract has no source weapon holder/type/positive-tracetime binding')
            continue
        if not bindings:
            continue
        source = styles[bindings[0][2]]
        if source is None:
            ck.error(f'{rel}: trace contract source style missing')
            continue
        expected = _calls(source, definitions, bindings[0][1])
        actual = _calls(root, definitions, built=True)
        if collections.Counter(k for k, _, _ in expected) != collections.Counter(k for k, _, _ in actual):
            ck.error(f'{rel}: trace contract calls differ from source (primary/crouched/burst/tagged/inherited)')
        for event in W._gun_shot_els(root):
            if event.get('split_damage') != MARKER or event.get('split_count') != '0':
                ck.error(f'{rel}: trace contract requires inert beam/flame marker on every weapon call')
        for _, attrs, _ in actual:
            if attrs.get('split_damage') != MARKER or attrs.get('split_count') != '0':
                ck.error(f'{rel}: effective inherited weapon call overrides its trace marker')
        for _, _, weapon in expected:
            if any((weapon.get('type', '').lower(), struct.pack('<f', float(weapon['tracetime']))) !=
                   (holder.get('type', '').lower(), struct.pack('<f', float(holder['tracetime'])))
                   for _, holder, _ in bindings):
                ck.error(f'{rel}: named weapon trace type/interval differs from its source holder')
        for actor, w, _ in bindings:
            pending.append((rel, actor))
            checked_actors.add(actor)
        ck.count('nonbullet_trace_styles_checked')
    for rows in holders.values():
        for actor, _, _ in rows:
            if actor in built_holders and actor not in checked_actors:
                ck.error(f'trace contract holder {actor} has no validated source weapon style')
    if not pending:
        return
    try:
        expected = S.contract(stats, definitions_root, {k: t for k, t in styles.items() if t is not None})
        expected_rows = {r.split('|')[0]: r for r in expected['records']}
        actual = json.loads((Path(ctx.out) / '_build' / S.CONTRACT_FILE).read_text(encoding='utf-8'))
        S.ini_sections(actual)
        rows = {r.split('|')[0]: r for r in actual['records']}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        ck.error(f'nonbullet trace contract metadata missing or invalid: {exc}')
        rows, expected_rows = {}, {}
    for rel, actor in pending:
        if actor not in expected_rows or rows.get(actor) != expected_rows[actor]:
            ck.error(f'{rel}: trace contract requires complete source-derived schema-4 row for {actor}')
    try:
        supported = CAPABILITY in (Path(ctx.out) / 'dinput.dll').read_bytes()
    except OSError:
        supported = False
    if not supported:
        ck.error('nonbullet trace contract requires a companion with lc-npc-beam-trace/1 capability')
