"""xml1build.w2_limits - the data limits of the W2 save layout ([Limits] SaveLayout=w2; limits wave 2).

One place that turns the builder option ``--save-layout`` (``ctx.args.save_layout``; 'retail' by default) into the
limits the build's data is checked against:

  retail  the limits XMen2.exe has had all along, as the existing checks state them (25 mission files, 299
          objectives, 75 per act, a talent registry of 100 names in 9 files, 99 shared talents). Nothing else is
          checked: with W2 off the validator and the budgets behave exactly as before.
  w2      the descriptor lcsave.layout.W2 (limits-wave2.md section 2/3): 64 mission files, 1024 objectives, 127 per
          act, 256 registrations per talent pool (still 9 files), a talent multiplier of 200 (hero position < 200,
          shared < 199), 1024 item definitions / item instances / world slots, 4096 enhancement and attached
          records, at most 1024 placements per zone (the zone loader's stack arrays are not raised), and a
          zone-string table of 8191 names / 0x1ffff arena bytes shared by the (at most 8) resident zone records.

The numbers are read from the descriptor, not copied, so they cannot drift from the layout the converter and the
DLL use. check() is V67: it refuses data over a W2 limit when W2 is selected, and does nothing otherwise.

Counting rules (what the DLL's own counters count, `save layout` status line):
  definitions          distinct <item> names of Data/items
  enhancement records  every <enhancement> of Data/items (prefixes, suffixes, tr_item affixes, then the items);
                       attached records are the same records attached, so they cannot exceed this total - the
                       attached pool is checked against it. The runtime attach count itself is the DLL's counter.
  placements           every <inst> of a zone's Maps/*.XMLB, recursively (the C2 counting rule of limits-wave2, the
                       same count the DLL's zone-loader preflight makes)
  instances / world    placements of world items (an entity with classname inventoryent or an inventoryitem) in the
  slots                zones that can be resident together: the sum over the `resident` heaviest zones is an upper
                       bound on what the save manager can hold at once
  zone-string names    distinct <inst> names of the `resident` zones with the most of them (their bytes include a
                       terminating NUL)
"""
from __future__ import annotations

from typing import NamedTuple, Optional

from lcsave import layout as L

OPTION = 'save_layout'
W2_NAME = 'w2'
TALENT_FILES = 9                  # talent-file slots per zone: 9 in every layout (not an INI key; limits-wave2 step 8)


class Limits(NamedTuple):
    """one layout's limits; None = not checked by this layout's rows"""
    name: str
    mission_files: int
    objectives: int
    objectives_per_act: int
    talent_pool: int
    talent_files: int
    shared_talents: int            # the shared loader's exclusive upper bound (ids 0..cap-1)
    talent_positions: Optional[int] = None      # hero talent position < this (the talent multiplier M)
    definitions: Optional[int] = None
    enhancement_records: Optional[int] = None
    attached_enhancements: Optional[int] = None
    instances: Optional[int] = None
    world_slots: Optional[int] = None
    placements: Optional[int] = None            # per zone
    zone_names: Optional[int] = None            # usable names (slot 0 is reserved)
    zone_arena: Optional[int] = None            # usable arena bytes
    resident_zones: Optional[int] = None


# XMen2.exe's own: the constants validate.py / scripts.py / talent_budget.py / characters.py stated before W2
RETAIL_LIMITS = Limits('retail', mission_files=25, objectives=299, objectives_per_act=75, talent_pool=100,
                       talent_files=TALENT_FILES, shared_talents=99)

_W2 = L.W2
W2_LIMITS = Limits(W2_NAME, mission_files=_W2.objective_files, objectives=_W2.objectives,
                   objectives_per_act=_W2.objectives_per_act, talent_pool=_W2.talent_pool, talent_files=TALENT_FILES,
                   shared_talents=_W2.talent_multiplier - 1, talent_positions=_W2.talent_multiplier,
                   definitions=_W2.definitions, enhancement_records=_W2.enhancement_records,
                   attached_enhancements=_W2.attached_enhancements, instances=_W2.instances,
                   world_slots=_W2.world_slots, placements=_W2.loader_placements,
                   zone_names=_W2.zone_string_slots - 1, zone_arena=_W2.zone_arena - 1,
                   resident_zones=_W2.record_count)


