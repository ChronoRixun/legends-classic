"""Canonical JSON dumps of both formats, by NAME, for semantic comparison (SPEC-new-save 5.5 step 5's shape).

dump_old: old model -> names through the era tables (no catalogue, no container code involved)
dump_new: LC file -> names through the catalogue entries' key hashes
semantic_diff: the differences between two dumps as a list of strings (empty = equal). Zone states are
compared as multisets of (list, definition name, instance name, flags, position, payload): the ordinal itself is
an era position and is reported separately.
"""
from __future__ import annotations

import struct

from . import oldsave
from . import layout as L
from .binds import KEY_ITEM_NAMES, TRIVIA_PER_ACT, REVIEW_PER_CATEGORY
from .container import read_file
from .keys import key_hash, DOMAINS


def _name(env, tag, h):
    """the key text of a hash, lower-cased (identifiers are case-insensitive: the canonical key is lower-case)"""
    if h is None:
        return None
    n = env.name_of(tag, h)
    return n.lower() if n is not None else f'<{tag}:{h[:12]}>'


def _era_name(env, era, domain, tag, index):
    t = era.table(domain)
    if not 0 <= index < len(t) or t[index] is None:
        return f'<{domain} position {index} out of range>'
    return _name(env, tag, t[index])


def _instance_old(env, era, inst):
    d = dict(definition=_era_name(env, era, 'ITEM', 'ITEM', inst['definition']), location=inst['location'],
             name_a=None if inst['name_a'] == 0xff else _era_name(env, era, 'NAMA', 'NAMA', inst['name_a']),
             special=None if inst['special'] == 0xff else _era_name(env, era, 'TRIT', 'TRIT', inst['special']))
    if inst['name_b'] == 0xff:
        d['name_b'] = None
    else:
        cls = era.table('ITEM_class')[inst['definition']] if inst['definition'] < len(era.table('ITEM_class')) else ''
        lst = era.table('NAMB').get(cls or '', [])
        d['name_b'] = _name(env, 'NAMB', lst[inst['name_b']]) if inst['name_b'] < len(lst) else '<out of range>'
    for k in ('prefixes', 'own', 'suffixes'):
        d[k] = [[_era_name(env, era, 'ENHC', 'ENHC', e['record']), e['value']] for e in inst[k]]
    return d


