"""xml1build.loot - the first game's item economy as data (loot + Forge, step 1: the builder side; 0.4.2).

Opt-in: `--loot xml1` (default off). With it the build

  * keeps today's 88 item definitions byte-identical in order and keys, converts the 19 Danger Room rewards again in
    place (no cost, unique, source class, every bonus) and appends the other 97 XML1 equipment as `lc_x1_<name>`
    (identity table: DESIGN 2.1); every bonus of every one of them is converted (xml1build.item_bonuses; nothing is
    pending, every record is single-valued) and quality is baked into the display name (XML1's own prefix strings
    1006-1009 + one space);
  * rewrites every reference the converted maps make to an XML1 equipment name to the new identity;
  * writes `Data/x1economy.txt`, the sidecar the XML2 Fix economy rule reads (format: DESIGN 2.2.1; it carries what
    XMen2.exe's item parser never reads: group, frequency, Grab Bag, sellable, ...), and `approximations.json` /
    `APPROXIMATIONS.md` (DESIGN 2.4), one row per item per non-exact bonus and per behaviour deviation;
  * writes `[Game] Xml1Economy=1` (fix_ini) and hides the shop's Training tab (shop_appearance);
  * is checked by V-LOOT (validate_loot below, DESIGN 8.1).

It needs the W2 save layout (`--save-layout w2`: item definitions > 160, enhancement records > 512). Without
`--loot xml1` nothing here runs and the build is byte-identical to a build without this module. The DLL half (the
roller, prices, the Forge) is xml2-fix's, steps 3-8 of DESIGN 9; this module only produces the data.

Pure helpers first (no ctx), then the build hooks zones.py / fix_ini.py / savefiles.py / shop_appearance.py call.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import xml.etree.ElementTree as ET

from . import common as C
from . import item_bonuses as IB

OPTION = 'loot'
CHOICES = ('off', 'xml1')
CONSTRUCTION_CHOICES = ('zero-draw', 'one-roll')     # DESIGN 2.5: plan A, or the accepted native fallback (D7)
DEF_DAMAGE_SCALE_CHOICES = IB.DEF_DAMAGE_SCALE_MODES  # DESIGN 12 D8: ('noop', 'resist'); noop = the original's behaviour
NAME_PREFIX = 'lc_x1_'
SIDECAR_REL = 'Data/x1economy.txt'
SIDECAR_HEADER = 'x1economy'
SIDECAR_FORMAT = 1
APPROXIMATIONS_JSON = 'approximations.json'
APPROXIMATIONS_MD = 'APPROXIMATIONS.md'
DOCS_DIR = 'Docs'
REPORT_META = 'loot.json'                              # <out>/_build/loot.json: what V-LOOT re-checks

# sidecar flags (DESIGN 2.2.1)
F_UNIQUE, F_GRABBAG, F_REBUILT, F_NOAWARD, F_SELLABLE, F_MONEY, F_EQUIPMENT = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40
SELLABLE_MIN_INDEX = 15              # XML1 0x17b7eb: non-equipment is sold when its source index is above this
QUALITY_STRING_ID = {-2: 1006, -1: 1007, 1: 1008, 2: 1009}        # Broken / Basic / Super / Ultra (0 and uniques: none)
MAX_NEW_NAME = 27                    # DESIGN 2.1: the longest `lc_x1_` name
OWN_REBUILT_ATTRIBUTE = 0x1          # catalogue.lcc ITEM entry attribute: the instance's own list is rebuilt on load

# what the economy can see of the first game's non-equipment definitions, by source type
PLAIN_TYPES = ('item', 'money', 'skill', 'stat')

# DESIGN 1.3 / 8.1 item 3: the numbers the validator pins against the source (aggregate counts, no game text)
FORGE_BY_G = (18, 37, 52, 69, 85)
FORGE_UNIQUES_BY_G = (7, 14, 17, 17, 17)
DROP_POOLS = {1: ((7, 7), (6, 3), (8, 0)), 2: ((16, 16), (10, 4), (17, 0)), 3: ((22, 22), (13, 4), (26, 0)),
              4: ((23, 23), (17, 4), (39, 0)), 5: ((14, 14), (16, 3), (43, 0))}      # G: (bucket 1, 2, 3) = (n, uniques)
SOURCE_EQUIPMENT, SOURCE_POWERUPS = 116, 168
NEW_DEFINITIONS, KEPT_DR_REWARDS = 97, 19
LEGACY_DEFINITIONS = 88

# DESIGN 2.4: the behaviour deviations of 0.4.2, source-controlled. Each is one row of approximations.json; a row is
# active when the build carries the rule it records. `construction-one-roll` ships only when the build is told the
# DLL fallback does (--loot-construction one-roll).
BEHAVIOUR_ROWS = (
    ('grabbag-charge-once', 'grab bag',
     'the bag price (2000 x G^2) is debited again when XML1 retries an empty first pass (0x17c480)',
     'the bag is charged once, by the native buy path; the retry adds no charge, and a bag that finds nothing after '
     'the retry refunds nothing',
     'owner decision D6 (2026-10-26)'),
    ('g-per-roll', 'drop tiers',
     'the item tier G is cached when a level is placed, when the character menu updates and when a shop opens',
     'G = min(5, highest roster level / 10 + 1) is computed at every roll, every shop open and every bag purchase',
     'the character menu opens on one PC only online, so a cached G would diverge between peers (lockstep)'),
    ('carry-gate-20', 'inventory',
     'the carry limit counts item quantities',
     'XML2\'s carry gate of 20 equipment items is kept',
     'the gate lives in XMen2.exe\'s shop and pickup code and is not changed'),
    ('legacy-xml2-gear', 'existing saves',
     'no such items exist',
     'XML2 gear a save already holds stays usable, no longer drops or sells in the Forge, and sells at XML1\'s '
     '25 percent (33 percent for uniques) of its XML2 value',
     'owner decision D2 (2026-10-25)'),
    ('dr-king-pip-branch', 'danger room',
     'the drop roller has no king-pip branch (SKIRMISH_KING_PIP is a map-placed item)',
     'the PC roller\'s Danger Room king-pip branch (0x46e539-0x46e573) is kept',
     'a Danger Room mode feature, not a loot drop'),
    ('treasure-pc-cadence', 'treasure',
     'XML1 has no treasure entity class; breakables roll once',
     'PC treasure entities keep their 5-12 ordinary events plus one special event, each a full roll at category 5; the '
     'native argument-3 equipment restriction and single-pickup money are not applied',
     'CTreasureEntity is PC-only content with no XML1 counterpart'),
    ('level-adjust-no-regen', 'level adjustment',
     'changing a level regenerates nothing; heroes keep what they wear',
     'XML2\'s level-adjustment gear regeneration (0x448dc0) is bypassed, so equipped gear is kept',
     'an XML2 behaviour removed, recorded because it is not an approximation'),
    ('physical-spawn-rng', 'drop placement',
     'XML1\'s placement draws scatter a drop',
     'the spawn scatter uses the PC engine\'s own placement draws (0x46be70), separate from the roller\'s draws',
     'physical placement is PC engine code'),
)
CONSTRUCTION_ROW = ('construction-one-roll', 'construction',
                    'an item is built with its own bonuses and no random draw',
                    'the native constructor draws one lockstep value per own enhancement; every economy record is '
                    'single-valued, so the bonus is unchanged, only the draw count differs',
                    'owner decision D7 (2026-10-26): the accepted fallback if the zero-draw initializer cannot reach parity')


# ---------------------------------------------------------------------------------------------------- options
def _args(x):
    a = getattr(x, 'args', None)
    return a if a is not None else x


def selected(x) -> bool:
    """True when the build was asked for `--loot xml1`. x: a BuildContext, an argparse namespace or anything with
    `.loot` (a standalone check over a finished build gets it through common.args_for_out)."""
    return str(getattr(_args(x), OPTION, 'off') or 'off').lower() == 'xml1'


def w2_selected(args) -> bool:
    """True when the W2 save layout is selected (builder option --save-layout w2). The one place that reads that
    option for the economy."""
    return str(getattr(_args(args), 'save_layout', 'retail') or 'retail').lower() == 'w2'


def construction_fallback(x) -> bool:
    return str(getattr(_args(x), 'loot_construction', 'zero-draw') or 'zero-draw').lower() == 'one-roll'


def def_damage_resist(x) -> bool:
    """True when the build was asked for `--loot-def-damage-scale resist` (D8: the four dead `def_damage_scale` items get
    their authored multiplier as a damage-resistance record). build_xml1 makes resist the default of a --loot xml1 build
    (Owen's D8); an args object without the option reads noop (the original's dead bonus, byte for byte)."""
    return str(getattr(_args(x), 'loot_def_damage_scale', 'noop') or 'noop').lower() == 'resist'


def refusal(args) -> str | None:
    """why `--loot xml1` cannot be built with `args`, or None. The economy needs the W2 item limits (185 definitions,
    records over 512) and the XML1 front end (the Danger Room rewards)."""
    if not selected(args):
        if construction_fallback(args):
            return '--loot-construction one-roll needs --loot xml1'
        if def_damage_resist(args):
            return '--loot-def-damage-scale resist needs --loot xml1'
        return None
    if not w2_selected(args):
        return ('--loot xml1 needs the W2 save layout (--save-layout w2): the first game\'s economy has 185 item '
                'definitions and more than 512 enhancement records')
    frontend = str(getattr(_args(args), 'frontend', 'xml1') or 'xml1').lower()
    if frontend != 'xml1':
        return '--loot xml1 needs the XML1 front end (--frontend xml1): the Danger Room rewards are part of the economy'
    return None


# ---------------------------------------------------------------------------------------------------- source data
class SourceItem:
    """one XML1 definition: its position in items.eng, its element (lower-case attribute names) and its place in the
    economy's identity table"""

    def __init__(self, index, element):
        self.index = index
        self.element = element
        self.name = (element.get('name') or '').strip()
        self.lname = self.name.lower()
        self.type = (element.get('type') or 'item').strip().lower()
        self.is_equipment = self.type == 'equipment'
        self.group = _int(element.get('group'))
        self.frequency = _int(element.get('frequency'))
        self.quality = _int(element.get('quality'))
        self.cost = _int(element.get('cost'))
        self.unique = _true(element, 'unique')
        self.grabbag = _true(element, 'grabbag')
        self.xml1_class = element.get('class')
        self.identity = None            # the Data/items name the economy uses for it
        self.rebuilt = False            # a Danger Room reward converted again in place (own_rebuilt)


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _true(el, key):
    return (el.get(key) or '').strip().lower() == 'true'