def selected(args_or_ctx) -> bool:
    """True when the build was made with --save-layout w2 (a BuildContext, its args or a Validator)"""
    args = getattr(args_or_ctx, 'args', args_or_ctx)
    ctx = getattr(args_or_ctx, 'ctx', None)
    if ctx is not None and not hasattr(args, 'save_layout'):
        args = getattr(ctx, 'args', None)
    return str(getattr(args, OPTION, '') or '').strip().lower() == W2_NAME


def limits(args_or_ctx) -> Limits:
    """the limits the build is checked against (W2_LIMITS with --save-layout w2, else RETAIL_LIMITS)"""
    return W2_LIMITS if selected(args_or_ctx) else RETAIL_LIMITS


# ------------------------------------------------------------------------------------------------ pure counting
def _tag(el) -> str:
    return el.tag.lower() if isinstance(el.tag, str) else ''


def over(label: str, n: int, cap: Optional[int], where: str = '') -> Optional[str]:
    """the refusal text for `n` of `label` above `cap`, else None (also None when the layout has no such cap)"""
    if cap is None or n <= cap:
        return None
    return f'{where + ": " if where else ""}{n} {label} > {cap} (W2 limit)'


def item_counts(root) -> tuple:
    """(distinct item definition names, enhancement records) of one Data/items tree"""
    names, enhancements = set(), 0
    for el in root.iter():
        tag = _tag(el)
        if tag == 'item' and (el.get('name') or '').strip():
            names.add(el.get('name').strip().lower())
        elif tag == 'enhancement':
            enhancements += 1
    return len(names), enhancements


def placements(root) -> int:
    """the C2 counting rule: every <inst> of the zone's tree, recursively"""
    return sum(1 for el in root.iter() if _tag(el) == 'inst')


def world_item_classes(*roots) -> set:
    """lower names of the entity definitions (<entity>) of these trees that place a world item: classname
    inventoryent, or an inventoryitem attribute"""
    out = set()
    for root in roots:
        if root is None:
            continue
        for el in root.iter():
            if _tag(el) == 'entity' and (el.get('name') or '') and (
                    (el.get('classname') or '').strip().lower() == 'inventoryent' or (el.get('inventoryitem') or '').strip()):
                out.add(el.get('name').strip().lower())
    return out


def world_item_placements(root, shared_classes=()) -> int:
    """<inst> placements of a zone whose <entinst type=...> is a world-item definition (its own or `shared_classes`)"""
    items = world_item_classes(root) | {c.lower() for c in shared_classes}
    n = 0
    for group in root.iter():
        if _tag(group) == 'entinst' and (group.get('type') or '').strip().lower() in items:
            n += sum(1 for el in group.iter() if _tag(el) == 'inst')
    return n


def inst_names(root) -> set:
    """distinct <inst> names of a zone tree (what its state records intern in the zone-string table)"""
    return {(el.get('name') or '').strip() for el in root.iter() if _tag(el) == 'inst' and (el.get('name') or '').strip()}


def worst_resident(per_zone: dict, resident: int) -> list:
    """the `resident` zones with the largest value (name order breaks ties): [(zone, value)]"""
    return sorted(per_zone.items(), key=lambda kv: (-kv[1], kv[0]))[:resident]


def zone_string_demand(names_by_zone: dict, resident: int) -> tuple:
    """(distinct names, bytes incl. one NUL each, zones) of the union over the `resident` zones with the most
    distinct names: an upper bound on what the zone-string table can have to hold at once"""
    zones = [z for z, _ in worst_resident({z: len(n) for z, n in names_by_zone.items()}, resident)]
    names = set().union(*(names_by_zone[z] for z in zones)) if zones else set()
    return len(names), sum(len(n.encode('latin-1', 'replace')) + 1 for n in names), zones


