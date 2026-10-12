"""XML1 scan turrets for the XML2 Fix turret controller (SPEC "XML1 scan turrets", number assigned at merge).

XML1's scanturretent becomes a physent (x1schema.CLASS_REMAP) that keeps its scanner attributes; XMen2.exe has no
scanner. XML2 Fix (Game.Xml1Turrets, [Xml1Turrets]) runs the first game's scanner/weapon timing on those physents.
This module gives the DLL each placement's authored values, read from the built zone (the physent and its inst) and
XML1's own weapon list (data/weapons/weapons.eng) and value table (data/values.xml):

    zone|instance|px,py,pz,rx,ry,rz,mx,my,mz|visrange,minspeed,mintime,resetdelay,visextent,yawextent,pitchextent,turnrate,team|
    kind,recoil,count,spread,speed,accuracy,range,damage_lo,damage_hi,tracetime,radius,damagetype,damagemods|
    projectileent|entfile|muzzlefx,muzzleaccfx,impactfx|firesound,rotatesound

Missing scanner attributes take the original constructor's defaults (default.xbe 0xa8600: visrange 600, minspeed 0,
mintime 0.75, resetdelay 10/3, visextent 30, yaw/pitch extent 45, turnrate 20 degrees/s); the reader 0xa83e0 stores
the one authored resetdelay in both of its fields. filterteam defaults to hero (XML1 team 27 -> PC bit 29).
Weapon damage is XML1's gun draw (weapons.gun_damage_range: one integer in trunc(min*0.7f)..trunc(min*1.3f)).
count/spread default to 1/10 (the projectile packet defaults, default.xbe 0xbb240). tracetime defaults to 0 (the
prototype constructor, default.xbe 0xb9c15). damagetype/damagemods are the PC exe's bit values of the weapon's own names
(XML1 keeps damage types as an enum, 0 = dmg_physical, and damagemod bits that match the PC ones by name); a name the
PC exe does not know is reported and left out. The effects are the weapon's effect paths (relative to effects/), empty
when the weapon names none. The sounds are the weapon's firesound and the turret definition's rotatesound (sound
names as the zone's sound bank keys them; empty when absent).

m is the muzzle: the translation of the turret model's `Gun1` node (default.xbe 0xb9e40 fires from the weapon's
`Gun<emitter+1>` bolt; a turret's single weapon is emitter 0), read from the built model; 0,0,0 (the turret's own
position, as the original without that bolt) when the model has none.

Only definitions that are scanturretent in the XML1 zone (maps/<zone>.eng) are turrets; XML1's damaged deathspawn
models also carry a turretweapon but are plain physents and are never listed.

A turret that a zone script spawns (XML1's Hive tanks: spawn("tank1", "tank_turret_sp01", "turret1", ...) in the zone's
own script folder) has no authored spot: it is listed as '*<name>' with a zero position and rest, and the DLL binds it
by name anywhere in the zone, taking its orientation when bound as the rest basis.

Only the weapon kinds the controller emits are listed (SUPPORTED_KINDS: projectile, bullet, flame); beam weapons
(no turret uses one) stay inert physents and are reported. The file goes to <out>/_build/turrets.json; fix_ini.build_turrets turns it into INI keys.
"""
from __future__ import annotations

import math
import re

from . import common as C
from . import weapons as W

REVISION = 2
KINDS = {'bullet': 0, 'flame': 1, 'projectile': 2, 'beam': 3}       # default.xbe type table 0x44fc44
SUPPORTED_KINDS = ('projectile', 'bullet', 'flame')
# PC damage-type bits by name (XMen2.exe table 0x6d61e0); XML1's own values are an enum (default.xbe 0x44c498)
PC_DAMAGE_TYPES = {'dmg_teleport': 0x8, 'dmg_physical': 0x80, 'dmg_telekinesis': 0x100, 'dmg_mental': 0x800,
                   'dmg_magnetic': 0x1000, 'dmg_energy': 0x8000, 'dmg_fire': 0x10000, 'dmg_electricity': 0x20000,
                   'dmg_cold': 0x40000, 'dmg_wind': 0x80000, 'dmg_radiation': 0x8000000, 'dmg_direct': 0x10000000,
                   'dmg_special': 0x20000000}
