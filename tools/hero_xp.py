"""Read every hero's level and XP from a running XMen2.exe (read only: ReadProcessMemory, nothing is written).

usage: hero_xp.py [--build DIR]     one line per herostat hero: name, level, XP (xpexempt heroes marked)
--build: that build's game (several running: see current_zone.game_pid; without it, the one game or the one serving
XML2FIX_PIPE).

The HUD and the stats screen show a hero's level and an XP bar, never the XP itself; this is how the in-game checks
of SPEC 23 (xml2-fix [Game] XPCurve=xml1) read it, e.g. before and after a kill: the benched hero's XP rises by half
the kill's XP. Where it is (XMen2.exe retail, research/heroes/levels.md): the hero registry at [0x71770c] (its getter
0x44b8f0); its records at +0x9b38, 0x1c bytes each, [+0xbba8] of them, in use when byte +8 has bit 0; a record's
handle at +0; its stats at registry + 4 + (handle & [registry + 0x9b20]) * 0x4f8 (the roster award 0x449fe0 walks
them the same way); a hero's stats have team 0x1d at +0x2a0, the level byte at +0x1c, the name at +0x150, xpexempt
= bit 0x20 of +0x2ad, and the XP at +0x38 of the object +0xc0 points to (vtable 0x685294: get 0x551370, set 0x5383d0).
"""
import ctypes
import ctypes.wintypes as w
import struct
import sys

from current_zone import game_pid, pop_build

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.restype = w.HANDLE

REGISTRY_POINTER = 0x71770C
RECORDS, RECORD_SIZE, RECORD_COUNT, HANDLE_MASK, STATS_SIZE = 0x9B38, 0x1C, 0xBBA8, 0x9B20, 0x4F8
TEAM, TEAM_HERO, LEVEL, NAME, FLAGS, XP_OBJECT, XP = 0x2A0, 0x1D, 0x1C, 0x150, 0x2AD, 0xC0, 0x38


def read(h, address, size):
    buf = ctypes.create_string_buffer(size)
    n = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(address), buf, size, ctypes.byref(n)) or n.value != size:
        raise OSError(f'cannot read {size} bytes at 0x{address:08x}')
    return buf.raw


def u32(h, address):
    return struct.unpack('<I', read(h, address, 4))[0]


def heroes(pid):
    """[(name, level, xp or None, xpexempt)] for every herostat hero in the registry."""
    h = k32.OpenProcess(0x0010 | 0x0400, False, pid)  # PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
    if not h:
        raise OSError(f'cannot open process {pid} (error {ctypes.get_last_error()})')
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
            name = read(h, stats + NAME, 64).split(b'\0')[0].decode('latin-1')
            level = read(h, stats + LEVEL, 1)[0]
            exempt = bool(read(h, stats + FLAGS, 1)[0] & 0x20)
            xp_object = u32(h, stats + XP_OBJECT)
            out.append((name, level, u32(h, xp_object + XP) if xp_object else None, exempt))
        return out
    finally:
        k32.CloseHandle(h)


def main():
    pid = game_pid(pop_build(sys.argv[1:]))
    if not pid:
        sys.exit('XMen2.exe is not running')
    rows = heroes(pid)
    if not rows:
        print('no hero registry yet (the game is still starting?)')
    for name, level, xp, exempt in rows:
        print(f'{name:16} level {level:3}  xp {xp if xp is not None else "-":>11}{"  (xpexempt)" if exempt else ""}')


if __name__ == '__main__':
    main()
