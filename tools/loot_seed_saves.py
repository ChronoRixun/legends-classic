"""Seeded LC saves for the loot + Forge acceptance (DESIGN 8.3 / 8.4: G1-G5 shop tiers, the level-adjustment check).

    python tools/loot_seed_saves.py --base REAL.lcsave --build BUILD_DIR --out SEEDED_DIR [--money 250000]

Reads one real LC save (read only), writes edited copies and `manifest.json` into SEEDED_DIR (a folder of its own; it
refuses any folder that holds or sits under a game install or the player's Documents\\Activision tree). The seeds are
campaign files in the layout the game reads from `<Documents>\\Activision\\<game>\\SaveLC\\saveslotN.lcsave`; copying
them there is the live task's job, not this tool's.

What a seed changes (everything else is the base file's, byte for byte: the other sections are copied as raw payload):
  HERO   every herostat hero except the two xpexempt guests (ProfXAstral, ProfXGladiator) gets the seed's level and the
         first-game XP total for it (XPCurve=xml1: T1(L), research/heroes/levels.md section 4), ack_level = level. The
         registry's "highest hero level" (shop and loot tier G = min(5, highest / 10 + 1)) skips xpexempt heroes, so it
         is exactly the seed's level. A seed may hold one hero below it (the level-adjustment seed).
  ITEM   money (tech_bits); one Danger Room reward in the carried inventory (a legacy instance: its OLD own-enhancement
         list, location 2) and its definition-state row (obtained); everything else the base holds (equipped XML2
         generated gear, old vendor stock) stays.
  ULCK   the Healer and the Forge in the campaign (the Xtraction menu offers them only then); no other change.
  META   the description (what the Load menu shows) and a campaign serial of its own per seed.
  KEYS   the documentation rows for ids the edit added.
The XML2-generated equipped gear a seed carries is whatever the base holds (affix-bearing instances on a hero), listed in
the manifest. Nothing here carries game data: names come from the player's own build at run time and the output is not
for Git.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lcsave import container as CT, convert, dump as dumpmod                     # noqa: E402
from lcsave.keys import DOMAIN_NUMBER, key_hash                                  # noqa: E402

XPEXEMPT = ('profxastral', 'profxgladiator')          # herostat xpexempt="true" (the registry's highest level skips them)
CARRIED = 2                                           # ITEM instance location: carried (3 = vendor stock, 4 sold, 5 stash)
LEGACY_REWARD = 'goddess_medallion'                   # a Danger Room reward whose OLD own list (3 records) differs from the
                                                      # rebuilt one (2): the step 8 migration is visible on it
DEFAULT_MONEY = 250_000                               # every Forge row is at most 15,000; a G5 Grab Bag is 50,000

# slot, name, highest non-exempt level, {hero: level} exceptions (the level-adjustment seed)
SEEDS = (
    (0, 'G1', 1, {}),
    (1, 'G2', 10, {}),
    (2, 'G3', 20, {}),
    (3, 'G4', 30, {}),
    (4, 'G5', 40, {}),
    (5, 'ADJ', 30, {'magma': 12}),                    # G4, with the generated-gear wearer well below the others
)


def xp_for_level(level):
    """XML1's XP total at the start of `level` (xbe 0x541e0; levels 1-45): T1(1) = 0,
    T1(n) = T1(n-1) + 5 (n + 8) f(n-1), f(L) = int(2.5 (4/3)^(L-1))"""
    if not 1 <= level <= 45:
        raise ValueError(f'level {level} outside the first game\'s 1-45')
    total = 0
    for n in range(2, level + 1):
        total += 5 * (n + 8) * int(2.5 * (4 / 3) ** (n - 2))
    return total


def tier(level):
    """shop / loot tier G of a highest hero level"""
    return min(5, level // 10 + 1)


# ---------------------------------------------------------------------------------------------------- the file
class Save:
    """a decoded LC campaign file whose untouched sections are carried as raw payload"""

    def __init__(self, buf):
        self.buf = bytes(buf)
        self.file = CT.read_file(self.buf)
        self.header = dict(self.file['header'])
        self.order = list(self.file['order'])
        self.sections = self.file['sections']
        self.dirty = set()

    def data(self, tag):
        d = self.sections[tag]['data']
        if d is None:
            raise ValueError(f'section {tag} is not decodable here')
        self.dirty.add(tag)
        return d

    def to_bytes(self):
        out = []
        for tag in self.order:
            s = self.sections[tag]
            e = s['entry']
            if tag in self.dirty:
                out.append((tag, e['major'], e['minor'], e['flags'], s['data']))
            else:
                out.append((tag, e['major'], e['minor'], e['flags'],
                            {'_opaque_payload': s['payload'], '_opaque_records': e['records']}))
        return CT.write_file(self.header['kind'], out, self.header)


def hero_name(env, hero_id):
    ent = env.catalogue.entry_of(hero_id)
    if ent is None:
        return None
    tag, e = ent
    return (env.name_of(tag, e['hash']) or '').lower() or None


def lookup(env, tag, *fields):
    v = env.catalogue.lookup(tag, key_hash(*fields))
    if v is None:
        raise ValueError(f'{tag} {"/".join(fields)} is not in the catalogue')
    return v


def add_key_rows(save, env, ids_with_text):
    """KEYS documents every id of the file; add the rows of ids the edit introduced"""
    if 'KEYS' not in save.sections:
        return
    keys = save.data('KEYS')['keys']
    have = {k['id'] for k in keys}
    for i, text in ids_with_text:
        if i not in have:
            ent = env.catalogue.entry_of(i)
            keys.append(dict(id=i, domain=DOMAIN_NUMBER[ent[0]] if ent else (i >> 24), key=text))
            have.add(i)


def set_levels(save, env, level, exceptions=None, exempt=XPEXEMPT):
    """level + XP for every non-exempt hero; exceptions {hero: level}. -> {hero: level} of the non-exempt heroes"""
    exceptions = {k.lower(): v for k, v in (exceptions or {}).items()}
    out = {}
    for h in save.data('HERO')['heroes']:
        name = hero_name(env, h['hero'])
        if name is None:
            raise ValueError(f'hero id {h["hero"]:#x} has no name in the build')
        if name in exempt:
            continue
        lv = exceptions.get(name, level)
        h['level'] = lv
        h['experience'] = xp_for_level(lv)
        h['ack_level'] = lv
        out[name] = lv
    return out


def set_money(save, amount):
    if not 0 <= amount <= 999_999:
        raise ValueError('money outside 0-999,999')
    save.data('ITEM')['tech_bits'] = amount


def legacy_own_list(env, build, name, count):
    """the OLD own-enhancement list of a legacy reward instance: `i/<name>/e1..eN` at interpolation 0.0"""
    return [dict(enhancement=lookup(env, 'ENHC', 'i', name, f'e{k}'), value=0) for k in range(1, count + 1)]


def add_carried_reward(save, env, name, own_count):
    """one carried instance of a (legacy) Danger Room reward and its definition-state row (obtained)"""
    item = save.data('ITEM')
    did = lookup(env, 'ITEM', name)
    inst = dict(definition=did, name_a=0, name_b=0, special=0, location=CARRIED, prefixes=[],
                own=legacy_own_list(env, None, name, own_count), suffixes=[], _extra=b'')
    item['instances'].append(inst)
    row = next((r for r in item['def_state'] if r['item'] == did), None)
    if row is None:
        item['def_state'].append(dict(item=did, quantity=0, flag=1))
    else:
        row['flag'] = 1
    ids = [(did, name)] + [(o['enhancement'], f'i/{name}/e{k}') for k, o in enumerate(inst['own'], 1)]
    add_key_rows(save, env, ids)
    return inst


def ensure_unlocked(save, env, names):
    """-> the names that had to be added to the campaign's unlocked list"""
    unlocked = save.data('ULCK')['unlocked']
    added = []
    for n in names:
        i = lookup(env, 'STAT', n)
        if i not in unlocked:
            unlocked.append(i)
            added.append(n)
    add_key_rows(save, env, [(lookup(env, 'STAT', n), n) for n in names])
    return added


