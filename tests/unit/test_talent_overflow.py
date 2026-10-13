"""The TalentRegistry fix pieces without game data: talent_sets partitioning/grouping, the talent registry demand model
(talent_budget against a synthetic validator), and the 0.2.0 save_positions order contract. Invented names only.
"""
import sys

sys.path.insert(0, 'tools')

from xml1build import save_positions as SP, talent_sets as TS, talent_budget as TB


# ------------------------------------------------------------------------------------------------ talent_sets
def test_npc_set_and_set_file():
    assert TS.npc_set({'alpha', 'beta', 'gamma'}, {'alpha'}) == frozenset({'alpha'})
    assert TS.npc_set({'alpha'}, set()) == frozenset()
    assert TS.set_file(frozenset()) == ''
    assert TS.set_file(frozenset({'fightstyle_villain'})) == TS.GENERIC_FILE
    assert TS.set_file(frozenset({'physical_res', 'x1_fightstyle_gun_rifle'})) == TS.GENERIC_FILE
    own = TS.set_file(frozenset({'zz_claw', 'zz_spin'}))
    assert own == 'data/talents/npc_zz_claw+zz_spin'
    assert TS.set_file(frozenset({'fightstyle_villain', 'zz_claw'})) != TS.GENERIC_FILE


def test_file_sets_groups_identical_refs():
    npc_refs = {
        'aa_brute': {'zz_claw', 'zz_spin'},
        'aa_brute_b': {'zz_spin', 'zz_claw'},
        'bb_gunner': {'x1_fightstyle_gun_rifle'},
        'cc_sniper': {'fightstyle_villain'},
        'ee_tough': {'physical_res'},
        'cc_plain': {'drone_energy'},
        'dd_none': set(),
    }
    sets = TS.file_sets(npc_refs, {'zz_claw', 'zz_spin', 'x1_fightstyle_gun_rifle',
                                   'fightstyle_villain', 'physical_res'})
    assert sets == {'data/talents/npc_zz_claw+zz_spin': frozenset({'zz_claw', 'zz_spin'}),
                    TS.GENERIC_FILE: frozenset({'x1_fightstyle_gun_rifle', 'fightstyle_villain', 'physical_res'})}


def test_partition_moves_keeps_hero_base_and_energy():
    keep = {'fightstyle_villain', 'zz_claw', 'toughness', 'dr_stun', 'drone_energy', 'might'}
    hero_refs = {'toughness', 'might'}
    npc_refs = {'fightstyle_villain', 'zz_claw', 'dr_stun', 'drone_energy'}
    x2_base = {'dr_stun', 'might'}
    energy = 'drone_energy'
    assert TS.partition_moves(keep, hero_refs, npc_refs, x2_base, energy) == ['fightstyle_villain', 'zz_claw']
    # a name no npc references never moves (it is dropped, not filed)
    assert TS.partition_moves({'zz_claw'}, set(), set(), set(), energy) == []


# -------------------------------------------------------------------------------------------------- zone rosters
class _E:
    """tiny element stand-in for the roster scanners."""

    def __init__(self, tag, _children=(), **attrs):
        self.tag = tag
        self._a = {k: v for k, v in attrs.items() if v is not None}
        self._c = list(_children)

    def get(self, k, d=None):
        return self._a.get(k, d)

    def iter(self):
        yield self
        for c in self._c:
            yield from c.iter()


def test_map_spawn_roster_takes_every_character_attr():
    root = _E('world', _children=[_E('entity', classname='worldent'),
                                  _E('entity', classname='monsterspawnerent', character='AA_Brute'),
                                  _E('entinst', type='sp_aa'),
                                  _E('entity', charactername='bb_gunner')])
    assert TS.map_spawn_roster(root) == {'aa_brute', 'bb_gunner'}
    assert TS.map_spawn_roster(None) == set()


def test_dangerroom_zone_roster_follows_arena_mapping():
    spawner = _E('SPAWNER', character='Aa_Boss')
    mustdie = _E('MUSTDIE', character='bb_lackey')
    course = _E('COURSE', name='ZZ001', arena='Test Pit', _children=[spawner, mustdie])
    other_sp = _E('SPAWNER', character='cc_elsewhere')
    other = _E('COURSE', name='ZZ002', arena='Elsewhere', _children=[other_sp])
    arena = _E('ARENA', title='Test Pit', zone='arena/arena_test')
    arena2 = _E('ARENA', title='Elsewhere', zone='arena/arena_other')
    root = _E('DANGERROOM', _children=[arena, arena2, course, other])
    assert TS.dangerroom_zone_roster(root, 'arena/arena_test') == {'aa_boss', 'bb_lackey'}
    assert TS.dangerroom_zone_roster(root, 'arena/arena_other') == {'cc_elsewhere'}
    assert TS.dangerroom_zone_roster(root, 'arena/missing') == set()