def data_problems(lim: Limits, *, definitions=None, enhancements=None, zone_placements=None, world_items=None,
                  names=None) -> list:
    """the refusals for the data a build carries against `lim` (a layout without the cap checks nothing):
    definitions / enhancements: ints of the items table; zone_placements / world_items: {zone: count};
    names: (distinct names, bytes) of zone_string_demand. Pure: every caller passes what it counted."""
    out = []
    if definitions is not None:
        out.append(over('item definitions', definitions, lim.definitions, 'Data/items'))
    if enhancements is not None:
        out.append(over('enhancement records', enhancements, lim.enhancement_records, 'Data/items'))
        out.append(over('attached enhancement records', enhancements, lim.attached_enhancements, 'Data/items'))
    for zone, n in sorted((zone_placements or {}).items()):
        out.append(over('placements', n, lim.placements, zone))
    if world_items is not None and lim.resident_zones:
        total = sum(v for _, v in worst_resident(world_items, lim.resident_zones))
        out.append(over(f'world-item placements in the {lim.resident_zones} heaviest zones (item instances)', total,
                        lim.instances))
        out.append(over(f'world-item placements in the {lim.resident_zones} heaviest zones (world slots)', total,
                        lim.world_slots))
    if names is not None:
        out.append(over('distinct zone-string names', names[0], lim.zone_names))
        out.append(over('zone-string arena bytes', names[1], lim.zone_arena))
    return [m for m in out if m]


def talent_position_problems(lim: Limits, hero_files: dict, shared_count: int) -> list:
    """hero position < M and shared position < M - 1: `hero_files` {file: talent count} (positions are 0..count-1),
    `shared_count` the shared talents. Layouts without a multiplier check nothing here (TalentRegistry's own V44
    rows keep the retail pool and shared caps)."""
    out = []
    if lim.talent_positions is None:
        return out
    for rel, n in sorted(hero_files.items()):
        out.append(over('talent positions (position < M)', n, lim.talent_positions, rel))
    out.append(over('shared talent positions (position < M - 1)', shared_count, lim.talent_positions - 1,
                    'data/shared_talents'))
    return [m for m in out if m]


# ------------------------------------------------------------------------------------------------ V67
MAP_DIR = 'maps'
ITEM_FILES = ('data/items.xmlb', 'data/items.engb')
SHARED_ENTITY_FILES = ('data/common_ents.xmlb', 'data/common_ents.engb', 'data/item_ents.xmlb', 'data/item_ents.engb')


def check(v, ck) -> None:
    """V67 (limits wave 2): with --save-layout w2 the build's data against the W2 limits - item definitions,
    enhancement and attached records, per-zone placements, world items, zone-string names. The mission, objective and
    talent rows live in V44 and the missions check, which take their numbers from limits(). Without W2: a note."""
    lim = limits(v)
    ck.set('layout', lim.name)
    if lim.name != W2_NAME:
        ck.note('save layout retail: the W2 data limits are not checked')
        return
    definitions = enhancements = None
    for rel in ITEM_FILES:
        root = v.tree(rel)
        if root is not None:
            definitions, enhancements = item_counts(root)
            break
    if definitions is None:
        ck.error('Data/items missing or undecodable (the item definitions cannot be counted)')
    else:
        ck.set('item_definitions', definitions)
        ck.set('enhancement_records', enhancements)
    shared = [r for r in (v.tree(rel) for rel in SHARED_ENTITY_FILES) if r is not None]
    shared_classes = world_item_classes(*shared)
    zone_placements, world_items, names_by_zone = {}, {}, {}
    seen = set()
    for rel in sorted(v.idx.under(MAP_DIR)):
        if not rel.lower().endswith('.xmlb') or rel.lower() in seen:
            continue
        seen.add(rel.lower())
        root = v.tree(rel)
        if root is None:
            continue                      # V3 reports an undecodable file
        zone = rel[len(MAP_DIR) + 1:-5].lower()
        zone_placements[zone] = placements(root)
        world_items[zone] = world_item_placements(root, shared_classes)
        names_by_zone[zone] = inst_names(root)
    names = zone_string_demand(names_by_zone, lim.resident_zones)
    ck.set('zones_checked', len(zone_placements))
    ck.set('placements_max', max(zone_placements.values(), default=0))
    ck.set('world_items_resident', sum(x for _, x in worst_resident(world_items, lim.resident_zones)))
    ck.set('zone_string_names', names[0])
    ck.set('zone_string_bytes', names[1])
    for problem in data_problems(lim, definitions=definitions, enhancements=enhancements,
                                 zone_placements=zone_placements, world_items=world_items, names=names[:2]):
        ck.error(problem)
    ck.details['zone_string_zones'] = names[2]