def source_items(root):
    """[SourceItem] of an XML1 items.eng root (any depth: the builder passes the table's top-level element)."""
    top = C.iter_roots(root)[0]
    return [SourceItem(i, c) for i, c in enumerate(c for c in top if c.tag.lower() == 'item')]


def quality_strings(strings_root):
    """{quality: prefix text} from XML1 strings.eng (ids 1006-1009); a missing string is an error for the caller"""
    texts = {}
    for el in strings_root.iter():
        if el.tag.lower() == 'string' and el.get('id'):
            texts[_int(el.get('id'))] = el.get('text') or ''
    return {q: texts.get(sid) for q, sid in QUALITY_STRING_ID.items()}


def display_name(src, prefixes):
    """XML1's `%s%s%s` with a single ASCII space after a non-empty prefix; none for quality 0 and for uniques (they
    carry no quality)"""
    name = src.element.get('displayname') or src.name
    if src.unique or src.quality in (None, 0):
        return name
    prefix = prefixes.get(src.quality)
    if prefix is None:
        raise ValueError(f'{src.name}: quality {src.quality} has no prefix string')
    return f'{prefix} {name}' if prefix else name


def new_name(source_name):
    return NAME_PREFIX + source_name.lower()


class Plan:
    """the identity table of one build: which source definition is which Data/items name"""

    def __init__(self, items, dr_names):
        self.items = items
        self.dr = {n.lower() for n in dr_names}
        self.dr_order = list(dr_names)
        for it in items:
            if it.is_equipment:
                if it.lname in self.dr:
                    it.identity, it.rebuilt = it.name, True
                else:
                    it.identity = new_name(it.name)
            else:
                it.identity = it.name
        self.by_lname = {it.lname: it for it in items}
        self.equipment = [it for it in items if it.is_equipment]
        self.new = [it for it in self.equipment if not it.rebuilt]
        self.kept_dr = [it for it in self.equipment if it.rebuilt]
        # names the converted maps place (set by the reference rewrite): their definitions are awarded in play
        self.placed = set()

    def reference_map(self):
        """{lower XML1 equipment name: new identity} for the references the rewrite changes (the kept Danger Room
        rewards keep their names)"""
        return {it.lname: it.identity for it in self.new}


def build_plan(ctx, x1top=None):
    """the Plan of this build (cached in ctx.shared). x1top: the XML1 items table as the world-table merge holds it;
    given, the plan's source elements are swapped for those (so the conversion reads what the legacy path read)."""
    plan = ctx.shared.get('loot_plan')
    if plan is None:
        from . import frontend as FE
        plan = Plan(source_items(ctx.read_x1_xml('data/items.eng')), FE.dr_reward_items(ctx))
        ctx.shared['loot_plan'] = plan
    if x1top is not None:
        fresh = {it.lname: it for it in source_items(x1top)}
        for it in plan.items:
            other = fresh.get(it.lname)
            if other is not None:
                it.element = other.element
    return plan


