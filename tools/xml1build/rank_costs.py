"""xml1build.rank_costs - X-Men Legends 1's per-rank skill costs (issue #35) kept in the hero talent files.

In the first game a talent rank has a cost: `<level cost="2">` on the rank's level (the ranks that open a new form
of a power: an Xtreme power's rank, the boost's 1/4/7, the attacks' 6/11 and the second power's 1). default.xbe keeps
up to three (rank, cost) pairs per talent (parser 0xb4250, byte = rank index | cost << 5) and charges, refunds and
greys by them (CTalent vt+0x34 = 0xb3ad0; the skills menu 0x16c800 / 0x169200). heroes.py copies `cost` verbatim onto
the converted level; XMen2.exe ignores it unless xml2-fix's [Game] RankCosts=1 is set (fix_ini.RANK_COSTS), which then
reads the level that 0x4bdea0 finds for the rank - the n-th rank's level counted by the levels' `count`.

The check (heroes validation V-H16): every cost of the XML1 source sits on the same rank of the built talent, every
level up to it covers exactly one rank (count="1"; otherwise the engine's rank -> level walk lands elsewhere), the
value is one the fix honours (1..7), no built level carries a cost the source does not have, and no talent has more
than the first game's 3 costed ranks (a level without `count` covers one rank, as 0x4bdea0 reads it)."""
from __future__ import annotations

COST_MIN, COST_MAX = 1, 7            # xml2-fix rank_costs_rules::parse_cost; XML1 keeps 3 bits
COSTS_PER_TALENT = 3                 # default.xbe 0xb4250 keeps 3 (rank, cost) pairs (cmp [esi+8],3); a 4th costs 1 there


def _tag(e):
    return (e.tag or '').lower()


def _levels(talent):
    return [c for c in talent if _tag(c) == 'level']


def _attr(e, key):
    for k, v in e.attrib.items():
        if k.lower() == key:
            return v
    return None


def source_costs(stats):
    """{talent name (lower): {rank: cost text}} of an XML1 <stats> element's talents with at least one cost."""
    out = {}
    for t in stats.iter():
        if _tag(t) != 'talent':
            continue
        costs = {i + 1: _attr(lv, 'cost') for i, lv in enumerate(_levels(t)) if _attr(lv, 'cost')}
        if costs:
            out[(_attr(t, 'name') or '').lower()] = costs
    return out


def built_levels(root):
    """{talent name (lower): [(cost text or None, count text or None) per <level>]} of a built talent file."""
    out = {}
    for t in root.iter('talent'):
        out[(t.get('name') or '').lower()] = [(lv.get('cost'), lv.get('count')) for lv in _levels(t)]
    return out


def problems(source, built, where):
    """V-H16 for one hero file: messages for every cost the build lost, moved, mangled or invented."""
    out = []
    for name in sorted(source):
        if len(source[name]) > COSTS_PER_TALENT:
            out.append(f'{where}: {name} has {len(source[name])} costed ranks in XML1; the first game keeps only '
                       f'{COSTS_PER_TALENT} (0xb4250), the fix would honour all')
        levels = built.get(name)
        if levels is None:
            out.append(f'{where}: {name} has XML1 rank costs {source[name]} but no built talent')
            continue
        for rank, cost in sorted(source[name].items()):
            if rank > len(levels):
                out.append(f'{where}: {name} rank {rank} costs {cost} in XML1; the built talent has {len(levels)} levels')
                continue
            if levels[rank - 1][0] != cost:
                out.append(f'{where}: {name} rank {rank} costs {cost} in XML1, {levels[rank - 1][0]!r} in the build')
            if any((c if c is not None else '1') != '1' for _, c in levels[:rank]):   # absent count = 1 (0x4bdea0)
                out.append(f'{where}: {name} rank {rank}: a level up to it covers more or fewer ranks than one '
                           f'(count {[c for _, c in levels[:rank]]}), so the engine prices another rank')
    for name, levels in sorted(built.items()):
        for i, (cost, _) in enumerate(levels):
            if cost is None:
                continue
            if source.get(name, {}).get(i + 1) != cost:
                out.append(f'{where}: {name} rank {i + 1} carries cost {cost!r} that XML1 does not')
            if not (cost.isdigit() and COST_MIN <= int(cost) <= COST_MAX):
                out.append(f'{where}: {name} rank {i + 1} cost {cost!r} is outside {COST_MIN}..{COST_MAX} (the fix charges 1)')
    return out


def costed_ranks(built):
    """How many ranks of a built file carry a cost."""
    return sum(1 for levels in built.values() for cost, _ in levels if cost is not None)