# PC damagemod bits by name (XMen2.exe table 0x6d6258..); XML1's (default.xbe 0x44c508..) use the same bit for a name
PC_DAMAGE_MODS = {'dmgmod_none': 0, 'dmgmod_no_damage': 0x1, 'dmgmod_no_actors': 0x2, 'dmgmod_drain': 0x4,
                  'dmgmod_auto_knockback': 0x8, 'dmgmod_popup': 0x10, 'dmgmod_trip': 0x20, 'dmgmod_stun': 0x40,
                  'dmgmod_immobilize': 0x80, 'dmgmod_extinguish': 0x100, 'dmgmod_ground_only': 0x400,
                  'dmgmod_critical': 0x800, 'dmgmod_forcepain': 0x1000, 'dmgmod_energize': 0x2000,
                  'dmgmod_weld': 0x4000, 'dmgmod_pierce': 0x8000, 'dmgmod_teleport': 0x10000,
                  'dmgmod_ground': 0x20000, 'dmgmod_bounce': 0x40000, 'dmgmod_no_pain': 0x80000,
                  'dmgmod_ignore_dist': 0x100000, 'dmgmod_kill': 0x200000, 'dmgmod_no_text': 0x400000,
                  'dmgmod_environment': 0x800000, 'dmgmod_force_fx': 0x2000000, 'dmgmod_ignore_def': 0x4000000,
                  'dmgmod_no_atk_roll': 0x8000000}
_EFFECT = re.compile(r'^[A-Za-z0-9_/]{1,63}$')
_SPAWN = re.compile(r'\bspawn\s*\(\s*"[^"]*"\s*,\s*"([A-Za-z0-9_]+)"\s*,\s*"([A-Za-z0-9_]+)"')
SCAN_DEFAULTS = {'visrange': 600.0, 'minspeed': 0.0, 'mintime': 0.75, 'resetdelay': 10.0, 'visextent': 30.0,
                 'yawextent': 45.0, 'pitchextent': 45.0, 'turnrate': 20.0}
X1_TEAMS = {'none': 26, 'hero': 27, 'enemy': 28, 'altenemy': 29}     # XML1 team bits; PC = XML1 + 2 (mold_query)
_NAME = re.compile(r'^[A-Za-z0-9_]{1,31}$')
_ZONE = re.compile(r'^[A-Za-z0-9_/]{1,63}$')


def _num(text, default):
    try:
        v = float(str(text).strip())
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _fmt(v) -> str:
    """shortest exact-enough decimal (binary32 values from the map round-trip through %.9g)"""
    s = '%.9g' % float(v)
    return '0' if s in ('-0', '0') else s


def team_bit(filterteam) -> int | None:
    """the PC team bit the scanner filters on (XML1 'hero' 27 -> 29); None for an unknown team."""
    t = (filterteam or 'hero').strip().lower()
    return X1_TEAMS[t] + 2 if t in X1_TEAMS else None


def weapon_list(root) -> dict:
    """lower weapon name -> lower-cased attribute dict, from XML1's data/weapons/weapons.eng"""
    out = {}
    if root is None:
        return out
    for w in root.iter():
        if w.tag.lower() == 'weapon' and w.get('name'):
            out[w.get('name').strip().lower()] = {k.lower(): v for k, v in w.attrib.items()}
    return out


def damage_bits(w: dict):
    """(damagetype bits, damagemod bits, [unknown names]) on the PC exe for an XML1 weapon"""
    unknown = []
    t = (w.get('damagetype') or 'dmg_physical').strip().lower()
    dtype = PC_DAMAGE_TYPES.get(t)
    if dtype is None:
        unknown.append(t)
        dtype = PC_DAMAGE_TYPES['dmg_physical']
    mods = 0
    for name in (w.get('damagemod') or '').lower().split():
        if name in PC_DAMAGE_MODS:
            mods |= PC_DAMAGE_MODS[name]
        else:
            unknown.append(name)
    return dtype, mods, unknown


def weapon_effects(w: dict) -> str:
    """'muzzlefx,muzzleaccfx,impactfx' (effect paths under effects/, empty when absent or unusable)"""
    out = []
    for key in ('muzzlefx', 'muzzleaccfx', 'impactfx'):
        v = (w.get(key) or '').strip().replace('\\', '/')
        out.append(v if _EFFECT.match(v) else '')
    return ','.join(out)


def sound_name(v) -> str:
    """a sound name as the scripts and banks use it ('zone_shared/objects/turretloop'), '' when unusable"""
    v = (v or '').strip().replace('\\', '/')
    return v if _EFFECT.match(v) else ''


