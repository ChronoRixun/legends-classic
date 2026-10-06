"""Owned-input checks for SPEC 46; never launches the game.

From tools/: python -m xml1build.ladder_motion_selftest --out <build>
"""
import argparse
from pathlib import Path
import struct

from . import common as C
from . import ladder_motion as L
from .igb_file import IgbFile
from .sources import Sources


def check(out, source_root=None):
    sources = Sources.developer(root=source_root) if source_root else Sources.for_out(out)
    checked_paths = set()
    for ref, (database, clip, enum, path) in L.LADDERS.items():
        candidates = [sources.x1_loose / f'actors/{database}.igb',
                      sources.x1_assets / f'actors/{database}.igb']
        source = next(p for p in candidates if p.is_file())
        points, rotations, times, duration = L.read_motion(source.read_bytes(), clip)
        g = IgbFile((out / f'MotionPaths/{path}.IGB').read_bytes())
        root = next(o for o in g.objects_of('igTransform') if o.get(2) == L.PATH_NODE)
        seq = g.obj(root.get(11))
        pos_list = g.obj(seq.get(2))
        actual = list(struct.iter_unpack('<3f', bytes(g.buf[slice(*_bounds(g, pos_list.get(4)))])))
        assert len(actual) == len(points), (ref, 'position count')
        assert all(abs(x - y) < 1e-4 for a, b in zip(actual, points) for x, y in zip(a, b)), (ref, 'position keys')
        for slot, expected in ((3, rotations), (11, times)):
            item = g.obj(seq.get(slot)); start, size = g.blocks[item.get(4)]
            assert g.data[start:start + size] == expected, (ref, 'rotation/timing keys')
        assert seq.get(4) == -1 and seq.get(5) == -1 and seq.get(18) == duration
        script = (out / C.script_rel(ref)).read_text(encoding='latin-1')
        assert f'"{path}/{L.PATH_NODE}"' in script and enum in script
        assert script.count('waitsignal') == 1 and 'waittimed' not in script
        assert script.index('startMotionPath') < script.index('playanim') < script.index('waitsignal')
        assert L.rewrite_script(ref, script.splitlines()) == script.splitlines()
        assert script.count('setNoClip') == 2 and script.count('setNoCollide') == 2
        checked_paths.add(path + '/' + L.PATH_NODE)
    affected = 0
    for pkg in (out / 'Packages/generated/maps').rglob('*.PKGB'):
        entries = C.decode_xmlb(pkg.read_bytes())
        paths = {e.get('filename') for e in entries if e.tag == 'motionpath'}
        scripts = {C.script_ref(e.get('filename', '')) for e in entries if e.tag == 'script'}
        needed = {L.LADDERS[s][3] + '/' + L.PATH_NODE for s in scripts & L.LADDERS.keys()}
        if needed:
            assert needed <= paths, (pkg.name, 'missing ladder path')
            assert len(paths) <= 16, (pkg.name, 'motion path capacity')
            affected += 1
    assert affected > 0
    world = C.decode_xmlb((out / 'Maps/sewers/grso/sewers3_1_2.engb').read_bytes())
    untouched = next(e for e in world.iter('entity') if e.get('name') == 'ladderdude02')
    assert untouched.get('monster_spawnscript') == 'object_ambi/sewers/grso_slide_down'
    # Ground spawns (no exact location) run the unconverted descent; exact ones keep the path.
    path_spawners = floor_spawners = 0
    for engb in (out / 'Maps').rglob('*.engb'):
        entities = [e for e in C.decode_xmlb(engb.read_bytes()).iter('entity')
                    if (e.get('classname') or '').lower() == 'monsterspawnerent']
        assert not L.path_spawner_problems(C.decode_xmlb(engb.read_bytes())), (engb.name, 'ground spawn on a path')
        for e in entities:
            script = (e.get('monster_spawnscript') or '').lower()
            if script in L.LADDERS:
                assert L.exact_location(e.attrib), (engb.name, e.get('name'))
                path_spawners += 1
            elif L.floor_base(script):
                assert not L.exact_location(e.attrib), (engb.name, e.get('name'))
                text = (out / C.script_rel(script)).read_text(encoding='latin-1')
                base = (out / C.script_rel(L.floor_base(script))).read_text(encoding='latin-1')
                assert 'startMotionPath' not in text and 'setNoClip' not in text and 'setNoCollide' not in text
                assert L.rewrite_script(L.floor_base(script), text.splitlines()) == base.splitlines()
                floor_spawners += 1
    assert path_spawners and floor_spawners
    world = C.decode_xmlb((out / 'Maps/sewers/grso/sewers3_1_3.engb').read_bytes())
    ground = next(e for e in world.iter('entity') if e.get('name') == 'ladderdude01')
    assert ground.get('monster_spawnscript') == L.floor_ref('sewers/grso/grso_ladder_down')
    print(f'PASS: {len(checked_paths)} authored motion paths, {affected} zone packages; original exceptional spawn retained')
    print(f'PASS: {path_spawners} ladder-top spawners run the path, {floor_spawners} ground spawners the original descent')
    print('No runtime checks performed: slide timing, concurrent actors and save/reload remain manual.')


def _bounds(g, ref):
    start, size = g.blocks[ref]
    return start, start + size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--source-root', type=Path, help='optional developer input checkout for a split-source build')
    args = parser.parse_args()
    check(args.out.resolve(), args.source_root)


if __name__ == '__main__':
    main()
