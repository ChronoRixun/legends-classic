"""Prepare phase 1b pieces without game data (BUILDER_DESIGN.md 6.1): P1 with and without the movie files (and the
movies.json providers a --no-movies build reads), the P3 script rewriter on a tiny synthetic XML1 tree, the shared
stage helpers (NTFS walk order, report path rebasing, the memory-budgeted worker pool), Sources.movies_index."""

import json
import os
import struct
import tempfile
from pathlib import Path
from types import SimpleNamespace

import synth
from xml1build import media as M
from xml1build import prepare
from xml1build.prepare import disc as P1, scripts as P3
from xml1build.sources import Sources


def _noop(*a, **k):
    pass


# ---------------------------------------------------------------------------------------------------- helpers
def _square(x):
    return x * x


def _boom(x):
    if x == 2:
        raise ValueError('boom')
    return x


def test_pool_map_order_budget_and_errors():
    items = [5, 4, 3, 2, 1]
    assert prepare.pool_map(_square, items, 1) == [25, 16, 9, 4, 1]
    seen = []
    got = prepare.pool_map(_square, items, 3, cost=lambda x: 100 * x, budget=450,
                           progress=lambda d, t, u: seen.append((d, t)))
    assert got == [25, 16, 9, 4, 1] and seen[-1] == (5, 5)
    try:
        prepare.pool_map(_boom, [1, 2, 3], 2)
    except ValueError as e:
        assert 'boom' in str(e)
    else:
        raise AssertionError('a worker exception must reach the caller')
    flag = {'n': 0}

    def cancel():
        flag['n'] += 1
        return flag['n'] > 1
    try:
        prepare.pool_map(_square, list(range(6)), 2, cancel=cancel)
    except prepare.Cancelled:
        pass
    else:
        raise AssertionError('cancel must stop the pool')


def test_publish_waits_out_a_transient_rename_lock():
    """a scanner holding a fresh file makes the directory rename fail with PermissionError for a moment: publish
    retries (prepare.rename) instead of failing the build; a lock that never clears still raises."""
    with tempfile.TemporaryDirectory() as td:
        partial, final = Path(td) / 'stage-v1-x.partial', Path(td) / 'stage-v1-x'
        partial.mkdir()
        real, calls = Path.rename, []

        def flaky(self, target):
            calls.append(self.name)
            if len(calls) <= 2:
                raise PermissionError(5, 'Access is denied')
            return real(self, target)
        Path.rename = flaky
        try:
            st = prepare.publish(partial, final, {'stage': 'stage'})
        finally:
            Path.rename = real
        assert calls == ['stage-v1-x.partial'] * 3 and final.is_dir() and not partial.exists()
        assert st['stage'] == 'stage' and (final / 'stage.json').is_file()

        def locked(self, target):
            raise PermissionError(5, 'Access is denied')
        Path.rename = locked
        try:
            prepare.rename(final, partial, tries=3, wait=0)
        except PermissionError:
            pass
        else:
            raise AssertionError('a lock that never clears must still fail')
        finally:
            Path.rename = real


def test_ntfs_walk_order_and_helpers():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for rel in ('b/x.py', 'B_/y.py', '_z/q.py', 'a/Zeta.txt', 'a/alpha.txt', 'a/_under.txt', 'top.txt'):
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'x')
        walk = list(prepare.ntfs_walk(root))
        order = [(Path(d).relative_to(root).as_posix(), ds, fs) for d, ds, fs in walk]
        assert order[0] == ('.', ['a', 'b', 'B_', '_z'], ['top.txt'])       # upper-case order: letters before '_'
        assert order[1] == ('a', [], ['alpha.txt', 'Zeta.txt', '_under.txt'])
        assert [o[0] for o in order] == ['.', 'a', 'b', 'B_', '_z']         # pre-order, like os.walk topdown
        if os.name == 'nt':                                                  # = FindFirstFile order on NTFS
            assert [(Path(d).resolve(), ds, fs) for d, ds, fs in os.walk(root)] == \
                [(Path(d).resolve(), ds, fs) for d, ds, fs in walk]
        assert prepare.find_ci(root, 'A', 'ZETA.TXT') is not None and prepare.find_ci(root, 'nope') is None
        assert prepare.listing_digest(root) == prepare.listing_digest(str(root))
    reb = prepare.rebase_paths({'out': 'C:/c/x.partial/all_ima/eng\\a.zss', 'in': 'D:/disc/a',
                                'l': ['C:\\c\\x.partial\\m', ('C:/c/x.partial/t', 1)]},
                               ('C:/c/x.partial', 'C:/c/x'))
    assert reb == {'out': 'C:/c/x/all_ima/eng\\a.zss', 'in': 'D:/disc/a', 'l': ['C:/c/x\\m', ('C:/c/x/t', 1)]}


