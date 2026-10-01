"""xml1build.npc_values - XML1 value codes in the styles characters writes, and the NPC energy pool (SPEC 24).

Value codes. XMen2.exe (PE base 0x400000; research/scripts/xml2_text.asm):
  * A numeric style attribute (damage, knockback, powerusage, life, level ...) is read through the talent-value
    manager's parser 0x4c1580 (vtable 0x68ed18 +0x18; e.g. 0x4de670 attack damage, 0x4e7890 powerup life /
    damage, 0x4dadb0 powerusage) or straight through the value table 0x4c4bb0 -> vt+8 (0x4e8830 damage /
    knockback). '%name' is a talentvalue id; anything else goes to 0x4c4870: leading blanks skipped; a digit, '-'
    or '.' starts a number ("%f %f" when the text holds a blank: min and max, else "%f": both the number); a name
    is _stricmp-compared (0x672562) with the 5 rows of the table 0x6da240 {index, name}: DMG2 DMG3 DMG4 K2 K3,
    whose min / max 0x4c4640 reads from data/values.xmlb at start (no other <value> is kept); any other name
    returns 0.0 (0x680030) and max 0. So an XML1 code (L3, M5, K7, P5, A6, BST6 ...) left in a style reads as 0:
    no base damage, no knockback, no energy cost. XML2's retail styles carry no code (numbers, "min max" ranges
    and %talentvalues only; npc_values_selftest T2).
  * XML1 (default.xbe, image base 0x10000; research/scripts/xml1_text.asm): the value table singleton 0xb8550
    (vtable 0x3d4380) loads data/values.xml at start (0xb8100: every <value name min max>, up to 120 names); its
    resolver vt+8 = 0xb7e60 returns atof of a number, or a named code's min (and its max through the out
    pointer), 0.0 for an unknown name. Every style attribute reader calls it while the style is parsed (0xcf6b0
    attack "Damage" with the max, 0xd7bc0 damage / knockback, 0xcdc10 powerusage, 0xd40b0 damage / damagelevel /
    heaviness) and stores the result: the number never depends on the actor, its level or the difficulty (level
    scaling is the stats' job, SPEC 11.8). A reader that wants one number gets the min in both exes (XML1: no max
    pointer; XMen2.exe: the first number of "min max"), so a code written as XML1's "min max" (or "min") is XML1's
    value under every reader. The L/M/H/K rows of both games' values tables are the same numbers; XML2's P codes
    are XML1's / 10. XML2's own ports of XML1 NPCs resolved their codes the same way (retail ps_sabretooth:
    damage L3 -> "15 18", knockback K5 -> "305"; ps_pyro flame_dmg L3 -> "15 18"; T3).

The NPC energy pool (both exes have the same design):
  * Every actor outside the player heroes spends a powerusage trigger's cost (XML1 0xcde90 -> 0x3f410; XMen2.exe
    0x4daa30 -> 0x4318d0; the only exemption is a hero actor, flag bit 0 of +0x334 / +0x3d8, whose player slot
    the player manager (0xf9a00 vt+0x1b0 / 0x5252e0 vt+0x1bc) reports free). FightMove canAfford (XML1 0xe1a20,
    XMen2.exe 0x4f5fb0, FightMove vtable +0xc) refuses a move whose summed trigger costs exceed the actor's
    energy, and XML1's AI picks a power only while its energy is at least half its maximum (0xee37a: max /
    energy > 2.0 -> no power). XML1 NPCs therefore had a pool, spent it and waited for it.
  * Maximum: XML1 0xafbd0 = 30 + 4 level + 7 mind (0x44f200 / 0x44f204 / 0x44f208), then the maxenergy affecter
    (add, then scale); XMen2.exe 0x4b8c20 = 30 + 4 level + 2 mind (0x6d9774 / 0x6d9778 / 0x6d977c) at the default
    difficulty (game vt+0x268 == 1; below it the enemy / neutral base is halved, above it a level-50 formula),
    then the maxenergy affecter (add, then scale).
  * Regeneration per second: XML1 0x3a950 = (15 + energy_regen add) x scale x (1 + 0.01 mind) (0x3c836c,
    0xaf860 / 0x3c93c0) outside the hero team (the hero team regenerates max / 60 instead of 15); XMen2.exe
    0x42cc60 = (15 + add) x scale for team 0x1e "enemy" (0x683f2c; teams 0x45fbd0: hero 0x1d, altenemy 0x1f,
    none 0x1c regenerate max / 60), no mind factor.
  The port keeps XML1's level and mind in npcstat (SPEC 11.8), so every stats entry characters converts gets the
  shared talent ENERGY_TALENT at rank = its mind: maxenergy +5 mind and energy_regen x (1 + 0.01 mind) - XML1's
  pool and regeneration through XMen2.exe's formulas - and the styles' powerusage codes resolve to XML1's P
  numbers. Differences left (SPEC 24.3): XMen2.exe's other difficulties, a team-"none" NPC's max / 60 base, the
  AI's own energy thresholds.

Pure except verify_exe / verify_xbe (read-only).
"""
from __future__ import annotations

