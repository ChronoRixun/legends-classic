"""Semantic XML1 -> LC mapping using the existing LC encoder and native loader.

Tables name identities; source ordinals are never destination ordinals. R1 can
exercise this core on invented saves but has no admitted retail checkpoint.
"""
from __future__ import annotations

import copy
import secrets
import time

from lcsave import container, convert, layout as L, oldsave

from .errors import ImportRefusal
from .progress import checkpoint, pack_variables
from .source import digest

# Import mapping semantics, separate from the manifest schema and content identity.
# Bind previews to this version as well as the exact installed mapping-table hash.
MAPPING_VERSION = 1


def defaults(schema):
    """One semantic default constructor, using the real codec's schema."""
    out = {}
    for name, typ in schema:
        if typ == 'str':
            value = ''
        elif typ == 'f32x3':
            value = [0.0] * 3
        elif typ == 'u16x16':
            value = [0] * 16
        elif typ.startswith('bytes:'):
            value = bytes(int(typ.split(':')[1]))
        else:
            value = 0.0 if typ == 'f32' else 0
        out[name] = value
    return out


def empty_campaign():
    result = {}
    for tag in container.REQUIRED[L.KIND_CAMPAIGN]:
        head, lists = container.SECTIONS[tag]
        result[tag] = defaults(head)
        result[tag].update({name: [] for name, _ in lists})
    return result


class Changes:
    def __init__(self):
        self.imported, self.approximated, self.skipped = [], [], []

    def approximate(self, code, field, source, target, reason):
        self.approximated.append(dict(code=code, field=field, source=source, target=target,
                                      reason=reason, confidence='INFERRED'))

    def skip(self, field, source, reason):
        self.skipped.append(dict(field=field, source=source, reason=reason))

    def preserve(self, field, value):
        self.imported.append(dict(field=field, value=value))


def _profile_patch(ir, table):
    """Only explicit, sample-proven bit/name rows; no native codex-index guess."""
    patch = dict(highest_level=0, flags=0, characters=[], review=[])
    for row in table.data.get('profile_unlock_bits', []):
        if row.get('confirmed') is not True:
            raise ImportRefusal('MERGE', 'An unlock bit has no confirmed meaning.')
        if row['field'] not in ('characters', 'review', 'flags') or not 0 <= row['offset'] < len(ir['profile']) or not 0 < row['mask'] <= 255:
            raise ImportRefusal('BUILD', 'Invalid source profile bit mapping.')
        if ir['profile'][row['offset']] & row['mask']:
            field = row['field']
            if field == 'flags':
                patch[field] |= row['target_mask']
            else:
                domain = 'STAT' if field == 'characters' else 'REVW'
                patch[field].append(table.resolve(domain, *row['target']))
    return patch


def merge_profile(profile_bytes, patch, env):
    """Pure monotonic profile merge. Platform options/scores/opaque sections stay.

    Installation is a separate transaction; this function never opens a file.
    """
    f = validate_profile(profile_bytes, env)
    sections = []
    for tag in f['order']:
        entry = f['sections'][tag]
        data = copy.deepcopy(entry['data'])
        if tag == 'PRFP':
            if container.encode_section(tag, data) != entry['payload']:
                raise ImportRefusal('MERGE', 'The profile contains newer progress fields that this importer cannot preserve.')
            data['highest_level'] = max(data['highest_level'], patch['highest_level'])
            data['flags'] |= patch['flags']
            for field in ('characters', 'review'):
                data[field] = sorted(set(data[field]) | set(patch[field]))
        else:
            # Preserve byte-for-byte payloads, including newer optional records
            # and unknown KEEP sections. Only PRFP is semantically changed.
            data = dict(_opaque_payload=entry['payload'], _opaque_records=entry['entry']['records'])
        e = entry['entry']
        sections.append((tag, e['major'], e['minor'], e['flags'], data))
    header = dict(f['header'], save_sequence=f['header']['save_sequence'] + 1)
    result = container.write_file(L.KIND_PROFILE, sections, header)
    validate_profile(result, env)
    return result