# ---------------------------------------------------------------------------------------------------- references
def rewrite_references(ctx, root, where=''):
    """every `inventoryitem` of a tree that names an XML1 equipment (not a kept Danger Room reward) now names its
    identity. Returns [(old name, new name)] (the number of references rewritten)."""
    if not selected(ctx):
        return []
    plan = build_plan(ctx)
    refs = plan.reference_map()
    done = []
    for el in root.iter():
        v = (el.get('inventoryitem') or '').strip()
        new = refs.get(v.lower())
        if new is not None:
            el.set('inventoryitem', new)
            plan.placed.add(v.lower())
            done.append((v, new))
    return done


# ---------------------------------------------------------------------------------------------------- definitions
def convert_definitions(ctx, plan=None):
    """-> [Definition]: the 19 rebuilt Danger Room rewards and the 97 new definitions (source order), each with its
    <item> element and Conversion. The converter is xml1build.item_bonuses (DESIGN 2.2 / 2.3)."""
    plan = plan or build_plan(ctx)
    prefixes = quality_strings(ctx.read_x1_xml('data/strings.eng'))
    values = ctx.x1_values()
    out = []
    for it in plan.equipment:
        conv = IB.convert_equipment(ctx, it.element, name=it.identity, displayname=display_name(it, prefixes),
                                    values=values, def_damage_scale='resist' if def_damage_resist(ctx) else 'noop')
        if conv.item is None:
            raise ValueError(f'{it.name}: {conv.error}')
        out.append(Definition(it, conv))
    return out


class Definition:
    def __init__(self, source, conversion):
        self.source = source
        self.conversion = conversion
        self.element = conversion.item

    @property
    def records(self):
        return len(self.element.findall('enhancement'))


def definitions(ctx, plan=None):
    """the economy's Definitions of this build, converted once (cached in ctx.shared)"""
    cached = ctx.shared.get('loot_defs')
    if cached is None:
        cached = ctx.shared['loot_defs'] = convert_definitions(ctx, plan or build_plan(ctx))
    return cached


def dr_reward_element(ctx, source):
    """(<item>, note) of one Danger Room reward converted again from the source (zones.items_to_add): the legacy
    translate_equipment defaults (cost 10000, legend, guessed class) are retired for it"""
    name = (source.get('name') or '').strip().lower()
    for d in definitions(ctx):
        if d.source.rebuilt and d.source.lname == name:
            return d.element, (f'{d.source.name}: converted again from the source (no cost, unique, source class, '
                               f'{d.records} bonus records, own_rebuilt)')
    return None, f'{name}: not a Danger Room reward of this build'


def apply_items(zones, x1top, out, report):
    """The loot form of Zones.items_to_add's result. `out` is the legacy list (the 24 appended XML1 items, sorted as
    ever) whose Danger Room rewards are already their re-conversion in place; the 97 new definitions are appended in
    source order. Returns (out, report)."""
    ctx = zones.ctx
    plan = build_plan(ctx, x1top)
    defs = definitions(ctx, plan)
    rebuilt = {d.element.get('name').lower(): d.element for d in defs if d.source.rebuilt}
    legacy_fp = {}
    replaced = 0
    for el in out:
        low = (el.get('name') or '').lower()
        if low in rebuilt:
            replaced += rebuilt[low] is el
        else:
            legacy_fp[el.get('name')] = fingerprint(el)
    if replaced != len(plan.kept_dr):
        ctx.error(f'loot: {replaced} Danger Room rewards re-converted in place, expected {len(plan.kept_dr)} '
                  f'(a reward the legacy list does not carry keeps no position to rebuild in)')
    result = list(out) + [d.element for d in defs if not d.source.rebuilt]
    report.append(f'loot: {len(plan.new)} equipment definitions appended as {NAME_PREFIX}<name>; '
                  f'{sum(d.records for d in defs)} own enhancement records')
    zones.loot_defs = defs
    zones.loot_legacy_fp = legacy_fp
    return result, report


def fingerprint(el):
    """canonical SHA-256 of an element (tag, sorted attributes, children in order): the legacy-definition ledger"""
    def canon(e):
        parts = [e.tag, ';'.join(f'{k}={v}' for k, v in sorted(e.attrib.items()))]
        parts.extend('(' + canon(c) + ')' for c in e)
        return '|'.join(parts)
    return hashlib.sha256(canon(el).encode('utf-8', 'replace')).hexdigest()


# ---------------------------------------------------------------------------------------------------- sidecar
def _tok(v):
    return '-' if v is None else str(v)


def sidecar_rows(plan, item_names):
    """[(definition index, line)] of the sidecar body for a built items table: item_names = the definition names of
    Data/items in order. Every XML1 definition the economy can see, sorted by definition index (DESIGN 2.2.1)."""
    index = {n.lower(): i for i, n in enumerate(item_names)}
    rows = []
    for it in plan.items:
        if not it.is_equipment and it.type not in PLAIN_TYPES:
            continue                              # xp pickups: no single PC definition (the per-amount items)
        i = index.get(it.identity.lower())
        if i is None:
            continue
        rows.append((i, sidecar_line(plan, it, item_names[i])))
    rows.sort(key=lambda r: r[0])
    return rows


def sidecar_line(plan, it, name):
    flags = 0
    if it.is_equipment:
        flags |= F_EQUIPMENT
    if it.unique:
        flags |= F_UNIQUE
    if it.grabbag:
        flags |= F_GRABBAG
    if it.rebuilt:
        flags |= F_REBUILT
    if it.is_equipment and it.group == -1 and not it.rebuilt and it.lname not in plan.placed:
        flags |= F_NOAWARD                          # converted, never awarded in play (XML1 has no path)
    if it.is_equipment or it.index > SELLABLE_MIN_INDEX:
        flags |= F_SELLABLE
    if it.type == 'money':
        flags |= F_MONEY
    if it.is_equipment:
        vendor = 'forge'
    elif it.group is not None and it.group > 0 and it.type == 'item':
        vendor = 'healer'
    else:
        vendor = 'none'
    group = it.group
    frequency = it.frequency if it.frequency and it.frequency > 0 else None
    # packs carry no cost in the table: the price is code (225G-125)
    pack = not it.is_equipment and it.type == 'item' and it.group is not None and it.group > 0
    cost = None if pack else it.cost
    return ' '.join((name, _tok(group), _tok(frequency), format(flags, 'x'), _tok(cost), vendor,
                     _tok(it.quality if it.quality is not None else None), str(it.index)))


def sidecar_bytes(plan, item_names):
    body = ''.join(line + '\n' for _, line in sidecar_rows(plan, item_names))
    count = body.count('\n')
    digest = hashlib.sha256(body.encode('ascii')).hexdigest()
    return (f'{SIDECAR_HEADER} {SIDECAR_FORMAT}\ncount {count}\nsha256 {digest}\n' + body).encode('ascii'), count, digest


