"""Synthetic compact trivia persistence and old-save identity regressions."""
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from test_lcsave import make_build, make_old_save, _era_model, _xmlb
from lcsave import binds, catalogue, convert, oldsave, container, lcfiles, keys, dump


def trivia_env(folder, *, compact=True, sizes=None):
    root = make_build(os.path.join(folder, 'build'))
    tv = ET.Element('trivia', **({'persistence': 'compact'} if compact else {}))
    for act, count in sizes or [(1, 9), (3, 9), (5, 8), (6, 8), (8, 8), (9, 8)]:
        for q in range(count):
            ET.SubElement(tv, 'question', act=str(act), text=f'invented question {act}/{q}')
    _xmlb(os.path.join(root, 'Data', 'trivia.engb'), tv)
    b = binds.Binds(root)
    model = _era_model(b, b)
    cat = catalogue.Catalogue()
    cat.update(catalogue.tables_from_hashes(b.hash_tables()), 13)
    ep, cp = Path(folder) / 'eras.json', Path(folder) / 'cat.json'
    ep.write_text(json.dumps(model)); assert json.loads(ep.read_text()) == model
    cat.save(str(cp))
    return convert.Environment(root, eras_path=str(ep), catalogue_path=str(cp))


def test_frontend_marks_compact_without_changing_act_split():
    from xml1build import frontend
    class Fake:
        def read_x1_xml(self, rel):
            root = ET.Element('trivia')
            for i in range(50):
                q = ET.SubElement(root, 'question', text=f'invented question {i}')
                ET.SubElement(q, 'answer', text='invented answer', correct='true')
            return root
        def research_json(self, rel):
            return {str(a): {'acts': [a]} for a in (1, 3, 5, 6, 8, 9)}
        def x1_zones(self): return [str(a) for a in (1, 3, 5, 6, 8, 9)]
        def x1_path(self, rel):
            class Source:
                def read_bytes(self): return b'triviaMenu()'
            return Source()
    root, report = frontend.trivia_tree(Fake())
    assert root.get('persistence') == 'compact'
    assert report['split'] == {1: 9, 3: 9, 5: 8, 6: 8, 8: 8, 9: 8}
    assert [q.get('text') for q in root] == [f'invented question {i}' for i in range(50)]


def blank_model(env):
    m = make_old_save(def_count=len(env.binds.item), zone=False)
    m['game']['trivia'] = [0] * 8
    return m


