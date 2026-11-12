"""XML1 handler-requested loop actions mapped to the action XMen2.exe's same handler requests.

Some combat handlers pick their own continuation: at the end of a cycle they ask the current move for a chain by
action id (XML1 default.xbe 0x381f0, XMen2.exe 0x427c80) and take its result. The input that keeps the move going is
the same in both games, but the action id the handler asks for is not:

* ch_skating (Iceman's and Magma's ice / lava slide). XML1 0xda570 (vtable 0x3d7ad8 slot 6): unless the cycle's
  tag-100 powerusage exceeds the energy (then idle -> the end move), while the jump button (input bit 6, the bit
  ch_jump 0xde4a0 turns into action 4 `move`) is held and the cycle time is up (timer + 0.25 > actor+0x580) it
  requests action 4 `move`. XMen2.exe 0x4ec9e0 (vtable 0x69321c slot 6) is the same routine - jump bit 6, the same
  0.25 s window against actor+0x798, the move's affordability check (move vt+0xc 0x4f5fb0) - but requests action 0x1e
  `samepowerhold` (also when the move's own power button is held, 0x4fce10). XML2's Iceman power5 therefore chains
  samepowerhold -> power5; a converted XML1 slide that only names `move` gets no continuation and ends after one
  cycle whatever the player holds (b6live row 1).

The converter keeps XML1's `move` chain (XML2's generic transition 0x4fce50 may still resolve it, as XML1's 0xe7460
did) and adds the XML2 action with the same result, so holding jump keeps the slide going cycle after cycle while the
rank counter (only_looped counter require, fallback exit) and the energy allow, as in XML1.

ch_charge_move (Colossus's charge) also loops on `move` in XML1 (0xdaa00). XMen2.exe 0x4eced0 asks for `special`
only while the move's own power button is held and otherwise runs the generic transition, which resolves the `move`
chain while jump is held (live: the converted chargeforward keeps going until jump is released). Not mapped.

Engine dependency: XMen2.exe's held-jump request does not run the slide's exit (handler vt+0xc 0x4ecfb0, which
clears physical flag 4) the way XML1 0xda5f8 does before every request. When the request leaves the slide (the
counter-exhausted fallback with energy left) the flag stays set and ch_jump turns every later jump into `special`
(land at once: no slide, no jump attack) until the zone reloads. XML2 Fix must run that exit when the resolved
move is not the slide's own handler (SPEC_heroes, handler-requested loops).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

# XML1 handler -> (XML1 loop action, XMen2.exe loop action)
HANDLER_LOOP_ACTIONS = {
    'ch_skating': ('move', 'samepowerhold'),
}


def _moves(moves):
    return {(m.get('name') or '').lower(): m for m in moves}


def handler_of(move, by_name, seen=None):
    """the move's own handler or the one it inherits (lower case, '' when none)."""
    seen = set() if seen is None else seen
    h = move.get('handler')
    if h:
        return h.lower()
    parent = (move.get('inherit') or '').lower()
    if parent and parent in by_name and parent not in seen:
        seen.add(parent)
        return handler_of(by_name[parent], by_name, seen)
    return ''


def _chains(move):
    return [c for c in move if c.tag.lower() == 'chain']


def expected(moves):
    """[(move name, xml2 action, result)] that the style must carry: one per XML1 loop-action chain of a mapped
    handler's move."""
    by_name = _moves(moves)
    out = []
    for m in moves:
        pair = HANDLER_LOOP_ACTIONS.get(handler_of(m, by_name))
        if pair is None:
            continue
        x1, x2 = pair
        for c in _chains(m):
            if (c.get('action') or '').lower() == x1:
                out.append((m.get('name'), x2, c.get('result')))
    return out


def add_loop_actions(moves, report=None):
    """add the XMen2.exe loop action beside every XML1 loop-action chain of a mapped handler's move (in place);
    returns the [(move, action, result)] added."""
    by_name = _moves(moves)
    added = []
    for name, x2, result in expected(moves):
        m = by_name[(name or '').lower()]
        x1 = HANDLER_LOOP_ACTIONS[handler_of(m, by_name)][0]
        have = [c for c in _chains(m) if (c.get('action') or '').lower() == x2]
        if any(c.get('result') == result for c in have):
            continue
        if have:
            raise ValueError(f'{name}: chain {x2} -> {have[0].get("result")} conflicts with the XML1 loop to {result}')
        src = next(c for c in _chains(m) if (c.get('action') or '').lower() == x1 and c.get('result') == result)
        new = ET.Element(src.tag, {'action': x2, 'result': result})
        new.tail = src.tail
        m.insert(list(m).index(src) + 1, new)
        added.append((name, x2, result))
    if report is not None:
        report.setdefault('loop_actions', []).extend(f'{n}: chain {a} -> {r}' for n, a, r in added)
    return added


def problems(style):
    """serialized style check: every XML1 loop chain of a mapped handler has its XMen2.exe action beside it."""
    moves = style.findall('FightMove')
    errors = []
    by_name = _moves(moves)
    for name, x2, result in expected(moves):
        m = by_name[(name or '').lower()]
        if not any((c.get('action') or '').lower() == x2 and c.get('result') == result for c in _chains(m)):
            errors.append(f'{name}: {handler_of(m, by_name)} loop chain to {result} has no {x2} action '
                          f'(XMen2.exe requests {x2}, never {HANDLER_LOOP_ACTIONS[handler_of(m, by_name)][0]})')
    return errors
