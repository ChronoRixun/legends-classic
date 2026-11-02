"""SPEC 107 (--anim-enums xml1, xml2-fix [Limits] AnimEnums): the clip transplant, the ANIMTABLE and moveset merges,
the option / ini / DLL coupling and the validator's coupling. Synthetic fixtures: every clip, bone, keyframe and
FightMove below is invented (the enum names are the interoperability identifiers both exes and the DLL use).
The owned-file round trip runs only when LC_OWNED_XML2_COMMON and LC_OWNED_XML1_COMMON name the player's own
Actors/common.IGB and actors/common.igb; it is skipped otherwise."""
import hashlib
import json
import os
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import build_xml1
from test_main_appearance import fixture, raises
from xml1build import anim_enums as AE
from xml1build import fix_ini as FI
from xml1build import igb_anim_merge as M
from xml1build import validate as V
from xml1build.igb_file import IgbError, IgbFile

LIST = [(2, 'i'), (3, 'i'), (4, 'b')]
SCHEMAS = [('igDataList', None, LIST), ('igObjectList', 'igDataList', LIST),
           ('igAnimationList', 'igObjectList', LIST), ('igSkeletonBoneInfoList', 'igObjectList', LIST),
           ('igAnimationBindingList', 'igObjectList', LIST), ('igAnimationTrackList', 'igObjectList', LIST),
           ('igAnimationDatabase', None, [(2, 's'), (5, 'r'), (6, 'r')]),
           ('igSkeletonBoneInfo', None, [(2, 's'), (3, 'i')]),
           ('igSkeleton', None, [(2, 's'), (3, 'b'), (4, 'r'), (5, 'b'), (6, 'i')]),
           ('igAnimationBinding', None, [(2, 'r'), (3, 'b')]),
           ('igAnimationTrack', None, [(2, 's'), (3, 'r'), (4, 'q')]),
           ('igSynthKeySource', None, [(2, 'b'), (3, 'f')]),
           ('igAnimation', None, [(2, 's'), (3, 'i'), (4, 'r'), (5, 'r')])]
BONES = (('synth_root', -1), ('synth_spine', 0), ('synth_head', 1))


def common(clips, *, flip=False, bones=BONES, extra_schema=None):
    """a synthetic shared anim DB: one skeleton 'common_skel', one database listing `clips` ({name: track count}).
    flip reverses the meta object order (XML1's and XML2's common.igb list their types in different orders)."""
    objs, blocks = [], []

    def obj(kind, values):
        objs.append([kind, values])
        return len(objs) - 1

    def blk(data):
        blocks.append(data)
        return ('B', len(blocks) - 1)

    db = obj('igAnimationDatabase', {2: 'common', 5: -1, 6: None})
    lst = obj('igAnimationList', None)
    sk = obj('igSkeleton', {2: 'common_skel', 3: blk(struct.pack('<3f', 1, 2, 3)), 4: None, 5: -1, 6: len(bones)})
    bl = obj('igSkeletonBoneInfoList', None)
    bone_refs = [obj('igSkeletonBoneInfo', {2: n, 3: p}) for n, p in bones]
    objs[bl][1] = {2: len(bone_refs), 3: len(bone_refs), 4: blk(struct.pack(f'<{len(bone_refs)}i', *bone_refs))}
    objs[sk][1][4] = bl
    anims = []
    for c, (name, tracks) in enumerate(clips.items()):
        a = obj('igAnimation', {2: name, 3: c, 4: None, 5: None})
        binds = obj('igAnimationBindingList', None)
        b = obj('igAnimationBinding', {2: sk, 3: blk(struct.pack('<3i', 0, 1, 2))})     # bone indices, not refs
        objs[binds][1] = {2: 1, 3: 1, 4: blk(struct.pack('<i', b))}
        tl = obj('igAnimationTrackList', None)
        trs = []
        for i in range(tracks):
            src = obj('igSynthKeySource', {2: blk(f'{name} keys {i}'.encode() + bytes(3)), 3: 0.5 + i})
            trs.append(obj('igAnimationTrack', {2: bones[i % len(bones)][0], 3: src, 4: [0.0, 0.0, 0.0, 1.0]}))
        objs[tl][1] = {2: len(trs), 3: len(trs), 4: blk(struct.pack(f'<{len(trs)}i', *trs))}
        objs[a][1][4], objs[a][1][5] = binds, tl
        anims.append(a)
    objs[lst][1] = {2: len(anims), 3: len(anims), 4: blk(struct.pack(f'<{len(anims)}i', *anims))}
    objs[db][1][6] = lst
    n = len(objs)
    for _kind, values in objs:
        for k, v in values.items():
            if isinstance(v, tuple):
                values[k] = n + v[1]
    schemas = list(SCHEMAS) + (extra_schema or [])
    if flip:
        schemas = schemas[::-1]
    return fixture(schemas, [tuple(o) for o in objs], blocks)


