"""Rule 45 ground-grab switch. Synthetic metadata only; no game inputs."""
import json
import tempfile
from pathlib import Path

import build_xml1
from xml1build import common as C
from xml1build import fix_ini as FI


def test_grab_carry_option_and_ini_coupled_with_stale_key_removal():
    # 0.4.1-beta.1 (beta 8): XML1's grab lifecycle is the default, xml2 the stock handlers for A/B builds
    assert build_xml1.parse_args(['--out', '.']).grab_carry == 'xml1'
    assert build_xml1.parse_args(['--out', '.', '--grab-carry', 'xml2']).grab_carry == 'xml2'
    assert build_xml1.CONTENT_OPTS['grab_carry'] == ('characters', 'xml1')
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        meta = out / '_build'
        meta.mkdir()
        for value in ('xml1', 'xml2', None):
            record = {'build': {key: default for key, (_, default) in build_xml1.CONTENT_OPTS.items()}}
            if value:
                record['build']['grab_carry'] = value
            else:
                record['build'].pop('grab_carry')
            (meta / 'report.json').write_text(json.dumps(record), encoding='utf-8')
            keys = FI.port_keys(out)
            assert (keys['Game'].get('Xml1GrabCarry') == 'xml1') == (value == 'xml1')
            assert ('Xml1GrabCarry' in FI.dropped_keys(keys).get('Game', [])) == (value != 'xml1')
            assert getattr(C.args_for_out(out), 'grab_carry', None) == value
            merged = FI.merge_text('[Game]\nXml1GrabCarry=xml1\nKeepMe=7\n', keys, FI.dropped_keys(keys))
            assert ('Xml1GrabCarry=xml1' in merged) == (value == 'xml1')
            assert 'KeepMe=7' in merged
            # a record without the option counts as the default (xml1 since beta 8): toggling means xml2
            args = build_xml1.parse_args(['--out', td, '--grab-carry', 'xml1' if value == 'xml2' else 'xml2'])
            assert 'characters' in build_xml1.plan_content_opts(out, args, [])


def test_grab_carry_default_ini_bytes_equal_legacy_report():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        meta = out / '_build'
        meta.mkdir()
        record = {'build': {key: default for key, (_, default) in build_xml1.CONTENT_OPTS.items()}}
        record['build'].pop('grab_carry')
        report = meta / 'report.json'
        report.write_text(json.dumps(record), encoding='utf-8')
        old_keys = FI.port_keys(out)
        old = FI.merge_text('[Game]\nKeepMe=7\n', old_keys, FI.dropped_keys(old_keys))
        record['build']['grab_carry'] = 'xml2'
        report.write_text(json.dumps(record), encoding='utf-8')
        keys = FI.port_keys(out)
        new = FI.merge_text('[Game]\nKeepMe=7\n', keys, FI.dropped_keys(keys))
        assert old.encode('utf-8') == new.encode('utf-8')


