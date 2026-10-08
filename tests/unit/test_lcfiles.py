"""lcsave.lcfiles - the save-format data files of a build (SPEC 70; SPEC-new-save 3.4/5.3): the catalogue.lcc /
legacy.lcm / .lcbind writers and readers, the bind-row conventions and the content fingerprint. Invented names
only (a tiny synthetic build, shared with test_lcsave)."""
import os
import struct
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lcsave import binds as bindsmod, catalogue as catmod, keys, lcfiles as LF, legacy as legmod  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_lcsave as T  # noqa: E402  the synthetic build (invented names)


# ------------------------------------------------------------------------------------------------ helpers
def synthetic(tmp, content_version=1):
    """(build dir, Binds, Catalogue of the synthetic build, key texts)"""
    T.make_build(str(tmp))
    b = bindsmod.Binds(str(tmp))
    cat = catmod.Catalogue()
    cat.update(catmod.tables_from_hashes(b.hash_tables()), content_version)
    return b, cat, LF.key_text_index(b)


def write_set(tmp, cat, texts, cv=15):
    files, problems = LF.bind_files(str(tmp), cat)
    files[LF.CATALOGUE_LCC.replace(os.sep, '/')] = LF.write_catalogue_lcc(cat, texts, cv)
    for rel, blob in files.items():
        p = os.path.join(str(tmp), rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(blob)
    return files, problems


def lcc_rows(read):
    return {tag: [(e['id'], e['key']) for e in es] for tag, es in read['domains'].items()}


# ------------------------------------------------------------------------------------------------ catalogue.lcc
def test_catalogue_lcc_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        b, cat, texts = synthetic(td)
        blob = LF.write_catalogue_lcc(cat, texts, 15)
        back = LF.read_catalogue_lcc(blob)
        assert back['revision'] == cat.revision and back['content_version'] == 15
        assert set(back['domains']) == set(cat.data['domains'])
        for tag, entries in back['domains'].items():
            number = keys.DOMAIN_NUMBER[tag]
            assert [e['id'] for e in entries] == sorted(x['id'] for x in entries)                        # ascending id
            for e in entries:
                assert keys.id_domain(e['id']) == number and e['key']                   # every key known here
                assert e['flags'] == 0 and e['successor'] == 0 and e['aliases'] == []
        # a key decodes back to the canonical bytes the hash is of
        stat = dict(lcc_rows(back)['STAT'])
        assert stat[cat.lookup('STAT', keys.key_hash('hero_a'))] == b'hero_a'
        taln = dict(lcc_rows(back)['TALN'])
        assert taln[cat.lookup('TALN', keys.key_hash('shared', 'sh_might'))] == b'shared/sh_might'
        assert LF.read_catalogue_lcc(blob) == back                                      # deterministic parse


def test_catalogue_lcc_rejects_bad_files():
    with tempfile.TemporaryDirectory() as td:
        b, cat, texts = synthetic(td)
        blob = bytearray(LF.write_catalogue_lcc(cat, texts, 15))
        for bad, why in ((b'BADMAGIC', 'magic'),):
            try:
                LF.read_catalogue_lcc(bad + bytes(blob[8:]))
                assert False, why
            except LF.LCFileError:
                pass
        blob[-1] ^= 0xFF                                                                # CRC no longer matches
        try:
            LF.read_catalogue_lcc(bytes(blob))
            assert False, 'crc'
        except LF.LCFileError:
            pass
        try:
            LF.read_catalogue_lcc(bytes(blob)[:20])
            assert False, 'truncated'
        except LF.LCFileError:
            pass


def test_catalogue_lcc_empty_key_for_content_the_build_does_not_know():
    with tempfile.TemporaryDirectory() as td:
        b, cat, texts = synthetic(td)
        ghost = keys.key_hash('old_thing_gone_from_the_build')
        cat.add('ITEM', ghost)                                                          # an earlier era's item
        blob = LF.write_catalogue_lcc(cat, texts, 15)
        back = LF.read_catalogue_lcc(blob)
        by_id = {e['id']: e for e in back['domains']['ITEM']}
        assert by_id[cat.lookup('ITEM', ghost)]['key'] == b''                           # resolves by id only
        assert all(e['key'] for e in back['domains']['ITEM'] if e['id'] != cat.lookup('ITEM', ghost))


# ------------------------------------------------------------------------------------------------ .lcbind
def test_lcbind_roundtrip_and_row_conventions():
    with tempfile.TemporaryDirectory() as td:
        b, cat, texts = synthetic(td)
        files, problems = LF.bind_files(td, cat)
        assert not problems                                                             # every key catalogued
        assert set(files) == {'Data/items.lcbind', 'Data/herostat.lcbind', 'Data/npcstat.lcbind',
                              'Data/shared_talents.lcbind', 'Data/talents/hero_a.lcbind',
                              'Data/talents/hero_b.lcbind', 'Data/missions/missions.lcbind',
                              'Data/missions/act_x.lcbind', 'Data/dangerroom.lcbind',
                              'Data/review_paths.lcbind', 'Data/xtraction_points.lcbind',
                              'Data/trivia.lcbind'}
        read = {rel: LF.read_lcbind(blob) for rel, blob in files.items()}
        # every header carries the SHA-1 of the data file it describes
        for rel, r in read.items():
            data = os.path.join(td, rel[:-7].replace('/', os.sep))
            for ext in ('.engb', '.xmlb'):
                if os.path.isfile(data + ext):
                    assert r['sha1'] == keys.hashlib.sha1(open(data + ext, 'rb').read()).digest()
        lists = {tag: rows for tag, rule, rows in read['Data/herostat.lcbind']['lists']}
        assert [r[1] for r in lists['STAT']] == [1, 2]                                  # herostat from index 1
        assert all(g == 0 for g, p, i, k in lists['STAT'])
        assert sorted((g, p) for g, p, i, k in lists['COST']) == \
            sorted((gi, s) for gi in (1, 2) for s in range(9))                          # every (hero, slot)
        npc = {t: rows for t, rule, rows in read['Data/npcstat.lcbind']['lists']}['STAT']
        assert [p for g, p, i, k in npc] == [3, 4, 5]                                   # npcstat continues
        items = {t: rows for t, rule, rows in read['Data/items.lcbind']['lists']}
        by_pos = {p: (g, k) for g, p, i, k in items['ITEM']}
        assert by_pos[0][0] == 1 and by_pos[1][0] == 2 and by_pos[3][0] == 3            # belt/gloves/armor
        assert by_pos[2][0] == 0                                                        # no class -> group 0
        assert by_pos[0][1] == keys.canonical_key('belt_x')
        assert [p for g, p, i, k in items['ENHC']] == list(range(len(b.enhancement)))
        assert items['NAMB'] == [(1, 0, cat.lookup('NAMB', keys.key_hash('belt', 'cls_belt_a')),
                                  keys.canonical_key('belt', 'cls_belt_a'))]
        shared = {t: rows for t, rule, rows in read['Data/shared_talents.lcbind']['lists']}['TALN']
        assert [(g, p) for g, p, i, k in shared] == [(0, i) for i in range(len(b.shared_talent))]
        hero_a = {t: rows for t, rule, rows in read['Data/talents/hero_a.lcbind']['lists']}['TALN']
        assert [(g, p) for g, p, i, k in hero_a] == [(1, i) for i in range(3)]          # group = stats index
        objv = {t: rows for t, rule, rows in read['Data/missions/act_x.lcbind']['lists']}['OBJV']
        assert all(g == 0 for g, p, i, k in objv)                                       # mission file 0
        drcs = {t: rows for t, rule, rows in read['Data/dangerroom.lcbind']['lists']}
        assert all(rule == 1 for tag, rule, rows in read['Data/dangerroom.lcbind']['lists'])
        triv = {t: rows for t, rule, rows in read['Data/trivia.lcbind']['lists']}['TRIV']
        assert all(g >= 1 for g, p, i, k in triv)                                       # group = act
        # ids resolve through the catalogue
        stat0 = lists['STAT'][0]
        assert stat0[2] == cat.lookup('STAT', keys.key_hash('hero_a')) != 0


def test_lcbind_id0_for_a_key_the_catalogue_does_not_know():
    with tempfile.TemporaryDirectory() as td:
        b = bindsmod.Binds(T.make_build(str(td)) and td)
        cat = catmod.Catalogue()                                                        # empty: nothing known
        files, problems = LF.bind_files(td, cat)
        assert problems                                                                 # reported for V39
        items = {t: rows for t, rule, rows in LF.read_lcbind(files['Data/items.lcbind'])['lists']}['ITEM']
        assert all(i == 0 and k for g, p, i, k in items)                                # id 0, key carried


# ------------------------------------------------------------------------------------------------ legacy.lcm
def synthetic_model(b):
    """a tiny era model of the synthetic build (reference = the build itself, one older era with a moved
    talent and one zone delta)"""
    tabs = b.hash_tables()
    tabs['content_version'] = 3
    older = dict(tabs)
    older['TALN_shared'] = list(reversed(tabs['TALN_shared']))                          # a moved table
    hold = {keys.key_hash(h): [0, 1] for h in [b.stat[1]]}
    zones = {}
    zlist = sorted(b.zone_names)
    if zlist:
        zones[keys.key_hash(zlist[0])] = {'map': [1, 0], 'ambiguous': [2]}
    return {'reference': tabs, 'reference_release': 'x',
            'eras': {'2': {'TALN_shared': older['TALN_shared'], 'hero_count': tabs['hero_count'],
                           'conversation_digest': '', 'hero_shared_holdable': hold, 'zones': zones},
                     '3': {'hero_count': tabs['hero_count'], 'conversation_digest': '',
                           'hero_shared_holdable': hold, 'zones': {}}}}


def test_legacy_lcm_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        b, cat, texts = synthetic(td)
        model = synthetic_model(b)
        blob = LF.write_legacy_lcm(model, cat)
        back = LF.read_legacy_lcm(blob)
        assert back['map_id'] == 3 and back['catalogue_revision'] == cat.revision
        assert [e['content_version'] for e in back['eras']] == [2, 3]                   # ascending
        ref = back['eras'][1]
        assert back['checks'] == {'hero_blocks': b.hero_count, 'courses': len(b.course),
                                  'grades': len(b.grade), 'objectives': len(b.objective)}
        stat = ref['tables']['STAT']
        assert stat[0] == (0, 0, 0)                                                     # index 0 reserved
        assert stat[1][2] == cat.lookup('STAT', keys.key_hash('hero_a'))
        old = back['eras'][0]
        shared2 = [i for g, p, i in old['tables']['TALN'] if g == 0]
        shared_ref = [i for g, p, i in ref['tables']['TALN'] if g == 0]
        assert shared2 == list(reversed(shared_ref))                                    # the era's own order
        if b.zone_names:
            (zid, delta), = old['zones'].items()
            assert zid == cat.lookup('ZONE', keys.key_hash(sorted(b.zone_names)[0]))
            assert delta == {'map': [1, 0], 'ambiguous': [2]}
        hero_id = cat.lookup('STAT', keys.key_hash('hero_a'))
        assert old['hero_shared_holdable'] == {hero_id: [0, 1]}
        assert old['hero_count'] == b.hero_count
        ranges = old['enhc_ranges']
        assert ranges['prefix'][0] == 0 and ranges['own'][1] == len(b.enhancement)
        enhc_ids = {i for g, p, i in old['tables']['ENHC']}
        assert all(i in enhc_ids for g, p, i in old['tables']['IOWN'] + old['tables']['TOWN'])
        # a hash the catalogue does not know stops the writer
        model['eras']['2']['TALN_shared'] = [keys.key_hash('never_catalogued')] + \
            list(model['eras']['2']['TALN_shared'][1:])
        try:
            LF.write_legacy_lcm(model, cat)
            assert False, 'uncatalogued era hash'
        except LF.LCFileError:
            pass


def test_legacy_lcm_of_the_shipped_model_resolves_every_hash():
    cat = catmod.Catalogue.load()
    model = legmod.load_eras()
    blob = LF.write_legacy_lcm(model, cat)
    back = LF.read_legacy_lcm(blob)
    assert back['map_id'] == 13 and [e['content_version'] for e in back['eras']] == [5, 6, 7, 8, 9, 11, 12, 13]
    assert back['checks'] == {'hero_blocks': 21, 'courses': 62, 'grades': 6, 'objectives': 177}
    ref = [e for e in back['eras'] if e['content_version'] == 13][0]
    assert len(ref['tables']['STAT']) == 236 and len(ref['tables']['DRCS']) == 62
    assert all(i or p == 0 for g, p, i in ref['tables']['STAT'])                        # only index 0 has id 0
    zoned = [e for e in back['eras'] if e['zones']]
    assert zoned and all(cat.entry_of(zid) for e in zoned for zid in e['zones'])


# ------------------------------------------------------------------------------------------------ the whole set + the fingerprint
def test_write_build_files_and_fingerprint():
    with tempfile.TemporaryDirectory() as td:
        b, cat, texts = synthetic(td)
        assert LF.content_fingerprint(td) is None                                       # nothing written yet
        files, problems = write_set(td, cat, texts)
        assert not problems
        fp = LF.content_fingerprint(td)
        assert fp and len(fp) == 64
        write_set(td, cat, texts)                                                       # deterministic rewrite
        assert LF.content_fingerprint(td) == fp
        # the fingerprint covers the catalogue and every bind
        p = Path(td) / 'Data' / 'lcsave' / 'catalogue.lcc'
        p.write_bytes(p.read_bytes()[:-1] + bytes([p.read_bytes()[-1] ^ 1]))
        assert LF.content_fingerprint(td) != fp
        write_set(td, cat, texts)
        assert LF.content_fingerprint(td) == fp
        p = Path(td) / 'Data' / 'trivia.lcbind'
        raw = bytearray(p.read_bytes())
        raw[-5] ^= 1
        p.write_bytes(bytes(raw))
        assert LF.content_fingerprint(td) != fp
        # header corruption is caught by the readers
        try:
            LF.read_lcbind(p.read_bytes())
            assert False, 'crc'
        except LF.LCFileError:
            pass
