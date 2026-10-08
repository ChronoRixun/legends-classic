"""xml1build.weapons - XML1's weapon definitions as style triggers (SPEC 29).

XML1 (default.xbe) arms a gun soldier through `weapon="wp_..."` on its stats entry: data/weapons/weapons.eng gives
the model and its bolt, and at fire time (the shared event `weapon_fire` = ce_atk_weap, Damage="L0" in XML1's
shared_combat_events.xml: a placeholder) the WEAPON supplies the damage and range, the muzzle effect, the tracer
(muzzleaccfx), the impact effect, the fire / charge sounds, a continuous beam or a projectile entity.

XMen2.exe has none of it (research/heroes/weapon_events.md, every address there):
  * its ce_atk_weap is the SOUND event class (factory 0x4fb550 -> the ce_sound constructor 0x4f9540), so a
    `weapon_fire` trigger plays nothing and hits nothing; the stats attribute `weapon` is accepted and dropped
    (0x4ba373 -> 0x4bb2e7); data/weapons/weapons.xmlb ships empty; none of XML1's weapon attribute names exist.
  * ch_constantbeam (0x4eee00) is a timer: while the beam is on it fires the move's triggers tagged 150 / 151 / 152
    every `timeinterval` (+ rand `intervalrandom`) seconds; ce_set_constantbeamdata reads only setbeam,
    timeinterval, intervalrandom; setbeam="true" also loops the move's tag-100 trigger if it is a sound.
  * the `beam` event (ce_atk_beam) is a one-call hit-scan: beambolt, beameffect (spawned once along the ray),
    hiteffect, damage, damagetype, damagescale, maxrange, pierce, noaimfx, useboltinfo, <damageMod name=.../>.
    XML2's own sustained flame (ps_pyro flame_dmg) is a beam with noaimfx + useboltinfo + pierce.
  * the `projectile` event (ce_atk_spawn_proj) spawns `count` copies of <entity> from data/entities/<filename> at
    `speed`, carrying the trigger's attack data; the entity carries its own damage too (both set here).
  * effect / sound / effect_sound: effect (relative to effects/), bolt, fxlevel; sound.

So, per (XML1 style, weapon) pair in use, characters writes a VARIANT style `x1_<style>_<weapon>`: the XML1
style with every `weapon_fire` trigger replaced by the weapon's own (`apply` below), and points the soldier's
stats entry at it (its character package follows). One XML1 style serves many weapons (ps_grso: mp5, laser,
lightning, nullifier, freeze, knockback, superlaser), hence variants. Value codes stay codes here (L1..L5, K10):
npc_values.resolve_style turns them into XML1's numbers afterwards (SPEC 24), in the styles and in the two
projectile entity files. A FightMove holds at most 19 triggers (0x4f6aa7), so a burst of 7 weapon_fire triggers
gets 2 triggers per shot: the attack and one effect_sound (muzzle flash + fire sound in one).
"""
from __future__ import annotations

import collections
import xml.etree.ElementTree as ET

WEAPON_TYPES = frozenset({'bullet', 'beam', 'flame', 'projectile'})   # melee weapons change nothing in the style
MAX_TRIGGERS = 19                                                      # XMen2.exe 0x4f6aa7: the 20th is freed
DEFAULT_BOLT = 'Bip01 R Hand'
FLAME_INTERVAL = '0.1'            # ch_constantbeam fires the tag-150 beam this often (XML2's ps_pyro: 0.08 s)
LOOP_TAG = '100'                  # the tag ch_constantbeam loops as a sound while the beam is on
DAMAGE_SCALE = 'difficulty'       # XML2's retail NPC attacks
# XML2's AI fires a FightMove only when it carries `aitype` (parser 0x4f6b80, the 20-name table at 0x6db940; XML1's
# AI chose by weapon and its styles have none): retail gun soldiers (ps_shocktrooper, ps_powguard) use
# aitype="beamanyrange" aireusetime="3" priority="5"; a thrown / fired entity (ps_mercenary) "projectile" 2.5;
# Pyro's short flame (ps_pyro power_attack) "projectilenear" 4.
AI_TYPE = {'bullet': 'beamanyrange', 'beam': 'beamanyrange', 'projectile': 'projectile', 'flame': 'projectilenear'}
AI_REUSE = {'bullet': '3', 'beam': '3', 'projectile': '2.5', 'flame': '4'}
AI_PRIORITY = '5'


def variant_name(mapped_style: str, weapon_name: str) -> str:
    """'ps_grso' + 'wp_mp5' -> 'x1_ps_grso_mp5' (a mapped 'x1_ps_x' keeps its prefix once)."""
    base = mapped_style[3:] if mapped_style.startswith('x1_') else mapped_style
    wp = weapon_name[3:] if weapon_name.lower().startswith('wp_') else weapon_name
    return f'x1_{base}_{wp}'.lower()