def test_grab_carry_refuses_companion_without_requested_key_only():
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        dll.write_bytes(b'MZ' + 'Xml1RogueDecide'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1'}}) == ['[Game] Xml1GrabCarry',
                                                                           '[Game] Xml1GrabCarry revision 3',
                                                                           '[Game] Xml1GrabCarry (no carry self-chain)',
                                                                           '[Game] Xml1GrabCarry (thrown impact, animated bones)',
                                                                           FI.FLYING_CARRY_ON_NAME, FI.FLYING_CARRY_R2_NAME, FI.FLYING_CARRY_082D_NAME, FI.FLYING_CARRY_082E_NAME]
        assert FI.old_fix_keys(dll, {'Game': {}}) == []
        # 080b's DLL knows the key but runs revision 2 (no flying carry, no XML1 flight upkeep): refused by marker
        dll.write_bytes(b'MZ' + 'Xml1GrabCarry'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1'}}) == ['[Game] Xml1GrabCarry revision 3',
                                                                           '[Game] Xml1GrabCarry (no carry self-chain)',
                                                                           '[Game] Xml1GrabCarry (thrown impact, animated bones)',
                                                                           FI.FLYING_CARRY_ON_NAME, FI.FLYING_CARRY_R2_NAME, FI.FLYING_CARRY_082D_NAME, FI.FLYING_CARRY_082E_NAME]
        # 080c / 080d's DLL runs revision 3 but re-enters the established carry node every frame: refused by marker
        dll.write_bytes(b'MZ' + 'Xml1GrabCarry'.encode('utf-16le') + FI.GRAB_CARRY_R3_MARKER)
        assert FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1'}}) == ['[Game] Xml1GrabCarry (no carry self-chain)',
                                                                           '[Game] Xml1GrabCarry (thrown impact, animated bones)',
                                                                           FI.FLYING_CARRY_ON_NAME, FI.FLYING_CARRY_R2_NAME, FI.FLYING_CARRY_082D_NAME, FI.FLYING_CARRY_082E_NAME]
        # 080e / 080f's DLL: a thrown body's world impact never reaches its receiver, the carry pose reads synthetic bones
        dll.write_bytes(b'MZ' + 'Xml1GrabCarry'.encode('utf-16le') + FI.GRAB_CARRY_R3_MARKER + FI.CARRY_CHAIN_MARKER)
        assert FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1'}}) == ['[Game] Xml1GrabCarry (thrown impact, animated bones)',
                                                                           FI.FLYING_CARRY_ON_NAME, FI.FLYING_CARRY_R2_NAME, FI.FLYING_CARRY_082D_NAME, FI.FLYING_CARRY_082E_NAME]
        dll.write_bytes(b'MZ' + 'Xml1GrabCarry'.encode('utf-16le') + FI.GRAB_CARRY_R3_MARKER + FI.CARRY_CHAIN_MARKER
                        + FI.THROWN_IMPACT_MARKER)
        # beta 8 (1.9.0-beta.1 / beta.2): the flying carry on (no Xml1FlyingCarry key) still throws with 0 damage
        assert FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1'}}) == [FI.FLYING_CARRY_ON_NAME, FI.FLYING_CARRY_R2_NAME, FI.FLYING_CARRY_082D_NAME, FI.FLYING_CARRY_082E_NAME]
        dll.write_bytes(b'MZ' + 'Xml1GrabCarry'.encode('utf-16le') + FI.GRAB_CARRY_R3_MARKER + FI.CARRY_CHAIN_MARKER
                        + FI.THROWN_IMPACT_MARKER + FI.CARRY_THROW_MARKER)
        # 082b (beta 9 round 1): throw damage, but the guard shortcut skips carry admission and the entry pose is off
        assert FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1'}}) == [FI.FLYING_CARRY_R2_NAME, FI.FLYING_CARRY_082D_NAME, FI.FLYING_CARRY_082E_NAME]
        dll.write_bytes(b'MZ' + 'Xml1GrabCarry'.encode('utf-16le') + FI.GRAB_CARRY_R3_MARKER + FI.CARRY_CHAIN_MARKER
                        + FI.THROWN_IMPACT_MARKER + FI.CARRY_THROW_MARKER + FI.CARRY_ROUND2_MARKER)
        # 082c (round 2): hovers over the target, attaches an ally by its feet, throws with DMG3 instead of L2
        assert FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1'}}) == [FI.FLYING_CARRY_082D_NAME, FI.FLYING_CARRY_082E_NAME]
        dll.write_bytes(dll.read_bytes() + FI.CARRY_082D_MARKER)
        # 082d (round 3 live): the pickup's clearance probe collides with the selected character, so she never descends
        assert FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1'}}) == [FI.FLYING_CARRY_082E_NAME]
        dll.write_bytes(dll.read_bytes() + FI.CARRY_082E_MARKER)
        assert FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1'}}) == []
        # beta 8's shipped flying carry off (Xml1FlyingCarry=0) asks for neither beta 9 marker
        dll.write_bytes(b'MZ' + 'Xml1GrabCarry'.encode('utf-16le') + FI.GRAB_CARRY_R3_MARKER + FI.CARRY_CHAIN_MARKER
                        + FI.THROWN_IMPACT_MARKER + 'Xml1FlyingCarry'.encode('utf-16le') + FI.FLYING_CARRY_OFF_MARKER)
        assert FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1', **FI.FLYING_CARRY_OFF}}) == []