import collections
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

# ------------------------------------------------------------------------------------------ value codes
VALUE_RESOLVER = 0x4c4870            # XMen2.exe: number / 5 names / 0.0
VALUE_NAME_TABLE = 0x6da240          # {index, name} x 5, loop bound 0x4c48d6 cmp edi,5 / 0x4c47b1 cmp esi,0x6da268
VALUE_LOADER = 0x4c4640              # reads data/values.xmlb (0x68f2fc) at start
VALUE_ZERO = 0x680030                # 0.0f returned for any other name
# the codes XMen2.exe itself resolves (from data/values.xmlb): {name: (index, string address)}
EXE_VALUE_NAMES = {'DMG2': (0, 0x68f2c4), 'DMG3': (1, 0x68f2bc), 'DMG4': (2, 0x68f2b4), 'K2': (3, 0x68f2b0),
                   'K3': (4, 0x68f2ac)}
# any value-code shaped attribute value: XML1's L/M/H/K/P/A/BST/XTL codes (+/- variants), XML1's XLT typos, XML2's
# DMGn. XML2 retail styles hold none of these (T2), so the shape is safe to treat as a code.
CODE_RE = re.compile(r'^(?:[LMHKP]\d+[+-]?|BST\d+|A\d+|XTL\d+|XLT\d+|DMG\d+)$')
# attributes reported by name (the rest count as 'other')
REPORTED_ATTRS = ('damage', 'knockback', 'powerusage')


def is_code(v):
    return isinstance(v, str) and bool(CODE_RE.match(v.strip()))


def exe_reads_as_zero(v):
    """a value-code shaped attribute value XMen2.exe's 0x4c4870 does not resolve (it reads 0.0)."""
    return is_code(v) and v.strip().upper() not in EXE_VALUE_NAMES


def _skip_attrs():
    from . import heroes as H                   # noqa: WPS433 - heroes imports this module too
    return H._NAME_LIKE_ATTRS                   # attributes that hold names, never numbers


def resolve_style(root, values, where=''):
    """every XML1 value code in the attributes of one style tree -> XML1's number(s), in place and idempotent:
    'min max' for a code with a range (L/M/H), 'min' otherwise (values: heroes.Values of XML1's data/values.xml,
    whose resolve() is exactly XML1's 0xb7e60 row). XMen2.exe's own five codes are resolved too (the same numbers:
    XML1's K2 / K3 rows equal XML2's; XML1 has no DMG code). Returns (Counter {attr or 'other': n, 'code:<C>': n},
    [problems]) - an unknown code is a problem and stays."""
    c = collections.Counter()
    problems = []
    if root is None:
        return c, problems
    skip = _skip_attrs()
    for e in root.iter():
        if not isinstance(e.tag, str):
            continue
        for k, v in list(e.attrib.items()):
            kl = k.lower()
            if kl in skip or not is_code(v):
                continue
            code = v.strip()
            try:
                new = values.resolve(code)
            except KeyError:
                new = None
            if new is None or new == code or is_code(new):
                problems.append(f'{where}<{e.tag} {k}="{v}">: not a code of XML1\'s data/values.xml')
                continue
            e.set(k, new)
            c[kl if kl in REPORTED_ATTRS else 'other'] += 1
            c[f'code:{code}'] += 1
    return c, problems


def resolve_entity_codes(ctx, root, rel):
    """Use the same value-code conversion for every importer of an XML1 entity file.

    Zones may take ownership of a file previously written by characters. Both must resolve the
    codes, or that later import silently restores values XMen2.exe interprets as zero.
    """
    n = str(rel).replace('\\', '/').lower()
    if not n.startswith('data/entities/'):
        return None
    from .heroes import Values                    # local import: heroes imports npc_values
    result = resolve_style(root, Values(ctx.read_x1_xml('data/values.xml')), f'{n}:')
    for problem in result[1]:
        ctx.error(f'Entity value code: {problem}')
    return result