# The thrown grenade (issue #36): XML1's moveset_grenade hardcodes entity="grenade" and default.xbe chose the
# thrown entity at runtime from the weapon's grenade= (weapons.eng) or the spawner's monster_grenade= (a unanimous
# override; on the XML1 disc it sits on the six nuclear-plant NukeGuard spawners, whose weapon names the default).
# The builder materializes that choice per holder. Runtime traces execute the canonical power_smash
# from moveset1; its grenade_projectile supplies the actual entity. The variant powerstyle retains an auxiliary
# power_grenade copy at priority 9, whose entity stays aligned with the moveset. Its selection/priority necessity
# is not established by the acceptance runs. Shared guns need per-grenade variants; a unanimous spawner override
# grants moveset1 to holders whose XML1 stats did not carry it (the nuclear-plant guards).
GRENADE_MOVESET = 'moveset_grenade'   # moveset1 supplies the actual entity selected at throw time
DEFAULT_GRENADE = 'grenade'           # the entity XML1's moveset_grenade hardcodes
GRENADE_MOVE = 'power_grenade'        # auxiliary copy in the variant powerstyle
GRENADE_TRIGGER = 'grenade_projectile'
AI_GRENADE_TYPE = 'grenade'           # XML1's aitype; a name XMen2.exe's aitype table knows (0x2dba6c)
GRENADE_AIREUSE = '7'                 # XML1's aireusetime on moveset_grenade's power_smash
GRENADE_PRIORITY = '9'                # retained auxiliary-copy policy, above the guns' AI_PRIORITY


def grenade_variant_name(mapped_style: str, grenade: str) -> str:
    """'moveset_grenade' + 'flashbang' -> 'x1_moveset_grenade_flashbang' (a mapped 'x1_foo' keeps its prefix once)."""
    base = mapped_style[3:] if mapped_style.startswith('x1_') else mapped_style
    return f'x1_{base}_{grenade}'.lower()


def apply_grenade(root, grenade: str, where: str = '') -> collections.Counter:
    """point every grenade_projectile trigger's entity at `grenade` (filename stays the entity file the trigger
    names, data/entities/grenade_ents, which carries grenade / flashbang / incendiary). Returns counts;
    `root` is changed in place."""
    rep = collections.Counter()
    for c in root.iter('trigger'):
        a = _lower(c)
        if (a.get('name') or '').lower() != GRENADE_TRIGGER:
            continue
        c.set('entity', grenade)
        rep['grenade_projectile_entity_set'] += 1
    return rep


def grenade_moveset_want(moveset1: str, weapon, override: str, map_fightstyle) -> str:
    """the moveset1 the built entry must carry ('' = the base moveset stands): when XML1 would throw a grenade
    other than the default, the variant of the entry's (mapped) grenade moveset that throws it. moveset1: the
    entry's XML1 moveset1 ('' when XML1's data has none: then only a spawner override is known to grant the throw
    - XML1's spawner attribute alone did, e.g. the NukeGuards - and the shared grenade moveset is the variant's
    base; a weapon's grenade= by itself grants no move the data did not give)."""
    g = effective_grenade(weapon, override)
    if not g or g.lower() == DEFAULT_GRENADE or (not moveset1 and not override):
        return ''
    base = map_fightstyle((moveset1 or GRENADE_MOVESET).lower())
    return grenade_variant_name(base, g)


def variant_grenade_name(variant: str, grenade: str) -> str:
    """'x1_ps_grso_mp5' + 'flashbang' -> 'x1_ps_grso_mp5_flashbang' (the variant identity of a gun whose
    effective grenade is not the default; the default keeps the plain SPEC 29 name)."""
    return f'{variant}_{grenade}'.lower()


def variant_grenade(variant: str, grenades) -> str:
    """the grenade entity a variant name names ('' when it names none): 'x1_ps_grso_mp5_flashbang' -> 'flashbang'
    when the suffix is one of `grenades` (the entity names of XML1's grenade_ents)."""
    tail = variant.rsplit('_', 1)[-1]
    return tail if tail.lower() in grenades else ''


def grenade_move(grenade: str) -> ET.Element:
    """Auxiliary POWERSTYLE copy of XML1's moveset_grenade power_smash: XML1's own aitype "grenade"
    (a name XMen2.exe's 20-name aitype table knows) at the retained GRENADE_PRIORITY, XML1's
    aireusetime 7, the same animation, sound, grenade bolton and grenade_projectile trigger, throwing `grenade`
    from data/entities/grenade_ents."""
    m = ET.Element('FightMove', {'name': GRENADE_MOVE, 'animenum': 'ea_power2', 'handler': 'ch_grenade',
                                 'aitype': AI_GRENADE_TYPE, 'aireusetime': GRENADE_AIREUSE,
                                 'priority': GRENADE_PRIORITY, 'lockangles': 'true'})
    ET.SubElement(m, 'trigger', {'name': 'stop', 'time': '0'})
    ET.SubElement(m, 'trigger', {'name': 'sound', 'sound': 'character/grso_m/throw_grenade', 'time': '0.4'})
    ET.SubElement(m, 'trigger', {'name': GRENADE_TRIGGER, 'type': 'ce_atk_spawn_grenade', 'time': '0.45',
                                 'filename': 'grenade_ents', 'entity': grenade, 'count': '1',
                                 'actorbolt': 'Bip01 L Hand'})
    ET.SubElement(m, 'trigger', {'name': 'bolton', 'type': 'ce_bolton', 'time': '0.1',
                                 'model': 'models/weapons/grenade', 'bolt': 'Bip01 L Hand',
                                 'boltslot': 'ebolton_altweapon', 'attachpoint': 'Grab1'})
    ET.SubElement(m, 'trigger', {'name': 'removebolton', 'type': 'ce_bolton', 'time': '0.44',
                                 'removebolton': 'true', 'boltslot': 'ebolton_altweapon'})
    ET.SubElement(m, 'chain', {'action': 'idle', 'result': 'idle'})
    return m


