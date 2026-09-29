"""Sources (research_path overrides, modes, round trip) and P2's pure pieces: the vectorised ELF hash and random
chain against zhash / resolve.py's loop, the mission plan on a synthetic mission set, the collision categories."""
import json
import random
import tempfile
from pathlib import Path

import synth  # noqa: F401  (puts tools/ on sys.path)
from xml1build import common as C
from xml1build.sources import Sources
from xml1build.prepare import tables as P2


def test_sources_developer_and_overrides():
    s = Sources.developer('X:/xml2', root='X:/repo')
    assert s.mode == 'developer' and s.x1_loose.name == 'xml1_loose' and s.x1_xbox.name == 'xml1_xbox'
    assert s.research_path('scripts/out/zone_acts.json') == s.research / 'scripts/out/zone_acts.json'
    assert s.collisions == s.research / 'characters/collisions.json'
    t = Sources(**{**s.__dict__, 'mode': 'prepared',
                   'overrides': (('scripts/out', Path('P:/p3/out')), ('scripts/out/data', Path('P:/p3b')),
                                 ('characters/collisions.json', Path('P:/t/c.json')))})
    assert t.research_path('scripts/out/scripts/a.py') == Path('P:/p3/out/scripts/a.py')
    assert t.research_path('scripts/out/data/missions') == Path('P:/p3b/missions')      # longest prefix wins
    assert t.research_path('scripts/out') == Path('P:/p3/out')
    assert t.research_path('scripts/outside.json') == t.research / 'scripts/outside.json'   # whole components only
    assert t.research_path('scripts\\out\\x.json') == Path('P:/p3/out/x.json')
    assert t.collisions == Path('P:/t/c.json')
    assert Path('P:/p3/out') in t.protected()
    back = Sources.from_json(json.loads(json.dumps(t.describe())))
    assert back.research_path('scripts/out/x') == t.research_path('scripts/out/x') and back.mode == 'prepared'


def test_sources_for_out():
    with tempfile.TemporaryDirectory() as td:
        assert Sources.for_out(td, 'X:/xml2').mode == 'developer'
        s = Sources.developer('X:/xml2', root='X:/repo')
        p = Sources(**{**s.__dict__, 'mode': 'prepared', 'x1_loose': Path('C:/cache/disc/loose')})
        (Path(td) / '_build').mkdir()
        (Path(td) / '_build' / 'sources.json').write_text(json.dumps(p.describe()))
        got = Sources.for_out(td)
        assert got.mode == 'prepared' and got.x1_loose == Path('C:/cache/disc/loose')


def test_check_out_safe_protects_sources():
    s = Sources.developer('X:/xml2', root='X:/repo')
    p = Sources(**{**s.__dict__, 'cache': Path('X:/cache')})
    for bad in ('X:/cache/out', 'X:/repo/xml1_loose/x', 'X:/xml2/sub', 'X:/'):
        try:
            C._check_out_safe(Path(bad), Path('X:/xml2'), p.protected())
            raise AssertionError(f'{bad} must be refused')
        except ValueError:
            pass
    C._check_out_safe(Path('X:/games/port'), Path('X:/xml2'), p.protected())


def test_elf_np_matches_zhash():
    from xml1build.lib.zhash import elf_hash
    rnd = random.Random(7)
    alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/.*-'
    names = [''.join(rnd.choice(alphabet) for _ in range(rnd.randint(1, 60))) for _ in range(500)] + ['', 'a']
    got = P2._elf_np(names)
    assert [int(x) for x in got] == [elf_hash(n) for n in names]
    seeds = [rnd.getrandbits(28) for _ in names]
    got = P2._elf_np(names, seeds)
    assert [int(x) for x in got] == [elf_hash(n, h) for n, h in zip(names, seeds)]


def test_random_chain_matches_resolve_loop():
    """resolve.py: for i in range(16): h2 = elf('/***RANDOM***/i', h); hit -> name it; miss and i > 0 -> stop."""
    import numpy as np
    from xml1build.lib.zhash import elf_hash
    seeds = [elf_hash(f'sound/{i}') for i in range(40)]
    keys = set()
    for j, h in enumerate(seeds):                  # seed j has variants 0..(j % 6) as keys; seed 5 only variant 3
        for i in range(j % 6):
            keys.add(elf_hash(f'/***RANDOM***/{i}', h))
    keys.add(elf_hash('/***RANDOM***/3', seeds[5 * 7]))
    expect = {}
    for r, h in enumerate(seeds):
        for i in range(16):
            h2 = elf_hash(f'/***RANDOM***/{i}', h)
            if h2 in keys:
                expect[(r, i)] = h2
            elif i > 0:
                break
    got = {}
    for i, (rows, vals) in P2._random_chain(np.array(seeds, dtype=np.uint64),
                                            np.array(sorted(keys), dtype=np.uint64)).items():
        for r, v in zip(rows, vals):
            got[(int(r), i)] = int(v)
    assert got == expect


