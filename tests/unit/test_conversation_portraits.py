"""Conversation head residency using invented speakers, skins and package data."""
import collections
import types
import xml.etree.ElementTree as ET

from xml1build import conversations as CV
from xml1build import validate as V
from xml1build import zones as Z


def tree(text):
    return ET.fromstring(text)


def fixture():
    data = {
        'data/herostat.engb': tree('<stats><stats name="ember" skin="91001"/></stats>'),
        'data/npcstat.engb': tree('<stats><stats name="river" skin="92003"/>'
                                '<stats name="ember_double" skin="91001"/>'
                                '<stats name="mist" skin="93002"/></stats>'),
        'conversations/arrival.engb': tree('<conversation><line text="%EMBER%: Greeting">'
                                         '<response text="Choice"/></line>'
                                         '<participant name="copied_jump"><line textb="%RIVER%: Reply"/>'
                                         '<line text="%EMBER_DOUBLE%: Echo"/></participant></conversation>'),
        'hud/hud_head_91001.igb': b'fictional',
        'hud/hud_head_92003.igb': b'fictional',
        'packages/generated/maps/package/permanent.pkgb': tree('<packagedef/>'),
    }
    idx = types.SimpleNamespace(
        find=lambda n, exts: next((n.lower() + e.lower() for e in exts if n.lower() + e.lower() in data), None),
        path=lambda n: n.lower() if n.lower() in data else None)
    ctx = types.SimpleNamespace(out_index=idx, read_out_xmlb=lambda n: data[n.lower()])
    z = Z.Zones.__new__(Z.Zones)
    z.ctx, z.counts = ctx, collections.Counter()
    return data, z


def test_speaker_positions_case_builtins_and_exact_skin():
    root = tree('<CONVERSATION><LINE TEXT="%Ember%: Greeting" TEXTB="ABCD%RIVER%: Reply"/>'
                '<response text="%EMBER_DOUBLE%: Echo"/><line text="%PLAYER%: Activator"/>'
                '<line text="%X-TEAM%: Team"/><line text="%END%"/>'
                '<line text="x%mist%"/><line text="%unknown%: Missing"/></CONVERSATION>')
    stats = {s.get('name'): s for s in tree('<stats><stats name="ember" skin="91001"/>'
             '<stats name="river" skin="92003"/><stats name="ember_double" skin="91001"/></stats>')}
    assert CV.portrait_requirements(root, stats) == {
        'ember': 'hud/hud_head_91001', 'river': 'hud/hud_head_92003',
        'ember_double': 'hud/hud_head_91001', 'unknown': None}


def test_heads_only_deduplicated_before_core_and_idempotent():
    data, z = fixture()
    pkg = Z.Pkg([('xml', 'conversations/arrival'), ('characters', 'maps/lobby'),
                 ('zonexml', 'maps/lobby'), ('model', 'maps/lobby')])
    before = ET.tostring(data['conversations/arrival.engb'])
    z.conversation_heads('lobby', pkg)
    expected = [('model', 'hud/hud_head_91001'), ('model', 'hud/hud_head_92003')]
    assert pkg.entries()[1:3] == expected
    assert z.counts['conversation_heads_added'] == 2
    first = pkg.entries()
    z.conversation_heads('lobby', pkg)
    assert pkg.entries() == first and z.counts['conversation_heads_added'] == 2
    assert ET.tostring(data['conversations/arrival.engb']) == before


def test_existing_zone_permanent_and_missing_asset():
    data, z = fixture()
    data['packages/generated/maps/package/permanent.pkgb'].append(
        ET.Element('model', filename='hud/hud_head_91001'))
    data['conversations/arrival.engb'].append(ET.Element('line', text='%mist%: Greeting'))
    pkg = Z.Pkg([('xml', 'conversations/arrival'), ('model', 'hud/hud_head_92003')])
    before = pkg.entries()
    z.conversation_heads('lobby', pkg)
    assert pkg.entries() == before and z.counts['conversation_heads_added'] == 0