def effective_grenade(weapon, override: str) -> str:
    """the entity XML1's runtime would throw: the spawner's monster_grenade beats the weapon's grenade= (on the
    XML1 disc the override is the NukeGuards' only non-default path; its weapon names the default), then the
    weapon's grenade=, else '' (the XML1 soldier did not throw)."""
    g = (override or '').strip()
    if g:
        return g
    return (weapon or {}).get('grenade', '').strip()


def grenade_powerstyle_want(powerstyle: str, weapon_name: str, weapon, override: str, map_powerstyle) -> str:
    """the powerstyle variant the built entry must carry ('' = the SPEC 29 variant stands): when XML1 would
    throw a non-default grenade (the spawner monster_grenade override beats the weapon's grenade=), the weapon
    variant suffixed with that entity - the same name characters.weapon_style writes. powerstyle: the base style
    (the entry's XML1 powerstyle, else the weapon's own)."""
    g = effective_grenade(weapon, override)
    if not g or g.lower() == DEFAULT_GRENADE or not powerstyle:
        return ''
    return variant_grenade_name(variant_name(map_powerstyle(powerstyle.lower()), weapon_name), g)


def grenade_override_votes(map_roots) -> dict:
    """{character lower: {grenade: set of map rels}} of monsterspawnerent monster_grenade votes across parsed
    XML1 map roots (the .eng maps carry every spawner; one language is enough - all name the same entities)."""
    votes = {}
    for rel, root in map_roots:
        for el in root.iter():
            g = (el.get('monster_grenade') or '').strip()
            ch = (el.get('character') or '').strip().lower()
            if g and ch:
                votes.setdefault(ch, {}).setdefault(g, set()).add(rel)
    return votes


def gun_fightstyle(weapon) -> str:
    """The XML1 fighting style a gun gives its holder, or '' (a melee weapon, a gun without one, no weapon).

    default.xbe replaces the holder's selected fighting style with the weapon's while it is armed (spawn's weapon
    assignment 0x327A0 installs it in fighting-style slot 1, 0xED300 / 0xED390, and 0x30890 overwrites animation
    slot 1 with its animations; the talent's style is kept only to restore it), and XML1's character bundles list
    only the weapon's style. XMen2.exe uses one fighting-style talent per character (the lowest talent id,
    0x43B0A0), so the stats entry carries the weapon's style INSTEAD of its own (characters.convert_stats)."""
    if not weapon or (weapon.get('type') or '').lower() not in WEAPON_TYPES:
        return ''
    return (weapon.get('fightstyle') or '').strip()


def fightstyle_problems(fight_talents, weapon, map_fightstyle) -> list:
    """V5 (SPEC 57): a stats entry armed with an XML1 gun must carry exactly that
    gun's fighting style (mapped: map_fightstyle) as its only fighting-style talent. fight_talents: the entry's
    fighting-style talent names in file order. Returns problem strings (empty when fine or not a gun)."""
    want = gun_fightstyle(weapon)
    if not want:
        return []
    want = map_fightstyle(want).lower()
    have = [t.lower() for t in fight_talents]
    if have == [want]:
        return []
    return [f'gun {weapon.get("name")!r} gives fighting style {want!r} (XML1 replaces the entry\'s style while '
            f'armed; XMen2.exe uses one fighting-style talent), but the entry has {have}']


def bind_style_package(root, base: str, variant: str, kind: str = 'powerstyles'):
    """A variant style's own package must load that variant, not its source style.

    The source bundle also carries effects/entities and sometimes other styles. Replace only
    its self-reference, preserving dependency entries and their order. Missing self-references
    (including asset-only bundles) get an explicit XML entry.
    """
    old, new = f'data/{kind}/{base}', f'data/{kind}/{variant}'
    for entry in root:
        if entry.tag.lower() in ('xml', 'xml_resident', 'fightstyle') and \
                (entry.get('filename') or '').replace('\\', '/').lower() == old:
            entry.set('filename', new)
    if not any(entry.tag.lower() in ('xml', 'xml_resident', 'fightstyle') and
               (entry.get('filename') or '').replace('\\', '/').lower() == new for entry in root):
        ET.SubElement(root, 'xml', {'filename': new})


def _lower(el) -> dict:
    return {k.lower(): v for k, v in el.attrib.items()}