def _talents_old(env, era, stats_index, a):
    out = []
    stat_hash = era.table('STAT')[stats_index] if stats_index < len(era.table('STAT')) else None
    hero_tal = era.table('TALN_hero').get(stat_hash, [])
    for e in a['talents'][:a['count']]:
        f = oldsave.talent_fields(e)
        tid = e['id']
        if tid < 100:
            name = _era_name(env, era, 'TALN_shared', 'TALN', tid)
        else:
            pos = tid % 100
            name = _name(env, 'TALN', hero_tal[pos]) if (tid // 100 - 1) == stats_index and pos < len(hero_tal) else f'<talent id {tid}>'
        out.append(dict(talent=name, rank=f['rank'], pending=f['pending'], cap=f['cap'], base=f['base'], byte5=f['byte5']))
    return sorted(out, key=lambda t: str(t['talent']))


def _hero_old(env, era, item_era, stats_index, h):
    a, eq = h['attributes'], h['equipment']
    d = dict(hero=_era_name(env, era, 'STAT', 'STAT', stats_index), level=a['level'], experience=eq['experience'],
             traits=[[a['trait_base'][i], a['trait_pending'][i], a['trait_bonus'][i], a['trait_bonus2'][i]] for i in range(4)],
             skill_points=a['skill_points'], trait_points=a['trait_points'], ai=[a['ai_level'], a['ai_attack']],
             talents=_talents_old(env, era, stats_index, a),
             equipped=[_instance_old(env, item_era, i) for i in eq['equipped']],
             vitals=[eq['vitals_valid'] & 1, round(eq['health'], 3), round(eq['energy'], 3), eq['player_seat']],
             counters=[eq['ack_level'], eq['health_boosts'], eq['energy_boosts'], eq['levels_purchased'], eq['points_bought'],
                       eq['respec_count'], eq['skirmish_boost'], eq['flags'] & 0x1f])
    return d


def _snapshot_old(env, era, s):
    objs = {}
    objv = era.table('OBJV')
    for i, st in enumerate(s['objectives']):
        if i < len(objv):
            objs[_name(env, 'OBJV', objv[i])] = [st & 0x3f, (st >> 6) & 3]
    seats = {}
    for i in range(4):
        if s['seat_names'][i]:
            pose = s['seat_pose'][i * 6:(i + 1) * 6]
            seats[str(i)] = dict(hero=s['seat_names'][i].lower(), position=[round(x, 3) for x in pose[:3]], orientation=[round(x, 3) for x in pose[3:]])
    return dict(zone=s['zone'].lower(), seats=seats, objectives=objs, anchor=[round(x, 3) for x in s['anchor_pos']] + [round(x, 3) for x in s['anchor_orient']])


def _bits(words, n):
    return [i for i in range(n) if words[i // 32] >> (i % 32) & 1]


def _zone_states_old(old, z):
    strings = old['zone_strings']
    out = []

    def st(idx, kind, ordinal):
        s = z['states'][idx]
        out.append(dict(list=kind, ordinal=ordinal, definition=oldsave.zone_string(strings, s['def_name']),
                        instance=oldsave.zone_string(strings, s['inst_name']), flags=[s['flags_a'], s['flags_b']],
                        position=list(s['position']), payload=s['payload'].hex()))
    for k in range(len(z['ordinal_map'])):                # the record's own ordinal map (its native layout's size)
        if z['ordinal_map'][k]:
            st(z['ordinal_map'][k], 1, k + 1)
    for idx in z['dynamic'][:z['dynamic_count']]:
        st(idx, 2, 0)
    for idx in z['smart'][:z['smart_count']]:
        st(idx, 3, 0)
    return out


def dump_old(old, env, era_hint, *, native=False):
    """era_hint: dict(start=cv, items=cv) - the eras the converter chose (the dump reads positions with them)"""
    era_t = env.by_cv[era_hint['start']]
    era_i = env.by_cv[era_hint['items']]
    g = old['game']
    trivia_hashes = ({bit: key_hash(*env.binds.key_trivia(*position))
                      for position, bit in env.binds.trivia_bits.items()} if native else
                     {(int(a) - 1) * TRIVIA_PER_ACT + int(q): h
                      for k, h in env.ref['TRIV'].items() for a, q in [k.split(',')]})
    it = old['items']
    stat = era_t.table('STAT')
    d = {}
    d['description'] = old['description']
    d['game'] = dict(timer=[round(g['timer_threshold'], 3), round(g['timer_remaining'], 3), round(g['timer_after_add'], 3), round(g['timer_last_add'], 3), g['timer_script']],
                     recall=[g['recall_zone'].lower(), [round(x, 3) for x in g['recall_pos']] if g['recall_zone'].lower() not in ('', 'none') else None, round(g['recall_cooldown'], 3)],
                     xtreme=[g['xtreme_charges'], g['xtreme_pips']], loading_name=g['loading_name'], act=g['act'],
                     value_608=g['value_608'], difficulty=g['difficulty'], play_time=round(g['play_time'], 3),
                     potion=g['flags_d8'] & 3, counters=[(g['flags_d8'] >> 2) & 0x1f, g['flags_d9'] & 0x1f],
                     flags=((g['flags_d9'] >> 5) & 7) | ((g['flags_da'] & 0x7f) << 3),
                     trivia=sorted(_name(env, 'TRIV', trivia_hashes.get(b)) for b in _bits(g['trivia'], 250)))
    item_t = era_i.table('ITEM')
    d['items'] = dict(tech_bits=it['tech_bits'], health=it['health_items'], energy=it['energy_items'],
                      keys={KEY_ITEM_NAMES[i].lower(): it['key_counts'][i] for i in range(6)},
                      def_state={_name(env, 'ITEM', item_t[i]) if i < len(item_t) else f'<{i}>': [it['def_state'][2 * i], it['def_state'][2 * i + 1]]
                                 for i in range(L.OLD_DEF_STATE_PAIRS) if it['def_state'][2 * i] or it['def_state'][2 * i + 1]},
                      carried=[_instance_old(env, era_i, x) for x in it['carried']],
                      world={str(w['slot']): _instance_old(env, era_i, w['instance']) for w in it['world']})
    d['heroes'] = [_hero_old(env, era_t, era_i, n + 1, h) for n, h in enumerate(old['heroes'])]
    for h, oh in zip(d['heroes'], old['heroes']):
        h['powers'] = {str(i): dict(name=n, flags=f) for i, (n, f) in enumerate(zip(oh['powers'], oh['power_flags']))
                       if n or f != L.POWER_USABLE}
        h['costume'] = oh['costume']
        h['costumes_unlocked'] = [b for b in range(32) if oh['costume_mask'] >> b & 1]
    d['unlocked'] = [_era_name(env, era_t, 'STAT', 'STAT', i) for i in old['unlocked']['entries'][:old['unlocked']['count']]]
    d['restore'] = dict(valid=old['restore_flag'], records={str(n): _hero_old(env, era_t, era_i, n, r) for n, r in enumerate(old['restore'])
                                                             if r['attributes']['count'] or r['equipment']['equipped'] or r['equipment']['experience']})
    d['mission'] = _snapshot_old(env, era_t, old['mission'])
    d['side'] = [_snapshot_old(env, era_t, old['side']['frames'][i]) for i in range(old['side']['count'])]
    courses = {}
    for i, c in enumerate(old['danger_room']['courses']):
        cd = dict(c)
        for f in ('largest_hit_hero', 'least_damage_hero', 'most_health_packs_hero', 'most_energy_packs_hero', 'most_defeats_hero'):
            v = cd[f]
            cd[f] = None if v in (0, 0xffff) else _era_name(env, era_t, 'STAT', 'STAT', v)
        for f in ('tier0', 'tier1', 'tier2'):
            cd[f] &= 1
        courses[_name(env, 'DRCS', env.ref['DRCS'][i])] = cd
    d['danger_room'] = dict(courses=courses, grades={_name(env, 'DRGR', env.ref['DRGR'][i]): v for i, v in enumerate(old['danger_room']['grades'][:len(env.ref['DRGR'])])})
    d['review'] = {k: sorted(_name(env, 'REVW', env.ref['REVW'].get(f'{c},{i}')) for c in range(5) for i in _bits(old['review'][k][c * 3:c * 3 + 3], REVIEW_PER_CATEGORY))
                   for k in ('unlocked', 'seen')}
    zones = []
    for z in old['zones']:
        zones.append(dict(zone=oldsave.zone_string(old['zone_strings'], z['name_handle']).lower(), time_stamp=round(z['time_stamp'], 3), flag=z['flag'],
                          conversation=list(z['conversation']), fog=z['fog'].hex(), states=_zone_states_old(old, z)))
    d['zones'] = zones
    d['script_vars'] = {k: {v['name']: oldsave.script_var_value(v) for v in old['script_vars'][k] if v['name']} for k in ('zone', 'game')}
    d['town_centres'] = [_name(env, 'XPNT', env.ref['XPNT'][i]) if i < len(env.ref['XPNT']) else f'<{i}>' for i in _bits([old['town_centres']], 32)]
    p = old['profile']
    d['profile'] = dict(options=p['options'][0] | (p['options'][1] << 8) | (p['options'][2] << 16), name=p['player_name'],
                        scores=[dict(course=_name(env, 'DRCS', env.ref['DRCS'][s['course']]) if s['course'] < len(env.ref['DRCS']) else None,
                                     party_a=[_era_name(env, era_t, 'STAT', 'STAT', v) for v in s['party_a'][:s['count_a']]],
                                     party_b=[_era_name(env, era_t, 'STAT', 'STAT', v) for v in s['party_b'][:s['count_b']]], score=s['score'])
                                for s in p['high_scores'][:p['score_count']]],
                        characters=[_era_name(env, era_t, 'STAT', 'STAT', i) for i in _bits(p['char_unlock'], 297)],
                        review=sorted(_name(env, 'REVW', env.ref['REVW'].get(f'{c},{i}')) for c in range(5) for i in _bits(p['review'][c * 3:c * 3 + 3], REVIEW_PER_CATEGORY)),
                        highest_level=p['highest_level'], flags=p['flags_229'])
    return d


# ------------------------------------------------------------------------------------------------ new
def _idn(env, v):
    if not v:
        return None
    ent = env.catalogue.entry_of(v)
    if ent is None:
        return f'<unknown id {v:#x}>'
    tag, e = ent
    return _name(env, tag, e['hash'])


def _instance_new(env, r):
    d = dict(definition=_idn(env, r['definition']), location=r['location'], name_a=_idn(env, r['name_a']),
             name_b=_idn(env, r['name_b']), special=_idn(env, r['special']))
    for k in ('prefixes', 'own', 'suffixes'):
        d[k] = [[_idn(env, e['enhancement']), e['value']] for e in r[k]]
    return d


def _hero_new(env, h, owner_key='hero'):
    tr = h['traits']
    return dict(hero=_idn(env, h[owner_key]), level=h['level'], experience=h['experience'],
                traits=[tr[i * 4:i * 4 + 4] for i in range(4)], skill_points=h['skill_points'], trait_points=h['trait_points'],
                ai=[h['ai_level'], h['ai_attack']],
                talents=sorted([dict(talent=_idn(env, t['talent']), rank=t['rank'], pending=t['pending'], cap=t['cap'], base=t['base'], byte5=t['byte5']) for t in h['talents']], key=lambda t: str(t['talent'])),
                equipped=[_instance_new(env, i) for i in h['equipped']],
                vitals=[h['vitals_valid'], round(h['health'], 3), round(h['energy'], 3), h['player_seat']],
                counters=[h['ack_level'], h['health_boosts'], h['energy_boosts'], h['levels_purchased'], h['points_bought'], h['respec_count'], h['skirmish_boost'], h['flags']])


def _snapshot_new(env, s):
    return dict(zone=_idn(env, s['zone']) or '', seats={str(x['seat']): dict(hero=_idn(env, x['hero']), position=[round(v, 3) for v in x['position']], orientation=[round(v, 3) for v in x['orientation']]) for x in s['seats']},
                objectives={_idn(env, o['objective']): [o['counter'], o['flags']] for o in s['objectives']},
                anchor=[round(x, 3) for x in s['anchor_pos']] + [round(x, 3) for x in s['anchor_orient']])


def dump_new(buf, env):
    f = read_file(buf, L.KIND_CAMPAIGN)
    S = {t: f['sections'][t]['data'] for t in f['sections'] if f['sections'][t]['data'] is not None}
    G, I = S['GAME'], S['ITEM']
    d = {}
    d['description'] = S['META']['description']
    d['game'] = dict(timer=[round(G['timer_threshold'], 3), round(G['timer_remaining'], 3), round(G['timer_after_add'], 3), round(G['timer_last_add'], 3), G['timer_script']],
                     recall=[_idn(env, G['recall_zone']) or 'none', [round(x, 3) for x in G['recall_pos']] if G['recall_zone'] else None, round(G['recall_cooldown'], 3)],
                     xtreme=[G['xtreme_charges'], G['xtreme_pips']], loading_name=G['loading_name'], act=G['act'], value_608=G['value_608'],
                     difficulty=G['difficulty'], play_time=round(G['play_time'], 3), potion=G['team_potion'], counters=[G['counter_a'], G['counter_b']],
                     flags=G['flags'], trivia=sorted(_idn(env, v) for v in G['trivia']))
    d['items'] = dict(tech_bits=I['tech_bits'], health=I['health_items'], energy=I['energy_items'],
                      keys={_idn(env, e['item']): e['quantity'] for e in I['key_counts']},
                      def_state={_idn(env, e['item']): [e['quantity'], e['flag']] for e in I['def_state']},
                      carried=[_instance_new(env, x) for x in I['instances']],
                      world={str(w['handle']): _instance_new(env, w['instance']) for w in I['world']})
    heroes = []
    for h in S['HERO']['heroes']:
        hd = _hero_new(env, h)
        hd['powers'] = {str(p['button']): dict(name=p['name'], flags=p.get('flags', L.POWER_USABLE)) for p in h['powers']
                        if p['name'] or p.get('flags', L.POWER_USABLE) != L.POWER_USABLE}
        hd['costume'] = _costume_slot(env, h['costume'])
        hd['costumes_unlocked'] = sorted(_costume_slot(env, v) for v in h['costumes_unlocked'])
        heroes.append(hd)
    d['heroes'] = heroes
    d['unlocked'] = [_idn(env, v) for v in S['ULCK']['unlocked']]
    d['restore'] = dict(valid=S['REST']['bank_valid'], records={str(env.binds.stat.index(_idn(env, r['owner']))) if env.binds else _idn(env, r['owner']): _hero_new(env, r, 'owner') for r in S['REST']['records']})
    snaps = S['MISS']['snapshots']
    d['mission'] = _snapshot_new(env, snaps[0])
    d['side'] = [_snapshot_new(env, s) for s in snaps[1:]]
    courses = {}
    for c in S['DNGR']['courses']:
        cd = dict(flags=c['flags'], tier0=c['tiers'][0], tier1=c['tiers'][1], tier2=c['tiers'][2], largest_hit=c['largest_hit'],
                  least_damage=c['least_damage'], best_time=c['best_time'], best_combo=c['best_combo'], most_health_packs=c['most_health_packs'],
                  most_energy_packs=c['most_energy_packs'], most_defeats=c['most_defeats'])
        for fld in ('largest_hit_hero', 'least_damage_hero', 'most_health_packs_hero', 'most_energy_packs_hero', 'most_defeats_hero'):
            cd[fld] = _idn(env, c[fld])
        courses[_idn(env, c['course'])] = cd
    d['danger_room'] = dict(courses=courses, grades={_idn(env, g['grade']): g['value'] for g in S['DNGR']['grades']})
    d['review'] = {k: sorted(_idn(env, v) for v in S['REVW'][k]) for k in ('unlocked', 'seen')}
    zones = []
    for z in S['ZONE']['records']:
        states = []
        for s in z['states']:
            if s['payload_kind'] == 2:
                slot, qty = struct.unpack('<Ii', s['payload'][:8])
                payload = (bytes([slot]) + struct.pack('<h', qty) + s['payload'][8:13]).hex()
            else:
                payload = s['payload'].hex()
            states.append(dict(list=s['list'], ordinal=s['ordinal'], definition=z['names'][s['def_name']], instance=z['names'][s['inst_name']],
                               flags=[s['flags_a'], s['flags_b']], position=[int(x) for x in s['position']], payload=payload))
        zones.append(dict(zone=_idn(env, z['zone']), time_stamp=round(z['time_stamp'], 3), flag=z['flag'], conversation=z['conversation'],
                          fog=z['fog']['data'].hex(), states=states))
    d['zones'] = zones
    d['script_vars'] = {k: {v['name']: v['value'] for v in S['SVAR'][k + '_vars']} for k in ('zone', 'game')}
    d['town_centres'] = [_idn(env, v) for v in S['XTRC']['unlocked']]
    O, P, Sc = S['PRFO'], S['PRFP'], S['PRFS']
    d['profile'] = dict(options=O['options'], name=O['player_name'],
                        scores=[dict(course=_idn(env, s['course']), party_a=[_idn(env, v) for v in s['party_a']], party_b=[_idn(env, v) for v in s['party_b']], score=s['score']) for s in Sc['scores']],
                        characters=[_idn(env, v) for v in P['characters']], review=sorted(_idn(env, v) for v in P['review']),
                        highest_level=P['highest_level'], flags=P['flags'])
    d['lgcy'] = {k: (v.hex() if isinstance(v, bytes) else v) for k, v in S['LGCY'].items()} if 'LGCY' in S else None
    return d


def _costume_slot(env, v):
    n = _idn(env, v)
    if n is None or '/' not in n:
        return n
    attr = n.split('/', 1)[1]
    from .binds import COSTUME_SLOTS
    return 0 if attr == 'skin' else COSTUME_SLOTS.get(attr[5:], n)


def dump_any(buf, env):
    if buf[:8] == L.NEW_MAGIC:
        return dump_new(buf, env)
    old = oldsave.read_slot(buf)
    from .convert import convert_slot
    r = convert_slot(buf, 'x', env)
    hint = r.era if not r.refused else dict(start=13, items=13)
    return dump_old(old, env, hint)


# ------------------------------------------------------------------------------------------------ diff
def semantic_diff(a, b, path='', out=None, zones_as_sets=True):
    """-> list of differences; zone states compared as multisets without ordinals"""
    out = [] if out is None else out
    if path == '.zones' and zones_as_sets and isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f'{path}: {len(a)} vs {len(b)} records')
        for i, (x, y) in enumerate(zip(a, b)):
            for k in x:
                if k == 'states':
                    sa = sorted(_state_key(s) for s in x['states'])
                    sb = sorted(_state_key(s) for s in y['states'])
                    if sa != sb:
                        missing = [s for s in sa if s not in sb]
                        extra = [s for s in sb if s not in sa]
                        out.append(f'{path}[{i}].states: {len(x["states"])} vs {len(y["states"])}; not carried {missing[:3]}; added {extra[:3]}')
                elif x[k] != y.get(k):
                    out.append(f'{path}[{i}].{k}: differ')
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k == 'lgcy':
                continue
            if k not in a or k not in b:
                out.append(f'{path}.{k}: only in {"old" if k in a else "new"}')
            else:
                semantic_diff(a[k], b[k], f'{path}.{k}', out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f'{path}: length {len(a)} vs {len(b)}')
        for i, (x, y) in enumerate(zip(a, b)):
            semantic_diff(x, y, f'{path}[{i}]', out)
    elif a != b:
        out.append(f'{path}: {a!r:.80} vs {b!r:.80}')
    return out


def _state_key(s):
    return (s['list'], s['definition'], s['instance'], tuple(s['flags']), tuple(int(x) for x in s['position']), s['payload'])