def weapon_fields(w: dict, values):
    """(kind, '<13 numbers>', projectileent, entfile, effects) or (None, reason)"""
    kind = (w.get('type') or 'bullet').strip().lower()
    if kind not in KINDS:
        return None, f'weapon type {kind!r}'
    drawn = W.gun_damage_range(values, w.get('damage')) if w.get('damage') else None
    if not drawn:
        return None, f'damage {w.get("damage")!r} does not resolve'
    lo, hi = drawn.split()
    count = int(_num(w.get('count'), 1)) if kind == 'projectile' else 1
    dtype, mods, unknown = damage_bits(w)
    if unknown:
        return None, f'damage names unknown to the PC exe: {unknown}'
    nums = [KINDS[kind], _num(w.get('recoiltime'), 0.0), max(1, count), _num(w.get('spread'), 10.0),
            _num(w.get('projectilespeed'), 0.0), _num(w.get('accuracy'), 0.0), _num(w.get('range'), 0.0), lo, hi,
            _num(w.get('tracetime'), 0.0), _num(w.get('radius'), 0.0)]
    proj = (w.get('projectileent') or '').strip() if kind == 'projectile' else ''
    ents = (w.get('entfile') or '').strip() if kind == 'projectile' else ''
    if kind == 'projectile' and not (_NAME.match(proj) and _NAME.match(ents) and nums[4] > 0):
        return None, 'projectile weapon without projectileent/entfile/projectilespeed'
    if kind in ('bullet', 'flame') and not nums[6] > 0:
        return None, f'{kind} weapon without a range'
    gun = ','.join(_fmt(n) for n in nums) + f',{dtype},{mods}'
    return (kind, gun, proj, ents, weapon_effects(w)), None


def muzzle_offset(data) -> tuple:
    """the model-space translation of an IGB model's Gun1 node (a child of the scene root), or (0, 0, 0)"""
    from . import igb_file as I
    try:
        f = I.IgbFile(data)
    except Exception:
        return (0.0, 0.0, 0.0)
    objs = f.objects if isinstance(f.objects, dict) else {o.ref: o for o in f.objects}
    for o in objs.values():
        if o.name == 'igTransform' and o.get(2) == 'Gun1':
            m = o.get(8)
            if isinstance(m, list) and len(m) == 16 and all(math.isfinite(v) for v in m[12:15]):
                return (m[12], m[13], m[14])
    return (0.0, 0.0, 0.0)


def script_spawns(texts) -> list:
    """[(entity type, spawned name)] of the spawn("parent", "type", "name", ...) calls in a zone's scripts"""
    out = []
    for text in texts:
        for m in _SPAWN.finditer(text or ''):
            if (m.group(1), m.group(2)) not in out:
                out.append((m.group(1), m.group(2)))
    return out


def scan_turret_definitions(x1_root) -> set:
    """names of the XML1 zone's scanturretent definitions (its maps/<zone>.eng). Only those are turrets: XML1's
    damaged deathspawn models (tank_turret_sp_d, tank_turret_haarp_sp_d) are plain physents that also carry a
    turretweapon, and become indistinguishable from a remapped turret once converted."""
    if x1_root is None:
        return set()
    return {el.get('name') for el in x1_root.iter('entity')
            if el.get('name') and (el.get('classname') or '').strip().lower() == 'scanturretent'}


def placements(zone: str, root, weapons: dict, values, spawns=(), muzzle=None, turret_defs=None) -> tuple[list, list]:
    """([(line, detail)], [skipped reason]) for one built zone (its .engb root); spawns: script_spawns() of the zone's
    script folder; muzzle(model path) -> the model's Gun1 offset (muzzle_offset), (0, 0, 0) when not given;
    turret_defs: scan_turret_definitions() of the XML1 zone (None: every physent with a turretweapon)"""
    defs = {}
    for el in root.iter('entity'):
        if el.get('name') and el.get('turretweapon') and (el.get('classname') or '').lower() == 'physent':
            if turret_defs is None or el.get('name') in turret_defs:
                defs[el.get('name')] = el
    lines, skipped = [], []
    if not defs:
        return lines, skipped
    found = []
    for group in root.iter('entinst'):
        d = defs.get(group.get('type'))
        if d is None:
            continue
        for inst in group:
            found.append((d, inst.get('name') or '', inst.get('pos') or '', inst.get('orient') or '0 0 0', False))
    placed = {name for _, name, *_ in found}
    for etype, name in spawns:
        if etype in defs and name not in placed:
            found.append((defs[etype], name, '0 0 0', '0 0 0', True))
    for d, name, pos_text, orient_text, spawned in found:
        if True:
            where = f'{zone}:{name}'
            pos = [_num(v, None) for v in pos_text.split()]
            orient = [_num(v, None) for v in orient_text.split()]
            if not _NAME.match(name) or len(pos) != 3 or None in pos or len(orient) != 3 or None in orient:
                skipped.append(f'{where}: placement without a usable name/pos/orient')
                continue
            w = weapons.get((d.get('turretweapon') or '').strip().lower())
            if w is None:
                skipped.append(f'{where}: turretweapon {d.get("turretweapon")!r} not in XML1 weapons')
                continue
            fields, why = weapon_fields(w, values)
            if fields is None:
                skipped.append(f'{where}: {why}')
                continue
            kind, gun, proj, ents, fx = fields
            if kind not in SUPPORTED_KINDS:
                skipped.append(f'{where}: {kind} weapon {d.get("turretweapon")} not emitted by the controller yet')
                continue
            team = team_bit(d.get('filterteam'))
            if team is None:
                skipped.append(f'{where}: filterteam {d.get("filterteam")!r}')
                continue
            scan = [_num(d.get(k), SCAN_DEFAULTS[k]) for k in ('visrange', 'minspeed', 'mintime', 'resetdelay',
                                                               'visextent', 'yawextent', 'pitchextent', 'turnrate')]
            mz = list(muzzle(d.get('model') or '') if muzzle else (0.0, 0.0, 0.0))
            sounds = sound_name(w.get('firesound')) + ',' + sound_name(d.get('rotatesound'))
            line = '|'.join([zone, ('*' if spawned else '') + name, ','.join(_fmt(v) for v in pos + orient + mz),
                             ','.join(_fmt(v) for v in scan) + f',{team}', gun, proj, ents, fx, sounds])
            lines.append((line, {'zone': zone, 'instance': name, 'definition': d.get('name'),
                                 'weapon': d.get('turretweapon'), 'kind': kind, 'spawned': spawned}))
    return lines, skipped


