"""Synthetic helper ownership, timer cleanup and unchanged saved identities."""
import copy
import importlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from xml1build import common as C, scripts_lint as L, validate as V
from xml1build import zones as Z
from lcsave.binds import numbered_entities
from lcsave.zonecompat import attest_equivalent


def converter():
    try:
        return importlib.import_module('xml1build.emitter_lifetime')
    except ImportError:
        raise AssertionError('emitter lifetime converter not implemented') from None


def zone():
    return ET.fromstring('''<world>
      <entinst type="body"><inst name="left" pos="100 200 0"/>
        <inst name="right" pos="900 200 0"/></entinst>
      <entinst type="gate"><inst name="gate" pos="2000 0 0"/></entinst>
      <entity name="body" classname="physent" health="80" nogravity="true"
        nopickup="true" nopush="true" startenabled="false" actspawn="pulse"
        spawnscript="made=spawn('_OWNER_','pulse','wave','0 0 0','0 0 0')\n\rsetParent(made,'_OWNER_')"/>
      <entity name="pulse" classname="affectableharment" model="" persistent="false"
        smartent="false" radiusdamage="true" damage="17" damagetype="dmg_cold"
        firstact="1.25" actrescheduledelay="1.75" actrescheduledelaymin="0.75"
        acteffect="invented/wave" spawnscript=""/>
      <entity name="gate" classname="doorent" smartent="false"/>
    </world>'''.replace("\n\rsetParent", r'\n\rsetParent'))


def definitions(root):
    return {e.get('name'): e for e in root.iter('entity')}


def converted(root):
    scripts = {}
    count = converter().convert(root, scripts)
    return count, scripts


def run_raven(text, api):
    """Execute generated straight-line Raven/if code against synthetic API edges."""
    lines, depth = [], 0
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith('#'):
            continue
        if s == 'endif':
            depth -= 1
            continue
        assert not s.startswith(('while ', 'def ', 'elif ', 'else'))
        lines.append('    ' * depth + s + (':' if s.startswith('if ') else ''))
        if s.startswith('if '):
            depth += 1
    assert depth == 0
    exec('\n'.join(lines), {'__builtins__': {}, **api})


def test_body_placements_and_saved_ordinals_are_unchanged():
    root = zone()
    before = copy.deepcopy(root)
    old, errors = numbered_entities(root)
    assert not errors
    assert converted(root)[0] == 1
    new, errors = numbered_entities(root)
    assert not errors and old == new
    assert C.xmlb.encode(definitions(root)['body']) == C.xmlb.encode(definitions(before)['body'])
    assert [C.xmlb.encode(g) for g in root.findall('entinst')] == [
        C.xmlb.encode(g) for g in before.findall('entinst')]
    child = definitions(root)['pulse']
    child.set('spawnscript', '')
    child.attrib.pop('xml1emitterlifetime', None)
    assert child.attrib == definitions(before)['pulse'].attrib


def test_dead_or_missing_body_removes_only_its_helper_and_watcher():
    E = converter()
    _, scripts = converted(zone())
    for body_health in (0, -5, None):
        parents = {301: 101, 101: 201, 302: 102, 102: 202}
        health = {202: 80}
        if body_health is not None:
            health[201] = body_health
        removed, disabled = [], []
        resolve = lambda value: 301 if value == '_OWNER_' else value
        run_raven(scripts[E.CHECK_REF], {
            'getParentID': lambda child: parents.get(resolve(child), 0),
            'getHealth': lambda body: health.get(body, 0),
            'setEnable': lambda child, enabled: disabled.append((resolve(child), enabled)),
            'remove': lambda target, activator: removed.append(resolve(target)),
        })
        assert disabled == [(101, 'FALSE')]
        assert removed == [101, 301]
        assert not {102, 202, 302}.intersection(removed)


def test_live_low_health_body_is_not_disabled_or_removed():
    E = converter()
    _, scripts = converted(zone())
    for health in (0.5, 80):
        events = []
        run_raven(scripts[E.CHECK_REF], {
            'getParentID': lambda child: {'_OWNER_': 101, 101: 201}.get(child, 0),
            'getHealth': lambda body: health if body == 201 else 0,
            'setEnable': lambda *args: events.append(('disable', args)),
            'remove': lambda *args: events.append(('remove', args)),
        })
        assert not events


def test_startup_parents_the_new_watcher_to_the_exact_helper_handle():
    E = converter()
    root = zone()
    _, scripts = converted(root)
    calls = []
    def spawn(*args):
        calls.append(('spawn', args))
        return 987
    run_raven(scripts[E.START_REF], {
        'spawn': spawn,
        'setParent': lambda child, parent: calls.append(('parent', child, parent)),
    })
    assert calls == [('spawn', ('_OWNER_', E.WATCHER, E.WATCHER, '0 0 0', '0 0 0')),
                     ('parent', 987, '_OWNER_')]
    watcher = definitions(root)[E.WATCHER]
    assert watcher.get('persistent') == 'false' and watcher.get('smartent') == 'false'
    assert 0 < float(watcher.get('firstact')) <= 0.1
    assert 0 < float(watcher.get('actrescheduledelay')) <= 0.1
    assert 'actrescheduledelaymin' not in watcher.attrib
    assert not any(g.get('type') == E.WATCHER for g in root.findall('entinst'))


def test_generated_scripts_pass_native_api_and_crlf_checks():
    _, scripts = converted(zone())
    api = json.loads((Path(__file__).parents[2] / 'research/scripts/xml2_api.json').read_text())
    for script in scripts.values():
        assert not L.lint_script_bytes(script.replace('\n', '\r\n').encode('ascii'), api)[0]