def parse_sidecar(data):
    """-> ([row dict], count, digest) of a sidecar, or raises ValueError naming the line (the DLL's refusals)"""
    if b'\r' in data or data.startswith(b'\xef\xbb\xbf'):
        raise ValueError('CR or BOM in the sidecar')
    text = data.decode('ascii')
    lines = text.split('\n')
    if lines[-1] != '':
        raise ValueError('the sidecar does not end with LF')
    lines = lines[:-1]
    if len(lines) < 3 or lines[0] != f'{SIDECAR_HEADER} {SIDECAR_FORMAT}':
        raise ValueError('line 1: bad header')
    m = re.fullmatch(r'count (\d+)', lines[1])
    d = re.fullmatch(r'sha256 ([0-9a-f]{64})', lines[2])
    if not m or not d:
        raise ValueError('lines 2-3: bad count or digest line')
    body = lines[3:]
    if len(body) != int(m.group(1)):
        raise ValueError('count mismatch')
    raw = ''.join(l + '\n' for l in body).encode('ascii')
    if hashlib.sha256(raw).hexdigest() != d.group(1):
        raise ValueError('digest mismatch')
    rows, names = [], set()
    for n, line in enumerate(body, 4):
        t = line.split(' ')
        if len(t) != 8 or any(not x for x in t):
            raise ValueError(f'line {n}: bad token count')
        name, group, freq, flags, cost, vendor, quality, source = t
        if name in names:
            raise ValueError(f'line {n}: duplicate name')
        names.add(name)
        if vendor not in ('forge', 'healer', 'none'):
            raise ValueError(f'line {n}: bad vendor')
        rows.append(dict(name=name, group=None if group == '-' else int(group),
                         frequency=None if freq == '-' else int(freq), flags=int(flags, 16),
                         cost=None if cost == '-' else int(cost), vendor=vendor,
                         quality=None if quality == '-' else int(quality), source=int(source)))
    return rows, int(m.group(1)), d.group(1)


# ---------------------------------------------------------------------------------------------------- approximations
def _describe_source(p, values):
    a = {k.lower(): v for k, v in p.attrib.items()}
    out = []
    for k in sorted(a):
        v = a[k]
        if k == 'level' and values is not None:
            try:
                r = values.resolve(v)
            except KeyError:
                r = v
            out.append(f'level={v}' + (f' [{r}]' if r != v else ''))
        else:
            out.append(f'{k}={v}')
    for sc in p:
        if sc.tag.lower() == 'scope':
            out.append('scope(' + ' '.join(f'{k.lower()}={v}' for k, v in sorted(sc.attrib.items())) + ')')
    return ' '.join(out)


def _describe_record(enh):
    pu = enh.find('powerup')
    parts = []
    extra = {k: v for k, v in pu.attrib.items() if k != 'life'}
    if extra:
        parts.append('powerup ' + ' '.join(f'{k}={v}' for k, v in sorted(extra.items())))
    for aff in pu.iter('affecter'):
        attrs = ' '.join(f'{k}={v}' for k, v in aff.attrib.items())
        kids = ''.join(' scope(' + ' '.join(f'{k}={v}' for k, v in s.attrib.items()) + ')' for s in aff.findall('scope'))
        parts.append(f'affecter {attrs}{kids}')
    return '; '.join(parts)


def record_numbers(items_root):
    """{item name lower: [record number of each own enhancement]} for a Data/items tree: prefixes, suffixes and the
    special-affix items first, then every item's own records in definition order (the engine's allocation order)"""
    top = C.iter_roots(items_root)[0]
    n = 0
    for tag in ('prefixes', 'suffixes'):
        sec = top.find(tag)
        n += len(sec) if sec is not None else 0
    for tr in top.findall('tr_item'):
        n += len(tr.findall('enhancement'))
    out = {}
    for it in top.findall('item'):
        k = len(it.findall('enhancement'))
        out[(it.get('name') or '').lower()] = list(range(n, n + k))
        n += k
    return out, n


def bonus_rows(ctx, defs, items_root):
    """the item rows of approximations.json: one per item per source bonus, in item then source order"""
    values = ctx.x1_values()
    numbers, _ = record_numbers(items_root) if items_root is not None else ({}, 0)
    rows = []
    for d in defs:
        src = d.source
        own = list(numbers.get(d.element.get('name', '').lower(), []))
        records = iter(own)
        for p, b in zip(src.element.findall('activepowerup'), d.conversion.bonuses):
            if b.status == IB.UNSUPPORTED:
                raise ValueError(f'{src.name}: {b.powerup}: {b.reason}')
            record = None
            port = 'no record written (XML1 does nothing for it either)'
            if b.status != IB.SOURCE_NOOP:
                record = next(records, None)
                port = _describe_record(b.enhancements[0])
            low = {k.lower(): v for k, v in p.attrib.items()}
            bonus = low.get('powerup', '?') + (f'/{low["func_damage"].lower()}' if low.get('func_damage') else '')
            rows.append(dict(kind=b.kind, item=src.identity, xml1_item=src.name, bonus=bonus,
                             xml1_value=_describe_source(p, values), port_value=port, why=b.reason,
                             family=b.family, record=record))
    return rows


def behaviour_rows(fallback=False):
    rows = [dict(kind='behaviour', item=None, xml1_item=None, bonus=i, xml1_value=x, port_value=y, why=w,
                 family=f, record=None) for i, f, x, y, w in BEHAVIOUR_ROWS]
    if fallback:
        i, f, x, y, w = CONSTRUCTION_ROW
        rows.append(dict(kind='construction', item=None, xml1_item=None, bonus=i, xml1_value=x, port_value=y,
                         why=w, family=f, record=None))
    return rows


def approximation_rows(ctx, defs, items_root, fallback=False):
    return bonus_rows(ctx, defs, items_root) + behaviour_rows(fallback)


def approximations_md(rows):
    """APPROXIMATIONS.md: the same rows as the JSON, generated, never edited"""
    count = collections.Counter(r['kind'] for r in rows)
    lines = ['# Approximations and deviations of the first game\'s economy', '',
             'Generated by the builder with `--loot xml1` from `approximations.json` (the same rows). Do not edit.',
             '', 'Rows by kind: ' + ', '.join(f'{k} {count[k]}' for k in sorted(count)) + '.', '']
    order = ('bonus-approx', 'adapter', 'noop-original', 'exact', 'behaviour', 'construction')
    for kind in order:
        sel = [r for r in rows if r['kind'] == kind]
        if not sel:
            continue
        lines += [f'## {kind} ({len(sel)})', '',
                  '| item | XML1 item | bonus | XML1 value | port value | why | family | record |',
                  '|---|---|---|---|---|---|---|---|']
        for r in sel:
            cells = [r['item'], r['xml1_item'], r['bonus'], r['xml1_value'], r['port_value'], r['why'], r['family'],
                     r['record']]
            lines.append('| ' + ' | '.join('' if c is None else str(c).replace('|', '/').replace('\n', ' ')
                                          for c in cells) + ' |')
        lines.append('')
    return '\n'.join(lines) + '\n'


def approximations_json(rows):
    return json.dumps({'schema': 1, 'rows': rows}, indent=1, ensure_ascii=True).encode('ascii') + b'\n'


