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


def bind_style_package(root, base: str, variant: str):
    """A weapon variant's own package must load that variant, not its source style.

    The source bundle also carries effects/entities and sometimes other styles. Replace only
    its self-reference, preserving dependency entries and their order. Missing self-references
    (including asset-only bundles) get an explicit XML entry.
    """
    old, new = f'data/powerstyles/{base}', f'data/powerstyles/{variant}'
    for entry in root:
        if entry.tag.lower() in ('xml', 'xml_resident', 'fightstyle') and \
                (entry.get('filename') or '').replace('\\', '/').lower() == old:
            entry.set('filename', new)
    if not any(entry.tag.lower() in ('xml', 'xml_resident', 'fightstyle') and
               (entry.get('filename') or '').replace('\\', '/').lower() == new for entry in root):
        ET.SubElement(root, 'xml', {'filename': new})


def _lower(el) -> dict:
    return {k.lower(): v for k, v in el.attrib.items()}


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


def rewrite_weapon_events(root, weapons: dict, where: str = '') -> collections.Counter:
    """XML1 styles can also NAME a weapon on an event of their own: ps_mystique's `left_gun` / `right_gun` are
    `<event inherit="weapon_fire" weapon="wp_myst_pistol" [boltselect=...]>`, fired by plain triggers with those
    names. XMen2.exe builds `weapon_fire` as a sound event (see the module doc), so every such shot did nothing.
    Each such event (at the style root or inside a FightMove) becomes a `beam` event with the weapon's data,
    exactly as `shot_triggers` builds a bullet / beam shot (beambolt = the event's `boltselect`, else the weapon's
    `actorbolt`). The triggers keep their names, so no move gains a trigger for the shot itself; the weapon's
    muzzle flash + fire sound (one `effect_sound`) go on the first shots of each move while it stays within
    MAX_TRIGGERS. Projectile / flame weapons named this way are reported, not rewritten (none on the disc).
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


def apply(root, w: dict, where: str = '') -> collections.Counter:
    """replace every weapon_fire trigger of every FightMove with the weapon's triggers; for a continuous (flame)
    weapon also give the constant beam its firing interval. Returns counts; `root` is changed in place."""
    rep = collections.Counter()
    kind = (w.get('type') or '').lower()
    if kind not in WEAPON_TYPES:
        return rep
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
    return rep
