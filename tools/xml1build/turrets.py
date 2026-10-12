"""XML1 scan turrets for the XML2 Fix turret controller (SPEC "XML1 scan turrets", number assigned at merge).

XML1's scanturretent becomes a physent (x1schema.CLASS_REMAP) that keeps its scanner attributes; XMen2.exe has no
scanner. XML2 Fix (Game.Xml1Turrets, [Xml1Turrets]) runs the first game's scanner/weapon timing on those physents.
This module gives the DLL each placement's authored values, read from the built zone (the physent and its inst) and
XML1's own weapon list (data/weapons/weapons.eng) and value table (data/values.xml):

    zone|instance|px,py,pz,rx,ry,rz|visrange,minspeed,mintime,resetdelay,visextent,yawextent,pitchextent,turnrate,team|
    kind,recoil,count,spread,speed,accuracy,range,damage_lo,damage_hi|projectileent|entfile

Missing scanner attributes take the original constructor's defaults (default.xbe 0xa8600: visrange 600, minspeed 0,
mintime 0.75, resetdelay 10/3, visextent 30, yaw/pitch extent 45, turnrate 20 degrees/s); the reader 0xa83e0 stores
the one authored resetdelay in both of its fields. filterteam defaults to hero (XML1 team 27 -> PC bit 29).
Weapon damage is XML1's gun draw (weapons.gun_damage_range: one integer in trunc(min*0.7f)..trunc(min*1.3f)).
count/spread default to 1/10 (the projectile packet defaults, default.xbe 0xbb240).

Only the weapon kinds the controller emits are listed (SUPPORTED_KINDS); the others stay inert physents, as before,
and are reported. The file goes to <out>/_build/turrets.json; fix_ini.build_turrets turns it into INI keys.
"""
from __future__ import annotations

import math
import re

from . import common as C
from . import weapons as W

REVISION = 1
KINDS = {'bullet': 0, 'flame': 1, 'projectile': 2, 'beam': 3}       # default.xbe type table 0x44fc44
SUPPORTED_KINDS = ('projectile',)
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


def weapon_fields(w: dict, values):
    """(kind, '<9 numbers>', projectileent, entfile) or (None, reason)"""
    kind = (w.get('type') or 'bullet').strip().lower()
    if kind not in KINDS:
        return None, f'weapon type {kind!r}'
    drawn = W.gun_damage_range(values, w.get('damage')) if w.get('damage') else None
    if not drawn:
        return None, f'damage {w.get("damage")!r} does not resolve'
    lo, hi = drawn.split()
    count = int(_num(w.get('count'), 1)) if kind == 'projectile' else 1
    nums = [KINDS[kind], _num(w.get('recoiltime'), 0.0), max(1, count), _num(w.get('spread'), 10.0),
            _num(w.get('projectilespeed'), 0.0), _num(w.get('accuracy'), 0.0), _num(w.get('range'), 0.0), lo, hi]
    proj = (w.get('projectileent') or '').strip() if kind == 'projectile' else ''
    ents = (w.get('entfile') or '').strip() if kind == 'projectile' else ''
    if kind == 'projectile' and not (_NAME.match(proj) and _NAME.match(ents) and nums[4] > 0):
        return None, 'projectile weapon without projectileent/entfile/projectilespeed'
    return (kind, ','.join(_fmt(n) for n in nums), proj, ents), None


def placements(zone: str, root, weapons: dict, values) -> tuple[list, list]:
    """([(line, detail)], [skipped reason]) for one built zone (its .engb root)"""
    defs = {}
    for el in root.iter('entity'):
        if el.get('name') and el.get('turretweapon') and (el.get('classname') or '').lower() == 'physent':
            defs[el.get('name')] = el
    lines, skipped = [], []
    if not defs:
        return lines, skipped
    for group in root.iter('entinst'):
        d = defs.get(group.get('type'))
        if d is None:
            continue
        for inst in group:
            name = inst.get('name') or ''
            where = f'{zone}:{name}'
            pos = [_num(v, None) for v in (inst.get('pos') or '').split()]
            orient = [_num(v, None) for v in (inst.get('orient') or '0 0 0').split()]
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
            kind, gun, proj, ents = fields
            if kind not in SUPPORTED_KINDS:
                skipped.append(f'{where}: {kind} weapon {d.get("turretweapon")} not emitted by the controller yet')
                continue
            team = team_bit(d.get('filterteam'))
            if team is None:
                skipped.append(f'{where}: filterteam {d.get("filterteam")!r}')
                continue
            scan = [_num(d.get(k), SCAN_DEFAULTS[k]) for k in ('visrange', 'minspeed', 'mintime', 'resetdelay',
                                                               'visextent', 'yawextent', 'pitchextent', 'turnrate')]
            line = '|'.join([zone, name, ','.join(_fmt(v) for v in pos + orient),
                             ','.join(_fmt(v) for v in scan) + f',{team}', gun, proj, ents])
            lines.append((line, {'zone': zone, 'instance': name, 'definition': d.get('name'),
                                 'weapon': d.get('turretweapon'), 'kind': kind}))
    return lines, skipped


def build(ctx, zones) -> dict:
    """the contract for <out>/_build/turrets.json; zones: the converted XML1 zones ('haarp/ext/haarp_ext02')"""
    try:
        wroot = ctx.read_x1_xml('data/weapons/weapons.eng')
    except KeyError:
        wroot = None
    weapons, values = weapon_list(wroot), ctx.x1_values()
    lines, details, skipped = [], [], []
    for zone in sorted(zones):
        rel = f'Maps/{zone}.engb'
        if not _ZONE.match(zone) or not ctx.out_exists(rel):
            continue
        got, miss = placements(zone, ctx.read_out_xmlb(rel), weapons, values)
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
        if len(f) != 7 or ';' in line or not _ZONE.match(f[0]) or not _NAME.match(f[1]):
            problems.append(f'turrets contract: malformed placement {line!r}')
            continue
        if (f[0], f[1], f[2]) in seen:
            problems.append(f'turrets contract: duplicate placement {f[0]}:{f[1]}')
        seen.add((f[0], f[1], f[2]))
        if len(f[2].split(',')) != 6 or len(f[3].split(',')) != 9 or len(f[4].split(',')) != 9:
            problems.append(f'turrets contract: wrong field counts in {f[0]}:{f[1]}')
    return problems