def test_actor_pools_off_by_default_written_only_when_recorded():
    # E4 stage 1 ([Limits] ActorPools=124, rule 44) stays off in beta 8 until its live runs pass.
    assert build_xml1.parse_args(['--out', '.']).actor_pools == 'off'
    assert build_xml1.CONTENT_OPTS['actor_pools'] == ('characters', 'off')
    assert 'ActorPools' in FI.PORT_OWNED['Limits'] and 'ActorPools' in FI.RELEASE_18_KEYS['Limits']
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        (out / '_build').mkdir()
        for value, written in (('124', True), ('off', False), (None, False)):
            record = {'build': {key: default for key, (_, default) in build_xml1.CONTENT_OPTS.items()}}
            if value:
                record['build']['actor_pools'] = value
            else:
                record['build'].pop('actor_pools')
            (out / '_build' / 'report.json').write_text(json.dumps(record), encoding='utf-8')
            keys = FI.port_keys(out)
            assert (keys['Limits'].get('ActorPools') == '124') == written
            assert ('ActorPools' in FI.dropped_keys(keys).get('Limits', [])) == (not written)
        dll = out / 'dinput.dll'
        dll.write_bytes(b'MZ' + 'IGBCache'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, {'Limits': {'ActorPools': '124'}}) == ['[Limits] ActorPools']
        assert FI.old_fix_keys(dll, {'Limits': {}}) == []
        dll.write_bytes(b'MZ' + 'ActorPools'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, {'Limits': {'ActorPools': '124'}}) == []


def test_shared_handlers_c_keys_written_and_required():
    # rule 46: the nine wave C keys in every XML1 build, each refused by name on a DLL that lacks it
    assert set(FI.SHARED_HANDLERS_C) == {'JumpAttackDamageRule', 'FlyChargeDamageRule', 'ColossusChargeRule', 'BeastBounceRule',
                                         'FastballRule', 'IdleBoredRule', 'LocomotionScaleRule', 'AnimationPhaseRule',
                                         'TeleportVisibilityRule'}
    game = FI.game_keys()
    assert all(game[k] == 'xml1' for k in FI.SHARED_HANDLERS_C)
    assert all(k in FI.PORT_OWNED['Game'] and k in FI.RELEASE_18_KEYS['Game'] for k in FI.SHARED_HANDLERS_C)
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        dll.write_bytes(b'MZ' + ''.join(FI.SHARED_HANDLERS).encode('utf-16le'))
        colossus = '[Game] ColossusChargeRule (caster talents)'
        assert FI.old_fix_keys(dll, {'Game': dict(FI.SHARED_HANDLERS_C)}) == [f'[Game] {k}' for k in FI.SHARED_HANDLERS_C] + [colossus]
        # 080f and older: the Colossus charge evaluates its talents on the struck soldier (no damage), refused by marker
        dll.write_bytes(b'MZ' + '\0'.join(FI.SHARED_HANDLERS_C).encode('utf-16le'))
        assert FI.old_fix_keys(dll, {'Game': dict(FI.SHARED_HANDLERS_C)}) == [colossus]
        dll.write_bytes(b'MZ' + '\0'.join(FI.SHARED_HANDLERS_C).encode('utf-16le') + FI.COLOSSUS_CASTER_MARKER)
        assert FI.old_fix_keys(dll, {'Game': dict(FI.SHARED_HANDLERS_C)}) == []


def test_juggernaut_npc_records_get_the_grab_talent():
    # 080b live + trace: XMen2.exe's ch_guard_decide (0x4ec3c6) grabs only with grab_scale_dmg > 0, whose only provider
    # is the hidden shared talent `grab` (heroes.GRAB_TALENT, heroes.py issue #51); XML1 has no such gate, so the two
    # Juggernauts that fight with x1_ps_juggernaut's grabstart carry the same reference.
    import xml.etree.ElementTree as ET
    from xml1build import characters as CH
    from xml1build import heroes as H
    assert CH.NPC_GRAB_TALENT == ('juggernautflashback', 'juggernautact3')
    root = ET.fromstring('<npcstats>'
                         '<stats name="JuggernautFlashback"><talent level="0" name="jug_punch"/></stats>'
                         '<stats name="JuggernautAct3"><talent level="1" name="grab"/></stats>'
                         '<stats name="JuggernautScripted"><talent level="1" name="might"/></stats>'
                         '<stats name="Blob"/></npcstats>')
    assert CH.add_npc_grab_talent(root) == ['JuggernautFlashback']
    grab = {st.get('name'): [(t.get('name'), t.get('level')) for t in st.iter('talent') if t.get('name') == H.GRAB_TALENT]
            for st in root.iter('stats')}
    assert grab == {'JuggernautFlashback': [('grab', '1')], 'JuggernautAct3': [('grab', '1')],
                    'JuggernautScripted': [], 'Blob': []}
    assert CH.add_npc_grab_talent(root) == []                           # idempotent: never a second reference