# ---------------------------------------------------------------------------------------------------- build outputs
def write_outputs(zones, items_root):
    """after Data/items is written: the sidecar, the approximations files and the ledger V-LOOT re-checks"""
    ctx = zones.ctx
    plan = build_plan(ctx)
    defs = zones.loot_defs
    top = C.iter_roots(items_root)[0]
    names = [c.get('name') for c in top if c.tag == 'item']
    data, count, digest = sidecar_bytes(plan, names)
    ctx.write_bytes(SIDECAR_REL, data, source='loot: the first game\'s economy sidecar (DESIGN 2.2.1)')
    rows = approximation_rows(ctx, defs, items_root, construction_fallback(ctx))
    js, md = approximations_json(rows), approximations_md(rows).encode('utf-8')
    ctx.write_meta(APPROXIMATIONS_JSON, js)
    ctx.write_meta(APPROXIMATIONS_MD, md)
    ctx.write_bytes(f'{DOCS_DIR}/{APPROXIMATIONS_JSON}', js, source='loot: approximations.json (DESIGN 2.4)')
    ctx.write_bytes(f'{DOCS_DIR}/{APPROXIMATIONS_MD}', md, source='loot: APPROXIMATIONS.md (DESIGN 2.4)')
    numbers, records = record_numbers(items_root)
    kinds = collections.Counter(r['kind'] for r in rows)
    ledger = dict(schema=1, definitions=len(names), legacy_definitions=len(names) - len(plan.new), records=records,
                  sidecar={'count': count, 'sha256': digest}, rows=dict(kinds),
                  legacy=getattr(zones, 'loot_legacy_fp', {}),
                  legacy_order=names[:len(names) - len(plan.new)],
                  new=[d.element.get('name') for d in defs if not d.source.rebuilt],
                  rebuilt=[d.element.get('name') for d in defs if d.source.rebuilt],
                  placed=sorted(plan.placed), construction='one-roll' if construction_fallback(ctx) else 'zero-draw')
    if def_damage_resist(ctx):          # recorded only when asked for: the default ledger keeps its bytes
        ledger['def_damage_scale'] = 'resist'
    ctx.write_meta(REPORT_META, ledger)
    ctx.note(f'loot: {len(names)} definitions ({len(plan.new)} new, {len(plan.kept_dr)} rebuilt), {records} enhancement '
             f'records, sidecar {count} rows, approximations {dict(kinds)}')
    for k, v in sorted(kinds.items()):
        ctx.set_count('loot_rows_' + k.replace('-', '_'), v)
    ctx.set_count('loot_definitions', len(names))
    ctx.set_count('loot_records', records)
    ctx.set_count('loot_sidecar_rows', count)


# ---------------------------------------------------------------------------------------------------- save catalogue
def derived_catalogue(build, content_version=None):
    """The master catalogue (tools/lcsave/data/catalogue.json, hashes only) plus the keys of a `--loot xml1` build:
    every item / enhancement key the economy adds is appended in table order (the same order `python -m lcsave
    catalogue --append-only` uses, so a release that commits the result gets these very ids), and the ITEM entries of
    the Danger Room rewards converted again in place are marked own_rebuilt (catalogue.ITEM_OWN_REBUILT). The
    committed catalogue stays untouched, so a build without the option writes the files it always wrote."""
    from pathlib import Path
    from lcsave import binds as BN, catalogue as CAT
    from lcsave.keys import key_hash
    cat = CAT.Catalogue.load()
    b = BN.Binds(str(build))
    cat.extend(CAT.tables_from_hashes(b.hash_tables(include_conversation_digest=False)), content_version)
    ledger = json.loads(Path(build, '_build', REPORT_META).read_text(encoding='utf-8'))
    for name in ledger.get('rebuilt', []):
        cat.set_attribute_bits('ITEM', key_hash(name), CAT.ITEM_OWN_REBUILT)
    return cat


# ---------------------------------------------------------------------------------------------------- validator
def _source_pools(plan):
    """independent of the sidecar: Forge sizes per G, drop pools per G, Grab Bag pools per G from the source items"""
    forge, drops, bags = [], {}, {}
    for g in range(1, 6):
        cat = [i for i in plan.equipment if i.group and 0 < i.group <= g and not i.grabbag]
        forge.append((len(cat), sum(1 for i in cat if i.unique)))
        row = []
        for f in (1, 2, 3):
            pool = [i for i in plan.equipment if i.frequency == f and i.group and i.group > 0
                    and (i.group == 1 or g - 2 <= i.group <= g)]
            row.append((len(pool), sum(1 for i in pool if i.unique)))
        drops[g] = tuple(row)
        flagged = [i for i in plan.equipment if i.group == g and i.grabbag and i.type == 'equipment']
        ordinary = [i for i in plan.equipment if i.group == g and not i.grabbag]
        bags[g] = (len(flagged), len(ordinary))
    return forge, drops, bags


def _sidecar_pools(rows):
    equip = [r for r in rows if r['flags'] & F_EQUIPMENT]
    forge, drops, bags = [], {}, {}
    for g in range(1, 6):
        cat = [r for r in equip if r['group'] and 0 < r['group'] <= g and not r['flags'] & F_GRABBAG]
        forge.append((len(cat), sum(1 for r in cat if r['flags'] & F_UNIQUE)))
        row = []
        for f in (1, 2, 3):
            pool = [r for r in equip if r['frequency'] == f and r['group'] and r['group'] > 0
                    and (r['group'] == 1 or g - 2 <= r['group'] <= g)]
            row.append((len(pool), sum(1 for r in pool if r['flags'] & F_UNIQUE)))
        drops[g] = tuple(row)
        bags[g] = (len([r for r in equip if r['group'] == g and r['flags'] & F_GRABBAG]),
                   len([r for r in equip if r['group'] == g and not r['flags'] & F_GRABBAG]))
    return forge, drops, bags


