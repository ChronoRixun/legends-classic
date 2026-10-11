"""The one-time converter (SPEC-new-save 5, revision 2.2): old slot file -> LC campaign file, and the reverse
reader (LC campaign -> old model) that the tests and the fix's loader design use.

Rules implemented (and the number of the spec rule): fail closed on anything inconsistent (5.4 steps 1-4), era
detection (legacy.py), park what the catalogue cannot name (D4 / 3.6: here nothing is unknown to the catalogue by
construction, so "park" means "refuse" for an index outside its era table), D6 (one mapping through the era
model), D7 (party positions carried), D8 (no inference of renames: the catalogue is complete for every era),
D12 (declared limits: the old caps), LGCY record per file.
"""
from __future__ import annotations

import copy
import hashlib
import os
import struct
import time

from . import layout as L
from . import oldsave
from .binds import Binds, KEY_ITEM_NAMES, TRIVIA_PER_ACT, REVIEW_PER_CATEGORY, COSTUME_SLOT_COUNT
from .catalogue import Catalogue
from .container import write_file, read_file, SECTION_FLAGS, SECTION_MINOR, CAMPAIGN_SECTIONS
from .keys import key_hash, make_id, DOMAIN_NUMBER, id_domain, DOMAINS, canonical_key
from .legacy import load_eras, eras_of, talent_era, zone_record_eras, CONTENT_TO_RELEASE
from . import CONVERTER_VERSION

WRITER_KIND_PYTHON = 1
ORIGIN_CONVERTED = 1
MISSION_FLAG_POSITIONS = 1
MISSION_FLAG_ANCHOR = 2
IDENTITY_MODE_ORDINAL = 2
STATE_NUMBERED, STATE_DYNAMIC, STATE_SMART = 1, 2, 3
PAYLOAD_ENGINE, PAYLOAD_WORLD_ITEM = 1, 2
FOG_ENCODING_ENGINE = 1
FOG_SIDE = 82
DEFAULT_RESTORE_ATTR = dict(trait_base=[1, 1, 1, 1], trait_pending=[0] * 4, trait_bonus=[0] * 4, trait_bonus2=[0] * 4,
                            skill_points=0, trait_points=0, level=1, ai_level=1, ai_attack=0, pad17=0, bitmap=0, count=0)
DEFAULT_RESTORE_TAIL = dict(health=0.0, energy=0.0, player_seat=-1, vitals_valid=0, pad0d=[0, 0, 0], experience=0,
                            ack_level=1, health_boosts=0, energy_boosts=0, levels_purchased=0, points_bought=0,
                            respec_count=0, skirmish_boost=0, flags=0)
ITEM_POOLS = (375, 512)          # enhancement record pools of XML2 Fix before / from 1.3.0 (the item table cut)


class ConvertError(ValueError):
    """the file is refused; the message names what a player can act on"""


class Environment:
    """what a conversion needs: the era model, the catalogue, and (for names, zones and KEYS) the player's build"""

    def __init__(self, build=None, eras_path=None, catalogue_path=None):
        self.model = load_eras(eras_path) if eras_path else load_eras()
        self.eras = eras_of(self.model)                        # newest first
        self.by_cv = {e.cv: e for e in self.eras}
        self.ref = self.model['reference']
        from .conversations import historical_tables
        self.conversation_tables = historical_tables(self.model)
        self.catalogue = Catalogue.load(catalogue_path) if catalogue_path else Catalogue.load()
        self.binds = Binds(build) if build else None
        if self.binds:
            from .conversations import current_tables
            self.conversation_tables.update(current_tables(self.binds.build, self.binds.all_zone_files()))
        self._names = {}
        if self.binds:
            for tag, hashes in _name_index(self.binds).items():
                self._names[tag] = hashes

    def id_of(self, tag, hash_hex):
        v = self.catalogue.lookup(tag, hash_hex) if hash_hex else None
        return v

    def name_of(self, tag, hash_hex):
        name = self._names.get(tag, {}).get(hash_hex)
        return name.replace('%2f', '/').replace('%25', '%') if name is not None else None


def _name_index(b):
    """{domain: {key hash: canonical key text}} from the build's names (for KEYS and dumps)"""
    out = {t: {} for t in DOMAIN_NUMBER}

    def put(tag, fields):
        if fields and all(f is not None for f in fields):
            out[tag][key_hash(*fields)] = canonical_key(*fields).decode('cp1252')
    for i in range(len(b.stat)):
        put('STAT', b.key_stat(i))
    for i in range(len(b.item)):
        put('ITEM', b.key_item(i))
    for i in range(len(b.enhancement)):
        put('ENHC', b.key_enh(i))
    for i in range(len(b.name_a)):
        put('NAMA', b.key_name_a(i))
    for c, lst in b.name_b.items():
        for i in range(len(lst)):
            put('NAMB', b.key_name_b(c, i))
    for i in range(len(b.trit)):
        put('TRIT', b.key_trit(i))
    for n in b.shared_talent:
        put('TALN', ('shared', n))
    for h, lst in b.hero_talent.items():
        for n in lst:
            put('TALN', (h, n))
    for h in b.costume:
        for s in range(9):
            put('COST', b.key_costume(h, s))
    for f in b.mission_file:
        put('MSNF', (f,))
    for i in range(len(b.objective)):
        put('OBJV', b.key_objective(i))
    for i in range(len(b.course)):
        put('DRCS', b.key_course(i))
    for i in range(len(b.grade)):
        put('DRGR', b.key_grade(i))
    for (c, i) in b.review:
        put('REVW', b.key_review(c, i))
    for i in range(len(b.xpoint)):
        put('XPNT', b.key_xpoint(i))
    for (a, i) in b.trivia:
        put('TRIV', b.key_trivia(a, i))
    for z in b.zone_names:
        put('ZONE', (z,))
    return out


class Result:
    def __init__(self):
        self.file_bytes = None
        self.refused = None
        self.notes = []          # human-readable decisions and drops
        self.dropped = {'zone_records': 0, 'world_items': 0, 'zone_vars': 0, 'other': 0, 'talents': 0, 'states': 0}
        self.era = {}
        self.parked = 0

    def summary(self):
        return (f'start era {self.era.get("start")} items era {self.era.get("items")}; dropped {self.dropped}; '
                f'{len(self.notes)} notes')

    def report(self):
        return dict(refused=self.refused, era=self.era, dropped=self.dropped, notes=self.notes)


# ------------------------------------------------------------------------------------------------ helpers
def _id(env, res, tag, hash_hex, what):
    v = env.id_of(tag, hash_hex)
    if v is None:
        raise ConvertError(f'{what}: no catalogue entry (key hash {hash_hex[:12] if hash_hex else None}); the save names '
                           f'something no builder release ever shipped')
    return v


def _era_list(env, era, domain, index, what):
    t = era.table(domain)
    if not 0 <= index < len(t) or t[index] is None:
        raise ConvertError(f'{what}: position {index} is outside the {domain} table of builder {era.release} '
                           f'({len(t)} entries)')
    return t[index]


def it_instances(old):
    """every item instance of an old save with a label: carried, world, equipped, restore"""
    it = old['items']
    for i, inst in enumerate(it['carried']):
        yield f'carried item {i}', inst
    for i, w in enumerate(it['world']):
        yield f'world item {i}', w['instance']
    for n, h in enumerate(old['heroes']):
        for i, inst in enumerate(h['equipment']['equipped']):
            yield f'hero block {n} equipped item {i}', inst
    for n, r in enumerate(old['restore']):
        for i, inst in enumerate(r['equipment']['equipped']):
            yield f'restore record {n} equipped item {i}', inst


def _instance_keys(env, res, era, inst, what, world=False):
    """old instance -> INST record (ids); the own-record cross-check (5.4 step 4)"""
    d = inst['definition']
    item_hash = _era_list(env, era, 'ITEM', d, f'{what}: definition index')
    rec = dict(definition=_id(env, res, 'ITEM', item_hash, f'{what}: item'))
    for name in ('name_a', 'name_b', 'special'):
        v = inst[name]
        if v == 0xff:
            rec[name] = 0
        elif name == 'name_a':
            rec[name] = _id(env, res, 'NAMA', _era_list(env, era, 'NAMA', v, f'{what}: item name A'), what)
        elif name == 'name_b':
            cls = era.table('ITEM_class')[d]
            lst = era.table('NAMB').get(cls or '', [])
            if not 0 <= v < len(lst):
                raise ConvertError(f'{what}: item name B position {v} outside the {cls!r} list')
            rec[name] = _id(env, res, 'NAMB', lst[v], what)
        else:
            rec[name] = _id(env, res, 'TRIT', _era_list(env, era, 'TRIT', v, f'{what}: special item'), what)
    rec['location'] = inst['location']
    for lst in ('prefixes', 'own', 'suffixes'):
        rec[lst] = []
        for e in inst[lst]:
            r = e['record']
            if r & 0x8000:
                raise ConvertError(f'{what}: negative enhancement record {r}')
            h = _era_list(env, era, 'ENHC', r, f'{what}: {lst} enhancement record')
            rec[lst].append(dict(enhancement=_id(env, res, 'ENHC', h, what), value=e['value']))
    _cross_check_instance(env, era, inst, what)
    return rec


def _cross_check_instance(env, era, inst, what):
    """every prefix record is a prefix, every suffix a suffix, every own record belongs to the instance's
    definition or its special item (the mapping check of SPEC 5.4 step 4; data from the era's binds hashes)"""
    ranges = era.table('ENHC_ranges')
    plo, phi = ranges['prefix']; slo, shi = ranges['suffix']
    for e in inst['prefixes']:
        if not plo <= e['record'] < phi:
            raise ConvertError(f'{what}: prefix enhancement record {e["record"]} is not a prefix in builder {era.release}')
    for e in inst['suffixes']:
        if not slo <= e['record'] < shi:
            raise ConvertError(f'{what}: suffix enhancement record {e["record"]} is not a suffix in builder {era.release}')
    own_tables = era.table('ITEM_own')
    allowed = set(own_tables[inst['definition']]) if inst['definition'] < len(own_tables) else set()
    if inst['special'] != 0xff:
        trit_own = era.table('TRIT_own')
        if inst['special'] < len(trit_own):
            allowed |= set(trit_own[inst['special']])
    for e in inst['own']:
        if e['record'] not in allowed:
            raise ConvertError(f'{what}: own enhancement record {e["record"]} does not belong to definition '
                               f'{inst["definition"]} in builder {era.release} (the item table of another release?)')


def _hero_record(env, res, era, item_era, block_index, stats_index, h, what):
    a, eq = h['attributes'], h['equipment']
    stat_hash = _era_list(env, era, 'STAT', stats_index, f'{what}: stats index')
    rec = dict(hero=_id(env, res, 'STAT', stat_hash, what))
    traits = []
    for i in range(4):
        traits += [a['trait_base'][i], a['trait_pending'][i], a['trait_bonus'][i], a['trait_bonus2'][i]]
    rec.update(traits=traits, skill_points=a['skill_points'], trait_points=a['trait_points'], level=a['level'],
               ai_level=a['ai_level'], ai_attack=a['ai_attack'])
    talents = []
    hero_tal = era.table('TALN_hero').get(stat_hash, [])
    for e in a['talents'][:a['count']]:
        tid = e['id']
        f = oldsave.talent_fields(e)
        if tid < 100:
            t = era.table('TALN_shared')
            if tid >= len(t):
                res.dropped['talents'] += 1
                res.notes.append(f'{what}: shared talent id {tid} beyond the {len(t)}-entry table of builder {era.release}: dropped')
                continue
            h_ = t[tid]
        else:
            owner = tid // 100 - 1
            pos = tid % 100
            if owner != stats_index:
                res.dropped['talents'] += 1
                res.notes.append(f'{what}: talent id {tid} belongs to stats index {owner}, not this hero: dropped')
                continue
            if pos >= len(hero_tal):
                res.dropped['talents'] += 1
                res.notes.append(f'{what}: talent position {pos} beyond the hero talent file ({len(hero_tal)}): dropped')
                continue
            h_ = hero_tal[pos]
        talents.append(dict(talent=_id(env, res, 'TALN', h_, what), rank=f['rank'], pending=f['pending'], cap=f['cap'],
                            base=f['base'], byte5=f['byte5']))
    rec['talents'] = talents
    rec['equipped'] = [_instance_keys(env, res, item_era, inst, f'{what}: equipped item {i}') for i, inst in enumerate(eq['equipped'])]
    rec.update(vitals_valid=eq['vitals_valid'] & 1, health=eq['health'], energy=eq['energy'], player_seat=eq['player_seat'],
               experience=eq['experience'], ack_level=eq['ack_level'], health_boosts=eq['health_boosts'],
               energy_boosts=eq['energy_boosts'], levels_purchased=eq['levels_purchased'], points_bought=eq['points_bought'],
               respec_count=eq['respec_count'], skirmish_boost=eq['skirmish_boost'], flags=eq['flags'] & 0x1f)
    if not -1 <= eq['player_seat'] <= 3:
        raise ConvertError(f'{what}: player seat {eq["player_seat"]} is not -1..3')
    return rec


