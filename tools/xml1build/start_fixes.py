"""SPEC 41: player starts that land the party outside the walkable area on XMen2.exe, moved to a tested spot.

mansion/man8/subbasement8 (issue #28): its default start player_start01 (732.275 1535.96 24.0228) - where every load
without a matching prevzone arrives, e.g. the portal after the Shadow King side mission - puts the hero behind the war
room's console desk, between the desk and the map wall; walking towards the room drops her into the void. The same
room's default start in subbasement7 (701.376 1674.6 24) is in the room proper; in subbasement8 a hero placed there
walks to the computer and the stairs (2026-10-02 harness check, issue #28). Each fix names the position it expects to
replace, so a different source fails closed instead of moving the wrong thing; a second run is a no-op.

SPEC 41.1, the same table for a placed NPC: mansion/man1a/mansion1a_1's sp_profx01 (Professor X at his desk, issue #54).
XMen2.exe resolves that spawn point to a different walk cell than the first game does: the original Xbox (xemu, the
first visit's 1_2_1_1 conversation) seats him at (2938.85 1540 1.15), behind the desk with a clear gap; the port seated
him at (2899.4 1580), inside the desk, on every fresh load (3/3). Spawn points tried on XMen2.exe: (2940 1540) ->
(2939.4 1580), (2940 1520) -> (2939.4 1500), (2940 1500) -> (2939.4 1540) on 3/3 fresh loads - the original's seat.
The same one-cell difference seats him at (859.7 1899.9) in subbasement1a (original 819.93 1899.80) and (2260.6 1780) in
subbasement2 (original 2260 1740, beside the war room console); the tabled spawn points land on the original's seats.
"""
import re

# zone ref -> {start instance name: (expected XML1 pos, tested pos)}
START_FIXES = {
    'maps/mansion/man8/subbasement8': {'player_start01': ('732.275 1535.96 24.0228', '701.376 1674.6 24')},
    # SPEC 41.1: the spawn point XMen2.exe resolves to the original Xbox's seat behind Xavier's desk
    'maps/mansion/man1a/mansion1a_1': {'sp_profx01': ('2925.34 1558.67 0', '2940 1500 0')},
    # SPEC 41.1: the same correction where the original seats him one walk cell away from where XMen2.exe does
    'maps/mansion/man1a/subbasement1a': {'sp_profx01': ('838.602 1895.28 23.3504', '798.602 1895.28 23.3504')},
    'maps/mansion/man2/subbasement2': {'sp_profx01': ('2266.03 1742.65 6.11299', '2266.03 1702.65 6.11299'),
                                       'profx_a': ('2266.03 1742.65 6.11299', '2266.03 1702.65 6.11299')},
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