# XML1's gun damage draw (default.xbe, shared by every weapon type's fire path): the weapon parser resolves the
# damage code through the values getter with a NULL maximum pointer and stores only the minimum (0xbc2ef-0xbc30d,
# the parsed word at prototype +0x1c6); at fire time 0xbcc47-0xbcc99 loads that minimum and makes ONE integer
# RNG draw (0x1233c0) between trunc(min x 0.7f) and trunc(min x 1.3f) - the binary32 constants at 0x3ca9d8 and
# 0x3d4a60 - which becomes the attack's damage. The authored code maximum is never a bound, so the trigger the
# builder writes carries the draw's bounds instead of the code's range.
GUN_DRAW_LO = 0.699999988079071            # default.xbe 0x3ca9d8: binary32 0.7 (not idealized 0.7)
GUN_DRAW_HI = 1.2999999523162842           # default.xbe 0x3d4a60: binary32 1.3 (not idealized 1.3)


def gun_damage_range(values, damage):
    """XML1's gun-draw bounds 'lo hi' for a weapon damage declaration (a value code or a plain number),
    computed from the declaration's resolved MINIMUM as the fire path draws it. None when the minimum does
    not resolve (the declaration stays as written and npc_values.resolve_style reports it as today).
    `values`: heroes.Values of XML1's data/values.xml; None-safe (a caller without a table gets None)."""
    if values is None:
        return None
    try:
        resolved = values.resolve(damage)
    except (KeyError, TypeError, AttributeError):
        return None
    try:
        minimum = float(str(resolved).split()[0])
    except (TypeError, ValueError):
        return None
    return f'{int(minimum * GUN_DRAW_LO)} {int(minimum * GUN_DRAW_HI)}'


def _attack(w: dict, extra: dict) -> ET.Element:
    """an attack trigger with the weapon's damage data (+ its damageMod child) and `extra`."""
    a = dict(extra)
    if w.get('damage'):
        a['damage'] = w['damage']                 # a code (L3) or a number: resolved later (SPEC 24)
    a['damagetype'] = w.get('damagetype') or 'dmg_physical'
    if w.get('range'):
        a['maxrange'] = w['range']
    a['damagescale'] = DAMAGE_SCALE
    a['damagelevel'] = '1'
    el = ET.Element('trigger', a)
    if w.get('damagemod'):
        ET.SubElement(el, 'damageMod', {'name': w['damagemod']})
    return el


def _fx_sound(w: dict, t: str, fx_key: str, sound_key: str, bolt: str) -> list:
    """one trigger for the effect + the sound (effect_sound) when both exist, else whichever exists."""
    fx, snd = w.get(fx_key), w.get(sound_key)
    if fx and snd:
        return [ET.Element('trigger', {'name': 'effect_sound', 'effect': fx, 'sound': snd, 'bolt': bolt, 'time': t})]
    if fx:
        return [ET.Element('trigger', {'name': 'effect', 'effect': fx, 'bolt': bolt, 'time': t})]
    if snd:
        return [ET.Element('trigger', {'name': 'sound', 'sound': snd, 'time': t})]
    return []


def _beam(w: dict, t: str, bolt: str, flame: bool = False) -> ET.Element:
    a = {'name': 'beam', 'time': t, 'attacktype': 'beam', 'arc': '0', 'beambolt': bolt,
         'pierce': 'true' if flame else 'false'}
    if flame:
        a.update({'noaimfx': 'true', 'useboltinfo': 'true'})      # XML2's ps_pyro flame_dmg form
    if w.get('muzzleaccfx'):
        a['beameffect'] = w['muzzleaccfx']                        # the tracer / the flame along the ray
    if w.get('impactfx'):
        a['hiteffect'] = w['impactfx']
    return _attack(w, a)


def shot_triggers(w: dict, t: str, with_fx: bool = True) -> list:
    """the triggers that replace one `weapon_fire` at time t for a bullet / beam / projectile weapon."""
    bolt = w.get('actorbolt', DEFAULT_BOLT)
    kind = (w.get('type') or '').lower()
    out = []
    if kind in ('bullet', 'beam'):
        out.append(_beam(w, t, bolt))
    elif kind == 'projectile':
        a = {'name': 'projectile', 'time': t, 'attacktype': 'projectile',
             'actorbolt': bolt, 'count': '1', 'targetable': 'true'}
        if w.get('projectileent'):
            a['entity'] = w['projectileent']
        if w.get('entfile'):
            a['filename'] = w['entfile']
        if w.get('projectilespeed'):
            a['speed'] = w['projectilespeed']
        out.append(_attack(w, a))
    if with_fx:
        out += _fx_sound(w, t, 'muzzlefx', 'firesound', bolt)
    return out


def flame_triggers(w: dict, t: str, tag: str | None) -> list:
    """a continuous weapon's shot: the flame beam (tagged when the original was: ch_constantbeam fires it every
    FLAME_INTERVAL while the beam is on) and, for the tagged form, the roar the engine loops on tag 100."""
    bolt = w.get('actorbolt', DEFAULT_BOLT)
    beam = _beam(w, t, bolt, flame=True)
    out = [beam]
    if tag:
        beam.set('tag', tag)
        if w.get('firesound'):
            out.append(ET.Element('trigger', {'name': 'sound', 'sound': w['firesound'], 'tag': LOOP_TAG, 'time': '-1'}))
    elif w.get('firesound'):
        out.append(ET.Element('trigger', {'name': 'sound', 'sound': w['firesound'], 'time': t}))
    return out