PC_CLIPS = {'synth_idle': 2, 'synth_walk': 3}
X1_CLIPS = {'synth_idle': 2, 'synth_carry_a': 3, 'synth_walk': 1, 'synth_carry_b': 2}
NEW = ('synth_carry_a', 'synth_carry_b')
# pinned: the synthetic transplant's bytes (a change to the writer's layout or ordering must be deliberate)
SYNTH_SHA256 = '2eea7c0e4330067c5fa19a188c2c6c8212f7c9e8dbba42731c419a988a9ca7df'


def test_transplant_round_trip_keeps_originals_and_adds_named_clips():
    target, source = common(PC_CLIPS), common(X1_CLIPS, flip=True)
    out, rep = M.transplant(target, source, NEW)
    t, s, o = IgbFile(target), IgbFile(source), IgbFile(out)
    assert M.clip_names(o) == ['synth_idle', 'synth_walk', 'synth_carry_a', 'synth_carry_b']
    assert rep['clips'] == list(NEW) and rep['animations_before'] == 2 and rep['animations_after'] == 4
    _db, tlist = M.database(t)
    # every original object / memory block byte-identical at its old reference (the list's count and data aside)
    for r, item in enumerate(t.items):
        if item is not None and r != tlist.ref:
            assert t.data[item.offset:item.offset + item.size] == \
                o.data[o.items[r].offset:o.items[r].offset + o.items[r].size]
        elif item is None and r != tlist.get(4):
            (a, n), (b, m) = t.blocks[r], o.blocks[r]
            assert t.data[a:a + n] == o.data[b:b + m]
    assert o.items[tlist.ref].get(2) == o.items[tlist.ref].get(3) == 4
    # the new clips bind to the TARGET's skeleton, their bone-index arrays and key blobs are not relocated
    skel = M.skeleton(o)
    for ref in o.list_items(tlist.ref)[2:]:
        anim = o.obj(ref)
        binding = o.obj(o.list_items(anim.get(4))[0])
        assert binding.get(2) == skel.ref and o.ref_list(binding.get(3)) == [0, 1, 2]
        for tr in o.list_items(anim.get(5)):
            src = o.obj(o.obj(tr).get(3))
            off, size = o.block(src.get(2))
            assert o.data[off:off + size].startswith(anim.get(2).encode() + b' keys ')
    # meta numbers were remapped by name (the source lists its types in reverse)
    assert {o.items[r].name for r in range(len(t.items), len(o.items)) if o.items[r] is not None} == \
        {'igAnimation', 'igAnimationBindingList', 'igAnimationBinding', 'igAnimationTrackList', 'igAnimationTrack',
         'igSynthKeySource'}
    assert rep['objects_added'] + rep['blocks_added'] == len(o.items) - len(t.items) == rep['closure_items']
    assert len(o.objects_of('igSkeleton')) == 1 and len(o.objects_of('igAnimationDatabase')) == 1
    # the source and target bytes are untouched (pure function)
    assert target == common(PC_CLIPS) and source == common(X1_CLIPS, flip=True)
    assert s.items  # parsed


def test_transplant_output_is_deterministic():
    target, source = common(PC_CLIPS), common(X1_CLIPS, flip=True)
    a, ra = M.transplant(target, source, NEW)
    b, rb = M.transplant(target, source, NEW)
    assert a == b and ra['sha256'] == rb['sha256'] == hashlib.sha256(a).hexdigest()
    assert hashlib.sha256(a).hexdigest() == SYNTH_SHA256, hashlib.sha256(a).hexdigest()
    # the order the names are requested in does not matter: the source database's order is used
    assert M.transplant(target, source, NEW[::-1])[0] == a


