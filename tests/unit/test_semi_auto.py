"""Synthetic metadata cases; no source game data."""
import copy
import xml.etree.ElementTree as ET
from xml1build import semi_auto as S

PROJECTILE = '|00000000|00000002|00000000|00000000'   # no warm-up, projectile type


def fixture():
    stats = ET.fromstring('<list><stats name="TestGuard" weapon="testgun"/></list>')
    weapons = ET.fromstring('<list><weapon name="testgun" type="projectile" recoiltime="0.625" range="400" powerstyle="teststyle"/></list>')
    styles = {'teststyle': ET.fromstring('<style><FightMove name="power_attack" handler="ch_weapon_semi_auto"/></style>')}
    return stats, weapons, styles


def refused(data):
    try:
        S.ini_sections(data)
    except ValueError:
        return True
    return False


def test_source_recoil_bits_and_input_unchanged():
    args = fixture()
    before = [ET.tostring(args[0]), ET.tostring(args[1]), ET.tostring(args[2]['teststyle'])]
    result = S.contract(*args)
    assert result['schema'] == 4
    assert result['records'] == ['testguard|3f200000|43c80000|3f800000|00000000' + PROJECTILE]
    assert S.ini_sections(result)['NpcSemiAuto']['W1'] == result['records'][0]
    assert before == [ET.tostring(args[0]), ET.tostring(args[1]), ET.tostring(args[2]['teststyle'])]


def test_invalid_weapon_semantics_are_excluded():
    for key, value in [('type', ''), ('type', 'melee'), ('recoiltime', 'nan'), ('recoiltime', '-1'),
                       ('recoiltime', '0'), ('range', '0'), ('range', '300.5'), ('bursttime', 'nan'),
                       ('warmuptime', 'nan'), ('warmuptime', '-0.5'), ('warmuptime', '61')]:
        args = fixture()
        args[1][0].set(key, value)
        result = S.contract(*args)
        assert not result['records'] and len(result['excluded']) == 1, (key, value)


def test_every_gun_family_gets_its_flags_and_warmup():
    cases = [
        # (weapon attributes, expected recoil|range|burst|leader|warmup|flags tail)
        ({'type': 'beam', 'recoiltime': '0.7', 'warmuptime': '0.5', 'range': '550'},
         '|3f333333|44098000|3f800000|00000000|3f000000|00000003|00000000|00000000'),
        ({'type': 'projectile', 'recoiltime': '0.8', 'warmuptime': '0.5', 'range': '550'},
         '|3f4ccccd|44098000|3f800000|00000000|3f000000|00000002|00000000|00000000'),
        ({'type': 'beam', 'continuousbeam': 'true', 'recoiltime': '0', 'warmuptime': '0.6', 'range': '550',
          'bursttime': '2.5'}, '|00000000|44098000|40200000|00000000|3f19999a|00000013|00000000|00000000'),
        ({'type': 'flame', 'continuousbeam': 'true', 'recoiltime': '0.03', 'warmuptime': '1', 'range': '275',
          'bursttime': '3.5'}, '|3cf5c28f|43898000|40600000|00000000|3f800000|00000011|00000000|00000000'),
        ({'type': 'bullet', 'rapidfire': 'true', 'recoiltime': '0.16', 'range': '550', 'bursttime': '1.5'},
         '|3e23d70a|44098000|3fc00000|00000000|00000000|00000020|00000000|00000000'),
    ]
    for attrs, tail in cases:
        args = fixture()
        for key, value in attrs.items():
            args[1][0].set(key, value)
        result = S.contract(*args)
        assert result['records'] == ['testguard' + tail], (attrs, result)
        assert S.ini_sections(result)['NpcSemiAuto']['W1'] == result['records'][0]


def test_zero_recoil_needs_a_continuous_beam():
    args = fixture()
    args[1][0].set('recoiltime', '0')
    assert not S.contract(*args)['records']
    args[1][0].set('continuousbeam', 'true')
    assert S.contract(*args)['records'] == ['testguard|00000000|43c80000|3f800000|00000000|00000000|00000012|00000000|00000000']
    for row in ['testguard|00000000|43c80000|3f800000|00000000|00000000|00000002|00000000|00000000',
                'testguard|80000000|43c80000|3f800000|00000000|00000000|00000012|00000000|00000000']:
        assert refused({'schema': 4, 'records': [row]}), row


def test_default_handler_pistol_primary():
    args = fixture()
    args[1][0].set('type', 'bullet')
    args[1][0].set('recoiltime', '0.2')
    args[2]['teststyle'][0].attrib.pop('handler')
    args[2]['teststyle'][0].set('lockangles', 'true')
    assert S.contract(*args)['records'] == ['testguard|3e4ccccd|43c80000|3f800000|00000000|00000000|00000040|00000000|00000000']
    for key, value in [('warmuptime', '0.5'), ('continuousbeam', 'true')]:
        bad = copy.deepcopy(args)
        bad[1][0].set(key, value)
        result = S.contract(*bad)
        assert not result['records'] and 'default-handler' in result['excluded'][0]['reason']
    authored = copy.deepcopy(args)
    authored[2]['teststyle'][0].set('aitype', 'beamanyrange')
    assert 'authored gun AI' in S.contract(*authored)['excluded'][0]['reason']
    for row in ['testguard|3e4ccccd|43c80000|3f800000|00000000|3f000000|00000040|00000000|00000000',
                'testguard|3e4ccccd|43c80000|3f800000|00000000|00000000|00000050|00000000|00000000']:
        assert refused({'schema': 4, 'records': [row]}), row