def test_script_closure_conversation_and_copied_subtree_are_covered():
    _, z = fixture()
    z.prov = types.SimpleNamespace(zone_package_extras=lambda ctx, zone: [])
    z.script_literals = lambda ref: set()
    z.resolve_refs = lambda *args, **kwargs: None
    z.script_text = lambda name: 'synthetic script'
    z.call_targets = lambda text: [('conversation', 'conversations/arrival')]
    z.ensure_call_target = lambda pkg, kind, rel, *args: pkg.add('xml', rel, extra=True)
    z.data_refs = lambda *args: []
    root = z.build_package('lobby', [('maps/lobby.chr', 'characters'), ('maps/lobby.xml', 'zonexml')],
                           {'zonescript': 'starter', 'refs': []}, False, False)
    entries = [(e.tag, e.get('filename')) for e in root]
    assert entries.index(('xml', 'conversations/arrival')) < entries.index(('characters', 'maps/lobby'))
    for head in ('91001', '92003'):
        assert entries.index(('model', 'hud/hud_head_' + head)) < entries.index(('characters', 'maps/lobby'))
    assert not any(k in ('actorskin', 'actoranimdb', 'fightstyle', 'xml_talents') for k, _ in entries)


def test_validator_negative_restore_and_inherited_missing_head():
    data, z = fixture()
    pkg = Z.Pkg([('xml', 'conversations/arrival')])
    z.conversation_heads('lobby', pkg)
    stats = {s.get('name'): ('synthetic', s) for name in ('herostat', 'npcstat')
             for s in data['data/' + name + '.engb']}
    v = types.SimpleNamespace(stats=lambda: {'by_name': stats},
        zone_pkg=lambda zone: pkg.entries() if zone == 'lobby' else [],
        converted_zones=lambda: ['lobby'], idx=z.ctx.out_index,
        tree=lambda rel: data[rel], exists=lambda rel: rel in data,
        x1_stats=lambda: stats,
        ctx=types.SimpleNamespace(base_index=types.SimpleNamespace(path=lambda rel: None), x1_path=lambda rel: None))
    def check():
        ck = V.Check('V-TBD', 'conversation portraits')
        V.Validator.conversation_portraits(v, ck)
        return ck
    assert not check().errors
    removed = pkg.extra.pop()
    assert len(check().errors) == 1 and 'river' in check().errors[0]
    pkg.extra.append(removed)
    assert not check().errors
    data['conversations/arrival.engb'].append(ET.Element('line', text='%mist%: Greeting'))
    ck = check()
    assert not ck.errors and len(ck.details['unavailable']) == 1 and ck.warnings
    # A renamed speaker with a lost imported asset is not an inherited gap.
    stats['river'][1].set('skin', '21101')
    v.x1_stats = lambda: {'old_river': ('synthetic', ET.Element('stats', name='old_river', skin='7101'))}
    v.ctx.x1_path = lambda rel: rel if rel == 'hud/hud_head_7101.igb' else None
    ck = check()
    assert any('river' in e and 'source head exists' in e for e in ck.errors)


def test_native_namespace_exception_requires_same_stats_and_conversation():
    data, z = fixture()
    stats = {s.get('name'): ('synthetic', s) for name in ('herostat', 'npcstat')
             for s in data['data/' + name + '.engb']}
    # Only river is kept with its native skin; ember was converted. The native
    # silent character is not a speaker in the package and must not be exempted.
    base = tree('<stats><stats name="river" skin="92003"/><stats name="ember" skin="81001"/>'
                '<stats name="mist" skin="93002"/></stats>')
    v = types.SimpleNamespace(stats=lambda: {'by_name': stats}, idx=z.ctx.out_index,
        tree=lambda rel: data[rel], ctx=types.SimpleNamespace(
            base_index=types.SimpleNamespace(find=lambda n, exts: n), read_base_xmlb=lambda rel: base))
    heads = V.Validator.native_conversation_heads(v, [('xml', 'conversations/arrival')])
    assert heads == {'hud/hud_head_92003'}
    assert V.Validator.native_conversation_heads(v, [('model', 'hud/hud_head_92003')]) == set()