def validate_profile(profile_bytes, env):
    """Use the installed W2 tables even though profile layout itself is fixed."""
    f = container.read_file(profile_bytes, L.KIND_PROFILE)
    sections = {tag: s['data'] for tag, s in f['sections'].items() if s['data'] is not None}
    convert.validate_native_sections(sections, env, native=L.W2)
    profile = convert.PositionTables(env, native=L.W2).profile(sections)
    oldsave.write_profile_file(sections['META']['description'], profile)
    return f


def _instance(table, target, location):
    b = table.env.binds
    matches = [i for i, n in enumerate(b.item) if n.lower() == target.lower()]
    if len(matches) != 1 or b.item_type[matches[0]].lower() != 'equipment':
        raise ImportRefusal('IDENTITY', 'The saved equipment has no unique target definition.', item=target)
    economy = table.economy.get(target.lower())
    if economy is None or not economy['flags'] & 0x40:
        raise ImportRefusal('BUILD', 'The target equipment is outside the verified XML1 economy.', item=target)
    return dict(definition=table.resolve('ITEM', target), name_a=0, name_b=0, special=0, location=location,
                prefixes=[], own=[dict(enhancement=table.resolve('ENHC', *b.key_enh(n)), value=0)
                                  for n in b.item_own[matches[0]]], suffixes=[])


