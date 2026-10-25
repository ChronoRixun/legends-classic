import json
import tempfile
from pathlib import Path
from xml1build import fix_ini as F
import harness
import xmlb
import xml.etree.ElementTree as ET


def boss_map(instances):
    root = ET.Element('world')
    for i, name in enumerate(instances):
        ET.SubElement(root, 'entity', name=f'invented_spawner{i}', monster_name=name, classname='monsterspawnerent')
    return xmlb.encode(root)


def test_effective_stage_binding_uses_narrowed_width():
    layout = dict(kind='pack', gamevar='invented_stage', first_bit=3, nbits=24)
    assert F.mold_stage_binding(layout, 5) == 'invented_stage:3:5'
    assert F.mold_stage_binding(layout) == 'invented_stage:3:24'
    for bad in [dict(layout, first_bit=0), dict(layout, first_bit=31),
                dict(layout, gamevar='../invalid'), dict(layout, nbits=True), dict(layout, kind='zone')]:
        assert F.mold_stage_binding(bad, 5) is None
    assert F.mold_stage_binding(layout, 25) is None


def test_mold_ini_requires_generated_valid_contract():
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        assert F.build_mold_controller(out) == {}
        (out / '_build').mkdir()
        metadata = out / '_build/scripts_detail.json'
        metadata.write_text(json.dumps({'mold_controller': dict(revision=1, stage=dict(
            kind='pack', gamevar='invented_stage', first_bit=3, nbits=5))}))
        assert F.build_mold_controller(out) == dict(Xml1MasterMold='1', Xml1MoldStage='invented_stage:3:5')
        for revision in (2, True, 1.0):
            metadata.write_text(json.dumps({'mold_controller': dict(revision=revision, stage=dict(
                kind='pack', gamevar='invented_stage', first_bit=3, nbits=5))}))
            assert F.build_mold_controller(out) == {}


def test_harness_only_enables_mold_for_port_identity():
    keys = dict(Xml1MasterMold='1', Xml1MoldStage='invented_stage:3:5')
    assert 'Xml1MasterMold=1' in harness.ini_text('windowed', 1280, 720, True, port_identity=True, mold_controller=keys)
    assert 'Xml1MasterMold' not in harness.ini_text('windowed', 1280, 720, True, mold_controller=keys)
    assert 'Xml1MasterMold' not in harness.ini_text('windowed', 1280, 720, True, xml1_opening=False, port_identity=True, mold_controller=keys)


def test_bosses_key_lists_only_bosses_whose_zone_and_instances_are_built():
    # Invented bytes; only the instance names the DLL binds by are real (fix_ini.BOSS_BINDINGS).
    name, zones, instances = F.BOSS_BINDINGS[0]
    assert name == 'dopples' and [b[0] for b in F.BOSS_BINDINGS] == [
        'dopples', 'avalanche', 'pyro', 'mystique', 'shadowking', 'marrow', 'magneto', 'blob']
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        assert F.build_bosses(out) == {}
        path = out / zones[0]
        path.parent.mkdir(parents=True)
        path.write_bytes(boss_map(instances[:-1]))
        assert F.build_bosses(out) == {}
        path.write_bytes(boss_map(instances))
        assert F.build_bosses(out) == {'Xml1Bosses': 'dopples'}
        second = out / F.BOSS_BINDINGS[1][1][1]          # the second zone alone lists the boss
        second.parent.mkdir(parents=True, exist_ok=True)
        second.write_bytes(boss_map(F.BOSS_BINDINGS[1][2]))
        assert F.build_bosses(out) == {'Xml1Bosses': 'dopples,avalanche'}
    assert 'Xml1Bosses' in F.PORT_OWNED['Game'] and 'Xml1Bosses' in F.RELEASE_18_KEYS['Game']


def test_wave2_binding_requires_actual_actor_names_and_complete_forms():
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        for name, zones, actors in F.BOSS_BINDINGS[2:]:
            path = out / zones[-1]
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = F.boss_instance_names(xmlb.decode(path.read_bytes())) if path.exists() else set()
            # A reference or substring is insufficient, even if every byte spelling appears.
            root = ET.Element('world', references=','.join(actors))
            ET.SubElement(root, 'entity', monster_name='prefix_' + actors[0])
            group = ET.SubElement(root, 'entinst', type='invented_waypoints')
            for actor in actors:
                ET.SubElement(group, 'inst', name=actor)
            path.write_bytes(xmlb.encode(root))
            assert name not in F.build_bosses(out).get('Xml1Bosses', '').split(',')
            path.write_bytes(boss_map(sorted(existing | set(actors))))
            for script in F.BOSS_SCRIPT_CONTRACTS.get(name, ()):
                generated = out / 'Scripts' / (script + '.py')
                generated.parent.mkdir(parents=True, exist_ok=True)
                generated.write_text(f'setPatternSequence("magneto", "mag{script[-1]}")\n' if name == 'magneto' else 'setPatternSequence("shadowking", "sk3")\n')
            assert name in F.build_bosses(out)['Xml1Bosses'].split(',')
        assert F.build_bosses(out)['Xml1Bosses'] == 'pyro,mystique,shadowking,marrow,magneto,blob'
        assert F.BOSS_IMPLEMENTATIONS['marrow'] == 'native'