def set_description(save, text, serial_name):
    meta = save.data('META')
    meta['description'] = text
    save.header['campaign_serial'] = int.from_bytes(hashlib.sha256(serial_name.encode('ascii')).digest()[:8], 'little')


# ---------------------------------------------------------------------------------------------------- inspection
def _kind_of(env, i):
    ent = env.catalogue.entry_of(i)
    return ent[0] if ent else None


def instance_summary(env, inst):
    def name(i):
        tag, e = env.catalogue.entry_of(i)
        return dumpmod._name(env, tag, e['hash'])
    return dict(definition=name(inst['definition']), location=inst['location'],
                prefixes=[name(e['enhancement']) for e in inst['prefixes']],
                own=[name(e['enhancement']) for e in inst['own']],
                suffixes=[name(e['enhancement']) for e in inst['suffixes']])


def generated_equipped(save, env):
    """[{hero, slot, definition, prefixes, suffixes}] of the equipped instances that carry a random prefix or suffix"""
    out = []
    for h in save.sections['HERO']['data']['heroes']:
        for k, inst in enumerate(h['equipped']):
            if inst['prefixes'] or inst['suffixes']:
                d = instance_summary(env, inst)
                out.append(dict(hero=hero_name(env, h['hero']), slot=k, definition=d['definition'],
                                prefixes=d['prefixes'], suffixes=d['suffixes']))
    return out