def _mission(name, objs):
    body = ''.join(f'<OBJECTIVE name="{n}" descname="{d}" description="{d} text" xp="{xp}"/>' for n, d, xp in objs)
    return f'<MISSION name="{name}">{body}</MISSION>'


def test_mission_plan_groups():
    with tempfile.TemporaryDirectory() as td:
        assets, loose = Path(td) / 'assets', Path(td) / 'loose'
        md = assets / 'data' / 'missions'
        md.mkdir(parents=True)
        (loose / 'scripts' / 'x').mkdir(parents=True)
        (md / 'missions.xml').write_text('<MISSIONS><MISSION name="m1"/><MISSION name="m2"/><MISSION name="M3"/>'
                                         '</MISSIONS>')
        (md / 'm1.eng').write_text(_mission('m1', [('a', 'Beat A', 10), ('b', 'Find B & C', 20)]))
        (md / 'm2.eng').write_text(_mission('m2', [('a', 'Beat A', 10), ('c', 'Go', 5)]))
        (md / 'm3.eng').write_text(_mission('m3', [('a', 'Other A', 1)]))          # redefines 'a': new group
        (md / 'side.eng').write_text(_mission('side', [('s', 'Side', 0)]))
        (md / 'dead.eng').write_text(_mission('dead', [('d', 'Dead', 0)]))
        (loose / 'scripts' / 'x' / 'go.py').write_text('beginSideMission("side")\n')
        plan, texts = P2.mission_plan(assets, loose)
        assert [g['missions'] for g in plan['groups']] == [['m1', 'm2'], ['m3', 'side']]
        assert plan['unused_mission_files'] == ['dead'] and plan['n_objectives_total'] == 5
        assert plan['missions']['m2']['act'] == 1 and plan['missions']['side']['group_file'] == 'x1_act02'
        assert plan['missions']['m1']['file'] == 'm1.eng'
        assert sorted(texts) == ['missions.xml', 'x1_act01.xml', 'x1_act02.xml']
        assert 'descname="Find B &amp; C"' in texts['x1_act01.xml']
        assert texts['missions.xml'].count('<MISSION ') == 2


def test_collision_categories_and_compare():
    assert P2._category('actors/5810.igb') == 'actors/skin(numeric)'
    assert P2._category('actors/01_cyclops.igb') == 'actors/animdb(NN_name)'
    assert P2._category('actors/fightstyle_default.igb') == 'actors/other(fightstyle)'
    assert P2._category('ui/hud/characters/0101.igb') == 'ui/hud/characters'
    assert P2._category('data/powerstyles/ps_x.eng') == 'data/powerstyles'
    assert P2._category('data/npcstat.eng') == 'data/npcstat'
    assert P2._category('maps/nyc/x.eng') == 'maps/nyc'
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / 'x1').mkdir()
        (t / 'x2').mkdir()
        (t / 'x1' / 'same.eng').write_text('<a B="1"><c/></a>')
        (t / 'x1' / 'diff.xml').write_text('<a b="2"/>')
        (t / 'x1' / 'bad.eng').write_text('<a b="1">')
        (t / 'x1' / 's.py').write_bytes(b'x = 1\r\n')
        (t / 'x1' / 'new.igb').write_bytes(b'igb')
        root = C.xmlb.decode(C.xmlb.encode(C.parse_x1_text(b'<a b="1"><c/></a>')))
        (t / 'x2' / 'same.engb').write_bytes(C.xmlb.encode(root))
        (t / 'x2' / 'diff.xmlb').write_bytes(C.xmlb.encode(root))
        (t / 'x2' / 'bad.engb').write_bytes(C.xmlb.encode(root))
        (t / 'x2' / 's.py').write_bytes(b'x = 1\n')
        idx = {p.name.lower(): str(p) for p in (t / 'x2').iterdir()}
        got = {n: P2._compare(n, str(t / 'x1' / n), idx)[0]
               for n in ('same.eng', 'diff.xml', 'bad.eng', 's.py', 'new.igb')}
        assert got == {'same.eng': 'identical', 'diff.xml': 'collision', 'bad.eng': 'x1_parse_error',
                       's.py': 'identical', 'new.igb': 'x1_only'}, got
        assert P2._compare('v.fre', 'x', idx)[0] == 'skip'