def validate(v, ck):
    """V-LOOT (DESIGN 8.1). Without `--loot xml1`: the build must carry nothing of the economy."""
    ctx = v.ctx
    rel = lambda r: ctx.out_path(r)
    if not selected(ctx):
        for r in (SIDECAR_REL, f'{DOCS_DIR}/{APPROXIMATIONS_JSON}', f'{DOCS_DIR}/{APPROXIMATIONS_MD}'):
            if rel(r).exists():
                ck.error(f'{r} exists in a build made without --loot xml1')
        items = v.tree('data/items.engb')
        if items is not None and any((c.get('name') or '').lower().startswith(NAME_PREFIX) for c in items.iter('item')):
            ck.error(f'{NAME_PREFIX}* definitions in a build made without --loot xml1')
        ck.note('loot economy not selected')
        return
    why = refusal(ctx.args)
    if why:
        ck.error(why)
        return
    plan = build_plan(ctx)
    items_root = v.tree('data/items.engb')
    if items_root is None:
        ck.error('Data/items.engb is missing')
        return
    top = C.iter_roots(items_root)[0]
    defs = [c for c in top if c.tag == 'item']
    names = [c.get('name') for c in defs]
    by_name = {n.lower(): c for n, c in zip(names, defs)}
    ledger = json.loads(rel('_build/' + REPORT_META).read_text(encoding='utf-8')) if rel('_build/' + REPORT_META).exists() else None
    if ledger is None:
        ck.error('_build/loot.json is missing')
        return

    # 1. accounting
    if len(plan.equipment) != SOURCE_EQUIPMENT:
        ck.error(f'{len(plan.equipment)} source equipment definitions, expected {SOURCE_EQUIPMENT}')
    if len(plan.new) != NEW_DEFINITIONS or len(plan.kept_dr) != KEPT_DR_REWARDS:
        ck.error(f'{len(plan.new)} new + {len(plan.kept_dr)} rebuilt, expected {NEW_DEFINITIONS} + {KEPT_DR_REWARDS}')
    for it in plan.equipment:
        if it.identity.lower() not in by_name:
            ck.error(f'{it.name}: identity {it.identity} is not in Data/items')
        elif len(it.identity) > MAX_NEW_NAME and not it.rebuilt:
            ck.warn(f'{it.identity}: longer than the expected {MAX_NEW_NAME} characters')
    _plain_semantics(plan, by_name, ck)
    legacy = ledger.get('legacy', {})
    plan.placed = set(ledger.get('placed', []))               # the maps' rewrites of this build (a standalone check)
    kept = len(names) - len(plan.new)
    if names[kept:] != [it.identity for it in plan.new] or names[:kept] != ledger.get('legacy_order'):
        ck.error('the table is not the legacy definitions in their order followed by the appended identities')
    if kept != LEGACY_DEFINITIONS:
        ck.warn(f'{kept} legacy definitions (the default options give {LEGACY_DEFINITIONS})')
    for n, fp in legacy.items():
        c = by_name.get(n.lower())
        if c is None or fingerprint(c) != fp:
            ck.error(f'legacy definition {n} differs from its legacy conversion')
    if any(n.lower() in plan.dr for n in legacy):
        ck.error('a rebuilt Danger Room reward is in the legacy ledger')
    ck.set('legacy_definitions_kept', kept)
    ck.set('definitions', len(names))

    # 2. sidecar equals the source field for field
    path = rel(SIDECAR_REL)
    if not path.exists():
        ck.error(f'{SIDECAR_REL} is missing')
        rows = []
    else:
        raw = path.read_bytes()
        try:
            rows, count, digest = parse_sidecar(raw)
        except ValueError as e:
            ck.error(f'{SIDECAR_REL}: {e}')
            rows = []
        else:
            want, wcount, wdigest = sidecar_bytes(plan, names)
            if raw != want:
                ck.error(f'{SIDECAR_REL} differs from the source (count {count} vs {wcount})')
            ck.set('sidecar_rows', count)
            position = {n.lower(): i for i, n in enumerate(names)}
            idx = [position.get(r['name'].lower(), -1) for r in rows]
            if -1 in idx:
                ck.error(f'{SIDECAR_REL}: a name does not resolve in Data/items')
            if idx != sorted(idx):
                ck.error(f'{SIDECAR_REL}: rows are not in definition order')
            for r in rows:
                by_src = {i.identity.lower(): i for i in plan.items}
                it = by_src.get(r['name'].lower())
                if it and it.lname == 'magnetos_helmet' and not r['flags'] & F_NOAWARD:
                    ck.error('MAGNETOS_HELMET must carry the noaward flag')
                if it and it.is_equipment and it.lname != 'magnetos_helmet' and r['flags'] & F_NOAWARD:
                    ck.error(f'{r["name"]}: noaward on an awardable definition')
            identities = {it.identity.lower() for it in plan.equipment}
            for r in rows:                      # shops, drops and bags only ever offer the economy's own equipment
                if r['flags'] & F_EQUIPMENT and r['name'].lower() not in identities:
                    ck.error(f'{SIDECAR_REL}: equipment row {r["name"]!r} is not one of the economy identities')
            noaward = [r['name'] for r in rows if r['flags'] & F_NOAWARD]
            ck.set('noaward', len(noaward))
            sellable = sum(1 for r in rows if r['flags'] & F_SELLABLE)
            ck.set('sellable', sellable)
            if any(not r['flags'] & F_SELLABLE for r in rows if r['flags'] & F_EQUIPMENT):
                ck.error('equipment that is not sellable')
            if any(r['flags'] & F_SELLABLE and not r['flags'] & F_EQUIPMENT and r['source'] <= SELLABLE_MIN_INDEX for r in rows):
                ck.error('a non-equipment definition with source index <= 15 is sellable')
            if not any(r['flags'] & F_SELLABLE and not r['flags'] & F_EQUIPMENT for r in rows):
                ck.error('no sellable non-equipment definition (HEALTH_ITEM / ENERGY_ITEM / pips)')

    # 3. Forge, drop and Grab Bag pools
    forge, drops, bags = _source_pools(plan)
    if tuple(n for n, _ in forge) != FORGE_BY_G or tuple(u for _, u in forge) != FORGE_UNIQUES_BY_G:
        ck.error(f'source Forge catalog per G {forge}, expected {FORGE_BY_G} / {FORGE_UNIQUES_BY_G}')
    if {g: drops[g] for g in drops} != DROP_POOLS:
        ck.error(f'source drop pools {drops} differ from DESIGN 1.2')
    if rows:
        sf, sd, sb = _sidecar_pools(rows)
        if (sf, sd, sb) != (forge, drops, bags):
            ck.error('the sidecar\'s Forge / drop / Grab Bag pools differ from the source')
    ck.details['forge_by_G'] = [n for n, _ in forge]
    ck.details['drop_pools'] = {str(g): [list(x) for x in drops[g]] for g in drops}
    ck.details['grabbag_pools'] = {str(g): list(bags[g]) for g in bags}

    # 4. bonuses: 168, none pending, single-valued records, own slots, records
    stat = collections.Counter()
    problems = 0
    converted = convert_definitions(ctx, plan)
    for d in converted:
        for b in d.conversion.bonuses:
            stat[b.status] += 1
            if b.status == IB.UNSUPPORTED:
                ck.error(f'{d.source.name}: {b.powerup} is pending: {b.reason}')
    total = sum(stat.values())
    if total != SOURCE_POWERUPS:
        ck.error(f'{total} source powerups converted, expected {SOURCE_POWERUPS}')
    ck.set('powerups', total)
    for k in (IB.EXACT, IB.APPROXIMATE, IB.SOURCE_NOOP, IB.ADAPTER, IB.UNSUPPORTED):
        ck.set('powerups_' + k, stat.get(k, 0))
    numbers, records = record_numbers(items_root)
    _enhancement_payloads(ck, plan, by_name, converted)
    for it in plan.equipment:
        c = by_name.get(it.identity.lower())
        if c is None:
            continue
        enh = c.findall('enhancement')
        if len(enh) > IB.OWN_SLOTS:
            ck.error(f'{it.identity}: {len(enh)} own records exceed {IB.OWN_SLOTS}')
        if not enh and any(b != 'noop' for b in ()):
            pass
        for e in enh:
            if not IB.single_valued(e):
                ck.error(f'{it.identity}: an enhancement record is not single-valued')
            if len(e.findall('powerup')) != 1:
                ck.error(f'{it.identity}: an enhancement without exactly one powerup')
    if any(0xffff in r for r in numbers.values()):
        ck.error('an own enhancement record is the 0xffff sentinel')
    ck.set('records', records)

    # 5. capacity
    from lcsave import layout as L
    w2 = L.W2
    if len(names) > w2.definitions:
        ck.error(f'{len(names)} definitions > {w2.definitions}')
    if records > w2.enhancement_records:
        ck.error(f'{records} enhancement records > {w2.enhancement_records}')
    worst = sum(len(c.findall('enhancement')) for c in defs)          # every definition carried once
    ck.set('attached_worst_inventory', worst)
    if worst > w2.attached_enhancements // 2:
        ck.error(f'worst-case attached records {worst} > 50 percent of {w2.attached_enhancements}')
    stock = FORGE_BY_G[-1]
    ck.set('vendor_stock_max', stock)
    if stock > 100:
        ck.error(f'vendor stock {stock} > the 100-row shop array')

    # 6. references
    _references(v, ck, plan, by_name)

    # 7. text
    prefixes = quality_strings(ctx.read_x1_xml('data/strings.eng'))
    for it in plan.equipment:
        c = by_name.get(it.identity.lower())
        if c is None:
            continue
        if not (c.get('displayname') or '').strip() or not (c.get('description') or '').strip():
            ck.error(f'{it.identity}: displayname or description is missing')
        want = display_name(it, prefixes)
        if c.get('displayname') != want:
            ck.error(f'{it.identity}: displayname {c.get("displayname")!r} is not {want!r}')
        if c.get('quality') is not None:
            ck.error(f'{it.identity}: carries a PC quality attribute')
        if c.get('enemy_level') != '-1':
            ck.error(f'{it.identity}: enemy_level is {c.get("enemy_level")!r}, expected -1')
        if (c.get('cost') or None) != (str(it.cost) if it.cost is not None else None):
            ck.error(f'{it.identity}: cost {c.get("cost")!r} is not the source cost {it.cost!r}')
        if (c.get('unique') or '').lower() != ('true' if it.unique else ''):
            ck.error(f'{it.identity}: unique flag differs from the source')
        if c.get('class') != IB.CLASS_MAP.get(it.xml1_class):
            ck.error(f'{it.identity}: class {c.get("class")!r} is not the source class {it.xml1_class!r}')

    # 9. approximations both ways
    _approximations(v, ck, plan, top, items_root)

    # 9b. D8: the four dead def_damage_scale items carry a damage-resistance record exactly when `resist` was asked for
    _def_damage_scale(ctx, ck, plan, by_name, ledger)

    # 10. treasure entities in the converted maps
    ck.set('treasureent_placements', _treasure_count(v))