def power_records(names, flags):
    """`PWR` records (SPEC 2.6, HERO minor 1) of a hero block's four slots: button, name and the whole flag byte (bit 0
    = usable, the other bits carried). A slot is listed when it has a name or its flag byte is not 1; an empty usable
    slot is left out and reads back as one (all 6888 slots of the 82 corpus saves have a name and the byte 1)."""
    return [dict(button=i, name=n, flags=f) for i, (n, f) in enumerate(zip(names, flags)) if n or f != L.POWER_USABLE]


def _hero_full(env, res, era, item_era, block_index, stats_index, h, what):
    rec = _hero_record(env, res, era, item_era, block_index, stats_index, h, what)
    rec['powers'] = power_records(h['powers'], h['power_flags'])
    stat_hash = era.table('STAT')[stats_index]
    cost = era.table('COST').get(stat_hash, {})
    slot = h['costume']
    if str(slot) not in cost:
        raise ConvertError(f'{what}: costume slot {slot} is not a slot the engine knows (0..8)')
    rec['costume'] = _id(env, res, 'COST', cost[str(slot)], what)
    unlocked = []
    mask = h['costume_mask']
    for bit in range(32):
        if mask >> bit & 1:
            if str(bit) in cost:
                unlocked.append(_id(env, res, 'COST', cost[str(bit)], what))
            else:
                res.dropped['other'] += 1
                res.notes.append(f'{what}: costume mask bit {bit} has no slot: dropped')
    rec['costumes_unlocked'] = unlocked
    return rec


def _is_default_restore(r):
    a = {k: v for k, v in r['attributes'].items() if k != 'talents'}
    t = {k: v for k, v in r['equipment'].items() if k != 'equipped'}
    return (a == DEFAULT_RESTORE_ATTR and t == DEFAULT_RESTORE_TAIL and not r['equipment']['equipped']
            and all(not any(e.values()) for e in r['attributes']['talents']))


def _snapshot(env, res, era, s, what, positions_valid=True):
    zone_hash = key_hash(s['zone']) if s['zone'] else None
    rec = dict(zone=_id(env, res, 'ZONE', zone_hash, f'{what}: zone {s["zone"]!r}') if s['zone'] else 0)
    seats = []
    for i in range(4):
        n = s['seat_names'][i]
        if not n:
            continue
        stat_hash = key_hash(n)
        hero = env.id_of('STAT', stat_hash)
        if hero is None:
            raise ConvertError(f'{what}: seat {i} names a character no builder release ever had ({n!r})')
        pose = s['seat_pose'][i * 6:(i + 1) * 6]
        seats.append(dict(seat=i, hero=hero, position=pose[:3], orientation=pose[3:]))
    rec['seats'] = seats
    objs = []
    objv = era.table('OBJV')
    for i, st in enumerate(s['objectives']):
        if i < len(objv):
            objs.append(dict(objective=_id(env, res, 'OBJV', objv[i], what), counter=st & 0x3f, flags=(st >> 6) & 3))
        elif st:
            raise ConvertError(f'{what}: objective index {i} has state but builder {era.release} registers only {len(objv)}')
    rec['objectives'] = objs
    rec['anchor_pos'] = s['anchor_pos']
    rec['anchor_orient'] = s['anchor_orient']
    flags = (MISSION_FLAG_POSITIONS if positions_valid else 0) | (MISSION_FLAG_ANCHOR if any(s['anchor_pos']) else 0)
    rec['flags'] = flags
    return rec


