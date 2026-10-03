"""SPEC 41: player starts that land the party outside the walkable area on XMen2.exe, moved to a tested spot.

mansion/man8/subbasement8 (issue #28): its default start player_start01 (732.275 1535.96 24.0228) - where every load
without a matching prevzone arrives, e.g. the portal after the Shadow King side mission - puts the hero behind the war
room's console desk, between the desk and the map wall; walking towards the room drops her into the void. The same
room's default start in subbasement7 (701.376 1674.6 24) is in the room proper; in subbasement8 a hero placed there
walks to the computer and the stairs (2026-10-02 harness check, issue #28). Each fix names the position it expects to
replace, so a different source fails closed instead of moving the wrong thing; a second run is a no-op.
"""
import re

# zone ref -> {start instance name: (expected XML1 pos, tested pos)}
START_FIXES = {
    'maps/mansion/man8/subbasement8': {'player_start01': ('732.275 1535.96 24.0228', '701.376 1674.6 24')},
}


def _ref(rel):
    value = str(rel).replace('\\', '/').lower()
    return re.sub(r'\.(xml|eng|fre|ger|engb|xmlb|ita|spa)$', '', value)


def fix_player_starts(root, rel, table=None):
    """Move the tabled start instances of this zone; returns the number moved."""
    fixes = (START_FIXES if table is None else table).get(_ref(rel))
    if not fixes or root is None:
        return 0
    moved = 0
    for name, (expected, tested) in fixes.items():
        insts = [i for g in root.iter('entinst') for i in g if i.tag == 'inst' and i.get('name') == name]
        if len(insts) != 1:
            raise ValueError(f'{rel}: start fix {name}: expected one instance, found {len(insts)}')
        pos = insts[0].get('pos', '')
        if pos == tested:
            continue
        if pos.split() != expected.split():
            raise ValueError(f'{rel}: start fix {name}: expected pos {expected!r}, found {pos!r}')
        insts[0].set('pos', tested)
        moved += 1
    return moved