def test_transplant_refuses_incompatible_inputs():
    target, source = common(PC_CLIPS), common(X1_CLIPS)
    raises(M.MergeError, lambda: M.transplant(target, common(X1_CLIPS, bones=BONES[:2]), NEW))     # other skeleton
    raises(M.MergeError, lambda: M.transplant(target, source, ('synth_idle',)))                   # already there
    raises(M.MergeError, lambda: M.transplant(target, source, ('synth_absent',)))                 # not in XML1
    raises(M.MergeError, lambda: M.transplant(target, source, ('synth_carry_a', 'SYNTH_CARRY_A')))
    other = common(X1_CLIPS, extra_schema=[('igSynthExtra', None, [(2, 'i')])])
    raises(M.MergeError, lambda: M.transplant(target, other, NEW))                                # type tables differ
    assert issubclass(M.MergeError, IgbError)


def test_igb_appended_matches_rebuilt_and_checks_items():
    data = common(PC_CLIPS)
    g = IgbFile(data)
    assert g.appended() == g.rebuilt({}) == data
    blk = next(iter(g.blocks))
    assert g.appended((), {blk: b'1234' * 5}) == g.rebuilt({blk: b'1234' * 5})
    mem_ref = next(r for r in range(len(g.items)) if g.items[r] is None)
    entry = bytearray(g.entry_bytes(mem_ref))
    struct.pack_into('<i', entry, 8, 6)
    out = IgbFile(g.appended([('memory', bytes(entry), b'synth!')]))
    assert len(out.items) == len(g.items) + 1 and out.block(len(g.items))[1] == 6
    raises(IgbError, lambda: g.appended([('memory', bytes(entry), b'short')]))                  # size != entry
    raises(IgbError, lambda: g.appended([('object', bytes(entry), b'synth!')]))                 # wrong entry kind
    raises(IgbError, lambda: g.appended([('widget', bytes(entry), b'synth!')]))


def test_owned_common_igb_round_trip():
    t_path, s_path = os.environ.get('LC_OWNED_XML2_COMMON'), os.environ.get('LC_OWNED_XML1_COMMON')
    if not (t_path and s_path and Path(t_path).is_file() and Path(s_path).is_file()):
        raise unittest.SkipTest('LC_OWNED_XML2_COMMON / LC_OWNED_XML1_COMMON not set (owned files)')
    target, source = Path(t_path).read_bytes(), Path(s_path).read_bytes()
    out, rep = M.transplant(target, source)            # verify() inside: originals and closures byte-identical
    names = [n.lower() for n in M.clip_names(IgbFile(out))]
    assert all(names.count(c) == 1 for c in M.REQUIRED_CLIPS)
    assert not set(M.KNOWN_ABSENT_IN_XML1) & set(names)
    assert M.transplant(target, source)[0] == out and rep['sha256'] == hashlib.sha256(out).hexdigest()


# ------------------------------------------------------------------------------------------------ ANIMTABLE
def _table(entries):
    root = ET.Element('ANIMTABLE')
    ET.SubElement(root, 'anims', entries)
    return root


def test_shared_anims_merge_appends_the_23_xml1_mappings_only():
    pc = _table({f'ea_synth{i}': f'synth_clip{i}' for i in range(209)})
    x1 = {n: f'Synth_{n[3:]}' for n in AE.BUILTIN_ENUMS}
    x1.update({'ea_mission1': 'mission1', 'ea_synth0': 'xml1_other'})
    out, rep = AE.merge_shared_anims(pc, _table(x1))
    got = AE.table_entries(out)
    assert len(got) == rep['entries'] == 232 and rep['added'] == list(AE.BUILTIN_ENUMS)
    assert got['ea_synth0'] == 'synth_clip0' and 'ea_mission1' not in got        # PC wins; no ea_mission*
    assert got['ea_flyingcarry_pickup_v'] == 'Synth_flyingcarry_pickup_v'        # XML1's value verbatim
    assert rep['x1_only_not_added'] == ['ea_mission1']
    assert len(AE.table_entries(pc)) == 209                                       # input untouched
    raises(AE.AnimEnumError, lambda: AE.merge_shared_anims(pc, _table({'ea_flyingcarry_idle': 'x'})))
    big = _table({f'ea_synth{i}': 'c' for i in range(AE.CAPACITY - 22)})
    raises(AE.AnimEnumError, lambda: AE.merge_shared_anims(big, _table(x1)))