def _hero(source, row, table, changes):
    name = source['name']
    target = row['target']
    if any(source['pending']) or any(t['pending'] for t in source['talents']):
        raise ImportRefusal('CONTEXT', 'Commit or cancel pending upgrades before importing.', hero=name)
    thresholds = table.data['xp_thresholds']
    level, xp = source['level'], source['experience']
    if not 1 <= level <= len(thresholds) or xp < thresholds[level - 1] or (level < len(thresholds) and xp >= thresholds[level]):
        raise ImportRefusal('DAMAGED', 'Hero level and XP disagree with the source curve.', hero=name, level=level, experience=xp)
    if not 1 <= source['ack_level'] <= level:
        raise ImportRefusal('DAMAGED', 'The processed point-award level is invalid.', hero=name)
    result = defaults(container.RECORDS['HREC'])
    result.update(hero=table.resolve('STAT', target), level=level, experience=xp, ack_level=source['ack_level'],
                  player_seat=-1, skill_points=source['skill_points'], trait_points=source['trait_points'] * 4,
                  talents=[], equipped=[], powers=copy.deepcopy(row['powers']))
    if 'vitality' in source:
        result['health_boosts'], result['energy_boosts'] = source['vitality']
        changes.preserve(name + '.permanent_vitality', source['vitality'])
        if source['auto_equip']:
            changes.approximate('auto_equip', name + '.auto_equip', True, False,
                                'The source auto-equip preference has no proven target flag mapping; use manual equipment.')
    formula = row.get('stat_reconstruction')
    if formula:
        # Saved base = authored base + native class growth + earned allocations.
        # All four arrays are supplied by the pinned, sample-validated table.
        src_start, dst_start = formula['source_base'], formula['target_base']
        src_growth, dst_growth = formula['source_growth'][level - 1], formula['target_growth'][level - 1]
        allocation = [source['base'][i] - src_start[i] - src_growth[i] for i in range(4)]
        if any(x < 0 for x in allocation):
            raise ImportRefusal('CONTEXT', 'Saved base traits cannot be reconstructed.', hero=name)
        base = [dst_start[i] + dst_growth[i] + 4 * allocation[i] for i in range(4)]
    else:
        base = [4 * source['base'][0], min(22, max(14, 10 + 2 * source['base'][1])),
                4 * source['base'][2], 4 * source['base'][3]]
        changes.approximate('base_traits', name + '.base_traits', source['base'], base,
                            'Provisional authored-stat scaling; saved class growth has not been proven.')
    if any(not 0 <= n <= 65535 for n in base):
        raise ImportRefusal('CAPACITY', 'Converted traits exceed the target width.', hero=name)
    result['traits'] = [n for x in base for n in (x, 0, 0, 0)]
    if not table.source.get('stat_points_confirmed', False):
        changes.approximate('stat_points', name + '.trait_points', source['trait_points'], result['trait_points'],
                            'Convert unspent stat points to the target four-point scale; sample verification remains open.')
    result['ai_level'], result['ai_attack'] = source['ai_level'], source['ai_power']
    changes.approximate('ai', name + '.ai', [source['ai_level'], source['ai_power']],
                        [result['ai_level'], result['ai_attack']], 'Source nibbles are confirmed; target behavior equivalence is inferred.')
    changes.approximate('vitals', name + '.vitals', [source['health'], source['energy'], source['seat'], source['validity']],
                        'fresh checkpoint spawn', 'Health, energy and control validity are rebuilt at checkpoint entry.')
    if any(source['bonus']) or any(source['bonus2']):
        changes.approximate('trait_bonuses', name + '.bonuses', [source['bonus'], source['bonus2']], [0] * 8,
                            'Equipment effects are recalculated; the second source bonus bank has unresolved semantics.')
    unknown = source['raw'][13:16] + source['raw'][42:44]
    if any(unknown):
        changes.approximate('character_flags', name + '.unresolved_scalar_bytes', unknown.hex(), 'target defaults',
                            'No proven target interpretation for these source bytes.')
    talents = table.data.get('talents', {}).get(name, {})
    for t in source['talents']:
        if source.get('talent_identities') is not None:
            saved = source['talent_identities'][t['native_id']]
            matches = [r['target'] for r in table.data.get('named_talents', {}).get(name, [])
                       if all(r[k] == saved[k] for k in ('name', 'source', 'selector'))]
            if len(matches) > 1:
                raise ImportRefusal('BUILD', 'Ambiguous named talent mapping.', hero=name)
            identity = matches[0] if matches else None
        else:
            identity = talents.get(str(t['native_id']))
        if not identity:
            if t['rank'] or t['baseline'] or t['bonus']:
                raise ImportRefusal('IDENTITY', 'Unknown purchased or active native talent ID.', hero=name, native_id=t['native_id'])
            changes.skip(name + '.talent', t['native_id'], 'Unidentified zero-rank declaration; no purchased rank is discarded.')
            continue
        if t['limit'] > 3 or t['baseline'] > 3:
            raise ImportRefusal('CAPACITY', 'Talent limit or baseline cannot fit without clipping.', hero=name, native_id=t['native_id'])
        if t['bonus']:
            changes.approximate('talent_bonus', name + '.talent.' + str(t['native_id']), t['bonus'], 'equipment recalculation',
                                'Target talents have no persistent source bonus nibble.')
        result['talents'].append(dict(talent=table.resolve('TALN', *identity), rank=t['rank'], pending=0,
                                      cap=t['limit'], base=t['baseline'], byte5=0))
    attr = row.get('skins', {}).get(str(source['skin']))
    if attr is None:
        attr = 'skin'
        changes.approximate('selected_skin', name + '.physical_skin', source['skin'], attr,
                            'The source skin byte has no proven attribute mapping; use the base skin.')
    result['costume'] = table.resolve('COST', target, attr)
    result['costumes_unlocked'] = sorted({table.resolve('COST', target, 'skin'), result['costume']})
    changes.skip(name + '.other_costume_unlocks', 'not encoded on the retail character record',
                 'Only base and selected costumes can be established from this mapping.')
    changes.preserve(name + '.progression', dict(level=level, experience=xp, ack_level=source['ack_level'],
                                               skill_points=result['skill_points'], trait_points=result['trait_points'],
                                               talents=copy.deepcopy(result['talents'])))
    return result


