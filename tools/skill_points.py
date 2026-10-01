"""Read every hero's unspent skill and attribute points from a running XMen2.exe (read only: ReadProcessMemory).

usage: skill_points.py [--build DIR]     one line per herostat hero: name, level, unspent skill points, unspent
                                         attribute points, levels not yet processed (xpexempt heroes marked)
--build: that build's game (several running: see current_zone.game_pid; without it, the one game or the one serving
XML2FIX_PIPE).

What XMen2.exe's "points to spend" test (0x4b7b00) reads (SPEC 32): the two words of the saved block at CStats+4 -
the unspent skill points at block+0x14 (CStats+0x18, read by 0x544a30, written by 0x43a5b0) and the unspent attribute
points at block+0x16 (CStats+0x1a) - and the levels the hero hasn't been given their points for yet: the level byte
CStats+0x1c past the XP object's processed count (the object at CStats+0xc0, its byte +0x3c, vt+0x14 = 0x5f5ff0).
The registry walk is tools/hero_xp.py's.
"""
import struct
import sys

from current_zone import game_pid, pop_build
from hero_xp import FLAGS, HANDLE_MASK, LEVEL, NAME, RECORDS, RECORD_COUNT, RECORD_SIZE, REGISTRY_POINTER, STATS_SIZE, TEAM, TEAM_HERO, XP_OBJECT, k32, read, u32

SKILL_POINTS, ATTRIBUTE_POINTS, PROCESSED = 0x18, 0x1A, 0x3C


def heroes(pid):
    """[(name, level, skill points, attribute points, pending levels, xpexempt)] for every herostat hero."""
    h = k32.OpenProcess(0x0010 | 0x0400, False, pid)
    if not h:
        raise OSError(f'cannot open process {pid}')
    try:
        registry = u32(h, REGISTRY_POINTER)
        if not registry:
            return []
        count, mask = u32(h, registry + RECORD_COUNT), u32(h, registry + HANDLE_MASK)
        out = []
        for i in range(min(count, 4096)):
            record = read(h, registry + RECORDS + i * RECORD_SIZE, RECORD_SIZE)
            handle = struct.unpack_from('<I', record, 0)[0]
            if not (record[8] & 1) or not handle:
                continue
            stats = registry + 4 + (handle & mask) * STATS_SIZE
            if u32(h, stats + TEAM) != TEAM_HERO:
                continue
            name = read(h, stats + NAME, 0x20).split(b'\0', 1)[0].decode('latin-1')
            level = read(h, stats + LEVEL, 1)[0]
            skill = struct.unpack('<h', read(h, stats + SKILL_POINTS, 2))[0]
            attr = struct.unpack('<h', read(h, stats + ATTRIBUTE_POINTS, 2))[0]
            exempt = bool(read(h, stats + FLAGS, 1)[0] & 0x20)
            xp_object = u32(h, stats + XP_OBJECT)
            processed = read(h, xp_object + PROCESSED, 1)[0] if xp_object else None
            pending = (level - processed) if processed is not None else None
            out.append((name, level, skill, attr, pending, exempt))
        return out
    finally:
        k32.CloseHandle(h)


def main(argv):
    build = pop_build(argv)
    pid = game_pid(build)
    if not pid:
        sys.exit('no XMen2.exe running' + (f' from {build}' if build else ''))
    rows = heroes(pid)
    if not rows:
        print('no heroes loaded yet')
    for name, level, skill, attr, pending, exempt in rows:
        print(f'{name:16} level {level:3}  skill points {skill:3}  attribute points {attr:3}  pending levels {pending!s:>4}'
              f'{"  (xpexempt)" if exempt else ""}')


if __name__ == '__main__':
    main(sys.argv[1:])