def code_findings(root):
    """[(move, element tag, attribute, value)] of every attribute value XMen2.exe reads as 0 (exe_reads_as_zero)
    in one style tree; and a Counter of the codes XMen2.exe resolves itself. For validators."""
    out, exe_codes = [], collections.Counter()
    if root is None:
        return out, exe_codes
    skip = _skip_attrs()
    roots = list(root) if root.tag == 'xmlb_multiple_roots' else [root]
    for top in roots:
        # Entity files can be a container, a single entity, or XMLB multiple roots.
        elements = [top] if isinstance(top.tag, str) and top.tag.lower() == 'entity' else list(top)
        for el in elements:
            where = (el.get('name') or el.get('Name') or '<style>') if isinstance(el.tag, str) else '<style>'
            for e in el.iter():
                if not isinstance(e.tag, str):
                    continue
                for k, v in e.attrib.items():
                    if k.lower() in skip or not is_code(v):
                        continue
                    if exe_reads_as_zero(v):
                        out.append((where, e.tag, k, v))
                    else:
                        exe_codes[v.strip().upper()] += 1
    return out, exe_codes


# ------------------------------------------------------------------------------------------ the NPC energy pool
ENERGY_TALENT = 'x1_npc_energy'
TV_MAX = 'x1npc_ep_max'              # maxenergy add at rank r (talentvalue names <= 19 chars, 0x4c188c)
TV_REGEN = 'x1npc_ep_regen'          # energy_regen scale at rank r
RANK_MAX = 99                        # XML2 retail NPC talents reach rank 99 (monst_dmg_high)
X1_MAXENERGY = (30, 4, 7)            # default.xbe 0xafbd0: base 0x44f200, x level 0x44f204, x mind 0x44f208
X2_MAXENERGY = (30, 4, 2)            # XMen2.exe 0x4b8c20: 0x6d9774, 0x6d9778, 0x6d977c (difficulty 1)
X1_REGEN_MIND = 0.01                 # default.xbe 0xaf860: regen scale x (1 + 0.01 mind), 0x3c93c0
REGEN_BASE = 15.0                    # default.xbe 0x3c836c (non-hero team) = XMen2.exe 0x683f2c (enemy team)
# (address, float) facts verify_exe / verify_xbe check byte for byte
X2_FLOATS = {0x6d9774: 30.0, 0x6d9778: 4.0, 0x6d977c: 2.0, 0x683f2c: 15.0, 0x684068: 1 / 60, VALUE_ZERO: 0.0}
X1_FLOATS = {0x44f200: 30.0, 0x44f204: 4.0, 0x44f208: 7.0, 0x3c93c0: 0.01, 0x3c836c: 15.0, 0x3ca950: 1 / 60,
             0x3c9404: 2.0, 0x3c6de4: 0.0}


def maxenergy_add(rank):
    """the maxenergy add that turns XMen2.exe's 2 x mind into XML1's 7 x mind."""
    return (X1_MAXENERGY[2] - X2_MAXENERGY[2]) * rank


def regen_scale(rank):
    return 1 + X1_REGEN_MIND * rank


def _num(x):
    return f'{x:g}'


def x1_max_energy(level, mind):
    return X1_MAXENERGY[0] + X1_MAXENERGY[1] * level + X1_MAXENERGY[2] * mind


def x2_max_energy(level, mind, rank=None):
    """XMen2.exe's maximum (difficulty 1) with ENERGY_TALENT at `rank` (None: without it)."""
    base = X2_MAXENERGY[0] + X2_MAXENERGY[1] * level + X2_MAXENERGY[2] * mind
    return base + (maxenergy_add(rank) if rank else 0)


def x1_regen(mind):
    return REGEN_BASE * (1 + X1_REGEN_MIND * mind)


def x2_regen(rank=None):
    return REGEN_BASE * (regen_scale(rank) if rank else 1)


def _int_attr(el, name):
    k = next((k for k in el.attrib if k.lower() == name), None)
    try:
        return int(float(el.get(k))) if k else None
    except (TypeError, ValueError):
        return None


def energy_rank(stats_el):
    """the ENERGY_TALENT rank a converted stats entry needs: its (XML1) mind, capped at RANK_MAX; None for 0 / none."""
    m = _int_attr(stats_el, 'mind')
    if not m or m <= 0:
        return None
    return min(m, RANK_MAX)


def attach_energy_talent(stats_el):
    """give one converted stats entry <talent name=ENERGY_TALENT level=rank/> (idempotent: an existing reference is
    updated). Returns the rank or None (mind 0 / absent: XML1's and XML2's formulas already agree)."""
    rank = energy_rank(stats_el)
    old = [t for t in stats_el if isinstance(t.tag, str) and t.tag.lower() == 'talent'
           and (t.get('name') or '').lower() == ENERGY_TALENT]
    for t in old[1:]:
        stats_el.remove(t)
    if rank is None:
        if old:
            stats_el.remove(old[0])
        return None
    if old:
        old[0].set('level', str(rank))
    else:
        stats_el.append(ET.Element('talent', {'level': str(rank), 'name': ENERGY_TALENT}))
    return rank