def charge_triggers(w: dict, t_fire: float) -> list:
    """the wind-up (chargefx / chargesound) `warmuptime` before the first shot, never before 0."""
    if not (w.get('chargefx') or w.get('chargesound')):
        return []
    try:
        warm = float(w.get('warmuptime') or 0)
    except ValueError:
        warm = 0.0
    t = max(0.0, t_fire - warm)
    return _fx_sound(w, f'{t:g}', 'chargefx', 'chargesound', w.get('actorbolt', DEFAULT_BOLT))


def _weapon_event_chain(events: dict, name: str):
    """(True, weapon name or '', boltselect or '') when the named style event inherits XML1's `weapon_fire`
    (directly or through other events of the same style); the nearest `weapon=` / `boltselect=` wins."""
    weapon, bolt, seen = '', '', set()
    while name and name.lower() not in seen:
        seen.add(name.lower())
        if name.lower() == 'weapon_fire':
            return True, weapon, bolt
        ev = events.get(name.lower())
        if ev is None:
            return False, '', ''
        a = _lower(ev)
        weapon = weapon or a.get('weapon', '')
        bolt = bolt or a.get('boltselect', '')
        name = a.get('inherit', '')
    return False, '', ''


def _drop_bolton_churn(move, dry=False) -> int:
    """Remove (or, with dry=True, just count) a mid-move bolton holster/redraw cycle (a removebolton whose
    boltslot is re-added later in the same FightMove, plus that re-add): the weapon simply stays attached. XML1
    attached the fire sound to the weapon_fire EVENT, so every shot of a burst played it; XMen2.exe has no such
    inheritance and a FightMove holds at most MAX_TRIGGERS triggers, so a 6-10 shot burst needs those slots for
    its per-shot sound (issue #83: Mystique's pistols went silent after the first shots).
    Returns the number of triggers removed (twice the number of cycles)."""
    trigs = [c for c in move if c.tag.lower() == 'trigger']
    order = {id(c): i for i, c in enumerate(trigs)}
    pending_adds = {}       # boltslot -> the 'bolton' adds not yet consumed by a churn pair
    for c in trigs:
        a = _lower(c)
        if (a.get('name') or '').lower() == 'bolton' and a.get('boltslot'):
            pending_adds.setdefault(a['boltslot'], []).append(c)
    drop = []
    for c in trigs:
        a = _lower(c)
        if (a.get('name') or '').lower() == 'removebolton' and a.get('boltslot') in pending_adds:
            later = [x for x in pending_adds[a['boltslot']] if order[id(x)] > order[id(c)]]
            if later:
                drop.append(c)
                drop.append(later[0])
                pending_adds[a['boltslot']].remove(later[0])
    if not dry:
        for c in drop:
            move.remove(c)
    return len(drop)