def test_partial_shadow_build_keeps_substitute_without_listing_controller():
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        _, zones, actors = F.BOSS_BINDINGS[4]
        path = out / zones[0]
        path.parent.mkdir(parents=True)
        path.write_bytes(boss_map(actors))
        assert F.build_bosses(out) == {}
        assert F.build_bosses(out, check_scripts=False) == {'Xml1Bosses': 'shadowking'}
        for script in F.BOSS_SCRIPT_CONTRACTS['shadowking']:
            generated = out / 'Scripts' / (script + '.py')
            generated.parent.mkdir(parents=True, exist_ok=True)
            generated.write_text('setInvulnerable("shadowking", "TRUE")\n')
        assert F.build_bosses(out) == {}
        from types import SimpleNamespace
        ctx = SimpleNamespace(shared={'selected_modules': ['scripts']}, out=out)
        assert F.source_bosses(ctx) == {'shadowking'}


def test_source_script_plan_uses_same_zone_and_instance_contract():
    from types import SimpleNamespace
    zone = F.BOSS_BINDINGS[4][1][0][5:-5].lower()
    root = ET.Element('world')
    ET.SubElement(root, 'entity', monster_name='shadowking', classname='monsterspawnerent')
    ctx = SimpleNamespace(shared={}, x1_zones=lambda: [zone], read_x1_xml=lambda _: root)
    assert 'shadowking' not in F.source_bosses(ctx)
    ET.SubElement(root, 'entity', monster_name='shadowking2', classname='monsterspawnerent')
    ctx.shared.clear()
    assert F.source_bosses(ctx) == {'shadowking'}


def test_magneto_contract_rejects_old_scripts_and_old_map_independently():
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        _, zones, actors = F.BOSS_BINDINGS[6]
        path = out / zones[0]
        path.parent.mkdir(parents=True)
        root = xmlb.decode(boss_map(actors))
        relay = ET.SubElement(root, 'entity', name='shieldup', actcountact='4',
                              actscript='setPatternSequence("magneto","magshield")')
        path.write_bytes(xmlb.encode(root))
        assert 'magneto' not in F.build_bosses(out).get('Xml1Bosses', '').split(',')
        assert 'magneto' in F.build_bosses(out, check_scripts=False)['Xml1Bosses']
        for stage, script in enumerate(F.BOSS_SCRIPT_CONTRACTS['magneto'], 2):
            generated = out / 'Scripts' / (script + '.py')
            generated.parent.mkdir(parents=True, exist_ok=True)
            generated.write_text(f'setPatternSequence("magneto","mag{stage}")\n')
        assert F.build_bosses(out) == {'Xml1Bosses': 'magneto'}
        generated.write_text('unrelatedAction()\n')
        assert F.build_bosses(out) == {}
        generated.write_text('setPatternSequence("magneto","mag5")\nsetInvulnerable("magneto","FALSE")\n')
        assert F.build_bosses(out) == {}
        generated.write_text('setPatternSequence("magneto","mag5")\n')
        relay.set('actscript', relay.get('actscript') + r'\n\rsetInvulnerable("magneto","TRUE")')
        path.write_bytes(xmlb.encode(root))
        assert F.build_bosses(out) == {}


def test_magneto_scripts_only_keeps_releases_for_an_old_protected_map():
    from types import SimpleNamespace
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        _, zones, actors = F.BOSS_BINDINGS[6]
        path = out / zones[0]
        path.parent.mkdir(parents=True)
        root = xmlb.decode(boss_map(actors))
        ET.SubElement(root, 'entity', name='shieldup',
                      actscript=r'setPatternSequence("magneto","magshield")\n\rsetInvulnerable("magneto","TRUE")')
        path.write_bytes(xmlb.encode(root))
        assert F.build_bosses(out, check_scripts=False) == {}
        ctx = SimpleNamespace(shared={'selected_modules': ['scripts']}, out=out)
        assert 'magneto' not in F.source_bosses(ctx)
        from xml1build import boss_phases as B
        text = 'setPatternSequence("magneto","mag4")\n'
        assert 'setInvulnerable' in B.rewrite_script('asteroid_m/stage4', text, controller_bosses=F.source_bosses(ctx))


def test_magneto_zones_only_keeps_protection_until_existing_scripts_are_compatible():
    from types import SimpleNamespace
    from xml1build import boss_phases as B
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        _, zones, actors = F.BOSS_BINDINGS[6]
        zone = zones[0][5:-5].lower()
        root = xmlb.decode(boss_map(actors))
        relay = ET.SubElement(root, 'entity', name='shieldup', actscript='setPatternSequence("magneto","magshield")')
        ctx = SimpleNamespace(shared={'selected_modules': ['zones']}, out=out,
                              x1_zones=lambda: [zone], read_x1_xml=lambda _: root)
        assert 'magneto' not in F.source_bosses(ctx)
        assert B.rewrite_data(root, B.MAGNETO_ZONE, controller_bosses=F.source_bosses(ctx)) == 1
        assert 'setInvulnerable' in relay.get('actscript')
        for stage, script in enumerate(F.BOSS_SCRIPT_CONTRACTS['magneto'], 2):
            path = out / 'Scripts' / (script + '.py')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f'setPatternSequence("magneto","mag{stage}")\n')
        ctx.shared = {'selected_modules': ['zones']}
        assert 'magneto' in F.source_bosses(ctx)
        assert B.rewrite_data(root, B.MAGNETO_ZONE, controller_bosses=F.source_bosses(ctx)) == 1
        assert 'setInvulnerable' not in relay.get('actscript')