def energy_talent(max_rank):
    """the shared talent definition: one <level count=max_rank> whose permanent powerup adds maxenergy and scales
    energy_regen by %talentvalues listed for every rank (XML2's own form: mutantmaster's energy_regen scale, the
    NPC talent might's %talentvalue powerup; no interpolation relied on)."""
    n = max(1, min(int(max_rank), RANK_MAX))
    t = ET.Element('talent', {'name': ENERGY_TALENT})
    tvs = ET.SubElement(t, 'talentvalues')
    for r in range(1, n + 1):
        ET.SubElement(tvs, 'talentvalue', {'level': str(r), 'name': TV_MAX, 'value': _num(maxenergy_add(r))})
    for r in range(1, n + 1):
        ET.SubElement(tvs, 'talentvalue', {'level': str(r), 'name': TV_REGEN, 'value': _num(regen_scale(r))})
    lv = ET.SubElement(t, 'level', {'count': str(n)})
    pu = ET.SubElement(lv, 'powerup', {'life': '-1'})
    ET.SubElement(pu, 'affecter', {'attribute': 'maxenergy', 'level': f'%{TV_MAX}'})
    ET.SubElement(pu, 'affecter', {'affect_type': 'scale', 'attribute': 'energy_regen', 'level': f'%{TV_REGEN}'})
    return t


def talent_problems(t, need_rank):
    """what is wrong with an ENERGY_TALENT definition in <out> for ranks 1..need_rank ([] when right)."""
    if t is None:
        return [f'shared talent {ENERGY_TALENT} missing']
    bad = []
    vals = collections.defaultdict(dict)
    for tv in t.iter('talentvalue'):
        try:
            vals[(tv.get('name') or '').lower()][int(tv.get('level'))] = float(tv.get('value'))
        except (TypeError, ValueError):
            bad.append(f'{ENERGY_TALENT}: unreadable talentvalue {tv.attrib}')
    for name, fn in ((TV_MAX, maxenergy_add), (TV_REGEN, regen_scale)):
        for r in range(1, need_rank + 1):
            got = vals[name].get(r)
            if got is None or abs(got - fn(r)) > 1e-6:
                bad.append(f'{ENERGY_TALENT}: {name} at rank {r} is {got}, {fn(r):g} expected')
                break
    levels = [lv for lv in t if isinstance(lv.tag, str) and lv.tag.lower() == 'level']
    count = sum(int(lv.get('count') or 1) for lv in levels)
    if count < need_rank:
        bad.append(f'{ENERGY_TALENT}: {count} ranks < {need_rank} (the highest rank a stats entry uses)')
    affs = {((a.get('attribute') or '').lower(), (a.get('affect_type') or '').lower(), a.get('level'))
            for a in t.iter('affecter')}
    for want in (('maxenergy', '', f'%{TV_MAX}'), ('energy_regen', 'scale', f'%{TV_REGEN}')):
        if want not in affs:
            bad.append(f'{ENERGY_TALENT}: no <affecter attribute="{want[0]}" level="{want[2]}"'
                       f'{" affect_type=" + chr(34) + want[1] + chr(34) if want[1] else ""}>')
    if not any(p.get('life') == '-1' for p in t.iter('powerup')):
        bad.append(f'{ENERGY_TALENT}: the powerup is not permanent (life="-1")')
    return bad


# ------------------------------------------------------------------------------- NPC immunity talents (SPEC 30)
# XML1 defines its boss immunities inline on the npcstat entry: <Talent name="blob_special" level="1"><level>
# <activepowerup powerup="def_stun" affect_type="scale" level="0" life="-1"/>...</level></Talent>. XMen2.exe's
# affecter table 0x6ddb18 has every attribute they use (combat_events.AFFECTERS: def_damage 39, def_knockback 40,
# def_stun 41, def_pain 42, def_critical 43, def_pickup 44, def_grab 45, def_reflect_pain 46, def_finisher 47,
# def_mind_control 50, no_iceshell 81, slow_immune 85) and XML2 ships the same idea as a shared talent
# (boss_resistances = <talent><level><powerup life="-1"><affecter affect_type="scale" attribute="def_stun" level="0"/>
# ...). characters emits one shared talent per distinct inline body in that form and rewrites the entries' references
# to it; heroes keeps those talents in its shared_talents prune (is_immunity_talent).
IMMUNITY_AFFECTERS = ('def_damage', 'def_knockback', 'def_stun', 'def_pain', 'def_critical', 'def_pickup',
                      'def_grab', 'def_reflect_pain', 'def_finisher', 'def_mind_control', 'no_iceshell',
                      'slow_immune')
