"""Read XMen2.exe's conversation-system state from the running game (read-only).

usage: conv_probe.py [--build DIR]         print the state once
       conv_probe.py json [--build DIR]    the same as one JSON line (for harness scripts)
--build: that build's game (several running: see current_zone.game_pid; without it, the one game or the one
serving XML2FIX_PIPE).

Why: a conversation that ignores Enter can be (a) the reply-menu cursor clamp - the menu builder sets
sel = visibleCount when sel >= visibleCount (0x45b5f1-0x45b5fc), so nothing is highlighted and accept selects
nothing until Up/Down - (b) a lost next-line lookup (file key at +0x4b0 overwritten with a stack address), or
(c) accept never registered (controller "pressed" bit 4, 0x5d4970). Fields and meanings from
research/heroes/conversation-speakers.md section 6 (static reads of the conversation singleton [0x717aac],
getter 0x4583f0, size 0x239dc). talker_handle / talker_name: the entity the current line talk-animates (SPEC 18.1).
"""
import ctypes
import ctypes.wintypes as w
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from current_zone import game_pid, pop_build, read_zone  # noqa: E402

CS_PTR = 0x00717AAC
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.restype = w.HANDLE


def _read(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    n = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n)) or n.value != size:
        return None
    return buf.raw


def probe(pid):
    h = k32.OpenProcess(0x0010 | 0x0400, False, pid)
    if not h:
        return {'error': 'cannot open the game process'}
    try:
        raw = _read(h, CS_PTR, 4)
        if raw is None:
            return {'error': 'cannot read [0x717aac]'}
        base = struct.unpack('<I', raw)[0]
        if not base:
            return {'conversation_system': None}

        def u8(off):
            b = _read(h, base + off, 1)
            return b[0] if b else None

        def i16(off):
            b = _read(h, base + off, 2)
            return struct.unpack('<h', b)[0] if b else None

        def u32(off):
            b = _read(h, base + off, 4)
            return struct.unpack('<I', b)[0] if b else None

        def f32(off):
            b = _read(h, base + off, 4)
            return struct.unpack('<f', b)[0] if b else None

        flags = u8(0x21b24)
        sel, count = i16(0x21b26), i16(0x21b28)
        slots = []
        for i in range(8):
            v = u32(0x4c0 + 4 * i)
            slots.append(None if v is None else (-1 if v == 0xFFFFFFFF else v))
        file_key = u32(0x4b0)
        out = {
            'base': hex(base),
            'active': bool(flags & 2) if flags is not None else None,
            'ending': bool(flags & 8) if flags is not None else None,
            'initialised': bool(flags & 16) if flags is not None else None,
            'flags': flags,
            'line_id': u32(0x4bc),
            'selected': sel,
            'visible_responses': count,
            'response_slots': slots,
            'pending_response': u32(0x239a0),
            'voice_handle': hex(u32(0x21b80) or 0),
            'accept_enable_time': f32(0x21b5c),
            'file_key_ptr': hex(file_key or 0),
            # the entity the current line talk-animates: 0x45bd1e looks the speaker key up in the entity-name table and,
            # found, plays anim 0xb6+rand on it and stores its handle here (0x45bddd); a previous talker gets anim 2
            # and 0 (0x45bda0). 0 / unchanged = the speaker names no entity (no talk animation). talker_name() below.
            'talker_handle': u32(0x2399c),
        }
        # (a): the cursor sits past the last visible response; (b): the file key points into a stack (below the
        # image and not a heap-looking address is only a hint - compare with a healthy conversation's value)
        out['diagnosis'] = []
        if sel is not None and count is not None and count > 0 and sel >= count:
            out['diagnosis'].append('(a) cursor clamp: press Up/Down, then Enter')
        return out
    finally:
        k32.CloseHandle(h)


ENTITY_TABLE = 0x00778B70     # 0x4c7f20: the entity table; vt+8 0x4c6f20 = by name, vt+0xc 0x4c6c20 = by handle
STRING_POOL = 0x00A2C440      # 0x602280: interned names (0x41ab70 interns, 0x41abd8 reads them back)


def talker_name(pid, handle):
    """The entity name(s) that map to `handle` in XMen2.exe's entity-name tree (SPEC 18.1: who the line talk-animates):
    tree at ENTITY_TABLE+0xc44 (0x5ab7d0: node i = +0x10 + i*16 {left, right, key}), key = interned name id
    (0x8000000 | index; the text at STRING_POOL + 0x4008 + [STRING_POOL + 4 + index*4]), node i's handle =
    [ENTITY_TABLE + 0x248c + ([ENTITY_TABLE+0xc44+0x1444 + i*4] & [ENTITY_TABLE+0x34c4]) * 8]. [] if none."""
    if not handle:
        return []
    h = k32.OpenProcess(0x0010 | 0x0400, False, pid)
    if not h:
        return []
    try:
        n = 4096
        nodes = _read(h, ENTITY_TABLE + 0xc44 + 0x10, n * 16)
        vals = _read(h, ENTITY_TABLE + 0xc44 + 0x1444, n * 4)
        mask = _read(h, ENTITY_TABLE + 0x34c4, 4)
        if not nodes or not vals or not mask:
            return []
        mask = struct.unpack('<I', mask)[0]
        out = []
        for i in range(n):
            key = struct.unpack_from('<I', nodes, i * 16 + 8)[0]
            if key == 0x3fffffff or not key & 0x8000000:
                continue
            v = struct.unpack_from('<I', vals, i * 4)[0] & mask
            hb = _read(h, ENTITY_TABLE + 0x248c + v * 8, 4)
            if not hb or struct.unpack('<I', hb)[0] != handle:
                continue
            ob = _read(h, STRING_POOL + 4 + (key & 0xffffff) * 4, 4)
            txt = _read(h, STRING_POOL + 0x4008 + struct.unpack('<I', ob)[0], 64) if ob else None
            if txt:
                out.append(txt.split(b'\0', 1)[0].decode('latin-1'))
        return out
    finally:
        k32.CloseHandle(h)


if __name__ == '__main__':
    args = sys.argv[1:]
    pid = game_pid(pop_build(args))
    if not pid:
        sys.exit('game not running')
    state = probe(pid)
    state['talker_name'] = talker_name(pid, state.get('talker_handle'))
    state['zone'] = read_zone(pid)
    if args and args[0] == 'json':
        print(json.dumps(state))
    else:
        for k, v in state.items():
            print(f'{k:20} {v}')