def vendor_stock(save, env):
    return [instance_summary(env, i)['definition'] for i in save.sections['ITEM']['data']['instances']
            if i['location'] == 3]


def refuse_out_dir(out):
    """a seed folder is never a game folder nor the player's Documents\\Activision tree"""
    p = os.path.abspath(out)
    low = p.replace('/', '\\').lower()
    if '\\documents\\activision' in low or low.endswith('\\activision') or '\\steamapps\\' in low:
        raise ValueError(f'{p}: refusing to write seeds into a game or Documents\\Activision folder')
    probe = p
    while True:
        if os.path.isfile(os.path.join(probe, 'XMen2.exe')) or os.path.isfile(os.path.join(probe, 'xmen2.exe')):
            raise ValueError(f'{p}: refusing to write seeds into a game folder ({probe} holds XMen2.exe)')
        up = os.path.dirname(probe)
        if up == probe:
            break
        probe = up


# ---------------------------------------------------------------------------------------------------- the seeds
def make_seed(base_buf, env, name, level, exceptions, money, description=None, *, reward=LEGACY_REWARD,
              reward_records=3, unlock=('healer', 'forge'), exempt=XPEXEMPT):
    """-> (bytes, info) of one seed (the keywords are the real build's defaults; the unit tests give an invented build's)"""
    save = Save(base_buf)
    levels = set_levels(save, env, level, exceptions, exempt)
    set_money(save, money)
    added = ensure_unlocked(save, env, unlock)
    add_carried_reward(save, env, reward, reward_records)
    set_description(save, description or f'SEED {name} L{level}', f'loot-seed-{name}-{level}-{sorted((exceptions or {}).items())}')
    highest = max(levels.values())
    info = dict(name=name, highest_level=highest, tier_G=tier(highest), hero_levels=levels, money=money,
                held_reward=dict(definition=reward, own_records=[f'i/{reward}/e{k}' for k in range(1, reward_records + 1)],
                                 location='carried'),
                unlocked_added=added, generated_equipped=generated_equipped(save, env), old_vendor_stock=vendor_stock(save, env))
    return save.to_bytes(), info


def verify_seed(path, base_buf, env, info):
    """re-read a written seed: container valid, only the intended sections changed, values as the manifest says"""
    buf = open(path, 'rb').read()
    new, base = CT.read_file(buf), CT.read_file(base_buf)
    problems = []
    changed = {t for t in new['order'] if new['sections'][t]['payload'] != base['sections'].get(t, {}).get('payload')}
    if not changed <= {'META', 'KEYS', 'ITEM', 'HERO', 'ULCK'}:
        problems.append(f'unexpected sections changed: {sorted(changed)}')
    if new['order'] != base['order']:
        problems.append('section order changed')
    d = dumpmod.dump_any(buf, env)
    levels = {h['hero']: h['level'] for h in d['heroes'] if h['hero'] not in XPEXEMPT}
    if levels != info['hero_levels']:
        problems.append('hero levels differ from the manifest')
    for h in d['heroes']:
        if h['hero'] not in XPEXEMPT and h['experience'] != xp_for_level(h['level']):
            problems.append(f'{h["hero"]}: experience {h["experience"]} is not T1({h["level"]})')
    if d['items']['tech_bits'] != info['money']:
        problems.append('money differs')
    held = [c for c in d['items']['carried'] if c['definition'] == LEGACY_REWARD and c['location'] == CARRIED]
    if len(held) != 1 or len(held[0]['own']) != 3:
        problems.append('the held reward is missing or has no old own list')
    if not {'healer', 'forge'} <= set(d['unlocked']):
        problems.append('healer / forge not unlocked')
    if max(levels.values()) != info['highest_level']:
        problems.append('highest level differs')
    if d['description'] != info['description']:
        problems.append('description differs')
    return problems