def _source_roster(ir, table, changes):
    """Resolve every source ID before selecting supported destination records."""
    recomp = ir['decoder'].startswith('recomp-')
    target_names = {n.lower() for n in table.env.binds.stat[1:table.env.binds.hero_count + 1]}
    party = {n.lower() for n in ir['mission']['party'] if n}
    supported, by_id, names = [], {}, set()
    for h in ir['heroes']:
        ident, name = h['definition_id'], h['name']
        if ident in by_id or name.lower() in names:
            raise ImportRefusal('IDENTITY', 'Duplicate source definition ID or name.')
        by_id[ident] = h
        names.add(name.lower())
        if recomp and (not getattr(table, 'recomp', False) or table.definitions.get(ident) != name):
            raise ImportRefusal('IDENTITY', 'The character does not match the effective source definition ledger.', definition_id=ident)
        row = table.data['heroes'].get(name)
        if row is None or row['target'].lower() not in target_names:
            if not recomp or name.lower() in party or h['seat'] != -1:
                raise ImportRefusal('IDENTITY', 'An active or required source hero cannot be represented by this roster.', hero=name,
                                    definition_id=ident)
            loss = {key: copy.deepcopy(value) for key, value in h.items()
                    if key not in ('raw', 'offset', 'identity_resolved')}
            loss['unlocked'] = ident in ir['unlocked']
            changes.skip('unsupported_hero.' + str(ident), loss,
                         'This source character is absent from the target roster; its progression and unlock are omitted. Equipment is handled separately.')
            continue
        supported.append(h)
    if any(n not in names for n in party):
        raise ImportRefusal('IDENTITY', 'Unknown saved party hero.')
    return supported, by_id


def _recomp_state(ir, table, result, changes, supported):
    """Preserve known adjunct state, disclose every remaining adjunct field."""
    if not ir['decoder'].startswith('recomp-'):
        return
    mapped_names = {h['name'] for h in supported}
    for name, moves in ir['power_selections'].items():
        if name not in mapped_names:
            changes.skip('recomp.power_selections.' + name, moves,
                         'The saved power owner has no mapped source character; these selections are omitted.')
    if ir['hard_unlocked']:
        changes.skip('recomp.hard_unlocked', True, 'No confirmed destination profile-completion flag mapping is supplied.')
    extra = ir['campaign_extra']
    if extra:
        if 'acts' in extra and extra['acts'][0] != result['GAME']['act']:
            raise ImportRefusal('CONTEXT', 'The saved current act disagrees with the checkpoint recipe.')
        changes.skip('recomp.campaign_extra', {k: v for k, v in extra.items() if k != 'difficulty'},
                     'Retained difficulty/act, recall departure and cooldowns, and collectible allowances reset at the checkpoint.')
    stash = ir['stash']
    if stash['live']:
        for value in stash['live']:
            matches = [r for r in table.data['items'] if r.get('source_name') == value['name']]
            if len(matches) != 1 or matches[0]['route'] != 'equipment':
                raise ImportRefusal('IDENTITY', 'A named stash item has no unique equipment mapping.', item=value['name'])
            row = matches[0]
            result['ITEM']['instances'] += [_instance(table, row['target'], 2) for _ in range(value['quantity'])]
        changes.approximate('stash_location', 'recomp.stash.live', stash['live'], 'carried equipment',
                            'Preserve every named stash copy in carried equipment; the target has no matching source stash container.')
    if stash['valid'] or stash['snapshot']:
        changes.skip('recomp.stash.snapshot', dict(valid=stash['valid'], items=stash['snapshot']),
                     'This is rollback inventory, invalidated with the other source restore banks.')


