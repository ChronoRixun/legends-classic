"""Restart HAARP wall loops at their scripted destination (SPEC 45)."""
import re

SCRIPTS = frozenset('haarp/ext/create_firewall' + suffix for suffix in ('1', '1b', '2', '3', '4', '6'))
_ACT = re.compile(r'''^\s*act\s*\(\s*["'](?P<wall>fire_wall\d+[a-z]?)["']\s*,\s*["'](?P=wall)["']\s*\)\s*$''')
_MOVE = re.compile(r'''^(?P<indent>\s*)copyOriginAndAngles\s*\(\s*["'](?P<wall>fire_wall\d+[a-z]?)["']\s*,\s*["'][A-Za-z_]\w*["']\s*\)\s*$''')


def rewrite(ref, lines):
    if ref not in SCRIPTS:
        return lines
    out = []
    i = found = 0
    while i < len(lines):
        move = _MOVE.fullmatch(lines[i])
        if not move:
            out.append(lines[i]); i += 1
            continue
        wall, indent = move['wall'], move['indent']
        hide = f'{indent}setInvisible("{wall}", "TRUE" )'
        show = f'{indent}setInvisible("{wall}", "FALSE" )'
        found += 1
        previous = _ACT.fullmatch(out[-1]) if out else None
        # Preserve an authored act before the move; move-only scripts stay so.
        already_hidden = (len(out) >= 2 and previous and out[-2] == hide) or (out and out[-1] == hide)
        if already_hidden:
            following_act = _ACT.fullmatch(lines[i + 2]) if i + 2 < len(lines) else None
            if i + 1 >= len(lines) or lines[i + 1] != show or following_act:
                raise ValueError(f'{ref}: incomplete or reordered wall visibility block')
            if previous and previous['wall'] != wall:
                raise ValueError(f'{ref}: activation targets a different wall')
            out.extend(lines[i:i + 2]); i += 2
            continue
        activation = []
        if previous:
            if previous['wall'] != wall:
                raise ValueError(f'{ref}: activation targets a different wall')
            activation.append(out.pop())
        out.extend([hide, *activation, lines[i], show])
        i += 1
    if found != 1:
        raise ValueError(f'{ref}: expected exactly one wall placement')
    return out