def build_env(build):
    """the environment of a `--loot xml1` build: the master catalogue with the build's keys appended and the rebuilt
    Danger Room rewards marked own_rebuilt (what the build's catalogue.lcc says), else the plain master catalogue"""
    if os.path.isfile(os.path.join(build, '_build', 'loot.json')):
        from xml1build import loot as LOOT
        return convert.Environment(build, catalogue=LOOT.derived_catalogue(build))
    return convert.Environment(build)


def check_load(path, env, build):
    """the reference loader (LC file -> the W2 native model) accepts a seed: -> (held reward's migrated own records, notes)"""
    from lcsave import layout as L, typed_registry
    reg_path = os.path.join(build, 'Data', 'lcsave', 'typed-entity-ids.txt')
    reg = typed_registry.load_registry(open(reg_path, 'rb').read()) if os.path.isfile(reg_path) else None
    model, notes = convert.reverse_slot(open(path, 'rb').read(), env, native=L.W2, registry=reg)
    held = [i for i in model['items']['carried'] if i['location'] == CARRIED
            and env.binds.item[i['definition']].lower() == LEGACY_REWARD]
    return [env.binds.enhancement[e['record']] for i in held for e in i['own']], notes


def run(base, build, out, money=DEFAULT_MONEY, load_check=True):
    refuse_out_dir(out)
    base_buf = open(base, 'rb').read()
    env = build_env(build)
    folder = os.path.join(out, 'SaveLC')
    os.makedirs(folder, exist_ok=True)
    manifest = dict(schema=1, base=dict(file=os.path.basename(base), sha256=hashlib.sha256(base_buf).hexdigest(),
                                        bytes=len(base_buf)),
                    build_used_for_names=os.path.basename(os.path.abspath(build)), xp_curve='xml1 (T1)',
                    layout='campaign .lcsave; copy to <Documents>\\Activision\\<game folder>\\SaveLC\\', seeds=[])
    problems = []
    for slot, name, level, exceptions in SEEDS:
        desc = f'SEED {name} L{level}' + (' + magma L12' if exceptions else '')
        data, info = make_seed(base_buf, env, name, level, exceptions, money, desc)
        info['description'] = desc
        file = f'saveslot{slot}.lcsave'
        path = os.path.join(folder, file)
        with open(path, 'wb') as f:
            f.write(data)
        info.update(slot=slot, file=f'SaveLC/{file}', sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        problems += [f'{name}: {p}' for p in verify_seed(path, base_buf, env, info)]
        if load_check:
            try:
                own, _ = check_load(path, env, build)
                info['loads_in_w2_reference'] = True
                info['held_reward_after_load'] = ['/'.join(r) for r in own]
            except Exception as e:             # noqa: BLE001 - any refusal is a problem of the seed
                info['loads_in_w2_reference'] = False
                problems.append(f'{name}: the reference loader refuses it: {e}')
        manifest['seeds'].append(info)
    with open(os.path.join(out, 'manifest.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(manifest, f, indent=1)
        f.write('\n')
    return manifest, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description='seeded LC saves for the loot + Forge acceptance (see the module docstring)')
    ap.add_argument('--base', required=True, help='a real LC campaign save (read only)')
    ap.add_argument('--build', required=True, help='a build folder of the same content (names come from it)')
    ap.add_argument('--out', required=True, help='an empty or dedicated folder; never a game folder')
    ap.add_argument('--money', type=int, default=DEFAULT_MONEY)
    ap.add_argument('--no-load-check', dest='load_check', action='store_false',
                    help='skip the reference loader pass (about 20 s per seed)')
    a = ap.parse_args(argv)
    manifest, problems = run(a.base, a.build, a.out, a.money, a.load_check)
    for s in manifest['seeds']:
        print(f'slot {s["slot"]} {s["name"]}: highest {s["highest_level"]} (G{s["tier_G"]}), money {s["money"]}, {s["file"]}')
    for p in problems:
        print('PROBLEM:', p)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