def map_campaign(ir, source, table, *, slot, allow_inferred=False, profile_bytes=None, merge_unlocks=False, now=None, serial=None):
    if not 0 <= slot <= 9:
        raise ImportRefusal('SLOT', 'Slot must be in the range 0 through 9.')
    changes = Changes()
    source_heroes, by_id = _source_roster(ir, table, changes)
    recipe = checkpoint(ir, table.data.get('checkpoints', []))
    result = empty_campaign()
    target_zone = table.resolve('ZONE', recipe['target_zone'])
    difficulty = ir.get('difficulty', 1)
    if type(difficulty) is not int or difficulty not in (0, 1, 2):
        raise ImportRefusal('CONTEXT', 'The source difficulty is not representable.', difficulty=difficulty)
    result['META'].update(saved_at=int(time.time() if now is None else now), description='Imported XML1 campaign',
                          origin=1, zone=target_zone, act=recipe['act'], difficulty=difficulty,
                          play_time=ir['play_time'], writer='XML1 save importer', slot=slot)
    result['GAME'].update(act=recipe['act'], difficulty=difficulty, play_time=ir['play_time'])
    if 'difficulty' in ir:
        changes.preserve('difficulty', difficulty)
    else:
        changes.approximate('difficulty', 'difficulty', 'retail semantics unresolved', 1,
                            'No source difficulty field is established; use Normal difficulty.')
    changes.approximate('checkpoint', 'world', dict(zone=ir['mission']['zone'], cached_zones=len(ir['zones'])),
                        dict(zone=recipe['target_zone'], checkpoint=recipe['name']),
                        'Resume at zone/checkpoint start. Enemies and props respawn; fog, heard lines and world drops reset.')
    changes.approximate('retained_state', 'rollback_banks', dict(hero_valid=ir['restore_valid'], inventory_valid=ir['inventory_snapshot_valid']),
                        'invalidated', 'Source snapshots are rollback state, not banked gear; checkpoint starts without a side mission.')
    changes.skip('game_records', dict(live_sha256=digest(ir['game']), retained_sha256=digest(ir['retained_game'])),
                 'Unresolved game-mode, trivia and loading fields use idle target checkpoint defaults.')
    hero_rows = table.data['heroes']
    source_targets = {}
    for h in source_heroes:
        row = hero_rows[h['name']]
        target = row['target'].lower()
        if target in source_targets:
            raise ImportRefusal('IDENTITY', 'Two source heroes map to one target hero.')
        h = copy.deepcopy(h)
        if ir.get('character_version', 0) >= 4:
            h['talent_identities'] = ir['talent_identities']
        mapped = _hero(h, row, table, changes)
        selected = ir.get('power_selections', {}).get(h['name'])
        if selected is not None:
            defaults_by_button = {p['button']: p for p in mapped['powers']}
            for button, move in enumerate(selected):
                target_move = row.get('power_selections', {}).get(move)
                if target_move is not None:
                    defaults_by_button[button] = dict(button=button, name=target_move, flags=int(bool(target_move)))
                    changes.preserve(h['name'] + '.selected_power.' + str(button), target_move)
                elif move or defaults_by_button.get(button, {}).get('name'):
                    changes.approximate('selected_power', h['name'] + '.selected_power.' + str(button), move,
                                        defaults_by_button.get(button, {}).get('name', ''),
                                        'This named source power has no confirmed target move mapping; use the pinned default.')
            mapped['powers'] = [p for _, p in sorted(defaults_by_button.items())]
        source_targets[target] = (mapped, h)
    target_heroes = table.env.binds.stat[1:table.env.binds.hero_count + 1]
    if any(n not in [x.lower() for x in target_heroes] for n in source_targets):
        raise ImportRefusal('IDENTITY', 'A source hero is absent from the target roster.')
    for name in target_heroes:
        if name.lower() in source_targets:
            hero = source_targets[name.lower()][0]
        else:
            try:
                hero = copy.deepcopy(table.data['target_defaults'][name.lower()])
                hero['hero'] = table.resolve('STAT', name)
            except KeyError as e:
                raise ImportRefusal('BUILD', 'Target-only hero has no validated defaults.', hero=name) from e
            changes.skip(name, 'absent from source', 'Initialize this target-only hero with pinned target defaults and keep it locked.')
        result['HERO']['heroes'].append(hero)
    by_name = {h['name'].lower(): h for h in ir['heroes']}
    seats = []
    for i, name in enumerate(ir['mission']['party']):
        if not name:
            continue
        if name.lower() not in by_name:
            raise ImportRefusal('IDENTITY', 'Unknown saved party hero.', hero=name)
        mapped = source_targets[hero_rows[by_name[name.lower()]['name']]['target'].lower()][0]
        if by_name[name.lower()]['seat'] not in (-1, i):
            raise ImportRefusal('CONTEXT', 'Character control seat disagrees with the saved party.', hero=name)
        mapped['player_seat'] = i
        pose = recipe['seat_poses'][i]
        seats.append(dict(seat=i, hero=mapped['hero'], position=pose[:3], orientation=pose[3:]))
    unlocked = []
    for source_id in ir['unlocked']:
        if source_id not in by_id:
            raise ImportRefusal('IDENTITY', 'Unknown unlocked hero definition.', definition_id=source_id)
        name = by_id[source_id]['name']
        if name == 'default':
            changes.skip('unlocked.default', source_id, 'The default definition is not a playable hero.')
        elif name in hero_rows and hero_rows[name]['target'].lower() in source_targets:
            unlocked.append(table.resolve('STAT', hero_rows[name]['target']))
    if any(s['hero'] not in unlocked for s in seats):
        raise ImportRefusal('CONTEXT', 'A party hero is absent from the campaign unlock list.')
    result['ULCK']['unlocked'] = unlocked
    obj = []
    mappings = recipe['objectives']
    for i, value in enumerate(ir['mission']['objectives']):
        target = mappings.get(str(i))
        if any(value['unknown']) or value['raw_word'] & 0x7000:
            changes.approximate('objective_padding', 'objective.' + str(i) + '.unresolved_bits',
                                dict(word_bits=value['raw_word'] & 0x7000, extra=value['unknown'].hex()), 0,
                                'No semantic target interpretation is proven for these source bits.')
        if target is None:
            if value['counter'] or value['enabled'] or value['complete'] or value['required'] or value['hidden']:
                changes.approximate('unmapped_objective', 'objective.' + str(i), {k: v for k, v in value.items() if k != 'unknown'},
                                    None, 'This source objective has no named checkpoint mapping.')
            continue
        if not 0 <= value['counter'] <= 63:
            raise ImportRefusal('CAPACITY', 'A saved objective counter exceeds the target six-bit range.', objective=i, counter=value['counter'])
        obj.append(dict(objective=table.resolve('OBJV', *target), counter=value['counter'],
                        flags=int(value['complete']) | (int(value['hidden'] or not value['enabled']) << 1)))
        if value['required'] != recipe.get('required_objectives', {}).get(str(i), False):
            changes.approximate('objective_required', 'objective.' + str(i) + '.required', value['required'],
                                'target mission definition', 'Target saves have no equivalent required-state flag.')
        if value['hidden'] or not value['enabled']:
            changes.approximate('objective_visibility', 'objective.' + str(i) + '.visibility',
                                dict(enabled=value['enabled'], hidden=value['hidden']), 'hidden',
                                'Target persistence merges disabled and hidden states.')
    result['MISS']['snapshots'] = [dict(zone=target_zone, flags=3, seats=seats, objectives=obj,
                                      anchor_pos=recipe['anchor_pose'][:3], anchor_orient=recipe['anchor_pose'][3:])]
    result['SVAR']['game_vars'] = pack_variables(ir['variables'], table.data.get('variables', []), recipe['scope'], changes.approximate)
    items = {r['source_index']: r for r in table.data['items']}
    if len(items) != len(table.data['items']):
        raise ImportRefusal('BUILD', 'Duplicate source item mappings.')
    equipped_counts = {}
    for h in ir['heroes']:
        for index in h['equipped']:
            equipped_counts[index] = equipped_counts.get(index, 0) + 1
    mode = table.data.get('quantity_policy')
    if mode not in ('excludes_equipped', 'includes_equipped'):
        raise ImportRefusal('BUILD', 'The source equipment conservation policy is missing.')
    changes.approximate('equipment_conservation', 'quantity_policy', mode, mode,
                        'This interpretation of carried quantities versus equipped copies needs paired real saves.')
    result['ITEM']['tech_bits'] = ir['tech_bits']
    changes.preserve('tech_bits', ir['tech_bits'])
    for i, value in enumerate(ir['inventory']):
        row = items.get(i)
        if row is None:
            if value['quantity'] or value['flag'] or i in equipped_counts:
                raise ImportRefusal('IDENTITY', 'Unknown inventory definition.', source_index=i)
            continue
        quantity = value['quantity']
        if quantity > row['maximum']:
            raise ImportRefusal('CAPACITY', 'A source quantity exceeds its authored limit.', source_index=i)
        if value['flag']:
            changes.approximate('item_flag', 'inventory.' + str(i) + '.flag', value['flag'], 0,
                                'Unique-award flag meaning is unresolved; no raw flag is transplanted.')
        route = row['route']
        if i in equipped_counts and route != 'equipment':
            raise ImportRefusal('IDENTITY', 'An equipped definition is not mapped as equipment.', source_index=i)
        if route == 'equipment':
            carried = quantity - (equipped_counts.get(i, 0) if mode == 'includes_equipped' else 0)
            if carried < 0:
                raise ImportRefusal('DAMAGED', 'Equipped copies exceed the inclusive quantity.', source_index=i)
            if carried + equipped_counts.get(i, 0) > L.W2.instances:
                raise ImportRefusal('CAPACITY', 'Too many equipment copies.')
            result['ITEM']['instances'] += [_instance(table, row['target'], 2) for _ in range(carried)]
            changes.preserve('equipment.' + str(i), dict(target=row['target'], carried=carried, equipped=equipped_counts.get(i, 0)))
        elif route in ('health', 'energy'):
            if quantity > row['target_maximum']:
                raise ImportRefusal('CAPACITY', 'A consumable quantity exceeds the target pack limit.', source_index=i)
            result['ITEM'][route + '_items'] += quantity
        elif route == 'key':
            if quantity:
                result['ITEM']['key_counts'].append(dict(item=table.resolve('ITEM', row['target']), quantity=quantity, flag=0))
        elif route == 'effect':
            if quantity:
                changes.approximate('effect_quantity', 'inventory.' + str(i), quantity, 0,
                                    'Pickup effects are not carried items or additional Tech Bits.')
        else:
            raise ImportRefusal('BUILD', 'Unknown item routing policy.')
    for hero, h in source_targets.values():
        for index in h['equipped']:
            hero['equipped'].append(_instance(table, items[index]['target'], 1))
    supported_ids = {h['definition_id'] for h in source_heroes}
    for h in ir['heroes']:
        if h['definition_id'] not in supported_ids and h['equipped']:
            for index in h['equipped']:
                result['ITEM']['instances'].append(_instance(table, items[index]['target'], 2))
            changes.approximate('unsupported_hero_equipment', h['name'] + '.equipped', h['equipped'], 'carried equipment',
                                'Preserve these equipped copies as carried gear because the source hero is absent from the target roster.')
    _recomp_state(ir, table, result, changes, source_heroes)
    patch = _profile_patch(ir, table)
    if profile_bytes:
        f = validate_profile(profile_bytes, table.env)
        for tag in ('PRFO', 'PRFP', 'PRFS'):
            if container.encode_section(tag, f['sections'][tag]['data']) != f['sections'][tag]['payload']:
                raise ImportRefusal('MERGE', 'The existing profile has newer fields that cannot be embedded safely.')
            result[tag] = copy.deepcopy(f['sections'][tag]['data'])
    for field in ('characters', 'review'):
        result['PRFP'][field] = sorted(set(result['PRFP'][field]) | set(patch[field]))
    result['PRFP']['flags'] |= patch['flags']
    if merge_unlocks and not table.data.get('profile_unlock_bits'):
        raise ImportRefusal('MERGE', 'No confirmed source profile-unlock decoder is supplied.')
    merged = merge_profile(profile_bytes, patch, table.env) if merge_unlocks and profile_bytes else None
    if merge_unlocks and merged is None:
        raise ImportRefusal('MERGE', 'Select an existing target profile to merge into.')
    changes.skip('embedded_profile', dict(bytes=len(ir['profile']), sha256=digest(ir['profile'])),
                 'Only explicitly mapped unlock bits are imported; Xbox options, codex, scores and remaining completion state are unresolved.')
    if any(ir['courses']) or any(ir['grades']) or ir['credits']:
        changes.approximate('danger_room', 'danger_room', dict(courses=list(ir['courses']), grades=list(ir['grades']), credits=ir['credits']),
                            'target defaults', 'Completion, extra-credit and grade byte semantics are unresolved. No reward is re-awarded.')
    if any(ir['review']):
        changes.approximate('review', 'review_banks', ir['review'].hex(), [],
                            'Review category and seen/unlocked bank semantics need paired samples.')
    result['XTRC']['unlocked'] = [table.resolve('XPNT', *key) for key in recipe.get('xtraction', [])]
    changes.skip('other_travel_unlocks', 'unresolved source representation', 'Only the admitted checkpoint travel anchor is granted.')
    report = dict(schema=1, mapping_version=MAPPING_VERSION,
                  source_sha256=source.sha256, source_profile=table.source['id'], decoder=ir['decoder'],
                  signature_status=source.signature_status, signature_message='Xbox signature not checked' if source.signature_status == 'unavailable' else 'Xbox signature verified',
                  target_fingerprint=table.fingerprint, import_table_sha256=table.sha256, checkpoint=recipe['name'],
                  zone=recipe['target_zone'], slot=slot, merge_unlocks=merge_unlocks, difficulty=difficulty,
                  heroes=[dict(name=h['name'], level=h['level'], experience=h['experience'], unlocked=h['definition_id'] in ir['unlocked']) for h in ir['heroes']],
                  progress=dict(zone=ir['mission']['zone'], mission_id=ir['mission']['mission_id'], party=ir['mission']['party']),
                  imported=changes.imported, approximated=changes.approximated, skipped=changes.skipped,
                  player_use_validated=False, validation='Python LC loader only; native C++ and real-save acceptance pending')
    if ir['decoder'].startswith('recomp-'):
        report['source_herostat_sha256'] = table.source['herostat_sha256']
        report['survey_revision'] = ir['survey_revision']
    if changes.approximated and not allow_inferred:
        raise ImportRefusal('INFERRED', approximated=changes.approximated, skipped=changes.skipped)
    # A semantic model goes directly through the real encoder, never the PC-era
    # detector. Native W2 is required only by the shared representability rule.
    optional = L.OPTIONAL_LEVEL_SKILL_POINTS | L.OPTIONAL_LEVEL_STAT_POINTS
    if all(hero_rows[h['name']].get('stat_reconstruction') for h in source_heroes):
        optional |= L.OPTIONAL_CLASS_GROWTH
    header = dict(writer_version=0x01000000, content_version=table.env.catalogue.data['content_version'],
                  catalogue_revision=table.env.catalogue.revision, campaign_serial=serial or secrets.randbits(64) or 1,
                  save_sequence=1, required_features=L.FEATURE_ENTITY_LAYOUT_CONTIGUOUS10,
                  optional_features=optional)
    try:
        encoded = encode_and_validate(result, header, table.env)
    except (ValueError, KeyError, IndexError, OverflowError) as e:
        raise ImportRefusal('CAPACITY', 'The LC native loader refused the mapped campaign: ' + str(e)) from e
    report['output_sha256'] = digest(encoded)
    report['output_bytes'] = len(encoded)
    report['campaign_serial'] = header['campaign_serial']
    return encoded, report, merged