def test_script_zone_roster_recognizes_spawn_calls_only():
    texts = {'x1/test': 'spawn("aa_brute")\nspawnInto("arena/arena_test", "bb_lackey")\n'
                        'waittimed(1.0)\nstartConversation("x1/hi")\n'}
    got = TS.script_zone_roster(texts, lambda n: n in {'aa_brute', 'bb_lackey'})
    assert got == {'aa_brute', 'bb_lackey'}


def test_script_closure_follows_literal_script_calls():
    texts = {'x1/a': 'callscript("x1/b")\nspawn("aa_boss")',
             'x1/b': 'act("sp_x", "sp_x")\ncallscript("x1/c")',
             'x1/c': 'spawn("bb_add")'}
    closed = TS.script_closure_refs(['x1/a'], lambda r: texts.get(r))
    assert closed == {'x1/a', 'x1/b', 'x1/c'}
    got = TS.script_zone_roster({r: texts[r] for r in closed}, lambda n: True)
    assert got == {'aa_boss', 'bb_add'}


def test_zone_set_files_drops_only_fully_covered_files():
    jugg = frozenset({'zz_punch', 'zz_slam', 'zz_armor'})
    vulcan = frozenset({'zz_flame', 'zz_fring', 'zz_fbat', 'fightstyle_villain'})
    generic = frozenset({'fightstyle_villain'})
    kept = TS.zone_set_files([jugg, vulcan, generic])
    assert set(kept) == {TS.set_file(jugg), TS.set_file(vulcan)}
    # a file with a unique name is always kept
    toad = frozenset({'zz_toad'})
    kept = TS.zone_set_files([generic, toad])
    assert set(kept) == {TS.GENERIC_FILE, TS.set_file(toad)}
    # identical sets collapse to one file
    kept = TS.zone_set_files([jugg, frozenset({'zz_slam', 'zz_punch', 'zz_armor'})])
    assert len(kept) == 1


# ------------------------------------------------------------------------------------------------ demand model
def test_demand_counts_union_and_files():
    counts = {'data/shared_talents': frozenset({'s1', 's2'}),
              'data/talents/aa': frozenset({'a1'}),
              'data/talents/bb': frozenset({'a1', 'b1'})}
    d = TB.demand({'data/shared_talents', 'data/talents/aa', 'data/talents/bb'}, counts)
    assert d == {'talents': 4, 'files': 3}
    d = TB.demand({'data/shared_talents', 'data/talents/aa'}, counts)
    assert d == {'talents': 3, 'files': 2}
    try:
        TB.demand({'data/talents/unknown'}, counts)
        assert False, 'unknown file must raise'
    except ValueError:
        pass


def test_problems_and_full_warnings():
    assert TB.problems({'talents': 100, 'files': 9}) == []
    over_n = TB.problems({'talents': 101, 'files': 9})
    over_f = TB.problems({'talents': 50, 'files': 10})
    assert any('101' in p for p in over_n) and any('10 talent files' in p for p in over_f)


def test_worst_party_picks_heaviest():
    counts = {'data/shared_talents': frozenset({'s'})}
    heroes = {'h1': {'data/talents/h1'}, 'h2': {'data/talents/h2'}, 'h3': {'data/talents/h3'}}
    for h, n in (('h1', ('a',)), ('h2', ('b',)), ('h3', ('c',))):
        counts[f'data/talents/{h}'] = frozenset(n)
    best, who = TB.worst_party({'data/shared_talents'}, heroes, counts, size=2)
    assert best['talents'] == 3 and len(who) == 2


class FakeCheck:
    def __init__(self):
        self.errors, self.warnings, self.counts, self.sets, self.details = [], [], {}, {}, {}

    def error(self, m):
        self.errors.append(m)

    def warn(self, m):
        self.warnings.append(m)

    def count(self, k):
        self.counts[k] = self.counts.get(k, 0) + 1

    def set(self, k, v):
        self.sets[k] = v


class FakeTree:
    """minimal v.tree stand-in over {rel: [(name, ...)]} talent leaves."""

    def __init__(self, talents):
        self.talents = talents        # {rel: [talent names]}

    def iter(self, tag=None):
        class E:
            def __init__(self, n):
                self.tag = 'talent'
                self._n = n

            def get(self, k, d=None):
                return self._n if k == 'name' else d
        return iter([E(n) for n in self.talents])


