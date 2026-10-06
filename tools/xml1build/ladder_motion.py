"""Preserve XML1 ladder descent through native relative motion paths (SPEC 46).

Only our conversion code is distributed. Both the motion keys and the structural
motion-path template are read from the player's own XML1 files during the build.
"""
from __future__ import annotations

import math
import re
import struct

from .igb_file import IgbFile, IgbError

# script -> (source animation DB, clip, converted animation enum, generated path)
LADDERS = {
    'sewers/grso/grso_ladder_down': ('mission_grso', 'mission2', 'EA_ZONE2', 'x1_ladders/sewers'),
    'arbiter/a_int/grso_ladder_down': ('mission_a_int', 'mission1', 'EA_ZONE1', 'x1_ladders/arbiter'),
}
TEMPLATE = 'motionpaths/common/cabinet_knockedover.igb'
PATH_NODE = 'mp_cabinet'  # retained template node name, scoped by the generated file

# A spawner without monster_spawnexactlocation never starts its soldier at the ladder top: both
# games move the spawn to the nearest navigation point dropped onto the ground (SPEC 46). Such a
# spawner runs this unconverted copy of the descent script, so no path drives it through the floor.
FLOOR_SUFFIX = '_floor'


def floor_ref(ref):
    return ref + FLOOR_SUFFIX if ref in LADDERS else None


def floor_base(ref):
    """the converted descent script whose unconverted copy `ref` is, else None."""
    base = ref[:-len(FLOOR_SUFFIX)] if ref.endswith(FLOOR_SUFFIX) else None
    return base if base in LADDERS else None


def _script_ref(value):
    ref = (value or '').strip().replace('\\', '/').lower()
    return ref[:-3] if ref.endswith('.py') else ref


def exact_location(attrs):
    return (attrs.get('monster_spawnexactlocation') or '').strip().lower() in ('true', '1')


def floor_spawn_ref(attrs):
    """attrs: one entity's attributes. The floor copy's ref for a monster spawner whose spawn script
    is an authored ladder descent but which does not place its spawn at its own position; else None."""
    attrs = {k.lower(): v for k, v in attrs.items()}
    if (attrs.get('classname') or '').strip().lower() != 'monsterspawnerent' or exact_location(attrs):
        return None
    return floor_ref(_script_ref(attrs.get('monster_spawnscript')))


def path_spawner_problems(root):
    """names of the monster spawners in an XML tree that run a ladder path script without placing the
    spawn at the ladder top (the regression SPEC 46's floor copy prevents)."""
    return [el.get('name') for el in root.iter()
            if floor_spawn_ref(el.attrib) is not None]


def relative_keys(points, times):
    if (len(points) < 2 or len(points) != len(times) or times[0] != 0
            or any(a >= b for a, b in zip(times, times[1:]))
            or any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points)
            or points[-1][2] >= points[0][2]):
        raise ValueError('ladder motion must have finite descending keys and increasing times from zero')
    return [tuple(p[i] - points[0][i] for i in range(3)) for p in points]


def rewrite_script(ref, lines):
    entry = LADDERS.get(ref)
    if entry is None:
        return lines
    enum, path = entry[2], entry[3] + '/' + PATH_NODE
    start = f'startMotionPath("_OWNER_", "{path}", "TRUE", "" )'
    # Validate the complete original or rewritten sequence, including the same
    # per-actor signal on playanim/waitsignal. Merely seeing our path call is
    # insufficient: a truncated or externally edited script must fail closed.
    canon = lambda line: re.sub(r'\s+', '', line).replace("'", '"')
    statements = [canon(line) for line in lines if line.strip() and not line.lstrip().startswith('#')]
    plays = [i for i, line in enumerate(lines) if re.match(r'\s*playanim\s*\(', line)]
    waits = [i for i, line in enumerate(lines) if re.match(r'\s*waitsignal\s*\(', line)]
    match = (re.fullmatch(r'playanim\("' + enum + r'","_OWNER_","NONE",([A-Za-z_]\w*)\)',
                          canon(lines[plays[0]])) if len(plays) == 1 else None)
    if match is None or len(waits) != 1:
        raise ValueError(f'{ref}: unexpected ladder animation or completion signal')
    signal = match.group(1)
    original = ['setAIActive("_OWNER_","FALSE")', f'{signal}=getIDString("_OWNER_")',
                canon(lines[plays[0]]), f'waitsignal({signal})', 'setAIActive("_OWNER_","TRUE")']
    rewritten = original[:2] + ['setNoCollide("_OWNER_","TRUE")', 'setNoClip("_OWNER_","TRUE")', canon(start)] + original[2:4] + [
        'setNoClip("_OWNER_","FALSE")', 'setNoCollide("_OWNER_","FALSE")', original[4]]
    if statements == rewritten:
        return lines
    if statements != original:
        raise ValueError(f'{ref}: unexpected ladder animation or completion signal')
    out = list(lines)
    out[waits[0] + 1:waits[0] + 1] = ['setNoClip("_OWNER_", "FALSE" )', 'setNoCollide("_OWNER_", "FALSE" )']
    out[plays[0]:plays[0]] = ['setNoCollide("_OWNER_", "TRUE" )', 'setNoClip("_OWNER_", "TRUE" )', start]
    return out