def rewrite_weapon_events(root, weapons: dict, where: str = '', values=None) -> collections.Counter:
    """XML1 styles can also NAME a weapon on an event of their own: ps_mystique's `left_gun` / `right_gun` are
    `<event inherit="weapon_fire" weapon="wp_myst_pistol" [boltselect=...]>`, fired by plain triggers with those
    names. XMen2.exe builds `weapon_fire` as a sound event (see the module doc), so every such shot did nothing.
    Each such event (at the style root or inside a FightMove) becomes a `beam` event with the weapon's data,
    exactly as `shot_triggers` builds a bullet / beam shot (beambolt = the event's `boltselect`, else the weapon's
    `actorbolt`). The triggers keep their names, so no move gains a trigger for the shot itself; the weapon's
    muzzle flash + fire sound (one `effect_sound`) go on the burst's shots. A FightMove holds at most
    MAX_TRIGGERS triggers, so when the shots do not all fit, a mid-move bolton holster/redraw cycle is dropped
    first (the weapon stays attached) to give every shot its sound, as XML1's weapon_fire event did (issue #83);
    shots beyond the cap still go without. Projectile / flame weapons named this way are reported, not
    rewritten (none on the disc). `values`: heroes.Values - when given, each rewritten event carries the XML1
    gun draw of its weapon's damage minimum (gun_damage_range), as weapons.apply does for the variants.
    Returns counts; `root` is changed in place."""
    rep = collections.Counter()
    events = {}
    for ev in root.iter('event'):
        n = (_lower(ev).get('name') or '').lower()
        if n and n not in events:
            events[n] = ev
    shots = {}                                # event name -> (weapon record, bolt) of each rewritten event
    chains = {n: _weapon_event_chain(events, n) for n in events}      # before any event is rewritten
    for n, ev in events.items():
        found, wname, bolt = chains[n]
        if not found or not wname:
            continue
        w = weapons.get(wname.lower())
        if w is None:
            rep['weapon_event_unknown_weapon'] += 1
            continue
        if values is not None and w.get('damage'):
            drawn = gun_damage_range(values, w['damage'])
            if drawn is not None:
                w = dict(w, damage=drawn)
                rep['gun_damage_drawn'] += 1
        kind = (w.get('type') or '').lower()
        if kind not in ('bullet', 'beam'):
            rep[f'weapon_event_{kind or "untyped"}_kept'] += 1
            continue
        bolt = bolt or w.get('actorbolt', DEFAULT_BOLT)
        beam = _beam(w, '0', bolt)
        orig_name = _lower(ev).get('name')
        ev.attrib.clear()
        for k, v in beam.attrib.items():
            if k not in ('name', 'time'):
                ev.set(k, v)
        ev.set('name', orig_name)
        ev.set('inherit', 'beam')
        for c in list(ev):
            ev.remove(c)
        for c in beam:
            ev.append(c)
        shots[n] = (w, bolt)
        rep['weapon_event_to_beam'] += 1
    if not shots:
        return rep
    for move in root.iter('FightMove'):
        trigs = [c for c in move if c.tag.lower() == 'trigger']
        fired = [c for c in trigs if (_lower(c).get('name') or '').lower() in shots]
        if not fired:
            continue
        rep['weapon_event_moves'] += 1
        rep['weapon_event_shots'] += len(fired)
        room = MAX_TRIGGERS - len(trigs)
        if room < len(fired):
            # XML1 played the fire sound on EVERY shot of the burst (it rides the weapon_fire event); reclaim
            # a mid-move holster/redraw cycle so as many shots as possible carry their sound (issue #83).
            reclaimed = _drop_bolton_churn(move)
            rep['weapon_event_bolton_churn_dropped'] += reclaimed // 2
            trigs = [c for c in move if c.tag.lower() == 'trigger']
            room = MAX_TRIGGERS - len(trigs)
        for c in fired:
            if room <= 0:
                break
            w, bolt = shots[(_lower(c).get('name') or '').lower()]
            fx = _fx_sound(w, _lower(c).get('time', '0'), 'muzzlefx', 'firesound', bolt)
            for el in fx[:room]:
                move.insert(list(move).index(c) + 1, el)
                room -= 1
                rep['weapon_event_fx_added'] += 1
        if sum(1 for c in move if c.tag.lower() == 'trigger') > MAX_TRIGGERS:
            rep['moves_over_trigger_cap'] += 1
    return rep


def silent_shots(root) -> list:
    """V42 (SPEC 29.4): ['<move>:<trigger name>'] for gun-shot triggers whose shot carries no fire sound while
    the same FightMove still spends triggers on a mid-move bolton holster/redraw cycle (a removebolton whose
    boltslot is re-added later in the move). The reclaimed slots belong to the burst's sound (issue #83)."""
    if root is None:
        return []
    out = []
    for top in (list(root) if root.tag == 'xmlb_multiple_roots' else [root]):
        shot_ev = {(_lower(ev).get('name') or '').lower()
                   for ev in top.iter('event')
                   if (_lower(ev).get('inherit') or '').lower() == 'beam'
                   and (_lower(ev).get('attacktype') or '').lower() == 'beam'}
        if not shot_ev:
            continue
        for move in top.iter('FightMove'):
            trigs = [c for c in move if c.tag.lower() == 'trigger']
            fired = [c for c in trigs if (_lower(c).get('name') or '').lower() in shot_ev]
            if not fired:
                continue
            after = {id(a): b for a, b in zip(trigs, trigs[1:])}
            quiet = [c for c in fired
                     if after.get(id(c)) is None or (_lower(after[id(c)]).get('name') or '').lower() != 'effect_sound']
            if not quiet:
                continue
            if _drop_bolton_churn(move, dry=True):
                mname = _lower(move).get('name', '?')
                out += [f'{mname}:{(_lower(c).get("name") or "?")}' for c in quiet]
    return out


def weapon_fire_left(root) -> list:
    """[('<move>:<trigger name>', names_a_weapon)] for every trigger of a style that still fires XML1's
    `weapon_fire`, by its own name (names_a_weapon False: the stats entry's weapon would supply the shot) or through
    style events inheriting it (True when the chain names a `weapon=`): validator V5 (SPEC 29.3)."""
    if root is None:
        return []
    roots = list(root) if root.tag == 'xmlb_multiple_roots' else [root]
    out = []
    for top in roots:
        events = {}
        for ev in top.iter('event'):
            n = (_lower(ev).get('name') or '').lower()
            if n and n not in events:
                events[n] = ev
        for move in top.iter('FightMove'):
            mname = _lower(move).get('name', '?')
            for c in move:
                if c.tag.lower() != 'trigger':
                    continue
                a = _lower(c)
                n = (a.get('inherit') or a.get('name') or '').lower()
                if a.get('type') or not n:
                    continue
                found, wname, _bolt = _weapon_event_chain(events, n)
                if n == 'weapon_fire' or found:
                    out.append((f'{mname}:{a.get("name") or n}', bool(wname)))
    return out