_IMMUNITY_ROW_ATTRS = ('powerup', 'affect_type', 'level', 'life', 'scope_damage')
# a row = (attribute, affect_type, level, scope_damage), all lower-case strings ('' when absent): the affecter's form


def _lower(el):
    return {k.lower(): v for k, v in el.attrib.items()}


def immunity_rows(talent_el):
    """One XML1 inline <Talent> -> (rows, losses) when its body is an immunity body (every activepowerup is a
    permanent IMMUNITY_AFFECTERS affecter, `none` rows aside), else (None, reason). rows keep XML1's order;
    losses name what the XML2 form cannot carry (a `none` row's func_* callbacks, user1 ...)."""
    levels = [lv for lv in talent_el if isinstance(lv.tag, str) and lv.tag.lower() == 'level']
    if len(levels) != 1:
        return None, f'{len(levels)} <level> children (one expected)'
    rows, losses = [], []
    for ap in levels[0]:
        if not isinstance(ap.tag, str) or ap.tag.lower() != 'activepowerup':
            return None, f'<{ap.tag}> child (activepowerup expected)'
        a = _lower(ap)
        pu = (a.get('powerup') or '').lower()
        if pu == 'none':
            losses.append('activepowerup none (' + ' '.join(f'{k}={v}' for k, v in sorted(a.items())
                                                            if k not in ('powerup', 'life')) + ') dropped')
            continue
        if pu not in IMMUNITY_AFFECTERS:
            return None, f'activepowerup {pu} is not an immunity affecter'
        if (a.get('life') or '-1') != '-1':
            return None, f'activepowerup {pu} life={a.get("life")} (permanent expected)'
        extra = sorted(k for k in a if k not in _IMMUNITY_ROW_ATTRS)
        if extra:
            losses.append(f'{pu}: ' + ' '.join(f'{k}={a[k]}' for k in extra) + ' dropped')
        rows.append((pu, (a.get('affect_type') or '').lower(), (a.get('level') or '').lower(),
                     (a.get('scope_damage') or '').lower()))
    if not rows:
        return None, 'no affecter rows'
    return rows, losses


def immunity_key(rows):
    """the body identity: the rows as a multiset."""
    return tuple(sorted(rows))


def immunity_talent(name, rows):
    """the shared talent definition in XML2's boss_resistances form."""
    t = ET.Element('talent', {'name': name})
    pu = ET.SubElement(ET.SubElement(t, 'level'), 'powerup', {'life': '-1'})
    for attr, affect, level, scope in rows:
        a = {}
        if affect:
            a['affect_type'] = affect
        a['attribute'] = attr
        if level != '':
            a['level'] = level
        if scope:
            a['scope_damage'] = scope
        ET.SubElement(pu, 'affecter', a)
    return t


def definition_rows(talent_el):
    """rows of a shared talent definition in <out> when it has the immunity form (one <level>, one permanent
    <powerup>, only IMMUNITY_AFFECTERS affecters, no talentvalues), else None."""
    if talent_el is None or any(isinstance(c.tag, str) and c.tag.lower() == 'talentvalues' for c in talent_el):
        return None
    levels = [lv for lv in talent_el if isinstance(lv.tag, str) and lv.tag.lower() == 'level']
    if len(levels) != 1 or (levels[0].get('count') or '1') != '1':
        return None
    pus = [p for p in levels[0] if isinstance(p.tag, str)]
    if len(pus) != 1 or pus[0].tag.lower() != 'powerup' or pus[0].get('life') != '-1' or pus[0].get('class'):
        return None
    rows = []
    for a in pus[0]:
        if not isinstance(a.tag, str) or a.tag.lower() != 'affecter':
            return None
        d = _lower(a)
        attr = (d.get('attribute') or '').lower()
        if attr not in IMMUNITY_AFFECTERS or set(d) - {'attribute', 'affect_type', 'level', 'scope_damage'}:
            return None
        rows.append((attr, (d.get('affect_type') or '').lower(), (d.get('level') or '').lower(),
                     (d.get('scope_damage') or '').lower()))
    return rows or None


def is_immunity_talent(talent_el):
    return definition_rows(talent_el) is not None