def encode_and_validate(sections, header, env):
    rows = [(tag, 1, container.SECTION_MINOR.get(tag, 0), container.SECTION_FLAGS.get(tag, 0), data)
            for tag, data in sections.items()]
    encoded = container.write_file(L.KIND_CAMPAIGN, rows, header)
    container.read_file(encoded, L.KIND_CAMPAIGN)
    convert.validate_native_sections(sections, env, native=L.W2)
    model, _ = convert.reverse_slot(encoded, env, native=L.W2)
    native = oldsave.write_slot(model, L.W2)
    oldsave.read_slot(native, L.W2)
    # Reuse the native saver's normal writer for a second cycle. This detects
    # representable-but-unstable scalar/gear/power normalization before output.
    saved = convert.old_stream_to_new(native, env, native=L.W2, now=sections['META']['saved_at'],
                                       origin=1, writer='XML1 save importer',
                                       campaign_serial=header['campaign_serial'], optional_features=header['optional_features'])
    if saved.refused:
        raise ValueError('Native LC resave refused: ' + saved.refused)
    second, _ = convert.reverse_slot(saved.file_bytes, env, native=L.W2)
    if oldsave.write_slot(second, L.W2) != native:
        raise ValueError('Native LC second cycle changed campaign state.')
    if convert.representable(encoded, env, L.E10A2):
        header['required_features'] |= L.FEATURE_NATIVE_W2
        encoded = container.write_file(L.KIND_CAMPAIGN, rows, header)
    return encoded