def test_source_handler_and_actor_override_required():
    args = fixture()
    args[0][0].set('powerstyle', 'another_style')
    assert not S.contract(*args)['records']
    args = fixture()
    args[2]['teststyle'][0].set('handler', 'another_handler')
    assert not S.contract(*args)['records']


def test_canonical_names_sort_before_the_separator():
    data = {'schema': 4, 'records': ['guardb|3f200000|43c80000|3f800000|00000000' + PROJECTILE,
                                     'guard|3f000000|43c80000|3f800000|00000000' + PROJECTILE]}
    section = S.ini_sections(data)['NpcSemiAuto']
    assert section['W1'].startswith('guard|') and section['W2'].startswith('guardb|')


def test_contract_refuses_duplicate_or_invalid_records():
    for rows in [['guard|7f800000'], ['guard|00000000'], ['guard|3f000000'] * 2,
                 ['bad|name|3f000000'], ['guard|bf000000'], ['guard|42800000']]:
        assert refused({'schema': 4, 'records': [row + '|43c80000|3f800000|00000000' + PROJECTILE for row in rows]}), rows
    for tail in ['|7fc00000|00000002', '|bf000000|00000002', '|80000000|00000002', '|00000000|00000004',
                 '|00000000|00000080', '|00000000']:
        assert refused({'schema': 4, 'records': ['guard|3f000000|43c80000|3f800000|00000000' + tail + '|00000000|00000000']}), tail
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
    assert row.endswith('|43c80000|3fc00000|00000000' + PROJECTILE)
    for data in ({'schema': 1, 'records': ['guard|3f000000']},
                 {'schema': 2, 'records': ['guard|3f000000|43c80000|3f800000|00000000']},
                 {'schema': 2, 'records': [row]},
                 {'schema': 4, 'records': ['guard|3f000000|43c80000|3f800000|00000000']},
                 {'schema': 4, 'records': ['guard|3f000000|42960000|00000000|00000000' + PROJECTILE]},
                 {'schema': 4, 'records': ['guard|3f000000|7f800000|3f800000|00000000' + PROJECTILE]}):
        assert refused(data), data


def test_source_leader_is_not_lost_with_weapon_brain_selection():
    args = fixture()
    args[0][0].set('leader', 'TRUE')
    row = S.contract(*args)['records'][0]
    assert row.endswith('|00000001' + PROJECTILE)
    assert S.ini_sections({'schema': 4, 'records': [row]})['NpcSemiAuto']['W1'] == row
    assert refused({'schema': 4, 'records': [row.replace('|00000001|', '|00000002|')]})


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
        assert data['records'] == ['testguard|3f200000|43c80000|3f800000|00000000' + PROJECTILE]
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
        for content in (None, 'not json', json.dumps({'schema': 4, 'records': []}),
                        json.dumps({'schema': 1, 'records': ['guard|3f000000']}),
                        json.dumps({'schema': 2, 'records': ['guard|3f000000|43c80000|3f800000|00000000']})):
            path = Path(td, '_build', S.CONTRACT_FILE)
            if content is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
            keys = FI.port_keys(td)
            assert 'NpcSemiAuto' not in keys['Game'] and 'NpcSemiAuto' not in keys
            assert keys['Game']['NpcPowerRule'] == 'xml1'
            dropped = FI.dropped_keys(keys)
            assert 'NpcSemiAuto' in dropped['Game'] and dropped['NpcSemiAuto'][:2] == ['Count', 'W1']


def test_bullet_weapons_share_the_discrete_contract():
    for extra, flags in (({'type': 'bullet'}, '00000000'), ({'type': 'bullet', 'rapidfire': 'true'}, '00000020'),
                         ({'type': 'beam'}, '00000003')):
        args = fixture()
        for key, value in extra.items():
            args[1][0].set(key, value)
        assert S.contract(*args)['records'] == ['testguard|3f200000|43c80000|3f800000|00000000|00000000|' + flags + '|00000000|00000000']


def test_schema4_trace_accuracy_round_trip():
    args = fixture()
    for key, value in {'type': 'bullet', 'recoiltime': '0.16', 'range': '550',
                       'bursttime': '1.5', 'rapidfire': 'true', 'tracetime': '0.5', 'accuracy': '0'}.items():
        args[1][0].set(key, value)
    data = S.contract(*args)
    assert data['schema'] == 4
    assert data['records'] == ['testguard|3e23d70a|44098000|3fc00000|00000000|00000000|00000020|3f000000|00000000']
    assert S.ini_sections(data)['NpcSemiAuto']['W1'] == data['records'][0]
    for key in ('tracetime', 'accuracy'):
        for bad in ('nan', 'inf', '-1'):
            invalid = copy.deepcopy(args)
            invalid[1][0].set(key, bad)
            assert not S.contract(*invalid)['records']
    assert refused({'schema': 3, 'records': data['records']})
    for index in (7, 8):
        for bits in ('7fc00000', '7f800000', 'bf800000', '80000000', '43b48000'):
            invalid = data['records'][0].split('|')
            invalid[index] = bits
            assert refused({'schema': 4, 'records': ['|'.join(invalid)]})


def test_only_converted_bullets_carry_the_inert_gate_marker():
    from xml1build import weapons as W
    for kind in ('bullet', 'beam', 'flame', 'projectile'):
        triggers = W.shot_triggers({'type': kind}, '0')
        marked = [t for t in triggers if t.get('split_damage') == '32766 32766' and t.get('split_count') == '0']
        assert bool(marked) == (kind == 'bullet')