def immunity_plan(npc_root, exclude=()):
    """Census of the inline immunity bodies of an XML1 npcstat tree. Returns
    {'bodies': {key: {'rows', 'names': {xml1 name: entries}, 'entries': [...], 'canonical'}},
     'alias': {key: canonical}, 'skipped': {(entry, name): reason}, 'losses': {(entry, name): [..]}}.
    `exclude`: lower-case talent names XML2 defines itself (dr_stun, sentinel_special): their references stay as
    they are and XML2's definition applies. Canonical name per body: the XML1 name used by the most entries, ties
    alphabetical; a name already taken by another body gets the next candidate (or a _2 suffix)."""
    bodies = {}
    skipped, losses = {}, {}
    ex = {e.lower() for e in exclude}
    stats = npc_root if isinstance(npc_root, (list, tuple)) else npc_root.iter()      # a tree or a stats list
    for st in stats:
        if not isinstance(st.tag, str) or st.tag.lower() != 'stats':
            continue
        sname = st.get('name') or ''
        for t in st:
            if not isinstance(t.tag, str) or t.tag.lower() != 'talent' or len(t) == 0:
                continue
            tn = t.get('name') or ''
            if tn.lower() in ex:
                skipped[(sname, tn)] = 'defined by XML2 shared_talents'
                continue
            rows, info = immunity_rows(t)
            if rows is None:
                skipped[(sname, tn)] = info
                continue
            if info:
                losses[(sname, tn)] = info
            b = bodies.setdefault(immunity_key(rows), {'rows': rows, 'names': {}, 'entries': []})
            b['names'][tn.lower()] = b['names'].get(tn.lower(), 0) + 1
            b['entries'].append(sname)
    taken = set()
    alias = {}
    for key in sorted(bodies, key=lambda k: (-len(bodies[k]['entries']), min(bodies[k]['names']))):
        b = bodies[key]
        cands = sorted(b['names'], key=lambda n: (-b['names'][n], n))
        name = next((c for c in cands if c not in taken), None)
        if name is None:
            name = next(f'{cands[0]}_{i}' for i in range(2, 100) if f'{cands[0]}_{i}' not in taken)
        taken.add(name)
        b['canonical'] = name
        alias[key] = name
    return {'bodies': bodies, 'alias': alias, 'skipped': skipped, 'losses': losses}


# ------------------------------------------------------------------------------------------ exe / xbe facts
def verify_exe(exe_path):
    """the value name table 0x6da240 and the energy constants against XMen2.exe. Returns mismatch strings."""
    from .combat_events import _pe_sections, _read_va       # noqa: WPS433
    data = Path(exe_path).read_bytes()
    base, secs = _pe_sections(data)
    bad = []
    for name, (idx, sva) in EXE_VALUE_NAMES.items():
        row = _read_va(data, base, secs, VALUE_NAME_TABLE + 8 * idx, 8)
        if row != struct.pack('<II', idx, sva):
            bad.append(f'value table row {idx} at 0x{VALUE_NAME_TABLE + 8 * idx:06x} is not ({idx}, 0x{sva:06x})')
            continue
        s = _read_va(data, base, secs, sva, len(name) + 1)
        if s != name.encode() + b'\0':
            bad.append(f'value name {name}: string at 0x{sva:06x} is {s!r}')
    loop = _read_va(data, base, secs, 0x4c48d6, 4)
    if loop != b'\x83\xff\x05\x7c':                         # cmp edi,5 / jl: the resolver reads 5 names only
        bad.append(f'resolver name loop 0x4c48d6 is {loop!r}, not cmp edi,5')
    for va, want in X2_FLOATS.items():
        got = _read_va(data, base, secs, va, 4)
        if got is None or abs(struct.unpack('<f', got)[0] - want) > 1e-6:
            bad.append(f'float at 0x{va:06x} is {struct.unpack("<f", got)[0] if got else None}, {want:g} expected')
    return bad


def _xbe_reader(path):
    d = Path(path).read_bytes()
    if d[:4] != b'XBEH':
        raise ValueError('not an XBE')
    base = struct.unpack_from('<I', d, 0x104)[0]
    nsec = struct.unpack_from('<I', d, 0x11c)[0]
    shdr = struct.unpack_from('<I', d, 0x120)[0] - base
    secs = []
    for i in range(nsec):
        _flags, va, vsz, raw, rsz = struct.unpack_from('<IIIII', d, shdr + 56 * i)
        secs.append((va, vsz, raw, rsz))

    def rd(va, n):
        for sva, vsz, raw, rsz in secs:
            if sva <= va < sva + vsz and va - sva + n <= rsz:
                return d[raw + va - sva:raw + va - sva + n]
        return None
    return rd