class FakeV:
    """the Validator surface talent_budget.validate touches."""

    def __init__(self, shared, npc, sets):
        self._shared = shared
        self._npc = npc               # {stats name: [talent names]}
        self._sets = sets             # {rel: [talent names]}
        self._stats = {'talents': {'.engb': list(shared), '.xmlb': list(shared)},
                       'variants': {}, 'by_name': {}}

    def stats(self):
        return self._stats

    def tree(self, rel):
        ln = rel.lower()
        if ln == 'data/shared_talents.engb':
            return FakeTree(self._shared)
        if ln == 'data/npcstat.engb':
            class Root:
                def __init__(self, npc):
                    self._npc = npc

                def iter(self, tag=None):
                    class S:
                        def __init__(self, name, refs):
                            self._name, self._refs = name, refs

                        def get(self, k, d=None):
                            return self._name if k == 'name' else d

                        def iter(self, tag=None):
                            class T:
                                def __init__(self, n):
                                    self.tag = 'talent'
                                    self._n = n

                                def get(self, k, d=None):
                                    return self._n if k == 'name' else d
                            return iter([T(r) for r in self._refs])
                    return iter([S(n, r) for n, r in self._npc.items()])
            return Root(self._npc)
        for rel_noext, names in self._sets.items():
            if ln == rel_noext + '.engb':
                return FakeTree(names)
        return None

    class _Scan:
        pkg = {}

    scan = _Scan()

    class _Idx:
        def __init__(self, sets):
            self._sets = sets

        def under(self, prefix):
            p = prefix.lower()
            return [r + '.engb' for r in self._sets if r.lower().startswith(p)]

    @property
    def idx(self):
        return FakeV._Idx(self._sets)

    def converted_zones(self):
        return []

    def zone_pkg(self, z):
        return None


def test_validate_resolves_shared_npc_refs_and_forbids_set_files():
    shared = ['s1', 's2', 'drone_energy', 'zz_claw']
    npc = {'aa_brute': ['s1', 'zz_claw'], 'bb_plain': ['s2']}
    sets = {}
    v = FakeV(shared, npc, sets)
    ck = FakeCheck()
    TB.validate(v, ck)
    assert not ck.errors, ck.errors
    assert ck.sets['npc_set_files'] == 0
    # A dangling converted NPC reference is an error even before its zone is visited.
    npc_bad = {'aa_brute': ['s1', 'zz_claw'], 'cc_lost': ['s2', 'nowhere']}
    ck = FakeCheck()
    TB.validate(FakeV(shared, npc_bad, sets), ck)
    assert any('nowhere' in e for e in ck.errors), ck.errors
    # A stale per-set output must not accidentally ship alongside the restored shared pool.
    ck = FakeCheck()
    TB.validate(FakeV(shared, npc, {'data/talents/npc_zz_claw': ['zz_claw']}), ck)
    assert any('forbidden' in e for e in ck.errors)


# ------------------------------------------------------------------------------------------------ save_positions
def test_shared_order_survivors_must_keep_pinned_relative_order():
    pinned = [n for n in SP.SHARED_TALENT_ORDER]
    survivors = [n for n in pinned if n not in ('sabre_claw', 'pyro_flame')]
    errors, warnings = SP.shared_order_problems(survivors, moved=('sabre_claw', 'pyro_flame'))
    assert not errors, errors
    assert any('sabre_claw' in w and 'npc set file' in w for w in warnings)
    # a reorder of the survivors is still an error
    reordered = list(survivors)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    errors, _w = SP.shared_order_problems(reordered, moved=())
    assert errors


def test_shared_order_unmoved_missing_name_is_unreferenced():
    survivors = [n for n in SP.SHARED_TALENT_ORDER if n != 'sabre_claw']
    errors, warnings = SP.shared_order_problems(survivors, moved=())
    assert not errors
    assert any('sabre_claw' in w and 'unreferenced' in w for w in warnings)

def test_review_generic_selector_unions_requirements_for_the_same_file():
    import itertools
    requested = ({'fightstyle_villain'}, {'physical_res'}, {'fightstyle_villain', 'zz_special'})
    for order in itertools.permutations(requested):
        selected = TS.zone_set_files(order)
        assert TS.GENERIC_FILE in selected, selected
        assert selected[TS.GENERIC_FILE] == frozenset({'fightstyle_villain', 'physical_res'})
        assert set().union(*selected.values()) == {'fightstyle_villain', 'physical_res', 'zz_special'}


def test_review_validator_reads_installed_script_roster():
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        script = out / 'Scripts/invented/spawn.py'
        script.parent.mkdir(parents=True)
        script.write_text('spawn("invented_beast")', encoding='utf-8')
        class Index:
            def get(self, name):
                return 'Scripts/invented/spawn.py' if name.lower() == 'scripts/invented/spawn.py' else None
        v = FakeV(['s1'], {'invented_beast': ['zz_claw']}, {})
        v.ctx = SimpleNamespace(out=out, out_index=Index())
        v.converted_zones = lambda: ['invented/yard']
        v.zone_pkg = lambda zone: [('script', 'invented/spawn')]
        ck = FakeCheck()
        TB.validate(v, ck)
        assert any('invented/yard: npcstat invented_beast' in e for e in ck.errors), ck.errors
        v._shared.append('zz_claw')
        v._stats['talents']['.engb'].append('zz_claw')
        ck = FakeCheck()
        TB.validate(v, ck)
        assert not ck.errors, ck.errors