# ---------------------------------------------------------------------------------------------------- P1 movies
def _sfd(rate=44100, samples=441000):
    """a tiny Sofdec-like program stream: an MPEG-1 pack header and one C0 packet carrying an ADX header."""
    cofs = 0x20
    head = bytearray(b'\x80\x00' + struct.pack('>H', cofs) + bytes([3, 18, 4, 2]) + struct.pack('>II', rate, samples))
    head += bytes(cofs - 2 - len(head)) + b'(c)CRI' + bytes(16)
    payload = b'\x0f' + bytes(head)
    pack = b'\x00\x00\x01\xba' + bytes([0x21]) + bytes(7)
    return pack + b'\x00\x00\x01\xc0' + struct.pack('>H', len(payload)) + payload + b'\x00\x00\x01\xb9' + bytes(64)


def test_p1_without_movies_then_added():
    with tempfile.TemporaryDirectory() as td:
        files = synth.xml1_disc_files()
        sfd = _sfd()
        files['movies/ntsc/i/1/i101.sfd'] = sfd
        iso = Path(td) / 'xml1.iso'
        iso.write_bytes(synth.xdvdfs(files))
        cache = Path(td) / 'cache'
        r = P1.run(iso, cache, log=_noop, movies=False)
        d = r['dir']
        assert r['stage']['movies'] is False and not (d / 'xbox' / 'movies').exists()
        assert (d / 'xbox' / 'sounds' / 'zsds' / 'a' / 'c' / 'aco_m.zsm').is_file()
        rows = json.loads((d / 'movies.json').read_text())
        assert [(x['name'], x['path'], x['size'], x['dirs'], x['duration']) for x in rows] == \
            [('i101', 'movies/ntsc/i/1/i101.sfd', len(sfd), ['i', '1'], 10.0)]
        # the providers of a --no-movies build read movies.json when the files are absent ...
        ctx = SimpleNamespace(x1_xbox=d / 'xbox', sources=SimpleNamespace(movies_index=d / 'movies.json'))
        [p] = M.x1_movie_files(ctx)
        assert p == d / 'xbox' / 'movies' / 'ntsc' / 'i' / '1' / 'i101.sfd' and not p.exists()
        from_index = M.movie_facts(ctx, p)
        assert from_index[0] == len(sfd) and from_index[1]['adx']['c0']['rate'] == 44100
        assert M._x1_movies(ctx) == [('i101', p, ('i', '1'))]
        assert M.movie_duration(ctx, 'I101') == 10.0
        # ... a cached P1 without movies cannot serve a movies build without the image
        try:
            prepare.run_stages(cache, Path(td), None, stages=(), movies=True, log=_noop)
        except prepare.PrepareError as e:
            assert e.code == 'E_CACHE_NO_MOVIES'
        else:
            raise AssertionError('E_CACHE_NO_MOVIES expected')
        # a movies run adds the files to the same directory (same key), and the facts read from them are equal
        r2 = P1.run(iso, cache, log=_noop, movies=True)
        assert r2['cached'] and r2['dir'] == d and r2['stage']['movies'] is True
        assert r2['stage']['key'] == r['stage']['key'] and P1.read_stage(d)['movies'] is True
        assert p.read_bytes() == sfd and M.movie_facts(ctx, p) == from_index
        assert not any(x.name.endswith('.partial') for x in (d).iterdir())
        # a no-movies run of a disc prepared with movies reuses it (and keeps the files)
        r3 = P1.run(iso, cache, log=_noop, movies=False)
        assert r3['cached'] and p.is_file()


def test_sources_movies_index_round_trip():
    with tempfile.TemporaryDirectory() as td:
        disc = Path(td) / 'disc'
        disc.mkdir()
        (disc / P1.MOVIES_JSON).write_text('[]')
        s = Sources.prepared(disc, Path(td) / 'xml2', overrides={'scripts/out': Path(td) / 'p3' / 'out'})
        assert s.movies_index == (disc / P1.MOVIES_JSON).resolve()
        assert s.research_path('scripts/out/zone_acts.json') == (Path(td) / 'p3' / 'out' / 'zone_acts.json').resolve()
        back = Sources.from_json(json.loads(json.dumps(s.describe())))
        assert back.movies_index == s.movies_index and back.overrides == s.overrides
        assert Sources.developer().movies_index is None