def _list(g, ref, kind, width):
    obj = g.obj(ref)
    if obj is None or not obj.decoded or obj.name != kind:
        raise IgbError(f'expected {kind}')
    n, capacity, block = obj.get(2), obj.get(3), g.block(obj.get(4))
    if not isinstance(n, int) or not 2 <= n <= 4096 or capacity < n or block is None or block[1] != n * width:
        raise IgbError(f'invalid {kind} key count or storage')
    return obj, g.data[block[0]:block[0] + block[1]], n


def read_motion(data, clip):
    g = IgbFile(data)
    animations = [o for o in g.objects_of('igAnimation') if o.get(2) == clip]
    if len(animations) != 1:
        raise IgbError(f'expected one {clip} animation')
    tracks = [g.obj(r) for r in g.list_items(animations[0].get(5))]
    tracks = [o for o in tracks if o is not None and (o.get(2) or '').lower() == 'motion']
    if len(tracks) != 1:
        raise IgbError(f'{clip}: expected one Motion track')
    seq = g.obj(tracks[0].get(3))
    if seq is None or not seq.decoded or seq.name != 'igTransformSequence1_5':
        raise IgbError('unsupported ladder motion sequence')
    expected = {4: -1, 5: -1, 6: -1.0, 7: 0, 8: 1, 10: [0.0, 0.0, 0.0],
                12: -1, 13: -1, 14: -1, 15: 3, 16: 769, 19: -1}
    if any(seq.get(slot) != value for slot, value in expected.items()):
        raise IgbError('unsupported ladder motion interpolation or scale channels')
    _, positions, n = _list(g, seq.get(2), 'igVec3fList', 12)
    _, rotations, nr = _list(g, seq.get(3), 'igQuaternionfList', 16)
    _, time_data, nt = _list(g, seq.get(11), 'igLongList', 8)
    if n != nr or n != nt:
        raise IgbError('ladder motion channels have different key counts')
    times = list(struct.unpack(f'<{n}q', time_data))
    points = list(struct.iter_unpack('<3f', positions))
    relative = relative_keys(points, times)
    if times[-1] != seq.get(18) or seq.get(17) != 0 or animations[0].get(9) != times[-1]:
        raise IgbError('ladder animation and path durations differ')
    # The two authored descent clips use identity rotation; refuse a changed
    # rotating clip until its relative rotation is explicitly supported.
    if any(q != (0.0, 0.0, 0.0, 1.0) for q in struct.iter_unpack('<4f', rotations)):
        raise IgbError('rotating ladder Motion track is unsupported')
    return relative, rotations, time_data, times[-1]


def make_path(template, animation, clip):
    points, rotations, times, duration = read_motion(animation, clip)
    g = IgbFile(template)
    roots = [o for o in g.objects_of('igTransform') if o.get(2) == PATH_NODE]
    if len(roots) != 1:
        raise IgbError('unexpected ladder motion-path template root')
    root = roots[0]
    seq = g.obj(root.get(11))
    if seq is None or seq.name != 'igTransformSequence1_5' or not seq.decoded:
        raise IgbError('unexpected ladder motion-path template sequence')
    expected = {5: -1, 6: -1.0, 7: 0, 8: 1, 10: [0.0, 0.0, 0.0],
                12: -1, 13: -1, 14: -1, 15: 11, 16: 769, 19: -1}
    if any(seq.get(slot) != value for slot, value in expected.items()):
        raise IgbError('unexpected ladder motion-path template channels')
    def integer(obj, slot, value):
        field = obj.fields[slot]
        if field.size not in (4, 8):
            raise IgbError('unexpected motion-path scalar size')
        struct.pack_into('<q' if field.size == 8 else '<i', g.buf, field.offset, value)
    replacements = {}
    for slot, kind, width, blob in [
        (2, 'igVec3fList', 12, b''.join(struct.pack('<3f', *p) for p in points)),
        (3, 'igQuaternionfList', 16, rotations),
        (11, 'igLongList', 8, times),
    ]:
        obj, _, _ = _list(g, seq.get(slot), kind, width)
        integer(obj, 2, len(points)); integer(obj, 3, len(points))
        replacements[obj.get(4)] = blob
    # Discard the cabinet's animated scale and use the source clip's channel flags.
    integer(seq, 4, -1); integer(seq, 5, -1)
    integer(seq, 15, 3); integer(seq, 16, 769)
    integer(seq, 17, 0); integer(seq, 18, duration)
    g.set_floats(root, 8, [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
    for scene in g.objects_of('igSceneInfo'):
        integer(scene, 8, 0); integer(scene, 9, duration)
    result = g.rebuilt(replacements)
    IgbFile(result)  # validate all directory, object and memory sizes after resizing
    return result, {'keys': len(points), 'duration_ns': duration, 'displacement': points[-1]}


def build_for_scripts(ctx, refs):
    """Generate only needed paths; return their package entries and diagnostics."""
    result = []
    for ref in sorted(set(refs) & LADDERS.keys()):
        database, clip, _, path = LADDERS[ref]
        out_rel = f'MotionPaths/{path}.IGB'
        if not ctx.registry.get(out_rel):
            source = ctx.x1_path(f'actors/{database}.igb')
            template = ctx.x1_path(TEMPLATE)
            if source is None or template is None:
                raise IgbError(f'{ref}: missing source animation or motion-path template')
            data, info = make_path(template.read_bytes(), source.read_bytes(), clip)
            ctx.write_bytes(out_rel, data, source=f'zones:ladder motion {database}/{clip}')
            ctx.note(f'{ref}: ladder motion {info}')
        result.append(('motionpath', path + '/' + PATH_NODE))
    return result