def apply(root, w: dict, where: str = '', grenade: str = '', values=None) -> collections.Counter:
    """replace every weapon_fire trigger of every FightMove with the weapon's triggers; for a continuous (flame)
    weapon also give the constant beam its firing interval. Then carry the soldier's grenade throw (issue #36):
    XML1's holders of a grenade= weapon throw that grenade from moveset_grenade. Runtime traces execute the
    canonical power_smash in moveset1; this variant retains an auxiliary power_grenade copy with a consistent
    entity (XML1's aitype "grenade", at the retained priority above the guns).
    `grenade`: the effective entity
    (the spawner override beats the weapon's grenade=); '' = the weapon's own grenade=; a variant whose effective
    grenade is non-default is named for it by the caller (weapons.variant_grenade_name). `values`: heroes.Values
    of XML1's values table - when given, the weapon's damage declaration becomes the XML1 gun draw of its
    minimum (gun_damage_range; the shot carries the draw's bounds, not the code's range). Returns counts;
    `root` is changed in place."""
    rep = collections.Counter()
    kind = (w.get('type') or '').lower()
    if kind not in WEAPON_TYPES:
        return rep
    if values is not None and w.get('damage'):
        drawn = gun_damage_range(values, w['damage'])
        if drawn is not None:
            w = dict(w, damage=drawn)
            rep['gun_damage_drawn'] += 1
    for move in root.iter('FightMove'):
        trigs = [c for c in move if c.tag.lower() == 'trigger']
        fires = [c for c in trigs if (_lower(c).get('name') or '').lower() == 'weapon_fire']
        if not fires:
            continue
        others = len(trigs) - len(fires)
        first = True
        new_children = []
        for c in list(move):
            if c in fires:
                a = _lower(c)
                t = a.get('time', '0')
                if kind == 'flame':
                    repl = flame_triggers(w, t, a.get('tag'))
                else:
                    # the fire sound + muzzle flash on every shot while the move's 19 triggers allow it, else
                    # on every other shot of a burst
                    budget = MAX_TRIGGERS - others - len(fires) * 2
                    with_fx = first or budget >= 0 or (fires.index(c) % 2 == 0)
                    repl = shot_triggers(w, t, with_fx)
                    if a.get('tag'):
                        for r in repl:
                            r.set('tag', a['tag'])
                if first:
                    try:
                        repl = charge_triggers(w, float(t)) + repl
                    except ValueError:
                        pass
                first = False
                new_children += repl
                rep['weapon_fire_replaced'] += 1
                rep[f'weapon_{kind}'] += 1
            else:
                new_children.append(c)
        for c in list(move):
            move.remove(c)
        for c in new_children:
            move.append(c)
        n = sum(1 for c in move if c.tag.lower() == 'trigger')
        if n > MAX_TRIGGERS:
            rep['moves_over_trigger_cap'] += 1
        ma = _lower(move)
        if not ma.get('aitype'):                      # let XML2's AI pick the move (see AI_TYPE)
            move.set('aitype', AI_TYPE[kind])
            move.set('aireusetime', AI_REUSE[kind])
            if not ma.get('priority'):
                move.set('priority', AI_PRIORITY)
            rep['aitype_added'] += 1
        if kind == 'flame':
            for c in move:
                a = _lower(c)
                if c.tag.lower() == 'trigger' and (a.get('type') or '').lower() == 'ce_set_constantbeamdata' \
                        and (a.get('setbeam') or '').lower() == 'true' and not a.get('timeinterval'):
                    c.set('timeinterval', FLAME_INTERVAL)
                    rep['constantbeam_interval_set'] += 1
    g = (grenade or w.get('grenade') or '').strip()
    if g and not any((_lower(m).get('name') or '').lower() == GRENADE_MOVE for m in root.iter('FightMove')):
        root.append(grenade_move(g))
        rep['grenade_move_added'] = 1
        rep[f'grenade_{g.lower()}'] = 1
    return rep


# ------------------------------------------------------------------------------------------ validator (V-TBD)

def _gun_shot_els(root) -> list:
    """every element of a built style tree that _attack wrote: a beam / projectile shot trigger, or a beam
    event rewritten from a style-named weapon (SPEC 29.3). XML1's own power beams (ps_havok's name="beam")
    carry no damagescale / damagelevel, so the fingerprint (damagescale=difficulty + damagelevel=1 + damage)
    matches gun shots only."""
    out = []
    if root is None:
        return out
    for e in root.iter():
        if not isinstance(e.tag, str):
            continue
        a = _lower(e)
        if (a.get('damagescale') or '').lower() != DAMAGE_SCALE or a.get('damagelevel') != '1' \
                or not a.get('damage'):
            continue
        if e.tag.lower() == 'trigger' and (a.get('name') or '').lower() in ('beam', 'projectile'):
            out.append(e)
        elif e.tag.lower() == 'event' and (a.get('inherit') or '').lower() == 'beam':
            out.append(e)
    return out


def _is_gun_draw(lo: int, hi: int) -> bool:
    """True when (lo, hi) is XML1's draw of some whole-number minimum: an m with trunc(m x 0.7f) == lo and
    trunc(m x 1.3f) == hi. Such an m lies within +/-3 of lo / 0.7f (the m interval is ~1.43 wide)."""
    centre = round(lo / GUN_DRAW_LO)
    return any(int(m * GUN_DRAW_LO) == lo and int(m * GUN_DRAW_HI) == hi
               for m in range(max(0, centre - 3), centre + 4))