def build(ctx, zones) -> dict:
    """the contract for <out>/_build/turrets.json; zones: the converted XML1 zones ('haarp/ext/haarp_ext02')"""
    try:
        wroot = ctx.read_x1_xml('data/weapons/weapons.eng')
    except KeyError:
        wroot = None
    weapons, values = weapon_list(wroot), ctx.x1_values()
    muzzles = {}

    def model_muzzle(model):
        if model not in muzzles:
            path = ctx.out_path(f'Models/{model}.IGB') if _ZONE.match(model or '') else None
            if path is not None and not path.is_file():
                path = path.with_suffix('.igb')
            muzzles[model] = muzzle_offset(path.read_bytes()) if path is not None and path.is_file() else (0.0, 0.0, 0.0)
        return muzzles[model]
    lines, details, skipped = [], [], []
    for zone in sorted(zones):
        rel = f'Maps/{zone}.engb'
        if not _ZONE.match(zone) or not ctx.out_exists(rel):
            continue
        folder = ctx.out_path(f'Scripts/{zone.rsplit("/", 1)[0]}') if '/' in zone else None
        texts = [f.read_text(encoding='utf-8', errors='replace') for f in sorted(folder.glob('*.py'))] \
            if folder is not None and folder.is_dir() else []
        try:
            x1_root = ctx.read_x1_xml(f'maps/{zone}.eng')
        except KeyError:
            x1_root = None
        got, miss = placements(zone, ctx.read_out_xmlb(rel), weapons, values, script_spawns(texts), model_muzzle,
                               scan_turret_definitions(x1_root))
        for line, detail in got:
            lines.append(line)
            details.append(detail)
        skipped.extend(miss)
    return {'revision': REVISION, 'placements': lines, 'details': details, 'skipped': skipped}


def validate_contract(data) -> list:
    """problems of a turrets.json contract (V-TBD): placements well formed, unique, within the DLL's 32"""
    problems = []
    if not isinstance(data, dict) or data.get('revision') != REVISION:
        return ['turrets contract: missing or other revision']
    lines = data.get('placements') or []
    if len(lines) > 32:
        problems.append(f'turrets contract: {len(lines)} placements (the controller reads 32)')
    seen = set()
    for line in lines:
        f = str(line).split('|')
        if len(f) != 9 or ';' in line or not _ZONE.match(f[0]) or not _NAME.match(f[1].removeprefix('*')):
            problems.append(f'turrets contract: malformed placement {line!r}')
            continue
        if (f[0], f[1], f[2]) in seen:
            problems.append(f'turrets contract: duplicate placement {f[0]}:{f[1]}')
        seen.add((f[0], f[1], f[2]))
        if (len(f[2].split(',')) != 9 or len(f[3].split(',')) != 9 or len(f[4].split(',')) != 13
                or len(f[7].split(',')) != 3 or len(f[8].split(',')) != 2):
            problems.append(f'turrets contract: wrong field counts in {f[0]}:{f[1]}')
    return problems