RESIST_ITEMS = ('magnetos_helmet', 'shiar_mind_gem', 'shiar_body_shield', 'shiar_energy_armor')    # DESIGN 12 D8


def _def_damage_scale(ctx, ck, plan, by_name, ledger):
    resist = def_damage_resist(ctx)
    recorded = ledger.get('def_damage_scale', 'noop')
    if resist != (recorded == 'resist'):
        ck.error(f'--loot-def-damage-scale is {"resist" if resist else "noop"} but _build/loot.json records {recorded!r}')
    found = 0
    for low in RESIST_ITEMS:
        it = plan.by_lname.get(low)
        c = by_name.get(it.identity.lower()) if it is not None else None
        if c is None:
            ck.error(f'{low}: not in Data/items')
            continue
        recs = [e for e in c.findall('enhancement')]
        scoped = [e for e in recs if any(a.get('attribute') == 'def_damage_scope' for a in e.iter('affecter'))]
        found += len(scoped)
        if resist and len(scoped) != 1:
            ck.error(f'{it.identity}: expected one damage-resistance record under resist, found {len(scoped)}')
        if not resist and recs:
            ck.error(f'{it.identity}: carries {len(recs)} records but its only bonus is the original no-op')
    if resist:                      # a default (noop) build keeps its validate.json as it was
        ck.set('d8_resist_records', found)


def _enhancement_payloads(ck, plan, by_name, converted):
    """every emitted enhancement record equals the one the converter produces from the source now (tag, attributes,
    children, in order): the approximation ledger (_approximations) is regenerated from the same conversion, so a
    record that drifted in Data/items (a bonus 10 written as 999) must not pass just because its index is right"""
    wanted = {d.element.get('name', '').lower(): d.element.findall('enhancement') for d in converted}
    checked = 0
    for it in plan.equipment:
        c = by_name.get(it.identity.lower())
        want = wanted.get(it.identity.lower())
        if c is None or want is None:
            continue                                   # a missing definition is already an error
        got = c.findall('enhancement')
        if len(got) != len(want):
            ck.error(f'{it.identity}: {len(got)} enhancement records emitted, the conversion gives {len(want)}')
        for i, (g, w) in enumerate(zip(got, want)):
            checked += 1
            if fingerprint(g) != fingerprint(w):
                ck.error(f'{it.identity}: enhancement record {i} differs from the conversion: emitted '
                         f'[{_record_text(g)}], expected [{_record_text(w)}]')
    ck.set('enhancement_payloads_checked', checked)


def _record_text(enh):
    """one record as `description | tag attr=value ...` for a message (every attribute, nested, in order)"""
    parts = []
    for e in enh.iter():
        parts.append(e.tag + ''.join(f' {k}={v}' for k, v in e.attrib.items()))
    return ' / '.join(parts)


def _plain_semantics(plan, by_name, ck):
    for it in plan.items:
        if it.is_equipment:
            continue
        low = it.lname
        c = by_name.get(low)
        if it.type == 'xp':
            if not any(n.startswith('xp_') or n == 'xp' for n in by_name):
                ck.error('the XML1 xp pickup has no counterpart item')
            continue
        if c is None:
            ck.error(f'{it.name}: no entry in Data/items')
            continue
        t = (c.get('type') or '').lower()
        want = {'money': 'money'}.get(it.type)
        if it.type == 'money' and t != 'money':
            ck.error(f'{it.name}: type {t!r}, expected money')
        elif low in ('health_item', 'energy_item') and (t != 'potion' or not c.get('onactivate')):
            ck.error(f'{it.name}: expected a potion with onactivate')
        elif low in ('xtreme_pip', 'skirmish_king_pip') and not c.get('onactivate'):
            ck.error(f'{it.name}: a pip without its script')
        elif it.type in ('skill', 'stat') and not c.get('onactivate'):
            ck.error(f'{it.name}: no onactivate')
        del want