def verify_xbe(xbe_path):
    """XML1's energy constants and the value table's resolver slot against default.xbe. Returns mismatch strings."""
    rd = _xbe_reader(xbe_path)
    bad = []
    for va, want in X1_FLOATS.items():
        got = rd(va, 4)
        if got is None or abs(struct.unpack('<f', got)[0] - want) > 1e-6:
            bad.append(f'default.xbe float at 0x{va:06x} is {struct.unpack("<f", got)[0] if got else None}, '
                       f'{want:g} expected')
    vt = rd(0x3d4380, 12)
    if vt is None or struct.unpack('<III', vt) != (0xb8100, 0x13d370, 0xb7e60):
        bad.append(f'default.xbe value table vtable 0x3d4380 is {vt!r} (loader 0xb8100, resolver 0xb7e60 expected)')
    return bad


# ------------------------------------------------------------------------------------------ validator V19
def validate_entity_codes(v, ck):
    """Check the final entity files, after every importer has had a chance to overwrite them."""
    seen = set()
    for rel in sorted(v.idx.under('data/entities/'), key=str.lower):
        if not rel.lower().endswith(('.xmlb', '.engb')) or v.entry(rel) is None:
            continue                               # unchanged XML2 files retain retail behavior
        ck.count('entity_files_checked')
        found, _ = code_findings(v.tree(rel))
        for where, tag, attr, value in found:
            key = (str(Path(rel).with_suffix('')).lower(), where, tag, attr.lower(), value)
            if key in seen:
                continue
            seen.add(key)
            ck.error(f'{rel}:{where} <{tag} {attr}="{value}">: entity value code XMen2.exe reads as 0; '
                     f'resolve the XML1 code in every entity import path (SPEC 29.2)')
    ck.set('entity_value_codes_left', len(seen))


def v19(v, ck):
    """V19 NPC value codes and energy (SPEC 24): the name table / energy constants equal the install's XMen2.exe;
    no style file the build wrote holds a value code XMen2.exe reads as 0 (XML2 retail files are allowlisted
    per file; the five codes XMen2.exe resolves itself are notes); the shared talent ENERGY_TALENT carries XML1's
    energy terms for every rank a stats entry uses, and every XML1-origin npcstat entry with a mind carries it at
    rank = mind (none elsewhere)."""
    from . import combat_events as CE             # noqa: WPS433
    ctx = v.ctx
    exe = Path(ctx.base) / 'XMen2.exe'
    if not exe.exists():
        exe = v.idx.path('XMen2.exe')
    if exe is None or not Path(exe).exists():
        ck.error('XMen2.exe not found in the base install or <out>: value table unverified')
    else:
        for b in verify_exe(exe):
            ck.error(f'XMen2.exe does not match npc_values: {b}')
    seen = set()
    retail = collections.Counter()
    exe_total = collections.Counter()
    per_style = collections.Counter()
    for rel in CE.style_rels(v.idx):
        root = v.tree(rel)
        if root is None:
            continue
        stem = CE._stem(rel)
        ours = v.entry(rel) is not None
        ck.count('style_files_checked')
        found, exe_codes = code_findings(root)
        if ours:
            exe_total.update(exe_codes)
        for where, tag, k, val in found:
            if not ours:
                retail[stem] += 1
                continue
            key = (stem, where, tag, k.lower(), val)
            if key in seen:
                continue
            seen.add(key)
            per_style[stem] += 1
            ck.error(f'{stem}:{where} <{tag} {k}="{val}">: value code XMen2.exe reads as 0 (0x{VALUE_RESOLVER:x} '
                     f'resolves only {"/".join(EXE_VALUE_NAMES)}); characters resolves XML1\'s codes (SPEC 24)')
    ck.set('value_codes_left', len(seen))
    ck.set('value_code_styles', len(per_style))
    if exe_total:
        ck.note(f'codes XMen2.exe resolves itself from data/values.xmlb left in built styles: {dict(exe_total)}')
    for stem, n in sorted(retail.items()):
        ck.allow(f'{stem}: {n} value code(s)', 'XML2 retail style file, unchanged (XMen2.exe ships it so)')
    validate_entity_codes(v, ck)
    # ---- the NPC energy talent
    st = v.stats()
    x1 = v.x1_stats()
    for ext in ('.xmlb', '.engb'):
        t = v.tree(f'data/shared_talents{ext}')
        defs = [x for x in t.iter('talent') if (x.get('name') or '').lower() == ENERGY_TALENT] if t is not None else []
        ranks = {}
        for el in st['variants'].get(ext, {}).get('npcstat', []):
            name = (el.get('name') or '').lower()
            refs = [x for x in el if isinstance(x.tag, str) and x.tag.lower() == 'talent'
                    and (x.get('name') or '').lower() == ENERGY_TALENT]
            want = energy_rank(el) if name in x1 else None
            got = [int(x.get('level') or 0) for x in refs]
            if name not in x1:
                if refs:
                    ck.error(f'npcstat{ext} {el.get("name")}: XML2 entry carries {ENERGY_TALENT}')
                continue
            if want is None and got:
                ck.error(f'npcstat{ext} {el.get("name")}: {ENERGY_TALENT} {got} but no mind')
            elif want is not None and got != [want]:
                ck.error(f'npcstat{ext} {el.get("name")}: {ENERGY_TALENT} ranks {got}, [{want}] expected (mind '
                         f'{el.get("mind")}: XML1 pool {x1_max_energy(_int_attr(el, "level") or 1, want)})')
            if want is not None:
                ranks[name] = want
        if ext == '.engb':
            ck.set('npc_energy_entries', len(ranks))
            ck.set('npc_energy_max_rank', max(ranks.values(), default=0))
        if ranks:
            if len(defs) != 1:
                ck.error(f'shared_talents{ext}: {len(defs)} definitions of {ENERGY_TALENT} (1 expected)')
            for b in talent_problems(defs[0] if defs else None, max(ranks.values())):
                ck.error(f'shared_talents{ext}: {b}')
    v19_immunities(v, ck)