# ---------------------------------------------------------------------------------------------------- P3 rewriter
def _xml1_tree(root: Path):
    loose, assets = root / 'loose', root / 'assets'
    files = {
        loose / '_fb_manifest.json': json.dumps({'packages/generated/maps/z/zone1.fb': [
            ['scripts/z/zone1.py', 'py'], ['maps/z/zone1.eng', 'zonexml']]}),
        loose / 'maps/z/zone1.eng': '<world>\r\n<entity name="world" mission="m1" zonescript="z/zone1" />\r\n</world>',
        loose / 'scripts/z/zone1.py': 'setMissionVar("count", 3)\r\nx = getMissionVar("count")\r\n'
                                      'createPopupDialog("$1")\r\n'
                                      'addPopupDialogOption("$1", "beginMission(\'m2\')")\r\n'
                                      'showPopupDialog()\r\nbeginMission("m2")\r\n',
        loose / 'conversations/c1.eng': '<conversation onexit="setMissionFlag(\'seen\', 2, 1)" />',
        assets / 'data/strings.eng': '<strings>\r\n<string id="1" text="Hello" />\r\n</strings>',
        assets / 'scripts/menus/start.py': 'loadMap("z/zone1")',
    }
    for p, t in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(t.encode('latin-1'))
    plan = {'missions': {
        'm1': {'act': 1, 'attrs': {}, 'objectives': [{'name': 'o1', 'enabled': 'true'}], 'required': []},
        'm2': {'act': 2, 'attrs': {'mapload': 'z/zone2'}, 'objectives': [{'name': 'o2'}], 'required': ['Cyclops']}}}
    return loose, assets, plan


def test_rewriter_synthetic_tree():
    api1, api2 = P3.load_api()
    with tempfile.TemporaryDirectory() as td:
        loose, assets, plan = _xml1_tree(Path(td))
        outs = []
        for n in (1, 2):
            out = Path(td) / f'out{n}'
            lines, rep, counts = P3.Rewriter(loose, assets, plan, api1, api2).write(str(out))
            outs.append({p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob('*') if p.is_file()})
        assert outs[0] == outs[1]                                 # deterministic
        o = outs[0]
        z = o['scripts/z/zone1.py'].decode('latin-1')
        assert z.endswith('\r\n') and '\n' not in z.replace('\r\n', '')
        body = z.split('\r\n')
        assert body[1] == 'setCurrentAct(1 )'                      # the zone's act, injected at the top
        assert 'getMissionVar' not in z and 'setGameFlag(' in z and 'getGameFlag(' in z
        assert 'createPopupDialogXml("x1/p001" )' in z and 'setCurrentAct(2 )' in z
        assert 'unlockCharacter("cyclops", "" )' in z and 'loadMapKeepTeam("z/zone2" )' in z
        assert 'dialogs/x1/p001.xml' in o and 'dialogs/x1/p001.XMLB' in o and 'dialogs/x1/p001.engb' in o
        assert b'text="Hello"' in o['dialogs/x1/p001.xml'] and b'x1/missions/begin_m2' in o['dialogs/x1/p001.xml']
        assert 'scripts/x1/missions/begin_m1.py' in o and 'scripts/x1/missions/begin_m2.py' in o
        assert o['scripts/menus/start.py'].decode() == 'loadMapKeepTeam("z/zone1" )\r\n'
        acts = json.loads(o['zone_acts.json'])
        assert acts['z/zone1']['acts'] == [1] and acts['z/zone1']['inject_act'] == 1
        store = json.loads(o['var_storage.json'])
        assert store['m:count']['kind'] == 'pack' and store['m:seen']['kind'] == 'flag'
        inline = json.loads(o['inline_rewrites.json'])
        assert inline == {"setMissionFlag('seen', 2, 1)": "setGameFlag('seen', 2, 1 )"}
        # the popup option's beginMission('m2') became the mission start script; zone1 packages it and the dialog
        assert json.loads(o['helper_refs.json']) == {'x1/missions/begin_m2': ['scripts/z/zone1.py:5 popup option']}
        assert json.loads(o['zone_extra_files.json']) == {'z/zone1': ['dialogs/x1/p001',
                                                                      'scripts/x1/missions/begin_m2']}
        assert counts['scripts'] == 2 and counts['dialogs'] == 1 and lines[0] == 'rewrite_scripts.py report'
