import json
import tempfile
from pathlib import Path
from xml1build import fix_ini as F
import harness


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