def test_unrelated_or_authored_helper_scripts_are_not_replaced():
    for name, key, value in [('body', 'classname', 'actor'), ('body', 'nopush', 'false'),
                             ('body', 'health', '0'), ('pulse', 'persistent', 'true'),
                             ('pulse', 'model', 'invented/visible'),
                             ('pulse', 'spawnscript', 'invented/owned_start'),
                             ('pulse', 'radiusdamage', 'false')]:
        root = zone()
        definitions(root)[name].set(key, value)
        before = C.encode_xmlb(root)
        assert converted(root) == (0, {})
        assert C.encode_xmlb(root) == before
    root = zone()
    g = ET.SubElement(root, 'entinst', type='pulse')
    ET.SubElement(g, 'inst', name='standalone', pos='0 0 0')
    assert converted(root) == (0, {})


def test_watcher_collision_fails_before_mutating_the_original_tree():
    E = converter()
    root = zone()
    ET.SubElement(root, 'entity', name=E.WATCHER, classname='physent')
    before = C.encode_xmlb(root)
    try:
        converted(root)
    except ValueError:
        pass
    else:
        assert False, 'watcher collision accepted'
    assert before == C.encode_xmlb(root)


def test_conversion_is_idempotent_and_missing_or_corrupt_guards_reject():
    E = converter()
    root = zone()
    assert E.problems(root)
    count, scripts = converted(root)
    assert count == 1 and not E.problems(root)
    before = C.encode_xmlb(root)
    assert converted(root) == (0, scripts)
    assert C.encode_xmlb(root) == before
    definitions(root)[E.WATCHER].set('actrescheduledelay', '0')
    assert E.problems(root)


def test_inline_unparented_spawns_do_not_acquire_a_lifetime_watcher():
    root = zone()
    ET.SubElement(root, 'entity', name='independent', classname='actionent',
                  actscript="spawn('_OWNER_','pulse','free_wave','0 0 0','0 0 0')")
    assert converted(root) == (0, {})


def test_partial_guard_tampering_is_detected_with_another_valid_factory():
    E = converter()
    root = zone()
    body = copy.deepcopy(definitions(root)['body'])
    body.set('name', 'another_body')
    body.set('spawnscript', body.get('spawnscript').replace("'pulse'", "'other_pulse'"))
    body.set('actspawn', 'other_pulse')
    helper = copy.deepcopy(definitions(root)['pulse'])
    helper.set('name', 'other_pulse')
    root.extend((body, helper))
    g = ET.SubElement(root, 'entinst', type='another_body')
    ET.SubElement(g, 'inst', name='another_body', pos='2000 200 0')
    assert converted(root)[0] == 2
    definitions(root)['pulse'].set('spawnscript', 'invented/wrong_start')
    assert E.problems(root)


def test_exact_equivalence_preserves_smart_saved_state_and_has_no_fresh_aliases():
    root = zone()
    before = C.encode_xmlb(root)
    converted(root)
    row = attest_equivalent('invented/bay', before, C.encode_xmlb(root))
    assert row is not None
    assert row['placements'] == [2]
    assert row['fresh_aliases'] == row['ambiguous_aliases'] == []
    for name, key, value in [('body', 'health', '99'), ('pulse', 'damage', '99'),
                             ('body', 'smartent', 'false')]:
        bad = copy.deepcopy(root)
        definitions(bad)[name].set(key, value)
        assert attest_equivalent('invented/bay', before, C.encode_xmlb(bad)) is None


def test_output_validator_checks_both_maps_and_generated_script_bytes():
    assert hasattr(V.Validator, 'emitter_lifetimes'), 'emitter output validator not implemented'
    good = zone()
    _, scripts = converted(good)
    files = {C.norm(C.script_rel(ref)): C.to_crlf(text).encode('ascii') for ref, text in scripts.items()}
    class Output:
        def converted_zones(self): return ['invented/bay']
        def tree(self, rel): return good if rel.endswith('.xmlb') else zone()
        def read(self, rel): return files.get(C.norm(rel))
    ck = V.Check('test', 'emitter')
    V.Validator.emitter_lifetimes(Output(), ck)
    assert any('.engb' in error for error in ck.errors)
    class Good(Output):
        def tree(self, rel): return good
    ck = V.Check('test', 'emitter')
    V.Validator.emitter_lifetimes(Good(), ck)
    assert not ck.errors
    files[C.norm(C.script_rel(converter().CHECK_REF))] = b'remove("invented_bystander", "_OWNER_")\r\n'
    ck = V.Check('test', 'emitter')
    V.Validator.emitter_lifetimes(Good(), ck)
    assert ck.errors


def test_generated_refs_package_with_the_fallback_script_provider():
    E = converter()
    builder = Z.Zones.__new__(Z.Zones)
    class Context:
        def out_exists(self, rel): return C.norm(rel) in {
            C.norm(C.script_rel(E.START_REF)), C.norm(C.script_rel(E.CHECK_REF))}
        def base_exists(self, rel): return False
    class Provider:
        def script_exists(self, ctx, ref): return False
    builder.ctx, builder.prov, builder._script_ok = Context(), Provider(), {}
    assert builder.script_ok(E.START_REF) and builder.script_ok(E.CHECK_REF)
    refs = Z.Zones.extract_refs(builder, converted_tree(), full=True)
    assert {value for kind, value, _ in refs if kind == 'script'} >= {E.START_REF, E.CHECK_REF}


def converted_tree():
    root = zone()
    converted(root)
    return root