def _bits(words, n_bits):
    return [i for i in range(n_bits) if words[i // 32] >> (i % 32) & 1]


# ------------------------------------------------------------------------------------------------ zones
def _zone_record(env, res, old, z, index, candidate_eras, what, captures=None, require_capture_metadata=False):
    """old zone record -> ZREC, or None (dropped, reason noted). Needs the build (names, numbering)."""
    strings = old['zone_strings']
    zone = oldsave.zone_string(strings, z['name_handle']).lower()
    if env.binds is None:
        raise ConvertError('zone records need the build (--build) to verify their entities')
    matches = [c for c in (captures or []) if c['zone'].lower() == zone and c['time_stamp'] == z['time_stamp']]
    if len(matches) > 1:
        raise ConvertError(f'{what}: duplicate capture metadata')
    capture = matches[0] if matches else None
    if require_capture_metadata and capture is None:
        raise ConvertError(f'{what}: missing observed capture metadata')
    if capture and (capture['capture_flags'] & ~3 or capture['capture_flags'] & 1):
        raise ConvertError(f'{what}: unsupported or incomplete capture')
    zone_hash = key_hash(zone)
    zid = env.id_of('ZONE', zone_hash)
    if zid is None:
        res.notes.append(f'{what}: zone {zone!r} unknown to every release: record dropped')
        return None
    num = env.binds.zone_numbering(zone)
    if num is None or num['problems']:
        res.notes.append(f'{what}: zone {zone!r}: no placement file in the build or its numbering cannot be modelled '
                         f'({num["problems"] if num else "missing"}): record dropped')
        return None
    ref_hashes = [(key_hash(t), key_hash(n)) for t, n, _ in num['numbered']]
    names_by_ordinal = {}
    for k in range(1, L.OLD_ZONE_ORDINALS + 1):
        idx = z['ordinal_map'][k - 1]
        if idx:
            s = z['states'][idx]
            names_by_ordinal[k] = (key_hash(oldsave.zone_string(strings, s['def_name'])),
                                   key_hash(oldsave.zone_string(strings, s['inst_name'])))
    eras = candidate_eras[:1] if capture else zone_record_eras(names_by_ordinal, zone_hash, candidate_eras, ref_hashes)
    if not eras:
        res.notes.append(f'{what}: zone {zone!r}: no builder release numbers its {len(names_by_ordinal)} numbered '
                         f'entities as the record does: record dropped (the zone starts fresh)')
        return None
    era = eras[0]
    delta = era.zone_map(zone_hash)
    names = ['']
    name_index = {'': 0}

    def name_text(t):
        if t not in name_index:
            name_index[t] = len(names); names.append(t)
        return name_index[t]
    def nm(handle): return name_text(oldsave.zone_string(strings, handle))
    states = []
    world_handles = {w['slot'] for w in old['items']['world']}

    def state_rec(s, kind, ordinal=0, placement=0):
        p = s['payload']
        rec = dict(list=kind, entity_tag=0, ordinal=ordinal, placement_index=placement, def_name=nm(s['def_name']),
                   inst_name=nm(s['inst_name']), flags_a=s['flags_a'], flags_b=s['flags_b'],
                   position=[float(x) for x in s['position']])
        if s['flags_a'] & 1:
            slot = p[0]
            qty = struct.unpack('<h', p[1:3])[0]
            if slot not in world_handles:
                # Native factory 0x465c35 checks numbered alive bit 8 before
                # virtual item restore. Retain the removed placement without
                # a stale item payload the engine will never read.
                if captures is not None and kind == STATE_NUMBERED and not (s['flags_b'] & 8):
                    rec.update(flags_a=0, payload_kind=PAYLOAD_ENGINE, payload=bytes(8))
                    res.notes.append(f'{what}: dead numbered item slot {slot}: removed placement retained without stale item reference (native load skips item restore)')
                    return rec
                # Native item restore tolerates absent slots. Omit only unnumbered ghosts;
                # live numbered identity loss and the historical importer drop policy stay strict.
                if captures is not None and kind != STATE_NUMBERED:
                    res.notes.append(f'{what}: dangling world item slot {slot}: unnumbered item state omitted (native load has no item instance)')
                    return None
                res.dropped['states'] += 1
                res.notes.append(f'{what}: a state owns world item slot {slot} that the item section does not list: dropped')
                return None
            rec['payload_kind'] = PAYLOAD_WORLD_ITEM
            rec['payload'] = struct.pack('<Ii', slot, qty) + p[3:8]
        else:
            rec['payload_kind'] = PAYLOAD_ENGINE
            rec['payload'] = p
        return rec
    for k in sorted(names_by_ordinal):
        if delta is None or capture:
            ref_k = k
        else:
            m, ambiguous = delta
            ref_k = m[k - 1] if k <= len(m) else 0
            if k in ambiguous or ref_k == 0:
                res.dropped['states'] += 1
                res.notes.append(f'{what}: zone {zone!r} ordinal {k}: the entity has no unambiguous counterpart in the '
                                 f'build (builder {era.release} numbering): state dropped')
                continue
        if capture:
            entities = [e for e in capture['entities'] if e['ordinal'] == k]
            if len(entities) != 1 or (key_hash(entities[0]['definition_name']), key_hash(entities[0]['instance_name'])) != names_by_ordinal[k]:
                raise ConvertError(f'{what}: captured entity association missing or differs')
            placement = entities[0]['placement_index']
        else:
            t, n, placement = num['numbered'][ref_k - 1]
        r = state_rec(z['states'][z['ordinal_map'][k - 1]], STATE_NUMBERED, ref_k, placement)
        if r:
            states.append(r)
    if capture:
        ordinals, placements = set(), set()
        for e in capture['entities']:
            ordinal, placement = e['ordinal'], e['placement_index']
            if not 1 <= ordinal <= L.OLD_ZONE_ORDINALS or ordinal in ordinals or placement in placements:
                raise ConvertError(f'{what}: invalid or duplicate observed entity association')
            ordinals.add(ordinal); placements.add(placement)
            if not z['ordinal_map'][ordinal - 1]:
                states.append(dict(list=1, entity_tag=0, ordinal=ordinal, placement_index=placement,
                    def_name=name_text(e['definition_name']), inst_name=name_text(e['instance_name']), flags_a=0, flags_b=0,
                    position=[0., 0., 0.], payload_kind=1, payload=bytes(8)))
    for idx in z['dynamic'][:z['dynamic_count']]:
        r = state_rec(z['states'][idx], STATE_DYNAMIC)
        if r:
            states.append(r)
    for idx in z['smart'][:z['smart_count']]:
        r = state_rec(z['states'][idx], STATE_SMART)
        if r:
            states.append(r)
    if len(states) >= L.OLD_ZONE_STATES: raise ConvertError('capture identities exceed native state capacity')
    digest = era.conversation_digest or ('0' * 64)
    capture_digest = capture['conversation_digest'] if capture else bytes.fromhex(digest)
    if capture is None and captures is not None:
        from .conversations import zone_digest
        capture_digest = bytes.fromhex(zone_digest(env.binds.build, zone))
    rec = dict(zone=zid, identity_mode=IDENTITY_MODE_ORDINAL, content_hash=capture['placement_sha1'] if capture else bytes.fromhex(num['sha1']),
               time_stamp=z['time_stamp'], flag=z['flag'], capture_flags=capture['capture_flags'] if capture else 2, conversation=list(z['conversation']),
               conversation_digest=capture_digest, names=names, states=states,
               fog=dict(encoding=FOG_ENCODING_ENGINE, width=FOG_SIDE, height=FOG_SIDE, data=z['fog']))
    res.era.setdefault('zones', []).append(dict(zone=zone, era=era.cv, numbered=len(names_by_ordinal),
                                                dynamic=z['dynamic_count'], smart=z['smart_count']))
    return rec, era


# XML1 campaign directories reached only after the first mansion's HAARP departure.
# Do not use act, hero unlocks, tour completion, training or flashback zones as progress.
_FORGE_LATER_DIRS = (
    'haarp/ext/', 'haarp/int/', 'haarp/ice_sq/',
    'mansion/man2/', 'mansion/man3/', 'mansion/man4/', 'mansion/man5/',
    'mansion/man6/', 'mansion/man7/', 'mansion/man8/',
    'muir_is/muir1/', 'muir_is/muir2/', 'muir_is/muir3/',
    'sewers/hub/', 'sewers/healer/', 'sewers/grso/', 'arbiter/deck/', 'arbiter/a_int/',
    'nuke_plant/nuke/', 'astral/ast1/', 'astral/ast3/', 'astral/savepx/',
    'weapon_x/old/', 'weapon_x/secret/', 'mount/mount/', 'nyc/riots/',
    'hive/h_ext/', 'hive/h_int/', 'astroid_m/visit1/', 'mastermold/',
)
_FORGE_IMPORT_NOTE = 'Forge contact unlock granted (0.1.x builds did not record it)'


def _legacy_forge_recovery(old, env, res, game_vars):
    # Zone names are carried directly by every supported native era, independently of
    # objective numbering. A retained record/return frame proves progress in a hub too.
    zones = [old['mission']['zone']]
    zones += [s['zone'] for s in old['side']['frames'][:old['side']['count']]]
    zones += [oldsave.zone_string(old['zone_strings'], z['name_handle']) for z in old['zones']]
    if not any((z.lower().startswith(_FORGE_LATER_DIRS) or z.lower() in ('arbiter/arb_fd1', 'arbiter/arb_fd2')) and env.id_of('ZONE', key_hash(z)) is not None for z in zones):
        return
    target = next((v for v in game_vars if v['name'].lower() == 'x1v03'), None)
    if target is None:
        if len(game_vars) >= L.OLD_SCRIPT_GAME_VARS:
            raise ConvertError('Forge contact unlock: game-variable store is full')
        target = dict(name='x1v03', value=0)
        game_vars.append(target)
    # Script bit indices are ONE based: ftalk at bit 31 is mask 0x40000000.
    if not target['value'] & 0x40000000:
        target['value'] |= 0x40000000
        res.notes.append(_FORGE_IMPORT_NOTE)


# ------------------------------------------------------------------------------------------------ main
def convert_slot(old_bytes, original_name, env, slot=0, now=None, campaign_serial=None):
    res = Result()
    try:
        old = oldsave.read_slot(old_bytes)
        sections = _translate(old, env, res, original_name, old_bytes, slot, now)
        sections = add_keys_section(sections, env)
        header = dict(writer_version=(CONVERTER_VERSION[0] << 24) | (CONVERTER_VERSION[1] << 16) | (CONVERTER_VERSION[2] << 8) | WRITER_KIND_PYTHON,
                      content_version=env.model['reference'].get('content_version', 0),
                      catalogue_revision=env.catalogue.revision,
                      campaign_serial=campaign_serial if campaign_serial is not None else int.from_bytes(hashlib.sha1(old_bytes).digest()[:8], 'little'),
                      save_sequence=1)
        res.file_bytes = write_file(L.KIND_CAMPAIGN, sections, header)
        read_file(res.file_bytes, L.KIND_CAMPAIGN)        # the writer re-reads its own output (1.6 step 1)
    except (oldsave.OldSaveError, ConvertError, ValueError) as e:
        res.refused = str(e)
    return res


def _translate(old, env, res, original_name, old_bytes, slot, now=None, context=None):
    # ---- fingerprint (5.4 step 3)
    ref = env.ref
    nheroes = len(old['heroes'])
    eras_ok = [e for e in env.eras if e.hero_count == nheroes]
    if not eras_ok:
        raise ConvertError(f'{nheroes} hero blocks; no builder release has that many ({ {e.hero_count for e in env.eras} })')
    live_courses = len(old['danger_room']['courses'])
    if live_courses != len(ref['DRCS']):
        raise ConvertError(f'{live_courses} live Danger Room courses; the builder releases have {len(ref["DRCS"])} '
                           f'(a developer build with another course table?)')
    # ---- eras
    start_era, ev = talent_era(old, eras_ok, ref['STAT'])
    res.era['start'] = start_era.cv
    res.era['start_release'] = start_era.release
    res.era['talent_evidence'] = ev
    if ev['unexplained']:
        res.notes.append(f'{len(ev["unexplained"])} shared talent ranks are talents the hero cannot hold in any release '
                         f'(kept under builder {start_era.release} names): {ev["unexplained"][:6]}')
    # items: the era whose table the definition count byte fits (the engine wrote the live count: the table cut
    # by the enhancement pool of the XML2 Fix in use) and whose own-record ranges every instance agrees with
    counts = _counts_by_era(env)
    item_eras = [e for e in eras_ok if old['items']['def_count'] in counts[e.cv]]
    if not item_eras:
        raise ConvertError(f'definition count byte {old["items"]["def_count"]} matches no builder release '
                           f'(expected one of { {CONTENT_TO_RELEASE[cv]: sorted(c) for cv, c in counts.items()} })')
    all_instances = list(it_instances(old))
    era_items = None
    reasons = []
    for e in item_eras:                               # newest first
        try:
            for what, inst in all_instances:
                _cross_check_instance(env, e, inst, what)
            era_items = e
            break
        except ConvertError as x:
            reasons.append(f'{e.release}: {x}')
    if era_items is None:
        raise ConvertError('the inventory agrees with no builder release: ' + '; '.join(reasons[:3]))
    res.era['items'] = era_items.cv
    res.era['items_release'] = era_items.release
    res.era['items_evidence'] = (f'definition count {old["items"]["def_count"]} fits {[e.release for e in item_eras]}; '
                                 f'own-record check passes on {era_items.release}')
    # zone records: each record names its own era by the entity names it stores
    zone_recs = []
    for i, z in enumerate(old['zones']):
        out = _zone_record(env, res, old, z, i, eras_ok, f'zone record {i}', (context or {}).get('zone_captures'), (context or {}).get('require_capture_metadata', False))
        if out is None:
            res.dropped['zone_records'] += 1
            continue
        rec, era = out
        zone_recs.append(rec)
    writer_era = era_items
    era_tal = start_era
    # ---- META
    g = old['game']
    desc = old['description']
    mission = old['mission']
    cur_zone = mission['zone'].lower()
    sections = []
    cur_zone_id = env.id_of('ZONE', key_hash(cur_zone)) if cur_zone else 0
    if cur_zone and cur_zone_id is None:
        raise ConvertError(f'current zone {cur_zone!r} is unknown to every builder release')
    saved_at = int((now if now is not None else time.time()) * 10_000_000) + 11644473600 * 10_000_000   # FILETIME
    sections.append(('META', 1, 0, SECTION_FLAGS['META'], dict(
        saved_at=saved_at, description=desc, origin=ORIGIN_CONVERTED, zone=cur_zone_id, act=g['act'],
        difficulty=g['difficulty'], play_time=g['play_time'], writer=f'lcsave {".".join(map(str, CONVERTER_VERSION))}',
        slot=slot, mods=[])))
    # ---- GAME
    trivia = []
    native_trivia = {v: k for k, v in env.binds.trivia_bits.items()} if context is not None else None
    for bit in _bits(g['trivia'], 250):
        if native_trivia is not None:
            if bit not in native_trivia:
                raise ConvertError(f'native trivia bit {bit} names no question in this build')
            act, q = native_trivia[bit]
        else:
            act, q = bit // TRIVIA_PER_ACT + 1, bit % TRIVIA_PER_ACT
        h = ref['TRIV'].get(f'{act},{q}')
        if h is None:
            raise ConvertError(f'trivia bit {bit} (act {act} question {q + 1}) names a question no release has')
        trivia.append(_id(env, res, 'TRIV', h, 'trivia'))
    recall = g['recall_zone'].lower()
    recall_id = 0
    if recall and recall != 'none':
        recall_id = env.id_of('ZONE', key_hash(recall))
        if recall_id is None:
            raise ConvertError(f'recall zone {recall!r} is unknown to every builder release')
    d8, d9, da = g['flags_d8'], g['flags_d9'], g['flags_da']
    flags = ((d9 >> 5) & 7) | (((da) & 0x7f) << 3)
    sections.append(('GAME', 1, 0, 0, dict(
        timer_threshold=g['timer_threshold'], timer_remaining=g['timer_remaining'], timer_after_add=g['timer_after_add'],
        timer_last_add=g['timer_last_add'], timer_script=g['timer_script'], recall_cooldown=g['recall_cooldown'],
        xtreme_charges=g['xtreme_charges'], xtreme_pips=g['xtreme_pips'], loading_name=g['loading_name'],
        recall_zone=recall_id, recall_pos=list(g['recall_pos']) if recall_id else [0.0, 0.0, 0.0], act=g['act'],
        value_608=g['value_608'], difficulty=g['difficulty'], play_time=g['play_time'], team_potion=d8 & 3,
        counter_a=(d8 >> 2) & 0x1f, counter_b=d9 & 0x1f, flags=flags, trivia=trivia)))
    # ---- ITEM
    it = old['items']
    item_table = era_items.table('ITEM')
    def_state = []
    for i in range(L.OLD_DEF_STATE_PAIRS):
        q, f = it['def_state'][2 * i], it['def_state'][2 * i + 1]
        if q or f:
            if i >= len(item_table):
                raise ConvertError(f'definition state pair {i} is beyond the item table of builder {era_items.release}')
            def_state.append(dict(item=_id(env, res, 'ITEM', item_table[i], 'definition state'), quantity=q, flag=f))
    key_counts = []
    for i, n in enumerate(KEY_ITEM_NAMES):
        h = key_hash(n)
        v = env.id_of('ITEM', h)
        if v is None:
            raise ConvertError(f'key item {n} is not in the catalogue')
        key_counts.append(dict(item=v, quantity=it['key_counts'][i], flag=0))
    instances = [_instance_keys(env, res, era_items, inst, f'carried item {i}') for i, inst in enumerate(it['carried'])]
    world = []
    for i, w in enumerate(it['world']):
        world.append(dict(handle=w['slot'], instance=_instance_keys(env, res, era_items, w['instance'], f'world item {i}')))
    sections.append(('ITEM', 1, 0, 0, dict(tech_bits=it['tech_bits'], health_items=it['health_items'],
                                           energy_items=it['energy_items'], def_state=def_state, key_counts=key_counts,
                                           instances=instances, world=world)))
    # ---- HERO
    heroes = [_hero_full(env, res, era_tal, era_items, n, n + 1, h, f'hero block {n}') for n, h in enumerate(old['heroes'])]
    sections.append(('HERO', 1, SECTION_MINOR['HERO'], 0, dict(heroes=heroes)))
    # ---- ULCK
    stat = era_tal.table('STAT')
    unlocked = []
    for i in old['unlocked']['entries'][:old['unlocked']['count']]:
        if not 0 <= i < len(stat) or stat[i] is None:
            raise ConvertError(f'unlocked character index {i} is outside the stats table ({len(stat)})')
        unlocked.append(_id(env, res, 'STAT', stat[i], 'unlocked character'))
    sections.append(('ULCK', 1, 0, 0, dict(unlocked=unlocked)))
    # ---- REST
    records = []
    for n, r in enumerate(old['restore']):
        if _is_default_restore(r):
            continue
        rec = _hero_record(env, res, era_tal, era_items, n, n, r, f'restore record {n}') if n > 0 else None
        if rec is None:
            res.dropped['other'] += 1
            res.notes.append('restore record 0 (the reserved stats entry) is not default: dropped')
            continue
        rec = dict(owner=rec.pop('hero'), **rec)
        records.append(rec)
    sections.append(('REST', 1, 0, 0, dict(bank_valid=old['restore_flag'], records=records)))
    # ---- MISS
    snaps = [_snapshot(env, res, era_tal, mission, 'mission state')]
    for i in range(old['side']['count']):
        snaps.append(_snapshot(env, res, era_tal, old['side']['frames'][i], f'side-mission frame {i}'))
    sections.append(('MISS', 1, 0, 0, dict(stack_depth=old['side']['count'], snapshots=snaps)))
    # ---- DNGR
    courses = []
    for i, c in enumerate(old['danger_room']['courses']):
        rec = dict(course=_id(env, res, 'DRCS', ref['DRCS'][i], 'course'), flags=c['flags'],
                   tiers=bytes([c['tier0'] & 1, c['tier1'] & 1, c['tier2'] & 1]), largest_hit=c['largest_hit'],
                   least_damage=c['least_damage'], best_time=c['best_time'], best_combo=c['best_combo'],
                   most_health_packs=c['most_health_packs'], most_energy_packs=c['most_energy_packs'],
                   most_defeats=c['most_defeats'])
        for f in ('largest_hit_hero', 'least_damage_hero', 'most_health_packs_hero', 'most_energy_packs_hero', 'most_defeats_hero'):
            v = c[f]
            if v in (0, 0xffff):
                rec[f] = 0
            elif v < len(stat) and stat[v]:
                rec[f] = _id(env, res, 'STAT', stat[v], f'course {i} {f}')
            else:
                raise ConvertError(f'course {i}: {f} index {v} is outside the stats table')
        courses.append(rec)
    grades = [dict(grade=_id(env, res, 'DRGR', ref['DRGR'][i], 'grade'), value=v)
              for i, v in enumerate(old['danger_room']['grades'][:len(ref['DRGR'])])]
    sections.append(('DNGR', 1, 0, 0, dict(courses=courses, grades=grades)))
    # ---- REVW
    def review_ids(words):
        out = []
        for c in range(5):
            for i in _bits(words[c * 3:c * 3 + 3], REVIEW_PER_CATEGORY):
                h = ref['REVW'].get(f'{c},{i}')
                if h is None:
                    raise ConvertError(f'Review bit (category {c}, entry {i}) names an entry no release has')
                out.append(_id(env, res, 'REVW', h, 'review'))
        return out
    sections.append(('REVW', 1, 0, 0, dict(unlocked=review_ids(old['review']['unlocked']), seen=review_ids(old['review']['seen']))))
    # ---- ZONE
    newest = max([z['time_stamp'] for z in zone_recs], default=0.0)
    sections.append(('ZONE', 1, 0, 0, dict(newest_time=newest, container_flag=0, records=zone_recs)))
    # ---- SVAR
    sv = old['script_vars']
    zone_vars = [dict(name=v['name'], value=oldsave.script_var_value(v)) for v in sv['zone'] if v['name']]
    game_vars = [dict(name=v['name'], value=oldsave.script_var_value(v)) for v in sv['game'] if v['name']]
    if context is None:
        _legacy_forge_recovery(old, env, res, game_vars)
    sections.append(('SVAR', 1, 0, 0, dict(zone_vars=zone_vars, game_vars=game_vars)))
    # ---- XTRC
    xp = []
    for i in _bits([old['town_centres']], 32):
        if i >= len(ref['XPNT']):
            raise ConvertError(f'town centre bit {i} beyond the extraction-point table ({len(ref["XPNT"])})')
        xp.append(_id(env, res, 'XPNT', ref['XPNT'][i], 'town centre'))
    sections.append(('XTRC', 1, 0, 0, dict(unlocked=xp)))
    # ---- profile
    sections += profile_sections(old['profile'], env, res, era_tal)
    # ---- LGCY
    sections.append(('LGCY', 1, 0, SECTION_FLAGS['LGCY'], dict(
        original_name=original_name, original_size=len(old_bytes), sha1=hashlib.sha1(old_bytes).digest(),
        start_era=start_era.cv, writer_era=era_items.cv, def_count_byte=it['def_count'],
        zone_records_dropped=res.dropped['zone_records'], world_items_dropped=res.dropped['world_items'],
        zone_vars_dropped=res.dropped['zone_vars'], other_dropped=res.dropped['other'] + res.dropped['talents'] + res.dropped['states'],
        notes=list(res.notes))))
    return sections


def profile_sections(p, env, res, era):
    """the three profile sections from an old 0x228 profile block"""
    options = p['options'][0] | (p['options'][1] << 8) | (p['options'][2] << 16)
    out = [('PRFO', 1, 0, 0, dict(options=options, player_name=p['player_name']))]
    stat = era.table('STAT')
    ref = env.ref
    scores = []
    for s in p['high_scores'][:p['score_count']]:
        if s['course'] >= len(ref['DRCS']):
            raise ConvertError(f'high score names course position {s["course"]} beyond the table')

        def party(lst, n):
            ids = []
            for v in lst[:n]:
                if not 0 <= v < len(stat) or stat[v] is None:
                    raise ConvertError(f'high score participant index {v} is outside the stats table')
                ids.append(_id(env, res, 'STAT', stat[v], 'high score participant'))
            return ids
        scores.append(dict(course=_id(env, res, 'DRCS', ref['DRCS'][s['course']], 'high score'),
                           party_a=party(s['party_a'], s['count_a']), party_b=party(s['party_b'], s['count_b']), score=s['score']))
    out.append(('PRFS', 1, 0, 0, dict(scores=scores)))
    chars = []
    for i in _bits(p['char_unlock'], 297):
        if i >= len(stat) or stat[i] is None:
            raise ConvertError(f'profile unlock bit {i} is outside the stats table')
        chars.append(_id(env, res, 'STAT', stat[i], 'profile unlock'))
    review = []
    for c in range(5):
        for i in _bits(p['review'][c * 3:c * 3 + 3], REVIEW_PER_CATEGORY):
            h = ref['REVW'].get(f'{c},{i}')
            if h is None:
                raise ConvertError(f'profile Review bit (category {c}, entry {i}) names an entry no release has')
            review.append(_id(env, res, 'REVW', h, 'profile review'))
    out.append(('PRFP', 1, 0, 0, dict(highest_level=p['highest_level'], flags=p['flags_229'], characters=chars, review=review)))
    return out


def _counts_by_era(env):
    """{cv: {definition count the engine would load: pool}} per era from ITEM_own and the pre-item record count"""
    out = {}
    for era in env.eras:
        own = era.table('ITEM_own')
        pre = era.table('ENHC_ranges')['trit'][1]
        out[era.cv] = {}
        for pool in ITEM_POOLS:
            used, k = pre, 0
            for lst in own:
                if used + len(lst) > pool:
                    break
                used += len(lst); k += 1
            out[era.cv][k] = pool
    return out


# ------------------------------------------------------------------------------------------------ KEYS
def add_keys_section(sections, env):
    """append the KEYS documentation section (every catalogue id that occurs, with its key text from the build)"""
    if env.binds is None:
        return sections
    used = {}

    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    ids = set()

    def collect(schema_name, data):
        pass
    # ids are u32 values in fields typed 'id'; walk the section data with the schemas
    from .container import SECTIONS, RECORDS, PACKED

    def rec_ids(schema, data):
        for n, t in schema:
            if n not in data:
                continue
            v = data[n]
            if t == 'id':
                ids.add(v)
            elif t.startswith('list:'):
                et = t[5:]
                for x in v:
                    elem_ids(et, x)
            elif t.startswith('rec:') or t.startswith('packed:'):
                elem_ids(t, v)

    def elem_ids(et, x):
        if et == 'id':
            ids.add(x)
        elif et.startswith('rec:'):
            rec_ids(RECORDS[et[4:]], x)
        elif et.startswith('packed:'):
            rec_ids(PACKED[et[7:]], x)
    for tag, major, minor, flags, data in sections:
        head, lists = SECTIONS[tag]
        rec_ids(head, data)
        for name, et in lists:
            for x in data.get(name, []):
                elem_ids(et, x)
    keys = []
    for v in sorted(i for i in ids if i):
        ent = env.catalogue.entry_of(v)
        if ent is None:
            continue
        tag, e = ent
        text = env._names.get(tag, {}).get(e['hash'], '')
        keys.append(dict(id=v, domain=DOMAIN_NUMBER[tag], key=text))
    out = list(sections)
    out.insert(1, ('KEYS', 1, 0, SECTION_FLAGS['KEYS'], dict(keys=keys)))
    return out


# ------------------------------------------------------------------------------------------------ reverse
def power_slots(records):
    """the four power slots of a hero block (old 1.6 d) from its `PWR` records -> (names, flag bytes). A slot the
    file does not list is empty and usable (flag byte 1). A `PWR` record of a HERO 1.0 file (written before SPEC
    revision 2.3, by the 0.2.0 candidates only) has no flag byte: it is read as 1, the value of every slot of the 82
    corpus saves - without bit 0 the power-button handler (0x4fd4de) refuses the power."""
    names = [''] * 4
    flags = [L.POWER_USABLE] * 4
    for pw in records:
        names[pw['button']] = pw['name']
        flags[pw['button']] = pw.get('flags', L.POWER_USABLE)
    return names, flags


def reverse_slot(new_bytes, env, template=None):
    """LC campaign -> old model (the internal stream the fix's loader must feed the engine). Needs the build's
    binds (positions). `template`: the old model of the original file when known (pads and stale bytes); without
    it those bytes are zero. -> (old model, notes)"""
    f = read_file(new_bytes, L.KIND_CAMPAIGN)
    S = {t: f['sections'][t]['data'] for t in f['sections'] if f['sections'][t]['data'] is not None}
    b = env.binds
    if b is None:
        raise ConvertError('the reverse reader needs the build (--build)')
    pos = PositionTables(env)
    validate_native_sections(S, env)
    notes = []
    m = {}
    m['description'] = S['META']['description']
    m['begin_tag'] = f'[SAVEGAMEBEGIN: {m["description"]}]'
    m['end_tag'] = f'[SAVEGAMEEND: {m["description"]}]'
    G = S['GAME']
    recall = pos.zone_name(G['recall_zone']) if G['recall_zone'] else 'none'
    trivia = [0] * 8
    for v in G['trivia']:
        act, q = pos.trivia(v)
        bit = env.binds.trivia_bits[(act, q)]
        if not 0 <= bit < 250:
            raise ConvertError('trivia question outside native persistence range 0..249')
        trivia[bit // 32] |= 1 << (bit % 32)
    fl = G['flags']
    m['game'] = dict(timer_threshold=G['timer_threshold'], timer_remaining=G['timer_remaining'], timer_after_add=G['timer_after_add'],
                     timer_last_add=G['timer_last_add'], timer_script=G['timer_script'], recall_cooldown=G['recall_cooldown'],
                     xtreme_charges=G['xtreme_charges'], xtreme_pips=G['xtreme_pips'], loading_name=G['loading_name'],
                     recall_zone=recall, recall_pos=list(G['recall_pos']), act=G['act'], unused_a5=b'\0' * 6, pad_ab=0,
                     trivia=trivia, value_608=G['value_608'], difficulty=G['difficulty'], play_time=G['play_time'],
                     flags_d8=(G['team_potion'] & 3) | ((G['counter_a'] & 0x1f) << 2),
                     flags_d9=(G['counter_b'] & 0x1f) | ((fl & 7) << 5), flags_da=(fl >> 3) & 0x7f, pad_db=0)
    I = S['ITEM']
    ds = [0] * (2 * L.OLD_DEF_STATE_PAIRS)
    for e in I['def_state']:
        i = pos.item(e['item'])
        ds[2 * i] = e['quantity']; ds[2 * i + 1] = e['flag']
    keyc = [0] * 6
    for e in I['key_counts']:
        n = pos.item_name(e['item'])
        if n not in KEY_ITEM_NAMES: raise ConvertError('key counter definition is not a native key item')
        keyc[KEY_ITEM_NAMES.index(n)] = e['quantity']
    m['items'] = dict(def_count=len(b.item), def_state=ds, tech_bits=I['tech_bits'], health_items=I['health_items'],
                      energy_items=I['energy_items'], key_counts=keyc,
                      carried=[pos.instance(x) for x in I['instances']],
                      world=[dict(slot=w['handle'], instance=pos.instance(w['instance'])) for w in I['world']])
    heroes = []
    for h in S['HERO']['heroes']:
        hb = pos.hero_block(h)
        hb['powers'], hb['power_flags'] = power_slots(h['powers'])
        hb['powers_raw'] = None
        hb['power_pad'] = 0
        hb['costume'] = pos.costume_slot(h['costume'])
        mask = 0
        for v in h['costumes_unlocked']:
            mask |= 1 << pos.costume_slot(v)
        hb['costume_mask'] = mask
        heroes.append(hb)
    m['heroes'] = heroes
    ul = [0] * L.OLD_UNLOCKED_SLOTS
    for i, v in enumerate(S['ULCK']['unlocked']):
        ul[i] = pos.stat(v)
    m['unlocked'] = dict(entries=ul, count=len(S['ULCK']['unlocked']))
    m['restore_flag'] = S['REST']['bank_valid']
    rest = [_default_restore() for _ in range(L.OLD_RESTORE_RECORDS)]
    for r in S['REST']['records']:
        n = pos.stat(r['owner'])
        rr = pos.hero_block(dict(r, hero=r['owner']))
        rest[n] = dict(attributes=rr['attributes'], equipment=rr['equipment'])
    m['restore'] = rest
    snaps = [pos.snapshot(s) for s in S['MISS']['snapshots']]
    m['mission'] = snaps[0]
    frames = snaps[1:] + [_empty_snapshot() for _ in range(L.OLD_SIDE_FRAMES - len(snaps) + 1)]
    m['side'] = dict(frames=frames[:L.OLD_SIDE_FRAMES], pad_4d8=0, count=S['MISS']['stack_depth'])
    courses = []
    by_course = {pos.course(c['course']): c for c in S['DNGR']['courses']}
    for i in range(len(b.course)):
        c = by_course.get(i)
        if c is None:
            courses.append(dict(flags=0, tier0=0, tier1=0, tier2=0, largest_hit=0, largest_hit_hero=0, least_damage=0,
                                least_damage_hero=0, best_time=0, best_combo=0, most_health_packs=0, most_health_packs_hero=0,
                                most_energy_packs=0, most_energy_packs_hero=0, most_defeats=0, most_defeats_hero=0))
            continue
        d = dict(flags=c['flags'], tier0=c['tiers'][0], tier1=c['tiers'][1], tier2=c['tiers'][2], largest_hit=c['largest_hit'],
                 least_damage=c['least_damage'], best_time=c['best_time'], best_combo=c['best_combo'],
                 most_health_packs=c['most_health_packs'], most_energy_packs=c['most_energy_packs'], most_defeats=c['most_defeats'])
        for fld in ('largest_hit_hero', 'least_damage_hero', 'most_health_packs_hero', 'most_energy_packs_hero', 'most_defeats_hero'):
            d[fld] = pos.stat(c[fld]) if c[fld] else 0
        courses.append(d)
    grades = [0] * L.OLD_DR_GRADES
    for g in S['DNGR']['grades']:
        grades[pos.grade(g['grade'])] = g['value']
    m['danger_room'] = dict(courses=courses, course_residue=[0] * (L.OLD_DR_COURSES - len(courses)), grades=grades)
    m['review'] = dict(unlocked=pos.review_words(S['REVW']['unlocked']), seen=pos.review_words(S['REVW']['seen']))
    zs, zones = pos.zone_records(S['ZONE']['records'], notes, m['items']['world'], S['META']['origin'] == 1)
    m['zone_strings'] = zs
    m['zones'] = zones
    m['profile'] = pos.profile(S)
    sv = {'zone': [], 'game': []}
    for kind, n in (('zone', L.OLD_SCRIPT_ZONE_VARS), ('game', L.OLD_SCRIPT_GAME_VARS)):
        lst = S['SVAR'][kind + '_vars']
        for v in lst:
            sv[kind].append(dict(name=v['name'], value_be=struct.pack('>I', v['value'])))
        while len(sv[kind]) < n:
            sv[kind].append(dict(name='', value_be=b'\0' * 4))
    m['script_vars'] = sv
    mask = 0
    for v in S['XTRC']['unlocked']:
        mask |= 1 << pos.xpoint(v)
    m['town_centres'] = mask
    if template is not None:
        _apply_template(m, template)
    try:
        oldsave.write_slot(m)  # verify all unmasked scalar widths and fixed layouts before exposing a native model
    except (ValueError, struct.error, OverflowError) as e:
        raise ConvertError(str(e)) from e
    return m, notes


def _default_restore():
    a = dict(DEFAULT_RESTORE_ATTR)
    a['trait_base'] = list(a['trait_base']); a['trait_pending'] = [0] * 4; a['trait_bonus'] = [0] * 4; a['trait_bonus2'] = [0] * 4
    a['talents'] = [dict(id=0, rank_bits=0, pending_cap_bits=0, base_bits=0, byte5=0, pad6=0) for _ in range(L.OLD_TALENT_ENTRIES)]
    t = dict(DEFAULT_RESTORE_TAIL); t['pad0d'] = [0, 0, 0]; t['equipped'] = []
    return dict(attributes=a, equipment=t)


def _empty_snapshot():
    return dict(zone='', seat_pose=[0.0] * 24, pad_a0=0, seat_names=['', '', '', ''], pad_124=0, objectives=[0] * 300,
                objective_301=0, pad_252=0, anchor_pos=[0.0] * 3, anchor_orient=[0.0] * 3)


def _apply_template(m, t):
    """copy the bytes the new format drops (pads, uninitialised and stale bytes) from the original's model, so
    that the reverse check compares only what is carried (SPEC 2.15 first table)"""
    m['description_raw'] = t.get('description_raw')
    for k in ('unused_a5', 'pad_ab', 'pad_db'):
        m['game'][k] = t['game'][k]
    for k in ('loading_name_raw', 'timer_script_raw', 'recall_zone_raw'):
        if k in t['game']:
            m['game'][k] = t['game'][k]
    if not m['game']['recall_zone'] or m['game']['recall_zone'] == 'none':
        m['game']['recall_pos'] = list(t['game']['recall_pos'])
    for h, th in zip(m['heroes'], t['heroes']):
        _template_block(h, th)
        h['powers_raw'] = th.get('powers_raw')
        h['power_pad'] = th.get('power_pad', 0)
    for r, tr in zip(m['restore'], t['restore']):
        _template_block(r, tr)
    for s, ts in zip([m['mission']] + m['side']['frames'], [t['mission']] + t['side']['frames']):
        for k in ('pad_a0', 'pad_124', 'objective_301', 'pad_252', 'zone_raw'):
            if k in ts:
                s[k] = ts[k]
        for i in range(4):
            if f'seat_name{i}_raw' in ts:
                s[f'seat_name{i}_raw'] = ts[f'seat_name{i}_raw']
    # stale side-mission frames above the count are not carried
    for i in range(m['side']['count'], L.OLD_SIDE_FRAMES):
        m['side']['frames'][i] = t['side']['frames'][i]
    m['side']['pad_4d8'] = t['side']['pad_4d8']
    m['danger_room']['course_residue'] = list(t['danger_room']['course_residue'])
    m['danger_room']['grades'][6:] = t['danger_room']['grades'][6:]
    m['review']['unlocked'][15] = t['review']['unlocked'][15]
    m['review']['seen'][15] = t['review']['seen'][15]
    m['items']['def_count'] = t['items']['def_count']
    m['profile']['pad_1b4'] = t['profile']['pad_1b4']; m['profile']['pad_220'] = t['profile']['pad_220']
    m['profile']['pad_22a'] = t['profile']['pad_22a']
    if 'player_name_raw' in t['profile']:
        m['profile']['player_name_raw'] = t['profile']['player_name_raw']
    for i in range(t['profile']['score_count'], L.OLD_HIGH_SCORES):
        m['profile']['high_scores'][i] = t['profile']['high_scores'][i]
    for i in range(t['profile']['score_count']):
        m['profile']['high_scores'][i]['pad1'] = t['profile']['high_scores'][i]['pad1']
    for i in range(t['unlocked']['count'], L.OLD_UNLOCKED_SLOTS):
        m['unlocked']['entries'][i] = t['unlocked']['entries'][i]
    for kind in ('zone', 'game'):
        for v, tv in zip(m['script_vars'][kind], t['script_vars'][kind]):
            if f'name_raw' in tv:
                v['name_raw'] = tv['name_raw']
            if not v['name']:
                v['value_be'] = tv['value_be']
    m['slack'] = t.get('slack')
    # zone records: the engine's state-record indices follow its capture order (world handles), which the new
    # format does not keep; the byte comparison therefore takes the original zone block and the semantic dump
    # (dump.py) compares the records' content
    m['zone_strings'] = t['zone_strings']
    m['zones'] = t['zones']
    m['begin_tag_raw'] = t.get('begin_tag_raw')
    m['end_tag_raw'] = t.get('end_tag_raw')


def _template_block(h, th):
    a, ta = h['attributes'], th['attributes']
    a['pad17'] = ta['pad17']
    for e, te in zip(a['talents'], ta['talents']):
        e['rank_bits'] = (e['rank_bits'] & 0x3f) | (te['rank_bits'] & 0xc0)
        e['base_bits'] = (e['base_bits'] & 3) | (te['base_bits'] & 0xfc)
        e['pad6'] = te['pad6']
    for i in range(a['count'], L.OLD_TALENT_ENTRIES):
        a['talents'][i] = dict(ta['talents'][i])
    a['bitmap'] = ta['bitmap']
    e, te = h['equipment'], th['equipment']
    e['pad0d'] = list(te['pad0d'])
    e['vitals_valid'] = te['vitals_valid']
    e['flags'] = (e['flags'] & 0x1f) | (te['flags'] & 0xe0)


def _validate_native_build(b):
    # Native installation budgets; reader ceilings remain unchanged (SPEC 2.16).
    budgets = ((len(b.item), 160, 'item definitions'), (b.hero_count, 21, 'hero records'),
               (len(b.stat), 297, 'stats slots including reserved zero'), (len(b.name_a), 32, 'flat names'),
               (len(b.trit), 128, 'special items'))
    for count, maximum, what in budgets:
        if count > maximum: raise ConvertError(f'native {what} budget exceeded ({maximum})')
    for names in b.name_b.values():
        if len(names) > 4: raise ConvertError('native category name budget exceeded (4)')
    for costumes in b.costume.values():
        if len(costumes) > 10 or any(slot < 0 or slot >= 10 for slot in costumes):
            raise ConvertError('native costume budget exceeded (10 slots)')


class PositionTables:
    """id -> position for the reverse direction (the build's binds through the catalogue)"""

    def __init__(self, env, *, hash_conversations=True):
        self.env = env
        from .lcfiles import CONVERSATION_LCM, read_conversation_lcm
        sidecar = os.path.join(env.binds.build, CONVERSATION_LCM)
        if os.path.isfile(sidecar):
            env.conversation_tables.update(read_conversation_lcm(open(sidecar, 'rb').read()))
        b = env.binds
        _validate_native_build(b)
        self.b = b
        cat = env.catalogue
        self._hash_conversations = hash_conversations
        T = b.hash_tables() if hash_conversations else b.hash_tables(include_conversation_digest=False)
        self._conversation_digest = T['conversation_digest']
        self._stat = {cat.lookup('STAT', h): i for i, h in enumerate(T['STAT']) if h}
        self._item = {cat.lookup('ITEM', h): i for i, h in enumerate(T['ITEM'])}
        self._enh = {cat.lookup('ENHC', h): i for i, h in enumerate(T['ENHC'])}
        self._nama = {cat.lookup('NAMA', h): i for i, h in enumerate(T['NAMA'])}
        self._namb = {cat.lookup('NAMB', h): i for lst in T['NAMB'].values() for i, h in enumerate(lst)}
        self._trit = {cat.lookup('TRIT', h): i for i, h in enumerate(T['TRIT'])}
        self._tal = {cat.lookup('TALN', h): i for i, h in enumerate(T['TALN_shared'])}
        for hh, lst in T['TALN_hero'].items():
            si = next(i for i, h in enumerate(T['STAT']) if h == hh)
            for p, h in enumerate(lst):
                self._tal[cat.lookup('TALN', h)] = (si + 1) * 100 + p
        self._cost = {cat.lookup('COST', h): int(s) for d in T['COST'].values() for s, h in d.items()}
        self._obj = {cat.lookup('OBJV', h): i for i, h in enumerate(T['OBJV'])}
        self._course = {cat.lookup('DRCS', h): i for i, h in enumerate(T['DRCS'])}
        self._grade = {cat.lookup('DRGR', h): i for i, h in enumerate(T['DRGR'])}
        self._review = {cat.lookup('REVW', h): tuple(int(x) for x in k.split(',')) for k, h in T['REVW'].items()}
        self._xp = {cat.lookup('XPNT', h): i for i, h in enumerate(T['XPNT'])}
        self._triv = {cat.lookup('TRIV', h): tuple(int(x) for x in k.split(',')) for k, h in T['TRIV'].items()}
        self._zone = {cat.lookup('ZONE', key_hash(z)): z for z in b.zone_names}

    def _get(self, table, v, what):
        if v not in table:
            raise ConvertError(f'{what}: id {v:#x} is not in this build (parked / unknown)')
        return table[v]

    def _native(self, value, low, high, what):
        if not low <= value <= high: raise ConvertError(f'native {what} index outside {low}..{high}')
        return value

    def stat(self, v): return self._native(self._get(self._stat, v, 'character'), 1, 296, 'stats')
    def item(self, v): return self._native(self._get(self._item, v, 'item'), 0, 159, 'item definition')
    def item_name(self, v): return self.b.item[self.item(v)]
    def course(self, v): return self._get(self._course, v, 'course')
    def grade(self, v): return self._get(self._grade, v, 'grade')
    def xpoint(self, v): return self._get(self._xp, v, 'town centre')
    def trivia(self, v): return self._get(self._triv, v, 'trivia')
    def zone_name(self, v): return self._get(self._zone, v, 'zone')
    def costume_slot(self, v): return self._native(self._get(self._cost, v, 'costume'), 0, 9, 'costume')

    def instance(self, r):
        inst = dict(definition=self.item(r['definition']), name_a=self._native(self._get(self._nama, r['name_a'], 'item name'), 0, 31, 'flat name') if r['name_a'] else 0xff,
                    name_b=self._native(self._get(self._namb, r['name_b'], 'item name'), 0, 3, 'category name') if r['name_b'] else 0xff,
                    special=self._native(self._get(self._trit, r['special'], 'special item'), 0, 127, 'special item') if r['special'] else 0xff, location=r['location'])
        for lst in ('prefixes', 'own', 'suffixes'):
            inst[lst] = [dict(record=self._get(self._enh, e['enhancement'], 'enhancement'), value=e['value']) for e in r[lst]]
        if r['name_b']:
            category = self.b.item_class[inst['definition']]
            hashes = (self.b.hash_tables() if self._hash_conversations else self.b.hash_tables(include_conversation_digest=False))['NAMB'].get(category or '', [])
            allowed = {self.env.id_of('NAMB', h) for h in hashes}
            if r['name_b'] not in allowed: raise ConvertError('item name category does not match definition')
        return inst

    def hero_block(self, h):
        tr = h['traits']
        a = dict(trait_base=tr[0::4], trait_pending=tr[1::4], trait_bonus=tr[2::4], trait_bonus2=tr[3::4],
                 skill_points=h['skill_points'], trait_points=h['trait_points'], level=h['level'], ai_level=h['ai_level'],
                 ai_attack=h['ai_attack'], pad17=0)
        ents = []
        for t in h['talents']:
            tid = self._get(self._tal, t['talent'], 'talent')
            ents.append(dict(id=tid, rank_bits=t['rank'] & 0x3f, pending_cap_bits=(t['pending'] & 0x3f) | ((t['cap'] & 3) << 6),
                             base_bits=t['base'] & 3, byte5=t['byte5'], pad6=0))
        ents.sort(key=lambda e: e['id'])
        if len(ents) > L.OLD_TALENT_ENTRIES:
            raise ConvertError(f'{len(ents)} talents do not fit the engine heap of {L.OLD_TALENT_ENTRIES}')
        a['count'] = len(ents)
        a['bitmap'] = (1 << len(ents)) - 1
        while len(ents) < L.OLD_TALENT_ENTRIES:
            ents.append(dict(id=0, rank_bits=0, pending_cap_bits=0, base_bits=0, byte5=0, pad6=0))
        a['talents'] = ents
        eq = dict(equipped=[self.instance(x) for x in h['equipped']], health=h['health'], energy=h['energy'],
                  player_seat=h['player_seat'], vitals_valid=h['vitals_valid'], pad0d=[0, 0, 0], experience=h['experience'],
                  ack_level=h['ack_level'], health_boosts=h['health_boosts'], energy_boosts=h['energy_boosts'],
                  levels_purchased=h['levels_purchased'], points_bought=h['points_bought'], respec_count=h['respec_count'],
                  skirmish_boost=h['skirmish_boost'], flags=h['flags'] & 0x1f)
        if len(eq['equipped']) > 3:
            raise ConvertError('more than 3 equipped items do not fit the engine')
        return dict(attributes=a, equipment=eq)

    def snapshot(self, s):
        out = _empty_snapshot()
        out['zone'] = self.zone_name(s['zone']) if s['zone'] else ''
        for seat in s['seats']:
            i = seat['seat']
            out['seat_names'][i] = self.b.stat[self.stat(seat['hero'])].lower()   # the engine writes them lower-case (all 82 corpus saves)
            out['seat_pose'][i * 6:i * 6 + 3] = seat['position']
            out['seat_pose'][i * 6 + 3:i * 6 + 6] = seat['orientation']
        for o in s['objectives']:
            i = self._get(self._obj, o['objective'], 'objective')
            out['objectives'][i] = (o['counter'] & 0x3f) | ((o['flags'] & 3) << 6)
        out['anchor_pos'] = list(s['anchor_pos']); out['anchor_orient'] = list(s['anchor_orient'])
        return out

    def review_words(self, ids):
        words = [0] * 16
        for v in ids:
            c, i = self._get(self._review, v, 'review entry')
            words[c * 3 + i // 32] |= 1 << (i % 32)
        return words

    def profile(self, S):
        O, P, Sc = S['PRFO'], S['PRFP'], S['PRFS']
        p = dict(options=[O['options'] & 0xff, (O['options'] >> 8) & 0xff, (O['options'] >> 16) & 0xff], player_name=O['player_name'])
        scores = []
        for s in Sc['scores']:
            a = [self.stat(v) for v in s['party_a']]; bb = [self.stat(v) for v in s['party_b']]
            scores.append(dict(course=self.course(s['course']), pad1=[0, 0, 0], party_a=a + [0] * (6 - len(a)), count_a=len(a),
                               party_b=bb + [0] * (6 - len(bb)), count_b=len(bb), score=s['score']))
        while len(scores) < L.OLD_HIGH_SCORES:
            scores.append(dict(course=0, pad1=[0, 0, 0], party_a=[0] * 6, count_a=0, party_b=[0] * 6, count_b=0, score=0))
        p['high_scores'] = scores
        p['pad_1b4'] = 0; p['score_count'] = len(Sc['scores'])
        words = [0] * 10
        for v in P['characters']:
            i = self.stat(v); words[i // 32] |= 1 << (i % 32)
        p['char_unlock'] = words
        p['review'] = self.review_words(P['review'])[:15]
        p['pad_220'] = 0; p['highest_level'] = P['highest_level']; p['flags_229'] = P['flags']; p['pad_22a'] = [0, 0]
        return p

    def conversation_words(self, r, zone, notes):
        from .conversations import remap, zone_bits, package_digest
        words = list(r['conversation'])
        recorded = r['conversation_digest'].hex()
        if not any(words): return words
        target = zone_bits(self.b.build, zone)
        current = package_digest(key_hash(zone), target)
        if recorded == current: return words
        source = self.env.conversation_tables.get((recorded, key_hash(zone)))
        if source is None:
            notes.append(f'zone {zone}: conversation provenance unknown: heard marks dropped')
            return [0] * 5
        try: return remap(words, source, target, zone, notes)
        except ValueError as e: raise ConvertError(str(e)) from e

    def zone_records(self, recs, notes, world, legacy_import=False):
        """Refill native zone layouts and remove world handles owned exclusively by discarded records."""
        strings = dict(generation=0, offsets=[0] * L.OLD_ZONE_STRING_SLOTS, used=2, arena=bytearray(L.OLD_ZONE_ARENA))
        strings['offsets'][0] = 1
        interned = {}
        def dependencies(record):
            return {struct.unpack('<I', s['payload'][:4])[0] for s in record['states'] if s['payload_kind'] == PAYLOAD_WORLD_ITEM}
        owned = {h for r in recs for h in dependencies(r)}
        applied = set()

        def intern(text):
            if text == '':
                return 0
            if text in interned:
                return interned[text]
            raw = text.encode('cp1252')
            slot = (_hash_string(raw) & 0x7ff) or 1
            while strings['offsets'][slot]:
                slot = (slot + 1) & 0x7ff or 1
            off = strings['used']
            if off + len(raw) + 1 > L.OLD_ZONE_ARENA:
                raise ConvertError('zone string arena full')
            strings['arena'][off:off + len(raw) + 1] = raw + b'\0'
            strings['offsets'][slot] = off
            strings['used'] = off + len(raw) + 1
            interned[text] = slot
            return slot
        zones = []
        for r in recs:
            zone = self.zone_name(r['zone'])
            num = self.b.zone_numbering(zone)
            if num is None:
                raise ConvertError(f'zone {zone!r} has no placement file in this build')
            if r['identity_mode'] != IDENTITY_MODE_ORDINAL:
                raise ConvertError('identity mode 1 (entity tags) is not implemented by the reverse reader')
            if r['capture_flags'] & 2: notes.append(f'zone {zone!r}: legacy capture provenance inferred (unknown completeness)')
            if r['capture_flags'] & ~3:
                raise ConvertError('unsupported capture status bits')
            if r['capture_flags'] & 1:
                notes.append(f'zone {zone!r}: incomplete capture: record not applied')
                continue
            if r['content_hash'] != bytes.fromhex(num['sha1']):
                notes.append(f'zone {zone!r}: placement file changed since the record was made: record not applied')
                continue
            mapped = {}
            for state in r['states']:
                if state['list'] != STATE_NUMBERED:
                    continue
                matches = [k + 1 for k, (dn, inn, pi) in enumerate(num['numbered']) if pi == state['placement_index'] and
                           key_hash(dn) == key_hash(r['names'][state['def_name']]) and key_hash(inn) == key_hash(r['names'][state['inst_name']])]
                if len(matches) != 1:
                    notes.append(f'zone {zone!r}: entity placement/name changed: record not applied')
                    break
                mapped[state['ordinal']] = matches[0]
            else:
                matches = None
            if matches is not None:
                continue
            promoted = _legacy_pinned_states(r, num['numbered'], set(mapped.values()), legacy_import)
            states = [dict(def_name=0, inst_name=0, payload=b'\0' * 8, flags_a=0, flags_b=0, position=[0, 0, 0])]
            ordinal_map = [0] * L.OLD_ZONE_ORDINALS
            dynamic, smart = [], []
            for state_index, s in enumerate(r['states']):
                if len(states) >= L.OLD_ZONE_STATES:
                    raise ConvertError('more states than the engine record holds')
                if s['payload_kind'] == PAYLOAD_WORLD_ITEM:
                    slot, qty = struct.unpack('<Ii', s['payload'][:8])
                    if slot > 0xff or not -32768 <= qty <= 32767:
                        raise ConvertError('world item handle / quantity do not fit the engine record')
                    payload = bytes([slot]) + struct.pack('<h', qty) + s['payload'][8:13]
                else:
                    payload = s['payload'][:8]
                posi = [int(round(x)) for x in s['position']]
                idx = len(states)
                states.append(dict(def_name=intern(r['names'][s['def_name']]), inst_name=intern(r['names'][s['inst_name']]),
                                   payload=payload, flags_a=s['flags_a'] & 0xff, flags_b=s['flags_b'] & 0xff, position=posi))
                if s['list'] == STATE_NUMBERED:
                    k = mapped[s['ordinal']]
                    if not 1 <= k <= L.OLD_ZONE_ORDINALS:
                        raise ConvertError(f'ordinal {k} outside the engine map')
                    if k > len(num['numbered']):
                        raise ConvertError(f'ordinal {k} beyond the zone numbering ({len(num["numbered"])})')
                    ordinal_map[k - 1] = idx
                elif state_index in promoted:
                    k = promoted[state_index]
                    if not 1 <= k <= L.OLD_ZONE_ORDINALS:
                        raise ConvertError('promoted ordinal outside the engine map')
                    ordinal_map[k - 1] = idx
                    states[idx]['flags_b'] |= 8  # an unnumbered list entry proves existence, even while dormant
                    notes.append(f'zone {zone!r}: legacy unnumbered state restored as numbered placement {k}')
                elif s['list'] == STATE_DYNAMIC:
                    dynamic.append(idx)
                else:
                    smart.append(idx)
            while len(states) < L.OLD_ZONE_STATES:
                states.append(dict(def_name=0, inst_name=0, payload=b'\0' * 8, flags_a=0, flags_b=0, position=[0, 0, 0]))
            z = dict(name_handle=intern(zone), states=states, pad_4804=0, state_count=1 + len(r['states']), ordinal_map=ordinal_map,
                     pad_4a0c=0, dynamic=dynamic + [0] * (L.OLD_ZONE_DYNAMIC - len(dynamic)), pad_4c68=0, dynamic_count=len(dynamic),
                     smart=smart + [0] * (L.OLD_ZONE_SMART - len(smart)), pad_5270=0, smart_count=len(smart),
                     fog=r['fog']['data'], conversation=self.conversation_words(r, zone, notes), time_stamp=r['time_stamp'], flag=r['flag'],
                     pad_55dd=[0, 0, 0])
            zones.append(z)
            applied.update(dependencies(r))
        # Shared handles and items not owned by any zone survive; rejected zones release exclusive dependencies.
        world[:] = [w for w in world if w['slot'] not in owned or w['slot'] in applied]
        strings['arena'] = bytes(strings['arena'])
        return strings, zones


def _hash_string(raw):
    h = 0
    for c in raw:
        h = (h * 31 + c) & 0xffffffff
    return h


# ------------------------------------------------------------------------------------------------ verification
def verify_file(old_path, env, out_dir=None):
    """convert one old file, re-read it, dump both and compare; reverse it into the reference build's stream and
    compare that too (SPEC 5.5 steps 2-3). -> report dict:
      semantic_diff      old dump (era tables) vs new dump (catalogue): must be empty
      reverse_identical  reverse(new) rebuilt the original bytes exactly (expected only when every era of the
                         save is the reference era and nothing was dropped or repaired)
      reverse_semantic   dump of the reversed stream (read as the reference era) vs the new dump: must be empty
      reverse_diff_fields the model fields that differ byte-wise (talent ids, definition indices that the era
                         mapping moved; zone blocks are compared through the dumps only)"""
    from .dump import dump_old, dump_new, semantic_diff
    buf = open(old_path, 'rb').read()
    name = os.path.basename(old_path)
    res = convert_slot(buf, name, env)
    rep = dict(file=old_path, refused=res.refused, era=res.era, dropped=res.dropped, notes=res.notes, ok=False)
    if res.refused:
        return rep
    old = oldsave.read_slot(buf)
    d_old = dump_old(old, env, era_hint=res.era)
    d_new = dump_new(res.file_bytes, env)
    # The maintained migration changes one script flag deliberately. Compare all
    # other semantics against the untouched old dump and disclose the repair.
    expected = copy.deepcopy(d_old)
    rep['legacy_repairs'] = [_FORGE_IMPORT_NOTE] if _FORGE_IMPORT_NOTE in res.notes else []
    if rep['legacy_repairs']:
        variables = expected['script_vars']['game']
        variable_name = next((n for n in variables if n.lower() == 'x1v03'), 'x1v03')
        variables[variable_name] = variables.get(variable_name, 0) | 0x40000000
    rep['semantic_diff'] = semantic_diff(expected, d_new)
    back, notes = reverse_slot(res.file_bytes, env, template=old)
    rep['reverse_notes'] = notes
    rebuilt = oldsave.write_slot(back)
    rep['reverse_identical'] = rebuilt == buf
    ref_cv = env.ref['content_version']
    rep['reverse_expected_identical'] = (res.era['start'] == ref_cv and res.era['items'] == ref_cv
                                         and all(z['era'] == ref_cv for z in res.era.get('zones', []))
                                         and not any(res.dropped.values()) and not rep['legacy_repairs']
                                         and old['game']['trivia'] == back['game']['trivia'])
    if not rep['reverse_identical']:
        rep['reverse_first_diff'] = next((i for i in range(len(buf)) if buf[i] != rebuilt[i]), None)
        rep['reverse_diff_fields'] = _diff_fields(old, back)
    d_back = dump_old(back, env, era_hint=dict(start=ref_cv, items=ref_cv), native=True)
    d_back['zones'] = d_new['zones']        # the reverse keeps the original zone block (indices are capture order)
    rep['reverse_semantic'] = semantic_diff(d_back, d_new)
    rep['ok'] = (not rep['semantic_diff'] and not rep['reverse_semantic']
                 and (rep['reverse_identical'] or not rep['reverse_expected_identical']))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        base = os.path.join(out_dir, name)
        open(base + '.lcsave', 'wb').write(res.file_bytes)
        import json
        json.dump(d_old, open(base + '.old.json', 'w'), indent=1, sort_keys=True)
        json.dump(d_new, open(base + '.new.json', 'w'), indent=1, sort_keys=True)
        json.dump(rep, open(base + '.report.json', 'w'), indent=1, default=str)
    return rep


def _diff_fields(a, b, path=''):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            out += _diff_fields(a.get(k), b.get(k), f'{path}.{k}')
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f'{path}: length {len(a)} vs {len(b)}')
        for i, (x, y) in enumerate(zip(a, b)):
            out += _diff_fields(x, y, f'{path}[{i}]')
    elif a != b:
        out.append(f'{path}: {a!r:.60} vs {b!r:.60}')
    return out[:40]


def verify_corpus(folder, env, out_dir):
    import glob
    results = {}
    for p in sorted(glob.glob(os.path.join(folder, '**', 'saveslot*.save'), recursive=True)):
        rel = os.path.relpath(p, folder).replace('\\', '/')
        sub = os.path.join(out_dir, os.path.dirname(rel))
        rep = verify_file(p, env, sub)
        if rep['refused']:
            status = 'refused: ' + rep['refused']
        elif rep['ok']:
            status = 'converted clean' if not any(rep['dropped'].values()) else f'converted with drops {rep["dropped"]}'
            status += ' (byte-exact reverse)' if rep['reverse_identical'] else ''
        else:
            status = (f'MISMATCH semantic={len(rep.get("semantic_diff", []))} reverse_semantic='
                      f'{len(rep.get("reverse_semantic", []))} reverse_identical={rep.get("reverse_identical")}')
        results[rel] = dict(status=status, era=rep.get('era'), notes=rep.get('notes'))
        print(rel, '->', status)
    return results

# Runtime/tool mirror of the native library's durable saver contract.
def _retain_sections(sections, retained_file, kind):
    if not retained_file:
        return sections
    prior = read_file(retained_file, kind)
    out = list(sections)
    opaque = False
    for tag in prior['order']:
        sec = prior['sections'][tag]; e = sec['entry']
        if tag == 'LGCY' or (sec['data'] is None and e['flags'] & L.SECTION_KEEP):
            out.append((tag, e['major'], e['minor'], e['flags'], dict(_opaque_payload=sec['payload'], _opaque_records=e['records'])))
            opaque |= sec['data'] is None
    if opaque:
        if 'KEYS' not in prior['sections']:
            raise ConvertError('opaque KEEP without KEYS contract cannot be resaved')
        old_keys = prior['sections']['KEYS']['data']
        if old_keys.get('_extra') or any(k.get('_extra') for k in old_keys['keys']):
            raise ConvertError('opaque KEEP with extended KEYS contract cannot be resaved')
        for tag, _, _, _, data in out:
            if tag == 'KEYS':
                prefix = list(prior['sections']['KEYS']['data']['keys'])
                data['keys'] = prefix + [k for k in data['keys'] if not any(all(k[n] == old[n] for n in ('id', 'domain', 'key')) for old in prefix)]
    return out


def _current_environment(env, *, hash_conversations=True):
    import copy
    from .legacy import Era
    _validate_native_build(env.binds)
    current = copy.copy(env)
    current.ref = env.binds.hash_tables() if hash_conversations else env.binds.hash_tables(include_conversation_digest=False)
    current.ref['content_version'] = env.catalogue.data.get('content_version', 0)
    cv = current.ref['content_version']
    current.model = dict(reference=current.ref, eras={str(cv): dict(hero_shared_holdable={})})
    current.eras = [Era(current.model, str(cv))]
    return current


def old_stream_to_new(old_bytes, env, *, retained_file=b'', now=None, zone_captures=None,
                      require_capture_metadata=False, campaign_serial=0, save_sequence=1,
                      writer_version=0x01040000, writer='XML2 Fix', slot=0, mods=(), origin=0, _hash_conversations=True):
    res = Result()
    try:
        if len(old_bytes) == L.OLD_PAYLOAD:
            old_bytes = bytes(0x80) + struct.pack('<I', L.OLD_PAYLOAD) + old_bytes
        old = oldsave.read_slot(old_bytes)
        current = _current_environment(env, hash_conversations=_hash_conversations)
        context = dict(zone_captures=zone_captures or [], require_capture_metadata=require_capture_metadata)
        sections = _translate(old, current, res, '', old_bytes, slot, now, context)
        if any(res.dropped.values()):
            raise ConvertError('native save translation would drop state; original retained')
        sections = [s for s in sections if s[0] != 'LGCY']
        for tag, _, _, _, data in sections:
            if tag == 'META': data.update(origin=origin, writer=writer, mods=list(mods))
        sections = _retain_sections(add_keys_section(sections, env), retained_file, L.KIND_CAMPAIGN)
        header = dict(writer_version=writer_version, content_version=current.ref['content_version'],
                      catalogue_revision=env.catalogue.revision, campaign_serial=campaign_serial, save_sequence=save_sequence)
        res.file_bytes = write_file(L.KIND_CAMPAIGN, sections, header)
        read_file(res.file_bytes, L.KIND_CAMPAIGN)
    except (ValueError, IndexError, KeyError) as e:
        res.refused = str(e); res.file_bytes = None
    return res


def _profile_file(old_bytes, original_name, env, *, converter, retained_file=b'', now=None, writer_version=None, writer=None, slot=0):
    res = Result()
    try:
        if len(old_bytes) == L.OLD_PROFILE_PAYLOAD:
            old_bytes = bytes(0x80) + struct.pack('<I', L.OLD_PROFILE_PAYLOAD) + old_bytes
        description, p = oldsave.read_profile_file(old_bytes)
        current = env if converter else _current_environment(env)
        era = current.eras[0]
        sections = [('META', 1, 0, L.SECTION_REQUIRED, dict(saved_at=now if now is not None else int((time.time() + 11644473600) * 10000000),
                    description=description, origin=int(converter), zone=0, act=0, difficulty=0, play_time=0., writer=writer or ('lcsave 0.1.0' if converter else 'XML2 Fix'), slot=slot, mods=[]))]
        sections += profile_sections(p, current, res, era)
        if converter:
            sections.append(('LGCY', 1, 0, L.SECTION_KEEP, dict(original_name=original_name, original_size=len(old_bytes),
                sha1=hashlib.sha1(old_bytes).digest(), start_era=era.cv, writer_era=era.cv, def_count_byte=0,
                zone_records_dropped=0, world_items_dropped=0, zone_vars_dropped=0, other_dropped=0, notes=[])))
        sections = _retain_sections(add_keys_section(sections, env), retained_file, L.KIND_PROFILE)
        header = dict(writer_version=writer_version if writer_version is not None else (0x00010001 if converter else 0x01040000),
                      content_version=current.ref.get('content_version', 0), catalogue_revision=env.catalogue.revision, campaign_serial=0, save_sequence=0)
        res.file_bytes = write_file(L.KIND_PROFILE, sections, header)
        read_file(res.file_bytes, L.KIND_PROFILE)
    except (ValueError, IndexError, KeyError) as e:
        res.refused = str(e); res.file_bytes = None
    return res


def convert_profile(old_bytes, original_name, env, **kwargs):
    return _profile_file(old_bytes, original_name, env, converter=True, **kwargs)


def old_profile_to_new(old_bytes, env, **kwargs):
    return _profile_file(old_bytes, '', env, converter=False, **kwargs)


def reverse_profile(new_bytes, env):
    f = read_file(new_bytes, L.KIND_PROFILE)
    sections = {t: s['data'] for t, s in f['sections'].items() if s['data'] is not None}
    validate_native_sections(sections, env)
    return sections['META']['description'], PositionTables(env).profile(sections)


def validate_native_sections(S, env, *, hash_conversations=True):
    import math
    def bound(v, lo, hi, what):
        if not lo <= v <= hi:
            raise ConvertError(f'{what} outside native range {lo}..{hi}')
    def unique(rows, key, what):
        vals = [r[key] for r in rows]
        if len(vals) != len(set(vals)): raise ConvertError(f'duplicate {what}')
    def finite(v):
        if isinstance(v, dict):
            for x in v.values(): finite(x)
        elif isinstance(v, list):
            for x in v: finite(x)
        elif isinstance(v, float) and not math.isfinite(v):
            raise ConvertError('nonfinite native value')
    finite(S)
    pos = PositionTables(env, hash_conversations=hash_conversations)
    if 'GAME' in S:
        g = S['GAME']
        for n, hi in (('team_potion', 3), ('counter_a', 31), ('counter_b', 31), ('flags', 1023)):
            bound(g[n], 0, hi, n)
        miss = S['MISS']; depth = miss['stack_depth']
        bound(depth, 0, L.OLD_SIDE_FRAMES, 'mission stack depth')
        if len(miss['snapshots']) != depth + 1: raise ConvertError('mission stack snapshots do not match depth')
        for snap in miss['snapshots']:
            unique(snap['seats'], 'seat', 'seat'); unique(snap['objectives'], 'objective', 'objective')
            for seat in snap['seats']:
                bound(seat['seat'], 0, 3, 'seat')
            for o in snap['objectives']:
                bound(o['counter'], 0, 63, 'objective counter'); bound(o['flags'], 0, 3, 'objective flags')
        unique(S['HERO']['heroes'], 'hero', 'hero')
        for index, hero in enumerate(S['HERO']['heroes'], 1):
            if pos.stat(hero['hero']) != index: raise ConvertError('hero block order/identity differs from native table')
            owner = env.binds.stat[index]
            allowed = {env.id_of('COST', keys_hash) for keys_hash in (env.binds.hash_tables() if hash_conversations else env.binds.hash_tables(include_conversation_digest=False))['COST'].get(key_hash(owner), {}).values()}
            if hero['costume'] not in allowed or any(c not in allowed for c in hero['costumes_unlocked']):
                raise ConvertError('costume does not belong to hero')
        unique(S['DNGR']['courses'], 'course', 'course'); unique(S['DNGR']['grades'], 'grade', 'grade')
        if len(S['HERO']['heroes']) != env.binds.hero_count: raise ConvertError('hero block count differs from build')
        unique(S['REST']['records'], 'owner', 'restore owner')
        items = S['ITEM']
        for e in items['def_state']: bound(e['quantity'], 0, 255, 'item quantity')
        unique(items['def_state'], 'item', 'definition state'); unique(items['key_counts'], 'item', 'key counter')
        unique(items['world'], 'handle', 'world item handle')
        handles = {w['handle'] for w in items['world']}
        for handle in handles: bound(handle, 0, 149, 'world handle')
        if len(handles) > 150: raise ConvertError('world item pool exhausted')
        instances = list(items['instances']) + [w['instance'] for w in items['world']]
        for hero in S['HERO']['heroes'] + S['REST']['records']:
            bound(hero['player_seat'], -1, 3, 'player seat'); bound(hero['flags'], 0, 31, 'hero flags')
            unique(hero['talents'], 'talent', 'talent')
            owner = pos.stat(hero.get('hero', hero.get('owner')))
            for t in hero['talents']:
                tid = pos._get(pos._tal, t['talent'], 'talent')
                if tid >= 100 and tid // 100 != owner + 1: raise ConvertError('talent does not belong to hero')
            for talent in hero['talents']:
                for field, hi in (('rank', 63), ('pending', 63), ('cap', 3), ('base', 3)):
                    bound(talent[field], 0, hi, 'talent ' + field)
            instances.extend(hero['equipped'])
        if len(instances) > 256: raise ConvertError('native instance pool exhausted')
        attached = sum(len(i[n]) for i in instances for n in ('prefixes', 'own', 'suffixes'))
        if attached > 375: raise ConvertError('native attached enhancement pool exhausted')
        era = _current_environment(env, hash_conversations=hash_conversations).eras[0]
        for instance in instances:
            _cross_check_instance(env, era, pos.instance(instance), 'item')
        unique(S['ZONE']['records'], 'zone', 'zone record')
        if len(S['ZONE']['records']) > 5: raise ConvertError('native zone cache exhausted')
        for z in S['ZONE']['records']:
            if z['fog']['encoding'] != 1 or z['fog']['width'] != 82 or z['fog']['height'] != 82 or len(z['fog']['data']) != L.OLD_FOG_BYTES:
                raise ConvertError('unsupported native fog')
            if len(z['conversation']) != 5: raise ConvertError('native conversation word count')
            ords = []
            placements = set()
            if len(z['states']) >= L.OLD_ZONE_STATES: raise ConvertError('native state pool exhausted')
            for state in z['states']:
                bound(state['list'], 1, 3, 'state list')
                for n in ('def_name', 'inst_name'): bound(state[n], 0, len(z['names']) - 1, 'state name index')
                for x in state['position']:
                    if not -32768 <= x <= 32767 or x != round(x): raise ConvertError('state position not representable')
                bound(state['flags_a'], 0, 255, 'state flags'); bound(state['flags_b'], 0, 255, 'state flags')
                if state['list'] == 1:
                    bound(state['ordinal'], 1, L.OLD_ZONE_ORDINALS, 'ordinal'); ords.append(state['ordinal'])
                    if state['placement_index'] in placements: raise ConvertError('duplicate destination placement')
                    placements.add(state['placement_index'])
                if state['payload_kind'] == 2:
                    if len(state['payload']) != 13 or not state['flags_a'] & 1: raise ConvertError('world payload contract')
                    handle, quantity = struct.unpack('<Ii', state['payload'][:8])
                    if handle not in handles: raise ConvertError('state world item reference missing')
                    bound(quantity, -32768, 32767, 'world quantity')
                elif state['payload_kind'] != 1 or len(state['payload']) != 8 or state['flags_a'] & 1:
                    raise ConvertError('engine payload contract')
            if len(ords) != len(set(ords)): raise ConvertError('duplicate ordinal')
            for kind, cap in ((2, L.OLD_ZONE_DYNAMIC), (3, L.OLD_ZONE_SMART)):
                if sum(s['list'] == kind for s in z['states']) > cap: raise ConvertError('native state list exhausted')
    O, P, Scores = S['PRFO'], S['PRFP'], S['PRFS']['scores']
    bound(O['options'], 0, 0xffffff, 'profile options')
    if len(Scores) > L.OLD_HIGH_SCORES: raise ConvertError('native profile score count')
    for score in Scores:
        if len(score['party_a']) > 6 or len(score['party_b']) > 6: raise ConvertError('native profile party count')

def native_zone_metadata(old_stream, env):
    """Validated current-build associations for a native transfer without an LC sidecar; inferred only."""
    result = old_stream_to_new(old_stream, env, now=0, _hash_conversations=False)
    if result.refused:
        raise ConvertError(result.refused)
    # Avoid reverse_slot here: it hashes all conversation files and can delay a cold online join.
    f = read_file(result.file_bytes)
    validate_native_sections({tag: sec['data'] for tag, sec in f['sections'].items() if sec['data'] is not None}, env, hash_conversations=False)
    zones = {env.catalogue.lookup('ZONE', key_hash(z)): z for z in env.binds.zone_names}
    captures = []
    for record in f['sections']['ZONE']['data']['records']:
        captures.append(dict(zone=zones[record['zone']], time_stamp=record['time_stamp'],
                             placement_sha1=record['content_hash'], capture_flags=2, conversation_digest=bytes(32),
                             entities=[dict(ordinal=s['ordinal'], placement_index=s['placement_index'],
                                            definition_name=record['names'][s['def_name']], instance_name=record['names'][s['inst_name']])
                                       for s in record['states'] if s['list'] == STATE_NUMBERED]))
    return captures


def _legacy_pinned_states(record, numbered, occupied, legacy_import=False):
    """Unique legacy unnumbered placements newly pinned by the build. Explicit numbered states win."""
    if not (legacy_import or record['capture_flags'] & 2):
        return {}
    candidates = {}
    for i, state in enumerate(record['states']):
        if state['list'] not in (STATE_DYNAMIC, STATE_SMART):
            continue
        pair = (key_hash(record['names'][state['def_name']]), key_hash(record['names'][state['inst_name']]))
        matches = [k + 1 for k, (dn, inn, _) in enumerate(numbered) if (key_hash(dn or ''), key_hash(inn or '')) == pair]
        if len(matches) == 1 and matches[0] not in occupied:
            candidates[i] = matches[0]
    return {i: k for i, k in candidates.items() if list(candidates.values()).count(k) == 1}


def loaded_zone_metadata(new_bytes, env):
    """Applied cached captures, with ordinals aligned to the reconstructed native map."""
    native, _ = reverse_slot(new_bytes, env)
    applied = {oldsave.zone_string(native['zone_strings'], z['name_handle']) for z in native['zones']}
    f = read_file(new_bytes)
    records = f['sections']['ZONE']['data']['records']
    pos = PositionTables(env)
    from .conversations import zone_digest
    out = []
    for r in records:
        zone = pos.zone_name(r['zone'])
        if zone not in applied: continue
        num = env.binds.zone_numbering(zone)['numbered']
        restored = next(z for z in native['zones'] if oldsave.zone_string(native['zone_strings'], z['name_handle']) == zone)
        entities = [dict(ordinal=k + 1, placement_index=num[k][2],
                        definition_name=oldsave.zone_string(native['zone_strings'], restored['states'][idx]['def_name']),
                        instance_name=oldsave.zone_string(native['zone_strings'], restored['states'][idx]['inst_name']))
                    for k, idx in enumerate(restored['ordinal_map']) if idx]
        out.append(dict(zone=zone, time_stamp=r['time_stamp'], placement_sha1=r['content_hash'],
                        conversation_digest=bytes.fromhex(zone_digest(env.binds.build, zone)), capture_flags=r['capture_flags'] | (2 if f['sections']['META']['data']['origin'] == 1 or r['conversation_digest'] == bytes(32) else 0), entities=entities))
    return out
