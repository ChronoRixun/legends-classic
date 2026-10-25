"""Synthetic metadata cases; no source game data."""
import copy
import xml.etree.ElementTree as ET
from xml1build import semi_auto as S


def fixture():
    stats = ET.fromstring('<list><stats name="TestGuard" weapon="testgun"/></list>')
    weapons = ET.fromstring('<list><weapon name="testgun" type="projectile" recoiltime="0.625" range="400" powerstyle="teststyle"/></list>')
    styles = {'teststyle': ET.fromstring('<style><FightMove name="power_attack" handler="ch_weapon_semi_auto"/></style>')}
    return stats, weapons, styles


def test_source_recoil_bits_and_input_unchanged():
    args = fixture()
    before = [ET.tostring(args[0]), ET.tostring(args[1]), ET.tostring(args[2]['teststyle'])]
    result = S.contract(*args)
    assert result['records'] == ['testguard|3f200000|43c80000|3f800000|00000000']
    assert S.ini_sections(result)['NpcSemiAuto']['W1'] == result['records'][0]
    assert before == [ET.tostring(args[0]), ET.tostring(args[1]), ET.tostring(args[2]['teststyle'])]


def test_distinct_weapon_semantics_are_not_collapsed():
    for key, value in [('rapidfire', 'true'), ('continuousbeam', 'true'),
                       ('warmuptime', '0.5'), ('recoiltime', 'nan'), ('recoiltime', '-1'),
                       ('type', 'bullet'), ('range', '0'), ('range', '300.5'), ('bursttime', 'nan')]:
        args = fixture()
        args[1][0].set(key, value)
        result = S.contract(*args)
        assert not result['records'] and len(result['excluded']) == 1


def test_source_handler_and_actor_override_required():
    args = fixture()
    args[0][0].set('powerstyle', 'another_style')
    assert not S.contract(*args)['records']
    args = fixture()
    args[2]['teststyle'][0].set('handler', 'another_handler')
    assert not S.contract(*args)['records']


def test_canonical_names_sort_before_the_separator():
    data = {'schema': 2, 'records': ['guardb|3f200000|43c80000|3f800000|00000000', 'guard|3f000000|43c80000|3f800000|00000000']}
    section = S.ini_sections(data)['NpcSemiAuto']
    assert section['W1'].startswith('guard|') and section['W2'].startswith('guardb|')


def test_contract_refuses_duplicate_or_invalid_records():
    for rows in [['guard|7f800000'], ['guard|00000000'], ['guard|3f000000'] * 2,
                 ['bad|name|3f000000'], ['guard|bf000000'], ['guard|42800000']]:
        try:
            S.ini_sections({'schema': 2, 'records': [row + '|43c80000|3f800000|00000000' for row in rows]})
        except ValueError:
            pass
        else:
            raise AssertionError(rows)
    args = fixture()
    args[0].append(copy.deepcopy(args[0][0]))
    try:
        S.contract(*args)
    except ValueError:
        pass
    else:
        raise AssertionError('duplicate actor accepted')


def test_source_range_burst_and_old_schema_rejection():
    args = fixture()
    args[1][0].set('bursttime', '1.5')
    row = S.contract(*args)['records'][0]
    assert row.endswith('|43c80000|3fc00000|00000000')
    for data in ({'schema': 1, 'records': ['guard|3f000000']},
                 {'schema': 2, 'records': ['guard|3f000000|42960000|00000000|00000000']},
                 {'schema': 2, 'records': ['guard|3f000000|7f800000|3f800000|00000000']}):
        try:
            S.ini_sections(data)
        except ValueError:
            pass
        else:
            raise AssertionError(data)


def test_source_leader_is_not_lost_with_weapon_brain_selection():
    args = fixture()
    args[0][0].set('leader', 'TRUE')
    row = S.contract(*args)['records'][0]
    assert row.endswith('|00000001')
    assert S.ini_sections({'schema': 2, 'records': [row]})['NpcSemiAuto']['W1'] == row
    try:
        S.ini_sections({'schema': 2, 'records': [row[:-1] + '2']})
    except ValueError:
        pass
    else:
        raise AssertionError('unknown leader flags accepted')


def test_authored_gun_ai_metadata_is_not_silently_removed():
    for key, value in [('aitype', 'projectile'), ('aireusetime', '3')]:
        args = fixture()
        args[2]['teststyle'][0].set(key, value)
        result = S.contract(*args)
        assert not result['records'] and 'authored gun AI' in result['excluded'][0]['reason']


class _Ctx:
    """the characters-stage context surface build_contract uses (XML1 sources by relative path, _build metadata)."""

    def __init__(self, root, sources):
        self.root, self.sources, self.warnings = root, sources, []

    def read_x1_xml(self, rel):
        if rel not in self.sources:
            raise KeyError(f'XML1 has no {rel}')
        return self.sources[rel]

    def x1_path(self, rel):
        return rel if rel in self.sources else None

    def warn(self, msg):
        self.warnings.append(msg)

    def write_meta(self, name, obj):
        import json
        from pathlib import Path
        p = Path(self.root, '_build', name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj), encoding='utf-8')
        return p


def _sources():
    stats, weapons, styles = fixture()
    stats.append(ET.fromstring('<stats name="OtherGuard" weapon="testgun"/>'))
    return {'data/npcstat.eng': stats, 'data/weapons/weapons.eng': weapons,
            'data/powerstyles/teststyle.eng': styles['teststyle']}


def test_build_contract_records_the_source_rows_for_the_build_and_port_keys_write_them():
    import tempfile
    from pathlib import Path
    from xml1build import fix_ini as FI
    with tempfile.TemporaryDirectory() as td:
        data = S.build_contract(_Ctx(td, _sources()), {'testguard'})
        assert data['records'] == ['testguard|3f200000|43c80000|3f800000|00000000']
        assert {'actor': 'otherguard', 'reason': 'actor not in this build'} in data['excluded']
        assert Path(td, '_build', S.CONTRACT_FILE).is_file()
        keys = FI.port_keys(td)
        assert keys['Game']['NpcPowerRule'] == 'xml1' and keys['Game']['NpcSemiAuto'] == FI.NPC_SEMI_AUTO == 'xml1'
        assert keys['NpcSemiAuto'] == {'Count': '1', 'W1': data['records'][0]}
        dropped = FI.dropped_keys(keys)   # a rebuild with fewer rows drops the stale higher rows
        assert 'NpcSemiAuto' not in dropped.get('Game', []) and dropped['NpcSemiAuto'][0] == 'W2'


def test_no_or_bad_contract_writes_no_weapon_brain_keys_and_drops_stale_ones():
    import json
    import tempfile
    from pathlib import Path
    from xml1build import fix_ini as FI
    with tempfile.TemporaryDirectory() as td:
        ctx = _Ctx(td, {k: v for k, v in _sources().items() if 'weapons' not in k})
        assert S.build_contract(ctx, None) is None and ctx.warnings
        for content in (None, 'not json', json.dumps({'schema': 2, 'records': []}),
                        json.dumps({'schema': 1, 'records': ['guard|3f000000']})):
            path = Path(td, '_build', S.CONTRACT_FILE)
            if content is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
            keys = FI.port_keys(td)
            assert 'NpcSemiAuto' not in keys['Game'] and 'NpcSemiAuto' not in keys
            assert keys['Game']['NpcPowerRule'] == 'xml1'
            dropped = FI.dropped_keys(keys)
            assert 'NpcSemiAuto' in dropped['Game'] and dropped['NpcSemiAuto'][:2] == ['Count', 'W1']