def test_builtin_order_matches_the_dll_ids():
    assert len(AE.BUILTIN_ENUMS) == len(set(AE.BUILTIN_ENUMS)) == 23 and AE.FIRST_ID == 0xD2
    assert AE.BUILTIN_ENUMS.index('ea_flyingcarry_pickup_v') + AE.FIRST_ID == 0xDB
    assert AE.BUILTIN_ENUMS.index('ea_flyingcarry_pickup_a') + AE.FIRST_ID == 0xE1
    assert AE.BUILTIN_ENUMS[-1] == 'ea_jug_grab_throw_right_v' and AE.FIRST_ID + 22 == 0xE8
    assert set(M.KNOWN_ABSENT_IN_XML1.values()) == {'ea_flyingcarry_pickup_v', 'ea_flyingcarry_throwdown_a'}
    assert len(M.REQUIRED_CLIPS) == 21


# ------------------------------------------------------------------------------------------------ moveset_flying
def _style(names, tag='pc'):
    root = ET.Element('FightingStyle')
    for n in names:
        ET.SubElement(root, 'FightMove', {'name': n, 'animenum': f'ea_{n}', 'synth': tag})
    return root


PC_MOVES = [n for n, (side, _w) in AE.MOVESET_FLYING_PRECEDENCE.items() if side != AE.XML1]
X1_ONLY = [n for n, (side, _w) in AE.MOVESET_FLYING_PRECEDENCE.items() if side == AE.XML1]


def test_moveset_flying_precedence_table_is_total_and_applied():
    assert len(AE.MOVESET_FLYING_PRECEDENCE) == 18 and len(X1_ONLY) == 8 and len(PC_MOVES) == 10
    assert all(why for _side, why in AE.MOVESET_FLYING_PRECEDENCE.values())
    pc, x1 = _style(PC_MOVES), _style(PC_MOVES + X1_ONLY, 'xml1')
    out, rep = AE.merge_moveset_flying(pc, x1, xml1_flight_upkeep=False)
    assert [m.get('name') for m in out] == PC_MOVES + X1_ONLY
    assert [m.get('synth') for m in out] == ['pc'] * 10 + ['xml1'] * 8
    assert rep['added_xml1'] == X1_ONLY and rep['replaced_by_xml1'] == []
    up, rep = AE.merge_moveset_flying(pc, x1, xml1_flight_upkeep=True)
    assert rep['replaced_by_xml1'] == ['flying']
    assert [(m.get('name'), m.get('synth')) for m in up][PC_MOVES.index('flying')] == ('flying', 'xml1')
    assert [m.get('name') for m in up] == PC_MOVES + X1_ONLY            # replaced in place, order kept
    # beta 8: xml2-fix rule 45 revision 3 ports XML1's flight upkeep, so the build default replaces `flying`
    assert AE.XML1_FLIGHT_UPKEEP is True
    _, rep = AE.merge_moveset_flying(pc, x1)
    assert rep['replaced_by_xml1'] == ['flying']
    raises(AE.AnimEnumError, lambda: AE.merge_moveset_flying(_style(PC_MOVES + ['synthnode']), x1))   # unlisted
    raises(AE.AnimEnumError, lambda: AE.merge_moveset_flying(_style(PC_MOVES + ['fastball']), x1))    # XML1-only on PC
    raises(AE.AnimEnumError, lambda: AE.merge_moveset_flying(_style(PC_MOVES[1:]), x1))               # PC node gone


# ------------------------------------------------------------------------------------------------ option / ini / DLL
def _dll_block(names):
    return AE.DLL_MARKER + struct.pack('<H', len(names)) + b''.join(n.encode() + b'\0' for n in names)