def _references(v, ck, plan, by_name):
    """no converted content names a legacy XML2 equipment; every XML1 equipment reference resolves to its identity"""
    ctx = v.ctx
    x1 = {it.lname for it in plan.equipment}
    keep = {it.lname for it in plan.kept_dr}
    allowed = keep | {it.identity.lower() for it in plan.new}
    bad, ok = [], 0
    for n, vals in v.scan.inv_items.items():
        for ref in vals:
            low = ref.strip().lower()
            if low in x1 and low not in keep:
                bad.append((v.scan.files[n]['rel'], ref))
            elif low in allowed:
                ok += 1
    for rel, ref in bad[:20]:
        ck.error(f'{rel}: inventoryitem {ref!r} names a legacy equipment; it must be {NAME_PREFIX}{ref.lower()}')
    # every equipment reference, whatever it names, must be one of the economy's identities: a definition in Data/items
    # of type equipment that is not an XML1 reward kept in the Danger Room or an appended lc_x1_ identity (an XML2-only
    # equipment, a legacy one) is not part of the classic economy and has no row in the sidecar
    stray = {}
    for n, vals in v.scan.inv_items.items():
        for ref in vals:
            _stray_equipment(by_name, allowed, x1, ref, v.scan.files[n]['rel'], stray)
    dr = v.tree('data/dangerroom.engb') if v.entry('data/dangerroom.engb') else None
    seen = set()
    no_reward = []
    for course in (dr.iter('COURSE') if dr is not None else ()):
        rewards = [r for r in course if r.tag == 'REWARD']
        item = next((r.get('rewarditem') for r in rewards if r.get('rewarditem')), None)
        if item is None:
            no_reward.append(course.get('name'))
        else:
            seen.add(item.strip().lower())
            if item.strip().lower() not in keep:
                ck.error(f'course {course.get("name")}: rewarditem {item!r} is not one of the kept rewards')
        for r in rewards:                                   # a second reward item on a course is a reference too
            _stray_equipment(by_name, allowed, x1, r.get('rewarditem'), f'Data/dangerroom.engb course {course.get("name")}', stray)
    for (rel, low), c in sorted(stray.items())[:20]:
        ck.error(f'{rel}: names {low!r}, an equipment definition that is not one of the economy identities')
    if seen != keep:
        ck.error(f'the Danger Room names {len(seen)} reward items, expected the {len(keep)} kept ones')
    ck.set('equipment_references', ok)
    ck.set('courses_without_reward_item', len(no_reward))
    ck.details['courses_without_reward_item'] = no_reward          # the PC generated-gear branch is suppressed for them


def _stray_equipment(by_name, allowed, legacy, ref, where, found):
    """records (where, name) -> definition in `found` when `ref` names an equipment definition outside `allowed`
    (`legacy`: the XML1 names, which the legacy-name check reports with the identity to use instead)"""
    low = (ref or '').strip().lower()
    c = by_name.get(low)
    if c is not None and (c.get('type') or '').strip().lower() == 'equipment' and low not in allowed and low not in legacy:
        found[(where, low)] = c


def _treasure_count(v):
    """placements of treasureent entities in the maps the zones module wrote (each map once: .XMLB and .engb twins)"""
    stems = {}
    for rel, f in v.scan.files.items():
        if f.get('owner') == 'zones' and rel.startswith('maps/') and f.get('ok'):
            stem = rel.rsplit('.', 1)[0]
            if stem not in stems or rel.endswith('.engb'):
                stems[stem] = f['rel']
    n = 0
    for rel in stems.values():
        root = v.tree(rel)
        if root is None:
            continue
        kinds = {(e.get('name') or '') for e in root.iter('entity') if (e.get('classname') or '').lower() == 'treasureent'}
        if kinds:
            n += sum(len(list(ei.iter('inst'))) for ei in root.iter('entinst') if ei.get('type') in kinds)
    return n


def _approximations(v, ck, plan, top, items_root):
    ctx = v.ctx
    jp = ctx.out_path('_build/' + APPROXIMATIONS_JSON)
    mp = ctx.out_path('_build/' + APPROXIMATIONS_MD)
    if not jp.exists() or not mp.exists():
        ck.error('approximations.json / APPROXIMATIONS.md missing from the report folder')
        return
    got = json.loads(jp.read_text(encoding='utf-8'))
    rows = got.get('rows', [])
    for folder in (DOCS_DIR,):
        for name, path in ((APPROXIMATIONS_JSON, jp), (APPROXIMATIONS_MD, mp)):
            other = ctx.out_path(f'{folder}/{name}')
            if not other.exists() or other.read_bytes() != path.read_bytes():
                ck.error(f'{folder}/{name} differs from the report folder\'s copy')
    if mp.read_text(encoding='utf-8') != approximations_md(rows):
        ck.error('APPROXIMATIONS.md does not equal approximations.json')
    defs = convert_definitions(ctx, plan)
    want = approximation_rows(ctx, defs, items_root, construction_fallback(ctx))
    if rows != want:
        ck.error('approximations.json differs from the rows the conversion and the behaviour table produce')
    # both ways: every non-exact conversion has exactly one row; every row names an existing item / record
    keyed = collections.Counter((r['kind'], r['item'], r['bonus'], r['xml1_value']) for r in rows)
    for k, n in keyed.items():
        if n > 1:
            ck.error(f'duplicate approximation row {k[:3]}')
    numbers, nrec = record_numbers(items_root)
    names = {(c.get('name') or '').lower() for c in top if c.tag == 'item'}
    for r in rows:
        if r['kind'] in ('behaviour', 'construction'):
            continue
        if (r['item'] or '').lower() not in names:
            ck.error(f'approximation row names a missing item {r["item"]!r}')
        if r['record'] is not None and r['record'] not in numbers.get((r['item'] or '').lower(), []):
            ck.error(f'approximation row {r["item"]}/{r["bonus"]}: record {r["record"]} is not one of its records')
    behaviours = {r['bonus'] for r in rows if r['kind'] in ('behaviour', 'construction')}
    expected = {b[0] for b in BEHAVIOUR_ROWS} | ({CONSTRUCTION_ROW[0]} if construction_fallback(ctx) else set())
    if behaviours != expected:
        ck.error(f'behaviour rows {sorted(behaviours)} differ from the source-controlled list {sorted(expected)}')
    kinds = collections.Counter(r['kind'] for r in rows)
    ck.details['rows_by_kind'] = dict(kinds)
    for k in ('bonus-approx', 'noop-original', 'exact', 'behaviour', 'adapter'):
        ck.set('rows_' + k.replace('-', '_'), kinds.get(k, 0))
    if kinds.get('adapter'):
        ck.warn(f'{kinds["adapter"]} adapter rows (a PC mechanism is missing for them)')