def validate(v, ck) -> None:
    """V-TBD (SPEC section number assigned at merge): XML1's weapon fire rolls ONE integer draw between
    trunc(min x 0.7f) and trunc(min x 1.3f) of the damage code's MINIMUM (default.xbe 0xbcc47-0xbcc99; the
    authored maximum is never a bound), so (1) every gun-shot trigger of a built style must carry a range
    that is exactly that draw of some minimum, and (2) a powerstyle named for an XML1 weapon
    (weapons.variant_name, a non-default grenade suffix aside) must carry exactly that weapon's draw.
    XML1's entity parser reads explodedamage as ONE number - the code's minimum (0x97940-0x97953) - so
    (3) a built entity file's single-value attributes must hold one number, never a 'min max' range."""
    ctx = v.ctx
    from . import heroes as H                  # noqa: WPS433 - heroes imports this package's modules lazily too
    from . import npc_values as NV             # noqa: WPS433 - the single-value entity attribute names
    try:
        values = H.Values(ctx.read_x1_xml('data/values.xml'))
    except Exception:          # noqa: BLE001 - no XML1 source readable: the draw cannot be recomputed
        ck.warn('XML1 data/values.xml not readable: gun damage rolls (SPEC 29) unverified')
        return
    x1_weapons = {}
    try:
        root = ctx.read_x1_xml('data/weapons/weapons.eng')
        x1_weapons = {(w.get('name') or '').lower(): {k.lower(): val for k, val in w.attrib.items()}
                      for w in root.iter() if isinstance(w.tag, str) and w.tag.lower() == 'weapon' and w.get('name')}
    except Exception:          # noqa: BLE001
        ck.warn('XML1 data/weapons/weapons.eng not readable: weapon-variant draws (SPEC 29) unverified')
    grenades = set()
    try:
        ent_rel = next((r for r in ('data/entities/grenade_ents.eng', 'data/entities/grenade_ents.xml')
                        if ctx.x1_path(r)), None)
        if ent_rel is not None:
            grenades = {(e.get('name') or '').strip().lower()
                        for e in ctx.read_x1_xml(ent_rel).iter()
                        if isinstance(e.tag, str) and e.tag.lower() == 'entity' and e.get('name')}
    except Exception:          # noqa: BLE001
        grenades = set()
    for rel in v.idx.under('data/powerstyles/'):
        if v.entry(rel) is None or not rel.lower().endswith(('.xmlb', '.engb')):
            continue                       # XML2 retail styles: not gun conversions
        root = v.tree(rel)
        shots = _gun_shot_els(root)
        if not shots:
            continue
        for e in shots:
            ck.count('gun_shot_triggers_checked')
            parts = (e.get('damage') or '').split()
            nums = []
            if len(parts) == 2:
                try:
                    nums = [float(parts[0]), float(parts[1])]
                except ValueError:
                    pass
            if len(nums) != 2 or nums[0] != int(nums[0]) or nums[1] != int(nums[1]) \
                    or not _is_gun_draw(int(nums[0]), int(nums[1])):
                ck.error(f'{rel}: gun shot damage {e.get("damage")!r} is not XML1\'s draw trunc(min*0.7f)..'
                         f'trunc(min*1.3f) of one minimum (SPEC 29)')
        if not x1_weapons:
            continue
        name = rel.rsplit('/', 1)[-1].rsplit('.', 1)[0].lower()
        g = variant_grenade(name, grenades)
        if g:
            name = name[:-(len(g) + 1)]
        for wname, wrec in x1_weapons.items():
            if (wrec.get('type') or '').lower() not in WEAPON_TYPES:
                continue
            suffix = wname[3:] if wname.startswith('wp_') else wname
            if not (name.startswith('x1_') and name.endswith('_' + suffix)):
                continue
            ck.count('gun_variant_styles_checked')
            want = gun_damage_range(values, wrec.get('damage'))
            if want is None:
                ck.warn(f'{rel}: {wname} damage {wrec.get("damage")!r} does not resolve; its draw not checked')
                break
            for e in shots:
                if e.get('damage') != want:
                    ck.error(f'{rel}: {wname} gun shot damage {e.get("damage")!r}, {want!r} expected '
                             f"(XML1's draw of the damage declaration's minimum, SPEC 29)")
            break
    n = 0
    for rel in v.idx.under('data/entities/'):
        if v.entry(rel) is None or not rel.lower().endswith(('.xmlb', '.engb')):
            continue                       # XML2 retail entities keep the retail range
        for e in v.tree(rel).iter():
            if not isinstance(e.tag, str):
                continue
            for k, val in e.attrib.items():
                if k.lower() in NV.SINGLE_VALUE_ENTITY_ATTRS and len((val or '').split()) == 2:
                    n += 1
                    ck.error(f'{rel}: <{e.tag} {k}="{val}"> must be XML1\'s single minimum, not a range '
                            '(the XML1 entity parser reads one number; SPEC 29)')
    ck.set('entity_single_value_attrs_checked', n)
