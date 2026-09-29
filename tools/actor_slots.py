"""Read XMen2.exe's actor-table use (skins + animation databases resident, cap 40) from the running game.

usage: actor_slots.py [--build DIR]                     print zone + slots/cap once
       actor_slots.py watch <csv> [secs] [--build DIR]  log every change (zone, slots) until secs pass
--build: that build's game only (several running: see current_zone.game_pid; without it, the one game or the one
serving XML2FIX_PIPE). watch follows the game across restarts (a tour's relaunches).

The actor manager is the singleton object at 0x7b05e8 (getter 0x56b8e0: `mov ecx, 0x7b05e8`); its used-slot
count is this+0x73c4 = 0x7b79ac, compared with 0x28 at 0x56b2c3 (`cmp dword ptr [ebx+0x73c4], 0x28 / jge` ->
the load is refused and returns NULL; see SPEC section 14). Reading it per zone shows whether slots leak across
zone loads (the mansion4_1 tour crash only happened after ~60 zones in one session).

With xml2-fix's [Limits] ActorSlots the table lives in a block of the DLL instead; xml2-fix.log (next to the
game, rewritten every launch) says where: "limits: actor table raised from 40 to N slots ... live count at
0x...". That address and cap are used when the log of the running game has the line, 0x7b79ac / 40 otherwise.
"""
import ctypes
import ctypes.wintypes as w
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from current_zone import game_pid, pop_build, ZONE_ADDR  # noqa: E402

SLOTS_ADDR = 0x007B79AC
SLOTS_CAP = 40
RAISED = re.compile(r'limits: actor table raised from 40 to (\d+) slots.* live count at (0x[0-9A-Fa-f]+)')
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.restype = w.HANDLE


def game_folder(pid):
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = w.DWORD(len(buf))
        if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return None
        return os.path.dirname(buf.value)
    finally:
        k32.CloseHandle(h)


def slots_counter(pid):
    """(address, cap) of the live count: xml2-fix's relocated table if its log says so, else the game's own."""
    folder = game_folder(pid)
    try:
        with open(os.path.join(folder, 'xml2-fix.log'), encoding='latin-1') as f:
            for line in f:
                m = RAISED.search(line)
                if m:
                    return int(m.group(2), 16), int(m.group(1))
    except (OSError, TypeError):
        pass
    return SLOTS_ADDR, SLOTS_CAP


def read(pid, addr=SLOTS_ADDR):
    h = k32.OpenProcess(0x0010 | 0x0400, False, pid)
    if not h:
        return None, None
    try:
        n = ctypes.c_size_t()
        buf = ctypes.create_string_buffer(128)
        zone = None
        if k32.ReadProcessMemory(h, ctypes.c_void_p(ZONE_ADDR), buf, 128, ctypes.byref(n)):
            zone = buf.raw.split(b'\0')[0].decode('latin-1')
        val = ctypes.c_int32()
        slots = None
        if k32.ReadProcessMemory(h, ctypes.c_void_p(addr), ctypes.byref(val), 4, ctypes.byref(n)):
            slots = val.value
        return zone, slots
    finally:
        k32.CloseHandle(h)


def watch(csv, seconds, build=None):
    t0, last, pid, addr = time.time(), None, None, SLOTS_ADDR
    with open(csv, 'a', encoding='utf-8') as f:
        if f.tell() == 0:
            f.write('time,zone,slots\n')
        while time.time() - t0 < seconds:
            if not pid:
                pid = game_pid(build)
                if not pid:
                    time.sleep(2)
                    continue
                addr = slots_counter(pid)[0]
            zone, slots = read(pid, addr)
            if zone is None and slots is None:
                pid = None
                time.sleep(1)
                continue
            if (zone, slots) != last:
                f.write(f'{time.strftime("%H:%M:%S")},{zone},{slots}\n')
                f.flush()
                last = (zone, slots)
            time.sleep(1)


if __name__ == '__main__':
    args = sys.argv[1:]
    build = pop_build(args)
    if len(args) > 1 and args[0] == 'watch':
        watch(args[1], float(args[2]) if len(args) > 2 else 3600, build)
    else:
        pid = game_pid(build)
        if pid:
            addr, cap = slots_counter(pid)
            zone, slots = read(pid, addr)
            print(pid, zone, f'{slots}/{cap}')
        else:
            print(None, None, None)
