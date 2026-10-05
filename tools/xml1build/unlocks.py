"""xml1build.unlocks - XML1's per-mission hero unlocks (issue #55).

XML1 (default.xbe, image base 0x10000) unlocks heroes mainly through one cumulative table, applied at every mission
start:
  * data/missions/missions.xml gives every <MISSION> a charunlock milestone (parser 0x858d2, stored per mission
    index at 0x8592a in the array 0x49e898).
  * The mission loader 0x86560 calls 0x84fc0 unconditionally (0x866fb) on every console 'beginmission' (0x18da90:
    New Game's 'beginmission alison', the script beginMission 0x9a770 and beginSideMission 0x9a4f0 -> 0x18dd70),
    before the party builder 0x18d6d0.
  * 0x84fc0 walks the table at 0x44e2e8, 8-byte rows {milestone label, hero}, ended by a NULL label: it finds the
    FIRST row whose label equals the mission's milestone (case-insensitive, 0x343612 = _stricmp) and unlocks the
    hero of that row and of every row before it (registry vt+0x2c = 0x552a0: the campaign bit and the save's
    unlock list). A milestone no row carries unlocks nobody; unlabelled rows carry the empty label, so an empty
    milestone matches the first of them.
  * Loading a save never re-applies it (the save keeps its own unlock list); resetgame relocks everyone.

The port reads both from the player's own copy: the milestones from the prepared missions.xml, the table from the
prepared default.xbe, after checking that the code that walks the table is the code above (WALK_SHA1, and that the
mission loader calls it). Another executable fails the build (scripts module error) instead of guessing. Nothing
from the table is written into this repository; the tests build invented tables in memory.

Pure except read_xbe_table (read-only)."""
from __future__ import annotations

import hashlib
import struct

TABLE_VA = 0x44e2e8                 # {char *milestone, char *hero} rows, NULL milestone ends the table
WALK_VA, WALK_LEN = 0x84fc0, 0xb3   # the function that walks it (ends with ret 4 at 0x85070)
WALK_SHA1 = 'c7bbefe53ff555e43ba6bd49aa025ca920dc135e'   # of those bytes in the X-Men Legends (Xbox) default.xbe
CALLER_VA = 0x866fb                 # the mission loader's call to WALK_VA
MAX_ROWS = 256                      # the table has 17 rows; a longer run means the address is wrong
MAX_NAME = 64


class UnlockTableError(ValueError):
    """default.xbe does not hold the unlock table this module knows how to read."""


def _cstr(rd, va):
    raw = rd(va, MAX_NAME)
    if raw is None:
        # near the end of a section: shorter reads
        for n in range(MAX_NAME - 1, 0, -1):
            raw = rd(va, n)
            if raw is not None:
                break
    if raw is None or b'\0' not in raw:
        raise UnlockTableError(f'no string at 0x{va:06x}')
    s = raw[:raw.index(b'\0')]
    if any(c < 0x20 or c > 0x7e for c in s):
        raise UnlockTableError(f'string at 0x{va:06x} is not ASCII text')
    return s.decode('ascii')


def read_table(rd, walk_sha1=WALK_SHA1):
    """-> [(milestone label, hero)] in table order. rd(va, n) -> bytes or None (npc_values._xbe_reader). Raises
    UnlockTableError when the walking code differs from the known one, the loader does not call it, or the table
    cannot be read."""
    code = rd(WALK_VA, WALK_LEN)
    if code is None or hashlib.sha1(code).hexdigest() != walk_sha1:
        raise UnlockTableError(f'the code at 0x{WALK_VA:06x} that applies the unlock table is not the known '
                               f'X-Men Legends (Xbox) code')
    call = rd(CALLER_VA, 5)
    if call is None or call[0] != 0xe8 or (CALLER_VA + 5 + struct.unpack('<i', call[1:])[0]) & 0xffffffff != WALK_VA:
        raise UnlockTableError(f'the mission loader does not call 0x{WALK_VA:06x} at 0x{CALLER_VA:06x}')
    rows = []
    for i in range(MAX_ROWS):
        raw = rd(TABLE_VA + 8 * i, 8)
        if raw is None:
            raise UnlockTableError(f'unlock table row {i} at 0x{TABLE_VA + 8 * i:06x} is outside the image')
        label, hero = struct.unpack('<II', raw)
        if label == 0:
            return rows
        rows.append((_cstr(rd, label), _cstr(rd, hero) if hero else ''))
    raise UnlockTableError(f'unlock table at 0x{TABLE_VA:06x} has no end within {MAX_ROWS} rows')


def read_xbe_table(xbe_path):
    """read_table over a default.xbe file."""
    from .npc_values import _xbe_reader          # noqa: WPS433 - the XBE section reader verify_xbe uses
    try:
        rd = _xbe_reader(xbe_path)
    except (OSError, ValueError, struct.error) as e:
        raise UnlockTableError(f'{xbe_path}: {e}') from e
    return read_table(rd)


def cumulative(rows, milestone):
    """[hero] 0x84fc0 unlocks for `milestone`: the heroes of the first row whose label equals it (ignoring case) and
    of every row before it, in table order (the exe walks them backwards; the order does not matter); [] when no
    row carries it. Empty hero names (the table's padding row) are dropped."""
    m = (milestone or '').lower()
    for i, (label, _hero) in enumerate(rows):
        if label.lower() == m:
            return [h.lower() for _, h in rows[:i + 1] if h]
    return []


def group(rows, milestone):
    """[hero] of the rows cumulative() adds at `milestone` beyond the previous labelled row (the milestone's own
    group: 'mansion1' -> the rows after 'start' up to and including 'mansion1'); [] when no row carries it."""
    m = (milestone or '').lower()
    for i, (label, _hero) in enumerate(rows):
        if label.lower() == m:
            prev = max((j for j in range(i) if rows[j][0]), default=-1) if m else -1
            return [h.lower() for _, h in rows[prev + 1:i + 1] if h]
    return []


def mission_milestones(missions_root):
    """({lower mission name: milestone}, [mission without a charunlock]) from missions.xml's root element (attribute
    names lowercased, as common.parse_x1_text gives them). The first entry of a name wins, as the exe's index
    lookup does."""
    out, missing = {}, []
    for el in missions_root.iter():
        if el.tag.lower() != 'mission':
            continue
        name = (el.get('name') or '').strip().lower()
        if not name or name in out:
            continue
        if el.get('charunlock') is None:
            missing.append(name)
            continue
        out[name] = el.get('charunlock').strip()
    return out, missing


def mission_unlocks(milestones, rows, playable, fn=None):
    """({mission: (hero, ...)}, {mission: (dropped hero, ...)}): the cumulative set (fn=group: the milestone's own
    group) of each mission's milestone, split into the playable heroes of this build (`playable`, lowercase) and the
    rest (XML1's NPC-only rows)."""
    fn = fn or cumulative
    keep, drop = {}, {}
    for m, ms in sorted(milestones.items()):
        heroes = fn(rows, ms)
        keep[m] = tuple(h for h in heroes if h in playable)
        gone = tuple(h for h in heroes if h not in playable)
        if gone:
            drop[m] = gone
    return keep, drop