def v19_immunities(v, ck):
    """SPEC 30: every XML1-origin npcstat entry whose XML1 source carried an inline immunity body (immunity_rows)
    names a shared talent whose definition in <out> carries the same affecter rows (any name); every immunity-form
    shared talent in <out> is named by some stats entry (else a warning: it costs a pool slot for nothing)."""
    ctx = v.ctx
    try:
        x2 = {(t.get('name') or '').lower() for t in ctx.read_base_xmlb('Data/shared_talents.engb').iter('talent')}
    except Exception:          # noqa: BLE001 - no base install: nothing XML2-defined to exclude
        x2 = set()
    try:
        x1root = ctx.read_x1_xml('data/npcstat.eng')
    except Exception:          # noqa: BLE001
        x1root = None
    if x1root is None:
        ck.warn('XML1 data/npcstat.eng not readable: NPC immunity talents (SPEC 30) unverified')
        return
    x1_by = {(st.get('name') or '').lower(): st for st in x1root.iter()
             if isinstance(st.tag, str) and st.tag.lower() == 'stats'}
    st = v.stats()
    for ext in ('.xmlb', '.engb'):
        t = v.tree(f'data/shared_talents{ext}')
        defs = {(x.get('name') or '').lower(): x for x in t.iter('talent')} if t is not None else {}
        def_rows = {n: definition_rows(x) for n, x in defs.items()}
        n_entries = n_refs = 0
        used, referenced = set(), set()
        for el in st['variants'].get(ext, {}).get('npcstat', []) + st['variants'].get(ext, {}).get('herostat', []):
            name = (el.get('name') or '').lower()
            refs = [(x.get('name') or '').lower() for x in el if isinstance(x.tag, str) and x.tag.lower() == 'talent']
            referenced.update(refs)
            src = x1_by.get(name)
            if src is None:
                continue
            wanted = []
            for tl in src:
                if not isinstance(tl.tag, str) or tl.tag.lower() != 'talent' or len(tl) == 0 \
                        or (tl.get('name') or '').lower() in x2:
                    continue
                rows, _info = immunity_rows(tl)
                if rows is not None:
                    wanted.append((tl.get('name'), immunity_key(rows)))
            if not wanted:
                continue
            n_entries += 1
            have = {r: immunity_key(def_rows[r]) for r in refs if def_rows.get(r)}
            for tn, key in wanted:
                hits = [r for r, k in have.items() if k == key]
                if not hits:
                    ck.error(f'npcstat{ext} {el.get("name")}: XML1 inline talent {tn} '
                             f'({" ".join(a + ("=" + lv if lv else "") for a, _, lv, _ in key)}) has no shared '
                             f'talent with the same affecters (SPEC 30)')
                else:
                    used.update(hits)
                    n_refs += 1
        idle = sorted(n for n, r in def_rows.items() if r and n not in x2 and n not in referenced)
        if idle:
            ck.warn(f'shared_talents{ext}: immunity talents named by no stats entry {idle} (a pool slot each)')
        if ext == '.engb':
            ck.set('npc_immunity_entries', n_entries)
            ck.set('npc_immunity_refs', n_refs)
            ck.set('npc_immunity_talents', len(used))