def test_all_questions_survive_two_native_saves_and_loads():
    with tempfile.TemporaryDirectory() as d:
        env = trivia_env(d)
        assert len(env.binds.trivia_bits) == 50
        for question, bit in env.binds.trivia_bits.items():
            m = blank_model(env); m['game']['trivia'][bit // 32] = 1 << (bit % 32)
            wanted = env.id_of('TRIV', keys.key_hash(*env.binds.key_trivia(*question)))
            retained = b''
            for _ in range(2):
                res = convert.old_stream_to_new(oldsave.write_slot(m), env, retained_file=retained, now=0)
                assert res.refused is None, res.refused
                assert container.read_file(res.file_bytes)['sections']['GAME']['data']['trivia'] == [wanted]
                back, _ = convert.reverse_slot(res.file_bytes, env)
                assert back['game']['trivia'] == m['game']['trivia']
                m, retained = back, res.file_bytes


def test_legacy_sparse_bits_keep_identities_in_compact_build():
    with tempfile.TemporaryDirectory() as d:
        env = trivia_env(d); m = blank_model(env)
        for act, q in [(1, 8), (3, 8), (5, 7)]:
            bit = (act - 1) * 50 + q
            m['game']['trivia'][bit // 32] |= 1 << (bit % 32)
        res = convert.convert_slot(oldsave.write_slot(m), 'synthetic.save', env, now=0)
        assert res.refused is None, res.refused
        wanted = {env.id_of('TRIV', keys.key_hash(str(a), f'q{q+1}')) for a, q in [(1, 8), (3, 8), (5, 7)]}
        assert set(container.read_file(res.file_bytes)['sections']['GAME']['data']['trivia']) == wanted
        back, _ = convert.reverse_slot(res.file_bytes, env)
        assert back['game']['trivia'] == [1 << 8 | 1 << 17 | 1 << 25] + [0] * 7
        assert dump.dump_old(back, env, dict(start=13, items=13), native=True)['game']['trivia'] == dump.dump_new(res.file_bytes, env)['game']['trivia']
        path = Path(d) / 'synthetic.save'; path.write_bytes(oldsave.write_slot(m))
        assert path.read_bytes() == oldsave.write_slot(m)
        report = convert.verify_file(str(path), env)
        assert report['ok'], report
        assert not report['reverse_expected_identical']
        again = convert.old_stream_to_new(oldsave.write_slot(back), env, now=0)
        assert again.refused is None, again.refused
        assert set(container.read_file(again.file_bytes)['sections']['GAME']['data']['trivia']) == wanted


def test_legacy_build_keeps_sparse_layout_and_bind_rule():
    with tempfile.TemporaryDirectory() as d:
        env = trivia_env(d, compact=False)
        assert env.binds.trivia_bits[(5, 7)] == 207
        files, problems = lcfiles.bind_files(env.binds.build, env.catalogue)
        assert not problems
        assert lcfiles.read_lcbind(files['Data/trivia.lcbind'])['lists'][0][1] == 1


def test_compact_binding_rule_and_native_budget_boundaries():
    with tempfile.TemporaryDirectory() as d:
        env = trivia_env(d, sizes=[(a, 50) for a in (1, 3, 6, 8, 9)])
        assert env.binds.trivia_bits[(9, 49)] == 249
        files, problems = lcfiles.bind_files(env.binds.build, env.catalogue)
        assert not problems
        assert lcfiles.read_lcbind(files['Data/trivia.lcbind'])['lists'][0][1] == 2
        m = blank_model(env); m['game']['trivia'][7] = 1 << 25
        res = convert.old_stream_to_new(oldsave.write_slot(m), env, now=0)
        assert res.refused is None, res.refused
        back, _ = convert.reverse_slot(res.file_bytes, env)
        assert back['game']['trivia'] == m['game']['trivia']
    for sizes in [[(a, 50) for a in range(1, 6)] + [(9, 1)], [(1, 51)], [(0, 1)]]:
        with tempfile.TemporaryDirectory() as d:
            try: trivia_env(d, sizes=sizes)
            except ValueError: pass
            else: assert False, 'invalid trivia mapping accepted'
    with tempfile.TemporaryDirectory() as d:
        env = trivia_env(d); m = blank_model(env); m['game']['trivia'][1] = 1 << 18 # bit 50, not assigned
        result = convert.old_stream_to_new(oldsave.write_slot(m), env, now=0)
        assert 'native trivia bit 50' in result.refused


def export_vectors(folder):
    out = Path(folder); out.mkdir(parents=True, exist_ok=True)
    env = trivia_env(str(out))
    files, problems = lcfiles.write_build_files(env.binds.build, 13, env.catalogue, env.model)
    assert not problems
    def write(p, data):
        p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data); assert p.read_bytes() == data
    for rel, data in files.items(): write(Path(env.binds.build) / rel, data)
    rows = []
    for (act, q), bit in env.binds.trivia_bits.items():
        name = f'question_{act}_{q}'
        m = blank_model(env); m['game']['trivia'][bit // 32] = 1 << (bit % 32)
        raw = oldsave.write_slot(m)
        res = convert.old_stream_to_new(raw, env, now=-11644473600, campaign_serial=17, save_sequence=2)
        assert res.refused is None, res.refused
        write(out / name / 'input.raw', raw); write(out / name / 'expected.lcsave', res.file_bytes)
        rows.append(f'{name}\tbuild\tnative-trivia\t2\n')
        back, _ = convert.reverse_slot(res.file_bytes, env)
        write(out / (name + '_reverse') / 'input.lcsave', res.file_bytes)
        write(out / (name + '_reverse') / 'expected.old', oldsave.write_slot(back))
        rows.append(f'{name}_reverse\tbuild\treverse\t2\n')
        second = convert.old_stream_to_new(oldsave.write_slot(back), env, retained_file=res.file_bytes,
                                           now=-11644473600, campaign_serial=17, save_sequence=3)
        assert second.refused is None, second.refused
        write(out / (name + '_resave') / 'input.lcsave', res.file_bytes)
        write(out / (name + '_resave') / 'expected.lcsave', second.file_bytes)
        rows.append(f'{name}_resave\tbuild\tcampaign\t3\n')
    m = blank_model(env)
    for bit in (8, 108, 207): m['game']['trivia'][bit // 32] |= 1 << (bit % 32)
    raw = oldsave.write_slot(m)
    res = convert.convert_slot(raw, 'synthetic.save', env, now=-11644473600)
    assert res.refused is None, res.refused
    write(out / 'legacy_sparse' / 'input.raw', raw); write(out / 'legacy_sparse' / 'expected.lcsave', res.file_bytes)
    rows.append('legacy_sparse\tbuild\tlegacy-import\t1\n')
    write(out / 'cases.tsv', ''.join(rows).encode())
    print(f'verified {len(rows)} synthetic parity vectors')


if __name__ == '__main__':
    import sys
    export_vectors(sys.argv[1])
