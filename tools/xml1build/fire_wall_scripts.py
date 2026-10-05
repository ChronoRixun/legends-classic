"""Restart relocated harm loops (SPEC 45 and SPEC 51)."""
import collections
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


def loop_targets(root):
    """Named instances -> qualifying/nonqualifying definitions in one source map.

    Keep negative facts too: a reused name must not make an unrelated entity
    visible in another map sharing the script directory.
    """
    from .x1schema import CLASS_REMAP
    definitions = {(e.get('name') or '').lower(): e for e in root.iter('entity')}
    targets = collections.defaultdict(set)
    for block in root.iter('entinst'):
        entity = definitions.get((block.get('type') or '').lower())
        attrs = entity.attrib if entity is not None else {}
        cls = (attrs.get('classname') or '').strip().lower()
        qualifies = (CLASS_REMAP.get(cls, cls) == 'affectableharment'
                     and bool((attrs.get('loopfx') or '').strip())
                     and (attrs.get('loopfxstarton') or '').strip().lower() == 'true'
                     and (attrs.get('smartfire') or '').strip().lower() in ('', 'false', '0')
                     and (attrs.get('invisible') or '').strip().lower() not in ('true', '1'))
        for inst in block:
            if inst.get('name'):
                targets[inst.get('name').lower()].add(qualifies)
    return dict(targets)


def relocation_plan(ctx):
    """Source-derived targets grouped by the maps/scripts directory namespace."""
    from . import common as C
    plan = collections.defaultdict(lambda: collections.defaultdict(set))
    for rel in sorted(ctx.x1_rels('maps/')):
        if not rel.lower().endswith(('.eng', '.xml')):
            continue
        root = ctx.read_x1_xml(rel)
        if root is None:
            continue
        folder = C.norm(rel).rsplit('/', 1)[0][len('maps/'):]
        for name, states in loop_targets(root).items():
            plan[folder][name].update(states)
    return {folder: dict(targets) for folder, targets in plan.items()}


_LOOP_MOVE = re.compile(r'''^(?P<indent>\s*)copyOriginAndAngles\s*\(\s*["'](?P<target>[^"']+)["']\s*,\s*["'][^"']+["']\s*\)\s*$''', re.I)
_LOOP_ACT = re.compile(r'''^\s*act\s*\(\s*["'](?P<target>[^"']+)["']\s*,\s*["'][^"']+["']\s*\)\s*$''', re.I)


def rewrite_loops(ref, lines, targets):
    """Hide/move/show only a proven, authored start-on harm loop.

    Preserve a preceding activation of that same entity, without adding acts.
    Existing SPEC 45 blocks remain byte-identical. Ambiguous source names fail
    instead of making a different entity visible in another zone.
    """
    out = []
    i = changed = 0
    while i < len(lines):
        move = _LOOP_MOVE.fullmatch(lines[i])
        states = targets.get(move['target'].lower(), set()) if move else set()
        if True not in states:
            out.append(lines[i]); i += 1
            continue
        if states != {True}:
            raise ValueError(f'{ref}: ambiguous relocated loop target {move["target"]!r}')
        name, indent = move['target'], move['indent']
        hide = f'{indent}setInvisible("{name}", "TRUE" )'
        show = f'{indent}setInvisible("{name}", "FALSE" )'
        previous = _LOOP_ACT.fullmatch(out[-1]) if out else None
        same_act = previous and previous['target'].lower() == name.lower()
        hidden = (out and out[-1] == hide) or (same_act and len(out) >= 2 and out[-2] == hide)
        if hidden:
            if i + 1 >= len(lines) or lines[i + 1] != show:
                raise ValueError(f'{ref}: incomplete relocated loop visibility block')
            out.extend(lines[i:i + 2]); i += 2
            continue
        activation = [out.pop()] if same_act else []
        out.extend([hide, *activation, lines[i], show])
        changed += 1
        i += 1
    return out, changed