def test_anim_enums_option_on_by_default_and_ini_written_only_when_recorded():
    # 0.4.1-beta.1 (beta 8 candidate 080c): on by default, with the grab lifecycle (rule 45 revision 3 needs it)
    assert build_xml1.parse_args(['--out', '.']).anim_enums == 'xml1'
    assert build_xml1.parse_args(['--out', '.', '--anim-enums', 'off', '--grab-carry', 'xml2']).anim_enums == 'off'
    raises(SystemExit, lambda: build_xml1.parse_args(['--out', '.', '--anim-enums', 'off']))   # grab-carry xml1 needs it
    assert build_xml1.CONTENT_OPTS['anim_enums'] == ('characters', 'xml1')
    assert 'AnimEnums' in FI.PORT_OWNED['Limits'] and 'AnimEnums' in FI.RELEASE_18_KEYS['Limits']
    assert FI.ANIM_ENUMS == AE.LIMIT_VALUE == '512'
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        (out / '_build').mkdir()
        for value, written in (('xml1', True), ('off', False), (None, False)):
            record = {'build': {key: default for key, (_, default) in build_xml1.CONTENT_OPTS.items()}}
            if value:
                record['build']['anim_enums'] = value
            else:
                record['build'].pop('anim_enums')
            (out / '_build' / 'report.json').write_text(json.dumps(record), encoding='utf-8')
            keys = FI.port_keys(out)
            assert (keys['Limits'].get('AnimEnums') == '512') == written
            assert ('AnimEnums' in FI.dropped_keys(keys).get('Limits', [])) == (not written)
            merged = FI.merge_text('[Limits]\nAnimEnums=512\nKeepMe=7\n', keys, FI.dropped_keys(keys))
            assert ('AnimEnums=512' in merged) == written and 'KeepMe=7' in merged


def test_anim_enums_dll_gate_needs_the_marked_table():
    keys = {'Limits': {'AnimEnums': '512'}}
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        assert FI.old_fix_keys(dll, keys) == []                                   # source-only build: no DLL
        dll.write_bytes(b'MZ' + 'IGBCache'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Limits] AnimEnums', '[Limits] AnimEnums (AnimEnums table)']
        dll.write_bytes(b'MZ' + 'AnimEnums'.encode('utf-16le'))                    # key, no table
        assert FI.old_fix_keys(dll, keys) == ['[Limits] AnimEnums (AnimEnums table)']
        dll.write_bytes(b'MZ' + 'AnimEnums'.encode('utf-16le') + _dll_block(AE.BUILTIN_ENUMS[::-1]))
        assert FI.old_fix_keys(dll, keys) == ['[Limits] AnimEnums (AnimEnums table)']
        dll.write_bytes(b'MZ' + 'AnimEnums'.encode('utf-16le') + _dll_block(AE.BUILTIN_ENUMS) + b'\0\0tail')
        assert FI.old_fix_keys(dll, keys) == []
        assert FI.old_fix_keys(dll, {'Limits': {}}) == []
        assert AE.dll_builtin_names(dll.read_bytes()) == AE.BUILTIN_ENUMS
        assert AE.dll_builtin_names(b'MZ') is None and AE.dll_builtin_names(AE.DLL_MARKER + b'\x05\x00ea_a\0') is None


class _Check:
    def __init__(self):
        self.errors, self.warnings, self.counts, self.details = [], [], {}, {}

    def error(self, m):
        self.errors.append(m)

    def warn(self, m):
        self.warnings.append(m)

    def set(self, k, v):
        self.counts[k] = v


def test_validator_couples_the_builtin_names_to_the_dll_table():
    with tempfile.TemporaryDirectory() as td:
        me = SimpleNamespace(ctx=SimpleNamespace(out=Path(td)))
        ck = _Check()
        assert V.Validator._v7_anim_enum_names(me, ck) == set(AE.BUILTIN_ENUMS)
        assert not ck.errors and len(ck.warnings) == 1 and ck.counts['anim_enums_dll_checked'] == 0   # no DLL
        dll = Path(td) / 'dinput.dll'
        for body, ok in ((_dll_block(AE.BUILTIN_ENUMS), True), (_dll_block(AE.BUILTIN_ENUMS[:-1]), False),
                         (b'no table', False)):
            dll.write_bytes(b'MZ' + body)
            ck = _Check()
            V.Validator._v7_anim_enum_names(me, ck)
            assert (not ck.errors) == ok and not ck.warnings and ck.counts['anim_enums_dll_checked'] == 1
    assert V.DEFERRED_ANIM_ENUMS.match('ea_flyingcarry_idle') and V.DEFERRED_ANIM_ENUMS.match('ea_jug_grab_hold_v')
